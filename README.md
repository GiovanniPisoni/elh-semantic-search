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
| **2** | Advanced RAG (query rewriting, re-ranking, second corpus, conversational memory) | 🔄 Step 1/4 done |
| **3** | Hybrid / Agentic RAG (tool calling on Supabase: geo, price, policy) | 🔜 Planned |
| **4** | Evaluation (golden dataset, RAGAS, Naive vs Advanced comparison) | 🔜 Planned |
| **5** | Deliverable for ELH (FastAPI, Docker, technical docs) | 🔜 Planned |

### Phase 2 progress

| Step | Description | Status |
|---|---|---|
| 1 | Query rewriting (LLM rephrases the question before retrieval) | ✅ Done |
| 2 | Cross-encoder re-ranking | 🔜 Next |
| 3 | Second corpus: house + room descriptions with intent routing | 🔜 |
| 4 | Conversational memory for follow-up questions | 🔜 |

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
                  │   (optional, Phase 2) │   ENABLE_QUERY_REWRITING toggle
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
                  │  (top-k cosine)       │   metadata filter: city, rating
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
**only** for retrieval — the answer generation LLM always receives the
original question, so the response stays stylistically faithful to the
user's phrasing. The step can be disabled via `ENABLE_QUERY_REWRITING=false`
to enable Naive vs Advanced A/B comparison in Phase 4.

### Architecture (Phase 2 upcoming + Phase 3)

The remaining Phase 2 steps will introduce **cross-encoder re-ranking**
after retrieval, a **second corpus** (property and room descriptions) with
**intent-based routing**, and **conversational memory** for follow-up
questions. Phase 3 will add **tool calling** for structured queries
(geographic filters, price ranges, policies) on Supabase, turning the
system from RAG to **Agentic RAG**.

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
│   │   └── query_rewriter.py   # LLM-based query rewriter (Phase 2, Step 1)
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
│   └── test_query_rewriter.py  # Phase 2, Step 1
│
└── evaluation/                 # Phase 4 — golden set + RAGAS metrics
```

---

## Tech Stack

| Component | Technology | Status | Reason |
|---|---|---|---|
| Language | Python 3.12 | ✅ | Stable ML ecosystem |
| LLM (generation) | Anthropic Claude Sonnet | ✅ | Strong instruction following and faithfulness |
| LLM (query rewriting) | Anthropic Claude Haiku | ✅ | Smaller/cheaper/faster for a simpler task (Phase 2) |
| Embeddings | `paraphrase-multilingual-mpnet-base-v2` | ✅ | Native EN + PT support, 768-dim, free, local |
| Vector store | Pinecone (serverless) | ✅ | Cloud-managed, persists after thesis, accessible by ELH |
| Database | PostgreSQL (Supabase) | ✅ | ELH operational DB, accessed live (no local copy) |
| UI | Streamlit | ✅ | Fast prototyping, ideal for academic demo |
| Configuration | Pydantic Settings | ✅ | Validated env vars at boot |
| Re-ranking | cross-encoder | 🔜 | Phase 2, Step 2 |
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

### 3. Build the Pinecone index

```bash
make index             # incremental upsert (idempotent)
make index-reset       # wipe and rebuild from scratch
```

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

When query rewriting is active, the pipeline rewrites the user's question **only** for retrieval. The generation LLM still receives the original question, so the final answer stays stylistically faithful to how the user phrased the request. This avoids a common pitfall where a rewritten, keyword-heavy query leaks into the final response.

Query rewriting uses a cheaper model (Claude Haiku) since it's a structured, short-output task — roughly 10× cheaper and 2-3× faster than using Sonnet for both stages. Results are memoised in-process (`lru_cache(128)`) to avoid redundant API calls during demos and repeated queries.

The step is gated by `ENABLE_QUERY_REWRITING` so Phase 4 evaluation can run the same golden set twice — with and without rewriting — and report the retrieval quality delta.

### Graceful degradation

If the rewriter fails (API down, malformed response, network timeout), the pipeline falls back to the original question rather than crashing. This applies to the retrieval path too: empty retrieval results produce a clear "no relevant reviews" response instead of an error. A thesis system should be observable and robust, not brittle.

### Idempotent indexing

Pinecone `upsert` is idempotent by design: writing the same ID twice is a no-op rather than a duplicate. This eliminates the need for per-document existence checks (which previously cost N API calls), making indexing dramatically faster and cheaper.

---

## Roadmap

### Phase 2 — Advanced RAG

- ✅ Query rewriting (LLM rephrases the query before retrieval, toggled via env var)
- 🔜 Cross-encoder re-ranking (re-scores top-N candidates)
- 🔜 Second corpus: house and room descriptions
- 🔜 Intent-based routing between corpora
- 🔜 Conversational memory (follow-up questions like *"and in Porto?"*)

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
