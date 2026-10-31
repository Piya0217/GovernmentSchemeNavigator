"""Typed, immutable schemas for source and rule-evidence catalogues."""

from __future__ import annotations

import hashlib
from datetime import date
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    StringConstraints,
    model_validator,
)

NonEmptyString = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=512),
]
StableId = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=3,
        max_length=160,
        pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$",
    ),
]
Sha256 = Annotated[StrictStr, StringConstraints(pattern=r"^[a-fA-F0-9]{64}$")]


def _validate_http_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        any(character.isspace() for character in value)
        or parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("official_source_url must be a valid HTTP(S) URL.")
    return value


def _validate_data_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        "\\" in value
        or path.is_absolute()
        or not value.startswith("data/raw/")
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("local_path must stay within repository-relative data/raw/.")
    return value


HttpUrl = Annotated[StrictStr, AfterValidator(_validate_http_url)]
DataRawPath = Annotated[StrictStr, AfterValidator(_validate_data_path)]


class SourceIdentityStatus(StrEnum):
    """Whether official source identity has been checked."""

    UNASSESSED = "unassessed"
    OFFICIAL_HOSTING_CONFIRMED = "official_hosting_confirmed"
    OFFICIAL_HOSTING_NOT_CONFIRMED = "official_hosting_not_confirmed"


class ByteMatchStatus(StrEnum):
    """Whether local document bytes were compared with official bytes."""

    UNASSESSED = "unassessed"
    MATCH = "match"
    MISMATCH = "mismatch"


class ContentReviewStatus(StrEnum):
    """Whether the document content has received human review."""

    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"


class CurrentnessStatus(StrEnum):
    """Assessment of whether a source is current."""

    UNASSESSED = "unassessed"
    CURRENT = "current"
    OUTDATED = "outdated"
    UNKNOWN = "unknown"


class EvidenceRelationship(StrEnum):
    """How a source passage supports or qualifies a candidate rule."""

    PRIMARY = "primary"
    SUPPORTING = "supporting"
    EXCEPTION = "exception"
    AMENDMENT = "amendment"
    CLARIFICATION = "clarification"


class DocumentRelationshipType(StrEnum):
    """Explicit document relationship without implied legal precedence."""

    AMENDMENT = "amendment"
    CLARIFICATION = "clarification"
    RELATED = "related"


class DocumentRelationship(BaseModel):
    """Explicit relation to another document and, when known, its provisions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: StableId
    relationship: DocumentRelationshipType
    affected_provisions: tuple[NonEmptyString, ...] = ()


class SourceCheckObservation(BaseModel):
    """Dated source-check observation; it does not assert currentness by itself."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    last_checked_at: AwareDatetime | None = None
    checked_by: NonEmptyString | None = None
    check_notes: NonEmptyString | None = None


class SourceDocument(BaseModel):
    """Stable document identity and independent verification state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: StableId
    scheme_id: StableId
    title: NonEmptyString
    issuing_authority: NonEmptyString | None = None
    official_source_url: HttpUrl
    local_path: DataRawPath | None = None
    local_pdf_sha256: Sha256 | None = None
    publication_date: date | None = None
    effective_date: date | None = None
    document_version: NonEmptyString | None = None
    document_version_basis: NonEmptyString | None = None
    source_identity_status: SourceIdentityStatus = SourceIdentityStatus.UNASSESSED
    byte_match_status: ByteMatchStatus = ByteMatchStatus.UNASSESSED
    content_review_status: ContentReviewStatus = ContentReviewStatus.UNREVIEWED
    currentness_status: CurrentnessStatus = CurrentnessStatus.UNKNOWN
    check_observation: SourceCheckObservation = Field(
        default_factory=SourceCheckObservation
    )
    relationships: tuple[DocumentRelationship, ...] = ()

    @model_validator(mode="after")
    def validate_source_metadata(self) -> SourceDocument:
        if (self.local_path is None) != (self.local_pdf_sha256 is None):
            raise ValueError(
                "local_path and local_pdf_sha256 must be supplied together."
            )
        if (self.document_version is None) != (self.document_version_basis is None):
            raise ValueError(
                "A document version requires its explicit supporting basis."
            )
        return self


class SchemeRegistryEntry(BaseModel):
    """Additive scheme registry schema that retains unmodeled legacy fields."""

    model_config = ConfigDict(extra="allow")

    scheme_id: StableId
    verification_status: NonEmptyString
    source_documents: tuple[SourceDocument, ...] = ()


class SchemeRegistry(BaseModel):
    """Scheme registry envelope; extra legacy envelope fields are preserved."""

    model_config = ConfigDict(extra="allow")

    version: NonEmptyString
    schemes: tuple[SchemeRegistryEntry, ...]


class EvidenceRecord(BaseModel):
    """Page-level evidence passage with separate excerpt and retrieval hashes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: StableId
    scheme_id: StableId
    document_id: StableId
    page_number: int = Field(ge=1, strict=True)
    section: NonEmptyString | None = None
    excerpt: NonEmptyString
    excerpt_sha256: Sha256
    retrieval_chunk_sha256: tuple[Sha256, ...] = ()
    is_synthetic: StrictBool = False
    is_exact_source_text: StrictBool = False

    @model_validator(mode="after")
    def validate_excerpt(self) -> EvidenceRecord:
        digest = hashlib.sha256(self.excerpt.encode("utf-8")).hexdigest()
        if self.excerpt_sha256.lower() != digest:
            raise ValueError("excerpt_sha256 must match the exact excerpt UTF-8 bytes.")
        if self.is_synthetic:
            if not self.excerpt.startswith("[SYNTHETIC TEST DATA]"):
                raise ValueError(
                    "Synthetic excerpts must carry the explicit synthetic marker."
                )
        elif not self.is_exact_source_text:
            raise ValueError(
                "Non-synthetic excerpts must be marked as exact source text."
            )
        return self


class EvidenceCatalogue(BaseModel):
    """Versioned page/section evidence catalogue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: NonEmptyString
    evidence: tuple[EvidenceRecord, ...] = ()


class RuleEvidenceLink(BaseModel):
    """Sidecar link from a PENDING rule candidate to one source passage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: StableId
    scheme_id: StableId
    document_id: StableId
    evidence_id: StableId
    document_version: NonEmptyString
    relationship: EvidenceRelationship
    status: Literal["PENDING"] = "PENDING"


class RuleEvidenceSidecar(BaseModel):
    """Rule-to-evidence links kept separate from Phase 3 rule models."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: NonEmptyString
    links: tuple[RuleEvidenceLink, ...] = ()


class CatalogueIssue(BaseModel):
    """Stable machine-readable catalogue validation issue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: NonEmptyString
    location: NonEmptyString
    message: NonEmptyString


def candidate_document_version(document: SourceDocument) -> str:
    """Return a verified catalogue version or block candidate creation."""
    if document.document_version is None:
        raise ValueError(
            f"Rule candidate creation is blocked: document {document.document_id} "
            "has no explicitly supported version."
        )
    return document.document_version


__all__ = [
    "CatalogueIssue",
    "ByteMatchStatus",
    "ContentReviewStatus",
    "CurrentnessStatus",
    "DataRawPath",
    "DocumentRelationship",
    "DocumentRelationshipType",
    "EvidenceCatalogue",
    "EvidenceRecord",
    "EvidenceRelationship",
    "RuleEvidenceLink",
    "RuleEvidenceSidecar",
    "SchemeRegistry",
    "SchemeRegistryEntry",
    "SourceCheckObservation",
    "SourceDocument",
    "SourceIdentityStatus",
    "candidate_document_version",
]
