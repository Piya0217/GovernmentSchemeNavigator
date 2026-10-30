"""Scheme registry endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_api_services
from src.api.errors import ApiServiceError
from src.api.schemas.schemes import (
    Jurisdiction,
    SchemeListResponse,
    VerificationStatus,
)
from src.api.services import ApiServices, SchemeRegistryUnavailableError

router = APIRouter(prefix="/api/schemes", tags=["schemes"])


@router.get("", response_model=SchemeListResponse, summary="List registered schemes")
def list_schemes(
    services: Annotated[ApiServices, Depends(get_api_services)],
    jurisdiction: Jurisdiction | None = None,
    verification_status: VerificationStatus | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> SchemeListResponse:
    """Return registry metadata, preserving its verification states and nulls."""
    try:
        return services.scheme_registry.list_schemes(
            jurisdiction=jurisdiction,
            verification_status=verification_status,
            name_query=q,
        )
    except SchemeRegistryUnavailableError as error:
        raise ApiServiceError(
            503,
            "scheme_registry_unavailable",
            "Scheme information is temporarily unavailable.",
        ) from error
