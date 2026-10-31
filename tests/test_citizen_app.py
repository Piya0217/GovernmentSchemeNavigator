"""Streamlit smoke tests with a fake backend client."""

from __future__ import annotations

from pathlib import Path

import app.api_client as api_client_module
from streamlit.testing.v1 import AppTest


class _FakeApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def health(self) -> dict[str, str]:
        return {"retrieval": "ready", "eligibility": "not_configured"}

    def list_schemes(self, **kwargs: str) -> dict[str, object]:
        return {
            "schemes": [
                {
                    "scheme_id": "central_pm_kisan",
                    "scheme_name": "PM-KISAN",
                    "jurisdiction": "central",
                    "issuing_authority": "Government of India",
                    "official_source_url": "https://example.gov/pm-kisan.pdf",
                    "verification_status": "verified_digital_text",
                }
            ]
        }

    def ask(self, query: str, scheme_id: str | None = None) -> dict[str, object]:
        return {
            "query": query,
            "status": "supported",
            "passages": [
                {
                    "scheme_id": "central_pm_kisan",
                    "source_document": "pm_kisan_guidelines.pdf",
                    "official_source_url": "https://example.gov/pm-kisan.pdf",
                    "page_number": 5,
                    "document_version": "2020-03-29",
                    "chunk_id": "central_pm_kisan_p5_c0",
                    "chunk_index": 0,
                    "passage_text": "Verbatim official evidence.",
                    "distance": 0.1,
                    "similarity_score": 0.9,
                    "rerank_score": 0.8,
                }
            ],
            "eligibility_assessed": False,
            "abstention_reason": None,
        }

    def check_eligibility(
        self, scheme_id: str, profile: dict[str, str | int | float | None]
    ) -> dict[str, object]:
        return {
            "scheme_id": scheme_id,
            "status": "needs_more_information",
            "outcome": "NEEDS_MORE_INFORMATION",
            "eligible": False,
            "explanation": "Outcome requires the missing age field.",
            "missing_fields": ["age"],
            "rule_evaluations": [
                {
                    "rule_id": "test-rule",
                    "outcome": "UNEVALUABLE",
                    "reason": "Missing profile field 'age'.",
                    "citation": {
                        "document_id": "guidelines.pdf",
                        "source_url": "https://example.gov/guidelines.pdf",
                        "page_number": 5,
                        "document_version": "test-v1",
                    },
                }
            ],
        }

    def close(self) -> None:
        return None


def test_citizen_app_renders_in_english_and_kannada(monkeypatch) -> None:
    monkeypatch.setattr(
        api_client_module,
        "GovernmentSchemeApiClient",
        _FakeApiClient,
    )
    app_path = Path(__file__).resolve().parents[1] / "app" / "citizen_app.py"
    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    assert not app.exception
    assert app.title[0].value == "Government Scheme Navigator"

    language_picker = next(
        picker for picker in app.selectbox if picker.label == "Language / ಭಾಷೆ"
    )
    language_picker.select("ಕನ್ನಡ").run()

    assert not app.exception
    assert app.title[0].value == "ಸರ್ಕಾರಿ ಯೋಜನೆಗಳ ಮಾರ್ಗದರ್ಶಿ"
    assert "ಯೋಜನೆಗಳನ್ನು ಹುಡುಕಿ" in [item.value for item in app.subheader]


def test_citizen_app_displays_api_evidence_with_its_page_citation(monkeypatch) -> None:
    monkeypatch.setattr(
        api_client_module,
        "GovernmentSchemeApiClient",
        _FakeApiClient,
    )
    app_path = Path(__file__).resolve().parents[1] / "app" / "citizen_app.py"
    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    navigation = next(item for item in app.radio if item.label == "Go to")
    navigation.set_value("Ask a question").run()
    app.text_area[0].set_value("What does PM-KISAN provide?")
    submit = next(item for item in app.button if item.label == "Find official evidence")
    submit.click().run()

    assert not app.exception
    assert any("Verbatim official evidence." in item.value for item in app.markdown)
    assert any("Page: 5" in item.value for item in app.caption)
    assert any(
        "not an official eligibility decision" in item.value for item in app.caption
    )


def test_citizen_app_submits_profile_and_displays_missing_field(monkeypatch) -> None:
    monkeypatch.setattr(
        api_client_module,
        "GovernmentSchemeApiClient",
        _FakeApiClient,
    )
    app_path = Path(__file__).resolve().parents[1] / "app" / "citizen_app.py"
    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    navigation = next(item for item in app.radio if item.label == "Go to")
    navigation.set_value("Eligibility status").run()
    submit = next(item for item in app.button if item.label == "Check eligibility")
    submit.click().run()

    assert not app.exception
    assert any(
        "Eligibility could not be established" in item.value for item in app.info
    )
    assert any("Information needed: age" in item.value for item in app.warning)
    assert any("Page: 5" in item.value for item in app.caption)
