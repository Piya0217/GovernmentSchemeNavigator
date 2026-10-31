"""Deterministic query analyzer for scheme recognition and cross-lingual intent expansion."""  # noqa: E501

from __future__ import annotations

import logging
import re
from typing import NamedTuple

logger = logging.getLogger("scheme_navigator.retrieval.query_analyzer")


class SchemeMatch(NamedTuple):
    scheme_id: str
    matched_alias: str


# ---------------------------------------------------------------------------
# Authoritative Scheme Alias Registry (English + Kannada)
# ---------------------------------------------------------------------------

SCHEME_ALIASES: dict[str, list[str]] = {
    "central_pm_kisan": [
        # English
        "pm-kisan",
        "pm kisan",
        "pmkisan",
        "kisan samman nidhi",
        "pradhan mantri kisan samman nidhi",
        # Kannada
        "ಪಿಎಂ ಕಿಸಾನ್",
        "ಪಿಎಂ-ಕಿಸಾನ್",
        "ಪಿಎಂಕಿಸಾನ್",
        "ಕಿಸಾನ್ ಸಮ್ಮಾನ್ ನಿಧಿ",
        "ಪ್ರಧಾನ ಮಂತ್ರಿ ಕಿಸಾನ್ ಸಮ್ಮಾನ್ ನಿಧಿ",
    ],
    "central_pmjay": [
        # English
        "pm-jay",
        "pmjay",
        "pm jay",
        "ayushman bharat",
        "ayushman",
        "pradhan mantri jan arogya yojana",
        "jan arogya yojana",
        "golden card",
        # Kannada
        "ಪಿಎಂ-ಜೆಎವೈ",
        "ಪಿಎಂ ಜೆಎವೈ",
        "ಪಿಎಂಜೆಯುವೈ",
        "ಆಯುಷ್ಮಾನ್ ಭಾರತ್",
        "ಆಯುಷ್ಮಾನ್",
        "ಪ್ರಧಾನ ಮಂತ್ರಿ ಜನ ಆರೋಗ್ಯ ಯೋಜನೆ",
        "ಗೋಲ್ಡನ್ ಕಾರ್ಡ್",
    ],
    "central_pm_vishwakarma": [
        # English
        "pm vishwakarma",
        "pm-vishwakarma",
        "pmvishwakarma",
        "vishwakarma scheme",
        "vishwakarma yojana",
        "pradhan mantri vishwakarma",
        "vishwakarma",
        # Kannada
        "ಪಿಎಂ ವಿಶ್ವಕರ್ಮ",
        "ಪಿಎಂ-ವಿಶ್ವಕರ್ಮ",
        "ಪಿಎಂವಿಶ್ವಕರ್ಮ",
        "ವಿಶ್ವಕರ್ಮ ಯೋಜನೆ",
        "ವಿಶ್ವಕರ್ಮ",
        "ಪ್ರಧಾನ ಮಂತ್ರಿ ವಿಶ್ವಕರ್ಮ ಯೋಜನೆ",
    ],
    "central_sukanya_samriddhi": [
        # English
        "sukanya samriddhi",
        "sukanya",
        "ssy",
        "sukanya samriddhi yojana",
        "sukanya samriddhi account",
        # Kannada
        "ಸುಕನ್ಯಾ ಸಮೃದ್ಧಿ",
        "ಸುಕನ್ಯಾ",
        "ಸುಕನ್ಯಾ ಸಮೃದ್ಧಿ ಯೋಜನೆ",
        "ಸುಕನ್ಯಾ ಖಾತೆ",
    ],
}

# ---------------------------------------------------------------------------
# Curated Kannada-to-English Welfare Intent Mapping
# Note: Uses robust substring/token matching to handle Indic inflectional suffixes
# ---------------------------------------------------------------------------

KANNADA_INTENT_MAP: list[tuple[tuple[str, ...], str]] = [
    # Farmers / Agriculture
    (
        ("ರೈತ", "ಕೃಷಿಕ", "ಕೃಷಿ"),
        "farmers agricultural landholding income support",
    ),
    # Financial assistance / Cash transfer
    (
        ("ಆರ್ಥಿಕ ನೆರವು", "ಸಹಾಯಧನ", "ಹಣಕಾಸು ನೆರವು", "ಆರ್ಥಿಕ ಸಹಾಯ"),
        "financial assistance income support benefit",
    ),
    # Health insurance / Medical treatment
    (
        ("ಆರೋಗ್ಯ ವಿಮೆ", "ಚಿಕಿತ್ಸಾ", "ಆಸ್ಪತ್ರೆ", "ಚಿಕಿತ್ಸೆ", "ಆರೋಗ್ಯ"),
        "health insurance hospitalization medical treatment cover",
    ),
    # Poor families / Deprived households
    (
        ("ಬಡ ಕುಟುಂಬ", "ಬಡವರಿಗೆ", "ಬಡವರ", "ಬಿಪಿಎಲ್"),
        "poor families rural urban deprivation secc households",
    ),
    # Artisans / Craftspeople / Traditional trades
    (
        ("ಕುಶಲಕರ್ಮಿ", "ಕರಕುಶಲ"),
        "traditional artisans craftspeople trades toolkit credit",
    ),
    # Girl child / Daughter
    (
        ("ಹೆಣ್ಣು ಮಕ್ಕಳಿಗೆ", "ಹೆಣ್ಣು ಮಗು", "ಹೆಣ್ಣು ಮಕ್ಕಳ", "ಬಾಲಕಿ"),
        "girl child daughter age limit guardian",
    ),
    # Savings / Deposit account
    (
        ("ಉಳಿತಾಯ ಯೋಜನೆ", "ಉಳಿತಾಯ ಖಾತೆ", "ಠೇವಣಿ", "ಉಳಿತಾಯ"),
        "savings account deposit interest education withdrawal",
    ),
]


def has_kannada_script(text: str) -> bool:
    """Check if the text contains any Kannada Unicode characters (U+0C80 - U+0CFF)."""
    return any(0x0C80 <= ord(char) <= 0x0CFF for char in text)


def detect_explicit_scheme(query: str) -> str | None:
    """Identify if a user query explicitly mentions exactly one registered scheme.

    Rules:
    - Normalizes text (lowercase, strips punctuation).
    - Checks for exact word/phrase boundary matches across known aliases.
    - If matches point to ONE unique scheme_id, returns that scheme_id.
    - If multiple distinct schemes are mentioned or none, returns None.
    """
    cleaned = query.lower()
    matches: set[str] = set()

    for s_id, aliases in SCHEME_ALIASES.items():
        for alias in aliases:
            alias_lower = alias.lower()
            if has_kannada_script(alias_lower):
                # For Indic text, substring matching avoids matra/virama boundary failures  # noqa: E501
                if alias_lower in cleaned:
                    matches.add(s_id)
                    break
            else:
                # For Latin text, use word-boundary matching
                pattern = rf"(?:\b|\s|^){re.escape(alias_lower)}(?:\b|\s|$)"
                if re.search(pattern, cleaned):
                    matches.add(s_id)
                    break

    if len(matches) == 1:
        matched_id = next(iter(matches))
        logger.info(
            "Detected explicit scheme '%s' from query: '%s'",
            matched_id,
            query[:60],
        )
        return matched_id

    if len(matches) > 1:
        logger.info(
            "Multiple schemes detected in query (%s). Keeping generic search.",
            matches,
        )

    return None


def expand_query_intent(query: str) -> str:
    """Enhance cross-lingual matching for regional language queries.

    For queries containing Kannada text:
    - Identifies recognized welfare concepts using substring root matching.
    - Appends curated English semantic keywords to assist multilingual vector anchoring.
    - Does NOT mutate or replace official terms or invent information.
    """
    if not has_kannada_script(query):
        return query

    cleaned = query.lower()
    expansions: list[str] = []
    for keywords, english_terms in KANNADA_INTENT_MAP:
        if any(kw in cleaned for kw in keywords):
            expansions.append(english_terms)

    if expansions:
        # Append cross-lingual semantic anchor terms
        expanded = f"{query} {' '.join(expansions)}"
        logger.info("Expanded Kannada query '%s' -> '%s'", query, expanded)
        return expanded

    return query
