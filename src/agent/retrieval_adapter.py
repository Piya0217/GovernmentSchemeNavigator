"""Adapter from application workflows to the Phase 2 retrieval API."""

from __future__ import annotations

from typing import Protocol

from src.retrieval.answer import AnswerResponse


class AnswerBuilderLike(Protocol):
    """The subset of AnswerBuilder consumed by the application."""

    def answer(
        self,
        query: str,
        scheme_id: str | None = None,
    ) -> AnswerResponse:
        """Return the retrieval layer's answer and evidence unchanged."""


class RetrievalAdapter:
    """Delegate informational queries to the existing AnswerBuilder."""

    def __init__(self, answer_builder: AnswerBuilderLike) -> None:
        self._answer_builder = answer_builder

    def answer(
        self,
        query: str,
        scheme_id: str | None = None,
    ) -> AnswerResponse:
        """Call AnswerBuilder without duplicating retrieval behavior."""
        return self._answer_builder.answer(query, scheme_id)
