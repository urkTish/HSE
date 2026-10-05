"""Time helpers. Store UTC; compute day boundaries in the project timezone (spec K2)."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Riyadh"


def now() -> datetime:
    return datetime.now(UTC)


def local_date(ts: datetime, tz: str = DEFAULT_TZ) -> date:
    return ts.astimezone(ZoneInfo(tz)).date()


def today(tz: str = DEFAULT_TZ) -> date:
    return local_date(now(), tz)
