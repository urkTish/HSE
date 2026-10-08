"""Scaffold register, tags, inspections and stickers (spec 4-third-party-cert §3.8, §4.6, §6.4,
SF-1…SF-7, DF-3 for scaffolds)."""

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    HookKind,
    HookSubjectType,
    OpsEventType,
    QrKind,
    QrTokenStatus,
    RequirementStatus,
)
from app.core.cert_enums import (
    ChecklistItemResult,
    ReinspectionReason,
    ScaffoldChecklistItem,
    ScaffoldInspectionResult,
    ScaffoldInspectionType,
    ScaffoldStatus,
    ScaffoldTagStatus,
    ScaffoldType,
)
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.models import OpsEvent, ProjectEngagement, Scaffold, ScaffoldInspection, Worker, Zone
from app.schemas.equipment import EquipmentStickerRead, StickerReissueRequest
from app.schemas.hse_common import ApiWarning
from app.schemas.inductions import EligibilityItem
from app.schemas.scaffolds import (
    ScaffoldBoard,
    ScaffoldBoardZone,
    ScaffoldChecklistLineRead,
    ScaffoldCreate,
    ScaffoldInspectionCreate,
    ScaffoldInspectionList,
    ScaffoldInspectionRead,
    ScaffoldPage,
    ScaffoldRead,
    ScaffoldReinspectionRequest,
    ScaffoldReinspectionResult,
    ScaffoldTransitionRequest,
    ScaffoldUpdate,
)
from app.services import projects
from app.services.access import common as acommon
from app.services.access import eligibility
from app.services.access import hooks as ahooks
from app.services.cert import alerts, events, providers, validity
from app.services.cert import common as cc
from app.services.cert import reference as ref
from app.services.cert import settings as cset
from app.services.common import invalid_transition, paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal, engagement_descendants, forbidden_error

C = Capability
SS = ScaffoldStatus
TS = ScaffoldTagStatus
RES = ScaffoldInspectionResult
LOAD_KN = {1: "0.75", 2: "1.5", 3: "2.0", 4: "3.0", 5: "4.5", 6: "6.0"}
DESIGN_TYPES = frozenset(
    {ScaffoldType.cantilever, ScaffoldType.suspended_hanging, ScaffoldType.loading_bay}
)
STRUCTURAL = frozenset({"scaffold_type", "height_m", "load_class", "design_ref", "sheeting_fitted"})
BACKDATE = timedelta(minutes=60)


# ---- access --------------------------------------------------------------------------------------


def get_row(db: Session, scaffold_id: uuid.UUID) -> Scaffold:
    sc = db.get(Scaffold, scaffold_id)
    if sc is None:
        raise not_found("Scaffold")
    return sc


def _site(db: Session, sc: Scaffold) -> list[uuid.UUID]:
    z = db.get(Zone, sc.zone_id)
    return [z.site_id] if z else []


def get_visible(db: Session, p: Principal, scaffold_id: uuid.UUID) -> Scaffold:
    sc = get_row(db, scaffold_id)
    if not acommon.grant_covers(
        p.grant(sc.project_id, C.cert_register_view), _site(db, sc), sc.engagement_id
    ):
        raise not_found("Scaffold")
    return sc


def _require(db: Session, p: Principal, sc: Scaffold, cap: Capability) -> None:
    cc.require(p, sc.project_id, cap, sc.engagement_id, _site(db, sc))


# ---- state ---------------------------------------------------------------------------------------


def design_required(db: Session, sc: Scaffold) -> bool:
    """SF-2."""
    s = cset.get(db, sc.project_id)
    return bool(
        sc.height_m > s.scaffold_design_height_m
        or sc.scaffold_type in DESIGN_TYPES
        or sc.load_class >= 4
        or sc.sheeting_fitted
    )


def tag_state(sc: Scaffold, d: date | None = None) -> TS:
    return providers.scaffold_state(sc, d or today())


def usable(sc: Scaffold, d: date | None = None) -> bool:
    """SF-1."""
    return sc.status == SS.in_use and tag_state(sc, d) in (TS.green, TS.yellow)


def crew_items(
    db: Session, sc: Scaffold, at: datetime | None = None
) -> list[tuple[uuid.UUID, eligibility.Item]]:
    """SF-3: SCAFFOLDER (advanced for SF-2 scaffolds) per crew member under the project stage."""
    at = at or now()
    s = acommon.settings(db, sc.project_id)
    ctx = ahooks.HookContext(
        project_id=sc.project_id, zone_id=sc.zone_id, scaffold_design=design_required(db, sc)
    )
    out = []
    for wid in sc.erection_crew_worker_ids or []:
        it = eligibility.hook_item(
            db,
            HookSubjectType.worker,
            wid,
            HookKind.personnel_certificate,
            "SCAFFOLDER",
            at,
            s,
            ctx,
        )
        out.append((wid, it))
    return out


def _crew_schema(db: Session, sc: Scaffold, names: bool) -> list[EligibilityItem]:
    out = []
    for wid, it in crew_items(db, sc):
        e = it.to_schema()
        w = db.get(Worker, wid)
        e.ref = (
            (w.worker_no if w else None)
            if not names
            else (f"{w.worker_no} {w.full_name_en}" if w else None)
        )
        out.append(e)
    return out


# ---- reads ---------------------------------------------------------------------------------------


def inspection_read(
    db: Session,
    p: Principal | None,
    i: ScaffoldInspection,
    project_id: uuid.UUID,
    refs: Refs | None = None,
) -> ScaffoldInspectionRead:
    refs = refs or Refs(db)
    names = acommon.can_see_names(p, project_id)
    w = db.get(Worker, i.inspector_worker_id)
    return ScaffoldInspectionRead(
        id=i.id,
        scaffold_id=i.scaffold_id,
        inspection_type=i.inspection_type,
        inspected_at=i.inspected_at,
        inspector=acommon.worker_ref(w, names) if (w is not None and names) else None,
        recorded_by=refs.user(i.recorded_by_user_id) or cc.UNKNOWN_USER,
        checklist=[
            ScaffoldChecklistLineRead(
                item=ScaffoldChecklistItem(x["item"]),
                label_en=ref.SIC_TEXT[ScaffoldChecklistItem(x["item"])][0],
                label_ar=ref.SIC_TEXT[ScaffoldChecklistItem(x["item"])][1],
                result=ChecklistItemResult(x["result"]),
            )
            for x in i.checklist or []
        ],
        result=i.result,
        restrictions_en=i.restrictions_en,
        restrictions_ar=i.restrictions_ar,
        tag_valid_until=i.tag_valid_until,
        photo_attachment_ids=list(i.photo_attachment_ids or []),
        warnings=[ApiWarning(**w_) for w_ in i.warnings or []],
    )


def scaffold_read(
    db: Session, p: Principal | None, sc: Scaffold, refs: Refs | None = None
) -> ScaffoldRead:
    refs = refs or Refs(db)
    names = acommon.can_see_names(p, sc.project_id)
    sup = db.get(Worker, sc.erection_supervisor_worker_id)
    crew = [
        w for w in (db.get(Worker, x) for x in sc.erection_crew_worker_ids or []) if w is not None
    ]
    last = db.get(ScaffoldInspection, sc.last_inspection_id) if sc.last_inspection_id else None
    tok = acommon.active_qr(db, sc.id)
    eng = refs.eng(sc.engagement_id)
    zone = refs.zone(sc.zone_id)
    assert eng is not None and zone is not None  # noqa: S101
    d = today()
    return ScaffoldRead(
        id=sc.id,
        project_id=sc.project_id,
        scaffold_no=sc.scaffold_no,
        tag=sc.tag,
        engagement=eng,
        zone=zone,
        location_desc=sc.location_desc,
        level_code=sc.level_code,
        grid_x_m=sc.grid_x_m,
        grid_y_m=sc.grid_y_m,
        scaffold_type=sc.scaffold_type,
        height_m=sc.height_m,
        load_class=sc.load_class,
        load_class_kn_m2=Decimal(LOAD_KN[sc.load_class]),
        design_ref=sc.design_ref,
        design_required=design_required(db, sc),
        sheeting_fitted=sc.sheeting_fitted,
        erection_supervisor=acommon.worker_ref(sup, names) if sup else None,
        erection_crew=[acommon.worker_ref(w, names) for w in crew],
        crew_certification=_crew_schema(db, sc, names) if sc.status != SS.dismantled else [],
        status=sc.status,
        tag_status=tag_state(sc, d),
        tag_valid_until=sc.tag_valid_until,
        usable_today=usable(sc, d),
        restrictions_en=sc.restrictions_en if sc.tag_status == TS.yellow else None,
        restrictions_ar=sc.restrictions_ar if sc.tag_status == TS.yellow else None,
        inspection_required_reason=sc.inspection_required_reason,
        inspection_required_at=sc.inspection_required_at,
        last_inspection=inspection_read(db, p, last, sc.project_id, refs) if last else None,
        sticker_printed_ref=tok.printed_ref if tok else None,
        has_sticker=tok is not None,
        created_at=sc.created_at,
        updated_at=sc.updated_at,
    )


def read(db: Session, p: Principal, scaffold_id: uuid.UUID) -> ScaffoldRead:
    return scaffold_read(db, p, get_visible(db, p, scaffold_id))


def _scoped(db: Session, p: Principal, project_id: uuid.UUID) -> Any:
    project = projects.get_visible(db, p, project_id)
    g = p.grant(project.id, C.cert_register_view)
    if g is None:
        raise forbidden_error()
    stmt = (
        select(Scaffold)
        .join(Zone, Zone.id == Scaffold.zone_id)
        .where(Scaffold.project_id == project.id)
    )
    if g.engagement_ids is not None:
        stmt = stmt.where(Scaffold.engagement_id.in_(list(g.engagement_ids)))
    if g.site_ids is not None:
        stmt = stmt.where(Zone.site_id.in_(list(g.site_ids)))
    return stmt


def list_scaffolds(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    q: str | None = None,
    statuses: list[ScaffoldStatus] | None = None,
    tag_statuses: list[ScaffoldTagStatus] | None = None,
    types: list[ScaffoldType] | None = None,
    site_id: uuid.UUID | None = None,
    zone_ids: list[uuid.UUID] | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    include_subcontractors: bool = True,
    inspection_due_by: date | None = None,
) -> ScaffoldPage:
    stmt = _scoped(db, p, project_id)
    if q:
        pat = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Scaffold.tag.ilike(pat),
                Scaffold.location_desc.ilike(pat),
                Scaffold.scaffold_no.ilike(pat),
            )
        )
    if statuses:
        stmt = stmt.where(Scaffold.status.in_(statuses))
    if types:
        stmt = stmt.where(Scaffold.scaffold_type.in_(types))
    if site_id:
        stmt = stmt.where(Zone.site_id == site_id)
    if zone_ids:
        stmt = stmt.where(Scaffold.zone_id.in_(zone_ids))
    if engagement_ids:
        ids: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                ids |= engagement_descendants(db, e)
        stmt = stmt.where(Scaffold.engagement_id.in_(ids))
    if inspection_due_by is not None:
        stmt = stmt.where(
            Scaffold.status == SS.in_use, Scaffold.tag_valid_until <= inspection_due_by
        )
    stmt = stmt.order_by(Scaffold.tag)
    refs = Refs(db)
    if tag_statuses:
        d = today()
        rows = [sc for sc in db.scalars(stmt) if tag_state(sc, d) in tag_statuses]
        total = len(rows)
        rows = rows[(page - 1) * page_size : page * page_size]
    else:
        page_rows, total = paginate(db, stmt, page, page_size)
        rows = list(page_rows)
    return ScaffoldPage(
        items=[scaffold_read(db, p, sc, refs) for sc in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


def board(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    site_id: uuid.UUID | None = None,
    as_of: date | None = None,
) -> ScaffoldBoard:
    stmt = _scoped(db, p, project_id).where(Scaffold.status != SS.dismantled)
    if site_id:
        stmt = stmt.where(Zone.site_id == site_id)
    d = as_of or today()
    by_zone: dict[uuid.UUID, list[Scaffold]] = defaultdict(list)
    for sc in db.scalars(stmt.order_by(Scaffold.tag)):
        by_zone[sc.zone_id].append(sc)
    refs = Refs(db).load(zones=list(by_zone))
    zones = []
    for zid, scs in by_zone.items():
        counts: dict[str, int] = defaultdict(int)
        items = []
        for sc in scs:
            ts = tag_state(sc, d)
            counts[ts.value] += 1
            r = cc.scaffold_ref(sc)
            r.tag_status = ts
            items.append(r)
        z = refs.zone(zid)
        assert z is not None  # noqa: S101
        zones.append(ScaffoldBoardZone(zone=z, scaffolds=items, counts=dict(counts)))
    zones.sort(key=lambda x: x.zone.code)
    return ScaffoldBoard(project_id=project_id, as_of=d, zones=zones)


def inspections(db: Session, p: Principal, scaffold_id: uuid.UUID) -> ScaffoldInspectionList:
    sc = get_visible(db, p, scaffold_id)
    rows = db.scalars(
        select(ScaffoldInspection)
        .where(ScaffoldInspection.scaffold_id == sc.id)
        .order_by(ScaffoldInspection.inspected_at.desc())
    )
    refs = Refs(db)
    return ScaffoldInspectionList(
        items=[inspection_read(db, p, i, sc.project_id, refs) for i in rows]
    )


# ---- create / update -----------------------------------------------------------------------------


def _check_place(
    db: Session, project_id: uuid.UUID, engagement_id: uuid.UUID, zone_id: uuid.UUID
) -> Zone:
    eng = db.get(ProjectEngagement, engagement_id)
    if eng is None or eng.project_id != project_id:
        raise validation_error("engagement_id", "Engagement not on this project.")
    z = db.get(Zone, zone_id)
    if z is None or z.site_id not in (eng.site_ids or []):
        raise validation_error("zone_id", "Choose a zone of the engagement's sites.")
    return z


def _check_workers(db: Session, sup: uuid.UUID, crew: list[uuid.UUID]) -> None:
    for i, wid in enumerate([sup, *crew]):
        if db.get(Worker, wid) is None:
            raise validation_error(
                "erection_crew_worker_ids" if i else "erection_supervisor_worker_id",
                "Worker not found.",
            )
    if len(set(crew)) != len(crew):
        raise validation_error("erection_crew_worker_ids", "Duplicate crew member.")


def _tag_unique(
    db: Session, project_id: uuid.UUID, tag: str, exclude: uuid.UUID | None = None
) -> None:
    stmt = select(Scaffold.id).where(
        Scaffold.project_id == project_id,
        func.upper(Scaffold.tag) == tag.upper(),
        Scaffold.status != SS.dismantled,
    )
    if exclude:
        stmt = stmt.where(Scaffold.id != exclude)
    if db.scalar(stmt) is not None:
        raise ApiError(
            409,
            ErrorCode.TAG_EXISTS,
            "This tag is already used on the project.",
            "رقم البطاقة مستخدم في المشروع.",
            meta={"field": "tag"},
        )


def create(db: Session, p: Principal, project_id: uuid.UUID, body: ScaffoldCreate) -> ScaffoldRead:
    project = projects.get_visible(db, p, project_id)
    z = _check_place(db, project.id, body.engagement_id, body.zone_id)
    cc.require(p, project.id, C.equipment_edit, body.engagement_id, [z.site_id])
    _check_workers(db, body.erection_supervisor_worker_id, body.erection_crew_worker_ids)
    tag = body.tag.strip().upper()
    _tag_unique(db, project.id, tag)
    sc = new_scaffold(db, p, project.id, body, tag)
    return scaffold_read(db, p, sc)


def new_scaffold(
    db: Session,
    p: Principal | None,
    project_id: uuid.UUID,
    body: ScaffoldCreate,
    tag: str,
    seed_fake: bool = False,
) -> Scaffold:
    seq = (
        db.scalar(select(func.max(Scaffold.seq)).where(Scaffold.project_id == project_id)) or 0
    ) + 1
    code = cc.project_code(db, project_id)
    data = body.model_dump(exclude={"tag"})
    sc = Scaffold(
        id=uuid.uuid4(),
        project_id=project_id,
        seq=seq,
        scaffold_no=f"SCF-{code}-{seq:04d}",
        tag=tag,
        status=SS.under_erection,
        tag_status=TS.red,
        alerts_sent=[],
        **data,
    )
    cc.stamp(sc, p, create=True)
    db.add(sc)
    db.flush()
    acommon.issue_qr(db, QrKind.EQ, project_id, sc.id, f"{code}-{tag}")
    cc.record(db, p, AuditAction.create, EntityType.scaffold, sc, project_id)
    return sc


def update(db: Session, p: Principal, scaffold_id: uuid.UUID, body: ScaffoldUpdate) -> ScaffoldRead:
    sc = get_visible(db, p, scaffold_id)
    _require(db, p, sc, C.equipment_edit)
    if sc.status == SS.dismantled:
        raise invalid_transition("Scaffold", sc.status.value, "edit")
    ch = body.changes()
    if STRUCTURAL & set(ch) and sc.status == SS.in_use and sc.tag_status in (TS.green, TS.yellow):
        raise ApiError(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Start an alteration before changing the scaffold structure.",
            "ابدأ التعديل قبل تغيير هيكل السقالة.",
        )
    before = cc.snap(sc)
    for k, v in ch.items():
        setattr(sc, k, v)
    _check_place(db, sc.project_id, sc.engagement_id, sc.zone_id)
    _check_workers(db, sc.erection_supervisor_worker_id, list(sc.erection_crew_worker_ids or []))
    cc.stamp(sc, p)
    db.flush()
    cc.record(db, p, AuditAction.update, EntityType.scaffold, sc, sc.project_id, before)
    return scaffold_read(db, p, sc)


def _publish(db: Session, sc: Scaffold) -> None:
    events.publish(db, "scaffold.tag_changed", project_id=sc.project_id, scaffold_ids=[sc.id])


def _red(db: Session, sc: Scaffold, text: str, p: Principal | None) -> None:
    sc.tag_status = TS.red
    sc.tag_valid_until = None
    users = alerts.reps(db, sc.project_id, sc.engagement_id) | alerts.officers(db, sc.project_id)
    alerts.send(
        db,
        users,
        NotificationKind.scaffold_tag_red,
        f"Scaffold {sc.tag} red-tagged — do not use ({text})",
        f"السقالة {sc.tag} ببطاقة حمراء — ممنوع الاستخدام ({text})",
        EntityType.scaffold,
        sc.id,
        sc.project_id,
    )


def transition(
    db: Session, p: Principal, scaffold_id: uuid.UUID, body: ScaffoldTransitionRequest
) -> ScaffoldRead:
    sc = get_visible(db, p, scaffold_id)
    _require(db, p, sc, C.equipment_edit)
    src, dst = sc.status, body.to_status
    before = cc.snap(sc)
    if dst == SS.under_alteration and src in (SS.in_use, SS.closed_red):
        sc.status = dst
        _red(db, sc, "alteration", p)
    elif dst == SS.dismantled and src != SS.dismantled:
        sc.status = dst
        sc.tag_status = TS.none
        sc.tag_valid_until = None
        acommon.end_qr(db, sc.id, QrTokenStatus.revoked)
    else:
        raise invalid_transition("Scaffold", src.value, dst.value)
    cc.stamp(sc, p)
    db.flush()
    cc.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.scaffold,
        sc,
        sc.project_id,
        before,
        {"from": src.value, "to": dst.value, "reason": body.reason},
    )
    _publish(db, sc)
    return scaffold_read(db, p, sc)


# ---- inspections (SF-2…SF-6) ---------------------------------------------------------------------


def inspector_certified(
    db: Session, worker_id: uuid.UUID, at: datetime, project_id: uuid.UUID
) -> bool:
    """SF-4: in-force SCAFFOLD-INSPECTOR at `at` (every hook stage)."""
    r = providers.check_personnel(db, worker_id, "SCAFFOLD-INSPECTOR", at, None, project_id)
    return r.status.value in ("met", "expiring")


def inspect(
    db: Session, p: Principal, scaffold_id: uuid.UUID, body: ScaffoldInspectionCreate
) -> ScaffoldInspectionRead:
    sc = get_visible(db, p, scaffold_id)
    _require(db, p, sc, C.scaffold_inspect)
    at_now = now()
    at = body.inspected_at or at_now
    if at > at_now + timedelta(minutes=1) or at < at_now - BACKDATE:
        raise ApiError(
            422,
            ErrorCode.BACKDATED_INSPECTION,
            "The inspection time must be within the last 60 minutes.",
            "يجب أن يكون وقت الفحص خلال آخر 60 دقيقة.",
            meta={"field": "inspected_at"},
        )
    if sc.status == SS.dismantled:
        raise invalid_transition("Scaffold", sc.status.value, "inspection")
    handover = body.inspection_type == ScaffoldInspectionType.handover
    if sc.status == SS.under_erection and not handover:
        raise validation_error(
            "inspection_type", "The first inspection is the handover inspection."
        )
    if handover and sc.status != SS.under_erection:
        raise validation_error("inspection_type", "Handover is the first inspection only.")
    items = [x.item for x in body.checklist]
    if set(items) != set(ScaffoldChecklistItem):
        raise validation_error("checklist", "Every SIC item must be answered once.")
    for x in body.checklist:
        if x.result == ChecklistItemResult.na and x.item != ScaffoldChecklistItem.SIC_10:
            raise validation_error("checklist", f"{x.item.value}: n.a. is allowed only for SIC-10.")
    failed = any(x.result == ChecklistItemResult.fail for x in body.checklist)
    if body.result == RES.green and failed:
        raise validation_error("result", "A failed checklist item cannot be green.")
    if body.result == RES.yellow and not (body.restrictions_en or "").strip():
        raise ApiError(
            422,
            ErrorCode.RESTRICTIONS_REQUIRED,
            "A yellow tag must state the restrictions.",
            "يجب أن تذكر البطاقة الصفراء القيود.",
            meta={"field": "restrictions_en"},
        )
    # SF-4
    if not inspector_certified(db, body.inspector_worker_id, at, sc.project_id):
        raise ApiError(
            422,
            ErrorCode.INSPECTOR_NOT_CERTIFIED,
            "The inspector does not hold an in-force SCAFFOLD-INSPECTOR certificate.",
            "لا يحمل المفتش شهادة «مفتش سقالات» سارية.",
            meta={"field": "inspector_worker_id"},
        )
    warnings: list[ApiWarning] = []
    if handover and body.result != RES.red:
        if body.inspector_worker_id == sc.erection_supervisor_worker_id:
            raise cc.sod()
        if design_required(db, sc) and not sc.design_ref:
            raise ApiError(
                422,
                ErrorCode.SCAFFOLD_DESIGN_REQUIRED,
                "This scaffold needs a design reference before handover.",
                "تتطلب هذه السقالة مرجع تصميم قبل التسليم.",
                meta={"field": "design_ref"},
            )
        # SF-3
        bad = []
        warn_nos = []
        for wid, it in crew_items(db, sc, at):
            w = db.get(Worker, wid)
            no = w.worker_no if w else str(wid)
            if it.status == RequirementStatus.not_met:
                bad.append(no)
            elif it.status in (RequirementStatus.warn, RequirementStatus.not_evaluated):
                warn_nos.append(no)
        if bad:
            raise ApiError(
                422,
                ErrorCode.CREW_NOT_CERTIFIED,
                f"Crew without an in-force SCAFFOLDER certificate: {', '.join(bad)}.",
                f"أفراد بدون شهادة «سقّاف» سارية: {', '.join(bad)}.",
                meta={"workers": bad},
            )
        if warn_nos:
            warnings.append(
                cc.warn(
                    "CREW_NOT_CERTIFIED",
                    f"Crew certificates not confirmed: {', '.join(warn_nos)} (transition period).",
                    f"لم تتأكد شهادات الطاقم: {', '.join(warn_nos)} (فترة انتقالية).",
                )
            )
    s = cset.get(db, sc.project_id)
    day = acommon.local_day(at)
    until = validity.scaffold_tag_until(day, s) if body.result != RES.red else None
    i = ScaffoldInspection(
        id=uuid.uuid4(),
        scaffold_id=sc.id,
        inspection_type=body.inspection_type,
        inspected_at=at,
        inspector_worker_id=body.inspector_worker_id,
        recorded_by_user_id=p.user.id,
        checklist=[{"item": x.item.value, "result": x.result.value} for x in body.checklist],
        result=body.result,
        restrictions_en=body.restrictions_en,
        restrictions_ar=body.restrictions_ar,
        tag_valid_until=until,
        photo_attachment_ids=list(body.photo_attachment_ids),
        warnings=[w.model_dump() for w in warnings],
    )
    db.add(i)
    db.flush()
    apply_inspection(db, sc, i, p)
    cc.record(
        db,
        p,
        AuditAction.create,
        EntityType.scaffold_inspection,
        i,
        sc.project_id,
        details={"scaffold": sc.tag, "result": body.result.value},
    )
    return inspection_read(db, p, i, sc.project_id)


def apply_inspection(db: Session, sc: Scaffold, i: ScaffoldInspection, p: Principal | None) -> None:
    before = cc.snap(sc)
    sc.last_inspection_id = i.id
    if i.result == RES.red:
        if sc.status == SS.in_use:
            sc.status = SS.closed_red
        _red(db, sc, "inspection", p)
    else:
        sc.status = SS.in_use
        sc.tag_status = TS.green if i.result == RES.green else TS.yellow
        sc.tag_valid_until = i.tag_valid_until
        sc.restrictions_en = i.restrictions_en if i.result == RES.yellow else None
        sc.restrictions_ar = i.restrictions_ar if i.result == RES.yellow else None
        sc.inspection_required_reason = None
        sc.inspection_required_at = None
        sc.alerts_sent = []
    cc.stamp(sc, p)
    db.flush()
    cc.record(db, p, AuditAction.update, EntityType.scaffold, sc, sc.project_id, before)
    _publish(db, sc)


# ---- re-inspection (SF-5), stop use (DF-3) -------------------------------------------------------


def require_inspection(
    db: Session,
    sc: Scaffold,
    reason: ReinspectionReason,
    at: datetime,
    text: str,
    p: Principal | None,
) -> bool:
    if sc.status != SS.in_use or sc.tag_status == TS.inspection_required:
        return False
    before = cc.snap(sc)
    sc.tag_status = TS.inspection_required
    sc.inspection_required_reason = reason
    sc.inspection_required_at = at
    db.flush()
    cc.record(
        db, p, AuditAction.update, EntityType.scaffold, sc, sc.project_id, before, {"reason": text}
    )
    _publish(db, sc)
    return True


def request_reinspection(
    db: Session, p: Principal, project_id: uuid.UUID, body: ScaffoldReinspectionRequest
) -> ScaffoldReinspectionResult:
    project = projects.get_visible(db, p, project_id)
    cc.require(p, project.id, C.defect_close, None, [body.site_id])
    stmt = (
        select(Scaffold)
        .join(Zone, Zone.id == Scaffold.zone_id)
        .where(
            Scaffold.project_id == project.id,
            Zone.site_id == body.site_id,
            Scaffold.status == SS.in_use,
        )
    )
    if body.zone_id:
        stmt = stmt.where(Scaffold.zone_id == body.zone_id)
    at = now()
    affected = []
    for sc in db.scalars(stmt.order_by(Scaffold.tag)):
        if require_inspection(db, sc, body.reason, at, body.reason_text, p):
            affected.append(sc)
    if affected:
        _alert_reinspection(db, project.id, affected, body.reason_text)
    return ScaffoldReinspectionResult(
        at=at, reason=body.reason, affected=[cc.scaffold_ref(sc) for sc in affected]
    )


def _alert_reinspection(db: Session, project_id: uuid.UUID, scs: list[Scaffold], text: str) -> None:
    users = alerts.officers(db, project_id)
    for eng in {sc.engagement_id for sc in scs}:
        users |= alerts.reps(db, project_id, eng)
    tags = ", ".join(sc.tag for sc in scs[:10])
    alerts.send(
        db,
        users,
        NotificationKind.scaffold_tag_expiry,
        f"Scaffolds need re-inspection before use: {tags}",
        f"تتطلب السقالات إعادة فحص قبل الاستخدام: {tags}",
        EntityType.scaffold,
        scs[0].id,
        project_id,
        body_en=text,
        body_ar=text,
    )


def ops_event_trigger(db: Session, e: OpsEvent) -> int:
    """SF-5: dust_sandstorm / thunderstorm_lightning on the site → every In Use scaffold of the
    site needs re-inspection (once per event)."""
    if e.type not in (OpsEventType.dust_sandstorm, OpsEventType.thunderstorm_lightning):
        return 0
    if not alerts.once(db, f"scaffold-ops:{e.id}"):
        return 0
    rows = db.scalars(
        select(Scaffold)
        .join(Zone, Zone.id == Scaffold.zone_id)
        .where(
            Scaffold.project_id == e.project_id,
            Zone.site_id == e.site_id,
            Scaffold.status == SS.in_use,
        )
    )
    hit = [
        sc
        for sc in rows
        if require_inspection(db, sc, ReinspectionReason.ops_event, e.started_at, e.ops_no, None)
    ]
    if hit:
        _alert_reinspection(db, e.project_id, hit, f"{e.ops_no} ({e.type.value})")
    return len(hit)


def stop_use(db: Session, sc: Scaffold, p: Principal | None, ref_: str) -> None:
    """DF-3: a category A defect on a scaffold → red tag, Closed (Red)."""
    before = cc.snap(sc)
    if sc.status == SS.in_use:
        sc.status = SS.closed_red
    _red(db, sc, ref_, p)
    db.flush()
    cc.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.scaffold,
        sc,
        sc.project_id,
        before,
        {"defect": ref_},
    )
    _publish(db, sc)


# ---- stickers ------------------------------------------------------------------------------------


def sticker_read(db: Session, sc: Scaffold) -> EquipmentStickerRead:
    from app.core.cert_enums import EquipmentCertCategory  # noqa: PLC0415

    tok = acommon.active_qr(db, sc.id)
    if tok is None:
        raise ApiError(
            409,
            ErrorCode.INVALID_TRANSITION,
            "This scaffold has no active sticker.",
            "لا يوجد ملصق ساري لهذه السقالة.",
        )
    eng = db.get(ProjectEngagement, sc.engagement_id)
    return EquipmentStickerRead(
        deployment=None,
        scaffold_id=sc.id,
        qr_payload=acommon.payload(tok),
        printed_ref=tok.printed_ref,
        category=EquipmentCertCategory.scaffold,
        tag=sc.tag,
        owner_short_code=(cc.owner_code(db, eng.contractor_id) if eng else None) or "",
        issued_at=tok.created_at,
    )


def get_sticker(db: Session, p: Principal, scaffold_id: uuid.UUID) -> EquipmentStickerRead:
    return sticker_read(db, get_visible(db, p, scaffold_id))


def reissue_sticker(
    db: Session, p: Principal, scaffold_id: uuid.UUID, body: StickerReissueRequest
) -> EquipmentStickerRead:
    sc = get_visible(db, p, scaffold_id)
    _require(db, p, sc, C.equipment_edit)
    if sc.status == SS.dismantled:
        raise invalid_transition("Scaffold", sc.status.value, "sticker_reissue")
    acommon.end_qr(db, sc.id, QrTokenStatus.rotated)
    acommon.issue_qr(
        db, QrKind.EQ, sc.project_id, sc.id, f"{cc.project_code(db, sc.project_id)}-{sc.tag}"
    )
    cc.record(
        db,
        p,
        AuditAction.update,
        EntityType.scaffold,
        sc,
        sc.project_id,
        None,
        {"sticker_reissued": body.reason},
        after={"sticker": "rotated"},
    )
    return sticker_read(db, sc)


# ---- jobs (SF-5 expiry, §7) ----------------------------------------------------------------------


def tag_expiry_job(db: Session, at: datetime | None = None) -> int:
    """Green / yellow tags past tag_valid_until → expired (job); alert on the last valid day
    and when expired."""
    at = at or now()
    d = acommon.local_day(at)
    n = 0
    for sc in db.scalars(
        select(Scaffold).where(
            Scaffold.status == SS.in_use, Scaffold.tag_status.in_([TS.green, TS.yellow])
        )
    ):
        users = alerts.reps(db, sc.project_id, sc.engagement_id) | alerts.officers(
            db, sc.project_id
        )
        if sc.tag_valid_until is not None and sc.tag_valid_until < d:
            before = cc.snap(sc)
            sc.tag_status = TS.expired
            db.flush()
            cc.record(db, None, AuditAction.update, EntityType.scaffold, sc, sc.project_id, before)
            alerts.send(
                db,
                users,
                NotificationKind.scaffold_tag_expiry,
                f"Scaffold {sc.tag}: tag expired — re-inspect before use",
                f"السقالة {sc.tag}: انتهت البطاقة — أعد الفحص قبل الاستخدام",
                EntityType.scaffold,
                sc.id,
                sc.project_id,
            )
            _publish(db, sc)
            n += 1
        elif sc.tag_valid_until == d and alerts.once(db, f"scaffold-last-day:{sc.id}:{d}"):
            alerts.send(
                db,
                users,
                NotificationKind.scaffold_tag_expiry,
                f"Scaffold {sc.tag}: tag valid until today — inspect today",
                f"السقالة {sc.tag}: البطاقة سارية حتى اليوم — افحصها اليوم",
                EntityType.scaffold,
                sc.id,
                sc.project_id,
            )
    return n
