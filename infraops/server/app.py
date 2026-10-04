"""FastAPI application factory and server entry point."""

import asyncio
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from infraops.common.config import get_settings
from infraops.server.alerting.engine import AlertEngine
from infraops.server.alerting.rules import AlertRule
from infraops.server.api import alerts, health, hosts, incidents, ingest, metrics, sops
from infraops.server.db import get_engine, init_db
from infraops.server.incidents.service import IncidentService
from infraops.server.models import Alert, Incident
from infraops.server.sop.engine import SOPEngine

alert_engine = AlertEngine()
sop_engine = SOPEngine()


def on_alert_triggered(alert: Alert, rule: AlertRule, db: Session):
    """Callback when an alert rule with a SOP triggers."""
    if not rule.sop:
        return

    # Check for existing open incident for this SOP on target host
    open_inc = db.scalars(
        select(Incident).where(
            Incident.host_id == alert.host_id,
            Incident.sop_id == rule.sop,
            Incident.state.notin_(["RESOLVED", "CLOSED", "ESCALATED"]),
        )
    ).first()
    if open_inc:
        alert.incident_id = open_inc.id
        return

    settings = get_settings()
    mode = "auto" if settings.auto_remediate else "manual"
    title = rule.summary or f"{rule.id} threshold breached on {alert.host_id}"
    title = title.replace("{value}", f"{alert.value:.0f}").replace("{host_id}", alert.host_id)

    incident = IncidentService.create_incident(
        db=db,
        title=title,
        host_id=alert.host_id,
        severity=rule.severity,
        sop_id=rule.sop,
        mode=mode,
        initial_event_msg=f"Alert '{rule.id}' triggered. Initiating {rule.sop} in {mode} mode.",
    )
    alert.incident_id = incident.id
    db.commit()

    target_host_id = str(incident.host_id)
    target_sop_id = str(incident.sop_id)
    target_inc_id = str(incident.id)

    def _execute():
        engine = get_engine()
        with Session(engine) as s:
            sop_engine.run_sop(
                sop_id=target_sop_id,
                incident_id=target_inc_id,
                host_id=target_host_id,
                db=s,
                mode=mode,
            )

    thread = threading.Thread(target=_execute, daemon=True)
    thread.start()


alert_engine.set_incident_callback(on_alert_triggered)
ingest.set_alert_evaluator(lambda batch, db: alert_engine.evaluate_batch(batch, db))


async def heartbeat_worker():
    """Background task running stale host checks periodically."""
    engine = get_engine()
    while True:
        try:
            with Session(engine) as db:
                alert_engine.check_stale_hosts(db)
        except Exception:
            pass
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for database init and background tasks."""
    init_db()
    task = asyncio.create_task(heartbeat_worker())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="InfraOps",
        description="Infrastructure Monitoring & Incident Response Platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Enable CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include core API routers
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(hosts.router, prefix="/api/v1")
    app.include_router(ingest.router, prefix="/api/v1")
    app.include_router(metrics.router, prefix="/api/v1")
    app.include_router(alerts.router, prefix="/api/v1")
    app.include_router(incidents.router, prefix="/api/v1")
    app.include_router(sops.router, prefix="/api/v1")

    return app


app = create_app()


def main():
    """CLI server runner."""
    import uvicorn

    uvicorn.run("infraops.server.app:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
