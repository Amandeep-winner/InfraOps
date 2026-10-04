"""AWS inspection and security audit API endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from infraops.server.aws import cloudwatch, ec2, iam, s3, vpc
from infraops.server.security import verify_api_key

router = APIRouter(prefix="/aws", tags=["aws"], dependencies=[Depends(verify_api_key)])


class PublishMetricRequest(BaseModel):
    host_id: str
    cpu_percent: Optional[float] = None
    mem_percent: Optional[float] = None
    disk_percent: Optional[float] = None


@router.get("/summary", response_model=Dict[str, Any])
def get_aws_overview_summary():
    """Aggregate high-level overview of AWS infrastructure and security posture."""
    instances = ec2.list_instances()
    vpcs = vpc.list_vpcs()
    subnets = vpc.list_subnets()
    sgs = vpc.list_security_groups()
    iam_audit = iam.audit_least_privilege()
    buckets = s3.list_buckets()
    alarms = cloudwatch.list_alarms()

    risky_sgs = [sg for sg in sgs if sg.get("is_risky")]
    unprotected_buckets = [
        b for b in buckets if not b.get("public_access_block", {}).get("is_secure")
    ]

    return {
        "instances_total": len(instances),
        "instances_running": sum(1 for i in instances if i.get("state") == "running"),
        "vpcs_count": len(vpcs),
        "subnets_count": len(subnets),
        "security_groups_total": len(sgs),
        "security_groups_risky": len(risky_sgs),
        "iam_roles_total": iam_audit.get("total_roles", 0),
        "iam_compliance_score": iam_audit.get("compliance_score_percent", 100.0),
        "s3_buckets_total": len(buckets),
        "s3_unprotected_buckets": len(unprotected_buckets),
        "cloudwatch_alarms_total": len(alarms),
        "cloudwatch_alarms_firing": sum(1 for a in alarms if a.get("state") == "ALARM"),
    }


@router.get("/ec2", response_model=List[Dict[str, Any]])
def list_ec2_instances():
    """List EC2 instances with tags, network bindings, and current operational states."""
    return ec2.list_instances()


@router.get("/ec2/{instance_id}", response_model=Dict[str, Any])
def get_ec2_instance(instance_id: str):
    """Retrieve details for a specific EC2 instance."""
    inst = ec2.get_instance(instance_id)
    if not inst:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"EC2 instance {instance_id} not found",
        )
    return inst


@router.get("/vpc", response_model=List[Dict[str, Any]])
def list_vpcs():
    """List VPCs configured in the account."""
    return vpc.list_vpcs()


@router.get("/subnets", response_model=List[Dict[str, Any]])
def list_subnets(
    vpc_id: Optional[str] = Query(None, description="Optional VPC ID filter"),
):
    """List VPC subnets with usable host capacities and AWS 5-reserved-IP breakdown."""
    return vpc.list_subnets(vpc_id=vpc_id)


@router.get("/security-groups", response_model=List[Dict[str, Any]])
def list_security_groups(
    vpc_id: Optional[str] = Query(None, description="Optional VPC ID filter"),
):
    """List security groups with ingress rule risk evaluations (e.g. 0.0.0.0/0 exposures)."""
    return vpc.list_security_groups(vpc_id=vpc_id)


@router.get("/iam", response_model=List[Dict[str, Any]])
def list_iam_roles():
    """List custom IAM roles with attached policies and least-privilege analysis."""
    return iam.list_roles()


@router.get("/iam/audit", response_model=Dict[str, Any])
def audit_iam_least_privilege():
    """Perform least-privilege audit across all custom IAM roles and policies."""
    return iam.audit_least_privilege()


@router.get("/s3", response_model=List[Dict[str, Any]])
def list_s3_buckets():
    """List S3 buckets with versioning and public access block security postures."""
    return s3.list_buckets()


@router.get("/s3/reports", response_model=List[Dict[str, Any]])
def list_s3_incident_reports():
    """List incident post-mortem markdown reports archived in S3."""
    return s3.list_incident_reports()


@router.get("/s3/reports/{incident_id}", response_model=Dict[str, Any])
def get_s3_incident_report(incident_id: str):
    """Fetch archived incident report markdown content from S3."""
    content = s3.get_incident_report(incident_id)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report for incident {incident_id} not found in S3",
        )
    return {"incident_id": incident_id, "content": content}


@router.get("/cloudwatch", response_model=List[Dict[str, Any]])
def list_cloudwatch_alarms():
    """List CloudWatch alarms with evaluation states, metrics, and thresholds."""
    return cloudwatch.list_alarms()


@router.post("/cloudwatch/metrics", response_model=Dict[str, Any])
def publish_cloudwatch_metrics(req: PublishMetricRequest):
    """Publish host telemetry to CloudWatch."""
    results = cloudwatch.publish_host_metrics(
        host_id=req.host_id,
        cpu_percent=req.cpu_percent,
        mem_percent=req.mem_percent,
        disk_percent=req.disk_percent,
    )
    return {"host_id": req.host_id, "published": results}
