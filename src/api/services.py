"""Application services and runtime dependency construction."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from src.agent.orchestrator import WorkflowOrchestrator
from src.agent.retrieval_adapter import RetrievalAdapter
from src.api.eligibility_service import EligibilityService
from src.api.schemas.schemes import (
    Jurisdiction,
    SchemeListResponse,
    SchemeRegistryDocument,
    VerificationStatus,
)
from src.config import Settings

logger = logging.getLogger("scheme_navigator.api.services")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RetrievalStatus = Literal[
    "ready",
    "collection_missing",
    "collection_empty",
    "unavailable",
]


class SchemeRegistryUnavailableError(Exception):
    """Raised when the registry cannot be read or validated."""


class SchemeRegistryService:
    """Read, validate, and filter the source scheme registry."""

    def __init__(self, registry_path: Path) -> None:
        self._registry_path = registry_path

    def _load(self) -> SchemeRegistryDocument:
        """Load and validate the registry without replacing missing values."""
        try:
            raw_registry = json.loads(self._registry_path.read_text(encoding="utf-8"))
            return SchemeRegistryDocument.model_validate(raw_registry)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            logger.error("Unable to load scheme registry: %s", error)
            raise SchemeRegistryUnavailableError from error

    def is_available(self) -> bool:
        """Check the actual registry file and schema for health reporting."""
        try:
            self._load()
        except SchemeRegistryUnavailableError:
            return False
        return True

    def list_schemes(
        self,
        jurisdiction: Jurisdiction | None = None,
        verification_status: VerificationStatus | None = None,
        name_query: str | None = None,
    ) -> SchemeListResponse:
        """Return registry entries matching the optional API filters."""
        registry = self._load()
        schemes = registry.schemes
        if jurisdiction is not None:
            schemes = [item for item in schemes if item.jurisdiction == jurisdiction]
        if verification_status is not None:
            schemes = [
                item
                for item in schemes
                if item.verification_status == verification_status
            ]
        if name_query:
            query = name_query.casefold().strip()
            schemes = [item for item in schemes if query in item.scheme_name.casefold()]
        return SchemeListResponse(
            version=registry.version,
            last_updated=registry.last_updated,
            total=len(schemes),
            schemes=schemes,
        )


@dataclass(frozen=True)
class ApiServices:
    """Injected API dependencies shared for the application lifetime."""

    workflow: WorkflowOrchestrator
    scheme_registry: SchemeRegistryService
    retrieval_status: RetrievalStatus
    eligibility: EligibilityService = field(
        default_factory=lambda: EligibilityService(PROJECT_ROOT / "data" / "rules")
    )
    eligibility_status: Literal["ready", "unavailable", "not_configured"] = (
        "not_configured"
    )


def resolve_chroma_persist_dir(settings: Settings) -> Path:
    """Resolve configured relative Chroma paths from the repository root."""
    configured_path = Path(settings.chroma_persist_dir).expanduser()
    if not configured_path.is_absolute():
        configured_path = PROJECT_ROOT / configured_path
    return configured_path.resolve()


def build_api_services(settings: Settings) -> ApiServices:
    """Build lazy retrieval dependencies and the registry service."""
    registry_path = PROJECT_ROOT / "data" / "scheme_registry.json"
    registry_service = SchemeRegistryService(registry_path)
    eligibility_service = EligibilityService(PROJECT_ROOT / "data" / "rules")
    eligibility_status = eligibility_service.readiness()

    chroma_dir = resolve_chroma_persist_dir(settings)
    chroma_database = chroma_dir / "chroma.sqlite3"
    if not chroma_database.is_file():
        return ApiServices(
            workflow=WorkflowOrchestrator(retrieval=None),
            scheme_registry=registry_service,
            retrieval_status="unavailable",
            eligibility=eligibility_service,
            eligibility_status=eligibility_status,
        )

    try:
        import chromadb

        from src.retrieval.answer import AnswerBuilder
        from src.retrieval.embedder import SentenceTransformerEmbedder
        from src.retrieval.search import SchemeSearcher
        from src.retrieval.store import DEFAULT_COLLECTION_NAME, ChromaVectorStore

        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection_names = {
            item if isinstance(item, str) else item.name
            for item in client.list_collections()
        }
        if DEFAULT_COLLECTION_NAME not in collection_names:
            return ApiServices(
                workflow=WorkflowOrchestrator(retrieval=None),
                scheme_registry=registry_service,
                retrieval_status="collection_missing",
                eligibility=eligibility_service,
                eligibility_status=eligibility_status,
            )

        collection = client.get_collection(name=DEFAULT_COLLECTION_NAME)
        if collection.count() == 0:
            return ApiServices(
                workflow=WorkflowOrchestrator(retrieval=None),
                scheme_registry=registry_service,
                retrieval_status="collection_empty",
                eligibility=eligibility_service,
                eligibility_status=eligibility_status,
            )
        sample = collection.get(limit=1, include=["documents", "metadatas"])
        documents = sample.get("documents") or []
        metadatas = sample.get("metadatas") or []
        required_metadata = {
            "scheme_id",
            "source_document",
            "official_source_url",
            "page_number",
            "chunk_index",
        }
        if (
            not documents
            or not isinstance(documents[0], str)
            or not documents[0].strip()
            or not metadatas
            or not required_metadata.issubset(metadatas[0])
            or not all(
                str(metadatas[0][key]).strip()
                for key in (
                    "scheme_id",
                    "source_document",
                    "official_source_url",
                )
            )
            or int(metadatas[0]["page_number"]) < 1
            or int(metadatas[0]["chunk_index"]) < 0
        ):
            return ApiServices(
                workflow=WorkflowOrchestrator(retrieval=None),
                scheme_registry=registry_service,
                retrieval_status="unavailable",
                eligibility=eligibility_service,
                eligibility_status=eligibility_status,
            )

        store = ChromaVectorStore(persist_dir=chroma_dir, client=client)
        embedder = SentenceTransformerEmbedder(model_name=settings.embedding_model)
        searcher = SchemeSearcher(vector_store=store, embedder=embedder)
        answer_builder = AnswerBuilder(searcher=searcher)
        retrieval = RetrievalAdapter(answer_builder)
    except Exception as error:
        logger.exception("Unable to initialize retrieval adapter: %s", error)
        return ApiServices(
            workflow=WorkflowOrchestrator(retrieval=None),
            scheme_registry=registry_service,
            retrieval_status="unavailable",
            eligibility=eligibility_service,
            eligibility_status=eligibility_status,
        )

    return ApiServices(
        workflow=WorkflowOrchestrator(retrieval=retrieval),
        scheme_registry=registry_service,
        retrieval_status="ready",
        eligibility=eligibility_service,
        eligibility_status=eligibility_status,
    )
