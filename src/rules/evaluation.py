"""Deterministic evaluation of approved eligibility rules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypeAlias

from src.rules.models import (
    CitizenProfile,
    EligibilityOutcome,
    EligibilityResult,
    EligibilityRule,
    EligibilityRuleSet,
    RuleEvaluation,
    RuleOperator,
    RuleOutcome,
    RuleStatus,
)
from src.rules.validation import validate_rule_activation, validate_rule_set

ENGINE_VERSION = "0.1.0"
Scalar: TypeAlias = str | int | float | bool


def evaluate_rule(rule: EligibilityRule, profile: CitizenProfile) -> RuleEvaluation:
    """Evaluate one ACTIVE, approval-validated rule against a profile."""
    if rule.status is not RuleStatus.ACTIVE:
        return _unevaluable(
            rule, f"Rule status is {rule.status.value}; it is not ACTIVE."
        )

    activation = validate_rule_activation(rule)
    if not activation.ready_for_activation:
        reasons = "; ".join(issue.message for issue in activation.issues)
        return _unevaluable(rule, f"Activation validation failed: {reasons}")

    observed = getattr(profile, rule.field)
    if observed is None:
        return _unevaluable(rule, f"Missing profile field '{rule.field}'.")
    if not _profile_value_is_valid(observed, rule.field):
        return _unevaluable(rule, f"Profile field '{rule.field}' has an invalid type.")

    comparison = _compare_rule_value(rule, observed)
    if comparison is None:
        return _unevaluable(rule, f"Rule value is incompatible with '{rule.field}'.")
    outcome = RuleOutcome.PASS if comparison else RuleOutcome.FAIL
    reason = f"Comparison for profile field '{rule.field}' returned {outcome.value}."
    return RuleEvaluation(
        rule_id=rule.rule_id,
        outcome=outcome,
        reason=reason,
        provenance=rule.provenance,
    )


def evaluate_rule_set(
    rule_set: EligibilityRuleSet,
    profile: CitizenProfile,
    *,
    evaluated_at: datetime | None = None,
    engine_version: str = ENGINE_VERSION,
) -> EligibilityResult:
    """Evaluate a validated rule set and aggregate mandatory outcomes.

    Optional rules are evaluated and reported, but never change the outcome
    derived from mandatory rules. Invalid or empty rule sets fail closed.
    """
    structural = validate_rule_set(rule_set)
    ordered_rules = tuple(sorted(rule_set.rules, key=lambda rule: rule.rule_id))
    if structural.is_valid:
        evaluations = tuple(evaluate_rule(rule, profile) for rule in ordered_rules)
        outcome = _aggregate_mandatory_outcomes(ordered_rules, evaluations)
    else:
        reason = "Rule set validation failed: " + ", ".join(
            issue.code.value for issue in structural.issues
        )
        evaluations = tuple(_unevaluable(rule, reason) for rule in ordered_rules)
        outcome = EligibilityOutcome.NEEDS_MORE_INFORMATION

    explanation = _build_explanation(ordered_rules, evaluations, outcome)
    if not structural.is_valid:
        issue_codes = ", ".join(issue.code.value for issue in structural.issues)
        explanation = f"Rule set validation failed ({issue_codes}). {explanation}"
    return EligibilityResult(
        scheme_id=rule_set.scheme_id,
        outcome=outcome,
        rule_evaluations=evaluations,
        explanation=explanation,
        evaluated_at=evaluated_at or datetime.now(UTC),
        engine_version=engine_version,
    )


def _compare_rule_value(rule: EligibilityRule, observed: Scalar) -> bool | None:
    """Apply one supported operator without coercing profile values."""
    expected_values = rule.value if isinstance(rule.value, tuple) else (rule.value,)
    if any(not _value_matches_field(value, rule.field) for value in expected_values):
        return None
    if any(not _values_are_comparable(observed, value) for value in expected_values):
        return None

    expected = expected_values[0]
    match rule.operator:
        case RuleOperator.EQ:
            return observed == expected
        case RuleOperator.NE:
            return observed != expected
        case RuleOperator.GT:
            return observed > expected
        case RuleOperator.GTE:
            return observed >= expected
        case RuleOperator.LT:
            return observed < expected
        case RuleOperator.LTE:
            return observed <= expected
        case RuleOperator.IN:
            return observed in expected_values
        case RuleOperator.NOT_IN:
            return observed not in expected_values
    return None


def _profile_value_is_valid(value: object, field: str) -> bool:
    """Defend against values introduced by bypassing profile validation."""
    return _value_matches_field(value, field)


def _value_matches_field(value: object, field: str) -> bool:
    """Check the runtime type for a supported citizen profile field."""
    if field in {"age", "household_size"}:
        return isinstance(value, int) and not isinstance(value, bool)
    if field == "annual_income":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, str)


def _values_are_comparable(left: object, right: object) -> bool:
    """Permit same-domain strings or non-boolean numeric comparisons only."""
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return True
    return isinstance(left, str) and isinstance(right, str)


def _aggregate_mandatory_outcomes(
    rules: tuple[EligibilityRule, ...],
    evaluations: tuple[RuleEvaluation, ...],
) -> EligibilityOutcome:
    """Apply the mandatory fail, unknown, then pass precedence."""
    mandatory_ids = {rule.rule_id for rule in rules if rule.mandatory}
    mandatory_outcomes = [
        evaluation.outcome
        for evaluation in evaluations
        if evaluation.rule_id in mandatory_ids
    ]
    if RuleOutcome.FAIL in mandatory_outcomes:
        return EligibilityOutcome.INELIGIBLE
    if RuleOutcome.UNEVALUABLE in mandatory_outcomes or not mandatory_outcomes:
        return EligibilityOutcome.NEEDS_MORE_INFORMATION
    return EligibilityOutcome.ELIGIBLE


def _build_explanation(
    rules: tuple[EligibilityRule, ...],
    evaluations: tuple[RuleEvaluation, ...],
    outcome: EligibilityOutcome,
) -> str:
    """Build a stable, evidence-neutral summary of rule outcomes."""
    mandatory_ids = {rule.rule_id for rule in rules if rule.mandatory}
    mandatory = _format_outcomes(evaluations, mandatory_ids)
    optional = _format_optional(evaluations, mandatory_ids)
    missing = _missing_fields(rules, evaluations)
    explanation = (
        f"Outcome: {outcome.value}. Mandatory rules: {mandatory}. "
        f"Optional rules (informational only): {optional}."
    )
    if missing:
        explanation += f" Missing profile fields: {', '.join(missing)}."
    if not mandatory_ids:
        explanation += " No mandatory rules were available to determine the outcome."
    return explanation


def _format_outcomes(
    evaluations: tuple[RuleEvaluation, ...],
    rule_ids: set[str],
) -> str:
    """Format a selected group of outcomes in stable rule-ID order."""
    selected = [
        f"{evaluation.rule_id}={evaluation.outcome.value}"
        for evaluation in evaluations
        if evaluation.rule_id in rule_ids
    ]
    return ", ".join(selected) if selected else "none"


def _format_optional(
    evaluations: tuple[RuleEvaluation, ...],
    mandatory_ids: set[str],
) -> str:
    """Format non-mandatory outcomes without affecting aggregation."""
    selected = [
        f"{evaluation.rule_id}={evaluation.outcome.value}"
        for evaluation in evaluations
        if evaluation.rule_id not in mandatory_ids
    ]
    return ", ".join(selected) if selected else "none"


def _missing_fields(
    rules: tuple[EligibilityRule, ...],
    evaluations: tuple[RuleEvaluation, ...],
) -> list[str]:
    """Return fields specifically missing from the supplied profile."""
    fields_by_rule = {rule.rule_id: rule.field for rule in rules}
    return sorted(
        {
            fields_by_rule[evaluation.rule_id]
            for evaluation in evaluations
            if evaluation.outcome is RuleOutcome.UNEVALUABLE
            and evaluation.reason.startswith("Missing profile field '")
        }
    )


def _unevaluable(rule: EligibilityRule, reason: str) -> RuleEvaluation:
    """Create an UNEVALUABLE result while preserving source provenance."""
    return RuleEvaluation(
        rule_id=rule.rule_id,
        outcome=RuleOutcome.UNEVALUABLE,
        reason=reason,
        provenance=rule.provenance,
    )


__all__ = [
    "ENGINE_VERSION",
    "evaluate_rule",
    "evaluate_rule_set",
]
