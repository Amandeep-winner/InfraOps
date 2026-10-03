"""Unit tests for incident management, sequential IDs, state machine, and report generator."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from infraops.server.incidents.reports import generate_incident_report
from infraops.server.incidents.service import (
    IncidentService,
    InvalidStateTransitionError,
)
from infraops.server.models import Base, Host


@pytest.fixture
def db_session(tmp_path):
    """Isolated file-backed or memory SQLite session."""
    db_file = tmp_path / "incidents_test.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        # Pre-seed host
        h = Host(id="web-01", hostname="web-01")
        session.add(h)
        session.commit()
        yield session


def test_sequential_id_generation(db_session):
    """Verify IDs follow INC-001, INC-002, etc."""
    id1 = IncidentService.generate_next_id(db_session)
    assert id1 == "INC-001"

    inc1 = IncidentService.create_incident(db_session, "First Incident", "web-01")
    assert inc1.id == "INC-001"

    id2 = IncidentService.generate_next_id(db_session)
    assert id2 == "INC-002"

    inc2 = IncidentService.create_incident(db_session, "Second Incident", "web-01")
    assert inc2.id == "INC-002"


def test_concurrent_id_generation(tmp_path):
    """Verify sequential ID uniqueness under multithreaded concurrent incident creation."""
    db_file = tmp_path / "concurrent_incidents.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"timeout": 30})
    Base.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(Host(id="web-concurrent", hostname="web-concurrent"))
        s.commit()

    def worker(i):
        with Session(engine) as session:
            inc = IncidentService.create_incident(session, f"Incident {i}", "web-concurrent")
            return inc.id

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(worker, range(10)))

    assert len(results) == 10
    assert len(set(results)) == 10  # All IDs must be unique
    sorted_ids = sorted(results)
    assert sorted_ids[0] == "INC-001"
    assert sorted_ids[-1] == "INC-010"


def test_valid_state_machine_lifecycle(db_session):
    """Verify standard happy-path progression through the complete incident lifecycle."""
    inc = IncidentService.create_incident(
        db_session, "High CPU Alert", "web-01", severity="P1", sop_id="SOP-001"
    )
    assert inc.state == "DETECTED"

    # DETECTED -> INVESTIGATING
    inc = IncidentService.transition_state(db_session, inc.id, "INVESTIGATING", actor="sop")
    assert inc.state == "INVESTIGATING"

    # INVESTIGATING -> IDENTIFIED
    inc = IncidentService.transition_state(db_session, inc.id, "IDENTIFIED", actor="sop")
    assert inc.state == "IDENTIFIED"

    # IDENTIFIED -> REMEDIATING
    inc = IncidentService.transition_state(db_session, inc.id, "REMEDIATING", actor="sop")
    assert inc.state == "REMEDIATING"

    # REMEDIATING -> VERIFYING
    inc = IncidentService.transition_state(db_session, inc.id, "VERIFYING", actor="sop")
    assert inc.state == "VERIFYING"

    # VERIFYING -> RESOLVED
    inc = IncidentService.transition_state(db_session, inc.id, "RESOLVED", actor="sop")
    assert inc.state == "RESOLVED"
    assert inc.resolved_at is not None

    # RESOLVED -> CLOSED
    inc = IncidentService.close_incident(
        db_session, inc.id, actor="operator", resolution_summary="Offender terminated"
    )
    assert inc.state == "CLOSED"
    assert inc.closed_at is not None
    assert inc.resolution_summary == "Offender terminated"


def test_verify_failure_retry_and_escalate(db_session):
    """Verify verify failure transitions back to REMEDIATING and can escalate to ESCALATED."""
    inc = IncidentService.create_incident(db_session, "Failing Incident", "web-01")
    IncidentService.transition_state(db_session, inc.id, "INVESTIGATING")
    IncidentService.transition_state(db_session, inc.id, "IDENTIFIED")
    IncidentService.transition_state(db_session, inc.id, "REMEDIATING")
    IncidentService.transition_state(db_session, inc.id, "VERIFYING")

    # Verify fails -> retry remediation
    inc = IncidentService.transition_state(
        db_session, inc.id, "REMEDIATING", message="Verification failed: retry 1"
    )
    assert inc.state == "REMEDIATING"

    IncidentService.transition_state(db_session, inc.id, "VERIFYING")

    # Verify fails again -> escalate to L2
    inc = IncidentService.transition_state(
        db_session, inc.id, "ESCALATED", message="Max retries exceeded: handoff to L2"
    )
    assert inc.state == "ESCALATED"


def test_invalid_state_transitions_raise(db_session):
    """Verify illegal transitions raise InvalidStateTransitionError."""
    inc = IncidentService.create_incident(db_session, "Invalid Flow", "web-01")
    assert inc.state == "DETECTED"

    # Cannot jump directly from DETECTED to RESOLVED
    with pytest.raises(InvalidStateTransitionError):
        IncidentService.transition_state(db_session, inc.id, "RESOLVED")

    # Cannot close an incident that is only DETECTED
    with pytest.raises(InvalidStateTransitionError):
        IncidentService.close_incident(db_session, inc.id)


def test_incident_report_generation(db_session, tmp_path):
    """Verify report formatting, timeline inclusion, and disk persistence."""
    inc = IncidentService.create_incident(
        db_session,
        "Disk Exhaustion Outage",
        "web-01",
        severity="P1",
        sop_id="SOP-003",
    )
    IncidentService.transition_state(db_session, inc.id, "INVESTIGATING")
    IncidentService.record_event(
        db_session, inc.id, "investigate", "sop", "Captured df -h snapshot"
    )
    IncidentService.transition_state(db_session, inc.id, "IDENTIFIED")
    IncidentService.transition_state(db_session, inc.id, "REMEDIATING")
    IncidentService.record_event(
        db_session, inc.id, "remediate", "sop", "Deleted 45MB of rotated test logs"
    )
    IncidentService.transition_state(db_session, inc.id, "VERIFYING")
    IncidentService.record_event(
        db_session, inc.id, "verify", "sop", "Disk utilization dropped to 52%"
    )
    IncidentService.transition_state(db_session, inc.id, "RESOLVED")

    report_md = generate_incident_report(inc.id, db_session, reports_dir=str(tmp_path / "reports"))

    assert f"# Incident Post-Mortem Report: {inc.id}" in report_md
    assert "Disk Exhaustion Outage" in report_md
    assert "Mean Time to Resolve (MTTR)" in report_md
    assert "Incident Timeline" in report_md
    assert "Deleted 45MB of rotated test logs" in report_md
    assert "Disk utilization dropped to 52%" in report_md

    # Check file exists on disk
    expected_file = tmp_path / "reports" / f"{inc.id}.md"
    assert expected_file.exists()
    assert expected_file.read_text(encoding="utf-8") == report_md
