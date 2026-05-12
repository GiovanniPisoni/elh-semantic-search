"""End-to-end smoke test for Tool 6 (``answer_policy_question``).

Loads the real ``kb/policies.yaml`` with the real multilingual
SentenceTransformer (mpnet) and runs six scenarios:

    1. Clear in-corpus question (cancellation)
    2. Paraphrased question (booking how-to)
    3. Multilingual question — Italian (cancellation)
    4. Multilingual question — Portuguese (deposit)
    5. Landlord-audience question (payment timing)
    6. Out-of-corpus question (expect fallback)

The multilingual scenarios exercise mpnet's claim of native EN/PT
support — if confidences look low, the threshold may need tuning.
"""

from __future__ import annotations

import sys

from elh_rag.indexing.embeddings import Embedder
from elh_rag.tools._kb import KBContext
from elh_rag.tools.answer_policy_question import (
    AnswerPolicyQuestionInput,
    AnswerPolicyQuestionOutput,
    answer_policy_question,
)

_SEP = "=" * 78


def _print_result(label: str, result: AnswerPolicyQuestionOutput) -> None:
    print(f"\n{_SEP}")
    print(f"SCENARIO: {label}")
    print(_SEP)
    print(f"Summary    : {result.summary}")
    print(f"Found      : {result.found}")
    if result.fallback_message:
        print(f"Fallback   : {result.fallback_message}")
    print(f"Matches ({len(result.matches)}):")
    for i, m in enumerate(result.matches, 1):
        print(f"  [{i}] id={m.id}  conf={m.confidence:.4f}  category={m.category}")
        print(f"      Q: {m.canonical_question}")
        ans_preview = m.answer.strip().replace("\n", " ")[:140]
        print(f"      A: {ans_preview}{'...' if len(m.answer) > 140 else ''}")
        if m.sources:
            print(f"      sources: {', '.join(m.sources)}")
        if m.related_ids:
            print(f"      related: {', '.join(m.related_ids)}")


def _run(
    label: str,
    ctx: KBContext,
    payload: AnswerPolicyQuestionInput,
) -> bool:
    try:
        result = answer_policy_question(payload, ctx=ctx)
        _print_result(label, result)
        return True
    except Exception as e:
        print(f"\n[FAIL] {label}: {type(e).__name__}: {e}")
        return False


def main() -> int:
    print("Loading SentenceTransformer embedder (this may take a few seconds)...")
    # Use the project's standard embedder, same as Phase 2 RAG.
    embedder = Embedder()
    print("Building KB from default YAML...")
    ctx = KBContext.from_default_yaml(embedder)
    print(f"KB ready: {len(ctx.kb_store)} entries indexed.")

    completed = 0

    # 1 — Clear in-corpus EN
    if _run(
        "EN — direct cancellation question",
        ctx,
        AnswerPolicyQuestionInput(
            question="What is the cancellation policy?",
        ),
    ):
        completed += 1

    # 2 — Paraphrased EN
    if _run(
        "EN — paraphrased booking question",
        ctx,
        AnswerPolicyQuestionInput(
            question="I want to reserve a room, how does that work?",
        ),
    ):
        completed += 1

    # 3 — IT
    if _run(
        "IT — cancellation in Italian",
        ctx,
        AnswerPolicyQuestionInput(
            question="Come posso cancellare la mia prenotazione?",
        ),
    ):
        completed += 1

    # 4 — PT
    if _run(
        "PT — deposit in Portuguese",
        ctx,
        AnswerPolicyQuestionInput(
            question="É preciso pagar caução?",
        ),
    ):
        completed += 1

    # 5 — Landlord audience
    if _run(
        "EN — landlord payment timing (audience=landlord)",
        ctx,
        AnswerPolicyQuestionInput(
            question="When do landlords get paid?",
            audience="landlord",
        ),
    ):
        completed += 1

    # 6 — Out of corpus
    if _run(
        "EN — off-topic (expect fallback)",
        ctx,
        AnswerPolicyQuestionInput(
            question="What's the weather like in Lisbon today?",
            confidence_threshold=0.5,
        ),
    ):
        completed += 1

    print(f"\n{_SEP}")
    print(f"SMOKE TEST COMPLETE: {completed}/6 scenarios produced output.")
    print(_SEP)
    return 0 if completed == 6 else 1


if __name__ == "__main__":
    sys.exit(main())
