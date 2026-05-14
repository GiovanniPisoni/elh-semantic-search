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
        description="Cross-encoder model for reranking (multilingual, 100+ languages)",
    )
    reranker_pool_size: int = Field(
        default=20,
        gt=0,
        le=100,
        description="Number of condidates to retrive before reranking",
    )
    reranker_batch_size: int = Field(default=16, gt=0)

    # Tool 3 — total cost computation
    reservation_fee_pct: float = Field(
        default=0.09,
        ge=0.0,
        le=1.0,
        description=(
            "Reservation fee as a fraction of total rent (default 0.09 = 9%). "
            "Confirmed with ELH business 2026-05-11."
        ),
    )

    # Intent routing
    enable_intent_routing: bool = Field(
        default=True,
        description="Toggle the LLM-based intent router; disable for A/B in Phase 4",
    )
    intent_router_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Smaller/cheaper LLM used for intent classification",
    )
    intent_router_confidence_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum confidence to commit to a single-corpus route; "
            "below this, query both corpora and let the reranker merge"
        ),
    )
    intent_router_max_tokens: int = Field(default=200, gt=0)

    # Conversational memory
    enable_conversational_memory: bool = Field(
        default=True,
        description="Toggle follow-up rewriting using conversation history",
    )
    conversational_memory_max_turns: int = Field(
        default=5,
        gt=0,
        le=20,
        description="How many past (question, answer) pairs to keep in memory",
    )
    followup_rewriter_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="LLM used to expand follow-up questions into standalone queries",
    )
    followup_rewriter_max_tokens: int = Field(default=200, gt=0)

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

    # Agent layer (Phase 3 D4)
    agent_llm_model: str = Field(
        default="claude-sonnet-4-5",
        description="LLM model used by the Phase 3 agent loop (D4.1).",
    )
    agent_llm_max_tokens: int = Field(default=4096, gt=0)
    agent_llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Sampling temperature for the agent LLM. Default 0.0 for "
            "deterministic tool routing and reproducible benchmarks."
        ),
    )
    agent_llm_max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description=(
            "Maximum number of tenacity retry attempts on transient LLM API errors (D4.8)."
        ),
    )
    agent_max_hops: int = Field(
        default=5,
        ge=1,
        le=20,
        description=("Maximum LLM-call + tool-dispatch iterations per agent turn (D4.5)."),
    )
    agent_max_query_chars: int = Field(
        default=4000,
        gt=0,
        description=("Hard upper bound on user query length in characters (D6.4)."),
    )

    # Logging
    log_level: str = Field(default="INFO")
    log_file_path: Path | None = Field(
        default=None,
        description=(
            "Optional path to a JSON Lines log file. When set, structured "
            "events are persisted in addition to stdout. Leave unset for "
            "development; set in benchmark/production environments to "
            "enable post-hoc analysis (e.g. logs/elh_rag.jsonl)."
        ),
    )
    log_file_max_bytes: int = Field(
        default=10_485_760,  # 10 MB
        gt=0,
        description="Maximum size of a single rotated log file, in bytes.",
    )
    log_file_backup_count: int = Field(
        default=5,
        ge=0,
        description="Number of rotated log file backups to keep.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings singleton."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
