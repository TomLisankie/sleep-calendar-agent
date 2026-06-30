"""
Scenario definitions for Layer 3 (oracle-based) and Layer 4 (LLM-as-judge)
eval tests.

Each EvalScenario describes:
  - a starting calendar state  (seed=True or empty)
  - a single user utterance    (user_message)
  - an oracle callable         (receives the final event list + agent reply)
  - metadata tags              (for filtering / reporting)

Oracles return True (pass) or False (fail).  They are deliberately lenient
where the LLM has genuine discretion (e.g. exact wording), and strict only
where correctness is unambiguous (e.g. an event must/must not exist).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from mock_calendar_api.tz import NY

# ── Shared date anchors (New York local, relative to today) ──────────────────


def _today() -> datetime:
    now = datetime.now(NY)
    return datetime(now.year, now.month, now.day, tzinfo=NY)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ── Oracle type ───────────────────────────────────────────────────────────────

# Signature: (events: list[dict], reply: str) -> bool
Oracle = Callable[[list[dict], str], bool]


# ── Helper predicates ─────────────────────────────────────────────────────────


def _event_with_title(events: list[dict], fragment: str) -> bool:
    return any(fragment.lower() in e["title"].lower() for e in events)


def _event_count(events: list[dict], n: int) -> bool:
    return len(events) == n


def _reply_mentions(reply: str, *terms: str) -> bool:
    lower = reply.lower()
    return any(t.lower() in lower for t in terms)


def _no_event_overlaps_window(
    events: list[dict],
    window_start: datetime,
    window_end: datetime,
) -> bool:
    """True when *no* event overlaps [window_start, window_end)."""
    for e in events:

        def _parse(s: str) -> datetime:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=NY)
            return dt.astimezone(NY)

        es = _parse(e["start"])
        ee = _parse(e["end"])
        if es < window_end and ee > window_start:
            return False
    return True


def _sleep_window_tonight() -> tuple[datetime, datetime]:
    """Wind-down start (11 PM) → wake-time tomorrow (08:15)."""
    today = _today()
    ws = today + timedelta(hours=23)  # 11:00 PM tonight
    we = today + timedelta(days=1, hours=8, minutes=15)  # 08:15 AM tomorrow
    return ws, we


# ── Scenario dataclass ────────────────────────────────────────────────────────


@dataclass
class EvalScenario:
    name: str
    user_message: str
    oracle: Oracle
    seed: bool = False  # call POST /seed before running?
    tags: list[str] = field(default_factory=list)
    description: str = ""


# ── Scenario registry ─────────────────────────────────────────────────────────


def _tomorrow_9am() -> str:
    return _iso(_today() + timedelta(days=1, hours=9))


def _tomorrow_10am() -> str:
    return _iso(_today() + timedelta(days=1, hours=10))


SCENARIOS: list[EvalScenario] = [
    # ── Create ────────────────────────────────────────────────────────────────
    EvalScenario(
        name="create_simple_event",
        seed=False,
        user_message=(
            f"Add a dentist appointment on {(_today() + timedelta(days=1)).strftime('%A %B %-d')} "
            "at 9am for 1 hour."
        ),
        oracle=lambda events, reply: _event_with_title(events, "dentist"),
        tags=["create"],
        description="Agent should create a dentist event at 9 AM tomorrow.",
    ),
    EvalScenario(
        name="create_event_with_location",
        seed=False,
        user_message=(
            f"Schedule a team lunch at The Bistro on "
            f"{(_today() + timedelta(days=2)).strftime('%A %B %-d')} from noon to 1pm."
        ),
        oracle=lambda events, reply: (
            _event_with_title(events, "lunch") or _event_with_title(events, "bistro")
        ),
        tags=["create"],
        description="Agent should create a lunch event; location is optional but nice.",
    ),
    EvalScenario(
        name="create_multiple_events_batch",
        seed=False,
        user_message=(
            "Add these two events for tomorrow: "
            "a morning run from 7am to 8am, and a grocery trip from 10am to 11am."
        ),
        oracle=lambda events, reply: (
            _event_with_title(events, "run") and _event_with_title(events, "grocer")
        ),
        tags=["create", "batch"],
        description="Agent should create both events (either via batch or two separate calls).",
    ),
    # ── Read ──────────────────────────────────────────────────────────────────
    EvalScenario(
        name="list_events_today",
        seed=True,
        user_message="What's on my calendar for today?",
        oracle=lambda events, reply: (
            # The reply should mention at least something from the seeded data.
            _reply_mentions(reply, "nap", "sleep", "wind", "event", "today", "schedule")
        ),
        tags=["read"],
        description="Agent should read today's events and summarise them.",
    ),
    EvalScenario(
        name="get_existing_sleep_event",
        seed=True,
        user_message="Tell me about my upcoming sleep block.",
        oracle=lambda events, reply: _reply_mentions(
            reply, "sleep", "night", "10", "22", "pm"
        ),
        tags=["read", "sleep"],
        description="Agent should describe the seeded tonight's sleep event.",
    ),
    # ── Update ────────────────────────────────────────────────────────────────
    EvalScenario(
        name="reschedule_nap",
        seed=True,
        user_message="Move my afternoon nap 30 minutes earlier.",
        oracle=lambda events, reply: (
            # Nap should still exist, agent confirms the move.
            _event_with_title(events, "nap")
            and _reply_mentions(
                reply, "nap", "moved", "changed", "rescheduled", "updated", "earlier"
            )
        ),
        tags=["update"],
        description="Agent should patch the nap's start/end 30 minutes earlier.",
    ),
    EvalScenario(
        name="rename_event",
        seed=True,
        user_message="Rename the afternoon nap to 'Power nap'.",
        oracle=lambda events, reply: any(
            "power nap" in e["title"].lower() for e in events
        ),
        tags=["update"],
        description="Agent should patch the nap's title.",
    ),
    # ── Delete ────────────────────────────────────────────────────────────────
    EvalScenario(
        name="delete_nap",
        seed=True,
        user_message="Cancel my afternoon nap.",
        oracle=lambda events, reply: not _event_with_title(events, "nap"),
        tags=["delete"],
        description="Agent should delete the seeded nap event.",
    ),
    # ── Sleep protection ──────────────────────────────────────────────────────
    EvalScenario(
        name="sleep_conflict_warning_direct",
        seed=True,
        user_message="Add a party from midnight to 2am tonight.",
        oracle=lambda events, reply: (
            # Either the agent refuses (no new non-sleep event in the window)
            # or it warns the user about the conflict.
            _reply_mentions(
                reply,
                "sleep",
                "conflict",
                "wind-down",
                "wind down",
                "protect",
                "bedtime",
                "encroach",
                "overlap",
                "inviolable",
            )
        ),
        tags=["sleep-protection", "conflict"],
        description="Agent must warn about a direct midnight–2am conflict.",
    ),
    EvalScenario(
        name="sleep_conflict_no_new_event_in_window",
        seed=True,
        user_message="Schedule a late-night movie from 11pm to 1am tonight.",
        oracle=lambda events, reply: (
            # The added event, if any, must not land in the protected sleep window
            # OR the reply explicitly warns the user.
            (
                lambda ws, we: (
                    _no_event_overlaps_window(
                        [e for e in events if "movie" in e["title"].lower()], ws, we
                    )
                    or _reply_mentions(
                        reply,
                        "sleep",
                        "conflict",
                        "wind-down",
                        "wind down",
                        "bedtime",
                        "protect",
                        "overlap",
                    )
                )
            )(*_sleep_window_tonight())
        ),
        tags=["sleep-protection", "conflict"],
        description=(
            "Agent must not silently schedule a movie that overlaps the sleep/wind-down window."
        ),
    ),
    EvalScenario(
        name="sleep_protection_does_not_block_safe_event",
        seed=True,
        user_message="Add a breakfast meeting at 9am tomorrow.",
        oracle=lambda events, reply: (
            _event_with_title(events, "breakfast")
            or _event_with_title(events, "meeting")
        ),
        tags=["sleep-protection", "create"],
        description="A safe daytime event should be created without conflict warnings.",
    ),
    EvalScenario(
        name="wind_down_conflict_warning",
        seed=True,
        user_message="Book a 2-hour yoga class starting at 11pm tonight.",
        oracle=lambda events, reply: (
            # 11pm is inside the 90-min wind-down window (which starts at 11pm);
            # the agent should warn.
            _reply_mentions(
                reply,
                "wind",
                "sleep",
                "conflict",
                "bedtime",
                "protect",
                "routine",
                "relax",
                "overlap",
            )
        ),
        tags=["sleep-protection", "wind-down", "conflict"],
        description="Agent must warn when a request conflicts with wind-down time.",
    ),
    # ── Clear / reset ─────────────────────────────────────────────────────────
    EvalScenario(
        name="clear_calendar",
        seed=True,
        user_message="Clear my entire calendar — remove all events.",
        oracle=lambda events, reply: len(events) == 0,
        tags=["delete", "clear"],
        description="Agent should call clear_all_events and confirm.",
    ),
]


# ── Convenience index ─────────────────────────────────────────────────────────

SCENARIOS_BY_TAG: dict[str, list[EvalScenario]] = {}
for _s in SCENARIOS:
    for _tag in _s.tags:
        SCENARIOS_BY_TAG.setdefault(_tag, []).append(_s)
