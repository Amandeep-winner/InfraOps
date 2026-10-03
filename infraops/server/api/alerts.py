"""Alerts query API router."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from infraops.server.db import get_db
from infraops.server.models import Alert
from infraops.server.security import verify_api_key

router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(verify_api_key)])


@router.get("")
def list_alerts(
    state: Optional[str] = Query(None, description="Filter by alert state: firing or resolved"),
    host_id: Optional[str] = Query(None, description="Filter by host ID"),
    db: Session = Depends(get_db),
):
    """Retrieve alerts with optional filtering by state and host."""
    query = select(Alert).order_by(Alert.last_seen.desc())
    if state:
        query = query.where(Alert.state == state)
    if host_id:
        query = query.where(Alert.host_id == host_id)

    alerts = db.scalars(query).all()
    return [
        {
            "id": a.id,
            "rule_id": a.rule_id,
            "host_id": a.host_id,
            "severity": a.severity,
            "state": a.state,
            "first_seen": a.first_seen.isoformat(),
            "last_seen": a.last_seen.isoformat(),
            "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
            "value": a.value,
            "summary": a.summary,
            "incident_id": a.incident_id,
        }
        for a in alerts
    ]
