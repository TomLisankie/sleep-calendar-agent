"""FastAPI application exposing the mock calendar API."""

from datetime import datetime
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlmodel import Session, select

from .db import init_db
from .models import (
    Event,
    EventCreate,
    EventRead,
    EventUpdate,
    apply_create_fields,
    apply_update_fields,
    to_read,
)
from .seed import clear_events, seed_events
from .tz import attach_local, to_local_naive

app = FastAPI(title="Sleep Calendar API", version="0.1.0")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def session_dep() -> Session:
    from .db import get_session

    with get_session() as s:
        yield s


def _validate_span(start: datetime, end: datetime) -> None:
    if end <= start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"end ({end}) must be after start ({start}).",
        )


def _get_event_or_404(session: Session, event_id: UUID) -> Event:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event {event_id} not found.",
        )
    return event


@app.get("/events", response_model=list[EventRead])
def list_events(
    start: datetime | None = None,
    end: datetime | None = None,
    session: Session = Depends(session_dep),
) -> list[EventRead]:
    """List events, optionally filtered to those overlapping [start, end)."""
    statement = select(Event)
    if start is not None:
        start_n = to_local_naive(start)
        statement = statement.where(Event.end > start_n)
    if end is not None:
        end_n = to_local_naive(end)
        statement = statement.where(Event.start < end_n)
    if start is not None and end is not None:
        _validate_span(start, end)
    statement = statement.order_by(Event.start)
    events = session.exec(statement).all()
    return [to_read(e) for e in events]


@app.post(
    "/events",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_event(payload: EventCreate, session: Session = Depends(session_dep)) -> EventRead:
    _validate_span(payload.start, payload.end)
    event = Event(id=payload.id) if payload.id is not None else Event()
    apply_create_fields(event, payload)
    session.add(event)
    session.commit()
    session.refresh(event)
    return to_read(event)


@app.get("/events/{event_id}", response_model=EventRead)
def get_event(event_id: UUID, session: Session = Depends(session_dep)) -> EventRead:
    event = _get_event_or_404(session, event_id)
    return to_read(event)


@app.patch("/events/{event_id}", response_model=EventRead)
def update_event(
    event_id: UUID,
    payload: EventUpdate,
    session: Session = Depends(session_dep),
) -> EventRead:
    event = _get_event_or_404(session, event_id)
    apply_update_fields(event, payload)
    new_start = payload.start if payload.start is not None else event.start
    new_end = payload.end if payload.end is not None else event.end
    _validate_span(attach_local(new_start), attach_local(new_end))
    session.add(event)
    session.commit()
    session.refresh(event)
    return to_read(event)


@app.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: UUID, session: Session = Depends(session_dep)) -> None:
    event = _get_event_or_404(session, event_id)
    session.delete(event)
    session.commit()


@app.post("/events/batch", response_model=list[EventRead])
def batch_upsert(
    payloads: list[EventCreate], session: Session = Depends(session_dep)
) -> list[EventRead]:
    """Batch create/update (upsert).

    Each item with an `id` updates the existing event if present, otherwise
    creates one with that ID. Items without `id` create new events.
    """
    if not payloads:
        return []
    results: list[EventRead] = []
    for payload in payloads:
        _validate_span(payload.start, payload.end)
        if payload.id is not None:
            event = session.get(Event, payload.id)
            if event is None:
                event = Event(id=payload.id)
        else:
            event = Event()
        apply_create_fields(event, payload)
        session.add(event)
        results.append(to_read(event))
    session.commit()
    return results


@app.delete("/events", response_model=dict)
def clear_all_events(session: Session = Depends(session_dep)) -> dict:
    """Delete every event (reset to empty)."""
    count = clear_events(session)
    session.commit()
    return {"deleted": count}


@app.post("/seed", response_model=list[EventRead])
def seed(replace: bool = True, session: Session = Depends(session_dep)) -> list[EventRead]:
    """Insert the deterministic seed dataset.

    With replace=True (default) the table is cleared first, yielding a known
    starting state. Returns the seeded events.
    """
    events = seed_events(session, replace=replace)
    session.commit()
    for e in events:
        session.refresh(e)
    return [to_read(e) for e in events]
