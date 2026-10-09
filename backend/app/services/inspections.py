"""Inspection plans and inspections (spec 1-dashboard §3.7, §4.4, rules N-1…N-5)."""

import calendar
import uuid
from collections.abc import Iterator, Sequence
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import Select, and_, false, func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.field_enums import Rotation, TemplateKind
from app.core.hse_enums import (
    CaSourceType,
    InspectionFrequency,
    InspectionStatus,
    InspectionTimeliness,
    InspectionType,
    Weekday,
)
from app.models import (
    ChecklistResponse,
    CorrectiveAction,
    Inspection,
    InspectionPlan,
    Project,
    ProjectEngagement,
    Zone,
)
from app.schemas.inspections import (
    FindingRead,
    InspectionCancel,
    InspectionComplete,
    InspectionPage,
    InspectionPlanCreate,
    InspectionPlanPage,
    InspectionPlanRead,
    InspectionPlanUpdate,
    InspectionRead,
    InspectionResults,
    UnplannedInspectionCreate,
)
from app.services import audit, hse_settings, notify, projects
from app.services import corrective_actions as ca_svc
from app.services.common import ensure_open, invalid_transition, paginate
from app.services.hse_common import (
    Refs,
    check_engagement,
    check_site_zone,
    covers,
    make_ref,
    next_seq,
    project_today,
)
from app.services.incidents import local_date
from app.services.permissions import Principal, deny, forbidden_error

ST = InspectionStatus
HORIZON = 35  # §4.4: generated daily for the next 35 days


# ---- generation (N-1) ----------------------------------------------------------------------------


def _weekday_index(w: Weekday) -> int:
    """Python weekday() index for a Weekday value."""
    return ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].index(
        w.value
    )


def due_dates(plan: InspectionPlan, start: date, end: date) -> Iterator[date]:
    """Planned dates of a plan within [start, end]."""
    lo = max(start, plan.start_date)
    hi = min(end, plan.end_date) if plan.end_date else end
    if lo > hi:
        return
    f = plan.frequency
    if f == InspectionFrequency.once:
        if lo <= plan.start_date <= hi:
            yield plan.start_date
        return
    if f in (InspectionFrequency.monthly, InspectionFrequency.quarterly):
        # 6d §3.3: quarterly = the start date's day of month every 3 months, clamped
        step = 3 if f == InspectionFrequency.quarterly else 1
        y, m = plan.start_date.year, plan.start_date.month
        while True:
            last = calendar.monthrange(y, m)[1]
            d = date(y, m, min(plan.start_date.day, last))
            if d > hi:
                return
            if d >= lo:
                yield d
            m += step
            y, m = (y + (m - 1) // 12, (m - 1) % 12 + 1)
    d = lo
    if f == InspectionFrequency.daily:
        while d <= hi:
            yield d
            d += timedelta(days=1)
        return
    assert plan.weekday is not None  # noqa: S101
    target = _weekday_index(plan.weekday)
    first = plan.start_date + timedelta(days=(target - plan.start_date.weekday()) % 7)
    step = 14 if f == InspectionFrequency.fortnightly else 7
    if first < lo:
        first += timedelta(days=((lo - first).days + step - 1) // step * step)
    d = first
    while d <= hi:
        yield d
        d += timedelta(days=step)


def generate(db: Session, plan: InspectionPlan, today: date) -> int:
    """Create Planned instances from today to today + 35 days (idempotent)."""
    if not plan.active:
        return 0
    project = db.get(Project, plan.project_id)
    assert project is not None  # noqa: S101
    end = today + timedelta(days=HORIZON)
    existing = set(
        db.scalars(
            select(Inspection.planned_date).where(
                Inspection.plan_id == plan.id, Inspection.planned_date >= today
            )
        )
    )
    n = 0
    rot = _rotation(plan, today, end)
    for d in due_dates(plan, today, end):
        if d in existing:
            continue
        zone_id, eng_id = plan.zone_id, plan.engagement_id
        if d in rot:  # 6d ISP-2
            if plan.rotation == Rotation.zones:
                zone_id = rot[d]
            else:
                eng_id = rot[d]
        seq = next_seq(db, Inspection, project.id, d.year)
        db.add(
            Inspection(
                project_id=project.id,
                ref=make_ref("INS", project.code, d.year, seq, 5),
                year=d.year,
                seq=seq,
                plan_id=plan.id,
                inspection_type=plan.inspection_type,
                site_id=plan.site_id,
                zone_id=zone_id,
                engagement_id=eng_id,
                assignee_role=plan.assignee_role,
                assignee_user_id=plan.assignee_user_id,
                planned_date=d,
                status=ST.planned,
                findings=[],
            )
        )
        db.flush()
        n += 1
    plan.generated_until = end
    return n


def _rotation(plan: InspectionPlan, today: date, end: date) -> dict[date, uuid.UUID]:
    """6d ISP-2: instance k (planned-date order from the start) takes rotation_list[k mod n]."""
    lst = list(plan.rotation_list or [])
    if plan.rotation == Rotation.none or not lst:
        return {}
    out: dict[date, uuid.UUID] = {}
    for k, d in enumerate(due_dates(plan, plan.start_date, end)):
        if d >= today:
            out[d] = lst[k % len(lst)]
    return out


def _drop_future(db: Session, plan: InspectionPlan, today: date) -> None:
    for ins in db.scalars(
        select(Inspection).where(
            Inspection.plan_id == plan.id,
            Inspection.planned_date >= today,
            Inspection.status == ST.planned,
        )
    ):
        db.delete(ins)
    db.flush()


# ---- derived -------------------------------------------------------------------------------------


def timeliness(ins: Inspection, grace: int) -> InspectionTimeliness:
    if ins.status == ST.cancelled:
        return InspectionTimeliness.cancelled
    if ins.plan_id is None or ins.planned_date is None:
        return InspectionTimeliness.unplanned
    if ins.status == ST.missed:
        return InspectionTimeliness.missed
    if ins.status == ST.completed:
        assert ins.completed_date is not None  # noqa: S101
        if ins.completed_date <= ins.planned_date + timedelta(days=grace):
            return InspectionTimeliness.on_time
        return InspectionTimeliness.late
    return InspectionTimeliness.pending


def score(ins: Inspection) -> Decimal | None:
    if not ins.items_checked:
        return None
    v = Decimal(ins.items_compliant or 0) / Decimal(ins.items_checked) * 100
    return v.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


# ---- visibility ----------------------------------------------------------------------------------


def can_view(p: Principal, ins: Inspection) -> bool:
    if p.user.id in (ins.assignee_user_id, ins.inspector_id):
        return True
    return covers(p.grant(ins.project_id, Capability.incident_view), ins.site_id, ins.engagement_id)


def _scoped(p: Principal, project: Project) -> Select[Any]:
    In = Inspection  # noqa: N806
    stmt = select(In).where(In.project_id == project.id)
    own = or_(In.assignee_user_id == p.user.id, In.inspector_id == p.user.id)
    g = p.grant(project.id, Capability.incident_view)
    if g is None:
        return stmt.where(own)
    conds: list[Any] = []
    if g.site_ids is not None:
        conds.append(In.site_id.in_(g.site_ids) if g.site_ids else false())
    if g.engagement_ids is not None:
        engs = list(g.engagement_ids)
        conds.append(In.engagement_id.in_(engs) if engs else false())
    if conds:
        stmt = stmt.where(or_(and_(*conds), own))
    return stmt


def get_ins(db: Session, p: Principal, ins_id: uuid.UUID) -> Inspection:
    ins = db.get(Inspection, ins_id)
    if ins is None or not can_view(p, ins):
        raise deny(
            db, p, EntityType.inspection, ins_id, ins.project_id if ins else None, "Inspection"
        )
    return ins


# ---- read models ---------------------------------------------------------------------------------


def reads(db: Session, items: Sequence[Inspection]) -> list[InspectionRead]:
    if not items:
        return []
    plans = {
        pl.id: pl
        for pl in db.scalars(
            select(InspectionPlan).where(
                InspectionPlan.id.in_({i.plan_id for i in items if i.plan_id})
            )
        )
    }
    ca_ids = [uuid.UUID(f["ca_id"]) for i in items for f in (i.findings or []) if f.get("ca_id")]
    ca_refs = (
        dict(
            db.execute(
                select(CorrectiveAction.id, CorrectiveAction.ref).where(
                    CorrectiveAction.id.in_(ca_ids)
                )
            ).all()
        )
        if ca_ids
        else {}
    )
    refs = Refs(db).load(
        sites=[i.site_id for i in items],
        zones=[i.zone_id for i in items],
        engs=[i.engagement_id for i in items],
        users=[i.assignee_user_id for i in items] + [i.inspector_id for i in items],
    )
    grace = hse_settings.get(db, items[0].project_id).inspection_grace_days
    resp = {
        r.id: r
        for r in db.scalars(
            select(ChecklistResponse).where(
                ChecklistResponse.id.in_({i.response_id for i in items if i.response_id})
            )
        )
    }
    out = []
    for i in items:
        pl = plans.get(i.plan_id) if i.plan_id else None
        r = resp.get(i.response_id) if i.response_id else None
        out.append(
            InspectionRead(
                id=i.id,
                ref=i.ref,
                project_id=i.project_id,
                plan_id=i.plan_id,
                plan_name_en=pl.name_en if pl else None,
                plan_name_ar=pl.name_ar if pl else None,
                inspection_type=i.inspection_type,
                site=refs.site(i.site_id),
                zone=refs.zone(i.zone_id),
                engagement=refs.eng(i.engagement_id),
                assignee_role=i.assignee_role,
                assignee=refs.user(i.assignee_user_id),
                planned_date=i.planned_date,
                due_by=i.planned_date + timedelta(days=grace) if i.planned_date else None,
                completed_at=i.completed_at,
                inspector=refs.user(i.inspector_id),
                items_checked=i.items_checked,
                items_compliant=i.items_compliant,
                score_pct=_rscore(r) if r is not None else score(i),
                findings=[
                    FindingRead(
                        id=uuid.UUID(f["id"]),
                        description=f["description"],
                        severity=f["severity"],
                        ca_required=bool(f.get("ca_required")),
                        ca_id=uuid.UUID(f["ca_id"]) if f.get("ca_id") else None,
                        ca_ref=ca_refs.get(uuid.UUID(f["ca_id"])) if f.get("ca_id") else None,
                    )
                    for f in i.findings or []
                ],
                status=i.status,
                timeliness=timeliness(i, grace),
                cancel_reason=i.cancel_reason,
                created_at=i.created_at,
                updated_at=i.updated_at,
                response_id=i.response_id,
                result=r.result if r is not None else None,
                offline_delay_min=i.offline_delay_min,
                recorded_offline=i.offline_delay_min is not None,
                void_reason=i.void_reason,
            )
        )
    return out


def _rscore(r: ChecklistResponse) -> Decimal | None:
    """6d EXE-3: the checklist score (§6.2) of a template-based inspection."""
    if r.score_pct is None:
        return None
    return Decimal(r.score_pct).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def read(db: Session, p: Principal, ins_id: uuid.UUID) -> InspectionRead:
    return reads(db, [get_ins(db, p, ins_id)])[0]


def plan_read(db: Session, pl: InspectionPlan) -> InspectionPlanRead:
    refs = Refs(db).load(
        sites=[pl.site_id], zones=[pl.zone_id], engs=[pl.engagement_id], users=[pl.assignee_user_id]
    )
    project = db.get(Project, pl.project_id)
    assert project is not None  # noqa: S101
    nxt = db.scalar(
        select(func.min(Inspection.planned_date)).where(
            Inspection.plan_id == pl.id,
            Inspection.status == ST.planned,
            Inspection.planned_date >= project_today(project),
        )
    )
    return InspectionPlanRead(
        id=pl.id,
        project_id=pl.project_id,
        name_en=pl.name_en,
        name_ar=pl.name_ar,
        inspection_type=pl.inspection_type,
        site=refs.site(pl.site_id),
        zone=refs.zone(pl.zone_id),
        engagement=refs.eng(pl.engagement_id),
        frequency=pl.frequency,
        weekday=pl.weekday,
        start_date=pl.start_date,
        end_date=pl.end_date,
        assignee_role=pl.assignee_role,
        assignee=refs.user(pl.assignee_user_id),
        active=pl.active,
        next_planned_date=nxt,
        created_at=pl.created_at,
        updated_at=pl.updated_at,
        template_code=pl.template_code,
        rotation=pl.rotation,
        rotation_list=list(pl.rotation_list or []),
        without_checklist=without_checklist(db, pl),
    )


def without_checklist(db: Session, pl: InspectionPlan) -> bool:
    """6d ISP-1: an active plan without a template after the switch date."""
    from app.services.field import common as fc  # noqa: PLC0415

    c = fc.cfg(db, pl.project_id)
    return pl.active and not pl.template_code and c.templates_required(fc.local_day())


def _template_required() -> ApiError:
    return ApiError(
        422,
        ErrorCode.TEMPLATE_REQUIRED,
        "A checklist template is required from the project's switch date (6d ISP-1 / EXE-3).",
        "قائمة التحقق مطلوبة اعتباراً من تاريخ التحول.",
    )


def _check_plan_6d(db: Session, project: Project, pl: InspectionPlan) -> None:
    """6d §3.3: template of the plan's type, required after the switch; rotation list 2–20."""
    from app.services.field import common as fc  # noqa: PLC0415
    from app.services.field import library  # noqa: PLC0415

    if pl.template_code:
        t = library.published(db, pl.template_code)
        if (
            t is None
            or t.kind != TemplateKind.inspection
            or t.inspection_type != pl.inspection_type
            or not library.offered(t, project.id)
        ):
            raise ApiError(
                422,
                ErrorCode.TEMPLATE_NOT_APPLICABLE,
                "Use a Published inspection template of the plan's inspection type.",
                "استخدم نموذج تفتيش منشوراً من نوع الخطة.",
            )
    elif fc.cfg(db, project.id).templates_required(fc.local_day()):
        raise _template_required()
    if pl.rotation == Rotation.none:
        pl.rotation_list = []
        return
    lst = list(pl.rotation_list or [])
    if not 2 <= len(lst) <= 20 or len(set(lst)) != len(lst):
        raise validation_error("rotation_list", "Give 2–20 distinct entries (ISP-2).")
    for x in lst:
        if pl.rotation == Rotation.zones:
            z = db.get(Zone, x)
            ok = z is not None and z.site_id == pl.site_id
        else:
            e = db.get(ProjectEngagement, x)
            ok = e is not None and e.project_id == project.id
        if not ok:
            raise validation_error("rotation_list", "Zones of the plan site or engagements.")


# ---- plans ---------------------------------------------------------------------------------------


def _plan(db: Session, p: Principal, plan_id: uuid.UUID) -> InspectionPlan:
    pl = db.get(InspectionPlan, plan_id)
    if pl is None or not covers(p.grant(pl.project_id, Capability.incident_view), pl.site_id, None):
        raise deny(
            db, p, EntityType.inspection_plan, plan_id, pl.project_id if pl else None, "Plan"
        )
    return pl


def get_plan(db: Session, p: Principal, plan_id: uuid.UUID) -> InspectionPlanRead:
    return plan_read(db, _plan(db, p, plan_id))


def create_plan(
    db: Session, p: Principal, project_id: uuid.UUID, body: InspectionPlanCreate
) -> InspectionPlanRead:
    project = projects.get_visible(db, p, project_id)
    ensure_open(project)
    g = p.require(project.id, Capability.inspection_plan_manage)
    if not g.covers_site(body.site_id):
        raise forbidden_error()
    check_site_zone(db, project, body.site_id, body.zone_id)
    if body.engagement_id:
        check_engagement(db, project, body.engagement_id)
    pl = InspectionPlan(project_id=project.id, **body.model_dump())
    _check_plan_6d(db, project, pl)
    db.add(pl)
    db.flush()
    generate(db, pl, project_today(project))
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.inspection_plan,
        entity_id=pl.id,
        project_id=project.id,
        after=body.model_dump(mode="json"),
    )
    return plan_read(db, pl)


def update_plan(
    db: Session, p: Principal, plan_id: uuid.UUID, body: InspectionPlanUpdate
) -> InspectionPlanRead:
    pl = _plan(db, p, plan_id)
    project = db.get(Project, pl.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    p.require(project.id, Capability.inspection_plan_manage)
    ch = body.changes()
    if "zone_id" in ch:
        check_site_zone(db, project, pl.site_id, ch["zone_id"])
    if ch.get("engagement_id"):
        check_engagement(db, project, ch["engagement_id"])
    before = {k: getattr(pl, k) for k in ch}
    for k, v in ch.items():
        setattr(pl, k, v)
    if pl.end_date and pl.end_date < pl.start_date:
        raise validation_error("end_date", "end_date must be on or after start_date")
    if pl.frequency in (InspectionFrequency.weekly, InspectionFrequency.fortnightly) and (
        pl.weekday is None
    ):
        raise validation_error("weekday", "weekday is required for weekly/fortnightly plans")
    _check_plan_6d(db, project, pl)
    pl.updated_at = now()
    today = project_today(project)
    _drop_future(db, pl, today)  # N-1: only future planned instances change
    generate(db, pl, today)
    audit.record(
        db,
        AuditAction.update,
        p.actor(project.id),
        entity_type=EntityType.inspection_plan,
        entity_id=pl.id,
        project_id=project.id,
        before=before,
        after=ch,
    )
    return plan_read(db, pl)


def list_plans(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    active: bool | None,
    inspection_type: InspectionType | None,
    site_id: uuid.UUID | None,
) -> InspectionPlanPage:
    project = projects.get_visible(db, p, project_id)
    g = p.grant(project.id, Capability.incident_view)
    if g is None:
        raise forbidden_error()
    P = InspectionPlan  # noqa: N806
    stmt = select(P).where(P.project_id == project.id)
    if g.site_ids is not None:
        stmt = stmt.where(P.site_id.in_(g.site_ids) if g.site_ids else false())
    if active is not None:
        stmt = stmt.where(P.active.is_(active))
    if inspection_type:
        stmt = stmt.where(P.inspection_type == inspection_type)
    if site_id:
        stmt = stmt.where(P.site_id == site_id)
    items, total = paginate(db, stmt.order_by(P.name_en), page, page_size)
    return InspectionPlanPage(
        items=[plan_read(db, x) for x in items], total=total, page=page, page_size=page_size
    )


# ---- inspections ---------------------------------------------------------------------------------


def _findings(
    db: Session, p: Principal, project: Project, ins: Inspection, body: InspectionResults
) -> list[dict[str, Any]]:
    out = []
    for i, f in enumerate(body.findings):
        ca_id = f.ca_id
        if f.ca_required and ca_id is None and f.corrective_action is None:
            raise ApiError(
                422,
                ErrorCode.FINDING_CA_REQUIRED,
                f"Finding {i + 1} requires a corrective action before completing (N-4).",
                "الملاحظة تتطلب إجراءً تصحيحياً قبل الإنجاز.",
            )
        if ca_id is not None:
            ca = db.get(CorrectiveAction, ca_id)
            if ca is None or ca.project_id != project.id:
                raise validation_error(f"findings[{i}].ca_id", "Unknown corrective action.")
        elif f.corrective_action is not None:
            g = p.require(project.id, Capability.ca_create)
            if not covers(g, ins.site_id, None):
                raise forbidden_error()
            ca, _ = ca_svc.new_ca(db, p, project, f.corrective_action, CaSourceType.inspection, ins)
            ca_id = ca.id
        out.append(
            {
                "id": str(uuid.uuid4()),
                "description": f.description,
                "severity": f.severity.value,
                "ca_required": f.ca_required,
                "ca_id": str(ca_id) if ca_id else None,
            }
        )
    return out


def _record(
    db: Session, p: Principal, project: Project, ins: Inspection, body: InspectionResults
) -> None:
    if body.completed_at > now() + timedelta(minutes=5):
        raise validation_error("completed_at", "The completion time cannot be in the future.")
    from app.services.field import common as fc  # noqa: PLC0415

    if fc.cfg(db, project.id).templates_required(local_date(project, body.completed_at)):
        raise _template_required()  # 6d EXE-3: completed through a checklist submission
    ins.completed_at = body.completed_at
    ins.completed_date = local_date(project, body.completed_at)
    ins.inspector_id = p.user.id
    ins.items_checked = body.items_checked
    ins.items_compliant = body.items_compliant
    ins.status = ST.completed
    ins.findings = _findings(db, p, project, ins, body)
    ins.updated_at = now()


def complete(
    db: Session, p: Principal, ins_id: uuid.UUID, body: InspectionComplete
) -> InspectionRead:
    ins = get_ins(db, p, ins_id)
    project = db.get(Project, ins.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    p.ensure_writer()
    if ins.status not in (ST.planned, ST.missed):
        raise invalid_transition("Inspection", ins.status, ST.completed)
    g = p.grant(project.id, Capability.inspection_record)
    if p.user.id != ins.assignee_user_id and not covers(g, ins.site_id, ins.engagement_id):
        raise forbidden_error()
    src = ins.status
    _record(db, p, project, ins, body)
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(project.id),
        entity_type=EntityType.inspection,
        entity_id=ins.id,
        project_id=project.id,
        before={"status": src},
        after={"status": ST.completed},
    )
    return reads(db, [ins])[0]


def create_unplanned(
    db: Session, p: Principal, project_id: uuid.UUID, body: UnplannedInspectionCreate
) -> InspectionRead:
    project = projects.get_visible(db, p, project_id)
    ensure_open(project)
    g = p.require(project.id, Capability.inspection_record)
    if not covers(g, body.site_id, body.engagement_id if g.engagement_ids is not None else None):
        raise forbidden_error()
    check_site_zone(db, project, body.site_id, body.zone_id)
    if body.engagement_id:
        check_engagement(db, project, body.engagement_id)
    year = local_date(project, body.completed_at).year
    seq = next_seq(db, Inspection, project.id, year)
    ins = Inspection(
        project_id=project.id,
        ref=make_ref("INS", project.code, year, seq, 5),
        year=year,
        seq=seq,
        inspection_type=body.inspection_type,
        site_id=body.site_id,
        zone_id=body.zone_id,
        engagement_id=body.engagement_id,
        status=ST.completed,
        findings=[],
    )
    db.add(ins)
    db.flush()
    _record(db, p, project, ins, body)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.inspection,
        entity_id=ins.id,
        project_id=project.id,
        details={"unplanned": True},
    )
    return reads(db, [ins])[0]


def cancel(db: Session, p: Principal, ins_id: uuid.UUID, body: InspectionCancel) -> InspectionRead:
    ins = get_ins(db, p, ins_id)
    project = db.get(Project, ins.project_id)
    assert project is not None  # noqa: S101
    ensure_open(project)
    p.require(project.id, Capability.inspection_plan_manage)
    if ins.status not in (ST.planned, ST.missed):
        raise invalid_transition("Inspection", ins.status, ST.cancelled)
    if ins.status == ST.missed and not p.is_manager:
        raise forbidden_error("Cancelling a missed inspection needs the HSE Manager (N-3).")
    src = ins.status
    ins.status = ST.cancelled
    ins.cancel_reason = body.reason
    ins.updated_at = now()
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(project.id),
        entity_type=EntityType.inspection,
        entity_id=ins.id,
        project_id=project.id,
        before={"status": src},
        after={"status": ST.cancelled},
        details={"reason": body.reason},
    )
    return reads(db, [ins])[0]


def mark_missed(db: Session, project: Project, today: date) -> list[Inspection]:
    """§4.4 job: Planned → Missed when today > planned_date + grace."""
    grace = hse_settings.get(db, project.id).inspection_grace_days
    rows = list(
        db.scalars(
            select(Inspection).where(
                Inspection.project_id == project.id,
                Inspection.status == ST.planned,
                Inspection.planned_date < today - timedelta(days=grace),
            )
        )
    )
    for ins in rows:
        ins.status = ST.missed
        ins.missed_at = now()
        if ins.assignee_user_id:
            notify.notify(
                db,
                [ins.assignee_user_id],
                NotificationKind.inspection_missed,
                f"{ins.ref} was missed",
                f"فات موعد {ins.ref}",
                entity_type=EntityType.inspection,
                entity_id=ins.id,
                project_id=project.id,
            )
    db.flush()
    return rows


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    *,
    statuses: list[InspectionStatus] | None = None,
    timeliness_: list[InspectionTimeliness] | None = None,
    plan_id: uuid.UUID | None = None,
    inspection_type: InspectionType | None = None,
    site_ids: list[uuid.UUID] | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    assigned_to_me: bool = False,
    planned_from: date | None = None,
    planned_to: date | None = None,
    sort: str = "-planned_date",
) -> InspectionPage:
    project = projects.get_visible(db, p, project_id)
    In = Inspection  # noqa: N806
    stmt = _scoped(p, project)
    if statuses:
        stmt = stmt.where(In.status.in_(statuses))
    if timeliness_:
        grace = hse_settings.get(db, project.id).inspection_grace_days
        due = In.planned_date + grace
        conds = {
            InspectionTimeliness.cancelled: In.status == ST.cancelled,
            InspectionTimeliness.unplanned: and_(In.plan_id.is_(None), In.status != ST.cancelled),
            InspectionTimeliness.missed: and_(In.plan_id.is_not(None), In.status == ST.missed),
            InspectionTimeliness.pending: and_(In.plan_id.is_not(None), In.status == ST.planned),
            InspectionTimeliness.on_time: and_(
                In.plan_id.is_not(None), In.status == ST.completed, In.completed_date <= due
            ),
            InspectionTimeliness.late: and_(
                In.plan_id.is_not(None), In.status == ST.completed, In.completed_date > due
            ),
        }
        stmt = stmt.where(or_(*[conds[t] for t in timeliness_]))
    if plan_id:
        stmt = stmt.where(In.plan_id == plan_id)
    if inspection_type:
        stmt = stmt.where(In.inspection_type == inspection_type)
    if site_ids:
        stmt = stmt.where(In.site_id.in_(site_ids))
    if engagement_ids:
        stmt = stmt.where(In.engagement_id.in_(engagement_ids))
    if assigned_to_me:
        stmt = stmt.where(In.assignee_user_id == p.user.id)
    if planned_from:
        stmt = stmt.where(In.planned_date >= planned_from)
    if planned_to:
        stmt = stmt.where(In.planned_date <= planned_to)
    order: Any = {
        "planned_date": In.planned_date.asc().nulls_last(),
        "-planned_date": In.planned_date.desc().nulls_last(),
        "completed_at": In.completed_at.asc().nulls_last(),
        "-completed_at": In.completed_at.desc().nulls_last(),
    }[sort]
    items, total = paginate(db, stmt.order_by(order, In.ref), page, page_size)
    return InspectionPage(items=reads(db, list(items)), total=total, page=page, page_size=page_size)
