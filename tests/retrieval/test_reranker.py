"""Deterministic tests for Phase 2E: Passage reranking and answer-focused selection.

Test coverage:
1. detect_question_intent(): English and Kannada intent classification
2. score_passage(): deterministic scoring with intent boosts and admin penalties
3. rerank_passages(): before/after PM-KISAN ranking regression test
4. Provenance preservation: distance and similarity_score untouched
5. Safe fallback: neutral scoring for general/ambiguous queries
"""

from __future__ import annotations

import pytest
from src.retrieval.reranker import (
    QuestionIntent,
    detect_question_intent,
    rerank_passages,
    score_passage,
)
from src.retrieval.schemas import SearchResult


def _make_result(
    chunk_id: str,
    text: str,
    distance: float,
    scheme_id: str = "central_pm_kisan",
) -> SearchResult:
    """Helper to construct deterministic SearchResult instances."""
    similarity = round(1.0 - min(distance, 1.0), 4)
    return SearchResult(
        chunk_id=chunk_id,
        scheme_id=scheme_id,
        source_document="sample_doc.pdf",
        official_source_url="https://example.gov.in/sample_doc.pdf",
        page_number=1,
        chunk_index=0,
        document_readiness="verified_digital_text",
        text=text,
        distance=distance,
        similarity_score=similarity,
    )


# ---------------------------------------------------------------------------
# 1. Intent Detection Tests
# ---------------------------------------------------------------------------


def test_detect_intent_pm_kisan_what_does_it_provide() -> None:
    intent = detect_question_intent("What does PM-KISAN provide?")
    assert intent == QuestionIntent.BENEFITS_PROVISION


def test_detect_intent_benefits_of_scheme() -> None:
    intent = detect_question_intent("What are the benefits of Ayushman Bharat?")
    assert intent == QuestionIntent.BENEFITS_PROVISION


def test_detect_intent_financial_assistance() -> None:
    intent = detect_question_intent("financial assistance for rural farmers")
    assert intent == QuestionIntent.BENEFITS_PROVISION


def test_detect_intent_how_much_money() -> None:
    intent = detect_question_intent("How much money do farmers get under PM-KISAN?")
    assert intent == QuestionIntent.BENEFITS_PROVISION


def test_detect_intent_interest_rate() -> None:
    intent = detect_question_intent("What is the interest rate for Sukanya Samriddhi?")
    assert intent == QuestionIntent.BENEFITS_PROVISION


def test_detect_intent_kannada_farmer_financial_aid() -> None:
    # "ರೈತರಿಗೆ ಆರ್ಥಿಕ ನೆರವು ನೀಡುವ ಯೋಜನೆ ಯಾವುದು?"
    intent = detect_question_intent("ರೈತರಿಗೆ ಆರ್ಥಿಕ ನೆರವು ನೀಡುವ ಯೋಜನೆ ಯಾವುದು?")
    assert intent == QuestionIntent.BENEFITS_PROVISION


def test_detect_intent_kannada_what_does_it_provide() -> None:
    # "ಯೋಜನೆ ಏನು ನೀಡುತ್ತದೆ?"
    intent = detect_question_intent("ಈ ಯೋಜನೆ ಏನು ನೀಡುತ್ತದೆ?")
    assert intent == QuestionIntent.BENEFITS_PROVISION


def test_detect_intent_who_is_eligible() -> None:
    intent = detect_question_intent("Who is eligible for PM Vishwakarma scheme?")
    assert intent == QuestionIntent.ELIGIBILITY_CRITERIA


def test_detect_intent_eligibility_criteria() -> None:
    intent = detect_question_intent("PM-JAY eligibility criteria for rural families")
    assert intent == QuestionIntent.ELIGIBILITY_CRITERIA


def test_detect_intent_kannada_who_is_eligible() -> None:
    # "ಯಾರು ಅರ್ಹರು"
    intent = detect_question_intent("ಈ ಯೋಜನೆಗೆ ಯಾರು ಅರ್ಹರು?")
    assert intent == QuestionIntent.ELIGIBILITY_CRITERIA


def test_detect_intent_how_to_apply() -> None:
    intent = detect_question_intent("How to apply for PM Vishwakarma online?")
    assert intent == QuestionIntent.APPLICATION_PROCESS


def test_detect_intent_documents_required() -> None:
    intent = detect_question_intent("documents required for Sukanya Samriddhi account")
    assert intent == QuestionIntent.APPLICATION_PROCESS


def test_detect_intent_kannada_how_to_apply() -> None:
    # "ಅರ್ಜಿ ಸಲ್ಲಿಸುವುದು ಹೇಗೆ"
    intent = detect_question_intent("ಪಿಎಂ ಕಿಸಾನ್ ಯೋಜನೆಗೆ ಅರ್ಜಿ ಸಲ್ಲಿಸುವುದು ಹೇಗೆ?")
    assert intent == QuestionIntent.APPLICATION_PROCESS


def test_detect_intent_empty_query() -> None:
    assert detect_question_intent("") == QuestionIntent.GENERAL
    assert detect_question_intent("   ") == QuestionIntent.GENERAL


def test_detect_intent_generic_query() -> None:
    assert detect_question_intent("government guidelines") == QuestionIntent.GENERAL


# ---------------------------------------------------------------------------
# 2. Passage Scoring Tests
# ---------------------------------------------------------------------------


def test_score_passage_benefits_boost() -> None:
    """Passage containing 'Objective and Benefits' gets intent boost."""
    result = _make_result(
        chunk_id="c_benefits",
        text=(
            "2. Objective and Benefits. The scheme aims to supplement "
            "financial needs of farmers."
        ),
        distance=0.5159,
    )
    score = score_passage(QuestionIntent.BENEFITS_PROVISION, result)
    # Base similarity is ~0.4841. With boost +0.22, score should be >= 0.70
    assert score > result.similarity_score
    assert score >= 0.70


def test_score_passage_admin_penalty() -> None:
    """Passage with administrative land transfer edge cases receives penalty."""
    result = _make_result(
        chunk_id="c_admin",
        text=(
            "In case of transfer of cultivable land for reasons other than "
            "death after 01.02.2019..."
        ),
        distance=0.5092,
    )
    score = score_passage(QuestionIntent.BENEFITS_PROVISION, result)
    # Base similarity is ~0.4908. With penalty -0.18, score drops
    assert score < result.similarity_score
    assert score <= 0.35


def test_score_passage_general_intent_unchanged() -> None:
    """Under GENERAL intent, score equals original base similarity."""
    result = _make_result(
        chunk_id="c_gen",
        text="Some general text about agriculture in India.",
        distance=0.40,
    )
    score = score_passage(QuestionIntent.GENERAL, result)
    assert score == pytest.approx(result.similarity_score, abs=1e-4)


# ---------------------------------------------------------------------------
# 3. PM-KISAN Before / After Ranking Regression Test
# ---------------------------------------------------------------------------


def test_pm_kisan_reranking_promotes_benefits_ahead_of_land_transfer() -> None:
    """Critical regression test:

    Before reranking:
      Rank 1: Land transfer edge case (p5_c23, dist=0.5092, sim=0.4908)
      Rank 2: Objective and Benefits (p2_c1, dist=0.5159, sim=0.4841)
      Rank 3: Nagaland administrative procedure (p5_c28, dist=0.5318, sim=0.4682)

    After reranking:
      Rank 1: Objective and Benefits (p2_c1, boosted!)
      Rank 2+: Land transfer & Nagaland (penalized for being procedural edge cases)
    """
    land_transfer = _make_result(
        chunk_id="central_pm_kisan_p5_c23",
        text=(
            "In case of transfer of cultivable land for reasons other than death "
            "after 01.02.2019, the officials have to reassess eligibility... "
            "Transferees are not entitled for any benefits under PM-KISAN."
        ),
        distance=0.5092,
    )

    benefits_passage = _make_result(
        chunk_id="central_pm_kisan_p2_c1",
        text=(
            "PRADHAN MANTRI KISAN SAMMAN NIDHI (PM-KISAN) SCHEME\n"
            "OPERATIONAL GUIDELINES\n"
            "1. Scheme: With a view to provide income support to all landholding "
            "farmers...\n"
            "2. Objective and Benefits: The scheme aims to supplement the financial "
            "needs of all landholding farmers' families in procuring various inputs."
        ),
        distance=0.5159,
    )

    nagaland_procedure = _make_result(
        chunk_id="central_pm_kisan_p5_c28",
        text=(
            "beneficiary under PM-Kisan Scheme in Nagaland, the following procedure "
            "was approved by the Committee: In case of community owned cultivable land "
            "in the state of Nagaland which is under permanent cultivation, "
            "certificate issued by village council/authority/village chieftan..."
        ),
        distance=0.5318,
    )

    # Initial order (pure cosine distance): land_transfer is first!
    raw_results = [land_transfer, benefits_passage, nagaland_procedure]
    assert raw_results[0].chunk_id == "central_pm_kisan_p5_c23"
    assert raw_results[1].chunk_id == "central_pm_kisan_p2_c1"

    # Execute deterministic reranking
    reranked = rerank_passages("What does PM-KISAN provide?", raw_results)

    # After reranking: benefits_passage MUST be rank 1
    assert reranked[0].chunk_id == "central_pm_kisan_p2_c1"
    assert reranked[0].rerank_score is not None
    assert reranked[0].rerank_score > reranked[1].rerank_score  # type: ignore[operator]

    # Verify original distance and similarity_score remain uncorrupted
    assert reranked[0].distance == 0.5159
    assert reranked[0].similarity_score == pytest.approx(0.4841, abs=1e-4)


def test_rerank_passages_preserves_provenance() -> None:
    """Reranking must not lose or alter chunk metadata."""
    res = _make_result("chunk_1", "Objective and Benefits of scheme", 0.35)
    reranked = rerank_passages("benefits of the scheme", [res])

    assert len(reranked) == 1
    item = reranked[0]
    assert item.chunk_id == "chunk_1"
    assert item.source_document == "sample_doc.pdf"
    assert item.official_source_url == "https://example.gov.in/sample_doc.pdf"
    assert item.page_number == 1
    assert item.distance == 0.35
    assert item.rerank_score is not None


def test_rerank_passages_empty_list() -> None:
    assert rerank_passages("any query", []) == []


def test_kannada_farmer_query_boosts_benefits_passage() -> None:
    """Kannada farmer query promotes income support passage."""
    res1 = _make_result(
        chunk_id="chunk_income",
        text=(
            "The scheme aims to supplement financial needs. Under the Scheme an "
            "amount of Rs.6000/- per year is released."
        ),
        distance=0.30,
    )
    res2 = _make_result(
        chunk_id="chunk_admin",
        text="Creation of login ID for State-admin and District-admin portal.",
        distance=0.28,  # slightly closer in vector distance
    )
    reranked = rerank_passages("ರೈತರಿಗೆ ಆರ್ಥಿಕ ನೆರವು ನೀಡುವ ಯೋಜನೆ ಯಾವುದು?", [res2, res1])
    # Even though res2 had closer distance (0.28 vs 0.30), res1 is boosted
    assert reranked[0].chunk_id == "chunk_income"
