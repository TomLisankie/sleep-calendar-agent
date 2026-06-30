"""
Layer 1b/c — System prompt integrity and tool schema compliance tests.

These tests are purely structural: they never call an LLM, never open a
socket, and complete in milliseconds.  They catch regressions introduced by
edits to system_prompt.py or tools.py.
"""
from __future__ import annotations

import json
import re

import pytest

from agent.system_prompt import get_system_prompt, get_tool_list
from agent.tools import TOOLS


# ── System prompt structural checks ──────────────────────────────────────────

class TestSystemPromptIntegrity:
    """get_system_prompt() must contain specific structural invariants."""

    @pytest.fixture(autouse=True)
    def prompt(self):
        self._prompt = get_system_prompt()

    def test_prompt_is_non_empty_string(self):
        assert isinstance(self._prompt, str)
        assert len(self._prompt) > 100

    def test_contains_current_ny_datetime(self):
        # We can't know the exact time, but the prompt must contain a year
        # and a time-zone indicator like "EDT" or "EST".
        assert re.search(r"\b202[5-9]\b", self._prompt), "Expected a year in the prompt"
        assert re.search(r"\b(EDT|EST)\b", self._prompt), "Expected EDT or EST timezone in prompt"

    def test_mentions_sleep_protection(self):
        lower = self._prompt.lower()
        assert "sleep" in lower, "Prompt must mention sleep"
        assert any(word in lower for word in ("protect", "inviolable", "conflict", "wind")), \
            "Prompt must include sleep-protection language"

    def test_mentions_new_york_timezone(self):
        lower = self._prompt.lower()
        assert any(phrase in lower for phrase in ("new york", "america/new_york", "ny local")), \
            "Prompt must mention New York timezone"

    def test_contains_iso8601_guidance(self):
        assert "ISO-8601" in self._prompt or "iso-8601" in self._prompt.lower(), \
            "Prompt must mention ISO-8601 datetime format"

    def test_tool_list_included(self):
        # Every tool name should appear in the prompt (injected via get_tool_list).
        for tool in TOOLS:
            name = tool["function"]["name"]
            assert name in self._prompt, f"Tool '{name}' missing from system prompt"


# ── Tool list summary ─────────────────────────────────────────────────────────

class TestToolListSummary:
    """get_tool_list() must produce a human-readable summary."""

    @pytest.fixture(autouse=True)
    def tool_list(self):
        self._tool_list = get_tool_list()

    def test_non_empty(self):
        assert len(self._tool_list) > 50

    def test_every_tool_name_present(self):
        for tool in TOOLS:
            name = tool["function"]["name"]
            assert name in self._tool_list, f"Tool '{name}' missing from tool list"

    def test_each_entry_has_bullet(self):
        # Our format is: "  • tool_name(...)"
        assert self._tool_list.count("•") == len(TOOLS), \
            "Expected one bullet point per tool"

    def test_descriptions_included(self):
        # Every tool description should contribute some text.
        for tool in TOOLS:
            desc_snippet = tool["function"]["description"][:20]
            assert desc_snippet in self._tool_list, \
                f"Description for '{tool['function']['name']}' missing from tool list"


# ── Tool schema compliance ─────────────────────────────────────────────────────

class TestToolSchemaCompliance:
    """Every entry in TOOLS must satisfy the OpenAI function-calling schema."""

    @pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["function"]["name"])
    def test_top_level_type_is_function(self, tool):
        assert tool.get("type") == "function", \
            f"tool['type'] must be 'function', got {tool.get('type')!r}"

    @pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["function"]["name"])
    def test_has_name(self, tool):
        fn = tool["function"]
        assert "name" in fn and fn["name"], "Tool must have a non-empty 'name'"

    @pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["function"]["name"])
    def test_has_description(self, tool):
        fn = tool["function"]
        assert "description" in fn and fn["description"], \
            f"Tool '{fn['name']}' must have a non-empty 'description'"

    @pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["function"]["name"])
    def test_parameters_is_object_type(self, tool):
        params = tool["function"]["parameters"]
        assert params.get("type") == "object", \
            f"Tool '{tool['function']['name']}' parameters.type must be 'object'"

    @pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["function"]["name"])
    def test_required_is_a_list(self, tool):
        params = tool["function"]["parameters"]
        assert isinstance(params.get("required"), list), \
            f"Tool '{tool['function']['name']}' parameters.required must be a list"

    @pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["function"]["name"])
    def test_all_required_params_exist_in_properties(self, tool):
        fn = tool["function"]
        params = fn["parameters"]
        props = params.get("properties", {})
        for req_param in params.get("required", []):
            assert req_param in props, (
                f"Tool '{fn['name']}': required param '{req_param}' "
                f"not found in properties. Properties: {list(props.keys())}"
            )

    @pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["function"]["name"])
    def test_all_property_types_are_valid_json_schema_types(self, tool):
        valid_types = {"string", "number", "integer", "boolean", "array", "object", "null"}
        fn = tool["function"]
        props = fn["parameters"].get("properties", {})
        for prop_name, schema in props.items():
            if "type" in schema:
                assert schema["type"] in valid_types, (
                    f"Tool '{fn['name']}' property '{prop_name}' "
                    f"has invalid type '{schema['type']}'"
                )

    @pytest.mark.parametrize("tool", TOOLS, ids=lambda t: t["function"]["name"])
    def test_array_properties_have_items(self, tool):
        fn = tool["function"]
        props = fn["parameters"].get("properties", {})
        for prop_name, schema in props.items():
            if schema.get("type") == "array":
                assert "items" in schema, (
                    f"Tool '{fn['name']}' array property '{prop_name}' "
                    f"must define 'items'"
                )

    def test_no_duplicate_tool_names(self):
        names = [t["function"]["name"] for t in TOOLS]
        assert len(names) == len(set(names)), \
            f"Duplicate tool names found: {[n for n in names if names.count(n) > 1]}"

    def test_tool_names_are_snake_case(self):
        for tool in TOOLS:
            name = tool["function"]["name"]
            assert re.match(r"^[a-z][a-z0-9_]*$", name), \
                f"Tool name '{name}' is not snake_case"

    def test_all_required_tools_present(self):
        """The eight tools documented in AGENTS.md must all be present."""
        expected = {
            "create_event",
            "get_event",
            "list_events",
            "update_event",
            "delete_event",
            "batch_upsert",
            "clear_all_events",
        }
        actual = {t["function"]["name"] for t in TOOLS}
        missing = expected - actual
        assert not missing, f"Missing required tools: {missing}"
