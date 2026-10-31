"""Application configuration loaded from environment variables.

Uses pydantic-settings so every value is validated at startup.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Central configuration for the Government Scheme Navigator API."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: str = Field(default="development", description="Runtime environment.")
    log_level: str = Field(default="INFO", description="Logging level.")

    # API
    api_host: str = Field(default="127.0.0.1", description="Bind host.")
    api_port: int = Field(default=8000, description="Bind port.")
    cors_origins: list[str] = Field(
        default_factory=list,
        description="Explicit browser origins allowed to call the API.",
    )

    # ChromaDB
    chroma_persist_dir: str = Field(
        default="./data/chroma",
        description="Path for ChromaDB persistence.",
    )

    # Embeddings
    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        description="HuggingFace sentence-transformers model ID.",
    )

    # LLM (future use)
    llm_provider: str = Field(default="", description="LLM provider identifier.")
    llm_model: str = Field(default="", description="LLM model name/ID.")
    llm_api_key: str = Field(default="", description="LLM API key.")


def get_settings() -> Settings:
    """Return a validated Settings instance (reads .env on first call)."""
    return Settings()
