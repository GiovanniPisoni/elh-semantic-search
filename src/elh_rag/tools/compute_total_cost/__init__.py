"""Tool 3: ``compute_total_cost``.

Given a specific room and a stay window, returns the full cost
picture the student needs at booking time. See :mod:`.tool` for the
registered entry point.

Package layout:

    * :mod:`._expenses` — utility categorisation (rent-included vs
                          student-paid), keyed on the house version
                          the room is attached to.
    * :mod:`.tool`      — registered entry point, cost composition,
                          summary, notes.
"""

from ._expenses import UtilityCategorization, fetch_utility_categorization
from .tool import (
    ComputeTotalCostInput,
    ComputeTotalCostOutput,
    MonthRentOut,
    compute_total_cost,
)

__all__ = [
    "ComputeTotalCostInput",
    "ComputeTotalCostOutput",
    "MonthRentOut",
    "UtilityCategorization",
    "compute_total_cost",
    "fetch_utility_categorization",
]
