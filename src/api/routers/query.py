"""Informational query endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.agent.orchestrator import RetrievalUnavailableError
from src.agent.schemas import QueryResponse
from src.api.dependencies import get_api_services
from src.api.errors import ApiServiceError
from src.api.schemas.query import QueryRequest
from src.api.services import ApiServices, SchemeRegistryUnavailableError

router = APIRouter(prefix="/api/query", tags=["query"])


@router.post(
    "",
    response_model=QueryResponse,
    summary="Retrieve official scheme evidence",
)
def query_schemes(
    request: QueryRequest,
    services: Annotated[ApiServices, Depends(get_api_services)],
) -> QueryResponse:
    """Return the retrieval layer's answer and provenance without modification."""
    if request.scheme_id is not None:
        try:
            registry = services.scheme_registry.list_schemes()
        except SchemeRegistryUnavailableError as error:
            raise ApiServiceError(
                503,
                "scheme_registry_unavailable",
                "Scheme information is temporarily unavailable.",
            ) from error
        if not any(item.scheme_id == request.scheme_id for item in registry.schemes):
            raise ApiServiceError(
                404,
                "scheme_not_found",
                "The requested scheme is not present in the scheme registry.",
            )

    try:
        return services.workflow.answer_query(request.query, request.scheme_id)
    except RetrievalUnavailableError as error:
        raise ApiServiceError(
            503,
            "retrieval_unavailable",
            "Official document search is not available.",
        ) from error
