# ELH AI Assistant — Technical Documentation

> Version 3.0.0 · Phase 3 release (Agentic RAG)
> For the ELH technical team

This document explains how to run, operate, integrate, and extend the ELH AI assistant in production. It is meant as a handover from the thesis author to the ELH technical team, and assumes basic familiarity with Python but no prior knowledge of the codebase.

> **Note on the deployment context.** This system was developed against a deployment database built by Giovanni Pisoni and Giovanni Rinchiuso after the domain analysis phase, not against the ELH production database. The schema and data on the production side may differ from what is described here, and some aspects may need to be handled differently when integrated into the live ELH stack.

> **Scope of this document.** This documentation covers the backend Python system: installation, operations, architecture, and extension. Frontend integration (wiring the assistant into the ELH website) is intentionally left out — that is part of a future adaptation by the ELH technical team and depends on production-side choices that fall outside the scope of this thesis work.

---

## Table of contents

1. [What the system does](#1-what-the-system-does)
2. [Quick start — first install](#2-quick-start--first-install)
3. [Day-to-day operations](#3-day-to-day-operations)
4. [Architecture overview](#4-architecture-overview)
5. [Conversation memory](#5-conversation-memory)
6. [Changing the LLM provider](#6-changing-the-llm-provider)
7. [Monitoring costs](#7-monitoring-costs)
8. [Known limitations and how to extend](#8-known-limitations-and-how-to-extend)
9. [Appendix — useful commands](#9-appendix--useful-commands)

---

## 1. What the system does

The ELH AI assistant answers natural-language questions from students about housing, in any of six languages (English, Italian, Portuguese, Spanish, German, French). It does so by combining the ELH operational database with the body of student reviews and property descriptions in a single conversational interface.

### What it can answer

| Type of question | Example | Tool used |
|---|---|---|
| Catalogue filtering | *"Find single rooms under €600 in Lisbon"* | `find_rooms` |
| Availability checks | *"Rooms available from September to February in Porto"* | `find_available_rooms` |
| Cost calculations | *"Total cost for a 6-month stay starting September 2026"* | `compute_total_cost` |
| Property details | *"Tell me everything about room X"* | `get_property_details` |
| Aggregate stats | *"What is the most popular neighbourhood?"* | `get_booking_stats` |
| Policy questions | *"What is included in the monthly rent?"* | `answer_policy_question` |
| Semantic search on reviews | *"Is the Alfama neighbourhood quiet at night?"* | `search_reviews` |
| Semantic search on descriptions | *"Show me cozy apartments near the beach"* | `search_descriptions` |

The assistant decides autonomously which tool to call for each question, and can chain multiple tools together for complex queries (e.g. *"Find the cheapest single room in Lisbon and compute the total cost for 6 months"* triggers `find_rooms` followed by `compute_total_cost`).

### What it deliberately does not do

* **It does not write SQL.** All database access goes through eight Python functions with strict input validation (Pydantic schemas). The LLM only chooses which function to call and with what arguments. This is a hard architectural boundary motivated by GDPR posture and prompt-injection safety.
* **It does not modify data.** All eight tools are read-only. The assistant cannot create, update, or delete bookings, listings, or any other records.
* **It does not invent information.** Every factual claim comes from a real database row or a real review text. When no relevant data exists, the assistant says so explicitly rather than fabricating.

### Performance baseline

Measured on a 20-question benchmark spanning all eight tools and five languages (after the post-evaluation fixes of May 2026):

| Metric | Value |
|---|---|
| Success rate (any answer produced) | 100% (20/20) |
| Tool routing accuracy | 100% (correct tool always selected) |
| Average response time | 9.6 seconds |
| Worst-case response time | 12.6 seconds |
| Cost per question (mixed) | ~$0.018 USD |
| Cost per full benchmark run | $0.37 USD |

The latency is dominated by the LLM provider (Anthropic) calls. Optimisations applied: prompt caching (90% input-token discount on repeated calls within 5 minutes), and a dual-model split — Claude Sonnet 4.5 for the first reasoning step, Claude Haiku 4.5 (about 5× faster) for follow-up steps.

---

## 2. Quick start — first install

This section covers a clean install on a fresh machine. The system has been tested on Windows 11 and Ubuntu 24.04, with Python 3.12.

### Prerequisites

* Python 3.12 (any patch version)
* Git
* Network access to Anthropic, Pinecone, and Supabase
* An Anthropic API key (https://console.anthropic.com)
* A Pinecone account with API key (https://app.pinecone.io)
* The ELH Supabase Postgres connection string

### Step 1 — Clone and create the virtual environment

```bash
git clone https://github.com/GiovanniPisoni/elh-semantic-search.git
cd elh-semantic-search
git checkout v3.0.0-agentic-rag   # or whichever release you want to deploy

python -m venv venv
source venv/bin/activate          # Linux / macOS
# .\venv\Scripts\activate         # Windows PowerShell
```

### Step 2 — Install dependencies

```bash
pip install -r requirements.txt
pip install -e .
```

The first `pip install` takes 2–4 minutes because it includes PyTorch and sentence-transformers, which are needed for the multilingual embedder.

### Step 3 — Configure environment variables

Copy the template and fill in the three secrets:

```bash
cp .env.example .env
```

Edit `.env` with your editor of choice:

```env
# Database (ELH Supabase)
DB_URI=postgresql://USER:PASSWORD@HOST:5432/postgres

# Pinecone (vector store)
PINECONE_API_KEY=pcsk-...

# Anthropic (LLM)
ANTHROPIC_API_KEY=sk-ant-...
```

All other variables in `.env.example` have sensible defaults and can be left as-is for a first deployment.

### Step 4 — Create the two Pinecone indexes

The system uses two separate Pinecone indexes:

* `elh-reviews` — student reviews (~1 100 documents)
* `elh-descriptions` — house and room descriptions (~350 documents)

Both must be created in the Pinecone dashboard with:

* **Dimension**: 768
* **Metric**: cosine
* **Cloud**: any region close to your AWS deployment (e.g. `us-east-1` or `eu-west-1`)

If you do the login with the ELH e-mail you will already find the two correct Pinecone indexes.

### Step 5 — Build the indexes from the database

The first time, run the indexing pipeline to populate both Pinecone indexes from the Supabase data:

```bash
python -m scripts.run_indexer --source all
```

This takes 5–10 minutes on a first run (depending on database size) and pulls all reviews and descriptions from Supabase, embeds them with the multilingual model, and uploads vectors to Pinecone.

### Step 6 — Verify the install

Run the offline test suite to confirm the package imports correctly and all internal logic works:

```bash
pytest tests/ -q
```

Expected output: `895 passed in <5s`. No API keys or network needed — the tests are fully mocked.

Then run a single live query against the agent to confirm Anthropic and Pinecone are reachable:

```bash
python -m scripts.smoke_tests.smoke_test_agent
```

Expected output: a printed answer in 5–15 seconds.

If both pass, the system is operational.

---

## 3. Day-to-day operations

This section covers the recurring tasks the ELH team will perform: updating indexes when new reviews arrive, monitoring system health, and adjusting configuration.

### Re-indexing after new reviews

The Pinecone indexes are built offline from the Supabase database and do not auto-refresh. When new reviews are added, the embeddings must be regenerated and re-uploaded.

**Recommended frequency**: weekly during high season, monthly otherwise.

The same `scripts/run_indexer.py` script handles incremental updates. There are two strategies:

**Full rebuild** (safe, slower, idempotent):

```bash
python -m scripts.run_indexer --source reviews
python -m scripts.run_indexer --source descriptions
```

Each invocation drops and rebuilds the relevant index. Takes 3–6 minutes per index.

**Incremental update** (faster, more complex):

If your review volume is high, consider a custom script that:

1. Queries Supabase for reviews added since the last run (using `created_at > last_run_timestamp`).
2. Embeds only the new texts.
3. Calls `index.upsert(vectors)` on the Pinecone index.

A starter template is in `scripts/run_indexer.py`. The team can adapt it as needed.

### Configuration that is safe to change

The file `src/elh_rag/config.py` contains all tunable settings. The ones most likely to matter operationally:

| Setting | Default | Effect |
|---|---|---|
| `agent_llm_model` | `claude-sonnet-4-5` | Primary model (hop 0, routing decisions) |
| `agent_synthesis_model` | `claude-haiku-4-5-20251001` | Secondary model (hop 1+, answer writing) |
| `agent_use_haiku_synthesis` | `True` | Kill-switch — set to `False` to use Sonnet for all hops (slower, more expensive, marginally higher quality) |
| `agent_max_hops` | `5` | Hard cap on reasoning steps. Lower = faster but may truncate complex queries; higher = more flexibility |
| `agent_max_query_chars` | `4000` | Reject queries longer than this. Prevents runaway costs from accidental copy-pasted documents |
| `agent_max_history_turns` | `10` | Hard cap on conversation history accepted from the client (see §5). Requests with more turns are rejected |
| `agent_llm_max_tokens` | `4096` | Max tokens in each LLM response. Increase if you see truncated answers |
| `agent_llm_temperature` | `0.0` | Determinism. Higher = more variation. Keep at 0 unless you need creative answers |

To change any of these in production, set the corresponding environment variable in `.env` (the lowercase Pydantic name uppercased), for example:

```env
AGENT_MAX_HOPS=8
AGENT_USE_HAIKU_SYNTHESIS=False
```

No code change or redeploy needed — just restart the process.

### Logs to watch in production

The system uses Python's standard `logging` module at `INFO` level by default. Three log lines are particularly informative:

1. **Model selection per hop** (per query):
   ```
   agent.loop: hop=0 using model=claude-sonnet-4-5
   agent.loop: hop=1 using model=claude-haiku-4-5-20251001
   ```
   Confirms the dual-model split is active.

2. **Cache usage** (per LLM call):
   ```
   agent.llm: cache_creation=9712, cache_read=0, input=333, output=96
   agent.llm: cache_creation=0, cache_read=9712, input=337, output=139
   ```
   `cache_read > 0` means prompt caching is working. If you see `cache_creation` on every call and never `cache_read`, the cache is not being hit (could indicate a long gap between requests, the 5-minute TTL has expired, or a config issue).

3. **Tool routing**:
   ```
   tool.dispatch: name=find_rooms, hop=0
   tool.execute: name=find_rooms, latency=180ms, ok=True
   ```
   Useful for tracing user complaints back to specific failed queries.

In production, pipe logs to a structured logging service (CloudWatch on AWS, Datadog, etc.) and set up alerts on:
* High rate of `tool.execute: ok=False`
* Sustained absence of `cache_read` (indicates inefficient usage)
* `agent.loop: stop_reason=max_hops_reached` (indicates queries the model can't resolve)

---

## 4. Architecture overview

The system is an **Agentic RAG**: an LLM-driven agent autonomously selects among eight registered tools, executes them, examines the results, and decides whether to call more tools or write the final answer. Each tool is a Python function with a strictly-typed Pydantic input schema.

### High-level data flow

```mermaid
flowchart TB
    Q[Student question<br/>any of 6 languages]
    V[Input validation<br/>reject empty / over 4000 chars<br/>reject history over 10 turns]
    L[Agent loop<br/>max 5 hops]
    H0[hop 0: Claude Sonnet 4.5<br/>routing + first tool selection]
    H1[hop 1..N: Claude Haiku 4.5<br/>synthesis + follow-up tools]
    R[TOOLS_REGISTRY<br/>8 tools]
    DB[(PostgreSQL<br/>Supabase<br/>rooms, houses,<br/>bookings, reviews)]
    KB[(Policy KB<br/>27 entries<br/>YAML in-memory)]
    PC[(Pinecone<br/>2 indexes:<br/>descriptions,<br/>reviews)]
    A[Final answer<br/>in user's language]

    Q --> V
    V --> L
    L --> H0
    H0 --> H1
    H0 --> R
    H1 --> R
    R --> DB
    R --> KB
    R --> PC
    DB --> R
    KB --> R
    PC --> R
    H1 --> A
```

### Agent loop detail

The core control structure is `run_agent_turn` in `src/elh_rag/agent/loop.py`. Each iteration ("hop") is one LLM call; if the model decides to use a tool, the hop count advances and the next hop sees the tool result; if the model produces a final answer (`stop_reason=end_turn`), the loop terminates.

```mermaid
sequenceDiagram
    participant U as User query
    participant L as Agent loop
    participant S as Claude Sonnet 4.5
    participant H as Claude Haiku 4.5
    participant T as Tool registry
    participant E as External services

    U->>L: query (+ optional history)
    L->>S: hop 0 (routing decision)
    S-->>L: tool_use { name, input }
    L->>T: dispatch(name, input)
    T->>E: query DB / Pinecone / KB
    E-->>T: result
    T-->>L: tool_result
    L->>H: hop 1 (synthesis + maybe more tools)
    alt model needs another tool
        H-->>L: tool_use { ... }
        L->>T: dispatch
        T-->>L: tool_result
        L->>H: hop 2
    end
    H-->>L: final text
    L-->>U: AgentResponse
```

### Tool inventory

The eight tools are grouped by category. Each is a Python function decorated with `@register_tool(...)`, declaring its input schema and the sub-context it needs (`db`, `kb`, `pinecone`, or `None`).

```mermaid
flowchart LR
    A[Agent]

    subgraph SDB [Structured DB tools]
        T1[find_rooms<br/>SQL filters]
        T2[find_available_rooms<br/>filters + dates]
        T3[compute_total_cost<br/>full quote]
        T4[get_property_details<br/>one room/house]
        T5[get_booking_stats<br/>k-anonymous aggregates]
    end

    subgraph SKB [Knowledge base tool]
        T6[answer_policy_question<br/>FAQ KB]
    end

    subgraph SEM [Semantic search tools]
        T7[search_descriptions<br/>vector search]
        T8[search_reviews<br/>vector search]
    end

    A --> T1
    A --> T2
    A --> T3
    A --> T4
    A --> T5
    A --> T6
    A --> T7
    A --> T8
```

### Components in detail

* **The agent loop** (`src/elh_rag/agent/loop.py`) — entry point `run_agent_turn(query, ctx, *, conversation_history=None, ...)`. Validates input, instantiates the LLM clients, runs up to 5 hops, returns an `AgentResponse` object containing the answer, tool trace, token counts, and total duration.
* **Tool registry** (`src/elh_rag/agent/tool_registry.py`) — a global dict populated at import time via the `@register_tool(...)` decorator. Each tool declares its name, description (shown to the LLM), Pydantic input model, and which sub-context it needs (`ctx_attr="db"` or `"kb"` or `None`).
* **LLM client** (`src/elh_rag/agent/agent_llm_client.py`) — wraps the Anthropic SDK with `tenacity`-based retries, streaming support, and prompt caching. Two instances exist at runtime: one for Sonnet (`AgentLLMClient(model="claude-sonnet-4-5")`), one for Haiku.
* **Agent context** (`src/elh_rag/agent/context.py`) — lazy-loaded container for the database connection (Supabase), the in-memory policy knowledge base (loaded from YAML at startup, currently 27 entries with 125 variant embeddings), and the Pinecone client. Built once per process at startup.
* **System prompt** (`src/elh_rag/agent/agent_prompt.py`) — about 2 500 tokens of routing rules (13 rules), error handling guidance, and six few-shot examples in six languages. Combined with tool schemas (~7 500 tokens of JSON), the total cached prefix is ~11 200 tokens.

### Where Anthropic's API fits in

The Anthropic API is called once per hop. Each call sends the full conversation so far plus the system prompt; with prompt caching enabled, the system prompt is sent only as a cache reference on every call after the first within 5 minutes.

The LLM never receives database credentials, never sees raw SQL, and never has direct internet access. It can only do what the eight registered tools allow.

---

## 5. Conversation memory

The agent is **backend-stateless**: it does not maintain conversation state across requests. Instead, the calling application keeps the conversation history client-side and passes the relevant turns into each `run_agent_turn` call. This pattern matches the design of all major chat LLMs (Anthropic, OpenAI, Google) and keeps the backend horizontally scalable with no session store.

### Data flow

```mermaid
sequenceDiagram
    participant U as User
    participant C as Client app<br/>(keeps history)
    participant B as Backend<br/>(run_agent_turn)
    participant L as LLM<br/>(Anthropic API)

    Note over C: history = []
    U->>C: "Find cheap rooms in Lisbon"
    C->>B: run_agent_turn(query, history=None)
    B->>L: messages = [user: query]
    L-->>B: assistant final_message
    B-->>C: AgentResponse
    Note over C: history = [user, assistant]
    C-->>U: shows answer

    U->>C: "How much for the cheapest?"
    C->>C: take last 5 turns (FIFO)
    C->>B: run_agent_turn(query, history=[...])
    B->>L: messages = [history..., user: new query]
    Note over L: model reads context,<br/>resolves "the cheapest"
    L-->>B: assistant final_message
    B-->>C: AgentResponse
    Note over C: history grows
    C-->>U: shows answer
```

### API

The `run_agent_turn` function accepts an optional `conversation_history` keyword argument:

```python
from elh_rag.agent import AgentContext, ConversationTurn, run_agent_turn

ctx = AgentContext.build()

# Turn 1 — no history yet
response_1 = run_agent_turn(
    query="Find the cheapest single rooms in Lisbon.",
    ctx=ctx,
)

# Turn 2 — pass the prior exchange as history
history = [
    ConversationTurn(role="user", content="Find the cheapest single rooms in Lisbon."),
    ConversationTurn(role="assistant", content=response_1.final_message),
]
response_2 = run_agent_turn(
    query="How much for 6 months from September for the cheapest one?",
    ctx=ctx,
    conversation_history=history,
)
```

The model reads the history and resolves anaphoric references ("the cheapest one", "the second one", "it") natively, without any query rewriting.

### Truncation rules

The client is expected to truncate to a small number of recent turns (typically 5) before sending. Longer histories are accepted up to `settings.agent_max_history_turns` (default 10); requests exceeding this hard cap are rejected with `InputValidationError`.

What gets sent in each `ConversationTurn`:

* **`role`**: `"user"` or `"assistant"` (literal type, validated by Pydantic).
* **`content`**: plain text. For user turns this is the original query. For assistant turns this is the `final_message` from the previous `run_agent_turn` call — not the full tool trace. Tool calls and tool results from prior turns are intentionally NOT carried over, because they would balloon context tokens without giving the model new information.

### What does NOT get carried across turns

Only the natural-language reply is preserved. The following are recomputed fresh each turn if needed:

* Tool calls and their results from prior turns
* The agent's internal scratchpad / reasoning between hops
* Any specific room IDs, prices, or other detailed data from prior tool outputs

If the model needs a specific room ID from a prior turn (e.g. to call `compute_total_cost`), it will either re-derive it from its own assistant reply if it included the ID in the visible text, or — more commonly — invoke `find_rooms` again to retrieve the current top results. This is intentional: it keeps each turn self-contained and avoids stale data leaking across the conversation.

### Smoke test

A 3-turn smoke test demonstrating anaphoric reference resolution lives at `scripts/smoke_tests/smoke_test_conversation.py`. It simulates:

1. *"Find the cheapest single rooms in Lisbon."*
2. *"What's the total cost for 6 months from September for the cheapest one?"* — the model must resolve "the cheapest one" by reading the prior assistant reply.
3. *"And the second one in your list?"* — the model must resolve "the second one" by reading two turns back.

Run it with `python -m scripts.smoke_tests.smoke_test_conversation`. Expected cost: ~$0.05.

---

## 6. Changing the LLM provider

ELH may want to switch from Anthropic to another provider (DeepSeek, Gemini, OpenAI, Mistral) for cost, latency, sovereignty, or vendor-diversification reasons. This section explains how, with the practical changes for each provider.

### Architectural disclaimer

The current `AgentLLMClient` is written specifically for the Anthropic Python SDK. Each provider has subtly different:

* **Tool-use schema format** (Anthropic uses `input_schema`, OpenAI uses `parameters`, Gemini uses `parameters` but with different type system)
* **Stop reasons** (Anthropic: `end_turn` / `tool_use` / `max_tokens`; OpenAI: `stop` / `tool_calls` / `length`)
* **Streaming protocol**
* **Prompt-caching support** (Anthropic, OpenAI: yes; Gemini: explicit caching API, different model; DeepSeek: yes; Mistral: limited)

The clean way to support multiple providers is an `LLMProvider` abstract base class with one concrete implementation per provider. The current code does not have this abstraction because a single provider is in use; introducing it would be the first step before supporting two providers in production simultaneously.

For a one-off switch (replace Anthropic entirely with another provider), it is faster to **rewrite `AgentLLMClient`** for the new provider and update the model strings. The sections below show this approach for each provider.

### 6.1 Switching to DeepSeek

DeepSeek's API is OpenAI-compatible, which makes the switch straightforward — you can use the `openai` Python SDK pointed at DeepSeek's base URL.

Install:

```bash
pip install openai>=1.50
```

Rewrite `src/elh_rag/agent/agent_llm_client.py` (only the `call` method shown; adapt `stream` similarly):

```python
from openai import OpenAI

class AgentLLMClient:
    def __init__(self, *, model: str = "deepseek-chat") -> None:
        self._client = OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com/v1",
        )
        self._model = model

    def call(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        system: str,
    ) -> Any:
        # DeepSeek expects system as a message at the top of messages.
        full_messages = [{"role": "system", "content": system}, *messages]

        response = self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            tools=self._convert_tools_to_openai_format(tools),
            tool_choice="auto",
            temperature=0.0,
            max_tokens=4096,
        )
        return response

    @staticmethod
    def _convert_tools_to_openai_format(
        anthropic_tools: list[dict],
    ) -> list[dict]:
        """Anthropic uses input_schema; OpenAI/DeepSeek use parameters."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in anthropic_tools
        ]
```

In the agent loop (`src/elh_rag/agent/loop.py`), update the stop-reason check:

```python
# Before (Anthropic):
if response.stop_reason == "end_turn":
    ...

# After (DeepSeek):
choice = response.choices[0]
if choice.finish_reason == "stop":
    ...
elif choice.finish_reason == "tool_calls":
    # Dispatch each tool_call in choice.message.tool_calls
    ...
```

**Pricing**: DeepSeek-V3 is at $0.27/$1.10 per million tokens (input/output) — roughly **10× cheaper than Sonnet 4.5**, comparable quality on many tasks.

**Caveat**: DeepSeek does not support the `cache_control` parameter the way Anthropic does. Caching is automatic on their side but less predictable.

### 6.2 Switching to OpenAI (GPT-4o, GPT-4-turbo)

Almost identical to DeepSeek, since DeepSeek's API is OpenAI-compatible. Differences:

```python
from openai import OpenAI

self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
# Default base_url is OpenAI's, no need to override

self._model = "gpt-4o"          # or "gpt-4o-mini" for cheaper/faster
```

The tool format conversion (`_convert_tools_to_openai_format` above) is the same.

For prompt caching on OpenAI: send identical prefixes ≥1024 tokens and OpenAI automatically caches them server-side (no `cache_control` parameter needed). Discount is 50%, less aggressive than Anthropic's 90%.

**Pricing**: GPT-4o is at $2.50/$10 per million tokens — comparable to Sonnet 4.5.

### 6.3 Switching to Google Gemini

Different SDK, more substantial changes.

```bash
pip install google-genai>=0.1
```

```python
from google import genai
from google.genai.types import Tool, FunctionDeclaration

class AgentLLMClient:
    def __init__(self, *, model: str = "gemini-2.5-flash") -> None:
        self._client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self._model = model

    def call(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        system: str,
    ) -> Any:
        gemini_tools = [
            Tool(function_declarations=[
                FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters=t["input_schema"],
                )
            ])
            for t in tools
        ]

        response = self._client.models.generate_content(
            model=self._model,
            contents=self._convert_messages_to_gemini(messages),
            config={
                "system_instruction": system,
                "tools": gemini_tools,
                "temperature": 0.0,
            },
        )
        return response
```

Gemini's response format is yet different (`response.candidates[0].content.parts`), so the parsing in `loop.py` needs updating to extract `function_call` parts from the response.

**Pricing**: Gemini 2.5 Flash is at $0.10/$0.40 per million tokens — about **30× cheaper than Sonnet 4.5**. Quality is competitive on many tasks.

**Gemini-specific**: native multilingual support (no separate embedder needed for some tasks), context caching via explicit API, no cross-region inference.

### 6.4 Switching to Mistral

```bash
pip install mistralai>=1.0
```

```python
from mistralai import Mistral

class AgentLLMClient:
    def __init__(self, *, model: str = "mistral-large-latest") -> None:
        self._client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
        self._model = model

    def call(self, *, messages, tools, system) -> Any:
        full_messages = [{"role": "system", "content": system}, *messages]
        return self._client.chat.complete(
            model=self._model,
            messages=full_messages,
            tools=self._convert_tools_to_openai_format(tools),
            tool_choice="auto",
            temperature=0.0,
        )
```

Mistral's API is OpenAI-compatible like DeepSeek, so the tool format conversion is the same.

**Pricing**: Mistral Large is at $2/$6 per million tokens — middle of the pack.

**Specifically interesting**: Mistral is European, which may matter for GDPR / data-sovereignty considerations. They also offer self-hosted models.

### 6.5 Comparison table

| Provider | Model | $ in/out per Mtok | Speed | Caching | Tool use |
|---|---|---|---|---|---|
| **Anthropic** (current) | Sonnet 4.5 + Haiku 4.5 | 3 / 15 (Sonnet) | Fast | 90% discount, explicit | Excellent |
| **DeepSeek** | DeepSeek-V3 | 0.27 / 1.10 | Medium | Automatic | Good (OpenAI-compatible) |
| **OpenAI** | GPT-4o | 2.50 / 10 | Fast | 50% discount, automatic | Excellent |
| **Google** | Gemini 2.5 Flash | 0.10 / 0.40 | Very fast | Explicit | Good |
| **Mistral** | Mistral Large | 2 / 6 | Fast | Limited | Good |

### 6.6 What to test after a provider switch

Whatever provider you choose, before considering the migration complete:

1. **Run the full test suite**: `pytest tests/` — must stay at 895/895 (the tests use mocks and should be provider-agnostic).
2. **Run the smoke test**: `python -m scripts.smoke_tests.smoke_test_agent` — should produce a sensible answer.
3. **Run the benchmark**: `python -m scripts.benchmarks.run_agent_benchmark` — compare coverage and latency to the Anthropic baseline (100% coverage, 9.6s avg). If coverage drops below 90%, the model is not a good fit for this agentic task and you should pick a stronger one.
4. **Re-tune the system prompt** if needed. The few-shot examples in `agent_prompt.py` were written for Anthropic's response style. Other models may need slightly different examples to produce equally good outputs.

A full migration including testing typically takes 1–2 days of engineering time.

---

## 7. Monitoring costs

### Anthropic console

The Anthropic web console (https://console.anthropic.com/usage) shows:

* **Daily token usage** broken down by model and by cache hit/miss
* **Daily cost** in USD
* **Per-API-key usage** if you have multiple keys

Set up email alerts at 50%, 80%, and 100% of your monthly budget via the Plans & billing → Usage limits section.

### In-application logging

The `AgentLLMClient._log_cache_usage` method emits an INFO log line on every call:

```
agent.llm: cache_creation=9712, cache_read=0, input=333, output=96
```

`input` and `output` are token counts. To compute cost in real-time:

* Sonnet 4.5: $3 per million input tokens, $15 per million output tokens
* Haiku 4.5: $1 per million input tokens, $5 per million output tokens
* Cache read: 10% of standard input price (i.e. $0.30/M for Sonnet, $0.10/M for Haiku)
* Cache creation: 125% of standard input price (one-off)

A 24-hour log aggregator (CloudWatch, Datadog, etc.) can sum these and produce a real-time cost dashboard.

### Typical costs in production

Based on the 20-question benchmark and assumptions:

* **Per question (mixed types)**: ~$0.018 USD
* **100 questions/day**: ~$1.80 USD/day, ~$55 USD/month
* **1 000 questions/day**: ~$18 USD/day, ~$540 USD/month
* **10 000 questions/day**: ~$180 USD/day, ~$5 400 USD/month

Switching to Haiku for hop 0 as well (set `agent_llm_model=claude-haiku-4-5-20251001`) reduces costs by ~50% with a modest quality drop on multi-hop questions. Switching to DeepSeek or Gemini Flash reduces costs by 10–30× — at the cost of a 1–2 day migration and re-validation.

### Setting hard cost limits

The application has no built-in monthly cost cap (Anthropic enforces this at the account level). To prevent surprises:

1. Set a low monthly limit in the Anthropic console (e.g. $200) for the first month and raise it as you gain confidence.
2. In production, add a rate-limiter at the frontend (e.g. 10 questions per user per hour) to prevent abuse.
3. Monitor the `agent_max_query_chars=4000` limit — long queries cost more.

---

## 8. Known limitations and how to extend

### Limitations

| Limitation | Impact | Workaround / fix |
|---|---|---|
| **Read-only** | Cannot book rooms, only find them | Add tools that perform write operations (with authentication and confirmation) |
| **English-leaning policy KB** | The 27 policy entries are in English, with question variants embedded in multiple languages but answers only in English | Translate answers to PT/IT/etc. and add language-specific entries (see `kb/policies.yaml`) |
| **Synchronous Python backend** | Each request blocks a worker | Convert `run_agent_turn` to async for higher concurrency |
| **Anthropic-specific code** | Vendor lock-in | See §6 for migration paths |
| **No automated re-indexing** | New reviews require manual `run_indexer` | Set up a weekly cron job in AWS EventBridge or equivalent scheduler |
| **Production logging is plain text** | Hard to alert on | Switch `logging` to JSON formatter, ship to CloudWatch or Datadog |
| **Stale tool results across turns** | Conversation memory carries only assistant text; specific room IDs from prior turns are not preserved | The agent re-invokes `find_rooms` when it needs IDs again; this is intentional but adds 1 hop in some multi-turn scenarios |

### How to add a new tool

Adding a new capability (e.g. *"check user's booking history"*) follows this pattern:

1. **Create a new module** under `src/elh_rag/tools/your_tool_name/`.
2. **Define a Pydantic input model** (`YourToolInput`) and output model (`YourToolOutput`).
3. **Implement the tool function** taking the input model and context:

   ```python
   from elh_rag.tools.base import register_tool

   @register_tool(
       name="your_tool_name",
       description="Brief description of what the tool does, in plain English. The LLM reads this.",
       input_model=YourToolInput,
       ctx_attr="db",  # or "kb" or None
   )
   def your_tool(payload: YourToolInput, ctx: DBExecutor) -> YourToolOutput:
       # Implementation here
       return YourToolOutput(...)
   ```

4. **Add unit tests** in `tests/tools/your_tool_name/test_your_tool.py`.
5. **Import the module** in `src/elh_rag/tools/__init__.py` so the `@register_tool` decorator fires.
6. **Update the few-shot examples** in `agent_prompt.py` if the new tool requires unusual usage patterns.
7. **Run the benchmark** to confirm the LLM picks up the new tool when appropriate.

The agent will automatically include the new tool in its routing options. No changes to the loop are needed.

### How to add a new language

To support a 7th language (e.g. Dutch):

1. **Add a few-shot example** in `src/elh_rag/agent/agent_prompt.py` showing a Dutch user query and the corresponding Dutch answer.
2. **Verify the embedder handles it**: `paraphrase-multilingual-mpnet-base-v2` supports 50+ languages including Dutch. Test with a Dutch query against the existing Pinecone index.
3. **Translate the policy KB entries** (`src/elh_rag/tools/answer_policy_question/kb/policies.yaml`) to Dutch and re-embed.
4. **Run a small benchmark** with Dutch queries to verify routing accuracy.

---

## 9. Appendix — useful commands

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt && pip install -e .

# Indexing
python -m scripts.run_indexer --source all          # full rebuild
python -m scripts.run_indexer --source reviews      # reviews only
python -m scripts.run_indexer --source descriptions # descriptions only

# Tests
pytest tests/ -q                                    # full offline suite (~5s)
pytest tests/ --cov=elh_rag                         # with coverage
mypy src/elh_rag                                    # type checking
ruff format src tests scripts                       # autoformat
ruff check src tests scripts                        # lint
pip-audit                                           # security audit

# Benchmarks (live, costs API tokens)
python -m scripts.benchmarks.run_agent_benchmark           # ~$0.37
python -m scripts.benchmarks.analyze_agent_benchmark       # generate report
python -m scripts.benchmarks.generate_human_eval_excel     # generate Excel template

# Smoke tests (live, ~$0.01-$0.05 each)
python -m scripts.smoke_tests.smoke_test_agent             # single-turn
python -m scripts.smoke_tests.smoke_test_conversation      # multi-turn memory
```

---

**Contact for questions during handover**: Giovanni Pisoni — giovanni.pisoni@studio.unibo.it

**Repository**: https://github.com/GiovanniPisoni/elh-semantic-search
**Release notes**: https://github.com/GiovanniPisoni/elh-semantic-search/releases/tag/v3.0.0-agentic-rag

*Developed as part of a Master's thesis at Alma Mater Studiorum Università di Bologna, supervised by Prof. Enrico Gallinucci, in collaboration with Erasmus Life Housing.*