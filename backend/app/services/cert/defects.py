"""Equipment and scaffold defects: raise → rectify → close / return to service (spec
4-third-party-cert §3.11, §4.5, §6.3, DF-1…DF-10)."""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.cert_enums import (
    CertificateStatus,
    CertInspectionType,
    DefectCategory,
    DefectClosureMethod,
    DefectSource,
    DefectStatus,
    EquipmentCertCategory,
    ServiceStatus,
    ServiceStatusReason,
    VerificationStatus,
)
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import Agency, DangerousOccurrenceCategory
from app.models import (
    EquipmentCertificate,
    EquipmentCertLine,
    EquipmentDefect,
    EquipmentDeployment,
    EquipmentItem,
    Incident,
    InjuryCase,
    Project,
    Scaffold,
    Worker,
)
from app.schemas.defects import (
    DefectCancelInput,
    DefectCloseInput,
    DefectClosureRead,
    DefectCreate,
    DefectDestroyInput,
    DefectPage,
    DefectRead,
    DefectReopenInput,
    IncidentDefectPrompt,
    RectificationInput,
    RectificationRead,
)
from app.schemas.hse_common import UserRef
from app.services import projects
from app.services.access import common as acommon
from app.services.cert import alerts, validity
from app.services.cert import common as cc
from app.services.cert import reference as ref
from app.services.cert import settings as cset
from app.services.common import invalid_transition, paginate
from app.services.hse_common import Refs, make_ref, next_seq
from app.services.permissions import Principal, engagement_descendants, forbidden_error

C = Capability
DS = DefectStatus
Q = EquipmentCertCategory
PROMPT_AGENCIES = frozenset({Agency.crane_lifting_gear, Agency.mewp, Agency.scaffold})
PROMPT_DO = frozenset(
    {
        DangerousOccurrenceCategory.crane_lifting_failure,
        DangerousOccurrenceCategory.scaffold_collapse,
    }
)


# ---- scope ---------------------------------------------------------------------------------------


def _subject_scope(db: Session, d: EquipmentDefect) -> tuple[uuid.UUID | None, list[uuid.UUID]]:
    """(engagement, site ids) used for grant checks."""
    if d.scaffold_id is not None:
        sc = db.get(Scaffold, d.scaffold_id)
        from app.models import Zone  # noqa: PLC0415

        z = db.get(Zone, sc.zone_id) if sc else None
        return (sc.engagement_id if sc else d.engagement_id), ([z.site_id] if z else [])
    dep = cc.latest_deployment_on(db, d.equipment_id, d.project_id) if d.equipment_id else None
    return d.engagement_id, (list(dep.site_ids) if dep else [])


def _get(db: Session, p: Principal, defect_id: uuid.UUID) -> EquipmentDefect:
    d = db.get(EquipmentDefect, defect_id)
    if d is None:
        raise not_found("Defect")
    eng, sites = _subject_scope(db, d)
    g = p.grant(d.project_id, C.cert_register_view)
    if not acommon.grant_covers(g, sites, eng):
        raise not_found("Defect")
    return d


def _require(db: Session, p: Principal, d: EquipmentDefect, cap: Capability) -> None:
    eng, sites = _subject_scope(db, d)
    cc.require(p, d.project_id, cap, eng, sites)


# ---- reads ---------------------------------------------------------------------------------------


def _user(refs: Refs, uid: uuid.UUID | None) -> UserRef | None:
    return refs.user(uid) if uid else None


def _allowed(d: EquipmentDefect, item: EquipmentItem | None) -> list[str]:
    out: list[str] = []
    destroy_only = (
        item is not None and item.category in ref.DESTROY_ONLY and d.category == DefectCategory.A
    )
    if d.status == DS.open:
        out.append("destroy" if destroy_only else "rectify")
    if d.status == DS.rectified:
        out += ["close", "reopen"]
    if d.status in (DS.open, DS.rectified) and d.source != DefectSource.tpi_inspection:
        out.append("cancel")
    return out


def defect_read(
    db: Session, p: Principal | None, d: EquipmentDefect, refs: Refs | None = None
) -> DefectRead:
    refs = refs or Refs(db)
    item = db.get(EquipmentItem, d.equipment_id) if d.equipment_id else None
    sc = db.get(Scaffold, d.scaffold_id) if d.scaffold_id else None
    tag = None
    if item is not None:
        dep = cc.latest_deployment_on(db, item.id, d.project_id)
        tag = dep.tag if dep else None
    elif sc is not None:
        tag = sc.tag
    line = db.get(EquipmentCertLine, d.cert_line_id) if d.cert_line_id else None
    w = db.get(Worker, d.raised_by_worker_id) if d.raised_by_worker_id else None
    names = acommon.can_see_names(p, d.project_id)
    # a reopened defect keeps only `reopened_reason` until it is rectified again
    rect = d.rectification if (d.rectification or {}).get("description") else None
    clo = d.closure or None
    t = today()
    overdue = (
        d.category == DefectCategory.B
        and d.due_date is not None
        and d.status in (DS.open, DS.rectified)
        and t > d.due_date
    )
    return DefectRead(
        id=d.id,
        defect_no=d.defect_no,
        project_id=d.project_id,
        equipment=cc.equipment_ref(db, item) if item else None,
        scaffold=cc.scaffold_ref(sc) if sc else None,
        tag=tag,
        engagement=refs.eng(d.engagement_id),
        source=d.source,
        source_ref=d.source_ref,
        cert_line=cc.line_ref(db, line) if line else None,
        category=d.category,
        description_en=d.description_en,
        description_ar=d.description_ar,
        photo_attachment_ids=list(d.photo_attachment_ids or []),
        raised_by_user=_user(refs, d.raised_by_user_id),
        raised_by_worker=acommon.worker_ref(w, names) if w else None,
        raised_at=d.raised_at,
        physical_tag_applied=d.physical_tag_applied,
        tpi_due_date=d.tpi_due_date,
        due_date=d.due_date,
        days_left=(d.due_date - t).days if d.due_date else None,
        overdue=overdue,
        rectification=RectificationRead(
            description=rect["description"],
            done_by_text=rect["done_by_text"],
            done_at=datetime.fromisoformat(rect["done_at"]),
            recorded_by=_user(refs, d.rectified_by_user_id)
            or UserRef(id=uuid.UUID(int=0), full_name_en="System", full_name_ar="النظام"),
            evidence_attachment_ids=[uuid.UUID(x) for x in rect.get("evidence_attachment_ids", [])],
        )
        if rect
        else None,
        closure=DefectClosureRead(
            method=DefectClosureMethod(clo["method"]),
            cert_line=cc.line_ref(db, cl)
            if (
                cl := (
                    db.get(EquipmentCertLine, uuid.UUID(clo["cert_line_id"]))
                    if clo.get("cert_line_id")
                    else None
                )
            )
            else None,
            closed_by=_user(refs, d.closed_by_user_id)
            or UserRef(id=uuid.UUID(int=0), full_name_en="System", full_name_ar="النظام"),
            closed_at=d.closed_at or d.updated_at,
            note=clo.get("note", ""),
            evidence_attachment_ids=[uuid.UUID(x) for x in clo.get("evidence_attachment_ids", [])],
        )
        if clo
        else None,
        status=d.status,
        cancelled_reason=d.cancelled_reason,
        allowed_actions=_allowed(d, item),
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def read(db: Session, p: Principal, defect_id: uuid.UUID) -> DefectRead:
    return defect_read(db, p, _get(db, p, defect_id))


def list_defects(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    statuses: list[DefectStatus] | None = None,
    categories: list[DefectCategory] | None = None,
    sources: list[DefectSource] | None = None,
    equipment_categories: list[EquipmentCertCategory] | None = None,
    equipment_id: uuid.UUID | None = None,
    scaffold_id: uuid.UUID | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    include_subcontractors: bool = True,
    overdue: bool | None = None,
    due_within_days: int | None = None,
) -> DefectPage:
    project = projects.get_visible(db, p, project_id)
    g = p.grant(project.id, C.cert_register_view)
    if g is None:
        raise forbidden_error()
    stmt = select(EquipmentDefect).where(EquipmentDefect.project_id == project.id)
    if g.engagement_ids is not None:
        stmt = stmt.where(EquipmentDefect.engagement_id.in_(list(g.engagement_ids)))
    if g.site_ids is not None:
        sites = list(g.site_ids)
        from app.models import Zone  # noqa: PLC0415

        stmt = stmt.where(
            or_(
                EquipmentDefect.equipment_id.in_(
                    select(EquipmentDeployment.equipment_id).where(
                        EquipmentDeployment.project_id == project.id,
                        EquipmentDeployment.site_ids.overlap(sites),
                    )
                ),
                EquipmentDefect.scaffold_id.in_(
                    select(Scaffold.id)
                    .join(Zone, Zone.id == Scaffold.zone_id)
                    .where(Zone.site_id.in_(sites))
                ),
            )
        )
    if statuses:
        stmt = stmt.where(EquipmentDefect.status.in_(statuses))
    if categories:
        stmt = stmt.where(EquipmentDefect.category.in_(categories))
    if sources:
        stmt = stmt.where(EquipmentDefect.source.in_(sources))
    if equipment_categories:
        stmt = stmt.where(
            EquipmentDefect.equipment_id.in_(
                select(EquipmentItem.id).where(EquipmentItem.category.in_(equipment_categories))
            )
        )
    if equipment_id:
        stmt = stmt.where(EquipmentDefect.equipment_id == equipment_id)
    if scaffold_id:
        stmt = stmt.where(EquipmentDefect.scaffold_id == scaffold_id)
    if engagement_ids:
        ids: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                ids |= engagement_descendants(db, e)
        stmt = stmt.where(EquipmentDefect.engagement_id.in_(ids))
    t = today()
    live = [DS.open, DS.rectified]
    if overdue is True:
        stmt = stmt.where(
            EquipmentDefect.status.in_(live),
            EquipmentDefect.category == DefectCategory.B,
            EquipmentDefect.due_date < t,
        )
    elif overdue is False:
        stmt = stmt.where(
            or_(
                EquipmentDefect.due_date.is_(None),
                EquipmentDefect.due_date >= t,
                EquipmentDefect.status.notin_(live),
            )
        )
    if due_within_days is not None:
        stmt = stmt.where(
            EquipmentDefect.status.in_(live),
            EquipmentDefect.due_date.is_not(None),
            EquipmentDefect.due_date <= t + timedelta(days=due_within_days),
        )
    stmt = stmt.order_by(EquipmentDefect.raised_at.desc())
    rows, total = paginate(db, stmt, page, page_size)
    refs = Refs(db)
    return DefectPage(
        items=[defect_read(db, p, d, refs) for d in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---- create --------------------------------------------------------------------------------------


def new_defect(
    db: Session,
    project_id: uuid.UUID,
    *,
    item: EquipmentItem | None,
    scaffold: Scaffold | None,
    engagement_id: uuid.UUID | None,
    source: DefectSource,
    category: DefectCategory,
    description_en: str,
    description_ar: str | None = None,
    raised_at: datetime | None = None,
    p: Principal | None = None,
    raised_by_worker_id: uuid.UUID | None = None,
    cert_line_id: uuid.UUID | None = None,
    source_ref: str | None = None,
    tpi_due_date: date | None = None,
    physical_tag_applied: bool = False,
    photo_attachment_ids: list[uuid.UUID] | None = None,
    seed_fake: bool = False,
    apply_effects: bool = True,
) -> EquipmentDefect:
    project = db.get(Project, project_id)
    assert project is not None  # noqa: S101
    raised_at = raised_at or now()
    year = acommon.local_day(raised_at).year
    seq = next_seq(db, EquipmentDefect, project.id, year)
    s = cset.get(db, project.id)
    due = validity.defect_due(category, acommon.local_day(raised_at), tpi_due_date, s)
    d = EquipmentDefect(
        id=uuid.uuid4(),
        year=year,
        seq=seq,
        project_id=project.id,
        defect_no=make_ref("DEF", project.code, year, seq, 4),
        equipment_id=item.id if item else None,
        scaffold_id=scaffold.id if scaffold else None,
        engagement_id=engagement_id,
        source=source,
        source_ref=source_ref,
        cert_line_id=cert_line_id,
        category=category,
        description_en=description_en,
        description_ar=description_ar,
        photo_attachment_ids=photo_attachment_ids or [],
        raised_by_user_id=p.user.id if p else None,
        raised_by_worker_id=raised_by_worker_id,
        raised_at=raised_at,
        physical_tag_applied=physical_tag_applied,
        tpi_due_date=tpi_due_date if category == DefectCategory.B else None,
        due_date=due,
        status=DS.open,
        alerts_sent=[],
        seed_fake=seed_fake,
    )
    cc.stamp(d, p, create=True)
    db.add(d)
    db.flush()
    cc.record(db, p, AuditAction.create, EntityType.equipment_defect, d, project.id)
    if apply_effects and category == DefectCategory.A:
        _stop_use(db, d, item, scaffold, p)
    return d


def _stop_use(
    db: Session,
    d: EquipmentDefect,
    item: EquipmentItem | None,
    scaffold: Scaffold | None,
    p: Principal | None,
) -> None:
    """DF-3: A → item Out of Service (`defect_a`) at once; alerts within 60 s."""
    from app.services.cert import equipment  # noqa: PLC0415

    if item is not None:
        if item.service_status not in (ServiceStatus.blacklisted, ServiceStatus.retired):
            equipment.set_status(
                db,
                item,
                ServiceStatus.out_of_service,
                ServiceStatusReason.defect_a,
                p,
                d.description_en[:500],
                d.defect_no,
                d.raised_at,
            )
        for pid, users in equipment.stop_use_recipients(db, item).items():
            dep = cc.latest_deployment_on(db, item.id, pid)
            tag = dep.tag if dep else item.equipment_no
            alerts.send(
                db,
                users,
                NotificationKind.equipment_stop_use,
                f"{tag}: category A defect {d.defect_no} — OUT OF SERVICE",
                f"{tag}: عيب من الفئة A {d.defect_no} — خارج الخدمة",
                EntityType.equipment_defect,
                d.id,
                pid,
                email=True,
            )
    if scaffold is not None:
        from app.services.cert import scaffolds  # noqa: PLC0415

        scaffolds.stop_use(db, scaffold, p, d.defect_no)


def create(db: Session, p: Principal, project_id: uuid.UUID, body: DefectCreate) -> DefectRead:
    project = projects.get_visible(db, p, project_id)
    if (body.equipment_id is None) == (body.scaffold_id is None):
        raise validation_error("equipment_id", "Give one of equipment_id or scaffold_id.")
    item = sc = None
    eng: uuid.UUID | None = None
    sites: list[uuid.UUID] = []
    if body.equipment_id is not None:
        item = db.get(EquipmentItem, body.equipment_id)
        dep = cc.latest_deployment_on(db, body.equipment_id, project.id) if item else None
        if item is None or dep is None:
            raise validation_error("equipment_id", "The item has no deployment on this project.")
        eng, sites = dep.engagement_id, list(dep.site_ids)
    else:
        sc = db.get(Scaffold, body.scaffold_id)
        if sc is None or sc.project_id != project.id:
            raise validation_error("scaffold_id", "Unknown scaffold on this project.")
        from app.models import Zone  # noqa: PLC0415

        z = db.get(Zone, sc.zone_id)
        eng, sites = sc.engagement_id, [z.site_id] if z else []
    cc.require(p, project.id, C.defect_raise, eng, sites)
    if body.source == DefectSource.tpi_inspection:
        raise validation_error("source", "TPI defects come from certificate lines (DF-2).")
    at = body.raised_at or now()
    if at > now() + timedelta(minutes=5):
        raise validation_error("raised_at", "Cannot be in the future.")
    if body.category == DefectCategory.A and not body.physical_tag_applied:
        raise ApiError(
            422,
            ErrorCode.PHYSICAL_TAG_REQUIRED,
            "Apply the physical red 'Do not use' tag (DF-3).",
            "ضع البطاقة الحمراء «ممنوع الاستخدام» على المعدة.",
        )
    if body.raised_by_worker_id is not None and db.get(Worker, body.raised_by_worker_id) is None:
        raise validation_error("raised_by_worker_id", "Unknown worker.")
    if body.tpi_due_date is not None and body.category != DefectCategory.B:
        raise validation_error("tpi_due_date", "Only category B defects have a due date.")
    d = new_defect(
        db,
        project.id,
        item=item,
        scaffold=sc,
        engagement_id=eng,
        source=body.source,
        category=body.category,
        description_en=body.description_en,
        description_ar=body.description_ar,
        raised_at=at,
        p=p,
        raised_by_worker_id=body.raised_by_worker_id,
        source_ref=body.source_ref,
        tpi_due_date=body.tpi_due_date,
        physical_tag_applied=body.physical_tag_applied,
        photo_attachment_ids=list(body.photo_attachment_ids),
    )
    return defect_read(db, p, d)


# ---- rectify / close / reopen / destroy / cancel -------------------------------------------------


def _item(db: Session, d: EquipmentDefect) -> EquipmentItem | None:
    return db.get(EquipmentItem, d.equipment_id) if d.equipment_id else None


def _destroy_only(item: EquipmentItem | None, d: EquipmentDefect) -> bool:
    return item is not None and item.category in ref.DESTROY_ONLY and d.category == DefectCategory.A


def rectify(
    db: Session, p: Principal, defect_id: uuid.UUID, body: RectificationInput
) -> DefectRead:
    d = _get(db, p, defect_id)
    _require(db, p, d, C.defect_rectify)
    item = _item(db, d)
    if _destroy_only(item, d):
        raise ApiError(
            422,
            ErrorCode.ACCESSORY_REPAIR_NOT_ALLOWED,
            "A category A defect on a lifting accessory or rescue winch cannot be repaired: "
            "destroy it or return it to the manufacturer (DF-7).",
            "لا يجوز إصلاح عيب من الفئة A في ملحقات الرفع أو رافعة الإنقاذ: تُتلف أو تعاد للمصنع.",
        )
    if d.status != DS.open:
        raise invalid_transition("Defect", d.status, DS.rectified)
    if body.done_at > now() + timedelta(minutes=5):
        raise validation_error("done_at", "Cannot be in the future.")
    if body.done_at < d.raised_at:
        raise validation_error("done_at", "Cannot be before the defect was raised.")
    before = cc.snap(d)
    d.rectification = {
        "description": body.description,
        "done_by_text": body.done_by_text,
        "done_at": body.done_at.isoformat(),
        "evidence_attachment_ids": [str(x) for x in body.evidence_attachment_ids],
    }
    d.rectified_by_user_id = p.user.id
    d.rectified_at = now()
    d.status = DS.rectified
    cc.stamp(d, p)
    db.flush()
    cc.record(
        db, p, AuditAction.status_change, EntityType.equipment_defect, d, d.project_id, before
    )
    return defect_read(db, p, d)


def _employed_by_owner(db: Session, p: Principal, item: EquipmentItem | None) -> bool:
    return (
        item is not None
        and not p.is_manager
        and p.user.employer_contractor_id is not None
        and p.user.employer_contractor_id == item.owner_contractor_id
    )


def close(db: Session, p: Principal, defect_id: uuid.UUID, body: DefectCloseInput) -> DefectRead:
    d = _get(db, p, defect_id)
    _require(db, p, d, C.defect_close)
    if d.status != DS.rectified:
        raise invalid_transition("Defect", d.status, DS.closed)
    item = _item(db, d)
    if p.user.id == d.rectified_by_user_id or _employed_by_owner(db, p, item):
        raise cc.sod()
    if body.method == DefectClosureMethod.destroyed:
        raise validation_error("method", "Use the destroy action for DF-7 closures.")
    needs_tpi = (
        item is not None
        and d.category == DefectCategory.A
        and item.category in ref.TPI_REINSPECTION_CATEGORIES
        and body.requires_tpi_reinspection is not False
    )
    line_id = None
    if body.method == DefectClosureMethod.tpi_certificate or needs_tpi:
        if body.method != DefectClosureMethod.tpi_certificate or body.cert_line_id is None:
            raise _reinspection_required()
        rect_day = (
            acommon.local_day(datetime.fromisoformat(d.rectification["done_at"]))
            if d.rectification
            else acommon.local_day(d.raised_at)
        )
        line = db.get(EquipmentCertLine, body.cert_line_id)
        cert = db.get(EquipmentCertificate, line.certificate_id) if line else None
        if (
            line is None
            or cert is None
            or line.equipment_id != d.equipment_id
            or cert.status != CertificateStatus.accepted
            or cert.verification_status != VerificationStatus.verified
            or cert.inspection_type != CertInspectionType.after_repair
            or cert.inspected_on < rect_day
        ):
            raise _reinspection_required()
        line_id = line.id
    elif not body.evidence_attachment_ids:
        raise validation_error(
            "evidence_attachment_ids", "HSE verification needs photo evidence (DF-6)."
        )
    before = cc.snap(d)
    d.closure = {
        "method": body.method.value,
        "cert_line_id": str(line_id) if line_id else None,
        "note": body.note,
        "evidence_attachment_ids": [str(x) for x in body.evidence_attachment_ids],
    }
    d.closed_by_user_id = p.user.id
    d.closed_at = now()
    d.status = DS.closed
    cc.stamp(d, p)
    db.flush()
    cc.record(
        db, p, AuditAction.status_change, EntityType.equipment_defect, d, d.project_id, before
    )
    return defect_read(db, p, d)


def _reinspection_required() -> ApiError:
    return ApiError(
        422,
        ErrorCode.TPI_REINSPECTION_REQUIRED,
        "Closure needs an accepted, verified after_repair certificate line inspected after "
        "the rectification (DF-6).",
        "يتطلب الإغلاق شهادة فحص بعد الإصلاح مقبولة ومتحقق منها وتاريخ فحصها بعد الإصلاح.",
    )


def reopen(db: Session, p: Principal, defect_id: uuid.UUID, body: DefectReopenInput) -> DefectRead:
    d = _get(db, p, defect_id)
    _require(db, p, d, C.defect_close)
    if d.status != DS.rectified:
        raise invalid_transition("Defect", d.status, DS.open)
    before = cc.snap(d)
    d.status = DS.open
    d.rectification = {**(d.rectification or {}), "reopened_reason": body.reason}
    cc.stamp(d, p)
    db.flush()
    cc.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.equipment_defect,
        d,
        d.project_id,
        before,
        {"reason": body.reason},
    )
    return defect_read(db, p, d)


def destroy(
    db: Session, p: Principal, defect_id: uuid.UUID, body: DefectDestroyInput
) -> DefectRead:
    d = _get(db, p, defect_id)
    _require(db, p, d, C.defect_close)
    item = _item(db, d)
    if not _destroy_only(item, d) or d.status != DS.open:
        raise invalid_transition("Defect", d.status, "destroyed")
    assert item is not None  # noqa: S101
    close_destroyed(db, d, item, p, body.note, body.returned_to_manufacturer)
    return defect_read(db, p, d)


def close_destroyed(
    db: Session,
    d: EquipmentDefect,
    item: EquipmentItem,
    p: Principal | None,
    note: str,
    returned: bool = False,
    at: datetime | None = None,
) -> None:
    from app.services.cert import equipment  # noqa: PLC0415

    before = cc.snap(d)
    d.closure = {
        "method": DefectClosureMethod.destroyed.value,
        "cert_line_id": None,
        "note": note,
        "returned_to_manufacturer": returned,
        "evidence_attachment_ids": [],
    }
    d.closed_by_user_id = p.user.id if p else None
    d.closed_at = at or now()
    d.status = DS.closed
    cc.stamp(d, p)
    db.flush()
    cc.record(
        db, p, AuditAction.status_change, EntityType.equipment_defect, d, d.project_id, before
    )
    equipment.retire_destroyed(db, item, p, d.defect_no, at)


def cancel(db: Session, p: Principal, defect_id: uuid.UUID, body: DefectCancelInput) -> DefectRead:
    d = _get(db, p, defect_id)
    _require(db, p, d, C.defect_close)
    if d.source == DefectSource.tpi_inspection:
        raise ApiError(
            422,
            ErrorCode.TPI_DEFECT_NOT_CANCELLABLE,
            "Defects raised by a TPI certificate cannot be cancelled.",
            "لا يمكن إلغاء العيوب الواردة في شهادة جهة الفحص.",
        )
    if d.status not in (DS.open, DS.rectified):
        raise invalid_transition("Defect", d.status, DS.cancelled)
    before = cc.snap(d)
    d.status = DS.cancelled
    d.cancelled_reason = body.reason
    cc.stamp(d, p)
    db.flush()
    cc.record(
        db, p, AuditAction.status_change, EntityType.equipment_defect, d, d.project_id, before
    )
    return defect_read(db, p, d)


# ---- DF-4 job ------------------------------------------------------------------------------------


def overdue_job(db: Session, at: datetime | None = None) -> int:
    """B defects not Closed by due_date → item Out of Service at due_date + 1 00:05."""
    from app.services.cert import equipment  # noqa: PLC0415

    at = at or now()
    d = acommon.local_day(at)
    n = 0
    for x in db.scalars(
        select(EquipmentDefect).where(
            EquipmentDefect.category == DefectCategory.B,
            EquipmentDefect.status.in_([DS.open, DS.rectified]),
            EquipmentDefect.overdue_applied.is_(False),
            EquipmentDefect.due_date < d,
        )
    ):
        x.overdue_applied = True
        item = _item(db, x)
        if item is None:
            continue
        n += 1
        if item.service_status not in (ServiceStatus.blacklisted, ServiceStatus.retired):
            equipment.set_status(
                db,
                item,
                ServiceStatus.out_of_service,
                ServiceStatusReason.defect_b_overdue,
                None,
                x.description_en[:500],
                x.defect_no,
                at,
            )
        dep = cc.latest_deployment_on(db, item.id, x.project_id)
        tag = dep.tag if dep else item.equipment_no
        alerts.send(
            db,
            alerts.reps(db, x.project_id, x.engagement_id) | alerts.officers(db, x.project_id),
            NotificationKind.equipment_out_of_service,
            f"{tag}: out of service — category B defect {x.defect_no} overdue",
            f"{tag}: خارج الخدمة — عيب من الفئة B {x.defect_no} متأخر",
            EntityType.equipment_defect,
            x.id,
            x.project_id,
            email=True,
        )
    return n


# ---- DF-9 incident prompt ------------------------------------------------------------------------


def incident_prompt(db: Session, p: Principal, incident_id: uuid.UUID) -> IncidentDefectPrompt:
    from app.services import incidents  # noqa: PLC0415

    inc: Incident = incidents.get_incident(db, p, incident_id)
    agencies = {
        c.agency for c in db.scalars(select(InjuryCase).where(InjuryCase.incident_id == inc.id))
    }
    hit = sorted(a.value for a in agencies if a in PROMPT_AGENCIES)
    do_hit = inc.do_category in PROMPT_DO
    agency = (
        hit[0]
        if hit
        else (
            "crane_lifting_gear"
            if inc.do_category == DangerousOccurrenceCategory.crane_lifting_failure
            else "scaffold"
            if do_hit
            else None
        )
    )
    linked = []
    if p.grant(inc.project_id, C.cert_register_view) is not None:
        linked = [
            defect_read(db, p, d)
            for d in db.scalars(
                select(EquipmentDefect).where(
                    EquipmentDefect.project_id == inc.project_id,
                    EquipmentDefect.source_ref == inc.ref,
                )
            )
        ]
    return IncidentDefectPrompt(
        incident_id=inc.id,
        incident_ref=inc.ref,
        prompt=bool(hit) or do_hit,
        agency=agency,
        linked_defects=linked,
    )


def open_for(db: Session, item_id: uuid.UUID) -> list[EquipmentDefect]:
    return list(
        db.scalars(
            select(EquipmentDefect).where(
                EquipmentDefect.equipment_id == item_id,
                EquipmentDefect.status.in_([DS.open, DS.rectified]),
            )
        )
    )
