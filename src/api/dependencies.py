"""FastAPI dependencies for the application service container."""

from __future__ import annotations

from fastapi import Request

from src.api.errors import ApiServiceError
from src.api.services import ApiServices


def get_api_services(request: Request) -> ApiServices:
    """Return the service container initialized by application lifespan."""
    services = getattr(request.app.state, "api_services", None)
    if services is None:
        raise ApiServiceError(
            status_code=503,
            code="application_not_initialized",
            message="Application services are not available.",
        )
    return services
