"""Shared pytest fixtures.

Patches the app's database engine to a fresh in-memory SQLite per test for
isolation, so no `calendar.db` file is created and tests don't interfere.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

import mock_calendar_api.db as db
from mock_calendar_api.api import app
from mock_calendar_api.db import init_db


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """A TestClient backed by a fresh in-memory SQLite DB."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    original = db.engine
    db.engine = test_engine
    init_db()
    try:
        # Use as a context manager so startup/shutdown lifecycle runs.
        with TestClient(app) as c:
            yield c
    finally:
        db.engine = original


def _iso(dt: datetime) -> str:
    return dt.isoformat()


@pytest.fixture()
def make_event():
    """Return a helper that builds a valid event-create payload dict.

    By default anchored to a fixed base time so range logic is deterministic.
    """

    base = datetime(2026, 7, 4, 10, 0, 0)  # July -> EDT (UTC-04:00)

    def _build(**overrides) -> dict:
        payload = {
            "title": "Test event",
            "start": _iso(base),
            "end": _iso(base + timedelta(hours=1)),
        }
        payload.update(overrides)
        return payload

    return _build
