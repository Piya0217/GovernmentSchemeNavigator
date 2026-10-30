"""Synthetic tests for source catalogue models and cross-reference validation."""

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError
from src.catalogue.schemas import (
    ByteMatchStatus,
    ContentReviewStatus,
    CurrentnessStatus,
    DocumentRelationship,
    EvidenceCatalogue,
    EvidenceRecord,
    EvidenceRelationship,
    RuleEvidenceLink,
    RuleEvidenceSidecar,
    SchemeRegistry,
    SourceDocument,
    SourceIdentityStatus,
    candidate_document_version,
)
from src.catalogue.validation import validate_catalogue

ROOT = Path(__file__).resolve().parents[2]


def make_document(**overrides: object) -> SourceDocument:
    values: dict[str, object] = {
        "document_id": "synthetic_guidelines_v1",
        "scheme_id": "synthetic_scheme",
        "title": "Synthetic Guidelines",
        "official_source_url": "https://example.gov.test/guidelines.pdf",
        "local_path": "data/raw/synthetic.pdf",
        "local_pdf_sha256": "a" * 64,
        "document_version": "synthetic-v1",
        "document_version_basis": (
            "[SYNTHETIC TEST DATA] Explicit synthetic version basis."
        ),
    }
    values.update(overrides)
    return SourceDocument(**values)


def make_evidence(**overrides: object) -> EvidenceRecord:
    excerpt = "[SYNTHETIC TEST DATA] Example passage for schema validation only."
    values: dict[str, object] = {
        "evidence_id": "synthetic_evidence_1",
        "scheme_id": "synthetic_scheme",
        "document_id": "synthetic_guidelines_v1",
        "page_number": 1,
        "excerpt": excerpt,
        "excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        "retrieval_chunk_sha256": ("b" * 64,),
        "is_synthetic": True,
    }
    values.update(overrides)
    return EvidenceRecord(**values)


def make_registry(*documents: SourceDocument) -> SchemeRegistry:
    return SchemeRegistry.model_validate(
        {
            "version": "1.0.0",
            "schemes": [
                {
                    "scheme_id": "synthetic_scheme",
                    "verification_status": "unresolved",
                    "source_documents": [
                        document.model_dump(mode="json") for document in documents
                    ],
                }
            ],
        }
    )


def make_link(**overrides: object) -> RuleEvidenceLink:
    values: dict[str, object] = {
        "rule_id": "synthetic_rule_1",
        "scheme_id": "synthetic_scheme",
        "document_id": "synthetic_guidelines_v1",
        "evidence_id": "synthetic_evidence_1",
        "document_version": "synthetic-v1",
        "relationship": EvidenceRelationship.PRIMARY,
    }
    values.update(overrides)
    return RuleEvidenceLink(**values)


def test_valid_synthetic_catalogue_has_no_issues() -> None:
    registry = make_registry(make_document())
    evidence = EvidenceCatalogue(schema_version="1.0.0", evidence=(make_evidence(),))
    sidecar = RuleEvidenceSidecar(schema_version="1.0.0", links=(make_link(),))

    assert (
        validate_catalogue(registry, evidence, sidecar, frozenset({"synthetic_rule_1"}))
        == ()
    )


def test_identifiers_are_valid_and_duplicate_ids_are_reported() -> None:
    first = make_document()
    duplicate = make_document(title="Second synthetic record")
    issues = validate_catalogue(
        make_registry(first, duplicate),
        EvidenceCatalogue(schema_version="1.0.0"),
        RuleEvidenceSidecar(schema_version="1.0.0"),
    )

    assert [(issue.code, issue.location) for issue in issues] == [
        ("duplicate_document_id", "document_id")
    ]
    with pytest.raises(ValidationError):
        make_document(document_id="not valid")


def test_cross_reference_and_scheme_consistency_issues_are_deterministic() -> None:
    foreign_evidence = make_evidence(document_id="synthetic_guidelines_other")
    link = make_link(scheme_id="other_scheme")
    registry = make_registry(
        make_document(), make_document(document_id="synthetic_guidelines_other")
    )
    issues = validate_catalogue(
        registry,
        EvidenceCatalogue(schema_version="1.0.0", evidence=(foreign_evidence,)),
        RuleEvidenceSidecar(schema_version="1.0.0", links=(link,)),
        frozenset({"different_rule"}),
    )

    assert [issue.code for issue in issues] == [
        "mixed_scheme_document",
        "mixed_scheme_evidence",
        "unknown_rule_candidate",
        "unknown_scheme",
    ]
    assert issues == validate_catalogue(
        registry,
        EvidenceCatalogue(schema_version="1.0.0", evidence=(foreign_evidence,)),
        RuleEvidenceSidecar(schema_version="1.0.0", links=(link,)),
        frozenset({"different_rule"}),
    )


@pytest.mark.parametrize("page_number", [0, -1])
def test_evidence_requires_positive_one_indexed_page(page_number: int) -> None:
    with pytest.raises(ValidationError):
        make_evidence(page_number=page_number)


@pytest.mark.parametrize(
    "local_path",
    [
        "../private.pdf",
        "data/processed/file.pdf",
        "C:/outside.pdf",
        "data/raw/../x.pdf",
    ],
)
def test_local_path_must_stay_within_data_raw(local_path: str) -> None:
    with pytest.raises(ValidationError):
        make_document(local_path=local_path)


def test_sha256_values_are_valid_and_excerpt_hash_must_match() -> None:
    with pytest.raises(ValidationError):
        make_document(local_pdf_sha256="not-a-hash")
    with pytest.raises(ValidationError):
        make_evidence(excerpt_sha256="c" * 64)
    with pytest.raises(ValidationError):
        make_evidence(retrieval_chunk_sha256=("not-a-hash",))


def test_unknown_dates_and_versions_remain_null_and_block_candidates() -> None:
    document = make_document(document_version=None, document_version_basis=None)

    assert document.publication_date is None
    assert document.effective_date is None
    assert document.document_version is None
    with pytest.raises(ValueError, match="blocked"):
        candidate_document_version(document)


def test_explicit_dates_validate_and_malformed_dates_are_rejected() -> None:
    document = make_document(
        publication_date=date(2024, 1, 2), effective_date=date(2024, 2, 3)
    )

    assert document.publication_date == date(2024, 1, 2)
    assert document.effective_date == date(2024, 2, 3)
    with pytest.raises(ValidationError):
        make_document(publication_date="2024-02-31")


def test_known_candidate_version_requires_explicit_basis() -> None:
    with pytest.raises(ValidationError):
        make_document(document_version="guessed-version", document_version_basis=None)
    assert candidate_document_version(make_document()) == "synthetic-v1"


def test_amendment_relationship_preserves_known_provisions_and_references() -> None:
    relation = DocumentRelationship(
        document_id="synthetic_addendum",
        relationship="amendment",
        affected_provisions=("Section 1E", "Section 8B"),
    )
    unspecified_relation = DocumentRelationship(
        document_id="synthetic_addendum", relationship="amendment"
    )
    assert unspecified_relation.affected_provisions == ()
    base = make_document(relationships=(relation,))
    target = make_document(document_id="synthetic_addendum", title="Synthetic Addendum")
    issues = validate_catalogue(
        make_registry(base, target),
        EvidenceCatalogue(schema_version="1.0.0"),
        RuleEvidenceSidecar(schema_version="1.0.0"),
    )
    assert issues == ()

    missing_target = make_registry(make_document(relationships=(relation,)))
    assert (
        validate_catalogue(
            missing_target,
            EvidenceCatalogue(schema_version="1.0.0"),
            RuleEvidenceSidecar(schema_version="1.0.0"),
        )[0].code
        == "unknown_related_document"
    )


@pytest.mark.parametrize("relationship", list(EvidenceRelationship))
def test_all_evidence_link_relationship_types_are_supported(
    relationship: EvidenceRelationship,
) -> None:
    assert make_link(relationship=relationship).relationship is relationship


def test_sidecar_rejects_non_pending_candidate_status() -> None:
    with pytest.raises(ValidationError):
        make_link(status="ACTIVE")


def test_link_version_must_match_document_version() -> None:
    sidecar = RuleEvidenceSidecar(
        schema_version="1.0.0", links=(make_link(document_version="synthetic-v2"),)
    )
    issues = validate_catalogue(
        make_registry(make_document()),
        EvidenceCatalogue(schema_version="1.0.0", evidence=(make_evidence(),)),
        sidecar,
        frozenset({"synthetic_rule_1"}),
    )
    assert [issue.code for issue in issues] == ["document_version_mismatch"]


def test_registry_legacy_fields_and_verification_values_are_preserved() -> None:
    data = json.loads((ROOT / "data/scheme_registry.json").read_text(encoding="utf-8"))
    registry = SchemeRegistry.model_validate(data)
    expected_statuses = {
        "central_pm_kisan": "verified_digital_text",
        "central_pmjay": "verified_digital_text",
        "central_pm_vishwakarma": "verified_digital_text",
    }

    assert registry.version == "1.1.0"
    for scheme_id, status in expected_statuses.items():
        entry = next(item for item in registry.schemes if item.scheme_id == scheme_id)
        assert entry.verification_status == status
        assert entry.model_extra is not None
        assert "document_title" in entry.model_extra
        assert len(entry.source_documents) == 1
        assert (
            entry.source_documents[0].source_identity_status
            is SourceIdentityStatus.UNASSESSED
        )
        assert entry.source_documents[0].byte_match_status is ByteMatchStatus.UNASSESSED
        assert (
            entry.source_documents[0].content_review_status
            is ContentReviewStatus.UNREVIEWED
        )
        assert entry.source_documents[0].currentness_status is CurrentnessStatus.UNKNOWN
        source = entry.source_documents[0]
        assert source.local_path is not None
        assert (
            source.local_pdf_sha256
            == hashlib.sha256((ROOT / source.local_path).read_bytes()).hexdigest()
        )
    assert "last_updated" in registry.model_extra
    assert data["last_updated"] == "2026-10-30"


def test_repository_catalogue_files_parse_and_cross_validate() -> None:
    registry = SchemeRegistry.model_validate_json(
        (ROOT / "data/scheme_registry.json").read_text(encoding="utf-8")
    )
    evidence = EvidenceCatalogue.model_validate_json(
        (ROOT / "data/evidence_catalogue.json").read_text(encoding="utf-8")
    )
    sidecar = RuleEvidenceSidecar.model_validate_json(
        (ROOT / "data/rule_candidates/rule_evidence_links.json").read_text(
            encoding="utf-8"
        )
    )

    assert validate_catalogue(registry, evidence, sidecar) == ()
    assert evidence.evidence == ()
    assert sidecar.links == ()


def test_catalogue_models_serialize_collection_fields_as_json_arrays() -> None:
    evidence = EvidenceCatalogue(schema_version="1.0.0", evidence=(make_evidence(),))
    dumped = evidence.model_dump(mode="json")

    assert isinstance(dumped["evidence"], list)
    assert dumped["evidence"][0]["is_synthetic"] is True
    assert "[SYNTHETIC TEST DATA]" in dumped["evidence"][0]["excerpt"]
