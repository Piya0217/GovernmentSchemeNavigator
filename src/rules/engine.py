"""Orchestration layer for validated deterministic eligibility evaluation."""

from __future__ import annotations

from datetime import UTC, datetime

from src.rules.evaluation import ENGINE_VERSION, evaluate_rule_set
from src.rules.models import (
    CitizenProfile,
    EligibilityOutcome,
    EligibilityResult,
    EligibilityRuleSet,
    RuleEvaluation,
    RuleOutcome,
)
from src.rules.validation import validate_rule_set


def evaluate_eligibility(
    profile: CitizenProfile,
    rule_set: EligibilityRuleSet,
    *,
    evaluated_at: datetime | None = None,
    engine_version: str = ENGINE_VERSION,
) -> EligibilityResult:
    """Validate and evaluate a scheme rule set for one citizen profile.

    Rule comparisons, activation checks, and mandatory outcome aggregation
    remain delegated to the existing validator and evaluator.
    """
    timestamp = evaluated_at if evaluated_at is not None else datetime.now(UTC)
    validation = validate_rule_set(rule_set)
    if not validation.is_valid:
        return _structural_failure_result(
            rule_set=rule_set,
            evaluated_at=timestamp,
            engine_version=engine_version,
            issue_codes=tuple(issue.code.value for issue in validation.issues),
        )
    return evaluate_rule_set(
        rule_set,
        profile,
        evaluated_at=timestamp,
        engine_version=engine_version,
    )


def _structural_failure_result(
    *,
    rule_set: EligibilityRuleSet,
    evaluated_at: datetime,
    engine_version: str,
    issue_codes: tuple[str, ...],
) -> EligibilityResult:
    """Return a non-positive result without evaluating invalid rules."""
    ordered_rules = sorted(rule_set.rules, key=lambda rule: rule.rule_id)
    evaluations = tuple(
        RuleEvaluation(
            rule_id=rule.rule_id,
            outcome=RuleOutcome.UNEVALUABLE,
            reason="Rule set failed structural validation; rule was not evaluated.",
            provenance=rule.provenance,
        )
        for rule in ordered_rules
    )
    codes = ", ".join(issue_codes)
    rules_summary = (
        ", ".join(
            f"{evaluation.rule_id}={evaluation.outcome.value}"
            for evaluation in evaluations
        )
        or "none"
    )
    explanation = (
        "Outcome: NEEDS_MORE_INFORMATION. Structural rule-set validation failed "
        f"({codes}). Rule outcomes: {rules_summary}."
    )
    return EligibilityResult(
        scheme_id=rule_set.scheme_id,
        outcome=EligibilityOutcome.NEEDS_MORE_INFORMATION,
        rule_evaluations=evaluations,
        explanation=explanation,
        evaluated_at=evaluated_at,
        engine_version=engine_version,
    )


__all__ = ["evaluate_eligibility"]
