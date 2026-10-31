"""Unit tests for streamlit_app helper functions."""

from pathlib import Path

from streamlit_app import (
    filter_schemes,
    get_status_info,
    is_valid_http_url,
    load_scheme_registry,
)


def test_is_valid_http_url() -> None:
    assert is_valid_http_url("https://pmkisan.gov.in/doc.pdf") is True
    assert is_valid_http_url("http://example.com/test") is True

    # Invalid URLs
    assert is_valid_http_url(None) is False
    assert is_valid_http_url("") is False
    assert is_valid_http_url("ftp://example.com/file") is False
    assert is_valid_http_url("not a url") is False
    assert is_valid_http_url("https://user:pass@example.com") is False
    assert is_valid_http_url("https://example .com") is False


def test_load_scheme_registry_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.json"
    assert load_scheme_registry(missing) is None


def test_load_scheme_registry_invalid_json(tmp_path: Path) -> None:
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{broken json", encoding="utf-8")
    assert load_scheme_registry(bad_json) is None


def test_load_scheme_registry_missing_schemes_key(tmp_path: Path) -> None:
    no_schemes = tmp_path / "no_schemes.json"
    no_schemes.write_text('{"version": "1.0"}', encoding="utf-8")
    assert load_scheme_registry(no_schemes) is None


def test_load_scheme_registry_valid(tmp_path: Path) -> None:
    valid_file = tmp_path / "registry.json"
    valid_file.write_text('{"schemes": [{"scheme_id": "test"}]}', encoding="utf-8")
    data = load_scheme_registry(valid_file)
    assert data is not None
    assert len(data["schemes"]) == 1


def test_get_status_info() -> None:
    info_ready = get_status_info("verified_digital_text")
    assert info_ready["category"] == "ready"

    info_scanned = get_status_info("verified_scanned_image")
    assert info_scanned["category"] == "needs_ocr"

    info_legacy = get_status_info("verified_legacy_font_mapped")
    assert info_legacy["category"] == "needs_font_mapping"

    info_unresolved = get_status_info("unresolved")
    assert info_unresolved["category"] == "unresolved"

    info_unknown = get_status_info("non_existent_status")
    assert info_unknown["category"] == "unknown"


def test_filter_schemes() -> None:
    sample_schemes = [
        {
            "scheme_id": "central_pm_kisan",
            "scheme_name": "PM-KISAN",
            "jurisdiction": "central",
            "issuing_authority": "Ministry of Agriculture",
            "notes": "Farmer income support scheme.",
            "verification_status": "verified_digital_text",
        },
        {
            "scheme_id": "karnataka_gruha_lakshmi",
            "scheme_name": "Gruha Lakshmi Scheme",
            "jurisdiction": "state",
            "issuing_authority": "Karnataka WCD",
            "notes": "Financial assistance to women head of family.",
            "verification_status": "verified_legacy_font_mapped",
        },
        {
            "scheme_id": "karnataka_sandhya_suraksha",
            "scheme_name": "Sandhya Suraksha Yojana",
            "jurisdiction": "state",
            "issuing_authority": "Karnataka Revenue Dept",
            "notes": "Senior citizen pension.",
            "verification_status": "unresolved",
        },
    ]

    base_profile = {"filter_active": False}

    # 1. Search text
    results = filter_schemes(sample_schemes, "farmer", "All", "All", base_profile)
    assert len(results) == 1
    assert results[0]["scheme_id"] == "central_pm_kisan"

    # 2. Jurisdiction filter
    results_central = filter_schemes(
        sample_schemes, "", "Central Government", "All", base_profile
    )
    assert len(results_central) == 1
    assert results_central[0]["scheme_id"] == "central_pm_kisan"

    results_state = filter_schemes(
        sample_schemes, "", "Karnataka State", "All", base_profile
    )
    assert len(results_state) == 2

    # 3. Readiness filter
    results_ready = filter_schemes(
        sample_schemes, "", "All", "Ready for Digital Search", base_profile
    )
    assert len(results_ready) == 1
    assert results_ready[0]["scheme_id"] == "central_pm_kisan"

    results_needs_ocr = filter_schemes(
        sample_schemes, "", "All", "Needs OCR / Legacy Font", base_profile
    )
    assert len(results_needs_ocr) == 1
    assert results_needs_ocr[0]["scheme_id"] == "karnataka_gruha_lakshmi"

    results_unres = filter_schemes(
        sample_schemes, "", "All", "Unresolved Source", base_profile
    )
    assert len(results_unres) == 1
    assert results_unres[0]["scheme_id"] == "karnataka_sandhya_suraksha"
