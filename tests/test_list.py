"""Tests for GET /events (list / range query)."""

from datetime import datetime, timedelta


def _create(client, start, end, **extra):
    payload = {"title": "ev", "start": start.isoformat(), "end": end.isoformat()}
    payload.update(extra)
    return client.post("/events", json=payload).json()


def test_list_empty_when_no_events(client):
    r = client.get("/events")
    assert r.status_code == 200
    assert r.json() == []


def test_list_returns_all_events(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    _create(client, base, base + timedelta(hours=1))
    _create(client, base + timedelta(days=1), base + timedelta(days=1, hours=1))
    r = client.get("/events")
    assert len(r.json()) == 2


def test_list_ordered_by_start(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    later = _create(client, base + timedelta(days=2), base + timedelta(days=2, hours=1))
    earlier = _create(client, base, base + timedelta(hours=1))
    r = client.get("/events")
    ids = [e["id"] for e in r.json()]
    assert ids == [earlier["id"], later["id"]]


def test_range_includes_overlapping_events(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    inside = _create(client, base + timedelta(hours=1), base + timedelta(hours=2))
    # Fully before the window.
    _create(client, base - timedelta(days=1, hours=1), base - timedelta(days=1))
    # Fully after the window.
    _create(client, base + timedelta(days=5), base + timedelta(days=5, hours=1))
    r = client.get(
        "/events",
        params={"start": base.isoformat(), "end": (base + timedelta(hours=3)).isoformat()},
    )
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == inside["id"]


def test_range_includes_event_starting_at_window_start(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    ev = _create(client, base, base + timedelta(hours=1))
    r = client.get(
        "/events",
        params={"start": base.isoformat(), "end": (base + timedelta(hours=1)).isoformat()},
    )
    assert any(e["id"] == ev["id"] for e in r.json())


def test_range_excludes_event_ending_exactly_at_window_start(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    _create(client, base - timedelta(hours=1), base)
    r = client.get(
        "/events",
        params={"start": base.isoformat(), "end": (base + timedelta(hours=1)).isoformat()},
    )
    assert r.json() == []


def test_range_excludes_event_starting_exactly_at_window_end(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    _create(client, base + timedelta(hours=1), base + timedelta(hours=2))
    r = client.get(
        "/events",
        params={"start": base.isoformat(), "end": (base + timedelta(hours=1)).isoformat()},
    )
    assert r.json() == []


def test_range_with_only_start(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    after = _create(client, base + timedelta(hours=1), base + timedelta(hours=2))
    # Ends before start filter -> excluded.
    _create(client, base - timedelta(days=1, hours=1), base - timedelta(days=1))
    r = client.get("/events", params={"start": base.isoformat()})
    ids = [e["id"] for e in r.json()]
    assert ids == [after["id"]]


def test_range_with_only_end(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    before = _create(client, base - timedelta(hours=1), base)
    # Starts after end filter -> excluded.
    _create(client, base + timedelta(days=2), base + timedelta(days=2, hours=1))
    r = client.get("/events", params={"end": base.isoformat()})
    ids = [e["id"] for e in r.json()]
    assert ids == [before["id"]]


def test_range_rejects_inverted_window(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    r = client.get(
        "/events",
        params={
            "start": (base + timedelta(hours=1)).isoformat(),
            "end": base.isoformat(),
        },
    )
    assert r.status_code == 400


def test_range_handles_overnight_event(client):
    base = datetime(2026, 7, 4, 23, 0, 0)
    overnight = _create(client, base, base + timedelta(hours=8))
    # Window fully inside the overnight event.
    r = client.get(
        "/events",
        params={
            "start": (base + timedelta(hours=2)).isoformat(),
            "end": (base + timedelta(hours=3)).isoformat(),
        },
    )
    assert [e["id"] for e in r.json()] == [overnight["id"]]
