"""Tests for rule-set and activation validation with synthetic rules."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from src.rules.models import (
    EligibilityRule,
    EligibilityRuleSet,
    RuleApprovalEvidence,
    RuleOperator,
    RuleProvenance,
    RuleStatus,
)
from src.rules.validation import (
    RULE_SCHEMA_VERSION,
    RuleValidationCode,
    validate_rule_activation,
    validate_rule_set,
)


def make_provenance(**overrides: object) -> RuleProvenance:
    """Build synthetic provenance for validation tests."""
    values: dict[str, object] = {
        "scheme_id": "synthetic_scheme",
        "document_id": "synthetic-guidelines.pdf",
        "source_url": "https://example.gov.in/synthetic-guidelines.pdf",
        "document_version": "synthetic-v1",
        "page_number": 2,
    }
    values.update(overrides)
    return RuleProvenance(**values)


def make_approval(**overrides: object) -> RuleApprovalEvidence:
    """Build synthetic human-review evidence."""
    values: dict[str, object] = {
        "reviewer_id": "reviewer-123",
        "reviewed_at": datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
        "document_id": "synthetic-guidelines.pdf",
        "document_version": "synthetic-v1",
        "rule_version": "1.0.0",
        "approval_reference": "review-record-456",
    }
    values.update(overrides)
    return RuleApprovalEvidence(**values)


def make_rule(**overrides: object) -> EligibilityRule:
    """Build a synthetic eligibility rule."""
    values: dict[str, object] = {
        "rule_id": "synthetic-age-rule",
        "field": "age",
        "operator": RuleOperator.GTE,
        "value": 18,
        "status": RuleStatus.PENDING,
        "mandatory": True,
        "provenance": make_provenance(),
        "rule_version": "1.0.0",
    }
    values.update(overrides)
    return EligibilityRule(**values)


def make_rule_set(*rules: EligibilityRule, **overrides: object) -> EligibilityRuleSet:
    """Build a synthetic rule set."""
    values: dict[str, object] = {
        "scheme_id": "synthetic_scheme",
        "schema_version": RULE_SCHEMA_VERSION,
        "rules": rules,
    }
    values.update(overrides)
    return EligibilityRuleSet(**values)


def test_validate_rule_set_accepts_valid_synthetic_rules() -> None:
    result = validate_rule_set(make_rule_set(make_rule()))

    assert result.is_valid
    assert result.issues == ()


def test_validate_rule_set_reports_empty_rule_collection() -> None:
    result = validate_rule_set(make_rule_set())

    assert not result.is_valid
    assert result.issues[0].code is RuleValidationCode.EMPTY_RULE_SET


def test_validate_rule_set_reports_duplicate_rule_ids() -> None:
    result = validate_rule_set(
        make_rule_set(make_rule(), make_rule(rule_version="2.0.0"))
    )

    assert [issue.code for issue in result.issues] == [
        RuleValidationCode.DUPLICATE_RULE_ID
    ]
    assert result.issues[0].rule_id == "synthetic-age-rule"


def test_validate_rule_set_reports_mixed_scheme_provenance() -> None:
    other_scheme_rule = make_rule(
        rule_id="other-scheme-rule",
        provenance=make_provenance(scheme_id="another_synthetic_scheme"),
    )

    result = validate_rule_set(make_rule_set(make_rule(), other_scheme_rule))

    assert not result.is_valid
    assert result.issues[0].code is RuleValidationCode.SCHEME_PROVENANCE_MISMATCH
    assert result.issues[0].rule_id == "other-scheme-rule"


def test_validate_rule_set_rejects_unsupported_schema_version() -> None:
    result = validate_rule_set(make_rule_set(make_rule(), schema_version="99.0.0"))

    assert not result.is_valid
    assert result.issues[0].code is RuleValidationCode.UNSUPPORTED_SCHEMA_VERSION


def test_validate_rule_set_reports_attached_approval_mismatches() -> None:
    rule = make_rule(
        status=RuleStatus.REVIEWED,
        approval_evidence=make_approval(document_version="synthetic-v0"),
    )

    result = validate_rule_set(make_rule_set(rule))

    assert not result.is_valid
    assert (
        result.issues[0].code is RuleValidationCode.APPROVAL_DOCUMENT_VERSION_MISMATCH
    )


def test_rule_set_collection_is_immutable_and_json_serializable() -> None:
    source_rules = [make_rule()]
    rule_set = EligibilityRuleSet(
        scheme_id="synthetic_scheme",
        schema_version=RULE_SCHEMA_VERSION,
        rules=source_rules,
    )

    source_rules.clear()
    assert len(rule_set.rules) == 1
    with pytest.raises(TypeError):
        rule_set.rules[0] = make_rule()

    serialized = rule_set.model_dump(mode="json")
    assert isinstance(serialized["rules"], list)
    assert serialized["schema_version"] == RULE_SCHEMA_VERSION


@pytest.mark.parametrize(
    "status,has_evidence,expected_ready",
    [
        (RuleStatus.PENDING, True, False),
        (RuleStatus.REVIEWED, True, True),
        (RuleStatus.ACTIVE, True, True),
        (RuleStatus.RETIRED, True, False),
    ],
)
def test_activation_lifecycle_statuses(
    status: RuleStatus,
    has_evidence: bool,
    expected_ready: bool,
) -> None:
    rule = make_rule(
        status=status,
        approval_evidence=make_approval() if has_evidence else None,
    )

    result = validate_rule_activation(rule)

    assert result.ready_for_activation is expected_ready
    assert (not result.issues) is expected_ready


def test_active_status_without_approval_is_not_activation_ready() -> None:
    active_rule = make_rule(status=RuleStatus.ACTIVE, approval_evidence=None)
    structural_result = validate_rule_set(make_rule_set(active_rule))
    activation_result = validate_rule_activation(active_rule)

    assert structural_result.is_valid
    assert not activation_result.ready_for_activation
    assert RuleValidationCode.APPROVAL_EVIDENCE_MISSING in {
        issue.code for issue in activation_result.issues
    }


def test_reviewed_status_without_approval_is_not_activation_ready() -> None:
    result = validate_rule_activation(make_rule(status=RuleStatus.REVIEWED))

    assert not result.ready_for_activation
    assert result.issues[0].code is RuleValidationCode.APPROVAL_EVIDENCE_MISSING


@pytest.mark.parametrize(
    "missing_field",
    [
        "reviewer_id",
        "reviewed_at",
        "document_id",
        "document_version",
        "rule_version",
        "approval_reference",
    ],
)
def test_approval_evidence_rejects_missing_required_fields(missing_field: str) -> None:
    values: dict[str, object] = {
        "reviewer_id": "reviewer-123",
        "reviewed_at": datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
        "document_id": "synthetic-guidelines.pdf",
        "document_version": "synthetic-v1",
        "rule_version": "1.0.0",
        "approval_reference": "review-record-456",
    }
    del values[missing_field]

    with pytest.raises(ValidationError):
        RuleApprovalEvidence(**values)


def test_approval_evidence_rejects_naive_review_timestamp() -> None:
    with pytest.raises(ValidationError):
        make_approval(reviewed_at=datetime(2026, 1, 15, 10, 30))


@pytest.mark.parametrize(
    "field,value,expected_code",
    [
        (
            "document_id",
            "different-guidelines.pdf",
            RuleValidationCode.APPROVAL_DOCUMENT_ID_MISMATCH,
        ),
        (
            "document_version",
            "synthetic-v2",
            RuleValidationCode.APPROVAL_DOCUMENT_VERSION_MISMATCH,
        ),
        (
            "rule_version",
            "2.0.0",
            RuleValidationCode.APPROVAL_RULE_VERSION_MISMATCH,
        ),
    ],
)
def test_activation_rejects_approval_version_or_document_mismatch(
    field: str,
    value: str,
    expected_code: RuleValidationCode,
) -> None:
    rule = make_rule(
        status=RuleStatus.REVIEWED,
        approval_evidence=make_approval(**{field: value}),
    )

    result = validate_rule_activation(rule)

    assert not result.ready_for_activation
    assert expected_code in {issue.code for issue in result.issues}


def test_validation_issue_order_is_independent_of_rule_input_order() -> None:
    first = make_rule(
        rule_id="duplicate-rule",
        provenance=make_provenance(scheme_id="other_scheme"),
    )
    second = make_rule(rule_id="duplicate-rule", rule_version="2.0.0")
    third = make_rule(
        rule_id="another-rule",
        provenance=make_provenance(scheme_id="other_scheme"),
    )

    forward = validate_rule_set(make_rule_set(first, second, third))
    reverse = validate_rule_set(make_rule_set(third, second, first))

    assert forward.issues == reverse.issues
