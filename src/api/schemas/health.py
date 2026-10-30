"""Health and component-readiness response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

ComponentStatus = Literal[
    "ready",
    "collection_missing",
    "collection_empty",
    "unavailable",
    "not_configured",
]


class ApiHealthResponse(BaseModel):
    """Readiness information for API-owned application components."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "degraded"]
    version: str
    service: str
    retrieval: ComponentStatus
    eligibility: ComponentStatus
    scheme_registry: ComponentStatus
