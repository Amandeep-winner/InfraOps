"""Incident lifecycle service, state machine enforcement, and event timeline."""

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from infraops.server.models import Incident, IncidentEvent


class InvalidStateTransitionError(Exception):
    """Raised when an illegal incident lifecycle transition is attempted."""


# Valid transition map
VALID_TRANSITIONS = {
    "DETECTED": {"INVESTIGATING"},
    "INVESTIGATING": {"IDENTIFIED", "ESCALATED"},
    "IDENTIFIED": {"REMEDIATING", "ESCALATED"},
    "REMEDIATING": {"VERIFYING", "ESCALATED"},
    "VERIFYING": {"RESOLVED", "REMEDIATING", "ESCALATED"},
    "RESOLVED": {"CLOSED"},
    "CLOSED": set(),
    "ESCALATED": {"INVESTIGATING", "CLOSED"},
}

_id_lock = threading.Lock()


class IncidentService:
    """Manages creation, state progression, and event tracking for incidents."""

    @staticmethod
    def _generate_next_id_locked(db: Session) -> str:
        latest = db.scalars(select(Incident.id).order_by(Incident.id.desc())).first()
        if not latest or not latest.startswith("INC-"):
            return "INC-001"
        try:
            num = int(latest.split("-")[1])
            return f"INC-{num + 1:03d}"
        except (IndexError, ValueError):
            return "INC-001"

    @classmethod
    def generate_next_id(cls, db: Session) -> str:
        """Atomically generate sequential INC-xxx identifier (e.g. INC-001)."""
        with _id_lock:
            return cls._generate_next_id_locked(db)

    @classmethod
    def create_incident(
        cls,
        db: Session,
        title: str,
        host_id: str,
        severity: str = "P2",
        sop_id: Optional[str] = None,
        mode: str = "auto",
        initial_event_msg: Optional[str] = None,
    ) -> Incident:
        """Create and persist a new incident in DETECTED state with writer locking."""
        with _id_lock:
            inc_id = cls._generate_next_id_locked(db)
            now_dt = datetime.now(timezone.utc)
            now_ts = time.time()

            incident = Incident(
                id=inc_id,
                title=title,
                host_id=host_id,
                severity=severity,
                state="DETECTED",
                sop_id=sop_id,
                opened_at=now_dt,
                mode=mode,
            )
            db.add(incident)
            db.flush()

            # Add initial detect event
            detect_event = IncidentEvent(
                incident_id=inc_id,
                ts=now_ts,
                phase="detect",
                actor="system",
                message=initial_event_msg or f"Incident detected: {title}",
                data={"severity": severity, "sop_id": sop_id},
            )
            db.add(detect_event)
            db.commit()
            db.refresh(incident)
            return incident

    @classmethod
    def transition_state(
        cls,
        db: Session,
        incident_id: str,
        new_state: str,
        actor: str = "system",
        message: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        phase: Optional[str] = None,
    ) -> Incident:
        """Transition incident state, validating legal state machine progression."""
        incident = db.get(Incident, incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")

        current_state = incident.state
        allowed = VALID_TRANSITIONS.get(current_state, set())
        if new_state not in allowed:
            raise InvalidStateTransitionError(
                f"Illegal state transition from {current_state} to {new_state} for {incident_id}. "
                f"Allowed transitions: {sorted(list(allowed))}"
            )

        now_dt = datetime.now(timezone.utc)
        now_ts = time.time()
        incident.state = new_state

        if new_state == "RESOLVED" and incident.resolved_at is None:
            incident.resolved_at = now_dt
        elif new_state == "CLOSED" and incident.closed_at is None:
            incident.closed_at = now_dt

        # Map state to phase for audit log
        event_phase = phase or new_state.lower()
        if event_phase == "escalated":
            event_phase = "note"

        event = IncidentEvent(
            incident_id=incident_id,
            ts=now_ts,
            phase=event_phase,
            actor=actor,
            message=message or f"State transitioned to {new_state}",
            data=data or {},
        )
        db.add(event)
        db.commit()
        db.refresh(incident)
        return incident

    @classmethod
    def record_event(
        cls,
        db: Session,
        incident_id: str,
        phase: str,
        actor: str,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> IncidentEvent:
        """Append an audit timeline event to the incident without altering its state."""
        event = IncidentEvent(
            incident_id=incident_id,
            ts=time.time(),
            phase=phase,
            actor=actor,
            message=message,
            data=data or {},
        )
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    @classmethod
    def close_incident(
        cls,
        db: Session,
        incident_id: str,
        actor: str = "human",
        resolution_summary: Optional[str] = None,
    ) -> Incident:
        """Close an incident that has reached RESOLVED state."""
        incident = db.get(Incident, incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")

        if incident.state != "RESOLVED":
            raise InvalidStateTransitionError(
                f"Cannot close incident {incident_id} in state '{incident.state}'. Must be RESOLVED first."
            )

        if resolution_summary:
            incident.resolution_summary = resolution_summary

        return cls.transition_state(
            db=db,
            incident_id=incident_id,
            new_state="CLOSED",
            actor=actor,
            message=f"Incident closed by {actor}. Resolution: {resolution_summary or 'Verified fixed'}",
            phase="close",
        )
