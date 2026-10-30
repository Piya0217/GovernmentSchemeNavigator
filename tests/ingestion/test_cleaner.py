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
