"""Tests for ``elh_rag.tools._booking_stats``."""

from __future__ import annotations

from datetime import date

from elh_rag.tools._booking_stats import (
    StatPoint,
    _compute_avg_booking_duration_months,
    _compute_avg_lead_time_days,
    _compute_avg_overall_rating,
    _compute_occupancy_rate,
    _compute_room_inventory_count,
    _compute_seasonal_demand,
    _compute_top_zones_by_bookings,
)

# Occupancy rate


class TestComputeOccupancyRate:
    def test_no_grouping_single_bucket(self, fake_db):
        """No group_by → one bucket aggregating everything."""
        # First call = numerator, second = denominator
        fake_db.add_response(
            "FROM reservation r",
            [{"booked_rooms": 8, "booking_count": 12}],
        )
        fake_db.add_response(
            "FROM latest_room lr",
            [{"active_rooms": 20}],
        )
        result = _compute_occupancy_rate(
            fake_db,
            city=None,
            zone=None,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            group_by=[],
        )
        assert len(result) == 1
        p = result[0]
        assert p.label == {}
        assert p.value == 0.4  # 8 / 20
        assert p.sample_size == 12

    def test_group_by_city_combines_numerator_and_denominator(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [
                {"city": "Lisbon", "booked_rooms": 10, "booking_count": 15},
                {"city": "Porto", "booked_rooms": 4, "booking_count": 5},
            ],
        )
        fake_db.add_response(
            "FROM latest_room lr",
            [
                {"city": "Lisbon", "active_rooms": 50},
                {"city": "Porto", "active_rooms": 20},
            ],
        )
        result = _compute_occupancy_rate(
            fake_db,
            city=None,
            zone=None,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            group_by=["city"],
        )
        by_city = {p.label["city"]: p for p in result}
        assert by_city["Lisbon"].value == 0.2  # 10/50
        assert by_city["Porto"].value == 0.2  # 4/20

    def test_bucket_with_no_inventory_skipped(self, fake_db):
        """If a city has bookings but no rooms in denominator, skip it."""
        fake_db.add_response(
            "FROM reservation r",
            [
                {"city": "Lisbon", "booked_rooms": 5, "booking_count": 6},
                {"city": "Porto", "booked_rooms": 3, "booking_count": 4},
            ],
        )
        fake_db.add_response(
            "FROM latest_room lr",
            [{"city": "Lisbon", "active_rooms": 10}],
            # Porto missing → division-by-zero would happen
        )
        result = _compute_occupancy_rate(
            fake_db,
            city=None,
            zone=None,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            group_by=["city"],
        )
        assert len(result) == 1
        assert result[0].label["city"] == "Lisbon"

    def test_city_filter_in_both_queries(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [{"booked_rooms": 1, "booking_count": 1}],
        )
        fake_db.add_response(
            "FROM latest_room lr",
            [{"active_rooms": 5}],
        )
        _compute_occupancy_rate(
            fake_db,
            city="Lisbon",
            zone=None,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            group_by=[],
        )
        # 2 calls — both must include the city param
        assert len(fake_db.calls) == 2
        assert "Lisbon" in fake_db.calls[0]["params"]
        assert "Lisbon" in fake_db.calls[1]["params"]


# Top zones by bookings


class TestComputeTopZonesByBookings:
    def test_returns_sorted_by_value_desc(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [
                {"zone": "Alfama", "value": 42, "sample_size": 42},
                {"zone": "Chiado", "value": 30, "sample_size": 30},
                {"zone": "Bairro Alto", "value": 18, "sample_size": 18},
            ],
        )
        result = _compute_top_zones_by_bookings(
            fake_db, city=None, period_start=None, period_end=None, top_n=10
        )
        # The DB ordering is responsibility of the SQL; helper preserves it.
        assert [p.label["zone"] for p in result] == [
            "Alfama",
            "Chiado",
            "Bairro Alto",
        ]
        assert all(isinstance(p, StatPoint) for p in result)

    def test_top_n_passed_to_sql_as_limit(self, fake_db):
        fake_db.add_response("FROM reservation r", [])
        _compute_top_zones_by_bookings(
            fake_db, city=None, period_start=None, period_end=None, top_n=5
        )
        params = fake_db.calls[0]["params"]
        # LIMIT is the last param
        assert params[-1] == 5

    def test_city_filter_added_to_where(self, fake_db):
        fake_db.add_response("FROM reservation r", [])
        _compute_top_zones_by_bookings(
            fake_db, city="Porto", period_start=None, period_end=None, top_n=10
        )
        sql = fake_db.calls[0]["sql"]
        params = fake_db.calls[0]["params"]
        assert "h.city = %s" in sql
        assert "Porto" in params

    def test_period_filters_added_when_provided(self, fake_db):
        fake_db.add_response("FROM reservation r", [])
        _compute_top_zones_by_bookings(
            fake_db,
            city=None,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            top_n=10,
        )
        sql = fake_db.calls[0]["sql"]
        params = fake_db.calls[0]["params"]
        assert "r.blockeddatestart >= %s" in sql
        assert "r.blockeddatestart <= %s" in sql
        assert date(2024, 1, 1) in params
        assert date(2024, 12, 31) in params

    def test_padded_zone_stripped(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [{"zone": "Alfama" + " " * 14, "value": 10, "sample_size": 10}],
        )
        result = _compute_top_zones_by_bookings(
            fake_db, city=None, period_start=None, period_end=None, top_n=10
        )
        assert result[0].label["zone"] == "Alfama"


# Avg booking duration


class TestComputeAvgBookingDurationMonths:
    def test_no_grouping(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [{"value": 3.5, "sample_size": 20}],
        )
        result = _compute_avg_booking_duration_months(
            fake_db,
            city=None,
            zone=None,
            period_start=None,
            period_end=None,
            group_by=[],
        )
        assert len(result) == 1
        assert result[0].value == 3.5
        assert result[0].sample_size == 20
        assert result[0].label == {}

    def test_group_by_season(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [
                {"season": "autumn", "value": 5.0, "sample_size": 30},
                {"season": "spring", "value": 3.5, "sample_size": 12},
                {"season": "summer", "value": 1.5, "sample_size": 8},
            ],
        )
        result = _compute_avg_booking_duration_months(
            fake_db,
            city=None,
            zone=None,
            period_start=None,
            period_end=None,
            group_by=["season"],
        )
        assert len(result) == 3
        by_season = {p.label["season"]: p for p in result}
        assert by_season["autumn"].value == 5.0
        assert by_season["summer"].value == 1.5

    def test_value_rounded_to_two_decimals(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [{"value": 3.456789, "sample_size": 5}],
        )
        result = _compute_avg_booking_duration_months(
            fake_db,
            city=None,
            zone=None,
            period_start=None,
            period_end=None,
            group_by=[],
        )
        assert result[0].value == 3.46

    def test_null_value_coerced_to_zero(self, fake_db):
        """AVG over empty set returns NULL in PG; coerce to 0.0."""
        fake_db.add_response("FROM reservation r", [{"value": None, "sample_size": 0}])
        result = _compute_avg_booking_duration_months(
            fake_db,
            city=None,
            zone=None,
            period_start=None,
            period_end=None,
            group_by=[],
        )
        assert result[0].value == 0.0


# Avg lead time


class TestComputeAvgLeadTimeDays:
    def test_basic(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [{"value": 45.7, "sample_size": 100}],
        )
        result = _compute_avg_lead_time_days(
            fake_db,
            city=None,
            zone=None,
            period_start=None,
            period_end=None,
            group_by=[],
        )
        assert result[0].value == 45.7
        assert result[0].sample_size == 100

    def test_rounded_to_one_decimal(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [{"value": 45.789, "sample_size": 50}],
        )
        result = _compute_avg_lead_time_days(
            fake_db,
            city=None,
            zone=None,
            period_start=None,
            period_end=None,
            group_by=[],
        )
        assert result[0].value == 45.8


# Seasonal demand


class TestComputeSeasonalDemand:
    def test_always_includes_season_dim(self, fake_db):
        """seasonal_demand always groups by season, even if not in input."""
        fake_db.add_response(
            "FROM reservation r",
            [
                {"season": "autumn", "value": 100, "sample_size": 100},
                {"season": "spring", "value": 40, "sample_size": 40},
                {"season": "summer", "value": 15, "sample_size": 15},
            ],
        )
        result = _compute_seasonal_demand(
            fake_db,
            city=None,
            period_start=None,
            period_end=None,
            group_by=[],
        )
        assert len(result) == 3
        seasons = {p.label["season"] for p in result}
        assert seasons == {"autumn", "spring", "summer"}

    def test_season_plus_year_group_by(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [
                {"season": "autumn", "year": 2024, "value": 50, "sample_size": 50},
                {"season": "autumn", "year": 2023, "value": 40, "sample_size": 40},
            ],
        )
        result = _compute_seasonal_demand(
            fake_db,
            city=None,
            period_start=None,
            period_end=None,
            group_by=["year"],
        )
        for p in result:
            assert "season" in p.label
            assert "year" in p.label

    def test_duplicate_season_in_group_by_not_repeated(self, fake_db):
        """User passes group_by=['season'] redundantly; helper should not duplicate."""
        fake_db.add_response(
            "FROM reservation r",
            [{"season": "autumn", "value": 100, "sample_size": 100}],
        )
        result = _compute_seasonal_demand(
            fake_db,
            city=None,
            period_start=None,
            period_end=None,
            group_by=["season"],
        )
        # Output label should have exactly one 'season' key
        assert result[0].label == {"season": "autumn"}


# Avg overall rating


class TestComputeAvgOverallRating:
    def test_filters_to_approved_status(self, fake_db):
        fake_db.add_response("FROM review rv", [{"value": 4.5, "sample_size": 20}])
        _compute_avg_overall_rating(
            fake_db,
            city=None,
            zone=None,
            period_start=None,
            period_end=None,
            group_by=[],
        )
        sql = fake_db.calls[0]["sql"]
        assert "rv.status = 'approved'" in sql

    def test_groups_by_zone(self, fake_db):
        fake_db.add_response(
            "FROM review rv",
            [
                {"zone": "Alfama", "value": 4.5, "sample_size": 10},
                {"zone": "Chiado", "value": 4.2, "sample_size": 8},
            ],
        )
        result = _compute_avg_overall_rating(
            fake_db,
            city=None,
            zone=None,
            period_start=None,
            period_end=None,
            group_by=["zone"],
        )
        by_zone = {p.label["zone"]: p for p in result}
        assert by_zone["Alfama"].value == 4.5

    def test_uses_datereview_for_period_filter(self, fake_db):
        fake_db.add_response("FROM review rv", [])
        _compute_avg_overall_rating(
            fake_db,
            city=None,
            zone=None,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            group_by=[],
        )
        sql = fake_db.calls[0]["sql"]
        assert "rv.datereview >= %s" in sql
        assert "rv.datereview <= %s" in sql


# Room inventory count


class TestComputeRoomInventoryCount:
    def test_total_inventory_no_grouping(self, fake_db):
        fake_db.add_response("FROM latest_room lr", [{"value": 150, "sample_size": 150}])
        result = _compute_room_inventory_count(fake_db, city=None, zone=None, group_by=[])
        assert len(result) == 1
        assert result[0].value == 150.0
        assert result[0].sample_size == 150
        assert result[0].label == {}

    def test_grouped_by_city(self, fake_db):
        fake_db.add_response(
            "FROM latest_room lr",
            [
                {"city": "Lisbon", "value": 100, "sample_size": 100},
                {"city": "Porto", "value": 50, "sample_size": 50},
            ],
        )
        result = _compute_room_inventory_count(fake_db, city=None, zone=None, group_by=["city"])
        by_city = {p.label["city"]: p for p in result}
        assert by_city["Lisbon"].value == 100
        assert by_city["Porto"].value == 50

    def test_time_dimensions_silently_ignored(self, fake_db, caplog):
        """season/year/month are not meaningful for inventory; should be dropped."""
        fake_db.add_response(
            "FROM latest_room lr",
            [{"city": "Lisbon", "value": 100, "sample_size": 100}],
        )
        with caplog.at_level("WARNING"):
            result = _compute_room_inventory_count(
                fake_db, city=None, zone=None, group_by=["city", "season", "year"]
            )
        # Only the 'city' label survives
        assert result[0].label == {"city": "Lisbon"}
        assert any("ignored" in r.message for r in caplog.records)

    def test_filters_to_available_status(self, fake_db):
        fake_db.add_response("FROM latest_room lr", [])
        _compute_room_inventory_count(fake_db, city=None, zone=None, group_by=[])
        sql = fake_db.calls[0]["sql"]
        assert "lr.status = 'Available'" in sql

    def test_city_and_zone_filters(self, fake_db):
        fake_db.add_response("FROM latest_room lr", [])
        _compute_room_inventory_count(fake_db, city="Lisbon", zone="Alfama", group_by=[])
        sql = fake_db.calls[0]["sql"]
        params = fake_db.calls[0]["params"]
        assert "h.city = %s" in sql
        assert "h.zone = %s" in sql
        assert "Lisbon" in params
        assert "Alfama" in params
