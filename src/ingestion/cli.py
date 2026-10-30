"""Command-line interface for ingesting a single scheme PDF."""

import argparse
import logging
import sys
from pathlib import Path

from src.ingestion.pipeline import run_ingestion_pipeline
from src.ingestion.schemas import ChunkingConfig, DocumentMetadata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description="Ingest an official government scheme PDF document.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--pdf-path",
        required=True,
        type=str,
        help="Path to the PDF file to ingest.",
    )
    parser.add_argument(
        "--scheme-id",
        required=True,
        type=str,
        help="Unique identifier for the scheme (e.g. 'pm-kisan').",
    )
    parser.add_argument(
        "--official-url",
        required=True,
        type=str,
        help="Official government URL from where the scheme document was obtained.",
    )
    parser.add_argument(
        "--document-version",
        default=None,
        type=str,
        help="Optional version or release year of the document.",
    )
    parser.add_argument(
        "--chunk-size",
        default=500,
        type=int,
        help="Maximum chunk character length.",
    )
    parser.add_argument(
        "--chunk-overlap",
        default=100,
        type=int,
        help="Overlap character count between consecutive chunks.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/processed",
        type=str,
        help="Directory to save the processed JSON artifact.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point for document ingestion.

    Args:
        argv: Optional command-line arguments (uses sys.argv if None).

    Returns:
        Exit code: 0 for success, non-zero for error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    pdf_file = Path(args.pdf_path)
    metadata = DocumentMetadata(
        scheme_id=args.scheme_id,
        source_document=pdf_file.name,
        official_source_url=args.official_url,
        document_version=args.document_version,
    )
    chunk_config = ChunkingConfig(
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )

    try:
        logger.info("Starting ingestion for scheme: %s", metadata.scheme_id)
        doc = run_ingestion_pipeline(
            pdf_path=pdf_file,
            metadata=metadata,
            chunk_config=chunk_config,
            output_dir=args.output_dir,
        )
        logger.info(
            "Successfully ingested %s: %d pages, %d chunks saved to %s/%s.json",
            metadata.scheme_id,
            doc.total_pages,
            doc.total_chunks,
            args.output_dir,
            metadata.scheme_id,
        )
        return 0
    except Exception as err:
        logger.error("Ingestion failed: %s", err)
        return 1


if __name__ == "__main__":
    sys.exit(main())
