"""
Tool schemas (OpenAI function-calling format) and HTTP dispatcher for the
mock Sleep Calendar API.

All datetime strings are ISO-8601 and interpreted as New York local time by
the API (timezone offset is accepted; naive strings are treated as NY local).
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_url() -> str:
    return os.environ.get("CALENDAR_API_URL", "http://127.0.0.1:8000").rstrip("/")


def _get(path: str, params: dict | None = None) -> Any:
    r = httpx.get(f"{_base_url()}{path}", params=params, timeout=10)
    r.raise_for_status()
    if r.status_code == 204 or not r.content:
        return None
    return r.json()


def _post(path: str, body: Any = None, params: dict | None = None) -> Any:
    r = httpx.post(f"{_base_url()}{path}", json=body, params=params, timeout=10)
    r.raise_for_status()
    if r.status_code == 204 or not r.content:
        return None
    return r.json()


def _patch(path: str, body: Any) -> Any:
    r = httpx.patch(f"{_base_url()}{path}", json=body, timeout=10)
    r.raise_for_status()
    return r.json()


def _delete(path: str) -> Any:
    r = httpx.delete(f"{_base_url()}{path}", timeout=10)
    r.raise_for_status()
    if r.status_code == 204 or not r.content:
        return {"status": "deleted"}
    return r.json()


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    # ── create_event ────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": (
                "Create a single calendar event. "
                "Returns the created EventRead object."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Event title (1–255 chars).",
                    },
                    "start": {
                        "type": "string",
                        "description": (
                            "Event start as an ISO-8601 datetime string "
                            "(New York local time, e.g. '2025-07-04T09:00:00')."
                        ),
                    },
                    "end": {
                        "type": "string",
                        "description": (
                            "Event end as an ISO-8601 datetime string "
                            "(New York local time). Must be after start."
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional free-text description (max 4096 chars).",
                    },
                    "location": {
                        "type": "string",
                        "description": "Optional location string (max 255 chars).",
                    },
                    "id": {
                        "type": "string",
                        "description": (
                            "Optional explicit UUID for the event "
                            "(useful for deterministic upserts)."
                        ),
                    },
                    "metadata_": {
                        "type": "object",
                        "description": (
                            "Optional free-form JSON metadata dict "
                            "(e.g. sleep-specific fields like {'type': 'sleep'})."
                        ),
                        "additionalProperties": True,
                    },
                },
                "required": ["title", "start", "end"],
            },
        },
    },
    # ── get_event ────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_event",
            "description": "Retrieve a single calendar event by its UUID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "UUID of the event to retrieve.",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    # ── list_events ──────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "list_events",
            "description": (
                "List calendar events, optionally filtered to those that overlap "
                "the half-open interval [start, end). "
                "Returns a list of EventRead objects ordered by start time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {
                        "type": "string",
                        "description": (
                            "Optional ISO-8601 datetime — only events ending "
                            "after this time are returned."
                        ),
                    },
                    "end": {
                        "type": "string",
                        "description": (
                            "Optional ISO-8601 datetime — only events starting "
                            "before this time are returned."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    # ── update_event ─────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "update_event",
            "description": (
                "Partially update (PATCH) an existing event. "
                "Only the fields you provide are changed. "
                "Returns the updated EventRead object."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "UUID of the event to update.",
                    },
                    "title": {"type": "string", "description": "New title (1–255 chars)."},
                    "start": {
                        "type": "string",
                        "description": "New start as ISO-8601 datetime (NY local).",
                    },
                    "end": {
                        "type": "string",
                        "description": "New end as ISO-8601 datetime (NY local). Must be after start.",
                    },
                    "description": {"type": "string", "description": "New description."},
                    "location": {"type": "string", "description": "New location."},
                    "metadata_": {
                        "type": "object",
                        "description": "New metadata dict (replaces existing).",
                        "additionalProperties": True,
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    # ── delete_event ─────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "delete_event",
            "description": "Delete a single calendar event by its UUID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "UUID of the event to delete.",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
    # ── batch_upsert ─────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "batch_upsert",
            "description": (
                "Create or update multiple events in one call. "
                "Each item with an 'id' updates the existing event if found, "
                "otherwise creates one with that ID. "
                "Items without 'id' always create new events. "
                "Returns a list of EventRead objects."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "events": {
                        "type": "array",
                        "description": "List of event payloads — same shape as create_event arguments.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "start": {"type": "string"},
                                "end": {"type": "string"},
                                "description": {"type": "string"},
                                "location": {"type": "string"},
                                "id": {"type": "string"},
                                "metadata_": {
                                    "type": "object",
                                    "additionalProperties": True,
                                },
                            },
                            "required": ["title", "start", "end"],
                        },
                    },
                },
                "required": ["events"],
            },
        },
    },
    # ── seed_calendar ────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "seed_calendar",
            "description": (
                "Insert the deterministic seed dataset into the calendar. "
                "With replace=true (default) the table is cleared first, "
                "giving a known starting state. "
                "Returns the list of seeded EventRead objects."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "replace": {
                        "type": "boolean",
                        "description": (
                            "If true (default), clear all existing events before seeding."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    # ── clear_all_events ─────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "clear_all_events",
            "description": (
                "Delete every event in the calendar. "
                "Returns {'deleted': <count>}."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def dispatch(tool_name: str, arguments: dict) -> str:
    """Call the appropriate calendar API endpoint and return the result as JSON string."""
    try:
        result = _dispatch_inner(tool_name, arguments)
    except httpx.HTTPStatusError as exc:
        result = {
            "error": f"HTTP {exc.response.status_code}",
            "detail": exc.response.text,
        }
    return json.dumps(result, default=str)


def _dispatch_inner(tool_name: str, args: dict) -> Any:
    if tool_name == "create_event":
        return _post("/events", body=args)

    if tool_name == "get_event":
        return _get(f"/events/{args['event_id']}")

    if tool_name == "list_events":
        params: dict = {}
        if "start" in args:
            params["start"] = args["start"]
        if "end" in args:
            params["end"] = args["end"]
        return _get("/events", params=params or None)

    if tool_name == "update_event":
        event_id = args.pop("event_id")
        return _patch(f"/events/{event_id}", body=args)

    if tool_name == "delete_event":
        return _delete(f"/events/{args['event_id']}")

    if tool_name == "batch_upsert":
        return _post("/events/batch", body=args["events"])

    if tool_name == "seed_calendar":
        params = {}
        if "replace" in args:
            # FastAPI expects a query param, not a body
            params["replace"] = str(args["replace"]).lower()
        return _post("/seed", params=params or None)

    if tool_name == "clear_all_events":
        return _delete("/events")

    return {"error": f"Unknown tool: {tool_name!r}"}
