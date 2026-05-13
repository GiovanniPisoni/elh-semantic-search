# Phase 3 — Outcomes & Implementation Notes

**Companion document to `phase3.md` (design).**
This file records what was actually built, the decisions that emerged during
implementation, the deltas relative to the design, and the smoke certification
that validates each tool against the live ELH database.

| Field | Value |
|---|---|
| **Status** | All six tools implemented, 31/31 live-DB smoke scenarios green, D6 safety decisions closed |
| **Last revision** | May 14, 2026 |
| **Branch** | `feature/phase3-tools` |
| **Test baseline** | 767 unit tests green |
| **Deadline** | May 30, 2026 (16 days remaining) |

---

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [Tools delivered — quick reference](#2-tools-delivered--quick-reference)
3. [Cross-cutting conventions — ACTUAL](#3-cross-cutting-conventions--actual)
4. [Per-tool outcomes](#4-per-tool-outcomes)
5. [Structural refactor — six commits](#5-structural-refactor--six-commits)
6. [Decisions that emerged during implementation](#6-decisions-that-emerged-during-implementation)
7. [Smoke certification — 31/31 scenarios on production DB](#7-smoke-certification--3131-scenarios-on-production-db)
8. [Validation figures for the thesis](#8-validation-figures-for-the-thesis)
9. [Cosmetic fixes closed pre-merge](#9-cosmetic-fixes-closed-pre-merge)

---

## 1. Executive summary

Phase 3 delivered six LLM-callable tools that cover the structured-search,
cost-quotation, property-lookup, internal-statistics, and FAQ branches of the
ELH agentic RAG. The Phase 2 semantic-RAG pipeline remains the fallback for
qualitative/review queries, as specified in the design document.

All tools were implemented in the same idiom: a Pydantic input model, a frozen
dataclass output, a function decorated with `@register_tool`, and a thin
context object (`Psycopg2Executor` for the SQL tools, `KBContext` for Tool 6)
injected by the caller. The original design intent (D1, D3.1–D3.10) was held
intact; one structural decision (D2, "flat file layout") was deliberately
reversed during a six-commit refactor in favour of a per-tool subpackage
layout — see §5 for the rule that drove the change.

Three operational facts emerged after the design freeze:

1. The reservation-fee formula was confirmed by the ELH owner at the
   2026-05-11 meeting: **9 % of the total rent over the stay**. The
   placeholder in `tools/_shared/pricing.py` was replaced with the real
   constant.
2. The k-anonymity output shape (D3.9) was refined: instead of returning
   `data_points=[]` when a bucket falls below k=5, the tool returns the
   visible buckets and reports a `suppressed_buckets` count plus a warning.
   The privacy guarantee is preserved (no row-level data and no
   small-bucket label is ever leaked); the response remains useful.
3. The pricing semantics for cross-season stays were locked as:
   each calendar month touched by the stay is billed in full at its
   seasonal rate. The user-facing average is the mean of the per-month
   rents. This is more intuitive for students than a day-weighted average,
   and aligns with the way the marketing team quotes prices.

Tool 6 (`answer_policy_question`) was kept TBD at design time (D5 open).
During implementation it was built on a multilingual sentence-transformer
(`paraphrase-multilingual-mpnet-base-v2`) over a 26-entry YAML knowledge
base. Smoke scenarios in English, Italian, and Portuguese all returned the
expected match; Portuguese confidence is borderline at 0.57 and is flagged
as a tuning target for Phase 4.

Two cosmetic findings are deferred post-merge: the human-readable
`query_summary` of Tool 1/2 omits `must_have_*` amenity filters, and the
`accepts_couples` filter is shown in the summary even when the underlying
column does not exist (the filter is correctly skipped at the SQL layer and
a warning is emitted — see D6 below). Neither is blocking.

---

## 2. Tools delivered — quick reference

| # | Tool name | Package | Files | Smoke scenarios | Status |
|---|---|---|---|---|---|
| 1 | `find_rooms` | `tools/find_rooms/` | 5 | 6/6 | ✓ |
| 2 | `find_available_rooms` | `tools/find_available_rooms/` | 2 | 6/6 | ✓ |
| 3 | `compute_total_cost` | `tools/compute_total_cost/` | 2 | 3/3 | ✓ |
| 4 | `get_property_details` | `tools/get_property_details/` | 3 | 3/3 | ✓ |
| 5 | `get_booking_stats` | `tools/get_booking_stats/` | 5 | 7/7 | ✓ |
| 6 | `answer_policy_question` | `tools/answer_policy_question/` | 5 + YAML KB | 6/6 | ✓ |

Naming convention (locked): `@register_tool(name="find_rooms")` uses the
semantic name. The earlier convention `tool1_find_rooms`, which numbered
the tools, was explicitly rejected because numbers carry no meaning for
the LLM. The numbering survives only in this document and in the smoke-test
filenames for readability.

---

## 3. Cross-cutting conventions — ACTUAL

This section records the actual conventions in place at the end of Phase 3,
making explicit where they differ from the design document.

### 3.1 Per-tool subpackage layout (revises D2)

The design called for a flat file layout under `src/elh_rag/tools/`. During
implementation, Tool 5 and Tool 6 grew large enough that single-file modules
became unreadable: `get_booking_stats` ended at ~1100 lines, mixing input
models, SQL builders, metric registrations, and the k-anonymity filter.
A six-commit refactor (see §5) converted every tool to a uniform subpackage:

```
src/elh_rag/tools/
├── _shared/                      # cross-tool helpers (DB exec, room ID,
│   ├── __init__.py               #  metro mapping, seasonal pricing)
│   ├── db.py
│   ├── room_id.py
│   ├── metro_lines.py
│   └── pricing.py
├── find_rooms/
├── find_available_rooms/
├── compute_total_cost/
├── get_property_details/
├── get_booking_stats/
├── answer_policy_question/
│   └── kb/policies.yaml          # knowledge base, deployed with the tool
├── __init__.py                   # re-exports for backward compatibility
├── base.py                       # @register_tool, ToolSpec, TOOLS_REGISTRY
└── errors.py                     # three normalised error types
```

The rule applied to decide when to subpackage and when to keep a single file
was made explicit during the refactor:

> **Subpackage when a tool has more than two distinct concerns (e.g. input
> models, SQL builders, business logic, post-processing) and the resulting
> file would exceed ~200 cohesive lines. Otherwise keep a single file.**

This produced an intentionally asymmetric layout: `find_available_rooms`
and `compute_total_cost` have two files because their domain logic is
narrow (only reservation overlap, only expenses lookup); `find_rooms`,
`get_booking_stats`, and `answer_policy_question` have five files each.

Each tool's public surface is preserved by `__init__.py` re-exports:

```python
# src/elh_rag/tools/find_rooms/__init__.py
from .tool import find_rooms
from ._inputs import FindRoomsInput
from ._schemas import FindRoomsOutput, RoomMatch

__all__ = ["find_rooms", "FindRoomsInput", "FindRoomsOutput", "RoomMatch"]
```

Tests and smoke scripts therefore still write
`from elh_rag.tools.find_rooms import FindRoomsInput`, even though the
class itself lives in `_inputs.py`. The leading underscore on internal
files (`_inputs.py`, `_schemas.py`, ...) marks them as private to the
subpackage; the `_shared/` directory uses the same convention but
without a leading underscore on the files inside it, because the
directory name itself already signals the privacy boundary.

### 3.2 Room ID encoding — actual format (refines D3.5)

The design specified a placeholder format `H{h}_R{r}_{ISO}`. The actual
encoding is **pipe-delimited**, using the original ELH string identifiers
rather than integers:

| Kind | Format | Example |
|---|---|---|
| Room ID | `{idhouse}|{idroom}|{ISO8601_dateupdate}` | `HSE_00F7359B|RM_HSE_00F7359B_1|2022-04-30T00:00:00` |
| House ID | `{idhouse}|{ISO8601_dateupdate}` | `HSE_00F7359B|2022-04-30T00:00:00` |

The pipe was chosen for three reasons: (a) it does not appear in any
existing ID, (b) it survives JSON serialisation unchanged, and
(c) it is unambiguous in human-readable LLM transcripts.

The encoder lives in `tools/_shared/room_id.py` with two functions:
`encode_room_id(idhouse, idroom, dateupdate)` and the decoder
`decode_room_id(encoded)` that returns a `RoomID` namedtuple with the
three components.

### 3.3 Model B seasonal pricing (new convention, not in design)

The design (D3.3) called for "weighted average across the days falling in
each season". After review, this was replaced with the simpler **Model B**:

> **Every calendar month touched by the requested stay is billed in full
> at its seasonal rate. The displayed `price_per_month_eur` is the mean
> of the per-month rents over the requested window.**

Season month sets, defined in `tools/_shared/pricing.py`:

```python
SPRING_MONTHS = {3, 4, 5, 6}        # March–June
SUMMER_MONTHS = {7, 8}              # July–August
AUTUMN_MONTHS = {9, 10, 11, 12, 1, 2}  # September–February
```

Examples verified arithmetically by the Tool 2 smoke (§7):

* `2026-05-15 → 2026-08-31` → 4 months touched (May, Jun, Jul, Aug)
  → 2 spring + 2 summer → (2 × 435 + 2 × 390) / 4 = **412.50 €/mo**
* `2026-09-01 → 2027-07-31` → 11 months touched (Sep–Feb autumn + Mar–Jun
  spring + Jul summer) → (6 × 510 + 4 × 435 + 1 × 390) / 11
  = 5190 / 11 = **471.82 €/mo**

Tool 2's `RoomMatch` carries an extra field `price_label: str` with a
context-rich, user-facing description, e.g.:

```
"€412.50/month average over 4 months: 2 months at spring rate €435.00,
 2 months at summer rate €390.00"
```

The label is what the orchestrator surfaces to the user; the numeric mean
is what the LLM compares against budget filters.

### 3.4 k-anonymity behaviour — actual shape (refines D3.9)

The design specified that buckets below the k=5 threshold should result in
an empty `data_points` list with a warning. In practice this loses
useful information: a query like *"average rating by Lisbon zone"* should
not be rejected wholesale just because two of the fifteen zones have fewer
than five reviews.

The actual implementation returns the visible buckets and reports the
hidden ones as a counter:

```python
@dataclass(frozen=True)
class GetBookingStatsOutput:
    metric: str
    summary: str
    data_points: list[StatPoint]      # visible buckets only
    total_underlying_rows: int        # includes hidden rows
    suppressed_buckets: int           # number of buckets hidden by k-anonymity
    warnings: list[str]               # one entry when suppressed_buckets > 0
    disclaimer: str                   # mandatory privacy disclaimer
```

Example output for `avg_overall_rating` grouped by Lisbon zones (smoke
scenario 6 of Tool 5):

```
Summary           : avg_overall_rating: 12 buckets (2 suppressed for k-anonymity).
Total rows        : 219
Suppressed buckets: 2
Warnings          : ["2 bucket(s) suppressed by k-anonymity filter (k=5)"]
Data points       : 12 zones with n ≥ 5
```

The privacy guarantee is preserved: no row-level data is exposed, no
suppressed-bucket label is included, and the underlying row count is
honest about the data behind the aggregate. The disclaimer remains
mandatory on every response.

### 3.5 Shared dataclasses — actual

The design listed three shared dataclasses (`RoomMatch`, `CostLineItem`,
`StatPoint`). The actual code adds one more and refines the original three:

| Dataclass | Module | Used by | Notes |
|---|---|---|---|
| `RoomMatch` | `find_rooms/_schemas.py` | Tool 1, Tool 2 | `price_label` field added for Tool 2 |
| `MonthlyRent` | `compute_total_cost/_expenses.py` | Tool 3 | per-month breakdown |
| `StatPoint` | `get_booking_stats/_models.py` | Tool 5 | adds `sample_size: int` for n |
| `PolicyMatch` | `answer_policy_question/_models.py` | Tool 6 | retrieval result with confidence |

`CostLineItem` from the design was deliberately not introduced: the cost
breakdown is exposed via two clearer surfaces in
`ComputeTotalCostOutput` — `monthly_recurring_eur` (when the stay sits in
a single season) or `monthly_breakdown: list[MonthlyRent]` (when it
crosses seasons), plus a flat `one_time_at_checkin_eur` for the
administrative tax. This matched the natural shape of the data better
than a heterogeneous list of line items.

---

## 4. Per-tool outcomes

For each tool: the actual subpackage layout, the input parameters that
ended up in production, the runtime decisions taken during implementation,
and the smoke-test results that exercise the tool against the live ELH
production database.

### 4.1 `find_rooms` (Tool 1)

#### Package layout

```
src/elh_rag/tools/find_rooms/
├── __init__.py              # re-exports FindRoomsInput, FindRoomsOutput,
│                            #   RoomMatch, find_rooms
├── _inputs.py               # Pydantic FindRoomsInput (29 fields)
├── _schemas.py              # frozen dataclass FindRoomsOutput + RoomMatch
├── _amenity_columns.py      # mapping must_have_* → DB column name
├── _sql_builder.py          # WHERE clause assembly, query_summary builder
└── tool.py                  # @register_tool decorated entry point
```

#### Input parameters (29 total)

The 29 parameters split into three groups:

* **16 structural filters**: `city`, `metro_line`, `max_price_eur`,
  `min_price_eur`, `gender_preference`, `accepts_pets`, `accepts_couples`,
  `accepts_smoking`, `min_contract_months`, `max_distance_to_transport_m`,
  `min_internet_speed_mbps`, `min_area_sqm`, `bed_type`, `max_house_occupancy`,
  `night_guests_allowed`, `sort_by`.
* **11 explicit amenity flags** prefixed `must_have_*`: `private_bathroom`,
  `balcony`, `washing_machine`, `dishwasher`, `air_conditioning`,
  `heating`, `furnished`, `desk`, `window`, `parking`,
  `kitchen_equipment`.
* **1 generic limit**: `max_results` (default 10, capped at 50).

#### Runtime decisions

* **`bills_included` removed.** The design (Appendix A) showed a
  `bills_included` filter for query Q2. The column does not exist in the
  ELH schema (bills are an attribute of the `expenses` table, joined per
  house, not a boolean on `room`). The filter was dropped from the
  Pydantic schema and is **not** silently translated; the orchestrator is
  expected to route bills questions to `answer_policy_question` or surface
  the per-room `expenses` from Tool 3.
* **`accepts_couples` silent-skip.** The column likewise does not exist
  in the production schema. The Pydantic field was kept (the LLM commonly
  asks this), but `_sql_builder.py` skips it at WHERE-clause time and
  emits a `logger.warning` with the message
  `find_rooms: accepts_couples=True ignored — column not present in
  the ELH schema.` This is the D6 "silent-skip with audit-log" pattern
  applied generally; see §6 for the full list of skipped filters.
* **`max_house_occupancy` silent-skip.** Same pattern, same reason.
* **`sort_by="price_asc"` uses the autumn column.** Without a date
  constraint, Tool 1 sorts on `autumnprice` (the Erasmus high-season
  default). Tool 2 reorders on the season-aware mean.

#### Smoke results (6/6 green)

| # | Scenario | Matches | Notes |
|---|---|---|---|
| 1 | Lisbon baseline | 10 (capped) | Intendente dominates (€410–€615) |
| 2 | Porto B (=red) + accepts_pets | 0 | restrictive combination, expected |
| 3 | private bath + balcony + ≤600€ | 2 | Santos €580, Anjos €565 |
| 4 | sort price_asc top 3 (Lisbon) | 3 | €370 / €380 / €385 ✓ |
| 5 | min_price_eur=10000 | 0 | impossible filter, expected |
| 6 | 5-filter marketing query | 0 + warning | `accepts_couples` skip audit-logged |

### 4.2 `find_available_rooms` (Tool 2)

#### Package layout

```
src/elh_rag/tools/find_available_rooms/
├── __init__.py             # re-exports FindAvailableRoomsInput,
│                           #   find_available_rooms (reuses FindRoomsOutput)
├── _reservation.py         # reservation overlap CTE + price computation
└── tool.py                 # @register_tool entry point
```

The tool inherits `FindAvailableRoomsInput(FindRoomsInput)` and adds two
mandatory fields:

```python
available_from: date
available_to:   date
```

#### Runtime decisions

* **Model B applied to every room.** The seasonal mean is computed in
  Python (not in SQL), so the per-room `price_label` can be rendered
  with full month-by-month context. The SQL query returns the three
  seasonal columns; the post-processing in `_reservation.py` decides the
  monthly schedule and the mean.
* **Reservation overlap as a CTE.** The exclusion of booked rooms uses a
  `NOT EXISTS` against `reservation` with overlap predicate
  `(daystart, dayend) ∩ (available_from, available_to)`. No date-range
  GiST index is required: the production set is small enough that a
  sequential scan with a `WHERE house_idhouse = ...` correlation is fast.
* **Fixed-price detection.** When a room's three seasonal columns are
  equal, the label collapses to
  `"€XXX.00/month (fixed rate, no seasonal variation)"`. Detection is
  arithmetic, not a database flag.

#### Smoke results (6/6 green)

| # | Window | Mean / label | Verification |
|---|---|---|---|
| 1 | Sep 2026 → Jan 2027 | €510.00 "5-month stay (all autumn rate)" | autumn pure |
| 2 | Jul → Aug 2026 | €390.00 "2-month stay (all summer rate)" | summer pure |
| 3 | May 15 → Aug 31 2026 | €412.50 (2 spring + 2 summer) | (2×435 + 2×390)/4 ✓ |
| 4 | Sep 2026 → Jul 2027 | €471.82 (6 autumn + 4 spring + 1 summer) | (6×510 + 4×435 + 1×390)/11 ✓ |
| 5 | Lisbon green + bath, Sep → Dec | €510.00 "4-month stay (all autumn rate)" | autumn pure |
| 6 | Porto min=5000, Sep → Jan | 0 matches | impossible, expected |

### 4.3 `compute_total_cost` (Tool 3)

#### Package layout

```
src/elh_rag/tools/compute_total_cost/
├── __init__.py             # re-exports ComputeTotalCostInput,
│                           #   ComputeTotalCostOutput, compute_total_cost
├── _expenses.py            # expenses table lookup + utility classification
└── tool.py                 # @register_tool entry point + cost assembly
```

#### Runtime decisions

* **Reservation fee = 9 % of the total rent.** Confirmed by the ELH owner
  at the 2026-05-11 meeting. The constant `RESERVATION_FEE_RATE = 0.09`
  lives in `tools/_shared/pricing.py`. The fee is computed as
  `0.09 × (mean_monthly_rent × stay_months)` and presented as
  refundable-only-if-the-room-does-not-match-the-listing.
* **Utility classification rule (from boss meeting).** A row in the
  `expenses` table with `maximumvalue NOT NULL` means the utility **is
  included** in the rent up to that monthly cap; a row with
  `maximumvalue NULL` means the utility is **excluded** and the tenant
  pays the provider directly. `_expenses.py` partitions the expenses
  list accordingly into `utilities_included` and `utilities_excluded`.
* **Administrative tax → landlord, not ELH.** `administrativetax` is a
  one-off paid at check-in directly to the landlord. The note in the
  output makes this explicit and reminds the tenant to request an invoice
  from the landlord.
* **Deposit semantics.** `deposit` + `depositvalue` denote a refundable
  security deposit; `lastmonthdeposit='Y'` denotes the last month's rent
  paid upfront. The two are independent and can coexist on the same room.
  The output surfaces both in the notes.
* **Extra person: one-off, opt-in.** When `extrapersonallowed='Y'`,
  `extrapersoncost` is added as a one-off (per stay), not per month, and
  only when the caller passes `extra_person=True`. Default is `False`.
* **VAT always included.** Every numeric figure in the output is VAT-in.
  A note at the end of the output makes this explicit.
* **Cross-season presentation.** Single-season stays return
  `monthly_recurring_eur`; cross-season stays return
  `monthly_breakdown: list[MonthlyRent]` with `year`, `month`, `season`,
  `rent_eur` per entry.

#### Smoke results (3/3 green, chained Tool 2 → Tool 3)

The smoke first picks a real room with Tool 2, then computes the cost on
the same window. All scenarios picked Cosy Home Lisbon Intendente
(`HSE_00F7359B|RM_HSE_00F7359B_1|2022-04-30T00:00:00`).

| # | Stay | Months | Payable at booking | Reservation fee | Breakdown |
|---|---|---|---|---|---|
| 1 | Sep–Nov 2026 (autumn) | 3 | €637.70 | €137.70 | `monthly_recurring` €510.00 |
| 2 | Jan–Apr 2027 (cross) | 4 | €670.10 | €170.10 | 2 × €510 autumn + 2 × €435 spring |
| 3 | Sep 2026–Feb 2027 + extra person | 6 | €835.40 | €275.40 | `monthly_recurring` €510.00 + €60 one-off |

All three scenarios surfaced:

* `utilities_included = ["Gas (up to €30.00/mo)", "Water (up to €15.00/mo)"]`
* `utilities_excluded = ["Maintenance (not included — paid to provider)"]`
* security deposit €500.00 refundable
* administrative fee €150.00 to the landlord at check-in
* VAT-inclusive disclaimer

Reservation fee arithmetic verification:

* Scenario 1: 0.09 × 510 × 3 = **137.70 €** ✓
* Scenario 2: 0.09 × (2×510 + 2×435) = 0.09 × 1890 = **170.10 €** ✓
* Scenario 3: 0.09 × 510 × 6 = **275.40 €** ✓

### 4.4 `get_property_details` (Tool 4)

#### Package layout

```
src/elh_rag/tools/get_property_details/
├── __init__.py             # re-exports GetPropertyDetailsInput,
│                           #   GetPropertyDetailsOutput, get_property_details
├── _property_details.py    # combined: SQL fetchers + dataclass models
│                           #   for House, Room, RoomSummary
├── _reviews_aggregate.py   # k-anonymity-aware review aggregation
└── tool.py                 # @register_tool entry point + dispatch on kind
```

`_property_details.py` is the largest file in the tool (~250 lines). It was
intentionally **not** split further: it carries the three House/Room/
RoomSummary models together with their fetchers, because the three concerns
are tightly coupled and splitting them would have introduced cross-file
data classes without separating logic. This is the application of the
"subpackage when more than two concerns" rule applied negatively.

#### Runtime decisions

* **Single output shape with `kind` discriminator.** The output is a
  `GetPropertyDetailsOutput` whose `house` field is always populated and
  whose `room` field is populated only when the lookup was room-level
  (the input ID had three pipe-separated components rather than two).
  The LLM checks `room is None` to know whether to talk about a single
  room or the whole property.
* **`rooms_summary` includes inactive rooms.** All rooms belonging to a
  house are summarised (status `Available` or `Inactive`), so the
  property's full inventory is visible. The active flag is shown
  explicitly per room.
* **Review status filter is lowercase.** Production DB stores
  `review.status='approved'` in lowercase (366 rows). An earlier prototype
  filtered on the title-cased `'Approved'`, which silently returned zero
  rows. The fix is commit `0da9cc4`.
* **Review aggregates only — no text.** The design enforced this for
  privacy. The aggregator returns mean overall rating plus mean by
  sub-category (cleaning, communication, location, price/quality), the
  approved-review count, and the three most recent reviews with title
  + 120-character excerpt. For richer review text the orchestrator
  defers to the Phase 2 RAG over `elh-reviews`.
* **`include_reviews=False` short-circuits the review query.** Useful
  for fast list-style lookups where the LLM only needs sizes and
  amenities.

#### Smoke results (3/3 green)

Tested against Cosy Home Lisbon Intendente
(`HSE_00F7359B|2022-04-30T00:00:00`):

| # | Lookup | Returned |
|---|---|---|
| 1 | Room + reviews | Double Deluxe room, 4-room house summary, 1 approved review |
| 2 | Room without reviews | Same minus reviews section |
| 3 | House + reviews | 4 rooms, 12 house amenities, 1 review at 5.0/5 |

Concrete house facts surfaced by the smoke:

* Area 114.47 m², 3 bathrooms
* Green metro line, 833 m to transport, 100 Mbps
* House amenities: Air conditioning, Balcony, Dishwasher, Double-glazed
  windows, Fridge, Furnished, Gas/electric stove, Internet, Kitchen
  equipment, Parking, Smart TV, Washer/drier (12)
* Other amenities free text: "Storage room"
* Rooms: Double Deluxe (variable €435/€390/€510), Cosy Double
  (fixed €615), Economy Room (fixed €460), Studio Loft (fixed €410)

Review (single approved, dated 2024-05-06):

> *"Absolutamente recomendo"* — 5.0/5 across all sub-categories.

### 4.5 `get_booking_stats` (Tool 5)

#### Package layout

```
src/elh_rag/tools/get_booking_stats/
├── __init__.py             # re-exports GetBookingStatsInput,
│                           #   GetBookingStatsOutput, StatPoint,
│                           #   get_booking_stats
├── _models.py              # Pydantic input + frozen output dataclasses
├── _sql_builders.py        # SQL templates, one per metric
├── _metrics.py             # metric registry + per-metric post-processor
├── _kanon.py               # k-anonymity filter with k=5
└── tool.py                 # @register_tool dispatch
```

This is the most complex tool in the suite. The five-file split makes the
metric registry an explicit, testable structure: each metric is a triple
of (SQL builder, post-processor, label).

#### Runtime decisions

* **Seven metrics, frozen at the Pydantic Literal.** No free-form SQL.
  The complete list: `occupancy_rate`, `top_zones_by_bookings`,
  `avg_booking_duration_months`, `avg_lead_time_days`, `seasonal_demand`,
  `avg_overall_rating`, `room_inventory_count`. New metrics require a
  code change and a new test, not a runtime configuration.
* **k=5 threshold, with visible-bucket preservation.** As described in
  §3.4. The disclaimer reminds the consumer that the data is
  privacy-filtered.
* **Mandatory disclaimer.** Every output ends with a 200-character
  disclaimer explaining the k-anonymity filter and the read-only,
  aggregate-only nature of the response.
* **No PII tables touched.** The SQL builders only reference
  `reservation`, `house`, `room`, `review`. The forbidden tables
  (`users`, `payment`, `email`, `question`, `reply`) are not joined,
  not selected, not aliased. This is enforced socially (review at
  PR time) rather than mechanically; an automated guardrail is a Phase
  4 candidate.
* **Group-by Literal.** The `group_by` parameter is a list of Literal
  strings (`"city"`, `"zone"`, `"season"`, ...) rather than free
  field names. The metric registry maps each Literal to a SQL fragment.

#### Smoke results (7/7 green) — these double as Phase 3 validation figures

| # | Metric | Group-by / filter | Outcome |
|---|---|---|---|
| 1 | `occupancy_rate` | Lisbon, 2024 full year | **0.4802** (138 records) |
| 2 | `top_zones_by_bookings` | top 5 (no filter) | Massarelos 62, Chiado 61, Foz do Douro 53, Santos 48, Belem 41 |
| 3 | `avg_booking_duration_months` | by city | Lisbon **9.36** (n=346), Porto **9.28** (n=254) |
| 4 | `avg_lead_time_days` | by season | autumn 32.0 (n=450), spring 36.6 (n=118), summer 56.3 (n=32) |
| 5 | `seasonal_demand` | by season | autumn 450, spring 118, summer 32 |
| 6 | `avg_overall_rating` | Lisbon by zone | **12 visible buckets**, 2 suppressed by k-anonymity; 219 underlying rows |
| 7 | `room_inventory_count` | by city | Lisbon **177**, Porto **107** |

Notable scenario 6 detail (visible buckets):

| Zone | Avg rating | n |
|---|---|---|
| Alfama | 2.62 | 8 |
| Intendente | 3.60 | 5 |
| Bairro Alto | 3.50 | 10 |
| Principe Real | 3.36 | 14 |
| Alvalade | 3.71 | 14 |
| Graca | 3.56 | 16 |
| Parque das Nacoes | 3.78 | 23 |
| Santos | 4.12 | 25 |
| Estrela | 3.38 | 26 |
| Belem | 3.68 | 28 |
| Anjos | 3.56 | 9 |
| Chiado | 3.97 | 38 |

### 4.6 `answer_policy_question` (Tool 6)

#### Package layout

```
src/elh_rag/tools/answer_policy_question/
├── __init__.py             # re-exports AnswerPolicyQuestionInput,
│                           #   AnswerPolicyQuestionOutput, KBContext,
│                           #   PolicyMatch, answer_policy_question
├── _models.py              # Pydantic input + frozen output + PolicyMatch
├── _loader.py              # YAML loader, schema validation, normalisation
├── _store.py               # in-memory KB store + sentence-transformer index
├── _context.py             # KBContext lifecycle (build from YAML / embedder)
├── tool.py                 # @register_tool entry point
└── kb/
    └── policies.yaml       # 26 entries, multilingual, structured per FAQ
```

The KB file structure (excerpt):

```yaml
- id: cancellation_policy_canonical
  category: cancellation
  audience: tenant
  canonical_question: "What is the cancellation policy?"
  paraphrases:
    - "How can I cancel my reservation?"
    - "What if I want to leave early?"
  answer: |
    The cancellation policy is tiered by notice:
    - More than 60 days before check-in: full refund
    - 30 to 59 days before check-in: 50 % refund
    - Less than 30 days before check-in: no refund
  sources: ["ELH Terms of Service §4.2"]
  related: ["reservation_fee_canonical"]
```

#### Runtime decisions

* **D5 closed by implementation.** The design left Decision 5 (Tool 6
  approach) open pending the marketing meeting. The actual approach:
  YAML knowledge base committed alongside the tool, embedded at
  `KBContext.from_default_yaml(embedder)` time with a multilingual
  sentence-transformer, and queried via cosine similarity. No Pinecone
  index: the KB is small (~26 entries today, expected ~80 at full
  coverage), so an in-memory NumPy matrix is faster, deterministic,
  and removes the deployment dependency.
* **Multilingual embedder.** The `Embedder` class in
  `elh_rag.indexing.embeddings` loads
  `paraphrase-multilingual-mpnet-base-v2` (~2.2 GB cached), the same
  model used in Phase 2 RAG. Reusing the model avoids loading two
  embedders in production.
* **Confidence threshold default 0.5.** Below this, the tool returns
  `found=False` with a templated fallback message rather than a
  low-confidence guess.
* **Audience field.** Some answers differ for tenants and landlords
  (payment timing is the obvious case). The `audience` Literal in the
  input model lets the LLM disambiguate. Landlord answers are tagged in
  the YAML with `audience: landlord` and are only retrievable when the
  caller passes that value.
* **No generative step.** The tool returns the canonical answer verbatim
  from the YAML, plus optional citations. There is no LLM rewriting of
  KB content. This was a deliberate decision: policy answers must be
  faithful, and the orchestrator can wrap the verbatim answer if the
  user needs softening.
* **Cancellation answer is canonical.** The cancellation tiers
  (60+ days → full refund, 30–59 → 50 %, <30 → no refund) are confirmed
  by the boss meeting and represented in the YAML as the canonical
  authority.

#### Smoke results (6/6 green)

| # | Query | Language | Confidence | Match |
|---|---|---|---|---|
| 1 | "What is the cancellation policy?" | EN direct | **1.00** | `cancellation_policy_canonical` |
| 2 | "I want to reserve a room, how does that work?" | EN paraphrased | **0.95** | `booking_flow_canonical` |
| 3 | "Come posso cancellare la mia prenotazione?" | IT | **0.97** | `cancellation_policy_canonical` |
| 4 | "É preciso pagar caução?" | PT | **0.57** | `deposit_policy_canonical` (borderline) |
| 5 | "When do landlords get paid?" | EN, landlord audience | **0.98** | `landlord_payment_timing` |
| 6 | "What's the weather like in Lisbon today?" | EN off-topic, threshold=0.5 | < threshold | fallback message ✓ |

The Portuguese borderline at 0.57 is the cleanest signal that the mpnet
threshold may need separate tuning per language. Flagged for Phase 4
(threshold tuning per language, with a small Portuguese golden set
derived from the marketing meeting).

---

## 5. Structural refactor — six commits

The refactor was carried out as six small commits on the same branch, each
self-contained and reviewable, applied **after** every tool had passed unit
tests in the original flat layout. Test count was 723 before and 723 after.

| # | Commit | Scope |
|---|---|---|
| 1 | `46990a5` | `refactor(tools): extract _shared subpackage for cross-tool helpers` — moves `_db.py`, `_room_id.py`, `_metro_lines.py`, `_pricing.py` under `tools/_shared/`. |
| 2 | `b594057` | `refactor(tools/find_available_rooms): convert to subpackage with SRP split` — extracts `_reservation.py`. |
| 3 | `3f3b537` | `refactor(tools/compute_total_cost): convert to subpackage` — extracts `_expenses.py`. |
| 4 | `6280073` | `refactor(tools/get_property_details): convert to subpackage` — extracts `_reviews_aggregate.py`; `_property_details.py` keeps the coupled models + fetchers. |
| 5 | `1be7a59` | `refactor(tools/get_booking_stats): convert to subpackage with SRP split` — full split into `_models.py`, `_sql_builders.py`, `_metrics.py`, `_kanon.py`. |
| 6 | `0daced2` | `refactor(tools/answer_policy_question): convert to subpackage with SRP split` — full split into `_models.py`, `_store.py`, `_loader.py`, `_context.py`. |

`find_rooms` was already a subpackage when the refactor started — it was
the model for the pattern.

The rule applied to decide split granularity, restated for clarity:

> *Subpackage when a tool has more than two distinct concerns and the
> single-file version would exceed ~200 cohesive lines. Otherwise keep a
> single file.*

The rule's most informative application is its **negative** use in
`get_property_details`: `_property_details.py` is ~250 lines because it
combines House/Room/RoomSummary models, their three SQL fetchers, and the
three dataclass builders. The three concerns are tightly coupled
(every fetcher returns one of the models, every builder consumes one of
the rows); splitting them would produce three files that constantly
re-import each other's types. The single-file solution is the cleaner
one. The reviews aggregator, by contrast, has its own privacy filter and
its own SQL, so it earns a separate file.

Post-refactor, every smoke test was re-run end-to-end against the
production DB. All 31 scenarios across the six tools returned green
without any change to the tools themselves — confirming the refactor was
purely structural.

A small follow-up was needed: the regex find-replace used in Commit 1 was
scoped to `src/elh_rag/tools/**/*.py` and `tests/tools/**/*.py`, so the
smoke scripts under `scripts/smoke_tests/` retained the obsolete
`from elh_rag.tools._db import` path. This was fixed in a separate commit
`dd3d0a4` (`fix(smoke): align tool 3/4/5 imports with _shared/
post-refactor`); the Tool 6 smoke had already been authored against the
new path during Commit 6. The new Tool 1 and Tool 2 smokes were added in
commit `ec2d867`.

---

## 6. Decisions that emerged during implementation

A number of small, concrete decisions were taken after the design freeze.
They are recorded here to keep `phase3.md` immutable as a design artefact.

| # | Decision | Context | Resolution |
|---|---|---|---|
| **R1** | Subpackage layout vs flat | `get_booking_stats` and `answer_policy_question` outgrew single-file readability | Subpackage with the "more than two concerns + 200 lines" rule (§3.1) |
| **R2** | Reservation fee formula | Open TODO in design | **9 % of the total rent** confirmed by ELH owner, 2026-05-11 meeting |
| **R3** | Cross-season pricing semantics | "Day-weighted average" felt unnatural in marketing-facing labels | **Model B**: each touched month billed in full at its seasonal rate; displayed mean is the mean of the per-month rents (§3.3) |
| **R4** | k-anonymity output shape | Empty `data_points` discarded useful visible buckets | Keep visible buckets, report `suppressed_buckets` count + warning (§3.4) |
| **R5** | `accepts_couples`, `max_house_occupancy`, `bills_included` | Columns absent from production schema | **Silent-skip with audit-log warning** for `accepts_couples` and `max_house_occupancy`; `bills_included` removed entirely from the Pydantic schema |
| **R6** | Review status filter casing | DB stores `'approved'` lowercase | Lowercase filter, fix in commit `0da9cc4` |
| **R7** | Tool 6 storage | Pinecone vs in-memory | **In-memory NumPy matrix**: KB is small (~26 entries), deterministic, no deployment dependency, single embedder shared with Phase 2 RAG |
| **R8** | Tool 6 generation step | LLM rewriting of KB answers | **None** — verbatim YAML retrieval, optional citations; orchestrator handles tone |
| **R9** | Utility classification | Ambiguous `expenses.maximumvalue` semantics | **`NOT NULL` ⇒ included up to cap; `NULL` ⇒ excluded, tenant pays provider** (confirmed at boss meeting, 2026-05-11) |
| **R10** | Administrative tax payee | ELH or landlord? | **Landlord, at check-in**; output note instructs tenant to request invoice (boss meeting) |
| **R11** | Deposit semantics | `deposit` vs `lastmonthdeposit` | **Independent**: security deposit refundable + last-month-rent-upfront; both can coexist (boss meeting) |
| **R12** | VAT presentation | Explicit per line vs included | **Always included**; one explicit note in the output |
| **R13** | Extra-person fee | One-off or recurring | **One-off, per stay, opt-in** (boss meeting) |
| **R14** | Cancellation tiers | Design left ambiguous | **60+ d full refund, 30–59 d 50 %, <30 d no refund** — canonical YAML entry (boss meeting) |
| **R15** | Rate limiting | Open D6.3: protect against runaway costs | **Deferred to deployment layer**. No public API surface today; the agent runs behind ELH-internal authentication. Application-level rate limit would require tuning thresholds against traffic data not yet available. Budget runaway is covered by Anthropic platform billing alerts. Reconsider when the agent is exposed to unauthenticated public traffic. |
| **R16** | PII safety enforcement pattern | Open D6.2: prevent regression of Tool 5 GDPR boundary | **Two-tier defense** — (a) AST-time test that scans every Python file in the package for forbidden table names as whole-word string literals, (b) runtime `@pii_safe_sql` decorator on each of seven extracted SQL builder functions, raising `PIISafetyError` (subclass of `ToolExecutionError`) on detection. The refactor extracting builders from `_compute_*` functions also unlocked Phase 4 opportunities for query caching and telemetry as additional decorators. |
| **R17** | `query_summary` invariant: reflect only applied filters | Open D6.5: bugs 1+2 in `find_rooms/_summarize_query` | **Summary must mirror the SQL.** `must_have_*` filters added to the summary via field-name derivation (`must_have_air_conditioning` → `'air conditioning'`). Silent-skipped filters (`accepts_couples`, `max_house_occupancy` — columns absent from the ELH schema) omitted from the summary to avoid misleading the LLM consumer. Invariant documented in the function docstring for future regressions. |

The list of decisions records the cumulative effect of two meetings,
the implementation work itself, and the D6 safety review post-implementation.
The earlier ELH meeting (2026-05-05) seeded R5 and R12 indirectly
through the GDPR rules; the boss meeting (2026-05-11) closed R2, R9,
R10, R11, R13, R14; the D6 safety review closed R15 (rate limiting
deferred), R16 (PII guard two-tier with builder pattern refactor),
and R17 (summary invariant).

---

## 7. Smoke certification — 31/31 scenarios on production DB

All six tools have a dedicated end-to-end smoke script under
`scripts/smoke_tests/`. Each script exercises the tool against the live
Supabase production database
(`aws-1-eu-west-1.pooler.supabase.com:5432/postgres`) with realistic
inputs covering the main code branches.

| Script | Tool | Scenarios | Result |
|---|---|---|---|
| `smoke_test_tool1.py` | `find_rooms` | 6 | 6/6 ✓ |
| `smoke_test_tool2.py` | `find_available_rooms` | 6 | 6/6 ✓ |
| `smoke_test_tool3.py` | `compute_total_cost` | 3 (chained with Tool 2) | 3/3 ✓ |
| `smoke_test_tool4.py` | `get_property_details` | 3 (chained with Tool 2) | 3/3 ✓ |
| `smoke_test_tool5.py` | `get_booking_stats` | 7 | 7/7 ✓ |
| `smoke_test_tool6.py` | `answer_policy_question` | 6 (EN/IT/PT) | 6/6 ✓ |
| **Total** | | **31** | **31/31 ✓** |

The smoke pattern is identical across all six scripts:

```python
from elh_rag.config import settings
from elh_rag.tools._shared.db import Psycopg2Executor

with Psycopg2Executor(settings.db_uri) as ctx:
    result = tool_function(payload, ctx=ctx)
```

`Psycopg2Executor` is a context manager that opens a psycopg2 connection
against the configured DSN, exposes an `execute(sql, params)` method
returning a list of dict rows, and closes the connection on exit. Tool 6
uses `KBContext` instead, built once at script startup from the bundled
YAML and the multilingual embedder.

Each scenario is independent: a failure of one does not short-circuit the
others, and the final line of every script reports the success ratio.
The arithmetic verifications performed by the Tool 2 and Tool 3 smokes
(the Model B means and the 9 % reservation fees) are checked manually
against the printed output — the smokes are not assertions on numeric
equality, they are exploratory probes whose outputs are reviewed.

---

## 8. Validation figures for the thesis

<!-- THESIS:Validation -->

The Tool 5 smoke is, in effect, a privacy-filtered descriptive analysis of
the ELH operational dataset. The following figures are taken directly
from the smoke output of 2026-05-12 and are suitable for inclusion in the
thesis Validation chapter, with the disclaimer that all aggregates are
k=5 privacy-filtered and do not expose row-level data.

### 8.1 Inventory

| City | Active rooms |
|---|---|
| Lisbon | **177** |
| Porto | **107** |
| **Total** | **284** |

### 8.2 Booking duration

| City | Mean duration (months) | n |
|---|---|---|
| Lisbon | **9.36** | 346 |
| Porto | **9.28** | 254 |
| **Pooled** | **9.33** | 600 |

A nine-month mean is consistent with the academic-year structure of the
Erasmus mobility programme (October to June, plus exam tails).

### 8.3 Seasonal demand

Bookings by check-in season (n=600 over the full reservation history):

| Season | Bookings | Share |
|---|---|---|
| autumn | **450** | 75 % |
| spring | **118** | 20 % |
| summer | **32** | 5 % |

The autumn dominance directly motivates the design choice (D3.3) to default
Tool 1 to the autumn price column. Summer is a residual market segment,
likely short-stay or non-Erasmus.

### 8.4 Lead time

| Season | Mean lead time (days) | n |
|---|---|---|
| autumn | **32.0** | 450 |
| spring | **36.6** | 118 |
| summer | **56.3** | 32 |

The longer lead time in summer reflects a different customer profile
(planners booking ahead) versus the autumn last-minute pattern typical of
late Erasmus offers.

### 8.5 Occupancy

For Lisbon, full calendar year 2024 (138 records):

* **Occupancy rate: 0.4802** (48.02 %)

### 8.6 Top zones by booking volume

| Rank | Zone | Bookings |
|---|---|---|
| 1 | Massarelos | 62 |
| 2 | Chiado | 61 |
| 3 | Foz do Douro | 53 |
| 4 | Santos | 48 |
| 5 | Belem | 41 |

Massarelos and Foz do Douro are Porto zones; Chiado, Santos, Belem are
Lisbon. The mix at the top illustrates the cross-city demand structure.

### 8.7 Average overall rating by Lisbon zone

Twelve visible zones, two suppressed by k-anonymity (219 underlying
reviews). Sorted by mean rating:

| Zone | Mean | n |
|---|---|---|
| Santos | **4.12** | 25 |
| Chiado | 3.97 | 38 |
| Parque das Nacoes | 3.78 | 23 |
| Alvalade | 3.71 | 14 |
| Belem | 3.68 | 28 |
| Intendente | 3.60 | 5 |
| Graca | 3.56 | 16 |
| Anjos | 3.56 | 9 |
| Bairro Alto | 3.50 | 10 |
| Estrela | 3.38 | 26 |
| Principe Real | 3.36 | 14 |
| Alfama | **2.62** | 8 |

Alfama is the clear underperformer; Santos and Chiado lead the city.

---

## 9. Cosmetic fixes closed pre-merge

Both cosmetic issues identified during the Tool 1 smoke runs were
fixed before the merge to `develop`. Decision D6.5 of the Phase 3
agent design. The fixes are local to
`find_rooms/_sql_builder.py::_summarize_query` and are covered by a
dedicated test module (`tests/tools/find_rooms/test_summarize_query.py`,
15 tests).

### 9.1 `query_summary` now includes `must_have_*` filters ✓

The summary iterates the `_EXPLICIT_AMENITY_COLUMN_MAP` keys and, for
each `must_have_*` field set to `True` or `False`, appends a label
derived from the field name (prefix `must_have_` stripped, underscores
replaced with spaces). `must_have_air_conditioning=True` yields
`'air conditioning'`; `must_have_window=False` yields `'no window'`;
`None` is silently skipped.

Smoke scenario 3 of Tool 1, after fix:

```
Input    : city=Lisbon, must_have_private_bathroom=True,
           must_have_balcony=True, max_price_eur=600
Summary  : "Filters: city=Lisbon, ≤€600, private bathroom, balcony"
```

### 9.2 `accepts_couples` removed from summary on silent-skip ✓

The summary no longer emits `couples-friendly` when
`accepts_couples=True` is passed, because the SQL builder silently
skips that filter (the column does not exist in the ELH schema). The
same omission applies to `max_house_occupancy`. The invariant is
recorded in the function docstring:

> *"The summary reflects only the filters that are actually applied
> to the SQL. Filters silently skipped at SQL build time — namely
> `accepts_couples` and `max_house_occupancy`, whose columns are
> absent from the ELH schema (D6 silent-skip pattern) — are
> deliberately omitted, so the LLM consumer is not misled into
> believing those constraints were honoured."*

The `logger.warning` audit trail at SQL build time is preserved
unchanged.

Smoke scenario 6 of Tool 1, after fix:

```
Input    : city=Lisbon, metro_line=green, accepts_couples=True,
           gender_preference=female_only, max_price_eur=500
Summary  : "Filters: city=Lisbon, metro=green, ≤€500, female_only"
```

### 9.3 Out-of-scope summary improvements (Phase 4 candidates)

While reviewing `_summarize_query` for D6.5 it became apparent that
several other filters are also missing from the human-readable
summary: `min_price_eur`, `min_contract_months`,
`max_distance_to_transport_m`, and `required_other_amenities`. These
are applied to the SQL but not surfaced in the summary. They were
deliberately left out of the D6.5 fix because (a) they were not the
documented bugs and (b) scope discipline matters more than
opportunistic improvements at this point in the timeline. Tracked as
Phase 4 polish.
