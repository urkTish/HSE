"""Live heat band (§8.1 item 2), zone heat state (§6.3), heat duty list (§8.4) and a worker's
acclimatisation status (§6.4)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus
from app.core.clock import now
from app.core.enums import Capability
from app.core.errors import not_found
from app.core.heat_enums import (
    AcclimatisationBasis,
    BanExemptionStatus,
    HeatLogStatus,
    PlanStatus,
)
from app.models import (
    AcclimatisationPlan,
    BanExemption,
    Deployment,
    HeatIllnessEntry,
    Worker,
    Zone,
)
from app.schemas.heat import (
    AcclimatisationStatusRead,
    DutyWorker,
    HeatBoard,
    HeatDutyList,
    RegimeCell,
    ZoneHeatState,
)
from app.services.heat import common as hc
from app.services.heat import plans, state
from app.services.permissions import Grant, Principal

C = Capability
AB = AcclimatisationBasis


def active_exemptions(db: Session, project_id: uuid.UUID, zone_id: uuid.UUID, d: date) -> list[str]:
    return [
        x.exemption_no
        for x in db.scalars(
            select(BanExemption).where(
                BanExemption.project_id == project_id,
                BanExemption.status == BanExemptionStatus.active,
                BanExemption.date_from <= d,
                BanExemption.date_to >= d,
                BanExemption.zone_ids.any(zone_id),  # type: ignore[arg-type]
            )
        )
    ]


def zone_view(db: Session, project_id: uuid.UUID, z: Zone, at: datetime) -> ZoneHeatState:
    cfg = hc.cfg(db, project_id)
    t = hc.table(db)
    zs = state.zone_state(db, project_id, z.id, at)
    h = state.headline(zs, cfg)
    last = zs.latest
    return ZoneHeatState(
        zone_id=z.id,
        zone_code=z.code,
        site_id=z.site_id,
        required=z.id in hc.required_zone_ids(db, project_id),
        point_code=zs.point.point_code if zs.point else None,
        state=zs.state,
        wbgt_c=str(last.wbgt) if last else None,
        reading_no=last.reading_no if last else None,
        measured_at=last.measured_at if last else None,
        age_minutes=int((at - last.measured_at).total_seconds() // 60) if last else None,
        headline_workload=cfg.headline,
        headline_regime=h,
        rest_minutes_per_hour=hc.REST_MIN.get(h),
        cells=[
            RegimeCell(
                basis=b,
                workload=w,
                regime=(r := zs.regime(t, cfg.offset, b, w)),
                rest_minutes_per_hour=hc.REST_MIN.get(r),
            )
            for b in AB
            for w in hc.WORKLOADS
        ],
        ban_in_force=cfg.in_ban(at),
        active_exemptions=active_exemptions(db, project_id, z.id, hc.local_day(at)),
    )


def _zones(db: Session, project_id: uuid.UUID, g: Grant | None) -> list[Zone]:
    zmap = hc.zone_map(db, project_id)
    ids = set(hc.required_zone_ids(db, project_id)) | set(hc.covering(db, project_id))
    out = [zmap[i] for i in ids if i in zmap]
    if g is not None and g.site_ids is not None:
        out = [z for z in out if z.site_id in g.site_ids]
    return sorted(out, key=lambda z: z.code)


def board(db: Session, p: Principal, project_id: uuid.UUID, at: datetime | None) -> HeatBoard:
    hc.project(db, p, project_id)
    g = hc.need(p, project_id, C.heat_view, write=False)
    at = at or now()
    cfg = hc.cfg(db, project_id)
    d = hc.local_day(at)
    from app.services.heat import config  # noqa: PLC0415

    acclim = 0
    for pl in db.scalars(
        select(AcclimatisationPlan).where(
            AcclimatisationPlan.project_id == project_id,
            AcclimatisationPlan.status.in_([PlanStatus.planned, PlanStatus.active]),
            AcclimatisationPlan.trigger_date <= d,
        )
    ):
        if g.covers_engagement(pl.engagement_id):
            acclim += 1
    open_reviews = int(
        db.scalar(
            select(func.count(HeatIllnessEntry.id)).where(
                HeatIllnessEntry.project_id == project_id,
                HeatIllnessEntry.status == HeatLogStatus.open,
            )
        )
        or 0
    )
    return HeatBoard(
        project_id=project_id,
        at=at,
        in_controls_period=cfg.in_controls(d),
        ban_in_force=cfg.in_ban(at),
        zones=[zone_view(db, project_id, z, at) for z in _zones(db, project_id, g)],
        coverage_gaps=config.coverage_gaps(db, project_id),
        acclimatising_today=acclim,
        open_reviews=open_reviews,
        water_advice_en=hc.WATER[0],
        water_advice_ar=hc.WATER[1],
    )


def zone_state(db: Session, p: Principal, zone_id: uuid.UUID, at: datetime | None) -> ZoneHeatState:
    z = db.get(Zone, zone_id)
    if z is None:
        raise not_found("Zone")
    from app.models import Site  # noqa: PLC0415

    site = db.get(Site, z.site_id)
    if site is None or not p.can_see_project(site.project_id):
        raise not_found("Zone")
    hc.need(p, site.project_id, C.heat_view, write=False)
    return zone_view(db, site.project_id, z, at or now())


def duty_list(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    day: date | None,
    engagement_id: uuid.UUID | None,
) -> HeatDutyList:
    from app.services.access import common as acommon  # noqa: PLC0415
    from app.services.med import engine  # noqa: PLC0415

    hc.project(db, p, project_id)
    g = hc.need(p, project_id, C.heat_view, write=False)
    d = day or hc.local_day()
    at = now()
    names = acommon.can_see_names(p, project_id)
    deps = [
        dep
        for dep in db.scalars(
            select(Deployment).where(
                Deployment.project_id == project_id,
                Deployment.status == DeploymentStatus.mobilised,
            )
        )
        if g.covers_engagement(dep.engagement_id)
        and (engagement_id is None or dep.engagement_id == engagement_id)
        and (g.site_ids is None or set(dep.site_ids or []) & set(g.site_ids))
    ]
    acc: list[DutyWorker] = []
    for pl in db.scalars(
        select(AcclimatisationPlan)
        .where(
            AcclimatisationPlan.project_id == project_id,
            AcclimatisationPlan.status.in_([PlanStatus.planned, PlanStatus.active]),
            AcclimatisationPlan.trigger_date <= d,
            AcclimatisationPlan.deployment_id.in_([x.id for x in deps]),
        )
        .order_by(AcclimatisationPlan.plan_no)
    ):
        w = db.get(Worker, pl.worker_id)
        if w is None:
            continue
        today = next((x for x in pl.days if x.get("work_date") == d.isoformat()), None)
        today = today or next((x for x in pl.days if not x.get("work_date")), None)
        acc.append(
            DutyWorker(
                worker=acommon.worker_ref(w, names),
                plan_no=pl.plan_no,
                day_no=today["day_no"] if today else None,
                max_pct=today["max_pct"] if today else None,
                max_minutes=today["max_minutes"] if today else None,
            )
        )
    nope: list[DutyWorker] = []
    c = engine.ctx_for(db, project_id)
    facts = engine.load(db, [x.worker_id for x in deps])
    for dep in deps:
        wf = facts.get(dep.worker_id)
        if wf is None or wf.worker is None:
            continue
        if any(
            x.get("code") == "no_heat_exposure" for _r, x in engine.restrictions_in_force(c, wf, at)
        ):
            nope.append(
                DutyWorker(
                    worker=acommon.worker_ref(wf.worker, names),
                    label_en="Not for heat work — HSE check",
                    label_ar="غير مسموح بالعمل في الحرارة — مراجعة السلامة",
                )
            )
    sites = {s for x in deps for s in x.site_ids or []}
    zones = [z for z in _zones(db, project_id, g) if z.site_id in sites or not deps]
    return HeatDutyList(
        project_id=project_id,
        day=d,
        engagement_id=engagement_id,
        acclimatising=acc,
        not_for_heat_work=nope,
        zones=[zone_view(db, project_id, z, at) for z in zones],
    )


def acclimatisation_status(
    db: Session, p: Principal, project_id: uuid.UUID, worker_id: uuid.UUID, day: date | None
) -> AcclimatisationStatusRead:
    from app.services.med import common as mcommon  # noqa: PLC0415

    hc.project(db, p, project_id)
    g = hc.need(p, project_id, C.heat_view, write=False)
    dep = mcommon.deployment(db, worker_id, project_id)
    if dep is None or not g.covers_engagement(dep.engagement_id):
        raise not_found("Worker")
    d = day or hc.local_day()
    s = plans.status_of(db, dep, d)
    return AcclimatisationStatusRead(
        worker_id=worker_id,
        day=d,
        status=s.status,
        basis=s.basis,
        plan_no=s.plan.plan_no if s.plan else None,
        day_no=s.day["day_no"] if s.day else None,
    )
