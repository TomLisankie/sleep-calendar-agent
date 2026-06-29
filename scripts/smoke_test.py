"""End-to-end smoke test of the calendar API using an in-memory SQLite DB."""

import os
import sys
import tempfile
import uuid as uuidlib
from datetime import datetime, timedelta

# Ensure the project package is importable when run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Point the DB at a fresh temp file before importing the app.
_dir = tempfile.mkdtemp()
os.environ["SQLITE_PATH"] = os.path.join(_dir, "test.db")

# We need to re-point the module-level engine; do it via a config tweak.
import mock_calendar_api.db as db  # noqa: E402
from sqlmodel import create_engine  # noqa: E402

db.engine = create_engine(
    "sqlite:///" + os.environ["SQLITE_PATH"],
    connect_args={"check_same_thread": False},
)

from fastapi.testclient import TestClient  # noqa: E402
from mock_calendar_api import app  # noqa: E402
from mock_calendar_api.db import init_db  # noqa: E402

init_db()
client = TestClient(app)


def iso(dt: datetime) -> str:
    return dt.isoformat()


now = datetime(2026, 6, 29, 8, 0, 0)  # naive -> assumed New York local by API
base = iso(now)

# 1. Seed
r = client.post("/seed?replace=true")
assert r.status_code == 200, r.text
seeded = r.json()
print(f"seed: {len(seeded)} events")

# 2. Get by ID (seeded fixed UUID)
r = client.get("/events/11111111-1111-1111-1111-111111111111")
assert r.status_code == 200, r.text
print("get by id:", r.json()["title"], "start tz:", r.json()["start"][-6:])

# 3. Create
new_id = str(uuidlib.uuid4())
r = client.post(
    "/events",
    json={
        "id": new_id,
        "title": "Deep work",
        "start": iso(now + timedelta(hours=10)),
        "end": iso(now + timedelta(hours=12)),
        "metadata_": {"focus": True},
    },
)
assert r.status_code == 201, r.text
print("create:", r.json()["title"], r.json()["metadata_"])

# 4. Update
r = client.patch(f"/events/{new_id}", json={"title": "Deep work (moved)", "end": iso(now + timedelta(hours=13))})
assert r.status_code == 200, r.text
assert r.json()["title"] == "Deep work (moved)"
print("update:", r.json()["title"], "end tz:", r.json()["end"][-6:])

# 5. Range query
r = client.get("/events", params={"start": iso(now), "end": iso(now + timedelta(hours=24))})
assert r.status_code == 200, r.text
print(f"range query: {len(r.json())} events overlapping today")

# 6. Batch upsert (update existing + create new)
r = client.post(
    "/events/batch",
    json=[
        {"id": new_id, "title": "Deep work", "start": iso(now + timedelta(hours=10)), "end": iso(now + timedelta(hours=12))},
        {"title": "Exercise", "start": iso(now + timedelta(hours=6)), "end": iso(now + timedelta(hours=7))},
    ],
)
assert r.status_code == 200, r.text
print(f"batch upsert: {len(r.json())} results")

# 7. Validation: start >= end should 400
r = client.post(
    "/events",
    json={"title": "bad", "start": iso(now), "end": iso(now)},
)
assert r.status_code == 400, r.text
print("validation ok (400 on bad span)")

# 8. Delete
r = client.delete(f"/events/{new_id}")
assert r.status_code == 204, r.text
print("delete ok")

# 9. 404 after delete
r = client.get(f"/events/{new_id}")
assert r.status_code == 404, r.text
print("404 after delete ok")

# 10. Clear all
r = client.delete("/events")
assert r.status_code == 200, r.text
print("clear:", r.json())

print("\nALL CHECKS PASSED")
