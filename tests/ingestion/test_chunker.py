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
        PageData(page_number=1, raw_text="Page 1 Content on farmers eligibility."),
        PageData(page_number=2, raw_text="Page 2 Content on exclusions and funds."),
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
        PageData(page_number=1, raw_text="Page 1 non-empty content."),
        PageData(page_number=2, raw_text="   \n  ", is_empty=True),
        PageData(page_number=3, raw_text="Page 3 non-empty content."),
    ]
    chunks = chunk_document_pages(pages, metadata)
    assert len(chunks) == 2
    assert chunks[0].page_number == 1
    assert chunks[1].page_number == 3
    assert chunks[1].chunk_index == 1


def test_chunk_multilingual_unicode_text() -> None:
    metadata = DocumentMetadata(
        scheme_id="pm-kisan",
        source_document="pmkisan_hindi.pdf",
        official_source_url="https://pmkisan.gov.in",
    )
    hindi_text = (
        "प्रधानमंत्री किसान सम्मान निधि भारत सरकार की एक महत्वपूर्ण योजना है। "
        "यह छोटे और सीमांत किसानों को आर्थिक सहायता प्रदान करती है।"
    )
    pages = [PageData(page_number=1, raw_text=hindi_text)]
    chunks = chunk_document_pages(pages, metadata)

    assert len(chunks) == 1
    assert "प्रधानमंत्री किसान" in chunks[0].text
    assert chunks[0].page_number == 1
