"""FastAPI application entry point for the Government Scheme Navigator.

Run with:
    uvicorn src.api.main:app --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.errors import register_error_handlers
from src.api.routers import eligibility, health, query, schemes
from src.api.services import ApiServices, build_api_services
from src.config import Settings, get_settings

logger = logging.getLogger(__name__)


def create_app(
    services: ApiServices | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    """Create the API app with optional injected services for tests."""
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Initialize shared services while keeping model loading lazy."""
        logger.info("Government Scheme Navigator API starting up.")
        if services is not None:
            application.state.api_services = services
        else:
            application.state.api_services = build_api_services(app_settings)
        yield
        logger.info("Government Scheme Navigator API shutting down.")

    application = FastAPI(
        title="Government Scheme Navigator",
        description=(
            "Multilingual assistant for discovering Indian government welfare "
            "schemes and exploring official scheme evidence."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    if services is not None:
        application.state.api_services = services

    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(application)
    application.include_router(health.router)
    application.include_router(health.api_router)
    application.include_router(query.router)
    application.include_router(schemes.router)
    application.include_router(eligibility.router)
    return application


app = create_app()
