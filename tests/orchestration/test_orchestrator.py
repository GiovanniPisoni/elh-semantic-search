"""Tests for the Orchestrator.

The orchestrator wires IntentRouter + per-corpus pipelines + generation
LLM together. Tests verify:
    - Correct pipeline(s) activated per routing intent
    - Sources merged by score, preserving per-corpus groups
    - RAGResponse payload shape (sources_by_source, routing)
    - Intent routing disabled → reviews-only behaviour (Phase 1 parity)
    - Empty retrieval paths
"""

from __future__ import annotations

from typing import Any

import pytest
from tests.conftest import FakeQueryRewriter, FakeReranker, FakeVectorStore

from elh_rag.generation.llm_client import LLMClient
from elh_rag.indexing.embeddings import Embedder
from elh_rag.orchestration.descriptions_pipeline import DescriptionsPipeline
from elh_rag.orchestration.orchestrator import (
    Orchestrator,
    _build_context,
    _build_descriptions_filter,
    _build_reviews_filter,
    _empty_answer,
    _mode_label,
    _select_prompts,
)
from elh_rag.orchestration.reviews_pipeline import ReviewsPipeline
from elh_rag.retrieval.intent_router import IntentRouter
from elh_rag.schemas import (
    DocumentSource,
    HouseMetadata,
    Intent,
    RetrievalResult,
    ReviewMetadata,
    RoomMetadata,
    RoutingDecision,
)

# Fake IntentRouter


class _FakeRouter(IntentRouter):
    """IntentRouter that returns canned RoutingDecision."""

    def __init__(self, decision: RoutingDecision) -> None:
        self._decision = decision
        self.calls: list[str] = []

    def route(self, query: str) -> RoutingDecision:
        self.calls.append(query)
        return self._decision


# Fixture factories


def _make_review_matches(n: int) -> list[dict[str, Any]]:
    out = []
    for i in range(n):
        meta = ReviewMetadata(
            id=f"rev-{i:03d}",
            city="Lisbon",
            flatname=f"House {i}",
            review_text_original=f"Review text {i}",
        )
        out.append({"id": meta.id, "score": 0.9 - i * 0.05, "metadata": meta.to_pinecone_dict()})
    return out


def _make_description_matches(n: int) -> list[dict[str, Any]]:
    out = []
    for i in range(n):
        is_house = i % 2 == 0
        if is_house:
            meta = HouseMetadata(
                id=f"house:H{i}",
                idhouse=f"H{i}",
                flatname=f"Flat {i}",
                city="Porto",
            )
        else:
            meta = RoomMetadata(
                id=f"room:R{i}",
                idroom=f"R{i}",
                roomname=f"Room {i}",
                flatname=f"Flat {i}",
                city="Porto",
            )
        raw_md = meta.to_pinecone_dict()
        raw_md["text"] = f"Description text {i}"
        out.append({"id": meta.id, "score": 0.85 - i * 0.05, "metadata": raw_md})
    return out


def _make_orchestrator(
    reviews_matches: list[dict[str, Any]],
    descriptions_matches: list[dict[str, Any]],
    router: IntentRouter,
    llm: LLMClient,
    embedder: Embedder,
) -> tuple[Orchestrator, FakeVectorStore, FakeVectorStore]:
    reviews_store = FakeVectorStore(canned_matches=reviews_matches)
    descriptions_store = FakeVectorStore(canned_matches=descriptions_matches)

    reviews_pipeline = ReviewsPipeline(
        vector_store=reviews_store,
        embedder=embedder,
        query_rewriter=FakeQueryRewriter(passthrough=True),
        reranker=FakeReranker(reverse=False),
    )
    descriptions_pipeline = DescriptionsPipeline(
        vector_store=descriptions_store,
        embedder=embedder,
        query_rewriter=FakeQueryRewriter(passthrough=True),
        reranker=FakeReranker(reverse=False),
    )

    orchestrator = Orchestrator(
        reviews_pipeline=reviews_pipeline,
        descriptions_pipeline=descriptions_pipeline,
        intent_router=router,
        llm_client=llm,
    )
    return orchestrator, reviews_store, descriptions_store


def _disable_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 1 baseline: rewriter and reranker off."""
    from elh_rag import config as cfg

    monkeypatch.setattr(cfg.settings, "enable_query_rewriting", False)
    monkeypatch.setattr(cfg.settings, "enable_reranking", False)
    monkeypatch.setattr(cfg.settings, "enable_intent_routing", True)


# Intent = reviews routes to reviews pipeline only


def test_intent_reviews_activates_only_reviews_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    _disable_extras(monkeypatch)

    router = _FakeRouter(RoutingDecision(intent=Intent.REVIEWS, confidence=0.9, source="llm"))
    orch, reviews_store, descriptions_store = _make_orchestrator(
        reviews_matches=_make_review_matches(3),
        descriptions_matches=_make_description_matches(3),
        router=router,
        llm=fake_llm,
        embedder=fake_embedder,
    )

    response = orch.query("did students feel safe?", top_k=3)

    # Reviews store queried, descriptions store NOT queried
    assert len(reviews_store.query_calls) == 1
    assert len(descriptions_store.query_calls) == 0

    # All sources are reviews
    assert len(response.sources) == 3
    assert all(s.metadata.source == DocumentSource.REVIEW for s in response.sources)
    assert response.sources_by_source is not None
    assert "reviews" in response.sources_by_source
    assert "descriptions" not in response.sources_by_source


# Intent = descriptions routes to descriptions only


def test_intent_descriptions_activates_only_descriptions_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    _disable_extras(monkeypatch)

    router = _FakeRouter(RoutingDecision(intent=Intent.DESCRIPTIONS, confidence=0.95, source="llm"))
    orch, reviews_store, descriptions_store = _make_orchestrator(
        reviews_matches=_make_review_matches(3),
        descriptions_matches=_make_description_matches(4),
        router=router,
        llm=fake_llm,
        embedder=fake_embedder,
    )

    response = orch.query("apartments with balcony", top_k=4)

    assert len(reviews_store.query_calls) == 0
    assert len(descriptions_store.query_calls) == 1
    assert len(response.sources) == 4
    assert all(
        s.metadata.source in (DocumentSource.HOUSE, DocumentSource.ROOM) for s in response.sources
    )


# Intent = both activates both pipelines and merges


def test_intent_both_activates_both_pipelines(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    _disable_extras(monkeypatch)

    router = _FakeRouter(RoutingDecision(intent=Intent.BOTH, confidence=0.6, source="llm"))
    orch, reviews_store, descriptions_store = _make_orchestrator(
        reviews_matches=_make_review_matches(3),
        descriptions_matches=_make_description_matches(3),
        router=router,
        llm=fake_llm,
        embedder=fake_embedder,
    )

    response = orch.query("ambiguous query", top_k=3)

    assert len(reviews_store.query_calls) == 1
    assert len(descriptions_store.query_calls) == 1

    # Both corpus groups present in sources_by_source
    assert response.sources_by_source is not None
    assert "reviews" in response.sources_by_source
    assert "descriptions" in response.sources_by_source

    # Merged sources contain a mix, capped at 2*top_k
    sources_types = {s.metadata.source for s in response.sources}
    assert len(sources_types) >= 2
    assert len(response.sources) <= 2 * 3


def test_intent_both_merges_sources_by_descending_score(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    _disable_extras(monkeypatch)

    router = _FakeRouter(RoutingDecision(intent=Intent.BOTH, confidence=0.7, source="llm"))
    orch, _, _ = _make_orchestrator(
        reviews_matches=_make_review_matches(3),
        descriptions_matches=_make_description_matches(3),
        router=router,
        llm=fake_llm,
        embedder=fake_embedder,
    )

    response = orch.query("mixed query", top_k=5)

    scores = [s.score for s in response.sources]
    assert scores == sorted(scores, reverse=True), "Sources should be sorted by score desc"


# Intent routing disabled → reviews-only


def test_intent_routing_disabled_always_queries_reviews(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    from elh_rag import config as cfg

    _disable_extras(monkeypatch)
    monkeypatch.setattr(cfg.settings, "enable_intent_routing", False)

    # Router would return DESCRIPTIONS, but routing is off so it's ignored
    router = _FakeRouter(RoutingDecision(intent=Intent.DESCRIPTIONS, confidence=0.99, source="llm"))
    orch, reviews_store, descriptions_store = _make_orchestrator(
        reviews_matches=_make_review_matches(2),
        descriptions_matches=_make_description_matches(2),
        router=router,
        llm=fake_llm,
        embedder=fake_embedder,
    )

    response = orch.query("anything", top_k=2)

    # Router should NOT have been called
    assert router.calls == []
    # Only reviews store queried
    assert len(reviews_store.query_calls) == 1
    assert len(descriptions_store.query_calls) == 0
    assert response.routing.source == "default"
    assert response.routing.intent == Intent.REVIEWS


# RAGResponse payload shape


def test_response_includes_routing_decision(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    _disable_extras(monkeypatch)

    decision = RoutingDecision(
        intent=Intent.DESCRIPTIONS,
        confidence=0.87,
        reasoning="Factual query about amenities",
        source="llm",
    )
    router = _FakeRouter(decision)
    orch, _, _ = _make_orchestrator(
        reviews_matches=[],
        descriptions_matches=_make_description_matches(2),
        router=router,
        llm=fake_llm,
        embedder=fake_embedder,
    )

    response = orch.query("query", top_k=2)

    assert response.routing == decision


def test_to_dict_serialises_routing_and_sources_by_source(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    import json

    _disable_extras(monkeypatch)

    router = _FakeRouter(
        RoutingDecision(intent=Intent.BOTH, confidence=0.65, reasoning="mixed", source="llm")
    )
    orch, _, _ = _make_orchestrator(
        reviews_matches=_make_review_matches(2),
        descriptions_matches=_make_description_matches(2),
        router=router,
        llm=fake_llm,
        embedder=fake_embedder,
    )

    response = orch.query("q", top_k=2)
    payload = response.to_dict()

    json.dumps(payload)
    assert payload["routing"]["intent"] == "both"
    assert payload["routing"]["confidence"] == 0.65
    assert "sources_by_source" in payload
    assert "reviews" in payload["sources_by_source"]
    assert "descriptions" in payload["sources_by_source"]


# Empty retrieval path


def test_empty_retrieval_returns_no_sources_message(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    _disable_extras(monkeypatch)

    router = _FakeRouter(RoutingDecision(intent=Intent.REVIEWS, confidence=0.9, source="llm"))
    orch, _, _ = _make_orchestrator(
        reviews_matches=[],
        descriptions_matches=[],
        router=router,
        llm=fake_llm,
        embedder=fake_embedder,
    )

    response = orch.query("no match query", top_k=3)

    assert response.sources == []
    assert "No relevant reviews" in response.answer


# Helper function tests


def test_build_reviews_filter_composes_city_and_rating() -> None:
    assert _build_reviews_filter(None, None) is None
    assert _build_reviews_filter("Porto", None) == {"city": {"$eq": "Porto"}}
    assert _build_reviews_filter(None, 4) == {"overall_rating": {"$gte": 4}}
    assert _build_reviews_filter("Lisbon", 3) == {
        "city": {"$eq": "Lisbon"},
        "overall_rating": {"$gte": 3},
    }


def test_build_descriptions_filter_ignores_min_rating() -> None:
    """Descriptions have no rating concept; min_rating is dropped."""
    assert _build_descriptions_filter(None) is None
    assert _build_descriptions_filter("Lisbon") == {"city": {"$eq": "Lisbon"}}


def test_empty_answer_varies_by_intent() -> None:
    reviews_dec = RoutingDecision(intent=Intent.REVIEWS, confidence=1.0)
    descriptions_dec = RoutingDecision(intent=Intent.DESCRIPTIONS, confidence=1.0)
    both_dec = RoutingDecision(intent=Intent.BOTH, confidence=1.0)

    assert "reviews" in _empty_answer(reviews_dec).lower()
    assert "descriptions" in _empty_answer(descriptions_dec).lower()
    assert "documents" in _empty_answer(both_dec).lower()


def test_mode_label_includes_routing_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from elh_rag import config as cfg

    monkeypatch.setattr(cfg.settings, "enable_query_rewriting", True)
    monkeypatch.setattr(cfg.settings, "enable_reranking", True)
    monkeypatch.setattr(cfg.settings, "enable_intent_routing", True)

    decision = RoutingDecision(intent=Intent.DESCRIPTIONS, confidence=0.9)
    label = _mode_label(decision)
    assert "rewrite" in label
    assert "rerank" in label
    assert "route:descriptions" in label


def test_build_context_tags_review_vs_description_headers() -> None:
    review = RetrievalResult(
        text="review text",
        metadata=ReviewMetadata(id="r1", city="Lisbon", flatname="Casa", overall_rating=5),
        vector_score=0.8,
    )
    house = RetrievalResult(
        text="house desc",
        metadata=HouseMetadata(id="house:h1", flatname="Casa Verde", city="Porto"),
        vector_score=0.7,
    )

    ctx = _build_context([review, house])

    assert "[REVIEW 1]" in ctx
    assert "[HOUSE 2]" in ctx
    assert "Overall rating: 5/5" in ctx
    assert "review text" in ctx
    assert "house desc" in ctx


# _select_prompts


def test_select_prompts_picks_review_only_prompt_when_all_sources_are_reviews() -> None:
    sources = [
        RetrievalResult(text="t1", metadata=ReviewMetadata(id="r1"), vector_score=0.8),
        RetrievalResult(text="t2", metadata=ReviewMetadata(id="r2"), vector_score=0.7),
    ]
    sys_prompt, _ = _select_prompts(question="q", context="c", sources=sources)

    # The Phase 1 review-only prompt mentions "student reviews" specifically
    assert "student reviews" in sys_prompt.lower()
    assert "descriptions" not in sys_prompt.lower()


def test_select_prompts_picks_multicorpus_prompt_when_any_description_present() -> None:
    sources = [
        RetrievalResult(text="t1", metadata=ReviewMetadata(id="r1"), vector_score=0.8),
        RetrievalResult(
            text="t2",
            metadata=HouseMetadata(id="h1", flatname="X"),
            vector_score=0.7,
        ),
    ]
    sys_prompt, _user_prompt = _select_prompts(question="q", context="c", sources=sources)

    # Multi-corpus prompt mentions both kinds
    assert "DESCRIPTIONS" in sys_prompt
    assert "REVIEWS" in sys_prompt


def test_select_prompts_picks_multicorpus_when_only_descriptions() -> None:
    sources = [
        RetrievalResult(
            text="t1",
            metadata=HouseMetadata(id="h1", flatname="X"),
            vector_score=0.8,
        ),
        RetrievalResult(
            text="t2",
            metadata=RoomMetadata(id="rm1", roomname="Y"),
            vector_score=0.7,
        ),
    ]
    sys_prompt, _ = _select_prompts(question="q", context="c", sources=sources)

    assert "DESCRIPTIONS" in sys_prompt


# Conversational memory integration


def test_orchestrator_passes_memory_through_rewriter(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    """When memory has turns, the followup rewriter should be called."""
    from elh_rag.retrieval.conversation_memory import ConversationMemory
    from elh_rag.retrieval.followup_rewriter import FollowUpRewriter

    _disable_extras(monkeypatch)

    class _RecordingFollowupLLM(LLMClient):
        def __init__(self) -> None:
            self.calls: list[str] = []

        def complete(self, system: str, user: str) -> str:
            self.calls.append(user)
            return "cheap house in Porto"

    followup_llm = _RecordingFollowupLLM()
    rewriter = FollowUpRewriter(llm_client=followup_llm)

    router = _FakeRouter(RoutingDecision(intent=Intent.DESCRIPTIONS, confidence=0.9, source="llm"))
    orch, _reviews_store, _descriptions_store = _make_orchestrator(
        reviews_matches=[],
        descriptions_matches=_make_description_matches(2),
        router=router,
        llm=fake_llm,
        embedder=fake_embedder,
    )
    # Replace the orchestrator's default followup rewriter with our spy
    orch._followup = rewriter

    memory = ConversationMemory(max_turns=5)
    memory.append("cheap house in Lisbon", "Residencia Campo de Ourique €350.")

    response = orch.query("and in Porto?", top_k=2, conversation_memory=memory)

    # The followup rewriter must have been called once
    assert len(followup_llm.calls) == 1
    # The retriever must have queried with the rewritten text — which we
    # can verify indirectly via the rewritten_query field on the response
    assert response.rewritten_query == "cheap house in Porto"


def test_orchestrator_skips_rewriter_when_memory_is_none(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    """No memory → no followup rewrite, original question goes through."""
    _disable_extras(monkeypatch)

    class _RecordingFollowupLLM(LLMClient):
        def __init__(self) -> None:
            self.calls: list[str] = []

        def complete(self, system: str, user: str) -> str:
            self.calls.append(user)
            return "should-not-be-used"

    from elh_rag.retrieval.followup_rewriter import FollowUpRewriter

    followup_llm = _RecordingFollowupLLM()
    rewriter = FollowUpRewriter(llm_client=followup_llm)

    router = _FakeRouter(RoutingDecision(intent=Intent.REVIEWS, confidence=0.9, source="llm"))
    orch, _, _ = _make_orchestrator(
        reviews_matches=_make_review_matches(2),
        descriptions_matches=[],
        router=router,
        llm=fake_llm,
        embedder=fake_embedder,
    )
    orch._followup = rewriter

    response = orch.query("standalone question", top_k=2, conversation_memory=None)

    assert followup_llm.calls == []
    assert response.query == "standalone question"


def test_orchestrator_respects_disable_conversational_memory_flag(
    monkeypatch: pytest.MonkeyPatch,
    fake_embedder: Embedder,
    fake_llm: LLMClient,
) -> None:
    """ENABLE_CONVERSATIONAL_MEMORY=False → rewriter never invoked."""
    from elh_rag import config as cfg
    from elh_rag.retrieval.conversation_memory import ConversationMemory
    from elh_rag.retrieval.followup_rewriter import FollowUpRewriter

    _disable_extras(monkeypatch)
    monkeypatch.setattr(cfg.settings, "enable_conversational_memory", False)

    class _RecordingFollowupLLM(LLMClient):
        def __init__(self) -> None:
            self.calls: list[str] = []

        def complete(self, system: str, user: str) -> str:
            self.calls.append(user)
            return "should-not-be-used"

    followup_llm = _RecordingFollowupLLM()
    rewriter = FollowUpRewriter(llm_client=followup_llm)

    router = _FakeRouter(RoutingDecision(intent=Intent.REVIEWS, confidence=0.9, source="llm"))
    orch, _, _ = _make_orchestrator(
        reviews_matches=_make_review_matches(2),
        descriptions_matches=[],
        router=router,
        llm=fake_llm,
        embedder=fake_embedder,
    )
    orch._followup = rewriter

    memory = ConversationMemory(max_turns=5)
    memory.append("previous question", "previous answer")

    orch.query("and in Porto?", top_k=2, conversation_memory=memory)

    # Even with non-empty memory, the rewriter is bypassed by the config flag
    assert followup_llm.calls == []
