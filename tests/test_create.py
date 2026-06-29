"""Tests for POST /events (create)."""

from datetime import datetime, timedelta
from uuid import uuid4


def test_create_returns_201(client, make_event):
    r = client.post("/events", json=make_event())
    assert r.status_code == 201


def test_create_returns_full_event(client, make_event):
    payload = make_event(
        title="Sleep",
        description="Night sleep",
        location="Bed",
        metadata_={"quality": 0.9},
    )
    r = client.post("/events", json=payload)
    body = r.json()
    assert body["title"] == "Sleep"
    assert body["description"] == "Night sleep"
    assert body["location"] == "Bed"
    assert body["metadata_"] == {"quality": 0.9}
    assert "id" in body and body["id"]
    assert body["created_at"] is not None
    assert body["updated_at"] is not None


def test_create_generates_uuid_id(client, make_event):
    from uuid import UUID

    r = client.post("/events", json=make_event())
    # Should parse as a UUID.
    UUID(r.json()["id"])


def test_create_with_explicit_id_uses_it(client, make_event):
    eid = uuid4()
    r = client.post("/events", json=make_event(id=str(eid)))
    assert r.status_code == 201
    assert r.json()["id"] == str(eid)


def test_create_returns_edt_offset_in_summer(client, make_event):
    # July base time -> EDT (UTC-04:00).
    r = client.post("/events", json=make_event())
    assert r.json()["start"].endswith("-04:00")


def test_create_rejects_end_before_start(client, make_event):
    start = datetime(2026, 7, 4, 10, 0, 0)
    bad = make_event(
        start=start.isoformat(), end=(start - timedelta(hours=1)).isoformat()
    )
    r = client.post("/events", json=bad)
    assert r.status_code == 400


def test_create_rejects_zero_length_event(client, make_event):
    t = datetime(2026, 7, 4, 10, 0, 0).isoformat()
    r = client.post("/events", json=make_event(start=t, end=t))
    assert r.status_code == 400


def test_create_rejects_missing_title(client, make_event):
    payload = make_event()
    del payload["title"]
    r = client.post("/events", json=payload)
    assert r.status_code == 422


def test_create_rejects_empty_title(client, make_event):
    r = client.post("/events", json=make_event(title=""))
    assert r.status_code == 422


def test_create_rejects_missing_start(client, make_event):
    payload = make_event()
    del payload["start"]
    r = client.post("/events", json=payload)
    assert r.status_code == 422


def test_create_optional_fields_default_none(client, make_event):
    r = client.post("/events", json=make_event())
    body = r.json()
    assert body["description"] is None
    assert body["location"] is None
    assert body["metadata_"] is None
