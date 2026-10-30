"""Deterministic evidence-relevance assessment for retrieved scheme passages.

Design philosophy (AGENTS.md compliance):
- This module NEVER makes eligibility decisions.
- A heuristic relevance verdict is clearly distinct from a verified legal fact.
- When evidence is ambiguous, the system abstains rather than inventing an answer.
- Distance threshold alone is insufficient; topical coherence and OOS detection
  are layered on top of distance to reduce false positives.
- Rules are conservative: a borderline case is treated as insufficient_evidence,
  not as a positive match.
"""

from __future__ import annotations

import logging
import re
from enum import StrEnum

from src.retrieval.query_analyzer import (
    detect_explicit_scheme,
    has_kannada_script,
)
from src.retrieval.schemas import SearchResult

logger = logging.getLogger("scheme_navigator.retrieval.evidence")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Cosine distance below which a passage is considered strongly relevant.
# Calibrated against Phase 2C evaluation: verified hits fall within 0.21–0.54.
STRONG_RELEVANCE_DISTANCE: float = 0.52

# Cosine distance above which a passage is unconditionally rejected,
# even if topical checks pass.
MAX_ACCEPTED_DISTANCE: float = 0.60

# Minimum number of passages required to produce a "supported" verdict.
MIN_EVIDENCE_PASSAGES: int = 1

# ---------------------------------------------------------------------------
# Out-of-Scope Topic Patterns
# ---------------------------------------------------------------------------
# These patterns match topics that are definitively outside the domain of
# Indian government welfare schemes.  They are NOT used to restrict valid
# paraphrases of scheme-related content; they only block clearly unrelated topics.
#
# Pattern design principles:
#   - Match whole words or distinctive phrase fragments.
#   - Do NOT include generic welfare words (income, support, benefit, family, etc.)
#   - Cover the known-failing OOS queries from Phase 2C evaluation.

_OOS_PATTERNS_LATIN: list[re.Pattern[str]] = [
    re.compile(r"\bisro\b", re.IGNORECASE),
    re.compile(r"\bchandrayaan\b", re.IGNORECASE),
    re.compile(r"\bmangalyaan\b", re.IGNORECASE),
    re.compile(r"\bspace\s+(mission|agency|launch|vehicle|rocket)\b", re.IGNORECASE),
    re.compile(r"\bdriving\s+licen[sc]e\b", re.IGNORECASE),
    re.compile(r"\bmotor\s+vehicle\s+licen[sc]e\b", re.IGNORECASE),
    re.compile(r"\blicen[sc]e\s+renewal\b", re.IGNORECASE),
    re.compile(r"\bpassport\s+(application|renewal|seva)\b", re.IGNORECASE),
    re.compile(r"\bstock\s+(market|exchange|broker|trading)\b", re.IGNORECASE),
    re.compile(r"\bcricket\b", re.IGNORECASE),
    re.compile(r"\bfilm\s+(award|festival|industry)\b", re.IGNORECASE),
    re.compile(r"\belection\s+result\b", re.IGNORECASE),
]

# Kannada OOS patterns (substring, no word-boundary needed for Indic)
_OOS_PATTERNS_KANNADA: list[str] = [
    "ಚಾಲನಾ ಪರವಾನಗಿ",  # driving license
    "ವಾಹನ ಚಾಲನಾ ಪರವಾನಿಗೆ",  # vehicle driving license variant
    "ಇಸ್ರೋ",  # ISRO in Kannada
    "ಪಾಸ್‌ಪೋರ್ಟ್",  # passport
]

# ---------------------------------------------------------------------------
# Welfare domain anchor words for generic (non-explicit) queries.
# If a generic query contains none of these, it is treated with extra caution.
# This is a soft heuristic - absence does not force rejection.
# ---------------------------------------------------------------------------

_WELFARE_ANCHOR_WORDS: frozenset[str] = frozenset(
    {
        # Scheme / programme
        "scheme",
        "yojana",
        "programme",
        "program",
        "benefit",
        "subsidy",
        "grant",
        "allowance",
        "pension",
        # Target beneficiaries
        "farmer",
        "kisan",
        "artisan",
        "craftsman",
        "craftspeople",
        "girl",
        "daughter",
        "woman",
        "family",
        "household",
        "poor",
        "rural",
        "urban",
        # Welfare services
        "health",
        "insurance",
        "hospitalization",
        "medical",
        "savings",
        "deposit",
        "income",
        "financial",
        "assistance",
        "support",
        "eligibility",
        "enroll",
        "register",
        "toolkit",
        "loan",
        "credit",
    }
)


# ---------------------------------------------------------------------------
# Evidence Verdict
# ---------------------------------------------------------------------------


class EvidenceVerdict(StrEnum):
    """Outcome of evidence assessment for a query-passage set.

    Values:
        supported: Sufficient, topically coherent passages found.
        insufficient_evidence: Passages found but too weak or ambiguous.
        out_of_scope: Query is definitively outside government welfare domain.
    """

    supported = "supported"
    insufficient_evidence = "insufficient_evidence"
    out_of_scope = "out_of_scope"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_out_of_scope(query: str) -> bool:
    """Return True if the query matches a known out-of-scope topic pattern.

    Checks both Latin script (regex word-boundary) and Kannada script
    (substring) OOS patterns.  Does NOT check whether results were found;
    this is purely a query-text analysis.

    Args:
        query: The raw user query string.

    Returns:
        True if the query is definitively out of scope, False otherwise.
    """
    query_lower = query.lower()

    # Latin OOS check
    for pattern in _OOS_PATTERNS_LATIN:
        if pattern.search(query_lower):
            logger.info(
                "OOS pattern matched for query: '%s' (pattern: %s)",
                query[:60],
                pattern.pattern,
            )
            return True

    # Kannada OOS check
    if has_kannada_script(query):
        query_stripped = query.strip()
        for kn_phrase in _OOS_PATTERNS_KANNADA:
            if kn_phrase in query_stripped:
                logger.info(
                    "Kannada OOS pattern matched: '%s' in query '%s'",
                    kn_phrase,
                    query[:60],
                )
                return True

    return False


def has_welfare_context(query: str) -> bool:
    """Heuristic check: does the query contain welfare-domain vocabulary?

    Used as a soft signal for generic queries that match no explicit scheme alias.
    A False result does not force rejection — it contributes to a lower confidence
    for ambiguous passages.

    Args:
        query: The raw user query string.

    Returns:
        True if at least one welfare anchor word is found in the query.
    """
    query_lower = query.lower()
    return any(word in query_lower for word in _WELFARE_ANCHOR_WORDS)


def assess_evidence(
    query: str,
    results: list[SearchResult],
    *,
    require_scheme_coherence: bool = True,
    max_distance: float | None = MAX_ACCEPTED_DISTANCE,
) -> tuple[EvidenceVerdict, list[SearchResult]]:
    """Assess the relevance of retrieved passages for a given query.

    Decision logic (conservative layered heuristic):
    1. If the query is definitively OOS -> return out_of_scope with no passages.
    2. If no passages were retrieved -> insufficient_evidence.
    3. If an explicit scheme was detected in the query, only passages from that
       scheme are considered (scheme coherence).
    4. Passages above max_distance (if set) are discarded.
    5. If the best-remaining passage distance > STRONG_RELEVANCE_DISTANCE AND
       the query has no welfare context AND no explicit scheme -> insufficient_evidence.
    6. If MIN_EVIDENCE_PASSAGES remain -> supported.
    7. Otherwise -> insufficient_evidence.

    Args:
        query: The raw user query string.
        results: SearchResult list from SchemeSearcher.
        require_scheme_coherence: If True (default), apply scheme-ID coherence
            filtering when an explicit scheme is detected in the query.
        max_distance: Hard ceiling for accepted distances. When None, no ceiling
            is applied (useful for testing with deterministic fake embedders
            or when caller has already applied their own threshold).

    Returns:
        A tuple of (EvidenceVerdict, list[SearchResult]) where the list
        contains only the accepted, evidence-qualified passages.
    """
    # Step 1: OOS check
    if is_out_of_scope(query):
        logger.info("Query classified as out_of_scope: '%s'", query[:80])
        return EvidenceVerdict.out_of_scope, []

    # Step 2: No results at all
    if not results:
        logger.info(
            "No passages retrieved for query — insufficient_evidence: '%s'",
            query[:80],
        )
        return EvidenceVerdict.insufficient_evidence, []

    # Step 3: Scheme coherence filtering
    explicit_scheme = detect_explicit_scheme(query)
    accepted: list[SearchResult] = []
    for r in results:
        # Hard distance ceiling (optional backstop)
        if max_distance is not None and r.distance > max_distance:
            logger.debug(
                "Discarding chunk %s: distance %.4f > max_distance %.4f",
                r.chunk_id,
                r.distance,
                max_distance,
            )
            continue

        # Scheme coherence: if the query explicitly names one scheme, only
        # accept passages from that scheme.
        if require_scheme_coherence and explicit_scheme:
            if r.scheme_id != explicit_scheme:
                logger.debug(
                    "Discarding chunk %s: scheme '%s' != explicit '%s'",
                    r.chunk_id,
                    r.scheme_id,
                    explicit_scheme,
                )
                continue

        accepted.append(r)

    # Step 4: Check if any passages survived
    if not accepted:
        return EvidenceVerdict.insufficient_evidence, []

    # Step 5: Confidence gate for generic, non-scheme queries
    best_distance = min(r.distance for r in accepted)
    is_explicit = explicit_scheme is not None
    has_context = has_welfare_context(query)

    if (
        not is_explicit
        and not has_context
        and best_distance > STRONG_RELEVANCE_DISTANCE
    ):
        logger.info(
            "Generic query with no welfare context and weak distance (%.4f) "
            "→ insufficient_evidence: '%s'",
            best_distance,
            query[:80],
        )
        return EvidenceVerdict.insufficient_evidence, []

    # Step 6: Minimum evidence threshold
    if len(accepted) < MIN_EVIDENCE_PASSAGES:
        return EvidenceVerdict.insufficient_evidence, []

    logger.info(
        "Evidence verdict: supported (%d passages, best dist=%.4f) for '%s'",
        len(accepted),
        best_distance,
        query[:80],
    )
    return EvidenceVerdict.supported, accepted
