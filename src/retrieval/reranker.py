"""Conservative, deterministic passage reranker for answer-focused retrieval.

Safety & Integrity (AGENTS.md):
- This module NEVER makes eligibility decisions.
- All reranking is deterministic, rule-based, and inspectable.
- Raw cosine distance from ChromaDB is preserved untouched.
- No benefits or scheme rules are invented.
- Query intent matching supports both English and Kannada questions.
"""

from __future__ import annotations

import logging
import re
from enum import StrEnum

from src.retrieval.schemas import SearchResult

logger = logging.getLogger("scheme_navigator.retrieval.reranker")


class QuestionIntent(StrEnum):
    """Categorization of citizen information intent."""

    BENEFITS_PROVISION = "benefits_provision"
    ELIGIBILITY_CRITERIA = "eligibility_criteria"
    APPLICATION_PROCESS = "application_process"
    GENERAL = "general"


# ---------------------------------------------------------------------------
# Intent Detection Patterns (English + Kannada)
# ---------------------------------------------------------------------------

_BENEFITS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(?:what\s+(?:does|do|is|are)\s+.*(?:provide|give|offer|benefit|grant)|"
        r"benefits?\s+of|financial\s+(?:assistance|aid|support)|income\s+support|"
        r"how\s+much\s+(?:money|benefit|amount|fund)|objective|purpose|"
        r"what\s+do\s+i\s+get|rate\s+of\s+interest|interest\s+rate|loan\s+amount|"
        r"stipend|toolkit|subsidy)\b",
        re.IGNORECASE,
    ),
]

_BENEFITS_KANNADA_TERMS: list[str] = [
    "ಏನು ನೀಡುತ್ತದೆ",
    "ಪ್ರಯೋಜನ",
    "ಲಾಭ",
    "ನೆರವು",
    "ಆರ್ಥಿಕ ನೆರವು",
    "ಉದ್ದೇಶ",
    "ಎಷ್ಟು ಹಣ",
    "ಬಡ್ಡಿ",
]

_ELIGIBILITY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(?:who\s+(?:is|are|can)\s+(?:eligible|apply|qualify|join)|"
        r"eligibility\s+criteria|qualifications?|requirements?|age\s+limit|"
        r"exclusions?|who\s+cannot\s+apply|am\s+i\s+eligible)\b",
        re.IGNORECASE,
    ),
]

_ELIGIBILITY_KANNADA_TERMS: list[str] = [
    "ಯಾರು ಅರ್ಹರು",
    "ಅರ್ಹತೆ",
    "ಅರ್ಹರು",
    "ಯಾರಿಗೆ ಸಿಗುತ್ತದೆ",
    "ವಯಸ್ಸಿನ ಮಿತಿ",
]

_APPLICATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(?:how\s+(?:to|can\s+i|do\s+i)\s+(?:apply|register|enrol|enroll)|"
        r"where\s+to\s+apply|registration\s+process|application\s+form|"
        r"documents?\s+(?:required|needed|list)|portal\s+link)\b",
        re.IGNORECASE,
    ),
]

_APPLICATION_KANNADA_TERMS: list[str] = [
    "ಅರ್ಜಿ ಸಲ್ಲಿಸುವುದು ಹೇಗೆ",
    "ನೋಂದಣಿ ಮಾಡುವುದು ಹೇಗೆ",
    "ದಾಖಲೆಗಳು",
    "ಹೇಗೆ ಅರ್ಜಿ",
]


def detect_question_intent(query: str) -> QuestionIntent:
    """Detect information intent from a citizen's query.

    Args:
        query: User input query (English or regional language).

    Returns:
        QuestionIntent enum variant.
    """
    clean_q = query.strip()
    if not clean_q:
        return QuestionIntent.GENERAL

    # 1. Benefits / Provision intent
    for pattern in _BENEFITS_PATTERNS:
        if pattern.search(clean_q):
            return QuestionIntent.BENEFITS_PROVISION
    for term in _BENEFITS_KANNADA_TERMS:
        if term in clean_q:
            return QuestionIntent.BENEFITS_PROVISION

    # 2. Eligibility intent
    for pattern in _ELIGIBILITY_PATTERNS:
        if pattern.search(clean_q):
            return QuestionIntent.ELIGIBILITY_CRITERIA
    for term in _ELIGIBILITY_KANNADA_TERMS:
        if term in clean_q:
            return QuestionIntent.ELIGIBILITY_CRITERIA

    # 3. Application process intent
    for pattern in _APPLICATION_PATTERNS:
        if pattern.search(clean_q):
            return QuestionIntent.APPLICATION_PROCESS
    for term in _APPLICATION_KANNADA_TERMS:
        if term in clean_q:
            return QuestionIntent.APPLICATION_PROCESS

    return QuestionIntent.GENERAL


# ---------------------------------------------------------------------------
# Deterministic Passage Content Scoring
# ---------------------------------------------------------------------------

_BENEFITS_BOOST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?:objective\s+and\s+benefits?|with\s+a\s+view\s+to\s+provide|"
        r"income\s+support|supplement\s+the\s+financial\s+needs|"
        r"financial\s+assistance|modalities\s+for\s+transfer\s+of\s+benefit|"
        r"under\s+the\s+scheme\s+an\s+amount\s+of|health\s+cover\s+of\s+rs|"
        r"collateral[- ]free\s+enterprise\s+credit|toolkit\s+incentive\s+of|"
        r"financial\s+benefit\s+of\s+rs)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:rs\.?|₹)\s*\d+", re.IGNORECASE),
]

_ADMIN_PENALTY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?:transfer\s+of\s+cultivable\s+land\s+for\s+reasons\s+other\s+than\s+death|"
        r"in\s+the\s+state\s+of\s+nagaland|village\s+chieftan|village\s+council|"
        r"creation\s+of\s+login\s+id|state-admin\s+and\s+district-admin|"
        r"grievance\s+redressal\s+committee|monitoring\s+committee|"
        r"operational\s+guidelines\s+revised\s+as\s+on\s+29\.03\.2020\s+ministry)",
        re.IGNORECASE,
    ),
]

_ELIGIBILITY_BOOST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?:definition\s+of\s+farmer['’]?s\s+family|exclusions?|not\s+eligible|"
        r"eligible\s+beneficiar(?:y|ies)|deprivation\s+criteria|occupational\s+criteria|"
        r"traditional\s+artisans?|girl\s+child|age\s+limit|higher\s+economic\s+status)",
        re.IGNORECASE,
    ),
]

_APPLICATION_BOOST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?:how\s+to\s+apply|registration\s+process|common\s+service\s+centres?|"
        r"csc|aadhaar\s+linked|portal\s+registration|enrolment\s+process|"
        r"verification\s+process)",
        re.IGNORECASE,
    ),
]


def score_passage(
    intent: QuestionIntent,
    result: SearchResult,
) -> float:
    """Compute a deterministic reranking score in [0.0, 1.0] for a passage.

    The score combines:
    1. Base normalized similarity from vector search (`similarity_score`).
    2. Intent-aligned content boost (+0.20 to +0.25) when passage directly
       answers the detected question type.
    3. Procedural/administrative penalty (-0.15 to -0.20) for peripheral minutiae.

    The original `distance` and `similarity_score` are NOT modified.

    Args:
        intent: Detected question intent.
        result: Raw SearchResult from ChromaDB.

    Returns:
        Deterministic float score in range [0.0, 1.0].
    """
    base_score = result.similarity_score
    boost = 0.0
    penalty = 0.0
    text = result.text

    if intent == QuestionIntent.BENEFITS_PROVISION:
        # Boost for direct benefits / objectives / monetary terms
        for pattern in _BENEFITS_BOOST_PATTERNS:
            if pattern.search(text):
                boost = max(boost, 0.22)
        # Penalty for administrative procedures, tribal exceptions, or portal logins
        for pattern in _ADMIN_PENALTY_PATTERNS:
            if pattern.search(text):
                penalty = max(penalty, 0.18)

    elif intent == QuestionIntent.ELIGIBILITY_CRITERIA:
        # Boost for eligibility / exclusion definitions
        for pattern in _ELIGIBILITY_BOOST_PATTERNS:
            if pattern.search(text):
                boost = max(boost, 0.22)
        for pattern in _ADMIN_PENALTY_PATTERNS:
            if pattern.search(text):
                penalty = max(penalty, 0.15)

    elif intent == QuestionIntent.APPLICATION_PROCESS:
        # Boost for registration / application / portal instructions
        for pattern in _APPLICATION_BOOST_PATTERNS:
            if pattern.search(text):
                boost = max(boost, 0.22)

    final_score = base_score + boost - penalty
    return round(max(0.0, min(1.0, final_score)), 4)


def rerank_passages(
    query: str,
    results: list[SearchResult],
) -> list[SearchResult]:
    """Deterministically rerank candidate passages to prioritize direct answers.

    Safety:
    - Retains all SearchResult provenance fields untouched.
    - Preserves ChromaDB `distance` and `similarity_score` verbatim.
    - Annotates each result with `rerank_score`.

    Args:
        query: Citizen question string.
        results: Retrieved SearchResult items.

    Returns:
        List of SearchResult objects sorted by rerank_score descending.
    """
    if not results:
        return []

    intent = detect_question_intent(query)
    logger.debug(
        "Detected question intent '%s' for query: '%s'",
        intent.value,
        query[:50],
    )

    scored: list[SearchResult] = []
    for res in results:
        r_score = score_passage(intent, res)
        # Construct updated SearchResult with rerank_score populated
        updated = SearchResult(
            chunk_id=res.chunk_id,
            scheme_id=res.scheme_id,
            source_document=res.source_document,
            official_source_url=res.official_source_url,
            page_number=res.page_number,
            chunk_index=res.chunk_index,
            document_version=res.document_version,
            document_readiness=res.document_readiness,
            text=res.text,
            distance=res.distance,
            similarity_score=res.similarity_score,
            rerank_score=r_score,
        )
        scored.append(updated)

    # Sort descending by (rerank_score, -distance)
    scored.sort(
        key=lambda r: (
            r.rerank_score if r.rerank_score is not None else r.similarity_score,
            -r.distance,
        ),
        reverse=True,
    )

    return scored
