"""Retrieval package for Government Scheme Navigator."""

from src.retrieval.embedder import (
    BaseEmbedder,
    EmbedderError,
    SentenceTransformerEmbedder,
)
from src.retrieval.indexer import IndexerError, SchemeIndexer
from src.retrieval.query_analyzer import (
    SCHEME_ALIASES,
    detect_explicit_scheme,
    expand_query_intent,
    has_kannada_script,
)
from src.retrieval.schemas import (
    DocumentIndexRecord,
    IndexedChunk,
    IndexedChunkMetadata,
    IndexManifest,
    SearchQuery,
    SearchResult,
)
from src.retrieval.search import SchemeSearcher, SearchError
from src.retrieval.store import ChromaVectorStore, VectorStoreError

__all__ = [
    "BaseEmbedder",
    "ChromaVectorStore",
    "DocumentIndexRecord",
    "EmbedderError",
    "IndexManifest",
    "IndexedChunk",
    "IndexedChunkMetadata",
    "IndexerError",
    "SCHEME_ALIASES",
    "SchemeIndexer",
    "SchemeSearcher",
    "SearchError",
    "SearchQuery",
    "SearchResult",
    "SentenceTransformerEmbedder",
    "VectorStoreError",
    "detect_explicit_scheme",
    "expand_query_intent",
    "has_kannada_script",
]
