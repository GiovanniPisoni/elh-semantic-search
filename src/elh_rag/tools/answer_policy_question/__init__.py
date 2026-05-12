"""Tool 6: ``answer_policy_question``.

Package layout (SRP-split):

    * :mod:`._models`   — KBEntry (Pydantic) + IndexedEntry
                          (dataclass with precomputed embeddings).
                          ``Audience`` Literal lives here.
    * :mod:`._store`    — KBStore: in-memory store + cosine search +
                          audience filter + threshold. Pure
                          algorithms, no I/O.
    * :mod:`._loader`   — YAML loader, cross-ref validation, and
                          the combined ``build_indexed_entries``
                          factory.
    * :mod:`._context`  — KBContext: bundles KBStore + Embedder
                          into the ctx object injected into Tool 6.
                          Distinct from the DBExecutor ctx used by
                          Tools 1-5.
    * :mod:`.tool`      — registered entry point, Pydantic I/O,
                          fallback-message composition.
    * :mod:`.kb`        — directory holding ``policies.yaml`` (26
                          hand-curated entries across 10 categories).
"""

from ._context import KBContext
from ._loader import build_indexed_entries, load_entries
from ._models import Audience, IndexedEntry, KBEntry
from ._store import KBStore, _audience_matches, _cosine_similarity
from .tool import (
    AnswerPolicyQuestionInput,
    AnswerPolicyQuestionOutput,
    PolicyMatch,
    answer_policy_question,
)

__all__ = [
    "AnswerPolicyQuestionInput",
    "AnswerPolicyQuestionOutput",
    "Audience",
    "IndexedEntry",
    "KBContext",
    "KBEntry",
    "KBStore",
    "PolicyMatch",
    "_audience_matches",
    "_cosine_similarity",
    "answer_policy_question",
    "build_indexed_entries",
    "load_entries",
]
