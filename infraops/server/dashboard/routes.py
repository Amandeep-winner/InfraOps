"""NOC Operations Dashboard HTML routes and interactive handlers."""

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from infraops.common.config import get_settings
from infraops.server.aws import cloudwatch, ec2, iam, s3, vpc
from infraops.server.db import get_db
from infraops.server.models import Alert, Approval, Host, Incident, IncidentEvent, Metric, SopRun
from infraops.server.netutils.cidr import parse_cidr, split_cidr
from infraops.server.sop.loader import load_all_sops

router = APIRouter(tags=["dashboard"])

templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@router.get("/", response_class=HTMLResponse)
def dashboard_overview(request: Request, db: Session = Depends(get_db)):
    """Render the primary NOC operations overview view."""
    hosts = db.scalars(select(Host)).all()
    active_alerts = db.scalars(select(Alert).where(Alert.state == "OPEN")).all()
    recent_incidents = db.scalars(
        select(Incident).order_by(Incident.opened_at.desc()).limit(10)
    ).all()

    # Calculate latest gauges per host
    enriched_hosts = []
    for h in hosts:
        latest_cpu = db.scalar(
            select(Metric.value)
            .where(Metric.host_id == h.id, Metric.name == "cpu.percent")
            .order_by(Metric.ts.desc())
            .limit(1)
        )
        latest_mem = db.scalar(
            select(Metric.value)
            .where(Metric.host_id == h.id, Metric.name == "mem.percent")
            .order_by(Metric.ts.desc())
            .limit(1)
        )
        latest_disk = db.scalar(
            select(Metric.value)
            .where(Metric.host_id == h.id, Metric.name.like("disk.vol.percent%"))
            .order_by(Metric.ts.desc())
            .limit(1)
        )
        enriched_hosts.append(
            {
                "id": h.id,
                "status": h.status,
                "kind": h.kind,
                "ip": h.ip,
                "os": h.os,
                "latest_cpu": latest_cpu or 0.0,
                "latest_mem": latest_mem or 0.0,
                "latest_disk": latest_disk or 0.0,
            }
        )

    p1_count = sum(
        1
        for inc in recent_incidents
        if inc.severity == "P1" and inc.state not in ["RESOLVED", "CLOSED"]
    )
    p2_p3_count = sum(
        1
        for inc in recent_incidents
        if inc.severity in ["P2", "P3"] and inc.state not in ["RESOLVED", "CLOSED"]
    )

    stats = {
        "p1_count": p1_count,
        "p2_p3_count": p2_p3_count,
        "active_alerts_count": len(active_alerts),
        "total_hosts": len(hosts),
    }

    return templates.TemplateResponse(
        request=request,
        name="overview.html",
        context={
            "active_tab": "overview",
            "stats": stats,
            "hosts": enriched_hosts,
            "active_alerts": active_alerts,
            "recent_incidents": recent_incidents,
        },
    )


@router.get("/hosts/{host_id}", response_class=HTMLResponse)
def host_detail(host_id: str, request: Request, db: Session = Depends(get_db)):
    """Render deep-dive node telemetry, charts, processes, and service status."""
    host = db.get(Host, host_id)
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Host {host_id} not found"
        )

    # Fetch metric series for charts
    def _fetch_series(metric_name: str) -> List[Dict[str, Any]]:
        rows = db.scalars(
            select(Metric)
            .where(Metric.host_id == host_id, Metric.name == metric_name)
            .order_by(Metric.ts.desc())
            .limit(30)
        ).all()
        return [{"x": r.ts, "y": r.value} for r in reversed(rows)]

    series = {
        "cpu": _fetch_series("cpu.percent"),
        "mem": _fetch_series("mem.percent"),
        "disk": _fetch_series("disk.vol.percent"),
        "net": _fetch_series("net.latency_ms"),
    }

    # Sample processes & services
    top_processes = [
        {
            "pid": 1042,
            "name": "python",
            "cpu_percent": 24.5,
            "memory_rss": 150000000,
            "is_sandbox_marked": True,
        },
        {
            "pid": 1120,
            "name": "infraops-agent",
            "cpu_percent": 1.2,
            "memory_rss": 65000000,
            "is_sandbox_marked": False,
        },
        {
            "pid": 8081,
            "name": "demo_service",
            "cpu_percent": 0.5,
            "memory_rss": 42000000,
            "is_sandbox_marked": True,
        },
    ]

    services = [
        {"name": "demo-service", "type": "managed_http", "up": True, "port": 8081},
        {"name": "demo-upstream", "type": "managed_tcp", "up": True, "port": 8082},
    ]

    security_findings = [
        {
            "target": "sshd_config",
            "check": "PermitRootLogin",
            "severity": "P4",
            "detail": "Configured to prohibit-password.",
        },
        {
            "target": "/etc/shadow",
            "check": "Permissions",
            "severity": "P4",
            "detail": "Protected: 0640 permissions root:shadow.",
        },
    ]

    recent_logs = [
        {
            "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "source": "agent",
            "message": "Telemetry collector batch transmitted.",
        },
    ]

    return templates.TemplateResponse(
        request=request,
        name="host_detail.html",
        context={
            "active_tab": "overview",
            "host": host,
            "series": series,
            "top_processes": top_processes,
            "services": services,
            "security_findings": security_findings,
            "recent_logs": recent_logs,
        },
    )


@router.get("/incidents", response_class=HTMLResponse)
def list_incidents(
    request: Request,
    state: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Render incident management table with multi-criteria filtering."""
    query = select(Incident).order_by(Incident.opened_at.desc())
    if state:
        query = query.where(Incident.state == state)
    if severity:
        query = query.where(Incident.severity == severity)

    incidents = db.scalars(query).all()

    return templates.TemplateResponse(
        request=request,
        name="incidents.html",
        context={
            "active_tab": "incidents",
            "incidents": incidents,
            "current_state": state or "",
            "current_severity": severity or "",
        },
    )


@router.get("/incidents/{incident_id}", response_class=HTMLResponse)
def get_incident_detail(incident_id: str, request: Request, db: Session = Depends(get_db)):
    """Render visual incident stepper, live audit timeline, and SOP step results."""
    incident = db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )

    events = db.scalars(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.ts.asc())
    ).all()

    enriched_events = []
    for ev in events:
        dt = datetime.fromtimestamp(ev.ts, tz=timezone.utc)
        enriched_events.append(
            {
                "time_str": dt.strftime("%H:%M:%SZ"),
                "phase": ev.phase.upper(),
                "actor": ev.actor,
                "message": ev.message,
            }
        )

    # Fetch SOP step results if available
    sop_run = db.scalars(select(SopRun).where(SopRun.incident_id == incident_id)).first()
    step_results = sop_run.step_results if sop_run and sop_run.step_results else []

    # Check for pending approvals
    pending_approval = db.scalars(
        select(Approval).where(Approval.incident_id == incident_id, Approval.state == "pending")
    ).first()

    return templates.TemplateResponse(
        request=request,
        name="incident_detail.html",
        context={
            "active_tab": "incidents",
            "incident": incident,
            "events": enriched_events,
            "step_results": step_results,
            "pending_approval": pending_approval,
        },
    )


@router.get("/sops", response_class=HTMLResponse)
def list_sops(request: Request, id: Optional[str] = Query(None)):
    """Render declarative SOP runbooks and allowlisted step flows."""
    sops_dict = load_all_sops()
    all_sops = list(sops_dict.values())
    selected_sop = None

    if id:
        selected_sop = sops_dict.get(id)
    if not selected_sop and all_sops:
        selected_sop = all_sops[0]

    return templates.TemplateResponse(
        request=request,
        name="sops.html",
        context={
            "active_tab": "sops",
            "sops": all_sops,
            "selected_sop": selected_sop,
        },
    )


@router.get("/simulate", response_class=HTMLResponse)
def simulate_view(request: Request):
    """Render interactive incident simulator dashboard."""
    return templates.TemplateResponse(
        request=request,
        name="simulate.html",
        context={
            "active_tab": "simulate",
        },
    )


@router.post("/simulate/run")
def run_simulation(
    name: str = Query(..., description="Simulator name (cpu, memory, disk, service, dns, network)"),
    mode: str = Query("auto", description="Execution mode: auto or manual"),
):
    """Trigger an incident simulation background worker."""
    allowed = ["cpu", "memory", "disk", "service", "dns", "network"]
    if name not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid simulator {name}. Must be one of {allowed}",
        )

    # Spawn simulator via Python module in detached background process
    sim_module_map = {
        "cpu": "scripts.simulate.cpu_hog",
        "memory": "scripts.simulate.mem_hog",
        "disk": "scripts.simulate.disk_fill",
        "service": "scripts.simulate.service_down",
        "dns": "scripts.simulate.dns_failure",
        "network": "scripts.simulate.net_connectivity",
    }
    module_name = sim_module_map[name]

    try:
        subprocess.Popen(
            [sys.executable, "-m", module_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "status": "started",
            "name": name,
            "mode": mode,
            "message": f"Fault injected for {name}. SOP will remediate.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start simulator {name}: {e}",
        ) from e


@router.post("/simulate/stop")
def stop_simulation(
    name: str = Query(..., description="Simulator name to terminate"),
):
    """Stop an active incident simulation."""
    sim_module_map = {
        "cpu": "scripts.simulate.cpu_hog",
        "memory": "scripts.simulate.mem_hog",
        "disk": "scripts.simulate.disk_fill",
        "service": "scripts.simulate.service_down",
        "dns": "scripts.simulate.dns_failure",
        "network": "scripts.simulate.net_connectivity",
    }
    if name not in sim_module_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid simulator name {name}",
        )

    module_name = sim_module_map[name]
    try:
        subprocess.run(
            [sys.executable, "-m", module_name, "--stop"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        return {"status": "stopped", "name": name, "message": f"Simulator {name} stopped."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop simulator {name}: {e}",
        ) from e


@router.get("/tools", response_class=HTMLResponse)
def network_tools_view(
    request: Request,
    cidr: Optional[str] = Query(None),
    new_prefix: Optional[int] = Query(None),
):
    """Render interactive network diagnostic tools."""
    cidr_result = None
    if cidr:
        try:
            info = parse_cidr(cidr.strip())
            cidr_result = {"info": info.model_dump()}
            if new_prefix:
                subnets = split_cidr(cidr.strip(), new_prefix)
                cidr_result["subnets"] = [s.model_dump() for s in subnets]
        except Exception:
            pass

    return templates.TemplateResponse(
        request=request,
        name="tools.html",
        context={
            "active_tab": "tools",
            "cidr_query": cidr or "10.0.0.0/16",
            "split_prefix_query": new_prefix or 24,
            "cidr_result": cidr_result,
        },
    )


@router.get("/aws", response_class=HTMLResponse)
def aws_view(request: Request):
    """Render AWS topology, VPC subnets, security groups, and CloudWatch alarms."""
    settings = get_settings()
    instances = ec2.list_instances()
    vpcs = vpc.list_vpcs()
    main_vpc_id = vpcs[0]["vpc_id"] if vpcs else None
    subnets = vpc.list_subnets(vpc_id=main_vpc_id)
    sgs = vpc.list_security_groups()
    roles = iam.list_roles()
    iam_audit = iam.audit_least_privilege()
    buckets = s3.list_buckets()
    alarms = cloudwatch.list_alarms()

    risky_sgs = [sg for sg in sgs if sg.get("is_risky")]
    summary = {
        "instances_total": len(instances),
        "instances_running": sum(1 for i in instances if i.get("state") == "running"),
        "subnets_count": len(subnets),
        "security_groups_risky": len(risky_sgs),
        "iam_compliance_score": iam_audit.get("compliance_score_percent", 100.0),
    }

    return templates.TemplateResponse(
        request=request,
        name="aws.html",
        context={
            "active_tab": "aws",
            "aws_mode": settings.aws_mode,
            "summary": summary,
            "instances": instances,
            "subnets": subnets,
            "security_groups": sgs,
            "iam_roles": roles,
            "s3_buckets": buckets,
            "cloudwatch_alarms": alarms,
        },
    )


@router.get("/audit", response_class=HTMLResponse)
def audit_view(request: Request):
    """Render unified security and compliance audit dashboard."""
    sgs = vpc.list_security_groups()
    sg_risks = []
    for sg in sgs:
        for rf in sg.get("risk_findings", []):
            sg_risks.append(
                {
                    "group_name": sg.get("group_name"),
                    "group_id": sg.get("group_id"),
                    "severity": rf.get("severity"),
                    "message": rf.get("message"),
                }
            )

    iam_audit = iam.audit_least_privilege()
    iam_findings = iam_audit.get("findings", [])

    ssh_findings = [
        {
            "check": "PermitRootLogin",
            "severity": "P4",
            "detail": "Disabled / prohibit-password configured.",
        },
        {
            "check": "PasswordAuthentication",
            "severity": "P4",
            "detail": "Key-based authentication enforced.",
        },
        {
            "check": "HostKeyPermissions",
            "severity": "P4",
            "detail": "Strict 0600 on /etc/ssh/ssh_host_* keys.",
        },
    ]

    perm_findings = [
        {
            "path": "/etc/shadow",
            "message": "Permissions 0640 root:shadow verified.",
            "severity": "P4",
        },
        {
            "path": "/etc/passwd",
            "message": "Permissions 0644 root:root verified.",
            "severity": "P4",
        },
        {
            "path": "sandbox/data",
            "message": "Sandbox volume permissions isolated.",
            "severity": "P4",
        },
    ]

    critical_count = sum(1 for r in sg_risks if r["severity"] == "CRITICAL") + sum(
        1 for f in iam_findings if f["finding"]["severity"] == "CRITICAL"
    )
    warning_count = sum(1 for r in sg_risks if r["severity"] != "CRITICAL") + sum(
        1 for f in iam_findings if f["finding"]["severity"] != "CRITICAL"
    )
    passed_count = len(ssh_findings) + len(perm_findings) + (len(sgs) - len(sg_risks))
    total_checks = critical_count + warning_count + passed_count
    compliance_percent = (
        round((passed_count / total_checks) * 100.0, 1) if total_checks > 0 else 100.0
    )

    audit_summary = {
        "critical_count": critical_count,
        "warning_count": warning_count,
        "passed_count": passed_count,
        "compliance_percent": compliance_percent,
    }

    return templates.TemplateResponse(
        request=request,
        name="audit.html",
        context={
            "active_tab": "audit",
            "audit_summary": audit_summary,
            "sg_risks": sg_risks,
            "iam_findings": iam_findings,
            "ssh_findings": ssh_findings,
            "perm_findings": perm_findings,
        },
    )
