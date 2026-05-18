"""Pydantic output model for aggregate statistics.

``StatPoint`` is the unit of result returned by every metric in
:mod:`._metrics`. Lives in its own module so importers don't pay the
cost of loading metric SQL builders just to type-annotate a return
value.
"""

from __future__ import annotations

from pydantic import BaseModel


class StatPoint(BaseModel):
    """One row of an aggregate statistic.

    ``label`` is a dict so it can hold an arbitrary number of dimension
    columns (e.g. ``{"city": "Lisbon", "year": "2024"}``). All values
    are strings for uniform LLM consumption, even when the underlying
    column was numeric (year).
    """

    label: dict[str, str]
    value: float
    sample_size: int
