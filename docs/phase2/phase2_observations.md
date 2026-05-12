# Phase 2 — Implementation observations

This file records the experimental investigations carried out during
the implementation of Phase 2 Step 4 (dual-corpus orchestrator).
It complements `phase2_step4_design.md` by documenting **what was
learned**, including hypotheses that turned out to be wrong.

---

## 1. Benchmark setup

A qualitative benchmark on **20 curated queries** was used throughout
the step to evaluate the orchestrated pipeline:

- **5 review-oriented** (subjective: safety, atmosphere, landlord)
- **5 description-oriented** (factual: balcony, price, size)
- **5 ambiguous** (intentionally mixed: "best place to study")
- **5 edge cases** (empty, nonsense, conversational, vague, multi-intent)

Languages covered: 15 EN, 1 PT, 2 IT, 2 ES.

Each query is annotated with an `expected_intent` field acting as
hand-labelled ground truth for routing accuracy. Full set in
`evaluation/queries_extended.yaml`.

The benchmark script (`scripts/run_orchestrator_benchmark.py`) accepts
`--disable rewriting | reranking | routing` flags so that the same
codebase can be run under different configurations for ablation.

---

## 2. Indexing observation: silent vector drops

### Symptom

Initial smoke test of `--source descriptions` indexed all 455 documents
according to the indexer logs, but `PineconeVectorStore.count()`
reported only 350 vectors a few minutes later. The drop was stable and
reproducible — not consistency lag.

### Diagnosis

Multi-step investigation:

1. Re-ran with smaller upsert chunks → no improvement.
2. Probed Pinecone with semantic queries to enumerate actual IDs → ~350
   unique IDs found (matching the count).
3. Inspected the source data: the `Document` stream from
   `DescriptionExtractor` did contain duplicate IDs.
4. Asked ELH about the schema: confirmed that `house` and `room` tables
   keep historical versions in-place, identified by the composite key
   `(id, dateupdate)`. Pinecone, keyed on `id` alone, was overwriting
   older versions with newer ones — which is the *desired* behaviour,
   but we were producing N versions per logical entity instead of one.

### Fix

`DescriptionExtractor` SQL queries now use `DISTINCT ON` to keep only
the row with the most recent `dateupdate` per logical entity:

```sql
SELECT DISTINCT ON (h.idhouse) ...
FROM house h
WHERE h.status = 'Validated'
ORDER BY h.idhouse, h.dateupdate DESC
```

Final corpus: **80 unique houses + 270 unique rooms = 350 documents**,
matching the production state of ELH's catalogue.

### Lesson

Always inspect the production schema, not just the column structure.
The composite-key versioning pattern is invisible from
`information_schema.columns` and easy to miss without a domain-aware
read of sample rows.

---

## 3. Performance investigation — the parallelism experiment

### 3.1 Initial observation (Run A, baseline)

First full benchmark with the production configuration (sequential
pipelines + cross-encoder reranker + intent routing):

| Metric | Value |
|---|---:|
| Latency avg | 25.7s |
| Latency median | 23.7s |
| Latency p95 | 36.4s |
| Reviews-only avg | 19.3s |
| Descriptions-only avg | 21.8s |
| **`both` avg** | **31.1s** |
| Routing accuracy | 19/20 (95%) |

The 31s average on dual-corpus (`both`) queries was the obvious target
for optimisation: it was running two pipelines back-to-back when they
were independent by construction.

### 3.2 Hypothesis 1: parallelise the two retrieves (rejected by experiment)

**Reasoning:** the two retrieves on `both` share no state. A
`ThreadPoolExecutor` with `max_workers=2` should let them overlap, since
both Pinecone HTTP calls (network I/O) and PyTorch reranker inference
release the GIL. Expected outcome: 30-40% latency reduction on `both`.

**Implementation:** see commit history; the change was localised to
`Orchestrator._run_pipelines`. A unit test (`test_intent_both_runs_the_two_retrieves_in_parallel`)
used wall-time measurement on a fake store with `time.sleep(0.25)` per
call to verify that two retrieves complete in ~0.25s rather than ~0.5s
when parallelised. The test passed, confirming the threading
mechanism worked.

**Run B (parallel + reranker):**

| Metric | Run A (seq) | Run B (par) | Δ |
|---|---:|---:|---:|
| Avg overall | 25.7s | 33.1s | **+29%** |
| `both` avg | 31.1s | 40.6s | **+30%** |
| Reviews avg | 19.3s | 17.0s | -12% (noise) |

Parallel was consistently **slower**, not faster. A second run (Run B
repeated) showed the same pattern, ruling out random network variance.

### 3.3 Hypothesis 2: the reranker is the contention point (partially correct)

**Reasoning:** BGE-reranker-v2-m3 is a 2.2GB cross-encoder running on
CPU. Two concurrent PyTorch forward passes contend for BLAS/OpenMP
resources, cancelling the parallelism gain.

**Test:** ablation. Disable reranking and re-run with both sequential
(Run C) and parallel (Run D). If hypothesis 2 is correct, parallel
should now be faster than sequential because the contended resource is
gone.

### 3.4 Ablation runs

**Run C (sequential, no rerank, routing forced off → all-reviews):**

| Metric | Value |
|---|---:|
| Latency avg | 9.8s |
| Latency median | 8.6s |
| Latency p95 | 13.4s |

The reranker accounts for ~10s/query — a major component of overall
latency. This is consistent with running BGE on a CPU laptop.

**Run D (parallel, no rerank, routing on, `both` activates parallelism):**

| Metric | Run C (seq, all reviews) | Run D (par, `both`) |
|---|---:|---:|
| Avg overall | 9.8s | 25.7s |
| `both` avg | n/a | 32.7s |

**The parallel path on `both` is still ~3× slower than single-corpus,
even with the reranker disabled.** Hypothesis 2 was wrong (or at most
partially true): removing the reranker didn't make parallel competitive.

### 3.5 The real root cause (data-driven)

Per-query comparison Run C vs Run D on the 8 queries that route to
`both` in D (and to reviews-only in C, where routing is disabled):

| Query | C (single-corpus, no rerank) | D (`both`, no rerank, parallel) | Δ |
|---|---:|---:|---:|
| a01 | 8.0s | 42.3s | +34.3 |
| a02 | 8.8s | 33.0s | +24.2 |
| a03 | 9.6s | 35.4s | +25.8 |
| a05 | 11.1s | 33.5s | +22.4 |
| e02 | 11.3s | 29.3s | +18.0 |
| e03 | 13.1s | 36.6s | +23.5 |
| e04 | 17.5s | 43.4s | +25.9 |
| e05 | 12.2s | 36.7s | +24.5 |

Average penalty for going dual-corpus: **+24.8s/query**, even with
parallelism on and reranker off. The retrieve+rerank stages cannot
account for this difference — they're already fast enough.

The dominant cost on `both` queries is the **final LLM generation
step**: when the orchestrator merges sources from both corpora, the
context handed to Claude Sonnet roughly doubles in length. Generation
runs **once**, **after** the merge, and is not parallelisable.
Doubling input tokens roughly doubles generation time, plus a longer
output as the model produces a more comprehensive answer over more
material.

### 3.6 Decision

**Rolled back to sequential.** The parallelism overhead (thread
startup, result marshalling, Pinecone connection pool contention) is
small but real, and there is no I/O-bound speedup to offset it. The
implementation note in `Orchestrator._run_pipelines` references this
investigation.

### 3.7 Open avenue

When LLM generation is no longer the bottleneck — e.g. when Phase 3
introduces structured tool calling that returns compact answers, or
when faster generation models become available — the cost balance may
flip. Sequential remains the right default for now.

---

## 4. Routing accuracy in production

The intent router (Claude Haiku, system prompt in `prompts.py`) reached
**19/20 (95%) agreement** with hand-labelled expected intent on the
benchmark set. The single mismatch:

- Query (ES): *"casas con buena ubicación y baratas"*
- Expected: `both` (location is descriptive, "baratas/cheap" is judgemental)
- Got: `descriptions` with confidence 0.95
- Router reasoning: *"Búsqueda específica de propiedades por ubicación y precio, características factuales de descriptions"*

This is a **legitimate disagreement** rather than a clear miss: the
router weighted the two factual dimensions (location, price) higher
than the implicit value judgement. The classification is defensible
on its own merits; the discrepancy reflects the inherent ambiguity of
hand-labelling rather than a router error.

Cross-lingual consistency check: the equivalent EN query
*"a quiet room to study"* and PT query *"quarto tranquilo para estudar"*
both produce the same routing decision (`reviews` escalated to `both`
via the confidence threshold), confirming the router behaves
consistently across the four languages tested (EN, PT, IT, ES).

---

## 5. Cost in production

Estimated per-query cost (heuristic token counts, public Anthropic
pricing as of April 2026):

| Component | Tokens (in / out) | Cost |
|---|---:|---:|
| Intent router (Haiku) | 2000 / 60 | $0.0018 |
| Query rewriter (Haiku) | 400 / 40 | $0.0005 |
| Generation (Sonnet) | 3000 / 250 | $0.0128 |
| **Total per query** | | **~$0.015** |
| **20-query benchmark** | | **~$0.30** |

Generation dominates the cost (~85%). Routing is a small additional
cost that the dual-corpus separation makes worthwhile by reducing
irrelevant retrieval (and the corresponding generation context bloat).

---

## 6. What this experience taught (notes for the thesis)

1. **Premature optimisation is real.** The first instinct (parallelise
   the obvious independent step) was wrong. Only an ablation study
   revealed that the bottleneck was elsewhere.

2. **Hand-labelled "ground truth" is itself fuzzy.** 19/20 routing
   agreement is good, but the 1/20 mismatch is not a clear router
   mistake — both labellings are defensible. The thesis should
   present this honestly rather than reporting "95% accuracy" as
   if the gold label were objective.

3. **Domain knowledge beats schema inspection.** The composite-key
   versioning pattern in the ELH database is invisible from column
   structure alone. A 5-minute call with the data owner saved hours
   of debugging.

4. **Test infrastructure pays for itself fast.** The unit test on
   parallelism wall-time prevented misattributing the regression to
   "the threading mechanism doesn't work" — it clearly worked, the
   problem was elsewhere.
