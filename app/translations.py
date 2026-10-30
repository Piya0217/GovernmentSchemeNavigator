"""English and Kannada interface strings."""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Government Scheme Navigator",
        "tagline": "Explore verified government scheme documents and evidence.",
        "language": "Language / ಭಾಷೆ",
        "navigation": "Go to",
        "schemes": "Find schemes",
        "questions": "Ask a question",
        "eligibility": "Eligibility status",
        "search": "Search scheme names",
        "jurisdiction": "Jurisdiction",
        "all_jurisdictions": "All jurisdictions",
        "verification_filter": "Document verification filter",
        "all_verification": "All verification statuses",
        "central": "Central government",
        "state": "State government",
        "search_button": "Search schemes",
        "no_schemes": "No schemes match these filters.",
        "authority": "Issuing authority",
        "verification": "Document verification status",
        "status_digital": "Verified digital text",
        "status_scan": "Verified scan; not digitally searchable",
        "status_legacy": "Verified legacy font; search readiness requires confirmation",
        "status_unresolved": "Source unresolved",
        "status_unknown": "Status unknown",
        "source": "Official source",
        "ask_heading": "Ask about a government scheme",
        "informational_only": (
            "This provides information from scheme documents; it is not an "
            "official eligibility decision."
        ),
        "question": "Your question (English or ಕನ್ನಡ)",
        "scheme_filter": "Limit question to a scheme (optional)",
        "all_schemes": "Search across indexed schemes",
        "submit_question": "Find official evidence",
        "supported": "Evidence found in indexed official documents",
        "insufficient": "There is not enough evidence in the indexed documents.",
        "out_of_scope": "This question is outside the supported scheme information.",
        "abstention": "The retrieval service could not provide a supported answer.",
        "evidence": "Supporting passages",
        "document": "Document",
        "page": "Page",
        "version": "Document version",
        "open_source": "Open cited source document",
        "eligibility_not_configured": (
            "No scheme rule sets are configured yet. The form can be submitted, "
            "but no eligibility decision will be made for unsupported schemes."
        ),
        "profile_optional": (
            "Enter only details you choose to share. Leave unknown fields blank; "
            "the rules engine will request information only when its rules require it."
        ),
        "profile_age": "Age in years (optional)",
        "profile_income": "Annual income (optional)",
        "profile_occupation": "Occupation (optional)",
        "profile_state": "State (optional)",
        "profile_district": "District (optional)",
        "profile_gender": "Gender (optional)",
        "profile_household_size": "Household size (optional)",
        "check_eligibility": "Check eligibility",
        "checking_eligibility": "Checking the deterministic rules…",
        "result_eligible": "The configured rules indicate eligible.",
        "result_ineligible": "The configured rules indicate ineligible.",
        "result_more_information": "Eligibility could not be established yet.",
        "result_unsupported": "No rule set is configured for this scheme.",
        "missing_information": "Information needed",
        "privacy": (
            "Profile information is sent to the API only when you submit this form; "
            "the application does not save it. Do not enter identity numbers."
        ),
        "backend_unavailable": (
            "The service is temporarily unavailable. Try again later."
        ),
        "retrieval_unavailable": "Official document search is currently unavailable.",
        "invalid_response": "The service returned information in an unexpected format.",
        "invalid_input": "Please review the submitted information and try again.",
        "health_ready": "Retrieval service is ready.",
        "health_degraded": "Some services are not ready.",
        "not_searchable": "This registry entry is not confirmed as searchable.",
        "unknown_scheme": "The selected scheme was not found in the registry.",
        "eligibility_unavailable": "Eligibility assessment is not available yet.",
        "registry_vs_index": (
            "Registry membership does not confirm that a document is present in the "
            "current search index."
        ),
    },
    "kn": {
        "title": "ಸರ್ಕಾರಿ ಯೋಜನೆಗಳ ಮಾರ್ಗದರ್ಶಿ",
        "tagline": "ಪರಿಶೀಲಿತ ಸರ್ಕಾರಿ ಯೋಜನೆಗಳ ದಾಖಲೆಗಳು ಮತ್ತು ಸಾಕ್ಷ್ಯವನ್ನು ಅನ್ವೇಷಿಸಿ.",
        "language": "ಭಾಷೆ / Language",
        "navigation": "ವಿಭಾಗಕ್ಕೆ ಹೋಗಿ",
        "schemes": "ಯೋಜನೆಗಳನ್ನು ಹುಡುಕಿ",
        "questions": "ಪ್ರಶ್ನೆ ಕೇಳಿ",
        "eligibility": "ಅರ್ಹತೆ ಸ್ಥಿತಿ",
        "search": "ಯೋಜನೆಯ ಹೆಸರನ್ನು ಹುಡುಕಿ",
        "jurisdiction": "ಆಡಳಿತ ವ್ಯಾಪ್ತಿ",
        "all_jurisdictions": "ಎಲ್ಲಾ ವ್ಯಾಪ್ತಿಗಳು",
        "verification_filter": "ದಾಖಲೆ ಪರಿಶೀಲನೆ ಫಿಲ್ಟರ್",
        "all_verification": "ಎಲ್ಲಾ ಪರಿಶೀಲನಾ ಸ್ಥಿತಿಗಳು",
        "central": "ಕೇಂದ್ರ ಸರ್ಕಾರ",
        "state": "ರಾಜ್ಯ ಸರ್ಕಾರ",
        "search_button": "ಯೋಜನೆಗಳನ್ನು ಹುಡುಕಿ",
        "no_schemes": "ಈ ಫಿಲ್ಟರ್‌ಗಳಿಗೆ ಹೊಂದುವ ಯೋಜನೆಗಳಿಲ್ಲ.",
        "authority": "ಸಂಬಂಧಿತ ಇಲಾಖೆ",
        "verification": "ದಾಖಲೆ ಪರಿಶೀಲನೆ ಸ್ಥಿತಿ",
        "status_digital": "ಪರಿಶೀಲಿತ ಡಿಜಿಟಲ್ ಪಠ್ಯ",
        "status_scan": "ಪರಿಶೀಲಿತ ಸ್ಕ್ಯಾನ್; ಡಿಜಿಟಲ್ ಹುಡುಕಾಟ ಸಾಧ್ಯವಿಲ್ಲ",
        "status_legacy": "ಪರಿಶೀಲಿತ ಹಳೆಯ ಫಾಂಟ್; ಹುಡುಕಾಟ ಸಿದ್ಧತೆ ದೃಢಪಡಿಸಬೇಕು",
        "status_unresolved": "ಮೂಲ ದೃಢವಾಗಿಲ್ಲ",
        "status_unknown": "ಸ್ಥಿತಿ ತಿಳಿದಿಲ್ಲ",
        "source": "ಅಧಿಕೃತ ಮೂಲ",
        "ask_heading": "ಸರ್ಕಾರಿ ಯೋಜನೆಯ ಬಗ್ಗೆ ಕೇಳಿ",
        "informational_only": (
            "ಇದು ಯೋಜನಾ ದಾಖಲೆಗಳ ಮಾಹಿತಿಯನ್ನು ನೀಡುತ್ತದೆ; ಇದು ಅಧಿಕೃತ ಅರ್ಹತಾ ನಿರ್ಧಾರವಲ್ಲ."
        ),
        "question": "ನಿಮ್ಮ ಪ್ರಶ್ನೆ (ಕನ್ನಡ ಅಥವಾ English)",
        "scheme_filter": "ಒಂದು ಯೋಜನೆಗೆ ಮಾತ್ರ ಸೀಮಿತಗೊಳಿಸಿ (ಐಚ್ಛಿಕ)",
        "all_schemes": "ಸೂಚ್ಯಂಕದಲ್ಲಿರುವ ಯೋಜನೆಗಳಲ್ಲಿ ಹುಡುಕಿ",
        "submit_question": "ಅಧಿಕೃತ ಸಾಕ್ಷ್ಯ ಹುಡುಕಿ",
        "supported": "ಸೂಚ್ಯಂಕದಲ್ಲಿರುವ ಅಧಿಕೃತ ದಾಖಲೆಗಳಲ್ಲಿ ಸಾಕ್ಷ್ಯ ದೊರಕಿದೆ",
        "insufficient": "ಸೂಚ್ಯಂಕದ ದಾಖಲೆಗಳಲ್ಲಿ ಸಾಕಷ್ಟು ಸಾಕ್ಷ್ಯವಿಲ್ಲ.",
        "out_of_scope": "ಈ ಪ್ರಶ್ನೆಗೆ ಬೆಂಬಲಿತ ಯೋಜನಾ ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ.",
        "abstention": "ಸಾಕ್ಷ್ಯಾಧಾರಿತ ಉತ್ತರವನ್ನು ಮರುಪಡೆಯಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ.",
        "evidence": "ಆಧಾರಿತ ಭಾಗಗಳು",
        "document": "ದಾಖಲೆ",
        "page": "ಪುಟ",
        "version": "ದಾಖಲೆ ಆವೃತ್ತಿ",
        "open_source": "ಉಲ್ಲೇಖಿಸಿದ ಮೂಲ ದಾಖಲೆ ತೆರೆಯಿರಿ",
        "eligibility_not_configured": (
            "ಯೋಜನೆಗಳಿಗೆ ನಿಯಮ ಸಮೂಹ ಇನ್ನೂ ಹೊಂದಿಸಿಲ್ಲ. ಬೆಂಬಲವಿಲ್ಲದ ಯೋಜನೆಗೆ ಅರ್ಹತಾ ನಿರ್ಧಾರ ನೀಡಲಾಗುವುದಿಲ್ಲ."
        ),
        "profile_optional": (
            "ಹಂಚಿಕೊಳ್ಳಲು ಬಯಸುವ ಮಾಹಿತಿಯನ್ನು ಮಾತ್ರ ನಮೂದಿಸಿ. ತಿಳಿಯದ ವಿವರಗಳನ್ನು ಖಾಲಿ ಬಿಡಿ; "
            "ನಿಯಮಗಳಿಗೆ ಅಗತ್ಯವಿರುವ ಮಾಹಿತಿಯನ್ನು ಮಾತ್ರ ನಿಯಮ ಎಂಜಿನ್ ಕೇಳುತ್ತದೆ."
        ),
        "profile_age": "ವಯಸ್ಸು (ಐಚ್ಛಿಕ)",
        "profile_income": "ವಾರ್ಷಿಕ ಆದಾಯ (ಐಚ್ಛಿಕ)",
        "profile_occupation": "ವೃತ್ತಿ (ಐಚ್ಛಿಕ)",
        "profile_state": "ರಾಜ್ಯ (ಐಚ್ಛಿಕ)",
        "profile_district": "ಜಿಲ್ಲೆ (ಐಚ್ಛಿಕ)",
        "profile_gender": "ಲಿಂಗ (ಐಚ್ಛಿಕ)",
        "profile_household_size": "ಕುಟುಂಬದ ಸದಸ್ಯರ ಸಂಖ್ಯೆ (ಐಚ್ಛಿಕ)",
        "check_eligibility": "ಅರ್ಹತೆ ಪರಿಶೀಲಿಸಿ",
        "checking_eligibility": "ನಿಯಮಾಧಾರಿತ ಪರಿಶೀಲನೆ ನಡೆಯುತ್ತಿದೆ…",
        "result_eligible": "ಹೊಂದಿಸಿದ ನಿಯಮಗಳ ಪ್ರಕಾರ ಅರ್ಹತೆ ಇದೆ.",
        "result_ineligible": "ಹೊಂದಿಸಿದ ನಿಯಮಗಳ ಪ್ರಕಾರ ಅರ್ಹತೆ ಇಲ್ಲ.",
        "result_more_information": "ಅರ್ಹತೆಯನ್ನು ಇನ್ನೂ ನಿರ್ಧರಿಸಲು ಸಾಧ್ಯವಾಗಿಲ್ಲ.",
        "result_unsupported": "ಈ ಯೋಜನೆಗೆ ನಿಯಮ ಸಮೂಹ ಹೊಂದಿಸಿಲ್ಲ.",
        "missing_information": "ಅಗತ್ಯ ಮಾಹಿತಿ",
        "privacy": (
            "ಫಾರ್ಮ್ ಸಲ್ಲಿಸಿದಾಗ ಮಾತ್ರ ಮಾಹಿತಿ API ಗೆ ಕಳುಹಿಸಲಾಗುತ್ತದೆ; ಅಪ್ಲಿಕೇಶನ್ ಅದನ್ನು "
            "ಉಳಿಸುವುದಿಲ್ಲ. ಗುರುತಿನ ಸಂಖ್ಯೆಗಳನ್ನು ನಮೂದಿಸಬೇಡಿ."
        ),
        "backend_unavailable": "ಸೇವೆ ತಾತ್ಕಾಲಿಕವಾಗಿ ಲಭ್ಯವಿಲ್ಲ. ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
        "retrieval_unavailable": "ಅಧಿಕೃತ ದಾಖಲೆ ಹುಡುಕಾಟ ಪ್ರಸ್ತುತ ಲಭ್ಯವಿಲ್ಲ.",
        "invalid_response": "ಸೇವೆಯಿಂದ ನಿರೀಕ್ಷಿತ ರೂಪದ ಮಾಹಿತಿ ಬಂದಿಲ್ಲ.",
        "invalid_input": "ದಯವಿಟ್ಟು ನಮೂದಿಸಿದ ಮಾಹಿತಿಯನ್ನು ಪರಿಶೀಲಿಸಿ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
        "health_ready": "ಮಾಹಿತಿ ಮರುಪಡೆಯುವ ಸೇವೆ ಸಿದ್ಧವಾಗಿದೆ.",
        "health_degraded": "ಕೆಲವು ಸೇವೆಗಳು ಸಿದ್ಧವಾಗಿಲ್ಲ.",
        "not_searchable": "ಈ ನೋಂದಣಿ ಮಾಹಿತಿಯನ್ನು ಹುಡುಕಬಹುದೆಂದು ದೃಢಪಡಿಸಲಾಗಿಲ್ಲ.",
        "unknown_scheme": "ಆಯ್ಕೆ ಮಾಡಿದ ಯೋಜನೆ ನೋಂದಣಿಯಲ್ಲಿ ಕಂಡುಬಂದಿಲ್ಲ.",
        "eligibility_unavailable": "ಅರ್ಹತಾ ಮೌಲ್ಯಮಾಪನ ಇನ್ನೂ ಲಭ್ಯವಿಲ್ಲ.",
        "registry_vs_index": (
            "ನೋಂದಣಿಯಲ್ಲಿ ಇರುವುದರಿಂದಲೇ ದಾಖಲೆ ಪ್ರಸ್ತುತ ಹುಡುಕಾಟ ಸೂಚ್ಯಂಕದಲ್ಲಿದೆ ಎಂದು ದೃಢವಾಗುವುದಿಲ್ಲ."
        ),
    },
}


def translate(language: str, key: str) -> str:
    """Return a localized string, falling back safely to English."""
    localized = STRINGS.get(language, STRINGS["en"])
    return localized.get(key, STRINGS["en"].get(key, key))
