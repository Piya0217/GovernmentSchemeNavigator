"""Extractive answer builder for Government Scheme Navigator.

AGENTS.md Safety Contract:
- This module produces extractive answers ONLY: short verbatim or
  carefully selected passages from indexed official documents.
- It NEVER synthesizes eligibility decisions.
- It NEVER invents benefit amounts, dates, income limits, or conditions.
- It NEVER fabricates citations.
- When evidence is insufficient or out-of-scope, it returns a typed
  abstention response — never a hallucinated answer.
- All passages carry full provenance: scheme_id, source_document,
  official_source_url, page_number, chunk_id, document_version.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.retrieval.evidence import EvidenceVerdict, assess_evidence
from src.retrieval.schemas import SearchResult
from src.retrieval.search import SchemeSearcher

logger = logging.getLogger("scheme_navigator.retrieval.answer")

# Maximum characters of a passage to include verbatim in the response.
# Keeps responses focused while preserving extractive integrity.
MAX_PASSAGE_CHARS: int = 600

# Maximum number of evidence passages to include per response.
MAX_PASSAGES_PER_ANSWER: int = 3


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class EvidencePassage(BaseModel):
    """A single extractive passage from an official indexed document.

    All fields are sourced directly from the ChromaDB metadata —
    nothing is inferred or generated.
    """

    model_config = ConfigDict(frozen=True)

    chunk_id: str = Field(..., description="Deterministic chunk identifier.")
    scheme_id: str = Field(
        ..., description="Scheme identifier (e.g. 'central_pm_kisan')."
    )
    source_document: str = Field(
        ..., description="Filename of the source PDF document."
    )
    official_source_url: str = Field(
        ..., description="Verified official government source URL."
    )
    page_number: int = Field(..., ge=1, description="1-indexed source page number.")
    chunk_index: int = Field(..., ge=0, description="0-indexed chunk position.")
    document_version: str | None = Field(
        default=None, description="Document version or publication date."
    )
    passage_text: str = Field(
        ...,
        description=(
            "Verbatim extractive passage from the source document "
            "(truncated to MAX_PASSAGE_CHARS)."
        ),
    )
    distance: float = Field(
        ...,
        description="ChromaDB cosine distance in [0.0, 2.0]. Lower is more relevant.",
    )
    similarity_score: float = Field(
        ..., ge=0.0, le=1.0, description="Normalized similarity score in [0.0, 1.0]."
    )


class AnswerResponse(BaseModel):
    """Typed structured response from the answer layer.

    Status values:
      - "supported": Evidence found; extractive passages included.
      - "insufficient_evidence": Passages retrieved but too weak/ambiguous.
      - "out_of_scope": Query is definitively outside the welfare scheme domain.

    AGENTS.md compliance:
      - eligibility_assessed is always False.
        Eligibility will be implemented only in Phase 3 (deterministic rules engine).
    """

    model_config = ConfigDict(frozen=True)

    query: str = Field(..., description="Original user query string.")
    status: Literal["supported", "insufficient_evidence", "out_of_scope"] = Field(
        ..., description="Answer status."
    )
    passages: list[EvidencePassage] = Field(
        default_factory=list,
        description="Extractive evidence passages (empty when status != supported).",
    )
    abstention_reason: str | None = Field(
        default=None,
        description=(
            "Human-readable reason for abstention (set when status != supported)."
        ),
    )
    eligibility_assessed: bool = Field(
        default=False,
        description=(
            "Always False. Eligibility decisions require Phase 3 rules engine."
        ),
    )
    detected_scheme_id: str | None = Field(
        default=None,
        description="Scheme ID auto-detected from the query, if any.",
    )

    @property
    def is_supported(self) -> bool:
        """True when the answer has supporting evidence passages."""
        return self.status == "supported"

    @property
    def is_abstained(self) -> bool:
        """True when the system abstained (insufficient evidence or OOS)."""
        return self.status in ("insufficient_evidence", "out_of_scope")


# ---------------------------------------------------------------------------
# Answer Builder
# ---------------------------------------------------------------------------


class AnswerBuilder:
    """Builds structured extractive answers from retrieved scheme passages.

    Combines SchemeSearcher (retrieval) with the evidence assessment layer
    to produce typed, citation-complete AnswerResponse objects.

    Usage:
        builder = AnswerBuilder(searcher=searcher)
        response = builder.answer("What does PM-KISAN provide?")
    """

    def __init__(
        self,
        searcher: SchemeSearcher,
        top_k: int = 5,
        max_distance: float | None = 0.60,
    ) -> None:
        """Initialise the AnswerBuilder.

        Args:
            searcher: An initialised SchemeSearcher instance.
            top_k: Number of passages to retrieve before evidence filtering.
            max_distance: Distance cutoff passed to SchemeSearcher. Defaults
                to 0.60 (Phase 2C calibrated threshold).
        """
        self.searcher = searcher
        self.top_k = top_k
        self.max_distance = max_distance

    def answer(
        self,
        query: str,
        scheme_id: str | None = None,
    ) -> AnswerResponse:
        """Produce a structured extractive answer for a user query.

        Steps:
        1. Retrieve candidate passages via SchemeSearcher (with scheme-aware
           routing and Kannada intent expansion from Phase 2C).
        2. Run evidence assessment (Phase 2D) to detect OOS, coherence, and
           confidence gate.
        3. Select top MAX_PASSAGES_PER_ANSWER passages.
        4. Build and return a typed AnswerResponse.

        Safety invariants:
        - eligibility_assessed is never set to True here.
        - passage_text is always verbatim from the index (truncated).
        - No text is synthesized or generated.

        Args:
            query: User query string (English or Kannada).
            scheme_id: Optional explicit scheme_id override.

        Returns:
            AnswerResponse with status, passages, and provenance.
        """
        query = query.strip()
        if not query:
            return AnswerResponse(
                query=query,
                status="insufficient_evidence",
                abstention_reason=(
                    "The query is empty. Please provide a question about a "
                    "government scheme."
                ),
            )

        # Step 1: Retrieve passages
        try:
            raw_results: list[SearchResult] = self.searcher.search(
                query=query,
                top_k=self.top_k,
                scheme_id=scheme_id,
                max_distance=self.max_distance,
            )
        except Exception as err:
            logger.error("Search failed for query '%s': %s", query[:60], err)
            return AnswerResponse(
                query=query,
                status="insufficient_evidence",
                abstention_reason=(
                    "Search service is unavailable. Please try again later."
                ),
            )

        # Step 2: Evidence assessment — relay the same threshold used for retrieval
        from src.retrieval.query_analyzer import detect_explicit_scheme

        verdict, accepted = assess_evidence(
            query, raw_results, max_distance=self.max_distance
        )
        detected = detect_explicit_scheme(query)

        if verdict == EvidenceVerdict.out_of_scope:
            return AnswerResponse(
                query=query,
                status="out_of_scope",
                abstention_reason=(
                    "This question appears to be outside the scope of Indian "
                    "government welfare schemes covered by this system. "
                    "Please ask about PM-KISAN, Ayushman Bharat (PM-JAY), "
                    "PM Vishwakarma, or Sukanya Samriddhi Yojana."
                ),
                detected_scheme_id=detected,
            )

        if verdict == EvidenceVerdict.insufficient_evidence:
            return AnswerResponse(
                query=query,
                status="insufficient_evidence",
                abstention_reason=(
                    "Insufficient evidence found in the indexed documents to "
                    "answer this question reliably. The question may be too "
                    "generic, phrased in a way the system cannot match, or "
                    "the relevant scheme document may not yet be indexed."
                ),
                detected_scheme_id=detected,
            )

        # Step 3: Build passages (top MAX_PASSAGES_PER_ANSWER)
        top_accepted = accepted[:MAX_PASSAGES_PER_ANSWER]
        passages = [_build_passage(r) for r in top_accepted]

        return AnswerResponse(
            query=query,
            status="supported",
            passages=passages,
            detected_scheme_id=detected,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_passage(result: SearchResult) -> EvidencePassage:
    """Convert a SearchResult into an EvidencePassage with truncated text.

    The passage_text is truncated to MAX_PASSAGE_CHARS to keep responses
    focused. The text is never paraphrased or synthesized.
    """
    passage_text = result.text[:MAX_PASSAGE_CHARS]
    # Trim to last sentence boundary if truncated, to avoid mid-sentence cuts.
    if len(result.text) > MAX_PASSAGE_CHARS:
        last_period = passage_text.rfind(".")
        if last_period > MAX_PASSAGE_CHARS // 2:
            passage_text = passage_text[: last_period + 1]

    return EvidencePassage(
        chunk_id=result.chunk_id,
        scheme_id=result.scheme_id,
        source_document=result.source_document,
        official_source_url=result.official_source_url,
        page_number=result.page_number,
        chunk_index=result.chunk_index,
        document_version=result.document_version,
        passage_text=passage_text,
        distance=result.distance,
        similarity_score=result.similarity_score,
    )
