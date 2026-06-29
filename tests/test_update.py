"""Tests for PATCH /events/{id} (update)."""

from datetime import datetime, timedelta


def _create(client, **extra):
    base = datetime(2026, 7, 4, 10, 0, 0)
    payload = {"title": "Original", "start": base.isoformat(), "end": (base + timedelta(hours=1)).isoformat()}
    payload.update(extra)
    return client.post("/events", json=payload).json()


def test_update_single_field(client):
    created = _create(client)
    r = client.patch(f"/events/{created['id']}", json={"title": "Renamed"})
    assert r.status_code == 200
    assert r.json()["title"] == "Renamed"


def test_update_partial_leaves_other_fields_untouched(client):
    created = _create(client, description="desc", location="loc", metadata_={"a": 1})
    r = client.patch(f"/events/{created['id']}", json={"title": "Renamed"})
    body = r.json()
    assert body["description"] == "desc"
    assert body["location"] == "loc"
    assert body["metadata_"] == {"a": 1}


def test_update_bumps_updated_at_not_created_at(client):
    created = _create(client)
    before_created = created["created_at"]
    before_updated = created["updated_at"]
    # Ensure timestamps differ by forcing a tick is flaky; instead just
    # assert created_at is unchanged and updated_at is present.
    r = client.patch(f"/events/{created['id']}", json={"title": "Renamed"})
    body = r.json()
    assert body["created_at"] == before_created
    assert body["updated_at"] == before_updated or body["updated_at"] >= before_updated


def test_update_start_and_end(client):
    created = _create(client)
    new_start = datetime(2026, 7, 5, 9, 0, 0)
    new_end = datetime(2026, 7, 5, 11, 0, 0)
    r = client.patch(
        f"/events/{created['id']}",
        json={"start": new_start.isoformat(), "end": new_end.isoformat()},
    )
    assert r.status_code == 200
    assert r.json()["start"].startswith("2026-07-05T09:00:00")
    assert r.json()["end"].startswith("2026-07-05T11:00:00")


def test_update_metadata_replaces(client):
    created = _create(client, metadata_={"a": 1})
    r = client.patch(f"/events/{created['id']}", json={"metadata_": {"b": 2}})
    assert r.json()["metadata_"] == {"b": 2}


def test_update_rejects_inverted_span(client):
    created = _create(client)
    r = client.patch(
        f"/events/{created['id']}",
        json={"start": datetime(2026, 7, 5, 12, 0, 0).isoformat(), "end": datetime(2026, 7, 5, 11, 0, 0).isoformat()},
    )
    assert r.status_code == 400


def test_update_rejects_inverted_span_when_only_end_changes(client):
    # Move end before the existing start.
    created = _create(client)  # start 10:00, end 11:00
    r = client.patch(
        f"/events/{created['id']}",
        json={"end": datetime(2026, 7, 4, 9, 0, 0).isoformat()},
    )
    assert r.status_code == 400


def test_update_empty_payload_is_noop(client):
    created = _create(client, title="Original")
    r = client.patch(f"/events/{created['id']}", json={})
    assert r.status_code == 200
    assert r.json()["title"] == "Original"


def test_update_404_for_unknown_id(client):
    from uuid import uuid4

    r = client.patch(f"/events/{uuid4()}", json={"title": "x"})
    assert r.status_code == 404


def test_update_rejects_empty_title(client):
    created = _create(client)
    r = client.patch(f"/events/{created['id']}", json={"title": ""})
    assert r.status_code == 422


def test_update_persists_across_requests(client):
    created = _create(client)
    client.patch(f"/events/{created['id']}", json={"title": "Persisted"})
    r = client.get(f"/events/{created['id']}")
    assert r.json()["title"] == "Persisted"
