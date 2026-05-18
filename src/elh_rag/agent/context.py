"""
Shared per-turn agent state.

``AgentContext`` is built once at startup and passed by reference to
every tool invocation in a turn. It bundles every resource that the
tools need:

    * ``db``              - DBExecutor for Tools 1-5 (SQL aggregates)
    * ``kb``              - KBContext for Tool 6 (in-memory NumPy KB)
    * ``embedder``        - SentenceTransformer (shared with Phase 2)
    * ``descriptions_store`` - VectorStore for search_descriptions
    * ``reviews_store``   - VectorStore for search_reviews
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from elh_rag.config import settings
from elh_rag.indexing.embeddings import Embedder
from elh_rag.indexing.pinecone_store import PineconeVectorStore
from elh_rag.indexing.vector_store import VectorStore
from elh_rag.tools._shared.db import DBExecutor, Psycopg2Executor
from elh_rag.tools.answer_policy_question._context import KBContext


@lru_cache
def _cached_embedder() -> Embedder:
    """Module-level cache of the SentenceTransformer instance."""
    return Embedder()


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Container of shared resources for a single agent turn."""

    db: DBExecutor
    kb: KBContext
    embedder: Embedder
    descriptions_store: VectorStore
    reviews_store: VectorStore

    @classmethod
    def build(cls) -> AgentContext:
        """Construct an AgentContext with eagerly-loaded resources."""
        embedder = _cached_embedder()
        return cls(
            db=Psycopg2Executor(dsn=settings.db_uri),
            kb=KBContext.from_default_yaml(embedder),
            embedder=embedder,
            descriptions_store=PineconeVectorStore(
                index_name=settings.pinecone_descriptions_index_name,
            ),
            reviews_store=PineconeVectorStore(
                index_name=settings.pinecone_index_name,
            ),
        )
