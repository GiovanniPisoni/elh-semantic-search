"""Tests for :func:`elh_rag.agent.tool_registry.build_tool_schemas`."""

from __future__ import annotations

from elh_rag.agent.tool_registry import build_tool_schemas
from elh_rag.tools.base import TOOLS_REGISTRY

EXPECTED_TOOL_NAMES = {
    "answer_policy_question",
    "compute_total_cost",
    "find_available_rooms",
    "find_rooms",
    "get_booking_stats",
    "get_property_details",
    "search_descriptions",
    "search_reviews",
}


class TestBuildToolSchemas:
    def test_returns_a_list_of_dicts(self) -> None:
        schemas = build_tool_schemas()
        assert isinstance(schemas, list)
        assert all(isinstance(s, dict) for s in schemas)

    def test_each_schema_has_required_keys(self) -> None:
        schemas = build_tool_schemas()
        for s in schemas:
            assert {"name", "description", "input_schema"} <= set(s.keys()), (
                f"missing keys in schema for {s.get('name')!r}"
            )

    def test_schemas_are_sorted_alphabetically(self) -> None:
        schemas = build_tool_schemas()
        names = [s["name"] for s in schemas]
        assert names == sorted(names), f"not sorted: {names}"

    def test_input_schema_is_a_json_schema_object(self) -> None:
        schemas = build_tool_schemas()
        for s in schemas:
            schema = s["input_schema"]
            assert schema.get("type") == "object", (
                f"input_schema for {s['name']!r} is not an object schema"
            )
            assert "properties" in schema, f"input_schema for {s['name']!r} has no properties"

    def test_includes_all_eight_registered_tools(self) -> None:
        schemas = build_tool_schemas()
        names = {s["name"] for s in schemas}
        missing = EXPECTED_TOOL_NAMES - names
        assert not missing, f"missing tools: {missing}"
        assert names <= set(TOOLS_REGISTRY)
