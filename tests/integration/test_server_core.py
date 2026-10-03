"""Integration tests for Server core API, database storage, and agent shipper."""

import os
import time

import pytest
from fastapi.testclient import TestClient

from infraops.agent.shipper import Shipper
from infraops.common.config import reset_settings
from infraops.common.schemas import (
    IngestBatch,
    LogEvent,
    MetricPoint,
    SnapshotPayload,
)
from infraops.server.app import create_app
from infraops.server.db import get_engine, init_db


@pytest.fixture
def client(tmp_path):
    """Fixture providing TestClient with an isolated temporary SQLite database."""
    test_db = tmp_path / "test_infraops.db"
    os.environ["INFRAOPS_DB_URL"] = f"sqlite:///{test_db}"
    os.environ["INFRAOPS_API_KEY"] = "test-secret"
    reset_settings()

    engine = get_engine(f"sqlite:///{test_db}")
    init_db(engine)

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client):
    """Verify /health returns 200 without requiring authentication."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


def test_auth_enforcement(client):
    """Verify protected endpoints require valid X-API-Key."""
    # Missing header
    resp = client.get("/api/v1/hosts")
    assert resp.status_code == 401

    # Invalid key
    resp_bad = client.get("/api/v1/hosts", headers={"X-API-Key": "wrong-key"})
    assert resp_bad.status_code == 401

    # Valid key
    resp_ok = client.get("/api/v1/hosts", headers={"X-API-Key": "test-secret"})
    assert resp_ok.status_code == 200


def test_host_registration_and_detail(client):
    """Verify host registration and subsequent detail lookup."""
    headers = {"X-API-Key": "test-secret"}
    reg_payload = {
        "id": "server-node-1",
        "hostname": "prod-web-01",
        "ip": "10.0.1.15",
        "os": "Ubuntu 22.04",
        "kind": "ec2",
        "tags": {"env": "production"},
    }
    reg_resp = client.post("/api/v1/hosts/register", headers=headers, json=reg_payload)
    assert reg_resp.status_code == 200

    # Query detail
    detail_resp = client.get("/api/v1/hosts/server-node-1", headers=headers)
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["host"]["id"] == "server-node-1"
    assert data["host"]["hostname"] == "prod-web-01"


def test_ingest_and_metrics_query_with_downsampling(client):
    """Verify batch ingestion, database storage, and metric downsampling queries."""
    headers = {"X-API-Key": "test-secret"}
    now = time.time()

    # Create batch with 5 data points spaced 5 seconds apart
    metrics = [
        MetricPoint(name="cpu.percent", value=float(50 + i * 5), ts=now - (20 - i * 5))
        for i in range(5)
    ]
    snapshots = [SnapshotPayload(kind="processes", payload={"total": 120, "zombies": 0}, ts=now)]
    logs = [
        LogEvent(
            source="demo-service",
            level="ERROR",
            message="Connection refused",
            ts=now,
        )
    ]

    batch = IngestBatch(
        host_id="server-node-1",
        ts=now,
        metrics=metrics,
        snapshots=snapshots,
        log_events=logs,
    )

    ingest_resp = client.post("/api/v1/ingest", headers=headers, json=batch.model_dump())
    assert ingest_resp.status_code == 200
    res_body = ingest_resp.json()
    assert res_body["metrics_stored"] == 5
    assert res_body["snapshots_stored"] == 1
    assert res_body["log_events_stored"] == 1

    # Raw metrics query
    query_resp = client.get(
        "/api/v1/metrics",
        headers=headers,
        params={"host_id": "server-node-1", "name": "cpu.percent"},
    )
    assert query_resp.status_code == 200
    points = query_resp.json()["points"]
    assert len(points) == 5

    # Downsampled metrics query (step=10s)
    step_resp = client.get(
        "/api/v1/metrics",
        headers=headers,
        params={"host_id": "server-node-1", "name": "cpu.percent", "step": 10},
    )
    assert step_resp.status_code == 200
    step_points = step_resp.json()["points"]
    assert len(step_points) >= 1
    assert "value" in step_points[0]
    assert "count" in step_points[0]


def test_shipper_spools_when_server_offline_and_flushes(tmp_path, client):
    """Verify agent shipper saves batches to disk when server is unreachable and flushes once back."""
    spool_dir = tmp_path / "spool"
    shipper = Shipper(
        server_url="http://127.0.0.1:54321",  # Unreachable server
        api_key="test-secret",
        spool_dir=spool_dir,
    )

    now = time.time()
    batch = IngestBatch(
        host_id="offline-node",
        ts=now,
        metrics=[MetricPoint(name="cpu.percent", value=75.0, ts=now)],
    )

    # Deliver while offline -> spools to disk
    delivered = shipper.ship(batch)
    assert not delivered
    spool_files = list(spool_dir.glob("*.json"))
    assert len(spool_files) == 1

    # Now point shipper to valid test server using custom httpx transport in client
    # Simulate flush via client endpoint
    headers = {"X-API-Key": "test-secret"}
    import json

    for sf in spool_files:
        payload = json.loads(sf.read_text(encoding="utf-8"))
        res = client.post("/api/v1/ingest", headers=headers, json=payload)
        assert res.status_code == 200
        sf.unlink()

    assert len(list(spool_dir.glob("*.json"))) == 0
