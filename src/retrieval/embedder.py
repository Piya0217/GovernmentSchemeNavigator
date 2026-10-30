"""Embedding generation for document chunks and search queries."""

from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger("scheme_navigator.retrieval.embedder")

DEFAULT_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_EMBEDDING_DIM = 384


class EmbedderError(Exception):
    """Base exception for embedding operations."""


class BaseEmbedder(ABC):
    """Abstract interface for generating vector embeddings."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the unique model identifier string."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return expected vector embedding dimensionality."""

    @abstractmethod
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of text passages into vectors."""

    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        """Embed a single search query into a vector."""


class SentenceTransformerEmbedder(BaseEmbedder):
    """Local multilingual embedder powered by sentence-transformers."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        device: str = "cpu",
        expected_dim: int = DEFAULT_EMBEDDING_DIM,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._expected_dim = expected_dim
        self._model: Any = None  # noqa: ANN401

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._expected_dim

    def _get_model(self) -> Any:  # noqa: ANN401
        """Lazily load the SentenceTransformer model on the configured device."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as err:
                msg = (
                    "sentence-transformers is not installed. Install it via "
                    "`pip install sentence-transformers`."
                )
                raise EmbedderError(msg) from err

            logger.info(
                "Loading embedding model '%s' on device '%s'...",
                self._model_name,
                self._device,
            )
            try:
                self._model = SentenceTransformer(self._model_name, device=self._device)
            except Exception as err:
                msg = f"Failed to load embedding model '{self._model_name}': {err}"
                raise EmbedderError(msg) from err

        return self._model

    def _validate_vector(self, vec: Sequence[float], context: str = "") -> list[float]:
        """Verify vector dimension and ensure no NaN or infinite values exist."""
        if len(vec) != self._expected_dim:
            msg = (
                f"Embedding dimension mismatch in {context}: "
                f"expected {self._expected_dim}, got {len(vec)}"
            )
            raise EmbedderError(msg)

        clean_vec: list[float] = []
        for i, val in enumerate(vec):
            float_val = float(val)
            if math.isnan(float_val) or math.isinf(float_val):
                msg = (
                    f"Non-finite value ({float_val}) detected at index {i} in {context}"
                )
                raise EmbedderError(msg)
            clean_vec.append(float_val)

        return clean_vec

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a sequence of texts with dimension and finiteness validation."""
        if not texts:
            return []

        model = self._get_model()
        try:
            # sentence-transformers encode returns numpy array or list of tensors
            encode_callable = getattr(model, "encode")  # noqa: B009
            embeddings = encode_callable(
                list(texts),
                batch_size=32,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
        except Exception as err:
            msg = f"Error generating embeddings for batch of {len(texts)} texts: {err}"
            raise EmbedderError(msg) from err

        validated_vectors: list[list[float]] = []
        for idx, emb in enumerate(embeddings):
            validated = self._validate_vector(emb, context=f"batch text item {idx}")
            validated_vectors.append(validated)

        return validated_vectors

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query text."""
        query_cleaned = query.strip()
        if not query_cleaned:
            msg = "Cannot embed empty or whitespace-only query."
            raise EmbedderError(msg)

        vectors = self.embed_texts([query_cleaned])
        if not vectors:
            msg = "Embedder returned no vector for query."
            raise EmbedderError(msg)

        return vectors[0]
