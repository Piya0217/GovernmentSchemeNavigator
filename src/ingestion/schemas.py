"""Pydantic schemas and data models for PDF ingestion."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentMetadata(BaseModel):
    """Metadata describing the official scheme document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scheme_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the scheme (e.g. 'pm-kisan').",
    )
    source_document: str = Field(
        ...,
        min_length=1,
        description="Filename or path of the source document.",
    )
    official_source_url: str = Field(
        ...,
        min_length=1,
        description="Official government portal URL where the document was published.",
    )
    document_version: str | None = Field(
        default=None,
        description="Optional version or release year of the document.",
    )


class ChunkingConfig(BaseModel):
    """Configuration options for chunking text."""

    model_config = ConfigDict(frozen=True)

    chunk_size: int = Field(
        default=500,
        gt=0,
        description="Maximum number of characters per chunk.",
    )
    chunk_overlap: int = Field(
        default=100,
        ge=0,
        description="Overlap between consecutive chunks in characters.",
    )
    min_chunk_size: int = Field(
        default=50,
        ge=0,
        description="Minimum character length for a chunk to be preserved.",
    )

    @model_validator(mode="after")
    def validate_overlap(self) -> "ChunkingConfig":
        """Validate that overlap is strictly less than chunk_size."""
        if self.chunk_overlap >= self.chunk_size:
            msg = (
                f"chunk_overlap ({self.chunk_overlap}) must be strictly "
                f"less than chunk_size ({self.chunk_size})."
            )
            raise ValueError(msg)
        if self.min_chunk_size > self.chunk_size:
            msg = (
                f"min_chunk_size ({self.min_chunk_size}) cannot exceed "
                f"chunk_size ({self.chunk_size})."
            )
            raise ValueError(msg)
        return self


class PageData(BaseModel):
    """Extracted text data for an individual PDF page."""

    page_number: int = Field(
        ...,
        ge=1,
        description="1-indexed page number within the PDF document.",
    )
    raw_text: str = Field(
        default="",
        description="Raw text directly extracted from the page.",
    )
    cleaned_text: str = Field(
        default="",
        description="Normalized and cleaned text.",
    )
    is_empty: bool = Field(
        default=False,
        description="Whether the page contained no meaningful text.",
    )


class SchemeChunk(BaseModel):
    """An individual chunk of scheme text with source provenance."""

    model_config = ConfigDict(frozen=True)

    scheme_id: str = Field(..., description="Unique scheme identifier.")
    source_document: str = Field(..., description="Original PDF file name.")
    official_source_url: str = Field(
        ..., description="Official URL for the scheme document."
    )
    page_number: int = Field(
        ...,
        ge=1,
        description="1-indexed page number where this chunk originated.",
    )
    chunk_index: int = Field(
        ...,
        ge=0,
        description="Global 0-indexed sequence position of the chunk in the document.",
    )
    text: str = Field(..., min_length=1, description="Text content of the chunk.")
    extraction_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when the chunk was extracted.",
    )
    document_version: str | None = Field(
        default=None,
        description="Document version or revision if specified.",
    )


class ProcessedDocument(BaseModel):
    """Complete structured output of the ingestion pipeline for a scheme PDF."""

    scheme_id: str
    source_document: str
    official_source_url: str
    document_version: str | None = None
    total_pages: int = Field(..., ge=0)
    total_chunks: int = Field(..., ge=0)
    processed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    chunks: list[SchemeChunk] = Field(default_factory=list)
