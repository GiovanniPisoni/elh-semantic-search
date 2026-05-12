"""Tests for Tool 5 — ``get_booking_stats``.

Covers:

    * input validation (occupancy_rate period requirement,
      end-after-start, metric Literal enforcement)
    * dispatch to each of the seven metrics
    * k-anonymity integration (suppression counter, empty-result warning)
    * output shape (disclaimer present, summary, total_underlying_rows)
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from elh_rag.tools.get_booking_stats import (
    GetBookingStatsInput,
    get_booking_stats,
)

# Input validation


class TestInputValidation:
    def test_unknown_metric_rejected(self):
        with pytest.raises(ValidationError):
            GetBookingStatsInput(metric="bogus_metric")  # type: ignore[arg-type]

    def test_period_end_before_start_rejected(self):
        with pytest.raises(ValidationError, match="must be on or after"):
            GetBookingStatsInput(
                metric="top_zones_by_bookings",
                period_start=date(2024, 12, 31),
                period_end=date(2024, 1, 1),
            )

    def test_occupancy_rate_requires_both_period_bounds(self):
        with pytest.raises(ValidationError, match="requires both"):
            GetBookingStatsInput(metric="occupancy_rate")

    def test_occupancy_rate_requires_period_end(self):
        with pytest.raises(ValidationError, match="requires both"):
            GetBookingStatsInput(metric="occupancy_rate", period_start=date(2024, 1, 1))

    def test_occupancy_rate_with_both_periods_accepted(self):
        payload = GetBookingStatsInput(
            metric="occupancy_rate",
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        )
        assert payload.period_start == date(2024, 1, 1)

    def test_top_n_bounded(self):
        with pytest.raises(ValidationError):
            GetBookingStatsInput(metric="top_zones_by_bookings", top_n=0)
        with pytest.raises(ValidationError):
            GetBookingStatsInput(metric="top_zones_by_bookings", top_n=100)

    def test_group_by_unknown_dim_rejected(self):
        with pytest.raises(ValidationError):
            GetBookingStatsInput(
                metric="seasonal_demand",
                group_by=["bogus_dim"],  # type: ignore[list-item]
            )

    def test_city_restricted_to_lisbon_or_porto(self):
        with pytest.raises(ValidationError):
            GetBookingStatsInput(
                metric="top_zones_by_bookings",
                city="Berlin",  # type: ignore[arg-type]
            )


# Dispatch


class TestDispatch:
    def test_dispatch_no_ctx_raises(self):
        with pytest.raises(RuntimeError, match="DBExecutor"):
            get_booking_stats(
                GetBookingStatsInput(metric="room_inventory_count"),
                ctx=None,
            )

    def test_dispatch_occupancy_rate(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [{"booked_rooms": 10, "booking_count": 12}],
        )
        fake_db.add_response(
            "FROM latest_room lr",
            [{"active_rooms": 50}],
        )
        result = get_booking_stats(
            GetBookingStatsInput(
                metric="occupancy_rate",
                period_start=date(2024, 1, 1),
                period_end=date(2024, 12, 31),
            ),
            ctx=fake_db,
        )
        assert result.metric == "occupancy_rate"
        assert len(result.data_points) == 1
        assert result.data_points[0].value == 0.2

    def test_dispatch_top_zones_by_bookings(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [
                {"zone": "Alfama", "value": 42, "sample_size": 42},
                {"zone": "Chiado", "value": 18, "sample_size": 18},
            ],
        )
        result = get_booking_stats(
            GetBookingStatsInput(metric="top_zones_by_bookings", top_n=5),
            ctx=fake_db,
        )
        assert result.metric == "top_zones_by_bookings"
        assert len(result.data_points) == 2

    def test_dispatch_avg_booking_duration_months(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [{"value": 4.5, "sample_size": 50}],
        )
        result = get_booking_stats(
            GetBookingStatsInput(metric="avg_booking_duration_months"),
            ctx=fake_db,
        )
        assert result.data_points[0].value == 4.5

    def test_dispatch_avg_lead_time_days(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [{"value": 45.0, "sample_size": 30}],
        )
        result = get_booking_stats(
            GetBookingStatsInput(metric="avg_lead_time_days"),
            ctx=fake_db,
        )
        assert result.data_points[0].value == 45.0

    def test_dispatch_seasonal_demand(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [
                {"season": "autumn", "value": 80, "sample_size": 80},
                {"season": "spring", "value": 40, "sample_size": 40},
                {"season": "summer", "value": 10, "sample_size": 10},
            ],
        )
        result = get_booking_stats(
            GetBookingStatsInput(metric="seasonal_demand"),
            ctx=fake_db,
        )
        assert len(result.data_points) == 3
        seasons = {p.label["season"] for p in result.data_points}
        assert seasons == {"autumn", "spring", "summer"}

    def test_dispatch_avg_overall_rating(self, fake_db):
        fake_db.add_response("FROM review rv", [{"value": 4.3, "sample_size": 100}])
        result = get_booking_stats(
            GetBookingStatsInput(metric="avg_overall_rating"),
            ctx=fake_db,
        )
        assert result.data_points[0].value == 4.3

    def test_dispatch_room_inventory_count(self, fake_db):
        fake_db.add_response("FROM latest_room lr", [{"value": 150, "sample_size": 150}])
        result = get_booking_stats(
            GetBookingStatsInput(metric="room_inventory_count"),
            ctx=fake_db,
        )
        assert result.data_points[0].value == 150.0


# K-anonymity integration


class TestKAnonymityIntegration:
    def test_buckets_below_threshold_suppressed(self, fake_db):
        """Buckets with sample_size < 5 are stripped, counter incremented."""
        fake_db.add_response(
            "FROM reservation r",
            [
                {"zone": "Alfama", "value": 10, "sample_size": 10},
                {"zone": "Chiado", "value": 3, "sample_size": 3},  # below k=5
                {"zone": "Bairro", "value": 6, "sample_size": 6},
                {"zone": "Belém", "value": 2, "sample_size": 2},  # below k=5
            ],
        )
        result = get_booking_stats(
            GetBookingStatsInput(metric="top_zones_by_bookings"),
            ctx=fake_db,
        )
        zones_kept = {p.label["zone"] for p in result.data_points}
        assert zones_kept == {"Alfama", "Bairro"}
        assert result.suppressed_buckets == 2

    def test_total_underlying_rows_counts_pre_suppression(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [
                {"zone": "A", "value": 10, "sample_size": 10},
                {"zone": "B", "value": 3, "sample_size": 3},
            ],
        )
        result = get_booking_stats(
            GetBookingStatsInput(metric="top_zones_by_bookings"),
            ctx=fake_db,
        )
        # 10 + 3 = 13, even though the B bucket was suppressed
        assert result.total_underlying_rows == 13

    def test_all_buckets_suppressed_returns_empty_with_warning(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [
                {"zone": "X", "value": 2, "sample_size": 2},
                {"zone": "Y", "value": 1, "sample_size": 1},
            ],
        )
        result = get_booking_stats(
            GetBookingStatsInput(metric="top_zones_by_bookings"),
            ctx=fake_db,
        )
        assert result.data_points == []
        assert result.suppressed_buckets == 2
        assert any("insufficient data" in w for w in result.warnings)

    def test_empty_db_result_returns_empty_with_warning(self, fake_db):
        fake_db.add_response("FROM reservation r", [])
        result = get_booking_stats(
            GetBookingStatsInput(metric="top_zones_by_bookings"),
            ctx=fake_db,
        )
        assert result.data_points == []
        assert result.suppressed_buckets == 0
        assert result.total_underlying_rows == 0
        assert any("no data matched" in w for w in result.warnings)


# Output shape


class TestOutputShape:
    def test_disclaimer_always_present(self, fake_db):
        fake_db.add_response("FROM latest_room lr", [{"value": 100, "sample_size": 100}])
        result = get_booking_stats(
            GetBookingStatsInput(metric="room_inventory_count"),
            ctx=fake_db,
        )
        assert result.disclaimer
        assert "k-anonymity" in result.disclaimer
        assert "internal" in result.disclaimer.lower()

    def test_disclaimer_present_even_on_empty_result(self, fake_db):
        fake_db.add_response("FROM reservation r", [])
        result = get_booking_stats(
            GetBookingStatsInput(metric="top_zones_by_bookings"),
            ctx=fake_db,
        )
        assert result.data_points == []
        assert result.disclaimer  # still present

    def test_summary_for_single_bucket_mentions_value(self, fake_db):
        fake_db.add_response("FROM latest_room lr", [{"value": 150, "sample_size": 150}])
        result = get_booking_stats(
            GetBookingStatsInput(metric="room_inventory_count"),
            ctx=fake_db,
        )
        assert "150" in result.summary

    def test_summary_for_multiple_buckets_mentions_count(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [
                {"zone": "A", "value": 10, "sample_size": 10},
                {"zone": "B", "value": 8, "sample_size": 8},
                {"zone": "C", "value": 6, "sample_size": 6},
            ],
        )
        result = get_booking_stats(
            GetBookingStatsInput(metric="top_zones_by_bookings"),
            ctx=fake_db,
        )
        assert "3 bucket" in result.summary

    def test_summary_mentions_no_data_when_empty(self, fake_db):
        fake_db.add_response("FROM reservation r", [])
        result = get_booking_stats(
            GetBookingStatsInput(metric="top_zones_by_bookings"),
            ctx=fake_db,
        )
        assert "no data" in result.summary.lower()

    def test_summary_mentions_suppression_when_all_below_k(self, fake_db):
        fake_db.add_response(
            "FROM reservation r",
            [
                {"zone": "X", "value": 2, "sample_size": 2},
                {"zone": "Y", "value": 1, "sample_size": 1},
            ],
        )
        result = get_booking_stats(
            GetBookingStatsInput(metric="top_zones_by_bookings"),
            ctx=fake_db,
        )
        assert "k-anonymity" in result.summary.lower() or "insufficient" in result.summary.lower()
