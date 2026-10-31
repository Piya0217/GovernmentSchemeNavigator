"""Tests for the eligibility-engine orchestration API."""

from datetime import UTC, datetime

import pytest
import src.rules.engine as engine_module
from src.rules.engine import evaluate_eligibility
from src.rules.evaluation import ENGINE_VERSION, evaluate_rule_set
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

EVALUATED_AT = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)


def make_provenance(**overrides: object) -> RuleProvenance:
    """Build provenance for a synthetic scheme document."""
    values: dict[str, object] = {
        "scheme_id": "synthetic_scheme",
        "document_id": "synthetic-guidelines.pdf",
        "source_url": "https://example.gov.in/synthetic-guidelines.pdf",
        "document_version": "synthetic-v1",
        "page_number": 1,
    }
    values.update(overrides)
    return RuleProvenance(**values)


def make_approval(**overrides: object) -> RuleApprovalEvidence:
    """Build matching synthetic approval metadata."""
    values: dict[str, object] = {
        "reviewer_id": "synthetic-reviewer",
        "reviewed_at": EVALUATED_AT,
        "document_id": "synthetic-guidelines.pdf",
        "document_version": "synthetic-v1",
        "rule_version": "1.0.0",
        "approval_reference": "synthetic-review-record",
    }
    values.update(overrides)
    return RuleApprovalEvidence(**values)


def make_rule(**overrides: object) -> EligibilityRule:
    """Build a synthetic ACTIVE rule with matching approval evidence."""
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
    """Build a rule set using synthetic rules."""
    return EligibilityRuleSet(
        scheme_id="synthetic_scheme",
        schema_version=RULE_SCHEMA_VERSION,
        rules=rules,
    )


def run_engine(
    rule_set: EligibilityRuleSet,
    profile: CitizenProfile,
    **kwargs: object,
):
    """Run the engine with a fixed timestamp by default."""
    return evaluate_eligibility(
        profile,
        rule_set,
        evaluated_at=EVALUATED_AT,
        **kwargs,
    )


def test_valid_profile_and_rule_set_produce_eligible_result() -> None:
    result = run_engine(make_rule_set(make_rule()), CitizenProfile(age=18))

    assert result.outcome is EligibilityOutcome.ELIGIBLE
    assert result.rule_evaluations[0].outcome is RuleOutcome.PASS


def test_mandatory_failure_produces_ineligible_result() -> None:
    result = run_engine(make_rule_set(make_rule(value=19)), CitizenProfile(age=18))

    assert result.outcome is EligibilityOutcome.INELIGIBLE


def test_missing_mandatory_data_needs_more_information() -> None:
    result = run_engine(make_rule_set(make_rule()), CitizenProfile())

    assert result.outcome is EligibilityOutcome.NEEDS_MORE_INFORMATION
    assert result.rule_evaluations[0].outcome is RuleOutcome.UNEVALUABLE
    assert "age" in result.explanation


def test_empty_rule_set_fails_closed_without_rule_evaluations() -> None:
    result = run_engine(make_rule_set(), CitizenProfile())

    assert result.outcome is EligibilityOutcome.NEEDS_MORE_INFORMATION
    assert result.rule_evaluations == ()
    assert "empty_rule_set" in result.explanation


@pytest.mark.parametrize(
    "rules",
    [
        lambda: (make_rule(), make_rule()),
        lambda: (
            make_rule(provenance=make_provenance(scheme_id="another_synthetic_scheme")),
        ),
    ],
    ids=["duplicate-rule-ids", "mixed-scheme-provenance"],
)
def test_invalid_rule_sets_fail_closed(rules) -> None:
    result = run_engine(make_rule_set(*rules()), CitizenProfile(age=100))

    assert result.outcome is EligibilityOutcome.NEEDS_MORE_INFORMATION
    assert all(
        evaluation.outcome is RuleOutcome.UNEVALUABLE
        for evaluation in result.rule_evaluations
    )
    assert "Structural rule-set validation failed" in result.explanation


@pytest.mark.parametrize(
    "status", [RuleStatus.PENDING, RuleStatus.REVIEWED, RuleStatus.RETIRED]
)
def test_inactive_rules_never_pass(status: RuleStatus) -> None:
    result = run_engine(
        make_rule_set(make_rule(status=status)),
        CitizenProfile(age=100),
    )

    assert result.outcome is EligibilityOutcome.NEEDS_MORE_INFORMATION
    assert result.rule_evaluations[0].outcome is RuleOutcome.UNEVALUABLE


def test_active_rule_without_approval_never_passes() -> None:
    result = run_engine(
        make_rule_set(make_rule(approval_evidence=None)),
        CitizenProfile(age=100),
    )

    assert result.outcome is EligibilityOutcome.NEEDS_MORE_INFORMATION
    assert result.rule_evaluations[0].outcome is RuleOutcome.UNEVALUABLE
    assert "Approval evidence is required" in result.rule_evaluations[0].reason


@pytest.mark.parametrize(
    "approval_update",
    [
        {"document_id": "different.pdf"},
        {"document_version": "synthetic-v2"},
        {"rule_version": "2.0.0"},
    ],
    ids=["document-id", "document-version", "rule-version"],
)
def test_approval_mismatches_fail_structural_validation(
    approval_update: dict[str, str],
) -> None:
    rule = make_rule(approval_evidence=make_approval(**approval_update))

    result = run_engine(make_rule_set(rule), CitizenProfile(age=100))

    assert result.outcome is EligibilityOutcome.NEEDS_MORE_INFORMATION
    assert result.rule_evaluations[0].outcome is RuleOutcome.UNEVALUABLE
    assert "Structural rule-set validation failed" in result.explanation


def test_timestamp_and_engine_version_are_propagated() -> None:
    result = run_engine(
        make_rule_set(make_rule()),
        CitizenProfile(age=18),
        engine_version="test-engine-2.0",
    )

    assert result.evaluated_at == EVALUATED_AT
    assert result.evaluated_at.utcoffset() is not None
    assert result.engine_version == "test-engine-2.0"


def test_explanations_are_stable_across_rule_input_order() -> None:
    first = make_rule(rule_id="rule-b", value=19)
    second = make_rule(rule_id="rule-a", value=20)
    profile = CitizenProfile(age=18)

    forward = run_engine(make_rule_set(first, second), profile)
    reverse = run_engine(make_rule_set(second, first), profile)

    assert forward.explanation == reverse.explanation
    assert "rule-a=FAIL" in forward.explanation
    assert "rule-b=FAIL" in forward.explanation


def test_engine_delegates_comparisons_to_existing_evaluator(monkeypatch) -> None:
    calls: list[tuple[EligibilityRuleSet, CitizenProfile]] = []

    def evaluator_spy(
        rule_set: EligibilityRuleSet,
        profile: CitizenProfile,
        *,
        evaluated_at: datetime,
        engine_version: str,
    ):
        calls.append((rule_set, profile))
        return evaluate_rule_set(
            rule_set,
            profile,
            evaluated_at=evaluated_at,
            engine_version=engine_version,
        )

    monkeypatch.setattr(engine_module, "evaluate_rule_set", evaluator_spy)
    rule_set = make_rule_set(make_rule())
    profile = CitizenProfile(age=18)

    result = run_engine(rule_set, profile)

    assert calls == [(rule_set, profile)]
    assert result.outcome is EligibilityOutcome.ELIGIBLE


def test_result_serialization_includes_provenance_and_engine_metadata() -> None:
    result = run_engine(make_rule_set(make_rule()), CitizenProfile(age=18))

    serialized = result.model_dump(mode="json")
    assert serialized["outcome"] == EligibilityOutcome.ELIGIBLE.value
    assert serialized["engine_version"] == ENGINE_VERSION
    assert (
        serialized["evaluated_at"].endswith("Z")
        or "+00:00" in serialized["evaluated_at"]
    )
    assert serialized["rule_evaluations"][0]["provenance"]["document_id"] == (
        "synthetic-guidelines.pdf"
    )
