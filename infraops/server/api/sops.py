"""SOP Library and manual execution router."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from infraops.server.db import get_db
from infraops.server.incidents.service import IncidentService
from infraops.server.models import Host
from infraops.server.security import verify_api_key
from infraops.server.sop.engine import SOPEngine
from infraops.server.sop.loader import load_all_sops

router = APIRouter(prefix="/sops", tags=["sops"], dependencies=[Depends(verify_api_key)])
_sop_engine = SOPEngine()


@router.get("")
def list_sops():
    """List all available Standard Operating Procedures."""
    sops = load_all_sops()
    return [
        {
            "id": s.id,
            "title": s.title,
            "severity_default": s.severity_default,
            "owner": s.owner,
            "estimated_minutes": s.estimated_minutes,
            "description": s.description.strip(),
            "trigger_rule": s.trigger.alert_rule,
            "steps_count": len(s.steps),
        }
        for s in sops.values()
    ]


@router.get("/{sop_id}")
def get_sop_detail(sop_id: str):
    """Retrieve complete SOP specification with steps, risks, and escalation path."""
    sops = load_all_sops()
    if sop_id not in sops:
        raise HTTPException(status_code=404, detail="SOP not found")
    sop = sops[sop_id]
    return sop.model_dump()


@router.post("/{sop_id}/run", status_code=status.HTTP_200_OK)
def run_sop_manually(
    sop_id: str,
    host_id: str = Query(..., description="Target host ID"),
    mode: str = Query("manual", description="Execution mode: auto or manual"),
    db: Session = Depends(get_db),
):
    """Trigger manual execution of an SOP for a target host."""
    sops = load_all_sops()
    if sop_id not in sops:
        raise HTTPException(status_code=404, detail="SOP not found")

    host = db.get(Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="Target host not found")

    sop = sops[sop_id]
    # Create incident for this run
    inc = IncidentService.create_incident(
        db=db,
        title=f"Manual SOP Run: {sop.title}",
        host_id=host_id,
        severity=sop.severity_default,
        sop_id=sop.id,
        mode=mode,
        initial_event_msg=f"Operator manually initiated {sop.id} ({sop.title}) on {host_id}",
    )

    # Dispatch SOP execution
    success = _sop_engine.run_sop(
        sop_id=sop_id,
        incident_id=inc.id,
        host_id=host_id,
        db=db,
        mode=mode,
    )

    return {
        "incident_id": inc.id,
        "sop_id": sop_id,
        "mode": mode,
        "success": success,
        "state": inc.state,
    }
