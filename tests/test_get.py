"""Tests for GET /events/{id} (get single event)."""

from uuid import uuid4


def test_get_returns_created_event(client, make_event):
    created = client.post("/events", json=make_event(title="Find me")).json()
    r = client.get(f"/events/{created['id']}")
    assert r.status_code == 200
    assert r.json()["title"] == "Find me"


def test_get_404_for_unknown_id(client):
    r = client.get(f"/events/{uuid4()}")
    assert r.status_code == 404


def test_get_422_for_invalid_uuid(client):
    BAD_ID = "not-a-uuid"
    r = client.get(f"/events/{BAD_ID}")
    assert r.status_code == 422
