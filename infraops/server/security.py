"""API authentication and security guards."""

from typing import Optional

from fastapi import Header, HTTPException, status

from infraops.common.config import get_settings


def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> str:
    """Validate X-API-Key header against server configured key."""
    settings = get_settings()
    if not x_api_key or x_api_key.strip() != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header",
        )
    return x_api_key
