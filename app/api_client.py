"""Small HTTP client for the Government Scheme Navigator API."""

from __future__ import annotations

from typing import Any

import httpx


class ApiClientError(Exception):
    """A safe-to-display API communication or response error."""

    def __init__(
        self,
        message: str,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class GovernmentSchemeApiClient:
    """Call the backend endpoints without duplicating domain logic."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )

    def health(self) -> dict[str, Any]:
        """Fetch API component readiness."""
        return self._request("GET", "/api/health")

    def list_schemes(
        self,
        query: str | None = None,
        jurisdiction: str | None = None,
        verification_status: str | None = None,
    ) -> dict[str, Any]:
        """Fetch scheme metadata using backend filters."""
        params: dict[str, str] = {}
        if query:
            params["q"] = query
        if jurisdiction:
            params["jurisdiction"] = jurisdiction
        if verification_status:
            params["verification_status"] = verification_status
        return self._request("GET", "/api/schemes", params=params)

    def ask(self, query: str, scheme_id: str | None = None) -> dict[str, Any]:
        """Submit an informational question to retrieval."""
        body: dict[str, str] = {"query": query}
        if scheme_id:
            body["scheme_id"] = scheme_id
        return self._request("POST", "/api/query", body=body)

    def check_eligibility(
        self, scheme_id: str, profile: dict[str, str | int | float | None]
    ) -> dict[str, Any]:
        """Submit caller-entered profile fields to the deterministic backend."""
        return self._request(
            "POST",
            "/api/eligibility/check",
            body={"scheme_id": scheme_id, "profile": profile},
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, params=params, json=body)
        except httpx.TimeoutException as error:
            raise ApiClientError(
                "The service took too long to respond.", code="timeout"
            ) from error
        except httpx.RequestError as error:
            raise ApiClientError(
                "The Government Scheme Navigator API is unavailable.",
                code="api_unavailable",
            ) from error

        if not response.is_success:
            code, message = self._error_details(response)
            raise ApiClientError(message, code=code, status_code=response.status_code)

        try:
            payload = response.json()
        except ValueError as error:
            raise ApiClientError("The API returned an unreadable response.") from error
        if not isinstance(payload, dict):
            raise ApiClientError("The API returned an unexpected response format.")
        return payload

    @staticmethod
    def _error_details(response: httpx.Response) -> tuple[str | None, str]:
        try:
            error = response.json().get("error", {})
            message = error.get("message")
            code = error.get("code")
            if isinstance(message, str) and message.strip():
                return code if isinstance(code, str) else None, message
        except (AttributeError, ValueError):
            pass
        return None, f"The API request failed (HTTP {response.status_code})."
