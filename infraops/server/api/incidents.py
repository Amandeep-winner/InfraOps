"""Incident management, approvals, notes, and post-mortem reporting router."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from infraops.server.db import get_db
from infraops.server.incidents.reports import generate_incident_report
from infraops.server.incidents.service import IncidentService, InvalidStateTransitionError
from infraops.server.models import Approval, Incident, IncidentEvent
from infraops.server.security import verify_api_key

router = APIRouter(prefix="/incidents", tags=["incidents"], dependencies=[Depends(verify_api_key)])


class NoteRequest(BaseModel):
    message: str = Field(..., description="Human operator note content")
    actor: str = Field(default="human", description="Operator name or identifier")


class CloseRequest(BaseModel):
    resolution_summary: Optional[str] = Field(default=None, description="Final resolution summary")
    actor: str = Field(default="human")


@router.get("")
def list_incidents(
    state: Optional[str] = Query(None, description="Filter by state (e.g. DETECTED, RESOLVED)"),
    severity: Optional[str] = Query(None, description="Filter by severity (P1-P4)"),
    host_id: Optional[str] = Query(None, description="Filter by host ID"),
    db: Session = Depends(get_db),
):
    """List incidents with optional filtering."""
    query = select(Incident).order_by(Incident.opened_at.desc())
    if state:
        query = query.where(Incident.state == state)
    if severity:
        query = query.where(Incident.severity == severity)
    if host_id:
        query = query.where(Incident.host_id == host_id)

    incidents = db.scalars(query).all()
    return [
        {
            "id": inc.id,
            "title": inc.title,
            "host_id": inc.host_id,
            "severity": inc.severity,
            "state": inc.state,
            "sop_id": inc.sop_id,
            "opened_at": inc.opened_at.isoformat() if inc.opened_at else None,
            "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
            "closed_at": inc.closed_at.isoformat() if inc.closed_at else None,
            "mode": inc.mode,
        }
        for inc in incidents
    ]


@router.get("/{incident_id}")
def get_incident_detail(incident_id: str, db: Session = Depends(get_db)):
    """Retrieve complete incident detail including timeline events and pending approvals."""
    incident = db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    events = db.scalars(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.ts.asc())
    ).all()

    approvals = db.scalars(select(Approval).where(Approval.incident_id == incident_id)).all()

    return {
        "incident": {
            "id": incident.id,
            "title": incident.title,
            "host_id": incident.host_id,
            "severity": incident.severity,
            "state": incident.state,
            "sop_id": incident.sop_id,
            "opened_at": incident.opened_at.isoformat() if incident.opened_at else None,
            "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
            "closed_at": incident.closed_at.isoformat() if incident.closed_at else None,
            "root_cause": incident.root_cause,
            "resolution_summary": incident.resolution_summary,
            "mode": incident.mode,
        },
        "timeline": [
            {
                "id": ev.id,
                "ts": ev.ts,
                "phase": ev.phase,
                "actor": ev.actor,
                "message": ev.message,
                "data": ev.data,
            }
            for ev in events
        ],
        "approvals": [
            {
                "id": a.id,
                "step_id": a.step_id,
                "state": a.state,
                "requested_at": a.requested_at.isoformat(),
                "decided_at": a.decided_at.isoformat() if a.decided_at else None,
            }
            for a in approvals
        ],
    }


@router.post("/{incident_id}/note", status_code=status.HTTP_200_OK)
def add_incident_note(incident_id: str, req: NoteRequest, db: Session = Depends(get_db)):
    """Append a human operator note to the incident timeline."""
    incident = db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    ev = IncidentService.record_event(
        db=db,
        incident_id=incident_id,
        phase="note",
        actor=req.actor,
        message=req.message,
    )
    return {"message": "Note recorded", "event_id": ev.id}


@router.post("/{incident_id}/close", status_code=status.HTTP_200_OK)
def close_incident(incident_id: str, req: CloseRequest, db: Session = Depends(get_db)):
    """Close an incident that is currently in RESOLVED state."""
    try:
        closed = IncidentService.close_incident(
            db=db,
            incident_id=incident_id,
            actor=req.actor,
            resolution_summary=req.resolution_summary,
        )
        return {"message": "Incident closed successfully", "id": closed.id, "state": closed.state}
    except ValueError:
        raise HTTPException(status_code=404, detail="Incident not found")
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{incident_id}/report")
def get_incident_report(incident_id: str, db: Session = Depends(get_db)):
    """Generate and return post-mortem markdown report."""
    try:
        report = generate_incident_report(incident_id, db)
        return Response(content=report, media_type="text/markdown")
    except ValueError:
        raise HTTPException(status_code=404, detail="Incident not found")


@router.post("/{incident_id}/approve/{step_id}", status_code=status.HTTP_200_OK)
def approve_step(incident_id: str, step_id: str, db: Session = Depends(get_db)):
    """Approve a paused manual-mode remediation step."""
    approval = db.scalars(
        select(Approval).where(
            Approval.incident_id == incident_id,
            Approval.step_id == step_id,
            Approval.state == "pending",
        )
    ).first()
    if not approval:
        raise HTTPException(status_code=404, detail="Pending approval not found")

    approval.state = "approved"
    approval.decided_at = datetime.now(timezone.utc)
    IncidentService.record_event(
        db=db,
        incident_id=incident_id,
        phase="remediate",
        actor="human",
        message=f"Operator approved remediation step '{step_id}'",
    )
    db.commit()
    return {"message": f"Step {step_id} approved", "state": "approved"}


@router.post("/{incident_id}/reject/{step_id}", status_code=status.HTTP_200_OK)
def reject_step(incident_id: str, step_id: str, db: Session = Depends(get_db)):
    """Reject a paused manual-mode remediation step."""
    approval = db.scalars(
        select(Approval).where(
            Approval.incident_id == incident_id,
            Approval.step_id == step_id,
            Approval.state == "pending",
        )
    ).first()
    if not approval:
        raise HTTPException(status_code=404, detail="Pending approval not found")

    approval.state = "rejected"
    approval.decided_at = datetime.now(timezone.utc)
    IncidentService.record_event(
        db=db,
        incident_id=incident_id,
        phase="remediate",
        actor="human",
        message=f"Operator rejected remediation step '{step_id}'",
    )
    db.commit()
    return {"message": f"Step {step_id} rejected", "state": "rejected"}
