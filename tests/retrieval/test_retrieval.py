"""Comprehensive unit tests for retrieval, indexing, and semantic search."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from pathlib import Path

import chromadb
import pytest
from src.ingestion.schemas import (
    ProcessedDocument,
    SchemeChunk,
)
from src.retrieval.embedder import BaseEmbedder, EmbedderError
from src.retrieval.indexer import (
    IndexerError,
    SchemeIndexer,
    get_verified_schemes_from_registry,
    is_meaningful_chunk,
)
from src.retrieval.search import SchemeSearcher
from src.retrieval.store import ChromaVectorStore, VectorStoreError

# ---------------------------------------------------------------------------
# Test Helpers & Fake Embedder (Zero external model downloads)
# ---------------------------------------------------------------------------


class FakeDeterministicEmbedder(BaseEmbedder):
    """Deterministic, CPU-only test embedder using SHA-256 hashes as vectors."""

    def __init__(
        self,
        model_name: str = "fake-multilingual-test-v1",
        dimension: int = 16,
    ) -> None:
        self._model_name = model_name
        self._dimension = dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _hash_to_vector(self, text: str) -> list[float]:
        # Generate dimension-sized vector from MD5/SHA256
        h = hashlib.sha256(text.encode("utf-8")).digest()
        raw = [float(b % 100) - 50.0 for b in h[: self._dimension]]
        # Normalize to unit length
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._hash_to_vector(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        if not query.strip():
            msg = "Query text is empty"
            raise EmbedderError(msg)
        return self._hash_to_vector(query.strip())


def make_sample_processed_doc(
    scheme_id: str = "central_pm_kisan",
    num_chunks: int = 3,
    version: str = "2020-03-29",
) -> ProcessedDocument:
    """Helper to generate a valid ProcessedDocument with predictable text."""
    chunks = []
    for i in range(num_chunks):
        chunks.append(
            SchemeChunk(
                scheme_id=scheme_id,
                source_document=f"{scheme_id}_guidelines.pdf",
                official_source_url=f"https://example.gov.in/{scheme_id}.pdf",
                page_number=i + 1,
                chunk_index=i,
                text=(
                    f"Substantive paragraph {i} for {scheme_id} detailing specific "
                    "benefits, operational financial guidelines, and citizen support."
                ),
                document_version=version,
            )
        )

    return ProcessedDocument(
        scheme_id=scheme_id,
        source_document=f"{scheme_id}_guidelines.pdf",
        official_source_url=f"https://example.gov.in/{scheme_id}.pdf",
        document_version=version,
        total_pages=num_chunks,
        total_chunks=num_chunks,
        chunks=chunks,
    )


# ---------------------------------------------------------------------------
# Unit Tests: Noise Filtering
# ---------------------------------------------------------------------------


def test_is_meaningful_chunk_valid() -> None:
    text = (
        "Pradhan Mantri Kisan Samman Nidhi provides financial benefit to eligible "
        "landholding farmer families."
    )
    assert is_meaningful_chunk(text) is True


def test_is_meaningful_chunk_filters_noise() -> None:
    # Empty / whitespace
    assert is_meaningful_chunk("") is False
    assert is_meaningful_chunk("   \n\t  ") is False

    # Short / table of contents / soft-hyphens
    assert is_meaningful_chunk("\xad") is False
    assert is_meaningful_chunk("\xad\n\nTABLE OF CONTENTS\n\n\xad") is False

    # Numbers only (e.g. isolated page numbers)
    assert is_meaningful_chunk("26") is False
    assert is_meaningful_chunk("40") is False
    assert is_meaningful_chunk("123456789012345678901234567890") is False

    # Short phrases below threshold
    assert is_meaningful_chunk("Short note.") is False


# ---------------------------------------------------------------------------
# Unit Tests: Store & Model Mixing Prevention
# ---------------------------------------------------------------------------


def test_chroma_store_prevents_mixing_models() -> None:
    chroma_client = chromadb.EphemeralClient()
    store = ChromaVectorStore(client=chroma_client)

    # Create collection with model A
    store.get_or_create_collection(
        collection_name="test_col",
        expected_model="model_alpha",
        expected_dim=16,
    )

    # Connecting with matching model succeeds
    col = store.get_or_create_collection(
        collection_name="test_col",
        expected_model="model_alpha",
        expected_dim=16,
    )
    assert col is not None

    # Connecting with different model raises VectorStoreError
    with pytest.raises(VectorStoreError, match="indexed with model 'model_alpha'"):
        store.get_or_create_collection(
            collection_name="test_col",
            expected_model="model_beta",
            expected_dim=16,
        )


# ---------------------------------------------------------------------------
# Unit Tests: Idempotency, Change Detection, and Stale Chunk Removal
# ---------------------------------------------------------------------------


def test_indexer_idempotent_duplicate_indexing(tmp_path: Path) -> None:
    chroma_client = chromadb.EphemeralClient()
    store = ChromaVectorStore(client=chroma_client)
    embedder = FakeDeterministicEmbedder()

    indexer = SchemeIndexer(
        vector_store=store,
        embedder=embedder,
        collection_name="test_idempotent",
        manifest_dir=tmp_path,
    )

    doc = make_sample_processed_doc("central_pm_kisan", num_chunks=3)
    json_path = tmp_path / "central_pm_kisan.json"
    json_path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")

    # Initial indexing: 3 chunks stored
    count, skipped = indexer.index_processed_file(json_path)
    assert count == 3
    assert skipped is False
    assert store.count("test_idempotent") == 3

    # Re-indexing without change: should be skipped idempotently
    count2, skipped2 = indexer.index_processed_file(json_path)
    assert count2 == 3
    assert skipped2 is True
    # Count in Chroma store remains exactly 3 (no duplicate chunks)
    assert store.count("test_idempotent") == 3


def test_indexer_cleans_stale_chunks_on_update(tmp_path: Path) -> None:
    chroma_client = chromadb.EphemeralClient()
    store = ChromaVectorStore(client=chroma_client)
    embedder = FakeDeterministicEmbedder()

    indexer = SchemeIndexer(
        vector_store=store,
        embedder=embedder,
        collection_name="test_stale",
        manifest_dir=tmp_path,
    )

    json_path = tmp_path / "central_pmjay.json"

    # Step 1: Write document with 3 chunks
    doc_initial = make_sample_processed_doc("central_pmjay", num_chunks=3)
    json_path.write_text(doc_initial.model_dump_json(indent=2), encoding="utf-8")

    count1, _ = indexer.index_processed_file(json_path)
    assert count1 == 3
    assert store.count("test_stale") == 3

    # Step 2: Update document so it now only has 1 chunk (simulating shrunk content)
    doc_shrunk = make_sample_processed_doc("central_pmjay", num_chunks=1)
    json_path.write_text(doc_shrunk.model_dump_json(indent=2), encoding="utf-8")

    count2, skipped2 = indexer.index_processed_file(json_path)
    assert count2 == 1
    assert skipped2 is False
    # Crucial: stale chunks were removed; store has exactly 1 chunk, NOT 3 or 4
    assert store.count("test_stale") == 1


def test_indexer_missing_file_raises_actionable_error(tmp_path: Path) -> None:
    chroma_client = chromadb.EphemeralClient()
    store = ChromaVectorStore(client=chroma_client)
    embedder = FakeDeterministicEmbedder()

    indexer = SchemeIndexer(
        vector_store=store,
        embedder=embedder,
        manifest_dir=tmp_path,
    )

    missing_path = tmp_path / "non_existent.json"
    with pytest.raises(IndexerError, match="Processed JSON file not found"):
        indexer.index_processed_file(missing_path)


# ---------------------------------------------------------------------------
# Unit Tests: Registry Filter
# ---------------------------------------------------------------------------


def test_get_verified_schemes_from_registry(tmp_path: Path) -> None:
    reg_json = {
        "schemes": [
            {
                "scheme_id": "verified_one",
                "verification_status": "verified_digital_text",
            },
            {
                "scheme_id": "scanned_two",
                "verification_status": "verified_scanned_image",
            },
            {
                "scheme_id": "legacy_three",
                "verification_status": "verified_legacy_font_mapped",
            },
        ]
    }
    import json

    registry_file = tmp_path / "reg.json"
    registry_file.write_text(json.dumps(reg_json), encoding="utf-8")

    verified = get_verified_schemes_from_registry(registry_file)
    assert verified == {"verified_one"}


# ---------------------------------------------------------------------------
# Unit Tests: Semantic Search & Provenance
# ---------------------------------------------------------------------------


def test_searcher_retrieval_and_provenance(tmp_path: Path) -> None:
    chroma_client = chromadb.EphemeralClient()
    store = ChromaVectorStore(client=chroma_client)
    embedder = FakeDeterministicEmbedder()

    indexer = SchemeIndexer(
        vector_store=store,
        embedder=embedder,
        collection_name="test_search",
        manifest_dir=tmp_path,
    )

    # Index two documents
    doc_kisan = make_sample_processed_doc("central_pm_kisan", num_chunks=2)
    doc_pmjay = make_sample_processed_doc("central_pmjay", num_chunks=2)

    p1 = tmp_path / "central_pm_kisan.json"
    p2 = tmp_path / "central_pmjay.json"
    p1.write_text(doc_kisan.model_dump_json(indent=2), encoding="utf-8")
    p2.write_text(doc_pmjay.model_dump_json(indent=2), encoding="utf-8")

    indexer.index_processed_file(p1)
    indexer.index_processed_file(p2)

    searcher = SchemeSearcher(
        vector_store=store,
        embedder=embedder,
        collection_name="test_search",
    )

    # 1. Unfiltered query matching exact chunk text
    results = searcher.search(doc_kisan.chunks[0].text, top_k=2)
    assert len(results) > 0
    top = results[0]
    assert top.scheme_id == "central_pm_kisan"
    assert top.page_number == 1
    assert top.official_source_url == "https://example.gov.in/central_pm_kisan.pdf"
    assert top.document_readiness == "verified_digital_text"
    assert 0.0 <= top.distance <= 2.0
    assert 0.0 <= top.similarity_score <= 1.0

    # 2. Scheme-filtered query: requesting central_pmjay must NOT
    # return central_pm_kisan chunks
    pmjay_results = searcher.search(
        "financial benefits",
        top_k=5,
        scheme_id="central_pmjay",
    )
    assert len(pmjay_results) > 0
    assert all(r.scheme_id == "central_pmjay" for r in pmjay_results)

    # 3. Insufficient evidence / max_distance cutoff
    strict_results = searcher.search(
        "arbitrary query",
        top_k=5,
        max_distance=0.0001,  # extremely strict distance cutoff
    )
    assert strict_results == []
