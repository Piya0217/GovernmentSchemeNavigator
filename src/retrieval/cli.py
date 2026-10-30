"""Command line interface for indexing and semantic search."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.retrieval.answer import AnswerBuilder
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

    # Subcommand: answer
    answer_parser = subparsers.add_parser(
        "answer",
        help="Return extractive answer passages with citations for a query.",
    )
    answer_parser.add_argument(
        "query",
        type=str,
        help="Question to answer (English or Kannada).",
    )
    answer_parser.add_argument(
        "--scheme-id",
        type=str,
        default=None,
        help="Optional scheme_id filter override.",
    )
    answer_parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of passages to retrieve before evidence filtering (default: 5).",
    )
    answer_parser.add_argument(
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


def handle_answer(args: argparse.Namespace) -> int:
    """Execute the answer subcommand.

    Retrieves scheme passages, runs evidence assessment, and prints a
    structured extractive answer with source citations, or a clear
    abstention message when evidence is insufficient.

    Safety: never prints eligibility decisions.
    """
    store = ChromaVectorStore(persist_dir=args.chroma_dir)
    embedder = SentenceTransformerEmbedder()
    searcher = SchemeSearcher(vector_store=store, embedder=embedder)
    builder = AnswerBuilder(searcher=searcher, top_k=args.top_k)

    try:
        response = builder.answer(query=args.query, scheme_id=args.scheme_id)
    except Exception as err:
        logger.error("Answer command failed: %s", err)
        return 1

    # --- Log formatted output ---
    logger.info("=" * 70)
    logger.info("QUERY : %s", response.query)
    logger.info("STATUS: %s", response.status.upper())
    if response.detected_scheme_id:
        logger.info("SCHEME: %s", response.detected_scheme_id)
    logger.info("=" * 70)

    if response.status == "supported":
        logger.info("Found %d evidence passage(s):", len(response.passages))
        for idx, p in enumerate(response.passages, start=1):
            logger.info("  [%d] Scheme   : %s", idx, p.scheme_id)
            logger.info("       Document : %s", p.source_document)
            logger.info(
                "       Page     : %d  |  Chunk: %d", p.page_number, p.chunk_index
            )
            logger.info(
                "       Distance : %.4f  |  Score: %.4f",
                p.distance,
                p.similarity_score,
            )
            logger.info("       Source   : %s", p.official_source_url)
            if p.document_version:
                logger.info("       Version  : %s", p.document_version)
            logger.info("       Chunk ID : %s", p.chunk_id)
            logger.info("       PASSAGE:\n       %s", p.passage_text)
        logger.info("NOTE: Eligibility not yet assessed. Phase 3 rules engine pending.")
    else:
        # Abstention
        logger.info("REASON: %s", response.abstention_reason)
        if response.status == "out_of_scope":
            logger.info(
                "This system covers: PM-KISAN, Ayushman Bharat (PM-JAY), "
                "PM Vishwakarma, Sukanya Samriddhi Yojana."
            )

    logger.info("=" * 70)
    return 0


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
    if args.command == "answer":
        return handle_answer(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
