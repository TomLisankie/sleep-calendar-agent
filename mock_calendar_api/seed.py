"""Seed data and reset helpers."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlmodel import Session, select

from .models import Event, EventCreate, apply_create_fields
from .tz import NY, to_local_naive


def clear_events(session: Session) -> int:
    """Delete all events. Returns the number deleted."""
    events = session.exec(select(Event)).all()
    count = len(events)
    for e in events:
        session.delete(e)
    return count


def seed_events(session: Session, *, replace: bool = True) -> list[Event]:
    """Insert a deterministic set of sleep-related events.

    With replace=True the events table is cleared first so seeding is
    idempotent and gives a known starting state for tests.
    """
    if replace:
        clear_events(session)

    # Build relative to "today at midnight" New York local so the seed is always current.
    now = datetime.now(NY)
    today = datetime(now.year, now.month, now.day, tzinfo=NY)

    def night(day_offset: int, start_hour: int, end_hour: int) -> tuple[datetime, datetime]:
        # A sleep block starting start_hour of day_offset and ending end_hour
        # of the following morning (handles overnight spans).
        start = today + timedelta(days=day_offset, hours=start_hour)
        end = today + timedelta(days=day_offset, hours=end_hour)
        if end <= start:
            end += timedelta(days=1)
        return start, end

    last_night = night(-1, 22, 7)  # yesterday 22:00 -> today 07:00
    tonight = night(0, 22, 7)  # today 22:00 -> tomorrow 07:00

    seed_data = [
        EventCreate(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            title="Sleep (night)",
            start=last_night[0],
            end=last_night[1],
            description="Baseline sleep block",
            metadata_={"quality": 0.82, "source": "seed"},
        ),
        EventCreate(
            id=UUID("22222222-2222-2222-2222-222222222222"),
            title="Nap",
            start=today + timedelta(hours=14),
            end=today + timedelta(hours=14, minutes=30),
            description="Afternoon nap",
            metadata_={"type": "nap", "source": "seed"},
        ),
        EventCreate(
            id=UUID("33333333-3333-3333-3333-333333333333"),
            title="Sleep (night)",
            start=tonight[0],
            end=tonight[1],
            description="Planned sleep block",
            metadata_={"quality": None, "source": "seed"},
        ),
        EventCreate(
            id=uuid4(),
            title="Wind-down",
            start=tonight[0] - timedelta(hours=1),
            end=tonight[0],
            description="Screen-free wind-down routine",
            metadata_={"kind": "routine", "source": "seed"},
        ),
    ]

    created: list[Event] = []
    for data in seed_data:
        event = Event(id=data.id) if data.id is not None else Event()
        apply_create_fields(event, data)
        session.add(event)
        created.append(event)
    return created
