"""Schemas for informational query endpoints."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class QueryRequest(BaseModel):
    """Validated request for an informational scheme query."""

    model_config = ConfigDict(extra="forbid")

    query: Annotated[str, Field(min_length=1, max_length=2000)]
    scheme_id: (
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True,
                min_length=1,
                max_length=128,
                pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
            ),
        ]
        | None
    ) = None

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        """Reject whitespace-only queries and normalize surrounding whitespace."""
        query = value.strip()
        if not query:
            msg = "query must contain non-whitespace characters."
            raise ValueError(msg)
        return query
