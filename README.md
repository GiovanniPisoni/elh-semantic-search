# ELH Semantic Search

> Master's Thesis · Alma Mater Studiorum Università di Bologna
> Supervisor: Prof. Enrico Gallinucci

An **Agentic RAG** system that lets students query Erasmus Life Housing's
data (operational database, property descriptions, and student reviews)
in natural language. An LLM-driven agent autonomously selects among
eight registered tools — six structured DB tools, one curated knowledge
base, and two semantic-search wrappers — and chains them across multiple
hops to deliver grounded answers in any of six languages.

---

## Context

**Erasmus Life Housing (ELH)** operates a student accommodation platform
in Lisbon and Porto. Their database has two complementary worlds: a
structured catalogue (rooms, prices, amenities, availability) and a
body of unstructured text (student reviews, property descriptions).

Standard SQL filters serve the structured side well but cannot capture
concepts like *"quiet area"* or *"responsive landlord"* that exist only
in free text. Conversely, factual questions about prices or availability
cannot be answered from text alone. Real-world questions typically need
both: subjective signals from past tenants *and* hard facts from the
catalogue.

This system bridges the two: an LLM agent chooses between deterministic
SQL tools (for facts) and semantic retrieval (for opinions), and synthesises
a single grounded answer.

## What you can ask

```
"Find the cheapest single rooms in Lisbon"                  → structural
"What is the cancellation policy if I cancel 45 days early?" → policy
"Total cost for a 6-month stay starting September 2026"      → multi-hop
"Is the Alfama neighborhood quiet at night?"                 → semantic
"Quartos com varanda em Lisboa para setembro de 2026"        → multilingual (PT)
```

The system supports English, Italian, Portuguese, Spanish, German, and
French. The agent detects the user's language and answers in the same
language. Tool inputs remain in canonical form (city names like "Lisbon",
ISO dates like `2026-09-01`).

## Architecture

```
              Student question
                     │
                     ▼
            ┌────────────────────┐
            │  Input validation  │  ≤ 4 000 chars (hard cap)
            └─────────┬──────────┘
                      ▼
            ┌────────────────────────────────────────────┐
            │           run_agent_turn  (loop)           │
            │                                            │
            │   hop 0:  Claude Sonnet 4.5  (routing)     │
            │   hop ≥1: Claude Haiku 4.5  (synthesis +   │
            │                              follow-up)    │
            │                                            │
            │   max_hops = 5     prompt caching enabled  │
            │                                            │
            │            ┌────────────────────┐          │
            │            │   TOOLS_REGISTRY   │          │
            │            │      8 tools       │          │
            │            └─────────┬──────────┘          │
            └──────────────────────┼─────────────────────┘
                                   │
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
        ┌────────────┐    ┌────────────┐    ┌──────────────┐
        │ PostgreSQL │    │  KBContext │    │   Pinecone   │
        │  (rooms,   │    │ (26 policy │    │ (descriptions │
        │ houses, …) │    │  entries)  │    │  + reviews)  │
        └────────────┘    └────────────┘    └──────────────┘
```

**The eight tools** are: `find_rooms`, `find_available_rooms`,
`compute_total_cost`, `get_property_details`, `get_booking_stats`
(structured DB), `answer_policy_question` (knowledge base),
`search_descriptions`, `search_reviews` (semantic RAG over Pinecone).

Each tool is a Python function with a Pydantic input schema. The LLM
only sees the JSON schema and decides which tool to invoke — it never
writes SQL.

## Key design choices

**Agentic, not pipelined.** Earlier phases used a fixed pipeline
(intent router → semantic retrieval → generator). Phase 3 replaces this
with an LLM-driven loop that decides each hop autonomously based on
prior tool results. This enables multi-hop reasoning — e.g.
*"find the cheapest room in Lisbon AND compute its 6-month cost"*
naturally produces two chained tool calls.

**Declarative `ctx_attr`.** Each tool declares which sub-context it
needs via `@register_tool(..., ctx_attr="db" | "kb" | None)`. The loop
reads this metadata and passes the right resource. Adding a new tool
means adding one keyword in its decorator; the loop never changes.

**Dual-model dispatch for latency.** Sonnet 4.5 handles hop 0 where
routing quality matters; Haiku 4.5 (~5× faster) handles synthesis and
follow-up hops. Combined with Anthropic prompt caching on the 9 700-token
system prompt, the median per-query latency dropped from 50 s to 9 s
without any drop in tool routing coverage.

**Graceful degradation.** Tool errors are surfaced to the LLM as
`tool_result` blocks with `is_error=True`; the model decides whether to
retry with different parameters, fall back to a different tool, or
explain the failure to the user. The loop never crashes a turn.

## Performance

Measured on a 20-query benchmark spanning five categories (structural,
policy, multi-hop cost, semantic, multilingual) and five languages:

| Metric | Value |
|---|---|
| Success rate | 100% (20/20) |
| Tool routing coverage | 100% |
| Latency average | 9.5 s |
| Latency p95 | 14.0 s |
| Latency worst case | 14.5 s |
| Cost per full benchmark | $0.37 USD |

Full methodology, before/after comparison vs the pre-optimisation
baseline, and per-category breakdown are documented in
[`docs/phase3_outcomes.md`](docs/phase3_outcomes.md). Raw run data is
preserved as JSONL under `benchmarks/runs/`.

## Tech stack

| Component | Choice |
|---|---|
| Language | Python 3.12 |
| Primary LLM (routing) | Anthropic Claude Sonnet 4.5 |
| Synthesis LLM (hop ≥ 1) | Anthropic Claude Haiku 4.5 |
| Embeddings | `paraphrase-multilingual-mpnet-base-v2` (768-dim) |
| Reranker | `BAAI/bge-reranker-v2-m3` (100+ languages) |
| Vector store | Pinecone (serverless, two indices) |
| Database | PostgreSQL (Supabase) |
| Validation | Pydantic v2 (settings + tool input schemas) |
| Retry / resilience | tenacity (exponential backoff on transient errors) |
| Tests | pytest, 852 tests, offline, < 5 s |
| Reporting | openpyxl (human eval Excel templates) |

## Setup

```bash
git clone <repo-url>
cd elh-semantic-search
python -m venv .venv && source .venv/bin/activate
make install

cp .env.example .env       # fill DB_URI, PINECONE_API_KEY, ANTHROPIC_API_KEY

python -m scripts.run_indexer --source all   # builds both Pinecone indices
make app                                     # opens Streamlit at :8501
```

Pinecone indices must be created beforehand on the dashboard with
**dimension 768** and **cosine** similarity (`elh-reviews` and
`elh-descriptions`).

## Development

```bash
make test         # full suite, no network, no API keys needed
make test-cov     # with coverage
make lint         # ruff
make format       # ruff + autofix
```

## Benchmark and human evaluation

```bash
# Run the 20-query benchmark against live services (~$0.40)
python -m scripts.benchmarks.run_agent_benchmark

# Generate the markdown report
python -m scripts.benchmarks.analyze_agent_benchmark

# Generate the Excel template for domain-expert evaluation
python -m scripts.benchmarks.generate_human_eval_excel
```

Use `--dry-run` on `run_agent_benchmark` for a 3-query smoke (~$0.05)
before committing to a full run. Outputs land under `benchmarks/runs/`,
`benchmarks/reports/`, and `benchmarks/human_eval/` respectively, all
timestamped for reproducibility.

---

**Author:** Giovanni Pisoni — *Alma Mater Studiorum Università di Bologna*
**Supervisor:** Prof. Enrico Gallinucci

*Developed for academic purposes. Private repository, not for distribution.*
