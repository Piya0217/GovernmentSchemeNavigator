"""Text chunking module with page-aware overlapping windows."""

from datetime import UTC, datetime

from src.ingestion.schemas import (
    ChunkingConfig,
    DocumentMetadata,
    PageData,
    SchemeChunk,
)


def _find_split_point(text: str, start: int, max_end: int, min_chunk_size: int) -> int:
    """Find a natural boundary (newline or space) before max_end to avoid cutting words.

    Args:
        text: Full page text.
        start: Start index of current window.
        max_end: Hard maximum cutoff index.
        min_chunk_size: Minimum preferred size before choosing a natural boundary.

    Returns:
        Index where the chunk should end.
    """
    search_start = max(start + 1, start + min_chunk_size)
    slice_to_search = text[search_start:max_end]

    newline_pos = slice_to_search.rfind("\n")
    if newline_pos != -1:
        return search_start + newline_pos

    space_pos = slice_to_search.rfind(" ")
    if space_pos != -1:
        return search_start + space_pos

    return max_end


def split_text_into_chunks(text: str, config: ChunkingConfig) -> list[str]:
    """Split text into overlapping chunks using boundary-aware windows.

    Args:
        text: Normalized text for a page.
        config: Chunking configuration specifying size and overlap.

    Returns:
        List of text chunks.
    """
    cleaned = text.strip()
    if not cleaned:
        return []

    if len(cleaned) <= config.chunk_size:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    text_len = len(cleaned)
    while start < text_len:
        max_end = start + config.chunk_size
        if max_end >= text_len:
            final_piece = cleaned[start:].strip()
            if final_piece:
                chunks.append(final_piece)
            break

        split_point = _find_split_point(cleaned, start, max_end, config.min_chunk_size)
        chunk_piece = cleaned[start:split_point].strip()
        if chunk_piece:
            chunks.append(chunk_piece)

        next_start = split_point - config.chunk_overlap
        if next_start <= start:
            next_start = split_point

        # Skip leading whitespace for next window
        while next_start < text_len and cleaned[next_start].isspace():
            next_start += 1
        start = next_start

    return chunks


def chunk_document_pages(
    pages: list[PageData],
    metadata: DocumentMetadata,
    config: ChunkingConfig | None = None,
) -> list[SchemeChunk]:
    """Split a list of page text data into structured SchemeChunks.

    Args:
        pages: List of extracted page data.  Each page's ``cleaned_text``
            field is used exclusively; ``raw_text`` is never fed to the
            chunker.  Pages whose ``cleaned_text`` is empty (e.g. image-only
            pages whose raw bytes were entirely control characters) produce
            no chunks — they are silently skipped rather than falling back
            to unfiltered bytes.
        metadata: Metadata describing the document and scheme.
        config: Optional ChunkingConfig; defaults to standard 500/100 config.

    Returns:
        List of SchemeChunk objects with complete provenance.
    """
    cfg = config or ChunkingConfig()
    chunks: list[SchemeChunk] = []
    global_index = 0
    now = datetime.now(UTC)

    for page in pages:
        text_to_chunk = page.cleaned_text
        page_chunks = split_text_into_chunks(text_to_chunk, cfg)

        for text in page_chunks:
            chunk = SchemeChunk(
                scheme_id=metadata.scheme_id,
                source_document=metadata.source_document,
                official_source_url=metadata.official_source_url,
                page_number=page.page_number,
                chunk_index=global_index,
                text=text,
                extraction_timestamp=now,
                document_version=metadata.document_version,
            )
            chunks.append(chunk)
            global_index += 1

    return chunks
