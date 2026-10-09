"""Heat-stress KPIs K-97…K-103 (spec 6b-heat-stress §6.5, §6.6, HM-1).

Computed from the 6b registers on the request's session (`HeatFacts`, loaded on first use like
the other phase facts). Period scope (HM-1): controls-period dates for K-97, K-101, K-102; ban
dates for K-99, K-100; any date for K-98 (days with work only, DECISIONS) and K-103. Filters:
site and zone apply to zones, points, stations, patrols and log entries; an engagement filter
narrows days with work (K-97, K-98, K-99, K-101 chip) to the filtered engagements' daily returns,
and K-100, K-102 and K-103 to records of those engagements."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.heat_enums import (
    HeatLogSource,
    HeatLogStatus,
    PatrolOutcome,
    PlanStatus,
    RecordStatus,
    Regime,
)
from app.core.hse_enums import CaseCategory, KpiKind, KpiMetric
from app.kpi import engine as engine_mod
from app.kpi.engine import Agg, Component, Engine, Result
from app.kpi.periods import Window
from app.models import (
    AcclimatisationPlan,
    BanPatrol,
    Deployment,
    HeatIllnessEntry,
    HeatWelfareCheck,
    MonitoringPoint,
    RestStation,
    WbgtReading,
)
from app.services.access.common import RIYADH

UUID = uuid.UUID
M = KpiMetric
HUNDRED = Decimal(100)
Counter_t = dict[str, int]
BUCKETS = ["R0", "R1", "R2", "R3", "R4", "stale", "unknown"]
BUCKET_LABELS = {
    "R0": ("R0 — continuous work", "R0 — عمل متواصل"),
    "R1": ("R1 — 45/15", "R1 — 45/15"),
    "R2": ("R2 — 30/30", "R2 — 30/30"),
    "R3": ("R3 — 15/45", "R3 — 15/45"),
    "R4": ("R4 — stop", "R4 — إيقاف"),
    "stale": ("Stale reading", "قراءة قديمة"),
    "unknown": ("No reading", "لا توجد قراءة"),
}


@dataclass
class Proj:
    pid: UUID
    cfg: Any
    required: list[UUID]
    covering: dict[UUID, MonitoringPoint]
    zone_site: dict[UUID, UUID]


@dataclass
class HeatFacts:
    pids: list[UUID]
    db: Session
    projects: dict[UUID, Proj | None] = field(default_factory=dict)
    memo: dict[Any, Any] = field(default_factory=dict)

    def proj(self, pid: UUID) -> Proj | None:
        from app.services.heat import common as hc  # noqa: PLC0415

        if pid not in self.projects:
            c = hc.cfg(self.db, pid)
            if c.register_from is None:
                self.projects[pid] = None
            else:
                zmap = hc.zone_map(self.db, pid)
                self.projects[pid] = Proj(
                    pid,
                    c,
                    hc.required_zone_ids(self.db, pid),
                    hc.covering(self.db, pid),
                    {z: x.site_id for z, x in zmap.items()},
                )
        return self.projects[pid]

    def all(self) -> list[Proj]:
        return [p for p in (self.proj(x) for x in self.pids) if p is not None]


def load_heat(db: Session, pids: list[UUID]) -> HeatFacts:
    return HeatFacts(list(pids), db)


def hfacts(e: Engine) -> HeatFacts | None:
    hf = getattr(e.facts, "heat", None)
    return hf if isinstance(hf, HeatFacts) else None


def _memo(e: Engine) -> dict[Any, Any]:
    m: dict[Any, Any] | None = getattr(e, "_heat_memo", None)
    if m is None:
        m = {}
        e._heat_memo = m  # type: ignore[attr-defined]
    return m


def _end(e: Engine, w: Window) -> date:
    return min(e.as_of, w.end)


def _range(d0: date, d1: date) -> tuple[datetime, datetime]:
    from app.services.heat import common as hc  # noqa: PLC0415

    return hc.day_start(d0), hc.day_start(d1 + timedelta(days=1))


def _lday(at: datetime) -> date:
    return at.astimezone(RIYADH).date()


def work_days(e: Engine, w: Window) -> dict[UUID, set[date]]:
    """§6.5 days with work per site (daily returns submitted or later, headcount > 0) of the
    filtered engagements and sites, in w up to as_of."""
    key = ("work", w)
    memo = _memo(e)
    if key not in memo:
        end = _end(e, w)
        out: dict[UUID, set[date]] = defaultdict(set)
        f = e.flt
        for r in e.facts.wf:
            if r.hc > 0 and r.reported and w.start <= r.d <= end and f.eng_ok(r.eng):
                out[r.site].add(r.d)
        memo[key] = out
    res: dict[UUID, set[date]] = memo[key]
    return res


def req_zones(e: Engine, p: Proj) -> list[UUID]:
    f = e.flt
    return [
        z for z in p.required if f.site_ok(p.zone_site.get(z, z)) and f.zone_ok(z, e.facts.zones)
    ]


def _zone_ok(e: Engine, p: Proj, z: UUID | None) -> bool:
    f = e.flt
    if z is None:
        return not f.zone_filtered
    site = p.zone_site.get(z)
    return (site is None or f.site_ok(site)) and f.zone_ok(z, e.facts.zones)


# ---- K-97 monitoring coverage ------------------------------------------------------------------


def _slots(hf: HeatFacts, point_id: UUID, d0: date, d1: date) -> set[tuple[date, int]]:
    key = ("slots", point_id, d0, d1)
    if key not in hf.memo:
        s, t = _range(d0, d1)
        rows = hf.db.scalars(
            select(WbgtReading.measured_at).where(
                WbgtReading.point_id == point_id,
                WbgtReading.status == RecordStatus.valid,
                WbgtReading.measured_at >= s,
                WbgtReading.measured_at < t,
            )
        )
        out: set[tuple[date, int]] = set()
        for at in rows:
            loc = at.astimezone(RIYADH)
            out.add((loc.date(), loc.hour))
        hf.memo[key] = out
    res: set[tuple[date, int]] = hf.memo[key]
    return res


@dataclass
class Coverage:
    covered: int = 0
    required: int = 0


def k97_counts(e: Engine, w: Window) -> Coverage:
    hf = hfacts(e)
    out = Coverage()
    if hf is None:
        return out
    wd = work_days(e, w)
    for p in hf.all():
        c = p.cfg
        h0 = int(c["heat_monitoring_hours"]["start_local"][:2])
        hours = range(h0, h0 + c.monitoring_hours())
        pts: dict[UUID, MonitoringPoint] = {}
        uncovered: list[UUID] = []
        for z in req_zones(e, p):
            pt = p.covering.get(z)
            if pt is None:
                uncovered.append(z)
            else:
                pts[pt.id] = pt
        for pt in pts.values():
            ds = sorted(d for d in wd.get(pt.site_id, ()) if c.active_on(d) and c.in_controls(d))
            out.required += len(ds) * len(hours)
            if ds:
                sl = _slots(hf, pt.id, w.start, _end(e, w))
                out.covered += sum(1 for d in ds for h in hours if (d, h) in sl)
        for z in uncovered:
            site = p.zone_site.get(z)
            ds = (
                [d for d in wd.get(site, ()) if c.active_on(d) and c.in_controls(d)] if site else []
            )
            out.required += len(ds) * len(hours)
    return out


def _k97(e: Engine, a: Agg) -> Result:
    c = k97_counts(e, a.window)
    return e._pct(M.K97, c.covered, c.required)


# ---- K-98 heat-stop zone-hours -----------------------------------------------------------------


def _point_hours(hf: HeatFacts, p: Proj, pt: MonitoringPoint, d: date) -> dict[str, Decimal]:
    from app.services.heat import common as hc  # noqa: PLC0415
    from app.services.heat import state  # noqa: PLC0415

    key = ("hours", pt.id, d)
    if key not in hf.memo:
        rs = state.day_readings(hf.db, pt.id, d, p.cfg)
        out: dict[str, Decimal] = defaultdict(Decimal)
        if not rs:
            s, t = p.cfg.monitoring(d)
            out["unknown"] += Decimal((t - s).total_seconds()) / Decimal(3600)
        else:
            from app.core.heat_enums import AcclimatisationBasis, HeatStateKind  # noqa: PLC0415

            k = hc.cell_key(AcclimatisationBasis.acclimatised, p.cfg.headline)
            for seg in state.timeline(rs, d, p.cfg, k):
                if seg.state == HeatStateKind.unknown or seg.regime == Regime.unknown:
                    out["unknown"] += seg.hours
                elif seg.state == HeatStateKind.stale:
                    out["stale"] += seg.hours
                else:
                    out[seg.regime.value] += seg.hours
        hf.memo[key] = dict(out)
    res: dict[str, Decimal] = hf.memo[key]
    return res


def k98_hours(e: Engine, w: Window, zone: UUID | None = None) -> dict[str, Decimal]:
    """Zone-hours by bucket over the monitoring hours of the days with work (current state
    only counts towards a regime; stale and unknown hours are their own buckets)."""
    hf = hfacts(e)
    out: dict[str, Decimal] = dict.fromkeys(BUCKETS, Decimal(0))
    if hf is None:
        return out
    wd = work_days(e, w)
    for p in hf.all():
        c = p.cfg
        hrs = Decimal(c.monitoring_hours())
        for z in req_zones(e, p):
            if zone is not None and z != zone:
                continue
            site = p.zone_site.get(z)
            ds = sorted(d for d in wd.get(site, ()) if c.active_on(d)) if site else []
            pt = p.covering.get(z)
            for d in ds:
                if pt is None:
                    out["unknown"] += hrs
                    continue
                for b, v in _point_hours(hf, p, pt, d).items():
                    out[b] += v
    return out


def _k98(e: Engine, a: Agg) -> Result:
    h = k98_hours(e, a.window)
    res = e._count(M.K98, h["R4"])
    total = sum(h.values(), Decimal(0))
    res.components = [
        Component(b, *BUCKET_LABELS[b], h[b], KpiKind.hours, 1,
                  (h[b] / total * HUNDRED) if total else None)
        for b in BUCKETS
    ]  # fmt: skip
    return res


# ---- K-99 / K-100 midday ban -------------------------------------------------------------------


def _patrols(hf: HeatFacts, pid: UUID, d0: date, d1: date) -> list[BanPatrol]:
    key = ("patrols", pid, d0, d1)
    if key not in hf.memo:
        s, t = _range(d0, d1)
        hf.memo[key] = list(
            hf.db.scalars(
                select(BanPatrol).where(
                    BanPatrol.project_id == pid,
                    BanPatrol.status == RecordStatus.valid,
                    BanPatrol.checked_at >= s,
                    BanPatrol.checked_at < t,
                )
            )
        )
    res: list[BanPatrol] = hf.memo[key]
    return res


@dataclass
class BanStats:
    patrolled: int = 0
    required: int = 0
    patrols: int = 0
    violations: int = 0
    by_eng: dict[UUID, int] = field(default_factory=dict)


def ban_stats(e: Engine, w: Window) -> BanStats:
    hf = hfacts(e)
    out = BanStats()
    if hf is None:
        return out
    wd = work_days(e, w)
    end = _end(e, w)
    for p in hf.all():
        c = p.cfg
        need = int(c["ban_patrols_per_zone_day"])
        rows = [
            x
            for x in _patrols(hf, p.pid, w.start, end)
            if c.ban_date(_lday(x.checked_at)) and _zone_ok(e, p, x.zone_id)
        ]
        per: dict[tuple[UUID, date], int] = defaultdict(int)
        for x in rows:
            per[(x.zone_id, _lday(x.checked_at))] += 1
        for z in req_zones(e, p):
            site = p.zone_site.get(z)
            for d in wd.get(site, ()) if site else ():
                if c.active_on(d) and c.ban_date(d):
                    out.required += 1
                    if per.get((z, d), 0) >= need:
                        out.patrolled += 1
        out.patrols += len(rows)
        for x in rows:
            if x.outcome == PatrolOutcome.violation and e.flt.eng_ok(x.engagement_id):
                out.violations += 1
                if x.engagement_id is not None:
                    out.by_eng[x.engagement_id] = out.by_eng.get(x.engagement_id, 0) + 1
    return out


def _k99(e: Engine, a: Agg) -> Result:
    s = ban_stats(e, a.window)
    return e._pct(M.K99, s.patrolled, s.required)


def _k100(e: Engine, a: Agg) -> Result:
    s = ban_stats(e, a.window)
    res = e._count(M.K100, s.violations)
    rate = Decimal(s.violations) * HUNDRED / Decimal(s.patrols) if s.patrols else None
    res.components = [
        Component("rate_per_100_patrols", "Per 100 patrols", "لكل 100 جولة", rate,
                  KpiKind.rate, 2),
        Component("patrols", "Valid patrols", "الجولات الصحيحة", Decimal(s.patrols),
                  KpiKind.count_),
    ]  # fmt: skip
    return res


# ---- K-101 welfare -----------------------------------------------------------------------------


@dataclass
class WelfareStats:
    compliant: int = 0
    applicable: int = 0
    checked: int = 0
    required: int = 0


def welfare_stats(e: Engine, w: Window) -> WelfareStats:
    hf = hfacts(e)
    out = WelfareStats()
    if hf is None:
        return out
    wd = work_days(e, w)
    end = _end(e, w)
    s, t = _range(w.start, end)
    f = e.flt
    for p in hf.all():
        c = p.cfg
        need = int(c["welfare_checks_per_station_day"])
        stations = [
            st
            for st in hf.db.scalars(select(RestStation).where(RestStation.project_id == p.pid))
            if f.site_ok(st.site_id)
            and (not f.zone_filtered or any(f.zone_ok(z, e.facts.zones) for z in st.zone_ids or []))
        ]
        if not stations:
            continue
        checks = list(
            hf.db.scalars(
                select(HeatWelfareCheck).where(
                    HeatWelfareCheck.station_id.in_([x.id for x in stations]),
                    HeatWelfareCheck.status == RecordStatus.valid,
                    HeatWelfareCheck.checked_at >= s,
                    HeatWelfareCheck.checked_at < t,
                )
            )
        )
        per: dict[tuple[UUID, date], int] = defaultdict(int)
        site_of = {x.id: x.site_id for x in stations}
        for x in checks:
            d = _lday(x.checked_at)
            if not (c.active_on(d) and c.in_controls(d)):
                continue
            if f.engs is not None and d not in wd.get(site_of[x.station_id], ()):
                continue
            per[(x.station_id, d)] += 1
            for i in x.items or []:
                if i.get("answer") in ("pass", "fail"):
                    out.applicable += 1
                    out.compliant += i["answer"] == "pass"
        for st in stations:
            if not st.active:
                continue
            for d in wd.get(st.site_id, ()):
                if c.active_on(d) and c.in_controls(d):
                    out.required += 1
                    out.checked += per.get((st.id, d), 0) >= need
    return out


def _k101(e: Engine, a: Agg) -> Result:
    s = welfare_stats(e, a.window)
    res = e._pct(M.K101, s.compliant, s.applicable)
    chip = Decimal(s.checked) * HUNDRED / Decimal(s.required) if s.required else None
    res.components = [
        Component("station_days_checked_pct", "Station-days checked", "أيام المحطات المفحوصة",
                  chip, KpiKind.percentage, 1),
        Component("station_days_checked", "Checked station-days", "أيام محطات مفحوصة",
                  Decimal(s.checked), KpiKind.count_),
        Component("station_days_required", "Required station-days", "أيام محطات مطلوبة",
                  Decimal(s.required), KpiKind.count_),
    ]  # fmt: skip
    return res


# ---- K-102 acclimatisation ---------------------------------------------------------------------


def plan_stats(e: Engine, w: Window) -> tuple[int, int, Counter_t]:
    from app.services.heat.plans import completed_as_planned  # noqa: PLC0415

    hf = hfacts(e)
    if hf is None:
        return 0, 0, {}
    end = _end(e, w)
    f = e.flt
    n = ok = 0
    by_type: Counter_t = defaultdict(int)
    for p in hf.all():
        rows = list(
            hf.db.scalars(
                select(AcclimatisationPlan).where(
                    AcclimatisationPlan.project_id == p.pid,
                    AcclimatisationPlan.status == PlanStatus.completed,
                    AcclimatisationPlan.completed_on >= w.start,
                    AcclimatisationPlan.completed_on <= end,
                )
            )
        )
        sites: dict[UUID, list[UUID]] = {}
        if f.sites is not None and rows:
            sites = {
                d.id: list(d.site_ids or [])
                for d in hf.db.scalars(
                    select(Deployment).where(Deployment.id.in_([x.deployment_id for x in rows]))
                )
            }
        for x in rows:
            if x.completed_on is None or not p.cfg.in_controls(x.completed_on):
                continue
            if not f.eng_ok(x.engagement_id):
                continue
            if f.sites is not None and not set(sites.get(x.deployment_id, [])) & f.sites:
                continue
            n += 1
            ok += bool(completed_as_planned(x))
            by_type[x.plan_type.value] += 1
    return ok, n, by_type


def _k102(e: Engine, a: Agg) -> Result:
    ok, n, _ = plan_stats(e, a.window)
    return e._pct(M.K102, ok, n)


# ---- K-103 heat-illness cases ------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    entry_no: str
    d: date
    eng: UUID | None
    zone: UUID | None
    category: CaseCategory | None
    control_gap: bool
    project: UUID


def entries(e: Engine, w: Window, source_only: bool = True) -> list[Case]:
    hf = hfacts(e)
    if hf is None:
        return []
    key = ("entries", w, source_only)
    memo = _memo(e)
    if key in memo:
        res: list[Case] = memo[key]
        return res
    end = _end(e, w)
    s, t = _range(w.start, end)
    cats = {c.id: c for c in e.facts.cases}
    out: list[Case] = []
    for p in hf.all():
        stmt = select(HeatIllnessEntry).where(
            HeatIllnessEntry.project_id == p.pid,
            HeatIllnessEntry.status != HeatLogStatus.voided,
            HeatIllnessEntry.event_at >= s,
            HeatIllnessEntry.event_at < t,
        )
        if source_only:
            stmt = stmt.where(HeatIllnessEntry.source_type == HeatLogSource.injury_case)
        for x in hf.db.scalars(stmt):
            cf = cats.get(x.source_id)
            zone = x.zone_id or (cf.zone if cf else None)
            site = cf.site if cf else (p.zone_site.get(zone) if zone else None)
            if site is not None and not e.flt.site_ok(site):
                continue
            if e.flt.zone_filtered and not e.flt.zone_ok(zone, e.facts.zones):
                continue
            if not e.flt.eng_ok(x.engagement_id or (cf.eng if cf else None)):
                continue
            out.append(
                Case(
                    x.entry_no,
                    _lday(x.event_at),
                    x.engagement_id or (cf.eng if cf else None),
                    zone,
                    cf.category if cf else None,
                    bool(x.control_gap),
                    p.pid,
                )
            )
    memo[key] = out
    return out


def _k103(e: Engine, a: Agg) -> Result:
    rows = entries(e, a.window)
    n = len(rows)
    rec = sum(1 for x in rows if x.category is not None and x.category != CaseCategory.FAC)
    base = e.config.rate_base
    rate = e._rate(M.K103, n, a, base)
    rrate = e._rate(M.K103, rec, a, base)
    res = e._count(M.K103, n)
    res.warnings = list(rate.warnings)
    res.components = [
        Component("rate", "Rate per 200,000 h", "المعدل لكل 200,000 ساعة", rate.value,
                  KpiKind.rate, 2),
        Component("recordable", "Recordable (not first aid)", "قابلة للتسجيل (غير الإسعافات)",
                  Decimal(rec), KpiKind.count_),
        Component("recordable_rate", "Recordable rate", "معدل الحالات القابلة للتسجيل",
                  rrate.value, KpiKind.rate, 2),
    ]  # fmt: skip
    return res


def e17_gaps(e: Engine, w: Window) -> int:
    return sum(1 for x in entries(e, w, source_only=False) if x.control_gap)


def has_entries(e: Engine, w: Window) -> bool:
    return bool(entries(e, w, source_only=False))


engine_mod._DISPATCH.update(
    {
        M.K97: _k97,
        M.K98: _k98,
        M.K99: _k99,
        M.K100: _k100,
        M.K101: _k101,
        M.K102: _k102,
        M.K103: _k103,
    }
)
