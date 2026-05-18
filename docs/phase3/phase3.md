# Phase 3 — Agentic RAG

**Status:** Complete (closed 18 May 2026).
**Branch (now merged):** `feature/phase3-agent` → `develop`.
**Architecture:** Agentic RAG with LLM-driven multi-hop tool selection.

This document describes Phase 3 of the ELH thesis project: the
introduction of an autonomous agent loop that, on each iteration,
chooses among eight registered tools to answer the user's question.
It supersedes the Phase 2 design (intent router + dual semantic
paths), which is preserved in [`phase2_design.md`](phase2_design.md)
and [`phase2_observations.md`](phase2_observations.md). The
quantitative outcomes of the latency-optimisation step (Step 3.7)
are documented in [`phase3_outcomes.md`](phase3_outcomes.md).

---

## Table of contents

1. [Architectural definition](#1-architectural-definition)
2. [Agent loop](#2-agent-loop)
3. [The eight registered tools](#3-the-eight-registered-tools)
4. [Declarative `ctx_attr` — per-tool context resolution](#4-declarative-ctx_attr--per-tool-context-resolution)
5. [Multilingual support](#5-multilingual-support)
6. [Step-by-step progress](#6-step-by-step-progress)
7. [Final results](#7-final-results)

---

## 1. Architectural definition

The Phase 3 system is an **Agentic RAG**, not a Hybrid Tool-augmented
RAG and not a classical RAG pipeline. The distinction is operational:

| | Classical RAG | Hybrid Tool-augmented | **Agentic RAG (Phase 3)** |
|---|---|---|---|
| Number of LLM calls per query | 1 | 1 | **2–5** |
| Tool selection | none | pipeline-determined | **LLM-driven, per hop** |
| Multi-step reasoning | no | rare | **first-class** |
| Error recovery | external | external | **LLM-internal** |

In the Phase 3 system the model (Claude Sonnet 4.5 on the first hop;
Claude Haiku 4.5 on subsequent hops) receives the user query plus
the schemas of eight available tools, autonomously decides which
tool(s) to invoke, examines the JSON results, and either calls more
tools (multi-hop) or writes the final answer. Tools are deterministic
Python functions that wrap structured database queries or curated
knowledge base lookups; the LLM never produces raw SQL (a hard
constraint motivated by ELH's GDPR posture).

```
              Student question
                     │
                     ▼
            ┌────────────────────┐
            │  Input validation  │  ≤ settings.agent_max_query_chars
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
            │            └────────────────────┘          │
            └─────────┬──────────────────────────────────┘
                      ▼
            ┌────────────────────┐
            │  AgentResponse     │  final_message,
            │  (Pydantic frozen) │  tool_trace,
            └────────────────────┘  tokens, duration, ...
```

---

## 2. Agent loop

The entry point is `run_agent_turn(query, ctx, *, on_text=, on_tool_call=, llm=, synthesis_llm=)` in
`src/elh_rag/agent/loop.py`. The algorithm:

1. **Input validation** (D6.4): reject empty queries and queries longer
   than `settings.agent_max_query_chars` (default 4 000 chars) — a hard
   cap that protects against accidental cost runaway.
2. **Setup**: build the messages list with the user's query, the system
   prompt (~9 700 tokens including tool schemas attached by the SDK),
   the tool schemas array, and the model clients.
3. **Loop** for up to `settings.agent_max_hops` (default 5):
   1. Choose the active LLM client based on `hop_index` (Sonnet at
      hop 0, Haiku at hop ≥ 1 when the synthesis split is enabled —
      see §6 Step 3.7.3).
   2. Call the LLM (streaming if `on_text` is provided, plain call
      otherwise — D4.9).
   3. Aggregate token usage and emit a log line with cache statistics.
   4. If `stop_reason == "end_turn"`, extract the text and exit the
      loop.
   5. If `stop_reason == "tool_use"`, dispatch every tool_use block
      via `execute_tool`, build matching tool_result blocks, append
      the assistant message and the tool_result list to the
      conversation, and continue. Tool errors are passed through
      to the model with `is_error=True` (D4.8 — pass-through).
4. **Termination**: assemble an `AgentResponse` carrying the final
   message, the full `ToolCall` trace, aggregate token counts, total
   wall-clock duration, and `stop_reason` (`end_turn`,
   `max_hops_reached`, `error`, or `input_invalid`).

The loop is single-turn and stateless (D4.6): no conversation history
is preserved across turns. Multi-turn behaviour is the LLM's job
within the turn's message list; across turns the agent starts fresh.

---

## 3. The eight registered tools

| Tool | Category | What it does |
|---|---|---|
| `find_rooms` | DB structured | Filter rooms by city / price / amenities / metro proximity, ordered |
| `find_available_rooms` | DB structured | Same as `find_rooms` but constrained to a check-in/out window |
| `compute_total_cost` | DB structured | Full quote for one room + period: rent, 9% fee, deposits, utility caps, admin tax |
| `get_property_details` | DB structured | Detailed snapshot of one house or room incl. review aggregates |
| `get_booking_stats` | DB structured | Aggregate k-anonymous metrics (occupancy, top neighbourhoods, lead time) |
| `answer_policy_question` | KB | FAQ over 26 curated policy entries (cancellation, deposits, utilities, …) |
| `search_descriptions` | RAG semantic | Vector search over house + room descriptions (Pinecone `elh-descriptions`) |
| `search_reviews` | RAG semantic | Vector search over student reviews (Pinecone `elh-reviews`) |

Each tool is implemented as a Python function decorated with
`@register_tool(name, description, input_model, *, ctx_attr=...)` and
exposes a typed Pydantic `Input` model. The LLM only sees the JSON
schema derived from the `Input` model; it never produces SQL directly.
The dispatcher `execute_tool(name, payload, ctx)` validates the
payload against the model, dispatches the function, and normalises
errors into `ToolNotFoundError`, `ToolValidationError`, or
`ToolExecutionError` — all subclasses of `ToolError`, all caught by
the loop and returned to the LLM as `tool_result` blocks with
`is_error=True`.

The two RAG-corpora tools (`search_descriptions`, `search_reviews`)
wrap the Phase 2 retrieval pipelines (Pinecone vector search +
optional cross-encoder reranking, disabled in the Phase 3 default
configuration because the reranker showed weak score discrimination
on the small reviews corpus — see [`phase2_observations.md`](phase2_observations.md)).

---

## 4. Declarative `ctx_attr` — per-tool context resolution

Different tools expect different shapes of `ctx`:

* Tools 1–5 (`find_rooms` … `get_booking_stats`) expect a `DBExecutor`.
* Tool 6 (`answer_policy_question`) expects a `KBContext` (the
  in-memory knowledge base with 112 variant embeddings).
* The two RAG wrappers want the full `AgentContext` (they need the
  embedder *and* the relevant Pinecone vector store).

The Step 3.5 fix introduces a declarative resolution: each tool
declares which attribute of the `AgentContext` it needs via the
optional `ctx_attr` kwarg on `@register_tool`. The loop reads
`spec.ctx_attr` from the registry and calls
`getattr(agent_ctx, ctx_attr)` before invoking the tool. When
`ctx_attr` is `None` (default), the full `AgentContext` is forwarded.

```python
@register_tool(
    name="find_rooms",
    description="...",
    input_model=FindRoomsInput,
    ctx_attr="db",          # ← receives agent_ctx.db
)
def find_rooms(payload, ctx: DBExecutor) -> FindRoomsOutput:
    ...

@register_tool(
    name="answer_policy_question",
    description="...",
    input_model=AnswerPolicyQuestionInput,
    ctx_attr="kb",          # ← receives agent_ctx.kb
)
def answer_policy_question(payload, ctx: KBContext) -> ...:
    ...
```

This design is **Open/Closed**: adding a new tool only requires
adding `ctx_attr=...` in its decorator. The loop is never modified.
The know-how about what each tool needs lives co-located with the
tool itself, where it belongs architecturally. The dispatcher
`execute_tool` remains agnostic to `ctx_attr` and forwards whatever
`ctx` it receives, which preserves backwards compatibility with the
Phase 2/3 unit-test patterns that construct tools with mock `ctx`
objects directly.

---

## 5. Multilingual support

The user can write in English, Italian, Portuguese, Spanish, German,
or French; the agent's final answer is produced in the user's
language. This is achieved via:

* **Six few-shot examples in six languages** in the SYSTEM_PROMPT
  (decision D4.4): one each in EN (structural), IT (policy),
  PT (semantic), ES (multi-hop), DE (semantic), FR (period
  availability). The examples model both the reasoning and the
  expected answer language.
* **Multilingual embeddings** (`paraphrase-multilingual-mpnet-base-v2`)
  used by both Pinecone indexes and by the in-memory KB, so semantic
  search works regardless of the query language.
* **Multilingual reranker** (`BAAI/bge-reranker-v2-m3`, 100+ languages)
  available for the Phase 2 semantic-search wrappers when needed.

In the 20-query Step 3.7 benchmark, all four non-English queries
(IT, PT, ES, DE) succeeded with 100% tool routing accuracy and
produced answers in the user's language, replicating the Step 3.6
baseline.

---

## 6. Step-by-step progress

Phase 3 was split into seven incremental steps committed and tested
in isolation, each closed with green tests before moving on.

| Step | Scope | Tests added |
|---|---|---|
| 3.1 | Scaffold agent package layout aligned with codebase style | 0 |
| 3.2 | `AgentLLMClient` with tenacity retry on transients + streaming | +17 |
| 3.3 | Tool registry, RAG corpora wrappers, dispatcher | +25 |
| 3.4 | `AgentContext` + multilingual SYSTEM_PROMPT with 6 few-shot examples | +11 |
| 3.5 | `run_agent_turn` loop + `AgentResponse`/`ToolCall` models + declarative `ctx_attr` | +26 |
| 3.6 | 20-query benchmark + analyser + Excel template for Tier-2 human eval | 0 |
| 3.7 | Latency optimisations: prompt caching + anti-repetition rule + dual-model dispatch | +8 |

Test count grew from 723 (Phase 2.5 close) to 852 (+129 across
Phase 3); all tests run offline in under 5 seconds with zero API
calls.

### Step 3.7 — latency optimisations

The 20-query benchmark of Step 3.6 ran with a median wall-clock of
~50 s per query, dominated by Anthropic API rate-limit retries and
by repeated processing of the 9 700-token system prompt on every
hop. The ELH team flagged this as "too high for an interactive
demo". Three optimisations were applied:

* **3.7.1 Prompt caching** — `AgentLLMClient` wraps the system prompt
  in a single `cache_control: ephemeral` content block. The first
  call in a 5-minute window writes the cache; subsequent calls read
  it at 10% of the standard input price. Implementation is internal
  to the client; `loop.py` continues to pass `system: str` and is
  unchanged.
* **3.7.2 Anti-repetition rule** — routing rule 7 in the SYSTEM_PROMPT
  was strengthened to forbid consecutive same-tool calls chasing a
  "better" answer (the pattern observed in `policy_03`, where the
  model issued three `answer_policy_question` reformulations before
  falling back to semantic search).
* **3.7.3 Dual-model dispatch** — the loop now uses Claude Sonnet 4.5
  for hop 0 (where routing-quality matters most) and Claude
  Haiku 4.5 for hop ≥ 1 (synthesis and follow-up tool calls). Haiku
  delivers ~90% of Sonnet's agentic performance at 4–5× the speed
  (Anthropic, October 2025). The split is observable in the run logs
  and disable-able via the `agent_use_haiku_synthesis` setting.

---

## 7. Final results

A second run of the 20-query benchmark on 18 May 2026, identical
methodology to the baseline, with the three Step 3.7 optimisations
applied between runs:

| Metric | Before (Step 3.6) | After (Step 3.7) | Δ |
|---|---|---|---|
| Success rate | 100% (20/20) | 100% (20/20) | = |
| Tool routing coverage | 100% (20/20) | 100% (20/20) | = |
| Latency average | 50.8 s | **9.5 s** | **−81%** |
| Latency p50 | 49.6 s | 8.9 s | −82% |
| Latency p95 | 69.5 s | 14.0 s | −80% |
| Latency max | 111.6 s | 14.5 s | −87% |
| Tokens in (total) | 538 725 | 60 756 | −89% |
| Cost total | $1.81 USD | $0.37 USD | −80% |

**The ELH operational target of "under 30 s" is met with margin: the
worst-case wall-clock is 14.5 s, average 9.5 s.** Coverage is
preserved across every category (structural, policy, cost, semantic,
multilingual) and every language tested (EN, IT, PT, ES, DE).

A Tier-2 qualitative evaluation by an ELH domain expert is in
progress: a 1–10 correctness/completeness scoring of all 20
post-optimisation answers in
`benchmarks/human_eval/human_eval_2026-05-18-172004.xlsx`.

The full breakdown — per-category latency, per-language statistics,
the `policy_03` outlier analysis — lives in
[`phase3_outcomes.md`](phase3_outcomes.md). The raw run data is
preserved as JSONL under `benchmarks/runs/` for both runs.
