"""Consistent JSON errors for application service failures."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ApiServiceError(Exception):
    """An expected service error safe to expose through the API."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


async def handle_api_service_error(
    request: Request,
    error: ApiServiceError,
) -> JSONResponse:
    """Serialize a service error without leaking implementation details."""
    del request
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {"code": error.code, "message": error.message}},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register application-level exception handlers."""
    app.add_exception_handler(ApiServiceError, handle_api_service_error)
