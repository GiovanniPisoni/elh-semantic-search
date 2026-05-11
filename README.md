# ELH Semantic Search

> Master's Thesis · Alma Mater Studiorum Università di Bologna
> Supervisor: Prof. Enrico Gallinucci

An **Agentic RAG** system that lets students query Erasmus Life Housing's 
data (reviews, property descriptions, and the live booking catalogue) in 
natural language. 
The system combines multi-corpus semantic retrieval over free text with autonomous 
tool calls against the operational database, orchestrated by Anthropic Claude.

---

## Context

**Erasmus Life Housing (ELH)** operates a student accommodation platform
in Lisbon and Porto. Their database has two complementary worlds:
a structured catalogue (rooms, prices, amenities, availability) and
a body of unstructured text (student reviews, property descriptions).

Standard filters serve the structured side well but cannot capture
concepts like *"quiet area"* or *"responsive landlord"* that exist only
in the free text. At the same time, factual questions about prices or
availability cannot be answered reliably from text. Real-world queries
typically need both, subjective signals from past tenants *and* hard
facts from the catalogue.

This system bridges the two: retrieval for the text, deterministic tool
calls for the structured data, unified under a single answer.

## What you can ask

```
"Find rooms where students mention a comfortable bed"
"Quiet places suitable for thesis writing"
"Available rooms in Lisbon under 500€ for January"
"Cheap rooms in central Porto that students recommend"
"Total cost for a 6-month stay starting September"
```

## Architecture

```
            Student question
                  │
                  ▼
        ┌─────────────────────┐
        │ Follow-up rewriter  │   uses conversation memory
        └──────────┬──────────┘
                   ▼
        ┌─────────────────────┐
        │   Intent router     │   Claude Haiku
        └──────────┬──────────┘
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
   ┌───────┐  ┌───────┐  ┌───────────┐
   │Reviews│  │ Descs │  │ Agentic   │
   │ (vec  │  │ (vec  │  │  tools    │
   │ + BGE │  │ + BGE │  │ (Supabase │
   │rerank)│  │rerank)│  │  SQL)     │
   └───┬───┘  └───┬───┘  └─────┬─────┘
       └─────┬────┘             │
             ▼                  ▼
      (merged sources)   (tool outputs)
             └────────┬─────────┘
                      ▼
            ┌──────────────────┐
            │ Answer (Sonnet)  │
            └──────────────────┘
```

Two separate Pinecone indices keep reviews and descriptions distinct;
a multilingual cross-encoder reranks each corpus before merging. Agentic
tools are Python functions registered against typed Pydantic schemas:
the LLM picks which tool to invoke, but the SQL is deterministic.

## Key design choices

**Dual-corpus retrieval.** Reviews and descriptions are semantically
different (subjective vs factual). Separate indices keep reranking
pools clean and enable per-source evaluation. The generation prompt is
source-aware: it knows when it's weaving subjective with factual rather
than treating both as "reviews".

**Agentic tools, not text-to-SQL.** The LLM never writes SQL. Tools
encapsulate domain logic (seasonal pricing, reservation overlap,
schema versioning) behind typed contracts. The LLM only sees the
generated JSON schema and decides which tool fits the question.

**Graceful degradation everywhere.** Every optional step has a
documented fallback: rewriter fails → original question; reranker fails
→ vector-only ranking; intent router fails → keyword heuristic, then
default to dual retrieval. A thesis system should be observable and
robust, not brittle.

## Tech stack

| Component | Choice |
|---|---|
| Language | Python 3.12 |
| Generation LLM | Anthropic Claude Sonnet |
| Auxiliary LLM | Anthropic Claude Haiku (routing, rewriting) |
| Embeddings | `paraphrase-multilingual-mpnet-base-v2` |
| Reranker | `BAAI/bge-reranker-v2-m3` (100+ languages) |
| Vector store | Pinecone (serverless) |
| Database | PostgreSQL (Supabase) |
| UI | Streamlit |
| Validation | Pydantic Settings + Pydantic tool schemas |
| Tests | pytest, offline, < 4s |

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
**dimension 768** and **cosine** similarity.

## Development

```bash
make test         # full suite, no network, no API keys needed
make test-cov     # with coverage
make lint         # ruff
make format       # ruff + autofix
```

---

**Author:** Giovanni Pisoni — *Alma Mater Studiorum Università di Bologna*
**Supervisor**: Prof. Enrico Gallinucci

*Developed for academic purposes. Private repository, not for distribution.*