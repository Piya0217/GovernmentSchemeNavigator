"""Unit tests for ingestion Pydantic schemas."""

from datetime import datetime

import pytest
from pydantic import ValidationError
from src.ingestion.schemas import (
    ChunkingConfig,
    DocumentMetadata,
    PageData,
    ProcessedDocument,
    SchemeChunk,
)


def test_document_metadata_valid() -> None:
    meta = DocumentMetadata(
        scheme_id="pm-kisan",
        source_document="pm_kisan_guidelines.pdf",
        official_source_url="https://pmkisan.gov.in/docs.pdf",
        document_version="2024-v1",
    )
    assert meta.scheme_id == "pm-kisan"
    assert meta.document_version == "2024-v1"


def test_document_metadata_missing_field_raises() -> None:
    with pytest.raises(ValidationError):
        DocumentMetadata(  # type: ignore[call-arg]
            scheme_id="pm-kisan",
            source_document="doc.pdf",
        )


@pytest.mark.parametrize("scheme_id", ["../outside", r"..\outside", "../x"])
def test_document_metadata_rejects_path_like_scheme_ids(scheme_id: str) -> None:
    with pytest.raises(ValidationError):
        DocumentMetadata(
            scheme_id=scheme_id,
            source_document="doc.pdf",
            official_source_url="https://example.gov.in/doc.pdf",
        )


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "file:///etc/passwd", "https://user:pass@example.gov.in"],
)
def test_document_metadata_rejects_unsafe_source_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        DocumentMetadata(
            scheme_id="safe-id",
            source_document="doc.pdf",
            official_source_url=url,
        )


def test_chunking_config_defaults() -> None:
    cfg = ChunkingConfig()
    assert cfg.chunk_size == 500
    assert cfg.chunk_overlap == 100
    assert cfg.min_chunk_size == 50


def test_chunking_config_overlap_greater_than_or_equal_size_raises() -> None:
    with pytest.raises(ValueError, match="chunk_overlap .* must be strictly less than"):
        ChunkingConfig(chunk_size=100, chunk_overlap=100)

    with pytest.raises(ValueError, match="chunk_overlap .* must be strictly less than"):
        ChunkingConfig(chunk_size=100, chunk_overlap=120)


def test_chunking_config_min_chunk_size_greater_than_chunk_size_raises() -> None:
    with pytest.raises(ValueError, match="min_chunk_size .* cannot exceed chunk_size"):
        ChunkingConfig(chunk_size=100, chunk_overlap=20, min_chunk_size=150)


def test_page_data_defaults() -> None:
    page = PageData(page_number=1, raw_text="Sample text")
    assert page.page_number == 1
    assert page.raw_text == "Sample text"
    assert not page.is_empty


def test_scheme_chunk_creation() -> None:
    chunk = SchemeChunk(
        scheme_id="pm-kisan",
        source_document="guide.pdf",
        official_source_url="https://pmkisan.gov.in",
        page_number=1,
        chunk_index=0,
        text="All landholding farmers families are eligible.",
    )
    assert chunk.scheme_id == "pm-kisan"
    assert chunk.chunk_index == 0
    assert isinstance(chunk.extraction_timestamp, datetime)
    assert chunk.extraction_timestamp.utcoffset() is not None
    assert chunk.document_version is None


def test_scheme_chunk_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        SchemeChunk(
            scheme_id="pm-kisan",
            source_document="guide.pdf",
            official_source_url="https://pmkisan.gov.in",
            page_number=1,
            chunk_index=0,
            text="Eligibility rules.",
            extraction_timestamp=datetime(2024, 1, 1),
        )


def test_processed_document_rejects_inconsistent_chunk_count() -> None:
    with pytest.raises(ValidationError, match="total_chunks must match"):
        ProcessedDocument(
            scheme_id="pm-kisan",
            source_document="guide.pdf",
            official_source_url="https://pmkisan.gov.in",
            total_pages=1,
            total_chunks=2,
            chunks=[],
        )


def test_processed_document_serialization() -> None:
    chunk = SchemeChunk(
        scheme_id="pm-kisan",
        source_document="guide.pdf",
        official_source_url="https://pmkisan.gov.in",
        page_number=1,
        chunk_index=0,
        text="Sample chunk content.",
    )
    doc = ProcessedDocument(
        scheme_id="pm-kisan",
        source_document="guide.pdf",
        official_source_url="https://pmkisan.gov.in",
        total_pages=1,
        total_chunks=1,
        chunks=[chunk],
    )
    dumped = doc.model_dump(mode="json")
    assert dumped["scheme_id"] == "pm-kisan"
    assert len(dumped["chunks"]) == 1
    assert dumped["chunks"][0]["page_number"] == 1
