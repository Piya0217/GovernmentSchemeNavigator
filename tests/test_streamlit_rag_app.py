"""Tests for the local Streamlit RAG application helpers and components."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from streamlit_rag_app import (
    get_status_badge,
    is_historical_document,
    load_registry,
)


def test_is_historical_document_pre_2023() -> None:
    """Documents published before 2023 must be marked as historical."""
    assert is_historical_document("2020-03-29") is True
    assert is_historical_document("2018-09-23") is True
    assert is_historical_document("2019-12-12") is True


def test_is_historical_document_recent() -> None:
    """Documents published 2023 or later are not marked historical."""
    assert is_historical_document("2023-09-17") is False
    assert is_historical_document("2024-01-15") is False
    assert is_historical_document("2026-10-30") is False


def test_is_historical_document_none_or_malformed() -> None:
    assert is_historical_document(None) is False
    assert is_historical_document("") is False
    assert is_historical_document("not-a-date") is False


def test_get_status_badge_supported() -> None:
    badge, alert = get_status_badge("supported")
    assert "Supported" in badge
    assert alert == "success"


def test_get_status_badge_out_of_scope() -> None:
    badge, alert = get_status_badge("out_of_scope")
    assert "Out of Scope" in badge
    assert alert == "error"


def test_get_status_badge_insufficient_evidence() -> None:
    badge, alert = get_status_badge("insufficient_evidence")
    assert "Insufficient Evidence" in badge
    assert alert == "warning"


def test_get_status_badge_unknown_fallback() -> None:
    badge, alert = get_status_badge("unknown_status")
    assert alert == "warning"


def test_load_registry_real_file() -> None:
    """Load actual repository scheme registry and verify verified schemes."""
    registry = load_registry(Path("data/scheme_registry.json"))
    assert isinstance(registry, dict)
    assert len(registry) >= 4
    assert "central_pm_kisan" in registry
    assert "central_pmjay" in registry
    assert "central_pm_vishwakarma" in registry
    assert "central_sukanya_samriddhi" in registry

    kisan = registry["central_pm_kisan"]
    assert kisan["verification_status"] == "verified_digital_text"
    assert is_historical_document(kisan["publication_or_effective_date"]) is True


def test_load_registry_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.json"
    result = load_registry(missing)
    assert result == {}


def test_load_registry_invalid_json(tmp_path: Path) -> None:
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not valid json", encoding="utf-8")
    result = load_registry(bad_json)
    assert result == {}


def test_mocked_answer_builder_integration() -> None:
    """Mock AnswerBuilder and verify response schema consumed by UI."""
    from src.retrieval.answer import AnswerResponse, EvidencePassage

    mock_builder = MagicMock()
    mock_builder.answer.return_value = AnswerResponse(
        query="What does PM-KISAN provide?",
        status="supported",
        detected_scheme_id="central_pm_kisan",
        passages=[
            EvidencePassage(
                chunk_id="chunk_1",
                scheme_id="central_pm_kisan",
                source_document="pm_kisan.pdf",
                official_source_url="https://pmkisan.gov.in/doc.pdf",
                page_number=2,
                chunk_index=1,
                document_version="2020-03-29",
                passage_text="With a view to provide income support...",
                distance=0.5159,
                similarity_score=0.4841,
                rerank_score=0.7041,
            )
        ],
    )

    resp = mock_builder.answer("What does PM-KISAN provide?")
    assert resp.status == "supported"
    assert len(resp.passages) == 1
    p = resp.passages[0]
    assert p.rerank_score == 0.7041
    assert p.distance == 0.5159
    assert p.source_document == "pm_kisan.pdf"
    assert resp.eligibility_assessed is False
