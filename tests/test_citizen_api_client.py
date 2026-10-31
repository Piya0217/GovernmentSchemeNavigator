"""Tests for the Streamlit application's FastAPI client."""

from __future__ import annotations

import json

import httpx
import pytest
from app.api_client import ApiClientError, GovernmentSchemeApiClient
from app.citizen_app import (
    _has_citation_metadata,
    _has_rule_citation,
    _is_official_http_url,
)
from app.translations import translate


def test_api_client_sends_query_and_preserves_response() -> None:
    answer = {
        "query": "ಯೋಜನೆಯ ಪ್ರಯೋಜನವೇನು?",
        "status": "supported",
        "passages": [
            {
                "source_document": "guidelines.pdf",
                "official_source_url": "https://example.gov/guidelines.pdf",
                "page_number": 4,
                "document_version": "2024-01-01",
                "chunk_id": "scheme_p4_c0",
                "chunk_index": 0,
                "similarity_score": 0.9,
                "distance": 0.1,
                "rerank_score": 0.8,
                "passage_text": "ಸರ್ಕಾರಿ ಮೂಲದ ಪಠ್ಯ.",
                "scheme_id": "central_example",
            }
        ],
        "eligibility_assessed": False,
        "detected_scheme_id": "central_example",
        "abstention_reason": None,
    }
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=answer)

    client = GovernmentSchemeApiClient(
        "http://api.test", transport=httpx.MockTransport(respond)
    )
    try:
        result = client.ask("ಯೋಜನೆಯ ಪ್ರಯೋಜನವೇನು?", "central_example")
    finally:
        client.close()

    assert result == answer
    assert requests[0].url.path == "/api/query"
    assert json.loads(requests[0].content) == {
        "query": "ಯೋಜನೆಯ ಪ್ರಯೋಜನವೇನು?",
        "scheme_id": "central_example",
    }


def test_api_client_lists_schemes_with_backend_filters() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/schemes"
        assert dict(request.url.params) == {
            "q": "farmer",
            "jurisdiction": "central",
            "verification_status": "verified_digital_text",
        }
        return httpx.Response(200, json={"schemes": []})

    client = GovernmentSchemeApiClient(
        "http://api.test", transport=httpx.MockTransport(respond)
    )
    try:
        assert client.list_schemes("farmer", "central", "verified_digital_text") == {
            "schemes": []
        }
    finally:
        client.close()


def test_api_client_posts_phase3_profile_to_eligibility_endpoint() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"status": "needs_more_information", "eligible": False},
        )

    client = GovernmentSchemeApiClient(
        "http://api.test", transport=httpx.MockTransport(respond)
    )
    profile = {"age": None, "state": "Karnataka"}
    try:
        result = client.check_eligibility("sample_scheme", profile)
    finally:
        client.close()

    assert result["status"] == "needs_more_information"
    assert requests[0].url.path == "/api/eligibility/check"
    assert json.loads(requests[0].content) == {
        "scheme_id": "sample_scheme",
        "profile": profile,
    }


def test_api_client_surfaces_structured_unavailable_error() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={
                "error": {
                    "code": "retrieval_unavailable",
                    "message": "Official document search is not available.",
                }
            },
        )

    client = GovernmentSchemeApiClient(
        "http://api.test", transport=httpx.MockTransport(respond)
    )
    try:
        with pytest.raises(ApiClientError, match="Official document search"):
            client.ask("Question")
    finally:
        client.close()


def test_translations_cover_english_kannada_and_unknown_language_fallback() -> None:
    assert translate("en", "schemes") == "Find schemes"
    assert translate("kn", "schemes") == "ಯೋಜನೆಗಳನ್ನು ಹುಡುಕಿ"
    assert translate("unknown", "schemes") == "Find schemes"


def test_evidence_is_renderable_only_with_page_level_official_citation() -> None:
    passage = {
        "passage_text": "Verbatim official passage.",
        "source_document": "guidelines.pdf",
        "official_source_url": "https://example.gov/guidelines.pdf",
        "page_number": 4,
    }

    assert _has_citation_metadata(passage)
    assert not _has_citation_metadata({**passage, "page_number": 0})
    assert not _has_citation_metadata({**passage, "official_source_url": None})
    assert not _has_citation_metadata({**passage, "passage_text": " "})
    assert not _is_official_http_url("http://[invalid")


def test_rule_citation_is_renderable_only_with_complete_rule_provenance() -> None:
    citation = {
        "document_id": "scheme-guidelines",
        "document_version": "2024-v1",
        "source_url": "https://example.gov/guidelines.pdf",
        "page_number": 3,
    }

    assert _has_rule_citation(citation)
    assert not _has_rule_citation({**citation, "page_number": None})
    assert not _has_rule_citation({**citation, "source_url": None})
    assert not _has_rule_citation({**citation, "document_id": " "})
