"""Time series metrics query and downsampling router."""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from infraops.server.db import get_db
from infraops.server.models import Metric
from infraops.server.security import verify_api_key

router = APIRouter(prefix="/metrics", tags=["metrics"], dependencies=[Depends(verify_api_key)])


@router.get("")
def query_metrics(
    host_id: str = Query(..., description="Host ID"),
    name: str = Query(..., description="Metric identifier, e.g. cpu.percent"),
    since: Optional[float] = Query(None, description="Start timestamp epoch seconds"),
    until: Optional[float] = Query(None, description="End timestamp epoch seconds"),
    step: Optional[int] = Query(None, description="Bucket downsampling interval in seconds"),
    db: Session = Depends(get_db),
):
    """Retrieve time-series points with optional step downsampling."""
    query = select(Metric).where(Metric.host_id == host_id, Metric.name == name)
    if since is not None:
        query = query.where(Metric.ts >= since)
    if until is not None:
        query = query.where(Metric.ts <= until)
    query = query.order_by(Metric.ts.asc())

    points = db.scalars(query).all()

    if not points:
        return {"host_id": host_id, "name": name, "points": []}

    # If step downsampling requested
    if step and step > 0:
        buckets: Dict[int, List[float]] = {}
        for p in points:
            bucket_ts = int(p.ts // step) * step
            buckets.setdefault(bucket_ts, []).append(p.value)

        downsampled = [
            {"ts": b_ts, "value": round(sum(vals) / len(vals), 2), "count": len(vals)}
            for b_ts, vals in sorted(buckets.items())
        ]
        return {"host_id": host_id, "name": name, "step": step, "points": downsampled}

    raw = [{"ts": p.ts, "value": p.value, "labels": p.labels} for p in points]
    return {"host_id": host_id, "name": name, "points": raw}
