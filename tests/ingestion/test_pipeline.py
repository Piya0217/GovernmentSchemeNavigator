"""Integration tests for the ingestion pipeline."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from src.ingestion.exceptions import CorruptedPDFError, ScannedPDFError
from src.ingestion.pipeline import run_ingestion_pipeline
from src.ingestion.schemas import ChunkingConfig, DocumentMetadata

from tests.ingestion.conftest import find_indic_font


def test_pipeline_end_to_end_success(
    make_pdf: Callable[..., Path], tmp_path: Path
) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir()
    processed_dir.mkdir()

    pages = [
        "Government of India. Pradhan Mantri Kisan Samman Nidhi.\n"
        "Under the scheme, Rs. 6000 per year is released in three "
        "4-monthly installments.",
        "Eligibility Criteria:\n"
        "1. All landholder farmer families.\n"
        "2. Exclusions: institutional landholders, tax payers.",
    ]
    pdf_path = make_pdf(pages, "pm_kisan.pdf")
    original_bytes = pdf_path.read_bytes()

    metadata = DocumentMetadata(
        scheme_id="pm-kisan",
        source_document=pdf_path.name,
        official_source_url="https://pmkisan.gov.in/guidelines.pdf",
        document_version="2024-v1",
    )
    chunk_config = ChunkingConfig(chunk_size=150, chunk_overlap=30)

    result = run_ingestion_pipeline(
        pdf_path=pdf_path,
        metadata=metadata,
        chunk_config=chunk_config,
        output_dir=processed_dir,
    )

    # 1. Output object validation
    assert result.scheme_id == "pm-kisan"
    assert result.total_pages == 2
    assert result.total_chunks > 0
    assert result.document_version == "2024-v1"

    # 2. Check each chunk has all required fields
    for chunk in result.chunks:
        assert chunk.scheme_id == "pm-kisan"
        assert chunk.source_document == "pm_kisan.pdf"
        assert chunk.official_source_url == "https://pmkisan.gov.in/guidelines.pdf"
        assert chunk.page_number in (1, 2)
        assert isinstance(chunk.chunk_index, int)
        assert len(chunk.text) > 0
        assert chunk.extraction_timestamp is not None
        assert chunk.document_version == "2024-v1"

    # 3. Check JSON output file saved to processed directory
    json_path = processed_dir / "pm-kisan.json"
    assert json_path.exists()
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["scheme_id"] == "pm-kisan"
    assert len(data["chunks"]) == result.total_chunks

    # 4. Verify original PDF is unchanged
    assert pdf_path.read_bytes() == original_bytes


def test_pipeline_unicode_preservation_in_json(
    make_pdf: Callable[..., Path], tmp_path: Path
) -> None:
    font_path = find_indic_font()
    if font_path is None:
        pytest.skip("No system Indic font found on this environment.")

    processed_dir = tmp_path / "processed"
    indic_text = "ಕರ್ನಾಟಕ ರೈತ ಸುರಕ್ಷಾ ಮತ್ತು प्रधान मंत्री फसल बीमा योजना।"
    pdf_path = make_pdf([indic_text], "karnataka_pmfby.pdf", font_path=font_path)

    metadata = DocumentMetadata(
        scheme_id="pmfby-ka",
        source_document=pdf_path.name,
        official_source_url="https://agri.karnataka.gov.in",
    )

    result = run_ingestion_pipeline(
        pdf_path=pdf_path,
        metadata=metadata,
        output_dir=processed_dir,
    )

    json_path = processed_dir / "pmfby-ka.json"
    raw_json_text = json_path.read_text(encoding="utf-8")

    # Verify Unicode is stored directly without \u escaping
    assert "ಕರ್ನಾಟಕ" in raw_json_text
    assert "प्रधान मंत्री" in raw_json_text
    assert result.total_chunks == 1


def test_pipeline_missing_file_raises(tmp_path: Path) -> None:
    metadata = DocumentMetadata(
        scheme_id="test-scheme",
        source_document="missing.pdf",
        official_source_url="https://example.gov.in",
    )
    with pytest.raises(FileNotFoundError):
        run_ingestion_pipeline(
            pdf_path=tmp_path / "missing.pdf",
            metadata=metadata,
            output_dir=tmp_path / "processed",
        )


def test_pipeline_scanned_pdf_raises(
    make_pdf: Callable[..., Path], tmp_path: Path
) -> None:
    pdf_path = make_pdf([""], "scanned.pdf")
    metadata = DocumentMetadata(
        scheme_id="scanned-scheme",
        source_document=pdf_path.name,
        official_source_url="https://example.gov.in",
    )
    with pytest.raises(ScannedPDFError):
        run_ingestion_pipeline(
            pdf_path=pdf_path,
            metadata=metadata,
            output_dir=tmp_path / "processed",
        )


def test_pipeline_corrupted_pdf_raises(tmp_path: Path) -> None:
    corrupt_file = tmp_path / "corrupt.pdf"
    corrupt_file.write_bytes(b"NOT_A_VALID_PDF_STREAM")
    metadata = DocumentMetadata(
        scheme_id="corrupt-scheme",
        source_document=corrupt_file.name,
        official_source_url="https://example.gov.in",
    )
    with pytest.raises(CorruptedPDFError):
        run_ingestion_pipeline(
            pdf_path=corrupt_file,
            metadata=metadata,
            output_dir=tmp_path / "processed",
        )
