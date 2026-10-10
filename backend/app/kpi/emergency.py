"""Emergency preparedness KPIs K-104…K-109 (spec 6c-emergency-drills §6.8, DP-5, EM-1).

Computed from the 6c registers through the services (programme lines, coverage, asset and team
readiness) on the request's session, reached through the per-request heat facts (same session and
project list). as_of = the period end or today, whichever is earlier. Filters: site applies to
every metric (team lines: any site of the team; project lines only without a site filter); an
engagement filter narrows K-107 to assets of those owners and is ignored by the others (site-level
records)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.emergency_enums import (
    ActiveStatus,
    CoverageState,
    DrillStatus,
    EventStatus,
    EventType,
    ProgrammeScope,
)
from app.core.hse_enums import KpiKind, KpiMetric
from app.kpi import engine as engine_mod
from app.kpi.engine import Agg, Component, Engine, Result
from app.kpi.periods import Window

UUID = uuid.UUID
M = KpiMetric


@dataclass
class EmFacts:
    db: Session
    pids: list[UUID]
    memo: dict[Any, Any] = field(default_factory=dict)
    # Plain-data results (no ORM rows) live in the Facts build's memo, shared by every request
    # that reads the same cached Facts until a fact write clears it: asset readiness alone took
    # about 0.7 s per call and the dashboard's warnings ask for it four times per request.
    shared: dict[Any, Any] = field(default_factory=dict)

    def active(self) -> list[UUID]:
        from app.services.emergency import common as ec  # noqa: PLC0415

        return [p for p in self.pids if ec.cfg(self.db, p).register_from is not None]


def efacts(e: Engine) -> EmFacts | None:
    m: EmFacts | None = getattr(e, "_em_facts", None)
    if m is None:
        hf = getattr(e.facts, "heat", None)
        if hf is None:
            return None
        m = EmFacts(hf.db, list(hf.pids), shared=e.facts.memo.setdefault("emergency", {}))
        e._em_facts = m  # type: ignore[attr-defined]
    return m


def _end(e: Engine, w: Window) -> date:
    return min(e.as_of, w.end)


_SHARED_KEYS = frozenset({"ready", "sites", "cov"})  # values hold no ORM rows (Drill etc.)


def _memo(ef: EmFacts, key: Any, fn: Any) -> Any:
    memo = ef.shared if key[0] in _SHARED_KEYS else ef.memo
    if key not in memo:
        memo[key] = fn()
    return memo[key]


# ---- K-104 ---------------------------------------------------------------------------------------


@dataclass
class ProgItem:
    pid: UUID
    drill_type: str
    site: UUID | None
    sites: tuple[UUID, ...]
    due: date
    met: bool


def _project_sites(ef: EmFacts, pid: UUID) -> tuple[UUID, ...]:
    from app.models import Site  # noqa: PLC0415

    return _memo(  # type: ignore[no-any-return]
        ef, ("sites", pid),
        lambda: tuple(ef.db.scalars(select(Site.id).where(Site.project_id == pid))),
    )  # fmt: skip


def programme_items(e: Engine, w: Window) -> list[ProgItem]:
    from app.models import RescueTeam  # noqa: PLC0415
    from app.services.emergency import programme  # noqa: PLC0415

    ef = efacts(e)
    if ef is None:
        return []
    end = _end(e, w)
    out: list[ProgItem] = []
    for pid in ef.active():
        lines = _memo(ef, ("lines", pid, end), lambda pid=pid: programme.lines(ef.db, pid, end))
        for ln in lines:
            if ln.scope == ProgrammeScope.site:
                sites: tuple[UUID, ...] = (ln.site_id,) if ln.site_id else ()
            elif ln.scope == ProgrammeScope.team:
                t = ef.db.get(RescueTeam, ln.team_id)
                sites = tuple(t.site_ids or []) if t else ()
            else:
                sites = ()
            if e.flt.sites is not None:
                # project lines (tabletop, airport exercise) count unless the filter narrows
                # the project to some of its sites (site breakdowns)
                scope_sites = sites or _project_sites(ef, pid)
                ok = any if sites else all
                if not ok(e.flt.site_ok(s) for s in scope_sites):
                    continue
            for it in ln.items:
                if w.start <= it.due <= end:
                    out.append(
                        ProgItem(pid, ln.drill_type.value, ln.site_id, sites, it.due, it.met)
                    )
    return out


def _k104(e: Engine, a: Agg) -> Result:
    items = programme_items(e, a.window)
    return e._pct(M.K104, sum(1 for x in items if x.met), len(items))


# ---- K-105 ---------------------------------------------------------------------------------------


@dataclass
class EvacStats:
    ok: int = 0
    n: int = 0
    evac: list[Decimal] = field(default_factory=list)
    head: list[Decimal] = field(default_factory=list)
    drills: list[str] = field(default_factory=list)


def evac_stats(e: Engine, w: Window) -> EvacStats:
    from app.models import Drill  # noqa: PLC0415
    from app.services.emergency import drills as dr  # noqa: PLC0415
    from app.services.emergency import programme  # noqa: PLC0415
    from app.services.emergency import reference as ref  # noqa: PLC0415

    ef = efacts(e)
    out = EvacStats()
    if ef is None:
        return out
    end = _end(e, w)
    for pid in ef.active():
        for x in ef.db.scalars(
            select(Drill).where(
                Drill.project_id == pid,
                Drill.status == DrillStatus.evaluated,
                Drill.drill_type.in_(list(ref.EVAC_TYPES)),
            )
        ):
            d = programme.drill_date(x)
            if d is None or not (w.start <= d <= end):
                continue
            if x.site_id is not None and not e.flt.site_ok(x.site_id):
                continue
            ms = dr.measures(x)
            ev, hd = ms["evac_min"], ms["headcount_min"]
            t = x.targets or {}
            out.n += 1
            if (
                ev is not None
                and hd is not None
                and ev <= Decimal(str(t.get("evacuation_min")))
                and hd <= Decimal(str(t.get("headcount_min")))
            ):
                out.ok += 1
            if ev is not None:
                out.evac.append(ev)
            if hd is not None:
                out.head.append(hd)
            out.drills.append(x.drill_no)
    return out


def _k105(e: Engine, a: Agg) -> Result:
    from app.services.emergency import common as ec  # noqa: PLC0415

    s = evac_stats(e, a.window)
    res = e._pct(M.K105, s.ok, s.n)
    res.components = [
        Component("median_evac_min", "Median evacuation minutes", "وسيط دقائق الإخلاء",
                  ec.median(s.evac), KpiKind.average, 1),
        Component("median_headcount_min", "Median headcount minutes", "وسيط دقائق الحصر",
                  ec.median(s.head), KpiKind.average, 1),
    ]  # fmt: skip
    return res


# ---- K-106 ---------------------------------------------------------------------------------------


REASONS = {
    "first_aider": ("First aiders short", "نقص المسعفين"),
    "fire_warden": ("Fire wardens short", "نقص مسؤولي الإخلاء"),
    "zone": ("Zones without a warden", "مناطق بلا مسؤول إخلاء"),
    "coordinator": ("No coordinator", "لا يوجد منسق"),
}


@dataclass
class CovStats:
    covered: int = 0
    required: int = 0
    reasons: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    short: list[str] = field(default_factory=list)


def coverage_stats(e: Engine, w: Window) -> CovStats:
    from app.services.emergency import common as ec  # noqa: PLC0415

    ef = efacts(e)
    out = CovStats()
    if ef is None:
        return out
    end = _end(e, w)
    if end < w.start:
        return out
    for pid in ef.active():
        rows = _memo(
            ef, ("cov", pid, w.start, end),
            lambda pid=pid: ec.coverage_days(ef.db, pid, w.start, end),
        )  # fmt: skip
        for x in rows:
            if not e.flt.site_ok(x.site_id) or x.result.state == CoverageState.not_required:
                continue
            out.required += 1
            if x.result.state == CoverageState.covered:
                out.covered += 1
            else:
                out.short.append(f"{ec.site_code(ef.db, x.site_id)} {x.day} {x.shift.value}")
                for r in x.result.reasons:
                    out.reasons[r] += 1
    return out


def _k106(e: Engine, a: Agg) -> Result:
    s = coverage_stats(e, a.window)
    res = e._pct(M.K106, s.covered, s.required)
    res.components = [
        Component(k, en, ar, Decimal(s.reasons.get(k, 0)), KpiKind.count_)
        for k, (en, ar) in REASONS.items()
    ]
    return res


# ---- K-107 ---------------------------------------------------------------------------------------


@dataclass
class AssetStats:
    ready: int = 0
    total: int = 0
    reasons: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_type: dict[str, list[int]] = field(default_factory=lambda: defaultdict(lambda: [0, 0]))


def asset_stats(e: Engine, w: Window) -> AssetStats:
    from app.models import EmergencyAsset  # noqa: PLC0415
    from app.services.emergency import assets  # noqa: PLC0415

    ef = efacts(e)
    out = AssetStats()
    if ef is None:
        return out
    end = _end(e, w)
    for pid in ef.active():
        rows = list(ef.db.scalars(select(EmergencyAsset).where(EmergencyAsset.project_id == pid)))
        rows = [
            x
            for x in rows
            if e.flt.site_ok(x.site_id)
            and e.flt.eng_ok(x.owner_engagement_id)
            and x.asset_type.value != "spill_kit"  # 6c v1.2: reported as 6e K-125
        ]
        by_id = {x.id: x for x in rows}
        rm = _memo(
            ef, ("ready", pid, end, e.flt.sites, e.flt.engs),
            lambda pid=pid, rows=rows: assets.ready_map(ef.db, pid, end, rows),
        )  # fmt: skip
        for aid, r in rm.items():
            out.total += 1
            bt = out.by_type[by_id[aid].asset_type.value]
            bt[1] += 1
            if r.ready:
                out.ready += 1
                bt[0] += 1
            elif r.reasons:
                out.reasons[r.reasons[0].value] += 1
    return out


def _k107(e: Engine, a: Agg) -> Result:
    from app.core.emergency_enums import NotReadyReason  # noqa: PLC0415

    s = asset_stats(e, a.window)
    res = e._pct(M.K107, s.ready, s.total)
    res.components = [
        Component(r.value, r.value, r.value, Decimal(s.reasons.get(r.value, 0)), KpiKind.count_)
        for r in NotReadyReason
    ]
    return res


# ---- K-108 ---------------------------------------------------------------------------------------


def team_stats(e: Engine, w: Window) -> tuple[int, int, list[str]]:
    from app.models import RescueTeam  # noqa: PLC0415
    from app.services.emergency import org  # noqa: PLC0415

    ef = efacts(e)
    if ef is None:
        return 0, 0, []
    end = _end(e, w)
    cur = n = 0
    bad: list[str] = []
    for pid in ef.active():
        for t in ef.db.scalars(
            select(RescueTeam).where(
                RescueTeam.project_id == pid,
                RescueTeam.status == ActiveStatus.active,
                RescueTeam.created_on <= end,
            )
        ):
            if e.flt.sites is not None and not any(e.flt.site_ok(s) for s in t.site_ids or []):
                continue
            n += 1
            if org.readiness(ef.db, t, end).current:
                cur += 1
            else:
                bad.append(t.team_code)
    return cur, n, bad


def _k108(e: Engine, a: Agg) -> Result:
    cur, n, _ = team_stats(e, a.window)
    return e._pct(M.K108, cur, n)


# ---- K-109 ---------------------------------------------------------------------------------------


@dataclass
class EventStats:
    n: int = 0
    false_alarms: int = 0
    by_type: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    first: list[Decimal] = field(default_factory=list)
    ext: list[Decimal] = field(default_factory=list)
    headcount_over: list[str] = field(default_factory=list)
    found: list[str] = field(default_factory=list)


def event_stats(e: Engine, w: Window) -> EventStats:
    from app.models import EmergencyEvent  # noqa: PLC0415
    from app.services.emergency import common as ec  # noqa: PLC0415

    ef = efacts(e)
    out = EventStats()
    if ef is None:
        return out
    end = _end(e, w)
    for pid in ef.active():
        for x in ef.db.scalars(
            select(EmergencyEvent).where(
                EmergencyEvent.project_id == pid,
                EmergencyEvent.status != EventStatus.voided,
                EmergencyEvent.raised_at >= ec.day_start(w.start),
                EmergencyEvent.raised_at < ec.day_start(end + timedelta(days=1)),
            )
        ):
            d = ec.local_day(x.raised_at)
            if not (w.start <= d <= end) or not e.flt.site_ok(x.site_id):
                continue
            out.n += 1
            out.by_type[x.event_type.value] += 1
            if x.event_type == EventType.false_alarm:
                out.false_alarms += 1
            fr = ec.minutes(x.raised_at, x.first_responder_at)
            if fr is not None:
                out.first.append(fr)
            for s in x.external_services or []:
                v = ec.minutes(ec.dt(s.get("called_at")), ec.dt(s.get("arrived_at")))
                if v is not None:
                    out.ext.append(v)
    return out


def _k109(e: Engine, a: Agg) -> Result:
    from app.services.emergency import common as ec  # noqa: PLC0415

    s = event_stats(e, a.window)
    res = e._count(M.K109, s.n)
    res.components = [
        Component("false_alarms", "False alarms", "إنذارات كاذبة", Decimal(s.false_alarms),
                  KpiKind.count_),
        Component("median_first_response_min", "Median first response (min)",
                  "وسيط الاستجابة الأولى (دقيقة)", ec.median(s.first), KpiKind.average, 1),
        Component("median_external_arrival_min", "Median external arrival (min)",
                  "وسيط وصول الجهات الخارجية (دقيقة)", ec.median(s.ext), KpiKind.average, 1),
    ]  # fmt: skip
    return res


engine_mod._DISPATCH.update(
    {M.K104: _k104, M.K105: _k105, M.K106: _k106, M.K107: _k107, M.K108: _k108, M.K109: _k109}
)


# ---- E18 / E19 inputs (§6.9) ---------------------------------------------------------------------


@dataclass
class Readiness:
    overdue_30: list[str] = field(default_factory=list)
    erp_overdue: list[str] = field(default_factory=list)
    headcount_over: list[str] = field(default_factory=list)
    found: list[str] = field(default_factory=list)


def readiness_facts(e: Engine, pid: UUID, w: Window) -> Readiness:
    """Overdue lines (> 30 days at month end), ERP overdue at month end, drills and events in
    the month with headcount over target or a `found_on_site` resolution."""
    from app.models import Drill, EmergencyEvent, Muster  # noqa: PLC0415
    from app.services.emergency import common as ec  # noqa: PLC0415
    from app.services.emergency import drills as dr  # noqa: PLC0415
    from app.services.emergency import muster as mu  # noqa: PLC0415
    from app.services.emergency import programme  # noqa: PLC0415

    ef = efacts(e)
    out = Readiness()
    if ef is None:
        return out
    end = _end(e, w)
    db = ef.db
    code = ec.pcode(db, pid)
    lines = _memo(ef, ("lines", pid, end), lambda: programme.lines(db, pid, end))
    for i, ln in enumerate(lines):
        if ln.due_by is not None and ln.status.value == "overdue" and (end - ln.due_by).days > 30:
            out.overdue_30.append(f"DPL-{code}-{i + 1:03d}")
    erp = ec.erp_in_force(db, pid)
    if ec.erp_overdue(erp, end):
        assert erp is not None  # noqa: S101
        out.erp_overdue.append(erp.erp_no)
    for x in db.scalars(
        select(Drill).where(
            Drill.project_id == pid,
            Drill.status.in_((DrillStatus.conducted, DrillStatus.evaluated)),
        )
    ):
        d = programme.drill_date(x)
        if d is None or not (w.start <= d <= end):
            continue
        hd = dr.measures(x)["headcount_min"]
        t = (x.targets or {}).get("headcount_min")
        if hd is not None and t is not None and hd > Decimal(str(t)):
            out.headcount_over.append(x.drill_no)
        m = db.get(Muster, x.muster_id) if x.muster_id else None
        if m is not None and mu.found_on_site(db, m):
            out.found.append(x.drill_no)
    target = Decimal(int(ec.cfg(db, pid)["headcount_target_minutes"]))
    for ev in db.scalars(
        select(EmergencyEvent).where(
            EmergencyEvent.project_id == pid,
            EmergencyEvent.status != EventStatus.voided,
            EmergencyEvent.raised_at >= ec.day_start(w.start),
            EmergencyEvent.raised_at < ec.day_start(end + timedelta(days=1)),
        )
    ):
        m = db.get(Muster, ev.muster_id) if ev.muster_id else None
        if m is None:
            continue
        hd = ec.minutes(m.opened_at, m.headcount_complete_at)
        if hd is not None and hd > target:
            out.headcount_over.append(ev.event_no)
        if mu.found_on_site(db, m):
            out.found.append(ev.event_no)
    return out
