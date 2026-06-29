"""Tests for timezone handling (America/New_York, DST-aware)."""

from datetime import datetime, timedelta, timezone


def test_summer_event_returns_edt_offset(client):
    # July -> EDT (UTC-04:00).
    r = client.post(
        "/events",
        json={
            "title": "summer",
            "start": "2026-07-04T10:00:00",
            "end": "2026-07-04T11:00:00",
        },
    )
    assert r.json()["start"].endswith("-04:00")
    assert r.json()["end"].endswith("-04:00")


def test_winter_event_returns_est_offset(client):
    # January -> EST (UTC-05:00).
    r = client.post(
        "/events",
        json={
            "title": "winter",
            "start": "2026-01-04T10:00:00",
            "end": "2026-01-04T11:00:00",
        },
    )
    assert r.json()["start"].endswith("-05:00")
    assert r.json()["end"].endswith("-05:00")


def test_utc_aware_input_is_converted_to_new_york(client):
    # 2026-07-04T16:00:00Z == 12:00 EDT.
    r = client.post(
        "/events",
        json={
            "title": "utc",
            "start": "2026-07-04T16:00:00+00:00",
            "end": "2026-07-04T17:00:00+00:00",
        },
    )
    body = r.json()
    assert body["start"] == "2026-07-04T12:00:00-04:00"
    assert body["end"] == "2026-07-04T13:00:00-04:00"


def test_aware_input_persisted_and_read_back_consistently(client):
    r = client.post(
        "/events",
        json={
            "title": "utc",
            "start": "2026-07-04T16:00:00+00:00",
            "end": "2026-07-04T17:00:00+00:00",
        },
    )
    eid = r.json()["id"]
    got = client.get(f"/events/{eid}").json()
    assert got["start"] == "2026-07-04T12:00:00-04:00"


def test_range_query_with_utc_window_matches_local_stored_events(client):
    # Store an event at NY 12:00 (== 16:00 UTC) in July.
    created = client.post(
        "/events",
        json={
            "title": "noon",
            "start": "2026-07-04T12:00:00",
            "end": "2026-07-04T13:00:00",
        },
    ).json()
    # Query with a UTC window that covers 16:00-17:00 UTC.
    r = client.get(
        "/events",
        params={"start": "2026-07-04T15:00:00+00:00", "end": "2026-07-04T17:00:00+00:00"},
    )
    assert any(e["id"] == created["id"] for e in r.json())


def test_overnight_event_across_dst_boundary_offset_changes(client):
    # The DST "fall back" transition in 2026: Nov 1 at 02:00 EDT -> 01:00 EST.
    # An event from 00:30 to 03:00 local crosses the boundary, so the start
    # and end carry different offsets (-04:00 vs -05:00).
    r = client.post(
        "/events",
        json={
            "title": "dst-cross",
            "start": "2026-11-01T00:30:00",
            "end": "2026-11-01T03:00:00",
        },
    )
    body = r.json()
    assert body["start"].endswith("-04:00")
    assert body["end"].endswith("-05:00")
