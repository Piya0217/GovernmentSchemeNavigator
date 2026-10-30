"""Tests for eligibility model validation using synthetic rule data."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from src.rules.models import (
    CitizenProfile,
    EligibilityOutcome,
    EligibilityResult,
    EligibilityRule,
    RuleEvaluation,
    RuleOperator,
    RuleOutcome,
    RuleProvenance,
    RuleStatus,
)


def make_provenance(**overrides: object) -> RuleProvenance:
    """Build valid synthetic source provenance for model tests."""
    values: dict[str, object] = {
        "scheme_id": "synthetic_scheme",
        "document_id": "synthetic-guidelines.pdf",
        "source_url": "https://example.gov.in/synthetic-guidelines.pdf",
        "document_version": "synthetic-v1",
        "page_number": 2,
        "section": "Synthetic eligibility section",
        "excerpt_hash": "a" * 64,
    }
    values.update(overrides)
    return RuleProvenance(**values)


def make_rule(**overrides: object) -> EligibilityRule:
    """Build a valid synthetic eligibility rule for model tests."""
    values: dict[str, object] = {
        "rule_id": "synthetic-age-minimum",
        "field": "age",
        "operator": RuleOperator.GTE,
        "value": 18,
        "status": RuleStatus.DRAFT,
        "mandatory": True,
        "provenance": make_provenance(),
        "rule_version": "1.0.0",
    }
    values.update(overrides)
    return EligibilityRule(**values)


def test_citizen_profile_valid_and_optional() -> None:
    profile = CitizenProfile(age=35, annual_income=125000.5, state="Karnataka")

    assert profile.age == 35
    assert profile.annual_income == 125000.5
    assert profile.state == "Karnataka"
    assert profile.district is None


@pytest.mark.parametrize("values", [{"age": -1}, {"age": 151}, {"household_size": 0}])
def test_citizen_profile_rejects_out_of_range_values(values: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        CitizenProfile(**values)


def test_citizen_profile_rejects_wrong_types_and_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CitizenProfile(age="35")
    with pytest.raises(ValidationError):
        CitizenProfile(unknown_attribute="value")


@pytest.mark.parametrize("income", [float("nan"), float("inf"), float("-inf")])
def test_citizen_profile_rejects_non_finite_income(income: float) -> None:
    with pytest.raises(ValidationError):
        CitizenProfile(annual_income=income)


def test_rule_provenance_valid() -> None:
    provenance = make_provenance(section=None, excerpt_hash=None)

    assert provenance.page_number == 2
    assert provenance.section is None
    assert provenance.excerpt_hash is None


@pytest.mark.parametrize("page_number", [0, -1])
def test_rule_provenance_rejects_invalid_page_number(page_number: int) -> None:
    with pytest.raises(ValidationError):
        make_provenance(page_number=page_number)


@pytest.mark.parametrize(
    "source_url",
    [
        "file:///tmp/source.pdf",
        "https://user:pass@example.gov.in/file.pdf",
        "not-a-url",
    ],
)
def test_rule_provenance_rejects_invalid_source_url(source_url: str) -> None:
    with pytest.raises(ValidationError):
        make_provenance(source_url=source_url)


def test_rule_provenance_rejects_invalid_excerpt_hash() -> None:
    with pytest.raises(ValidationError):
        make_provenance(excerpt_hash="not-a-sha256-hash")


def test_eligibility_rule_valid() -> None:
    rule = make_rule()

    assert rule.field == "age"
    assert rule.operator is RuleOperator.GTE
    assert rule.value == 18


def test_eligibility_rule_requires_all_fields() -> None:
    with pytest.raises(ValidationError):
        EligibilityRule(
            rule_id="rule",
            field="age",
            operator=RuleOperator.GTE,
            value=18,
            status=RuleStatus.DRAFT,
            mandatory=True,
            provenance=make_provenance(),
        )


def test_eligibility_rule_rejects_invalid_enum_values() -> None:
    with pytest.raises(ValidationError):
        make_rule(operator="EXEC")
    with pytest.raises(ValidationError):
        make_rule(status="AWAITING")


def test_legacy_draft_status_parses_and_serializes_as_pending() -> None:
    rule = make_rule(status="DRAFT")

    assert rule.status is RuleStatus.PENDING
    assert rule.model_dump(mode="json")["status"] == "PENDING"


def test_eligibility_rule_rejects_unsupported_fields_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        make_rule(field="unverified_attribute")
    with pytest.raises(ValidationError):
        make_rule(arbitrary_expression="age > 18")


@pytest.mark.parametrize(
    "operator,value",
    [
        (RuleOperator.IN, []),
        (RuleOperator.IN, 18),
        (RuleOperator.EQ, [18]),
        (RuleOperator.GT, "eighteen"),
        (RuleOperator.GT, 18.5),
        (RuleOperator.EQ, "eighteen"),
        (RuleOperator.GT, 1),
    ],
)
def test_eligibility_rule_rejects_malformed_values(
    operator: RuleOperator, value: object
) -> None:
    field = "occupation" if operator is RuleOperator.GT and value == 1 else "age"
    with pytest.raises(ValidationError):
        make_rule(operator=operator, value=value, field=field)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_eligibility_rule_rejects_non_finite_numeric_values(value: float) -> None:
    with pytest.raises(ValidationError):
        make_rule(field="annual_income", operator=RuleOperator.GTE, value=value)


def test_eligibility_rule_supports_synthetic_membership_rule() -> None:
    rule = make_rule(
        field="state",
        operator=RuleOperator.IN,
        value=["Example State A", "Example State B"],
    )

    assert rule.operator is RuleOperator.IN
    assert rule.value == ("Example State A", "Example State B")
    assert rule.model_dump(mode="json")["value"] == [
        "Example State A",
        "Example State B",
    ]


def test_membership_values_are_deeply_immutable() -> None:
    source_values = ["Example State A", "Example State B"]
    rule = make_rule(field="state", operator=RuleOperator.IN, value=source_values)

    source_values.append("Example State C")
    assert rule.value == ("Example State A", "Example State B")
    with pytest.raises(TypeError):
        rule.value[0] = "Changed State"


def test_rule_evaluation_valid() -> None:
    evaluation = RuleEvaluation(
        rule_id="synthetic-age-minimum",
        outcome=RuleOutcome.PASS,
        reason="Synthetic age condition passed.",
        provenance=make_provenance(),
    )

    assert evaluation.outcome is RuleOutcome.PASS


def test_eligibility_result_requires_timezone_aware_datetime() -> None:
    values: dict[str, object] = {
        "scheme_id": "synthetic_scheme",
        "outcome": EligibilityOutcome.NEEDS_MORE_INFORMATION,
        "rule_evaluations": [],
        "explanation": "Synthetic result; required information is missing.",
        "engine_version": "0.1.0",
    }
    with pytest.raises(ValidationError):
        EligibilityResult(**values, evaluated_at=datetime(2026, 1, 1))

    result = EligibilityResult(**values, evaluated_at=datetime(2026, 1, 1, tzinfo=UTC))
    assert result.evaluated_at.utcoffset() is not None
    assert result.rule_evaluations == ()


def test_result_rule_evaluations_are_deeply_immutable_and_serializable() -> None:
    evaluation = RuleEvaluation(
        rule_id="synthetic-age-minimum",
        outcome=RuleOutcome.PASS,
        reason="Synthetic age condition passed.",
        provenance=make_provenance(),
    )
    source_evaluations = [evaluation]
    result = EligibilityResult(
        scheme_id="synthetic_scheme",
        outcome=EligibilityOutcome.ELIGIBLE,
        rule_evaluations=source_evaluations,
        explanation="All synthetic conditions passed.",
        evaluated_at=datetime(2026, 1, 1, tzinfo=UTC),
        engine_version="0.1.0",
    )

    source_evaluations.clear()
    assert result.rule_evaluations == (evaluation,)
    with pytest.raises(AttributeError):
        result.rule_evaluations.append(evaluation)
    with pytest.raises(TypeError):
        result.rule_evaluations[0] = evaluation

    serialized = result.model_dump(mode="json")
    assert isinstance(serialized["rule_evaluations"], list)
    assert serialized["rule_evaluations"][0]["rule_id"] == evaluation.rule_id


def test_eligibility_result_rejects_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        EligibilityResult(
            scheme_id="synthetic_scheme",
            outcome=EligibilityOutcome.ELIGIBLE,
            rule_evaluations=[],
            explanation="Synthetic result.",
            evaluated_at=datetime(2026, 1, 1, tzinfo=UTC),
            engine_version="0.1.0",
            persisted_profile={"age": 30},
        )
