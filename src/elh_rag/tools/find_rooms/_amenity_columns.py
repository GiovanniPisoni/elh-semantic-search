"""Amenity name → DB column mappings.

Two dicts and one set:

* ``_EXPLICIT_AMENITY_COLUMN_MAP`` — keyed on input field names
  (``must_have_*`` booleans). All 11 entries map to columns that
  actually exist in the ELH schema.

* ``_OTHER_AMENITY_COLUMN_MAP`` — keyed on the ``OtherAmenity``
  Literal. **Audited 2026-05-08** against the production schema.
  Every Literal value maps 1:1 to an existing Y/N column on either
  ``house`` (22 entries) or ``room`` (4 entries: closet, bedlinen,
  pillows, extra_person_allowed).

* ``_OTHER_AMENITY_INVERTED`` — set of amenity names whose user-facing
  semantics are the negation of the column. ``non_smoking`` is True
  when ``smokingallowed = 'N'``.

The tuple value is ``(table_name, column_name)`` where ``table_name``
is ``"house"`` or ``"room"``; the SQL builder uses the first letter
as table alias.
"""

from __future__ import annotations

_EXPLICIT_AMENITY_COLUMN_MAP: dict[str, tuple[str, str]] = {
    "must_have_private_bathroom": ("room", "privatebathroom"),
    "must_have_balcony": ("room", "balcony"),
    "must_have_elevator": ("house", "elevator"),
    "must_have_air_conditioning": ("room", "airconditioning"),
    "must_have_heating": ("room", "heating"),
    "must_have_washing_machine": ("house", "washerdrier"),
    "must_have_dishwasher": ("house", "dishwasher"),
    "must_have_parking": ("house", "parking"),
    "must_have_internet": ("house", "internet"),
    "must_have_desk": ("room", "desk"),
    "must_have_window": ("room", "haswindow"),
}

_OTHER_AMENITY_COLUMN_MAP: dict[str, tuple[str, str]] = {
    "armored_door": ("house", "armoreddoor"),
    "bedlinen": ("room", "bedlinen"),
    "cable_tv": ("house", "cabletv"),
    "cctv": ("house", "cctv"),
    "central_heating": ("house", "centralheating"),
    "city_view": ("house", "cityview"),
    "closet": ("room", "closet"),
    "coded_entry": ("house", "codeentry"),
    "countryside_view": ("house", "fieldview"),
    "double_glazed_windows": ("house", "doubleglazedwindows"),
    "equipped_kitchen": ("house", "kitchenequipment"),
    "extra_person_allowed": ("room", "extrapersonallowed"),
    "fridge": ("house", "fridge"),
    "furnished": ("house", "furnished"),
    "microwave": ("house", "microwaveoven"),
    "night_guests_allowed": ("house", "allownightguests"),
    "non_smoking": ("house", "smokingallowed"),  # inverse — see _OTHER_AMENITY_INVERTED
    "pillows": ("room", "pillows"),
    "sea_view": ("house", "seaview"),
    "security_24h": ("house", "security24h"),
    "shared_space": ("house", "sharedspace"),
    "smart_tv": ("house", "smarttv"),
    "smoke_detector": ("house", "smokedetector"),
    "stove": ("house", "gaselectricstove"),
    "thermal_insulation": ("house", "thermalinsulation"),
    "wheelchair_accessible": ("house", "reducedmobilityaccess"),
}

# Amenity names whose user-facing meaning is the negation of the column.
_OTHER_AMENITY_INVERTED: frozenset[str] = frozenset({"non_smoking"})
