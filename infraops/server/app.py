"""FastAPI application factory and server entry point."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from infraops.server.alerting.engine import AlertEngine
from infraops.server.api import alerts, health, hosts, incidents, ingest, metrics, sops
from infraops.server.db import get_engine, init_db

alert_engine = AlertEngine()
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
