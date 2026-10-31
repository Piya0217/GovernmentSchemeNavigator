"""Schemas reflecting the checked-in scheme registry JSON structure."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Jurisdiction = Literal["central", "state"]
VerificationStatus = Literal[
    "verified_digital_text",
    "verified_scanned_image",
    "verified_legacy_font_mapped",
    "unresolved",
]


class SchemeMetadata(BaseModel):
    """One registry entry, retaining additional registry-provided fields."""

    model_config = ConfigDict(extra="allow", frozen=True)

    scheme_id: NonEmptyString
    scheme_name: NonEmptyString
    jurisdiction: Jurisdiction
    issuing_authority: NonEmptyString
    official_source_url: str | None
    portal_url: str | None
    document_title: str | None
    publication_or_effective_date: str | None
    local_filename: str | None
    verification_status: VerificationStatus
    document_metadata: dict[str, Any] | None
    warnings: list[str]
    notes: str | None


class SchemeRegistryDocument(BaseModel):
    """Validated top-level scheme registry document."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    version: NonEmptyString
    last_updated: NonEmptyString
    schemes: list[SchemeMetadata]


class SchemeListResponse(BaseModel):
    """Filtered registry response."""

    model_config = ConfigDict(frozen=True)

    version: str
    last_updated: str
    total: int = Field(ge=0)
    schemes: list[SchemeMetadata]
