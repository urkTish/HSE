"""Drills (spec 6c-emergency-drills §3.11, §4.5, DR-1…DR-9, §6.4): planning, unannounced
visibility, start (muster, PE-2 suspensions, DR-8), timings, conduct, evaluation with findings and
CAs, the result, cancel and void."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.emergency_enums import (
    CheckAnswer,
    DrillAction,
    DrillResult,
    DrillStatus,
    DrillType,
    FindingCategory,
    FindingSeverity,
    MusterSource,
    MusterStatus,
    TeamType,
)
from app.core.enums import AuditAction, Capability, EntityType, ProjectType, SiteSide
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.ptw_enums import StatusReason
from app.models import Drill, Muster, RescueTeam, Site, User
from app.schemas.emergency import (
    DrillCreate,
    DrillMeasures,
    DrillPage,
    DrillRead,
    DrillTransition,
    DrillUpdate,
    EvaluationInput,
)
from app.services.common import invalid_transition, paginate
from app.services.emergency import common as ec
from app.services.emergency import muster as mu
from app.services.emergency import reference as ref
from app.services.hse_common import make_ref
from app.services.permissions import Principal, build_principal, forbidden_error

C = Capability
DT = DrillType
DS = DrillStatus
LATE = timedelta(minutes=15)
TEAM_OF = {DT.cse_rescue: TeamType.confined_space, DT.height_rescue: TeamType.height}
# §6.4: measures required by the type → (measure key, target key)
REQUIRED: dict[DrillType, tuple[tuple[str, str], ...]] = {
    DT.evacuation_full: (("evac_min", "evacuation_min"), ("headcount_min", "headcount_min")),
    DT.evacuation_partial: (("evac_min", "evacuation_min"), ("headcount_min", "headcount_min")),
    DT.shelter_in_place: (("headcount_min", "headcount_min"),),
    DT.medical_response: (("response_min", "response_min"),),
    DT.cse_rescue: (("rescue_min", "rescue_min"),),
    DT.height_rescue: (("rescue_min", "rescue_min"),),
    DT.tabletop: (),
    DT.airport_exercise: (),
}
# a failed critical criterion becomes a critical finding of this category (DR-6)
DC_CATEGORY = {
    "DC01": FindingCategory.communication,
    "DC02": FindingCategory.behaviour,
    "DC03": FindingCategory.route_infrastructure,
    "DC04": FindingCategory.behaviour,
    "DC05": FindingCategory.behaviour,
    "DC06": FindingCategory.route_infrastructure,
    "DC07": FindingCategory.plan_deficiency,
    "DC08": FindingCategory.communication,
    "DC09": FindingCategory.training_competence,
    "DC10": FindingCategory.equipment,
    "DC11": FindingCategory.external_coordination,
    "DC12": FindingCategory.behaviour,
}
CA_DAYS = {FindingSeverity.critical: 3, FindingSeverity.major: 7, FindingSeverity.minor: 14}
ORDER = (
    ("alarm_at", "evacuation_complete_at"),
    ("evacuation_complete_at", "all_clear_at"),
    ("alarm_at", "headcount_complete_at"),
    ("headcount_complete_at", "all_clear_at"),
    ("alarm_at", "all_clear_at"),
    ("alarm_at", "first_responder_at"),
    ("alarm_at", "casualty_reached_at"),
    ("casualty_reached_at", "casualty_recovered_at"),
)


# ---- measures and result (§6.4) ------------------------------------------------------------------


def measures(d: Drill) -> dict[str, Decimal | None]:
    tl = d.timeline or {}
    a = ec.dt(tl.get("alarm_at"))
    return {
        "evac_min": ec.minutes(a, ec.dt(tl.get("evacuation_complete_at"))),
        "headcount_min": ec.minutes(a, ec.dt(tl.get("headcount_complete_at"))),
        "response_min": ec.minutes(a, ec.dt(tl.get("first_responder_at"))),
        "rescue_min": ec.minutes(a, ec.dt(tl.get("casualty_recovered_at"))),
    }


def findings(d: Drill) -> list[dict[str, Any]]:
    ev = d.evaluation or {}
    return list(ev.get("findings") or []) or list(ev.get("auto_findings") or [])


def result_of(db: Session, d: Drill) -> DrillResult:
    crit = any(f.get("severity") == FindingSeverity.critical.value for f in findings(d))
    if d.drill_type == DT.tabletop:
        return DrillResult.unsatisfactory if crit else DrillResult.satisfactory
    ms = measures(d)
    for mk, tk in REQUIRED[d.drill_type]:
        v, t = ms[mk], (d.targets or {}).get(tk)
        if v is None or (t is not None and v > Decimal(str(t))):
            return DrillResult.unsatisfactory
    if crit:
        return DrillResult.unsatisfactory
    m = db.get(Muster, d.muster_id) if d.muster_id else None
    if m is not None:
        if mu.found_on_site(db, m):
            return DrillResult.unsatisfactory
        if any(e.state == mu.ES.unaccounted for e in mu.entries(db, m)):
            return DrillResult.unsatisfactory
    return DrillResult.satisfactory


def check_order(tl: dict[str, Any]) -> None:
    for a, b in ORDER:
        x, y = ec.dt(tl.get(a)), ec.dt(tl.get(b))
        if x is not None and y is not None and y < x:
            raise ec.err(
                422,
                ErrorCode.TIMELINE_ORDER,
                f"{b} cannot be before {a} (DR-5).",
                "ترتيب التوقيتات غير صحيح.",
                field=f"timeline.{b}",
            )


# ---- visibility (DR-2) ---------------------------------------------------------------------------


def hidden(d: Drill) -> bool:
    return not d.announced and d.status == DS.planned


def sees_hidden(p: Principal, project_id: uuid.UUID, site_id: uuid.UUID | None) -> bool:
    """Holders of 184 for the site (S scope) and the HSE Manager."""
    if p.is_manager:
        return True
    g = p.grant(project_id, C.drill_plan)
    return g is not None and g.engagement_ids is None and g.covers_site(site_id)


def _drill(db: Session, p: Principal, drill_id: uuid.UUID) -> Drill:
    d = db.get(Drill, drill_id)
    if d is None or not p.can_see_project(d.project_id):
        raise not_found("Drill")
    ec.need(p, d.project_id, C.emergency_view, write=False)
    if hidden(d) and not sees_hidden(p, d.project_id, d.site_id):
        raise not_found("Drill")
    return d


def drill_read(db: Session, d: Drill, warnings: list[Any] | None = None) -> DrillRead:
    m = db.get(Muster, d.muster_id) if d.muster_id else None
    t = db.get(RescueTeam, d.team_id) if d.team_id else None
    ms = measures(d)
    return DrillRead(
        id=d.id,
        drill_no=d.drill_no,
        project_id=d.project_id,
        drill_type=d.drill_type,
        scenario_code=d.scenario_code,
        site_id=d.site_id,
        site_code=ec.site_code(db, d.site_id),
        zone_ids=list(d.zone_ids or []),
        team_id=d.team_id,
        team_code=t.team_code if t else None,
        planned_at=d.planned_at,
        shift=d.shift,
        announced=d.announced,
        suspend_permits=d.suspend_permits,
        conductor=ec.user_ref(db, d.conductor_user_id),
        evaluators=[ec.user_ref(db, u) for u in d.evaluator_user_ids or []],
        plan_note=d.plan_note,
        rescue_plan_ref=d.rescue_plan_ref,
        timeline=dict(d.timeline or {}),
        targets=dict(d.targets or {}),
        measures=DrillMeasures(**{k: ec.mstr(v) for k, v in ms.items()}),
        muster_id=d.muster_id,
        muster_no=m.muster_no if m else None,
        external_participation=list(d.external_participation or []),
        airport_exercise_ref=d.airport_exercise_ref,
        evaluation=dict(d.evaluation) if d.evaluation else None,
        result=d.result,
        late_entry=d.late_entry,
        status=d.status,
        status_reason=d.status_reason,
        warnings=warnings or [],
    )


def list_drills(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    site_id: uuid.UUID | None,
    drill_type: list[DrillType] | None,
    status: list[DrillStatus] | None,
    page: int,
    size: int,
) -> DrillPage:
    ec.project(db, p, project_id)
    ec.need(p, project_id, C.emergency_view, write=False)
    q = select(Drill).where(Drill.project_id == project_id)
    if site_id is not None:
        q = q.where(Drill.site_id == site_id)
    if drill_type:
        q = q.where(Drill.drill_type.in_(drill_type))
    if status:
        q = q.where(Drill.status.in_(status))
    if not p.is_manager:
        g = p.grant(project_id, C.drill_plan)
        visible = or_(Drill.announced.is_(True), Drill.status != DS.planned)
        if g is not None and g.engagement_ids is None:
            if g.site_ids is None:
                visible = None  # type: ignore[assignment]
            else:
                visible = or_(visible, Drill.site_id.in_(list(g.site_ids)))
        if visible is not None:
            q = q.where(visible)
    rows, total = paginate(db, q.order_by(Drill.planned_at.desc()), page, size)
    return DrillPage(
        items=[drill_read(db, d) for d in rows], total=total, page=page, page_size=size
    )


def read_drill(db: Session, p: Principal, drill_id: uuid.UUID) -> DrillRead:
    return drill_read(db, _drill(db, p, drill_id))


# ---- plan (DR-1, DR-3) ---------------------------------------------------------------------------


def _holds(db: Session, project_id: uuid.UUID, user_id: uuid.UUID, cap: Capability) -> bool:
    u = db.get(User, user_id)
    if u is None:
        return False
    return build_principal(db, u, None).grant(project_id, cap) is not None


def create_drill(db: Session, p: Principal, project_id: uuid.UUID, body: DrillCreate) -> DrillRead:
    pr = ec.project(db, p, project_id)
    g = ec.need(p, project_id, C.drill_plan)
    e = ec.erp_in_force(db, project_id)
    if e is None:
        raise ec.err(
            422,
            ErrorCode.ERP_NOT_APPROVED,
            "Drills are planned for a scenario of the Approved ERP (DR-1).",
            "يتم تخطيط التمارين لسيناريو من خطة الطوارئ المعتمدة.",
        )
    if body.scenario_code not in {s.get("scenario_code") for s in e.scenarios or []}:
        raise validation_error("scenario_code", "Choose a scenario of the Approved ERP.")
    scope = ref.DRILL_TYPES[body.drill_type][3]
    site: Site | None = None
    team: RescueTeam | None = None
    if scope == "team":
        if body.team_id is None:
            raise validation_error("team_id", "Choose the rescue team.")
        team = db.get(RescueTeam, body.team_id)
        if (
            team is None
            or team.project_id != project_id
            or team.team_type != TEAM_OF[body.drill_type]
        ):
            raise validation_error("team_id", "Choose an active rescue team of the drill's type.")
        sid = body.site_id or (team.site_ids[0] if team.site_ids else None)
        site = ec.site_or_422(db, project_id, sid) if sid else None
    elif scope == "site":
        if body.site_id is None:
            raise validation_error("site_id", "Choose the site.")
        site = ec.site_or_422(db, project_id, body.site_id)
    elif body.site_id is not None:
        site = ec.site_or_422(db, project_id, body.site_id)
    if site is not None and not ec.site_in_scope(db, g, project_id, site.id):
        raise forbidden_error()
    zones = list(body.zone_ids or [])
    if body.drill_type == DT.evacuation_partial and not zones:
        raise validation_error("zone_ids", "Choose the zones of the partial evacuation.")
    if zones:
        if site is None:
            raise validation_error("zone_ids", "Zones need the drill's site.")
        ec.zones_of_site(db, site.id, zones)
    at = now()
    if not body.announced and body.planned_at < at:
        raise validation_error("planned_at", "An unannounced drill is planned in the future.")
    if (
        pr.project_type == ProjectType.airport
        and site is not None
        and site.site_side == SiteSide.airside
        and body.drill_type in ref.EVAC_TYPES
        and not (body.plan_note or "").strip()
    ):
        raise validation_error(
            "plan_note", "Airside evacuation drills need the airport coordination ref (DR-1)."
        )
    if body.drill_type == DT.airport_exercise and not body.airport_exercise_ref:
        raise validation_error("airport_exercise_ref", "Give the airport operator's ref (DR-9).")
    evaluators = list(dict.fromkeys(body.evaluator_user_ids))
    if not [u for u in evaluators if u != body.conductor_user_id]:
        raise ec.err(
            422,
            ErrorCode.SOD_CONFLICT,
            "At least one evaluator must be someone other than the conductor (DR-3).",
            "يجب أن يكون أحد المقيّمين غير منفذ التمرين.",
            field="evaluator_user_ids",
        )
    for u in evaluators:
        if not _holds(db, project_id, u, C.drill_evaluate):
            raise validation_error("evaluator_user_ids", "Evaluators must hold capability 186.")
    if db.get(User, body.conductor_user_id) is None:
        raise validation_error("conductor_user_id", "Choose the conductor.")
    suspend = (
        body.suspend_permits
        if body.suspend_permits is not None
        else body.drill_type in ref.MUSTER_TYPES
    )
    year = ec.local_day(body.planned_at).year
    seq = ec.next_seq(db, Drill, project_id, year)
    d = Drill(
        id=uuid.uuid4(),
        year=year,
        seq=seq,
        drill_no=make_ref("DRL", pr.code, year, seq, 3),
        project_id=project_id,
        drill_type=body.drill_type,
        scenario_code=body.scenario_code,
        site_id=site.id if site else None,
        zone_ids=zones,
        team_id=team.id if team else None,
        planned_at=body.planned_at,
        shift=body.shift,
        announced=body.announced,
        suspend_permits=suspend,
        conductor_user_id=body.conductor_user_id,
        evaluator_user_ids=evaluators,
        plan_note=body.plan_note,
        rescue_plan_ref=body.rescue_plan_ref,
        timeline={},
        targets={},
        external_participation=[],
        airport_exercise_ref=body.airport_exercise_ref,
        status=DS.planned,
        late_entry=False,
        alerts_sent=[],
        created_by_user_id=p.user.id,
    )
    db.add(d)
    db.flush()
    ec.record(db, p, AuditAction.create, EntityType.emergency_drill, d, project_id)
    return drill_read(db, d)


# ---- timings (DR-5) ------------------------------------------------------------------------------


def _runner(db: Session, p: Principal, d: Drill) -> None:
    g = ec.need(p, d.project_id, C.drill_run)
    if d.site_id is not None and not ec.site_in_scope(db, g, d.project_id, d.site_id):
        raise forbidden_error()


def update_drill(db: Session, p: Principal, drill_id: uuid.UUID, body: DrillUpdate) -> DrillRead:
    d = _drill(db, p, drill_id)
    _runner(db, p, d)
    if d.status not in (DS.planned, DS.in_progress, DS.conducted):
        raise invalid_transition("Drill", d.status, "updated")
    before = {"timeline": dict(d.timeline or {})}
    ch = body.model_dump(exclude_unset=True)
    if body.timeline is not None:
        if d.status == DS.planned:
            raise invalid_transition("Drill", d.status, "timed")
        tl = dict(d.timeline or {})
        for k, v in body.timeline.model_dump(exclude_unset=True).items():
            if k == "alarm_at":
                continue  # set by Start
            tl[k] = v.isoformat() if v is not None else None
        check_order(tl)
        d.timeline = tl
    if body.external_participation is not None:
        d.external_participation = [
            {
                "agency": x.agency.value,
                "ref": x.ref,
                "arrived_at": x.arrived_at.isoformat() if x.arrived_at else None,
            }
            for x in body.external_participation
        ]
    for k in ("rescue_plan_ref", "plan_note"):
        if k in ch:
            setattr(d, k, ch[k])
    db.flush()
    ec.audit_change(
        db, p, EntityType.emergency_drill, d.id, d.project_id, before,
        {"timeline": dict(d.timeline or {})},
    )  # fmt: skip
    return drill_read(db, d)


# ---- transitions (§4.5) --------------------------------------------------------------------------


def _targets(db: Session, d: Drill) -> dict[str, Any]:
    c = ec.cfg(db, d.project_id)
    out: dict[str, Any] = {
        "evacuation_min": int(c["evacuation_target_minutes"]),
        "headcount_min": int(c["headcount_target_minutes"]),
        "response_min": int(c["response_target_minutes"]),
        "rescue_min": None,
    }
    if d.drill_type in TEAM_OF:
        out["rescue_min"] = int(c["rescue_target_minutes"][TEAM_OF[d.drill_type].value])
    return out


def start(db: Session, p: Principal | None, d: Drill, alarm: datetime, at: datetime) -> None:
    """DR-4: alarm_at; late entry when more than 15 min in the past (count mode, no
    suspensions, no live alerts); the muster (MU-1); PE-2 suspensions; DR-8."""
    from app.services.emergency import org  # noqa: PLC0415
    from app.services.emergency import ptw as eptw  # noqa: PLC0415

    d.late_entry = alarm < at - LATE
    d.timeline = {**(d.timeline or {}), "alarm_at": alarm.isoformat()}
    d.targets = _targets(db, d)
    d.status = DS.in_progress
    db.flush()
    if d.drill_type in ref.MUSTER_TYPES and d.site_id is not None:
        zones = list(d.zone_ids or []) if d.drill_type == DT.evacuation_partial else None
        m = mu.open_muster(
            db, d.project_id, MusterSource.drill, d.id, d.site_id, zones, alarm,
            d.late_entry, p.user.id if p else None,
        )  # fmt: skip
        d.muster_id = m.id
    if d.suspend_permits and not d.late_entry and d.site_id is not None:
        zones = list(d.zone_ids or []) or None
        eptw.suspend_for(
            db, d.project_id, d.site_id, zones, StatusReason.emergency_drill, d.drill_no, alarm
        )
    if d.team_id is not None:
        t = db.get(RescueTeam, d.team_id)
        if t is not None and not org.equipment_ready(db, t, ec.local_day(alarm)):
            mu.add_auto_finding(
                d, FindingCategory.equipment, FindingSeverity.major,
                f"Rescue equipment of {t.team_code} not ready at the alarm (DR-8)",
                f"معدات الإنقاذ للفريق {t.team_code} غير جاهزة عند الإنذار", t.team_code,
            )  # fmt: skip
    db.flush()


def conduct(db: Session, d: Drill, at: datetime) -> None:
    m = db.get(Muster, d.muster_id) if d.muster_id else None
    if m is not None and m.status == MusterStatus.open:
        mu.sync_exits(db, m, at)
        mu.reconcile(db, m)
    tl = d.timeline or {}
    if m is not None and m.status not in (MusterStatus.reconciled, MusterStatus.closed):
        raise ec.err(
            409,
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            "The muster is not reconciled: account for or resolve every entry (MU-7).",
            "لم تتم مطابقة التجميع: يجب حصر كل الأشخاص أو تسوية حالتهم.",
        )
    need = list(ref.DRILL_TYPES[d.drill_type][4])
    if d.drill_type in ref.MUSTER_TYPES and m is None:
        need = [k for k in need if k != "headcount_complete_at"]
    if d.drill_type == DT.tabletop:
        need = []
    missing = [k for k in need if not tl.get(k)]
    if missing:
        raise ec.err(
            422,
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            "Record the timings required by the drill type: " + ", ".join(missing),
            "سجّل التوقيتات المطلوبة لنوع التمرين.",
            field="timeline",
            missing=missing,
        )
    check_order(tl)
    end = ec.dt(tl.get("all_clear_at")) or ec.dt(tl.get("casualty_recovered_at")) or at
    if m is not None:
        mu.close(db, m, end)
    d.conducted_at = ec.dt(tl.get("alarm_at")) or end
    d.status = DS.conducted
    db.flush()


def transition_drill(
    db: Session, p: Principal, drill_id: uuid.UUID, body: DrillTransition
) -> DrillRead:
    d = _drill(db, p, drill_id)
    before = {"status": d.status.value}
    at = now()
    a = body.action
    if a == DrillAction.start:
        _runner(db, p, d)
        if d.status != DS.planned:
            raise invalid_transition("Drill", d.status, DS.in_progress)
        alarm = body.alarm_at or at
        if alarm > at + timedelta(minutes=2):
            raise validation_error("alarm_at", "The alarm time cannot be in the future.")
        start(db, p, d, alarm, at)
    elif a == DrillAction.conduct:
        _runner(db, p, d)
        if d.status != DS.in_progress:
            raise invalid_transition("Drill", d.status, DS.conducted)
        conduct(db, d, at)
    elif a == DrillAction.cancel:
        g = ec.need(p, d.project_id, C.drill_plan)
        if d.site_id is not None and not ec.site_in_scope(db, g, d.project_id, d.site_id):
            raise forbidden_error()
        if d.status != DS.planned:
            raise invalid_transition("Drill", d.status, DS.cancelled)
        d.status_reason = ec.reason(body.reason, 20)
        d.status = DS.cancelled
    else:
        p.require(d.project_id, C.emergency_void)
        if d.status not in (DS.in_progress, DS.conducted, DS.evaluated):
            raise invalid_transition("Drill", d.status, DS.voided)
        d.status_reason = ec.reason(body.reason, 20)
        d.status = DS.voided
        m = db.get(Muster, d.muster_id) if d.muster_id else None
        if m is not None and m.status != MusterStatus.voided:
            m.status = MusterStatus.voided
            m.closed_at = m.closed_at or at
    db.flush()
    ec.audit_change(
        db, p, EntityType.emergency_drill, d.id, d.project_id, before,
        {"status": d.status.value, "reason": d.status_reason},
    )  # fmt: skip
    return drill_read(db, d)


# ---- evaluation (DR-6, DR-7) ---------------------------------------------------------------------


def evaluation_due(db: Session, d: Drill) -> date | None:
    if d.conducted_at is None:
        return None
    days = int(ec.cfg(db, d.project_id)["drill_evaluation_days"])
    return ec.local_day(d.conducted_at) + timedelta(days=days)


def apply_evaluation(
    db: Session,
    d: Drill,
    criteria: dict[str, str],
    user_findings: list[dict[str, Any]],
    by: uuid.UUID | None,
    at: datetime,
    summary_en: str | None = None,
    summary_ar: str | None = None,
) -> None:
    ev = dict(d.evaluation or {})
    out: list[dict[str, Any]] = [dict(x) for x in ev.get("auto_findings") or []]
    for code, ans in criteria.items():
        if ans == CheckAnswer.fail.value and ref.DC(code) in ref.CRITICAL_CRITERIA:
            out.append(
                {
                    "category": DC_CATEGORY[code].value,
                    "severity": FindingSeverity.critical.value,
                    "description_en": f"{code} failed: {ref.CRITERIA[ref.DC(code)][0]}",
                    "description_ar": f"{code}: {ref.CRITERIA[ref.DC(code)][1]}",
                    "ref": code,
                    "auto": True,
                    "engagement_id": None,
                }
            )
    out.extend(user_findings)
    site = d.site_id
    if site is None and d.team_id is not None:
        t = db.get(RescueTeam, d.team_id)
        site = t.site_ids[0] if t and t.site_ids else None
    for f in out:
        sev = FindingSeverity(f["severity"])
        if sev == FindingSeverity.minor and not f.get("create_ca"):
            f["ca_id"] = None
            continue
        if site is None:
            f["ca_id"] = None
            continue
        eng = uuid.UUID(f["engagement_id"]) if f.get("engagement_id") else None
        prio = {FindingSeverity.critical: "critical", FindingSeverity.major: "high"}.get(
            sev, "medium"
        )
        ca = ec.make_ca(
            db, d.project_id, d.id, site, None, eng,
            f"{d.drill_no}: {f['description_en']}"[:150],
            f"Drill finding ({f['category']}, {sev.value}): {f['description_en']}",
            ec.local_day(at) + timedelta(days=CA_DAYS[sev]), by, priority=prio,
        )  # fmt: skip
        f["ca_id"] = str(ca.id)
        f["ca_ref"] = ca.ref
    if any(f["category"] == FindingCategory.plan_deficiency.value for f in out):
        ec.add_review_trigger(db, d.project_id, "drill_finding", d.drill_no)
    ev.update(
        criteria=[{"criterion": k, "answer": v} for k, v in criteria.items()],
        findings=out,
        summary_en=summary_en,
        summary_ar=summary_ar,
        evaluated_by=str(by) if by else None,
        evaluated_at=at.isoformat(),
    )
    d.evaluation = ev
    d.status = DS.evaluated
    d.result = result_of(db, d)
    db.flush()


def evaluate(db: Session, p: Principal, drill_id: uuid.UUID, body: EvaluationInput) -> DrillRead:
    d = _drill(db, p, drill_id)
    p.require(d.project_id, C.drill_evaluate)
    if p.user.id not in (d.evaluator_user_ids or []) and not p.is_manager:
        raise forbidden_error("Only an evaluator of the drill evaluates it (DR-6).")
    if d.status != DS.conducted:
        raise invalid_transition("Drill", d.status, DS.evaluated)
    relevant = [c.value for c in ref.RELEVANT_DC[d.drill_type]]
    given = {x.criterion.value: x.answer.value for x in body.criteria}
    missing = [c for c in relevant if c not in given]
    if missing:
        raise validation_error(
            "criteria", "Answer every criterion of the type: " + ", ".join(missing)
        )
    criteria = {c: given[c] for c in relevant}
    uf = []
    for i, f in enumerate(body.findings):
        if f.engagement_id is not None:
            ec.engagement_on(db, d.project_id, f.engagement_id, f"findings.{i}.engagement_id")
        uf.append(
            {
                "category": f.category.value,
                "severity": f.severity.value,
                "description_en": f.description_en,
                "description_ar": f.description_ar,
                "engagement_id": str(f.engagement_id) if f.engagement_id else None,
                "create_ca": f.create_ca,
                "auto": False,
            }
        )
    at = now()
    apply_evaluation(db, d, criteria, uf, p.user.id, at, body.summary_en, body.summary_ar)
    ec.audit_change(
        db, p, EntityType.emergency_drill, d.id, d.project_id, {"status": "conducted"},
        {"status": "evaluated", "result": d.result.value if d.result else None},
    )  # fmt: skip
    return drill_read(db, d)
