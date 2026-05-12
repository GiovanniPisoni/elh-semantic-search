# Phase 3 — Tool API Specifications

**Design document.** Architecture: Hybrid Tool-augmented RAG (no Text-to-SQL).
**Status:** Decisions 1, 2, 3 closed. Decisions 4–6 open.
**Date:** May 6, 2026
**Branch:** `feature/phase3-tools`

---

## Table of contents

1. [Architecture overview](#1-architecture-overview)
2. [Cross-cutting conventions](#2-cross-cutting-conventions)
3. [Tool 1 — `find_rooms`](#3-tool-1--find_rooms)
4. [Tool 2 — `find_available_rooms`](#4-tool-2--find_available_rooms)
5. [Tool 3 — `compute_total_cost`](#5-tool-3--compute_total_cost)
6. [Tool 4 — `get_property_details`](#6-tool-4--get_property_details)
7. [Tool 5 — `get_booking_stats`](#7-tool-5--get_booking_stats)
8. [Tool 6 — `answer_policy_question` (TBD)](#8-tool-6--answer_policy_question-tbd)
9. [Phase 2 RAG fallback](#9-phase-2-rag-fallback)
10. [Decision register](#10-decision-register)

---

## 1. Architecture overview

```
                          ┌─────────────────────┐
       user query ────►   │   Orchestrator      │   ◄── Phase 2 RAG
                          │   (LLM-driven)      │       (semantic search,
                          └──────────┬──────────┘        intent router,
                                     │                   reranker, generator)
                          tool_calls │
                                     ▼
                          ┌─────────────────────┐
                          │  TOOLS_REGISTRY     │
                          │  ┌───────────────┐  │
                          │  │ Tool 1: find  │  │
                          │  │ Tool 2: avail │  │
                          │  │ Tool 3: cost  │  │
                          │  │ Tool 4: prop  │  │
                          │  │ Tool 5: stats │  │
                          │  │ Tool 6: policy│  │
                          │  └───────────────┘  │
                          └──────────┬──────────┘
                                     │
                                     ▼
                            ┌────────────────┐
                            │  PostgreSQL    │  (ELH DB: house, room,
                            │  + Pinecone    │   reservation, review, ...)
                            └────────────────┘
```

**Key architectural decision (closed):** *NO free-form Text-to-SQL*. The LLM
never produces raw SQL; it only picks among predefined tools with Pydantic
schemas. Motivation: GDPR + reliability — the ELH team explicitly stated
*"yes I prefer to change [response]"* on ambiguous queries (they prefer
to change the answer rather than return uncertain results).

**Fallback strategy:**

1. Orchestrator analyses the query → selects a tool.
2. If a tool matches with high confidence → executes the tool, returns output.
3. If no tool matches → falls back to Phase 2 RAG (existing semantic search).
4. If Phase 2 RAG cannot find relevant sources → templated message
   *"Here is what I can do: [list of capabilities]"*.

---

## 2. Cross-cutting conventions

### 2.1 Tool interface (Decision 1, closed)

Each tool is made of:

* **Input:** Pydantic class `<ToolName>Input` with runtime validation
* **Output:** frozen `dataclass` with `to_dict()` method (full) and, where
  relevant, `to_dict_for_user()` (sanitised — internal fields like
  `sql_executed` are stripped)
* **Function:** decorated with `@register_tool(name, description, input_model)`,
  receives a validated input model instance

Single-source-of-truth registration in `TOOLS_REGISTRY: dict[str, ToolSpec]`,
populated at import time. A `execute_tool(name, payload)` dispatcher
validates the payload, dispatches the function, and normalises errors
into three types: `ToolNotFoundError`, `ToolValidationError`,
`ToolExecutionError`.

File layout: `src/elh_rag/tools/{base,errors,find_rooms,find_available_rooms,...}.py`
(flat structure).

### 2.2 Entity identifiers

DB tables use composite keys
`(loc_idhouse, loc_dateupdate, idroom, dateupdate)` to support versioning
(price drift). To simplify the LLM-facing interface we use **encoded strings**:

| Kind | Format | Example |
|---|---|---|
| Room ID | `H{house_id}_R{room_id}_{ISO8601_dateupdate}` | `H42_R3_2024-09-15T10:30:00` |
| House ID | `H{house_id}_{ISO8601_dateupdate}` | `H42_2024-09-15T10:30:00` |

Encoder/decoder live in `src/elh_rag/tools/_room_id.py`.

### 2.3 Shared output dataclasses

| Dataclass | Used by |
|---|---|
| `RoomMatch` | Tool 1, Tool 2, Tool 4 (result lists) |
| `CostLineItem` | Tool 3 (breakdown line items) |
| `StatPoint` | Tool 5 (aggregated data points) |

### 2.4 Price seasonality

The ELH DB uses 3 seasonal price bands:

| Band | Months | Notes |
|---|---|---|
| `springprice` | March–June | mid-season |
| `summerprice` | July–August | low season (Erasmus students absent) |
| `autumnprice` | September–February | **Erasmus high season** |

**Default for Tool 1** (dates optional): displays `autumnprice` (most
frequent use case).
**Tool 2** (dates mandatory): computes the **weighted average across the
days** falling in each season.

### 2.5 Zone → metro line mapping

File `src/elh_rag/tools/_metro_lines.py` with static Wikipedia data (Lisbon
+ Porto). Maps zones/neighbourhoods to the metro lines that serve them.
Example:

```python
LISBON_METRO_LINES = {
    "Alameda": ["green", "red"],
    "Areeiro": ["green"],
    "Cais do Sodre": ["green"],
    "Marques de Pombal": ["yellow", "blue"],
    ...
}
```

---

## 3. Tool 1 — `find_rooms`

### 3.1 Purpose

Structured search over multiple criteria. Answers most of the informational
queries from students (~70% of expected traffic).

### 3.2 Real examples (from meeting + ELH marketing)

**Q1:** *"Rooms for couples on the green line, max 5 people"*
```json
{
  "metro_line": "green",
  "accepts_couples": true,
  "max_house_occupancy": 5
}
```

**Q2:** *"Cheapest rooms in Lisbon, internal ok"*
```json
{
  "city": "Lisbon",
  "must_have_window": false,
  "sort_by": "price_asc"
}
```

**Q3:** *"Porto, annual contract, near metro, accepts cat"*
```json
{
  "city": "Porto",
  "min_contract_months": 12,
  "max_distance_to_transport_m": 500,
  "accepts_pets": true
}
```

---

## 4. Tool 2 — `find_available_rooms`

### 4.1 Purpose

Specialisation of `find_rooms` with **dates as a hard constraint**. Runs
overlap checks against `reservation` and excludes rooms that are not
actually free in the specified window. Computes season-aware weighted
prices.

Example: a `2026-09-01 → 2027-01-31` query → 100% of days in
`autumnprice`. A `2026-05-15 → 2026-08-31` query → 47 `springprice` days
+ 62 `summerprice` days.

### 4.2 When the orchestrator picks Tool 2 vs Tool 1

| Query | Tool | Reason |
|---|---|---|
| "Rooms free from Aug 20 to Dec 31 near NOVA" | **Tool 2** | "free" + explicit dates |
| "Couples rooms green line from September" | **Tool 1** | "September" generic, no end date |
| "3 bedrooms free August 20 till end of December" | **Tool 2** | "free" + explicit range |
| "Rooms in Lisbon near metro" | **Tool 1** | no dates |

**Rule:** if the query contains verbs like *free / available* + an
explicit date range → Tool 2. Otherwise → Tool 1.

### 4.3 Real examples

**Q1** (marketing): *"3 bedrooms free Aug 20 – end of Dec close to NOVA,
3 Italian girls, max 6 ppl, female only, 500€ bills included"*

```json
{
  "available_from": "2026-08-20",
  "available_to": "2026-12-31",
  "near_landmark": "NOVA University",
  "max_house_occupancy": 6,
  "gender_preference": "female_only",
  "max_price_eur": 500,
  "num_rooms_needed": 3
}
```

---

## 5. Tool 3 — `compute_total_cost`

### 5.1 Purpose

Given a `room_id` + a period, returns the **all-in total cost** with a
per-line breakdown: season-aware monthly rent, bills, cleaning, deposit,
reservation fee, administrative tax, optional extra-person fee.

### 5.2 Cost components

| Item | Source | Type |
|---|---|---|
| Monthly rent | `room.springprice/summerprice/autumnprice` (day-weighted) | recurring |
| Bills | `expenses` table (per house) | recurring |
| Cleaning | `cleaning` table (per house) | recurring |
| Reservation fee | `compute_reservation_fee(room, months)` helper ⚠️ | **one-off** |
| Deposit | `room.depositvalue` (or `room.lastmonthdeposit` if Y) | one-off |
| Administrative tax | `room.administrativetax` | one-off |
| Extra person | `room.extrapersoncost` when `extrapersonallowed=Y` | recurring |

⚠️ **TODO from the 2026-05-06 marketing meeting:** clarify the exact
reservation-fee formula. Current state: a separate function in
`tools/_pricing.py` with a reasonable placeholder, to be updated with the
real ELH formula once known.

### 5.3 Edge case — duration < `minreservemonths`

If the requested duration is below the room's `minreservemonths`, **the
tool still computes the cost** but adds a warning to the output. Rationale:
the orchestrator can present the calculation with a disclaimer
(*"This room requires a 5-month minimum, your request is 2 — the landlord
may refuse"*), instead of forcing the decision outside the tool.

---

## 6. Tool 4 — `get_property_details`

### 6.1 Purpose

Full lookup of a **single room** or **single house** given the encoded ID.
Typically invoked as a follow-up after `find_rooms` (*"tell me more
about the first result"*).


### 6.2 Design notes

* **`kind` discriminator** rather than two separate dataclasses: simpler
  for the LLM to consume (one shape, check `kind`).
* **NO review text** in output: only numeric aggregates. For queries like
  *"what do the reviews say?"* the orchestrator routes to Phase 2 RAG
  (semantic search over the `elh-reviews` index).
* **`current_availability`**: free windows computed by inverse query
  against `reservation`, 12-month horizon.

---

## 7. Tool 5 — `get_booking_stats`

### 7.1 Purpose

Aggregated statistics for the **internal ELH team** (~20% of expected
traffic). Answers operational queries on occupancy, average duration,
top zones, customer countries, seasonal patterns.

### 7.2 GDPR constraints (from the 2026-05-05 ELH meeting)

* ✅ Read permitted: `reservation`, `house`, `room`, `review`
* ❌ Read **forbidden**: `users`, `payment`, `email`, `question`, `reply`
* Aggregates only (count, avg, distribution), **never row-level data**
* **k-anonymity with k=5**: if an aggregate is based on fewer than 5
  records, return `data_points=[]` + warning
  "insufficient data for privacy-safe aggregation"
* **Mandatory disclaimer** on every output

### 7.3 Examples

**Q1:** *"What is Lisbon's occupancy rate?"*
```json
{"metric": "occupancy_rate", "city": "Lisbon"}
```

**Q2:** *"Top 5 countries of the students?"*
```json
{"metric": "top_countries", "top_n": 5}
```

**Q3** (NOT permitted): *"Show me all January reservations"*
→ Tool 5 does NOT handle this. Falls back to a response like
*"I cannot display individual reservations"*.

---

## 8. Tool 6 — `answer_policy_question` (TBD)

### 8.1 Purpose

Knowledge base of ELH FAQ for company policies, contracts, fees,
cancellations, rules, support. Answers the **majority** of the questions
analysed from marketing (10 out of 16 = 62%).

### 8.2 Status

⏸️ **Decision 5 — OPEN.** To be defined after the marketing meeting, once
we have the full FAQ material.

### 8.3 Examples of in-scope queries (preview)

* *"Do you accept long term rental? Max and min?"*
* *"How much reservation fee will I pay?"* (generic, not for a specific room)
* *"Accept families? Young professionals?"*
* *"Overnight guests allowed? Pay extra?"*
* *"Provide contract?"*
* *"Communication with landlord after move-in?"*
* *"What if room not as listed? Cancel and refund?"*
* *"Bring my guitar?"*

### 8.4 Probable approach (to be confirmed)

* Static knowledge base loaded into Pinecone (third index or sub-namespace
  of `elh-descriptions`)
* Tool 6 performs semantic retrieval + reranking + generation, similar to
  Phase 2 RAG but over the FAQ corpus instead of descriptions
* Advantage: a typed "policy" response with explicit source citation
  ("Source: ELH Terms of Service, section 4.2")

---

## 9. Phase 2 RAG fallback

### 9.1 When the orchestrator falls back to Phase 2 RAG

* No tool matches with sufficient confidence
* Semantic/qualitative queries that do not translate into structured
  parameters
* Examples:
  * *"What do Italian students say about the Bairro Alto house?"* → review search
  * *"Cosy rooms near the nightlife"* → semantic match
  * *"Can I work in smart working from the room?"* → multiple soft criteria

### 9.2 Implementation

No change relative to Phase 2: existing pipeline
(intent_router → retriever → reranker → generator). The orchestrator
forwards the native query to the Phase 2 RAG API and presents the
`RAGResponse` directly.

---

## 10. Decision register

### 10.1 Closed decisions

| # | Topic | Outcome |
|---|---|---|
| **D1** | Tool interface | Pydantic input + frozen dataclass output + registry decorator |
| **D2** | File layout | Flat: `src/elh_rag/tools/{base,errors,find_rooms,...}.py` |
| **D3.1** | Tool 1 parameters | 29 parameters (16 structural + 11 explicit amenities + 1 generic) |
| **D3.2** | Tool 2 inheritance | `class FindAvailableRoomsInput(FindRoomsInput)` |
| **D3.3** | Season-aware pricing | Tool 1 defaults to `autumnprice`; Tool 2 uses day-weighted avg |
| **D3.4** | Shared `RoomMatch` | across Tool 1, 2, 4 |
| **D3.5** | Room ID encoding | opaque string `"H{h}_R{r}_{ISO}"` |
| **D3.6** | Tool 3 promo code | hidden (not a public parameter) |
| **D3.7** | Tool 4 discriminator | `kind` Literal + single dataclass |
| **D3.8** | Tool 5 metric | Literal of 7 fixed values (no free-form SQL) |
| **D3.9** | Tool 5 GDPR | k-anonymity k=5 + mandatory disclaimer |
| **D3.10** | Output sanitisation | `to_dict()` full + `to_dict_for_user()` sanitised |

### 10.2 Open decisions

| # | Topic | When |
|---|---|---|
| **D4** | Orchestrator decision logic (LLM tool selection, fallback threshold, prompt) | After Tool 1+2 implementation |
| **D5** | Tool 6 knowledge base policy (structure, Pinecone index, retrieval) | After ELH marketing meeting |
| **D6** | Edge cases + safety (logging, rate limiting, error handling) | Pre-merge of `feature/phase3-tools` |

### 10.3 Explicit TODOs

* ⚠️ Reservation fee formula (Tool 3): clarify at the 2026-05-06 marketing meeting
* ⚠️ FAQ knowledge base (Tool 6): request material from marketing
* ⚠️ Deployed `minreservemonths` distribution: verify mean ~5 after DB
  re-population

---

## Appendix A — Mapping real queries → tools

Synthesis of the 16 real questions received from the ELH marketing manager:

| # | Query | Tool |
|---|---|---|
| 1 | Couples + green line + max 5 ppl + Sep–Jan | `find_rooms` |
| 2 | 3 rooms + Aug 20 – end Dec + NOVA + 3 IT girls + female + 500€ (bills via descr.) | `find_available_rooms` |
| 3 | Porto + year contract + metro + accepts cat | `find_rooms` |
| 4 | "Long term rental? Max and min?" | `answer_policy` |
| 5 | "Reservation fee?" (generic) | `answer_policy` |
| 6 | "Accept families?" | `answer_policy` |
| 7 | "Strictly students or young professionals?" | `answer_policy` |
| 8 | "Overnight guests? Pay extra?" | `answer_policy` |
| 9 | "Girlfriend weekend visit, how does it work?" | `answer_policy` |
| 10 | "Cheapest rooms, internal ok" | `find_rooms` (sort_by=price_asc, must_have_window=False) |
| 11 | "Room not as listed? Cancel + refund?" | `answer_policy` |
| 12 | "Flatmate broke the rules?" | `answer_policy` |
| 13 | "Provide contract?" | `answer_policy` |
| 14 | "Communication with landlord after move-in?" | `answer_policy` |
| 15 | "Flats only for girls?" | `find_rooms` (gender_preference=female_only) |
| 16 | "Bring my guitar?" | `answer_policy` |

**Expected distribution:**
* `find_rooms` / `find_available_rooms`: 6/16 (38%)
* `answer_policy_question`: 10/16 (62%)

This confirms the meeting's intuition: **policy is as important as search**.
