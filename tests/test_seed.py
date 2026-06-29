"""Tests for POST /seed and DELETE /events (clear all)."""

from datetime import datetime, timedelta


def test_clear_returns_zero_when_empty(client):
    r = client.delete("/events")
    assert r.status_code == 200
    assert r.json() == {"deleted": 0}


def test_clear_returns_count(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    for i in range(3):
        client.post(
            "/events",
            json={"title": "ev", "start": (base + timedelta(days=i)).isoformat(), "end": (base + timedelta(days=i, hours=1)).isoformat()},
        )
    r = client.delete("/events")
    assert r.json()["deleted"] == 3
    assert client.get("/events").json() == []


def test_seed_inserts_dataset(client):
    r = client.post("/seed")
    assert r.status_code == 200
    assert len(r.json()) >= 1
    assert len(client.get("/events").json()) == len(r.json())


def test_seed_replace_clears_existing(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    client.post(
        "/events",
        json={"title": "preexisting", "start": base.isoformat(), "end": (base + timedelta(hours=1)).isoformat()},
    )
    r = client.post("/seed?replace=true")
    titles = [e["title"] for e in r.json()]
    assert "preexisting" not in titles


def test_seed_without_replace_is_idempotent(client):
    # All seed events have fixed IDs, so seeding without replace upserts the
    # same set rather than appending duplicates.
    client.post("/seed")
    before = len(client.get("/events").json())
    r = client.post("/seed?replace=false")
    assert r.status_code == 200
    after = len(client.get("/events").json())
    assert after == before


def test_seed_is_deterministic_across_calls(client):
    a = client.post("/seed?replace=true").json()
    b = client.post("/seed?replace=true").json()
    # Fixed IDs should match between two seeds.
    assert {e["id"] for e in a} == {e["id"] for e in b}


def test_seed_includes_anchored_sleep_block_near_today(client):
    from mock_calendar_api.tz import NY

    r = client.post("/seed?replace=true").json()
    today = datetime.now(NY).date()
    # At least one event starts today or within a day of today.
    starts = [datetime.fromisoformat(e["start"]).astimezone(NY).date() for e in r]
    assert any(abs((d - today).days) <= 1 for d in starts)
