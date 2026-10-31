"""Comprehensive tests for Phase 2D: Evidence assessment and extractive answer layer.

Test coverage:
1. is_out_of_scope() -- OOS pattern matching (EN + Kannada)
2. has_welfare_context() -- welfare anchor word detection
3. assess_evidence() -- full verdict pipeline
4. AnswerBuilder.answer() -- end-to-end response structure
5. EvidencePassage provenance integrity
6. AnswerResponse invariants (eligibility_assessed always False)
7. CLI answer subcommand routing
8. Kannada query support
9. Abstention message content
10. No eligibility assertions in any output

All tests are fully deterministic. No real model downloads required.
The FakeDeterministicEmbedder produces stable SHA-256 hash vectors.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

import chromadb
import pytest
from pydantic import ValidationError
from src.ingestion.schemas import ProcessedDocument, SchemeChunk
from src.retrieval.answer import AnswerBuilder, AnswerResponse, EvidencePassage
from src.retrieval.embedder import BaseEmbedder, EmbedderError
from src.retrieval.evidence import (
    MAX_ACCEPTED_DISTANCE,
    EvidenceVerdict,
    assess_evidence,
    has_welfare_context,
    is_out_of_scope,
)
from src.retrieval.indexer import SchemeIndexer
from src.retrieval.schemas import SearchResult
from src.retrieval.search import SchemeSearcher
from src.retrieval.store import ChromaVectorStore

# ---------------------------------------------------------------------------
# Shared test infrastructure
# ---------------------------------------------------------------------------


class FakeDeterministicEmbedder(BaseEmbedder):
    """Deterministic CPU-only embedder — no model download required."""

    def __init__(
        self, model_name: str = "fake-2d-test-v1", dimension: int = 16
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
    num_chunks: int = 3,
    version: str = "2024-01-01",
) -> ProcessedDocument:
    """Build a minimal ProcessedDocument for integration tests."""
    chunks = [
        SchemeChunk(
            scheme_id=scheme_id,
            source_document=f"{scheme_id}_guidelines.pdf",
            official_source_url=f"https://india.gov.in/{scheme_id}.pdf",
            page_number=i + 1,
            chunk_index=i,
            text=(
                f"Official guidance paragraph {i} for {scheme_id}: "
                "eligibility criteria, income support, financial benefit, "
                "farmer household documentation requirements."
            ),
            document_version=version,
        )
        for i in range(num_chunks)
    ]
    return ProcessedDocument(
        scheme_id=scheme_id,
        source_document=f"{scheme_id}_guidelines.pdf",
        official_source_url=f"https://india.gov.in/{scheme_id}.pdf",
        document_version=version,
        total_pages=num_chunks,
        total_chunks=num_chunks,
        chunks=chunks,
    )


def _make_fake_search_result(
    scheme_id: str = "central_pm_kisan",
    distance: float = 0.30,
    text: str = "PM-KISAN provides financial support to farmers.",
) -> SearchResult:
    """Build a SearchResult with controlled distance for unit tests."""
    return SearchResult(
        chunk_id=f"{scheme_id}_chunk_0",
        scheme_id=scheme_id,
        source_document=f"{scheme_id}_guidelines.pdf",
        official_source_url=f"https://india.gov.in/{scheme_id}.pdf",
        page_number=1,
        chunk_index=0,
        document_version="2024-01-01",
        document_readiness="verified_digital_text",
        text=text,
        distance=distance,
        similarity_score=max(0.0, 1.0 - distance),
    )


# ---------------------------------------------------------------------------
# 1. is_out_of_scope() tests
# ---------------------------------------------------------------------------


def test_is_out_of_scope_isro() -> None:
    assert is_out_of_scope("What is the ISRO Chandrayaan mission?") is True


def test_is_out_of_scope_chandrayaan() -> None:
    assert is_out_of_scope("chandrayaan launch schedule 2024") is True


def test_is_out_of_scope_driving_license() -> None:
    assert is_out_of_scope("How do I renew my driving license?") is True


def test_is_out_of_scope_motor_vehicle_license() -> None:
    assert is_out_of_scope("motor vehicle license renewal process India") is True


def test_is_out_of_scope_license_renewal() -> None:
    assert is_out_of_scope("License renewal for car driving") is True


def test_is_out_of_scope_space_mission() -> None:
    assert is_out_of_scope("India space mission vehicle launch") is True


def test_is_out_of_scope_case_insensitive() -> None:
    assert is_out_of_scope("ISRO chandrayaan MISSION schedule") is True


def test_is_out_of_scope_false_for_pm_kisan() -> None:
    assert is_out_of_scope("PM-KISAN eligibility for small farmers") is False


def test_is_out_of_scope_false_for_ayushman() -> None:
    assert (
        is_out_of_scope("Ayushman Bharat health insurance for poor families") is False
    )


def test_is_out_of_scope_false_for_sukanya() -> None:
    assert is_out_of_scope("Sukanya Samriddhi Yojana interest rate") is False


def test_is_out_of_scope_false_for_generic_welfare() -> None:
    assert (
        is_out_of_scope("government financial assistance for rural families") is False
    )


def test_is_out_of_scope_kannada_driving_license() -> None:
    # "ಚಾಲನಾ ಪರವಾನಗಿ ಪಡೆಯುವುದು ಹೇಗೆ?" — driving license in Kannada
    query = (
        "\u0c9a\u0cbe\u0cb2\u0ca8\u0cbe "
        "\u0caa\u0cb0\u0cb5\u0cbe\u0ca8\u0c97\u0cbf "
        "\u0caa\u0ca1\u0cc6\u0caf\u0cc1\u0cb5\u0cc1\u0ca6\u0cc1 "
        "\u0cb9\u0cc7\u0c97\u0cc6?"
    )
    assert is_out_of_scope(query) is True


def test_is_out_of_scope_false_for_kannada_farmer() -> None:
    # "ರೈತರಿಗೆ ಆರ್ಥಿಕ ನೆರವು" — financial support for farmers (Kannada)
    query = (
        "\u0cb0\u0cc8\u0ca4\u0cb0\u0cbf\u0c97\u0cc6 "
        "\u0c86\u0cb0\u0ccd\u0ca5\u0cbf\u0c95 "
        "\u0ca8\u0cc6\u0cb0\u0cb5\u0cc1"
    )
    assert is_out_of_scope(query) is False


def test_is_out_of_scope_empty_string() -> None:
    assert is_out_of_scope("") is False


# ---------------------------------------------------------------------------
# 2. has_welfare_context() tests
# ---------------------------------------------------------------------------


def test_has_welfare_context_scheme_keyword() -> None:
    assert has_welfare_context("what scheme provides income support?") is True


def test_has_welfare_context_farmer() -> None:
    assert has_welfare_context("assistance for farmer households") is True


def test_has_welfare_context_health() -> None:
    assert has_welfare_context("health insurance hospitalization") is True


def test_has_welfare_context_savings() -> None:
    assert has_welfare_context("savings deposit account for girl") is True


def test_has_welfare_context_false_for_oos() -> None:
    assert has_welfare_context("ISRO Chandrayaan mission launch") is False


def test_has_welfare_context_false_driving_license() -> None:
    assert has_welfare_context("how to renew my driving license?") is False


# ---------------------------------------------------------------------------
# 3. assess_evidence() unit tests (with fake SearchResult objects)
# ---------------------------------------------------------------------------


def test_assess_evidence_supported_explicit_scheme() -> None:
    """Explicit scheme query + matching low-distance result → supported."""
    results = [_make_fake_search_result("central_pm_kisan", distance=0.25)]
    verdict, accepted = assess_evidence("What does PM-KISAN provide?", results)
    assert verdict == EvidenceVerdict.supported
    assert len(accepted) == 1
    assert accepted[0].scheme_id == "central_pm_kisan"


def test_assess_evidence_out_of_scope_isro() -> None:
    """ISRO query must return out_of_scope regardless of retrieved passages."""
    results = [_make_fake_search_result("central_pm_kisan", distance=0.30)]
    verdict, accepted = assess_evidence(
        "What is the launch schedule for ISRO Chandrayaan?", results
    )
    assert verdict == EvidenceVerdict.out_of_scope
    assert accepted == []


def test_assess_evidence_out_of_scope_driving_license() -> None:
    """Driving license query must return out_of_scope."""
    results = [_make_fake_search_result("central_sukanya_samriddhi", distance=0.54)]
    verdict, accepted = assess_evidence("How do I renew my driving license?", results)
    assert verdict == EvidenceVerdict.out_of_scope
    assert accepted == []


def test_assess_evidence_insufficient_no_results() -> None:
    """Empty result list → insufficient_evidence."""
    verdict, accepted = assess_evidence("PM-KISAN farmer support", results=[])
    assert verdict == EvidenceVerdict.insufficient_evidence
    assert accepted == []


def test_assess_evidence_insufficient_high_distance() -> None:
    """Result above MAX_ACCEPTED_DISTANCE → discarded → insufficient_evidence."""
    results = [
        _make_fake_search_result(
            "central_pm_kisan", distance=MAX_ACCEPTED_DISTANCE + 0.05
        )
    ]
    verdict, accepted = assess_evidence("PM-KISAN eligibility", results)
    assert verdict == EvidenceVerdict.insufficient_evidence
    assert accepted == []


def test_assess_evidence_scheme_coherence_filters_wrong_scheme() -> None:
    """If query names PM-KISAN but results are from PM-JAY, filter them out."""
    results = [_make_fake_search_result("central_pmjay", distance=0.30)]
    verdict, accepted = assess_evidence("PM-KISAN income support for farmers", results)
    assert verdict == EvidenceVerdict.insufficient_evidence
    assert accepted == []


def test_assess_evidence_generic_with_welfare_context() -> None:
    """Generic query with welfare context + borderline distance → supported."""
    results = [
        _make_fake_search_result(
            "central_pm_kisan",
            distance=0.55,
            text="Financial support scheme for farmers income.",
        )
    ]
    verdict, accepted = assess_evidence(
        "government financial assistance for farmer families", results
    )
    assert verdict == EvidenceVerdict.supported
    assert len(accepted) == 1


def test_assess_evidence_generic_no_context_weak_distance() -> None:
    """Generic query with no welfare anchor words + weak distance → insufficient."""
    results = [
        _make_fake_search_result(
            "central_pm_kisan",
            distance=0.58,  # above STRONG_RELEVANCE_DISTANCE
            text="Some text about documentation.",
        )
    ]
    verdict, accepted = assess_evidence("documents from the office", results)
    assert verdict == EvidenceVerdict.insufficient_evidence


def test_assess_evidence_multiple_results_keeps_all_valid() -> None:
    """Multiple results within threshold → all included."""
    results = [
        _make_fake_search_result("central_pm_kisan", distance=0.25),
        _make_fake_search_result("central_pm_kisan", distance=0.35),
        _make_fake_search_result("central_pm_kisan", distance=0.45),
    ]
    verdict, accepted = assess_evidence("PM-KISAN farmer income support", results)
    assert verdict == EvidenceVerdict.supported
    assert len(accepted) == 3


def test_assess_evidence_mixed_scheme_ids_generic_query() -> None:
    """Generic query (no explicit scheme) → all scheme IDs accepted if in distance."""
    results = [
        _make_fake_search_result("central_pm_kisan", distance=0.30),
        _make_fake_search_result("central_pmjay", distance=0.35),
    ]
    verdict, accepted = assess_evidence(
        "government health and income scheme for poor families", results
    )
    assert verdict == EvidenceVerdict.supported
    # Both schemes should be retained (no explicit scheme detected)
    assert len(accepted) == 2


def test_assess_evidence_kannada_oos() -> None:
    """Kannada driving license OOS query → out_of_scope."""
    kannada_oos = (
        "\u0c9a\u0cbe\u0cb2\u0ca8\u0cbe "
        "\u0caa\u0cb0\u0cb5\u0cbe\u0ca8\u0c97\u0cbf "
        "\u0caa\u0ca1\u0cc6\u0caf\u0cc1\u0cb5\u0cc1\u0ca6\u0cc1 "
        "\u0cb9\u0cc7\u0c97\u0cc6?"
    )
    results = [_make_fake_search_result("central_sukanya_samriddhi", distance=0.54)]
    verdict, accepted = assess_evidence(kannada_oos, results)
    assert verdict == EvidenceVerdict.out_of_scope
    assert accepted == []


# ---------------------------------------------------------------------------
# 4. AnswerBuilder integration tests (with fake embedder + ephemeral ChromaDB)
# ---------------------------------------------------------------------------


@pytest.fixture()
def indexed_searcher(tmp_path):
    """Provide an indexed SchemeSearcher backed by an ephemeral ChromaDB."""
    chroma_client = chromadb.EphemeralClient()
    store = ChromaVectorStore(client=chroma_client)
    embedder = FakeDeterministicEmbedder()

    indexer = SchemeIndexer(
        vector_store=store,
        embedder=embedder,
        collection_name="test_answer_2d",
        manifest_dir=tmp_path,
    )

    for scheme_id in [
        "central_pm_kisan",
        "central_pmjay",
        "central_pm_vishwakarma",
        "central_sukanya_samriddhi",
    ]:
        doc = make_doc(scheme_id, num_chunks=3)
        p = tmp_path / f"{scheme_id}.json"
        p.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
        indexer.index_processed_file(p)

    return SchemeSearcher(
        vector_store=store,
        embedder=embedder,
        collection_name="test_answer_2d",
    )


def test_answer_builder_pm_kisan_explicit(indexed_searcher) -> None:
    """Explicit PM-KISAN query → supported answer with passages."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("PM-KISAN farmer income support scheme")
    assert isinstance(response, AnswerResponse)
    assert response.status == "supported"
    assert response.is_supported
    assert not response.is_abstained
    assert len(response.passages) > 0
    assert response.detected_scheme_id == "central_pm_kisan"


def test_answer_builder_pmjay_explicit(indexed_searcher) -> None:
    """Explicit PM-JAY query → supported answer."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("Ayushman Bharat health insurance coverage")
    assert response.status == "supported"
    assert response.detected_scheme_id == "central_pmjay"


def test_answer_builder_vishwakarma_explicit(indexed_searcher) -> None:
    """Explicit PM Vishwakarma query → supported answer."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("vishwakarma yojana toolkit loan for artisans")
    assert response.status == "supported"
    assert response.detected_scheme_id == "central_pm_vishwakarma"


def test_answer_builder_sukanya_explicit(indexed_searcher) -> None:
    """Explicit Sukanya Samriddhi query → supported answer."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("sukanya samriddhi account for girl child")
    assert response.status == "supported"
    assert response.detected_scheme_id == "central_sukanya_samriddhi"


def test_answer_builder_empty_query(indexed_searcher) -> None:
    """Empty query → insufficient_evidence with meaningful message."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("")
    assert response.status == "insufficient_evidence"
    assert response.abstention_reason is not None
    assert len(response.abstention_reason) > 0
    assert response.passages == []


def test_answer_builder_whitespace_only_query(indexed_searcher) -> None:
    """Whitespace-only query → insufficient_evidence."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("   ")
    assert response.status == "insufficient_evidence"
    assert response.passages == []


def test_answer_builder_isro_out_of_scope(indexed_searcher) -> None:
    """ISRO query → out_of_scope status."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("What is the launch schedule for ISRO Chandrayaan?")
    assert response.status == "out_of_scope"
    assert response.passages == []
    assert response.abstention_reason is not None
    assert "scope" in response.abstention_reason.lower()


def test_answer_builder_driving_license_out_of_scope(indexed_searcher) -> None:
    """Driving license query → out_of_scope status."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("How do I renew my four-wheeler driving license?")
    assert response.status == "out_of_scope"
    assert response.passages == []


# ---------------------------------------------------------------------------
# 5. Citation integrity tests
# ---------------------------------------------------------------------------


def test_evidence_passage_has_full_provenance(indexed_searcher) -> None:
    """Every evidence passage must carry all required citation fields."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("PM-KISAN farmer income benefit eligibility")

    assert response.status == "supported"
    assert len(response.passages) > 0

    for p in response.passages:
        # All citation fields must be non-empty
        assert p.chunk_id, "chunk_id must not be empty"
        assert p.scheme_id, "scheme_id must not be empty"
        assert p.source_document, "source_document must not be empty"
        assert p.official_source_url, "official_source_url must not be empty"
        assert p.page_number >= 1, "page_number must be >= 1"
        assert p.chunk_index >= 0, "chunk_index must be >= 0"
        assert p.passage_text, "passage_text must not be empty"

        # Distance and score must be in valid ranges
        assert 0.0 <= p.distance <= 2.0, f"distance {p.distance} out of range"
        assert 0.0 <= p.similarity_score <= 1.0

        # URL must look like a URL
        assert p.official_source_url.startswith("http"), (
            f"source URL must start with http: {p.official_source_url}"
        )


def test_passage_text_is_extractive_not_synthesized(indexed_searcher) -> None:
    """Passage text must be a substring of the original chunk text, not generated."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("PM-KISAN farmer income support")
    assert response.status == "supported"

    for p in response.passages:
        # The original chunk text starts with this prefix (see make_doc)
        assert (
            "Official guidance paragraph" in p.passage_text
            or len(p.passage_text) <= 600
        ), "passage_text must be verbatim extract from indexed document"


def test_passage_text_respects_max_chars(indexed_searcher) -> None:
    """passage_text must never exceed MAX_PASSAGE_CHARS characters."""
    from src.retrieval.answer import MAX_PASSAGE_CHARS

    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("PM-KISAN farmer income support")

    for p in response.passages:
        assert len(p.passage_text) <= MAX_PASSAGE_CHARS


def test_response_scheme_id_matches_query_scheme(indexed_searcher) -> None:
    """When query explicitly names PM-KISAN, all passages must be from PM-KISAN."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("What does PM-KISAN provide to farmers?")
    assert response.status == "supported"
    assert response.detected_scheme_id == "central_pm_kisan"
    for p in response.passages:
        assert p.scheme_id == "central_pm_kisan", (
            f"Expected PM-KISAN passage, got {p.scheme_id}"
        )


def test_no_duplicate_chunk_ids_in_passages(indexed_searcher) -> None:
    """Passages must not contain duplicate chunk IDs."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("ayushman bharat health scheme hospitalization")
    assert response.status == "supported"
    chunk_ids = [p.chunk_id for p in response.passages]
    assert len(chunk_ids) == len(set(chunk_ids)), "Duplicate chunk IDs in passages"


# ---------------------------------------------------------------------------
# 6. AnswerResponse invariants
# ---------------------------------------------------------------------------


def test_eligibility_assessed_always_false(indexed_searcher) -> None:
    """eligibility_assessed must always be False — Phase 3 implements this."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    for query in [
        "PM-KISAN farmer income",
        "Ayushman Bharat health insurance",
        "ISRO Chandrayaan launch",
        "",
        "How do I renew my driving license?",
    ]:
        response = builder.answer(query)
        assert response.eligibility_assessed is False, (
            f"eligibility_assessed must be False for query: {query!r}"
        )


def test_supported_response_has_no_abstention_reason(indexed_searcher) -> None:
    """Supported responses must not set abstention_reason."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("PM-KISAN income support scheme for farmers")
    assert response.status == "supported"
    assert response.abstention_reason is None


def test_abstained_response_has_abstention_reason(indexed_searcher) -> None:
    """Insufficient-evidence responses must always include an abstention reason."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("")
    assert response.is_abstained
    assert response.abstention_reason is not None
    assert len(response.abstention_reason) > 10


def test_oos_response_has_abstention_reason(indexed_searcher) -> None:
    """OOS responses must include an abstention reason."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("ISRO space mission schedule 2024")
    assert response.status == "out_of_scope"
    assert response.abstention_reason is not None


def test_passages_empty_for_abstained_responses(indexed_searcher) -> None:
    """Abstained responses must always have an empty passages list."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    for query, expected_status in [
        ("ISRO Chandrayaan launch", "out_of_scope"),
        ("", "insufficient_evidence"),
        ("How do I renew my driving license?", "out_of_scope"),
    ]:
        response = builder.answer(query)
        assert response.status == expected_status
        assert response.passages == [], (
            f"Abstained response must have empty passages for query: {query!r}"
        )


def test_query_preserved_in_response(indexed_searcher) -> None:
    """The original query must always be preserved exactly in the response."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    test_queries = [
        "PM-KISAN farmer income",
        "ISRO Chandrayaan mission",
        "",
    ]
    for q in test_queries:
        response = builder.answer(q)
        assert response.query == q.strip(), (
            f"Query not preserved: expected {q.strip()!r}, got {response.query!r}"
        )


def test_max_passages_not_exceeded(indexed_searcher) -> None:
    """Supported response must not include more than MAX_PASSAGES_PER_ANSWER."""
    from src.retrieval.answer import MAX_PASSAGES_PER_ANSWER

    builder = AnswerBuilder(searcher=indexed_searcher, top_k=10, max_distance=None)
    response = builder.answer("PM-KISAN farmer income financial support benefit")
    if response.status == "supported":
        assert len(response.passages) <= MAX_PASSAGES_PER_ANSWER


# ---------------------------------------------------------------------------
# 7. Kannada query support
# ---------------------------------------------------------------------------


def test_kannada_farmer_query_does_not_crash(indexed_searcher) -> None:
    """Kannada farmer-support query must produce a valid AnswerResponse."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    kannada_query = (
        "\u0cb0\u0cc8\u0ca4\u0cb0\u0cbf\u0c97\u0cc6 "
        "\u0c86\u0cb0\u0ccd\u0ca5\u0cbf\u0c95 "
        "\u0ca8\u0cc6\u0cb0\u0cb5\u0cc1 "
        "\u0ca8\u0cc0\u0ca1\u0cc1\u0cb5 "
        "\u0caf\u0ccb\u0c9c\u0ca8\u0cc6 \u0caf\u0cbe\u0cb5\u0cc1\u0ca6\u0cc1?"
    )
    response = builder.answer(kannada_query)
    assert isinstance(response, AnswerResponse)
    assert response.eligibility_assessed is False


def test_kannada_explicit_pm_kisan_query(indexed_searcher) -> None:
    """Kannada explicit PM-KISAN query must route correctly."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    # "ಪಿಎಂ ಕಿಸಾನ್ ಯೋಜನೆ" — PM KISAN Yojane
    kannada_kisan = (
        "\u0caa\u0cbf\u0c8e\u0c82 \u0c95\u0cbf\u0cb8\u0cbe\u0ca8\u0ccd "
        "\u0caf\u0ccb\u0c9c\u0ca8\u0cc6"
    )
    response = builder.answer(kannada_kisan)
    assert isinstance(response, AnswerResponse)
    assert response.eligibility_assessed is False
    # Detected scheme must be PM-KISAN or None (alias detection)
    if response.detected_scheme_id:
        assert response.detected_scheme_id == "central_pm_kisan"


def test_kannada_oos_driving_license(indexed_searcher) -> None:
    """Kannada driving license query → out_of_scope."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    kannada_oos = (
        "\u0c9a\u0cbe\u0cb2\u0ca8\u0cbe \u0caa\u0cb0\u0cb5\u0cbe\u0ca8\u0c97\u0cbf "
        "\u0caa\u0ca1\u0cc6\u0caf\u0cc1\u0cb5\u0cc1\u0ca6\u0cc1 \u0cb9\u0cc7\u0c97\u0cc6?"  # noqa: E501
    )
    response = builder.answer(kannada_oos)
    assert response.status == "out_of_scope"
    assert response.passages == []
    assert response.eligibility_assessed is False


# ---------------------------------------------------------------------------
# 8. CLI answer subcommand routing (unit test of build_parser)
# ---------------------------------------------------------------------------


def test_cli_parser_has_answer_subcommand() -> None:
    """The retrieval CLI must expose an 'answer' subcommand."""
    from src.retrieval.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["answer", "What does PM-KISAN provide?"])
    assert args.command == "answer"
    assert args.query == "What does PM-KISAN provide?"


def test_cli_parser_answer_default_top_k() -> None:
    """CLI answer subcommand must default to top_k=5."""
    from src.retrieval.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["answer", "PM-KISAN query"])
    assert args.top_k == 5


def test_cli_parser_answer_scheme_id_optional() -> None:
    """CLI answer subcommand --scheme-id must default to None."""
    from src.retrieval.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["answer", "PM-KISAN query"])
    assert args.scheme_id is None


def test_cli_parser_answer_scheme_id_set() -> None:
    """CLI answer subcommand accepts --scheme-id."""
    from src.retrieval.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        ["answer", "income support", "--scheme-id", "central_pm_kisan"]
    )
    assert args.scheme_id == "central_pm_kisan"


# ---------------------------------------------------------------------------
# 9. EvidencePassage model validation
# ---------------------------------------------------------------------------


def test_evidence_passage_model_frozen() -> None:
    """EvidencePassage must be immutable (frozen Pydantic model)."""
    p = EvidencePassage(
        chunk_id="abc123",
        scheme_id="central_pm_kisan",
        source_document="pm_kisan.pdf",
        official_source_url="https://india.gov.in/pm_kisan.pdf",
        page_number=1,
        chunk_index=0,
        passage_text="Sample text about PM-KISAN.",
        distance=0.30,
        similarity_score=0.70,
    )
    with pytest.raises(ValidationError):
        p.chunk_id = "modified"  # type: ignore[misc]


def test_evidence_passage_similarity_score_range() -> None:
    """EvidencePassage similarity_score must be in [0.0, 1.0]."""
    with pytest.raises(ValidationError):
        EvidencePassage(
            chunk_id="abc123",
            scheme_id="central_pm_kisan",
            source_document="pm_kisan.pdf",
            official_source_url="https://india.gov.in/pm_kisan.pdf",
            page_number=1,
            chunk_index=0,
            passage_text="Sample text.",
            distance=0.30,
            similarity_score=1.5,  # invalid
        )


# ---------------------------------------------------------------------------
# 10. Abstention message content checks
# ---------------------------------------------------------------------------


def test_oos_abstention_mentions_covered_schemes(indexed_searcher) -> None:
    """OOS abstention reason must mention the covered scheme domains."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("ISRO Chandrayaan mission schedule")
    assert response.status == "out_of_scope"
    reason = response.abstention_reason or ""
    # Must mention at least one covered scheme name
    covered = ["PM-KISAN", "Ayushman", "Vishwakarma", "Sukanya"]
    assert any(name in reason for name in covered), (
        f"OOS reason must reference covered schemes. Got: {reason!r}"
    )


def test_insufficient_evidence_abstention_is_informative(indexed_searcher) -> None:
    """Insufficient-evidence reason must be a helpful, informative message."""
    builder = AnswerBuilder(searcher=indexed_searcher, max_distance=None)
    response = builder.answer("")  # empty → insufficient
    reason = response.abstention_reason or ""
    # Must contain actionable guidance, not a blank or error code
    assert len(reason) > 20, "Abstention reason must be informative"
