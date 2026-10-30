"""Ingestion pipeline coordinating loading, cleaning, chunking, and JSON output."""

import json
from datetime import UTC, datetime
from pathlib import Path

from src.ingestion.chunker import chunk_document_pages
from src.ingestion.cleaner import clean_text
from src.ingestion.pdf_loader import load_pdf_pages
from src.ingestion.schemas import (
    ChunkingConfig,
    DocumentMetadata,
    PageData,
    ProcessedDocument,
)


def _clean_pages(raw_pages: list[PageData]) -> list[PageData]:
    """Clean the raw text of each page.

    Args:
        raw_pages: Raw page data from the PDF loader.

    Returns:
        List of PageData with cleaned_text populated.
    """
    cleaned_pages: list[PageData] = []
    for page in raw_pages:
        cleaned = clean_text(page.raw_text)
        cleaned_pages.append(
            PageData(
                page_number=page.page_number,
                raw_text=page.raw_text,
                cleaned_text=cleaned,
                is_empty=(len(cleaned) == 0),
            )
        )
    return cleaned_pages


def _save_processed_document(
    doc: ProcessedDocument, output_dir: Path, overwrite: bool = False
) -> Path:
    """Save processed document to a JSON file in the target directory.

    Args:
        doc: ProcessedDocument model instance.
        output_dir: Destination folder path.
        overwrite: Whether to replace an existing artifact.

    Returns:
        Path to the saved JSON file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{doc.scheme_id}.json"
    doc_dict = doc.model_dump(mode="json")

    # Exclusive creation prevents an accidental rerun from silently replacing
    # an existing processed artifact.
    mode = "w" if overwrite else "x"
    with destination.open(mode, encoding="utf-8") as f:
        json.dump(doc_dict, f, ensure_ascii=False, indent=2)

    return destination


def run_ingestion_pipeline(
    pdf_path: Path | str,
    metadata: DocumentMetadata,
    chunk_config: ChunkingConfig | None = None,
    output_dir: Path | str = "data/processed",
    overwrite: bool = False,
) -> ProcessedDocument:
    """Execute the end-to-end ingestion pipeline for a single PDF.

    Args:
        pdf_path: Path to the raw PDF document.
        metadata: Document metadata including scheme ID and official URL.
        chunk_config: Optional chunking parameters (size and overlap).
        output_dir: Directory where processed JSON is written.
        overwrite: Whether to replace an existing processed JSON artifact.

    Returns:
        ProcessedDocument containing all metadata and chunks.
    """
    path = Path(pdf_path).resolve()
    raw_pages = load_pdf_pages(path)
    cleaned_pages = _clean_pages(raw_pages)
    chunks = chunk_document_pages(cleaned_pages, metadata, chunk_config)

    processed_doc = ProcessedDocument(
        scheme_id=metadata.scheme_id,
        source_document=metadata.source_document,
        official_source_url=metadata.official_source_url,
        document_version=metadata.document_version,
        total_pages=len(raw_pages),
        total_chunks=len(chunks),
        processed_at=datetime.now(UTC),
        chunks=chunks,
    )

    _save_processed_document(
        processed_doc, Path(output_dir).resolve(), overwrite=overwrite
    )
    return processed_doc
