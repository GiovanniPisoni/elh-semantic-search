"""
Build the tool-use schema list passed to the Anthropic API.
"""

from __future__ import annotations

import logging
from typing import Any

from elh_rag.tools.base import TOOLS_REGISTRY

logger = logging.getLogger(__name__)


def build_tool_schemas() -> list[dict[str, Any]]:
    """Return the full list of tool schemas for the Anthropic API call."""
    schemas: list[dict[str, Any]] = []
    for name in sorted(TOOLS_REGISTRY):
        spec = TOOLS_REGISTRY[name]
        schemas.append(
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_model.model_json_schema(),
            }
        )
    logger.debug("agent.tool_registry: built %d tool schemas", len(schemas))
    return schemas
