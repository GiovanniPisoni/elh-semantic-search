# ELH Semantic Search — RAG-Based System for Erasmus Life Housing

> Master's Thesis Project · Università degli Studi di Milano-Bicocca · 2025

A **Retrieval-Augmented Generation (RAG)** system that enables semantic search over Erasmus Life Housing's unstructured textual data — reviews, property descriptions, and listing details — using state-of-the-art NLP techniques.

---

## Overview

ELH's platform contains a wealth of structured data (prices, availability, amenities) already accessible through standard filters. However, a large category of data remains untapped: the **free-form text** written by students and landlords — reviews, property descriptions, and listing narratives.

This project builds a conversational AI system that makes this data queryable in natural language, answering questions that no SQL filter or dashboard can address:

- *"Find rooms where students mention a comfortable bed"*
- *"Which landlords are described as responsive to problems?"*
- *"Properties in a quiet area suitable for studying"*
- *"Apartments with complaints about noise or maintenance"*

The system retrieves semantically relevant text from the real database and synthesises accurate, grounded answers — never fabricating information.

---

## Architecture

```
Student query (natural language)
        │
        ▼
┌───────────────────┐
│   Query Rewriting  │  ← LLM rephrases query for better retrieval
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Vector Retrieval  │  ← Semantic search over ChromaDB
│  (ChromaDB)        │     embeddings: paraphrase-multilingual-mpnet-base-v2
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│    Re-ranking      │  ← Cross-encoder reranks top-k results
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Answer Generation │  ← Claude API synthesises grounded response
│  (Claude API)      │     citing real reviews as sources
└───────────────────┘
```

**Data sources indexed:**
| Table | Field | Content |
|---|---|---|
| `review` | `description`, `title` | Student reviews post-stay |
| `house` | `description`, `otherameneties` | Landlord property descriptions |
| `room` | `description` | Landlord room descriptions |

---

## Tech Stack

| Component | Technology | Reason |
|---|---|---|
| LLM | Claude (Anthropic API) | Best-in-class instruction following |
| Orchestration | LangChain | Modular RAG pipeline primitives |
| Embeddings | `paraphrase-multilingual-mpnet-base-v2` | Native EN + PT support |
| Vector Store | ChromaDB | Lightweight, runs fully local |
| Database | PostgreSQL (Supabase) | ELH operational database |
| Evaluation | RAGAS | Faithfulness & answer relevance metrics |
| Interface | Streamlit | Rapid prototyping of chat UI |
| Language | Python 3.12 | Stable ML ecosystem support |

---

## Project Structure

```
elh-rag-thesis/
│
├── src/
│   ├── extract.py        # Data extraction from Supabase
│   ├── indexer.py        # Embedding generation & ChromaDB indexing
│   ├── pipeline.py       # RAG pipeline (Naive → Advanced)
│   └── app.py            # Streamlit chat interface
│
├── evaluation/
│   ├── golden_dataset.xlsx   # 50 hand-crafted Q&A pairs for evaluation
│   └── evaluate.py           # RAGAS metrics runner
│
├── tests/
│   └── test_utils.py     # Unit tests for pure functions
│
├── data/                 # Local data cache (git-ignored)
│   └── chroma_db/        # Persisted vector store (git-ignored)
│
├── .env.template         # Environment variable template
├── requirements.txt      # Python dependencies
├── verify_setup.py       # Setup verification script
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.12
- Access to ELH Supabase database
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com))

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/elh-rag-thesis.git
cd elh-rag-thesis

# 2. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.template .env
# Edit .env and fill in your credentials
```

### Environment Variables

Create a `.env` file based on `.env.template`:

```env
DB_URI=postgresql://...           # Supabase connection string
ANTHROPIC_API_KEY=sk-ant-...      # Anthropic API key
EMBEDDING_MODEL=paraphrase-multilingual-mpnet-base-v2
CHROMA_PATH=./data/chroma_db
LLM_MODEL=claude-sonnet-4-20250514
LLM_TEMPERATURE=0.1
RETRIEVAL_TOP_K=5
```

### Verify Setup

```bash
python verify_setup.py
```

All checks should pass before proceeding.

---

## Usage

```bash
# Step 1 — Extract and index data from Supabase
python src/extract.py
python src/indexer.py

# Step 2 — Run the chat interface
streamlit run src/app.py

# Step 3 — Run evaluation against golden dataset
python evaluation/evaluate.py
```

---

## Evaluation Methodology

The system is evaluated on a **golden dataset** of 50 hand-crafted question–answer pairs, covering all six KPI categories identified in the ELH project documentation:

| Category | # Questions | Example |
|---|---|---|
| Comfort & bed | 8 | *"Rooms with comfortable beds"* |
| Cleanliness | 8 | *"Properties praised for cleanliness"* |
| WiFi & internet | 7 | *"Fast and reliable WiFi"* |
| Location | 8 | *"Quiet area, good transport links"* |
| Landlord | 10 | *"Responsive and helpful landlords"* |
| Price & value | 9 | *"Good value for money"* |

**Metrics measured:**

| Metric | Description | Tool |
|---|---|---|
| Faithfulness | Is the answer grounded in the retrieved reviews? | RAGAS |
| Answer Relevance | Does the answer actually address the question? | RAGAS |
| Recall@k | Were the relevant reviews retrieved? | Custom |
| Precision@k | Are retrieved reviews actually relevant? | Custom |
| Latency | End-to-end response time | `time` |

Results are compared across **Naive RAG** (baseline) and **Advanced RAG** (query rewriting + re-ranking).

---

## Thesis Context

This project constitutes the **AI layer** of a broader Master's thesis divided into two complementary parts:

- **Part 1 (colleague):** Data engineering — design and implementation of a Data Warehouse (DW) from the ELH operational database, following a data-driven, bottom-up methodology with DFM schema design.
- **Part 2 (this repo):** Applied AI — RAG system operating directly on the operational database, targeting unstructured textual data that cannot be queried through conventional means.

The two parts are designed to be complementary: the DW provides structured analytical intelligence for management, while this system provides semantic intelligence for end users and operational queries.

---

## Limitations

- **Synthetic data:** The database used for development contains synthetically generated reviews and descriptions. System performance on real ELH data may differ.
- **Multilingual corpus:** Reviews are primarily in English (~70%) and Portuguese (~30%). The embedding model handles both, but mixed-language queries may affect retrieval precision.
- **Review volume:** ELH's actual review rate is approximately 3% of bookings, which limits corpus coverage per property.
- **No real-time updates:** The vector index is built offline and requires periodic re-indexing as new reviews are added.

---

## Roadmap

- [x] Project setup & environment configuration
- [x] Database population with coherent synthetic data
- [ ] Data extraction pipeline (`extract.py`)
- [ ] Embedding & indexing pipeline (`indexer.py`)
- [ ] Naive RAG baseline (`pipeline.py`)
- [ ] Advanced RAG with query rewriting & re-ranking
- [ ] Streamlit chat interface (`app.py`)
- [ ] Golden dataset construction
- [ ] RAGAS evaluation
- [ ] Thesis writing

---

## Author

**Giovanni Pisoni**
Master's student · Università degli Studi di Milano-Bicocca
Thesis supervisor: Prof. Enrico Gallinucci

---

## License

This project is developed for academic purposes as part of a Master's thesis.
The codebase is private and not intended for public distribution.
