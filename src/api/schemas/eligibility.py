"""HTTP contracts for deterministic eligibility checks."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.rules.models import (
    CitizenProfile,
    EligibilityOutcome,
    RuleOutcome,
    SchemeId,
)


class EligibilityCheckRequest(BaseModel):
    """Scheme and caller-supplied profile for an in-memory assessment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scheme_id: SchemeId
    profile: CitizenProfile


class EligibilityCitation(BaseModel):
    """Source provenance attached to one evaluated rule."""

    model_config = ConfigDict(frozen=True)

    scheme_id: str
    document_id: str
    source_url: str
    document_version: str
    page_number: int = Field(ge=1)
    section: str | None = None
    excerpt_hash: str | None = None


class RuleEvaluationResponse(BaseModel):
    """Deterministic rule outcome and its official source citation."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    outcome: RuleOutcome
    reason: str
    citation: EligibilityCitation


class EligibilityCheckResponse(BaseModel):
    """Eligibility result without collapsing indeterminate outcomes to false."""

    model_config = ConfigDict(frozen=True)

    scheme_id: str
    status: Literal[
        "eligible",
        "ineligible",
        "needs_more_information",
        "unsupported_scheme",
    ]
    outcome: EligibilityOutcome | None = None
    eligible: bool = False
    explanation: str
    missing_fields: tuple[str, ...] = ()
    rule_evaluations: tuple[RuleEvaluationResponse, ...] = ()
    evaluated_at: str | None = None
    engine_version: str | None = None
