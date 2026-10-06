"""Period windows and comparisons (spec 1-dashboard K-R10, K-R11, §6.7). All inclusive."""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.enums import WeekStart
from app.core.hse_enums import ComparisonKind, PeriodPreset

MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTHS_AR = (
    "يناير",
    "فبراير",
    "مارس",
    "أبريل",
    "مايو",
    "يونيو",
    "يوليو",
    "أغسطس",
    "سبتمبر",
    "أكتوبر",
    "نوفمبر",
    "ديسمبر",
)


@dataclass(frozen=True, order=True)
class Window:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def contains(self, d: date) -> bool:
        return self.start <= d <= self.end


@dataclass(frozen=True)
class Period:
    preset: PeriodPreset
    window: Window
    label_en: str
    label_ar: str


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    """Calendar month shift, clamped to the month end (31 Mar − 1 month = 28/29 Feb)."""
    idx = d.year * 12 + (d.month - 1) + n
    y, m = divmod(idx, 12)
    last = calendar.monthrange(y, m + 1)[1]
    return date(y, m + 1, min(d.day, last))


def minus_year(d: date, years: int = 1) -> date:
    """Same date one year earlier; 29 Feb → 28 Feb (K-R11)."""
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        return d.replace(year=d.year - years, day=28)


def quarter_start(d: date) -> date:
    return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)


def week_start(d: date, start: WeekStart) -> date:
    # Python weekday(): Monday = 0 … Sunday = 6
    offset = d.weekday() if start == WeekStart.monday else (d.weekday() + 1) % 7
    return d - timedelta(days=offset)


def fmt_day(d: date) -> tuple[str, str]:
    return (
        f"{d.day:02d} {MONTHS_EN[d.month - 1]} {d.year}",
        f"{d.day:02d} {MONTHS_AR[d.month - 1]} {d.year}",
    )


def fmt_month(d: date) -> tuple[str, str]:
    return f"{MONTHS_EN[d.month - 1]} {d.year}", f"{MONTHS_AR[d.month - 1]} {d.year}"


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def range_label(w: Window) -> tuple[str, str]:
    """Readable label for any window (exact months/quarters/years get short names)."""
    s, e = w.start, w.end
    if s == e:
        return fmt_day(s)
    if s.day == 1 and e == month_end(s):
        return fmt_month(s)
    if s.day == 1 and s.month == 1 and e == date(s.year, 12, 31):
        return str(s.year), str(s.year)
    if s == quarter_start(s) and e == month_end(add_months(s, 2)):
        q = (s.month - 1) // 3 + 1
        return f"Q{q} {s.year}", f"الربع {q} {s.year}"
    if e == month_end(e) and s == add_months(e, -12) + timedelta(days=1):
        en, ar = fmt_month(e)
        return f"R12 to {en}", f"آخر 12 شهراً حتى {ar}"
    se, sa = fmt_day(s)
    ee, ea = fmt_day(e)
    return f"{se} – {ee}", f"{sa} – {ea}"


def resolve(
    preset: PeriodPreset,
    *,
    as_of: date,
    anchor: date | None = None,
    start: date | None = None,
    end: date | None = None,
    week_starts: WeekStart = WeekStart.sunday,
    project_start: date | None = None,
) -> Period:
    """Window for a preset. Calendar presets use ``anchor`` (default ``as_of``); to-date presets
    (mtd/qtd/ytd/r12/itd) end at ``as_of``."""
    a = anchor or as_of
    if preset == PeriodPreset.custom:
        if start is None or end is None:
            raise ValueError("custom period needs start and end")
        if end < start:
            raise ValueError("end must be on or after start")
        w = Window(start, end)
        en, ar = range_label(w)
    elif preset == PeriodPreset.day:
        w = Window(a, a)
        en, ar = fmt_day(a)
    elif preset == PeriodPreset.week:
        s = week_start(a, week_starts)
        w = Window(s, s + timedelta(days=6))
        de, da = fmt_day(s)
        en, ar = f"Week of {de}", f"أسبوع {da}"
    elif preset == PeriodPreset.month:
        w = Window(month_start(a), month_end(a))
        en, ar = fmt_month(a)
    elif preset == PeriodPreset.quarter:
        s = quarter_start(a)
        w = Window(s, month_end(add_months(s, 2)))
        en, ar = range_label(w)
    elif preset == PeriodPreset.year:
        w = Window(date(a.year, 1, 1), date(a.year, 12, 31))
        en, ar = str(a.year), str(a.year)
    elif preset == PeriodPreset.mtd:
        w = Window(month_start(as_of), as_of)
        me, ma = fmt_month(as_of)
        en, ar = f"{me} to date", f"{ma} حتى تاريخه"
    elif preset == PeriodPreset.qtd:
        w = Window(quarter_start(as_of), as_of)
        q = (as_of.month - 1) // 3 + 1
        en, ar = f"Q{q} {as_of.year} to date", f"الربع {q} {as_of.year} حتى تاريخه"
    elif preset == PeriodPreset.ytd:
        w = Window(date(as_of.year, 1, 1), as_of)
        en, ar = f"YTD {as_of.year}", f"منذ بداية {as_of.year}"
    elif preset == PeriodPreset.r12:
        w = Window(add_months(as_of, -12) + timedelta(days=1), as_of)
        if as_of == month_end(as_of):
            me, ma = fmt_month(as_of)
        else:
            me, ma = fmt_day(as_of)
        en, ar = f"R12 to {me}", f"آخر 12 شهراً حتى {ma}"
    else:  # itd
        s = project_start or date(as_of.year, 1, 1)
        w = Window(min(s, as_of), as_of)
        en, ar = "Project to date", "منذ بداية المشروع"
    return Period(preset, w, en, ar)


def previous(preset: PeriodPreset, w: Window) -> Window:
    """K-R11 'previous period': the same preset immediately preceding."""
    if preset == PeriodPreset.day:
        d = w.start - timedelta(days=1)
        return Window(d, d)
    if preset == PeriodPreset.week:
        return Window(w.start - timedelta(days=7), w.end - timedelta(days=7))
    if preset == PeriodPreset.month:
        s = add_months(w.start, -1)
        return Window(s, month_end(s))
    if preset == PeriodPreset.quarter:
        s = add_months(w.start, -3)
        return Window(s, month_end(add_months(s, 2)))
    if preset == PeriodPreset.year:
        return Window(date(w.start.year - 1, 1, 1), date(w.start.year - 1, 12, 31))
    if preset == PeriodPreset.mtd:
        s = add_months(w.start, -1)
        return Window(s, min(add_months(w.end, -1), month_end(s)))
    if preset == PeriodPreset.qtd:
        s = add_months(w.start, -3)
        return Window(s, min(add_months(w.end, -3), month_end(add_months(s, 2))))
    if preset == PeriodPreset.ytd:
        return Window(minus_year(w.start), minus_year(w.end))
    if preset == PeriodPreset.r12:
        e = w.start - timedelta(days=1)
        return Window(add_months(e, -12) + timedelta(days=1), e)
    # custom / itd: the N days ending the day before start
    e = w.start - timedelta(days=1)
    return Window(e - timedelta(days=w.days - 1), e)


def sply(w: Window) -> Window:
    return Window(minus_year(w.start), minus_year(w.end))


def r12_ending(end: date) -> Window:
    """R12 window ending at ``end`` = [add_months(end, −12) + 1 day, end]."""
    return Window(add_months(end, -12) + timedelta(days=1), end)


def comparison(kind: ComparisonKind, preset: PeriodPreset, w: Window) -> Window:
    if kind == ComparisonKind.previous:
        return previous(preset, w)
    if kind == ComparisonKind.sply:
        return sply(w)
    return r12_ending(w.end)


def months_ending(end: date, count: int) -> list[Window]:
    """``count`` calendar months, oldest first, the last one containing ``end``."""
    out = []
    m = month_start(end)
    for i in range(count - 1, -1, -1):
        s = add_months(m, -i)
        out.append(Window(s, month_end(s)))
    return out


def months_between(start: date, end: date) -> list[Window]:
    out = []
    m = month_start(start)
    while m <= end:
        out.append(Window(m, month_end(m)))
        m = add_months(m, 1)
    return out


def weeks_between(start: date, end: date, starts: WeekStart) -> list[Window]:
    out = []
    s = week_start(start, starts)
    while s <= end:
        out.append(Window(s, s + timedelta(days=6)))
        s += timedelta(days=7)
    return out
