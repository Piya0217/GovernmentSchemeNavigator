"""Fixtures and test helpers for PDF ingestion tests."""

import os
from collections.abc import Callable
from pathlib import Path

import pymupdf
import pytest

_INDIC_FONT_CANDIDATES = [
    "C:/Windows/Fonts/Nirmala.ttc",
    "C:/Windows/Fonts/mangal.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.otf",
]


def find_indic_font() -> str | None:
    """Find a system font that supports Indic scripts (Devanagari/Kannada)."""
    for candidate in _INDIC_FONT_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return None


@pytest.fixture
def make_pdf(tmp_path: Path) -> Callable[..., Path]:
    """Factory fixture to create sample PDFs with specified page contents."""

    def _create(
        pages_text: list[str],
        filename: str = "sample.pdf",
        font_path: str | None = None,
    ) -> Path:
        pdf_path = tmp_path / filename
        doc = pymupdf.open()

        for text in pages_text:
            page = doc.new_page()
            if text:
                if font_path and os.path.exists(font_path):
                    page.insert_font(fontname="f0", fontfile=font_path)
                    page.insert_text((50, 72), text, fontname="f0", fontsize=11)
                else:
                    page.insert_text((50, 72), text, fontsize=11)

        doc.save(str(pdf_path))
        doc.close()
        return pdf_path

    return _create
