"""System prompt construction for the SleepCal agent."""

from __future__ import annotations

import json
from datetime import datetime

try:
    from .tools import TOOLS  # relative  (when used as a package)
except ImportError:
    from agent.tools import TOOLS  # absolute (when run directly)

try:
    from .tz import NY  # type: ignore[import]
except ImportError:
    try:
        from mock_calendar_api.tz import NY
    except ImportError:
        from zoneinfo import ZoneInfo

        NY = ZoneInfo("America/New_York")


def get_tool_list() -> str:
    """Return a compact, human-readable summary of every available tool."""
    lines: list[str] = []
    for tool in TOOLS:
        fn = tool["function"]
        name = fn["name"]
        desc = fn.get("description", "")
        props = fn.get("parameters", {}).get("properties", {})
        required = fn.get("parameters", {}).get("required", [])

        param_parts: list[str] = []
        for param_name, schema in props.items():
            req_marker = "" if param_name in required else "?"
            ptype = schema.get("type", "any")
            param_parts.append(f"{param_name}{req_marker}: {ptype}")

        params_str = ", ".join(param_parts) if param_parts else ""
        lines.append(f"  • {name}({params_str}) — {desc}")

    return "\n".join(lines)


def _now_ny() -> str:
    """Return the current New York local time as a readable string."""
    return datetime.now(NY).strftime("%A, %B %-d %Y, %-I:%M %p %Z")


def get_system_prompt() -> str:
    """Return the fully rendered system prompt (built lazily so tools are ready)."""
    return f"""You are an assistant who specialises in scheduling a person's day. You operate inside of a calendar agent called SleepCal — a calendar agent who considers sleep to be the most important part of the day. You treat sleep with that weight: protect it, schedule around it, and never let other events encroach on sleep or wind-down time.

The current date and time is: {_now_ny()}

You have the following tools available to you:
{get_tool_list()}

Guidelines:
- Always read the user's sleep preferences (bedtime, waketime, wind_down_mins) before scheduling anything.
- Treat the sleep block and the wind-down block before it as inviolable; warn the user if a request would conflict with either.
- Datetimes are in New York local time (America/New_York). Use ISO-8601 strings (e.g. '2025-07-04T22:30:00').
- When the user asks to view, add, move, or remove events, use the appropriate calendar tool — do not just describe what you would do.
- After every mutating tool call, confirm what changed in plain language.
- Be concise. Do not repeat tool results verbatim unless the user asks.
"""
