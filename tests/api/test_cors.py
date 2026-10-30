"""Tests for explicit browser-origin configuration."""

from __future__ import annotations

from fastapi.testclient import TestClient
from src.api.main import create_app
from src.config import Settings


def test_configured_cors_origin_is_allowed(tmp_path) -> None:
    app = create_app(
        settings=Settings(
            cors_origins=["https://citizen.example"],
            chroma_persist_dir=str(tmp_path / "missing-index"),
        )
    )
    with TestClient(app) as client:
        response = client.options(
            "/api/query",
            headers={
                "Origin": "https://citizen.example",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://citizen.example"


def test_unconfigured_cors_origin_is_not_reflected(tmp_path) -> None:
    app = create_app(
        settings=Settings(
            cors_origins=[],
            chroma_persist_dir=str(tmp_path / "missing-index"),
        )
    )
    with TestClient(app) as client:
        response = client.options(
            "/api/query",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert "access-control-allow-origin" not in response.headers
