"""
RAG pipeline orchestration.
"""
from __future__ import annotations
 
import logging
 
from elh_rag.generation.llm_client import LLMClient
from elh_rag.indexing.embeddings import Embedder
from elh_rag.indexing.pinecone_store import PineconeVectorStore
from elh_rag.indexing.vector_store import VectorStore
from elh_rag.orchestration.descriptions_pipeline import DescriptionsPipeline
from elh_rag.orchestration.orchestrator import Orchestrator
from elh_rag.orchestration.reviews_pipeline import ReviewsPipeline
from elh_rag.retrieval.conversation_memory import ConversationMemory
from elh_rag.retrieval.followup_rewriter import FollowUpRewriter
from elh_rag.retrieval.intent_router import IntentRouter
from elh_rag.retrieval.query_rewriter import QueryRewriter
from elh_rag.retrieval.reranker import Reranker
from elh_rag.schemas import RAGResponse
 
logger = logging.getLogger(__name__)
logger = logging.getLogger(__name__)


class RAGPipeline:
    """Facade maintaining the Phase-1 public API on top of the Orchestrator."""
 
    def __init__(
        self,
        vector_store: VectorStore | None = None,
        embedder: Embedder | None = None,
        llm_client: LLMClient | None = None,
        query_rewriter: QueryRewriter | None = None,
        reranker: Reranker | None = None,
        intent_router: IntentRouter | None = None,
        followup_rewriter: FollowUpRewriter | None = None,
        descriptions_store: VectorStore | None = None,
    ) -> None:
        reviews_pipeline = ReviewsPipeline(
            vector_store=vector_store or PineconeVectorStore(),
            embedder=embedder,
            query_rewriter=query_rewriter,
            reranker=reranker,
        )
        descriptions_pipeline = DescriptionsPipeline(
            vector_store=descriptions_store,
            embedder=embedder,
            query_rewriter=query_rewriter,
            reranker=reranker,
        )
        self._orchestrator = Orchestrator(
            reviews_pipeline=reviews_pipeline,
            descriptions_pipeline=descriptions_pipeline,
            intent_router=intent_router,
            llm_client=llm_client,
            followup_rewriter=followup_rewriter,
        )
 
    def query(
        self,
        question: str,
        top_k: int | None = None,
        city_filter: str | None = None,
        min_rating: int | None = None,
        conversation_memory: ConversationMemory | None = None,
    ) -> RAGResponse:
        """Run the orchestrated pipeline on a single question."""
        return self._orchestrator.query(
            question=question,
            top_k=top_k,
            city_filter=city_filter,
            min_rating=min_rating,
            conversation_memory=conversation_memory,
        )