"""Targeted unit tests to ensure high test coverage and edge case handling across InfraOps."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from infraops.agent.action_api import app as agent_app
from infraops.agent.collectors.http import HttpCollector
from infraops.common.config import get_settings
from infraops.common.sandbox import get_sandbox_dir
from infraops.server.app import app as server_app
from infraops.server.db import get_engine
from infraops.server.incidents.service import IncidentService
from infraops.server.models import Approval, Host, Incident
from infraops.server.netutils.cidr import (
    check_overlap,
    split_cidr,
    validate_cidr,
)
from infraops.server.sop.actions import (
    action_check_logs,
    action_clean_path,
    action_disk_report,
    action_dns_diagnose,
    action_dns_switch_resolver,
    action_find_large_files,
    action_memory_report,
    action_notify,
    action_ping_check,
    action_service_restart,
    action_service_start,
    action_service_status,
    action_tcp_check,
    action_traceroute_lite,
    execute_action,
)
from infraops.server.sop.verify import (
    verify_http_endpoint,
    verify_metric_condition,
    verify_service_running,
)


@pytest.fixture
def auth_headers():
    settings = get_settings()
    return {"X-API-Key": settings.api_key}


@pytest.fixture
def test_host():
    engine = get_engine()
    with Session(engine) as db:
        host = db.get(Host, "test-cov-host")
        if not host:
            host = Host(
                id="test-cov-host",
                hostname="test-cov-host",
                os="Linux 6.1",
                ip="10.0.0.99",
                status="online",
                kind="linux",
            )
            db.add(host)
            db.commit()
    return "test-cov-host"


# 1. Action API tests
def test_agent_action_api(auth_headers):
    client = TestClient(agent_app)
    # Health endpoint
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

    # Unauthorized action execution
    res = client.post("/agent/action", json={"action": "notify", "params": {"message": "hello"}})
    assert res.status_code == 401

    # Authorized successful action
    res = client.post(
        "/agent/action",
        json={"action": "notify", "params": {"message": "hello agent"}},
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["output"] == "hello agent"

    # Authorized failed action (invalid action name)
    res = client.post(
        "/agent/action",
        json={"action": "nonexistent_action", "params": {}},
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is False
    assert "not in the security allowlist" in data["error"]


# 2. HTTP Collector tests
def test_http_collector():
    collector = HttpCollector(
        config={
            "checks": [
                {
                    "name": "mock_http",
                    "url": "http://127.0.0.1:8081/health",
                    "expect_status": 200,
                    "timeout": 1.0,
                },
                {
                    "name": "mock_https",
                    "url": "https://example.com/api",
                    "expect_status": 200,
                    "timeout": 1.0,
                },
            ]
        }
    )

    # Test TLS helper directly
    assert collector._get_tls_days_remaining("invalid.local.domain", 443) is None

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client.get", return_value=mock_resp):
        with patch.object(collector, "_get_tls_days_remaining", return_value=45.5):
            metrics, snap, logs = collector.collect()
            assert len(metrics) >= 6
            metric_names = [m.name for m in metrics]
            assert "http.up" in metric_names
            assert "http.status" in metric_names
            assert "http.latency_ms" in metric_names
            assert "tls.days_to_expiry" in metric_names


# 3. SOP Verify predicates
def test_sop_verify_metric():
    mock_db = MagicMock()
    # No metric found
    mock_db.scalars.return_value.first.return_value = None
    assert (
        verify_metric_condition(
            {"metric": "cpu.percent", "op": "<", "threshold": 50, "within_seconds": 0.1},
            mock_db,
            "h1",
        )
        is False
    )

    # Metric matches condition operators
    for op, val, thresh, expected in [
        ("<", 40.0, 50.0, True),
        ("<=", 50.0, 50.0, True),
        (">", 60.0, 50.0, True),
        (">=", 50.0, 50.0, True),
        ("==", 50.0, 50.0, True),
        ("<", 60.0, 50.0, False),
    ]:
        mock_m = MagicMock()
        mock_m.value = val
        mock_db.scalars.return_value.first.return_value = mock_m
        res = verify_metric_condition(
            {"metric": "test", "op": op, "threshold": thresh, "within_seconds": 0.1},
            mock_db,
            "h1",
        )
        assert res is expected


def test_sop_verify_http():
    with patch("httpx.Client.get") as mock_get:
        mock_get.return_value.status_code = 200
        assert verify_http_endpoint({"url": "http://test", "within_seconds": 0.1}) is True

    with patch("httpx.Client.get", side_effect=Exception("Connection refused")):
        assert verify_http_endpoint({"url": "http://test", "within_seconds": 0.1}) is False


def test_sop_verify_service():
    with patch("infraops.demo.supervisor.ServiceManager.is_running", return_value=True):
        assert verify_service_running({"service": "demo-service"}) is True


# 4. SOP Actions
def test_sop_actions():
    sandbox = get_sandbox_dir()

    # Memory report
    mem = action_memory_report({})
    assert "total_mb" in mem
    assert "available_mb" in mem
    assert "percent" in mem

    # Disk report
    disk = action_disk_report({"path": str(sandbox)})
    assert "total_mb" in disk
    assert "free_mb" in disk

    # Check logs
    assert "not found" in action_check_logs({"file": str(sandbox / "nonexistent.log")})[0]

    # DNS diagnose
    dns_res = action_dns_diagnose({"names": ["localhost", "invalid-domain-xyz-123.test"]})
    assert "localhost" in dns_res
    assert dns_res["localhost"]["resolved"] is True
    assert dns_res["invalid-domain-xyz-123.test"]["resolved"] is False

    # DNS switch resolver
    flag_res = action_dns_switch_resolver(
        {"remove_flag": str(sandbox / "faults" / "nonexistent_flag")}
    )
    assert "already clear" in flag_res

    # Ping check
    ping_res = action_ping_check({"target": "127.0.0.1"})
    assert ping_res["reachable"] is True

    # TCP check
    tcp_res = action_tcp_check({"host": "127.0.0.1", "port": 65530})
    assert tcp_res["open"] is False

    # Traceroute lite
    trace = action_traceroute_lite({"host": "127.0.0.1"})
    assert trace["hops"] == 1

    # Notify
    assert action_notify({"message": "test note"}) == "test note"

    # Service actions with mock
    with patch("infraops.demo.supervisor.ServiceManager.is_running", return_value=True):
        with patch("infraops.demo.supervisor.ServiceManager.get_pid", return_value=1234):
            status_res = action_service_status({"service": "demo-service"})
            assert status_res["running"] is True
            assert status_res["pid"] == 1234

    with patch("infraops.demo.supervisor.ServiceManager.start"):
        with patch("infraops.demo.supervisor.ServiceManager.get_pid", return_value=1234):
            assert "started" in action_service_start({"service": "demo-service"})

    with patch("infraops.demo.supervisor.ServiceManager.restart"):
        with patch("infraops.demo.supervisor.ServiceManager.get_pid", return_value=1234):
            assert "restarted" in action_service_restart({"service": "demo-service"})

    # Large files and clean path in sandbox
    test_file = sandbox / "data" / "test_large_file.tmp"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("sample content " * 100)

    found = action_find_large_files({"path": str(sandbox / "data"), "pattern": "*.tmp"})
    assert len(found) >= 1

    clean_res = action_clean_path({"path": str(sandbox / "data"), "pattern": "*.tmp"})
    assert clean_res["files_deleted"] >= 1
    assert not test_file.exists()

    # Unknown action execution
    with pytest.raises(ValueError, match="security allowlist"):
        execute_action("unauthorized_action", {})


# 5. Incident & SOP API routes
def test_incident_api_endpoints(test_host, auth_headers):
    client = TestClient(server_app)
    engine = get_engine()

    # Create an incident to test API endpoints
    with Session(engine) as db:
        inc = IncidentService.create_incident(
            db=db,
            title="Coverage Test Incident",
            host_id=test_host,
            severity="P2",
            sop_id="SOP-001",
            mode="manual",
            initial_event_msg="Incident opened for API coverage",
        )
        inc_id = inc.id

        # Add a pending approval
        approval = Approval(
            incident_id=inc_id,
            step_id="step-approve",
            state="pending",
            requested_at=datetime.now(timezone.utc),
        )
        db.add(approval)
        db.commit()

    # GET /api/v1/incidents with filter
    res = client.get(
        f"/api/v1/incidents?state=DETECTED&severity=P2&host_id={test_host}", headers=auth_headers
    )
    assert res.status_code == 200
    items = res.json()
    assert any(i["id"] == inc_id for i in items)

    # GET /api/v1/incidents/{id}
    res = client.get(f"/api/v1/incidents/{inc_id}", headers=auth_headers)
    assert res.status_code == 200
    detail = res.json()
    assert detail["incident"]["id"] == inc_id
    assert len(detail["approvals"]) >= 1

    # 404 for missing incident
    res = client.get("/api/v1/incidents/INC-999999", headers=auth_headers)
    assert res.status_code == 404

    # POST /api/v1/incidents/{id}/note
    res = client.post(
        f"/api/v1/incidents/{inc_id}/note",
        json={"message": "Investigating high load", "actor": "noc_operator"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert "Note recorded" in res.json()["message"]

    # POST /api/v1/incidents/{id}/approve/{step_id}
    res = client.post(f"/api/v1/incidents/{inc_id}/approve/step-approve", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["state"] == "approved"

    # POST /api/v1/incidents/{id}/reject/{step_id} (pending not found now)
    res = client.post(f"/api/v1/incidents/{inc_id}/reject/step-approve", headers=auth_headers)
    assert res.status_code == 404

    # GET /api/v1/incidents/{id}/report
    res = client.get(f"/api/v1/incidents/{inc_id}/report", headers=auth_headers)
    assert res.status_code == 200
    assert "Incident Post-Mortem Report" in res.text

    # Close incident (should fail before resolved, succeed after resolved)
    res = client.post(
        f"/api/v1/incidents/{inc_id}/close",
        json={"resolution_summary": "Done"},
        headers=auth_headers,
    )
    # Cannot close from OPEN / REMEDIATING directly without RESOLVED
    assert res.status_code == 400

    with Session(engine) as db:
        inc = db.get(Incident, inc_id)
        inc.state = "RESOLVED"
        db.commit()

    res = client.post(
        f"/api/v1/incidents/{inc_id}/close",
        json={"resolution_summary": "Resolved after review"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.json()["state"] == "CLOSED"


def test_sop_api_endpoints(test_host, auth_headers):
    client = TestClient(server_app)

    # GET /api/v1/sops
    res = client.get("/api/v1/sops", headers=auth_headers)
    assert res.status_code == 200
    sops = res.json()
    assert len(sops) >= 6

    # GET /api/v1/sops/{id}
    res = client.get("/api/v1/sops/SOP-001", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["id"] == "SOP-001"

    # 404 for unknown SOP
    res = client.get("/api/v1/sops/SOP-UNKNOWN", headers=auth_headers)
    assert res.status_code == 404

    # POST /api/v1/sops/{id}/run on unknown host
    res = client.post("/api/v1/sops/SOP-001/run?host_id=nonexistent-host", headers=auth_headers)
    assert res.status_code == 404


def test_tools_api_endpoints(auth_headers):
    client = TestClient(server_app)

    # /api/v1/tools/cidr
    res = client.get("/api/v1/tools/cidr?cidr=10.0.0.0/24&new_prefix=26", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "info" in data
    assert data["subnet_count"] == 4

    # Invalid CIDR
    res = client.get("/api/v1/tools/cidr?cidr=invalid", headers=auth_headers)
    assert res.status_code == 400

    # /api/v1/tools/dns
    res = client.get("/api/v1/tools/dns?name=localhost", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["resolved"] is True

    # /api/v1/tools/port
    res = client.get(
        "/api/v1/tools/port?host=127.0.0.1&port=65530&timeout=0.5", headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["open"] is False

    # Check overlap and validation helpers
    assert check_overlap("10.0.0.0/16", "10.0.1.0/24") is True
    assert validate_cidr("192.168.1.0/24") is True
    assert validate_cidr("invalid-cidr") is False
    assert len(split_cidr("10.0.0.0/24", 25)) == 2
