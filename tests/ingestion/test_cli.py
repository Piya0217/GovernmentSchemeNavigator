"""Unit tests for the ingestion CLI entry point."""

from collections.abc import Callable
from pathlib import Path

from src.ingestion.cli import main


def test_cli_success(make_pdf: Callable[..., Path], tmp_path: Path) -> None:
    pdf_path = make_pdf(["Official Guidelines for PM Kisan."], "pmkisan_cli.pdf")
    output_dir = tmp_path / "processed"

    args = [
        "--pdf-path",
        str(pdf_path),
        "--scheme-id",
        "pm-kisan-cli",
        "--official-url",
        "https://pmkisan.gov.in",
        "--document-version",
        "2024",
        "--chunk-size",
        "300",
        "--chunk-overlap",
        "50",
        "--output-dir",
        str(output_dir),
    ]

    exit_code = main(args)
    assert exit_code == 0
    assert (output_dir / "pm-kisan-cli.json").exists()


def test_cli_failure_on_missing_file(tmp_path: Path) -> None:
    args = [
        "--pdf-path",
        str(tmp_path / "non_existent.pdf"),
        "--scheme-id",
        "test-fail",
        "--official-url",
        "https://example.gov.in",
    ]

    exit_code = main(args)
    assert exit_code != 0


def test_cli_invalid_chunk_options_return_nonzero(tmp_path: Path) -> None:
    args = [
        "--pdf-path",
        str(tmp_path / "unused.pdf"),
        "--scheme-id",
        "test-scheme",
        "--official-url",
        "https://example.gov.in",
        "--chunk-size",
        "100",
        "--chunk-overlap",
        "100",
    ]

    assert main(args) == 1


def test_cli_page_filter_limits_chunks_and_preserves_total_pages(
    make_pdf: Callable[..., Path], tmp_path: Path
) -> None:
    """--page-filter must restrict which pages are chunked.

    total_pages in the output must still equal the full PDF page count
    (provenance), not the filtered subset.
    """
    import json

    pages_text = [
        "Page one content about eligibility.",
        "Page two content about benefits.",
        "Page three content about exclusions.",
    ]
    pdf_path = make_pdf(pages_text, "filter_test.pdf")
    output_dir = tmp_path / "processed"

    args = [
        "--pdf-path",
        str(pdf_path),
        "--scheme-id",
        "filter-test",
        "--official-url",
        "https://example.gov.in",
        "--output-dir",
        str(output_dir),
        "--page-filter",
        "1,3",
    ]

    exit_code = main(args)
    assert exit_code == 0

    with open(output_dir / "filter-test.json", encoding="utf-8") as f:
        doc = json.load(f)

    page_numbers = {chunk["page_number"] for chunk in doc["chunks"]}
    assert 2 not in page_numbers, "Page 2 must be excluded by --page-filter"
    assert page_numbers <= {1, 3}, "Only pages 1 and 3 must be present"
    assert doc["total_pages"] == 3, "total_pages must reflect full PDF, not filter"


def test_cli_page_filter_invalid_input_returns_nonzero(
    make_pdf: Callable[..., Path], tmp_path: Path
) -> None:
    """--page-filter with non-integer values must exit with code 1."""
    pdf_path = make_pdf(["Content."], "bad_filter.pdf")
    output_dir = tmp_path / "processed"

    args = [
        "--pdf-path",
        str(pdf_path),
        "--scheme-id",
        "bad-filter",
        "--official-url",
        "https://example.gov.in",
        "--output-dir",
        str(output_dir),
        "--page-filter",
        "1,abc,3",
    ]

    assert main(args) == 1
