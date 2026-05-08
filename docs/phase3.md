# Fase 3 — Specifiche Tool API

**Documento di design.** Architettura: Hybrid Tool-augmented RAG (no Text-to-SQL).
**Stato:** Decisione 1, 2, 3 chiuse. Decisioni 4-6 aperte.
**Data:** 6 maggio 2026
**Branch:** `feature/phase3-tools`

---

## Indice

1. [Architettura generale](#1-architettura-generale)
2. [Convenzioni trasversali](#2-convenzioni-trasversali)
3. [Tool 1 — `find_rooms`](#3-tool-1--find_rooms)
4. [Tool 2 — `find_available_rooms`](#4-tool-2--find_available_rooms)
5. [Tool 3 — `compute_total_cost`](#5-tool-3--compute_total_cost)
6. [Tool 4 — `get_property_details`](#6-tool-4--get_property_details)
7. [Tool 5 — `get_booking_stats`](#7-tool-5--get_booking_stats)
8. [Tool 6 — `answer_policy_question` (TBD)](#8-tool-6--answer_policy_question-tbd)
9. [Fallback Phase 2 RAG](#9-fallback-phase-2-rag)
10. [Riepilogo decisionale](#10-riepilogo-decisionale)

---

## 1. Architettura generale

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
                            │  PostgreSQL    │  (DB ELH: house, room,
                            │  + Pinecone    │   reservation, review, ...)
                            └────────────────┘
```

**Decisione architetturale chiave (chiusa):** *NO Text-to-SQL libero*. L'LLM
non genera mai SQL grezzo; sceglie solo tra tool predefiniti con schema
Pydantic. Motivazione GDPR + reliability: il team ELH ha richiesto esattamente
*"yes I prefer to change [response]"* su query ambigue (preferiscono cambiare
risposta piuttosto che fornire risultati incerti).

**Strategia fallback:**

1. Orchestrator analizza query → seleziona tool.
2. Se tool match ad alta confidenza → esegue tool, restituisce output.
3. Se nessun tool match → fallback a Phase 2 RAG (ricerca semantica esistente).
4. Se Phase 2 RAG non trova fonti rilevanti → messaggio template
   *"Ecco cosa so fare: [lista capabilities]"*.

---

## 2. Convenzioni trasversali

### 2.1 Tool interface (Decisione 1, chiusa)

Ogni tool è composto da:

* **Input:** classe Pydantic `<ToolName>Input` con validazione runtime
* **Output:** frozen `dataclass` con metodo `to_dict()` (full) e ove rilevante
  `to_dict_for_user()` (sanitized, senza campi interni come `sql_executed`)
* **Funzione:** decorata con `@register_tool(name, description, input_model)`,
  riceve un'istanza dell'input model validato

Registrazione single-source-of-truth in `TOOLS_REGISTRY: dict[str, ToolSpec]`,
popolato a import time. Dispatcher `execute_tool(name, payload)` valida il
payload e dispatcha la funzione, normalizzando errori in tre tipi:
`ToolNotFoundError`, `ToolValidationError`, `ToolExecutionError`.

Layout file: `src/elh_rag/tools/{base,errors,find_rooms,find_available_rooms,...}.py`
(flat structure).

### 2.2 Identificatori entità

Le tabelle DB hanno chiavi composite `(loc_idhouse, loc_dateupdate, idroom, dateupdate)`
per supportare il versioning (price drift). Per semplificare l'interfaccia con
l'LLM, usiamo **stringhe encoded**:

| Tipo | Formato | Esempio |
|---|---|---|
| Room ID | `H{house_id}_R{room_id}_{ISO8601_dateupdate}` | `H42_R3_2024-09-15T10:30:00` |
| House ID | `H{house_id}_{ISO8601_dateupdate}` | `H42_2024-09-15T10:30:00` |

Encoder/decoder in `src/elh_rag/tools/_room_id.py`.

### 2.3 Output dataclass condivise

| Dataclass | Usato da |
|---|---|
| `RoomMatch` | Tool 1, Tool 2, Tool 4 (lista risultati) |
| `CostLineItem` | Tool 3 (line items breakdown) |
| `StatPoint` | Tool 5 (data points aggregati) |

### 2.4 Stagionalità prezzi

Il DB ELH usa 3 fasce stagionali:

| Fascia | Mesi | Note |
|---|---|---|
| `springprice` | marzo–giugno | media stagione |
| `summerprice` | luglio–agosto | bassa stagione (Erasmus assenti) |
| `autumnprice` | settembre–febbraio | **alta stagione Erasmus** |

**Default per Tool 1** (date opzionali): mostra `autumnprice` (caso d'uso più frequente).
**Tool 2** (date obbligatorie): calcola **avg ponderato sui giorni** che cadono in
ciascuna stagione.

### 2.5 Mapping zone → linee metro

File `src/elh_rag/tools/_metro_lines.py` con dati statici Wikipedia (Lisbona +
Porto). Mappa zone/quartieri alle linee metro che li servono. Esempio:

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

### 3.1 Scopo

Ricerca strutturata di stanze su criteri multipli. Risponde alla maggior parte
delle query informative degli studenti (~70% del traffico atteso).

### 3.2 Esempi reali (dal meeting + marketing ELH)

**Q1:** *"Stanze per coppie sulla linea verde, max 5 persone"*
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

**Q3:** *"Porto, contratto annuale, vicino metro, accetta gatto"*
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

### 4.1 Scopo

Specializzazione di `find_rooms` con **date come vincolo hard**. Esegue check
di sovrapposizione contro `reservation` ed esclude room non realmente libere
nel periodo specificato. Calcola prezzi season-aware ponderati.

Esempio: query `2026-09-01 → 2027-01-31` → 100% giorni in `autumnprice`.
Query `2026-05-15 → 2026-08-31` → 47 giorni `springprice` + 62 `summerprice`.

### 4.2 Quando l'orchestrator sceglie Tool 2 vs Tool 1

| Query | Tool | Motivo |
|---|---|---|
| "Stanze libere dal 20 ago al 31 dic vicino NOVA" | **Tool 2** | "libere" + date specifiche |
| "Stanze couples linea verde da settembre" | **Tool 1** | "settembre" generico, no end date |
| "3 bedrooms free August 20 till end of December" | **Tool 2** | "free" + range esplicito |
| "Stanze Lisbona vicino metro" | **Tool 1** | nessuna data |

**Regola:** se la query contiene verbi tipo *free / available / libere* +
range date esplicito → Tool 2. Altrimenti Tool 1.

### 4.3 Esempi reali

**Q1** (marketing): *"3 bedrooms free Aug 20 – end of Dec close to NOVA, 3 Italian
girls, max 6 ppl, female only, 500€ bills included"*

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

### 5.1 Scopo

Dato `room_id` + periodo, restituisce il **costo totale all-in** con breakdown
per linea: affitto mensile season-aware, bills, cleaning, deposit, reservation
fee, administrative tax, eventuale extra-person.

### 5.2 Componenti del costo

| Voce | Sorgente | Tipo |
|---|---|---|
| Affitto mensile | `room.springprice/summerprice/autumnprice` (ponderato sui giorni) | ricorrente |
| Bills | tabella `expenses` (per house) | ricorrente |
| Cleaning | tabella `cleaning` (per house) | ricorrente |
| Reservation fee | funzione `compute_reservation_fee(room, months)` ⚠️ | **una tantum** |
| Deposit | `room.depositvalue` (o `room.lastmonthdeposit` se Y) | una tantum |
| Administrative tax | `room.administrativetax` | una tantum |
| Extra person | `room.extrapersoncost` se `extrapersonallowed=Y` | ricorrente |

⚠️ **TODO da meeting marketing 2026-05-06:** chiarire la formula esatta della
reservation fee. Allo stato attuale: funzione separata in `tools/_pricing.py`
con placeholder ragionevole, da aggiornare con la formula reale ELH una volta
nota.

### 5.3 Edge case — durata < `minreservemonths`

Se la durata richiesta è inferiore al `minreservemonths` della room, **il tool
calcola comunque il costo** ma aggiunge un warning all'output. Motivazione:
l'orchestrator può presentare il calcolo con disclaimer (*"Questa stanza richiede
minimo 5 mesi, la tua richiesta è di 2 — il landlord potrebbe rifiutare"*),
invece di forzare la decisione fuori dal tool.

---

## 6. Tool 4 — `get_property_details`

### 6.1 Scopo

Lookup completo di una **singola room** o **singola house** dato l'ID encoded.
Tipicamente chiamato come follow-up dopo `find_rooms` (*"dimmi di più sul
primo risultato"*).


### 6.2 Note di design

* **Discriminator `kind`** invece di due dataclass separate: più semplice da
  consumare per l'LLM (shape unica, controlla `kind`).
* **NO testo recensioni** in output: solo aggregati numerici. Per query tipo
  *"cosa dicono le recensioni?"*, l'orchestrator instrada su Phase 2 RAG
  (ricerca semantica sull'indice `elh-reviews`).
* **`current_availability`**: finestre libere calcolate via query inversa su
  `reservation`, orizzonte 12 mesi.

---

## 7. Tool 5 — `get_booking_stats`

### 7.1 Scopo

Aggregati statistici per il **team interno ELH** (~20% del traffico atteso).
Risponde a query operative su occupazione, durata media, top zone, paesi
clienti, pattern stagionali.

### 7.2 Vincoli GDPR (da meeting ELH 2026-05-05)

* ✅ Lettura ammessa: `reservation`, `house`, `room`, `review`
* ❌ Lettura **vietata**: `users`, `payment`, `email`, `question`, `reply`
* Solo aggregati (count, avg, distribution), **mai dati riga-per-riga**
* **k-anonymity con k=5**: se un aggregato si basa su < 5 record, restituisce
  `data_points=[]` + warning "insufficient data for privacy-safe aggregation"
* **Disclaimer obbligatorio** in ogni output

### 7.3 Esempi

**Q1:** *"Tasso di occupazione di Lisbona?"*
```json
{"metric": "occupancy_rate", "city": "Lisbon"}
```

**Q2:** *"Top 5 paesi degli studenti?"*
```json
{"metric": "top_countries", "top_n": 5}
```

**Q3** (NON ammessa): *"Mostrami tutte le prenotazioni di gennaio"*
→ Tool 5 NON gestisce. Fallback su risposta tipo *"Non posso mostrare prenotazioni
individuali"*.

---

## 8. Tool 6 — `answer_policy_question` (TBD)

### 8.1 Scopo

Knowledge base di FAQ ELH per policy aziendali, contratti, fees, cancellazioni,
regole, supporto. Risponde alla **maggioranza** delle domande del marketing
analizzate (10 su 16 = 62%).

### 8.2 Stato

⏸️ **Decisione 5 — APERTA.** Da definire dopo il meeting marketing,
quando avremo il materiale FAQ completo.

### 8.3 Esempi di query in scope (preview)

* *"Do you accept long term rental? Max e min?"*
* *"How much reservation fee will I pay?"* (generica, non per stanza specifica)
* *"Accept families? Young professionals?"*
* *"Overnight guests allowed? Pay extra?"*
* *"Provide contract?"*
* *"Communication with landlord after move-in?"*
* *"What if room not as listed? Cancel and refund?"*
* *"Bring my guitar?"*

### 8.4 Approccio probabile (da confermare)

* Knowledge base statica caricata su Pinecone (terzo indice o sotto-namespace
  di `elh-descriptions`)
* Tool 6 fa retrieval semantico + reranking + generazione, simile a Phase 2 RAG
  ma su corpus FAQ invece di descriptions
* Vantaggio: risposta tipata "policy" con citazione esplicita della fonte
  ("Source: ELH Terms of Service, section 4.2")

---

## 9. Fallback Phase 2 RAG

### 9.1 Quando l'orchestrator cade su Phase 2 RAG

* Nessun tool match con confidenza sufficiente
* Query semantica/qualitativa che non si traduce in parametri strutturati
* Esempi:
  * *"Cosa dicono gli studenti italiani della casa di Bairro Alto?"* → review search
  * *"Stanze accoglienti vicino vita notturna"* → semantic match
  * *"Posso lavorare in smart working dalla camera?"* → soft criteria multipli

### 9.2 Implementazione

Nessun cambio rispetto a Phase 2: pipeline esistente
(intent_router → retriever → reranker → generator). L'orchestrator passa la
query nativa all'API Phase 2 RAG e ne presenta la `RAGResponse` direttamente.

---

## 10. Riepilogo decisionale

### 10.1 Decisioni chiuse

| # | Argomento | Esito |
|---|---|---|
| **D1** | Tool interface | Pydantic input + frozen dataclass output + decoratore registry |
| **D2** | Layout file | Flat: `src/elh_rag/tools/{base,errors,find_rooms,...}.py` |
| **D3.1** | Tool 1 parametri | 29 parametri (16 strutturali + 11 amenity esplicite + 1 generico) |
| **D3.2** | Tool 2 ereditarietà | `class FindAvailableRoomsInput(FindRoomsInput)` |
| **D3.3** | Prezzi season-aware | Tool 1 default `autumnprice`; Tool 2 avg ponderato |
| **D3.4** | `RoomMatch` condivisa | tra Tool 1, 2, 4 |
| **D3.5** | Room ID encoding | stringa opaca `"H{h}_R{r}_{ISO}"` |
| **D3.6** | Tool 3 promo code | nascosto (non parametro pubblico) |
| **D3.7** | Tool 4 discriminator | `kind` Literal + dataclass unica |
| **D3.8** | Tool 5 metric | Literal di 7 valori fissi (no SQL libero) |
| **D3.9** | Tool 5 GDPR | k-anonymity k=5 + disclaimer obbligatorio |
| **D3.10** | Output sanitization | `to_dict()` full + `to_dict_for_user()` sanitized |

### 10.2 Decisioni aperte

| # | Argomento | Quando |
|---|---|---|
| **D4** | Orchestrator decision logic (LLM tool selection, fallback threshold, prompt) | Dopo implementazione Tool 1+2 |
| **D5** | Tool 6 knowledge base policy (struttura, indice Pinecone, retrieval) | Dopo meeting marketing ELH |
| **D6** | Edge case + safety (logging, rate limiting, error handling) | Pre-merge feature/phase3-tools |

### 10.3 TODO espliciti

* ⚠️ Reservation fee formula (Tool 3): chiarire al meeting marketing 2026-05-06
* ⚠️ Knowledge base FAQ (Tool 6): richiedere materiale al marketing
* ⚠️ Distribuzione `minreservemonths` (deployata): verificare media ~5 dopo
  re-populate del DB

---

## Appendice A — Mapping query reali → tool

Sintesi delle 16 domande reali ricevute dal marketing manager ELH:

| # | Query | Tool |
|---|---|---|
| 1 | Couples + green line + max 5 ppl + sett-gen | `find_rooms` |
| 2 | 3 stanze + 20 ago–fine dic + NOVA + 3 ragazze ITA + female + 500€ (bills via descr.) | `find_available_rooms` |
| 3 | Porto + year contract + metro + accepts cat | `find_rooms` |
| 4 | "Long term rental? Max e min?" | `answer_policy` |
| 5 | "Reservation fee?" (generica) | `answer_policy` |
| 6 | "Accept families?" | `answer_policy` |
| 7 | "Strictly students or young professionals?" | `answer_policy` |
| 8 | "Overnight guests? Pay extra?" | `answer_policy` |
| 9 | "Girlfriend weekend visit, how works?" | `answer_policy` |
| 10 | "Cheapest rooms, internal ok" | `find_rooms` (sort_by=price_asc, must_have_window=False) |
| 11 | "Room not as listed? Cancel + refund?" | `answer_policy` |
| 12 | "Flatmate broke the rules?" | `answer_policy` |
| 13 | "Provide contract?" | `answer_policy` |
| 14 | "Communication with landlord after move-in?" | `answer_policy` |
| 15 | "Flats only for girls?" | `find_rooms` (gender_preference=female_only) |
| 16 | "Bring my guitar?" | `answer_policy` |

**Distribuzione attesa:**
* `find_rooms` / `find_available_rooms`: 6/16 (38%)
* `answer_policy_question`: 10/16 (62%)

Conferma l'intuizione del meeting: **policy è importante quanto la ricerca**.