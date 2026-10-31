"""Text cleaning and normalization for extracted PDF text."""

import re
import unicodedata

# Non-printable control characters to strip:
#   \x00-\x08  – null, SOH-BS (includes PDF font-ligature artefacts \x01-\x06)
#   \x0b-\x0c  – vertical tab, form feed
#   \x0e-\x1f  – SO through US (shift-out, data-link, etc.)
#   \x7f-\x9f  – DEL + C1 control block (undefined in Unicode, leaked from
#                  subsetted PDF fonts such as PM Vishwakarma guidelines)
#   \ufeff     – BOM / zero-width no-break space
# Deliberately preserved: \x09 (TAB), \x0a (LF), \x0d (CR) — meaningful whitespace.
_CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufeff]")
_TABLE_TAB_PATTERN = re.compile(r"(?<=\S)\t+(?=\S)")
_TABLE_COLUMN_GAP_PATTERN = re.compile(r" {2,}")
_HORIZONTAL_WHITESPACE_PATTERN = re.compile(r"[^\S\n]+")
_MULTIPLE_NEWLINES_PATTERN = re.compile(r"\n{3,}")
_HYPHENATED_WORD_PATTERN = re.compile(r"(\b[a-zA-Z]+)-\n([a-zA-Z]+\b)")


def _clean_control_characters(text: str) -> str:
    """Remove control characters and encoding artefacts while preserving Indic text.

    Strips C0 bytes (0x00-0x08, 0x0B-0x0C, 0x0E-0x1F), which includes the
    PDF font-ligature placeholder bytes 0x01-0x06 emitted by some government
    PDFs (e.g. PM Vishwakarma), the full C1 block (0x7F-0x9F) that leaks from
    subsetted fonts with Windows-1252 glyph mappings, and the Unicode BOM
    (U+FEFF). TAB (0x09), LF (0x0A), and CR (0x0D) are preserved as
    meaningful whitespace.

    Valid Unicode — including Devanagari, Kannada, and other Indic scripts —
    is never affected.

    Args:
        text: Input string.

    Returns:
        String with control artefacts removed.
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
