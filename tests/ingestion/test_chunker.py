"""Unit tests for text chunker module."""

from src.ingestion.chunker import chunk_document_pages, split_text_into_chunks
from src.ingestion.schemas import ChunkingConfig, DocumentMetadata, PageData


def test_split_text_smaller_than_chunk_size() -> None:
    text = "Short text under chunk size."
    cfg = ChunkingConfig(chunk_size=100, chunk_overlap=20)
    chunks = split_text_into_chunks(text, cfg)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_text_empty_returns_empty_list() -> None:
    cfg = ChunkingConfig()
    assert split_text_into_chunks("", cfg) == []
    assert split_text_into_chunks("   \n   ", cfg) == []


def test_split_text_overlapping_windows() -> None:
    words = ["Word" + str(i) for i in range(100)]
    long_text = " ".join(words)
    cfg = ChunkingConfig(chunk_size=100, chunk_overlap=30)
    chunks = split_text_into_chunks(long_text, cfg)

    assert len(chunks) > 1
    # Check that chunks overlap (subsequent chunk contains parts from preceding window)
    for c in chunks:
        assert len(c) <= 120  # boundary snapping allows small leeway


def test_split_text_keeps_every_word_with_zero_and_high_overlap() -> None:
    words = [f"rule-{index:03}" for index in range(80)]
    text = " ".join(words)

    for overlap in (0, 29):
        config = ChunkingConfig(
            chunk_size=30,
            chunk_overlap=overlap,
            min_chunk_size=5,
        )
        chunks = split_text_into_chunks(text, config)
        assert chunks
        assert all(len(chunk) <= config.chunk_size for chunk in chunks)
        assert all(any(word in chunk for chunk in chunks) for word in words)


def test_min_chunk_size_avoids_tiny_early_chunk() -> None:
    text = "a\nbcdefghijklmnopqrstuvwxyz"
    config = ChunkingConfig(
        chunk_size=12,
        chunk_overlap=0,
        min_chunk_size=6,
    )

    chunks = split_text_into_chunks(text, config)

    assert len(chunks[0]) >= config.min_chunk_size


def test_chunk_document_pages_provenance() -> None:
    metadata = DocumentMetadata(
        scheme_id="pm-kisan",
        source_document="pmkisan.pdf",
        official_source_url="https://pmkisan.gov.in",
        document_version="v1.0",
    )
    pages = [
        PageData(
            page_number=1,
            raw_text="Page 1 Content on farmers eligibility.",
            cleaned_text="Page 1 Content on farmers eligibility.",
        ),
        PageData(
            page_number=2,
            raw_text="Page 2 Content on exclusions and funds.",
            cleaned_text="Page 2 Content on exclusions and funds.",
        ),
    ]
    cfg = ChunkingConfig(chunk_size=200, chunk_overlap=50)
    chunks = chunk_document_pages(pages, metadata, cfg)

    assert len(chunks) == 2
    assert chunks[0].page_number == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].scheme_id == "pm-kisan"
    assert chunks[0].document_version == "v1.0"
    assert chunks[1].page_number == 2
    assert chunks[1].chunk_index == 1


def test_chunk_document_pages_skips_empty_pages() -> None:
    metadata = DocumentMetadata(
        scheme_id="pm-kisan",
        source_document="pmkisan.pdf",
        official_source_url="https://pmkisan.gov.in",
    )
    pages = [
        PageData(
            page_number=1,
            raw_text="Page 1 non-empty content.",
            cleaned_text="Page 1 non-empty content.",
        ),
        PageData(
            page_number=2,
            raw_text="   \n  ",
            cleaned_text="",
            is_empty=True,
        ),
        PageData(
            page_number=3,
            raw_text="Page 3 non-empty content.",
            cleaned_text="Page 3 non-empty content.",
        ),
    ]
    chunks = chunk_document_pages(pages, metadata)
    assert len(chunks) == 2
    assert chunks[0].page_number == 1
    assert chunks[1].page_number == 3
    assert chunks[1].chunk_index == 1


# ---------------------------------------------------------------------------
# Regression: all-control-char page must NOT fall back to raw_text
# ---------------------------------------------------------------------------


def test_chunk_document_pages_control_char_page_produces_no_chunks() -> None:
    """A page whose raw_text is entirely C0 control bytes must yield 0 chunks.

    Root-cause: the previous ``cleaned_text or raw_text`` fallback fed raw
    bytes into the chunker when cleaning reduced the page to an empty string.
    After the fix, cleaned_text is used exclusively; empty == no chunks.
    """
    metadata = DocumentMetadata(
        scheme_id="pm-vish",
        source_document="vish.pdf",
        official_source_url="https://pmvishwakarma.gov.in",
    )
    # Simulate a PDF page whose extracted bytes are all control characters.
    raw = "\x1b\x1a\x19\x18\x1d\x17\x16\x15\x14\x13\x1e\x0e\x0f\x10\x11"
    # After clean_text these become empty.
    from src.ingestion.cleaner import clean_text

    cleaned = clean_text(raw)
    assert cleaned == "", "pre-condition: control chars must clean to empty string"

    pages = [
        PageData(
            page_number=3,
            raw_text=raw,
            cleaned_text=cleaned,  # empty — as pipeline sets it
            is_empty=True,
        ),
    ]
    chunks = chunk_document_pages(pages, metadata)
    assert chunks == [], (
        "A page of pure control characters must produce zero chunks, "
        "not fall back to unfiltered raw_text."
    )


def test_chunk_multilingual_unicode_text() -> None:
    metadata = DocumentMetadata(
        scheme_id="pm-kisan",
        source_document="pmkisan_hindi.pdf",
        official_source_url="https://pmkisan.gov.in",
    )
    # Short Hindi phrase: "PM Kisan – Government of India scheme."
    # fmt: off
    _pm     = "\u092a\u094d\u0930\u0927\u093e\u0928\u092e\u0902\u0924\u094d\u0930\u0940"
    _kisan  = "\u0915\u093f\u0938\u093e\u0928"
    _gov    = "\u092d\u093e\u0930\u0924 \u0938\u0930\u0915\u093e\u0930"
    _scheme = "\u0915\u0940 \u092f\u094b\u091c\u0928\u093e \u0939\u0948\u0964"
    # fmt: on
    hindi_text = f"{_pm} {_kisan} {_gov} {_scheme}"
    pages = [
        PageData(
            page_number=1,
            raw_text=hindi_text,
            cleaned_text=hindi_text,
        )
    ]
    chunks = chunk_document_pages(pages, metadata)

    assert len(chunks) == 1
    assert _pm in chunks[0].text  # "प्रधानमंत्री" present
    assert chunks[0].page_number == 1
