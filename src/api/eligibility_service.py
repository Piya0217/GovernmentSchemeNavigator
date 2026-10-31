"""Adapter between API requests and the Phase 3 deterministic rules engine."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from src.api.evidence_validation import (
    EvidenceProvenanceError,
    validate_rule_set_provenance,
)
from src.catalogue.schemas import EvidenceCatalogue, RuleEvidenceSidecar, SchemeRegistry
from src.rules.engine import evaluate_eligibility
from src.rules.models import (
    CitizenProfile,
    EligibilityResult,
    EligibilityRuleSet,
    RuleStatus,
)
from src.rules.validation import validate_rule_activation, validate_rule_set

logger = logging.getLogger("scheme_navigator.api.eligibility")
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class EligibilityConfigurationError(Exception):
    """A configured rule set could not be read or validated."""


class EligibilityService:
    """Load per-scheme validated rule sets and delegate all decisions to Phase 3.

    Rule files use the Phase 3 ``EligibilityRuleSet`` JSON schema at
    ``data/rules/<scheme_id>.json``. The Phase 3 branches currently provide no
    production rule files, so schemes without a file are reported unsupported.
    """

    def __init__(
        self,
        rules_dir: Path,
        registry_path: Path | None = None,
        evidence_path: Path | None = None,
        sidecar_path: Path | None = None,
    ) -> None:
        self._rules_dir = rules_dir
        self._registry_path = (
            registry_path or PROJECT_ROOT / "data/scheme_registry.json"
        )
        self._evidence_path = (
            evidence_path or PROJECT_ROOT / "data/evidence_catalogue.json"
        )
        self._sidecar_path = sidecar_path or (
            PROJECT_ROOT / "data/rule_candidates/rule_evidence_links.json"
        )

    def is_available(self) -> bool:
        """Return whether configured rule sets are structurally usable."""
        return self.readiness() == "ready"

    def readiness(self) -> Literal["ready", "unavailable", "not_configured"]:
        """Distinguish absent configuration from invalid or usable rule files."""
        if not self._rules_dir.is_dir():
            return "not_configured"
        if not list(self._rules_dir.glob("*.json")):
            return "not_configured"
        try:
            rule_sets = self._load_configured_rule_sets()
            candidate_ids = self._candidate_rule_ids(rule_sets)
            for rule_set in rule_sets.values():
                self._validate_evidence(rule_set, candidate_ids)
        except EligibilityConfigurationError:
            logger.exception("Eligibility rule or evidence configuration is invalid.")
            return "unavailable"

        for rule_set in rule_sets.values():
            if not validate_rule_set(rule_set).is_valid:
                logger.error(
                    "Structurally invalid eligibility rule set: %s",
                    rule_set.scheme_id,
                )
                return "unavailable"
            if any(
                rule.status is RuleStatus.ACTIVE
                and not validate_rule_activation(rule).ready_for_activation
                for rule in rule_set.rules
            ):
                logger.error(
                    "ACTIVE rule lacks valid approval metadata: %s",
                    rule_set.scheme_id,
                )
                return "unavailable"
        return "ready"

    def check(
        self, scheme_id: str, profile: CitizenProfile
    ) -> EligibilityResult | None:
        """Evaluate via the actual Phase 3 engine, or return None if unsupported."""
        path = self._rules_dir / f"{scheme_id}.json"
        if not path.is_file():
            return None
        rule_sets = self._load_configured_rule_sets()
        rule_set = rule_sets[scheme_id]
        self._validate_evidence(
            rule_set,
            self._candidate_rule_ids(rule_sets),
        )
        return evaluate_eligibility(profile, rule_set)

    def _load_configured_rule_sets(self) -> dict[str, EligibilityRuleSet]:
        """Parse every configured rule file and require filename/schema agreement."""
        try:
            rule_sets = {
                path.stem: self._load_path(path)
                for path in sorted(self._rules_dir.glob("*.json"))
            }
        except EligibilityConfigurationError:
            raise
        if any(
            scheme_id != rule_set.scheme_id for scheme_id, rule_set in rule_sets.items()
        ):
            raise EligibilityConfigurationError(
                "Rule-set scheme_id does not match its filename."
            )
        return rule_sets

    @staticmethod
    def _candidate_rule_ids(
        rule_sets: dict[str, EligibilityRuleSet],
    ) -> frozenset[str]:
        """Collect IDs so the Phase 3 validator can check all sidecar references."""
        rule_ids = [
            rule.rule_id for rule_set in rule_sets.values() for rule in rule_set.rules
        ]
        if len(rule_ids) != len(set(rule_ids)):
            raise EligibilityConfigurationError(
                "Rule IDs must be unique across rule sets."
            )
        return frozenset(rule_ids)

    def _validate_evidence(
        self,
        rule_set: EligibilityRuleSet,
        candidate_rule_ids: frozenset[str],
    ) -> None:
        """Load Phase 3 catalogue models and validate rule provenance references."""
        try:
            registry = SchemeRegistry.model_validate_json(
                self._registry_path.read_text(encoding="utf-8")
            )
            evidence = EvidenceCatalogue.model_validate_json(
                self._evidence_path.read_text(encoding="utf-8")
            )
            sidecar = RuleEvidenceSidecar.model_validate_json(
                self._sidecar_path.read_text(encoding="utf-8")
            )
            validate_rule_set_provenance(
                rule_set,
                registry,
                evidence,
                sidecar,
                candidate_rule_ids,
            )
        except (OSError, ValidationError, EvidenceProvenanceError) as error:
            raise EligibilityConfigurationError from error

    @staticmethod
    def _load_path(path: Path) -> EligibilityRuleSet:
        """Parse a rule file with the Phase 3 Pydantic schema."""
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return EligibilityRuleSet.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise EligibilityConfigurationError from error
