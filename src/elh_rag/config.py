"""
Centralised configuration for the ELH RAG system.

All environment variables are declared here, validated at import time, and
exposed as a single immutable `settings` object. No other module in the
codebase should call `os.getenv` directly.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All configuration values for the ELH RAG system."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database (Supabase)
    db_uri: str = Field(..., description="PostgreSQL connection URI")

    # Vector store (Pinecone)
    pinecone_api_key: str = Field(..., description="Pinecone API key")
    pinecone_index_name: str = Field(default="elh-reviews")

    # LLM (Anthropic)
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    llm_model: str = Field(default="claude-sonnet-4-20250514")
    llm_temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    llm_max_tokens: int = Field(default=1024, gt=0)

    # Embeddings
    embedding_model: str = Field(
        default="paraphrase-multilingual-mpnet-base-v2",
        description="SentenceTransformer model name (multilingual EN+PT)",
    )

    # Retrieval
    retrieval_top_k: int = Field(default=5, gt=0, le=50)

    # Indexing
    indexing_batch_size: int = Field(default=32, gt=0)
    indexing_upsert_batch: int = Field(default=100, gt=0)
    min_text_length: int = Field(default=30, ge=0)

    # Logging
    log_level: str = Field(default="INFO")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings singleton."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
