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

from src.api.routers import health

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle events."""
    logger.info("Government Scheme Navigator API starting up.")
    yield
    logger.info("Government Scheme Navigator API shutting down.")


app = FastAPI(
    title="Government Scheme Navigator",
    description=(
        "Multilingual AI assistant for discovering Indian government welfare schemes "
        "and checking eligibility using official scheme documents."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS (permissive in development; tighten in production via env config)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health.router)
