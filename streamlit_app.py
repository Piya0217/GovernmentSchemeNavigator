"""Government Scheme Navigator - Streamlit Demo.

A lightweight, honest, and verifiable public interface for discovering
Indian government welfare schemes and exploring authoritative source documents.

Safety & Integrity Rule (AGENTS.md):
- Eligibility decisions are NEVER hallucinated by an LLM.
- All schemes explicitly display "Eligibility not yet assessed" pending
  Phase 2 deterministic rules engine integration.
- Documents that are scanned images, legacy-font encoded, or unresolved
  are marked as NOT ready for digital search.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import streamlit as st

logger = logging.getLogger("scheme_navigator.streamlit")

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------

PAGE_TITLE = "Government Scheme Navigator"
PAGE_ICON = "🇮🇳"
REGISTRY_PATH = Path(__file__).resolve().parent / "data" / "scheme_registry.json"

ELIGIBILITY_STATUS_PENDING = "Eligibility not yet assessed"

DOCUMENT_STATUS_CONFIG: dict[str, dict[str, str]] = {
    "verified_digital_text": {
        "label": "Ready for Digital Search",
        "badge": "🟢 Digital PDF Verified",
        "category": "ready",
        "explanation": (
            "Authoritative digital PDF verified and chunked with clean text."
        ),
    },
    "verified_scanned_image": {
        "label": "Not Ready: Scanned Image",
        "badge": "🟠 Scanned Image Only",
        "category": "needs_ocr",
        "explanation": (
            "Scanned document containing no digital text. Requires OCR extraction."
        ),
    },
    "verified_legacy_font_mapped": {
        "label": "Not Ready: Legacy Font",
        "badge": "🟠 Legacy Font (Non-Unicode)",
        "category": "needs_font_mapping",
        "explanation": (
            "Uses non-Unicode legacy Kannada font glyphs. Requires font "
            "remapping or OCR."
        ),
    },
    "unresolved": {
        "label": "Not Ready: Unresolved Source",
        "badge": "🔴 Source Unresolved",
        "category": "unresolved",
        "explanation": (
            "No publicly verifiable standalone government PDF found on portal."
        ),
    },
}


def is_valid_http_url(url: str | None) -> bool:
    """Validate that a URL is a well-formed HTTP/HTTPS address."""
    if not url or not isinstance(url, str):
        return False
    url_stripped = url.strip()
    if any(ch.isspace() for ch in url_stripped):
        return False
    try:
        parsed = urlsplit(url_stripped)
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.netloc)
            and parsed.username is None
            and parsed.password is None
        )
    except Exception:
        return False


def load_scheme_registry(path: Path) -> dict[str, Any] | None:
    """Load and validate the scheme registry file gracefully."""
    if not path.is_file():
        logger.error("Registry file not found at path: %s", path)
        return None

    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        if not isinstance(data, dict) or "schemes" not in data:
            logger.error("Registry file missing top-level 'schemes' key")
            return None
        if not isinstance(data["schemes"], list):
            logger.error("'schemes' in registry is not a list")
            return None
        return data
    except (json.JSONDecodeError, OSError) as err:
        logger.error("Failed to read or parse scheme registry: %s", err)
        return None


def get_status_info(status_key: str | None) -> dict[str, str]:
    """Return presentation metadata for a given document verification status."""
    if not status_key or status_key not in DOCUMENT_STATUS_CONFIG:
        return {
            "label": "Not Ready: Unverified",
            "badge": "⚪ Status Unknown",
            "category": "unknown",
            "explanation": "Document status has not been confirmed.",
        }
    return DOCUMENT_STATUS_CONFIG[status_key]


# ---------------------------------------------------------------------------
# Streamlit Application
# ---------------------------------------------------------------------------


def render_header() -> None:
    """Render the top banner and mission statement."""
    st.title(PAGE_TITLE)
    st.caption(
        "Multilingual assistant for discovering Indian government welfare schemes "
        "and exploring verified official guidelines."
    )

    # Prominent Deterministic Safety Callout (AGENTS.md)
    st.info(
        "ℹ️ **Safety Notice & Rules Engine Status**: "
        "All eligibility determinations in this system are strictly deterministic and "
        "auditable. LLMs are **never** permitted to decide eligibility. "
        "Because the deterministic rules engine is scheduled for Phase 2, "
        "**all schemes currently display 'Eligibility not yet assessed'.**"
    )


def render_profile_sidebar() -> dict[str, Any]:
    """Render the demonstration user profile form in the sidebar."""
    with st.sidebar:
        st.header("👤 Citizen Profile")
        st.caption(
            "Preview of future personalized scheme discovery. "
            "Profile criteria will be evaluated against verified rules in Phase 2."
        )

        age = st.number_input("Age", min_value=0, max_value=120, value=30, step=1)
        state = st.selectbox(
            "State / UT of Residence",
            options=[
                "Karnataka",
                "All India / Central",
                "Andhra Pradesh",
                "Maharashtra",
                "Tamil Nadu",
                "Uttar Pradesh",
                "Other State / UT",
            ],
            index=0,
        )
        occupation = st.selectbox(
            "Occupation / Category",
            options=[
                "Any / General",
                "Farmer / Agricultural Worker",
                "Traditional Artisan / Craftsman (Vishwakarma)",
                "Woman Head of Household",
                "Senior Citizen (60+)",
                "Self-Employed / Small Business",
                "Student / Youth",
            ],
            index=0,
        )

        apply_profile_filter = st.checkbox(
            "Filter schemes relevant to this profile (Demo)",
            value=False,
            help="Filters visible schemes by matching state or target category.",
        )

        st.divider()
        st.markdown(
            "**Transparency Guarantee**:\n"
            "- No eligibility decisions are made without verified statutory rules.\n"
            "- Missing profile inputs will never result in false-positive eligibility."
        )

    return {
        "age": age,
        "state": state,
        "occupation": occupation,
        "filter_active": apply_profile_filter,
    }


def filter_schemes(
    schemes: list[dict[str, Any]],
    search_query: str,
    jurisdiction_filter: str,
    readiness_filter: str,
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    """Filter schemes based on user inputs, search keywords, and profile."""
    filtered: list[dict[str, Any]] = []

    for item in schemes:
        if not isinstance(item, dict):
            continue

        name = str(item.get("scheme_name", ""))
        jurisdiction = str(item.get("jurisdiction", "")).lower()
        issuing = str(item.get("issuing_authority", ""))
        notes = str(item.get("notes", ""))
        status = str(item.get("verification_status", ""))
        status_info = get_status_info(status)

        # 1. Text search filter
        if search_query:
            query = search_query.lower()
            haystack = f"{name} {issuing} {notes}".lower()
            if query not in haystack:
                continue

        # 2. Jurisdiction filter
        if jurisdiction_filter == "Central Government" and jurisdiction != "central":
            continue
        if jurisdiction_filter == "Karnataka State" and jurisdiction != "state":
            continue

        # 3. Document Readiness filter
        if (
            readiness_filter == "Ready for Digital Search"
            and status_info["category"] != "ready"
        ):
            continue
        if readiness_filter == "Needs OCR / Legacy Font" and status_info[
            "category"
        ] not in {"needs_ocr", "needs_font_mapping"}:
            continue
        if (
            readiness_filter == "Unresolved Source"
            and status_info["category"] != "unresolved"
        ):
            continue

        # 4. Optional profile-based match filter
        if profile.get("filter_active"):
            user_state = profile.get("state")
            user_occ = profile.get("occupation")

            # State check: If scheme is state-specific and user state is not Karnataka
            if jurisdiction == "state" and user_state != "Karnataka":
                continue

            # Occupation heuristic for demonstration
            if (
                user_occ == "Farmer / Agricultural Worker"
                and "kisan" not in name.lower()
                and jurisdiction != "state"
            ):
                continue
            if (
                user_occ == "Traditional Artisan / Craftsman (Vishwakarma)"
                and "vishwakarma" not in name.lower()
            ):
                continue
            if (
                user_occ == "Woman Head of Household"
                and "lakshmi" not in name.lower()
                and "ujjwala" not in name.lower()
                and "sukanya" not in name.lower()
            ):
                continue
            if user_occ == "Senior Citizen (60+)" and "sandhya" not in name.lower():
                continue

        filtered.append(item)

    return filtered


def render_scheme_card(scheme: dict[str, Any]) -> None:
    """Render an individual scheme card with status, links, and disclaimers."""
    scheme_name = scheme.get("scheme_name") or "Unnamed Scheme"
    scheme_id = scheme.get("scheme_id") or "unknown_id"
    jurisdiction = str(scheme.get("jurisdiction", "central")).capitalize()
    issuing = scheme.get("issuing_authority") or "Authority not specified"
    doc_title = scheme.get("document_title") or "Document title unavailable"
    pub_date = scheme.get("publication_or_effective_date") or "Date not specified"
    notes = scheme.get("notes") or "No description available."
    warnings = scheme.get("warnings") or []
    status_key = scheme.get("verification_status")
    status_info = get_status_info(status_key)

    official_doc_url = scheme.get("official_source_url")
    portal_url = scheme.get("portal_url")

    with st.container(border=True):
        col_title, col_badges = st.columns([3, 2])
        with col_title:
            st.subheader(scheme_name)
            st.caption(
                f"**Issuing Authority**: {issuing} | **Jurisdiction**: {jurisdiction}"
            )

        with col_badges:
            st.markdown(f"**Document Status**: `{status_info['badge']}`")
            st.markdown(f"**Eligibility**: ⚠️ **{ELIGIBILITY_STATUS_PENDING}**")

        # Status warning if not ready for digital search
        if status_info["category"] != "ready":
            st.warning(
                f"⚠️ **Not ready for searchable content**: {status_info['explanation']}"
            )

        # Metadata details inside an expander
        with st.expander("📄 Document Details & Official Sources", expanded=False):
            st.markdown(f"**Document Title**: {doc_title}")
            st.markdown(f"**Effective / Publication Date**: {pub_date}")
            st.markdown(f"**Scheme ID**: `{scheme_id}`")
            st.markdown(f"**Overview / Notes**: {notes}")

            if warnings:
                st.markdown("**Ingestion Warnings:**")
                for w in warnings:
                    st.markdown(f"- ⚠️ {w}")

            st.markdown("---")
            col_link1, col_link2 = st.columns(2)
            with col_link1:
                if is_valid_http_url(official_doc_url):
                    st.markdown(
                        f"🔗 [Download Official Document PDF]({official_doc_url})"
                    )
                else:
                    st.markdown(
                        "🔗 *Official document PDF not publicly available on open "
                        "endpoint.*"
                    )

            with col_link2:
                if is_valid_http_url(portal_url):
                    st.markdown(f"🌐 [Visit Official Scheme Portal]({portal_url})")
                else:
                    st.markdown("🌐 *Portal URL unavailable.*")


def main() -> None:
    """Main application execution flow."""
    render_header()
    profile = render_profile_sidebar()

    # Load registry
    registry_data = load_scheme_registry(REGISTRY_PATH)
    if registry_data is None:
        st.error(
            f"❌ Unable to load scheme registry from `{REGISTRY_PATH.name}`. "
            "Please ensure `data/scheme_registry.json` is present and valid."
        )
        st.stop()

    schemes = registry_data.get("schemes", [])
    if not schemes:
        st.warning("⚠️ No schemes are currently recorded in the registry.")
        st.stop()

    st.subheader(f"📚 Schemes Directory ({len(schemes)} Tracked Schemes)")

    # Filter controls
    col_search, col_jur, col_readiness = st.columns([2, 1, 1])
    with col_search:
        search_query = st.text_input(
            "Search Schemes",
            placeholder="Type scheme name, keyword (e.g. kisan, farmer, health)...",
            label_visibility="collapsed",
        )
    with col_jur:
        jurisdiction_filter = st.selectbox(
            "Filter Jurisdiction",
            options=["All", "Central Government", "Karnataka State"],
            label_visibility="collapsed",
        )
    with col_readiness:
        readiness_filter = st.selectbox(
            "Filter Readiness",
            options=[
                "All",
                "Ready for Digital Search",
                "Needs OCR / Legacy Font",
                "Unresolved Source",
            ],
            label_visibility="collapsed",
        )

    # Compute matches
    matched_schemes = filter_schemes(
        schemes=schemes,
        search_query=search_query,
        jurisdiction_filter=jurisdiction_filter,
        readiness_filter=readiness_filter,
        profile=profile,
    )

    if profile.get("filter_active"):
        occ = profile["occupation"]
        stt = profile["state"]
        st.info(
            f"🎯 Demonstrating profile filter for: **{occ}** in **{stt}**. "
            "Showing matching subset. (Eligibility is not assessed)."
        )

    st.markdown(f"Showing **{len(matched_schemes)}** of **{len(schemes)}** schemes")

    if not matched_schemes:
        st.info(
            "🔍 No schemes matched your current filters. "
            "Try resetting the search or filters."
        )
    else:
        for scheme in matched_schemes:
            render_scheme_card(scheme)

    # Footer
    st.divider()
    st.caption(
        "Government Scheme Navigator • Deterministic & auditable citizen assistance • "
        "Source data: Official Government of India & Government of Karnataka portals."
    )


if __name__ == "__main__":
    main()
