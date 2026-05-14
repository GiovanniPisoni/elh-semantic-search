"""
Build the tool-use schema list passed to the Anthropic API.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_tool_schemas() -> list[dict[str, Any]]:
    """Return the full list of tool schemas for the Anthropic API call."""
    raise NotImplementedError("Implemented in Step 3.3")
