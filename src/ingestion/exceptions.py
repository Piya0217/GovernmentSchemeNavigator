"""Custom exceptions for the PDF ingestion pipeline."""


class IngestionError(Exception):
    """Base exception for all ingestion pipeline errors."""


class CorruptedPDFError(IngestionError):
    """Raised when a PDF file is corrupted, malformed, or unreadable."""


class EmptyPDFError(IngestionError):
    """Raised when a PDF file contains zero pages."""


class ScannedPDFError(IngestionError):
    """Raised when a PDF has pages but no extractable text (e.g. scanned image)."""
