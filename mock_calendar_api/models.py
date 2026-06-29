"""SQLModel models and Pydantic schemas for calendar events."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from .tz import NY, attach_local, to_local_naive


class EventBase(SQLModel):
    title: str = Field(index=True, min_length=1, max_length=255)
    start: datetime = Field(description="Event start (New York local).")
    end: datetime = Field(description="Event end (New York local).")
    description: str | None = Field(default=None, max_length=4096)
    location: str | None = Field(default=None, max_length=255)


class Event(EventBase, table=True):
    __tablename__ = "events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: to_local_naive(datetime.now(NY)))
    updated_at: datetime = Field(default_factory=lambda: to_local_naive(datetime.now(NY)))
    # Free-form metadata for sleep-specific or arbitrary fields. The Python
    # attribute is `metadata_` (avoids clashing with SQLModel's reserved
    # `metadata`); the DB column is named `metadata` and stored as JSON.
    metadata_: dict | None = Field(
        default=None, sa_column=Column("metadata", JSON, nullable=True)
    )


class EventCreate(EventBase):
    id: UUID | None = Field(
        default=None, description="Optional explicit ID for upsert/deterministic seeding."
    )
    metadata_: dict | None = None


class EventUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    start: datetime | None = None
    end: datetime | None = None
    description: str | None = None
    location: str | None = None
    metadata_: dict | None = None


class EventRead(SQLModel):
    """Serialized event with New York-aware datetimes."""

    id: UUID
    title: str
    start: datetime
    end: datetime
    description: str | None
    location: str | None
    metadata_: dict | None
    created_at: datetime
    updated_at: datetime


def to_read(event: Event) -> EventRead:
    return EventRead(
        id=event.id,
        title=event.title,
        start=attach_local(event.start),
        end=attach_local(event.end),
        description=event.description,
        location=event.location,
        metadata_=event.metadata_,
        created_at=attach_local(event.created_at),
        updated_at=attach_local(event.updated_at),
    )


def apply_create_fields(event: Event, data: EventCreate) -> None:
    """Populate an Event from a create payload, normalizing datetimes to New York local."""
    event.title = data.title
    event.start = to_local_naive(data.start)
    event.end = to_local_naive(data.end)
    event.description = data.description
    event.location = data.location
    event.metadata_ = data.metadata_


def apply_update_fields(event: Event, data: EventUpdate) -> None:
    """Patch an Event with only the provided fields."""
    changed = False
    if data.title is not None:
        event.title = data.title
        changed = True
    if data.start is not None:
        event.start = to_local_naive(data.start)
        changed = True
    if data.end is not None:
        event.end = to_local_naive(data.end)
        changed = True
    if data.description is not None:
        event.description = data.description
        changed = True
    if data.location is not None:
        event.location = data.location
        changed = True
    if data.metadata_ is not None:
        event.metadata_ = data.metadata_
        changed = True
    if changed:
        event.updated_at = to_local_naive(datetime.now(NY))
