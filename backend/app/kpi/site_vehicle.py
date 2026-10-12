"""Site vehicle & plant readiness KPIs K-138…K-140 (spec 7b-fleet-driver §6.2–§6.5, SK-1;
prototype). Only projects with `site_vehicles_from` set count, from that date.

- K-138: readiness at min(as_of, period end) (§4.1; Phase 4 status is the current one):
  ready ÷ site vehicles not withdrawn and not idle; chips by readiness state.
- K-139: pre-use checks and journey plans (not Cancelled) in the period; authorised = the stored
  PU-6 flag (Active covering authorisation at the time) ÷ records.
- K-140: required vehicle-days (§6.2) with a Completed check ÷ required vehicle-days; chip paper.

Contractor filter (SK-1, K-R5 descendants): the engagement operating the vehicle or (K-139)
employing the driver. Site filter: the operating engagement's sites."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.hse_enums import KpiKind, KpiMetric
from app.core.site_vehicle_enums import SiteVehCheckSource, SiteVehJourneyStatus, SiteVehReadiness
from app.kpi import engine as engine_mod
from app.kpi.engine import Agg, Component, Engine, Result
from app.kpi.followup import _memo, ffacts

M = KpiMetric
R = SiteVehReadiness
D = Decimal
CHIPS = [
    (R.docs_expired, "Documents expired", "مستندات منتهية"),
    (R.defect_hold, "Defect hold", "إيقاف بسبب عيب"),
    (R.not_certified, "Not certified (Phase 4)", "غير معتمدة (المرحلة 4)"),
    (R.idle, "Idle", "متوقفة مؤقتاً"),
    (R.withdrawn, "Withdrawn", "مسحوبة"),
]


@dataclass
class SvFacts:
    cfgs: dict[UUID, Any] = field(default_factory=dict)
    vehicles: list[Any] = field(default_factory=list)
    created: dict[UUID, date] = field(default_factory=dict)
    items: dict[UUID, Any] = field(default_factory=dict)
    holds: dict[UUID, list[Any]] = field(default_factory=dict)
    checks: list[tuple[UUID, date, bool, bool, UUID | None, UUID | None]] = field(
        default_factory=list
    )  # (vehicle, date, paper, authorised, vehicle eng, driver eng)
    plans: list[tuple[date, bool, UUID | None, UUID | None]] = field(default_factory=list)
    eng_sites: dict[UUID, list[UUID]] = field(default_factory=dict)


def facts(e: Engine) -> SvFacts | None:
    f = ffacts(e)
    if f is None:
        return None

    def load() -> SvFacts:
        from app.models import JourneyPlan, ProjectEngagement, VehicleCheck  # noqa: PLC0415
        from app.services.site_vehicle import common as c  # noqa: PLC0415

        sf = SvFacts()
        pids = [p for p in f.pids if c.cfg(f.db, p).live]
        if not pids:
            return sf
        sf.cfgs = {p: c.cfg(f.db, p) for p in pids}
        for pid in pids:
            sf.vehicles.extend(f.db.scalars(c.site_vehicle_query(pid)))
        sf.created = {v.id: c.local_day(v.created_at) for v in sf.vehicles}
        ids = [v.id for v in sf.vehicles]
        sf.items = c.phase4_items(f.db, ids)
        sf.holds = c.hold_checks(f.db, ids)
        V = VehicleCheck  # noqa: N806
        sf.checks = [
            (r.vehicle_id, r.check_date, r.source == SiteVehCheckSource.paper,
             r.driver_authorised, r.engagement_id, r.driver_engagement_id)
            for r in f.db.execute(
                select(V.vehicle_id, V.check_date, V.source, V.driver_authorised,
                       V.engagement_id, V.driver_engagement_id).where(V.project_id.in_(pids))
            )
        ]  # fmt: skip
        J = JourneyPlan  # noqa: N806
        sf.plans = [
            (r.depart_date, r.driver_authorised, r.engagement_id, r.driver_engagement_id)
            for r in f.db.execute(
                select(J.depart_date, J.driver_authorised, J.engagement_id,
                       J.driver_engagement_id).where(
                    J.project_id.in_(pids), J.status != SiteVehJourneyStatus.cancelled
                )
            )
        ]  # fmt: skip
        sf.eng_sites = {
            eid: list(sites or [])
            for eid, sites in f.db.execute(
                select(ProjectEngagement.id, ProjectEngagement.site_ids).where(
                    ProjectEngagement.project_id.in_(pids)
                )
            )
        }
        return sf

    return _memo(f, "site_vehicle", load)  # type: ignore[no-any-return]


def _site_ok(e: Engine, sf: SvFacts, eng: UUID | None) -> bool:
    if e.flt.sites is None:
        return True
    return eng is not None and any(s in e.flt.sites for s in sf.eng_sites.get(eng, []))


def _vehicle_ok(e: Engine, sf: SvFacts, v: Any) -> bool:
    return e.flt.eng_ok(v.engagement_id) and _site_ok(e, sf, v.engagement_id)


def _live_on(sf: SvFacts, v: Any, d: date) -> bool:
    cf = sf.cfgs.get(v.project_id)
    return (
        cf is not None
        and cf.live_from is not None
        and cf.live_from <= d
        and sf.created.get(v.id, d) <= d
    )


def readiness_at(e: Engine, d: date) -> list[tuple[Any, SiteVehReadiness]]:
    from app.services.site_vehicle import common as c  # noqa: PLC0415

    sf = facts(e)
    if sf is None:
        return []
    return [
        (v, c.readiness_on(v, d, sf.items.get(v.id), sf.holds.get(v.id, []))[0])
        for v in sf.vehicles
        if _live_on(sf, v, d) and _vehicle_ok(e, sf, v)
    ]


def _k138(e: Engine, a: Agg) -> Result:
    d = min(e.as_of, a.window.end)
    rs = readiness_at(e, d)
    by = Counter(r for _, r in rs)
    den = sum(n for r, n in by.items() if r not in (R.withdrawn, R.idle))
    res = e._pct(M.K138, by.get(R.ready, 0), den)
    res.components = [Component(f"readiness:{r.value}", en, ar, D(by.get(r, 0)), KpiKind.count_)
                      for r, en, ar in CHIPS]  # fmt: skip
    return res


def required_days(e: Engine, start: date, end: date) -> tuple[int, int, int]:
    """§6.2: (required vehicle-days, those with a Completed check, of which paper)."""
    from app.services.site_vehicle import vehicles as svv  # noqa: PLC0415

    sf = facts(e)
    if sf is None or end < start:
        return 0, 0, 0
    done: dict[tuple[UUID, date], bool] = {}
    for vid, d, paper, *_ in sf.checks:
        if start <= d <= end:
            done[(vid, d)] = done.get((vid, d), False) or paper
    req = ok = paper_n = 0
    for v in sf.vehicles:
        if not _vehicle_ok(e, sf, v):
            continue
        cf = sf.cfgs[v.project_id]
        d = start
        while d <= end:
            if _live_on(sf, v, d) and svv.required_on(cf, v, d):
                req += 1
                if (v.id, d) in done:
                    ok += 1
                    paper_n += int(done[(v.id, d)])
            d += timedelta(days=1)
    return req, ok, paper_n


def _k140(e: Engine, a: Agg) -> Result:
    req, ok, paper = required_days(e, a.window.start, min(e.as_of, a.window.end))
    res = e._pct(M.K140, ok, req)
    res.components = [Component("paper", "Paper", "ورقي", D(paper), KpiKind.count_)]
    return res


def _k139(e: Engine, a: Agg) -> Result:
    sf = facts(e)
    if sf is None:
        return e._pct(M.K139, 0, 0)
    start, end = a.window.start, min(e.as_of, a.window.end)

    def ok(veng: UUID | None, deng: UUID | None) -> bool:
        return (e.flt.eng_ok(veng) or e.flt.eng_ok(deng)) and _site_ok(e, sf, veng)

    checks = [x for x in sf.checks if start <= x[1] <= end and ok(x[4], x[5])]
    plans = [x for x in sf.plans if start <= x[0] <= end and ok(x[2], x[3])]
    num = sum(1 for x in checks if x[3]) + sum(1 for x in plans if x[1])
    res = e._pct(M.K139, num, len(checks) + len(plans))
    k = KpiKind.count_
    res.components = [
        Component("pre_use_checks", "Pre-use checks", "الفحوص اليومية", D(len(checks)), k),
        Component("journey_plans", "Journey plans", "خطط الرحلات", D(len(plans)), k),
    ]
    return res


engine_mod._DISPATCH.update({M.K138: _k138, M.K139: _k139, M.K140: _k140})
