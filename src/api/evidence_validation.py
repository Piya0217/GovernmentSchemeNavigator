"""Validate Phase 3 rule provenance against its source and evidence catalogue."""

from __future__ import annotations

from src.catalogue.schemas import (
    ContentReviewStatus,
    EvidenceCatalogue,
    EvidenceRecord,
    RuleEvidenceLink,
    RuleEvidenceSidecar,
    SchemeRegistry,
    SourceDocument,
    SourceIdentityStatus,
)
from src.catalogue.validation import validate_catalogue
from src.rules.models import EligibilityRuleSet, RuleProvenance


class EvidenceProvenanceError(Exception):
    """Raised when rule provenance cannot be resolved to exact catalogue data."""


def validate_rule_set_provenance(
    rule_set: EligibilityRuleSet,
    registry: SchemeRegistry,
    evidence_catalogue: EvidenceCatalogue,
    sidecar: RuleEvidenceSidecar,
    candidate_rule_ids: frozenset[str],
) -> dict[str, EvidenceRecord]:
    """Resolve every rule to one exact, non-synthetic catalogue evidence record."""
    issues = validate_catalogue(
        registry, evidence_catalogue, sidecar, candidate_rule_ids
    )
    if issues:
        raise EvidenceProvenanceError("Catalogue cross-reference validation failed.")

    documents = {
        (scheme.scheme_id, document.document_id): document
        for scheme in registry.schemes
        for document in scheme.source_documents
    }
    records = {record.evidence_id: record for record in evidence_catalogue.evidence}
    links_by_rule: dict[str, list[RuleEvidenceLink]] = {}
    for link in sidecar.links:
        links_by_rule.setdefault(link.rule_id, []).append(link)

    validated: dict[str, EvidenceRecord] = {}
    for rule in rule_set.rules:
        provenance = rule.provenance
        if provenance.excerpt_hash is None:
            raise EvidenceProvenanceError("Rule provenance lacks an excerpt hash.")

        document = documents.get((provenance.scheme_id, provenance.document_id))
        if document is None:
            raise EvidenceProvenanceError("Rule source document is not registered.")
        if (
            document.source_identity_status
            is not SourceIdentityStatus.OFFICIAL_HOSTING_CONFIRMED
        ):
            raise EvidenceProvenanceError("Rule source identity is not confirmed.")
        if document.content_review_status is not ContentReviewStatus.REVIEWED:
            raise EvidenceProvenanceError(
                "Rule source document is not content-reviewed."
            )
        if document.official_source_url != provenance.source_url:
            raise EvidenceProvenanceError(
                "Rule source URL does not match the registry."
            )
        if document.document_version != provenance.document_version:
            raise EvidenceProvenanceError(
                "Rule document version does not match the registry."
            )

        rule_links = links_by_rule.get(rule.rule_id, [])
        if not rule_links:
            raise EvidenceProvenanceError("Rule has no catalogue evidence link.")
        _validate_linked_evidence(rule_links, documents, records)
        linked_records = [
            records[link.evidence_id]
            for link in rule_links
            if link.scheme_id == provenance.scheme_id
            and link.document_id == provenance.document_id
            and link.document_version == provenance.document_version
        ]
        matches = [
            record
            for record in linked_records
            if _matches_provenance(record, provenance)
            and not record.is_synthetic
            and record.is_exact_source_text
        ]
        if len(matches) != 1:
            raise EvidenceProvenanceError(
                "Rule provenance must resolve to exactly one exact-source "
                "evidence record."
            )
        validated[rule.rule_id] = matches[0]
    return validated


def _validate_linked_evidence(
    links: list[RuleEvidenceLink],
    documents: dict[tuple[str, str], SourceDocument],
    records: dict[str, EvidenceRecord],
) -> None:
    """Require each rule-linked record to be exact text from reviewed sources."""
    for link in links:
        document = documents[(link.scheme_id, link.document_id)]
        evidence = records[link.evidence_id]
        if (
            document.source_identity_status
            is not SourceIdentityStatus.OFFICIAL_HOSTING_CONFIRMED
        ):
            raise EvidenceProvenanceError(
                "Linked evidence source identity is not confirmed."
            )
        if document.content_review_status is not ContentReviewStatus.REVIEWED:
            raise EvidenceProvenanceError(
                "Linked evidence source is not content-reviewed."
            )
        if evidence.is_synthetic or not evidence.is_exact_source_text:
            raise EvidenceProvenanceError("Linked evidence is not exact source text.")


def _matches_provenance(record: EvidenceRecord, provenance: RuleProvenance) -> bool:
    """Match the fields shared by Phase 3 rule provenance and evidence records."""
    return (
        record.scheme_id == provenance.scheme_id
        and record.document_id == provenance.document_id
        and record.page_number == provenance.page_number
        and record.excerpt_sha256.lower() == provenance.excerpt_hash.lower()
        and (provenance.section is None or record.section == provenance.section)
    )


__all__ = ["EvidenceProvenanceError", "validate_rule_set_provenance"]
