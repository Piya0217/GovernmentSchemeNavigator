"""Pydantic schemas and typed data models for the retrieval layer."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class IndexedChunkMetadata(BaseModel):
    """Metadata payload stored alongside an embedded chunk in ChromaDB.

    ChromaDB metadata dictionaries must contain only primitive types
    (str, int, float, bool).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scheme_id: NonEmptyString = Field(
        ..., description="Unique scheme identifier (e.g. 'central_pm_kisan')."
    )
    source_document: NonEmptyString = Field(
        ..., description="Filename of original PDF document."
    )
    official_source_url: str = Field(
        ..., description="Verified official government source URL."
    )
    page_number: int = Field(..., ge=1, description="1-indexed source PDF page number.")
    chunk_index: int = Field(
        ..., ge=0, description="0-indexed position within the source document."
    )
    document_version: str = Field(
        default="", description="Document version string or publication date."
    )
    document_readiness: str = Field(
        default="verified_digital_text",
        description="Verification category from scheme registry.",
    )
    content_hash: str = Field(
        default="", description="SHA-256 hash of the chunk text content."
    )


class IndexedChunk(BaseModel):
    """Full representation of a chunk ready for indexing in vector store."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: NonEmptyString = Field(
        ..., description="Deterministic, collision-resistant unique ID."
    )
    text: NonEmptyString = Field(..., description="Cleaned passage text content.")
    metadata: IndexedChunkMetadata = Field(..., description="Structured metadata.")


class SearchResult(BaseModel):
    """Retrieved scheme passage with strict source attribution and scoring.

    Safety & Integrity (AGENTS.md):
    - Raw vector distance is clearly separated from normalized similarity score.
    - No eligibility inferences or assertions are included.
    """

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    scheme_id: str
    source_document: str
    official_source_url: str
    page_number: int
    chunk_index: int
    document_version: str | None = None
    document_readiness: str
    text: str
    distance: float = Field(
        ...,
        description="Raw cosine distance reported by ChromaDB in range [0.0, 2.0].",
    )
    similarity_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalized similarity metric in range [0.0, 1.0].",
    )
    rerank_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Optional deterministic question-passage reranking score in [0.0, 1.0]. "
            "Separated from raw vector distance to preserve auditability."
        ),
    )


class DocumentIndexRecord(BaseModel):
    """Record of an indexed document for change detection and idempotency."""

    model_config = ConfigDict(frozen=True)

    scheme_id: str
    source_file: str
    content_sha256: str
    chunk_count: int
    chunk_ids: list[str]
    indexed_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class IndexManifest(BaseModel):
    """Persistent manifest recording indexing status and model compatibility."""

    model_config = ConfigDict(frozen=True)

    manifest_version: str = "1.0.0"
    embedding_model: str
    embedding_dimension: int
    documents: dict[str, DocumentIndexRecord] = Field(default_factory=dict)
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class SearchQuery(BaseModel):
    """Input query parameters for semantic search."""

    query: NonEmptyString = Field(..., description="Search query string.")
    top_k: int = Field(default=5, ge=1, le=50, description="Max results to return.")
    scheme_id: str | None = Field(
        default=None, description="Optional scheme_id filter."
    )
    max_distance: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Optional maximum cosine distance threshold.",
    )
