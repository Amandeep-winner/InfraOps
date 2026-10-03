"""Host management and registration router."""

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from infraops.common.schemas import HostRegisterRequest, HostResponse
from infraops.server.db import get_db
from infraops.server.models import Host, Metric, Snapshot
from infraops.server.security import verify_api_key

router = APIRouter(prefix="/hosts", tags=["hosts"], dependencies=[Depends(verify_api_key)])


@router.post("/register", status_code=status.HTTP_200_OK)
def register_host(req: HostRegisterRequest, db: Session = Depends(get_db)):
    """Register or update monitored host record."""
    host = db.get(Host, req.id)
    now = datetime.now(timezone.utc)
    if not host:
        host = Host(
            id=req.id,
            hostname=req.hostname,
            ip=req.ip,
            os=req.os,
            kind=req.kind,
            last_seen=now,
            status="up",
            tags=req.tags,
        )
        db.add(host)
    else:
        host.hostname = req.hostname
        host.ip = req.ip
        host.os = req.os
        host.kind = req.kind
        host.last_seen = now
        host.status = "up"
        host.tags = req.tags

    db.commit()
    db.refresh(host)
    return {"message": "Host registered successfully", "id": host.id}


@router.get("", response_model=List[HostResponse])
def list_hosts(db: Session = Depends(get_db)):
    """List all registered hosts."""
    hosts = db.scalars(select(Host).order_by(Host.hostname)).all()
    return [
        HostResponse(
            id=h.id,
            hostname=h.hostname,
            ip=h.ip,
            os=h.os,
            kind=h.kind,
            last_seen=h.last_seen,
            status=h.status,
            tags=h.tags or {},
        )
        for h in hosts
    ]


@router.get("/{host_id}")
def get_host_detail(host_id: str, db: Session = Depends(get_db)):
    """Retrieve host details, latest metrics, and snapshots."""
    host = db.get(Host, host_id)
    if not host:
        raise HTTPException(status_code=404, detail="Host not found")

    # Get latest metrics
    latest_metrics_query = (
        select(Metric).where(Metric.host_id == host_id).order_by(Metric.ts.desc()).limit(100)
    )
    metrics = db.scalars(latest_metrics_query).all()
    latest_metric_map: Dict[str, Any] = {}
    for m in metrics:
        if m.name not in latest_metric_map:
            latest_metric_map[m.name] = {
                "value": m.value,
                "labels": m.labels,
                "ts": m.ts,
            }

    # Get latest snapshots by kind
    snapshots_query = (
        select(Snapshot).where(Snapshot.host_id == host_id).order_by(Snapshot.ts.desc()).limit(50)
    )
    snapshots = db.scalars(snapshots_query).all()
    latest_snapshots: Dict[str, Any] = {}
    for s in snapshots:
        if s.kind not in latest_snapshots:
            latest_snapshots[s.kind] = s.payload

    return {
        "host": {
            "id": host.id,
            "hostname": host.hostname,
            "ip": host.ip,
            "os": host.os,
            "kind": host.kind,
            "last_seen": host.last_seen,
            "status": host.status,
            "tags": host.tags,
        },
        "latest_metrics": latest_metric_map,
        "snapshots": latest_snapshots,
    }
