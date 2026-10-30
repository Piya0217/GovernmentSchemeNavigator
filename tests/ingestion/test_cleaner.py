"""Unit tests for text cleaning and normalization."""

from src.ingestion.cleaner import clean_text


def test_clean_text_normalizes_whitespace() -> None:
    raw = "Section 1:   Eligibility    Criteria.\n\n\n\nAll   farmers are eligible."
    cleaned = clean_text(raw)
    assert cleaned == "Section 1: Eligibility Criteria.\n\nAll farmers are eligible."


def test_clean_text_removes_control_characters() -> None:
    raw = "Document Header\x0c\n\ufeffContent line 1.\x00\x08End of page."
    cleaned = clean_text(raw)
    assert "\x0c" not in cleaned
    assert "\ufeff" not in cleaned
    assert "\x00" not in cleaned
    assert "Document Header" in cleaned
    assert "Content line 1." in cleaned


def test_clean_text_rejoins_hyphenated_words() -> None:
    raw = "The implemen-\ntation of the scheme requires docu-\nmentation."
    cleaned = clean_text(raw)
    assert "implementation of the scheme requires documentation." in cleaned


def test_clean_text_preserves_numeric_hyphen_and_bullets() -> None:
    raw = "- Financial year 2023-2024\n- Benefit amount: Rs. 6,000"
    cleaned = clean_text(raw)
    assert "- Financial year 2023-2024" in cleaned
    assert "- Benefit amount: Rs. 6,000" in cleaned


def test_clean_text_preserves_hindi_unicode() -> None:
    hindi_text = "प्रधानमंत्री किसान सम्मान निधि (पीएम-किसान) योजना। लाभ: ₹6,000 प्रति वर्ष।"
    cleaned = clean_text(hindi_text)
    assert "प्रधानमंत्री" in cleaned
    assert "किसान" in cleaned
    assert "₹6,000" in cleaned
    assert "।" in cleaned


def test_clean_text_preserves_kannada_unicode() -> None:
    kannada_text = "ಕರ್ನಾಟಕ ಸರ್ಕಾರದ ಯೋಜನೆಗಳು ಮತ್ತು ಅರ್ಹತಾ ಮಾನದಂಡಗಳು."
    cleaned = clean_text(kannada_text)
    assert "ಕರ್ನಾಟಕ" in cleaned
    assert "ಸರ್ಕಾರದ" in cleaned
    assert "ಮಾನದಂಡಗಳು" in cleaned


def test_clean_text_preserves_tab_separated_table_columns() -> None:
    raw = "Age\tAnnual income\tBenefit\n18\t₹60,000\t₹6,000"
    cleaned = clean_text(raw)
    assert cleaned == "Age | Annual income | Benefit\n18 | ₹60,000 | ₹6,000"


def test_clean_text_preserves_aligned_table_columns() -> None:
    raw = "Age      Annual income  Benefit\n18       Rs. 60,000      ₹6,000"
    cleaned = clean_text(raw)
    assert cleaned == "Age | Annual income | Benefit\n18 | Rs. 60,000 | ₹6,000"


def test_clean_text_handles_empty_or_whitespace() -> None:
    assert clean_text("") == ""
    assert clean_text("   \n\n\t   ") == ""


# ---------------------------------------------------------------------------
# Regression: PDF font-ligature artefact bytes (C0: 0x01-0x06)
# ---------------------------------------------------------------------------


def test_clean_text_strips_c0_font_ligature_bytes() -> None:
    """C0 bytes 0x01-0x06 emitted by some PDF subsetted fonts must be removed."""
    raw = "Eligibility\x01 criteria\x02:\x03 farmer\x04 family\x05 only\x06."
    cleaned = clean_text(raw)
    for code in range(0x01, 0x07):
        assert chr(code) not in cleaned
    assert "Eligibility" in cleaned
    assert "criteria" in cleaned
    assert "farmer" in cleaned
    assert "only" in cleaned


# ---------------------------------------------------------------------------
# Regression: C1 control block (0x7F-0x9F) leaked from subsetted PDF fonts
# ---------------------------------------------------------------------------


def test_clean_text_strips_c1_control_block() -> None:
    """C1 bytes 0x7F-0x9F leaked from some PDF subsetted fonts must be removed."""
    raw = "Scheme\x7f guideline\x80 document\x8d version\x9f 2023."
    cleaned = clean_text(raw)
    for code in range(0x7F, 0xA0):
        assert chr(code) not in cleaned
    assert "Scheme" in cleaned
    assert "guideline" in cleaned
    assert "document" in cleaned
    assert "version" in cleaned
    assert "2023" in cleaned


def test_clean_text_strips_mixed_c0_c1_preserves_unicode() -> None:
    """Mixed C0/C1 artefacts are stripped; Devanagari and Kannada are preserved."""
    raw = (
        "\x01PM\x02 Vishwakarma\x04 Guidelines\x7f\x8d\x9f "
        "प्रधानमंत्री \x05ವಿಶ್ವಕರ್ಮ\x06 Scheme."
    )
    cleaned = clean_text(raw)
    for code in list(range(0x01, 0x07)) + list(range(0x7F, 0xA0)):
        assert chr(code) not in cleaned
    assert "PM" in cleaned
    assert "Vishwakarma" in cleaned
    assert "Guidelines" in cleaned
    assert "प्रधानमंत्री" in cleaned
    assert "ವಿಶ್ವಕರ್ಮ" in cleaned
    assert "Scheme" in cleaned
