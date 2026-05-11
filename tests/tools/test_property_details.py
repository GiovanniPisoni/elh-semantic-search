"""Tests for ``elh_rag.tools._property_details``."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from elh_rag.tools._property_details import (
    _MAX_HOUSEMATE_ROOMS,
    HouseDetails,
    HousemateRoom,
    RoomDetails,
    build_house_details,
    build_room_details,
    fetch_house_at_version,
    fetch_housemate_rooms,
    fetch_room_latest,
)

# Helpers


def _make_house_row(
    *,
    idhouse: str = "HSE_001",
    dateupdate: date = date(2024, 9, 15),
    city: str = "Lisbon",
    zone: str = "Alfama",
    neighborhood: str = "Alfama",
    flatname: str = "Casa do Sol",
    description: str = "A nice flat near the river.",
    bathroom: int = 2,
    area: str = "85.50",
    distance: str = "120",
    internet_speed: str | None = "100.00",
    latitude: float = 38.7,
    longitude: float = -9.1,
    other_amenities: str = "Iron, hairdryer",
    status: str = "Available",
    # rules
    nightguests: str = "Y",
    pets: str = "N",
    smoking: str = "N",
    female: str = "N",
    male: str = "N",
    **amenities: str,
) -> dict:
    """Build a fake house row. Pass ``columnname='Y'`` to set amenities."""
    default_amenities = {
        "furnished": "Y",
        "sharedspace": "Y",
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
        "doubleglazedwindows": "Y",
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
    default_amenities.update(amenities)
    return {
        "idhouse": idhouse,
        "dateupdate": dateupdate,
        "city": city,
        "zone": zone,
        "neighboorhood": neighborhood,  # sic, column name in schema
        "flatname": flatname,
        "description": description,
        "bathroom": bathroom,
        "area": Decimal(area),
        "distancepublictransport": Decimal(distance),
        "internetspeed": Decimal(internet_speed) if internet_speed else None,
        "latitude": latitude,
        "longitude": longitude,
        "otherameneties": other_amenities,  # sic, column name in schema
        "status": status,
        "allownightguests": nightguests,
        "allowpets": pets,
        "smokingallowed": smoking,
        "femalepreferred": female,
        "malepreferred": male,
        "genreirrelevant": "Y" if female == "N" and male == "N" else "N",
        **default_amenities,
    }


def _make_room_row(
    *,
    loc_idhouse: str = "HSE_001",
    loc_dateupdate: date = date(2024, 9, 15),
    idroom: str = "RM_001",
    dateupdate: date = date(2024, 9, 15),
    roomname: str = "Blue Room",
    description: str = "A cosy room with a view.",
    area: str = "12.00",
    fixed: str = "N",
    spring: str = "400.00",
    summer: str = "300.00",
    autumn: str = "550.00",
    extra_allowed: str = "N",
    extra_cost: str = "0",
    deposit: str = "Y",
    deposit_value: str = "550.00",
    lastmonth: str = "N",
    admin_tax: str = "0",
    status: str = "Available",
    **flags: str,
) -> dict:
    """Build a fake room row. Pass ``columnname='Y'`` to set amenities/beds."""
    default_flags = {
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
    default_flags.update(flags)
    return {
        "loc_idhouse": loc_idhouse,
        "loc_dateupdate": loc_dateupdate,
        "idroom": idroom,
        "dateupdate": dateupdate,
        "roomname": roomname,
        "description": description,
        "area": Decimal(area),
        "fixedprice": fixed,
        "springprice": Decimal(spring),
        "summerprice": Decimal(summer),
        "autumnprice": Decimal(autumn),
        "extrapersonallowed": extra_allowed,
        "extrapersoncost": Decimal(extra_cost),
        "deposit": deposit,
        "depositvalue": Decimal(deposit_value),
        "lastmonthdeposit": lastmonth,
        "administrativetax": Decimal(admin_tax),
        "status": status,
        **default_flags,
    }


# Fetchers


class TestFetchRoomLatest:
    def test_returns_first_row_when_present(self, fake_db):
        row = _make_room_row()
        fake_db.add_response("FROM room", [row])
        result = fetch_room_latest(fake_db, "HSE_001", "RM_001")
        assert result is row

    def test_returns_none_when_empty(self, fake_db):
        fake_db.add_response("FROM room", [])
        result = fetch_room_latest(fake_db, "HSE_001", "RM_001")
        assert result is None

    def test_sql_uses_distinct_on_for_latest_version(self, fake_db):
        fake_db.add_response("FROM room", [])
        fetch_room_latest(fake_db, "HSE_001", "RM_001")
        sql = fake_db.calls[0]["sql"]
        assert "DISTINCT ON" in sql
        assert "dateupdate DESC" in sql


class TestFetchHouseAtVersion:
    def test_returns_row_when_present(self, fake_db):
        row = _make_house_row()
        fake_db.add_response("FROM house", [row])
        result = fetch_house_at_version(fake_db, "HSE_001", date(2024, 9, 15))
        assert result is row

    def test_returns_none_when_empty(self, fake_db):
        fake_db.add_response("FROM house", [])
        result = fetch_house_at_version(fake_db, "HSE_001", date(2024, 9, 15))
        assert result is None

    def test_sql_pins_exact_dateupdate(self, fake_db):
        fake_db.add_response("FROM house", [])
        fetch_house_at_version(fake_db, "HSE_001", date(2024, 9, 15))
        sql = fake_db.calls[0]["sql"]
        assert "idhouse = %s" in sql
        assert "dateupdate = %s" in sql


class TestFetchHousemateRooms:
    def test_joins_on_loc_idhouse_and_loc_dateupdate(self, fake_db):
        fake_db.add_response("FROM room", [_make_room_row()])
        result = fetch_housemate_rooms(fake_db, "HSE_001", date(2024, 9, 15))
        assert len(result) == 1
        sql = fake_db.calls[0]["sql"]
        assert "loc_idhouse = %s" in sql
        assert "loc_dateupdate = %s" in sql


# build_house_details


class TestBuildHouseDetails:
    def test_basic_assembly(self):
        row = _make_house_row()
        details = build_house_details(row, [])
        assert isinstance(details, HouseDetails)
        assert details.flat_name == "Casa do Sol"
        assert details.city == "Lisbon"
        assert details.zone == "Alfama"
        assert details.bathroom_count == 2
        assert details.area_sqm == 85.50
        assert details.distance_to_transport_m == 120
        assert details.internet_speed_mbps == 100.00
        assert details.rooms_total == 0
        assert details.rooms_summary == []

    def test_amenities_only_y_columns_alphabetised(self):
        row = _make_house_row(
            balcony="Y",
            seaview="Y",
            parking="Y",
            internet="N",  # excluded despite being a default Y
        )
        details = build_house_details(row, [])
        assert "Balcony" in details.amenities
        assert "Sea view" in details.amenities
        assert "Parking" in details.amenities
        assert "Internet" not in details.amenities
        # Verify sorted
        assert details.amenities == sorted(details.amenities)

    def test_house_rules_three_booleans(self):
        row = _make_house_row(nightguests="Y", pets="N", smoking="Y")
        details = build_house_details(row, [])
        assert details.night_guests_allowed is True
        assert details.pets_allowed is False
        assert details.smoking_allowed is True

    def test_gender_preference_female_only(self):
        row = _make_house_row(female="Y", male="N")
        details = build_house_details(row, [])
        assert details.gender_preference == "female_only"

    def test_gender_preference_male_only(self):
        row = _make_house_row(female="N", male="Y")
        details = build_house_details(row, [])
        assert details.gender_preference == "male_only"

    def test_gender_preference_any_when_both_zero(self):
        row = _make_house_row(female="N", male="N")
        details = build_house_details(row, [])
        assert details.gender_preference == "any"

    def test_gender_preference_any_when_both_set(self):
        """If both flags are Y (data oddity), default to 'any'."""
        row = _make_house_row(female="Y", male="Y")
        details = build_house_details(row, [])
        assert details.gender_preference == "any"

    def test_encoded_house_id_round_trippable(self):
        row = _make_house_row(idhouse="HSE_00F7359B", dateupdate=date(2024, 9, 15))
        details = build_house_details(row, [])
        # Encoded id has 2 segments separated by '|'
        assert details.encoded_house_id.count("|") == 1
        assert details.encoded_house_id.startswith("HSE_00F7359B|")

    def test_rooms_total_set_from_housemate_count(self):
        rooms = [_make_room_row(idroom=f"RM_{i:03d}") for i in range(5)]
        details = build_house_details(_make_house_row(), rooms)
        assert details.rooms_total == 5
        assert len(details.rooms_summary) == 5

    def test_rooms_summary_capped_at_max(self, caplog):
        rooms = [_make_room_row(idroom=f"RM_{i:03d}") for i in range(_MAX_HOUSEMATE_ROOMS + 5)]
        with caplog.at_level("WARNING"):
            details = build_house_details(_make_house_row(), rooms)
        # rooms_total reflects the real count, rooms_summary is capped
        assert details.rooms_total == _MAX_HOUSEMATE_ROOMS + 5
        assert len(details.rooms_summary) == _MAX_HOUSEMATE_ROOMS
        assert any("capping" in r.message for r in caplog.records)

    def test_padded_strings_stripped(self):
        """character() columns return right-padded values; assembly strips."""
        row = _make_house_row(
            city="Lisbon" + " " * 14,
            zone="Alfama" + " " * 14,
            flatname="Casa do Sol" + " " * 89,
        )
        details = build_house_details(row, [])
        assert details.city == "Lisbon"
        assert details.zone == "Alfama"
        assert details.flat_name == "Casa do Sol"


# build_room_details


class TestBuildRoomDetails:
    def test_basic_assembly(self):
        row = _make_room_row()
        details = build_room_details(row)
        assert isinstance(details, RoomDetails)
        assert details.room_name == "Blue Room"
        assert details.area_sqm == 12.00
        assert details.spring_price_eur == Decimal("400.00")
        assert details.summer_price_eur == Decimal("300.00")
        assert details.autumn_price_eur == Decimal("550.00")
        assert details.is_fixed_price is False

    def test_amenities_only_y_columns_alphabetised(self):
        row = _make_room_row(privatebathroom="Y", desk="Y", balcony="N")
        details = build_room_details(row)
        assert "Private bathroom" in details.amenities
        assert "Desk" in details.amenities
        assert "Balcony" not in details.amenities
        assert details.amenities == sorted(details.amenities)

    def test_bed_types_only_y_columns(self):
        row = _make_room_row(singlebed="Y", doublebed="Y", kingbed="N")
        details = build_room_details(row)
        assert "Single bed" in details.bed_types
        assert "Double bed" in details.bed_types
        assert "King bed" not in details.bed_types

    def test_extra_person_cost_none_when_not_allowed(self):
        row = _make_room_row(extra_allowed="N", extra_cost="200.00")
        details = build_room_details(row)
        assert details.extra_person_allowed is False
        assert details.extra_person_cost_eur is None

    def test_extra_person_cost_decimal_when_allowed(self):
        row = _make_room_row(extra_allowed="Y", extra_cost="200.00")
        details = build_room_details(row)
        assert details.extra_person_allowed is True
        assert details.extra_person_cost_eur == Decimal("200.00")

    def test_deposit_fields(self):
        row = _make_room_row(deposit="Y", deposit_value="550.00", lastmonth="Y")
        details = build_room_details(row)
        assert details.deposit_required is True
        assert details.deposit_value_eur == Decimal("550.00")
        assert details.last_month_deposit is True

    def test_administrative_tax(self):
        row = _make_room_row(admin_tax="150.00")
        details = build_room_details(row)
        assert details.administrative_tax_eur == Decimal("150.00")

    def test_fixed_price_room(self):
        row = _make_room_row(fixed="Y", spring="600.00", summer="600.00", autumn="600.00")
        details = build_room_details(row)
        assert details.is_fixed_price is True

    def test_encoded_room_id_round_trippable(self):
        row = _make_room_row(
            loc_idhouse="HSE_001",
            idroom="RM_001",
            dateupdate=date(2024, 9, 15),
        )
        details = build_room_details(row)
        assert details.encoded_room_id.count("|") == 2  # 3 segments

    def test_padded_strings_stripped(self):
        row = _make_room_row(
            roomname="Blue Room" + " " * 41,
            description="A cosy room." + " " * 50,
        )
        details = build_room_details(row)
        assert details.room_name == "Blue Room"
        assert not details.full_description.endswith(" ")


# HousemateRoom


class TestHousemateRoomEmbedding:
    def test_housemate_built_with_full_pricing_set(self):
        room = _make_room_row(spring="400.00", summer="300.00", autumn="550.00", fixed="N")
        house = build_house_details(_make_house_row(), [room])
        assert len(house.rooms_summary) == 1
        h = house.rooms_summary[0]
        assert isinstance(h, HousemateRoom)
        assert h.spring_price_eur == Decimal("400.00")
        assert h.summer_price_eur == Decimal("300.00")
        assert h.autumn_price_eur == Decimal("550.00")
        assert h.is_fixed_price is False
        assert h.private_bathroom is True  # default in _make_room_row

    def test_datetime_coercion_from_date(self):
        """Encoders need datetime; psycopg2 returns date — adapter handles it."""
        room = _make_room_row(dateupdate=date(2024, 9, 15))
        house = build_house_details(_make_house_row(), [room])
        # Should not have raised, and the encoded id should contain ISO datetime
        h = house.rooms_summary[0]
        assert "2024-09-15T00:00:00" in h.encoded_room_id

    def test_datetime_passes_through_unchanged(self):
        """A datetime input should not be re-wrapped."""
        room = _make_room_row(dateupdate=datetime(2024, 9, 15, 10, 30, 0))
        house = build_house_details(_make_house_row(), [room])
        h = house.rooms_summary[0]
        assert "2024-09-15T10:30:00" in h.encoded_room_id
