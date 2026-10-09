"""Acclimatisation plans (spec 6b-heat-stress §3.6, §4.2, §5.5 AP-1…AP-9, §6.4).

Worked days come from Phase 2 gate checks (AP-4). Plans are created and advanced by the gate
hook (`on_gate`), the 6a hooks (`on_hold_released`, `on_assessment`) and the daily job
(`run_daily`), which also catches up anything the hooks missed."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus, GateDirection, GateResult
from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.heat_enums import (
    AcclimatisationBasis,
    AcclimatisationStatus,
    PlanStatus,
    PlanTriggerKind,
    PlanType,
)
from app.models import (
    AcclimatisationPlan,
    Deployment,
    GateCheck,
    HealthProfile,
    MedicalSettings,
    Worker,
)
from app.schemas.heat import (
    PlanCancel,
    PlanDay,
    PlanDayConfirm,
    PlanPage,
    PlanRead,
    PlanTrigger,
    PriorExperienceInput,
)
from app.services.common import invalid_transition, paginate
from app.services.heat import common as hc
from app.services.permissions import Principal

C = Capability
PS = PlanStatus
AS = AcclimatisationStatus
PT = PlanType
K = NotificationKind
OPEN = (PS.planned, PS.waiting_restriction, PS.active)
LIVE_GATE = (GateResult.GRANTED, GateResult.GRANTED_WITH_WARNING)
# 6a v1.1 §11.5 item 1: heat_outdoor trade defaults (read here; 6a's own default list unchanged)
HEAT_TRADES = frozenset(
    {"labourer", "steel_fixer", "steel_erector", "scaffolder", "rigger", "mason", "carpenter",
     "flagman", "welder"}
)  # fmt: skip
NEW_WORKER_LOOKBACK_DAYS = 60


# ---- population and worked days ------------------------------------------------------------------


def in_population(db: Session, dep: Deployment) -> bool:
    """AP-1: deployments with exposure group heat_outdoor (6a profile, else trade defaults)."""
    pr = db.scalar(select(HealthProfile).where(HealthProfile.deployment_id == dep.id))
    if pr is not None and "heat_outdoor" in (pr.exposure_groups or []):
        return True
    s = db.get(MedicalSettings, dep.project_id)
    extra = set((s.exposure_group_trade_defaults or {}).get("heat_outdoor", [])) if s else set()
    return dep.trade.value in HEAT_TRADES | extra


def worked_days(
    db: Session, worker_id: uuid.UUID, project_id: uuid.UUID, d0: date, d1: date
) -> list[date]:
    """AP-4: local dates with an `in` gate check GRANTED / GRANTED_WITH_WARNING or admitted
    despite denial, on the project."""
    rows = db.execute(
        select(GateCheck.local_date, GateCheck.result, GateCheck.admitted_despite_denial).where(
            GateCheck.worker_id == worker_id,
            GateCheck.project_id == project_id,
            GateCheck.direction == GateDirection.in_,
            GateCheck.local_date >= d0,
            GateCheck.local_date <= d1,
        )
    )
    return sorted({d for d, r, adm in rows if r in LIVE_GATE or adm})


def _schedule(cfg: hc.Cfg, t: PT) -> list[int]:
    s = cfg["acclimatisation_schedules"]
    return list(s["new_worker"] if t == PT.new_worker else s["returner"])


def _minutes(cfg: hc.Cfg, pct: int) -> int:
    v = Decimal(pct) * cfg.dec("standard_shift_hours") * 60 / 100
    return int(v.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _days(cfg: hc.Cfg, sched: list[int], keep: list[dict[str, Any]] | None = None) -> list[Any]:
    out = []
    for i, pct in enumerate(sched, start=1):
        old = keep[i - 1] if keep and i - 1 < len(keep) else {}
        out.append(
            {
                "day_no": i,
                "work_date": old.get("work_date"),
                "max_pct": pct,
                "max_minutes": _minutes(cfg, pct),
                "confirmed_by": old.get("confirmed_by"),
                "confirmed_at": old.get("confirmed_at"),
                "followed": old.get("followed"),
                "note": old.get("note"),
            }
        )
    return out


# ---- creation and progression --------------------------------------------------------------------


def open_plans(db: Session, dep_id: uuid.UUID) -> list[AcclimatisationPlan]:
    return list(
        db.scalars(
            select(AcclimatisationPlan)
            .where(
                AcclimatisationPlan.deployment_id == dep_id, AcclimatisationPlan.status.in_(OPEN)
            )
            .order_by(AcclimatisationPlan.created_at)
        )
    )


def _end(db: Session, plan: AcclimatisationPlan, status: PlanStatus, reason: str | None) -> None:
    before = {"status": plan.status.value}
    plan.status, plan.status_reason, plan.ended_at = status, reason, now()
    db.flush()
    hc.record(
        db, None, AuditAction.status_change, EntityType.acclimatisation_plan, plan,
        plan.project_id, before,
    )  # fmt: skip


def create(
    db: Session,
    dep: Deployment,
    t: PT,
    trigger: dict[str, Any],
    trigger_date: date,
    status: PlanStatus = PS.planned,
) -> AcclimatisationPlan:
    cfg = hc.cfg(db, dep.project_id)
    for old in open_plans(db, dep.id):
        _end(db, old, PS.cancelled, "superseded")  # AP-7
    y = trigger_date.year
    seq = hc.next_seq(db, AcclimatisationPlan, dep.project_id, y)
    sched = _schedule(cfg, t)
    plan = AcclimatisationPlan(
        id=uuid.uuid4(),
        year=y,
        seq=seq,
        plan_no=f"ACP-{hc.pcode(db, dep.project_id)}-{y}-{seq:05d}",
        project_id=dep.project_id,
        deployment_id=dep.id,
        worker_id=dep.worker_id,
        engagement_id=dep.engagement_id,
        plan_type=t,
        trigger={**trigger, "on": trigger_date.isoformat()},
        trigger_date=trigger_date,
        schedule_pct=sched,
        days=_days(cfg, sched),
        status=status,
        alerts_sent=[],
    )
    db.add(plan)
    db.flush()
    hc.record(db, None, AuditAction.create, EntityType.acclimatisation_plan, plan, dep.project_id)
    users = hc.reps(db, dep.project_id, dep.engagement_id)
    label = PT.returner if t == PT.post_heat_illness else t  # P6b-3 in the alert
    w = db.get(Worker, dep.worker_id)
    hc.send(
        db,
        users,
        K.heat_plan_created,
        f"Acclimatisation plan {plan.plan_no} ({label.value}) for {w.worker_no if w else ''}",
        f"خطة تأقلم {plan.plan_no} للعامل {w.worker_no if w else ''}",
        dep.project_id,
        EntityType.acclimatisation_plan,
        plan.id,
    )
    return plan


def advance(db: Session, plan: AcclimatisationPlan, today: date) -> None:
    """Assign worked days, start, complete (after the last day ends) or interrupt (AP-5)."""
    if plan.status not in (PS.planned, PS.active):
        return
    cfg = hc.cfg(db, plan.project_id)
    gap = int(cfg["acclimatisation_restart_gap_days"])
    wd = worked_days(db, plan.worker_id, plan.project_id, plan.trigger_date, today)
    days = [dict(x) for x in plan.days]
    prev: date | None = None
    i = 0
    interrupted_at: date | None = None
    for dd in wd:
        if i >= len(days):
            break
        if prev is not None and (dd - prev).days - 1 >= gap:
            interrupted_at = dd
            break
        days[i]["work_date"] = dd.isoformat()
        prev = dd
        i += 1
    if (
        interrupted_at is None
        and prev is not None
        and i < len(days)
        and (today - prev).days - 1 >= gap
    ):
        interrupted_at = today
    plan.days = days
    if i > 0 and plan.status == PS.planned:
        plan.status = PS.active
    if interrupted_at is not None:
        _end(db, plan, PS.interrupted, None)
        dep = db.get(Deployment, plan.deployment_id)
        if dep is not None:
            nxt = create(
                db,
                dep,
                plan.plan_type,
                {"kind": plan.trigger.get("kind"), "ref": plan.plan_no},
                interrupted_at,
            )
            advance(db, nxt, today)
        return
    if i == len(days) and prev is not None and prev < today:
        plan.status = PS.completed
        plan.completed_on = prev
        plan.ended_at = now()
    db.flush()


def _had_recent_deployment(db: Session, dep: Deployment, d: date) -> bool:
    lo = d - timedelta(days=NEW_WORKER_LOOKBACK_DAYS)
    for o in db.scalars(select(Deployment).where(Deployment.worker_id == dep.worker_id)):
        if o.id == dep.id or o.mobilised_on is None or o.mobilised_on >= d:
            continue
        if o.demobilised_on is None or o.demobilised_on >= lo:
            return True
    return False


def on_worked_day(db: Session, dep: Deployment, d: date) -> AcclimatisationPlan | None:
    """AP-1 (a) and (b) at a worked day d, then progress the open plans."""
    cfg = hc.cfg(db, dep.project_id)
    if not (cfg.active_on(d) and in_population(db, dep)):
        return None
    plans = open_plans(db, dep.id)
    for pl in plans:
        advance(db, pl, d)
    if any(pl.status in OPEN for pl in plans) or not cfg.in_controls(d):
        return None
    prior = worked_days(
        db, dep.worker_id, dep.project_id, d - timedelta(days=400), d - timedelta(days=1)
    )
    last = prior[-1] if prior else None
    if last is None:
        if _had_recent_deployment(db, dep, d):
            return None
        pl = create(db, dep, PT.new_worker, {"kind": PlanTriggerKind.mobilisation.value}, d)
    elif (d - last).days - 1 >= int(cfg["deacclimatisation_days"]):
        if status_on(db, dep, d - timedelta(days=1))[0] != AcclimatisationStatus.acclimatised:
            return None
        pl = create(db, dep, PT.returner, {"kind": PlanTriggerKind.absence.value}, d)
    else:
        return None
    advance(db, pl, d)
    return pl


def on_gate(db: Session, row: Any) -> None:
    if row.deployment_id is None or not hc.enabled(db, row.project_id):
        return
    dep = db.get(Deployment, row.deployment_id)
    if dep is not None:
        on_worked_day(db, dep, row.local_date)


def period_start(db: Session, project_id: uuid.UUID, d: date) -> int:
    """AP-1 (d): on the first day of the controls period, population deployments with < 7 worked
    days in the 14 days before get a plan (returner schedule)."""
    cfg = hc.cfg(db, project_id)
    if not cfg.active_on(d) or d != cfg.controls_window(d.year)[0]:
        return 0
    n = 0
    for dep in db.scalars(
        select(Deployment).where(
            Deployment.project_id == project_id, Deployment.status == DeploymentStatus.mobilised
        )
    ):
        if not in_population(db, dep) or open_plans(db, dep.id):
            continue
        wd = worked_days(
            db, dep.worker_id, project_id, d - timedelta(days=14), d - timedelta(days=1)
        )
        if len(wd) < 7:
            create(db, dep, PT.period_start, {"kind": PlanTriggerKind.period_start.value}, d)
            n += 1
    return n


# ---- 6a hooks (AP-1c, AP-6) ----------------------------------------------------------------------


def heat_blocked(db: Session, worker_id: uuid.UUID, project_id: uuid.UUID, at: datetime) -> bool:
    """AP-6: `no_heat_exposure` in force, or no in-force GEN-FIT line."""
    from app.services.med import engine  # noqa: PLC0415

    c = engine.ctx_for(db, project_id)
    wf = engine.load_one(db, worker_id)
    if restricted(db, worker_id, project_id, at):
        return True
    rows = wf.lines.get("GEN-FIT", [])
    gov = engine.governing(rows, at)
    return gov is None or not engine.in_force(c, gov, at, gov)


def restricted(db: Session, worker_id: uuid.UUID, project_id: uuid.UUID, at: datetime) -> bool:
    """`no_heat_exposure` in force on the worker's governing lines (6a §6.2)."""
    from app.services.med import engine  # noqa: PLC0415

    cache: dict[Any, bool] = db.info.setdefault("heat_restricted", {})
    key = (worker_id, at)
    if key not in cache:
        c = engine.ctx_for(db, project_id)
        wf = engine.load_one(db, worker_id)
        cache[key] = any(
            x.get("code") == "no_heat_exposure" for _r, x in engine.restrictions_in_force(c, wf, at)
        )
    return cache[key]


def on_hold_released(db: Session, h: Any) -> None:
    """AP-1 (c): a released 6a hold with reason heat_illness → post_heat_illness plan."""
    if h.reason.value != "heat_illness" or not hc.enabled(db, h.project_id):
        return
    from app.services.med import common as mcommon  # noqa: PLC0415

    dep = mcommon.deployment(db, h.worker_id, h.project_id)
    cfg = hc.cfg(db, h.project_id)
    at = h.released_at or now()
    if dep is None or cfg.register_from is None:
        return
    blocked = heat_blocked(db, h.worker_id, h.project_id, at)
    create(
        db,
        dep,
        PT.post_heat_illness,
        {"kind": PlanTriggerKind.hold_release.value, "ref": h.hold_no},
        hc.local_day(at),
        PS.waiting_restriction if blocked else PS.planned,
    )


def on_assessment(db: Session, worker_id: uuid.UUID) -> None:
    """AP-6: a new accepted assessment may release a waiting plan."""
    db.info.pop("heat_restricted", None)
    for plan in db.scalars(
        select(AcclimatisationPlan).where(
            AcclimatisationPlan.worker_id == worker_id,
            AcclimatisationPlan.status == PS.waiting_restriction,
        )
    ):
        at = now()
        if not heat_blocked(db, worker_id, plan.project_id, at):
            before = {"status": plan.status.value}
            plan.status = PS.planned
            plan.trigger_date = hc.local_day(at)
            db.flush()
            hc.record(
                db, None, AuditAction.status_change, EntityType.acclimatisation_plan, plan,
                plan.project_id, before,
            )  # fmt: skip


# ---- status (§6.4) -------------------------------------------------------------------------------


@dataclass
class Status:
    status: AcclimatisationStatus
    plan: AcclimatisationPlan | None = None
    day: dict[str, Any] | None = None

    @property
    def basis(self) -> AcclimatisationBasis:
        return (
            AcclimatisationBasis.acclimatised
            if self.status
            in (AcclimatisationStatus.acclimatised, AcclimatisationStatus.not_applicable)
            else AcclimatisationBasis.unacclimatised
        )


def status_of(db: Session, dep: Deployment, d: date) -> Status:
    if not in_population(db, dep):
        return Status(AcclimatisationStatus.not_applicable)
    plans = list(
        db.scalars(
            select(AcclimatisationPlan)
            .where(AcclimatisationPlan.deployment_id == dep.id)
            .order_by(AcclimatisationPlan.created_at.desc())
        )
    )
    for pl in plans:
        if pl.trigger_date > d or pl.status == PS.cancelled:
            continue
        if pl.status == PS.waiting_restriction:
            return Status(AcclimatisationStatus.not_acclimatised, pl)
        live = pl.status in (PS.planned, PS.active)
        done = pl.status == PS.completed and pl.completed_on is not None and pl.completed_on >= d
        if live or done:
            day = next((x for x in pl.days if x.get("work_date") == d.isoformat()), None)
            if day is None and live:
                day = next((x for x in pl.days if not x.get("work_date")), None)
            return Status(AcclimatisationStatus.acclimatising, pl, day)
        if pl.status == PS.interrupted:
            return Status(AcclimatisationStatus.not_acclimatised, pl)
        break
    return Status(AcclimatisationStatus.acclimatised)


def status_on(db: Session, dep: Deployment, d: date) -> tuple[AcclimatisationStatus, Status]:
    s = status_of(db, dep, d)
    return s.status, s


# ---- daily job -----------------------------------------------------------------------------------


def run_daily(db: Session, project_id: uuid.UUID, today: date) -> None:
    cfg = hc.cfg(db, project_id)
    if cfg.register_from is None:
        return
    period_start(db, project_id, today)
    y0, y1 = cfg.controls_window(today.year)
    for plan in db.scalars(
        select(AcclimatisationPlan).where(
            AcclimatisationPlan.project_id == project_id, AcclimatisationPlan.status.in_(OPEN)
        )
    ):
        dep = db.get(Deployment, plan.deployment_id)
        if dep is not None and dep.status == DeploymentStatus.demobilised:
            _end(db, plan, PS.cancelled, "demobilised")
            continue
        if (
            plan.status == PS.planned
            and plan.plan_type != PT.post_heat_illness
            and not (y0 <= today <= y1)
            and plan.trigger_date <= y1 + timedelta(days=1)
            and today > y1
        ):
            _end(db, plan, PS.cancelled, "season_ended")
            continue
        advance(db, plan, today)
    # catch-up triggers for yesterday's worked days
    d = today - timedelta(days=1)
    for dep_id in set(
        db.scalars(
            select(GateCheck.deployment_id).where(
                GateCheck.project_id == project_id,
                GateCheck.local_date == d,
                GateCheck.direction == GateDirection.in_,
                GateCheck.deployment_id.is_not(None),
            )
        )
    ):
        dep = db.get(Deployment, dep_id)
        if dep is not None and worked_days(db, dep.worker_id, project_id, d, d):
            on_worked_day(db, dep, d)
    unconfirmed_alerts(db, project_id, now())


def unconfirmed_alerts(db: Session, project_id: uuid.UUID, at: datetime) -> int:
    """AP-8: a worked plan day not confirmed within `plan_confirmation_hours` after it ends
    alerts the Contractor HSE Rep, then the HSE Officer after a further 24 h."""
    cfg = hc.cfg(db, project_id)
    hours = int(cfg["plan_confirmation_hours"])
    n = 0
    for plan in db.scalars(
        select(AcclimatisationPlan).where(
            AcclimatisationPlan.project_id == project_id,
            AcclimatisationPlan.status.in_([PS.active, PS.completed, PS.interrupted]),
        )
    ):
        sent = list(plan.alerts_sent or [])
        for dd in plan.days:
            if not dd.get("work_date") or dd.get("confirmed_at"):
                continue
            wd = date.fromisoformat(dd["work_date"])
            due = hc.day_start(wd + timedelta(days=1)) + timedelta(hours=hours)
            for step, when, users in (
                ("rep", due, hc.reps(db, project_id, plan.engagement_id)),
                ("officer", due + timedelta(hours=24), hc.officers(db, project_id)),
            ):
                key = f"{dd['day_no']}:{step}"
                if at >= when and key not in sent:
                    sent.append(key)
                    n += hc.send(
                        db,
                        users,
                        K.heat_plan_unconfirmed,
                        f"Acclimatisation plan {plan.plan_no} day {dd['day_no']} ({wd}) is not "
                        "confirmed",
                        f"لم يتم تأكيد اليوم {dd['day_no']} من خطة التأقلم {plan.plan_no}",
                        project_id,
                        EntityType.acclimatisation_plan,
                        plan.id,
                    )
        plan.alerts_sent = sent
    db.flush()
    return n


# ---- API -----------------------------------------------------------------------------------------


def completed_as_planned(plan: AcclimatisationPlan) -> bool | None:
    if plan.status != PS.completed:
        return None
    return all(d.get("confirmed_at") and d.get("followed") is True for d in plan.days)


def _tier(db: Session, p: Principal | None, plan: AcclimatisationPlan) -> int:
    from app.services.med import common as mcommon  # noqa: PLC0415

    return mcommon.tier(p, plan.project_id, db.get(Deployment, plan.deployment_id))


def plan_read(db: Session, p: Principal | None, plan: AcclimatisationPlan) -> PlanRead:
    from app.services.access import common as acommon  # noqa: PLC0415

    w = db.get(Worker, plan.worker_id)
    masked = plan.plan_type == PT.post_heat_illness and _tier(db, p, plan) < 2  # P6b-3
    trig = dict(plan.trigger or {})
    trigger = (
        PlanTrigger(kind=PlanTriggerKind.absence, ref=None, on=plan.trigger_date)
        if masked
        else PlanTrigger(
            kind=PlanTriggerKind(trig.get("kind", "manual")),
            ref=trig.get("ref"),
            on=plan.trigger_date,
        )
    )
    return PlanRead(
        id=plan.id,
        plan_no=plan.plan_no,
        project_id=plan.project_id,
        deployment_id=plan.deployment_id,
        worker=acommon.worker_ref(w, acommon.can_see_names(p, plan.project_id)),  # type: ignore[arg-type]
        engagement_id=plan.engagement_id,
        plan_type=PT.returner if masked else plan.plan_type,
        trigger=trigger,
        schedule_pct=list(plan.schedule_pct or []),
        prior_heat_experience=plan.prior_heat_experience,
        days=[
            PlanDay(
                day_no=d["day_no"],
                work_date=date.fromisoformat(d["work_date"]) if d.get("work_date") else None,
                max_pct=d["max_pct"],
                max_minutes=d["max_minutes"],
                confirmed_by=hc.user_ref(db, uuid.UUID(d["confirmed_by"]))
                if d.get("confirmed_by")
                else None,
                confirmed_at=datetime.fromisoformat(d["confirmed_at"])
                if d.get("confirmed_at")
                else None,
                followed=d.get("followed"),
                note=d.get("note"),
            )
            for d in plan.days
        ],
        status=plan.status,
        status_reason=plan.status_reason,
        completed_as_planned=completed_as_planned(plan),
    )


def _visible(db: Session, p: Principal, plan_id: uuid.UUID, cap: Capability) -> AcclimatisationPlan:
    plan = db.get(AcclimatisationPlan, plan_id)
    if plan is None or not p.can_see_project(plan.project_id):
        raise not_found("Acclimatisation plan")
    g = p.grant(plan.project_id, cap)
    if g is None or not g.covers_engagement(plan.engagement_id):
        raise not_found("Acclimatisation plan")
    dep = db.get(Deployment, plan.deployment_id)
    if g.site_ids is not None and not (set(dep.site_ids or []) & set(g.site_ids) if dep else False):
        raise not_found("Acclimatisation plan")
    return plan


def list_plans(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: list[PlanStatus] | None,
    plan_type: PlanType | None,
    worker_id: uuid.UUID | None,
    engagement_id: uuid.UUID | None,
) -> PlanPage:
    hc.project(db, p, project_id)
    g = hc.need(p, project_id, C.heat_view, write=False)
    stmt = select(AcclimatisationPlan).where(AcclimatisationPlan.project_id == project_id)
    if status:
        stmt = stmt.where(AcclimatisationPlan.status.in_(status))
    if plan_type:
        stmt = stmt.where(AcclimatisationPlan.plan_type == plan_type)
    if worker_id:
        stmt = stmt.where(AcclimatisationPlan.worker_id == worker_id)
    if engagement_id:
        stmt = stmt.where(AcclimatisationPlan.engagement_id == engagement_id)
    if g.engagement_ids is not None:
        stmt = stmt.where(AcclimatisationPlan.engagement_id.in_(list(g.engagement_ids)))
    stmt = stmt.order_by(AcclimatisationPlan.plan_no.desc())
    rows, total = paginate(db, stmt, page, page_size)
    return PlanPage(
        items=[plan_read(db, p, x) for x in rows], total=total, page=page, page_size=page_size
    )


def read_plan(db: Session, p: Principal, plan_id: uuid.UUID) -> PlanRead:
    return plan_read(db, p, _visible(db, p, plan_id, C.heat_view))


def prior_experience(
    db: Session, p: Principal, plan_id: uuid.UUID, body: PriorExperienceInput
) -> PlanRead:
    plan = _visible(db, p, plan_id, C.heat_plan_manage)
    p.require(plan.project_id, C.heat_plan_manage)
    text = hc.reason(body.text, 20, "text")
    if plan.plan_type != PT.new_worker or plan.status not in OPEN:
        raise invalid_transition("Acclimatisation plan", plan.plan_type, "prior_heat_experience")
    today = hc.local_day()
    if any(
        d.get("work_date") and d["day_no"] >= 2 and date.fromisoformat(d["work_date"]) <= today
        for d in plan.days
    ):
        raise hc.err(
            422,
            ErrorCode.TOO_LATE_TO_CHANGE,
            "Prior heat experience can be recorded only before day 2 (AP-3).",
            "يمكن تسجيل الخبرة السابقة قبل اليوم الثاني فقط.",
            field="text",
        )
    cfg = hc.cfg(db, plan.project_id)
    before = {"schedule_pct": list(plan.schedule_pct)}
    plan.prior_heat_experience = {"by": str(p.user.id), "text": text, "at": now().isoformat()}
    plan.schedule_pct = _schedule(cfg, PT.returner)
    plan.days = _days(cfg, plan.schedule_pct, plan.days)
    plan.updated_by_user_id = p.user.id
    db.flush()
    hc.record(
        db, p, AuditAction.update, EntityType.acclimatisation_plan, plan, plan.project_id, before
    )
    return plan_read(db, p, plan)


def confirm_day(
    db: Session, p: Principal, plan_id: uuid.UUID, day_no: int, body: PlanDayConfirm
) -> PlanRead:
    plan = _visible(db, p, plan_id, C.heat_plan_manage)
    p.require(plan.project_id, C.heat_plan_manage)
    days = [dict(x) for x in plan.days]
    d = next((x for x in days if x["day_no"] == day_no), None)
    if d is None:
        raise not_found("Plan day")
    if not d.get("work_date") or date.fromisoformat(d["work_date"]) > hc.local_day():
        raise validation_error("day_no", "Only a worked day can be confirmed.")
    note = (body.note or "").strip() or None
    if not body.followed and (note is None or len(note) < 10):
        raise validation_error("note", "Explain in at least 10 characters why it was not followed.")
    d.update(
        confirmed_by=str(p.user.id),
        confirmed_at=now().isoformat(),
        followed=body.followed,
        note=note,
    )
    plan.days = days
    db.flush()
    hc.record(db, p, AuditAction.update, EntityType.acclimatisation_plan, plan, plan.project_id)
    return plan_read(db, p, plan)


def cancel(db: Session, p: Principal, plan_id: uuid.UUID, body: PlanCancel) -> PlanRead:
    plan = _visible(db, p, plan_id, C.heat_plan_manage)
    p.require(plan.project_id, C.heat_plan_manage)
    why = hc.reason(body.reason, 20)
    if plan.status not in OPEN:
        raise invalid_transition("Acclimatisation plan", plan.status, PS.cancelled)
    _end(db, plan, PS.cancelled, why)
    return plan_read(db, p, plan)
