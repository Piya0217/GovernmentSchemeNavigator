"""Health-check router.

Provides GET /health — a lightweight liveness probe with no external
dependencies so it is always fast to respond.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response schema for the health endpoint."""

    status: str
    version: str
    service: str


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns service liveness status. No external dependencies checked.",
)
def get_health() -> HealthResponse:
    """Return service health status.

    Returns:
        HealthResponse with status ``ok``, API version, and service name.
    """
    return HealthResponse(
        status="ok",
        version="0.1.0",
        service="government-scheme-navigator",
    )
