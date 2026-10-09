"""Zone heat state (spec 6b-heat-stress §3.5, §6.3, WR-7…WR-9): derived on read from the valid
readings of the zone's covering point. `timeline` splits a monitoring window into constant
segments (K-98, alerts)."""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.heat_enums import (
    AcclimatisationBasis,
    Clothing,
    HeatStateKind,
    ReadingSource,
    RecordStatus,
    Regime,
    Workload,
)
from app.models import MonitoringPoint, WbgtReading
from app.services.heat import common as hc

AB = AcclimatisationBasis
S = HeatStateKind


@dataclass(frozen=True)
class Rd:
    id: uuid.UUID
    reading_no: str
    point_id: uuid.UUID
    measured_at: datetime
    source: ReadingSource
    wbgt: Decimal
    cells: dict[str, str]

    @property
    def kind(self) -> str:
        return "station" if self.source == ReadingSource.station else "manual"


def rd(r: WbgtReading) -> Rd:
    return Rd(
        r.id,
        r.reading_no,
        r.point_id,
        r.measured_at,
        r.source,
        Decimal(r.wbgt_c),
        dict(r.regime_cells or {}),
    )


@dataclass
class ZState:
    state: HeatStateKind
    latest: Rd | None = None
    applying: list[Rd] = field(default_factory=list)
    point: MonitoringPoint | None = None

    def regime(
        self,
        t: hc.Table,
        offset: Decimal,
        basis: AcclimatisationBasis,
        workload: Workload,
        clothing: Clothing = Clothing.work_clothes,
        hood: bool = False,
    ) -> Regime:
        if self.latest is None:
            return Regime.unknown
        return hc.worst(
            hc.regime_for(t, offset, basis, workload, hc.effective(r.wbgt, clothing, hood))
            for r in self.applying
        )

    def cell(self, key: str) -> Regime:
        if self.latest is None:
            return Regime.unknown
        return hc.worst(Regime(r.cells.get(key, "unknown")) for r in self.applying)

    def acc_r4(self) -> list[Workload]:
        return [w for w in hc.WORKLOADS if self.cell(hc.cell_key(AB.acclimatised, w)) == Regime.R4]


def readings(db: Session, point_id: uuid.UUID, start: datetime, end: datetime) -> list[Rd]:
    """Valid readings of the point with start ≤ measured_at ≤ end, oldest first."""
    rows = db.scalars(
        select(WbgtReading)
        .where(
            WbgtReading.point_id == point_id,
            WbgtReading.status == RecordStatus.valid,
            WbgtReading.measured_at >= start,
            WbgtReading.measured_at <= end,
        )
        .order_by(WbgtReading.measured_at, WbgtReading.created_at)
    )
    return [rd(r) for r in rows]


def compute(rs: list[Rd], at: datetime, cfg: hc.Cfg) -> ZState:
    """§6.3 for the readings `rs` (oldest first, any range covering [day start − relax, at])."""
    day0 = hc.day_start(hc.local_day(at))
    upto = [r for r in rs if r.measured_at <= at]
    on_day = [r for r in upto if r.measured_at >= day0]
    if not on_day:
        return ZState(S.unknown)
    last = on_day[-1]
    lo = at - cfg.relax
    app = [r for r in upto if r.measured_at > lo]
    if last not in app:
        app.append(last)
    st = S.stale if at - last.measured_at > cfg.valid_for(last.kind) else S.current
    return ZState(st, last, app)


def point_state(db: Session, pt: MonitoringPoint, at: datetime, cfg: hc.Cfg) -> ZState:
    start = min(hc.day_start(hc.local_day(at)), at - cfg.relax)
    z = compute(readings(db, pt.id, start, at), at, cfg)
    z.point = pt
    return z


def zone_state(db: Session, project_id: uuid.UUID, zone_id: uuid.UUID, at: datetime) -> ZState:
    pt = hc.covering(db, project_id).get(zone_id)
    if pt is None:
        return ZState(S.unknown)
    return point_state(db, pt, at, hc.cfg(db, project_id))


def headline(z: ZState, cfg: hc.Cfg) -> Regime:
    return z.cell(hc.cell_key(AB.acclimatised, cfg.headline))


# ---- timeline -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Seg:
    start: datetime
    end: datetime
    state: HeatStateKind
    regime: Regime

    @property
    def hours(self) -> Decimal:
        return Decimal((self.end - self.start).total_seconds()) / Decimal(3600)


def timeline(rs: list[Rd], d: date, cfg: hc.Cfg, key: str) -> list[Seg]:
    """Constant segments of (state, cell `key`) over the monitoring hours of local date d.
    `rs` must hold the point's valid readings from d's start − relax to the window end."""
    ws, we = cfg.monitoring(d)
    cuts = {ws, we}
    for r in rs:
        for x in (r.measured_at, r.measured_at + cfg.relax, r.measured_at + cfg.valid_for(r.kind)):
            if ws < x < we:
                cuts.add(x)
    pts = sorted(cuts)
    out: list[Seg] = []
    for a, b in itertools.pairwise(pts):
        z = compute(rs, a + (b - a) / 2, cfg)  # constant inside the segment
        reg = z.cell(key) if z.latest is not None else Regime.unknown
        seg = Seg(a, b, z.state, reg)
        if out and out[-1].state == seg.state and out[-1].regime == seg.regime:
            out[-1] = Seg(out[-1].start, b, seg.state, seg.regime)
        else:
            out.append(seg)
    return out


def day_readings(db: Session, point_id: uuid.UUID, d: date, cfg: hc.Cfg) -> list[Rd]:
    s = hc.day_start(d) - cfg.relax
    return readings(db, point_id, s, hc.day_start(d + timedelta(days=1)))
