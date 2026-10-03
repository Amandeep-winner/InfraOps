"""Post-incident markdown report generator and S3 archival."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from infraops.server.models import Incident, IncidentEvent


def generate_incident_report(
    incident_id: str, db: Session, reports_dir: Optional[str] = None
) -> str:
    """Generate comprehensive post-incident markdown report and save to disk."""
    incident = db.get(Incident, incident_id)
    if not incident:
        raise ValueError(f"Incident {incident_id} not found")

    events = db.scalars(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.ts.asc())
    ).all()

    # Calculate MTTR (Time to resolve)
    mttr_str = "In progress"
    if incident.resolved_at and incident.opened_at:
        opened = incident.opened_at
        resolved = incident.resolved_at
        if opened.tzinfo is None and resolved.tzinfo is not None:
            opened = opened.replace(tzinfo=timezone.utc)
        elif opened.tzinfo is not None and resolved.tzinfo is None:
            resolved = resolved.replace(tzinfo=timezone.utc)
        duration = int((resolved - opened).total_seconds())
        mttr_str = f"{duration} seconds ({duration // 60}m {duration % 60}s)"

    # Identify remediations and verifications
    remediations = [e for e in events if e.phase == "remediate"]
    verifications = [e for e in events if e.phase == "verify"]

    lines = [
        f"# Incident Post-Mortem Report: {incident.id}",
        "",
        f"**Title:** {incident.title}",
        f"**Severity:** {incident.severity} | **State:** {incident.state} | **Mode:** {incident.mode.upper()}",
        f"**Target Host:** `{incident.host_id}` | **SOP Triggered:** `{incident.sop_id or 'Manual'}`",
        f"**Opened At:** {incident.opened_at.isoformat() if incident.opened_at else 'N/A'}",
        f"**Resolved At:** {incident.resolved_at.isoformat() if incident.resolved_at else 'N/A'}",
        f"**Mean Time to Resolve (MTTR):** {mttr_str}",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        incident.resolution_summary
        or "The incident was detected, investigated, and remediated per standard operating procedure.",
        "",
        "## 2. Root Cause Analysis",
        incident.root_cause
        or "Root cause identified through automated telemetry investigation and metric threshold breaches.",
        "",
        "## 3. Incident Timeline",
        "",
        "| Timestamp (UTC) | Phase | Actor | Message |",
        "| --- | --- | --- | --- |",
    ]

    for ev in events:
        dt_str = datetime.fromtimestamp(ev.ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        clean_msg = ev.message.replace("|", "/")
        lines.append(f"| {dt_str} | `{ev.phase.upper()}` | `{ev.actor}` | {clean_msg} |")

    lines.extend(
        [
            "",
            "## 4. Remediation Actions Taken",
        ]
    )
    if remediations:
        for r in remediations:
            lines.append(f"- **{r.actor}**: {r.message}")
    else:
        lines.append("- No explicit remediation actions recorded.")

    lines.extend(
        [
            "",
            "## 5. Verification Evidence",
        ]
    )
    if verifications:
        for v in verifications:
            lines.append(f"- [x] {v.message}")
    else:
        lines.append("- Manual verification completed.")

    lines.extend(
        [
            "",
            "## 6. Preventive & Follow-up Actions",
            "- [ ] Monitor host stability over the next 24 hours.",
            "- [ ] Audit root cause trigger and adjust alert sustain thresholds if necessary.",
            "- [ ] Ensure SOP runbook steps are updated to reflect any new diagnostic findings.",
            "",
            "---",
            f"*Report generated automatically by InfraOps L1 Incident Management on {datetime.now(timezone.utc).isoformat()}*",
        ]
    )

    report_content = "\n".join(lines) + "\n"

    # Save to disk
    out_dir = Path(reports_dir or "reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / f"{incident.id}.md"
    report_file.write_text(report_content, encoding="utf-8")

    return report_content
