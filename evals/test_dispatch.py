"""
Layer 1a — Tool dispatch routing tests.

Verifies that agent.tools.dispatch() maps every tool name to the correct HTTP
verb + URL + payload, with zero real network calls.  All httpx I/O is
intercepted by a lightweight patch of the private ``_dispatch_inner`` helper
so we can inspect exactly what arguments would have been sent.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from agent.tools import dispatch

# ── Helpers ───────────────────────────────────────────────────────────────────

BASE = "http://127.0.0.1:8000"


def _ok(value: Any = None) -> Any:
    """A dummy "success" return value."""
    return value or {"id": "test-uuid", "title": "ok"}


# We patch the four private HTTP helpers (_get, _post, _patch, _delete) in
# agent.tools so no network socket is opened.  The return value is serialised
# to JSON by dispatch(), so we always pass a JSON-serialisable dict.


# ── create_event ──────────────────────────────────────────────────────────────


class TestCreateEventDispatch:
    def test_posts_to_events(self):
        args = {
            "title": "Doctor",
            "start": "2026-07-05T10:00:00",
            "end": "2026-07-05T11:00:00",
        }
        with patch("agent.tools._post", return_value=_ok()) as mock_post:
            dispatch("create_event", args)
        mock_post.assert_called_once_with("/events", body=args)

    def test_optional_fields_passed_through(self):
        args = {
            "title": "Lab",
            "start": "2026-07-05T10:00:00",
            "end": "2026-07-05T10:30:00",
            "description": "Blood work",
            "location": "Clinic",
            "metadata_": {"type": "medical"},
        }
        with patch("agent.tools._post", return_value=_ok()) as mock_post:
            dispatch("create_event", args)
        _, call_kwargs = mock_post.call_args
        assert call_kwargs["body"]["description"] == "Blood work"
        assert call_kwargs["body"]["location"] == "Clinic"
        assert call_kwargs["body"]["metadata_"] == {"type": "medical"}

    def test_returns_json_string(self):
        with patch("agent.tools._post", return_value={"id": "abc"}):
            result = dispatch("create_event", {"title": "t", "start": "s", "end": "e"})
        data = json.loads(result)
        assert data["id"] == "abc"


# ── get_event ─────────────────────────────────────────────────────────────────


class TestGetEventDispatch:
    def test_gets_by_id(self):
        with patch("agent.tools._get", return_value=_ok()) as mock_get:
            dispatch("get_event", {"event_id": "uuid-123"})
        mock_get.assert_called_once_with("/events/uuid-123")

    def test_wrong_id_still_routed_correctly(self):
        with patch("agent.tools._get", return_value=_ok()) as mock_get:
            dispatch("get_event", {"event_id": "00000000-0000-0000-0000-000000000000"})
        mock_get.assert_called_once_with("/events/00000000-0000-0000-0000-000000000000")


# ── list_events ───────────────────────────────────────────────────────────────


class TestListEventsDispatch:
    def test_no_params(self):
        with patch("agent.tools._get", return_value=[]) as mock_get:
            dispatch("list_events", {})
        mock_get.assert_called_once_with("/events", params=None)

    def test_with_start_only(self):
        with patch("agent.tools._get", return_value=[]) as mock_get:
            dispatch("list_events", {"start": "2026-07-01T00:00:00"})
        _, kw = mock_get.call_args
        assert kw["params"] == {"start": "2026-07-01T00:00:00"}
        assert "end" not in kw["params"]

    def test_with_end_only(self):
        with patch("agent.tools._get", return_value=[]) as mock_get:
            dispatch("list_events", {"end": "2026-07-31T23:59:59"})
        _, kw = mock_get.call_args
        assert kw["params"] == {"end": "2026-07-31T23:59:59"}

    def test_with_start_and_end(self):
        with patch("agent.tools._get", return_value=[]) as mock_get:
            dispatch(
                "list_events",
                {"start": "2026-07-01T00:00:00", "end": "2026-07-07T23:59:59"},
            )
        _, kw = mock_get.call_args
        assert kw["params"]["start"] == "2026-07-01T00:00:00"
        assert kw["params"]["end"] == "2026-07-07T23:59:59"


# ── update_event ──────────────────────────────────────────────────────────────


class TestUpdateEventDispatch:
    def test_patches_correct_url(self):
        with patch("agent.tools._patch", return_value=_ok()) as mock_patch:
            dispatch("update_event", {"event_id": "uuid-456", "title": "Renamed"})
        mock_patch.assert_called_once_with(
            "/events/uuid-456", body={"title": "Renamed"}
        )

    def test_event_id_stripped_from_body(self):
        with patch("agent.tools._patch", return_value=_ok()) as mock_patch:
            dispatch(
                "update_event",
                {"event_id": "uuid-789", "title": "T", "location": "Gym"},
            )
        _, kw = mock_patch.call_args
        assert "event_id" not in kw["body"]
        assert kw["body"]["title"] == "T"
        assert kw["body"]["location"] == "Gym"


# ── delete_event ──────────────────────────────────────────────────────────────


class TestDeleteEventDispatch:
    def test_deletes_by_id(self):
        with patch(
            "agent.tools._delete", return_value={"status": "deleted"}
        ) as mock_del:
            dispatch("delete_event", {"event_id": "uuid-del"})
        mock_del.assert_called_once_with("/events/uuid-del")


# ── batch_upsert ──────────────────────────────────────────────────────────────


class TestBatchUpsertDispatch:
    def test_posts_to_batch_endpoint(self):
        events = [
            {
                "title": "A",
                "start": "2026-07-05T08:00:00",
                "end": "2026-07-05T09:00:00",
            },
            {
                "title": "B",
                "start": "2026-07-05T10:00:00",
                "end": "2026-07-05T11:00:00",
            },
        ]
        with patch("agent.tools._post", return_value=[_ok(), _ok()]) as mock_post:
            dispatch("batch_upsert", {"events": events})
        mock_post.assert_called_once_with("/events/batch", body=events)

    def test_events_list_forwarded_directly(self):
        events = [{"title": "X", "start": "s", "end": "e", "id": "some-uuid"}]
        with patch("agent.tools._post", return_value=[_ok()]) as mock_post:
            dispatch("batch_upsert", {"events": events})
        _, kw = mock_post.call_args
        assert kw["body"] == events


# ── seed_calendar ─────────────────────────────────────────────────────────────


class TestSeedCalendarNotExposed:
    """seed_calendar was removed from agent tools — it's an internal-only endpoint."""

    def test_seed_calendar_returns_unknown_tool_error(self):
        result = dispatch("seed_calendar", {})
        data = json.loads(result)
        assert "error" in data
        assert "seed_calendar" in data["error"]


# ── clear_all_events ──────────────────────────────────────────────────────────


class TestClearAllEventsDispatch:
    def test_deletes_root_events(self):
        with patch("agent.tools._delete", return_value={"deleted": 0}) as mock_del:
            dispatch("clear_all_events", {})
        mock_del.assert_called_once_with("/events")


# ── Error handling ────────────────────────────────────────────────────────────


class TestDispatchErrorHandling:
    def test_unknown_tool_returns_error_json(self):
        result = dispatch("no_such_tool", {})
        data = json.loads(result)
        assert "error" in data
        assert "no_such_tool" in data["error"]

    def test_http_error_returns_error_json(self):
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.text = '{"detail": "validation error"}'
        error = httpx.HTTPStatusError(
            "422", request=MagicMock(), response=mock_response
        )

        with patch("agent.tools._post", side_effect=error):
            result = dispatch("create_event", {"title": "t", "start": "s", "end": "e"})
        data = json.loads(result)
        assert "error" in data
        assert "422" in data["error"]
