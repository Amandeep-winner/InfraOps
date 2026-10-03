"""Metrics, snapshots, and log events batch ingestion router."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from infraops.common.schemas import IngestBatch
from infraops.server.db import get_db
from infraops.server.models import Host, LogEventModel, Metric, Snapshot
from infraops.server.security import verify_api_key

router = APIRouter(prefix="/ingest", tags=["ingest"], dependencies=[Depends(verify_api_key)])

_alert_engine_evaluator = None


def set_alert_evaluator(evaluator_fn):
    """Register alert evaluation callback invoked on every ingested batch."""
    global _alert_engine_evaluator
    _alert_engine_evaluator = evaluator_fn


@router.post("", status_code=status.HTTP_200_OK)
def ingest_batch(batch: IngestBatch, db: Session = Depends(get_db)):
    """Ingest a batch of metrics, snapshots, and log events from an agent."""
    now = datetime.now(timezone.utc)

    # Upsert host record
    host = db.get(Host, batch.host_id)
    if not host:
        host = Host(
            id=batch.host_id,
            hostname=batch.host_id,
            ip="127.0.0.1",
            os="linux",
            kind="vm",
            last_seen=now,
            status="up",
        )
        db.add(host)
    else:
        host.last_seen = now
        host.status = "up"

    # Store metrics
    metric_rows = [
        Metric(
            host_id=batch.host_id,
            ts=m.ts,
            name=m.name,
            value=m.value,
            labels=m.labels or {},
        )
        for m in batch.metrics
    ]
    if metric_rows:
        db.add_all(metric_rows)

    # Store snapshots
    snapshot_rows = [
        Snapshot(
            host_id=batch.host_id,
            ts=s.ts,
            kind=s.kind,
            payload=s.payload or {},
        )
        for s in batch.snapshots
    ]
    if snapshot_rows:
        db.add_all(snapshot_rows)

    # Store log events
    log_rows = [
        LogEventModel(
            host_id=batch.host_id,
            ts=lg.ts,
            source=lg.source,
            level=lg.level,
            message=lg.message,
            matched_pattern=lg.matched_pattern,
        )
        for lg in batch.log_events
    ]
    if log_rows:
        db.add_all(log_rows)

    db.commit()

    # Trigger alert engine evaluation
    if _alert_engine_evaluator is not None:
        try:
            _alert_engine_evaluator(batch, db)
        except Exception:
            pass

    return {
        "ok": True,
        "metrics_stored": len(metric_rows),
        "snapshots_stored": len(snapshot_rows),
        "log_events_stored": len(log_rows),
    }
