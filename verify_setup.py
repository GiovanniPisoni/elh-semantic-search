"""
verify_setup.py
━━━━━━━━━━━━━━━
Verifica che tutto il setup sia corretto prima di iniziare.
Esegui con: python verify_setup.py

Controlla:
  1. Variabili d'ambiente caricate
  2. Connessione al DB Supabase
  3. Librerie installate correttamente
  4. API Anthropic raggiungibile
  5. Modello di embedding scaricabile
"""

import sys

def check(label, fn):
    try:
        result = fn()
        print(f"  ✓  {label}" + (f" — {result}" if result else ""))
        return True
    except Exception as e:
        print(f"  ✗  {label} — ERRORE: {e}")
        return False

print("\n" + "=" * 50)
print("ELH RAG — Verifica setup")
print("=" * 50 + "\n")

all_ok = True

# ── 1. Variabili d'ambiente ───────────────────────────────
print("[1] Variabili d'ambiente (.env)")
from dotenv import load_dotenv
import os
load_dotenv()

for var in ["DB_URI", "ANTHROPIC_API_KEY", "EMBEDDING_MODEL", "CHROMA_PATH"]:
    ok = check(var, lambda v=var: "OK" if os.getenv(v) else (_ for _ in ()).throw(ValueError(f"{v} non trovata nel .env")))
    all_ok = all_ok and ok

# ── 2. Connessione DB ─────────────────────────────────────
print("\n[2] Connessione Supabase")
def test_db():
    import psycopg2
    conn = psycopg2.connect(os.getenv("DB_URI"))
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM review")
    count = cur.fetchone()[0]
    conn.close()
    return f"{count} review nel DB"

ok = check("Supabase connection", test_db)
all_ok = all_ok and ok

# ── 3. Librerie ───────────────────────────────────────────
print("\n[3] Librerie Python")
libs = [
    ("anthropic",            lambda: __import__("anthropic").__version__),
    ("langchain",            lambda: __import__("langchain").__version__),
    ("chromadb",             lambda: __import__("chromadb").__version__),
    ("sentence_transformers",lambda: __import__("sentence_transformers").__version__),
    ("streamlit",            lambda: __import__("streamlit").__version__),
    ("ragas",                lambda: __import__("ragas").__version__),
    ("pandas",               lambda: __import__("pandas").__version__),
]
for name, fn in libs:
    ok = check(name, fn)
    all_ok = all_ok and ok

# ── 4. API Anthropic ──────────────────────────────────────
print("\n[4] API Anthropic")
def test_anthropic():
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{"role": "user", "content": "Reply with just: OK"}]
    )
    return msg.content[0].text.strip()

ok = check("Claude API call", test_anthropic)
all_ok = all_ok and ok

# ── 5. Modello di embedding ───────────────────────────────
print("\n[5] Modello di embedding")
def test_embedding():
    from sentence_transformers import SentenceTransformer
    model_name = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-mpnet-base-v2")
    model = SentenceTransformer(model_name)
    vec   = model.encode("test sentence")
    return f"dim={len(vec)}, model={model_name}"

ok = check("SentenceTransformer", test_embedding)
all_ok = all_ok and ok

# ── Risultato finale ──────────────────────────────────────
print("\n" + "=" * 50)
if all_ok:
    print("✓  Tutto OK — puoi procedere con lo Step 2")
else:
    print("✗  Alcuni check hanno fallito — risolvi gli errori prima di procedere")
print("=" * 50 + "\n")
