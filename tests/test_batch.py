"""Tests for POST /events/batch (batch upsert)."""

from datetime import datetime, timedelta


def _ev(start, end, **extra):
    payload = {"title": "ev", "start": start.isoformat(), "end": end.isoformat()}
    payload.update(extra)
    return payload


def test_batch_creates_multiple(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    r = client.post(
        "/events/batch",
        json=[
            _ev(base, base + timedelta(hours=1)),
            _ev(base + timedelta(days=1), base + timedelta(days=1, hours=1)),
        ],
    )
    assert r.status_code == 200
    assert len(r.json()) == 2
    assert len(client.get("/events").json()) == 2


def test_batch_empty_payload_returns_empty(client):
    r = client.post("/events/batch", json=[])
    assert r.status_code == 200
    assert r.json() == []


def test_batch_upserts_existing_id(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    first = client.post("/events", json=_ev(base, base + timedelta(hours=1), title="First")).json()
    r = client.post(
        "/events/batch",
        json=[_ev(base, base + timedelta(hours=1), id=first["id"], title="Second")],
    )
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert len(client.get("/events").json()) == 1
    assert client.get(f"/events/{first['id']}").json()["title"] == "Second"


def test_batch_creates_with_explicit_id_when_absent(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    from uuid import uuid4

    eid = uuid4()
    r = client.post("/events/batch", json=[_ev(base, base + timedelta(hours=1), id=str(eid))])
    assert r.status_code == 200
    assert r.json()[0]["id"] == str(eid)
    assert client.get(f"/events/{eid}").status_code == 200


def test_batch_mixes_create_and_update(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    existing = client.post("/events", json=_ev(base, base + timedelta(hours=1), title="Old")).json()
    r = client.post(
        "/events/batch",
        json=[
            _ev(base, base + timedelta(hours=1), id=existing["id"], title="Updated"),
            _ev(base + timedelta(days=2), base + timedelta(days=2, hours=1), title="New"),
        ],
    )
    assert len(r.json()) == 2
    assert len(client.get("/events").json()) == 2
    assert client.get(f"/events/{existing['id']}").json()["title"] == "Updated"


def test_batch_rejects_bad_span_in_any_item(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    r = client.post(
        "/events/batch",
        json=[
            _ev(base, base + timedelta(hours=1)),
            _ev(base + timedelta(hours=1), base),  # inverted
        ],
    )
    assert r.status_code == 400


def test_batch_is_atomic_on_validation_failure(client):
    # If any item is invalid, none should be persisted.
    base = datetime(2026, 7, 4, 10, 0, 0)
    client.post(
        "/events/batch",
        json=[
            _ev(base, base + timedelta(hours=1)),
            _ev(base + timedelta(hours=1), base),  # inverted
        ],
    )
    assert client.get("/events").json() == []
