"""
Custom evaluation script.

Runs the ELH RAG pipeline on the curated golden set, then evaluates each
response with three custom metrics built on Claude as judge:

    - faithfulness:     answer claims supported by retrieved sources?
    - context_recall:   must-mention concepts present in retrieved sources?
    - answer_relevancy: does the answer address the question on-topic?

Outputs:
    - JSONL with one record per query (full per-metric details + reasoning)
    - Markdown report with aggregates, problems prioritised, per-query
      breakdown, and an interpretation guide
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from elh_rag.evaluation.judge import EvaluationJudge
from elh_rag.evaluation.metrics import (
    answer_relevancy,
    context_recall,
    faithfulness,
)
from elh_rag.logging_setup import setup_logging
from elh_rag.pipeline import RAGPipeline
from elh_rag.schemas import RAGResponse


# Golden set loading


def load_golden_set(path: Path) -> list[dict[str, Any]]:
    """Load golden set queries from YAML, skipping unannotated stubs."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    queries = data.get("queries", [])
    real = [q for q in queries if not q.get("question", "").startswith("REPLACE_WITH_")]
    skipped = len(queries) - len(real)
    if skipped:
        print(f"⚠️  Skipped {skipped} unannotated stub(s)")
    return real


# Pipeline runner


def run_pipeline_on_query(
    pipeline: RAGPipeline, question: str
) -> tuple[RAGResponse | None, float, str | None]:
    """Run a single query, return response + latency + optional error."""
    start = time.perf_counter()
    try:
        response = pipeline.query(question)
        elapsed = time.perf_counter() - start
        return response, elapsed, None
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return None, elapsed, str(exc)


def extract_contexts(response: RAGResponse) -> list[str]:
    """Extract retrieved-document texts as a list of strings."""
    if not response or not response.sources:
        return []
    return [src.text for src in response.sources if src.text]


# Evaluation


def evaluate_query(
    judge: EvaluationJudge,
    question: str,
    answer: str,
    contexts: list[str],
    must_mention: list[str],
) -> dict[str, Any]:
    """Run the three metrics on a single (question, answer, contexts) tuple."""
    f_result = faithfulness(judge=judge, answer=answer, contexts=contexts)
    cr_result = context_recall(judge=judge, must_mention=must_mention, contexts=contexts)
    ar_result = answer_relevancy(judge=judge, question=question, answer=answer)

    return {
        "faithfulness_score": f_result.score,
        "faithfulness_details": f_result.details,
        "context_recall_score": cr_result.score,
        "context_recall_details": cr_result.details,
        "answer_relevancy_score": ar_result.score,
        "answer_relevancy_details": ar_result.details,
    }


# Aggregation


def aggregate(scores: list[float | None]) -> dict[str, float | int]:
    """Compute summary statistics, ignoring None values."""
    valid = [s for s in scores if s is not None]
    if not valid:
        return {"avg": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "n": 0, "skipped": len(scores)}
    return {
        "avg": round(statistics.mean(valid), 3),
        "median": round(statistics.median(valid), 3),
        "min": round(min(valid), 3),
        "max": round(max(valid), 3),
        "n": len(valid),
        "skipped": len(scores) - len(valid),
    }


def identify_problems(
    records: list[dict[str, Any]],
    thresholds: dict[str, float],
) -> list[dict[str, Any]]:
    """Tag queries with sub-threshold metric scores, sorted by severity."""
    problems = []
    for r in records:
        if r.get("error"):
            continue
        for metric, threshold in thresholds.items():
            score = r.get(f"{metric}_score")
            if score is None:
                continue
            if score < threshold:
                problems.append({
                    "query_id": r["id"],
                    "question": r["question"],
                    "metric": metric,
                    "score": score,
                    "threshold": threshold,
                    "severity": round(threshold - score, 3),
                })
    problems.sort(key=lambda p: -p["severity"])
    return problems


# Persistence


def save_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    """Persist raw per-query records (machine-readable)."""
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def write_markdown_report(
    records: list[dict[str, Any]],
    problems: list[dict[str, Any]],
    path: Path,
    thresholds: dict[str, float],
) -> None:
    """Write the human-facing Markdown diagnostic report."""
    lines: list[str] = []

    lines.append("# ELH RAG — Phase 4 light diagnostic report (custom metrics)")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    n_ok = len([r for r in records if not r.get("error")])
    n_err = len(records) - n_ok
    lines.append(f"**Queries:** {len(records)} total · {n_ok} OK · {n_err} errored")
    lines.append("")
    lines.append("Custom evaluation framework — written from scratch after RAGAS 0.4 ")
    lines.append("produced ~90% NaN values on this golden set. Three metrics measured:")
    lines.append("**faithfulness**, **context_recall**, **answer_relevancy**. Each metric ")
    lines.append("is judged by Claude Sonnet 4.5 with a deterministic JSON-output ")
    lines.append("contract; per-claim reasoning is preserved in the JSONL companion file.")
    lines.append("")

    # Aggregates
    lines.append("## Aggregates")
    lines.append("")
    lines.append("| Metric | Avg | Median | Min | Max | Valid (N) | Skipped |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for metric in ["faithfulness", "context_recall", "answer_relevancy"]:
        scores = [r.get(f"{metric}_score") for r in records if not r.get("error")]
        agg = aggregate(scores)
        lines.append(
            f"| {metric} | {agg['avg']} | {agg['median']} | {agg['min']} | "
            f"{agg['max']} | {agg['n']} | {agg['skipped']} |"
        )
    lines.append("")
    lines.append("'Skipped' counts queries where the metric was not applicable, e.g. ")
    lines.append("`context_recall` on queries with empty `must_mention`, or ")
    lines.append("`faithfulness` when the answer correctly said 'I don't know'. ")
    lines.append("These are NOT failures — they are the metrics opting out cleanly.")
    lines.append("")

    # Problems
    lines.append("## Problems detected (prioritised)")
    lines.append("")
    if not problems:
        lines.append("**No sub-threshold scores detected.** ✅")
    else:
        lines.append(f"Found **{len(problems)} sub-threshold case(s)** out of {n_ok} queries.")
        lines.append("")
        lines.append("Thresholds:")
        for m, t in thresholds.items():
            lines.append(f"- {m} < {t}")
        lines.append("")
        lines.append("| # | Query ID | Metric | Score | Severity (gap) | Question |")
        lines.append("|---|---|---|---:|---:|---|")
        for i, p in enumerate(problems, 1):
            q_short = p["question"][:60] + ("..." if len(p["question"]) > 60 else "")
            lines.append(
                f"| {i} | {p['query_id']} | {p['metric']} | "
                f"{p['score']} | {p['severity']} | {q_short} |"
            )
    lines.append("")

    # Per-query details
    lines.append("## Per-query details")
    lines.append("")
    for r in records:
        lines.append(f"### {r['id']} — {r.get('category', 'unknown')}")
        lines.append("")
        lines.append(f"**Question ({r.get('language', '?')}):** `{r['question']}`")
        lines.append("")

        if r.get("error"):
            lines.append(f"❌ **Failed:** `{r['error']}`")
            lines.append("")
            lines.append("---")
            lines.append("")
            continue

        # Score row
        score_parts = []
        for m in ["faithfulness", "context_recall", "answer_relevancy"]:
            s = r.get(f"{m}_score")
            score_str = "N/A" if s is None else f"{s:.3f}"
            score_parts.append(f"**{m}:** {score_str}")
        lines.append(" · ".join(score_parts))
        lines.append("")

        lines.append(
            f"**Latency:** {r.get('latency_sec', '?')}s · "
            f"**Sources:** {len(r.get('contexts', []))}"
        )
        if r.get("routing"):
            rt = r["routing"]
            lines.append(
                f"**Routing:** {rt.get('intent')} "
                f"(conf={rt.get('confidence', 0):.2f}, src={rt.get('source')})"
            )
        lines.append("")

        # Brief answer preview
        answer = r.get("answer", "")
        preview = answer[:400] + ("..." if len(answer) > 400 else "")
        lines.append("**Answer (first 400 chars):**")
        lines.append("")
        lines.append("> " + preview.replace("\n", "\n> "))
        lines.append("")

        # Reasoning snippets if metrics flagged something
        ar_details = r.get("answer_relevancy_details", {})
        if ar_details.get("reasoning"):
            lines.append(f"**Judge reasoning (relevancy):** _{ar_details['reasoning']}_")
            lines.append("")

        f_details = r.get("faithfulness_details", {})
        if isinstance(f_details, dict) and f_details.get("claims"):
            unsupported = [c for c in f_details["claims"] if not c.get("supported")]
            if unsupported:
                lines.append(f"**Unsupported claims ({len(unsupported)}):**")
                lines.append("")
                for c in unsupported[:3]:  # cap at 3
                    lines.append(f"- *{c.get('text', '?')}* — {c.get('reason', '')}")
                lines.append("")

        lines.append("---")
        lines.append("")

    # Interpretation guide
    lines.append("## How to interpret these numbers")
    lines.append("")
    lines.append("**faithfulness** — fraction of answer claims supported by sources. ")
    lines.append("Avg < 0.7 means the LLM is fabricating facts. Likely fix: tighten ")
    lines.append("the system prompt to enforce 'use only the sources'.")
    lines.append("")
    lines.append("**context_recall** — fraction of must-mention concepts covered by ")
    lines.append("retrieved sources. Avg < 0.6 means the retriever is missing ")
    lines.append("relevant documents. Likely fix: increase top_k, investigate ")
    lines.append("reranker behaviour, or revisit chunk size for long descriptions.")
    lines.append("")
    lines.append("**answer_relevancy** — how on-topic the answer is. Avg < 0.7 means ")
    lines.append("the LLM is rambling, off-topic, or hallucinating answers to ")
    lines.append("unanswerable queries. Likely fix: prompt clarity, or upstream ")
    lines.append("retrieval quality (irrelevant sources push the LLM to improvise).")
    lines.append("")
    lines.append("**Skipped queries (None scores)** are the metrics opting out cleanly. ")
    lines.append("Queries q05 and q20 are unanswerable — `must_mention` is empty so ")
    lines.append("`context_recall` correctly skips. If the LLM said 'I don't know', ")
    lines.append("`faithfulness` skips too (no claims to verify). This is the SUCCESS ")
    lines.append("path for those queries — not a failure.")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# Main


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run custom evaluation on the ELH RAG golden set."
    )
    parser.add_argument(
        "--golden-set",
        type=Path,
        default=Path("evaluation/golden_set.yaml"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/reports/light_eval"),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit to first N queries (smoke testing)",
    )
    parser.add_argument(
        "--label",
        type=str,
        default="",
        help="Optional suffix appended to output filenames",
    )
    args = parser.parse_args()

    setup_logging()

    thresholds = {
        "faithfulness": 0.70,
        "context_recall": 0.60,
        "answer_relevancy": 0.70,
    }

    print("ELH RAG — light evaluation (custom evaluation)")
    print("=" * 60)
    print(f"Golden set: {args.golden_set}")
    queries = load_golden_set(args.golden_set)
    if args.limit:
        queries = queries[: args.limit]
    if not queries:
        print("❌ No annotated queries found.")
        return
    print(f"Annotated queries to run: {len(queries)}")
    print()

    print("Initialising pipeline (downloads models on first run)...")
    pipeline = RAGPipeline()
    judge = EvaluationJudge()

    # Step 1 & 2 interleaved: run pipeline + evaluate each response immediately.
    # This way if something crashes we keep partial results in memory.
    records: list[dict[str, Any]] = []
    for i, q in enumerate(queries, 1):
        print(f"  [{i}/{len(queries)}] {q['id']}: {q['question'][:60]}...")

        response, latency, error = run_pipeline_on_query(pipeline, q["question"])
        rec: dict[str, Any] = {**q, "latency_sec": round(latency, 3)}

        if error or response is None:
            rec["error"] = error or "unknown error"
            rec["contexts"] = []
            rec["answer"] = ""
            records.append(rec)
            print(f"      pipeline failed: {error}")
            continue

        rec["contexts"] = extract_contexts(response)
        rec["answer"] = response.answer
        if response.routing:
            rec["routing"] = {
                "intent": response.routing.intent.value,
                "confidence": response.routing.confidence,
                "source": response.routing.source,
            }

        # Evaluate immediately (3 judge calls)
        eval_start = time.perf_counter()
        eval_result = evaluate_query(
            judge=judge,
            question=q["question"],
            answer=rec["answer"],
            contexts=rec["contexts"],
            must_mention=q.get("must_mention", []),
        )
        rec.update(eval_result)
        eval_elapsed = time.perf_counter() - eval_start

        f_str = "N/A" if rec["faithfulness_score"] is None else f"{rec['faithfulness_score']:.2f}"
        cr_str = "N/A" if rec["context_recall_score"] is None else f"{rec['context_recall_score']:.2f}"
        ar_str = "N/A" if rec["answer_relevancy_score"] is None else f"{rec['answer_relevancy_score']:.2f}"
        print(
            f"      pipeline {latency:.1f}s + eval {eval_elapsed:.1f}s  "
            f"f={f_str} cr={cr_str} ar={ar_str}"
        )

        records.append(rec)

    # Step 3: identify problems, save outputs.
    problems = identify_problems(records, thresholds)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    label_suffix = f"_{args.label}" if args.label else ""
    jsonl_path = args.output_dir / f"phase2.5_custom_results_{ts}{label_suffix}.jsonl"
    md_path = args.output_dir / f"phase2.5_custom_report_{ts}{label_suffix}.md"

    save_jsonl(records, jsonl_path)
    write_markdown_report(records, problems, md_path, thresholds)

    # Console summary
    print()
    print("=" * 60)
    print(f"JSONL:   {jsonl_path}")
    print(f"Report:  {md_path}")
    print("=" * 60)
    print()
    print("Aggregates:")
    for metric in ["faithfulness", "context_recall", "answer_relevancy"]:
        scores = [r.get(f"{metric}_score") for r in records if not r.get("error")]
        agg = aggregate(scores)
        print(
            f"  {metric:18s}  avg={agg['avg']}  median={agg['median']}  "
            f"valid={agg['n']}  skipped={agg['skipped']}"
        )
    print()
    print(f"Sub-threshold cases: {len(problems)}")
    if problems:
        print("Top 3 most severe:")
        for p in problems[:3]:
            print(f"  {p['query_id']}  {p['metric']}={p['score']}  → {p['question'][:60]}")


if __name__ == "__main__":
    main()