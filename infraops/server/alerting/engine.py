"""Alert evaluation engine with sustain windows, deduplication, resolution, and flap guards."""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from infraops.common.logging import setup_logger
from infraops.common.schemas import IngestBatch
from infraops.server.alerting.rules import AlertRule, load_alert_rules
from infraops.server.models import Alert, Host

logger = setup_logger("infraops.alerting")


@dataclass
class AlertTracker:
    """In-memory state tracking sustain window, resolution window, and flapping."""

    first_breach_ts: Optional[float] = None
    last_breach_ts: Optional[float] = None
    first_clear_ts: Optional[float] = None
    state_transitions: List[float] = field(default_factory=list)
    is_firing: bool = False
    is_flapping: bool = False


class AlertEngine:
    """Evaluates metrics against alert rules and manages alert lifecycle."""

    def __init__(self, rules: Optional[List[AlertRule]] = None) -> None:
        self.rules = rules if rules is not None else load_alert_rules()
        self.trackers: Dict[str, AlertTracker] = {}
        self.incident_callback: Optional[Callable[[Alert, AlertRule, Session], None]] = None

    def set_incident_callback(self, cb: Callable[[Alert, AlertRule, Session], None]) -> None:
        """Register callback invoked when a rule with a SOP triggers an alert."""
        self.incident_callback = cb

    def _get_key(self, rule_id: str, host_id: str, labels: Optional[dict] = None) -> str:
        label_str = json.dumps(labels or {}, sort_keys=True)
        return f"{rule_id}:{host_id}:{label_str}"

    def _check_flapping(self, tracker: AlertTracker, now: float) -> bool:
        """Detect rapid oscillations (>=3 transitions within 60s window)."""
        cutoff = now - 60.0
        tracker.state_transitions = [t for t in tracker.state_transitions if t >= cutoff]
        tracker.state_transitions.append(now)
        if len(tracker.state_transitions) >= 4:
            tracker.is_flapping = True
            return True
        tracker.is_flapping = False
        return False

    def evaluate_batch(self, batch: IngestBatch, db: Session) -> List[Alert]:
        """Evaluate all metrics in an ingested batch against configured rules."""
        generated_alerts: List[Alert] = []
        now = batch.ts or time.time()
        now_dt = datetime.now(timezone.utc)

        # Build metric map for efficient lookup
        for m in batch.metrics:
            matching_rules = [r for r in self.rules if r.type == "metric" and r.metric == m.name]
            for rule in matching_rules:
                key = self._get_key(rule.id, batch.host_id, m.labels)
                if key not in self.trackers:
                    self.trackers[key] = AlertTracker()

                tracker = self.trackers[key]
                breached = rule.evaluate_condition(m.value)

                if breached:
                    tracker.first_clear_ts = None
                    if tracker.first_breach_ts is None:
                        tracker.first_breach_ts = now
                    tracker.last_breach_ts = now

                    held_duration = now - tracker.first_breach_ts
                    if held_duration >= rule.for_seconds:
                        if not tracker.is_firing:
                            self._check_flapping(tracker, now)
                            tracker.is_firing = True

                            # Check existing open alert in DB (deduplication)
                            existing_alert = db.scalars(
                                select(Alert).where(
                                    Alert.rule_id == rule.id,
                                    Alert.host_id == batch.host_id,
                                    Alert.state == "firing",
                                )
                            ).first()

                            if not existing_alert:
                                summary = (
                                    rule.summary or f"{rule.id} threshold breached ({m.value})"
                                )
                                summary = summary.replace("{value}", str(m.value)).replace(
                                    "{host_id}", batch.host_id
                                )
                                alert = Alert(
                                    rule_id=rule.id,
                                    host_id=batch.host_id,
                                    severity=rule.severity,
                                    state="firing",
                                    first_seen=now_dt,
                                    last_seen=now_dt,
                                    value=m.value,
                                    summary=summary,
                                )
                                db.add(alert)
                                db.flush()
                                generated_alerts.append(alert)

                                # Trigger incident if rule specifies a SOP
                                if rule.sop and self.incident_callback is not None:
                                    self.incident_callback(alert, rule, db)
                        else:
                            # Update existing firing alert
                            existing_alert = db.scalars(
                                select(Alert).where(
                                    Alert.rule_id == rule.id,
                                    Alert.host_id == batch.host_id,
                                    Alert.state == "firing",
                                )
                            ).first()
                            if existing_alert:
                                existing_alert.last_seen = now_dt
                                existing_alert.value = m.value

                else:
                    # Condition cleared
                    tracker.first_breach_ts = None
                    if tracker.is_firing:
                        if tracker.first_clear_ts is None:
                            tracker.first_clear_ts = now

                        clear_held = now - tracker.first_clear_ts
                        if clear_held >= rule.resolve_after_seconds:
                            self._check_flapping(tracker, now)
                            tracker.is_firing = False
                            tracker.first_clear_ts = None

                            existing_alert = db.scalars(
                                select(Alert).where(
                                    Alert.rule_id == rule.id,
                                    Alert.host_id == batch.host_id,
                                    Alert.state == "firing",
                                )
                            ).first()
                            if existing_alert:
                                existing_alert.state = "resolved"
                                existing_alert.resolved_at = now_dt

        db.commit()
        return generated_alerts

    def check_stale_hosts(self, db: Session, now_dt: Optional[datetime] = None) -> List[Alert]:
        """Check for hosts that have missed heartbeats and fire stale host alerts."""
        now_dt = now_dt or datetime.now(timezone.utc)
        alerts_created: List[Alert] = []

        stale_rule = next(
            (r for r in self.rules if r.id == "host_stale" or r.type == "heartbeat"), None
        )
        stale_threshold = stale_rule.stale_after_seconds if stale_rule else 30.0

        hosts = db.scalars(select(Host)).all()
        for h in hosts:
            last_seen = h.last_seen
            if last_seen.tzinfo is None and now_dt.tzinfo is not None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            elif last_seen.tzinfo is not None and now_dt.tzinfo is None:
                now_dt = now_dt.replace(tzinfo=timezone.utc)

            delta_seconds = (now_dt - last_seen).total_seconds()
            if delta_seconds > stale_threshold:
                if h.status != "stale":
                    h.status = "stale"

                # Check if firing alert already exists
                existing = db.scalars(
                    select(Alert).where(
                        Alert.rule_id == "host_stale",
                        Alert.host_id == h.id,
                        Alert.state == "firing",
                    )
                ).first()
                if not existing:
                    alert = Alert(
                        rule_id="host_stale",
                        host_id=h.id,
                        severity=stale_rule.severity if stale_rule else "P1",
                        state="firing",
                        first_seen=now_dt,
                        last_seen=now_dt,
                        value=delta_seconds,
                        summary=f"Host {h.id} is stale (no heartbeat for {int(delta_seconds)}s)",
                    )
                    db.add(alert)
                    alerts_created.append(alert)
            else:
                # Host reported in time: resolve stale alert if any
                if h.status == "stale":
                    h.status = "up"
                existing = db.scalars(
                    select(Alert).where(
                        Alert.rule_id == "host_stale",
                        Alert.host_id == h.id,
                        Alert.state == "firing",
                    )
                ).first()
                if existing:
                    existing.state = "resolved"
                    existing.resolved_at = now_dt

        db.commit()
        return alerts_created
