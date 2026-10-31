"""Health-check router.

Provides GET /health — a lightweight liveness probe with no external
dependencies so it is always fast to respond.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from src.api.dependencies import get_api_services
from src.api.schemas.health import ApiHealthResponse
from src.api.services import ApiServices

router = APIRouter(tags=["health"])
api_router = APIRouter(prefix="/api", tags=["health"])


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


@api_router.get(
    "/health",
    response_model=ApiHealthResponse,
    summary="API and component health",
)
def get_api_health(
    request: Request,
    services: Annotated[ApiServices, Depends(get_api_services)],
) -> ApiHealthResponse:
    """Report component readiness without loading the embedding model."""
    registry_status = (
        "ready" if services.scheme_registry.is_available() else "unavailable"
    )
    statuses = [
        services.retrieval_status,
        services.eligibility_status,
        registry_status,
    ]
    return ApiHealthResponse(
        status="ok" if all(status == "ready" for status in statuses) else "degraded",
        version=request.app.version,
        service="government-scheme-navigator",
        retrieval=services.retrieval_status,
        eligibility=services.eligibility_status,
        scheme_registry=registry_status,
    )
