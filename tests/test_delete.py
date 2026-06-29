"""Tests for DELETE /events/{id} (delete single)."""

from datetime import datetime, timedelta
from uuid import uuid4


def _create(client):
    base = datetime(2026, 7, 4, 10, 0, 0)
    payload = {"title": "ev", "start": base.isoformat(), "end": (base + timedelta(hours=1)).isoformat()}
    return client.post("/events", json=payload).json()


def test_delete_returns_204(client):
    created = _create(client)
    r = client.delete(f"/events/{created['id']}")
    assert r.status_code == 204


def test_delete_removes_event(client):
    created = _create(client)
    client.delete(f"/events/{created['id']}")
    assert client.get(f"/events/{created['id']}").status_code == 404


def test_delete_404_for_unknown_id(client):
    r = client.delete(f"/events/{uuid4()}")
    assert r.status_code == 404


def test_delete_only_removes_target(client):
    a = _create(client)
    b = _create(client)
    client.delete(f"/events/{a['id']}")
    assert client.get(f"/events/{a['id']}").status_code == 404
    assert client.get(f"/events/{b['id']}").status_code == 200


def test_delete_twice_second_is_404(client):
    created = _create(client)
    assert client.delete(f"/events/{created['id']}").status_code == 204
    assert client.delete(f"/events/{created['id']}").status_code == 404
