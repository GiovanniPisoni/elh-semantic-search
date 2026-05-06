"""
Description extrctor - reads curated house and room descriptions from Supabase.

this extractor produces TWO kinds of documents
from a single data source pass:
    - one `Document` per house (with `HouseMetadata`)
    - one `Document` per room (with `RoomMetadata`)

The two query results are merged in a single iterable, so the indexer can
stream all descriptions with one call.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

import psycopg2
import psycopg2.extras

from elh_rag.config import settings
from elh_rag.schemas import (
    Document,
    DocumentSource,
    HouseMetadata,
    RoomMetadata,
)

logger = logging.getLogger(__name__)

# SQL

_HOUSE_QUERY = """
    SELECT DISTINCT ON (h.idhouse)
        h.idhouse,
        h.flatname,
        h.city,
        h.zone,
        h.neighboorhood,
        h.description,
        h.dateupdate
    FROM house h
    WHERE h.status = %s
      AND LENGTH(TRIM(h.description)) >= %s
    ORDER BY h.idhouse, h.dateupdate DESC
"""

_ROOM_QUERY = """
    SELECT DISTINCT ON (r.loc_idhouse, r.idroom)
        r.idroom,
        r.roomname,
        r.loc_idhouse       AS idhouse,
        h.flatname,
        h.city,
        h.zone,
        h.neighboorhood,
        r.description,
        r.dateupdate
    FROM room r
    JOIN house h
        ON  r.loc_idhouse    = h.idhouse
        AND r.loc_dateupdate = h.dateupdate
    WHERE r.status = %s
      AND LENGTH(TRIM(r.description)) >= %s
    ORDER BY r.loc_idhouse, r.idroom, r.dateupdate DESC
"""

# Extractor class


class DescriptionExtractor:
    """Concrete Extractor for the house+room description corpus."""

    def __init__(
        self,
        db_uri: str | None = None,
        house_status_filter: str = "Validated",
        room_status_filter: str = "Available",
        min_text_length: int | None = None,
    ) -> None:
        self._db_uri = db_uri or settings.db_uri
        self._house_status = house_status_filter
        self._room_status = room_status_filter
        self._min_text_length = (
            min_text_length if min_text_length is not None else settings.min_text_length
        )

    @property
    def source(self) -> DocumentSource:
        return DocumentSource.HOUSE

    def extract(self) -> Iterable[Document]:
        """Fetch all descriptions from Supabase as typed Documents."""
        logger.info("Connecting to Supabase to fetch descriptions")

        with psycopg2.connect(self._db_uri) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(_HOUSE_QUERY, (self._house_status, self._min_text_length))
                house_rows = [dict(r) for r in cur.fetchall()]

            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(_ROOM_QUERY, (self._room_status, self._min_text_length))
                room_rows = [dict(r) for r in cur.fetchall()]

        logger.info(
            "Fetched %d house descriptions and %d room descriptions",
            len(house_rows),
            len(room_rows),
        )

        documents: list[Document] = []
        skipped = 0

        for row in house_rows:
            doc = _house_row_to_document(row)
            if len(doc.text) < self._min_text_length:
                skipped += 1
                continue
            documents.append(doc)

        for row in room_rows:
            doc = _room_row_to_document(row)
            if len(doc.text) < self._min_text_length:
                skipped += 1
                continue
            documents.append(doc)

        logger.info(
            "Built %d description documents (%d skipped for being too short)",
            len(documents),
            skipped,
        )
        return documents


# Row → Document transformation


def _house_row_to_document(row: dict[str, Any]) -> Document:
    """Build a Document for a single house row."""
    idhouse = _clean_str(row.get("idhouse"))
    flatname = _clean_str(row.get("flatname"))
    city = _clean_str(row.get("city"))
    zone = _clean_str(row.get("zone"))
    neighbourhood = _clean_str(row.get("neighboorhood"))
    description = _clean_str(row.get("description"))

    text = _build_house_text(
        flatname=flatname,
        city=city,
        zone=zone,
        neighbourhood=neighbourhood,
        description=description,
    )

    metadata = HouseMetadata(
        id=f"house:{idhouse}",
        idhouse=idhouse,
        flatname=flatname,
        city=city,
        zone=zone,
        neighbourhood=neighbourhood,
    )

    return Document(text=text, metadata=metadata)


def _room_row_to_document(row: dict[str, Any]) -> Document:
    """Build a Document for a single room row."""
    idroom = _clean_str(row.get("idroom"))
    roomname = _clean_str(row.get("roomname"))
    idhouse = _clean_str(row.get("idhouse"))
    flatname = _clean_str(row.get("flatname"))
    city = _clean_str(row.get("city"))
    zone = _clean_str(row.get("zone"))
    neighbourhood = _clean_str(row.get("neighboorhood"))
    description = _clean_str(row.get("description"))

    text = _build_room_text(
        roomname=roomname,
        flatname=flatname,
        city=city,
        zone=zone,
        neighbourhood=neighbourhood,
        description=description,
    )

    metadata = RoomMetadata(
        id=f"room:{idroom}",
        idroom=idroom,
        roomname=roomname,
        idhouse=idhouse,
        flatname=flatname,
        city=city,
        zone=zone,
        neighbourhood=neighbourhood,
    )

    return Document(text=text, metadata=metadata)


# Text builders


def _build_house_text(
    flatname: str,
    city: str,
    zone: str,
    neighbourhood: str,
    description: str,
) -> str:
    """Compose the text blob for a house document.

    Format:
        [HOUSE — {flatname}]
        Location: {city}, {zone}, {neighbourhood}

        {description}
    """
    header = f"[HOUSE — {flatname}]" if flatname else "[HOUSE]"
    location = _format_location(city, zone, neighbourhood)

    parts: list[str] = [header]
    if location:
        parts.append(f"Location: {location}")
    if description:
        parts.append("")
        parts.append(description)

    return "\n".join(parts)


def _build_room_text(
    roomname: str,
    flatname: str,
    city: str,
    zone: str,
    neighbourhood: str,
    description: str,
) -> str:
    """Compose the text blob for a room document.

    Format:
        [ROOM — {roomname} in {flatname}]
        Location: {city}, {zone}, {neighbourhood}

        {description}
    """
    if roomname and flatname:
        header = f"[ROOM — {roomname} in {flatname}]"
    elif roomname:
        header = f"[ROOM — {roomname}]"
    else:
        header = "[ROOM]"

    location = _format_location(city, zone, neighbourhood)

    parts: list[str] = [header]
    if location:
        parts.append(f"Location: {location}")
    if description:
        parts.append("")
        parts.append(description)

    return "\n".join(parts)


def _format_location(city: str, zone: str, neighbourhood: str) -> str:
    """Build a location string like 'Lisbon, Alfama, Jardim Botto Machado'."""
    return ", ".join(filter(None, [city, zone, neighbourhood]))


def _clean_str(value: Any) -> str:
    """Normalise a raw DB value to a trimmed string ('' if None)."""
    if value is None:
        return ""
    return str(value).strip()
