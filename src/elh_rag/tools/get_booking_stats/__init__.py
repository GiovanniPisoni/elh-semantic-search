"""Tool 5: ``get_booking_stats``.

Aggregate-statistics endpoint for the internal ELH team. See
:mod:`.tool` for the registered entry point.

Package layout (SRP-split):

    * :mod:`._models`        — StatPoint Pydantic model.
    * :mod:`._sql_builders`  — pure SQL fragment builders:
                               season / year / month expressions,
                               GROUP BY select clauses, label builder,
                               WHERE-clause helpers, latest-active
                               room CTE. ``GroupByDim`` Literal lives
                               here.
    * :mod:`._metrics`       — the 7 ``_compute_*`` functions, one
                               per supported metric, each returning
                               ``list[StatPoint]`` pre k-anonymity.
    * :mod:`._kanon`         — ``K_THRESHOLD`` constant and
                               ``filter_by_k_anonymity`` post-filter.
    * :mod:`.tool`           — registered entry point: input
                               validation, metric dispatch,
                               k-anonymity application, summary +
                               disclaimer composition.
"""

from ._kanon import K_THRESHOLD, filter_by_k_anonymity
from ._metrics import (
    _avg_reservation_metric,
    _compute_avg_booking_duration_months,
    _compute_avg_lead_time_days,
    _compute_avg_overall_rating,
    _compute_occupancy_rate,
    _compute_room_inventory_count,
    _compute_seasonal_demand,
    _compute_top_zones_by_bookings,
)
from ._models import StatPoint
from ._sql_builders import GroupByDim
from .tool import (
    GetBookingStatsInput,
    GetBookingStatsOutput,
    Metric,
    get_booking_stats,
)

__all__ = [
    "K_THRESHOLD",
    "GetBookingStatsInput",
    "GetBookingStatsOutput",
    "GroupByDim",
    "Metric",
    "StatPoint",
    "_avg_reservation_metric",
    "_compute_avg_booking_duration_months",
    "_compute_avg_lead_time_days",
    "_compute_avg_overall_rating",
    "_compute_occupancy_rate",
    "_compute_room_inventory_count",
    "_compute_seasonal_demand",
    "_compute_top_zones_by_bookings",
    "filter_by_k_anonymity",
    "get_booking_stats",
]
