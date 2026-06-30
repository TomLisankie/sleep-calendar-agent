"""
Shared pytest fixtures for the evals suite.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

import mock_calendar_api.db as db
from mock_calendar_api.api import app
from mock_calendar_api.db import init_db
from mock_calendar_api.tz import NY


# ── In-memory calendar API client ────────────────────────────────────────────


@pytest.fixture()
def api_client() -> Iterator[TestClient]:
    """
    TestClient backed by a fresh in-memory SQLite DB.

    Identical in structure to the one in ``conftest.py`` but named
    ``api_client`` to avoid collisions when both conftest files are active.

    Layer 3 / 4 scenario tests use this to run the real FastAPI app with zero
    I/O overhead, then query the resulting calendar state directly.
    """
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original = db.engine
    db.engine = test_engine
    init_db()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        db.engine = original


# ── Sleep-window helpers ──────────────────────────────────────────────────────

BEDTIME_HOUR = 0      # 12:30 AM  (next day midnight)
BEDTIME_MIN = 30
WAKETIME_HOUR = 8
WAKETIME_MIN = 15
WIND_DOWN_MINS = 90   # wind-down starts 90 min before bedtime = 11:00 PM

PREFS = {
    "bedtime": "12:30 AM",
    "waketime": "8:15 AM",
    "wind_down_mins": WIND_DOWN_MINS,
}


def sleep_window_for_date(
    date: datetime,
) -> tuple[datetime, datetime]:
    """
    Return (sleep_start, sleep_end) for a night anchored to *date* (NY local).

    sleep_start = date at 12:30 AM  (i.e. 00:30 the following wall-clock day
                  is still "that night's sleep", so we anchor the start at the
                  next midnight + 30 min).
    In practice for the eval oracles we just need a contiguous protected zone;
    we define it as:
        wind_down_start = bedtime - 90 min = 23:00 tonight
        sleep_end       = waketime = 08:15 tomorrow
    """
    today = datetime(date.year, date.month, date.day, tzinfo=NY)
    wind_down_start = today + timedelta(hours=23)          # 23:00 today  (11 PM)
    sleep_end = today + timedelta(days=1,
                                  hours=WAKETIME_HOUR,
                                  minutes=WAKETIME_MIN)    # 08:15 tomorrow
    return wind_down_start, sleep_end


def overlaps_protected_window(
    event_start_iso: str,
    event_end_iso: str,
    *,
    ref: datetime | None = None,
) -> bool:
    """
    Return True when the event [event_start, event_end) overlaps the
    protected sleep + wind-down window for the night of *ref* (defaults to
    today NY).
    """
    from datetime import timezone

    ref = ref or datetime.now(NY)
    ws, we = sleep_window_for_date(ref)

    def _parse(s: str) -> datetime:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=NY)
        return dt.astimezone(NY)

    es = _parse(event_start_iso)
    ee = _parse(event_end_iso)
    # Half-open interval overlap: es < we and ee > ws
    return es < we and ee > ws


# ── Convenience: load all events from the in-memory API ──────────────────────


def all_events(api_client: TestClient) -> list[dict]:
    r = api_client.get("/events")
    r.raise_for_status()
    return r.json()


# ── Marker for live-LLM tests ─────────────────────────────────────────────────

has_api_key = pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set — skipping live LLM tests",
)
