# ELH Semantic Search — RAG-Based System for Erasmus Life Housing

> Master's Thesis Project · Alma Mater Studiorum Università di Bologna

A **Retrieval-Augmented Generation (RAG)** system that enables semantic search over Erasmus Life Housing's unstructured textual data — student reviews, property descriptions, and listing details — using state-of-the-art NLP techniques.

---

## Project Status

This project is developed in **5 phases**. The current state of each is marked below.

| Phase | Description | Status |
|---|---|---|
| **0** | Domain analysis & technology study | ✅ Complete |
| **1** | Naive RAG prototype (retrieval + generation, Pinecone, Streamlit) | ✅ Complete |
| **2** | Advanced RAG (query rewriting, re-ranking, second corpus, conversational memory) | ✅ Complete |
| **3** | Hybrid / Agentic RAG (tool calling on Supabase: geo, price, policy) | 🔜 Planned |
| **4** | Evaluation (golden dataset, RAGAS, Naive vs Advanced comparison) | 🔜 Planned |
| **5** | Deliverable for ELH (FastAPI, Docker, technical docs) | 🔜 Planned |

### Phase 2 progress

| Step | Description | Status |
|---|---|---|
| 1 | Query rewriting (LLM rephrases the question before retrieval) | ✅ Done |
| 2 | Cross-encoder re-ranking (BGE-reranker-v2-m3, multilingual) | ✅ Done |
| 3 | Document chunking | 🔍 Conditional (deferred until Phase 4 measures the need) |
| 4 | Second corpus (house + room descriptions) + intent routing + orchestrator | ✅ Done |
| 5 | Conversational memory for follow-up questions | ✅ Done |

This README reflects the system **as it is today**. Features marked as planned are described in the [Roadmap](#roadmap) section.

---

## The Company — Erasmus Life Housing

**Erasmus Life Housing (ELH)** is a platform specialised in student accommodation for Erasmus and international students, operating primarily in **Lisbon and Porto, Portugal**. The platform connects students with landlords, managing the full rental lifecycle — from listing and booking to payments and reviews.

The ELH platform handles a rich operational database covering:

- **Properties and rooms** — location, amenities, pricing, availability
- **Reservations and payments** — booking lifecycle, seasonal pricing, deposits
- **Reviews** — student feedback on comfort, cleanliness, landlord communication, value
- **Landlords and clients** — profiles, portfolios, international student demographics

---

## The Problem

ELH's platform already provides standard search filters — city, price range, amenities — that work well for structured queries. However, a large and valuable category of data remains entirely untapped: the **free-form text** written by students and landlords.

This text contains information that cannot be captured in any structured field:

- A student writes *"the mattress was incredibly comfortable"* — no boolean captures this
- Another notes *"the landlord responded within hours whenever something broke"* — no rating fully conveys this
- A landlord describes *"a bright room ideal for students who need to study"* — no filter finds this

The result is that students cannot ask the platform the questions that matter most to them, and ELH cannot extract insights from the most honest data it collects.

---

## The Solution

This project builds a system that makes ELH's unstructured textual data **queryable in natural language**. A student types a question as they would ask a friend, and the system retrieves and synthesises relevant information from real reviews — without fabricating anything.

**Examples of questions the system can answer today (Phase 1):**

- *"Find rooms where students mention a comfortable bed"*
- *"Which landlords are described as responsive to problems?"*
- *"Properties in a quiet area suitable for studying"*
- *"Apartments with complaints about noise or maintenance issues"*
- *"Rooms praised for cleanliness and natural light"*

These are questions that no SQL filter, no dropdown menu, and no dashboard can answer — because the answers live only in the text.

---

## Why RAG and not something else

Two simpler alternatives were evaluated and discarded:

**Standard search filters** already exist and cover structured data well. Adding more filters cannot capture semantic concepts like "quiet", "cosy", or "responsive landlord" — these are qualitative judgements expressed in free text.

**Text-to-SQL on analytical KPIs** was considered for a management-facing tool, but carries high risk of hallucination on numerical data. A system that generates incorrect revenue figures or occupancy rates is worse than no system at all.

**RAG on unstructured text** is the right fit because the AI never generates numbers or facts from memory — it reads real text already in the database and synthesises it. The risk of hallucination is minimal, and the value added is genuine: answering questions that were previously unanswerable.

---

## Data Sources

The system indexes textual data from the ELH operational database. **Phase 1 currently uses only review data**; Phase 2 will extend the corpus to property and room descriptions.

| Source | Table | Field | Status |
|---|---|---|---|
| Student reviews | `review` | `description`, `title` | ✅ Indexed (Phase 1) |
| Property descriptions | `house` | `description`, `otherameneties` | 🔜 Phase 2 |
| Room descriptions | `room` | `description` | 🔜 Phase 2 |

Messages exchanged between students and landlords were evaluated but excluded: they are private between the two parties and not accessible to the ELH team.

---

## Architecture (current)

```
                  Student question (natural language)
                              │
                              ▼
                  ┌───────────────────────┐
                  │   Query rewriting     │   Anthropic Claude Haiku
                  │   (optional, Phase 2) │   ENABLE_QUERY_REWRITING
                  └───────────┬───────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │   Query embedding     │   sentence-transformers
                  │   (multilingual EN+PT)│   paraphrase-multilingual-mpnet-base-v2
                  └───────────┬───────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │  Vector retrieval     │   Pinecone serverless
                  │  (pool of N=20)       │   metadata filter: city, rating
                  └───────────┬───────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │  Cross-encoder rerank │   BAAI/bge-reranker-v2-m3
                  │  (optional, Phase 2)  │   100+ languages · ENABLE_RERANKING
                  │  N=20 → top_k=5       │
                  └───────────┬───────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │  Context assembly     │   review headers + body
                  └───────────┬───────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │  Answer generation    │   Anthropic Claude Sonnet
                  │  (grounded in reviews)│   sees ORIGINAL question
                  └───────────────────────┘
```

**Note on query rewriting (Phase 2, Step 1):** the rewriter transforms the
user's conversational question into a search-optimised query (e.g. *"I
need a quiet place where I can study"* → *"quiet room, peaceful, low
street noise, suitable for studying"*). This rewritten query is used
**only** for retrieval and reranking — the answer generation LLM always
receives the original question, so the response stays stylistically
faithful to the user's phrasing. The step can be disabled via
`ENABLE_QUERY_REWRITING=false`.

**Note on cross-encoder reranking (Phase 2, Step 2):** vector retrieval
is fast but approximate. It computes query and document embeddings
independently and compares them with cosine similarity — efficient but
missing fine-grained lexical and contextual signals. A cross-encoder
analyses the `(query, document)` pair jointly in a single transformer
forward pass, producing much more accurate relevance scores at the cost
of higher latency.

The standard pattern is two-stage retrieval: the bi-encoder retrieves a
pool of N candidates fast (N=20 by default), then the cross-encoder
re-scores all N jointly with the query and returns only the top K (K=5).
Both scores are preserved in the response (`vector_score` and
`rerank_score`) — this lets Phase 4 evaluation quantify exactly how much
reranking reshuffled the top-k, and whether the reshuffling improved
ground-truth recall.

`BAAI/bge-reranker-v2-m3` was chosen for its native support of 100+
languages — important for international Erasmus students querying in
their native language, not just the primary EN/PT corpus. The step can
be disabled via `ENABLE_RERANKING=false`.

### Architecture (Phase 2 upcoming + Phase 3)

The remaining Phase 2 steps will introduce a **second corpus** (property
and room descriptions) with **intent-based routing**, and **conversational
memory** for follow-up questions. Phase 3 will add **tool calling** for
structured queries (geographic filters, price ranges, policies) on
Supabase, turning the system from RAG to **Agentic RAG**.

---

## Project Structure

```
elh-semantic-search/
├── README.md
├── pyproject.toml              # Build, pytest, ruff, mypy config
├── requirements.txt            # Runtime dependencies
├── requirements-dev.txt        # Dev dependencies (pytest, ruff, mypy)
├── Makefile                    # Common commands (Linux/macOS)
├── dev.ps1                     # Windows equivalent
├── .env.example                # Template for environment variables
│
├── src/elh_rag/                # Main package
│   ├── config.py               # Pydantic Settings — single source of truth
│   ├── schemas.py              # Typed dataclasses (Document, Metadata, Response)
│   ├── pipeline.py             # RAG orchestration (composable steps)
│   ├── logging_setup.py        # Structured logging
│   │
│   ├── data/
│   │   └── extractor.py        # Supabase → Document objects
│   │
│   ├── indexing/
│   │   ├── vector_store.py     # VectorStore Protocol (interface)
│   │   ├── pinecone_store.py   # Pinecone implementation
│   │   ├── embeddings.py       # SentenceTransformer wrapper
│   │   └── indexer.py          # Build embeddings + upsert
│   │
│   ├── retrieval/
│   │   ├── query_rewriter.py   # LLM-based query rewriter (Phase 2, Step 1)
│   │   └── reranker.py         # Cross-encoder reranker (Phase 2, Step 2)
│   │
│   ├── generation/
│   │   ├── llm_client.py       # Anthropic wrapper
│   │   └── prompts.py          # System + user templates
│   │
│   └── ui/                     # Streamlit application (modular)
│
├── scripts/
│   └── run_indexer.py          # Entry point: python -m scripts.run_indexer
│
├── tests/
│   ├── conftest.py             # Fakes + fixtures (no network calls)
│   ├── test_schemas.py
│   ├── test_pipeline.py
│   ├── test_extractor.py
│   ├── test_query_rewriter.py  # Phase 2, Step 1
│   └── test_reranker.py        # Phase 2, Step 2
│
└── evaluation/                 # Phase 4 — golden set + RAGAS metrics
```

---

## Tech Stack

| Component | Technology | Status | Reason |
|---|---|---|---|
| Language | Python 3.12 | ✅ | Stable ML ecosystem |
| LLM (generation) | Anthropic Claude Sonnet | ✅ | Strong instruction following and faithfulness |
| LLM (query rewriting) | Anthropic Claude Haiku | ✅ | Smaller/cheaper/faster for a simpler task |
| Embeddings | `paraphrase-multilingual-mpnet-base-v2` | ✅ | Native EN + PT support, 768-dim, free, local |
| Reranker | `BAAI/bge-reranker-v2-m3` | ✅ | Multilingual cross-encoder (100+ languages) |
| Vector store | Pinecone (serverless) | ✅ | Cloud-managed, persists after thesis, accessible by ELH |
| Database | PostgreSQL (Supabase) | ✅ | ELH operational DB, accessed live (no local copy) |
| UI | Streamlit | ✅ | Fast prototyping, ideal for academic demo |
| Configuration | Pydantic Settings | ✅ | Validated env vars at boot |
| Routing | intent-based | 🔜 | Phase 2, Step 3 |
| Memory | conversational context | 🔜 | Phase 2, Step 4 |
| Evaluation | RAGAS | 🔜 | Phase 4 — faithfulness, answer relevance |
| API | FastAPI | 🔜 | Phase 5 — REST endpoint for ELH integration |
| Containerisation | Docker | 🔜 | Phase 5 — handover to ELH |

---

## Setup

### 1. Clone and install

```bash
git clone <repo-url>
cd elh-semantic-search

python -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate            # Windows

make install                       # runtime only
# or
make install-dev                   # runtime + pytest, ruff, mypy
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your real credentials (DB_URI, PINECONE_API_KEY, ANTHROPIC_API_KEY)
```

### 3. Build the Pinecone indices

The system uses two separate Pinecone indices — `elh-reviews` and `elh-descriptions`.
Both must be created on the Pinecone dashboard with **dimension 768** and **cosine** similarity.

```bash
# Index reviews only (Phase 1 default, backward-compatible)
python -m scripts.run_indexer

# Index descriptions only (Phase 2 Step 4)
python -m scripts.run_indexer --source descriptions

# Index both corpora in sequence
python -m scripts.run_indexer --source all

# Wipe and rebuild a specific corpus from scratch
python -m scripts.run_indexer --source descriptions --reset
```

Expected production state after `--source all`:
- `elh-reviews`: ~358 vectors
- `elh-descriptions`: ~350 vectors (80 unique houses + 270 unique rooms)

### 4. Run the app

```bash
make app
```

The Streamlit interface will open at `http://localhost:8501`.

---

## Development

```bash
make test              # run the test suite
make test-cov          # tests with coverage report
make lint              # check with ruff
make format            # auto-format and auto-fix
make clean             # remove caches and build artifacts
```

The test suite uses fake implementations of Pinecone, Anthropic, and SentenceTransformer — **no network calls, no API keys required to run tests.**

---

## Key Design Decisions

### Dependency injection over global singletons

The `RAGPipeline` accepts the vector store, embedder, and LLM client as constructor arguments. Defaults wire up the production stack, but tests inject fakes. This same pattern will let Phase 5's FastAPI layer instantiate multiple pipeline configurations from one codebase.

### `VectorStore` as a Protocol

Phase 2 will introduce a second corpus (house and room descriptions) requiring routing between two collections. A protocol-based abstraction means the pipeline does not need to know which backend (or how many) it is talking to.

### Composable pipeline steps

Each step of the RAG pipeline (`_retrieve`, `_build_context`, `_generate`) is a separate method. Phase 2 added `_maybe_rewrite` before retrieval without modifying existing steps; future steps (`_rerank`, routing, memory) will follow the same pattern.

### Query rewriting: same question for the user, optimised query for the retriever

When query rewriting is active, the pipeline rewrites the user's question **only** for retrieval and reranking. The generation LLM still receives the original question, so the final answer stays stylistically faithful to how the user phrased the request. This avoids a common pitfall where a rewritten, keyword-heavy query leaks into the final response.

Query rewriting uses a cheaper model (Claude Haiku) since it's a structured, short-output task — roughly 10× cheaper and 2-3× faster than using Sonnet for both stages. Results are memoised in-process (`lru_cache(128)`) to avoid redundant API calls during demos and repeated queries.

The step is gated by `ENABLE_QUERY_REWRITING` so Phase 4 evaluation can run the same golden set twice — with and without rewriting — and report the retrieval quality delta.

### Two-stage retrieval: fast bi-encoder + precise cross-encoder

Vector retrieval with a bi-encoder (SentenceTransformer) is fast because it can precompute document embeddings once at indexing time and only needs to embed the query at search time. The downside is approximation: the model has no direct access to the pair when scoring.

A cross-encoder takes the `(query, document)` pair as a single input and produces a relevance score — roughly 2-3 orders of magnitude more accurate but also slower, since every candidate requires a full forward pass. Running a cross-encoder over the entire corpus is prohibitive.

The solution, standard in information retrieval, is **two-stage retrieval**: the bi-encoder narrows the search space to a pool of N=20 candidates per query (millisecond-level), then the cross-encoder re-scores those 20 and returns the top K=5 — adding ~150-400ms on CPU for substantially better precision.

Both scores are preserved in `RetrievalResult.vector_score` and `RetrievalResult.rerank_score` so Phase 4 evaluation can quantify *how much* reranking changed the ranking, not just whether precision improved.

`BAAI/bge-reranker-v2-m3` was chosen over lighter alternatives because ELH's Erasmus students query in many languages beyond EN and PT. A model trained only on English (e.g. `ms-marco-MiniLM`) would systematically penalise non-English queries — a bias problem in a multilingual system. The 2.2GB model is downloaded once and cached locally.

### Dual-corpus architecture: separate indices, unified orchestrator

Phase 2 Step 4 added a second corpus — house and room descriptions written by ELH property managers — sitting in its own Pinecone index (`elh-descriptions`, 350 documents) alongside the existing reviews index (`elh-reviews`, 358 documents). The two corpora are semantically complementary: reviews answer *"what was it like?"*, descriptions answer *"what is it?"*.

Keeping them in **separate indices** rather than merged was a deliberate choice: the embedding distributions are visibly different (subjective narrative vs factual catalogue text), and per-corpus reranking pools stay cleaner. It also makes per-source A/B evaluation in Phase 4 trivial.

A new subpackage `elh_rag.orchestration` introduces:
- `CorpusPipeline` (base class): rewrite + retrieve + rerank for one corpus, no generation
- `ReviewsPipeline`, `DescriptionsPipeline`: concrete subclasses
- `Orchestrator`: composes the intent router + per-corpus pipelines + a single generation step

The legacy `RAGPipeline` becomes a thin facade over `Orchestrator`, preserving the Phase 1 API so existing entry points (Streamlit UI, benchmarks, tests) keep working without modification.

### Intent routing: LLM classifier + keyword fallback + safe default

A user query like *"did students feel safe at night?"* should not waste a retrieval round on the descriptions corpus, and *"apartments with balcony in Porto"* should not be answered from review opinions. An `IntentRouter` (`elh_rag.retrieval.intent_router`) classifies each query into one of three intents — `reviews`, `descriptions`, or `both` — using Claude Haiku with strict JSON output.

Three strategies cascade for robustness:
1. **LLM classification** (primary): Haiku returns `{intent, confidence, reasoning}`. If `confidence` is below the configurable threshold (`INTENT_ROUTER_CONFIDENCE_THRESHOLD`, default 0.8), single-corpus answers are escalated to `both` to avoid committing to the wrong corpus.
2. **Keyword fallback** (when the LLM fails or returns malformed JSON): simple multilingual keyword lists (EN, PT, IT, ES) covering review-style and description-style vocabulary.
3. **Default `both`** (safety net): empty queries or total failures route to dual retrieval with confidence 0.

Routing accuracy measured against hand-labelled expected intent on a benchmark of 20 multilingual queries: **19/20 (95%)**. Cost: ~$0.0018 per query.

When the orchestrator routes to `both`, sources from the two corpora are merged by score and the generation LLM is called **once** on the combined context. A source-aware system prompt (`MULTICORPUS_SYSTEM_PROMPT`) instructs the model to weave subjective and factual material rather than treat both as "reviews".

### Conversational memory: rewriter before the router

The follow-up rewriter (Step 5) lets the system handle dependent questions like *"and in Porto?"* after a turn about Lisbon. Architecturally, the rewriter runs **before** the intent router, so the rewritten standalone query reaches retrieval, reranking, and routing intact. A separate `ConversationMemory` (bounded FIFO of `ConversationTurn` objects, default 5 turns) stores past pairs and is per-session in the Streamlit state.

Two design choices worth noting:
1. **Memory helps retrieval, not generation.** The generation LLM still receives the user's *original* phrasing — the rewriter only feeds the embedder and the router. This preserves conversational tone without paying the latency cost of stuffing 10 messages into the generation prompt.
2. **Graceful fallback all the way down.** Empty memory → no rewrite. LLM call fails → original question. LLM returns garbage → original question. The rewriter cannot make the pipeline worse, only better.

The rewriter uses Claude Haiku with a prompt containing five canonical follow-up examples (city swap, property swap, constraint addition, language switch, attribute filter). Memoised via `lru_cache` keyed on `(memory_signature, question)` so identical follow-ups in demos and tests don't pay twice.

### Graceful degradation

If the rewriter fails (API down, malformed response, network timeout), the pipeline falls back to the original question rather than crashing. If the reranker fails (GPU OOM, corrupted model file), the pipeline falls back to the vector-only ranking. If the intent router fails, the keyword fallback takes over; if that fails too, the system safely defaults to dual-corpus retrieval. Retrieval returning zero results produces a clear "no relevant sources" response instead of an error. A thesis system should be observable and robust, not brittle.

### Idempotent indexing — with a versioning gotcha

Pinecone `upsert` is idempotent by design: writing the same ID twice is a no-op rather than a duplicate. This eliminates the need for per-document existence checks, making indexing dramatically faster and cheaper.

A subtlety surfaced when indexing the descriptions corpus: ELH's `house` and `room` tables keep historical versions of each entity in-place, identified by the composite key `(id, dateupdate)`. Indexing all rows produced N versions per logical entity, all sharing the same Pinecone ID — so the upsert overwrote them down to one (often the wrong one). The fix lives in `DescriptionExtractor`'s SQL queries, which use `SELECT DISTINCT ON (id) ... ORDER BY dateupdate DESC` to keep only the most recent version per logical entity. Final state: 80 unique houses + 270 unique rooms = 350 active descriptions in production.

---

## Roadmap

### Phase 2 — Advanced RAG

- ✅ Query rewriting (LLM rephrases the query before retrieval, toggled via env var)
- ✅ Cross-encoder re-ranking (BGE-reranker-v2-m3, 100+ languages, toggled via env var)
- 🔍 Document chunking (deferred until Phase 4 measurements show the need)
- ✅ Second corpus: house and room descriptions, indexed in `elh-descriptions`
- ✅ Intent-based routing between corpora (Haiku classifier, 95% routing agreement on 20-query benchmark)
- ✅ Orchestrator with per-corpus pipelines + unified generation
- ✅ Conversational memory (follow-up questions like *"and in Porto?"* — pre-router rewriter)

### Phase 3 — Hybrid / Agentic RAG

- Tool calling on Supabase for structured queries (geographic distance, price ranges, policies)
- Intent detection: semantic search vs structured query vs both
- Conversational refinement across turns

### Phase 4 — Evaluation

- Manually curated golden dataset (questions + expected answers + expected sources)
- Retrieval metrics: precision@k, recall@k
- Generation metrics: RAGAS faithfulness, answer relevance
- Quantitative comparison: Naive vs Advanced RAG
- Error analysis on worst-performing queries

### Phase 5 — Deliverable for ELH

- FastAPI REST endpoint (`POST /search`)
- Docker container (code only — Pinecone and Supabase stay cloud-managed)
- Technical documentation for the ELH dev team
- Final demo and code handover

---

## Author

**Giovanni Pisoni** — Master's Student, Alma Mater Studiorum Università di Bologna

Supervisor: Prof. Enrico Gallinucci

---

## License

This project is developed for academic purposes as part of a Master's thesis. The repository is private and not intended for public distribution.