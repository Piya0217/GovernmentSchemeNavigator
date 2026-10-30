"""Command line interface for indexing and semantic search."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.retrieval.embedder import SentenceTransformerEmbedder
from src.retrieval.indexer import SchemeIndexer
from src.retrieval.search import SchemeSearcher
from src.retrieval.store import ChromaVectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("scheme_navigator.retrieval.cli")


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser for retrieval CLI."""
    parser = argparse.ArgumentParser(
        prog="python -m src.retrieval.cli",
        description="Government Scheme Navigator - Retrieval & Indexing CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: index
    idx_parser = subparsers.add_parser(
        "index", help="Index processed scheme JSON files into ChromaDB."
    )
    idx_parser.add_argument(
        "--processed-dir",
        type=Path,
        default=Path("data/processed"),
        help="Directory containing processed scheme JSON documents.",
    )
    idx_parser.add_argument(
        "--registry",
        type=Path,
        default=Path("data/scheme_registry.json"),
        help="Path to scheme registry JSON file.",
    )
    idx_parser.add_argument(
        "--chroma-dir",
        type=Path,
        default=Path("data/chroma"),
        help="Persistence directory for ChromaDB.",
    )
    idx_parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-indexing even if source document SHA-256 is unchanged.",
    )

    # Subcommand: search
    search_parser = subparsers.add_parser(
        "search", help="Perform semantic vector search against indexed scheme chunks."
    )
    search_parser.add_argument(
        "query",
        type=str,
        help="Search query text (English or regional language).",
    )
    search_parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Maximum number of results to retrieve (default: 5).",
    )
    search_parser.add_argument(
        "--scheme-id",
        type=str,
        default=None,
        help="Optional scheme_id filter (e.g. 'central_pm_kisan').",
    )
    search_parser.add_argument(
        "--chroma-dir",
        type=Path,
        default=Path("data/chroma"),
        help="Persistence directory for ChromaDB.",
    )

    return parser


def handle_index(args: argparse.Namespace) -> int:
    """Execute the indexing subcommand."""
    logger.info("Initializing vector store at: %s", args.chroma_dir)
    store = ChromaVectorStore(persist_dir=args.chroma_dir)
    embedder = SentenceTransformerEmbedder()
    indexer = SchemeIndexer(
        vector_store=store,
        embedder=embedder,
        manifest_dir=args.chroma_dir,
    )

    try:
        results = indexer.index_all_verified_schemes(
            processed_dir=args.processed_dir,
            registry_path=args.registry,
            force=args.force,
        )
        total_indexed = sum(results.values())
        logger.info(
            "Indexing complete: %d schemes, %d total chunks stored.",
            len(results),
            total_indexed,
        )
        for s_id, count in results.items():
            logger.info("  - %s: %d chunks", s_id, count)
        return 0
    except Exception as err:
        logger.error("Indexing failed: %s", err)
        return 1


def handle_search(args: argparse.Namespace) -> int:
    """Execute the search subcommand."""
    store = ChromaVectorStore(persist_dir=args.chroma_dir)
    embedder = SentenceTransformerEmbedder()
    searcher = SchemeSearcher(vector_store=store, embedder=embedder)

    try:
        results = searcher.search(
            query=args.query,
            top_k=args.top_k,
            scheme_id=args.scheme_id,
        )

        logger.info("Query: '%s'", args.query)
        logger.info("Found %d matching passage(s):", len(results))

        if not results:
            logger.info(
                "No relevant passages found "
                "(insufficient evidence or distance above threshold)."
            )
            return 0

        for idx, res in enumerate(results, start=1):
            logger.info(
                "[%d] Scheme: %s | Page %d (Chunk #%d) | Dist: %.4f | Sim: %.4f",
                idx,
                res.scheme_id,
                res.page_number,
                res.chunk_index,
                res.distance,
                res.similarity_score,
            )
            logger.info("    Source: %s", res.official_source_url)
            logger.info("    Text: %s...", res.text[:200])
        return 0
    except Exception as err:
        logger.error("Search failed: %s", err)
        return 1


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "index":
        return handle_index(args)
    if args.command == "search":
        return handle_search(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
