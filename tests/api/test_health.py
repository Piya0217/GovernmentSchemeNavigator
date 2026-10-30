"""Tests for GET /health endpoint.

Uses FastAPI's TestClient (synchronous httpx transport) so no running
server is required.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)


def test_health_returns_200() -> None:
    """GET /health must respond with HTTP 200."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_body() -> None:
    """GET /health body must contain the expected fields and values."""
    response = client.get("/health")
    body = response.json()

    assert body["status"] == "ok"
    assert body["service"] == "government-scheme-navigator"
    assert "version" in body


def test_health_content_type_is_json() -> None:
    """GET /health must return application/json."""
    response = client.get("/health")
    assert "application/json" in response.headers["content-type"]
