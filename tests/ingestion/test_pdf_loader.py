"""Unit tests for pdf_loader module."""

from collections.abc import Callable
from pathlib import Path

import pymupdf
import pytest
from src.ingestion.exceptions import (
    CorruptedPDFError,
    EmptyPDFError,
    ScannedPDFError,
)
from src.ingestion.pdf_loader import load_pdf_pages

from tests.ingestion.conftest import find_indic_font


def test_load_pdf_single_page(make_pdf: Callable[..., Path]) -> None:
    pdf_path = make_pdf(["This is page 1 content."], "single.pdf")
    pages = load_pdf_pages(pdf_path)

    assert len(pages) == 1
    assert pages[0].page_number == 1
    assert "This is page 1 content." in pages[0].raw_text
    assert not pages[0].is_empty


def test_load_pdf_multiple_pages(make_pdf: Callable[..., Path]) -> None:
    page_texts = [
        "First page content on scheme overview.",
        "Second page content on criteria.",
        "Third page content on benefits.",
    ]
    pdf_path = make_pdf(page_texts, "multi.pdf")
    pages = load_pdf_pages(pdf_path)

    assert len(pages) == 3
    for i, p in enumerate(pages):
        assert p.page_number == i + 1
        assert page_texts[i] in p.raw_text


def test_load_pdf_with_empty_page_inside(make_pdf: Callable[..., Path]) -> None:
    page_texts = [
        "First page content.",
        "",  # blank page
        "Third page content.",
    ]
    pdf_path = make_pdf(page_texts, "with_blank.pdf")
    pages = load_pdf_pages(pdf_path)

    assert len(pages) == 3
    assert not pages[0].is_empty
    assert pages[1].is_empty
    assert not pages[2].is_empty


def test_load_pdf_scanned_raises_scanned_pdf_error(
    make_pdf: Callable[..., Path],
) -> None:
    # 2 pages with no text content
    pdf_path = make_pdf(["", ""], "scanned.pdf")
    with pytest.raises(ScannedPDFError, match="contains 2 page.*no extractable text"):
        load_pdf_pages(pdf_path)


def test_load_pdf_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    non_existent = tmp_path / "does_not_exist.pdf"
    with pytest.raises(FileNotFoundError):
        load_pdf_pages(non_existent)


def test_load_pdf_corrupted_file_raises_corrupted_pdf_error(
    tmp_path: Path,
) -> None:
    corrupted_path = tmp_path / "corrupt.pdf"
    corrupted_path.write_bytes(b"%PDF-1.4\nGARBAGE_BYTES_NOT_VALID_PDF_DATA")
    with pytest.raises(CorruptedPDFError):
        load_pdf_pages(corrupted_path)


def test_load_pdf_empty_zero_pages_raises_empty_pdf_error(
    tmp_path: Path,
) -> None:
    empty_pdf = tmp_path / "zero_pages.pdf"
    empty_pdf.write_bytes(b"%PDF-1.4\n")

    from unittest.mock import patch

    with patch("src.ingestion.pdf_loader._open_document") as mock_open:
        mock_doc = pymupdf.open()  # in-memory document with 0 pages
        mock_open.return_value = mock_doc

        with pytest.raises(EmptyPDFError, match="contains 0 pages"):
            load_pdf_pages(empty_pdf)


def test_load_pdf_unicode_indic_text(make_pdf: Callable[..., Path]) -> None:
    font_path = find_indic_font()
    if font_path is None:
        pytest.skip("No system Indic font found on this environment.")

    indic_text = "ಕರ್ನಾಟಕ ಮತ್ತು हिन्दी"
    pdf_path = make_pdf([indic_text], "indic.pdf", font_path=font_path)
    pages = load_pdf_pages(pdf_path)

    assert len(pages) == 1
    assert "ಕರ್ನಾಟಕ" in pages[0].raw_text
    assert "हिन्दी" in pages[0].raw_text
