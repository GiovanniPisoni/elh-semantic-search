"""
Qualitative benchmark for the full orchestrated pipeline.
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

from elh_rag.logging_setup import setup_logging
from elh_rag.pipeline import RAGPipeline
from elh_rag.schemas import Intent, RAGResponse


# Cost model (USD per million tokens)

_PRICING: dict[str, dict[str, float]] = {
    "claude-haiku": {"input": 0.80, "output": 4.00},
    "claude-sonnet": {"input": 3.00, "output": 15.00},
}

_EST_TOKENS_PER_QUERY = {
    "router_input": 2000,
    "router_output": 60,
    "rewriter_input": 400,
    "rewriter_output": 40,
    "generator_input": 3000,
    "generator_output": 250,
}


# Loaders


def load_queries(path: Path) -> list[dict[str, Any]]:
    """Load the extended query set from YAML."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["queries"]


# Single-query runner


def run_single(
    pipeline: RAGPipeline, question: str
) -> tuple[RAGResponse | None, float, str | None]:
    """Run a single query through the full pipeline."""
    start = time.perf_counter()
    try:
        response = pipeline.query(question)
        elapsed = time.perf_counter() - start
        return response, elapsed, None
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return None, elapsed, str(exc)


def extract_run_record(
    query_def: dict[str, Any],
    response: RAGResponse | None,
    latency: float,
    error: str | None,
) -> dict[str, Any]:
    """Flatten a run into a dict suitable for JSON serialisation and reporting."""
    base: dict[str, Any] = {
        "id": query_def["id"],
        "category": query_def["category"],
        "language": query_def.get("language", "en"),
        "text": query_def["text"],
        "expected_intent": query_def.get("expected_intent"),
        "notes": query_def.get("notes", ""),
        "latency_sec": round(latency, 3),
    }

    if error is not None or response is None:
        base["error"] = error or "unknown error"
        return base

    # Routing
    if response.routing is not None:
        base["routing"] = {
            "intent": response.routing.intent.value,
            "confidence": round(response.routing.confidence, 3),
            "source": response.routing.source,
            "reasoning": response.routing.reasoning,
        }

    # Rewrite
    base["rewritten_query"] = response.rewritten_query
    base["mode"] = response.mode

    # Sources by corpus
    if response.sources_by_source:
        base["sources_by_source"] = {
            corpus: _serialise_sources(sources)
            for corpus, sources in response.sources_by_source.items()
        }

    # Flat top-k view (what the LLM saw)
    base["merged_sources"] = _serialise_sources(response.sources)

    # Answer
    base["answer"] = response.answer
    return base


def _serialise_sources(sources: list) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in sources:
        m = s.metadata
        out.append(
            {
                "id": m.id,
                "source": m.source.value,
                "flatname": getattr(m, "flatname", ""),
                "roomname": getattr(m, "roomname", ""),
                "city": m.city,
                "zone": getattr(m, "zone", ""),
                "vector_score": round(s.vector_score, 3)
                if s.vector_score is not None
                else None,
                "rerank_score": round(s.rerank_score, 3)
                if s.rerank_score is not None
                else None,
            }
        )
    return out


# Aggregations


def compute_metrics(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary metrics across all runs."""
    total = len(runs)
    errored = [r for r in runs if "error" in r]
    ok = [r for r in runs if "error" not in r]

    metrics: dict[str, Any] = {
        "total_queries": total,
        "errored": len(errored),
        "ok": len(ok),
    }

    if not ok:
        return metrics

    # Latency aggregates
    latencies = [r["latency_sec"] for r in ok]
    latencies_sorted = sorted(latencies)
    metrics["latency"] = {
        "avg": round(statistics.mean(latencies), 3),
        "median": round(statistics.median(latencies), 3),
        "min": round(min(latencies), 3),
        "max": round(max(latencies), 3),
        "p95": round(
            latencies_sorted[max(0, int(0.95 * len(latencies_sorted)) - 1)], 3
        ),
    }

    # Routing accuracy vs expected_intent
    matched, mismatched = _routing_accuracy(ok)
    metrics["routing_accuracy"] = {
        "matched": matched,
        "mismatched": mismatched,
        "total": matched + mismatched,
        "pct": round(100 * matched / (matched + mismatched), 1)
        if (matched + mismatched) > 0
        else 0.0,
    }

    # Intent distribution
    intent_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    confidences: list[float] = []
    for r in ok:
        routing = r.get("routing", {})
        intent = routing.get("intent", "?")
        src = routing.get("source", "?")
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
        source_counts[src] = source_counts.get(src, 0) + 1
        conf = routing.get("confidence")
        if conf is not None:
            confidences.append(conf)

    metrics["routing_distribution"] = intent_counts
    metrics["routing_source_distribution"] = source_counts
    if confidences:
        metrics["confidence"] = {
            "avg": round(statistics.mean(confidences), 3),
            "median": round(statistics.median(confidences), 3),
            "min": round(min(confidences), 3),
            "max": round(max(confidences), 3),
        }

    # Cost estimate
    metrics["cost_estimate_usd"] = _cost_estimate(len(ok))

    return metrics


def _routing_accuracy(ok: list[dict[str, Any]]) -> tuple[int, int]:
    """Count matched / mismatched routing decisions vs expected_intent."""
    matched = 0
    mismatched = 0
    for r in ok:
        expected = r.get("expected_intent")
        got = r.get("routing", {}).get("intent")
        if expected is None or got is None:
            continue
        if expected == got:
            matched += 1
        else:
            mismatched += 1
    return matched, mismatched


def _cost_estimate(n_queries: int) -> dict[str, Any]:
    """Estimate total API cost (USD) for the benchmark run."""
    haiku_in = _EST_TOKENS_PER_QUERY["router_input"] + _EST_TOKENS_PER_QUERY["rewriter_input"]
    haiku_out = (
        _EST_TOKENS_PER_QUERY["router_output"]
        + _EST_TOKENS_PER_QUERY["rewriter_output"]
    )
    sonnet_in = _EST_TOKENS_PER_QUERY["generator_input"]
    sonnet_out = _EST_TOKENS_PER_QUERY["generator_output"]

    haiku_cost = (
        haiku_in * _PRICING["claude-haiku"]["input"] / 1_000_000
        + haiku_out * _PRICING["claude-haiku"]["output"] / 1_000_000
    )
    sonnet_cost = (
        sonnet_in * _PRICING["claude-sonnet"]["input"] / 1_000_000
        + sonnet_out * _PRICING["claude-sonnet"]["output"] / 1_000_000
    )

    per_query = haiku_cost + sonnet_cost
    total = per_query * n_queries
    return {
        "per_query_usd": round(per_query, 5),
        "total_usd": round(total, 4),
        "n_queries": n_queries,
    }


# Output: JSONL + Markdown


def save_jsonl(runs: list[dict[str, Any]], path: Path) -> None:
    """Write one JSON object per line — machine-readable full results."""
    with path.open("w", encoding="utf-8") as f:
        for r in runs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def generate_report(
    runs: list[dict[str, Any]],
    metrics: dict[str, Any],
    path: Path,
) -> None:
    """Render the human-facing Markdown report."""
    lines: list[str] = []

    lines.append("# ELH RAG — Orchestrator Qualitative Benchmark")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Queries:** {metrics['total_queries']}  ·  **OK:** {metrics['ok']}  ·  **Errored:** {metrics['errored']}")
    lines.append("")
    lines.append(
        "This report exercises the complete Phase 2 Step 4 pipeline: "
        "query rewriting + dual-corpus retrieval + cross-encoder "
        "reranking + intent routing + generation. Every query hits the "
        "same configuration; the interesting variation is the routing "
        "decision and how that affects the retrieval mix."
    )
    lines.append("")

    # Methodology
    lines.append("## Methodological note")
    lines.append("")
    lines.append(
        "This is a **qualitative benchmark**, not a rigorous quantitative "
        "evaluation. We report observables (latency, routing distribution, "
        "routing agreement against our own `expected_intent` labels) and "
        "let the reader judge quality. Proper precision@k / recall@k and "
        "RAGAS faithfulness will be measured in Phase 4 once a curated "
        "golden set is available."
    )
    lines.append("")

    # Executive summary
    lines.append("## Executive summary")
    lines.append("")

    if metrics.get("ok", 0) > 0:
        _write_exec_summary(lines, metrics)
    lines.append("")

    # Routing accuracy table
    lines.append("## Routing accuracy per query")
    lines.append("")
    lines.append("| ID | Category | Expected | Got | Confidence | Source | Match |")
    lines.append("|---|---|---|---|---:|---|:---:|")
    for r in runs:
        expected = r.get("expected_intent", "?")
        got = r.get("routing", {}).get("intent", "—")
        conf = r.get("routing", {}).get("confidence")
        src = r.get("routing", {}).get("source", "—")
        match = "✅" if expected == got else "❌"
        if "error" in r:
            match = "⚠️"
            got = "error"
            src = "—"
        conf_str = f"{conf:.2f}" if conf is not None else "—"
        lines.append(
            f"| {r['id']} | {r['category']} | {expected} | {got} | "
            f"{conf_str} | {src} | {match} |"
        )
    lines.append("")

    # Per-query details
    lines.append("## Per-query details")
    lines.append("")

    for r in runs:
        _write_query_section(lines, r)

    path.write_text("\n".join(lines), encoding="utf-8")


def _write_exec_summary(lines: list[str], metrics: dict[str, Any]) -> None:
    lat = metrics.get("latency", {})
    lines.append("### Latency")
    lines.append("")
    lines.append(
        f"- **Avg:** {lat.get('avg')}s  ·  **Median:** {lat.get('median')}s  "
        f"·  **Min:** {lat.get('min')}s  ·  **Max:** {lat.get('max')}s  "
        f"·  **p95:** {lat.get('p95')}s"
    )
    lines.append("")

    acc = metrics.get("routing_accuracy", {})
    lines.append("### Routing agreement with expected intents")
    lines.append("")
    lines.append(
        f"- **Matched:** {acc.get('matched')}/{acc.get('total')} "
        f"({acc.get('pct')}%)"
    )
    lines.append(
        f"- **Mismatched:** {acc.get('mismatched')}/{acc.get('total')}"
    )
    lines.append("")
    lines.append(
        "_'Expected intent' labels are our own annotation in the YAML. "
        "They reflect our view of what each query is asking for; the "
        "router may legitimately disagree on ambiguous cases._"
    )
    lines.append("")

    dist = metrics.get("routing_distribution", {})
    lines.append("### Intent distribution")
    lines.append("")
    for intent in ("reviews", "descriptions", "both"):
        lines.append(f"- **{intent}:** {dist.get(intent, 0)}")
    lines.append("")

    src = metrics.get("routing_source_distribution", {})
    lines.append("### Routing strategy used")
    lines.append("")
    for source in ("llm", "keyword", "default"):
        lines.append(f"- **{source}:** {src.get(source, 0)}")
    lines.append("")

    conf = metrics.get("confidence", {})
    if conf:
        lines.append("### Confidence distribution")
        lines.append("")
        lines.append(
            f"- **Avg:** {conf.get('avg')}  ·  **Median:** {conf.get('median')}  "
            f"·  **Min:** {conf.get('min')}  ·  **Max:** {conf.get('max')}"
        )
        lines.append("")

    cost = metrics.get("cost_estimate_usd", {})
    if cost:
        lines.append("### Cost estimate (USD)")
        lines.append("")
        lines.append(
            f"- **Per query:** ~${cost.get('per_query_usd'):.5f}  "
            f"·  **Total ({cost.get('n_queries')} queries):** "
            f"~${cost.get('total_usd'):.4f}"
        )
        lines.append("")
        lines.append(
            "_Based on heuristic token estimates and approximate Anthropic "
            "pricing. Real cost may vary ±30%._"
        )
        lines.append("")


def _write_query_section(lines: list[str], r: dict[str, Any]) -> None:
    lines.append(f"### {r['id']} — {r['category']}")
    lines.append("")
    lines.append(f"**Question ({r['language']}):** `{r['text']}`")
    lines.append("")
    lines.append(f"*Expected intent:* **{r.get('expected_intent', '?')}**")
    lines.append("")
    if r.get("notes"):
        lines.append(f"*{r['notes']}*")
        lines.append("")

    if "error" in r:
        lines.append(f"❌ **Failed:** `{r['error']}` (after {r['latency_sec']}s)")
        lines.append("")
        lines.append("---")
        lines.append("")
        return

    routing = r.get("routing", {})
    lines.append(
        f"**Routing:** intent=`{routing.get('intent')}` "
        f"· confidence={routing.get('confidence')} "
        f"· source=`{routing.get('source')}`"
    )
    if routing.get("reasoning"):
        lines.append(f"  _→ {routing['reasoning']}_")
    lines.append("")

    lines.append(
        f"**Latency:** {r['latency_sec']}s · **Mode:** `{r.get('mode', '?')}`"
    )
    if r.get("rewritten_query"):
        lines.append(f"**Rewritten:** *{r['rewritten_query']}*")
    lines.append("")

    by_corpus = r.get("sources_by_source", {})
    if by_corpus:
        lines.append("**Sources by corpus:**")
        lines.append("")
        for corpus, sources in by_corpus.items():
            lines.append(f"_{corpus}_ ({len(sources)} sources):")
            lines.append("")
            lines.append("| # | Type | Property | Location | Vec | Rerank |")
            lines.append("|---|---|---|---|---:|---:|")
            for i, s in enumerate(sources[:5], 1):
                name = s.get("roomname") or s.get("flatname") or "—"
                loc = ", ".join(filter(None, [s.get("zone"), s.get("city")])) or "—"
                vs = f"{s['vector_score']:.3f}" if s.get("vector_score") is not None else "—"
                rs = f"{s['rerank_score']:.3f}" if s.get("rerank_score") is not None else "—"
                lines.append(
                    f"| {i} | {s.get('source', '?')} | {name} | {loc} | {vs} | {rs} |"
                )
            lines.append("")

    answer = r.get("answer", "")
    preview = answer[:600] + ("…" if len(answer) > 600 else "")
    lines.append("**Answer (first 600 chars):**")
    lines.append("")
    lines.append("> " + preview.replace("\n", "\n> "))
    lines.append("")
    lines.append("---")
    lines.append("")


# Main


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Step 4 orchestrator benchmark."
    )
    parser.add_argument(
        "--queries",
        type=Path,
        default=Path("evaluation/queries_extended.yaml"),
        help="YAML file with the extended query set",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/reports"),
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

    print("ELH RAG — Orchestrator Qualitative Benchmark")
    print("=" * 60)

    queries = load_queries(args.queries)
    if args.limit:
        queries = queries[: args.limit]
    print(f"Loaded {len(queries)} queries from {args.queries}")

    print("Initialising pipeline (this may download models on first run)...")
    pipeline = RAGPipeline()

    runs: list[dict[str, Any]] = []

    for i, query_def in enumerate(queries, 1):
        qid = query_def["id"]
        qtext = query_def["text"]
        print(
            f"\n[{i}/{len(queries)}] {qid} ({query_def['category']}) "
            f"expected={query_def.get('expected_intent', '?')}"
        )
        preview = qtext if len(qtext) <= 80 else qtext[:77] + "..."
        print(f"    Query: {preview!r}")

        response, latency, error = run_single(pipeline, qtext)
        record = extract_run_record(query_def, response, latency, error)
        runs.append(record)

        if error:
            print(f"    FAILED: {error}")
        else:
            routing = record.get("routing", {})
            got = routing.get("intent", "?")
            conf = routing.get("confidence", 0)
            expected = query_def.get("expected_intent", "?")
            match = "OK" if got == expected else "MISS"
            print(
                f"    [{latency:.2f}s]  routing={got} "
                f"(conf={conf:.2f}, {routing.get('source')}) "
                f"expected={expected}  [{match}]"
            )

    metrics = compute_metrics(runs)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    jsonl_path = args.output_dir / f"orchestrator_results_{ts}.jsonl"
    md_path = args.output_dir / f"orchestrator_report_{ts}.md"

    save_jsonl(runs, jsonl_path)
    generate_report(runs, metrics, md_path)

    print()
    print("=" * 60)
    print(f"Raw results: {jsonl_path}")
    print(f"Report:      {md_path}")
    print("=" * 60)
    print()
    print("Summary:")
    if metrics.get("ok"):
        lat = metrics["latency"]
        acc = metrics["routing_accuracy"]
        print(
            f"  Latency  avg={lat['avg']}s  median={lat['median']}s  "
            f"p95={lat['p95']}s"
        )
        print(
            f"  Routing agreement: {acc['matched']}/{acc['total']} "
            f"({acc['pct']}%)"
        )
        dist = metrics["routing_distribution"]
        print(
            f"  Intent distribution: reviews={dist.get('reviews', 0)}, "
            f"descriptions={dist.get('descriptions', 0)}, "
            f"both={dist.get('both', 0)}"
        )
        cost = metrics["cost_estimate_usd"]
        print(f"  Cost estimate: ~${cost['total_usd']:.4f} total")


if __name__ == "__main__":
    main()