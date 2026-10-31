"""Coordinate application workflows without implementing domain decisions."""

from __future__ import annotations

from typing import Protocol

from src.retrieval.answer import AnswerResponse


class RetrievalService(Protocol):
    """Application-facing port for informational retrieval."""

    def answer(
        self,
        query: str,
        scheme_id: str | None = None,
    ) -> AnswerResponse:
        """Return an extractive answer from the retrieval service."""


class RetrievalUnavailableError(Exception):
    """Raised when retrieval was unavailable before a query could be attempted."""


class WorkflowOrchestrator:
    """Coordinate query workflows while leaving retrieval logic to Phase 2."""

    def __init__(self, retrieval: RetrievalService | None) -> None:
        self._retrieval = retrieval

    def answer_query(
        self,
        query: str,
        scheme_id: str | None = None,
    ) -> AnswerResponse:
        """Delegate an informational query to the retrieval adapter."""
        if self._retrieval is None:
            raise RetrievalUnavailableError("Retrieval is not configured.")
        return self._retrieval.answer(query, scheme_id)
