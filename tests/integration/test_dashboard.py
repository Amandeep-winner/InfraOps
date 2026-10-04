"""Integration tests for NOC operations dashboard views and HTML rendering."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from infraops.server.app import app
from infraops.server.db import get_engine
from infraops.server.incidents.service import IncidentService
from infraops.server.models import Host, Metric


@pytest.fixture
def client():
    """TestClient instance for dashboard testing."""
    return TestClient(app)


@pytest.fixture
def seeded_db():
    """Seed test database with sample host and incident for rich view rendering."""
    engine = get_engine()
    with Session(engine) as db:
        # Create test host if not exists
        host = db.get(Host, "test-dashboard-node")
        if not host:
            host = Host(
                id="test-dashboard-node",
                hostname="test-dashboard-node",
                os="Linux 6.1",
                ip="192.168.1.100",
                status="online",
                kind="linux",
            )
            db.add(host)
            db.commit()

        # Add sample metric
        metric = Metric(
            host_id="test-dashboard-node",
            name="cpu.percent",
            value=42.5,
            ts=1700000000.0,
        )
        db.add(metric)
        db.commit()

        # Create sample incident
        inc = IncidentService.create_incident(
            db=db,
            title="High CPU sustained breach on test-dashboard-node",
            host_id="test-dashboard-node",
            severity="P1",
            sop_id="SOP-001",
            mode="auto",
            initial_event_msg="Automated breach detected.",
        )
        inc_id = inc.id

    return {"host_id": "test-dashboard-node", "incident_id": inc_id}


def test_static_assets_served(client):
    """Verify static CSS stylesheet and JavaScript bundle are served with HTTP 200."""
    css_resp = client.get("/static/css/style.css")
    assert css_resp.status_code == 200
    assert "--p1-color" in css_resp.text

    js_resp = client.get("/static/js/dashboard.js")
    assert js_resp.status_code == 200
    assert "drawLineChart" in js_resp.text


def test_overview_page_renders(client, seeded_db):
    """Verify Overview (/) view renders key metrics, cards, and navigation."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Operations Overview" in resp.text
    assert "Monitored Infrastructure Nodes" in resp.text
    assert "test-dashboard-node" in resp.text
    assert "Active Alert Breaches" in resp.text
    assert "Recent Incidents" in resp.text


def test_host_detail_page_renders(client, seeded_db):
    """Verify Host Detail (/hosts/{id}) view renders time-series charts and processes."""
    host_id = seeded_db["host_id"]
    resp = client.get(f"/hosts/{host_id}")
    assert resp.status_code == 200
    assert host_id in resp.text
    assert "CPU Utilization (%)" in resp.text
    assert "Memory Utilization (%)" in resp.text
    assert "Top Active Processes" in resp.text
    assert "Monitored Services" in resp.text


def test_incidents_page_renders(client, seeded_db):
    """Verify Incidents (/incidents) table view renders and supports filtering."""
    resp = client.get("/incidents")
    assert resp.status_code == 200
    assert "Incident Management" in resp.text
    assert "All Incidents" in resp.text
    assert seeded_db["incident_id"] in resp.text

    # With state filter
    resp_filtered = client.get("/incidents?state=DETECTED")
    assert resp_filtered.status_code == 200
    assert seeded_db["incident_id"] in resp_filtered.text


def test_incident_detail_page_with_stepper(client, seeded_db):
    """Verify Incident Detail (/incidents/{id}) renders the visual stepper and timeline."""
    inc_id = seeded_db["incident_id"]
    resp = client.get(f"/incidents/{inc_id}")
    assert resp.status_code == 200
    assert inc_id in resp.text
    # Stepper stages
    assert "Detect" in resp.text
    assert "Investigate" in resp.text
    assert "Identify" in resp.text
    assert "Remediate" in resp.text
    assert "Verify" in resp.text
    assert "Close" in resp.text
    assert "Incident Audit Timeline" in resp.text


def test_sops_library_page_renders(client):
    """Verify SOP library (/sops) renders declarative runbooks and step details."""
    resp = client.get("/sops")
    assert resp.status_code == 200
    assert "Standard Operating Procedures (SOPs)" in resp.text
    assert "Available Runbooks" in resp.text
    assert "SOP-001" in resp.text
    assert "Execution Steps" in resp.text

    # Query specific SOP
    resp_sop = client.get("/sops?id=SOP-004")
    assert resp_sop.status_code == 200
    assert "SOP-004" in resp_sop.text


def test_simulator_page_renders(client):
    """Verify Simulator (/simulate) view renders all 6 incidents and sandbox safety banner."""
    resp = client.get("/simulate")
    assert resp.status_code == 200
    assert "Interactive Incident Simulator" in resp.text
    assert "Sandbox Only Guardrail" in resp.text
    assert "INC-001: High CPU" in resp.text
    assert "INC-002: High Memory" in resp.text
    assert "INC-003: Disk Full" in resp.text
    assert "INC-004: Service Down" in resp.text
    assert "INC-005: DNS Failure" in resp.text
    assert "INC-006: Connectivity" in resp.text


def test_network_tools_page_renders(client):
    """Verify Network Tools (/tools) view renders CIDR calculator and diagnostics."""
    resp = client.get("/tools")
    assert resp.status_code == 200
    assert "Network" in resp.text
    assert "CIDR Diagnostics Tools" in resp.text
    assert "IPv4 CIDR Calculator" in resp.text

    # With calculation query
    resp_calc = client.get("/tools?cidr=10.0.0.0/16&new_prefix=24")
    assert resp_calc.status_code == 200
    assert "AWS 5 Reserved IP Address Breakdown" in resp_calc.text
    assert "Total Addresses" in resp_calc.text
    assert "65536" in resp_calc.text


def test_aws_page_renders(client):
    """Verify AWS Topology (/aws) view renders instances, VPC subnets, and alarms."""
    resp = client.get("/aws")
    assert resp.status_code == 200
    assert "AWS Infrastructure Topology" in resp.text
    assert "EC2 Workload Instances" in resp.text
    assert "VPC Subnets" in resp.text
    assert "Address Capacity" in resp.text
    assert "Security Groups" in resp.text
    assert "CloudWatch Alarms" in resp.text


def test_audit_page_renders(client):
    """Verify Security Audit (/audit) view renders unified compliance findings."""
    resp = client.get("/audit")
    assert resp.status_code == 200
    assert "Comprehensive Security" in resp.text
    assert "Compliance Audit" in resp.text
    assert "Network Ingress Rules" in resp.text
    assert "IAM Least-Privilege Wildcard Violations" in resp.text
    assert "SSH Security" in resp.text
    assert "Filesystem Permission Audit" in resp.text


def test_simulate_stop_endpoint(client):
    """Verify POST /simulate/stop responds gracefully."""
    resp = client.post("/simulate/stop?name=cpu")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"
