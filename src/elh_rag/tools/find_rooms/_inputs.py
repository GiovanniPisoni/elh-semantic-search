"""Input model for ``find_rooms``.

Pure Pydantic + Literal types; no DB / SQL / IO imports here so this
module is cheap to import and easy to unit-test.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Allowed values

MetroLineInput = Literal[
    "blue",
    "yellow",
    "green",
    "red",
    "violet",
    "orange",
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
]

OtherAmenity = Literal[
    "armored_door",
    "cable_tv",
    "cctv",
    "central_heating",
    "city_view",
    "coded_entry",
    "countryside_view",
    "double_glazed_windows",
    "equipped_kitchen",
    "fridge",
    "furnished",
    "microwave",
    "night_guests_allowed",
    "non_smoking",
    "sea_view",
    "security_24h",
    "shared_space",
    "smart_tv",
    "smoke_detector",
    "stove",
    "thermal_insulation",
    "wheelchair_accessible",
]


# Input model


class FindRoomsInput(BaseModel):
    """Search rooms by structured criteria.

    All parameters are optional (None = no filter on that dimension).
    Returns up to ``max_results`` rooms ranked by ``match_score``.
    """

    # ── 1. LOCATION ──
    city: Literal["Lisbon", "Porto"] | None = None
    metro_line: MetroLineInput | None = Field(
        default=None,
        description="Metro line. Accepts colour names (blue, yellow, "
        "green, red, violet, orange) or Porto letter codes "
        "(A=blue, B=red, C=green, D=yellow, E=violet, F=orange).",
    )
    near_landmark: str | None = Field(
        default=None,
        max_length=100,
        description="Free-text landmark (e.g., 'NOVA University'). "
        "Matched ILIKE on house.zone, neighboorhood, description.",
    )
    max_distance_to_transport_m: int | None = Field(default=None, ge=0, le=5000)

    # 2. PRICE
    max_price_eur: float | None = Field(default=None, ge=0, le=10000)
    min_price_eur: float | None = Field(default=None, ge=0, le=10000)

    # 3. PERIOD
    available_from: date | None = None
    available_to: date | None = None
    min_contract_months: int | None = Field(default=None, ge=1, le=24)
    min_reserve_months: int | None = Field(default=None, ge=1, le=12)

    # 4. OCCUPANCY
    accepts_couples: bool | None = None
    accepts_pets: bool | None = None
    gender_preference: Literal["male_only", "female_only", "any"] | None = None
    max_house_occupancy: int | None = Field(default=None, ge=1, le=20)
    num_rooms_needed: int = Field(default=1, ge=1, le=10)

    # 5. EXPLICIT AMENITIES
    must_have_private_bathroom: bool | None = None
    must_have_balcony: bool | None = None
    must_have_elevator: bool | None = None
    must_have_air_conditioning: bool | None = None
    must_have_heating: bool | None = None
    must_have_washing_machine: bool | None = None
    must_have_dishwasher: bool | None = None
    must_have_parking: bool | None = None
    must_have_internet: bool | None = None
    must_have_desk: bool | None = None
    must_have_window: bool | None = None

    # 6. OTHER AMENITIES
    required_other_amenities: list[OtherAmenity] = Field(default_factory=list)

    # 7. SORT + LIMIT
    sort_by: Literal["price_asc", "price_desc", "default"] = "default"
    max_results: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def check_consistency(self) -> FindRoomsInput:
        # Price range
        if (
            self.max_price_eur is not None
            and self.min_price_eur is not None
            and self.max_price_eur < self.min_price_eur
        ):
            raise ValueError("max_price_eur must be >= min_price_eur")
        # Date range
        if (
            self.available_from is not None
            and self.available_to is not None
            and self.available_to <= self.available_from
        ):
            raise ValueError("available_to must be after available_from")
        return self
