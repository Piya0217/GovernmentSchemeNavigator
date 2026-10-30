"""Tests for deterministic rule evaluation using synthetic eligibility data."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from src.rules.evaluation import ENGINE_VERSION, evaluate_rule, evaluate_rule_set
from src.rules.models import (
    CitizenProfile,
    EligibilityOutcome,
    EligibilityRule,
    EligibilityRuleSet,
    RuleApprovalEvidence,
    RuleOperator,
    RuleOutcome,
    RuleProvenance,
    RuleStatus,
)
from src.rules.validation import RULE_SCHEMA_VERSION

EVALUATED_AT = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)


def make_provenance() -> RuleProvenance:
    """Build provenance for a synthetic source document."""
    return RuleProvenance(
        scheme_id="synthetic_scheme",
        document_id="synthetic-guidelines.pdf",
        source_url="https://example.gov.in/synthetic-guidelines.pdf",
        document_version="synthetic-v1",
        page_number=1,
    )


def make_approval() -> RuleApprovalEvidence:
    """Build matching synthetic review evidence."""
    return RuleApprovalEvidence(
        reviewer_id="reviewer-synthetic-1",
        reviewed_at=EVALUATED_AT,
        document_id="synthetic-guidelines.pdf",
        document_version="synthetic-v1",
        rule_version="1.0.0",
        approval_reference="synthetic-review-1",
    )


def make_rule(**overrides: object) -> EligibilityRule:
    """Build a synthetic ACTIVE rule with matching review evidence."""
    values: dict[str, object] = {
        "rule_id": "synthetic-age-rule",
        "field": "age",
        "operator": RuleOperator.GTE,
        "value": 18,
        "status": RuleStatus.ACTIVE,
        "mandatory": True,
        "provenance": make_provenance(),
        "rule_version": "1.0.0",
        "approval_evidence": make_approval(),
    }
    values.update(overrides)
    return EligibilityRule(**values)


def make_rule_set(*rules: EligibilityRule) -> EligibilityRuleSet:
    """Build a rule set from synthetic rules."""
    return EligibilityRuleSet(
        scheme_id="synthetic_scheme",
        schema_version=RULE_SCHEMA_VERSION,
        rules=rules,
    )


@pytest.mark.parametrize(
    "operator,rule_value,profile_value,expected",
    [
        (RuleOperator.EQ, 18, 18, RuleOutcome.PASS),
        (RuleOperator.NE, 18, 19, RuleOutcome.PASS),
        (RuleOperator.GT, 18, 19, RuleOutcome.PASS),
        (RuleOperator.GTE, 18, 18, RuleOutcome.PASS),
        (RuleOperator.GTE, 18, 17, RuleOutcome.FAIL),
        (RuleOperator.LT, 19, 18, RuleOutcome.PASS),
        (RuleOperator.LTE, 18, 18, RuleOutcome.PASS),
        (RuleOperator.LTE, 18, 19, RuleOutcome.FAIL),
        (RuleOperator.IN, [18, 19], 19, RuleOutcome.PASS),
        (RuleOperator.NOT_IN, [18, 19], 20, RuleOutcome.PASS),
        (RuleOperator.EQ, 18, 19, RuleOutcome.FAIL),
        (RuleOperator.NE, 18, 18, RuleOutcome.FAIL),
        (RuleOperator.GT, 18, 18, RuleOutcome.FAIL),
        (RuleOperator.LT, 18, 18, RuleOutcome.FAIL),
        (RuleOperator.IN, [18, 19], 20, RuleOutcome.FAIL),
        (RuleOperator.NOT_IN, [18, 19], 19, RuleOutcome.FAIL),
    ],
)
def test_evaluate_rule_supports_all_operators_and_boundaries(
    operator: RuleOperator,
    rule_value: object,
    profile_value: int,
    expected: RuleOutcome,
) -> None:
    rule = make_rule(operator=operator, value=rule_value)

    result = evaluate_rule(rule, CitizenProfile(age=profile_value))

    assert result.outcome is expected


def test_missing_required_field_is_unevaluable_and_needs_more_information() -> None:
    result = evaluate_rule_set(
        make_rule_set(make_rule()), CitizenProfile(), evaluated_at=EVALUATED_AT
    )

    assert result.outcome is EligibilityOutcome.NEEDS_MORE_INFORMATION
    assert result.rule_evaluations[0].outcome is RuleOutcome.UNEVALUABLE
    assert "age" in result.rule_evaluations[0].reason
    assert "age" in result.explanation


def test_profile_and_rule_comparisons_do_not_treat_booleans_as_integers() -> None:
    with pytest.raises(ValidationError):
        CitizenProfile(age=True)
    with pytest.raises(ValidationError):
        make_rule(value=True)

    bypass_validated_profile = CitizenProfile.model_construct(age=True)
    result = evaluate_rule(
        make_rule(operator=RuleOperator.EQ, value=1), bypass_validated_profile
    )

    assert result.outcome is RuleOutcome.UNEVALUABLE
    assert "invalid type" in result.reason


def test_mandatory_fail_takes_precedence_over_mandatory_missing_information() -> None:
    failing = make_rule(rule_id="rule-fail", value=20)
    missing = make_rule(
        rule_id="rule-missing",
        field="state",
        operator=RuleOperator.EQ,
        value="Example State",
    )

    result = evaluate_rule_set(
        make_rule_set(failing, missing),
        CitizenProfile(age=18),
        evaluated_at=EVALUATED_AT,
    )

    assert result.outcome is EligibilityOutcome.INELIGIBLE


def test_mandatory_missing_without_failure_needs_more_information() -> None:
    present = make_rule(rule_id="rule-pass")
    missing = make_rule(
        rule_id="rule-missing",
        field="state",
        operator=RuleOperator.EQ,
        value="Example State",
    )

    result = evaluate_rule_set(
        make_rule_set(present, missing),
        CitizenProfile(age=18),
        evaluated_at=EVALUATED_AT,
    )

    assert result.outcome is EligibilityOutcome.NEEDS_MORE_INFORMATION


def test_all_mandatory_rules_passing_is_eligible() -> None:
    rule = make_rule()

    result = evaluate_rule_set(
        make_rule_set(rule), CitizenProfile(age=18), evaluated_at=EVALUATED_AT
    )

    assert result.outcome is EligibilityOutcome.ELIGIBLE


@pytest.mark.parametrize("optional_state", ["fail", "missing"])
def test_optional_rule_outcomes_do_not_override_mandatory_result(
    optional_state: str,
) -> None:
    mandatory = make_rule(rule_id="mandatory-age")
    optional = make_rule(
        rule_id="optional-state",
        field="state",
        operator=RuleOperator.EQ,
        value="Example State",
        mandatory=False,
    )
    profile = (
        CitizenProfile(age=18, state="Other State")
        if optional_state == "fail"
        else CitizenProfile(age=18)
    )

    result = evaluate_rule_set(
        make_rule_set(optional, mandatory), profile, evaluated_at=EVALUATED_AT
    )

    assert result.outcome is EligibilityOutcome.ELIGIBLE
    assert "Optional rules (informational only)" in result.explanation


def test_optional_only_rule_set_does_not_create_positive_outcome() -> None:
    optional = make_rule(mandatory=False)

    result = evaluate_rule_set(
        make_rule_set(optional), CitizenProfile(age=18), evaluated_at=EVALUATED_AT
    )

    assert result.outcome is EligibilityOutcome.NEEDS_MORE_INFORMATION
    assert "No mandatory rules" in result.explanation


@pytest.mark.parametrize(
    "status", [RuleStatus.PENDING, RuleStatus.REVIEWED, RuleStatus.RETIRED]
)
def test_non_active_rules_are_not_evaluated(status: RuleStatus) -> None:
    rule = make_rule(status=status)

    result = evaluate_rule(rule, CitizenProfile(age=100))

    assert result.outcome is RuleOutcome.UNEVALUABLE
    assert "not ACTIVE" in result.reason


def test_active_status_without_approval_is_not_evaluated() -> None:
    rule = make_rule(status=RuleStatus.ACTIVE, approval_evidence=None)

    result = evaluate_rule(rule, CitizenProfile(age=100))

    assert result.outcome is RuleOutcome.UNEVALUABLE
    assert "Activation validation failed" in result.reason

    aggregate = evaluate_rule_set(make_rule_set(rule), CitizenProfile(age=100))
    assert aggregate.outcome is EligibilityOutcome.NEEDS_MORE_INFORMATION


def test_empty_rule_set_fails_closed() -> None:
    result = evaluate_rule_set(
        make_rule_set(), CitizenProfile(), evaluated_at=EVALUATED_AT
    )

    assert result.outcome is EligibilityOutcome.NEEDS_MORE_INFORMATION
    assert result.rule_evaluations == ()
    assert "rule set validation failed" in result.explanation.lower()


def test_explanation_is_deterministic_and_identifies_rule_outcomes() -> None:
    first = make_rule(rule_id="rule-b", value=20)
    second = make_rule(
        rule_id="rule-a",
        field="state",
        operator=RuleOperator.EQ,
        value="Example State",
    )
    profile = CitizenProfile(age=18)

    result_one = evaluate_rule_set(
        make_rule_set(first, second), profile, evaluated_at=EVALUATED_AT
    )
    result_two = evaluate_rule_set(
        make_rule_set(second, first), profile, evaluated_at=EVALUATED_AT
    )

    assert result_one.explanation == result_two.explanation
    assert "rule-a=UNEVALUABLE" in result_one.explanation
    assert "rule-b=FAIL" in result_one.explanation
    assert "state" in result_one.explanation


def test_result_serialization_contains_outcomes_provenance_and_engine_version() -> None:
    result = evaluate_rule_set(
        make_rule_set(make_rule()),
        CitizenProfile(age=18),
        evaluated_at=EVALUATED_AT,
    )

    serialized = result.model_dump(mode="json")
    assert serialized["outcome"] == EligibilityOutcome.ELIGIBLE.value
    assert serialized["engine_version"] == ENGINE_VERSION
    assert (
        serialized["evaluated_at"].endswith("Z")
        or "+00:00" in serialized["evaluated_at"]
    )
    assert serialized["rule_evaluations"][0]["outcome"] == RuleOutcome.PASS.value
    assert serialized["rule_evaluations"][0]["provenance"]["page_number"] == 1
