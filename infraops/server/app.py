"""FastAPI application factory and server entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infraops.server.api import health, hosts, ingest, metrics
from infraops.server.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for database init and background tasks."""
    init_db()
    yield


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

    return app


app = create_app()


def main():
    """CLI server runner."""
    import uvicorn

    uvicorn.run("infraops.server.app:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
