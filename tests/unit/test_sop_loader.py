"""Unit tests for SOP YAML schema parsing and validation."""

import pytest
import yaml

from infraops.server.sop.loader import load_all_sops, load_sop_file


def test_load_all_six_sops():
    """Verify all 6 required SOPs are present and strictly comply with schema."""
    sops = load_all_sops("sops")
    assert len(sops) == 6

    expected_ids = {"SOP-001", "SOP-002", "SOP-003", "SOP-004", "SOP-005", "SOP-006"}
    assert set(sops.keys()) == expected_ids

    for sop_id, sop in sops.items():
        assert sop.id == sop_id
        assert len(sop.title) > 0
        assert sop.trigger.alert_rule
        assert len(sop.description) > 0
        assert sop.rollback_note
        assert sop.escalation.if_failed

        # Check phase breakdown per Section 9.6
        phases = [step.phase for step in sop.steps]
        assert phases.count("investigate") >= 2
        assert "identify" in phases
        assert "remediate" in phases
        assert "verify" in phases


def test_invalid_sop_rejected(tmp_path):
    """Verify invalid SOP files are rejected with clear validation errors."""
    # Missing required trigger
    bad_data = {
        "id": "SOP-BAD",
        "title": "Bad SOP",
        "owner": "L1",
        "description": "Missing trigger",
        "steps": [],
        "escalation": {"if_failed": "escalate"},
    }
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text(yaml.dump(bad_data))

    with pytest.raises(Exception):
        load_sop_file(bad_file)


def test_invalid_phase_rejected(tmp_path):
    """Verify steps with illegal phase names are rejected."""
    bad_phase = {
        "id": "SOP-INVALID-PHASE",
        "title": "Invalid Phase",
        "trigger": {"alert_rule": "test"},
        "owner": "L1",
        "description": "Bad phase",
        "steps": [
            {
                "id": "s1",
                "phase": "destroy_world",  # Illegal phase
                "name": "Invalid",
                "action": "notify",
            }
        ],
        "escalation": {"if_failed": "escalate"},
    }
    bad_file = tmp_path / "bad_phase.yaml"
    bad_file.write_text(yaml.dump(bad_phase))

    with pytest.raises(Exception):
        load_sop_file(bad_file)
