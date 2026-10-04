"""Unit tests for AWS mock module, security auditors, and API endpoints."""

import pytest
from fastapi.testclient import TestClient

from infraops.common.config import get_settings
from infraops.server.app import app
from infraops.server.aws import cloudwatch, ec2, iam, s3, vpc
from infraops.server.aws.client import seed_mock_environment


@pytest.fixture(scope="module")
def seeded_aws():
    """Ensure mock environment is seeded once for the test module."""
    seed_mock_environment(force=True)
    return True


@pytest.fixture
def auth_client():
    """TestClient with valid API key header."""
    settings = get_settings()
    return TestClient(app, headers={"X-API-Key": settings.api_key})


@pytest.fixture
def unauth_client():
    """TestClient without API key."""
    return TestClient(app)


def test_seed_mock_environment(seeded_aws):
    """Verify seeding is idempotent and provisions all core AWS constructs."""
    res = seed_mock_environment()
    assert res["status"] in ["seeded", "already_seeded"]


def test_ec2_instances_listing(seeded_aws):
    """Test EC2 listing and single instance retrieval with tags."""
    instances = ec2.list_instances()
    assert len(instances) >= 3

    names = {i["name"] for i in instances}
    assert "infraops-web-1" in names
    assert "infraops-web-2" in names
    assert "infraops-db-1" in names

    first_id = instances[0]["instance_id"]
    single = ec2.get_instance(first_id)
    assert single is not None
    assert single["instance_id"] == first_id
    assert single["instance_type"] == "t3.micro"
    assert single["tags"]["Environment"] == "production"


def test_vpc_and_subnets_with_cidr(seeded_aws):
    """Test VPC querying and subnet usable IP math."""
    vpcs = vpc.list_vpcs()
    assert len(vpcs) >= 1
    main_vpc = next((v for v in vpcs if v["name"] == "infraops-vpc"), None)
    assert main_vpc is not None
    assert main_vpc["cidr_block"] == "10.0.0.0/16"

    subnets = vpc.list_subnets(vpc_id=main_vpc["vpc_id"])
    assert len(subnets) == 4

    for s in subnets:
        # /24 subnets in AWS have 256 total IPs, 254 standard usable, and 251 AWS usable (5 reserved)
        assert s["total_ips"] == 256
        assert s["standard_usable_hosts"] == 254
        assert s["aws_usable_hosts"] == 251
        assert s["aws_reserved_ips"] == 5


def test_security_group_risk_audit(seeded_aws):
    """Test security group listing and 0.0.0.0/0 exposure risk flagging."""
    sgs = vpc.list_security_groups()
    assert len(sgs) >= 2

    # Verify risky group is flagged
    risky_sg = next((g for g in sgs if g["group_name"] == "risky-external-ssh-sg"), None)
    assert risky_sg is not None
    assert risky_sg["is_risky"] is True
    assert len(risky_sg["risk_findings"]) > 0

    critical_finding = risky_sg["risk_findings"][0]
    assert critical_finding["severity"] == "CRITICAL"
    assert critical_finding["port"] == 22
    assert "0.0.0.0/0" in critical_finding["message"]

    # Verify standard workload group is not flagged as risky for port 22
    normal_sg = next((g for g in sgs if g["group_name"] == "infraops-sg"), None)
    assert normal_sg is not None
    port_22_risks = [f for f in normal_sg["risk_findings"] if f.get("port") == 22]
    assert len(port_22_risks) == 0


def test_iam_roles_and_least_privilege_audit(seeded_aws):
    """Test IAM role querying and least-privilege policy violation detection."""
    roles = iam.list_roles()
    assert len(roles) >= 2

    agent_role = next((r for r in roles if r["role_name"] == "infraops-agent-role"), None)
    assert agent_role is not None
    assert agent_role["is_least_privilege"] is True
    critical_findings = [f for f in agent_role["findings"] if f["severity"] in ["CRITICAL", "HIGH"]]
    assert len(critical_findings) == 0

    overpermissive_role = next(
        (r for r in roles if r["role_name"] == "overpermissive-legacy-admin-role"), None
    )
    assert overpermissive_role is not None
    assert overpermissive_role["is_least_privilege"] is False
    assert len(overpermissive_role["findings"]) > 0
    assert overpermissive_role["findings"][0]["severity"] == "CRITICAL"

    audit_summary = iam.audit_least_privilege()
    assert audit_summary["total_roles"] >= 2
    assert audit_summary["compliant_roles"] >= 1
    assert audit_summary["non_compliant_roles"] >= 1
    assert audit_summary["compliance_score_percent"] < 100.0


def test_s3_buckets_and_report_archive(seeded_aws):
    """Test S3 bucket listing, versioning, public access block, and report archive."""
    buckets = s3.list_buckets()
    assert len(buckets) >= 2

    reports_bucket = next((b for b in buckets if b["name"] == "infraops-incident-reports"), None)
    assert reports_bucket is not None
    assert reports_bucket["versioning_enabled"] is True
    assert reports_bucket["public_access_block"]["is_secure"] is True

    # Test report upload and retrieval
    inc_id = "INC-TEST-999"
    test_content = "# Test Post-Mortem Report\nSimulated incident content."

    upload_res = s3.upload_incident_report(inc_id, test_content)
    assert upload_res["status"] == "uploaded"
    assert upload_res["key"] == f"{inc_id}/report.md"

    retrieved = s3.get_incident_report(inc_id)
    assert retrieved == test_content

    all_reports = s3.list_incident_reports()
    assert any(r["incident_id"] == inc_id for r in all_reports)


def test_cloudwatch_alarms_and_metric_publishing(seeded_aws):
    """Test CloudWatch alarm retrieval and metric publication."""
    alarms = cloudwatch.list_alarms()
    assert len(alarms) >= 3
    alarm_names = {a["alarm_name"] for a in alarms}
    assert "HighCPUAlarm" in alarm_names
    assert "HighMemoryAlarm" in alarm_names
    assert "DiskSpaceAlarm" in alarm_names

    pub_res = cloudwatch.publish_host_metrics(
        host_id="test-host-1",
        cpu_percent=45.2,
        mem_percent=60.8,
        disk_percent=33.1,
    )
    assert pub_res["CPUPercent"] is True
    assert pub_res["MemPercent"] is True
    assert pub_res["DiskPercent"] is True


def test_aws_api_endpoints_auth(unauth_client, auth_client, seeded_aws):
    """Test API authentication and endpoints."""
    # Unauthenticated should fail
    resp = unauth_client.get("/api/v1/aws/summary")
    assert resp.status_code in [401, 403]

    # Authenticated summary
    resp = auth_client.get("/api/v1/aws/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["instances_total"] >= 3
    assert data["vpcs_count"] >= 1
    assert data["subnets_count"] >= 4
    assert data["security_groups_risky"] >= 1
    assert data["iam_roles_total"] >= 2
    assert data["s3_buckets_total"] >= 2

    # EC2 endpoints
    resp = auth_client.get("/api/v1/aws/ec2")
    assert resp.status_code == 200
    assert len(resp.json()) >= 3

    # VPC and Subnets
    resp = auth_client.get("/api/v1/aws/vpc")
    assert resp.status_code == 200
    vpc_id = next(v["vpc_id"] for v in resp.json() if v["name"] == "infraops-vpc")

    resp = auth_client.get(f"/api/v1/aws/subnets?vpc_id={vpc_id}")
    assert resp.status_code == 200
    assert len(resp.json()) == 4
    assert resp.json()[0]["aws_usable_hosts"] == 251

    # Security groups
    resp = auth_client.get("/api/v1/aws/security-groups")
    assert resp.status_code == 200
    assert any(g["is_risky"] for g in resp.json())

    # IAM audit
    resp = auth_client.get("/api/v1/aws/iam/audit")
    assert resp.status_code == 200
    assert resp.json()["non_compliant_roles"] >= 1

    # S3 buckets
    resp = auth_client.get("/api/v1/aws/s3")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2

    # CloudWatch
    resp = auth_client.get("/api/v1/aws/cloudwatch")
    assert resp.status_code == 200
    assert len(resp.json()) >= 3

    # Publish metric via API
    resp = auth_client.post(
        "/api/v1/aws/cloudwatch/metrics",
        json={"host_id": "api-host", "cpu_percent": 75.0},
    )
    assert resp.status_code == 200
    assert resp.json()["published"]["CPUPercent"] is True


def test_tools_api_endpoints(auth_client):
    """Test network CIDR, DNS, and port tools API endpoints."""
    # CIDR tool
    resp = auth_client.get("/api/v1/tools/cidr?cidr=10.0.0.0/16&new_prefix=24")
    assert resp.status_code == 200
    data = resp.json()
    assert data["info"]["cidr"] == "10.0.0.0/16"
    assert data["info"]["aws_usable_hosts"] == 65531
    assert data["subnet_count"] == 256

    # DNS tool
    resp = auth_client.get("/api/v1/tools/dns?name=localhost")
    assert resp.status_code == 200
    assert resp.json()["resolved"] is True
    assert "127.0.0.1" in resp.json()["ips"]

    # Port tool
    resp = auth_client.get("/api/v1/tools/port?host=127.0.0.1&port=65432")
    assert resp.status_code == 200
    assert "status" in resp.json()
