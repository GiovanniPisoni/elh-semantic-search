"""Output dataclasses for ``find_rooms`` (also used by Tool 2 and Tool 4).

Frozen dataclasses with explicit ``to_dict()`` for LLM consumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class RoomMatch:
    """Single room result. Reused by Tool 1, Tool 2, Tool 4."""

    room_id: str
    house_id: str
    house_name: str
    city: str
    zone: str
    neighborhood: str
    price_per_month_eur: float
    private_bathroom: bool
    distance_to_transport_m: int | None
    nearest_metro_line: str | None
    available_from: date | None
    min_reserve_months: int
    amenities: list[str] = field(default_factory=list)
    excerpt: str = ""
    match_score: float = 0.0
    is_fixed_price: bool = False
    price_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id,
            "house_id": self.house_id,
            "house_name": self.house_name,
            "city": self.city,
            "zone": self.zone,
            "neighborhood": self.neighborhood,
            "price_per_month_eur": self.price_per_month_eur,
            "price_label": self.price_label,
            "private_bathroom": self.private_bathroom,
            "distance_to_transport_m": self.distance_to_transport_m,
            "nearest_metro_line": self.nearest_metro_line,
            "available_from": self.available_from.isoformat() if self.available_from else None,
            "min_reserve_months": self.min_reserve_months,
            "amenities": list(self.amenities),
            "excerpt": self.excerpt,
            "match_score": self.match_score,
            "is_fixed_price": self.is_fixed_price,
        }


@dataclass(frozen=True)
class FindRoomsOutput:
    """Result of a find_rooms call."""

    rooms: list[RoomMatch]
    total_matches: int
    query_summary: str  # natural-language summary of filters

    def to_dict(self) -> dict[str, Any]:
        return {
            "rooms": [r.to_dict() for r in self.rooms],
            "total_matches": self.total_matches,
            "query_summary": self.query_summary,
        }
