"""Eligibility endpoint backed only by the Phase 3 deterministic engine."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import get_api_services
from src.api.eligibility_service import EligibilityConfigurationError
from src.api.errors import ApiServiceError
from src.api.schemas.eligibility import (
    EligibilityCheckRequest,
    EligibilityCheckResponse,
    EligibilityCitation,
    RuleEvaluationResponse,
)
from src.api.services import ApiServices, SchemeRegistryUnavailableError
from src.rules.models import EligibilityOutcome

router = APIRouter(prefix="/api/eligibility", tags=["eligibility"])


@router.post("/check", summary="Check eligibility using the deterministic rules engine")
def check_eligibility(
    request: EligibilityCheckRequest,
    services: Annotated[ApiServices, Depends(get_api_services)],
) -> EligibilityCheckResponse:
    """Validate the scheme and delegate profile evaluation to the real engine."""
    try:
        registry = services.scheme_registry.list_schemes()
    except SchemeRegistryUnavailableError as error:
        raise ApiServiceError(
            503,
            "scheme_registry_unavailable",
            "Scheme information is temporarily unavailable.",
        ) from error
    if not any(item.scheme_id == request.scheme_id for item in registry.schemes):
        raise ApiServiceError(
            404,
            "scheme_not_found",
            "The requested scheme is not present in the scheme registry.",
        )

    try:
        result = services.eligibility.check(request.scheme_id, request.profile)
    except EligibilityConfigurationError as error:
        raise ApiServiceError(
            503,
            "eligibility_configuration_unavailable",
            "Eligibility rules are temporarily unavailable.",
        ) from error
    if result is None:
        return EligibilityCheckResponse(
            scheme_id=request.scheme_id,
            status="unsupported_scheme",
            explanation=(
                "No Phase 3 rule set is configured for this scheme. "
                "No eligibility decision was made."
            ),
        )

    status = {
        EligibilityOutcome.ELIGIBLE: "eligible",
        EligibilityOutcome.INELIGIBLE: "ineligible",
        EligibilityOutcome.NEEDS_MORE_INFORMATION: "needs_more_information",
    }[result.outcome]
    missing_fields = tuple(
        sorted(
            {
                evaluation.reason.split("'", 2)[1]
                for evaluation in result.rule_evaluations
                if evaluation.reason.startswith("Missing profile field '")
            }
        )
    )
    return EligibilityCheckResponse(
        scheme_id=result.scheme_id,
        status=status,
        outcome=result.outcome,
        eligible=result.outcome is EligibilityOutcome.ELIGIBLE,
        explanation=result.explanation,
        missing_fields=missing_fields,
        rule_evaluations=tuple(
            RuleEvaluationResponse(
                rule_id=evaluation.rule_id,
                outcome=evaluation.outcome,
                reason=evaluation.reason,
                citation=EligibilityCitation(
                    scheme_id=evaluation.provenance.scheme_id,
                    document_id=evaluation.provenance.document_id,
                    source_url=evaluation.provenance.source_url,
                    document_version=evaluation.provenance.document_version,
                    page_number=evaluation.provenance.page_number,
                    section=evaluation.provenance.section,
                    excerpt_hash=evaluation.provenance.excerpt_hash,
                ),
            )
            for evaluation in result.rule_evaluations
        ),
        evaluated_at=result.evaluated_at.isoformat(),
        engine_version=result.engine_version,
    )
