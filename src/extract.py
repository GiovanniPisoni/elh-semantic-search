import os
import psycopg2
import psycopg2.extras
from datetime import date
from dotenv import load_dotenv

load_dotenv()

DB_URI = os.getenv("DB_URI")
MIN_TEXT_LENGTH = 30
REVIEW_STATUS = "approved"

EXTRACTION_QUERY = """
    SELECT
        rv.idreview,
        rv.description          AS review_text,
        rv.title                AS review_title,
        rv.datereview,
        rv.overallratings,
        rv.cleaningratings,
        rv.communicationratings,
        rv.locationratings,
        rv.pricequalityratings,
        h.idhouse,
        h.city,
        h.zone,
        h.neighboorhood,
        h.flatname,
        r.idroom,
        r.roomname
    FROM review rv
    JOIN room r
        ON  rv.idroom         = r.idroom
        AND rv.dateupdate     = r.dateupdate
        AND rv.loc_idhouse    = r.loc_idhouse
        AND rv.loc_dateupdate = r.loc_dateupdate
    JOIN house h
        ON  r.loc_idhouse    = h.idhouse
        AND r.loc_dateupdate = h.dateupdate
    WHERE rv.status = %s
      AND LENGTH(rv.description) >= %s
    ORDER BY rv.datereview DESC
"""

def build_enriched_text(row: dict) -> str:
    parts = []
    location_parts = [p for p in [row.get("city"), row.get("zone")] if p]
    
    if location_parts:
        parts.append(", ".join(p.strip() for p in location_parts))
    
    flatname = (row.get("flatname") or "").strip()
    roomname = (row.get("roomname") or "").strip()
    
    if flatname and roomname:
        parts.append(f"{flatname} — {roomname}")
    elif flatname:
        parts.append(flatname)
   
    title = (row.get("review_title") or "").strip()
    
    if title:
        parts.append(f"Review: {title}")
    
    text = (row.get("review_text") or "").strip()
    
    if text:
        parts.append(text)
    return ". ".join(filter(None, parts))


def fetch_documents(verbose: bool = False) -> list[dict]:
    conn = psycopg2.connect(DB_URI)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(EXTRACTION_QUERY, (REVIEW_STATUS, MIN_TEXT_LENGTH))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    documents = []
    skipped = 0
    
    for row in rows:
        row = dict(row)
        enriched_text = build_enriched_text(row)
        if len(enriched_text) < MIN_TEXT_LENGTH:
            skipped += 1
            continue

        doc = {
            "text": enriched_text,
            "metadata": {
                "id":                    row["idreview"],
                "source":                "review",
                "city":                  (row.get("city") or "").strip(),
                "zone":                  (row.get("zone") or "").strip(),
                "neighbourhood":         (row.get("neighboorhood") or "").strip(),
                "flatname":              (row.get("flatname") or "").strip(),
                "roomname":              (row.get("roomname") or "").strip(),
                "idhouse":               row.get("idhouse", ""),
                "idroom":                row.get("idroom", ""),
                "overall_rating":        int(row.get("overallratings") or 0),
                "cleaning_rating":       int(row.get("cleaningratings") or 0),
                "communication_rating":  int(row.get("communicationratings") or 0),
                "location_rating":       int(row.get("locationratings") or 0),
                "pricequality_rating":   int(row.get("pricequalityratings") or 0),
                "date_review":           row["datereview"].isoformat() if isinstance(row.get("datereview"), date) else str(row.get("datereview", "")),
                "review_title":          (row.get("review_title") or "").strip(),
                "review_text_original":  (row.get("review_text") or "").strip(),
            }
        }
        documents.append(doc)

    if verbose:
        print(f"Fetched from Supabase: {len(rows)}")
        print(f"Documents built: {len(documents)}")
        print(f"Skipped (too short): {skipped}")
        cities = {}
        for doc in documents:
            c = doc["metadata"]["city"] or "Unknown"
            cities[c] = cities.get(c, 0) + 1
        for city, count in sorted(cities.items(), key=lambda x: -x[1]):
            print(f"{city:<15} {count} reviews")

    return documents

if __name__ == "__main__":
    docs = fetch_documents(verbose=True)
    print(f"\nTotal documents ready for indexing: {len(docs)}")
    print("\nSample document:")
    if docs:
        print(f"  text    : {docs[0]['text'][:120]}...")
        print(f"  city    : {docs[0]['metadata']['city']}")
        print(f"  rating  : {docs[0]['metadata']['overall_rating']}/5")