"""API integration tests that exercise the actual Phase 3 rules engine."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from src.agent.orchestrator import WorkflowOrchestrator
from src.api.eligibility_service import EligibilityService
from src.api.main import create_app
from src.api.services import ApiServices, SchemeRegistryService
from src.catalogue.schemas import (
    ContentReviewStatus,
    EvidenceCatalogue,
    EvidenceRecord,
    RuleEvidenceLink,
    RuleEvidenceSidecar,
    SchemeRegistry,
    SchemeRegistryEntry,
    SourceDocument,
    SourceIdentityStatus,
)
from src.rules.models import (
    EligibilityRule,
    EligibilityRuleSet,
    RuleApprovalEvidence,
    RuleOperator,
    RuleProvenance,
    RuleStatus,
)
from src.rules.validation import RULE_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "data" / "scheme_registry.json"
SCHEME_ID = "central_pm_kisan"
REVIEWED_AT = datetime(2026, 10, 1, tzinfo=UTC)
DOCUMENT_ID = "central_pm_kisan_guidelines_2020"
EVIDENCE_ID = "synthetic_test_evidence"
SOURCE_URL = (
    "https://pmkisan.gov.in/Documents/RevisedPM-KISANOperationalGuidelines(English).pdf"
)
DOCUMENT_VERSION = "2020-03-29"
TEST_SOURCE_EXCERPT = (
    "iv) All superannuated / retired pensioners whose monthly pension is "
    "Rs.10,000/- or \n"
    "more (Excluding Multi Tasking Staff / Class IV / Group D employees)"
)
EXCERPT_HASH = sha256(TEST_SOURCE_EXCERPT.encode("utf-8")).hexdigest()


def _rule_set(status: RuleStatus = RuleStatus.ACTIVE) -> EligibilityRuleSet:
    """Create synthetic test-only criteria; no production scheme rule is asserted."""
    provenance = RuleProvenance(
        scheme_id=SCHEME_ID,
        document_id=DOCUMENT_ID,
        source_url=SOURCE_URL,
        document_version=DOCUMENT_VERSION,
        page_number=3,
        excerpt_hash=EXCERPT_HASH,
    )
    approval = (
        RuleApprovalEvidence(
            reviewer_id="synthetic-test-reviewer",
            reviewed_at=REVIEWED_AT,
            document_id=provenance.document_id,
            document_version=provenance.document_version,
            rule_version="test-v1",
            approval_reference="test-only",
        )
        if status is RuleStatus.ACTIVE
        else None
    )
    rule = EligibilityRule(
        rule_id="synthetic_test_age_rule",
        field="age",
        operator=RuleOperator.GTE,
        value=18,
        status=status,
        mandatory=True,
        provenance=provenance,
        rule_version="test-v1",
        approval_evidence=approval,
    )
    return EligibilityRuleSet(
        scheme_id=SCHEME_ID,
        schema_version=RULE_SCHEMA_VERSION,
        rules=(rule,),
    )


@pytest.fixture
def client(tmp_path: Path):
    """Build API services with a temporary synthetic rule-set directory."""
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    catalogue_dir = tmp_path / "catalogue"
    catalogue_dir.mkdir()
    _write_catalogue(catalogue_dir, _rule_set())
    services = ApiServices(
        workflow=WorkflowOrchestrator(retrieval=None),
        scheme_registry=SchemeRegistryService(REGISTRY),
        retrieval_status="unavailable",
        eligibility=EligibilityService(
            rules_dir,
            registry_path=catalogue_dir / "scheme_registry.json",
            evidence_path=catalogue_dir / "evidence_catalogue.json",
            sidecar_path=catalogue_dir / "rule_evidence_links.json",
        ),
        eligibility_status="ready",
    )
    with TestClient(create_app(services=services)) as test_client:
        yield test_client, rules_dir, catalogue_dir


def _write_rules(rules_dir: Path, status: RuleStatus = RuleStatus.ACTIVE) -> None:
    """Write a synthetic-only test rule set in the Phase 3 JSON schema."""
    payload = _rule_set(status).model_dump(mode="json")
    (rules_dir / f"{SCHEME_ID}.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_rule_set(rules_dir: Path, rule_set: EligibilityRuleSet) -> None:
    """Write a test-only rule set using the Phase 3 model serialization."""
    (rules_dir / f"{SCHEME_ID}.json").write_text(
        json.dumps(rule_set.model_dump(mode="json")), encoding="utf-8"
    )


def _write_catalogue(
    catalogue_dir: Path,
    rule_set: EligibilityRuleSet,
    *,
    include_evidence: bool = True,
    evidence_id: str = EVIDENCE_ID,
    link_document_id: str = DOCUMENT_ID,
    link_version: str = DOCUMENT_VERSION,
) -> None:
    """Write synthetic Phase 3 catalogue fixtures; these are test-only data."""
    provenance = rule_set.rules[0].provenance
    source_document = SourceDocument(
        document_id=DOCUMENT_ID,
        scheme_id=SCHEME_ID,
        title=(
            "Test-only fixture metadata; verification statuses are synthetic and "
            "not production assertions."
        ),
        official_source_url=SOURCE_URL,
        document_version=DOCUMENT_VERSION,
        document_version_basis=(
            "Test-only metadata copied from the checked-in source registry."
        ),
        source_identity_status=SourceIdentityStatus.OFFICIAL_HOSTING_CONFIRMED,
        content_review_status=ContentReviewStatus.REVIEWED,
    )
    registry = SchemeRegistry(
        version="synthetic-test-v1",
        schemes=(
            SchemeRegistryEntry(
                scheme_id=SCHEME_ID,
                verification_status="synthetic_test_fixture",
                source_documents=(source_document,),
            ),
        ),
    )
    evidence = EvidenceCatalogue(
        schema_version="1.0.0",
        evidence=(
            EvidenceRecord(
                evidence_id=EVIDENCE_ID,
                scheme_id=SCHEME_ID,
                document_id=DOCUMENT_ID,
                page_number=3,
                excerpt=TEST_SOURCE_EXCERPT,
                excerpt_sha256=EXCERPT_HASH,
                is_synthetic=False,
                is_exact_source_text=True,
            ),
        )
        if include_evidence
        else (),
    )
    sidecar = RuleEvidenceSidecar(
        schema_version="1.0.0",
        links=tuple(
            RuleEvidenceLink(
                rule_id=rule.rule_id,
                scheme_id=provenance.scheme_id,
                document_id=link_document_id,
                evidence_id=evidence_id,
                document_version=link_version,
                relationship="primary",
            )
            for rule in rule_set.rules
        ),
    )
    for filename, model in (
        ("scheme_registry.json", registry),
        ("evidence_catalogue.json", evidence),
        ("rule_evidence_links.json", sidecar),
    ):
        (catalogue_dir / filename).write_text(
            json.dumps(model.model_dump(mode="json")), encoding="utf-8"
        )


def _with_provenance(
    rule_set: EligibilityRuleSet,
    **provenance_changes: object,
) -> EligibilityRuleSet:
    """Return a synthetic test rule set with altered source provenance."""
    rule = rule_set.rules[0]
    updated = rule.model_copy(
        update={"provenance": rule.provenance.model_copy(update=provenance_changes)}
    )
    return rule_set.model_copy(update={"rules": (updated,)})


@pytest.mark.parametrize(
    ("profile", "expected_status", "expected_eligible"),
    [
        ({"age": 18}, "eligible", True),
        ({"age": 17}, "ineligible", False),
        ({}, "needs_more_information", False),
    ],
)
def test_api_uses_phase3_engine_and_preserves_citations(
    client,
    profile: dict[str, int],
    expected_status: str,
    expected_eligible: bool,
) -> None:
    test_client, rules_dir, _ = client
    _write_rules(rules_dir)

    response = test_client.post(
        "/api/eligibility/check",
        json={"scheme_id": SCHEME_ID, "profile": profile},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == expected_status
    assert body["eligible"] is expected_eligible
    if not profile:
        assert body["missing_fields"] == ["age"]
    citation = body["rule_evaluations"][0]["citation"]
    assert citation == {
        "scheme_id": SCHEME_ID,
        "document_id": DOCUMENT_ID,
        "source_url": SOURCE_URL,
        "document_version": DOCUMENT_VERSION,
        "page_number": 3,
        "section": None,
        "excerpt_hash": EXCERPT_HASH,
    }


def test_pending_rule_is_not_executable_and_cannot_return_positive(client) -> None:
    test_client, rules_dir, _ = client
    _write_rules(rules_dir, RuleStatus.PENDING)

    response = test_client.post(
        "/api/eligibility/check",
        json={"scheme_id": SCHEME_ID, "profile": {"age": 100}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_more_information"
    assert body["eligible"] is False
    assert body["rule_evaluations"][0]["outcome"] == "UNEVALUABLE"
    assert "not ACTIVE" in body["rule_evaluations"][0]["reason"]


def test_malformed_configured_rule_file_returns_service_unavailable(client) -> None:
    test_client, rules_dir, _ = client
    (rules_dir / f"{SCHEME_ID}.json").write_text("{invalid", encoding="utf-8")

    response = test_client.post(
        "/api/eligibility/check",
        json={"scheme_id": SCHEME_ID, "profile": {}},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == ("eligibility_configuration_unavailable")


def test_invalid_scheme_id_cannot_be_used_as_a_rule_path(client) -> None:
    test_client, _, _ = client

    response = test_client.post(
        "/api/eligibility/check",
        json={"scheme_id": "../../external", "profile": {}},
    )

    assert response.status_code == 422


def test_rule_service_readiness_distinguishes_missing_and_invalid_configuration(
    tmp_path: Path,
) -> None:
    missing = EligibilityService(tmp_path / "missing")
    assert missing.readiness() == "not_configured"

    rules_dir = tmp_path / "configured"
    rules_dir.mkdir()
    catalogue_dir = tmp_path / "catalogue"
    catalogue_dir.mkdir()
    pending_set = _rule_set(RuleStatus.PENDING)
    _write_catalogue(catalogue_dir, pending_set)
    (rules_dir / f"{SCHEME_ID}.json").write_text(
        json.dumps(pending_set.model_dump(mode="json")),
        encoding="utf-8",
    )
    service = EligibilityService(
        rules_dir,
        registry_path=catalogue_dir / "scheme_registry.json",
        evidence_path=catalogue_dir / "evidence_catalogue.json",
        sidecar_path=catalogue_dir / "rule_evidence_links.json",
    )
    assert service.readiness() == "ready"

    active_without_approval = _rule_set()
    payload_without_approval = active_without_approval.model_dump(mode="json")
    payload_without_approval["rules"][0]["approval_evidence"] = None
    (rules_dir / f"{SCHEME_ID}.json").write_text(
        json.dumps(payload_without_approval), encoding="utf-8"
    )
    assert service.readiness() == "unavailable"

    mismatched = tmp_path / "mismatched"
    mismatched.mkdir()
    (mismatched / "other_scheme.json").write_text(
        json.dumps(_rule_set().model_dump(mode="json")),
        encoding="utf-8",
    )
    mismatch_service = EligibilityService(
        mismatched,
        registry_path=catalogue_dir / "scheme_registry.json",
        evidence_path=catalogue_dir / "evidence_catalogue.json",
        sidecar_path=catalogue_dir / "rule_evidence_links.json",
    )
    assert mismatch_service.readiness() == "unavailable"

    structurally_invalid = _rule_set()
    invalid_payload = structurally_invalid.model_dump(mode="json")
    invalid_payload["rules"].append(invalid_payload["rules"][0])
    (rules_dir / f"{SCHEME_ID}.json").write_text(
        json.dumps(invalid_payload), encoding="utf-8"
    )
    assert service.readiness() == "unavailable"


@pytest.mark.parametrize(
    "changes",
    [
        {"document_id": "unknown_test_document"},
        {"source_url": "https://example.gov.test/other.pdf"},
        {"document_version": "different-v2"},
        {"page_number": 4},
        {"section": "Different section"},
        {"excerpt_hash": "f" * 64},
        {"excerpt_hash": None},
    ],
)
def test_provenance_mismatches_fail_closed(
    client,
    changes: dict[str, object],
) -> None:
    test_client, rules_dir, catalogue_dir = client
    rule_set = _with_provenance(_rule_set(), **changes)
    _write_rule_set(rules_dir, rule_set)
    _write_catalogue(catalogue_dir, rule_set)

    response = test_client.post(
        "/api/eligibility/check",
        json={"scheme_id": SCHEME_ID, "profile": {"age": 100}},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == ("eligibility_configuration_unavailable")


def test_unknown_evidence_id_fails_closed(client) -> None:
    test_client, rules_dir, catalogue_dir = client
    rule_set = _rule_set()
    _write_rule_set(rules_dir, rule_set)
    _write_catalogue(catalogue_dir, rule_set, evidence_id="unknown_test_evidence")

    response = test_client.post(
        "/api/eligibility/check",
        json={"scheme_id": SCHEME_ID, "profile": {"age": 100}},
    )

    assert response.status_code == 503


def test_rule_without_a_sidecar_evidence_link_fails_closed(client) -> None:
    test_client, rules_dir, catalogue_dir = client
    rule_set = _rule_set()
    _write_rule_set(rules_dir, rule_set)
    _write_catalogue(catalogue_dir, rule_set)
    sidecar_path = catalogue_dir / "rule_evidence_links.json"
    sidecar_path.write_text(
        json.dumps({"schema_version": "1.0.0", "links": []}),
        encoding="utf-8",
    )

    response = test_client.post(
        "/api/eligibility/check",
        json={"scheme_id": SCHEME_ID, "profile": {"age": 100}},
    )

    assert response.status_code == 503


def test_empty_evidence_catalogue_fails_closed(client) -> None:
    test_client, rules_dir, catalogue_dir = client
    rule_set = _rule_set()
    _write_rule_set(rules_dir, rule_set)
    _write_catalogue(catalogue_dir, rule_set, include_evidence=False)

    response = test_client.post(
        "/api/eligibility/check",
        json={"scheme_id": SCHEME_ID, "profile": {"age": 100}},
    )

    assert response.status_code == 503


def test_catalogue_excerpt_hash_mismatch_fails_closed(client) -> None:
    test_client, rules_dir, catalogue_dir = client
    rule_set = _rule_set()
    _write_rule_set(rules_dir, rule_set)
    _write_catalogue(catalogue_dir, rule_set)
    evidence_path = catalogue_dir / "evidence_catalogue.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["evidence"][0]["excerpt_sha256"] = "f" * 64
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")

    response = test_client.post(
        "/api/eligibility/check",
        json={"scheme_id": SCHEME_ID, "profile": {"age": 100}},
    )

    assert response.status_code == 503


def test_missing_provenance_fails_closed(client) -> None:
    test_client, rules_dir, _ = client
    payload = _rule_set().model_dump(mode="json")
    del payload["rules"][0]["provenance"]
    (rules_dir / f"{SCHEME_ID}.json").write_text(json.dumps(payload), encoding="utf-8")

    response = test_client.post(
        "/api/eligibility/check",
        json={"scheme_id": SCHEME_ID, "profile": {"age": 100}},
    )

    assert response.status_code == 503


def test_mixed_valid_and_invalid_rule_provenance_never_reaches_engine(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_client, rules_dir, catalogue_dir = client
    valid_rule = _rule_set().rules[0]
    invalid_provenance = valid_rule.provenance.model_copy(
        update={"excerpt_hash": "f" * 64}
    )
    invalid_rule = valid_rule.model_copy(
        update={
            "rule_id": "synthetic_test_second_rule",
            "provenance": invalid_provenance,
        }
    )
    rule_set = EligibilityRuleSet(
        scheme_id=SCHEME_ID,
        schema_version=RULE_SCHEMA_VERSION,
        rules=(valid_rule, invalid_rule),
    )
    _write_rule_set(rules_dir, rule_set)
    _write_catalogue(catalogue_dir, rule_set)
    import src.api.eligibility_service as eligibility_service_module

    calls: list[object] = []
    monkeypatch.setattr(
        eligibility_service_module,
        "evaluate_eligibility",
        lambda *args: calls.append(args),
    )

    response = test_client.post(
        "/api/eligibility/check",
        json={"scheme_id": SCHEME_ID, "profile": {"age": 100}},
    )

    assert response.status_code == 503
    assert response.json().get("outcome") is None
    assert calls == []
