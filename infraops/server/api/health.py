"""Health and liveness router."""

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health_check():
    """Unauthenticated health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}
