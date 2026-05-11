"""Tool 6: ``answer_policy_question``."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from ._kb import KBContext
from .base import register_tool

logger = logging.getLogger(__name__)


# Defaults

_DEFAULT_MAX_RESULTS = 3
_DEFAULT_THRESHOLD = 0.5
_FALLBACK_MESSAGE = (
    "I don't have a specific FAQ entry that matches your question. "
    "For details, please contact Erasmus Life Housing directly: "
    "hello@erasmuslifehousing.com or +351 932 483 834."
)


# Input model


class AnswerPolicyQuestionInput(BaseModel):
    """Inputs for a policy/FAQ lookup."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description=(
            "Natural language question about ELH policies, processes, or "
            "contact details. Examples: 'What is the cancellation policy?', "
            "'How do I book a room?', 'Where is the ELH office?'."
        ),
    )
    max_results: int = Field(
        default=_DEFAULT_MAX_RESULTS,
        ge=1,
        le=10,
        description="Cap on the number of matches returned.",
    )
    audience: Literal["student", "landlord", "both"] = Field(
        default="student",
        description=(
            "Filter KB entries by intended audience. Most callers are "
            "students; pass 'landlord' for landlord-onboarding questions "
            "and 'both' to include every entry."
        ),
    )
    confidence_threshold: float = Field(
        default=_DEFAULT_THRESHOLD,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum cosine similarity to consider a match. Higher values "
            "make the matcher stricter (more 'no match' fallbacks); lower "
            "values surface more matches at lower confidence."
        ),
    )


# Output models


class PolicyMatch(BaseModel):
    """One matched KB entry returned to the caller."""

    id: str
    category: str
    canonical_question: str
    answer: str
    sources: list[str] = Field(default_factory=list)
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Cosine similarity between the question and the best variant.",
    )
    related_ids: list[str] = Field(default_factory=list)


class AnswerPolicyQuestionOutput(BaseModel):
    """Result payload of a policy lookup."""

    matches: list[PolicyMatch] = Field(default_factory=list)
    found: bool = Field(
        ...,
        description="True if at least one match passed the confidence threshold.",
    )
    fallback_message: str | None = Field(
        default=None,
        description=(
            "Suggested user-facing reply when no match was found (``None`` when ``found`` is True)."
        ),
    )
    summary: str


# Summary composition


def _compose_summary(question: str, matches: list[PolicyMatch]) -> str:
    """One-line LLM-quotable summary of the lookup result."""
    if not matches:
        return (
            f"No KB entry matched the question {question!r}. Falling back to ELH contact details."
        )
    best = matches[0]
    extra = f" (+{len(matches) - 1} related)" if len(matches) > 1 else ""
    return f"Matched {best.id!r} ({best.category}) with confidence {best.confidence:.2f}{extra}."


# Registered tool


@register_tool(
    name="answer_policy_question",
    description=(
        "Answer questions about Erasmus Life Housing (ELH) policies, "
        "processes, fees, contact details, partnerships, and operational "
        "rules. Returns one or more matched FAQ-style entries from a "
        "hand-curated knowledge base, each with its canonical answer, "
        "provenance (website FAQ, Reamaze email templates, ELH "
        "presentation), and a confidence score. "
        "\n\nUse this tool for objective, authoritative questions about "
        "HOW ELH works: 'what is the cancellation policy', 'how do I "
        "book a room', 'when do landlords get paid', 'where is the ELH "
        "office', 'is there a promo code'. Do NOT use it for subjective "
        "or experiential questions about specific rooms ('is the bed "
        "comfortable', 'is the flat quiet') — those go through the "
        "Phase 2 RAG fallback over reviews and descriptions. Do NOT use "
        "it for data lookups (specific rooms, prices, availability) — "
        "use the find_rooms / compute_total_cost / get_property_details "
        "tools instead. "
        "\n\nThe audience parameter filters the KB: 'student' (default) "
        "for student-facing questions, 'landlord' for landlord onboarding "
        "questions, 'both' to include every entry. When no match passes "
        "the confidence threshold, the tool returns found=False with a "
        "fallback_message pointing to ELH support."
    ),
    input_model=AnswerPolicyQuestionInput,
)
def answer_policy_question(
    payload: AnswerPolicyQuestionInput,
    ctx: KBContext | None,
) -> AnswerPolicyQuestionOutput:
    """Match a natural-language question against the policy KB."""
    if ctx is None:
        raise RuntimeError(
            "answer_policy_question requires a KBContext in ctx. "
            "Bootstrap the orchestrator with a configured KBContext "
            "(e.g. KBContext.from_default_yaml(embedder))."
        )

    raw_matches = ctx.search(
        payload.question,
        audience=payload.audience,
        top_k=payload.max_results,
        threshold=payload.confidence_threshold,
    )

    matches: list[PolicyMatch] = [
        PolicyMatch(
            id=entry.id,
            category=entry.category,
            canonical_question=entry.canonical_question,
            answer=entry.answer,
            sources=list(entry.sources),
            confidence=round(score, 4),
            related_ids=list(entry.related),
        )
        for entry, score in raw_matches
    ]

    found = bool(matches)
    fallback = None if found else _FALLBACK_MESSAGE
    summary = _compose_summary(payload.question, matches)

    return AnswerPolicyQuestionOutput(
        matches=matches,
        found=found,
        fallback_message=fallback,
        summary=summary,
    )
