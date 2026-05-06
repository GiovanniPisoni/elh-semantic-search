"""ELH Semantic Search — RAG-based system for Erasmus Life Housing."""

from __future__ import annotations

from elh_rag.config import settings
from elh_rag.pipeline import RAGPipeline
from elh_rag.schemas import (
    Document,
    DocumentSource,
    RAGResponse,
    RetrievalResult,
    ReviewMetadata,
)

__all__ = [
    "Document",
    "DocumentSource",
    "RAGPipeline",
    "RAGResponse",
    "RetrievalResult",
    "ReviewMetadata",
    "settings",
]

__version__ = "0.2.0"
