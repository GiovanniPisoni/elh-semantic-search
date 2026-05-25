"""
Custom evaluation script.

Runs the ELH RAG pipeline on the curated golden set, then evaluates each
response with three custom metrics built on Claude as judge:

    - faithfulness:     answer claims supported by retrieved sources?
    - context_recall:   must-mention concepts present in retrieved sources?
    - answer_relevancy: does the answer address the question on-topic?

Outputs:
    - JSONL with one record per query (full per-metric details + reasoning),
      written incrementally so a crash mid-run never loses work
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

from elh_rag.agent import AgentContext, run_agent_turn
from elh_rag.evaluation.judge import EvaluationJudge
from elh_rag.evaluation.metrics import (
    answer_relevancy,
    context_recall,
    faithfulness,
    task_success,
)
from elh_rag.logging_setup import setup_logging

# Golden set loading


def load_golden_set(path: Path) -> list[dict[str, Any]]:
    """Load golden set queries from YAML, skipping unannotated stubs."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    queries = data.get("queries", [])
    real = [q for q in queries if not q.get("question", "").startswith("REPLACE_WITH_")]
    skipped = len(queries) - len(real)
    if skipped:
        print(f"Skipped {skipped} unannotated stub(s)")
    return real


# Agent runner


_PHASE3_SEMANTIC_TOOLS = ("search_descriptions", "search_reviews")
_PHASE3_POLICY_TOOLS = ("answer_policy_question",)


def run_phase3_on_query(
    ctx: AgentContext, question: str
) -> tuple[dict[str, Any] | None, float, str | None]:
    """Run the Phase 3 agent and normalise its response for the judge.

    The judge framework expects (answer, contexts) pairs. For Phase 3 we:
        - take ``answer = AgentResponse.final_message``;
        - extract ``contexts`` from the tool trace: ``hits[].text`` for
          the two RAG-search tools, ``matches[].answer`` for the policy
          tool. DB tools (find_rooms, compute_total_cost, ...) produce
          no semantic context, so ``contexts`` stays empty for
          structural/cost queries — that is the correct signal to the
          judge that faithfulness/context_recall do not apply.
    """
    start = time.perf_counter()
    try:
        response = run_agent_turn(query=question, ctx=ctx)
    except Exception as exc:
        return None, time.perf_counter() - start, str(exc)

    latency = time.perf_counter() - start

    contexts: list[str] = []
    tools_used: list[str] = []
    for tool_call in response.tool_trace:
        tools_used.append(tool_call.name)
        if tool_call.output_json is None:
            continue
        try:
            output = json.loads(tool_call.output_json)
        except json.JSONDecodeError:
            continue

        if tool_call.name in _PHASE3_SEMANTIC_TOOLS:
            for hit in output.get("hits", []):
                text = hit.get("text")
                if text:
                    contexts.append(text)
        elif tool_call.name in _PHASE3_POLICY_TOOLS:
            for match in output.get("matches", []):
                answer_text = match.get("answer")
                if answer_text:
                    contexts.append(answer_text)

    normalised: dict[str, Any] = {
        "answer": response.final_message,
        "contexts": contexts,
        "tools_used": tools_used,
        "hop_count": response.hop_count,
        "stop_reason": response.stop_reason,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "total_duration_ms": response.total_duration_ms,
    }
    return normalised, latency, None


# Evaluation


def evaluate_query(
    judge: EvaluationJudge,
    question: str,
    answer: str,
    contexts: list[str],
    must_mention: list[str],
) -> dict[str, Any]:
    """Run the four metrics on a single (question, answer, contexts) tuple."""
    f_result = faithfulness(judge=judge, answer=answer, contexts=contexts)
    cr_result = context_recall(judge=judge, must_mention=must_mention, contexts=contexts)
    ar_result = answer_relevancy(judge=judge, question=question, answer=answer)
    ts_result = task_success(judge=judge, question=question, answer=answer)

    return {
        "faithfulness_score": f_result.score,
        "faithfulness_details": f_result.details,
        "context_recall_score": cr_result.score,
        "context_recall_details": cr_result.details,
        "answer_relevancy_score": ar_result.score,
        "answer_relevancy_details": ar_result.details,
        "task_success_score": ts_result.score,
        "task_success_details": ts_result.details,
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
                problems.append(
                    {
                        "query_id": r["id"],
                        "question": r["question"],
                        "metric": metric,
                        "score": score,
                        "threshold": threshold,
                        "severity": round(threshold - score, 3),
                    }
                )
    problems.sort(key=lambda p: -p["severity"])
    return problems


# Persistence


def save_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    """Persist raw per-query records (machine-readable, full rewrite).

    Useful when reconstructing a JSONL from records held in memory, e.g.
    by a one-shot regenerator script. The live evaluation loop in `main`
    uses `append_jsonl_record` instead, to be crash-safe.
    """
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def append_jsonl_record(record: dict[str, Any], path: Path) -> None:
    """Append a single record to a JSONL file in 'a' mode.

    Used during a run to persist results incrementally. If the run is
    interrupted (API credit exhausted, rate limit, Ctrl+C, crash), all
    records completed so far are safely on disk.
    """
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def write_markdown_report(
    records: list[dict[str, Any]],
    problems: list[dict[str, Any]],
    path: Path,
    thresholds: dict[str, float],
    system: str = "agentic-RAG",
) -> None:
    """Write the human-facing Markdown diagnostic report."""
    lines: list[str] = []

    lines.append("# ELH RAG — Custom evaluation report — Phase 3 — Agentic RAG")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**System under test:** `{system}`")
    n_ok = len([r for r in records if not r.get("error")])
    n_err = len(records) - n_ok
    lines.append(f"**Queries:** {len(records)} total · {n_ok} OK · {n_err} errored")
    lines.append("")
    lines.append("Custom evaluation framework — written from scratch after RAGAS 0.4 ")
    lines.append("produced ~90% NaN values on this golden set. Four metrics measured:")
    lines.append("**faithfulness**, **context_recall**, **answer_relevancy**, **task_success**. ")
    lines.append("Each metric is judged by Claude Sonnet 4.5 with a deterministic JSON-output ")
    lines.append("contract; per-claim reasoning is preserved in the JSONL companion file. ")
    lines.append("`task_success` is architecture-agnostic — it judges (question, answer) ")
    lines.append(
        "without retrieved contexts, so it applies equally to pipeline and agentic systems."
    )
    lines.append("")

    # Aggregates
    lines.append("## Aggregates")
    lines.append("")
    lines.append("| Metric | Avg | Median | Min | Max | Valid (N) | Skipped |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for metric in ["faithfulness", "context_recall", "answer_relevancy", "task_success"]:
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
        for m in ["faithfulness", "context_recall", "answer_relevancy", "task_success"]:
            s = r.get(f"{m}_score")
            score_str = "N/A" if s is None else f"{s:.3f}"
            score_parts.append(f"**{m}:** {score_str}")
        lines.append(" · ".join(score_parts))
        lines.append("")

        lines.append(
            f"**Latency:** {r.get('latency_sec', '?')}s · **Sources:** {len(r.get('contexts', []))}"
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
    lines.append("**task_success** — did the answer actually solve the user's task? ")
    lines.append("3-point scale: 1.0 (fully solved with actionable specifics), 0.5 ")
    lines.append("(partially helpful), 0.0 (off-topic / evasive). A correct refusal of ")
    lines.append("a genuinely unanswerable question scores 1.0. Unlike faithfulness and ")
    lines.append("context_recall, this metric needs no retrieved contexts, so it crosses ")
    lines.append("architectural paradigms (pipeline vs agentic) cleanly. Avg < 0.5 means ")
    lines.append("the system frequently fails to deliver actionable content.")
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
    parser = argparse.ArgumentParser(description="Run custom evaluation on the ELH RAG golden set.")
    parser.add_argument(
        "--golden-set",
        type=Path,
        default=Path("evaluation/agent_queries_full_set.yaml"),
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
    parser.add_argument(
        "--system",
        type=str,
        choices=["agentic-RAG"],
        default="agentic-RAG",
        help=(
            "Which system to evaluate. Only 'agentic-RAG' (Phase 3) is "
            "supported on develop. Phase 2 (pipelined-RAG) has been "
            "archived to branch v2-pipelined-RAG-archive — checkout that "
            "branch to run the legacy pipelined-RAG evaluation."
        ),
    )
    args = parser.parse_args()

    setup_logging()

    thresholds = {
        "faithfulness": 0.70,
        "context_recall": 0.60,
        "answer_relevancy": 0.70,
        "task_success": 0.50,
    }

    print("ELH RAG — light evaluation (custom evaluation)")
    print("=" * 60)
    print(f"System:     {args.system}")
    print(f"Golden set: {args.golden_set}")
    queries = load_golden_set(args.golden_set)
    if args.limit:
        queries = queries[: args.limit]
    if not queries:
        print("No annotated queries found.")
        return
    print(f"Annotated queries to run: {len(queries)}")
    print()

    judge = EvaluationJudge()

    print("Initialising Phase 3 AgentContext (loads embedder, KB, stores)...")
    agent_ctx = AgentContext.build()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    label_suffix = f"_{args.label}" if args.label else ""
    jsonl_path = args.output_dir / f"phase2.5_custom_results_{ts}{label_suffix}.jsonl"
    md_path = args.output_dir / f"phase2.5_custom_report_{ts}{label_suffix}.md"

    jsonl_path.write_text("", encoding="utf-8")

    records: list[dict[str, Any]] = []
    for i, q in enumerate(queries, 1):
        print(f"  [{i}/{len(queries)}] {q['id']}: {q['question'][:60]}...")

        rec: dict[str, Any] = {**q, "system": args.system}

        normalised, latency, error = run_phase3_on_query(agent_ctx, q["question"])
        rec["latency_sec"] = round(latency, 3)

        if error or normalised is None:
            rec["error"] = error or "unknown error"
            rec["contexts"] = []
            rec["answer"] = ""
            records.append(rec)
            append_jsonl_record(rec, jsonl_path)
            print(f"      agent failed: {error}")
            continue

        rec["contexts"] = normalised["contexts"]
        rec["answer"] = normalised["answer"]
        rec["tools_used"] = normalised["tools_used"]
        rec["hop_count"] = normalised["hop_count"]
        rec["stop_reason"] = normalised["stop_reason"]
        rec["input_tokens"] = normalised["input_tokens"]
        rec["output_tokens"] = normalised["output_tokens"]
        rec["total_duration_ms"] = normalised["total_duration_ms"]

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
        cr_str = (
            "N/A" if rec["context_recall_score"] is None else f"{rec['context_recall_score']:.2f}"
        )
        ar_str = (
            "N/A"
            if rec["answer_relevancy_score"] is None
            else f"{rec['answer_relevancy_score']:.2f}"
        )
        print(
            f"      pipeline {latency:.1f}s + eval {eval_elapsed:.1f}s  "
            f"f={f_str} cr={cr_str} ar={ar_str}"
        )

        records.append(rec)
        append_jsonl_record(rec, jsonl_path)

    # Step 3: identify problems, write the Markdown report.
    # The JSONL has been written incrementally already.
    problems = identify_problems(records, thresholds)
    write_markdown_report(records, problems, md_path, thresholds, system=args.system)

    # Console summary
    print()
    print("=" * 60)
    print(f"JSONL:   {jsonl_path}")
    print(f"Report:  {md_path}")
    print("=" * 60)
    print()
    print("Aggregates:")
    for metric in ["faithfulness", "context_recall", "answer_relevancy", "task_success"]:
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
            print(f"  {p['query_id']}  {p['metric']}={p['score']}  -> {p['question'][:60]}")


if __name__ == "__main__":
    main()
