"""WAP daily windows (spec 2-access-permits WA-9, §6.7): local times; a window whose end ≤ start
crosses midnight and belongs to its start date. UTC = local − 3 h (Asia/Riyadh)."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from app.core.hse_enums import Weekday
from app.services.access.common import at_local, local_day

PY_WEEKDAY = {
    Weekday.monday: 0,
    Weekday.tuesday: 1,
    Weekday.wednesday: 2,
    Weekday.thursday: 3,
    Weekday.friday: 4,
    Weekday.saturday: 5,
    Weekday.sunday: 6,
}
ALL_DAYS = [w.value for w in Weekday]


@dataclass(frozen=True)
class WindowDef:
    start: time
    end: time
    weekdays: frozenset[int]

    @property
    def crosses_midnight(self) -> bool:
        return self.end <= self.start

    def label(self) -> str:
        return f"{self.start.strftime('%H:%M')}-{self.end.strftime('%H:%M')}"


@dataclass(frozen=True)
class Instance:
    local_date: date
    start_utc: datetime
    end_utc: datetime
    label: str


def parse(windows: list[dict[str, Any]]) -> list[WindowDef]:
    out = []
    for w in windows:
        out.append(
            WindowDef(
                start=time.fromisoformat(str(w["start_local"])),
                end=time.fromisoformat(str(w["end_local"])),
                weekdays=frozenset(PY_WEEKDAY[Weekday(x)] for x in w.get("weekdays") or ALL_DAYS),
            )
        )
    return out


def dump(windows: list[Any]) -> list[dict[str, Any]]:
    """Schema WapWindow objects → JSON."""
    return [
        {
            "start_local": w.start_local.strftime("%H:%M"),
            "end_local": w.end_local.strftime("%H:%M"),
            "weekdays": [d.value for d in w.weekdays],
        }
        for w in windows
    ]


def instance(w: WindowDef, d: date) -> Instance:
    end_day = d + timedelta(days=1) if w.crosses_midnight else d
    return Instance(d, at_local(d, w.start), at_local(end_day, w.end), w.label())


def instances(
    windows: list[WindowDef], valid_from: date, valid_to: date, start: date, end: date
) -> list[Instance]:
    out: list[Instance] = []
    d = max(valid_from, start)
    last = min(valid_to, end)
    while d <= last:
        for w in windows:
            if d.weekday() in w.weekdays:
                out.append(instance(w, d))
        d += timedelta(days=1)
    return sorted(out, key=lambda i: i.start_utc)


def current(
    windows: list[WindowDef], valid_from: date, valid_to: date, at: datetime
) -> Instance | None:
    d = local_day(at)
    for i in instances(windows, valid_from, valid_to, d - timedelta(days=1), d):
        if i.start_utc <= at < i.end_utc:
            return i
    return None


def upcoming(
    windows: list[WindowDef], valid_from: date, valid_to: date, at: datetime
) -> Instance | None:
    d = local_day(at)
    for i in instances(windows, valid_from, valid_to, d, d + timedelta(days=8)):
        if i.start_utc > at:
            return i
    return None


def last_ended(
    windows: list[WindowDef], valid_from: date, valid_to: date, at: datetime
) -> Instance | None:
    d = local_day(at)
    ended = [
        i
        for i in instances(windows, valid_from, valid_to, d - timedelta(days=2), d)
        if i.end_utc <= at
    ]
    return ended[-1] if ended else None


def today_label(windows: list[WindowDef], valid_from: date, valid_to: date, d: date) -> str | None:
    labels = [i.label for i in instances(windows, valid_from, valid_to, d, d)]
    return ", ".join(labels) if labels else None
