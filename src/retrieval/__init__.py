"""Retrieval package for Government Scheme Navigator."""

from src.retrieval.answer import AnswerBuilder, AnswerResponse, EvidencePassage
from src.retrieval.embedder import (
    BaseEmbedder,
    EmbedderError,
    SentenceTransformerEmbedder,
)
from src.retrieval.evidence import (
    EvidenceVerdict,
    assess_evidence,
    has_welfare_context,
    is_out_of_scope,
)
from src.retrieval.indexer import IndexerError, SchemeIndexer
from src.retrieval.query_analyzer import (
    SCHEME_ALIASES,
    detect_explicit_scheme,
    expand_query_intent,
    has_kannada_script,
)
from src.retrieval.reranker import (
    QuestionIntent,
    detect_question_intent,
    rerank_passages,
    score_passage,
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
    "AnswerBuilder",
    "AnswerResponse",
    "BaseEmbedder",
    "ChromaVectorStore",
    "DocumentIndexRecord",
    "EmbedderError",
    "EvidencePassage",
    "EvidenceVerdict",
    "IndexManifest",
    "IndexedChunk",
    "IndexedChunkMetadata",
    "IndexerError",
    "QuestionIntent",
    "SCHEME_ALIASES",
    "SchemeIndexer",
    "SchemeSearcher",
    "SearchError",
    "SearchQuery",
    "SearchResult",
    "SentenceTransformerEmbedder",
    "VectorStoreError",
    "assess_evidence",
    "detect_explicit_scheme",
    "detect_question_intent",
    "expand_query_intent",
    "has_kannada_script",
    "has_welfare_context",
    "is_out_of_scope",
    "rerank_passages",
    "score_passage",
]
