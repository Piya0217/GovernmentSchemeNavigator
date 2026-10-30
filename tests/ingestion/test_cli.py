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
