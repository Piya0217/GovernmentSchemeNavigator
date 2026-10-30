"""Pydantic schemas and data models for PDF ingestion."""

from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


def _validate_http_url(value: str) -> str:
    """Require an HTTP(S) URL without embedded credentials or whitespace."""
    parsed = urlsplit(value)
    if (
        any(character.isspace() for character in value)
        or parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        msg = "official_source_url must be a valid HTTP(S) URL without credentials."
        raise ValueError(msg)
    return value


SchemeId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
HttpUrlString = Annotated[str, AfterValidator(_validate_http_url)]


class DocumentMetadata(BaseModel):
    """Metadata describing the official scheme document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scheme_id: SchemeId = Field(
        ..., description="Unique identifier for the scheme (e.g. 'pm-kisan')."
    )
    source_document: NonEmptyString = Field(
        ..., description="Filename or path of the source document."
    )
    official_source_url: HttpUrlString = Field(
        ...,
        description="Official government portal URL where the document was published.",
    )
    document_version: NonEmptyString | None = Field(
        default=None, description="Optional version or release year of the document."
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
        description=(
            "Minimum preferred size before choosing a natural split point; "
            "short final chunks are retained to avoid data loss."
        ),
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

    scheme_id: SchemeId = Field(..., description="Unique scheme identifier.")
    source_document: NonEmptyString = Field(..., description="Original PDF file name.")
    official_source_url: HttpUrlString = Field(
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
    extraction_timestamp: AwareDatetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when the chunk was extracted.",
    )
    document_version: NonEmptyString | None = Field(
        default=None,
        description="Document version or revision if specified.",
    )


class ProcessedDocument(BaseModel):
    """Complete structured output of the ingestion pipeline for a scheme PDF."""

    scheme_id: SchemeId
    source_document: NonEmptyString
    official_source_url: HttpUrlString
    document_version: NonEmptyString | None = None
    total_pages: int = Field(..., ge=0)
    total_chunks: int = Field(..., ge=0)
    processed_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    chunks: list[SchemeChunk] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_chunk_consistency(self) -> "ProcessedDocument":
        """Ensure output counts and chunk provenance agree with the document."""
        if self.total_chunks != len(self.chunks):
            msg = "total_chunks must match the number of chunks."
            raise ValueError(msg)
        if any(chunk.scheme_id != self.scheme_id for chunk in self.chunks):
            msg = "Every chunk must have the same scheme_id as the document."
            raise ValueError(msg)
        if any(chunk.page_number > self.total_pages for chunk in self.chunks):
            msg = "Chunk page_number cannot exceed total_pages."
            raise ValueError(msg)
        if sorted(chunk.chunk_index for chunk in self.chunks) != list(
            range(self.total_chunks)
        ):
            msg = "Chunk indexes must be unique and sequential from zero."
            raise ValueError(msg)
        return self
