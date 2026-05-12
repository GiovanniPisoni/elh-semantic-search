"""Tests for ``elh_rag.tools.get_property_details`` review aggregator."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from elh_rag.tools.get_property_details import (
    ReviewsAggregate,
    ReviewSummary,
    fetch_reviews_aggregate,
)


def _make_review_row(
    *,
    datereview: date = date(2025, 6, 1),
    title: str = "Great stay",
    description: str = "Loved the place, very clean.",
    overall: str = "5.00",
    cleaning: str = "5.00",
    communication: str = "4.50",
    location: str = "4.00",
    price_quality: str = "4.50",
    status: str = "approved",
) -> dict:
    return {
        "datereview": datereview,
        "title": title,
        "description": description,
        "overallratings": Decimal(overall),
        "cleaningratings": Decimal(cleaning),
        "communicationratings": Decimal(communication),
        "locationratings": Decimal(location),
        "pricequalityratings": Decimal(price_quality),
        "status": status,
    }


_HOUSE_DT = date(2024, 9, 15)


# Empty result


class TestEmptyResult:
    def test_no_rows_returns_zero_count_and_none_averages(self, fake_db):
        fake_db.add_response("FROM review", [])
        result = fetch_reviews_aggregate(
            fake_db,
            house_id="HSE_001",
            house_dateupdate=_HOUSE_DT,
            room_id="RM_001",
        )
        assert isinstance(result, ReviewsAggregate)
        assert result.count == 0
        assert result.average_overall_rating is None
        assert result.average_cleaning_rating is None
        assert result.average_communication_rating is None
        assert result.average_location_rating is None
        assert result.average_price_quality_rating is None
        assert result.recent_reviews == []


# Averages


class TestAverages:
    def test_single_review_averages_equal_values(self, fake_db):
        fake_db.add_response(
            "FROM review",
            [_make_review_row(overall="4.50", cleaning="5.00")],
        )
        result = fetch_reviews_aggregate(
            fake_db, house_id="HSE_001", house_dateupdate=_HOUSE_DT, room_id="RM_001"
        )
        assert result.count == 1
        assert result.average_overall_rating == 4.50
        assert result.average_cleaning_rating == 5.00

    def test_two_reviews_arithmetic_mean(self, fake_db):
        fake_db.add_response(
            "FROM review",
            [
                _make_review_row(overall="5.00"),
                _make_review_row(overall="3.00"),
            ],
        )
        result = fetch_reviews_aggregate(
            fake_db, house_id="HSE_001", house_dateupdate=_HOUSE_DT, room_id="RM_001"
        )
        assert result.count == 2
        assert result.average_overall_rating == 4.00

    def test_averages_rounded_to_two_decimals(self, fake_db):
        fake_db.add_response(
            "FROM review",
            [
                _make_review_row(overall="4.00"),
                _make_review_row(overall="5.00"),
                _make_review_row(overall="5.00"),
            ],
        )
        result = fetch_reviews_aggregate(
            fake_db, house_id="HSE_001", house_dateupdate=_HOUSE_DT, room_id="RM_001"
        )
        assert result.average_overall_rating == 4.67

    def test_all_five_dimensions_averaged(self, fake_db):
        fake_db.add_response(
            "FROM review",
            [
                _make_review_row(
                    overall="5.00",
                    cleaning="4.00",
                    communication="3.00",
                    location="5.00",
                    price_quality="4.00",
                ),
                _make_review_row(
                    overall="3.00",
                    cleaning="2.00",
                    communication="5.00",
                    location="3.00",
                    price_quality="2.00",
                ),
            ],
        )
        result = fetch_reviews_aggregate(
            fake_db, house_id="HSE_001", house_dateupdate=_HOUSE_DT, room_id="RM_001"
        )
        assert result.average_overall_rating == 4.00
        assert result.average_cleaning_rating == 3.00
        assert result.average_communication_rating == 4.00
        assert result.average_location_rating == 4.00
        assert result.average_price_quality_rating == 3.00


# Recent reviews


class TestRecentReviews:
    def test_at_most_three_recent_returned(self, fake_db):
        rows = [
            _make_review_row(
                datereview=date(2025, 1, 1),
                title=f"Review {i}",
                description=f"Body of review {i}",
            )
            for i in range(10)
        ]
        fake_db.add_response("FROM review", rows)
        result = fetch_reviews_aggregate(
            fake_db, house_id="HSE_001", house_dateupdate=_HOUSE_DT, room_id="RM_001"
        )
        assert result.count == 10  # count uses all rows
        assert len(result.recent_reviews) == 3  # but recent_reviews capped

    def test_recent_preserves_db_order(self, fake_db):
        """SQL orders by datereview DESC; helper preserves that order."""
        rows = [
            _make_review_row(datereview=date(2025, 12, 1), title="Newest"),
            _make_review_row(datereview=date(2025, 6, 1), title="Mid"),
            _make_review_row(datereview=date(2025, 1, 1), title="Oldest"),
        ]
        fake_db.add_response("FROM review", rows)
        result = fetch_reviews_aggregate(
            fake_db, house_id="HSE_001", house_dateupdate=_HOUSE_DT, room_id="RM_001"
        )
        titles = [r.title for r in result.recent_reviews]
        assert titles == ["Newest", "Mid", "Oldest"]

    def test_excerpt_truncated_at_200_chars(self, fake_db):
        long_text = "x" * 500
        fake_db.add_response("FROM review", [_make_review_row(description=long_text)])
        result = fetch_reviews_aggregate(
            fake_db, house_id="HSE_001", house_dateupdate=_HOUSE_DT, room_id="RM_001"
        )
        excerpt = result.recent_reviews[0].excerpt
        # 200 chars + ellipsis marker
        assert excerpt.endswith("…")
        assert len(excerpt) == 201  # 200 + "…"

    def test_short_description_not_truncated(self, fake_db):
        fake_db.add_response("FROM review", [_make_review_row(description="Short.")])
        result = fetch_reviews_aggregate(
            fake_db, house_id="HSE_001", house_dateupdate=_HOUSE_DT, room_id="RM_001"
        )
        excerpt = result.recent_reviews[0].excerpt
        assert excerpt == "Short."
        assert not excerpt.endswith("…")

    def test_summary_fields_have_correct_types(self, fake_db):
        fake_db.add_response("FROM review", [_make_review_row()])
        result = fetch_reviews_aggregate(
            fake_db, house_id="HSE_001", house_dateupdate=_HOUSE_DT, room_id="RM_001"
        )
        summary = result.recent_reviews[0]
        assert isinstance(summary, ReviewSummary)
        assert isinstance(summary.overall_rating, float)
        assert isinstance(summary.date_review, date)


# Scope


class TestScope:
    def test_room_scope_filters_idroom_in_sql(self, fake_db):
        fake_db.add_response("FROM review", [])
        fetch_reviews_aggregate(
            fake_db,
            house_id="HSE_001",
            house_dateupdate=_HOUSE_DT,
            room_id="RM_001",
        )
        call = fake_db.calls[0]
        assert "idroom = %s" in call["sql"]
        assert call["params"] == ("HSE_001", _HOUSE_DT, "RM_001", "approved")

    def test_house_scope_drops_idroom_filter(self, fake_db):
        fake_db.add_response("FROM review", [])
        fetch_reviews_aggregate(
            fake_db,
            house_id="HSE_001",
            house_dateupdate=_HOUSE_DT,
            room_id=None,
        )
        call = fake_db.calls[0]
        assert "idroom = %s" not in call["sql"]
        assert call["params"] == ("HSE_001", _HOUSE_DT, "approved")

    def test_only_approved_reviews_queried(self, fake_db):
        fake_db.add_response("FROM review", [])
        fetch_reviews_aggregate(
            fake_db,
            house_id="HSE_001",
            house_dateupdate=_HOUSE_DT,
            room_id="RM_001",
        )
        sql = fake_db.calls[0]["sql"]
        params = fake_db.calls[0]["params"]
        assert "status = %s" in sql
        assert "approved" in params

    def test_padded_title_stripped(self, fake_db):
        """character(100) title columns return right-padded values."""
        fake_db.add_response(
            "FROM review",
            [_make_review_row(title="Great" + " " * 95)],
        )
        result = fetch_reviews_aggregate(
            fake_db, house_id="HSE_001", house_dateupdate=_HOUSE_DT, room_id="RM_001"
        )
        assert result.recent_reviews[0].title == "Great"
