"""Tests for Tool 4 — ``get_property_details``.

Exercises both lookup branches (room id, house id) with ``FakeDbExecutor``,
plus error paths (not found, malformed id, missing ctx) and the
include_reviews toggle.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from elh_rag.tools._shared.room_id import (
    InvalidRoomIdError,
    encode_house_id,
    encode_room_id,
)
from elh_rag.tools.get_property_details import (
    GetPropertyDetailsInput,
    GetPropertyDetailsOutput,
    get_property_details,
)

# Helpers


def _make_house_row(
    *,
    idhouse: str = "HSE_001",
    dateupdate: date = date(2024, 9, 15),
    flatname: str = "Casa do Sol",
    city: str = "Lisbon",
    zone: str = "Alfama",
) -> dict:
    return {
        "idhouse": idhouse,
        "dateupdate": dateupdate,
        "city": city,
        "zone": zone,
        "neighboorhood": zone,
        "flatname": flatname,
        "description": "A nice flat.",
        "bathroom": 2,
        "area": Decimal("85.50"),
        "distancepublictransport": Decimal("120"),
        "internetspeed": Decimal("100"),
        "latitude": 38.7,
        "longitude": -9.1,
        "otherameneties": "",
        "status": "Available",
        "allownightguests": "Y",
        "allowpets": "N",
        "smokingallowed": "N",
        "femalepreferred": "N",
        "malepreferred": "N",
        "genreirrelevant": "Y",
        # All Y/N amenity columns default to N
        "furnished": "Y",
        "sharedspace": "N",
        "balcony": "N",
        "cityview": "N",
        "fieldview": "N",
        "seaview": "N",
        "cctv": "N",
        "codeentry": "N",
        "security24h": "N",
        "smokedetector": "Y",
        "armoreddoor": "N",
        "elevator": "Y",
        "reducedmobilityaccess": "N",
        "parking": "N",
        "centralheating": "Y",
        "airconditioning": "N",
        "thermalinsulation": "N",
        "doubleglazedwindows": "N",
        "kitchenequipment": "Y",
        "fridge": "Y",
        "microwaveoven": "Y",
        "gaselectricstove": "Y",
        "dishwasher": "N",
        "washerdrier": "Y",
        "internet": "Y",
        "cabletv": "N",
        "smarttv": "N",
    }


def _make_room_row(
    *,
    loc_idhouse: str = "HSE_001",
    loc_dateupdate: date = date(2024, 9, 15),
    idroom: str = "RM_001",
    dateupdate: date = date(2024, 9, 15),
    roomname: str = "Blue Room",
) -> dict:
    return {
        "loc_idhouse": loc_idhouse,
        "loc_dateupdate": loc_dateupdate,
        "idroom": idroom,
        "dateupdate": dateupdate,
        "roomname": roomname,
        "description": "A cosy room.",
        "area": Decimal("12.00"),
        "fixedprice": "N",
        "springprice": Decimal("400.00"),
        "summerprice": Decimal("300.00"),
        "autumnprice": Decimal("550.00"),
        "extrapersonallowed": "N",
        "extrapersoncost": Decimal("0"),
        "deposit": "Y",
        "depositvalue": Decimal("550.00"),
        "lastmonthdeposit": "N",
        "administrativetax": Decimal("0"),
        "status": "Available",
        "singlebed": "Y",
        "doublebed": "N",
        "kingbed": "N",
        "queenbed": "N",
        "couchbed": "N",
        "secondbed": "N",
        "privatebathroom": "Y",
        "balcony": "N",
        "desk": "Y",
        "closet": "Y",
        "heating": "Y",
        "haswindow": "Y",
        "bedlinen": "Y",
        "pillows": "Y",
        "airconditioning": "N",
    }


def _encoded_room(
    house: str = "HSE_001",
    room: str = "RM_001",
    dt: datetime = datetime(2024, 9, 15),
) -> str:
    return encode_room_id(house, room, dt)


def _encoded_house(house: str = "HSE_001", dt: datetime = datetime(2024, 9, 15)) -> str:
    return encode_house_id(house, dt)


def _seed_room_lookup(
    fake_db,
    *,
    room_row: dict | None = None,
    house_row: dict | None = None,
    housemate_rows: list[dict] | None = None,
    reviews: list[dict] | None = None,
) -> None:
    """Seed the four queries the room-id branch issues.

    The order matters because ``FakeDbExecutor`` returns the FIRST
    registered pattern that matches the SQL substring. ``FROM room``
    matches both fetch_room_latest and fetch_housemate_rooms, so we
    must register them in invocation order: room first, then housemates.
    """
    rows_room = [room_row] if room_row is not None else []
    rows_housemates = housemate_rows if housemate_rows is not None else []
    rows_review = reviews if reviews is not None else []
    rows_house = [house_row] if house_row is not None else []
    # Order of add_response matters: first match wins.
    fake_db.add_response("WHERE loc_idhouse = %s AND idroom = %s", rows_room)
    fake_db.add_response("FROM house", rows_house)
    fake_db.add_response("WHERE loc_idhouse = %s AND loc_dateupdate = %s", rows_housemates)
    fake_db.add_response("FROM review", rows_review)


def _seed_house_lookup(
    fake_db,
    *,
    house_row: dict | None = None,
    housemate_rows: list[dict] | None = None,
    reviews: list[dict] | None = None,
) -> None:
    rows_house = [house_row] if house_row is not None else []
    rows_housemates = housemate_rows if housemate_rows is not None else []
    rows_review = reviews if reviews is not None else []
    fake_db.add_response("FROM house", rows_house)
    fake_db.add_response("WHERE loc_idhouse = %s AND loc_dateupdate = %s", rows_housemates)
    fake_db.add_response("FROM review", rows_review)


# Room id branch


class TestRoomIdBranch:
    def test_room_lookup_returns_house_and_room(self, fake_db):
        _seed_room_lookup(
            fake_db,
            room_row=_make_room_row(),
            house_row=_make_house_row(),
            housemate_rows=[_make_room_row(idroom="RM_001"), _make_room_row(idroom="RM_002")],
            reviews=[],
        )
        result = get_property_details(
            GetPropertyDetailsInput(encoded_id=_encoded_room()),
            ctx=fake_db,
        )
        assert isinstance(result, GetPropertyDetailsOutput)
        assert result.house is not None
        assert result.house.flat_name == "Casa do Sol"
        assert result.room is not None
        assert result.room.room_name == "Blue Room"
        assert result.house.rooms_total == 2

    def test_room_id_includes_reviews_when_requested(self, fake_db):
        _seed_room_lookup(
            fake_db,
            room_row=_make_room_row(),
            house_row=_make_house_row(),
            housemate_rows=[_make_room_row()],
            reviews=[
                {
                    "datereview": date(2025, 6, 1),
                    "title": "Great",
                    "description": "Loved it",
                    "overallratings": Decimal("5.00"),
                    "cleaningratings": Decimal("5.00"),
                    "communicationratings": Decimal("5.00"),
                    "locationratings": Decimal("4.00"),
                    "pricequalityratings": Decimal("4.50"),
                    "status": "approved",
                }
            ],
        )
        result = get_property_details(
            GetPropertyDetailsInput(encoded_id=_encoded_room(), include_reviews=True),
            ctx=fake_db,
        )
        assert result.reviews is not None
        assert result.reviews.count == 1
        assert result.reviews.average_overall_rating == 5.00

    def test_room_id_skips_reviews_when_disabled(self, fake_db):
        _seed_room_lookup(
            fake_db,
            room_row=_make_room_row(),
            house_row=_make_house_row(),
            housemate_rows=[_make_room_row()],
        )
        result = get_property_details(
            GetPropertyDetailsInput(encoded_id=_encoded_room(), include_reviews=False),
            ctx=fake_db,
        )
        assert result.reviews is None
        # Verify no review query was issued
        assert not any("FROM review" in c["sql"] for c in fake_db.calls)

    def test_room_lookup_uses_room_loc_dateupdate_for_house(self, fake_db):
        """House fetch must be pinned to the room's loc_dateupdate, not latest."""
        room_dt = date(2024, 9, 15)
        room = _make_room_row(loc_dateupdate=room_dt)
        _seed_room_lookup(
            fake_db,
            room_row=room,
            house_row=_make_house_row(dateupdate=room_dt),
            housemate_rows=[room],
            reviews=[],
        )
        get_property_details(
            GetPropertyDetailsInput(encoded_id=_encoded_room()),
            ctx=fake_db,
        )
        # Second call should be the house fetch; params must include room_dt
        house_call = fake_db.calls[1]
        assert "FROM house" in house_call["sql"]
        assert house_call["params"] == ("HSE_001", room_dt)

    def test_room_not_found_raises(self, fake_db):
        _seed_room_lookup(fake_db, room_row=None)
        with pytest.raises(ValueError, match="Room not found"):
            get_property_details(
                GetPropertyDetailsInput(encoded_id=_encoded_room()),
                ctx=fake_db,
            )

    def test_house_missing_for_room_raises_integrity_error(self, fake_db):
        """Room references house version that doesn't exist."""
        _seed_room_lookup(
            fake_db,
            room_row=_make_room_row(),
            house_row=None,  # not found
            housemate_rows=[],
        )
        with pytest.raises(ValueError, match="Data integrity issue"):
            get_property_details(
                GetPropertyDetailsInput(encoded_id=_encoded_room()),
                ctx=fake_db,
            )


# House id branch


class TestHouseIdBranch:
    def test_house_lookup_returns_house_only(self, fake_db):
        _seed_house_lookup(
            fake_db,
            house_row=_make_house_row(),
            housemate_rows=[
                _make_room_row(idroom="RM_001"),
                _make_room_row(idroom="RM_002"),
                _make_room_row(idroom="RM_003"),
            ],
            reviews=[],
        )
        result = get_property_details(
            GetPropertyDetailsInput(encoded_id=_encoded_house()),
            ctx=fake_db,
        )
        assert result.house.flat_name == "Casa do Sol"
        assert result.house.rooms_total == 3
        assert result.room is None

    def test_house_lookup_pins_exact_dateupdate(self, fake_db):
        # decode_house_id returns datetime — that's what gets passed downstream.
        target_dt = datetime(2024, 9, 15)
        _seed_house_lookup(
            fake_db,
            house_row=_make_house_row(dateupdate=date(2024, 9, 15)),
            housemate_rows=[],
            reviews=[],
        )
        get_property_details(
            GetPropertyDetailsInput(encoded_id=_encoded_house(dt=target_dt)),
            ctx=fake_db,
        )
        # First call is the house fetch; params second elem is datetime
        assert fake_db.calls[0]["params"] == ("HSE_001", target_dt)

    def test_house_lookup_reviews_scoped_without_room(self, fake_db):
        _seed_house_lookup(
            fake_db,
            house_row=_make_house_row(),
            housemate_rows=[_make_room_row()],
            reviews=[],
        )
        get_property_details(
            GetPropertyDetailsInput(encoded_id=_encoded_house()),
            ctx=fake_db,
        )
        review_call = next(c for c in fake_db.calls if "FROM review" in c["sql"])
        # House-scope: 3 params (house_id, dateupdate, status), no idroom
        assert len(review_call["params"]) == 3
        assert "idroom = %s" not in review_call["sql"]

    def test_house_not_found_raises(self, fake_db):
        _seed_house_lookup(fake_db, house_row=None)
        with pytest.raises(ValueError, match="House not found"):
            get_property_details(
                GetPropertyDetailsInput(encoded_id=_encoded_house()),
                ctx=fake_db,
            )


# Error handling


class TestErrorHandling:
    def test_no_ctx_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="DBExecutor"):
            get_property_details(
                GetPropertyDetailsInput(encoded_id=_encoded_room()),
                ctx=None,
            )

    def test_malformed_id_garbage_raises(self, fake_db):
        with pytest.raises(InvalidRoomIdError):
            get_property_details(
                GetPropertyDetailsInput(encoded_id="not-an-id"),
                ctx=fake_db,
            )

    def test_malformed_id_empty_raises(self, fake_db):
        with pytest.raises(InvalidRoomIdError):
            get_property_details(
                GetPropertyDetailsInput(encoded_id=""),
                ctx=fake_db,
            )

    def test_id_whitespace_stripped_before_parsing(self, fake_db):
        """A padded id (e.g. from a textbox) should resolve cleanly."""
        _seed_room_lookup(
            fake_db,
            room_row=_make_room_row(),
            house_row=_make_house_row(),
            housemate_rows=[_make_room_row()],
            reviews=[],
        )
        padded = f"  {_encoded_room()}  "
        result = get_property_details(
            GetPropertyDetailsInput(encoded_id=padded),
            ctx=fake_db,
        )
        assert result.house.flat_name == "Casa do Sol"


# Summary


class TestSummaryComposition:
    def test_room_summary_mentions_room_and_house(self, fake_db):
        _seed_room_lookup(
            fake_db,
            room_row=_make_room_row(roomname="Blue Room"),
            house_row=_make_house_row(flatname="Casa do Sol", zone="Alfama"),
            housemate_rows=[_make_room_row()],
            reviews=[],
        )
        result = get_property_details(
            GetPropertyDetailsInput(encoded_id=_encoded_room()),
            ctx=fake_db,
        )
        assert "Blue Room" in result.summary
        assert "Casa do Sol" in result.summary
        assert "Alfama" in result.summary

    def test_house_summary_mentions_rooms_total(self, fake_db):
        _seed_house_lookup(
            fake_db,
            house_row=_make_house_row(flatname="Casa do Sol"),
            housemate_rows=[_make_room_row(idroom=f"RM_{i:03d}") for i in range(4)],
            reviews=[],
        )
        result = get_property_details(
            GetPropertyDetailsInput(encoded_id=_encoded_house()),
            ctx=fake_db,
        )
        assert "Casa do Sol" in result.summary
        assert "4 rooms" in result.summary

    def test_summary_includes_reviews_when_count_positive(self, fake_db):
        _seed_room_lookup(
            fake_db,
            room_row=_make_room_row(),
            house_row=_make_house_row(),
            housemate_rows=[_make_room_row()],
            reviews=[
                {
                    "datereview": date(2025, 6, 1),
                    "title": "OK",
                    "description": "fine",
                    "overallratings": Decimal("4.00"),
                    "cleaningratings": Decimal("4.00"),
                    "communicationratings": Decimal("4.00"),
                    "locationratings": Decimal("4.00"),
                    "pricequalityratings": Decimal("4.00"),
                    "status": "approved",
                }
            ],
        )
        result = get_property_details(
            GetPropertyDetailsInput(encoded_id=_encoded_room()),
            ctx=fake_db,
        )
        assert "1 review" in result.summary
        assert "4.0" in result.summary  # average

    def test_summary_omits_reviews_when_disabled(self, fake_db):
        _seed_room_lookup(
            fake_db,
            room_row=_make_room_row(),
            house_row=_make_house_row(),
            housemate_rows=[_make_room_row()],
        )
        result = get_property_details(
            GetPropertyDetailsInput(encoded_id=_encoded_room(), include_reviews=False),
            ctx=fake_db,
        )
        assert "review" not in result.summary.lower()
