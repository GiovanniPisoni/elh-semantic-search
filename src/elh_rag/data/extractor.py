"""
Document extraction from the ELH operational database.

Reads approved reviews from Supabase via a JOIN across review/room/house,
enriches each review with location and property context, and returns a
list of typed Document objects ready for indexing.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import psycopg2
import psycopg2.extras

from elh_rag.config import settings
from elh_rag.schemas import Document, DocumentSource, ReviewMetadata

logger = logging.getLogger(__name__)


REVIEW_STATUS = "approved"


_EXTRACTION_QUERY = """
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


def _build_enriched_text(row: dict[str, Any]) -> str:
    """Compose a single text blob enriching the review with location + property."""
    parts: list[str] = []

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


def _row_to_document(row: dict[str, Any]) -> Document:
    """Convert a raw DB row into a typed Document."""
    enriched_text = _build_enriched_text(row)

    date_review = row.get("datereview")
    date_str = (
        date_review.isoformat()
        if isinstance(date_review, date)
        else str(date_review or "")
    )

    metadata = ReviewMetadata(
        id=str(row["idreview"]),
        source=DocumentSource.REVIEW,
        city=(row.get("city") or "").strip(),
        zone=(row.get("zone") or "").strip(),
        neighbourhood=(row.get("neighboorhood") or "").strip(),
        flatname=(row.get("flatname") or "").strip(),
        roomname=(row.get("roomname") or "").strip(),
        idhouse=str(row.get("idhouse") or ""),
        idroom=str(row.get("idroom") or ""),
        overall_rating=int(row.get("overallratings") or 0),
        cleaning_rating=int(row.get("cleaningratings") or 0),
        communication_rating=int(row.get("communicationratings") or 0),
        location_rating=int(row.get("locationratings") or 0),
        pricequality_rating=int(row.get("pricequalityratings") or 0),
        date_review=date_str,
        review_title=(row.get("review_title") or "").strip(),
        review_text_original=(row.get("review_text") or "").strip(),
    )

    return Document(text=enriched_text, metadata=metadata)


def fetch_documents() -> list[Document]:
    """Extract all approved reviews from Supabase as typed Documents."""
    logger.info("Connecting to Supabase to fetch reviews")

    with psycopg2.connect(settings.db_uri) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_EXTRACTION_QUERY, (REVIEW_STATUS, settings.min_text_length))
            rows = cur.fetchall()

    logger.info("Fetched %d rows from database", len(rows))

    documents: list[Document] = []
    skipped = 0
    for raw in rows:
        row = dict(raw)
        doc = _row_to_document(row)
        if len(doc.text) < settings.min_text_length:
            skipped += 1
            continue
        documents.append(doc)

    logger.info(
        "Built %d documents (%d skipped for being too short)",
        len(documents),
        skipped,
    )
    return documents


def summarise_corpus(documents: list[Document]) -> dict[str, int]:
    """Return a per-city count of documents — useful for diagnostics."""
    counts: dict[str, int] = {}
    for doc in documents:
        city = doc.metadata.city or "Unknown"
        counts[city] = counts.get(city, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))
