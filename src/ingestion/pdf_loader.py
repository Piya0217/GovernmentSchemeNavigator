"""PDF extraction module using PyMuPDF."""

from pathlib import Path

import pymupdf

from src.ingestion.exceptions import (
    CorruptedPDFError,
    EmptyPDFError,
    ScannedPDFError,
)
from src.ingestion.schemas import PageData


def _extract_page(page: pymupdf.Page, page_number: int) -> PageData:
    """Extract text from a single PDF page into a PageData object.

    Args:
        page: PyMuPDF Page instance.
        page_number: 1-indexed page number.

    Returns:
        PageData containing extracted text and empty status.
    """
    raw_text: str = page.get_text("text")
    stripped = raw_text.strip()
    if not stripped and page.get_images(full=True):
        msg = (
            f"PDF page {page_number} contains images but no extractable text. "
            "It may be a scanned page and requires OCR."
        )
        raise ScannedPDFError(msg)
    return PageData(
        page_number=page_number,
        raw_text=raw_text,
        cleaned_text="",
        is_empty=(len(stripped) == 0),
    )


def _open_document(path: Path) -> pymupdf.Document:
    """Safely open a PDF document using PyMuPDF.

    Args:
        path: Path to the PDF file.

    Returns:
        Opened pymupdf.Document.

    Raises:
        FileNotFoundError: If the file does not exist.
        CorruptedPDFError: If the file is not a valid PDF or is corrupted.
    """
    if not path.exists():
        msg = f"PDF file not found at path: {path}"
        raise FileNotFoundError(msg)
    if not path.is_file():
        msg = f"Path is not a regular file: {path}"
        raise FileNotFoundError(msg)

    try:
        return pymupdf.open(str(path))
    except (pymupdf.FileDataError, pymupdf.EmptyFileError, ValueError) as err:
        msg = f"Failed to open PDF due to corruption or invalid format: {path}"
        raise CorruptedPDFError(msg) from err
    except Exception as err:
        msg = f"Unexpected error while opening PDF file: {path}"
        raise CorruptedPDFError(msg) from err


def load_pdf_pages(file_path: Path | str) -> list[PageData]:
    """Extract page-wise text from a PDF file.

    Args:
        file_path: Path to the target PDF file.

    Returns:
        List of PageData objects representing each page.

    Raises:
        FileNotFoundError: If the PDF does not exist.
        EmptyPDFError: If the PDF has zero pages.
        ScannedPDFError: If no extractable text is found across any page.
        CorruptedPDFError: If the PDF is corrupted or invalid.
    """
    path = Path(file_path).resolve()
    doc = _open_document(path)

    try:
        page_count = len(doc)
        if page_count == 0:
            msg = f"PDF contains 0 pages: {path}"
            raise EmptyPDFError(msg)

        pages: list[PageData] = [
            _extract_page(doc[i], i + 1) for i in range(page_count)
        ]

        total_text = "".join(p.raw_text.strip() for p in pages)
        if len(total_text) == 0:
            msg = (
                f"PDF at {path} contains {page_count} page(s) but no extractable "
                "text. It may be a scanned or image-only PDF."
            )
            raise ScannedPDFError(msg)

        return pages
    except (EmptyPDFError, ScannedPDFError, CorruptedPDFError):
        raise
    except Exception as err:
        msg = f"Failed to extract pages from PDF; the file may be corrupted: {path}"
        raise CorruptedPDFError(msg) from err
    finally:
        doc.close()
