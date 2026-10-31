"""Ingestion package for Government Scheme Navigator."""

from src.ingestion.chunker import chunk_document_pages, split_text_into_chunks
from src.ingestion.cleaner import clean_text
from src.ingestion.exceptions import (
    CorruptedPDFError,
    EmptyPDFError,
    IngestionError,
    ScannedPDFError,
)
from src.ingestion.pdf_loader import load_pdf_pages
from src.ingestion.pipeline import run_ingestion_pipeline
from src.ingestion.schemas import (
    ChunkingConfig,
    DocumentMetadata,
    PageData,
    ProcessedDocument,
    SchemeChunk,
)

__all__ = [
    "ChunkingConfig",
    "CorruptedPDFError",
    "DocumentMetadata",
    "EmptyPDFError",
    "IngestionError",
    "PageData",
    "ProcessedDocument",
    "ScannedPDFError",
    "SchemeChunk",
    "chunk_document_pages",
    "clean_text",
    "load_pdf_pages",
    "run_ingestion_pipeline",
    "split_text_into_chunks",
]
