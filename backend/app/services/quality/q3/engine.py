"""Pure cold-chain calculations (spec 8-quality §D.3–§D.4): reading coverage and monitoring gaps
(Q-STO-04), time out of range (Q-STO-05), runs, transients and excursions with severity
(Q-EXC-01…03) and mean kinetic temperature (Q-EXC-12). No database access: the services feed
readings in and store what comes out, so the worked examples QX12, QX13, QX15 and QX18 are unit
tests of this module.

Time is handled in whole minutes (a reading at 08:15:40 counts from 08:15). A reading covers
[measured_at, next reading) when the next reading of the same point is at most
`reading_gap_factor` × interval later, else [measured_at, measured_at + interval) and the
minutes up to the next reading are unmonitored."""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.core.quality.q3 import SEVERITY_RANK, QExcursionSeverity

MIN = timedelta(minutes=1)
SEV = QExcursionSeverity


@dataclass(frozen=True)
class Reading:
    point: uuid.UUID
    at: datetime
    value: Decimal | None
    rid: int | None = None
    fault: bool = False  # probe_fault readings cover but are never out (Q-EXC-11)


@dataclass(frozen=True)
class Seg:
    point: uuid.UUID
    start: int  # minute index from the window start (inclusive)
    end: int  # exclusive
    value: Decimal | None
    rid: int | None
    fault: bool


@dataclass(frozen=True)
class Limits:
    lo: Decimal | None
    hi: Decimal | None

    def out(self, v: Decimal | None) -> bool:
        if v is None:
            return False
        return (self.lo is not None and v < self.lo) or (self.hi is not None and v > self.hi)

    def deviation(self, v: Decimal | None) -> Decimal:
        """°C beyond the nearest limit (0 when in range)."""
        if v is None:
            return Decimal(0)
        if self.hi is not None and v > self.hi:
            return v - self.hi
        if self.lo is not None and v < self.lo:
            return self.lo - v
        return Decimal(0)


@dataclass(frozen=True)
class Bands:
    alarm_delay: int
    d1: Decimal
    d2: Decimal
    t1: int
    t2: int


@dataclass
class Run:
    start: int
    end: int  # exclusive minute index; for an ongoing run the end of the known data
    ongoing: bool
    out_minutes: int
    data_gap: bool
    transient: bool = False
    # still out at the end of the data but shorter than the alarm delay: it may yet end as a
    # transient, so it is not an excursion yet (Q-EXC-03)
    pending: bool = False
    peak: Decimal | None = None
    peak_point: uuid.UUID | None = None
    max_deviation: Decimal = Decimal(0)
    degree_minutes: Decimal = Decimal(0)
    severity: QExcursionSeverity = SEV.minor
    points: set[uuid.UUID] = field(default_factory=set)

    @property
    def duration(self) -> int:
        return self.end - self.start


@dataclass
class Grid:
    """Per-minute zone state over a window: monitored and out (Q-STO-04 / -05)."""

    t0: datetime
    n: int
    mon: bytearray
    out: bytearray
    segs: list[Seg]

    def at(self, i: int) -> datetime:
        return self.t0 + i * MIN

    def index(self, t: datetime) -> int:
        return int((t - self.t0) / MIN)


def _floor(t: datetime) -> datetime:
    return t.replace(second=0, microsecond=0)


def segments(
    readings: Iterable[Reading],
    intervals: dict[uuid.UUID, int],
    factor: Decimal,
    t0: datetime,
    t1: datetime,
) -> list[Seg]:
    by_point: dict[uuid.UUID, list[Reading]] = {}
    for r in readings:
        by_point.setdefault(r.point, []).append(r)
    out: list[Seg] = []
    n = int((t1 - t0) / MIN)
    for pid, rows in by_point.items():
        rows.sort(key=lambda r: r.at)
        iv = intervals.get(pid, 15)
        limit = Decimal(iv) * factor
        for i, r in enumerate(rows):
            s = int((_floor(r.at) - t0) / MIN)
            nxt = rows[i + 1] if i + 1 < len(rows) else None
            if nxt is not None and Decimal(int((_floor(nxt.at) - _floor(r.at)) / MIN)) <= limit:
                e = int((_floor(nxt.at) - t0) / MIN)
            else:
                e = s + iv
            s, e = max(s, 0), min(e, n)
            if e > s:
                out.append(Seg(pid, s, e, r.value, r.rid, r.fault))
    return out


def grid(
    readings: Iterable[Reading],
    intervals: dict[uuid.UUID, int],
    factor: Decimal,
    limits: Limits,
    t0: datetime,
    t1: datetime,
) -> Grid:
    n = max(int((t1 - t0) / MIN), 0)
    mon = bytearray(n)
    out = bytearray(n)
    segs = segments(readings, intervals, factor, t0, t1)
    for sg in segs:
        mon[sg.start : sg.end] = b"\x01" * (sg.end - sg.start)
        if not sg.fault and limits.out(sg.value):
            out[sg.start : sg.end] = b"\x01" * (sg.end - sg.start)
    return Grid(t0, n, mon, out, segs)


def coverage(g: Grid, a: int = 0, b: int | None = None) -> tuple[int, int, int]:
    """(period minutes, monitored minutes, out minutes) over [a, b)."""
    b = g.n if b is None else b
    mon = g.mon[a:b].count(1)
    out = g.out[a:b].count(1)
    return b - a, mon, out


def gaps(g: Grid, min_minutes: int) -> list[tuple[int, int]]:
    """Unmonitored stretches of at least `min_minutes` (Q-STO-04 monitoring gap entries)."""
    res: list[tuple[int, int]] = []
    i = 0
    while i < g.n:
        if g.mon[i]:
            i += 1
            continue
        j = i
        while j < g.n and not g.mon[j]:
            j += 1
        if j - i >= min_minutes:
            res.append((i, j))
        i = j
    return res


def runs(g: Grid, bands: Bands, limits: Limits) -> list[Run]:
    """Q-EXC-01: a run starts at the first out minute and ends at the first later minute that is
    monitored and in range; unmonitored minutes inside count as out time and set `data_gap`
    (Q-EXC-02). Runs separated by fewer than `alarm_delay` in-range minutes are one excursion;
    a run shorter than `alarm_delay` is a transient (Q-EXC-03)."""
    raw: list[Run] = []
    i = 0
    n = g.n
    while i < n:
        if not g.out[i]:
            i += 1
            continue
        s = i
        gap = False
        outm = 0
        j = i
        while j < n and (g.out[j] or not g.mon[j]):
            if g.out[j]:
                outm += 1
            else:
                gap = True
            j += 1
        ongoing = j >= n
        e = j
        if ongoing:
            # trailing unmonitored minutes after the last out reading are not known data
            while e > s and not g.mon[e - 1]:
                e -= 1
            gap = gap and any(not g.mon[k] for k in range(s, e))
        raw.append(Run(s, e, ongoing, outm, gap))
        i = j
    merged: list[Run] = []
    for r in raw:
        if merged and r.start - merged[-1].end < bands.alarm_delay and not merged[-1].ongoing:
            m = merged[-1]
            m.end, m.ongoing = r.end, r.ongoing
            m.out_minutes += r.out_minutes
            m.data_gap = m.data_gap or r.data_gap
        else:
            merged.append(r)
    for r in merged:
        r.transient = r.duration < bands.alarm_delay and not r.ongoing
        r.pending = r.duration < bands.alarm_delay and r.ongoing
        _stats(g, r, limits)
        r.severity = severity(r.max_deviation, r.duration, bands)
    return merged


def _stats(g: Grid, r: Run, limits: Limits) -> None:
    peak_dev = Decimal(-1)
    dm = Decimal(0)
    for sg in g.segs:
        if sg.fault or sg.end <= r.start or sg.start >= r.end or not limits.out(sg.value):
            continue
        dev = limits.deviation(sg.value)
        covered = min(sg.end, r.end) - max(sg.start, r.start)
        dm += dev * covered
        r.points.add(sg.point)
        if dev > peak_dev:
            peak_dev, r.peak, r.peak_point = dev, sg.value, sg.point
    r.max_deviation = max(peak_dev, Decimal(0))
    r.degree_minutes = dm.quantize(Decimal("0.01"), ROUND_HALF_UP)


def level(value: Decimal | int, b1: Decimal | int, b2: Decimal | int) -> QExcursionSeverity:
    if value <= b1:
        return SEV.minor
    if value <= b2:
        return SEV.major
    return SEV.critical


def severity(max_dev: Decimal, duration: int, bands: Bands) -> QExcursionSeverity:
    """Q-EXC-02: the worse of the deviation level and the duration level."""
    a = level(max_dev, bands.d1, bands.d2)
    b = level(duration, bands.t1, bands.t2)
    return a if SEVERITY_RANK[a] >= SEVERITY_RANK[b] else b


# ---- mean kinetic temperature (Q-EXC-12) --------------------------------------------------------

DH_R = 10_000.0  # ΔH/R in kelvin (ΔH = 83.144 kJ/mol)


def mkt(values_c: Sequence[float | Decimal]) -> Decimal | None:
    """MKT = (ΔH/R) ÷ (−ln(Σ e^(−ΔH/(R·Tᵢ)) ÷ n)) − 273.15, Tᵢ the hourly means in kelvin."""
    vals = [float(v) for v in values_c]
    if not vals:
        return None
    s = sum(math.exp(-DH_R / (v + 273.15)) for v in vals) / len(vals)
    t = DH_R / (-math.log(s)) - 273.15
    return Decimal(str(t)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def hourly_means(rows: Iterable[tuple[datetime, Decimal | None]]) -> list[float]:
    buckets: dict[datetime, list[float]] = {}
    for at, v in rows:
        if v is None:
            continue
        buckets.setdefault(at.replace(minute=0, second=0, microsecond=0), []).append(float(v))
    return [sum(x) / len(x) for _, x in sorted(buckets.items())]
