"""Time helpers. Store UTC; compute day boundaries in the project timezone (spec K2).

`frozen()` pins "now" (tests and replaying jobs for a given instant); every caller goes through
`now()`, so the override applies everywhere."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Riyadh"
_override: list[datetime] = []


def now() -> datetime:
    if _override:
        return _override[-1]
    return datetime.now(UTC)


def local_date(ts: datetime, tz: str = DEFAULT_TZ) -> date:
    return ts.astimezone(ZoneInfo(tz)).date()


def today(tz: str = DEFAULT_TZ) -> date:
    return local_date(now(), tz)


def set_now(at: datetime | None) -> None:
    """Pin (or with None, release) the current instant."""
    _override.clear()
    if at is not None:
        _override.append(at.astimezone(UTC))


def advance(delta: timedelta) -> datetime:
    """Move a pinned clock forward (no-op error when not pinned)."""
    if not _override:
        raise RuntimeError("clock is not pinned")
    _override[-1] = _override[-1] + delta
    return _override[-1]


@contextmanager
def frozen(at: datetime) -> Iterator[datetime]:
    prev = list(_override)
    set_now(at)
    try:
        yield _override[-1]
    finally:
        _override.clear()
        _override.extend(prev)
