"""New York timezone handling.

The calendar stores and returns all datetimes in New York local time
(`America/New_York`), which observes DST (EST/EDT depending on the season).
Internally we store *naive* datetimes whose wall-clock is New York local;
on read we re-attach the `America/New_York` tzinfo so serialization stays
consistent and the offset reflects the actual DST in effect at that moment.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

# America/New_York: EST (UTC-05:00) in winter, EDT (UTC-04:00) in summer.
NY = ZoneInfo("America/New_York")


def to_local(dt: datetime) -> datetime:
    """Return a datetime normalized to New York local time.

    Naive datetimes are assumed to already be New York wall-clock. Aware
    datetimes are converted to New York.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=NY)
    return dt.astimezone(NY)


def to_local_naive(dt: datetime) -> datetime:
    """Return the New York wall-clock representation with tzinfo stripped, for storage."""
    return to_local(dt).replace(tzinfo=None)


def attach_local(dt: datetime) -> datetime | None:
    """Attach the New York tzinfo to a naive datetime read from the DB (or pass None)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=NY)
    return dt.astimezone(NY)
