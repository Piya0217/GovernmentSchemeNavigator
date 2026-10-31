"""Mock-based tests for Phase 4 API endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from src.agent.orchestrator import WorkflowOrchestrator
from src.api.main import create_app
from src.api.services import ApiServices, SchemeRegistryService
from src.retrieval.answer import AnswerResponse, EvidencePassage

REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "scheme_registry.json"


def _make_services(
    retrieval: MagicMock | None = None,
    registry_path: Path = REGISTRY_PATH,
    retrieval_status: str = "ready",
) -> tuple[ApiServices, MagicMock]:
    """Build an injected application service container without external services."""
    retrieval_service = retrieval or MagicMock()
    services = ApiServices(
        workflow=WorkflowOrchestrator(retrieval_service),
        scheme_registry=SchemeRegistryService(registry_path),
        retrieval_status=retrieval_status,  # type: ignore[arg-type]
    )
    return services, retrieval_service


def _supported_response() -> AnswerResponse:
    """Return a response exercising all Phase 2E passage metadata."""
    return AnswerResponse(
        query="What does PM-KISAN provide?",
        status="supported",
        passages=[
            EvidencePassage(
                chunk_id="central_pm_kisan_p2_c1",
                scheme_id="central_pm_kisan",
                source_document="central_pm_kisan_guidelines_2020.pdf",
                official_source_url=(
                    "https://pmkisan.gov.in/Documents/"
                    "RevisedPM-KISANOperationalGuidelines(English).pdf"
                ),
                page_number=2,
                chunk_index=1,
                document_version="2020-03-29",
                passage_text="Verbatim evidence passage.",
                distance=0.42,
                similarity_score=0.58,
                rerank_score=0.81,
            )
        ],
        eligibility_assessed=False,
        detected_scheme_id="central_pm_kisan",
    )


def test_health_legacy_endpoint_preserves_response_contract() -> None:
    """The existing root health endpoint remains available and unchanged."""
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "0.1.0",
        "service": "government-scheme-navigator",
    }


def test_api_health_reports_component_states() -> None:
    services, _ = _make_services()
    with TestClient(create_app(services=services)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "version": "0.1.0",
        "service": "government-scheme-navigator",
        "retrieval": "ready",
        "eligibility": "not_configured",
        "scheme_registry": "ready",
    }


def test_schemes_endpoint_returns_registry_and_nullable_metadata() -> None:
    services, _ = _make_services()
    with TestClient(create_app(services=services)) as client:
        response = client.get("/api/schemes")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 8
    assert body["version"] == "1.1.0"
    sandhya = next(
        item
        for item in body["schemes"]
        if item["scheme_id"] == "karnataka_sandhya_suraksha"
    )
    assert sandhya["official_source_url"] is None
    assert sandhya["document_metadata"] is None
    assert sandhya["verification_status"] == "unresolved"
    pm_kisan = next(
        item for item in body["schemes"] if item["scheme_id"] == "central_pm_kisan"
    )
    assert pm_kisan["source_documents"][0]["document_id"] == (
        "central_pm_kisan_guidelines_2020"
    )
    assert pm_kisan["source_documents"][0]["source_identity_status"] == "unassessed"


def test_schemes_endpoint_filters_registry_fields() -> None:
    services, _ = _make_services()
    with TestClient(create_app(services=services)) as client:
        response = client.get(
            "/api/schemes",
            params={
                "jurisdiction": "central",
                "verification_status": "verified_digital_text",
                "q": "pm-kisan",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["schemes"][0]["scheme_id"] == "central_pm_kisan"


@pytest.mark.parametrize("contents", ["{invalid", json.dumps({"schemes": []})])
def test_schemes_endpoint_returns_service_error_for_missing_or_invalid_registry(
    tmp_path: Path,
    contents: str,
) -> None:
    registry_path = tmp_path / "scheme_registry.json"
    registry_path.write_text(contents, encoding="utf-8")
    services, _ = _make_services(registry_path=registry_path)

    with TestClient(create_app(services=services)) as client:
        response = client.get("/api/schemes")
        health = client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "scheme_registry_unavailable"
    assert health.json()["scheme_registry"] == "unavailable"


def test_schemes_endpoint_returns_service_error_for_missing_file(
    tmp_path: Path,
) -> None:
    services, _ = _make_services(registry_path=tmp_path / "missing.json")
    with TestClient(create_app(services=services)) as client:
        response = client.get("/api/schemes")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "scheme_registry_unavailable"


def test_query_returns_supported_response_with_all_provenance() -> None:
    retrieval = MagicMock()
    retrieval.answer.return_value = _supported_response()
    services, _ = _make_services(retrieval=retrieval)

    with TestClient(create_app(services=services)) as client:
        response = client.post(
            "/api/query",
            json={
                "query": "  What does PM-KISAN provide?  ",
                "scheme_id": "central_pm_kisan",
            },
        )

    assert response.status_code == 200
    retrieval.answer.assert_called_once_with(
        "What does PM-KISAN provide?", "central_pm_kisan"
    )
    body = response.json()
    assert body["status"] == "supported"
    assert body["eligibility_assessed"] is False
    assert body["detected_scheme_id"] == "central_pm_kisan"
    assert body["passages"][0] == {
        "chunk_id": "central_pm_kisan_p2_c1",
        "scheme_id": "central_pm_kisan",
        "source_document": "central_pm_kisan_guidelines_2020.pdf",
        "official_source_url": (
            "https://pmkisan.gov.in/Documents/"
            "RevisedPM-KISANOperationalGuidelines(English).pdf"
        ),
        "page_number": 2,
        "chunk_index": 1,
        "document_version": "2020-03-29",
        "passage_text": "Verbatim evidence passage.",
        "distance": 0.42,
        "similarity_score": 0.58,
        "rerank_score": 0.81,
    }


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("insufficient_evidence", "No sufficiently relevant passages."),
        ("out_of_scope", "Question is outside the supported domain."),
    ],
)
def test_query_preserves_abstention_status_and_reason(status: str, reason: str) -> None:
    retrieval = MagicMock()
    retrieval.answer.return_value = AnswerResponse(
        query="Question", status=status, abstention_reason=reason
    )
    services, _ = _make_services(retrieval=retrieval)

    with TestClient(create_app(services=services)) as client:
        response = client.post("/api/query", json={"query": "Question"})

    assert response.status_code == 200
    assert response.json()["status"] == status
    assert response.json()["abstention_reason"] == reason
    assert response.json()["passages"] == []
    assert response.json()["eligibility_assessed"] is False


@pytest.mark.parametrize(
    "body",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "q" * 2001},
        {"query": "question", "unexpected": "field"},
    ],
)
def test_query_rejects_invalid_request(body: dict[str, str]) -> None:
    services, _ = _make_services()
    with TestClient(create_app(services=services)) as client:
        response = client.post("/api/query", json=body)
    assert response.status_code == 422


def test_query_rejects_unknown_scheme_id() -> None:
    services, retrieval = _make_services()
    with TestClient(create_app(services=services)) as client:
        response = client.post(
            "/api/query",
            json={"query": "Question", "scheme_id": "unknown_scheme"},
        )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "scheme_not_found"
    retrieval.answer.assert_not_called()


def test_query_returns_503_when_retrieval_is_unavailable() -> None:
    services = ApiServices(
        workflow=WorkflowOrchestrator(retrieval=None),
        scheme_registry=SchemeRegistryService(REGISTRY_PATH),
        retrieval_status="unavailable",
    )
    with TestClient(create_app(services=services)) as client:
        response = client.post("/api/query", json={"query": "Question"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "retrieval_unavailable"


def test_eligibility_endpoint_reports_unsupported_without_a_rule_set() -> None:
    services, _ = _make_services()
    with TestClient(create_app(services=services)) as client:
        response = client.post(
            "/api/eligibility/check",
            json={"scheme_id": "central_pm_kisan", "profile": {}},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "unsupported_scheme"
    assert response.json()["eligible"] is False
    assert response.json()["outcome"] is None


def test_eligibility_endpoint_validates_the_actual_phase3_profile_schema() -> None:
    services, _ = _make_services()
    with TestClient(create_app(services=services)) as client:
        response = client.post(
            "/api/eligibility/check",
            json={
                "scheme_id": "central_pm_kisan",
                "profile": {"age": True, "unexpected_field": "value"},
            },
        )

    assert response.status_code == 422
