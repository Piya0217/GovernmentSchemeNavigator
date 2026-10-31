"""Tests for path resolution and retrieval readiness without external services."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import chromadb
from fastapi.testclient import TestClient
from src.api.main import create_app
from src.api.services import PROJECT_ROOT, resolve_chroma_persist_dir
from src.config import Settings


class _FakeCollection:
    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        return self._count

    def get(self, limit: int, include: list[str]) -> dict[str, list[Any]]:
        assert limit == 1
        assert include == ["documents", "metadatas"]
        if self._count == 0:
            return {"documents": [], "metadatas": []}
        return {
            "documents": ["Indexed scheme passage."],
            "metadatas": [
                {
                    "scheme_id": "central_pm_kisan",
                    "source_document": "pm_kisan.pdf",
                    "official_source_url": "https://example.gov/document.pdf",
                    "page_number": 1,
                    "chunk_index": 0,
                }
            ],
        }


class _FakeClient:
    def __init__(self, collection_count: int | None) -> None:
        self._collection_count = collection_count

    def list_collections(self) -> list[types.SimpleNamespace]:
        if self._collection_count is None:
            return []
        return [types.SimpleNamespace(name="scheme_chunks")]

    def get_collection(self, name: str) -> _FakeCollection:
        assert name == "scheme_chunks"
        assert self._collection_count is not None
        return _FakeCollection(self._collection_count)


def _api_retrieval_status(
    tmp_path: Path,
    monkeypatch: Any,
    client: _FakeClient | None = None,
    client_error: Exception | None = None,
) -> str:
    """Build the real application services with a fake Chroma client."""
    database_dir = tmp_path / "chroma"
    database_dir.mkdir()
    (database_dir / "chroma.sqlite3").touch()

    def make_client(*, path: str) -> _FakeClient:
        assert path == str(database_dir.resolve())
        if client_error is not None:
            raise client_error
        assert client is not None
        return client

    monkeypatch.setattr(chromadb, "PersistentClient", make_client)
    app = create_app(settings=Settings(chroma_persist_dir=str(database_dir)))
    with TestClient(app) as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 200
    return response.json()["retrieval"]


def test_default_chroma_path_is_stable_across_working_directories(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("CHROMA_PERSIST_DIR", raising=False)
    settings = Settings(_env_file=None)
    first_cwd = tmp_path / "first"
    second_cwd = tmp_path / "second"
    first_cwd.mkdir()
    second_cwd.mkdir()

    monkeypatch.chdir(first_cwd)
    first_path = resolve_chroma_persist_dir(settings)
    monkeypatch.chdir(second_cwd)
    second_path = resolve_chroma_persist_dir(settings)

    assert first_path == second_path == (PROJECT_ROOT / "data/chroma").resolve()


def test_settings_dotenv_file_is_anchored_to_repository_root() -> None:
    assert Settings.model_config["env_file"] == PROJECT_ROOT / ".env"


def test_absolute_chroma_path_override_is_preserved(tmp_path: Path) -> None:
    override = tmp_path / "custom-index"
    settings = Settings(chroma_persist_dir=str(override))

    assert resolve_chroma_persist_dir(settings) == override.resolve()


def test_valid_nonempty_indexed_collection_reports_ready(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    assert (
        _api_retrieval_status(
            tmp_path,
            monkeypatch,
            client=_FakeClient(collection_count=3),
        )
        == "ready"
    )


def test_missing_collection_does_not_report_ready(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    assert (
        _api_retrieval_status(
            tmp_path,
            monkeypatch,
            client=_FakeClient(collection_count=None),
        )
        == "collection_missing"
    )


def test_empty_collection_does_not_report_ready(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    assert (
        _api_retrieval_status(
            tmp_path,
            monkeypatch,
            client=_FakeClient(collection_count=0),
        )
        == "collection_empty"
    )


def test_invalid_database_does_not_report_ready(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    assert (
        _api_retrieval_status(
            tmp_path,
            monkeypatch,
            client_error=RuntimeError("invalid Chroma database"),
        )
        == "unavailable"
    )


def test_health_does_not_load_embedding_model(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    def forbidden_model_load(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Health checks must not load the embedding model.")

    fake_sentence_transformers = types.ModuleType("sentence_transformers")
    fake_sentence_transformers.SentenceTransformer = forbidden_model_load
    monkeypatch.setitem(
        sys.modules, "sentence_transformers", fake_sentence_transformers
    )

    status = _api_retrieval_status(
        tmp_path,
        monkeypatch,
        client=_FakeClient(collection_count=1),
    )

    assert status == "ready"
