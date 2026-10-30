"""Text cleaning and normalization for extracted PDF text."""

import re
import unicodedata

# Form feed, null byte, BOM, and non-printable control characters
_CONTROL_CHARS_PATTERN = re.compile(r"[\x00\x07\x08\x0b\x0c\x0e-\x1f\ufeff]")
_TABLE_TAB_PATTERN = re.compile(r"(?<=\S)\t+(?=\S)")
_TABLE_COLUMN_GAP_PATTERN = re.compile(r" {2,}")
_HORIZONTAL_WHITESPACE_PATTERN = re.compile(r"[^\S\n]+")
_MULTIPLE_NEWLINES_PATTERN = re.compile(r"\n{3,}")
_HYPHENATED_WORD_PATTERN = re.compile(r"(\b[a-zA-Z]+)-\n([a-zA-Z]+\b)")


def _clean_control_characters(text: str) -> str:
    """Remove control characters and encoding artifacts while preserving Indic text.

    Args:
        text: Input string.

    Returns:
        String with control artifacts removed.
    """
    normalized = unicodedata.normalize("NFC", text)
    return _CONTROL_CHARS_PATTERN.sub("", normalized)


def _normalize_line_endings(text: str) -> str:
    """Normalize line endings to standard Unix newlines.

    Args:
        text: Input string.

    Returns:
        String with unified newline characters.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _clean_whitespace(text: str) -> str:
    """Normalize horizontal and excessive vertical whitespace.

    Args:
        text: Input string.

    Returns:
        String with normalized spaces and preserved paragraph breaks.
    """
    lines = text.split("\n")
    table_rows: set[int] = set()
    index = 0
    while index < len(lines):
        if not lines[index].strip() or not _TABLE_COLUMN_GAP_PATTERN.search(
            lines[index]
        ):
            index += 1
            continue
        start = index
        while (
            index < len(lines)
            and lines[index].strip()
            and _TABLE_COLUMN_GAP_PATTERN.search(lines[index])
        ):
            index += 1
        if index - start >= 2:
            table_rows.update(range(start, index))

    cleaned_lines = [
        _HORIZONTAL_WHITESPACE_PATTERN.sub(
            " ",
            _TABLE_COLUMN_GAP_PATTERN.sub(" | ", line)
            if line_index in table_rows
            else line,
        ).strip()
        for line_index, line in enumerate(lines)
    ]
    unified = "\n".join(cleaned_lines)
    collapsed = _MULTIPLE_NEWLINES_PATTERN.sub("\n\n", unified)
    return collapsed.strip()


def clean_text(text: str) -> str:
    """Clean and normalize extracted text without losing substantive information.

    Preserves Unicode characters (including Hindi, Kannada, Tamil, etc.),
    currency symbols, and punctuation.

    Args:
        text: Raw text extracted from a PDF page.

    Returns:
        Cleaned and normalized text.
    """
    if not text:
        return ""

    text = _normalize_line_endings(text)
    text = _clean_control_characters(text)
    # Keep explicit tab-separated cells distinguishable after whitespace cleanup.
    text = _TABLE_TAB_PATTERN.sub(" | ", text)
    text = _HYPHENATED_WORD_PATTERN.sub(r"\1\2", text)
    return _clean_whitespace(text)
