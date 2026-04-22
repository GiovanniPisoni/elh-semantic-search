"""
Intent router, decides which corpus to query.

The router sits between the user's question and retrieval: given a raw
query, it classifies the intent into one of three outcomes:
    - REVIEWS        → the query is about subjective experience
    - DESCRIPTIONS   → the query is about factual attributes
    - BOTH           → the query is mixed or ambiguous, query both corpora
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

from elh_rag.config import settings
from elh_rag.generation.llm_client import LLMClient
from elh_rag.generation.prompts import (
    INTENT_ROUTER_SYSTEM_PROMPT,
    build_intent_router_prompt,
)
from elh_rag.schemas import Intent, RoutingDecision

logger = logging.getLogger(__name__)


# Keyword hints for the fallback heuristic

_REVIEWS_KEYWORDS: tuple[str, ...] = (
    # English
    "experience", "experienced", "felt", "feel", "atmosphere", "vibe",
    "friendly", "unfriendly", "noisy", "quiet actually",
    "landlord", "host", "hosts", "landlords",
    "flatmate", "flatmates", "roommate", "roommates",
    "neighbour", "neighbours", "neighbor", "neighbors",
    "complain", "complaint", "complaints", "issue", "problem", "problems",
    "recommend", "recommendation", "recommendations",
    "stay", "stayed", "staying",
    "impression", "impressions", "opinion", "opinions",
    "loved", "hated", "enjoyed", "disappointed",
    # Portuguese
    "experiência", "experiencia", "gostei", "gostaram", "senhorio",
    "senhoria", "colegas",
    # Italian
    "esperienza", "proprietario", "proprietaria", "coinquilini",
    # Spanish
    "experiencia", "casero", "casera",
)

_DESCRIPTIONS_KEYWORDS: tuple[str, ...] = (
    # English
    "m2", "m²", "square meters", "square metres", "sqm",
    "price", "prices", "cost", "rent", "monthly", "deposit",
    "wifi", "internet", "mbps", "speed",
    "amenity", "amenities", "equipment", "appliances",
    "kitchen", "bathroom", "bathrooms", "balcony", "elevator",
    "bed", "beds", "bedroom", "double bed", "single bed", "queen bed",
    "furnished", "furniture", "desk", "wardrobe", "closet",
    "air conditioning", "heating", "washing machine",
    "how much", "how many", "what does",
    "distance", "minutes from", "metres from", "meters from",
    # Portuguese
    "quarto", "metros", "preço", "aluguel",
    # Italian
    "prezzo", "affitto", "metri",
    # Spanish
    "precio", "alquiler", "metros cuadrados",
)


# Extraction helpers


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw: str) -> dict[str, Any] | None:
    """Extract the first JSON object from an LLM response."""
    if not raw:
        return None

    # Strip common markdown fences
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    # Grab the first balanced-looking JSON object
    match = _JSON_OBJECT_RE.search(cleaned)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _parse_intent(value: Any) -> Intent | None:
    """Convert an LLM-returned string to an Intent enum, or None if invalid."""
    if not isinstance(value, str):
        return None
    normalised = value.strip().lower()
    for intent in Intent:
        if intent.value == normalised:
            return intent
    return None


def _parse_confidence(value: Any) -> float:
    """Coerce a confidence value into [0.0, 1.0], clamping out-of-range inputs."""
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, conf))


# Keyword-based fallback


def _keyword_fallback(query: str) -> RoutingDecision:
    """Classify the query using keyword presence alone."""
    lowered = query.lower()

    reviews_hits = sum(1 for k in _REVIEWS_KEYWORDS if k in lowered)
    descriptions_hits = sum(1 for k in _DESCRIPTIONS_KEYWORDS if k in lowered)

    if reviews_hits > 0 and descriptions_hits == 0:
        return RoutingDecision(
            intent=Intent.REVIEWS,
            confidence=0.6,
            reasoning=f"Keyword fallback: {reviews_hits} review keyword(s) matched",
            source="keyword",
        )
    if descriptions_hits > 0 and reviews_hits == 0:
        return RoutingDecision(
            intent=Intent.DESCRIPTIONS,
            confidence=0.6,
            reasoning=(
                f"Keyword fallback: {descriptions_hits} description keyword(s) matched"
            ),
            source="keyword",
        )

    return RoutingDecision(
        intent=Intent.BOTH,
        confidence=0.5,
        reasoning="Keyword fallback: no clear signal, querying both corpora",
        source="keyword",
    )


# Router


class IntentRouter:
    """Classifies a user query into one of three intents."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        confidence_threshold: float | None = None,
    ) -> None:
        self._llm = llm_client or LLMClient(
            model=settings.intent_router_model,
            max_tokens=settings.intent_router_max_tokens,
        )
        self._threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else settings.intent_router_confidence_threshold
        )

    def route(self, query: str) -> RoutingDecision:
        """Decide which corpus to query for this input."""
        if not query or not query.strip():
            return RoutingDecision(
                intent=Intent.BOTH,
                confidence=0.0,
                reasoning="Empty query, defaulting to both corpora",
                source="default",
            )

        return self._route_cached(query)

    @lru_cache(maxsize=128)
    def _route_cached(self, query: str) -> RoutingDecision:
        """Memoised routing logic. See `route` for the public entry point."""
        try:
            raw = self._llm.complete(
                system=INTENT_ROUTER_SYSTEM_PROMPT,
                user=build_intent_router_prompt(query),
            )
        except Exception as exc:
            logger.warning(
                "Intent router LLM failed (%s) — falling back to keyword heuristic",
                exc,
            )
            return _keyword_fallback(query)

        payload = _extract_json(raw)
        if payload is None:
            logger.warning(
                "Intent router returned unparseable output: %r — using keyword fallback",
                raw[:200] if raw else "",
            )
            return _keyword_fallback(query)

        intent = _parse_intent(payload.get("intent"))
        if intent is None:
            logger.warning(
                "Intent router returned unknown intent: %r — using keyword fallback",
                payload.get("intent"),
            )
            return _keyword_fallback(query)

        confidence = _parse_confidence(payload.get("confidence"))
        reasoning = str(payload.get("reasoning", "")).strip()

        # Low-confidence single-corpus answers are safer escalated to BOTH.
        if intent is not Intent.BOTH and confidence < self._threshold:
            logger.debug(
                "Low confidence (%.2f < %.2f), escalating %s to BOTH",
                confidence,
                self._threshold,
                intent.value,
            )
            return RoutingDecision(
                intent=Intent.BOTH,
                confidence=confidence,
                reasoning=(
                    f"Escalated from {intent.value} (conf {confidence:.2f}) "
                    f"below threshold {self._threshold:.2f}: {reasoning}"
                ),
                source="llm",
            )

        return RoutingDecision(
            intent=intent,
            confidence=confidence,
            reasoning=reasoning,
            source="llm",
        )