# Evaluation

This directory contains evaluation artifacts for the ELH RAG system.

## Current state (Phase 2)

### `queries.yaml`

A curated set of **15 test queries** covering a range of question types:

- **Conversational** (long, verbose, natural language)
- **Short/direct** (keyword-like)
- **Abstract concepts** ("feels like home")
- **Specific amenities** (WiFi, bed comfort, desk)
- **Negative sentiment** (complaints, issues)
- **Multilingual** (EN, PT, IT, ES — reflecting the Erasmus demographic)
- **Factual constraints** (specific cities, neighbourhoods)

This file is the **seed** for the full golden dataset that will be built
in Phase 4, Step 1.

### `run_qualitative_benchmark.py`

Runs the 15 test queries through three pipeline configurations:

1. **Naive** — Phase 1 baseline (no rewriting, no reranking)
2. **+Rewrite** — Phase 2, Step 1 only
3. **+Rewrite+Rerank** — Phase 2, Steps 1 and 2

For each (query, configuration) combination, the script records:

- Latency (wall-clock time, per-configuration)
- Mode label (from `RAGResponse.mode`)
- Rewritten query (when applicable)
- Top-5 retrieved sources with both vector and rerank scores
- Generated answer

Outputs two files into this directory:

- `qualitative_results_<timestamp>.jsonl` — machine-readable raw data
- `qualitative_report_<timestamp>.md` — human-readable report for review

Usage:

```bash
# Full benchmark (15 queries × 3 configurations = 45 pipeline executions)
python -m scripts.run_qualitative_benchmark

# Quick smoke test on the first 3 queries
python -m scripts.run_qualitative_benchmark --limit 3
```

## Methodological note

This is a **qualitative** benchmark, not a rigorous quantitative
evaluation. Without a ground-truth labelled dataset we cannot report
precision@k, recall@k, or RAGAS metrics — those belong to **Phase 4**.

What this benchmark *does* provide:

- **Side-by-side comparison** of the same queries across three
  configurations, useful for demoing system behaviour to supervisors
  and stakeholders.
- **Observables** (latency, reshuffling rate, rewriting activity) that
  characterise how the system operates without making accuracy claims.
- **Concrete examples** of rewriting and reranking effects that can be
  cited in the thesis "Qualitative Analysis" chapter.

## Future state (Phase 4)

Planned contents:

- `golden_set.jsonl` — expanded query set with ground-truth labels
  (relevant reviews for each query, expected answer notes)
- `run_evaluation.py` — rigorous evaluation with:
  - Retrieval metrics: precision@k, recall@k
  - Generation metrics: RAGAS faithfulness, answer relevance
  - A/B comparison: Naive vs Advanced (with statistical significance)
- `evaluation_report_<timestamp>.md` — publication-quality report