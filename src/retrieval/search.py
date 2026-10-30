"""Semantic search interface for querying indexed government scheme chunks."""

from __future__ import annotations

import logging
from typing import Any

from src.retrieval.embedder import BaseEmbedder
from src.retrieval.query_analyzer import detect_explicit_scheme, expand_query_intent
from src.retrieval.schemas import SearchQuery, SearchResult
from src.retrieval.store import ChromaVectorStore

logger = logging.getLogger("scheme_navigator.retrieval.search")

DEFAULT_SIMILARITY_THRESHOLD_DISTANCE = 0.60  # Cosine distance cutoff for relevance


class SearchError(Exception):
    """Base exception for search operations."""


class SchemeSearcher:
    """Performs semantic vector search against indexed scheme chunks."""

    def __init__(
        self,
        vector_store: ChromaVectorStore,
        embedder: BaseEmbedder,
        collection_name: str = "scheme_chunks",
    ) -> None:
        self.store = vector_store
        self.embedder = embedder
        self.collection_name = collection_name

    def search(
        self,
        query: str | SearchQuery,
        top_k: int = 5,
        scheme_id: str | None = None,
        max_distance: float | None = DEFAULT_SIMILARITY_THRESHOLD_DISTANCE,
    ) -> list[SearchResult]:
        """Perform semantic retrieval for a user query.

        Args:
            query: User search query string or SearchQuery object.
            top_k: Maximum number of retrieved passages to return.
            scheme_id: Optional scheme_id filter (e.g. 'central_pm_kisan').
            max_distance: Optional distance cutoff. Results with higher cosine distance
                than this threshold are considered insufficient evidence and excluded.

        Returns:
            List of SearchResult objects sorted by ascending distance
            (descending relevance). Returns an empty list if no results
            satisfy the query or threshold.

        Safety (AGENTS.md):
            - Results provide source document passages and attribution citations only.
            - Never evaluates, infers, or asserts user eligibility.
        """
        if isinstance(query, str):
            query_text = query.strip()
            search_query = SearchQuery(
                query=query_text,
                top_k=top_k,
                scheme_id=scheme_id,
                max_distance=max_distance,
            )
        else:
            search_query = query

        if not search_query.query:
            return []

        # 1. Scheme-Aware Routing: Auto-detect explicit scheme alias if not provided
        effective_scheme_id = search_query.scheme_id
        if not effective_scheme_id:
            effective_scheme_id = detect_explicit_scheme(search_query.query)
            if effective_scheme_id:
                logger.info(
                    "Auto-routed query to recognized scheme: '%s'",
                    effective_scheme_id,
                )

        # 2. Cross-lingual intent expansion for regional language queries
        search_text = expand_query_intent(search_query.query)

        # 3. Embed query text
        try:
            query_vector = self.embedder.embed_query(search_text)
        except Exception as err:
            msg = f"Failed to embed query: {err}"
            raise SearchError(msg) from err

        where_filter: dict[str, Any] | None = None
        if effective_scheme_id:
            where_filter = {"scheme_id": effective_scheme_id}

        # 4. Query vector store
        try:
            raw_results = self.store.query(
                collection_name=self.collection_name,
                query_embedding=query_vector,
                top_k=search_query.top_k,
                where=where_filter,
            )
        except Exception as err:
            msg = f"Vector search query failed: {err}"
            raise SearchError(msg) from err

        documents = raw_results.get("documents", [[]])[0]
        metadatas = raw_results.get("metadatas", [[]])[0]
        distances = raw_results.get("distances", [[]])[0]
        ids = raw_results.get("ids", [[]])[0]

        results: list[SearchResult] = []
        for i, chunk_id in enumerate(ids):
            raw_dist = float(distances[i]) if i < len(distances) else 1.0
            dist = max(0.0, raw_dist)

            # Apply distance cutoff threshold if specified
            if (
                search_query.max_distance is not None
                and dist > search_query.max_distance
            ):
                logger.debug(
                    "Excluding chunk '%s': distance %.3f exceeds threshold %.3f",
                    chunk_id,
                    dist,
                    search_query.max_distance,
                )
                continue

            text = documents[i] if i < len(documents) else ""
            meta = metadatas[i] if i < len(metadatas) else {}

            # Normalized similarity score for display: max(0.0, 1.0 - distance)
            sim_score = max(0.0, min(1.0, 1.0 - dist))

            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    scheme_id=meta.get("scheme_id", ""),
                    source_document=meta.get("source_document", ""),
                    official_source_url=meta.get("official_source_url", ""),
                    page_number=int(meta.get("page_number", 1)),
                    chunk_index=int(meta.get("chunk_index", 0)),
                    document_version=meta.get("document_version") or None,
                    document_readiness=meta.get(
                        "document_readiness", "verified_digital_text"
                    ),
                    text=text,
                    distance=dist,
                    similarity_score=sim_score,
                )
            )

        return results
