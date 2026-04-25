"""
Qualitative benchmark for the RAG pipeline.

Evaluates the system across three configurations (Naive, +Rewrite, +Rerank) 
to demonstrate behavioral changes and pipeline latency. It logs the rewritten 
queries, top-5 retrieved sources, final answers, and execution times, 
exporting the results to JSONL (raw) and Markdown (supervisor report).

Note: This is strictly a qualitative assessment. Lacking a ground-truth 
dataset, it tracks observable metrics (latency, answer comparisons) 
rather than rigorous quantitative metrics like precision or recall.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from elh_rag import config as cfg_module
from elh_rag.logging_setup import setup_logging
from elh_rag.pipeline import RAGPipeline
from elh_rag.schemas import RAGResponse


# Configurations under test

CONFIGURATIONS = [
    {
        "name": "naive",
        "label": "Naive (Phase 1 baseline)",
        "enable_query_rewriting": False,
        "enable_reranking": False,
    },
    {
        "name": "rewrite",
        "label": "+Query rewriting (Phase 2, Step 1)",
        "enable_query_rewriting": True,
        "enable_reranking": False,
    },
    {
        "name": "rewrite_rerank",
        "label": "+Query rewriting +Reranking (Phase 2, Step 2)",
        "enable_query_rewriting": True,
        "enable_reranking": True,
    },
]


# Benchmark runner


def load_queries(path: Path) -> list[dict[str, Any]]:
    """Load the test query set from YAML."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["queries"]


def apply_config(config: dict[str, Any]) -> None:
    """Patch the live settings object to match the configuration."""
    cfg_module.settings.enable_query_rewriting = config["enable_query_rewriting"]
    cfg_module.settings.enable_reranking = config["enable_reranking"]


def run_single_query(
    pipeline: RAGPipeline, question: str
) -> tuple[RAGResponse, float]:
    """Run a single query, returning the response and wall-clock latency."""
    start = time.perf_counter()
    response = pipeline.query(question)
    elapsed = time.perf_counter() - start
    return response, elapsed


def run_benchmark(
    queries: list[dict[str, Any]], pipeline: RAGPipeline
) -> list[dict[str, Any]]:
    """Run all queries through all configurations."""
    results: list[dict[str, Any]] = []

    for i, query_def in enumerate(queries, 1):
        qid = query_def["id"]
        qtext = query_def["text"]
        print(f"\n[{i}/{len(queries)}] {qid} ({query_def['category']})")
        print(f"    Query: {qtext[:90]}{'...' if len(qtext) > 90 else ''}")

        per_query_runs: list[dict[str, Any]] = []

        for config in CONFIGURATIONS:
            apply_config(config)
            print(f"    > {config['name']:<20}", end=" ", flush=True)

            try:
                response, latency = run_single_query(pipeline, qtext)
                print(f"[{latency:.2f}s, {len(response.sources)} sources]")

                per_query_runs.append(
                    {
                        "config": config["name"],
                        "config_label": config["label"],
                        "latency_sec": round(latency, 3),
                        "mode": response.mode,
                        "rewritten_query": response.rewritten_query,
                        "answer": response.answer,
                        "sources": [
                            {
                                "id": s.metadata.id,
                                "flatname": s.metadata.flatname,
                                "city": s.metadata.city,
                                "zone": s.metadata.zone,
                                "review_title": s.metadata.review_title,
                                "vector_score": s.vector_score,
                                "rerank_score": s.rerank_score,
                            }
                            for s in response.sources
                        ],
                    }
                )
            except Exception as exc:
                print(f"FAILED: {exc}")
                per_query_runs.append(
                    {
                        "config": config["name"],
                        "config_label": config["label"],
                        "error": str(exc),
                    }
                )

        results.append(
            {
                "id": qid,
                "category": query_def["category"],
                "language": query_def.get("language", "en"),
                "text": qtext,
                "notes": query_def.get("notes", ""),
                "runs": per_query_runs,
            }
        )

    return results


# Aggregated metrics


def compute_aggregate_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary statistics across all queries."""
    metrics: dict[str, Any] = {
        "total_queries": len(results),
        "per_config": {},
    }

    for cfg in CONFIGURATIONS:
        name = cfg["name"]
        runs = [
            r
            for query in results
            for r in query["runs"]
            if r.get("config") == name and "error" not in r
        ]

        if not runs:
            metrics["per_config"][name] = {"ok": False, "reason": "no successful runs"}
            continue

        latencies = [r["latency_sec"] for r in runs]
        latencies_sorted = sorted(latencies)
        n = len(latencies_sorted)

        metrics["per_config"][name] = {
            "label": cfg["label"],
            "ok": True,
            "runs": n,
            "latency_avg": round(sum(latencies) / n, 3),
            "latency_median": round(latencies_sorted[n // 2], 3),
            "latency_min": round(min(latencies), 3),
            "latency_max": round(max(latencies), 3),
            "avg_sources": round(sum(len(r.get("sources", [])) for r in runs) / n, 1),
        }

    metrics["reshuffling"] = compute_reshuffling(results)
    metrics["rewriting_activity"] = compute_rewriting_activity(results)

    return metrics


def compute_reshuffling(results: list[dict[str, Any]]) -> dict[str, Any]:
    """How often did reranking change the top-1 vs vector-only order?"""
    changes_top1 = 0
    changes_any = 0
    total = 0

    for query in results:
        runs_by_config = {r.get("config"): r for r in query["runs"]}

        rewrite_run = runs_by_config.get("rewrite")
        rerank_run = runs_by_config.get("rewrite_rerank")

        if not rewrite_run or not rerank_run:
            continue
        if "error" in rewrite_run or "error" in rerank_run:
            continue

        vector_ids = [s["id"] for s in rewrite_run.get("sources", [])]
        rerank_ids = [s["id"] for s in rerank_run.get("sources", [])]

        if not vector_ids or not rerank_ids:
            continue

        total += 1
        if vector_ids[0] != rerank_ids[0]:
            changes_top1 += 1
        if vector_ids != rerank_ids:
            changes_any += 1

    return {
        "total_compared": total,
        "top1_changed": changes_top1,
        "top1_changed_pct": round(100.0 * changes_top1 / total, 1) if total else 0.0,
        "any_order_changed": changes_any,
        "any_order_changed_pct": round(100.0 * changes_any / total, 1) if total else 0.0,
    }


def compute_rewriting_activity(results: list[dict[str, Any]]) -> dict[str, Any]:
    """How often did the rewriter actually produce a different query?"""
    total = 0
    rewritten = 0

    for query in results:
        for run in query["runs"]:
            if run.get("config") != "rewrite":
                continue
            if "error" in run:
                continue
            total += 1
            if run.get("rewritten_query"):
                rewritten += 1

    return {
        "total": total,
        "rewritten": rewritten,
        "rewritten_pct": round(100.0 * rewritten / total, 1) if total else 0.0,
    }


# Output: JSONL + Markdown report


def save_jsonl(results: list[dict[str, Any]], path: Path) -> None:
    """Save raw results as JSONL (one query per line)."""
    with path.open("w", encoding="utf-8") as f:
        for query in results:
            f.write(json.dumps(query, ensure_ascii=False) + "\n")


def generate_markdown_report(
    results: list[dict[str, Any]],
    metrics: dict[str, Any],
    path: Path,
) -> None:
    """Generate a human-readable Markdown report."""
    lines: list[str] = []

    lines.append("# ELH RAG — Qualitative Benchmark Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Queries:** {metrics['total_queries']}")
    lines.append("")

    # Methodology disclaimer
    lines.append("## Methodological note")
    lines.append("")
    lines.append(
        "This report is a **qualitative benchmark**, not a rigorous "
        "quantitative evaluation. Without a ground-truth labelled dataset "
        "(to be built in Phase 4, Step 1) we cannot report precision@k, "
        "recall@k, or RAGAS faithfulness / answer relevance."
    )
    lines.append("")
    lines.append(
        "What you will find below is a side-by-side comparison of three "
        "configurations on the same inputs, plus observables — latency, "
        "reshuffling rate, rewriting activity — that help describe how "
        "the system behaves. Judgements about *quality* are left to the "
        "reader and will be replaced by RAGAS metrics in Phase 4."
    )
    lines.append("")

    # Executive summary
    lines.append("## Executive summary")
    lines.append("")
    lines.append("### Latency comparison")
    lines.append("")
    lines.append("| Configuration | Avg (s) | Median (s) | Min | Max | Sources |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for cfg_name, stats in metrics["per_config"].items():
        if not stats.get("ok"):
            continue
        lines.append(
            f"| {stats['label']} | "
            f"{stats['latency_avg']} | {stats['latency_median']} | "
            f"{stats['latency_min']} | {stats['latency_max']} | "
            f"{stats['avg_sources']} |"
        )
    lines.append("")

    rew = metrics["rewriting_activity"]
    lines.append("### Query rewriting activity")
    lines.append("")
    lines.append(
        f"Of {rew['total']} queries, the rewriter produced a **different** "
        f"query **{rew['rewritten']} times ({rew['rewritten_pct']}%)**. "
        "The remaining queries were returned unchanged by the rewriter — "
        "typically because they were already well-formed search queries."
    )
    lines.append("")

    rsh = metrics["reshuffling"]
    lines.append("### Reranking reshuffling rate")
    lines.append("")
    lines.append(
        f"Comparing the vector-only order (+Rewrite config) against the "
        f"reranked order (+Rewrite+Rerank config) on {rsh['total_compared']} queries:"
    )
    lines.append("")
    lines.append(
        f"- **Top-1 result changed** in {rsh['top1_changed']}/"
        f"{rsh['total_compared']} cases ({rsh['top1_changed_pct']}%)"
    )
    lines.append(
        f"- **Any ordering change** in {rsh['any_order_changed']}/"
        f"{rsh['total_compared']} cases ({rsh['any_order_changed_pct']}%)"
    )
    lines.append("")
    lines.append(
        "*Interpretation:* a reshuffling rate close to 0% would suggest "
        "reranking adds latency without benefit; a rate close to 100% could "
        "indicate instability or conflict between the two signals. The "
        "sweet spot is typically 30-70%, indicating reranking refines but "
        "doesn't overturn the initial retrieval."
    )
    lines.append("")

    # Per-query details
    lines.append("## Per-query results")
    lines.append("")

    for query in results:
        lines.append(f"### {query['id']} — {query['category']}")
        lines.append("")
        lines.append(f"**Question:** {query['text']}")
        lines.append("")
        if query.get("notes"):
            lines.append(f"*{query['notes']}*")
            lines.append("")

        for run in query["runs"]:
            if "error" in run:
                lines.append(f"#### {run['config_label']}")
                lines.append("")
                lines.append(f"❌ **Failed:** `{run['error']}`")
                lines.append("")
                continue

            lines.append(f"#### {run['config_label']}")
            lines.append("")
            lines.append(
                f"- **Mode:** `{run['mode']}` · "
                f"**Latency:** {run['latency_sec']}s · "
                f"**Sources:** {len(run.get('sources', []))}"
            )
            if run.get("rewritten_query"):
                lines.append(f"- **Rewritten query:** *{run['rewritten_query']}*")
            lines.append("")

            lines.append("**Top sources:**")
            lines.append("")
            lines.append("| # | Property | Location | Vector score | Rerank score |")
            lines.append("|---|---|---|---:|---:|")
            for idx, src in enumerate(run.get("sources", [])[:5], 1):
                flat = src.get("flatname") or "—"
                loc = ", ".join(filter(None, [src.get("zone"), src.get("city")])) or "—"
                vs = f"{src['vector_score']:.3f}" if src.get("vector_score") is not None else "—"
                rs = f"{src['rerank_score']:.3f}" if src.get("rerank_score") is not None else "—"
                lines.append(f"| {idx} | {flat} | {loc} | {vs} | {rs} |")
            lines.append("")

            answer = run.get("answer", "")
            preview = answer[:600] + ("…" if len(answer) > 600 else "")
            lines.append("**Answer (first 600 chars):**")
            lines.append("")
            lines.append("> " + preview.replace("\n", "\n> "))
            lines.append("")

        lines.append("---")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# Main


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run qualitative benchmark of the RAG pipeline."
    )
    parser.add_argument(
        "--queries",
        type=Path,
        default=Path("evaluation/queries.yaml"),
        help="YAML file with the query set (default: evaluation/queries.yaml)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation"),
        help="Directory where JSONL and Markdown outputs are saved",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit to first N queries (useful for smoke tests)",
    )
    args = parser.parse_args()

    setup_logging()

    print("ELH RAG — Qualitative Benchmark")
    print("=" * 60)

    queries = load_queries(args.queries)
    if args.limit:
        queries = queries[: args.limit]
    print(f"Loaded {len(queries)} queries from {args.queries}")

    print("Initialising pipeline (this may download models on first run)...")
    pipeline = RAGPipeline()

    results = run_benchmark(queries, pipeline)
    metrics = compute_aggregate_metrics(results)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    jsonl_path = args.output_dir / f"qualitative_results_{ts}.jsonl"
    md_path = args.output_dir / f"qualitative_report_{ts}.md"

    save_jsonl(results, jsonl_path)
    generate_markdown_report(results, metrics, md_path)

    print()
    print("=" * 60)
    print(f"Raw results: {jsonl_path}")
    print(f"Report:      {md_path}")
    print("=" * 60)
    print()
    print("Summary:")
    for cfg_name, stats in metrics["per_config"].items():
        if stats.get("ok"):
            print(
                f"  {stats['label']:<55} "
                f"avg {stats['latency_avg']:>5.2f}s  "
                f"median {stats['latency_median']:>5.2f}s"
            )
    rsh = metrics["reshuffling"]
    print(
        f"  Reranking changed top-1 in {rsh['top1_changed']}/{rsh['total_compared']} "
        f"queries ({rsh['top1_changed_pct']}%)"
    )


if __name__ == "__main__":
    main()