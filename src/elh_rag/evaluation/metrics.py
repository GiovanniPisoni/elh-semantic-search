"""
Three custom evaluation metrics for ELH RAG.

Each metric is a pure function: takes (judge, inputs) → (score, details).

    faithfulness:     score in [0,1], None if no claims to evaluate
    context_recall:   score in [0,1], None if no must_mention given
    answer_relevancy: score in [0,1], always returns a value

Each metric also returns a `details` dict with per-item reasoning,
persisted to the JSONL output for diagnosis. When something goes wrong,
metrics return None — they never raise, never produce misleading 0.0.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from elh_rag.evaluation.judge import EvaluationJudge, JudgeError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MetricResult:
    """Output of a metric: score in [0,1] (or None if not applicable) + details."""

    score: float | None
    details: dict[str, Any]


# Metric 1 — Faithfulness

_FAITHFULNESS_SYSTEM = """You are evaluating whether the claims made in an \
AI-generated answer are supported by the source documents the AI was given.

Your task has two steps:

Step 1 — Extract atomic claims from the answer.
    A claim is a single factual statement, typically of the form
    "X has property Y" or "X is at location Z" or "X said Q".
    Ignore filler ("based on the sources", "I found that").
    Each claim should be self-contained and verifiable.

Step 2 — For each claim, check whether at least ONE of the provided
    sources supports it.
    "Supports" means: the source explicitly states the claim, or the
    claim is a direct paraphrase of source content. Inferences that
    require external knowledge are NOT supported.

Special cases:
    - If the answer says "I don't have information about this" or
      similar, it is NOT a claim — return zero claims and supported=0.
    - If a claim attributes a quote to a source/property, the quote
      must actually appear in that source. Misattribution counts as
      unsupported.

Output ONLY a JSON object with this exact schema:
{
  "claims": [
    {"text": "...", "supported": true|false, "reason": "..."},
    ...
  ]
}

No preamble, no markdown fences, no commentary. Just the JSON."""


def faithfulness(
    judge: EvaluationJudge,
    answer: str,
    contexts: list[str],
) -> MetricResult:
    """Faithfulness = fraction of answer claims supported by retrieved sources.

    Returns None if the answer contains no factual claims (e.g. the LLM
    correctly said "I don't have information").
    """
    if not answer.strip() or not contexts:
        return MetricResult(score=None, details={"reason": "empty answer or no contexts"})

    sources_block = "\n\n".join(f"[Source {i + 1}]\n{ctx}" for i, ctx in enumerate(contexts))
    user_prompt = (
        f"ANSWER:\n{answer}\n\n"
        f"SOURCES:\n{sources_block}\n\n"
        "Extract claims from the answer and verify each against the sources."
    )

    try:
        result = judge.ask_json(system=_FAITHFULNESS_SYSTEM, user=user_prompt)
    except JudgeError as exc:
        logger.warning("Faithfulness judge failed: %s", exc)
        return MetricResult(score=None, details={"error": str(exc)})

    claims = result.get("claims", [])
    if not isinstance(claims, list):
        return MetricResult(score=None, details={"error": "judge output 'claims' not a list"})

    if not claims:
        return MetricResult(
            score=None,
            details={"claims": [], "reason": "no claims found in answer"},
        )

    supported = sum(1 for c in claims if c.get("supported") is True)
    score = supported / len(claims)
    return MetricResult(
        score=round(score, 3),
        details={"total_claims": len(claims), "supported": supported, "claims": claims},
    )


# Metric 2 — Context Recall

_CONTEXT_RECALL_SYSTEM = """You are evaluating whether the source documents \
retrieved by a RAG system contain information about specific concepts that \
the user expected to be addressed.

For each EXPECTED CONCEPT in the list, check whether at least ONE source
document contains information about that concept.

"Contains information" means: the source explicitly mentions the concept
OR a clear semantic equivalent. Be SEMANTIC, not literal:
    - "safety" matches "feeling secure", "felt safe", "safe at night"
    - "balcony" matches "outdoor terrace", "small terrace"
    - "noisy" matches "loud", "noise complaints"
    - "Lisbon" matches "Lisboa"

A source covers a concept even if it discusses it negatively
(e.g. "no balcony available" still covers the "balcony" concept —
the question of presence/absence is information).

Output ONLY a JSON object with this exact schema:
{
  "concepts": [
    {"concept": "...", "covered": true|false, "evidence": "..."},
    ...
  ]
}

No preamble, no markdown fences, no commentary. Just the JSON.
The "evidence" field should be a brief quote from the source if covered=true,
or a one-line explanation if covered=false."""


def context_recall(
    judge: EvaluationJudge,
    must_mention: list[str],
    contexts: list[str],
) -> MetricResult:
    """Context recall = fraction of must-mention concepts covered by sources.

    Returns None if must_mention is empty (e.g. nonsense or unanswerable
    queries).
    """
    if not must_mention:
        return MetricResult(score=None, details={"reason": "no must_mention given"})

    if not contexts:
        return MetricResult(
            score=0.0,
            details={"concepts": [{"concept": k, "covered": False} for k in must_mention]},
        )

    sources_block = "\n\n".join(f"[Source {i + 1}]\n{ctx}" for i, ctx in enumerate(contexts))
    concepts_block = "\n".join(f"- {kw}" for kw in must_mention)
    user_prompt = (
        f"EXPECTED CONCEPTS:\n{concepts_block}\n\n"
        f"SOURCES:\n{sources_block}\n\n"
        "For each expected concept, check whether the sources contain "
        "information about it."
    )

    try:
        result = judge.ask_json(system=_CONTEXT_RECALL_SYSTEM, user=user_prompt)
    except JudgeError as exc:
        logger.warning("Context recall judge failed: %s", exc)
        return MetricResult(score=None, details={"error": str(exc)})

    concepts = result.get("concepts", [])
    if not isinstance(concepts, list) or not concepts:
        return MetricResult(
            score=None, details={"error": "judge output 'concepts' not a non-empty list"}
        )

    covered = sum(1 for c in concepts if c.get("covered") is True)
    score = covered / len(concepts)
    return MetricResult(
        score=round(score, 3),
        details={"total_concepts": len(concepts), "covered": covered, "concepts": concepts},
    )


# Metric 3 — Answer Relevancy

_ANSWER_RELEVANCY_SYSTEM = """You are evaluating whether an AI-generated \
answer addresses the user's question on-topic and directly.

Score the answer on a 0.0-1.0 scale:

    1.0 — Direct, complete, on-topic. Addresses exactly what was asked.
    0.8 — On-topic and useful, but with minor digressions.
    0.5 — Tangentially related. Touches the topic but mostly misses the point.
    0.2 — Off-topic. Discusses something different from what was asked.
    0.0 — Completely off-topic, evasive, or refusing without good cause.

SPECIAL CASE — unanswerable questions:
    If the question cannot be answered from typical RAG sources (nonsense,
    grammatically broken, asks about something outside the system's scope),
    then saying "I don't have information about this" or similar is the
    CORRECT behaviour and deserves score 1.0. In contrast, hallucinating
    an answer when the question was unanswerable deserves score 0.0.

To detect "unanswerable":
    - The question is nonsense (random characters, unrelated words)
    - The question asks about a person/entity not in the housing domain
    - The question is broken to the point that the intent is unclear

Output ONLY a JSON object with this exact schema:
{
  "score": 0.0,
  "reasoning": "...",
  "is_unanswerable_query": true|false
}

The "score" must be a float between 0.0 and 1.0.
No preamble, no markdown fences, no commentary outside the JSON."""


def answer_relevancy(
    judge: EvaluationJudge,
    question: str,
    answer: str,
) -> MetricResult:
    """Answer relevancy = how on-topic the answer is to the question.

    Always returns a score (never None). Has special handling for
    unanswerable queries: rewards "I don't know" responses, penalises
    hallucinated answers to nonsense questions.
    """
    if not answer.strip():
        return MetricResult(score=0.0, details={"reason": "empty answer"})

    user_prompt = (
        f"QUESTION:\n{question}\n\n"
        f"ANSWER:\n{answer}\n\n"
        "Score how well the answer addresses the question."
    )

    try:
        result = judge.ask_json(system=_ANSWER_RELEVANCY_SYSTEM, user=user_prompt)
    except JudgeError as exc:
        logger.warning("Answer relevancy judge failed: %s", exc)
        return MetricResult(score=None, details={"error": str(exc)})

    score = result.get("score")
    if not isinstance(score, (int, float)) or score < 0 or score > 1:
        return MetricResult(
            score=None,
            details={"error": f"judge returned invalid score: {score!r}"},
        )

    return MetricResult(
        score=round(float(score), 3),
        details={
            "reasoning": result.get("reasoning", ""),
            "is_unanswerable_query": result.get("is_unanswerable_query", False),
        },
    )
