"""
Centralised configuration for the ELH RAG system.

All environment variables are declared here, validated at import time, and
exposed as a single immutable `settings` object.
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
    pinecone_index_name: str = Field(
        default="elh-reviews",
        description="Pinecone index for student reviews",   
    )
    pinecone_descriptions_index_name: str = Field(
        default="elh-descriptions",
        description="Pinecone index for house + room descriptions",
    )

    # LLM (Anthropic)
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    llm_model: str = Field(default="claude-sonnet-4-20250514")
    llm_temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    llm_max_tokens: int = Field(default=1024, gt=0)

    # Query rewriting
    enable_query_rewriting: bool = Field(
        default=True,
        description="Toggle the LLM-based query rewriting step before retrival",
    )
    llm_rewriter_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Smaller/cheaper LLM used for query rewriting",
    )
    llm_rewriter_max_tokens: int = Field(default=256, gt=0)

    # Re-ranking
    enable_reranking: bool = Field(
        default=True,
        description="Toggle the cross-encoder reranking step after retrieval",
    )
    reranker_model: str = Field(
        default="BAAI/bge-reranker-v2-m3",
        description="Cross-encoder model for reranking (multilingual, 100+ languages)"
    )
    reranker_pool_size: int = Field(
        default=20,
        gt=0,
        le=100,
        description="Number of condidates to retrive before reranking",
    )
    reranker_batch_size: int = Field(default=16, gt=0)

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
