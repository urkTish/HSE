"""Time helpers. Store UTC; compute day boundaries in the project timezone (spec K2).

`frozen()` pins "now" (tests and replaying jobs for a given instant); every caller goes through
`now()`, so the override applies everywhere."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Riyadh"
_override: list[datetime] = []
_offset: list[timedelta] = []


def now() -> datetime:
    if _override:
        return _override[-1]
    if _offset:
        return datetime.now(UTC) + _offset[0]
    return datetime.now(UTC)


def pin_from_env(value: str | None, mode: str | None, environment: str) -> datetime | None:
    """Dev/e2e clock pin (HSE_CLOCK_AT, ISO 8601 with offset; HSE_CLOCK_MODE `advancing`
    (default: time runs on from that instant) or `fixed`). Refused in production."""
    if not value:
        return None
    if environment == "production":
        raise RuntimeError("HSE_CLOCK_AT is not allowed when ENVIRONMENT=production")
    at = datetime.fromisoformat(value)
    if at.tzinfo is None:
        raise ValueError("HSE_CLOCK_AT needs a UTC offset, e.g. 2026-10-06T10:00:00+03:00")
    if (mode or "advancing") == "fixed":
        set_now(at)
    elif mode in (None, "", "advancing"):
        _offset.clear()
        _offset.append(at.astimezone(UTC) - datetime.now(UTC))
    else:
        raise ValueError("HSE_CLOCK_MODE must be 'advancing' or 'fixed'")
    return at


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
