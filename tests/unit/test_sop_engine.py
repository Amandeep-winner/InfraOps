"""Unit tests for the SOP execution engine, approvals, and escalation logic."""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from infraops.server.incidents.service import IncidentService
from infraops.server.models import Approval, Base, Host
from infraops.server.sop.engine import SOPEngine
from infraops.server.sop.loader import EscalationConfig, SOPModel, SOPStep, SOPTrigger


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "sop_engine_test.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Host(id="host-sop-1", hostname="host-sop-1"))
        session.commit()
        yield session


def make_dummy_sop(requires_approval: bool = False, fail_verify: bool = False) -> SOPModel:
    """Helper creating a test SOP."""
    steps = [
        SOPStep(
            id="step_inv1",
            phase="investigate",
            name="Collect snapshot",
            action="notify",
            params={"msg": "snap"},
        ),
        SOPStep(
            id="step_inv2",
            phase="investigate",
            name="Top procs",
            action="notify",
            params={"msg": "procs"},
        ),
        SOPStep(
            id="step_id1",
            phase="identify",
            name="Identify offender",
            action="notify",
            params={"msg": "found"},
            store_as="offender",
        ),
        SOPStep(
            id="step_rem1",
            phase="remediate",
            name="Restart service",
            action="notify",
            params={"msg": "restarted"},
            requires_approval_in_manual=requires_approval,
        ),
        SOPStep(
            id="step_ver1",
            phase="verify",
            name="Verify recovery",
            action="test_verify_action",
            params={"fail": fail_verify},
        ),
    ]
    return SOPModel(
        id="SOP-TEST",
        title="Test Procedure",
        trigger=SOPTrigger(alert_rule="test_alert"),
        owner="L1",
        description="Test SOP description",
        steps=steps,
        rollback_note="No changes",
        escalation=EscalationConfig(if_failed="Escalate to L2 engineering"),
    )


def test_sop_auto_mode_success(db_session, monkeypatch):
    """Verify auto mode executes all steps sequentially and resolves the incident."""
    sop = make_dummy_sop(requires_approval=True, fail_verify=False)

    def fake_executor(action, params):
        if action == "test_verify_action":
            return True
        return "fake_ok"

    engine = SOPEngine(action_executor=fake_executor)
    monkeypatch.setattr(engine, "get_sop", lambda sid: sop)

    inc = IncidentService.create_incident(
        db_session, "Auto Mode Test", "host-sop-1", sop_id="SOP-TEST"
    )
    success = engine.run_sop(
        sop_id="SOP-TEST",
        incident_id=inc.id,
        host_id="host-sop-1",
        db=db_session,
        mode="auto",
    )
    assert success is True
    db_session.refresh(inc)
    assert inc.state == "RESOLVED"
    assert inc.resolved_at is not None


def test_sop_manual_mode_pause_and_approve(db_session, monkeypatch):
    """Verify manual mode pauses on approval-required steps and resumes upon approval."""
    sop = make_dummy_sop(requires_approval=True, fail_verify=False)

    def fake_executor(action, params):
        return True

    engine = SOPEngine(action_executor=fake_executor)
    monkeypatch.setattr(engine, "get_sop", lambda sid: sop)

    inc = IncidentService.create_incident(
        db_session, "Manual Approval Test", "host-sop-1", sop_id="SOP-TEST"
    )

    # First run in manual mode: should pause on remediation step
    res1 = engine.run_sop(
        sop_id="SOP-TEST",
        incident_id=inc.id,
        host_id="host-sop-1",
        db=db_session,
        mode="manual",
    )
    assert res1 is False

    # Check pending approval exists
    approval = db_session.scalars(
        select(Approval).where(Approval.incident_id == inc.id, Approval.step_id == "step_rem1")
    ).first()
    assert approval is not None
    assert approval.state == "pending"

    # Operator approves step
    approval.state = "approved"
    db_session.commit()

    # Second run resumes and finishes to RESOLVED
    res2 = engine.run_sop(
        sop_id="SOP-TEST",
        incident_id=inc.id,
        host_id="host-sop-1",
        db=db_session,
        mode="manual",
    )
    assert res2 is True
    db_session.refresh(inc)
    assert inc.state == "RESOLVED"


def test_sop_verify_failure_retries_and_escalates(db_session, monkeypatch):
    """Verify verification failure retries remediation then escalates to L2."""
    sop = make_dummy_sop(requires_approval=False, fail_verify=True)

    call_count = {"remediate": 0, "verify": 0}

    def fake_executor(action, params):
        if action == "test_verify_action":
            call_count["verify"] += 1
            return False  # Verification fails
        call_count["remediate"] += 1
        return "ok"

    engine = SOPEngine(action_executor=fake_executor)
    monkeypatch.setattr(engine, "get_sop", lambda sid: sop)

    inc = IncidentService.create_incident(
        db_session, "Failing SOP Test", "host-sop-1", sop_id="SOP-TEST"
    )
    success = engine.run_sop(
        sop_id="SOP-TEST",
        incident_id=inc.id,
        host_id="host-sop-1",
        db=db_session,
        mode="auto",
        max_retries=2,
    )
    assert success is False
    db_session.refresh(inc)
    assert inc.state == "ESCALATED"
    # Initial attempt + 2 retries = 3 verification attempts
    assert call_count["verify"] == 3
