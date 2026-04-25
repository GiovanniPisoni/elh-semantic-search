"""
Cross-encoder reranker

Retrieve-and-rerank pipeline for high accuracy and multilingual support.
    1. Retrieval: Fast approximate vector search (top 20).
    2. Reranking: Joint query-document scoring via BGE-m3 cross-encoder (top 5).
"""
from __future__ import annotations

import logging
from typing import Any

from elh_rag.config import settings
from elh_rag.schemas import RetrievalResult

logger = logging.getLogger(__name__)

class Reranker:
    """
    Cross-encoder reranker for improved top-k selection.

    Handles model initialization efficiently:
        - Lazy loading: ensures importing the module remains cheap.
        - Streamlit caching (@st.cache_resource): loads the model only once per process lifetime.
    """

    def __init__(
        self,
        model_name: str | None = None,
        batch_size: int | None = None,    
    ) -> None:
        self._model_name = model_name or settings.reranker_model
        self._batch_size = batch_size or settings.reranker_batch_size
        self._model: Any | None = None
    
    @property
    def model(self) -> Any:
        """Lazily-initialised CrossEncoder model."""
        if self._model is None:
            from sentence_transformers import CrossEncoder

            logger.info("Loading cross-encoder model: %s", self._model_name)
            self._model = CrossEncoder(self._model_name)
            logger.info("Corss-encoder ready")
        return self._model
    
    def rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        top_k: int,
    ) -> list[RetrievalResult]:
        """Re-score and reorder candidates by relevance to the query.
        
        Returns the top_k candidates sorted by descending rerank score.
        Each returned RetrievalResult preserves its original vector_score
        and is augmented with the new rerank_score.
        """
        if not candidates:
            return []
        
        try:
            pairs = [(query, c.text) for c in candidates]
            scores = self.model.predict(
                pairs,
                batch_size=self._batch_size,
                show_progress_bar=False,
            )
        except Exception as e:
            logger.warning(
                "Reranking failed (%s) — falling back to vector-only order", e
            )
            return candidates[:top_k]
        
        scored = [
            RetrievalResult(
                text=c.text,
                metadata=c.metadata,
                vector_score=c.vector_score,
                rerank_score=float(score),
            )
            for c, score in zip(candidates, scores)
        ]

        scored.sort(key=lambda r: r.rerank_score or 0.0, reverse=True)
        return scored[:top_k]