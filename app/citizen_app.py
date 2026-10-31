"""Citizen-facing Streamlit experience backed by the FastAPI application."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import streamlit as st
from dotenv import load_dotenv

from app.api_client import ApiClientError, GovernmentSchemeApiClient
from app.translations import translate

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

VERIFICATION_TRANSLATIONS = {
    "verified_digital_text": "status_digital",
    "verified_scanned_image": "status_scan",
    "verified_legacy_font_mapped": "status_legacy",
    "unresolved": "status_unresolved",
}
VERIFICATION_STATUSES = tuple(VERIFICATION_TRANSLATIONS)


@st.cache_resource
def get_api_client() -> GovernmentSchemeApiClient:
    """Create a shared HTTP client for the configured backend."""
    return GovernmentSchemeApiClient(API_BASE_URL)


def _is_official_http_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme in {"https", "http"} and bool(parsed.netloc)


def _has_citation_metadata(passage: object) -> bool:
    """Require source text and page-level provenance before rendering evidence."""
    if not isinstance(passage, dict):
        return False
    source_document = passage.get("source_document")
    page_number = passage.get("page_number")
    passage_text = passage.get("passage_text")
    return (
        isinstance(source_document, str)
        and bool(source_document.strip())
        and isinstance(page_number, int)
        and not isinstance(page_number, bool)
        and page_number >= 1
        and isinstance(passage_text, str)
        and bool(passage_text.strip())
        and _is_official_http_url(passage.get("official_source_url"))
    )


def _has_rule_citation(citation: object) -> bool:
    """Require the complete provenance fields before displaying a rule citation."""
    if not isinstance(citation, dict):
        return False
    page_number = citation.get("page_number")
    return (
        isinstance(citation.get("document_id"), str)
        and bool(citation["document_id"].strip())
        and isinstance(citation.get("document_version"), str)
        and bool(citation["document_version"].strip())
        and isinstance(page_number, int)
        and not isinstance(page_number, bool)
        and page_number >= 1
        and _is_official_http_url(citation.get("source_url"))
    )


def _show_error(error: ApiClientError, language: str) -> None:
    if error.code == "retrieval_unavailable":
        message = translate(language, "retrieval_unavailable")
    elif error.code == "scheme_not_found" or error.status_code == 404:
        message = translate(language, "unknown_scheme")
    elif error.code == "eligibility_engine_unavailable":
        message = translate(language, "eligibility_unavailable")
    elif error.code in {"api_unavailable", "timeout"} or (
        error.status_code is not None and error.status_code >= 500
    ):
        message = translate(language, "backend_unavailable")
    elif error.status_code == 422:
        message = translate(language, "invalid_input")
    else:
        message = str(error)
    st.error(message)


def _scheme_option_label(scheme: dict[str, Any], language: str) -> str:
    name = scheme.get("scheme_name", scheme.get("scheme_id", ""))
    status_key = VERIFICATION_TRANSLATIONS.get(
        scheme.get("verification_status"), "status_unknown"
    )
    return f"{name} ({translate(language, status_key)})"


def render_schemes(api: GovernmentSchemeApiClient, language: str) -> None:
    st.subheader(translate(language, "schemes"))
    with st.form("scheme_search_form"):
        query = st.text_input(translate(language, "search"), max_chars=200)
        jurisdiction_label = st.selectbox(
            translate(language, "jurisdiction"),
            [
                translate(language, "all_jurisdictions"),
                translate(language, "central"),
                translate(language, "state"),
            ],
        )
        verification_labels = [translate(language, "all_verification")] + [
            translate(language, VERIFICATION_TRANSLATIONS[status])
            for status in VERIFICATION_STATUSES
        ]
        verification_label = st.selectbox(
            translate(language, "verification_filter"), verification_labels
        )
        submitted = st.form_submit_button(translate(language, "search_button"))

    jurisdiction_map = {
        translate(language, "central"): "central",
        translate(language, "state"): "state",
    }
    jurisdiction = jurisdiction_map.get(jurisdiction_label)
    verification_status = None
    if verification_label != verification_labels[0]:
        verification_status = next(
            (
                status
                for status in VERIFICATION_STATUSES
                if translate(language, VERIFICATION_TRANSLATIONS[status])
                == verification_label
            ),
            None,
        )
    try:
        result = api.list_schemes(
            query=query.strip() or None,
            jurisdiction=jurisdiction if submitted or jurisdiction else None,
            verification_status=verification_status,
        )
    except ApiClientError as error:
        _show_error(error, language)
        return

    schemes = result.get("schemes")
    if not isinstance(schemes, list):
        st.error(translate(language, "invalid_response"))
        return
    if not schemes:
        st.info(translate(language, "no_schemes"))
        return
    st.caption(translate(language, "registry_vs_index"))

    for scheme in schemes:
        if not isinstance(scheme, dict):
            continue
        with st.container(border=True):
            st.markdown(f"### {scheme.get('scheme_name', '—')}")
            st.write(
                f"**{translate(language, 'authority')}:** "
                f"{scheme.get('issuing_authority', '—')}"
            )
            verification = scheme.get("verification_status", "")
            verification_key = VERIFICATION_TRANSLATIONS.get(
                verification, "status_unknown"
            )
            st.caption(
                f"{translate(language, 'verification')}: "
                f"{translate(language, verification_key)}"
            )
            official_url = scheme.get("official_source_url")
            if _is_official_http_url(official_url):
                st.link_button(translate(language, "open_source"), official_url)
            elif scheme.get("portal_url") and _is_official_http_url(
                scheme["portal_url"]
            ):
                st.link_button(translate(language, "source"), scheme["portal_url"])
            if verification != "verified_digital_text":
                st.caption(translate(language, "not_searchable"))


def render_question(api: GovernmentSchemeApiClient, language: str) -> None:
    st.subheader(translate(language, "ask_heading"))
    st.caption(translate(language, "informational_only"))
    try:
        scheme_response = api.list_schemes()
    except ApiClientError:
        st.warning(translate(language, "backend_unavailable"))
        scheme_response = {"schemes": []}
    schemes = scheme_response.get("schemes", [])
    if not isinstance(schemes, list):
        st.warning(translate(language, "invalid_response"))
        schemes = []

    known_schemes = [scheme for scheme in schemes if isinstance(scheme, dict)]
    options = [translate(language, "all_schemes")] + [
        _scheme_option_label(scheme, language) for scheme in known_schemes
    ]
    selected = st.selectbox(translate(language, "scheme_filter"), options)
    selected_id = None
    if selected != options[0]:
        selected_id = next(
            (
                str(item["scheme_id"])
                for item, label in zip(known_schemes, options[1:], strict=True)
                if label == selected
            ),
            None,
        )
    st.caption(translate(language, "registry_vs_index"))

    with st.form("question_form"):
        question = st.text_area(
            translate(language, "question"),
            max_chars=2000,
            height=100,
        )
        submitted = st.form_submit_button(
            translate(language, "submit_question"), type="primary"
        )
    if not submitted:
        return
    if not question.strip():
        st.warning(translate(language, "abstention"))
        return

    try:
        with st.spinner(translate(language, "submit_question")):
            answer = api.ask(question.strip(), selected_id)
    except ApiClientError as error:
        _show_error(error, language)
        return
    _render_answer(answer, language)


def _render_answer(answer: dict[str, Any], language: str) -> None:
    status = answer.get("status")
    status_labels = {
        "supported": "supported",
        "insufficient_evidence": "insufficient",
        "out_of_scope": "out_of_scope",
    }
    localized_status = status_labels.get(status)
    if localized_status is None:
        st.error(translate(language, "invalid_response"))
        return
    if status == "supported":
        st.success(translate(language, localized_status))
    elif status == "out_of_scope":
        st.warning(translate(language, localized_status))
    else:
        st.info(translate(language, localized_status))

    passages = answer.get("passages", [])
    if not isinstance(passages, list):
        st.error(translate(language, "invalid_response"))
        return
    if status == "supported" and not passages:
        st.error(translate(language, "invalid_response"))
        return
    if status != "supported" and passages:
        st.error(translate(language, "invalid_response"))
        return
    if not passages:
        return

    st.markdown(f"**{translate(language, 'evidence')}**")
    for passage in passages:
        if not _has_citation_metadata(passage):
            st.error(translate(language, "invalid_response"))
            return
        with st.container(border=True):
            st.write(passage.get("passage_text", ""))
            source = passage.get("source_document", "—")
            page = passage.get("page_number", "—")
            st.caption(
                f"{translate(language, 'document')}: {source} · "
                f"{translate(language, 'page')}: {page}"
            )
            version = passage.get("document_version")
            if version:
                st.caption(f"{translate(language, 'version')}: {version}")
            url = passage.get("official_source_url")
            if _is_official_http_url(url):
                st.link_button(translate(language, "open_source"), url)


def _profile_from_form(values: dict[str, str]) -> dict[str, int | float | str | None]:
    """Convert the Phase 3 profile fields without guessing missing values."""
    profile: dict[str, int | float | str | None] = {}
    for key in ("age", "household_size"):
        raw = values[key].strip()
        profile[key] = int(raw) if raw else None
    raw_income = values["annual_income"].strip()
    profile["annual_income"] = float(raw_income) if raw_income else None
    for key in ("occupation", "state", "district", "gender"):
        profile[key] = values[key].strip() or None
    return profile


def render_eligibility(
    api: GovernmentSchemeApiClient,
    health: dict[str, Any] | None,
    language: str,
) -> None:
    """Collect optional Phase 3 profile fields and display the API result."""
    st.subheader(translate(language, "eligibility"))
    if health is None:
        st.warning(translate(language, "backend_unavailable"))
    elif health.get("eligibility") != "ready":
        st.caption(translate(language, "eligibility_not_configured"))
    st.caption(translate(language, "privacy"))
    try:
        schemes = api.list_schemes().get("schemes", [])
    except ApiClientError as error:
        _show_error(error, language)
        return
    if not isinstance(schemes, list):
        st.error(translate(language, "invalid_response"))
        return
    schemes = [item for item in schemes if isinstance(item, dict)]
    if not schemes:
        st.info(translate(language, "no_schemes"))
        return

    labels = [_scheme_option_label(item, language) for item in schemes]
    with st.form("eligibility_form", clear_on_submit=True):
        selected = st.selectbox(translate(language, "scheme_filter"), labels)
        st.caption(translate(language, "profile_optional"))
        values = {
            "age": st.text_input(translate(language, "profile_age")),
            "annual_income": st.text_input(translate(language, "profile_income")),
            "occupation": st.text_input(translate(language, "profile_occupation")),
            "state": st.text_input(translate(language, "profile_state")),
            "district": st.text_input(translate(language, "profile_district")),
            "gender": st.text_input(translate(language, "profile_gender")),
            "household_size": st.text_input(
                translate(language, "profile_household_size")
            ),
        }
        submitted = st.form_submit_button(
            translate(language, "check_eligibility"), type="primary"
        )
    if not submitted:
        return

    selected_scheme = schemes[labels.index(selected)]
    try:
        profile = _profile_from_form(values)
    except ValueError:
        st.error(translate(language, "invalid_input"))
        return
    try:
        with st.spinner(translate(language, "checking_eligibility")):
            result = api.check_eligibility(str(selected_scheme["scheme_id"]), profile)
    except ApiClientError as error:
        _show_error(error, language)
        return
    _render_eligibility_result(result, language)


def _render_eligibility_result(result: dict[str, Any], language: str) -> None:
    """Render only the deterministic API result and its supplied citations."""
    labels = {
        "eligible": "result_eligible",
        "ineligible": "result_ineligible",
        "needs_more_information": "result_more_information",
        "unsupported_scheme": "result_unsupported",
    }
    key = labels.get(result.get("status"))
    if key is None:
        st.error(translate(language, "invalid_response"))
        return
    status = result["status"]
    if status == "eligible":
        st.success(translate(language, key))
    elif status == "ineligible":
        st.error(translate(language, key))
    else:
        st.info(translate(language, key))
    st.write(result.get("explanation", ""))
    missing = result.get("missing_fields", [])
    if isinstance(missing, list) and missing:
        st.warning(
            f"{translate(language, 'missing_information')}: "
            + ", ".join(str(field) for field in missing)
        )
    evaluations = result.get("rule_evaluations", [])
    if not isinstance(evaluations, list):
        st.error(translate(language, "invalid_response"))
        return
    for evaluation in evaluations:
        if not isinstance(evaluation, dict):
            continue
        citation = evaluation.get("citation")
        with st.container(border=True):
            st.markdown(
                f"**{evaluation.get('rule_id', '—')} · "
                f"{evaluation.get('outcome', '—')}**"
            )
            st.write(evaluation.get("reason", ""))
            if _has_rule_citation(citation):
                st.caption(
                    f"{citation.get('document_id', '—')} · "
                    f"{translate(language, 'page')}: "
                    f"{citation.get('page_number', '—')} · "
                    f"{translate(language, 'version')}: "
                    f"{citation.get('document_version', '—')}"
                )
                url = citation.get("source_url")
                if _is_official_http_url(url):
                    st.link_button(translate(language, "open_source"), url)


def main() -> None:
    """Render the citizen application in English or Kannada."""
    st.set_page_config(page_title="Government Scheme Navigator", page_icon="🇮🇳")
    language_choice = st.sidebar.selectbox(
        "Language / ಭಾಷೆ",
        ["English", "ಕನ್ನಡ"],
        key="interface_language",
    )
    language = "kn" if language_choice == "ಕನ್ನಡ" else "en"
    st.title(translate(language, "title"))
    st.caption(translate(language, "tagline"))

    api = get_api_client()
    try:
        health = api.health()
        if health.get("retrieval") != "ready":
            st.warning(translate(language, "retrieval_unavailable"))
    except ApiClientError:
        st.warning(translate(language, "backend_unavailable"))

    section = st.sidebar.radio(
        translate(language, "navigation"),
        [
            translate(language, "schemes"),
            translate(language, "questions"),
            translate(language, "eligibility"),
        ],
    )
    if section == translate(language, "schemes"):
        render_schemes(api, language)
    elif section == translate(language, "questions"):
        render_question(api, language)
    else:
        render_eligibility(api, health, language)


if __name__ == "__main__":
    main()
