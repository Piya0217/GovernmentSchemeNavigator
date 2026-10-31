"""Structural and activation validation for eligibility rule definitions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, StrictBool

from src.rules.models import (
    EligibilityRule,
    EligibilityRuleSet,
    RuleApprovalEvidence,
    RuleStatus,
)

RULE_SCHEMA_VERSION = "1.0.0"


class RuleValidationCode(StrEnum):
    """Stable machine-readable rule validation issue identifiers."""

    EMPTY_RULE_SET = "empty_rule_set"
    UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
    DUPLICATE_RULE_ID = "duplicate_rule_id"
    SCHEME_PROVENANCE_MISMATCH = "scheme_provenance_mismatch"
    APPROVAL_DOCUMENT_ID_MISMATCH = "approval_document_id_mismatch"
    APPROVAL_DOCUMENT_VERSION_MISMATCH = "approval_document_version_mismatch"
    APPROVAL_RULE_VERSION_MISMATCH = "approval_rule_version_mismatch"
    LIFECYCLE_NOT_ACTIVATABLE = "lifecycle_not_activatable"
    APPROVAL_EVIDENCE_MISSING = "approval_evidence_missing"
    APPROVAL_REVIEWER_MISSING = "approval_reviewer_missing"
    APPROVAL_TIMESTAMP_INVALID = "approval_timestamp_invalid"


class RuleValidationIssue(BaseModel):
    """One deterministic, structured rule validation issue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: RuleValidationCode
    message: str
    rule_id: str | None = None


class RuleSetValidationResult(BaseModel):
    """Structural validation result for a complete eligibility rule set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_valid: StrictBool
    issues: tuple[RuleValidationIssue, ...]


class RuleActivationValidationResult(BaseModel):
    """Whether a rule can be activated or safely treated as active."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ready_for_activation: StrictBool
    issues: tuple[RuleValidationIssue, ...]


def validate_rule_set(rule_set: EligibilityRuleSet) -> RuleSetValidationResult:
    """Validate collection-level integrity without inferring eligibility.

    The result covers structural consistency only. Activation readiness is
    checked separately by :func:`validate_rule_activation`.
    """
    issues: list[RuleValidationIssue] = []
    if rule_set.schema_version != RULE_SCHEMA_VERSION:
        issues.append(
            RuleValidationIssue(
                code=RuleValidationCode.UNSUPPORTED_SCHEMA_VERSION,
                message=(
                    f"Schema version '{rule_set.schema_version}' is not supported; "
                    f"expected '{RULE_SCHEMA_VERSION}'."
                ),
            )
        )
    if not rule_set.rules:
        issues.append(
            RuleValidationIssue(
                code=RuleValidationCode.EMPTY_RULE_SET,
                message="A rule set must contain at least one rule.",
            )
        )
    issues.extend(_duplicate_rule_id_issues(rule_set))
    issues.extend(_rule_consistency_issues(rule_set))
    ordered_issues = tuple(sorted(issues, key=_issue_sort_key))
    return RuleSetValidationResult(
        is_valid=not ordered_issues,
        issues=ordered_issues,
    )


def validate_rule_activation(rule: EligibilityRule) -> RuleActivationValidationResult:
    """Check lifecycle and matching review evidence for activation readiness.

    Review evidence is metadata from a trusted workflow; this function does
    not authenticate the reviewer or make a government eligibility decision.
    """
    issues: list[RuleValidationIssue] = []
    if rule.status not in {RuleStatus.REVIEWED, RuleStatus.ACTIVE}:
        issues.append(
            _issue(
                RuleValidationCode.LIFECYCLE_NOT_ACTIVATABLE,
                "Only REVIEWED or ACTIVE rules can be activation-ready.",
                rule.rule_id,
            )
        )

    evidence = rule.approval_evidence
    if evidence is None:
        issues.append(
            _issue(
                RuleValidationCode.APPROVAL_EVIDENCE_MISSING,
                "Approval evidence is required for activation readiness.",
                rule.rule_id,
            )
        )
    else:
        issues.extend(_approval_evidence_issues(rule, evidence))
        issues.extend(_reviewer_and_timestamp_issues(rule, evidence))

    ordered_issues = tuple(sorted(issues, key=_issue_sort_key))
    return RuleActivationValidationResult(
        ready_for_activation=not ordered_issues,
        issues=ordered_issues,
    )


def _duplicate_rule_id_issues(
    rule_set: EligibilityRuleSet,
) -> list[RuleValidationIssue]:
    """Return one issue for each duplicated rule identifier."""
    counts: dict[str, int] = {}
    for rule in rule_set.rules:
        counts[rule.rule_id] = counts.get(rule.rule_id, 0) + 1
    return [
        _issue(
            RuleValidationCode.DUPLICATE_RULE_ID,
            f"Rule ID '{rule_id}' appears more than once.",
            rule_id,
        )
        for rule_id, count in sorted(counts.items())
        if count > 1
    ]


def _rule_consistency_issues(
    rule_set: EligibilityRuleSet,
) -> list[RuleValidationIssue]:
    """Check scheme provenance and any attached approval references."""
    issues: list[RuleValidationIssue] = []
    for rule in sorted(rule_set.rules, key=lambda item: item.rule_id):
        if rule.provenance.scheme_id != rule_set.scheme_id:
            issues.append(
                _issue(
                    RuleValidationCode.SCHEME_PROVENANCE_MISMATCH,
                    "Rule provenance scheme_id must match the rule set.",
                    rule.rule_id,
                )
            )
        if rule.approval_evidence is not None:
            issues.extend(_approval_evidence_issues(rule, rule.approval_evidence))
    return issues


def _approval_evidence_issues(
    rule: EligibilityRule,
    evidence: RuleApprovalEvidence,
) -> list[RuleValidationIssue]:
    """Compare approval metadata with the exact source and rule version."""
    issues: list[RuleValidationIssue] = []
    expected = (
        (
            evidence.document_id,
            rule.provenance.document_id,
            RuleValidationCode.APPROVAL_DOCUMENT_ID_MISMATCH,
            "Approval document ID must match rule provenance.",
        ),
        (
            evidence.document_version,
            rule.provenance.document_version,
            RuleValidationCode.APPROVAL_DOCUMENT_VERSION_MISMATCH,
            "Approval document version must match rule provenance.",
        ),
        (
            evidence.rule_version,
            rule.rule_version,
            RuleValidationCode.APPROVAL_RULE_VERSION_MISMATCH,
            "Approval rule version must match the current rule version.",
        ),
    )
    for actual, required, code, message in expected:
        if actual != required:
            issues.append(_issue(code, message, rule.rule_id))
    return issues


def _reviewer_and_timestamp_issues(
    rule: EligibilityRule,
    evidence: RuleApprovalEvidence,
) -> list[RuleValidationIssue]:
    """Defensively verify required review identity and timezone information."""
    issues: list[RuleValidationIssue] = []
    if not evidence.reviewer_id.strip():
        issues.append(
            _issue(
                RuleValidationCode.APPROVAL_REVIEWER_MISSING,
                "Approval evidence must identify a reviewer.",
                rule.rule_id,
            )
        )
    reviewed_at = evidence.reviewed_at
    if (
        not isinstance(reviewed_at, datetime)
        or reviewed_at.tzinfo is None
        or reviewed_at.utcoffset() is None
    ):
        issues.append(
            _issue(
                RuleValidationCode.APPROVAL_TIMESTAMP_INVALID,
                "Review timestamp must be timezone-aware.",
                rule.rule_id,
            )
        )
    return issues


def _issue(
    code: RuleValidationCode,
    message: str,
    rule_id: str | None = None,
) -> RuleValidationIssue:
    """Construct a typed issue consistently."""
    return RuleValidationIssue(code=code, message=message, rule_id=rule_id)


def _issue_sort_key(
    issue: RuleValidationIssue,
) -> tuple[str, str, str]:
    """Return a stable ordering independent of rule-set input order."""
    return issue.code.value, issue.rule_id or "", issue.message


__all__ = [
    "RULE_SCHEMA_VERSION",
    "RuleActivationValidationResult",
    "RuleSetValidationResult",
    "RuleValidationCode",
    "RuleValidationIssue",
    "validate_rule_activation",
    "validate_rule_set",
]
