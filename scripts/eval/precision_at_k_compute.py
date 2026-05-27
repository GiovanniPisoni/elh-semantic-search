"""Compute Precision@K / Recall@K / F1@K for the two semantic RAG tools.

Loads:
    * ``benchmarks/queries/precision_at_k_queries.yaml`` — with manually
      filled ``relevant_source_ids`` per query (the ground truth).
    * ``benchmarks/runs/precision_at_k_candidates.jsonl`` — the top-10
      candidates per query produced by ``precision_at_k_extract.py``.

Computes per-query Precision@K, Recall@K, F1@K (with K =
``top_k_evaluate``, default 5) and aggregates by corpus and overall.

Writes the report to ``benchmarks/reports/precision_at_k_semantic.md``.

Usage::

    python -m scripts.eval.precision_at_k_compute
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

logger = logging.getLogger(__name__)


DEFAULT_QUERIES_FILE = Path("benchmarks/queries/precision_at_k_queries.yaml")
DEFAULT_CANDIDATES_FILE = Path("benchmarks/runs/precision_at_k_candidates.jsonl")
DEFAULT_REPORT_FILE = Path("benchmarks/reports/precision_at_k_semantic.md")


@dataclass(frozen=True)
class QueryGold:
    """One row of ground truth from the YAML file."""

    id: str
    query: str
    tool: str
    top_k_evaluate: int
    relevant_source_ids: list[str]


@dataclass(frozen=True)
class QueryResult:
    """Per-query computed metrics."""

    id: str
    query: str
    tool: str
    corpus: str
    k: int
    relevant_total: int
    retrieved_relevant: int
    precision: float
    recall: float
    f1: float


def load_gold(path: Path) -> dict[str, QueryGold]:
    """Load YAML and index by query id."""
    if not path.exists():
        raise FileNotFoundError(f"Queries file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict) or "queries" not in raw:
        raise ValueError(f"Invalid YAML schema: top-level key 'queries' required in {path}")
    out: dict[str, QueryGold] = {}
    for q in raw["queries"]:
        gold = QueryGold(
            id=q["id"],
            query=q["query"],
            tool=q["tool"],
            top_k_evaluate=int(q.get("top_k_evaluate", 5)),
            relevant_source_ids=[
                str(rid).strip() for rid in (q.get("relevant_source_ids") or [])
            ],
        )
        out[gold.id] = gold
    return out


def load_candidates(path: Path) -> dict[str, dict[str, Any]]:
    """Load candidates JSONL and index by query id."""
    if not path.exists():
        raise FileNotFoundError(
            f"Candidates file not found: {path}. "
            "Run scripts/eval/precision_at_k_extract.py first."
        )
    out: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            for cand in rec.get("candidates", []):
                if "source_id" in cand:
                    cand["source_id"] = str(cand["source_id"]).strip()
            out[rec["id"]] = rec
    return out


def _safe_div(num: float, den: float) -> float:
    return num / den if den > 0 else 0.0


def compute_metrics(gold: QueryGold, candidate_record: dict[str, Any]) -> QueryResult:
    """Compute Precision@K, Recall@K, F1@K for a single query."""
    k = gold.top_k_evaluate
    # Normalize whitespace on both sides: some corpus source_ids are stored
    # padded with trailing spaces, which breaks string equality against the
    # un-padded ids written into the YAML by the annotator.
    relevant_set = {rid.strip() for rid in gold.relevant_source_ids}
    relevant_total = len(relevant_set)

    candidates = candidate_record.get("candidates", [])
    top_k_ids = [str(c["source_id"]).strip() for c in candidates[:k]]
    retrieved_relevant = sum(1 for sid in top_k_ids if sid in relevant_set)

    precision = _safe_div(retrieved_relevant, k)
    recall = _safe_div(retrieved_relevant, relevant_total)
    f1 = _safe_div(2 * precision * recall, precision + recall)

    return QueryResult(
        id=gold.id,
        query=gold.query,
        tool=gold.tool,
        corpus=candidate_record.get("corpus", "?"),
        k=k,
        relevant_total=relevant_total,
        retrieved_relevant=retrieved_relevant,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def _truncate_query(query: str, limit: int = 70) -> str:
    if len(query) <= limit:
        return query
    return query[:limit].rstrip() + "..."


def _aggregate(results: list[QueryResult]) -> tuple[float, float, float]:
    """Mean P, R, F1 across a list of results. Returns (0, 0, 0) if empty."""
    if not results:
        return (0.0, 0.0, 0.0)
    return (
        mean(r.precision for r in results),
        mean(r.recall for r in results),
        mean(r.f1 for r in results),
    )


def render_report(results: list[QueryResult]) -> str:
    """Render the Markdown report."""
    if not results:
        return "# Precision@K — Semantic RAG\n\nNo results to report.\n"

    k_values = {r.k for r in results}
    k_label = (
        f"@{next(iter(k_values))}" if len(k_values) == 1 else "@K (varies; see per-query)"
    )

    by_corpus: dict[str, list[QueryResult]] = {}
    for r in results:
        by_corpus.setdefault(r.corpus, []).append(r)

    lines: list[str] = []
    lines.append("# Precision@K — Semantic RAG micro-benchmark")
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "We evaluate the two semantic RAG tools (`search_descriptions` and "
        "`search_reviews`) on a hand-curated set of 10 English queries (5 per "
        "tool), each clearly addressable by exactly one corpus. For each query "
        "we extract the top-10 candidate chunks from Pinecone with "
        "`top_k=10`, then a single human annotator (Giovanni) marks which of "
        "those chunks genuinely answer the query. The annotated IDs are stored "
        "in `benchmarks/queries/precision_at_k_queries.yaml` under "
        "`relevant_source_ids`."
    )
    lines.append("")
    lines.append(
        f"We then compute Precision{k_label}, Recall{k_label} and F1{k_label} "
        "per query, restricting the retrieved set to the top-K hits (K = "
        "`top_k_evaluate`, default 5). Precision is "
        "`|retrieved ∩ relevant| / K`; recall is "
        "`|retrieved ∩ relevant| / |relevant|`; F1 is the harmonic mean. "
        "The ground truth is bounded to the union of the 10 extracted "
        "candidates — chunks that exist in the corpus but never appear in the "
        "top-10 cannot be marked relevant, so recall is an optimistic estimate."
    )
    lines.append("")

    lines.append("## Per-query results")
    lines.append("")
    lines.append("| id | query | corpus | K | rel. (in top-10) | hits | P@K | R@K | F1@K |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        q_short = _truncate_query(r.query).replace("|", "\\|")
        lines.append(
            f"| {r.id} | {q_short} | {r.corpus} | {r.k} | "
            f"{r.relevant_total} | {r.retrieved_relevant} | "
            f"{r.precision:.2f} | {r.recall:.2f} | {r.f1:.2f} |"
        )
    lines.append("")

    lines.append("## Aggregate")
    lines.append("")
    lines.append("| scope | n queries | mean P@K | mean R@K | mean F1@K |")
    lines.append("|---|---|---|---|---|")
    for corpus in sorted(by_corpus):
        group = by_corpus[corpus]
        p, r, f1 = _aggregate(group)
        lines.append(
            f"| corpus: {corpus} | {len(group)} | {p:.2f} | {r:.2f} | {f1:.2f} |"
        )
    p_all, r_all, f1_all = _aggregate(results)
    lines.append(
        f"| overall | {len(results)} | {p_all:.2f} | {r_all:.2f} | {f1_all:.2f} |"
    )
    lines.append("")

    lines.append("## Caveats")
    lines.append("")
    lines.append(
        "- **Small sample size.** 10 queries (5 per tool) is enough to spot "
        "obvious retrieval failures but cannot ground statistical claims; "
        "treat numbers as indicative only."
    )
    lines.append(
        "- **Single annotator.** Ground truth comes from one human (Giovanni). "
        "Inter-annotator agreement is not measured, and subjective queries "
        "(\"quiet at night\", \"friendly housemates\") inherit the annotator's "
        "interpretation of relevance."
    )
    lines.append(
        "- **Bounded recall.** Relevant IDs are picked from the top-10 returned "
        "by the system, so Recall@K cannot detect relevant chunks that the "
        "embedder ranks below position 10 — recall numbers are an upper bound."
    )
    lines.append(
        "- **English only.** This micro-benchmark does not exercise the "
        "multilingual paths of the semantic tools."
    )
    lines.append("")

    lines.append("## Interpretation")
    lines.append("")
    if f1_all >= 0.6:
        lines.append(
            f"Overall mean F1@K = {f1_all:.2f}: semantic retrieval comfortably "
            "places relevant chunks within the top-K for most queries in this "
            "set. Per-corpus differences below highlight where the embedder "
            "struggles more."
        )
    elif f1_all >= 0.3:
        lines.append(
            f"Overall mean F1@K = {f1_all:.2f}: semantic retrieval surfaces "
            "some but not most relevant chunks within K; per-query failures "
            "are worth inspecting before relying on the top-K cutoff for "
            "downstream answers."
        )
    else:
        lines.append(
            f"Overall mean F1@K = {f1_all:.2f}: top-K retrieval is weak on this "
            "set; review failing queries and consider rerank, chunking, or "
            "embedding-model adjustments."
        )
    lines.append("")
    return "\n".join(lines)


def write_report(content: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    tmp.replace(output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queries",
        type=Path,
        default=DEFAULT_QUERIES_FILE,
        help=f"YAML query file with ground truth (default: {DEFAULT_QUERIES_FILE}).",
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=DEFAULT_CANDIDATES_FILE,
        help=f"Candidates JSONL (default: {DEFAULT_CANDIDATES_FILE}).",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT_FILE,
        help=f"Output report Markdown path (default: {DEFAULT_REPORT_FILE}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gold = load_gold(args.queries)
    candidates = load_candidates(args.candidates)

    results: list[QueryResult] = []
    skipped: list[str] = []
    for qid, g in gold.items():
        cand = candidates.get(qid)
        if cand is None:
            skipped.append(qid)
            logger.warning("query %r missing from candidates file — skipping", qid)
            continue
        if not g.relevant_source_ids:
            skipped.append(qid)
            logger.warning(
                "query %r has empty relevant_source_ids — annotate it before computing",
                qid,
            )
            continue
        results.append(compute_metrics(g, cand))

    if skipped:
        print(f"WARNING: skipped {len(skipped)} unannotated/missing queries: {skipped}")

    if not results:
        print(
            "ERROR: no annotated queries found. Fill relevant_source_ids in "
            f"{args.queries} and rerun."
        )
        return 1

    report_md = render_report(results)
    write_report(report_md, args.report)

    p_all, r_all, f1_all = _aggregate(results)
    print(f"Computed metrics for {len(results)} queries.")
    print(f"  overall mean P@K = {p_all:.2f}")
    print(f"  overall mean R@K = {r_all:.2f}")
    print(f"  overall mean F1@K = {f1_all:.2f}")
    print(f"Report written to: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
