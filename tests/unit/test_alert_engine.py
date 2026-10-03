"""Table-driven unit tests for the Alert Engine (sustain, dedupe, resolve, flap guard, heartbeat)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from infraops.common.schemas import IngestBatch, MetricPoint
from infraops.server.alerting.engine import AlertEngine
from infraops.server.alerting.rules import AlertRule
from infraops.server.models import Alert, Base, Host


@pytest.fixture
def db_session():
    """Isolated in-memory SQLite database session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.mark.parametrize(
    "op,threshold,val_pass,val_fail",
    [
        (">", 80.0, 85.0, 75.0),
        (">=", 80.0, 80.0, 79.9),
        ("<", 20.0, 15.0, 25.0),
        ("<=", 20.0, 20.0, 20.1),
        ("==", 0.0, 0.0, 1.0),
    ],
)
def test_rule_condition_operators(op, threshold, val_pass, val_fail):
    """Verify all comparison operators evaluate correctly."""
    rule = AlertRule(
        id=f"test_rule_{op}",
        metric="test.metric",
        op=op,
        threshold=threshold,
        for_seconds=0.0,
    )
    assert rule.evaluate_condition(val_pass) is True
    assert rule.evaluate_condition(val_fail) is False


def test_sustain_window_and_deduplication(db_session):
    """Verify alert only fires after sustain duration holds and deduplicates existing alerts."""
    rule = AlertRule(
        id="cpu_sustain",
        metric="cpu.percent",
        op=">",
        threshold=80.0,
        for_seconds=10.0,
        resolve_after_seconds=5.0,
        severity="P2",
    )
    engine = AlertEngine([rule])
    host_id = "node-1"

    t0 = 1000.0
    # Batch 1 at t=0s: breached, but held for 0s < 10s -> not firing
    b1 = IngestBatch(
        host_id=host_id, ts=t0, metrics=[MetricPoint(name="cpu.percent", value=90.0, ts=t0)]
    )
    alerts1 = engine.evaluate_batch(b1, db_session)
    assert len(alerts1) == 0
    assert len(db_session.scalars(select(Alert)).all()) == 0

    # Batch 2 at t=5s: breached, held for 5s < 10s -> still not firing
    t1 = t0 + 5.0
    b2 = IngestBatch(
        host_id=host_id, ts=t1, metrics=[MetricPoint(name="cpu.percent", value=92.0, ts=t1)]
    )
    alerts2 = engine.evaluate_batch(b2, db_session)
    assert len(alerts2) == 0

    # Batch 3 at t=11s: breached, held for 11s >= 10s -> FIRES!
    t2 = t0 + 11.0
    b3 = IngestBatch(
        host_id=host_id, ts=t2, metrics=[MetricPoint(name="cpu.percent", value=95.0, ts=t2)]
    )
    alerts3 = engine.evaluate_batch(b3, db_session)
    assert len(alerts3) == 1
    assert alerts3[0].state == "firing"
    assert alerts3[0].value == 95.0
    assert len(db_session.scalars(select(Alert)).all()) == 1

    # Batch 4 at t=15s: still breached -> deduplicated, no new row created, value updated
    t3 = t0 + 15.0
    b4 = IngestBatch(
        host_id=host_id, ts=t3, metrics=[MetricPoint(name="cpu.percent", value=97.0, ts=t3)]
    )
    alerts4 = engine.evaluate_batch(b4, db_session)
    assert len(alerts4) == 0  # Deduplicated
    assert len(db_session.scalars(select(Alert)).all()) == 1
    active_alert = db_session.scalars(select(Alert)).first()
    assert active_alert.value == 97.0


def test_auto_resolution(db_session):
    """Verify firing alert automatically resolves when clear condition holds for resolve window."""
    rule = AlertRule(
        id="mem_resolve",
        metric="mem.percent",
        op=">",
        threshold=80.0,
        for_seconds=0.0,
        resolve_after_seconds=5.0,
    )
    engine = AlertEngine([rule])
    host_id = "node-mem"

    # Fire immediately
    t0 = 2000.0
    b0 = IngestBatch(
        host_id=host_id, ts=t0, metrics=[MetricPoint(name="mem.percent", value=85.0, ts=t0)]
    )
    alerts = engine.evaluate_batch(b0, db_session)
    assert len(alerts) == 1
    assert alerts[0].state == "firing"

    # Value normalizes at t=2s, but held clear for 0s < 5s -> remains firing
    t1 = t0 + 2.0
    b1 = IngestBatch(
        host_id=host_id, ts=t1, metrics=[MetricPoint(name="mem.percent", value=40.0, ts=t1)]
    )
    engine.evaluate_batch(b1, db_session)
    alert = db_session.scalars(select(Alert)).first()
    assert alert.state == "firing"

    # At t=8s, clear has held for 6s >= 5s -> transitions to resolved
    t2 = t0 + 8.0
    b2 = IngestBatch(
        host_id=host_id, ts=t2, metrics=[MetricPoint(name="mem.percent", value=42.0, ts=t2)]
    )
    engine.evaluate_batch(b2, db_session)
    alert = db_session.scalars(select(Alert)).first()
    assert alert.state == "resolved"
    assert alert.resolved_at is not None


def test_flapping_guard(db_session):
    """Verify rapid oscillation triggers flapping detection."""
    rule = AlertRule(
        id="flap_test",
        metric="net.flapping",
        op=">",
        threshold=50.0,
        for_seconds=0.0,
        resolve_after_seconds=0.0,
    )
    engine = AlertEngine([rule])
    host_id = "node-flap"
    key = f"flap_test:{host_id}:{{}}"

    now = 3000.0
    for i in range(5):
        val = 60.0 if i % 2 == 0 else 20.0
        b = IngestBatch(
            host_id=host_id,
            ts=now + i,
            metrics=[MetricPoint(name="net.flapping", value=val, ts=now + i)],
        )
        engine.evaluate_batch(b, db_session)

    tracker = engine.trackers[key]
    assert tracker.is_flapping is True


def test_stale_host_heartbeat_check(db_session):
    """Verify stale host detection and subsequent recovery."""
    rule = AlertRule(
        id="host_stale",
        type="heartbeat",
        stale_after_seconds=20.0,
        severity="P1",
    )
    engine = AlertEngine([rule])

    now = datetime.now(timezone.utc)
    # Host reported 30 seconds ago
    h = Host(
        id="stale-box",
        hostname="stale-box",
        last_seen=now - timedelta(seconds=30),
        status="up",
    )
    db_session.add(h)
    db_session.commit()

    # Run check -> fires alert and sets status stale
    created_alerts = engine.check_stale_hosts(db_session, now)
    assert len(created_alerts) == 1
    assert created_alerts[0].rule_id == "host_stale"
    assert created_alerts[0].severity == "P1"
    assert h.status == "stale"

    # Host reports in fresh (e.g. heartbeat 2 seconds ago)
    h.last_seen = now - timedelta(seconds=2)
    db_session.commit()

    engine.check_stale_hosts(db_session, now)
    assert h.status == "up"
    alert = db_session.scalars(select(Alert).where(Alert.rule_id == "host_stale")).first()
    assert alert.state == "resolved"
