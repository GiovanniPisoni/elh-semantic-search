# Phase 2 — Design Document

## Second corpus (house + room descriptions) with intent routing

**Status:** ✅ completed (April 2026) — see Section 10 for the implementation summary
**Author:** Giovanni Pisoni
**Last updated:** April 2026

---

## 1. Motivation

Phase 1 indexed only student reviews (~3% of bookings), yielding a corpus
of experiential but narrow content. Step 4 introduces a **second corpus**
sourced from the property catalogue, complementary in nature:

| Aspect | Reviews corpus | Descriptions corpus |
|---|---|---|
| Authored by | Students, post-stay | ELH property managers |
| Style | Narrative, subjective | Descriptive, factual |
| Content | Experience, neighbours, issues | Amenities, prices, m², distances |
| Volume | ~3% booking ratio | 104 houses + 351 rooms = 455 docs |
| Coverage | Sparse, polarised | Complete, curated |

The two corpora are **strongly complementary**: reviews answer "what was
it like?", descriptions answer "what is it?". A routing layer decides
which corpus to query based on the user's intent.

## 2. Architectural decisions

### 2.1 Storage: two separate Pinecone collections

- `elh-reviews` (existing) — 768-dim, multilingual embeddings of review text
- `elh-descriptions` (new) — same embedding model, indexed from `house.description` and `room.description`

**Rationale:** semantic heterogeneity. Reviews and descriptions produce
different embedding distributions — keeping them in separate collections
yields cleaner reranking pools and simpler A/B evaluation per source.

### 2.2 Extractor: `Extractor` protocol + two implementations

```python
class Extractor(Protocol):
    def extract(self) -> Iterable[Document]: ...
```

Two concrete implementations:

- `ReviewExtractor` — the existing extractor, refactored to implement the protocol
- `DescriptionExtractor` — new, joins `house` and `room`, emits one document per property/room

**Rationale:** evolves the `VectorStore` Protocol pattern from Phase 1 to
the data ingestion layer. Adding a future `QuestionReplyExtractor` (for
the `question`/`reply` tables) becomes a matter of implementing the
protocol — no changes to existing code.

### 2.3 Three typed metadata schemas

- `ReviewMetadata` (existing, unchanged)
- `HouseMetadata` (new) — fields: idhouse, flatname, city, zone, neighbourhood, etc.
- `RoomMetadata` (new) — fields: idroom, roomname, idhouse (FK), area, beds, etc.

**Rationale:** explicit schemas serve as implicit documentation. A single
generic `DocumentMetadata` with 40 optional fields (most always empty)
would hide the domain model behind a grab-bag of nulls.

### 2.4 Intent routing with LLM classifier + confidence threshold

A new `IntentRouter` module calls Claude Haiku with the following signature:

```python
@dataclass(frozen=True)
class RoutingDecision:
    intent: Literal["review", "description", "both"]
    confidence: float  # 0.0 - 1.0
    reasoning: str     # one-line explanation for logging
```

**Decision rule:**
- `confidence >= 0.8` and `intent in {"review", "description"}` → query only that corpus
- Otherwise → query both and let the reranker merge

**Fallback:** on LLM failure, a keyword-based heuristic decides (words
like "felt", "experience", "landlord" → reviews; "price", "m²",
"amenities" → descriptions; otherwise "both").

**Rationale:** keeps the system non-brittle while allowing the "sometimes
single, sometimes dual" behaviour that's architecturally more interesting
than "always dual".

### 2.5 Pipeline: Orchestrator + specialised pipelines

Drops the single `RAGPipeline` in favour of a separated architecture:

```
                    User question
                         │
                         ▼
                  ┌──────────────┐
                  │ Orchestrator │
                  └──────┬───────┘
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
  ReviewsPipeline              DescriptionsPipeline
  (query-rewriting,            (query-rewriting,
   Pinecone elh-reviews,        Pinecone elh-descriptions,
   rerank)                      rerank)
```

**Components:**

- `ReviewsPipeline` — the current `RAGPipeline` refactored and renamed. Same internal steps (rewrite → retrieve → rerank → **return sources only**, no LLM generation at this level).
- `DescriptionsPipeline` — new, same interface, different collection.
- `Orchestrator` — the new brain:
  1. Calls `IntentRouter` to decide which pipeline(s) to activate
  2. Calls each active pipeline to get its retrieved sources
  3. Merges sources into a unified context
  4. Calls the generation LLM with the merged context + original question
  5. Returns a single `RAGResponse` with `sources_by_source: {reviews: [...], descriptions: [...]}`

**Rationale:** the Orchestrator pattern scales to Phase 3 (tool calling)
by simply registering new "tools" (GeoTool, PriceTool, etc.) alongside
the pipelines. The specialised pipelines stay simple, testable, and
reusable in isolation.

### 2.6 Pinecone metadata: location-only

Store in Pinecone `metadata`:
- `source` — enum: `review | house | room`
- `id`, `city`, `zone`, `neighbourhood` — for filtering queries like "only in Porto"

Do **not** store structured fields (price, m², amenity flags). Those are
Phase 3's territory (tool calling on Supabase).

**Rationale:** keeps Pinecone lean, prevents overloading the vector store
with a poor-man's SQL. Location filtering has obvious value for retrieval
("rooms in Porto" → pre-filter before rerank); structured queries want a
real database, not a JSON filter.

## 3. Document indexing strategy

### 3.1 House document

```text
[HOUSE — {flatname}]
Location: {city}, {zone}, {neighbourhood}

{description_raw}
```

- Embedded text: the whole block above (~900 chars on average)
- No chunking (max observed is 1338 chars — well within embedder context)
- Pinecone ID: `house:{idhouse}`

### 3.2 Room document

```text
[ROOM — {roomname} in house {flatname}]
Location: {city}, {zone}, {neighbourhood}

{description_raw}
```

- Embedded text: same pattern (~600 chars on average)
- No chunking (max 1052 chars)
- Pinecone ID: `room:{idroom}`

**Why narrative headers:** gives the embedder + cross-encoder additional
lexical hooks ("HOUSE", "ROOM") that help reranking when queries are
ambiguous ("I need a place" could be either).

## 4. Code structure

### New files

```
src/elh_rag/
├── data/
│   ├── extractor.py           # already exists, will hold the Protocol
│   ├── review_extractor.py    # renamed from current extractor.py
│   └── description_extractor.py  # NEW
├── retrieval/
│   ├── query_rewriter.py
│   ├── reranker.py
│   └── intent_router.py       # NEW
├── orchestration/             # NEW subpackage
│   ├── __init__.py
│   ├── orchestrator.py        # NEW — main entry point
│   ├── reviews_pipeline.py    # NEW — refactor of current pipeline.py (retrieval only)
│   └── descriptions_pipeline.py  # NEW — mirror of reviews_pipeline
├── schemas.py                 # UPDATE — add HouseMetadata, RoomMetadata, DocumentSource
└── pipeline.py                # LEGACY — kept as facade, delegates to Orchestrator
```

### Modified files

- `src/elh_rag/schemas.py` — new metadata classes, `RAGResponse` gets `sources_by_source`
- `src/elh_rag/config.py` — new env vars for descriptions index + intent router
- `.env.example` — new env vars
- `src/elh_rag/generation/prompts.py` — prompt for intent classifier
- `src/elh_rag/ui/components/results_panel.py` — render both source types
- `scripts/run_indexer.py` — add `--source` flag (reviews | descriptions | all)

### Tests

- `tests/test_description_extractor.py` — new (with fake DB)
- `tests/test_intent_router.py` — new (with fake LLM)
- `tests/test_orchestrator.py` — new (with fake pipelines)
- `tests/test_reviews_pipeline.py` — renamed from test_pipeline.py
- `tests/test_descriptions_pipeline.py` — new
- `tests/conftest.py` — add fake fixtures for new components
- `tests/test_schemas.py` — add tests for new metadata classes

## 5. Environment variables (new)

```bash
# Descriptions corpus
PINECONE_DESCRIPTIONS_INDEX_NAME=elh-descriptions

# Intent routing
ENABLE_INTENT_ROUTING=true          # toggle for A/B: on → smart, off → always query both
INTENT_ROUTER_MODEL=claude-haiku-4-5-20251001
INTENT_ROUTER_CONFIDENCE_THRESHOLD=0.8
```

## 6. Commit plan

8 atomic commits on branch `feature/phase2-step4-second-corpus`:

1. **feat(schemas)**: add HouseMetadata, RoomMetadata, DocumentSource enum expansion
2. **feat(data)**: add Extractor protocol + rename ReviewExtractor
3. **feat(data)**: add DescriptionExtractor with JOIN on house/room
4. **feat(indexing)**: extend run_indexer.py with --source flag
5. **feat(retrieval)**: add IntentRouter with LLM classifier + keyword fallback
6. **feat(orchestration)**: introduce Orchestrator + ReviewsPipeline + DescriptionsPipeline (refactor of pipeline.py)
7. **feat(ui)**: render sources_by_source in chat view
8. **docs**: update README + architecture diagram for Phase 2 Step 4 completion

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Intent classifier is the new latency bottleneck (~1-2s per query) | Cache with lru_cache(128), mirroring query_rewriter pattern |
| Classifier always returns "both" with low confidence | Good: graceful degradation, system still works |
| Orchestrator becomes a god-class over time | Orchestrator stays thin: only routing + merging, no business logic |
| Refactor breaks existing tests | Aggressive test-first approach; keep old pipeline.py as delegating facade for backward compat |
| Supabase description.length grows and exceeds embedder context (currently 1338 max) | Chunking is Step 3 of Phase 2, ready to be activated |

## 8. Success criteria (qualitative, pre-Phase 4)

- 455 descriptions indexed successfully in Pinecone
- Intent router correctly identifies "pure" intents (tested on handcrafted query set)
- End-to-end query on descriptions returns sensible results (e.g., "room under €500" finds low-price rooms)
- Orchestrator produces a response with clearly separated sources in UI
- All existing tests still pass; new tests ≥80% coverage on new modules

## 9. Out of scope

- **Chunking** — deferred to Phase 2 Step 3 (icon 🔍 in roadmap), conditional on Phase 4 results
- **Structured filters** (price, amenity flags) — Phase 3 (tool calling)
- **Question/Reply corpus** — future extension
- **Conversational memory** — Phase 2, Step 5
- **Performance optimization** (ONNX, quantization) — Phase 5 if needed for deployment

## 10. Implementation outcome (filled in at Step 4F)

**Final status:** ✅ **Completed**, April 2026.

This section closes the design doc by mapping each planned item to the
file(s) that implement it, plus deviations from the original plan.

### 10.1 What landed where

| Plan | Implementation | Notes |
|---|---|---|
| `Extractor` protocol | `src/elh_rag/data/extractor.py` | PEP 544 protocol, no inheritance |
| `ReviewExtractor` | `src/elh_rag/data/review_extractor.py` | Refactored from Phase 1 |
| `DescriptionExtractor` | `src/elh_rag/data/description_extractor.py` | Two SQL queries, mixed stream of HouseMetadata + RoomMetadata |
| `HouseMetadata`, `RoomMetadata` | `src/elh_rag/schemas.py` | Frozen dataclasses, dispatched via `metadata_from_pinecone_dict` |
| Source-agnostic indexer | `src/elh_rag/indexing/indexer.py` | Accepts any `Extractor` + `VectorStore` via DI |
| `--source` CLI flag | `scripts/run_indexer.py` | reviews / descriptions / all |
| `IntentRouter` | `src/elh_rag/retrieval/intent_router.py` | Haiku-based, with keyword + default fallback cascade |
| `RoutingDecision` | `src/elh_rag/schemas.py` | Carries intent + confidence + source ('llm' / 'keyword' / 'default') |
| `Orchestrator` + per-corpus pipelines | `src/elh_rag/orchestration/` | New subpackage, 4 modules |
| Backward-compatible facade | `src/elh_rag/pipeline.py` | Old `RAGPipeline` API preserved on top of `Orchestrator` |
| UI: source-type badge + debug expander | `src/elh_rag/ui/components/property_card.py`, `results_panel.py` | Badge styled per source kind, expander shows routing decision |

### 10.2 Deviations from the original plan

1. **Status filters per table.** The plan assumed both `house.status` and
   `room.status` would use the value `'approved'`. Live inspection of the
   ELH Supabase showed `house.status='Validated'` and `room.status='Available'`.
   `DescriptionExtractor` accepts two distinct status filters in its
   constructor.

2. **Versioning via `DISTINCT ON`.** Not foreseen in the plan: ELH keeps
   historical versions of houses and rooms in the same tables, identified
   by composite key `(id, dateupdate)`. Without `DISTINCT ON` deduplication,
   Pinecone silently kept only one version per id (often not the most
   recent), which produced the off-by-105 mismatch documented in the
   benchmark observations. The fix lives in the SQL queries of
   `DescriptionExtractor`, taking the row with the most recent `dateupdate`
   per logical entity. Final corpus size: **80 unique houses + 270 unique
   rooms = 350 descriptions** (down from the 455 the plan had estimated).

3. **Pinecone upsert robustness.** Added chunking (50 vectors per upsert)
   + sleep + exponential backoff retry to `PineconeVectorStore.upsert`,
   not in the original plan but proved necessary during indexing
   smoke tests (silent vector drops on larger batches).

4. **Source-aware generation prompt.** Added
   `MULTICORPUS_SYSTEM_PROMPT` and `_select_prompts` helper. Reviews-only
   responses keep the original Phase 1 prompt; mixed or descriptions-only
   responses get a multi-corpus prompt that knows to weave subjective and
   factual sources without calling everything "reviews".

5. **Parallel retrieve experiment, then rolled back.** Implementation
   detail not in the plan: tried `ThreadPoolExecutor` to parallelise
   the two pipelines on `intent=both`. Benchmark in four configurations
   (with/without parallelism × with/without reranker) showed the parallel
   path is consistently slower or equal, never faster. Rolled back to
   sequential. Full analysis in `phase2_step4_observations.md`.

### 10.3 Final test count

**154 unit tests passing offline** in ~1s (was 100 before Step 4):
- +12 indexer (source-agnostic)
- +30 intent router (LLM + keyword + edge cases)
- +13 orchestrator (routing × pipelines × merge)
- +19 description extractor
- +20 schemas (HouseMetadata, RoomMetadata, dispatcher, RoutingDecision)
- +3 prompt selection (Step 4F)
- assorted updates to existing tests

### 10.4 Production validation

Running the orchestrator benchmark on 20 curated multilingual queries
(Run A, sequential + reranker + routing):

- Routing accuracy vs hand-labelled expected intent: **19/20 (95%)**
- Median latency: **23.7s**  ·  p95: **36.4s**
- Estimated cost: **$0.015 / query** end-to-end

Both Pinecone collections stable in production:
- `elh-reviews`: 358 vectors
- `elh-descriptions`: 350 vectors

Step closes Phase 2 Step 4. Next: Phase 2 Step 5 (conversational memory).
