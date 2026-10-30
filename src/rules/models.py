"""Validated data models for deterministic eligibility rules and results."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    StringConstraints,
    model_validator,
)


class RuleStatus(StrEnum):
    """Lifecycle state for a rule definition."""

    PENDING = "PENDING"
    DRAFT = "PENDING"
    REVIEWED = "REVIEWED"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"

    @classmethod
    def _missing_(cls, value: object) -> RuleStatus | None:
        """Map the legacy DRAFT label to canonical PENDING."""
        if value == "DRAFT":
            return cls.PENDING
        return None


class RuleOutcome(StrEnum):
    """Outcome of evaluating one eligibility rule."""

    PASS = "PASS"  # noqa: S105  # Domain outcome value, not a password.
    FAIL = "FAIL"
    UNEVALUABLE = "UNEVALUABLE"


class EligibilityOutcome(StrEnum):
    """Overall result of an eligibility assessment."""

    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    NEEDS_MORE_INFORMATION = "NEEDS_MORE_INFORMATION"


class RuleOperator(StrEnum):
    """Supported deterministic comparison operators."""

    EQ = "EQ"
    NE = "NE"
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    IN = "IN"
    NOT_IN = "NOT_IN"


NonEmptyString = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=512),
]
SchemeId = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
ProfileField = Literal[
    "age",
    "annual_income",
    "occupation",
    "state",
    "district",
    "gender",
    "household_size",
]
ProfileText = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=256),
]
FiniteStrictFloat = Annotated[StrictFloat, Field(allow_inf_nan=False)]
RuleScalar = StrictStr | StrictInt | FiniteStrictFloat | StrictBool


def _validate_http_url(value: str) -> str:
    """Require an HTTP(S) URL without credentials or whitespace."""
    parsed = urlsplit(value)
    if (
        any(character.isspace() for character in value)
        or parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        msg = "source_url must be a valid HTTP(S) URL without credentials."
        raise ValueError(msg)
    return value


HttpUrlString = Annotated[StrictStr, AfterValidator(_validate_http_url)]
Sha256Hash = Annotated[
    StrictStr,
    StringConstraints(pattern=r"^[A-Fa-f0-9]{64}$"),
]


class CitizenProfile(BaseModel):
    """In-memory, caller-provided attributes that rules may evaluate.

    All fields are optional because each scheme defines its own information
    requirements. This model does not persist profile information.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    age: StrictInt | None = Field(default=None, ge=0, le=150)
    annual_income: StrictInt | FiniteStrictFloat | None = Field(default=None, ge=0)
    occupation: ProfileText | None = None
    state: ProfileText | None = None
    district: ProfileText | None = None
    gender: ProfileText | None = None
    household_size: StrictInt | None = Field(default=None, ge=1)


class RuleProvenance(BaseModel):
    """Official document location supporting a rule definition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scheme_id: SchemeId
    document_id: NonEmptyString
    source_url: HttpUrlString
    document_version: NonEmptyString
    page_number: StrictInt = Field(..., ge=1)
    section: NonEmptyString | None = None
    excerpt_hash: Sha256Hash | None = None


class RuleApprovalEvidence(BaseModel):
    """Review record metadata supplied by a trusted human-review workflow.

    This records review evidence but does not authenticate the reviewer.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reviewer_id: NonEmptyString
    reviewed_at: AwareDatetime
    document_id: NonEmptyString
    document_version: NonEmptyString
    rule_version: NonEmptyString
    approval_reference: NonEmptyString


class EligibilityRule(BaseModel):
    """A non-executable, structured comparison against one profile field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: NonEmptyString
    field: ProfileField
    operator: RuleOperator
    value: RuleScalar | tuple[RuleScalar, ...]
    status: RuleStatus
    mandatory: StrictBool
    provenance: RuleProvenance
    rule_version: NonEmptyString
    approval_evidence: RuleApprovalEvidence | None = None

    @model_validator(mode="after")
    def validate_definition(self) -> EligibilityRule:
        """Reject values incompatible with the selected field/operator."""
        is_membership = self.operator in {RuleOperator.IN, RuleOperator.NOT_IN}
        if is_membership != isinstance(self.value, tuple):
            msg = (
                "IN and NOT_IN require a non-empty list; "
                "other operators require a scalar."
            )
            raise ValueError(msg)
        values = self.value if isinstance(self.value, tuple) else (self.value,)
        if not values:
            msg = "Rule value lists cannot be empty."
            raise ValueError(msg)

        numeric_fields = {"age", "annual_income", "household_size"}
        if (
            self.operator
            in {
                RuleOperator.GT,
                RuleOperator.GTE,
                RuleOperator.LT,
                RuleOperator.LTE,
            }
            and self.field not in numeric_fields
        ):
            msg = "Ordering operators are supported only for numeric profile fields."
            raise ValueError(msg)

        for value in values:
            if not self._value_matches_field(value, self.field):
                msg = (
                    "Rule value type is incompatible with profile field "
                    f"'{self.field}'."
                )
                raise ValueError(msg)
        return self

    @staticmethod
    def _value_matches_field(value: RuleScalar, field: ProfileField) -> bool:
        """Check the JSON scalar type expected by a citizen profile field."""
        if field == "age" or field == "household_size":
            return isinstance(value, int) and not isinstance(value, bool)
        if field == "annual_income":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        return isinstance(value, str)


class EligibilityRuleSet(BaseModel):
    """Versioned, immutable collection of rules for one scheme."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scheme_id: SchemeId
    schema_version: NonEmptyString
    rules: tuple[EligibilityRule, ...]


class RuleEvaluation(BaseModel):
    """Auditable outcome and explanation for one evaluated rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: NonEmptyString
    outcome: RuleOutcome
    reason: NonEmptyString
    provenance: RuleProvenance


class EligibilityResult(BaseModel):
    """Overall eligibility outcome with per-rule explanations and provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scheme_id: SchemeId
    outcome: EligibilityOutcome
    rule_evaluations: tuple[RuleEvaluation, ...]
    explanation: NonEmptyString
    evaluated_at: AwareDatetime
    engine_version: NonEmptyString


__all__ = [
    "CitizenProfile",
    "EligibilityOutcome",
    "EligibilityResult",
    "EligibilityRule",
    "EligibilityRuleSet",
    "RuleApprovalEvidence",
    "RuleEvaluation",
    "RuleOperator",
    "RuleOutcome",
    "RuleProvenance",
    "RuleStatus",
]
