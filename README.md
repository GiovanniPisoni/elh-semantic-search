# ELH Semantic Search — RAG-Based System for Erasmus Life Housing

> Master's Thesis Project · Alma Mater Studiorum Università di Bologna · A.Y. 2026-2027

A **Retrieval-Augmented Generation (RAG)** system that enables semantic search over Erasmus Life Housing's unstructured textual data — reviews, property descriptions, and listing details — using state-of-the-art NLP techniques.

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

This project builds a system that makes ELH's unstructured textual data **queryable in natural language**. A student types a question as they would ask a friend, and the system retrieves and synthesises relevant information from real reviews and descriptions — without fabricating anything.

**Examples of questions the system can answer:**

- *"Find rooms where students mention a comfortable bed"*
- *"Which landlords are described as responsive to problems?"*
- *"Properties in a quiet area suitable for studying"*
- *"Apartments with complaints about noise or maintenance issues"*
- *"Rooms praised for cleanliness and natural light"*
- *"Places suitable for students with pets"*

These are questions that no SQL filter, no dropdown menu, and no dashboard can answer — because the answers live only in the text.

---

## Why RAG and not something else

Two simpler alternatives were evaluated and discarded:

**Standard search filters** already exist and cover structured data well. Adding more filters cannot capture semantic concepts like "quiet", "cosy", or "responsive landlord" — these are qualitative judgements expressed in free text.

**Text-to-SQL on analytical KPIs** was considered for a management-facing tool, but carries high risk of hallucination on numerical data. A system that generates incorrect revenue figures or occupancy rates is worse than no system at all.

**RAG on unstructured text** is the right fit because the AI never generates numbers or facts from memory — it reads real text already in the database and synthesises it. The risk of hallucination is minimal, and the value added is genuine: answering questions that were previously unanswerable.

## Data Sources

The system indexes three categories of textual data from the ELH operational database:

| Source | Table | Field | Content |
|---|---|---|---|
| Student reviews | `review` | `description`, `title` | Post-stay feedback on comfort, cleanliness, landlord, location |
| Property descriptions | `house` | `description`, `otherameneties` | Landlord narratives about the apartment |
| Room descriptions | `room` | `description` | Landlord details about individual rooms |

Messages exchanged between students and landlords were evaluated but excluded: they are private between the two parties and not accessible to the ELH team.

---

## Architecture

```
Student query (natural language)
        │
        ▼
┌─────────────────────┐
│   Query Rewriting   │  ← LLM rephrases the query for better retrieval
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Semantic Retrieval │  ← ChromaDB vector search
│    (ChromaDB)       │     model: paraphrase-multilingual-mpnet-base-v2
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│     Re-ranking      │  ← Cross-encoder reranks top-k results by relevance
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Answer Generation  │  ← Anthropic API synthesises a grounded response
│    (Anthropic API)  │     citing real reviews and descriptions as sources
└─────────────────────┘
```

---

## Tech Stack

| Component | Technology | Reason |
|---|---|---|
| LLM | Anthropic API (Claude) | Best-in-class instruction following and faithfulness |
| Orchestration | LangChain | Modular RAG pipeline components |
| Embeddings | `paraphrase-multilingual-mpnet-base-v2` | Native English + Portuguese support |
| Vector Store | ChromaDB | Lightweight, runs fully local, no external service |
| Database | PostgreSQL (Supabase) | ELH operational database |
| Evaluation | RAGAS | Faithfulness and answer relevance metrics |
| Interface | Streamlit | Conversational chat UI |
| Language | Python 3.12 | Stable ML ecosystem |

---

## Author

**Giovanni Pisoni**: Master's Student · Alma Mater Studiorum Università di Bologna

Supervisor: Prof. Enrico Gallinucci

---

## License

This project is developed for academic purposes as part of a Master's thesis.
The repository is private and not intended for public distribution.