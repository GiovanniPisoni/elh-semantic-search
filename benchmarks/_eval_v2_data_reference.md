# eval-v2 Data Reference (TASK-24 · Phase A / Step 0)

**Purpose.** Ground-truth reference for authoring the held-out eval-v2 golden set.
Reconnaissance only — no eval queries are written here, no agent/judge/embedding/
Pinecone calls were made. Tools and agent are read at their frozen state
(`62e2832`, v3.2.0).

**Provenance of every figure below — read this first.**

| Tag | Meaning | Trust |
|-----|---------|-------|
| `[CODE]` | Derived directly from the frozen source (formulas, enums, SQL, filters). | Authoritative. |
| `[CORPUS]` | Observed in the pre-embedding corpus text embedded in `benchmarks/runs/precision_at_k_candidates.jsonl` (the source text behind `search_descriptions`/`search_reviews`). Only the `candidates[].text`/`metadata` were read; **no query strings were used**. This is a *sample* (10 retrieval sets, 50 room/house docs + 50 review docs), not the full catalogue. | Indicative, not exhaustive. |
| `[DB <date>]` | Computed by a read-only query against the live Postgres (Supabase) catalogue on that date. **Step 0b (2026-06-19) ran all such queries** — every former `[DB-REQUIRED]` placeholder is now filled. The inline SQL that produced each figure is retained for re-verification. | Authoritative as of the query date. |

> **Status:** the catalogue counts (§A), price distribution (§B), reservation
> coverage + Sep-2026 availability (§D) and the ground-truth anchor rooms (§J) were
> all filled from the live DB on **2026-06-19**. Everything tagged `[CODE]` (cost
> model §E, policy facts §F, schema §C, tool I/O §H, boundaries §I) is source-derived
> and DB-independent. The one remaining `[CORPUS]` estimate (§B price range) is
> explicitly flagged as superseded by the `[DB]` figures.

Backing store: PostgreSQL (Supabase) accessed via `psycopg2` (`tools/_shared/db.py`).
Core tables: `house`, `room`, `reservation`, `review`, `expenses`. Rows are
**versioned** by `dateupdate`; a room is tied to a house version via
`(loc_idhouse, loc_dateupdate)`. Tools always take the latest version
(`DISTINCT ON (...) ORDER BY ... dateupdate DESC`).

---

## A. Catalogue overview

`[CODE]` **Cities are a hard enum: `Lisbon` and `Porto` only** — both `find_rooms`
and `get_booking_stats` type `city` as `Literal["Lisbon", "Porto"]`. No third city
can be queried.

`[DB 2026-06-19]` **Two valid "room count" lenses — keep them distinct:**

| City | Available room *rows* (find_rooms lens, no version dedup) | Distinct rooms (latest version, Tool 3/4 lens) | Distinct zones | Distinct neighborhoods |
|------|--------|--------|--------|--------|
| Lisbon | **556** | **435** | 14 | 14 |
| Porto | **376** | **295** | 9 | 11 |
| **Total** | **932** | **730** | — | — |

> Why two numbers: every row in `room` is `status='Available'` (932 rows total),
> but rooms are **versioned** by `dateupdate`. `find_rooms`/`find_available_rooms`
> count joined room rows **without** deduping versions, so `total_matches` reflects
> the **row** lens (556 / 376). `compute_total_cost` and `get_property_details`
> resolve `DISTINCT ON (loc_idhouse, idroom) … dateupdate DESC`, i.e. the **distinct
> room** lens (435 / 295). A golden-set "how many rooms in X" expectation must pick a
> lens; the row lens is what a user sees as the search result count.

`[DB 2026-06-19]` **Zones per city** (room-row counts):

- **Lisbon (14):** Santos 73, Belém 60, Mouraria 49, Graça 48, Chiado 42, Anjos 39,
  Arroios 39, Alfama 39, Príncipe Real 38, Parque das Nações 32, Alvalade 32,
  Bairro Alto 31, Estrela 18, Intendente 16.
- **Porto (9):** Boavista 77, Ramalde 55, Ribeira 52, Paranhos 46, Foz do Douro 45,
  Bonfim 43, Cedofeita 22, Massarelos 18, Campanhã 18.

`[DB 2026-06-19]` **Neighborhoods per city** (`neighboorhood` column, room-row counts):

- **Lisbon (14):** Graça 64, Roma 59, Mouraria 52, Santos 50, Alfama 47,
  Telheiras 45, Campo de Ourique 45, Benfica 43, Alvalade 32, Alcântara 32,
  Areeiro 27, Intendente 25, Chiado 24, Bairro Alto 11.
- **Porto (11):** Ribeira 64, Foz 48, Bonfim 41, Miragaia 37, Ramalde 34,
  Paranhos 32, Lordelo 31, Boavista 25, Campanhã 23, Nevogilde 23, Cedofeita 18.

> **⚠ Data characteristic — `zone` and `neighboorhood` are NOT a coherent
> hierarchy.** In this (synthetic) dataset the two columns are effectively
> independent: a house can have `zone='Belém'` with `neighboorhood='Alfama'`. So a
> single neighborhood name appears scattered across many zones and vice-versa. Do
> **not** assume `neighborhood ⊂ zone`. `near_landmark` matches ILIKE on *either*
> column (plus description), and the metro-line filter keys on *either* — so both
> name spaces are searchable independently.

> Note: the static metro map in `metro_lines.py` is the authoritative list of zone
> *names the tools recognize* for metro-line lookups; it is curated, not derived
> from the DB. Zones/neighborhoods present in the DB but absent from that map
> resolve to "no metro line" (e.g. Belém, Graça, Estrela, Foz, Massarelos → `[]`).

---

## B. Price distribution per city

`[CODE]` **Seasonal pricing model** (`tools/_shared/pricing.py`). Each room row
carries three rent columns plus a fixed-price flag:

- `springprice` — months **3,4,5,6** (medium season)
- `summerprice` — months **7,8** (low season; Erasmus students typically away)
- `autumnprice` — months **9,10,11,12,1,2** (high season, academic year)
- `fixedprice = 'Y'` → no seasonal variation; the **autumn column is the canonical
  fixed value** (a warning is logged if the three columns disagree while
  `fixedprice='Y'`).

`find_rooms` selects **one** column for filtering/sorting based on the requested
month (default **autumn** when no date is given). `find_available_rooms` and
`compute_total_cost` bill **every calendar month at its own seasonal rate** (see §D, §E).

> **⚠ The earlier `[CORPUS]` price estimate was wrong — superseded by the `[DB]`
> figures below.** A small biased corpus sample had suggested €315–990 / median
> ≈ €590. The real `autumnprice` distribution is **markedly higher** (median ≈ €980
> Lisbon / €895 Porto, tail to €2 355) and **fixed-price is the majority**, not a
> minority. Use the table below for ground truth; ignore the old sample range.

`[DB 2026-06-19]` **Authoritative distribution + threshold counts** (on
`autumnprice`, the high-season headline rate, over the **730 distinct latest-version
rooms**; recommended basis for a season-neutral golden set):

```sql
WITH latest AS (
  SELECT DISTINCT ON (r.loc_idhouse, r.idroom)
         h.city, r.autumnprice, r.springprice, r.summerprice, r.fixedprice
  FROM room r
  JOIN house h ON h.idhouse = r.loc_idhouse AND h.dateupdate = r.loc_dateupdate
  WHERE r.status = 'Available'
  ORDER BY r.loc_idhouse, r.idroom, r.dateupdate DESC
)
SELECT city,
       MIN(autumnprice)                       AS min_eur,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY autumnprice) AS median_eur,
       MAX(autumnprice)                       AS max_eur,
       COUNT(*) FILTER (WHERE autumnprice < 400) AS under_400,
       COUNT(*) FILTER (WHERE autumnprice < 450) AS under_450,
       COUNT(*) FILTER (WHERE autumnprice < 500) AS under_500,
       COUNT(*) FILTER (WHERE autumnprice < 600) AS under_600,
       COUNT(*) FILTER (WHERE autumnprice < 700) AS under_700,
       COUNT(*) FILTER (WHERE fixedprice = 'Y')  AS fixed_price_rooms,
       COUNT(*) FILTER (WHERE fixedprice <> 'Y')  AS seasonal_rooms,
       COUNT(*)                                AS total
FROM latest GROUP BY city ORDER BY city;
```

| City | min | median | max | <400 | <450 | <500 | <600 | <700 | fixed | seasonal | total |
|------|-----|--------|-----|------|------|------|------|------|-------|----------|-------|
| Lisbon | €220 | **€980** | €2 355 | 9 | 14 | 25 | 49 | 82 | 240 | 195 | 435 |
| Porto | **−€20** | **€895** | €2 040 | 18 | 21 | 29 | 55 | 92 | 180 | 115 | 295 |

Takeaways for golden-set design:
- **Fixed-price dominates:** Lisbon 240/435 (55%), Porto 180/295 (61%). A "fixed vs
  seasonal" expectation should assume fixed is the common case.
- **Cheap rooms are scarce:** only 9 Lisbon / 18 Porto rooms under €400 autumn; under
  €500 it is 25 / 29. A "room under €450" query is satisfiable but returns a small set.
- **⚠ Dirty data:** exactly **1 room has a non-positive `autumnprice`** (a Porto room
  at **−€20**, with its spring/summer also ≤ 0). It is the Porto `min`. **Exclude
  `autumnprice <= 0`** when constructing price-based ground truth — it will otherwise
  surface as the "cheapest room in Porto" and break any cost computation. (`min`
  excluding it: rerun with `WHERE autumnprice > 0`.)

---

## C. Room attribute schema (what `find_rooms` can and cannot filter)

`[CODE]` `FindRoomsInput` (`tools/find_rooms/_inputs.py`) + SQL builder
(`_sql_builder.py`) + amenity maps (`_amenity_columns.py`). `Y`/`N` text columns
throughout; `True`→`'Y'`, `False`→`'N'`.

### C.1 Filterable in `find_rooms` / `find_available_rooms`

**Location**
| Field | Type / range | Maps to |
|-------|--------------|---------|
| `city` | enum `Lisbon` \| `Porto` | `house.city` |
| `metro_line` | enum: `blue,yellow,green,red,violet,orange` + Porto letters `A,B,C,D,E,F` (A=blue,B=red,C=green,D=yellow,E=violet,F=orange) | resolved via static map to `house.zone`/`neighboorhood` IN (zones on that line) |
| `near_landmark` | free text ≤100 chars | `ILIKE` on `house.zone` OR `neighboorhood` OR `description` |
| `max_distance_to_transport_m` | int 0–5000 | `house.distancepublictransport <= x` (meters) |

**Price**
| Field | Range | Maps to |
|-------|-------|---------|
| `max_price_eur` / `min_price_eur` | float 0–10000 | the season-selected price column (default `autumnprice`) |

**Period / contract**
| Field | Range | Maps to |
|-------|-------|---------|
| `available_from` / `available_to` | date | selects season price column; in Tool 2 they are **required** and drive availability |
| `min_contract_months` | int 1–24 | `room.minreservemonths >= x` (approximation) |
| `min_reserve_months` | int 1–12 | `room.minreservemonths >= x` |

**Occupancy**
| Field | Range | Behaviour |
|-------|-------|-----------|
| `accepts_pets` | bool | `house.allowpets = 'Y'` |
| `gender_preference` | `male_only` \| `female_only` \| `any` | `house.malepreferred='Y'` / `house.femalepreferred='Y'` / no filter |
| `num_rooms_needed` | int 1–10 | **summary only — not a SQL filter** |
| `accepts_couples` | bool | **IGNORED — no column in schema** (logs a warning) |
| `max_house_occupancy` | int 1–20 | **IGNORED — no column in schema** (logs a warning) |

**Explicit must-have amenities** (11 booleans; `True`→`'Y'`, `False`→`'N'`):
`must_have_private_bathroom` (`room.privatebathroom`), `must_have_balcony`
(`room.balcony`), `must_have_elevator` (`house.elevator`),
`must_have_air_conditioning` (`room.airconditioning`), `must_have_heating`
(`room.heating`), `must_have_washing_machine` (`house.washerdrier`),
`must_have_dishwasher` (`house.dishwasher`), `must_have_parking` (`house.parking`),
`must_have_internet` (`house.internet`), `must_have_desk` (`room.desk`),
`must_have_window` (`room.haswindow` — this is the **"natural light"** proxy).

**Other amenities** (`required_other_amenities`, 26-value enum, all `='Y'` except
the inverted one):
`armored_door, bedlinen, cable_tv, cctv, central_heating, city_view, closet,
coded_entry, countryside_view, double_glazed_windows, equipped_kitchen,
extra_person_allowed, fridge, furnished, microwave, night_guests_allowed,
non_smoking (→ smokingallowed='N', INVERTED), pillows, sea_view, security_24h,
shared_space, smart_tv, smoke_detector, stove, thermal_insulation,
wheelchair_accessible`.

**Sort / limit:** `sort_by` ∈ `price_asc | price_desc | default(idroom asc)`;
`max_results` 1–50 (default 10). Hard pre-filter on every search: `r.status =
'Available'`.

### C.2 Present in the DB but **NOT filterable** (only surfaced by `get_property_details`)

These are real columns the agent can *report* but **cannot search on** — a key gap
for golden-set design (a query like "20 m² room with a double bed" cannot be
answered by structured filtering; the agent must fall back to descriptions or
list-then-inspect):

- **Room size `area` (m²)** — `room.area` / `house.area`. `[CORPUS]` sampled room
  sizes ≈ **9–28 m²** (small singles ~9–13 m², larger rooms ~20–28 m²); house
  `area` values are much larger (60–280 m²).
- **Bed type** — `room` Y/N columns `singlebed, doublebed, kingbed, queenbed,
  couchbed, secondbed` (a "second bed (sleeps 2)" flag). Reported as `bed_types`.
- **Bathroom (private vs shared)** — `room.privatebathroom` *is* filterable;
  the **count of shared bathrooms** (`house.bathroom`) is detail-only.
- **Internet speed** — `house.internetspeed` (Mbps), detail-only.
- **Geo** — `house.latitude` / `longitude`, detail-only.

### C.3 Distance / metro notes

`distancepublictransport` is a **house-level distance in meters to public
transport** (not per-room, not metro-specific). Metro-line membership is **not in
the DB** — it comes from the curated `metro_lines.py` map. Lisbon uses 4 colour
lines (blue/yellow/green/red); Porto has 6 (mapped to colours via A–F). Some
in-demand zones are explicitly **not metro-served** (Belém, Graça, Estrela in
Lisbon; Ribeira, Foz, Massarelos in Porto) → a metro-line filter excludes them.

---

## D. Availability model

`[CODE]` `find_available_rooms` (`tools/find_available_rooms/`) =
**structural filter (Tool 1, `status='Available'`) → minus reservation overlaps →
season-aware re-pricing.**

1. **Date window is required & inclusive.** `available_from` and `available_to` are
   mandatory; `available_to` must be **strictly after** `available_from`; max window
   = `3 × 366` days. Both endpoints inclusive.
2. **Overlap test** (`_reservation.py`): a room is *occupied* (excluded) if it has
   any `reservation` row with
   `blockeddatestart <= available_to AND blockeddataend >= available_from`
   (standard closed-interval overlap, keyed on `(loc_idhouse, idroom)`).
3. **Pricing across the window** (`compute_room_monthly_price`): every **calendar
   month touched** is billed at its seasonal rate; `price_per_month_eur` is the
   **average** across those months, and `price_label` spells out the composition
   (e.g. "€X/month average over 8 months: 6 months at autumn rate Y, 2 months at
   spring rate Z"). `fixedprice='Y'` rooms return a flat price + `is_fixed_price=True`.
4. **Partial months count as full months** — a stay 2026-09-15 → 2027-02-14 bills
   six full months (Sep–Feb), all autumn.

`[DB 2026-06-19]` **Reservation-calendar coverage** (7 260 reservation rows):

- **Earliest block start: 2023-01-01. Latest block end: 2024-11-30.**
- The monthly histogram spans **2023-01 → 2024-11** with a clear academic rhythm:
  big peaks in Mar / Jun / Sep (≈ 520–575 each), troughs in Jul (≈ 260–305) and
  near-empty Dec–Feb (≈ 13–25). **No reservations exist in 2025 or 2026.**

> **🔑 Critical for eval design — availability is a no-op for any future window.**
> Because the reservation table stops at **2024-11-30**, the overlap test returns
> **zero** occupied rooms for any window in 2025+. Verified probes
> (`blockeddatestart <= end AND blockeddataend >= start`, distinct
> `(loc_idhouse, idroom)`):
>
> | Window | Occupied (overlap) | Genuinely available |
> |--------|--------------------|---------------------|
> | Lisbon, 2026-09-01 → 2026-09-30 | **0** | **556** (= all Lisbon structural rows) |
> | Porto, 2026-09-01 → 2026-09-30 | **0** | **376** (= all Porto structural rows) |
> | Cross-season, 2026-09-01 → 2027-06-30 (Lisbon) | **0** | **556** |
> | *control:* any city, 2024-09-01 → 2024-09-30 | **483** | (filter demonstrably works where data exists) |
>
> So in 2026 `find_available_rooms` behaves like `find_rooms` plus season-aware
> pricing — it never excludes anyone. A golden-set item that wants availability
> filtering to actually *remove* rooms must target a **2023–2024** window; a 2026
> window only exercises the date-driven **pricing** path, not the exclusion path.
> The cross-season window above (Sep 2026 → Jun 2027) does span autumn + spring, so
> **multi-season average pricing is representable** there.

**Concrete example — "available in Lisbon for September 2026":**

`[CODE]` Call shape:
`find_available_rooms(city="Lisbon", available_from=2026-09-01,
available_to=2026-09-30)`. The result set = every Lisbon room with
`status='Available'` and **no** reservation overlapping 1–30 Sep 2026, priced at the
**autumn** rate (September ∈ autumn).

`[DB 2026-06-19]` **Member-list size: 556 Lisbon rooms are genuinely available that
window** (0 blocked — see the table above; the tool returns up to `max_results`,
default 10, but `total_matches=556`). Cheapest 10 by `autumnprice` (encoded
`idhouse|idroom`, autumn rate):

| # | `loc_idhouse \| idroom` | autumn €/mo |
|---|--------------------------|-------------|
| 1 | `HSE_D24DE65F \| RM_HSE_D24DE65F_5` | 220 |
| 2 | `HSE_4882F9A9 \| RM_HSE_4882F9A9_9` | 240 |
| 3 | `HSE_4882F9A9 \| RM_HSE_4882F9A9_7` | 240 |
| 4 | `HSE_4882F9A9 \| RM_HSE_4882F9A9_6` | 240 |
| 5 | `HSE_4882F9A9 \| RM_HSE_4882F9A9_3` | 250 |
| 6 | `HSE_4882F9A9 \| RM_HSE_4882F9A9_2` | 275 |
| 7 | `HSE_D24DE65F \| RM_HSE_D24DE65F_4` | 280 |
| 8 | `HSE_D24DE65F \| RM_HSE_D24DE65F_2` | 290 |
| 9 | `HSE_E825092D \| RM_HSE_E825092D_2` | 365 |
| 10 | `HSE_D24DE65F \| RM_HSE_D24DE65F_3` | 415 |

(Porto, same window: **376** available, 0 blocked.) The full encoded room id appends
the room's `dateupdate` as a third segment (see below) — captured per room in §J.

Encoded id format used downstream: **room** = `house_id|room_id|dateupdate`
(3 segments); **house** = `house_id|dateupdate` (2 segments).

---

## E. COST MODEL — `compute_total_cost` (most important)

`[CODE]` Sources: `tools/compute_total_cost/tool.py` (`_compute`),
`tools/_shared/pricing.py` (`compute_stay_breakdown`), `_expenses.py` (utilities),
`config` (`reservation_fee_pct = 0.09`, from `RESERVATION_FEE_PCT=0.09`).
Schedule per ELH ops confirmation **2026-05-19** (supersedes 2026-05-11).
All money is `Decimal`, rounded **half-up to 2 dp**.

### E.1 Components (exact)

Let the stay span calendar months `m₁ … m_N` (every month touched, partial =
full). For each month, `rent(mᵢ)` = the seasonal rate for that month's season
(`spring`/`summer`/`autumn`), or the autumn value if `fixedprice='Y'`.

```
total_rent            = Σ rent(mᵢ)                         # i = 1..N

reservation_fee       = round( total_rent × 0.09 )         # 9%, non-refundable, to ELH
security_deposit      = depositvalue          if deposit='Y'  else 0   # refundable, to landlord
lastmonth_advance     = rent(m_N)             if lastmonthdeposit='Y' AND N>=2  else 0
admin_tax             = administrativetax     if administrativetax > 0  else 0   # to landlord
extra_person_monthly  = extrapersoncost       if extra_person AND extrapersonallowed='Y'  else 0
extra_person_total    = round( extra_person_monthly × N )

first_month_rent      = rent(m₁)

payable_at_booking    = round( first_month_rent + reservation_fee )              # → ELH
one_time_at_checkin   = round( security_deposit + lastmonth_advance + admin_tax ) # → landlord (None if 0)

# remaining rent paid month-by-month during the stay:
remaining_months_rent = Σ rent(m₂..m_{N-1})   if lastmonth_advance>0            # last month prepaid
                      = Σ rent(m₂..m_N)        otherwise

total_stay_cost       = round( payable_at_booking + one_time_at_checkin
                               + remaining_months_rent + extra_person_total )
refundable_at_checkout= round( security_deposit )                                # only the deposit
total_out_of_pocket   = round( total_stay_cost − refundable_at_checkout )
```

`monthly_recurring_eur` is populated (single number, **excludes** the booking
first month and the prepaid last month) **iff every month bills the same effective
rate**; otherwise it is `None` and `monthly_breakdown` (per-month rents, with
extra-person folded in) is returned instead.

**Deposit rule nuance** (`deposit` flag vs `depositvalue`): the cost tool uses the
**stored `depositvalue`** when `deposit='Y'` — it does **not** assume "one month's
rent". The *policy* default (§F) is one month, but actual deposits vary by landlord
(flat €250, two months, etc.). Ground-truth deposit must come from the room row, not
the policy.

**Utilities** (`expenses` table, joined on `(idhouse, loc_dateupdate)`):
each expense row with a non-null `maximumvalue` → **included up to €cap/mo**
(e.g. "Gas (up to €25.00/mo)"); a **null** `maximumvalue` → **excluded** ("not
included — paid to provider"). Utilities are **informational, never a cost line** in
the totals. Every quote appends the note "All prices include VAT."

### E.2 Worked example (verified by running the frozen `_compute`)

`[CORPUS]`+`[CODE]` Room: **"Garden View Room", Residencia Intendente** (Lisbon),
seasonal. Rates from the listing: autumn **€865**, spring €620, summer €495,
extra-person €80/mo, **last-month deposit required**. Assumed for the example:
`deposit='Y'`, `depositvalue=€865` (matches policy default of one month),
`administrativetax=€0`, `extra_person=False`.

Stay: **check-in 2026-09-01 → check-out 2027-01-15**.

- Calendar months touched: Sep, Oct, Nov, Dec 2026 + Jan 2027 = **5 months, all
  autumn** → each €865.
- `total_rent` = 5 × 865 = **€4 325.00**
- `reservation_fee` = 9% × 4 325 = **€389.25**
- `first_month_rent` = €865 → **`payable_at_booking` = 865 + 389.25 = €1 254.25**
- `security_deposit` = €865 (refundable); `lastmonth_advance` = Jan rent = €865
  (lastmonthdeposit='Y', N≥2); `admin_tax` = €0
  → **`one_time_at_checkin` = 865 + 865 + 0 = €1 730.00**
- `remaining_months_rent` = Oct+Nov+Dec = 3 × 865 = €2 595.00 (Jan prepaid, Sep at
  booking)
- **`total_stay_cost` = 1 254.25 + 1 730.00 + 2 595.00 + 0 = €5 579.25**
- **`refundable_at_checkout` = €865.00**
- **`total_out_of_pocket` = 5 579.25 − 865.00 = €4 714.25**
- `monthly_recurring_eur` = **€865.00**; `total_stay_months` = 5;
  `is_fixed_price` = False.

Cross-check: 5 months rent (4 325) + reservation fee (389.25) + deposit (865) =
5 579.25 ✓; out-of-pocket = rent 4 325 + fee 389.25 = 4 714.25 (deposit fully
refunded, admin 0) ✓.

> Cross-season behaviour: had the stay run into spring (e.g. through March),
> `monthly_recurring_eur` would be `None` and `monthly_breakdown` would list each
> month at its own rate (autumn €865 / spring €620), with `total_rent` summing the
> mix.

---

## F. Policy facts — `answer_policy_question` knowledge base

`[CODE]` `tools/answer_policy_question/kb/policies.yaml` — **27 entries across 10
categories**. Hand-curated from the ELH website FAQ, Reamaze email templates, and
the ELH presentation deck. Each entry has `id, category, audience
(student|landlord|both), canonical_question, question_variants, answer, sources,
related`. Authoritative for policy questions (the agent must not derive policy from
descriptions/reviews).

Category breakdown: `booking_flow` 4 · `payments_and_fees` 4 ·
`cancellation_and_refunds` 4 · `room_quality_and_verification` 3 ·
`contracts_and_legal` 2 · `privacy_and_tenants` 1 · `landlord_onboarding` 5 ·
`contact_and_support` 1 · `promotions_and_discounts` 2 · `about_elh` 1.

**Booking flow.** Reserve on the platform → landlord accepts → confirmation email →
finalised once payment processes (**typically 2–3 days**). Reservations are
trackable on the platform with email notifications. In-person or video viewings are
offered before booking, subject to landlord availability.

**Payments & fees.** *At booking* (to ELH): **first month's rent + 9% reservation
fee**. *At check-in* (to landlord): **refundable security deposit (standard = one
month's rent), last-month rent advance if applicable, administrative tax if
applicable**. *During stay*: monthly rents (the prepaid last month, if any, covers
the final month). Deposit **varies by landlord** (flat €250, or two months, etc.) —
the listing states the exact terms. The **service/reservation fee is
non-refundable** in standard cancellations; it covers room verification + booking
support + ELH operations.

**Cancellation tiers** (`cancellation_policy`): **≥60 days before check-in → full
refund (minus applicable fees); 30–59 days → 50% refund; <30 days → no refund.**
Service fee non-refundable in standard cases.

**Refund exceptions.** *Room mismatch:* report within **24 h of check-in with
evidence (photos/videos)**; if valid, refund of first rent + deposit + service fee.
*Landlord cancellation:* ELH guarantees **relocation to a similar/superior room OR a
full refund**. *Replacement tenant:* a landlord may refund part/all if you find a
replacement; ELH can re-advertise the room.

**The 24-hour discrepancy window** (`evidence_window`): exactly **24 hours after
check-in** to report a discrepancy with evidence; later reports are harder to
process and may not qualify for the room-mismatch refund.

**Deposit refund** (`deposit_required`): refunded at check-out **minus deductions**
for damage to room/shared spaces; landlord assesses condition; full return if no
damage.

**What's included in rent / check-in process.** Documents (contract + house rules,
landlord-provided) arrive with the booking. Utilities included only up to per-room
caps (see §E); anything uncapped is paid to the provider directly.

**Verification & scam protection.** Every listing is personally verified (direct
landlord contact + in-person/virtual visit); "images may not be an exact
representation of the final product."

**Privacy** (`tenant_privacy`): ELH **does not disclose specific information about
current tenants**; demographic is Erasmus students / interns / young professionals.

**Landlord-facing** (5 entries, `audience: landlord`): free listings; payment
**transferred 48 h after reservation start** (funds held in custody until then);
only ID + IBAN required; conflict mediation is binding if direct resolution fails.

**Contact** (`contact_info`): hello@erasmuslifehousing.com · +351 932 483 834 ·
Travessa da Cara 14, Lisbon · Facebook "Erasmus Life Housing" · Instagram @erasmuslifehousing **Promotions** (note: marketing, time-bound, not cost
rules): `PROMO25` = 25% off service fee + €25 events voucher; an alternate entry
mentions €10 events credit + 50% off service fee — promotions overlap/change, so a
golden set should treat promo specifics as volatile.

---

## G. Subjective corpora coverage (descriptions & reviews)

`[CODE]` Two separate corpora, both built from the DB pre-embedding:

- **Descriptions** (`data/description_extractor.py`): one doc per **house**
  (`status='Validated'`) + one per **room** (`status='Available'`), text =
  `[HOUSE/ROOM — name]\nLocation: city, zone, neighbourhood\n\n{description}`,
  `LENGTH(TRIM(description)) >= MIN_TEXT_LENGTH` (30). Factual property prose.
- **Reviews** (`data/review_extractor.py`): one doc per **approved** review
  (`status='approved'`, `LENGTH(description) >= 30`), text = location + flat/room +
  title + review body. Metadata carries 5 numeric ratings: `overall, cleaning,
  communication, location, pricequality` (each 0–5). Subjective testimonials —
  the agent is instructed to treat them as opinions, not facts.

`[CORPUS]` **Attributes the corpora actually cover** (themes recurring in sampled text):

- *Descriptions:* room size in m², bed type (sofa bed / double), en-suite vs shared
  bathroom (incl. count, "3 shared bathrooms"), desk + wardrobe/storage, private
  balcony, in-room heating, bed linen/pillows provided, seasonal vs fixed pricing,
  extra-guest cost, last-month-deposit requirement, neighborhood character/location.
- *Reviews:* cleanliness, heating/warmth in winter, landlord responsiveness,
  natural light (mentioned), city view, kitchen equipment / washing machine, lift
  for moving luggage, private-bathroom cleanliness, internet/wifi reliability,
  desk/study suitability, safety (CCTV, digital entry), general recommend/experience
  sentiment. Reviews appear in multiple languages (English + Portuguese e.g. "Muito
  boa experiência").

**Notable GAPS** (things students plausibly ask about that the corpus may NOT
reliably contain — candidates for "out-of-corpus / weak-match" handling rather than
confident answers; the agent's weak-match thresholds in §I apply):

- **Specific named views** (e.g. "Tagus river view") — the system prompt itself uses
  this as the canonical *weak-match* example; "city view"/"sea view" exist as
  flags/text but a named-landmark view is not guaranteed.
- **Night-time noise / quietness** — asked about in the prompt's German example, but
  not a structured field; only sporadically present in reviews.
- **Distance/closeness to a specific university by name** — only via `near_landmark`
  ILIKE on zone/neighborhood/description text, not a measured field.
- **Party/nightlife suitability, smell, sunlight orientation, floor level, building
  age, accessibility specifics** — largely absent or anecdotal.
- **Landlord identity/personality beyond "responsive"** — out of scope by privacy
  policy.

These gaps are deliberate fodder for golden-set items that test honest "the corpus
doesn't confirm this" behaviour (weak-match flagging), not retrieval of a fact.

---

## H. `get_booking_stats` and `get_property_details` — I/O

### H.1 `get_property_details` (Tool 4) `[CODE]`

**Input:** `encoded_id` (room = 3-segment or house = 2-segment id from a search
result); `include_reviews` (default True).
**Output:** always a `house` block; `room` block only for a room-id lookup; optional
`reviews` aggregate; one-line `summary`.
- `HouseDetails`: flat_name, city/zone/neighborhood, lat/long, distance_to_transport,
  nearest_metro_lines (from static map), full_description, bathroom_count, area_sqm,
  internet_speed_mbps, full **amenities list** (27 house Y/N flags → labels),
  other_amenities_text, night_guests/pets/smoking allowed, gender_preference,
  status, `rooms_summary` (up to 30 housemate rooms with prices), `rooms_total`.
- `RoomDetails`: room_name, full_description, area_sqm, **amenities** (9 room flags),
  **bed_types** (6 bed flags), is_fixed_price, all three seasonal prices,
  extra_person_allowed + cost, deposit_required + value, last_month_deposit,
  administrative_tax, status.
- `reviews` (`ReviewsAggregate`): count, the five average ratings, and the **3 most
  recent** approved reviews (title + 200-char excerpt). Scoped to the room (room
  lookup) or whole house (house lookup).

### H.2 `get_booking_stats` (Tool 5) `[CODE]` — INTERNAL ONLY

**Input:** `metric` (one of 7), optional `city`, `zone`, `period_start`,
`period_end`, `top_n` (1–50, default 10), `group_by` (subset of
`city, zone, season, year, month`).
**Metrics:** `occupancy_rate` (**requires both period bounds**), `top_zones_by_bookings`,
`avg_booking_duration_months`, `avg_lead_time_days`, `seasonal_demand` (always grouped
by season), `avg_overall_rating` (joins `review`), `room_inventory_count` (city/zone
only; ignores time).
**Output:** `data_points` (per surviving bucket: label, value, sample_size),
`warnings`, a mandatory **GDPR/k-anonymity disclaimer**, `summary`,
`total_underlying_rows`, `suppressed_buckets`.
**Privacy guarantees:** **k-anonymity, k=5** — buckets backed by fewer than 5
records are suppressed; sample sizes shown are post-suppression. SQL builders are
wrapped by a PII guard (§I).

---

## I. Out-of-scope boundaries (what the system refuses / is designed not to do)

`[CODE]`

1. **No individual / row-level data.** `get_booking_stats` returns **only
   aggregates** with **k-anonymity (k=5)**; sub-5 buckets are suppressed and every
   response carries a non-distribution disclaimer. It is **internal-team only** by
   design (description states "Not a student-facing tool"; gating itself lives in
   the orchestrator).
2. **PII tables are hard-blocked.** `tools/get_booking_stats/_safety.py` raises
   `PIISafetyError` if any stats SQL references the forbidden tables
   **`users, payment, email, question, reply`**. Tool 5 is restricted to
   `reservation, house, room, review` (design decision D3.9). → No payment data,
   user accounts, emails, or support threads are reachable.
3. **No tenant personal data.** Policy `tenant_privacy`: ELH does not disclose
   specifics about current tenants/housemates.
4. **No landlord personal/contact data exposed.** Property and stats outputs carry
   **no landlord name, phone, email, or IBAN** (those live in the blocked PII
   tables / are landlord-onboarding-only). The only contact surfaced is ELH's own
   (`contact_info`). A request for a landlord's personal contact has no tool that can
   answer it.
5. **No fabrication / grounding requirement.** System prompt: answers must be
   grounded in tool outputs; "Do not fabricate prices, availability, policies, or
   property details … If your tools cannot answer, say so honestly."
6. **Weak-match honesty (semantic search).** Score thresholds (prompt rule 13):
   ≥0.7 confident; 0.5–0.7 hedge; **<0.5 → explicitly tell the user the corpus does
   not confirm the specific claim** and offer closest context only. Drives the §G
   gap cases.
7. **Entity disambiguation (rule 12).** Ambiguous "hosts/staff/they/team" → the
   agent must ask whether the user means **the ELH team** or **the landlords**
   before searching.
8. **Anti-retry / no-loop discipline** (rules 7, error-handling): tools are not
   re-called with near-identical params chasing a better answer; 0-result searches
   broaden at most once, then report honestly.

---

## J. Ground-truth anchor rooms `[DB 2026-06-19]`

Eight concrete rooms (latest version, `status='Available'`, positive prices),
spanning the autumn-price range across both cities and varied in every flag
`compute_total_cost` consumes. Use these to hand-compute exact M2 totals. The
**encoded room id** for `compute_total_cost` / `get_property_details` is
`idhouse|idroom|dateupdate` (all three columns below).

| # | City / zone | idhouse | idroom | dateupdate | spring | summer | autumn | fixed? | deposit | depositvalue | lastmonth | admin tax | extra allowed | extra cost |
|---|-------------|---------|--------|-----------|--------|--------|--------|--------|---------|--------------|-----------|-----------|---------------|------------|
| A1 | Lisbon / Intendente | `HSE_D24DE65F` | `RM_HSE_D24DE65F_5` | 2023-03-17 | 220 | 220 | 220 | **Y** | Y | 160 | N | 70 | N | (95) |
| A2 | Lisbon / Santos | `HSE_20BD910F` | `RM_HSE_20BD910F_3` | 2021-05-09 | 600 | 600 | 600 | **Y** | Y | 635 | N | 125 | N | (60) |
| A3 | Lisbon / Mouraria | `HSE_78101504` | `RM_HSE_78101504_4` | 2020-11-18 | 980 | 980 | 980 | **Y** | Y | 1140 | N | 175 | **Y** | 95 |
| A4 | Porto / Boavista | `HSE_0ACCD708` | `RM_HSE_0ACCD708_2` | 2022-08-09 | 265 | 215 | 310 | N | Y | 170 | N | 160 | N | (100) |
| A5 | Porto / Campanhã | `HSE_3B7120EC` | `RM_HSE_3B7120EC_2` | 2023-08-03 | 700 | 700 | 700 | **Y** | Y | 1115 | N | 70 | **Y** | 55 |
| A6 | Porto / Foz do Douro | `HSE_8858E7CB` | `RM_HSE_8858E7CB_1` | 2021-12-14 | 1255 | 1010 | 1500 | N | Y | 1465 | N | 145 | **Y** | 70 |
| A7 | Lisbon / Graça | `HSE_4882F9A9` | `RM_HSE_4882F9A9_7` | 2022-07-04 | 240 | 240 | 240 | **Y** | Y | 360 | N | 145 | **Y** | 110 |
| A8 | Lisbon / Graça | `HSE_4882F9A9` | `RM_HSE_4882F9A9_3` | 2022-07-04 | 210 | 175 | 250 | N | **N** | (245) | **Y** | 110 | **Y** | 95 |

All amounts in EUR. `( )` around an extra-person cost = `extrapersonallowed='N'`, so
that cost is **never charged** (the tool ignores it). `( )` around A8's depositvalue
= `deposit='N'`, so the security deposit is **€0** and `depositvalue` is ignored.

**Coverage notes / deliberate edge cases:**
- **Fixed vs seasonal:** A1–A3, A5, A7 are `fixedprice='Y'` (all-season flat);
  A4, A6, A8 are seasonal (autumn ≥ spring ≥ summer — note A6 spans €1010–€1500).
- **`lastmonthdeposit='Y'` is rare** (only A8 of these eight, consistent with the
  catalogue) → A8 exercises the last-month-advance branch (final month prepaid at
  check-in, dropped from monthly billing).
- **A8 deposit edge case:** `deposit='N'` ⇒ `refundable_at_checkout=€0` even though a
  `depositvalue` (245) is stored. Confirms the tool keys on the **flag**, not the value.
- **Extra-person:** A3, A5, A6, A7, A8 allow it (surcharge × every month when opted
  in); A1, A2, A4 do not (their stored cost is inert).

**Verified worked totals** (run through the frozen `_compute`, no DB, half-up 2 dp):

- **A1** — fixed €220, check-in 2026-09-01 → check-out 2027-01-15 (5 autumn months,
  no extra person): booking **€319.00** (= 220 + 9%×1100), at-check-in **€230.00**
  (= deposit 160 + admin 70; no last-month), monthly **€220.00**, total
  **€1 429.00**, out-of-pocket **€1 269.00**, refundable **€160.00**.
- **A8** — seasonal, check-in 2026-09-01 → check-out 2027-06-30 (10 cross-season
  months: Sep–Feb autumn €250, Mar–Jun spring €210): booking **€460.60**
  (= first month 250 + 9%×Σrent 2 340 = 210.60), at-check-in **€320.00**
  (= last-month advance 210 [June, spring] + admin 110; **deposit €0**), `monthly_recurring=None`
  (mixed rates → per-month breakdown), total **€2 660.60**, out-of-pocket **€2 660.60**
  (nothing refundable). With `extra_person=True` (+€95 × 10 = €950): total **€3 610.60**.

---

## Summary

- **Cities (2):** Lisbon, Porto (hard enum).
- **Total rooms:** **932 available room rows** (Lisbon **556** / Porto **376**) =
  **730 distinct latest-version rooms** (Lisbon **435** / Porto **295**). Lisbon has
  14 zones / 14 neighborhoods; Porto 9 / 11. (`[DB 2026-06-19]`.)
- **Median autumn price:** **Lisbon €980, Porto €895** (range €220–€2 355 Lisbon,
  −€20–€2 040 Porto; one dirty negative-price Porto room to exclude). Fixed-price is
  the majority (~55–61%).
- **Availability:** reservation calendar covers **2023-01 → 2024-11 only** → any 2026
  window has **0 overlaps**; **556 Lisbon rooms available for Sep 2026** (= the full
  structural set; nothing is excluded). Availability *exclusion* is only testable on
  2023–2024 windows.
- **Cost formula (one line):** `total_stay_cost = (first_month_rent + 9%×Σrent) +
  (deposit + last_month_advance + admin_tax) + Σ remaining-month rents +
  extra_person×N`, with `out_of_pocket = total − refundable deposit`; rents billed
  per calendar month at the season rate (autumn Sep–Feb / spring Mar–Jun / summer
  Jul–Aug), half-up to 2 dp.
- **Anchor rooms captured:** **8** (§J), spanning €220–€1 500 across both cities,
  with two fully verified worked totals (A1, A8).
- **Policy areas:** **27 entries across 10 categories** in `policies.yaml`.

All `[DB-REQUIRED]` placeholders from Step 0 are now resolved to `[DB 2026-06-19]`;
all `[CODE]` content is unchanged. The reference is ready to back golden-set authoring.
