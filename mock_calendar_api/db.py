"""Database engine, session management, and app lifespan."""

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

sqlite_url = os.environ.get("DATABASE_URL", "sqlite:///./calendar.db")
engine = create_engine(
    sqlite_url,
    echo=False,
    # SQLite handles writes serially; the check is cheap insurance for a mock.
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    # Import models so SQLModel registers them before create_all.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
