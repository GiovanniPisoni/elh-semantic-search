"""Amenity name → DB column mappings.

Two dicts:

* ``_EXPLICIT_AMENITY_COLUMN_MAP`` — keyed on input field names
  (``must_have_*`` booleans). All 11 entries map to columns that
  actually exist in the ELH schema.

* ``_OTHER_AMENITY_COLUMN_MAP`` — keyed on the ``OtherAmenity``
  Literal. **27/28 of these entries currently point at columns that
  do NOT exist in the production schema.** They produce SQL that
  always fails the ``= 'Y'`` check and silently zero out the result
  set. A separate commit (Commit 2) drops the fictional ones and
  remaps a handful to their real-schema counterparts.

The tuple value is ``(table_alias_letter, column_name)`` where
``table_alias_letter`` is ``"house"`` or ``"room"`` (the SQL builder
takes the first letter for the alias).
"""

from __future__ import annotations

_EXPLICIT_AMENITY_COLUMN_MAP: dict[str, tuple[str, str]] = {
    # field name on input → (table, column_name)
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

# TODO: Commit 2 — audit. 27/28 of these are fictional columns.
# Real ones (1):                cityview
# Remappable to real (4):       common_room→sharedspace,
#                               wheelchair_accessible→reducedmobilityaccess,
#                               kitchen_microwave→microwaveoven,
#                               non_smoking→smokingallowed='N' (inverse logic)
# To be dropped (23):           gardenview, riverview, securityalarm,
#                               doorman, videointercom, oven, microwave,
#                               freezer, kettle, bbq, pool, gym, tv, iron,
#                               hairdryer, safebox, linen, cleaningservice,
#                               garbagedisposal, fireplace, petfriendly,
#                               couplesallowed, longterm, shortterm
_OTHER_AMENITY_COLUMN_MAP: dict[str, tuple[str, str]] = {
    "city_view": ("house", "cityview"),
    "garden_view": ("house", "gardenview"),
    "river_view": ("house", "riverview"),
    "security_alarm": ("house", "securityalarm"),
    "doorman": ("house", "doorman"),
    "video_intercom": ("house", "videointercom"),
    "kitchen_oven": ("house", "oven"),
    "kitchen_microwave": ("house", "microwave"),
    "kitchen_freezer": ("house", "freezer"),
    "kitchen_kettle": ("house", "kettle"),
    "bbq": ("house", "bbq"),
    "pool": ("house", "pool"),
    "gym": ("house", "gym"),
    "common_room": ("house", "commonroom"),
    "tv": ("house", "tv"),
    "iron": ("house", "iron"),
    "hairdryer": ("house", "hairdryer"),
    "safebox": ("house", "safebox"),
    "linen_provided": ("house", "linen"),
    "cleaning_service": ("house", "cleaningservice"),
    "garbage_disposal": ("house", "garbagedisposal"),
    "fireplace": ("house", "fireplace"),
    "wheelchair_accessible": ("house", "wheelchairaccess"),
    "non_smoking": ("house", "nonsmoking"),
    "pet_friendly_common": ("house", "petfriendly"),
    "couples_welcome": ("house", "couplesallowed"),
    "long_term_friendly": ("house", "longterm"),
    "short_term_ok": ("house", "shortterm"),
}