"""Indexing pipeline for scheme documents.

Loads processed JSON chunks, filters noise, embeds, and indexes into ChromaDB.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from src.ingestion.schemas import ProcessedDocument
from src.retrieval.embedder import BaseEmbedder
from src.retrieval.schemas import (
    DocumentIndexRecord,
    IndexedChunk,
    IndexedChunkMetadata,
    IndexManifest,
)
from src.retrieval.store import ChromaVectorStore

logger = logging.getLogger("scheme_navigator.retrieval.indexer")

MIN_CHUNK_CHARS = 25
MANIFEST_FILENAME = "index_manifest.json"


class IndexerError(Exception):
    """Base exception for indexing errors."""


def compute_file_sha256(path: Path) -> str:
    """Compute the hex-encoded SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_text_sha256(text: str) -> str:
    """Compute hex SHA-256 hash of a text string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_meaningful_chunk(text: str, min_chars: int = MIN_CHUNK_CHARS) -> bool:
    """Check if a chunk contains sufficient substantive text to index.

    Filters out:
    - Empty or whitespace-only strings.
    - Pure soft-hyphens (\\xad), control characters, or TOC artifacts.
    - Standalone numbers (e.g. isolated page numbers '26', '40').
    - Strings with fewer than min_chars characters or without alphabetical letters.
    """
    cleaned = text.replace("\xad", "").strip()
    if len(cleaned) < min_chars:
        return False

    # Must contain at least some alphabetic content (not just digits or punctuation)
    has_letters = any(ch.isalpha() for ch in cleaned)
    if not has_letters:
        return False

    # Ensure no forbidden control characters are present
    for ch in cleaned:
        cp = ord(ch)
        if (0x00 <= cp <= 0x1F and cp not in (0x09, 0x0A, 0x0D)) or (
            0x7F <= cp <= 0x9F
        ):
            return False

    return True


def get_verified_schemes_from_registry(registry_path: Path) -> set[str]:
    """Read the scheme registry and return scheme IDs marked 'verified_digital_text'."""
    if not registry_path.is_file():
        msg = f"Registry file not found at: {registry_path}"
        raise IndexerError(msg)

    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        schemes = data.get("schemes", [])
        verified: set[str] = set()
        for s in schemes:
            if s.get("verification_status") == "verified_digital_text":
                s_id = s.get("scheme_id")
                if s_id:
                    verified.add(s_id)
        return verified
    except Exception as err:
        msg = f"Failed to parse scheme registry: {err}"
        raise IndexerError(msg) from err


class SchemeIndexer:
    """Coordinates idempotent extraction, embedding, and indexing."""

    def __init__(
        self,
        vector_store: ChromaVectorStore,
        embedder: BaseEmbedder,
        collection_name: str = "scheme_chunks",
        manifest_dir: Path | None = None,
    ) -> None:
        self.store = vector_store
        self.embedder = embedder
        self.collection_name = collection_name
        self.manifest_dir = manifest_dir or Path("data/chroma")
        self.manifest_path = self.manifest_dir / MANIFEST_FILENAME

    def load_manifest(self) -> IndexManifest:
        """Load persistent index manifest, or initialize a fresh one."""
        if self.manifest_path.is_file():
            try:
                raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                return IndexManifest.model_validate(raw)
            except Exception as err:
                logger.warning(
                    "Corrupt manifest at %s: %s. Creating fresh manifest.",
                    self.manifest_path,
                    err,
                )

        return IndexManifest(
            embedding_model=self.embedder.model_name,
            embedding_dimension=self.embedder.dimension,
            documents={},
        )

    def save_manifest(self, manifest: IndexManifest) -> None:
        """Persist index manifest to disk."""
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )

    def prepare_chunks(
        self,
        processed_doc: ProcessedDocument,
    ) -> list[IndexedChunk]:
        """Convert a ProcessedDocument into filtered, validated IndexedChunks."""
        indexed_chunks: list[IndexedChunk] = []

        for chunk in processed_doc.chunks:
            if not is_meaningful_chunk(chunk.text):
                continue

            cleaned_text = chunk.text.replace("\xad", "").strip()
            chunk_id = (
                f"{processed_doc.scheme_id}_p{chunk.page_number}_c{chunk.chunk_index}"
            )
            content_hash = compute_text_sha256(cleaned_text)

            meta = IndexedChunkMetadata(
                scheme_id=processed_doc.scheme_id,
                source_document=processed_doc.source_document,
                official_source_url=processed_doc.official_source_url,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                document_version=processed_doc.document_version or "",
                document_readiness="verified_digital_text",
                content_hash=content_hash,
            )

            indexed_chunks.append(
                IndexedChunk(
                    chunk_id=chunk_id,
                    text=cleaned_text,
                    metadata=meta,
                )
            )

        return indexed_chunks

    def index_processed_file(
        self,
        json_path: Path,
        force: bool = False,
    ) -> tuple[int, bool]:
        """Index a single processed JSON file idempotently.

        Returns:
            Tuple of (chunks_indexed, was_skipped).
        """
        if not json_path.is_file():
            msg = (
                f"Processed JSON file not found: {json_path}. "
                "Run Phase 1 ingestion CLI to generate it from the raw PDF."
            )
            raise IndexerError(msg)

        current_file_sha = compute_file_sha256(json_path)

        try:
            raw_data = json.loads(json_path.read_text(encoding="utf-8"))
            doc = ProcessedDocument.model_validate(raw_data)
        except Exception as err:
            msg = f"Failed to validate processed document at {json_path}: {err}"
            raise IndexerError(msg) from err

        manifest = self.load_manifest()

        # Check if model in manifest matches current embedder
        if manifest.embedding_model != self.embedder.model_name:
            if not force and manifest.documents:
                msg = (
                    f"Manifest model '{manifest.embedding_model}' does not match "
                    f"embedder '{self.embedder.model_name}'. "
                    "Re-indexing with force=True is required to avoid "
                    "incompatible vectors."
                )
                raise IndexerError(msg)
            # Reset manifest documents if model changed
            manifest = IndexManifest(
                embedding_model=self.embedder.model_name,
                embedding_dimension=self.embedder.dimension,
                documents={},
            )

        existing_record = manifest.documents.get(doc.scheme_id)

        # Idempotency check: Skip if SHA-256 matches and not forcing
        if (
            not force
            and existing_record
            and existing_record.content_sha256 == current_file_sha
        ):
            logger.info(
                "Scheme '%s' is up-to-date (SHA: %s). Skipping indexing.",
                doc.scheme_id,
                current_file_sha[:10],
            )
            return len(existing_record.chunk_ids), True

        # Prepare and filter chunks
        valid_chunks = self.prepare_chunks(doc)
        if not valid_chunks:
            logger.warning(
                "No substantive chunks found in %s after filtering noise.",
                json_path.name,
            )
            return 0, False

        # Generate embeddings *before* touching the existing index
        texts = [c.text for c in valid_chunks]
        try:
            embeddings = self.embedder.embed_texts(texts)
        except Exception as err:
            msg = f"Failed generating embeddings for scheme '{doc.scheme_id}': {err}"
            raise IndexerError(msg) from err

        chunk_ids = [c.chunk_id for c in valid_chunks]
        metadatas = [c.metadata.model_dump() for c in valid_chunks]

        # Stale chunk removal: if previous chunks existed for this scheme, delete them
        try:
            self.store.delete_scheme_chunks(self.collection_name, doc.scheme_id)
        except Exception as err:
            logger.debug(
                "No previous chunks to delete for '%s': %s", doc.scheme_id, err
            )

        # Upsert the new chunks
        self.store.upsert_chunks(
            collection_name=self.collection_name,
            chunk_ids=chunk_ids,
            texts=texts,
            embeddings=embeddings,
            metadatas=metadatas,
            expected_model=self.embedder.model_name,
            expected_dim=self.embedder.dimension,
        )

        # Update manifest
        new_record = DocumentIndexRecord(
            scheme_id=doc.scheme_id,
            source_file=json_path.name,
            content_sha256=current_file_sha,
            chunk_count=len(chunk_ids),
            chunk_ids=chunk_ids,
        )
        updated_docs = dict(manifest.documents)
        updated_docs[doc.scheme_id] = new_record

        new_manifest = IndexManifest(
            embedding_model=self.embedder.model_name,
            embedding_dimension=self.embedder.dimension,
            documents=updated_docs,
        )
        self.save_manifest(new_manifest)

        logger.info(
            "Successfully indexed '%s': %d chunks stored.",
            doc.scheme_id,
            len(chunk_ids),
        )
        return len(chunk_ids), False

    def index_all_verified_schemes(
        self,
        processed_dir: Path = Path("data/processed"),
        registry_path: Path = Path("data/scheme_registry.json"),
        force: bool = False,
    ) -> dict[str, int]:
        """Index all schemes verified for digital text extraction.

        Returns:
            Dict mapping scheme_id to indexed chunk count.
        """
        verified_schemes = get_verified_schemes_from_registry(registry_path)
        logger.info(
            "Found %d verified digital text schemes in registry: %s",
            len(verified_schemes),
            verified_schemes,
        )

        results: dict[str, int] = {}
        missing_schemes: list[str] = []

        for scheme_id in sorted(verified_schemes):
            json_file = processed_dir / f"{scheme_id}.json"
            if not json_file.is_file():
                missing_schemes.append(scheme_id)
                continue

            count, _ = self.index_processed_file(json_file, force=force)
            results[scheme_id] = count

        if missing_schemes:
            logger.warning(
                "Missing processed JSON for verified schemes: %s. "
                "Ensure Phase 1 ingestion has been run for these schemes.",
                missing_schemes,
            )

        return results
