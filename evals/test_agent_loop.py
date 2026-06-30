"""
Layer 2 — Agent loop behaviour tests.

Uses FakeLLMClient to drive agent.main._run_turn() through scripted
conversation sequences without any real LLM calls or network I/O.

The dispatch() function is also patched to a no-op HTTP layer so tests are
fully self-contained.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from agent.main import _run_turn
from evals.fake_llm import (
    FakeLLMClient,
    MultiToolCallStep,
    TextStep,
    ToolCallSpec,
    ToolCallStep,
)

# ---------------------------------------------------------------------------
# Shared dispatch stub: always returns a sensible JSON payload.
# ---------------------------------------------------------------------------

_STUB_EVENT = json.dumps(
    {
        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "title": "Stub event",
        "start": "2026-07-05T10:00:00-04:00",
        "end": "2026-07-05T11:00:00-04:00",
        "description": None,
        "location": None,
        "metadata_": None,
    }
)

_STUB_LIST = json.dumps(
    [
        {
            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "title": "Stub event B",
            "start": "2026-07-05T14:00:00-04:00",
            "end": "2026-07-05T15:00:00-04:00",
            "description": None,
            "location": None,
            "metadata_": None,
        }
    ]
)


def _stub_dispatch(tool_name: str, args: dict) -> str:  # noqa: ARG001
    if tool_name == "list_events":
        return _STUB_LIST
    return _STUB_EVENT


# ── Happy-path scenarios ──────────────────────────────────────────────────────


class TestSingleToolCallThenReply:
    """LLM calls one tool then provides a final text answer."""

    def test_returns_final_text(self):
        client = FakeLLMClient(
            [
                ToolCallStep(
                    "create_event",
                    {
                        "title": "Dentist",
                        "start": "2026-07-05T14:00:00",
                        "end": "2026-07-05T15:00:00",
                    },
                ),
                TextStep("I've added your dentist appointment at 2 PM."),
            ]
        )
        messages = [{"role": "user", "content": "Add a dentist appointment at 2pm"}]
        with patch("agent.main.dispatch", side_effect=_stub_dispatch):
            reply = _run_turn(client, messages)
        assert reply == "I've added your dentist appointment at 2 PM."

    def test_llm_is_called_twice(self):
        client = FakeLLMClient(
            [
                ToolCallStep("list_events", {}),
                TextStep("You have one event this week."),
            ]
        )
        messages = [{"role": "user", "content": "What's on my calendar?"}]
        with patch("agent.main.dispatch", side_effect=_stub_dispatch):
            _run_turn(client, messages)
        assert client.call_count == 2

    def test_tool_result_appended_to_messages(self):
        client = FakeLLMClient(
            [
                ToolCallStep(
                    "get_event", {"event_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}
                ),
                TextStep("Here is your event."),
            ]
        )
        messages: list[dict] = [{"role": "user", "content": "Show me event details"}]
        with patch("agent.main.dispatch", side_effect=_stub_dispatch):
            _run_turn(client, messages)
        # messages should now contain: user, assistant (tool_call), tool result, assistant (text)
        roles = [m["role"] for m in messages]
        assert "tool" in roles

    def test_all_steps_consumed(self):
        client = FakeLLMClient(
            [
                ToolCallStep("delete_event", {"event_id": "uuid-del"}),
                TextStep("Deleted."),
            ]
        )
        messages = [{"role": "user", "content": "Delete that event"}]
        with patch("agent.main.dispatch", side_effect=_stub_dispatch):
            _run_turn(client, messages)
        assert client.was_exhausted()


class TestDirectTextReply:
    """LLM answers immediately with no tool calls."""

    def test_single_llm_call(self):
        client = FakeLLMClient([TextStep("Hello! How can I help?")])
        messages = [{"role": "user", "content": "Hi"}]
        with patch("agent.main.dispatch", side_effect=_stub_dispatch):
            reply = _run_turn(client, messages)
        assert reply == "Hello! How can I help?"
        assert client.call_count == 1

    def test_messages_list_gets_assistant_entry(self):
        client = FakeLLMClient([TextStep("Sure thing.")])
        messages: list[dict] = [{"role": "user", "content": "OK"}]
        with patch("agent.main.dispatch", side_effect=_stub_dispatch):
            _run_turn(client, messages)
        # System + user + assistant
        assert messages[-1]["role"] == "assistant"

    def test_empty_content_returns_empty_string(self):
        """Edge case: model returns None content with no tool calls."""
        client = FakeLLMClient([TextStep("")])
        messages = [{"role": "user", "content": "..."}]
        with patch("agent.main.dispatch", side_effect=_stub_dispatch):
            reply = _run_turn(client, messages)
        assert reply == ""


class TestMultiStepChain:
    """LLM makes several sequential tool calls before replying."""

    def test_list_then_create_then_reply(self):
        """A two-tool chain: read calendar, then create an event, then reply."""
        client = FakeLLMClient(
            [
                ToolCallStep("list_events", {"start": "2026-07-05T00:00:00"}),
                ToolCallStep(
                    "create_event",
                    {
                        "title": "Morning run",
                        "start": "2026-07-05T07:00:00",
                        "end": "2026-07-05T08:00:00",
                    },
                ),
                TextStep("I've checked your calendar and added a morning run at 7 AM."),
            ]
        )
        messages = [{"role": "user", "content": "Add a morning run tomorrow"}]
        with patch("agent.main.dispatch", side_effect=_stub_dispatch):
            reply = _run_turn(client, messages)
        assert "morning run" in reply.lower()
        assert client.call_count == 3

    def test_three_tool_calls_before_reply(self):
        client = FakeLLMClient(
            [
                ToolCallStep("list_events", {}),
                ToolCallStep(
                    "get_event", {"event_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"}
                ),
                ToolCallStep(
                    "update_event",
                    {
                        "event_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "title": "Renamed",
                    },
                ),
                TextStep("Done — updated the event title."),
            ]
        )
        messages = [{"role": "user", "content": "Rename the 2pm event"}]
        with patch("agent.main.dispatch", side_effect=_stub_dispatch):
            reply = _run_turn(client, messages)
        assert reply == "Done — updated the event title."
        assert client.call_count == 4

    def test_tool_call_ids_forwarded_correctly(self):
        """tool_call_id in the tool result message must match the call's id."""
        client = FakeLLMClient(
            [
                ToolCallStep(
                    "get_event", {"event_id": "uuid-x"}, call_id="tc_unique_99"
                ),
                TextStep("Here it is."),
            ]
        )
        messages: list[dict] = [{"role": "user", "content": "Get event"}]
        with patch("agent.main.dispatch", side_effect=_stub_dispatch):
            _run_turn(client, messages)
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert tool_msgs, "Expected at least one tool result message"
        assert tool_msgs[0]["tool_call_id"] == "tc_unique_99"


class TestMultipleParallelToolCalls:
    """LLM emits two tool calls in a single response turn."""

    def test_both_tool_calls_dispatched(self):
        call_log: list[str] = []

        def _tracking_dispatch(name: str, args: dict) -> str:
            call_log.append(name)
            return _stub_dispatch(name, args)

        client = FakeLLMClient(
            [
                MultiToolCallStep(
                    [
                        ToolCallSpec("list_events", {}, call_id="tc_1"),
                        ToolCallSpec(
                            "get_event", {"event_id": "uuid-x"}, call_id="tc_2"
                        ),
                    ]
                ),
                TextStep("Fetched both."),
            ]
        )
        messages = [{"role": "user", "content": "List events and fetch the first"}]
        with patch("agent.main.dispatch", side_effect=_tracking_dispatch):
            _run_turn(client, messages)
        assert "list_events" in call_log
        assert "get_event" in call_log

    def test_two_tool_results_appended(self):
        client = FakeLLMClient(
            [
                MultiToolCallStep(
                    [
                        ToolCallSpec("list_events", {}, call_id="tc_a"),
                        ToolCallSpec(
                            "list_events",
                            {"start": "2026-08-01T00:00:00"},
                            call_id="tc_b",
                        ),
                    ]
                ),
                TextStep("Done."),
            ]
        )
        messages: list[dict] = [{"role": "user", "content": "Query"}]
        with patch("agent.main.dispatch", side_effect=_stub_dispatch):
            _run_turn(client, messages)
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 2


class TestDispatchErrorPropagation:
    """dispatch() returning an error JSON should not crash the loop."""

    def test_error_json_forwarded_as_tool_result(self):
        error_payload = json.dumps({"error": "HTTP 404", "detail": "Not found"})

        def _error_dispatch(name: str, args: dict) -> str:  # noqa: ARG001
            return error_payload

        client = FakeLLMClient(
            [
                ToolCallStep("get_event", {"event_id": "nonexistent"}),
                TextStep("Sorry, that event doesn't exist."),
            ]
        )
        messages = [{"role": "user", "content": "Get that event"}]
        with patch("agent.main.dispatch", side_effect=_error_dispatch):
            reply = _run_turn(client, messages)
        # Agent should still return the final text response.
        assert "Sorry" in reply or reply  # graceful degradation
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert json.loads(tool_msgs[0]["content"])["error"] == "HTTP 404"


# ── Conversation history hygiene ──────────────────────────────────────────────


class TestConversationHistory:
    """Messages accumulate correctly so multi-turn context is preserved."""

    def test_messages_grow_monotonically(self):
        """Each tool call + result + final reply must all be appended."""
        client = FakeLLMClient(
            [
                ToolCallStep("list_events", {}),
                TextStep("Two events."),
            ]
        )
        messages: list[dict] = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What's on today?"},
        ]
        initial_len = len(messages)
        with patch("agent.main.dispatch", side_effect=_stub_dispatch):
            _run_turn(client, messages)
        # Expect: assistant (tool call) + tool result + assistant (text)
        assert len(messages) == initial_len + 3

    def test_second_turn_sees_previous_history(self):
        """The second LLM call must receive the entire accumulated message list."""
        client = FakeLLMClient(
            [
                ToolCallStep("list_events", {}),
                TextStep("Done."),
            ]
        )
        messages: list[dict] = [{"role": "user", "content": "Show me events"}]
        with patch("agent.main.dispatch", side_effect=_stub_dispatch):
            _run_turn(client, messages)
        # The second call (for the final text) should have received all messages
        second_call_messages = client.calls[1]["messages"]
        roles = [m["role"] for m in second_call_messages]
        assert "tool" in roles, (
            "Second LLM call must include the tool result in history"
        )
