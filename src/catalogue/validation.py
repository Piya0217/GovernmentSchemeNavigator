"""Deterministic cross-reference checks for source/evidence catalogue data."""

from __future__ import annotations

from collections import Counter

from src.catalogue.schemas import (
    CatalogueIssue,
    EvidenceCatalogue,
    EvidenceRecord,
    RuleEvidenceSidecar,
    SchemeRegistry,
    SchemeRegistryEntry,
    SourceDocument,
)


def validate_catalogue(
    registry: SchemeRegistry,
    evidence_catalogue: EvidenceCatalogue,
    sidecar: RuleEvidenceSidecar,
    candidate_rule_ids: frozenset[str] = frozenset(),
) -> tuple[CatalogueIssue, ...]:
    """Return cross-reference issues in deterministic location/code order."""
    issues: list[CatalogueIssue] = []
    schemes = {scheme.scheme_id: scheme for scheme in registry.schemes}
    documents = {
        document.document_id: (scheme.scheme_id, document)
        for scheme in registry.schemes
        for document in scheme.source_documents
    }
    evidence = {record.evidence_id: record for record in evidence_catalogue.evidence}
    _validate_evidence(evidence_catalogue, schemes, documents, issues)
    _append_duplicate_issues(
        issues, "scheme_id", [s.scheme_id for s in registry.schemes]
    )
    _append_duplicate_issues(
        issues,
        "document_id",
        [
            doc.document_id
            for scheme in registry.schemes
            for doc in scheme.source_documents
        ],
    )
    _append_duplicate_issues(
        issues,
        "evidence_id",
        [record.evidence_id for record in evidence_catalogue.evidence],
    )
    _validate_document_relations(registry, documents, issues)
    _validate_links(sidecar, documents, evidence, schemes, candidate_rule_ids, issues)
    return tuple(
        sorted(issues, key=lambda issue: (issue.location, issue.code, issue.message))
    )


def _append_duplicate_issues(
    issues: list[CatalogueIssue], field: str, values: list[str]
) -> None:
    for value, count in sorted(Counter(values).items()):
        if count > 1:
            issues.append(
                CatalogueIssue(
                    code=f"duplicate_{field}",
                    location=field,
                    message=f"{field} '{value}' appears {count} times.",
                )
            )


def _validate_document_relations(
    registry: SchemeRegistry,
    documents: dict[str, tuple[str, SourceDocument]],
    issues: list[CatalogueIssue],
) -> None:
    for scheme in registry.schemes:
        for document in scheme.source_documents:
            if document.scheme_id != scheme.scheme_id:
                _issue(
                    issues,
                    "mixed_scheme_document",
                    f"schemes.{scheme.scheme_id}.source_documents.{document.document_id}",
                    "Document scheme_id differs from its registry scheme.",
                )
            for index, relation in enumerate(document.relationships):
                location = (
                    f"schemes.{scheme.scheme_id}.source_documents."
                    f"{document.document_id}.relationships.{index}"
                )
                target = documents.get(relation.document_id)
                if target is None:
                    _issue(
                        issues,
                        "unknown_related_document",
                        location,
                        "Related document does not exist.",
                    )
                elif target[0] != scheme.scheme_id:
                    _issue(
                        issues,
                        "mixed_scheme_relationship",
                        location,
                        "Related document belongs to another scheme.",
                    )


def _validate_evidence(
    catalogue: EvidenceCatalogue,
    schemes: dict[str, SchemeRegistryEntry],
    documents: dict[str, tuple[str, SourceDocument]],
    issues: list[CatalogueIssue],
) -> None:
    for index, record in enumerate(catalogue.evidence):
        location = f"evidence.{index}"
        if record.scheme_id not in schemes:
            _issue(
                issues, "unknown_scheme", location, "Evidence scheme does not exist."
            )
        document_pair = documents.get(record.document_id)
        if document_pair is None:
            _issue(
                issues,
                "unknown_document",
                location,
                "Evidence document does not exist.",
            )
        elif document_pair[0] != record.scheme_id:
            _issue(
                issues,
                "mixed_scheme_evidence",
                location,
                "Evidence scheme differs from its registry document scheme.",
            )


def _validate_links(
    sidecar: RuleEvidenceSidecar,
    documents: dict[str, tuple[str, SourceDocument]],
    evidence: dict[str, EvidenceRecord],
    schemes: dict[str, SchemeRegistryEntry],
    candidate_rule_ids: frozenset[str],
    issues: list[CatalogueIssue],
) -> None:
    for index, link in enumerate(sidecar.links):
        location = f"links.{index}"
        document_pair = documents.get(link.document_id)
        source = evidence.get(link.evidence_id)
        if link.scheme_id not in schemes:
            _issue(issues, "unknown_scheme", location, "Link scheme does not exist.")
        if document_pair is None:
            _issue(
                issues, "unknown_document", location, "Link document does not exist."
            )
        elif document_pair[0] != link.scheme_id:
            _issue(
                issues,
                "mixed_scheme_document",
                location,
                "Link and document schemes differ.",
            )
        elif document_pair[1].document_version is None:
            _issue(
                issues,
                "unknown_document_version",
                location,
                "Rule candidate requires an explicit document version.",
            )
        elif document_pair[1].document_version != link.document_version:
            _issue(
                issues,
                "document_version_mismatch",
                location,
                "Link version differs from its source document.",
            )
        if source is None:
            _issue(
                issues, "unknown_evidence", location, "Linked evidence does not exist."
            )
        elif (source.scheme_id, source.document_id) != (
            link.scheme_id,
            link.document_id,
        ):
            _issue(
                issues,
                "mixed_scheme_evidence",
                location,
                "Evidence and link provenance differ.",
            )
        if link.rule_id not in candidate_rule_ids:
            _issue(
                issues,
                "unknown_rule_candidate",
                location,
                "Linked rule candidate does not exist.",
            )


def _issue(
    issues: list[CatalogueIssue], code: str, location: str, message: str
) -> None:
    issues.append(CatalogueIssue(code=code, location=location, message=message))


__all__ = ["validate_catalogue"]
