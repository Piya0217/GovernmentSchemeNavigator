"""Vector store wrapper around ChromaDB for semantic retrieval."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import chromadb
    from chromadb.api.models.Collection import Collection

logger = logging.getLogger("scheme_navigator.retrieval.store")

DEFAULT_COLLECTION_NAME = "scheme_chunks"
DEFAULT_CHROMA_DIR = Path("data/chroma")


class VectorStoreError(Exception):
    """Base exception for vector store operations."""


class ChromaVectorStore:
    """Persistent or ephemeral ChromaDB vector store client wrapper."""

    def __init__(
        self,
        persist_dir: Path | str | None = DEFAULT_CHROMA_DIR,
        client: chromadb.ClientAPI | None = None,
    ) -> None:
        """Initialize Chroma vector store.

        Args:
            persist_dir: Directory where Chroma will store data. If None and
                client is None, an in-memory EphemeralClient is created.
            client: Optional pre-configured ClientAPI instance (for testing).
        """
        self._persist_dir = Path(persist_dir) if persist_dir is not None else None
        self._client: chromadb.ClientAPI | None = client

    def _get_client(self) -> chromadb.ClientAPI:
        """Lazily initialize or return ChromaDB client."""
        if self._client is None:
            try:
                import chromadb
            except ImportError as err:
                msg = "chromadb is not installed. Install via `pip install chromadb`."
                raise VectorStoreError(msg) from err

            if self._persist_dir is not None:
                self._persist_dir.mkdir(parents=True, exist_ok=True)
                logger.info(
                    "Initializing persistent ChromaDB at: %s", self._persist_dir
                )
                self._client = chromadb.PersistentClient(path=str(self._persist_dir))
            else:
                logger.info("Initializing in-memory ephemeral ChromaDB")
                self._client = chromadb.EphemeralClient()

        return self._client

    def get_or_create_collection(
        self,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        expected_model: str | None = None,
        expected_dim: int | None = None,
    ) -> Collection:
        """Retrieve or create a ChromaDB collection with cosine distance metric.

        Args:
            collection_name: Name of the collection.
            expected_model: Expected embedding model name to prevent mixing models.
            expected_dim: Expected vector dimension.

        Returns:
            ChromaDB Collection instance.
        """
        client = self._get_client()

        metadata: dict[str, Any] = {  # noqa: ANN401
            "hnsw:space": "cosine",  # Enforce cosine distance
        }
        if expected_model:
            metadata["embedding_model"] = expected_model
        if expected_dim:
            metadata["embedding_dimension"] = expected_dim

        try:
            # Check if collection already exists to verify model compatibility
            existing_collections = [c.name for c in client.list_collections()]
            if collection_name in existing_collections:
                col = client.get_collection(name=collection_name)
                col_meta = col.metadata or {}

                # Verify model compatibility if existing metadata recorded it
                existing_model = col_meta.get("embedding_model")
                if (
                    expected_model
                    and existing_model
                    and existing_model != expected_model
                ):
                    msg = (
                        f"Collection '{collection_name}' was indexed with model "
                        f"'{existing_model}', but requested model is "
                        f"'{expected_model}'. "
                        "Re-index the collection or use the matching model to "
                        "avoid mixed embeddings."
                    )
                    raise VectorStoreError(msg)

                existing_dim = col_meta.get("embedding_dimension")
                if expected_dim and existing_dim and existing_dim != expected_dim:
                    msg = (
                        f"Collection '{collection_name}' dimension mismatch: "
                        f"existing is {existing_dim}, requested is {expected_dim}."
                    )
                    raise VectorStoreError(msg)

                return col

            return client.create_collection(
                name=collection_name,
                metadata=metadata,
            )
        except VectorStoreError:
            raise
        except Exception as err:
            msg = (
                f"Failed to get or create Chroma collection '{collection_name}': {err}"
            )
            raise VectorStoreError(msg) from err

    def upsert_chunks(
        self,
        collection_name: str,
        chunk_ids: Sequence[str],
        texts: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        metadatas: Sequence[Mapping[str, str | int | float | bool]],
        expected_model: str | None = None,
        expected_dim: int | None = None,
    ) -> int:
        """Upsert a batch of chunks into the collection idempotently."""
        if not chunk_ids:
            return 0

        if not (len(chunk_ids) == len(texts) == len(embeddings) == len(metadatas)):
            msg = (
                f"Length mismatch: {len(chunk_ids)} ids, {len(texts)} texts, "
                f"{len(embeddings)} embeddings, {len(metadatas)} metadatas."
            )
            raise VectorStoreError(msg)

        collection = self.get_or_create_collection(
            collection_name,
            expected_model=expected_model,
            expected_dim=expected_dim,
        )

        try:
            collection.upsert(
                ids=list(chunk_ids),
                documents=list(texts),
                embeddings=list(embeddings),
                metadatas=[dict(m) for m in metadatas],
            )
            return len(chunk_ids)
        except Exception as err:
            msg = (
                f"Failed to upsert chunks into Chroma collection '{collection_name}': "
                f"{err}"
            )
            raise VectorStoreError(msg) from err

    def delete_chunks(self, collection_name: str, chunk_ids: Sequence[str]) -> None:
        """Delete specific chunks by ID."""
        if not chunk_ids:
            return
        collection = self.get_or_create_collection(collection_name)
        try:
            collection.delete(ids=list(chunk_ids))
        except Exception as err:
            msg = (
                f"Failed to delete {len(chunk_ids)} chunks from '{collection_name}': "
                f"{err}"
            )
            raise VectorStoreError(msg) from err

    def delete_scheme_chunks(self, collection_name: str, scheme_id: str) -> None:
        """Delete all chunks belonging to a specific scheme_id."""
        collection = self.get_or_create_collection(collection_name)
        try:
            collection.delete(where={"scheme_id": scheme_id})
        except Exception as err:
            msg = f"Failed to delete chunks for scheme '{scheme_id}': {err}"
            raise VectorStoreError(msg) from err

    def query(
        self,
        collection_name: str,
        query_embedding: Sequence[float],
        top_k: int = 5,
        where: Mapping[str, str | int | float | bool] | None = None,
    ) -> Mapping[str, Sequence[Any]]:  # noqa: ANN401
        """Perform a nearest-neighbor query in the collection using cosine distance."""
        collection = self.get_or_create_collection(collection_name)
        try:
            results = collection.query(
                query_embeddings=[list(query_embedding)],
                n_results=top_k,
                where=dict(where) if where else None,
                include=["documents", "metadatas", "distances"],
            )
            return results
        except Exception as err:
            msg = f"Query failed on collection '{collection_name}': {err}"
            raise VectorStoreError(msg) from err

    def count(self, collection_name: str = DEFAULT_COLLECTION_NAME) -> int:
        """Return total number of chunks currently stored in the collection."""
        collection = self.get_or_create_collection(collection_name)
        return collection.count()
