import os
import json
import psycopg2
import psycopg2.extras
from datetime import date
from dotenv import load_dotenv

load_dotenv()

DB_URI = os.getenv("DB_URI")
DATA_PATH = os.getenv("DATA_PATH", "./data")
OUTPUT = os.path.join(DATA_PATH, "reviews_raw.json")

MIN_TEXT_LENGTH = 30
REVIEW_STATUS = "approved"

EXTRACTION_QUERY = """
    SELECT
        rv.idreview,
        rv.description  AS review_text,
        rv.title        AS review_title,
        rv.datereview,
        rv.overallratings,
        rv.cleaningratings,
        rv.communicationratings,
        rv.locationratings,
        rv.pricequalityratings,
        rv. status      AS review_status,

        h.idhouse,
        h.city,
        h.zone,
        h.neighboorhood,
        h.flatname,

        r.idroom,
        r.roomname
    
    FROM review rv

    JOIN room r
        ON rv.idroom            = r.idroom
        AND rv.dateupdate       = r.dateupdate
        AND rv.loc_idhouse      = r.loc_idhouse
        AND rv.loc_dateupdate   = r.loc_dateupdate

    JOIN house h
        ON r.loc_idhouse        = h.idhouse
        AND r.loc_dateupdate    = h.dateupdate

    WHERE rv.status = %s
        AND LENGTH(rv.description) >= %s

    ORDER BY rv.datereview DESC
"""

# Document enrichment

def build_enriched_text(row: dict) -> str:
    parts = []

    location_parts = [p for p in [row.get("city"), row.get("zone")] if p]
    if location_parts:
        location = ", ".join(p.strip() for p in location_parts)
        parts.append(location)

    flatname = (row.get("flatname") or "").strip()
    roomname = (row.get("roomname") or "").strip()
    if flatname and roomname:
        parts.append(f"{flatname} - {roomname}")
    elif flatname:
        parts.append(flatname)

    title = (row.get("review_title") or "").strip()
    if title:
        parts.append(f"Review: {title}")


    text = (row.get("review_text") or "").strip()
    if text:
        parts.append(text)

    return ". ".join(filter(None, parts))

def json_serializer(obj):
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def extract():
    print("=" * 55)
    print("ELH PROJECT: Data Extraction")
    print("=" * 55)

    os.makedirs(DATA_PATH, exist_ok=True)

    print(f"\nConnecting to Supabase...")
    conn = psycopg2.connect(DB_URI)
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    print("  Connected.")

    print(f"\nExtracting reviews (status='{REVIEW_STATUS}', "
          f"min_length={MIN_TEXT_LENGTH})...")
    cur.execute(EXTRACTION_QUERY, (REVIEW_STATUS, MIN_TEXT_LENGTH))
    rows = cur.fetchall()
    print(f"  Raw rows fetched: {len(rows)}")

    cur.close()
    conn.close()

    if not rows:
        print("\nERROR: No reviews found. Check DB connection and filters.")
        return
    
    print(f"\nBuilding enriched documents...")
    documents = []
    skipped   = 0

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
                "date_review":           row.get("datereview"),
                "review_title":          (row.get("review_title") or "").strip(),
                "review_text_original":  (row.get("review_text") or "").strip(),
            }
        }
        documents.append(doc)

    print(f"  Documents built  : {len(documents)}")
    print(f"  Skipped (too short): {skipped}")

    cities = {}
    ratings = []
    for doc in documents:
        city = doc["metadata"]["city"] or "Unknown"
        cities[city] = cities.get(city, 0) + 1
        r = doc["metadata"]["overall_rating"]
        if r: ratings.append(r)
 
    print(f"\nBreakdown by city:")
    for city, count in sorted(cities.items(), key=lambda x: -x[1]):
        print(f"  {city:<15} {count} reviews")
 
    if ratings:
        avg = sum(ratings) / len(ratings)
        print(f"\nOverall rating avg : {avg:.2f} / 5")
        print(f"Rating distribution:")
        for star in range(5, 0, -1):
            count = ratings.count(star)
            bar   = "█" * count
            print(f"  {star}★  {bar} ({count})")
 
    # Salvataggio JSON
    print(f"\nSaving to {OUTPUT}...")
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2,
                  default=json_serializer)
 
    size_kb = os.path.getsize(OUTPUT) / 1024
    print(f"  Saved {len(documents)} documents ({size_kb:.1f} KB)")
    print(f"\n✓  Extraction complete. Run indexer.py next.")
    print("=" * 55)

if __name__ == "__main__":
    extract()