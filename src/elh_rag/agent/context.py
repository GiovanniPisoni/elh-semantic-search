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


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Container of shared resources for a single agent turn."""

    @classmethod
    def build(cls) -> AgentContext:
        """Construct an AgentContext with eagerly-loaded resources."""
        raise NotImplementedError("Implemented in next step")
