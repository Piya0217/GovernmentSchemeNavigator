"""Regression tests for Phase 2C: QueryAnalyzer module.

Covers:
- Explicit scheme alias matching (English and Kannada)
- Generic / ambiguous queries that must NOT trigger forced filtering
- Kannada intent expansion (welfare root keywords -> English anchor terms)
- Multiple-scheme disambiguation (no forced filter when >1 scheme detected)
- has_kannada_script() utility
- Source attribution preservation via SchemeSearcher
- Out-of-scope handling via max_distance threshold
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

import chromadb
from src.ingestion.schemas import ProcessedDocument, SchemeChunk
from src.retrieval.embedder import BaseEmbedder, EmbedderError
from src.retrieval.indexer import SchemeIndexer
from src.retrieval.query_analyzer import (
    SCHEME_ALIASES,
    detect_explicit_scheme,
    expand_query_intent,
    has_kannada_script,
)
from src.retrieval.search import SchemeSearcher
from src.retrieval.store import ChromaVectorStore

# ---------------------------------------------------------------------------
# Shared Fake Embedder (no model downloads, deterministic)
# ---------------------------------------------------------------------------


class FakeDeterministicEmbedder(BaseEmbedder):
    """Deterministic CPU-only embedder using SHA-256 hash projections."""

    def __init__(self, model_name: str = "fake-test-v1", dimension: int = 16) -> None:
        self._model_name = model_name
        self._dimension = dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _hash_to_vector(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        raw = [float(b % 100) - 50.0 for b in h[: self._dimension]]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._hash_to_vector(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        if not query.strip():
            msg = "Query text is empty"
            raise EmbedderError(msg)
        return self._hash_to_vector(query.strip())


def make_doc(
    scheme_id: str = "central_pm_kisan",
    num_chunks: int = 2,
    version: str = "2023-01-01",
) -> ProcessedDocument:
    """Build a minimal valid ProcessedDocument for indexing tests."""
    chunks = [
        SchemeChunk(
            scheme_id=scheme_id,
            source_document=f"{scheme_id}_doc.pdf",
            official_source_url=f"https://india.gov.in/{scheme_id}.pdf",
            page_number=i + 1,
            chunk_index=i,
            text=(
                f"Substantive text block {i} for {scheme_id}: details about "
                "eligibility criteria, financial benefits, and documentation."
            ),
            document_version=version,
        )
        for i in range(num_chunks)
    ]
    return ProcessedDocument(
        scheme_id=scheme_id,
        source_document=f"{scheme_id}_doc.pdf",
        official_source_url=f"https://india.gov.in/{scheme_id}.pdf",
        document_version=version,
        total_pages=num_chunks,
        total_chunks=num_chunks,
        chunks=chunks,
    )


# ---------------------------------------------------------------------------
# 1. has_kannada_script()
# ---------------------------------------------------------------------------


def test_has_kannada_script_detects_kannada() -> None:
    assert has_kannada_script("ರೈತರಿಗೆ ಆರ್ಥಿಕ ನೆರವು") is True
    assert has_kannada_script("ಪಿಎಂ ಕಿಸಾನ್") is True


def test_has_kannada_script_ignores_latin() -> None:
    assert has_kannada_script("PM-KISAN scheme for farmers") is False
    assert has_kannada_script("Ayushman Bharat health insurance") is False


def test_has_kannada_script_empty_string() -> None:
    assert has_kannada_script("") is False


# ---------------------------------------------------------------------------
# 2. detect_explicit_scheme() -- English Aliases
# ---------------------------------------------------------------------------


def test_detect_explicit_scheme_english_pm_kisan() -> None:
    for query in [
        "Tell me about PM-KISAN benefits",
        "PM Kisan Samman Nidhi eligibility",
        "kisan samman nidhi scheme",
        "pmkisan direct income support",
        "pradhan mantri kisan samman nidhi guidelines",
    ]:
        result = detect_explicit_scheme(query)
        assert result == "central_pm_kisan", f"Failed on: {query!r}"


def test_detect_explicit_scheme_english_pmjay() -> None:
    for query in [
        "How to enroll in Ayushman Bharat scheme?",
        "pm-jay hospital empanelment",
        "PMJAY golden card how to get",
        "Jan Arogya Yojana eligibility",
    ]:
        result = detect_explicit_scheme(query)
        assert result == "central_pmjay", f"Failed on: {query!r}"


def test_detect_explicit_scheme_english_vishwakarma() -> None:
    for query in [
        "PM Vishwakarma scheme for artisans",
        "vishwakarma yojana toolkit loan",
        "pradhan mantri vishwakarma eligibility",
    ]:
        result = detect_explicit_scheme(query)
        assert result == "central_pm_vishwakarma", f"Failed on: {query!r}"


def test_detect_explicit_scheme_english_sukanya() -> None:
    for query in [
        "Open a Sukanya Samriddhi account for my daughter",
        "sukanya scheme interest rate",
        "SSY account maturity",
        "sukanya samriddhi yojana age limit",
    ]:
        result = detect_explicit_scheme(query)
        assert result == "central_sukanya_samriddhi", f"Failed on: {query!r}"


# ---------------------------------------------------------------------------
# 3. detect_explicit_scheme() -- Kannada Aliases
# ---------------------------------------------------------------------------


def test_detect_explicit_scheme_kannada_pm_kisan() -> None:
    result = detect_explicit_scheme(
        "\u0caa\u0cbf\u0c8e\u0c82 \u0c95\u0cbf\u0cb8\u0cbe\u0ca8\u0ccd "
        "\u0caf\u0ccb\u0c9c\u0ca8\u0cc6\u0caf\u0ca1\u0cbf "
        "\u0cb0\u0cc8\u0ca4\u0cb0\u0cbf\u0c97\u0cc6 \u0c8e\u0cb7\u0ccd\u0c9f\u0cc1 "
        "\u0c86\u0cb0\u0ccd\u0ca5\u0cbf\u0c95 \u0ca8\u0cc6\u0cb0\u0cb5\u0cc1 "
        "\u0cb8\u0cbf\u0c97\u0cc1\u0ca4\u0ccd\u0ca4\u0ca6\u0cc6?"
    )
    assert result == "central_pm_kisan"


def test_detect_explicit_scheme_kannada_pmjay() -> None:
    result = detect_explicit_scheme(
        "\u0c86\u0caf\u0cc1\u0cb7\u0ccd\u0cae\u0cbe\u0ca8\u0ccd "
        "\u0cad\u0cbe\u0cb0\u0ca4\u0ccd "
        "\u0caf\u0ccb\u0c9c\u0ca8\u0cc6\u0caf\u0ca1\u0cbf "
        "\u0c9a\u0cbf\u0c95\u0cbf\u0ca4\u0ccd\u0cb8\u0cbe "
        "\u0cb8\u0ccc\u0cb2\u0cad\u0ccd\u0caf "
        "\u0cb9\u0cc7\u0c97\u0cc6 \u0caa\u0ca1\u0cc6\u0caf\u0cc1\u0cb5\u0cc1\u0ca6\u0cc1?"  # noqa: E501
    )
    assert result == "central_pmjay"


def test_detect_explicit_scheme_kannada_sukanya() -> None:
    result = detect_explicit_scheme(
        "\u0cb8\u0cc1\u0c95\u0ca8\u0ccd\u0caf\u0cbe "
        "\u0cb8\u0cae\u0cc3\u0ca6\u0ccd\u0ca7\u0cbf "
        "\u0caf\u0ccb\u0c9c\u0ca8\u0cc6\u0caf\u0cb2\u0ccd\u0cb2\u0cbf "
        "\u0cb9\u0cc6\u0ca3\u0ccd\u0ca3\u0cc1 \u0cae\u0c95\u0ccd\u0c95\u0cb3\u0cbf\u0c97\u0cc6 "  # noqa: E501
        "\u0c96\u0cbe\u0ca4\u0cc6 \u0ca4\u0cc6\u0cb0\u0cc6\u0caf\u0cb2\u0cc1 "
        "\u0cb5\u0caf\u0ccb\u0cae\u0cbf\u0ca4\u0cbf \u0c8f\u0ca8\u0cc1?"
    )
    assert result == "central_sukanya_samriddhi"


# ---------------------------------------------------------------------------
# 4. detect_explicit_scheme() -- Generic / Ambiguous = None
# ---------------------------------------------------------------------------


def test_detect_explicit_scheme_generic_query_returns_none() -> None:
    """Generic queries must not force any scheme filter."""
    generic_queries = [
        "Government financial assistance for farmers in India",
        "health insurance for poor families",
        "savings scheme for girl child education",
        "artisan support scheme",
        "Loan scheme for small-scale craftsmen in India",
    ]
    for q in generic_queries:
        result = detect_explicit_scheme(q)
        assert result is None, (
            f"Expected None (generic query), got '{result}' for: {q!r}"
        )


def test_detect_explicit_scheme_multiple_schemes_returns_none() -> None:
    """When >1 distinct schemes are explicitly named, return None."""
    multi_scheme_query = "Compare PM-KISAN and Ayushman Bharat eligibility"
    result = detect_explicit_scheme(multi_scheme_query)
    assert result is None, f"Should return None for multi-scheme query, got '{result}'"


def test_detect_explicit_scheme_out_of_scope_returns_none() -> None:
    """Out-of-scope queries with no scheme names must return None."""
    oos_queries = [
        "How do I renew my driving license?",
        "ISRO Chandrayaan launch schedule",
    ]
    for q in oos_queries:
        result = detect_explicit_scheme(q)
        assert result is None, f"OOS query should return None, got '{result}' for {q!r}"


# ---------------------------------------------------------------------------
# 5. expand_query_intent() -- Kannada Expansion
# ---------------------------------------------------------------------------


def test_expand_query_intent_expands_farmer_keyword() -> None:
    # "ರೈತರಿಗೆ ಆರ್ಥಿಕ ನೆರವು ನೀಡುವ ಯೋಜನೆ ಯಾವುದು?"
    query = (
        "\u0cb0\u0cc8\u0ca4\u0cb0\u0cbf\u0c97\u0cc6 "
        "\u0c86\u0cb0\u0ccd\u0ca5\u0cbf\u0c95 "
        "\u0ca8\u0cc6\u0cb0\u0cb5\u0cc1 "
        "\u0ca8\u0cc0\u0ca1\u0cc1\u0cb5 "
        "\u0caf\u0ccb\u0c9c\u0ca8\u0cc6 \u0caf\u0cbe\u0cb5\u0cc1\u0ca6\u0cc1?"
    )
    expanded = expand_query_intent(query)
    assert query in expanded
    assert "farmers" in expanded.lower() or "agricultural" in expanded.lower()


def test_expand_query_intent_expands_health_keyword() -> None:
    # "ಬಡ ಕುಟುಂಬಗಳಿಗೆ ಆರೋಗ್ಯ ವಿಮೆ ..."
    query = (
        "\u0cac\u0ca1 \u0c95\u0cc1\u0c9f\u0cc1\u0c82\u0cac\u0c97\u0cb3\u0cbf\u0c97\u0cc6 "  # noqa: E501
        "\u0c86\u0cb0\u0ccb\u0c97\u0ccd\u0caf \u0cb5\u0cbf\u0cae\u0cc6"
    )
    expanded = expand_query_intent(query)
    assert query in expanded
    assert "health" in expanded.lower() or "insurance" in expanded.lower()


def test_expand_query_intent_leaves_english_unchanged() -> None:
    """English queries must pass through expand_query_intent unchanged."""
    english_queries = [
        "PM-KISAN eligibility for small farmers",
        "Ayushman Bharat health coverage limit",
        "Sukanya Samriddhi interest rate 2024",
        "PM Vishwakarma artisan loan amount",
    ]
    for q in english_queries:
        result = expand_query_intent(q)
        assert result == q, f"English query must not be modified. Got: {result!r}"


def test_expand_query_intent_kannada_oos_unchanged() -> None:
    """Kannada OOS query with no known welfare keywords passes through unchanged."""
    # "ಚಾಲನಾ ಪರವಾನಗಿ ಪಡೆಯುವುದು ಹೇಗೆ?"
    query = (
        "\u0c9a\u0cbe\u0cb2\u0ca8\u0cbe \u0caa\u0cb0\u0cb5\u0cbe\u0ca8\u0c97\u0cbf "
        "\u0caa\u0ca1\u0cc6\u0caf\u0cc1\u0cb5\u0cc1\u0ca6\u0cc1 \u0cb9\u0cc7\u0c97\u0cc6?"  # noqa: E501
    )
    result = expand_query_intent(query)
    assert result == query


# ---------------------------------------------------------------------------
# 6. SCHEME_ALIASES Registry -- Structural Integrity
# ---------------------------------------------------------------------------


def test_scheme_aliases_covers_all_indexed_schemes() -> None:
    """All 4 indexed schemes must have alias entries."""
    required_ids = {
        "central_pm_kisan",
        "central_pmjay",
        "central_pm_vishwakarma",
        "central_sukanya_samriddhi",
    }
    assert required_ids.issubset(SCHEME_ALIASES.keys())


def test_scheme_aliases_all_lowercase_latin() -> None:
    """All Latin alias strings must be lowercase."""
    for scheme_id, aliases in SCHEME_ALIASES.items():
        for alias in aliases:
            if not has_kannada_script(alias):
                assert alias == alias.lower(), (
                    f"Alias '{alias}' for '{scheme_id}' must be lowercase"
                )


# ---------------------------------------------------------------------------
# 7. Source Attribution Preservation
# ---------------------------------------------------------------------------


def test_source_attribution_preserved_in_search_results(tmp_path) -> None:
    """Search results must carry full provenance: URL, page, chunk_id, doc version."""
    chroma_client = chromadb.EphemeralClient()
    store = ChromaVectorStore(client=chroma_client)
    embedder = FakeDeterministicEmbedder()

    indexer = SchemeIndexer(
        vector_store=store,
        embedder=embedder,
        collection_name="test_attribution",
        manifest_dir=tmp_path,
    )

    doc = make_doc("central_pm_kisan", num_chunks=2)
    p = tmp_path / "central_pm_kisan.json"
    p.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    indexer.index_processed_file(p)

    searcher = SchemeSearcher(
        vector_store=store,
        embedder=embedder,
        collection_name="test_attribution",
    )

    results = searcher.search(doc.chunks[0].text, top_k=1, max_distance=None)
    assert len(results) == 1

    r = results[0]
    assert r.scheme_id == "central_pm_kisan"
    assert r.official_source_url == "https://india.gov.in/central_pm_kisan.pdf"
    assert r.source_document == "central_pm_kisan_doc.pdf"
    assert isinstance(r.page_number, int) and r.page_number >= 1
    assert isinstance(r.chunk_index, int) and r.chunk_index >= 0
    assert r.document_version == "2023-01-01"
    assert r.chunk_id != ""
    assert 0.0 <= r.distance <= 2.0
    assert 0.0 <= r.similarity_score <= 1.0


# ---------------------------------------------------------------------------
# 8. Explicit Scheme Routing (Integration)
# ---------------------------------------------------------------------------


def test_scheme_aware_routing_restricts_to_detected_scheme(tmp_path) -> None:
    """When a query explicitly names a scheme, results come only from that scheme."""
    chroma_client = chromadb.EphemeralClient()
    store = ChromaVectorStore(client=chroma_client)
    embedder = FakeDeterministicEmbedder()

    indexer = SchemeIndexer(
        vector_store=store,
        embedder=embedder,
        collection_name="test_routing",
        manifest_dir=tmp_path,
    )

    for sid in ["central_pm_kisan", "central_pmjay"]:
        doc = make_doc(sid, num_chunks=2)
        p = tmp_path / f"{sid}.json"
        p.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
        indexer.index_processed_file(p)

    searcher = SchemeSearcher(
        vector_store=store,
        embedder=embedder,
        collection_name="test_routing",
    )

    results = searcher.search(
        "PM-KISAN eligibility farmers", top_k=3, max_distance=None
    )
    assert len(results) > 0
    for r in results:
        assert r.scheme_id == "central_pm_kisan", (
            f"Explicit PM-KISAN query returned wrong scheme: {r.scheme_id}"
        )


def test_generic_query_searches_all_schemes(tmp_path) -> None:
    """Generic queries (no explicit scheme) search across all indexed schemes."""
    chroma_client = chromadb.EphemeralClient()
    store = ChromaVectorStore(client=chroma_client)
    embedder = FakeDeterministicEmbedder()

    indexer = SchemeIndexer(
        vector_store=store,
        embedder=embedder,
        collection_name="test_generic_search",
        manifest_dir=tmp_path,
    )

    for sid in ["central_pm_kisan", "central_pmjay"]:
        doc = make_doc(sid, num_chunks=2)
        p = tmp_path / f"{sid}.json"
        p.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
        indexer.index_processed_file(p)

    searcher = SchemeSearcher(
        vector_store=store,
        embedder=embedder,
        collection_name="test_generic_search",
    )

    results = searcher.search("financial support scheme", top_k=4, max_distance=None)
    assert len(results) > 0


# ---------------------------------------------------------------------------
# 9. Insufficient Evidence / OOS Threshold
# ---------------------------------------------------------------------------


def test_out_of_scope_returns_empty_under_strict_threshold(tmp_path) -> None:
    """Extremely strict distance threshold returns no results for unrelated queries."""
    chroma_client = chromadb.EphemeralClient()
    store = ChromaVectorStore(client=chroma_client)
    embedder = FakeDeterministicEmbedder()

    indexer = SchemeIndexer(
        vector_store=store,
        embedder=embedder,
        collection_name="test_oos_threshold",
        manifest_dir=tmp_path,
    )

    doc = make_doc("central_pm_kisan", num_chunks=2)
    p = tmp_path / "central_pm_kisan.json"
    p.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    indexer.index_processed_file(p)

    searcher = SchemeSearcher(
        vector_store=store,
        embedder=embedder,
        collection_name="test_oos_threshold",
    )

    results = searcher.search(
        "driving license renewal process", top_k=5, max_distance=0.0001
    )
    assert results == []


def test_no_threshold_returns_results_even_for_oos(tmp_path) -> None:
    """With max_distance=None, Chroma always returns results (no filtering)."""
    chroma_client = chromadb.EphemeralClient()
    store = ChromaVectorStore(client=chroma_client)
    embedder = FakeDeterministicEmbedder()

    indexer = SchemeIndexer(
        vector_store=store,
        embedder=embedder,
        collection_name="test_oos_no_threshold",
        manifest_dir=tmp_path,
    )

    doc = make_doc("central_pm_kisan", num_chunks=2)
    p = tmp_path / "central_pm_kisan.json"
    p.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    indexer.index_processed_file(p)

    searcher = SchemeSearcher(
        vector_store=store,
        embedder=embedder,
        collection_name="test_oos_no_threshold",
    )

    results = searcher.search(
        "driving license renewal process", top_k=3, max_distance=None
    )
    assert len(results) > 0


# ---------------------------------------------------------------------------
# 10. Kannada Query End-to-End
# ---------------------------------------------------------------------------


def test_kannada_queries_do_not_crash(tmp_path) -> None:
    """Kannada queries must not raise exceptions when searched against an index."""
    chroma_client = chromadb.EphemeralClient()
    store = ChromaVectorStore(client=chroma_client)
    embedder = FakeDeterministicEmbedder()

    indexer = SchemeIndexer(
        vector_store=store,
        embedder=embedder,
        collection_name="test_kn_query",
        manifest_dir=tmp_path,
    )

    doc = make_doc("central_pm_kisan", num_chunks=2)
    p = tmp_path / "central_pm_kisan.json"
    p.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    indexer.index_processed_file(p)

    searcher = SchemeSearcher(
        vector_store=store,
        embedder=embedder,
        collection_name="test_kn_query",
    )

    kannada_queries = [
        # "ರೈತರಿಗೆ ಆರ್ಥಿಕ ನೆರವು ..."
        "\u0cb0\u0cc8\u0ca4\u0cb0\u0cbf\u0c97\u0cc6 \u0c86\u0cb0\u0ccd\u0ca5\u0cbf\u0c95 "  # noqa: E501
        "\u0ca8\u0cc6\u0cb0\u0cb5\u0cc1 \u0ca8\u0cc0\u0ca1\u0cc1\u0cb5 "
        "\u0caf\u0ccb\u0c9c\u0ca8\u0cc6 \u0caf\u0cbe\u0cb5\u0cc1\u0ca6\u0cc1?",
        # "ಚಾಲನಾ ಪರವಾನಗಿ ..."  (OOS)
        "\u0c9a\u0cbe\u0cb2\u0ca8\u0cbe \u0caa\u0cb0\u0cb5\u0cbe\u0ca8\u0c97\u0cbf "
        "\u0caa\u0ca1\u0cc6\u0caf\u0cc1\u0cb5\u0cc1\u0ca6\u0cc1 \u0cb9\u0cc7\u0c97\u0cc6?",  # noqa: E501
    ]
    for q in kannada_queries:
        result = searcher.search(q, top_k=3, max_distance=None)
        assert isinstance(result, list), f"Expected list for Kannada query: {q!r}"
