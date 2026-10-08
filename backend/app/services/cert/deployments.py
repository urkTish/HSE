"""Equipment deployments on projects: plan, mobilisation approval, arrival, arrival inspection,
demobilisation and the EQ sticker (spec 4-third-party-cert §3.5, §4.3, EQ-5, EM-1…EM-6, GE-3)."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.access_enums import HookSubjectType, QrKind, QrTokenStatus
from app.core.cert_enums import (
    ArrivalChecklistItem,
    ChecklistItemResult,
    DefectSource,
    EquipmentCertCategory,
    EquipmentDeploymentStatus,
    PassFail,
    ServiceStatus,
)
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, ContractorStatus, EntityType, Role
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.models import (
    EquipmentDefect,
    EquipmentDeployment,
    EquipmentItem,
    ProjectEngagement,
    Vehicle,
)
from app.schemas.equipment import (
    ArrivalChecklistLineRead,
    ArrivalInspectionInput,
    ArrivalInspectionRead,
    EquipmentDeploymentCreate,
    EquipmentDeploymentPage,
    EquipmentDeploymentRead,
    EquipmentDeploymentTransition,
    EquipmentDeploymentUpdate,
    EquipmentStickerRead,
    StickerReissueRequest,
)
from app.schemas.hse_common import ApiWarning, UserRef
from app.services import projects
from app.services.access import common as acommon
from app.services.access.hooks import HookContext
from app.services.cert import common as cc
from app.services.cert import events, providers
from app.services.cert import reference as ref
from app.services.cert import settings as cset
from app.services.common import invalid_transition, paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal, engagement_descendants, forbidden_error

C = Capability
DS = EquipmentDeploymentStatus


# ---- scope ---------------------------------------------------------------------------------------


def get_row(db: Session, deployment_id: uuid.UUID) -> EquipmentDeployment:
    d = db.get(EquipmentDeployment, deployment_id)
    if d is None:
        raise not_found("Deployment")
    return d


def get_visible(db: Session, p: Principal, deployment_id: uuid.UUID) -> EquipmentDeployment:
    d = get_row(db, deployment_id)
    if not acommon.grant_covers(
        p.grant(d.project_id, C.cert_register_view), d.site_ids, d.engagement_id
    ):
        raise not_found("Deployment")
    return d


def printed_ref(project_code: str, tag: str) -> str:
    return f"{project_code}-{tag}"


# ---- read ----------------------------------------------------------------------------------------


def usable(
    db: Session, d: EquipmentDeployment, item: EquipmentItem, at: datetime | None = None
) -> tuple[bool, str | None]:
    """§6.6 'item usable' on the project (provider order HK4-8)."""
    at = at or now()
    if item.service_status in (
        ServiceStatus.out_of_service,
        ServiceStatus.blacklisted,
        ServiceStatus.retired,
    ):
        return (
            False,
            item.service_status_reason.value
            if item.service_status_reason
            else item.service_status.value,
        )
    e = ref.EQC.get(item.category)
    if e is None:
        return False, None
    res = providers.check_equipment(
        db,
        HookSubjectType.equipment_tag,
        d.id,
        e.hook_code,
        at,
        HookContext(project_id=d.project_id, equipment_item_id=item.id, equipment_tag=d.tag),
    )
    from app.core.access_enums import HookProviderStatus as P  # noqa: PLC0415

    ok = res.status in (P.met, P.expiring)
    return ok, None if ok else res.reason_code


def arrival_due_at(db: Session, d: EquipmentDeployment) -> datetime | None:
    if d.status != DS.on_site or d.arrival_inspection_passed or d.arrived_at is None:
        return None
    s = cset.get(db, d.project_id)
    return d.arrived_at + timedelta(hours=s.arrival_inspection_hours)


def _inspection_read(
    db: Session, d: EquipmentDeployment, refs: Refs
) -> ArrivalInspectionRead | None:
    ai = d.arrival_inspection
    if not ai:
        return None
    by = refs.user(uuid.UUID(ai["by"])) if ai.get("by") else None
    defects = [db.get(EquipmentDefect, uuid.UUID(x)) for x in ai.get("defect_ids", [])]
    return ArrivalInspectionRead(
        at=datetime.fromisoformat(ai["at"]),
        by=by or UserRef(id=uuid.UUID(int=0), full_name_en="System", full_name_ar="النظام"),
        checklist=[
            ArrivalChecklistLineRead(
                item=ArrivalChecklistItem(x["item"]),
                label_en=ref.AIC_TEXT[ArrivalChecklistItem(x["item"])][0],
                label_ar=ref.AIC_TEXT[ArrivalChecklistItem(x["item"])][1],
                result=ChecklistItemResult(x["result"]),
            )
            for x in ai.get("checklist", [])
        ],
        result=PassFail(ai["result"]),
        notes=ai.get("notes"),
        defects=[cc.defect_ref(x) for x in defects if x is not None],
    )


def dep_read(
    db: Session, p: Principal | None, d: EquipmentDeployment, refs: Refs | None = None
) -> EquipmentDeploymentRead:
    refs = refs or Refs(db)
    item = db.get(EquipmentItem, d.equipment_id)
    assert item is not None  # noqa: S101
    tok = acommon.active_qr(db, d.id)
    ok, why = usable(db, d, item)
    warnings: list[ApiWarning] = []
    due = arrival_due_at(db, d)
    if due is not None:
        warnings.append(
            cc.warn(
                "ARRIVAL_INSPECTION_DUE",
                f"Arrival inspection due by {due.isoformat()}",
                "فحص الوصول مستحق",
            )
        )
    from app.services.cert import validity  # noqa: PLC0415

    ic = validity.current_line(db, item.id, now())
    if ic.ev.in_force and ic.ev.expiring:
        warnings.append(
            cc.warn("EXPIRING_7D", "Certificate expires within 7 days", "الشهادة تنتهي خلال 7 أيام")
        )
    if ic.ev.in_force and ic.ev.window_until:
        warnings.append(
            cc.warn(
                "CERT_UNVERIFIED",
                "Certificate not yet verified with the TPI",
                "الشهادة غير متحقق منها بعد",
            )
        )
    return EquipmentDeploymentRead(
        id=d.id,
        deployment_no=d.deployment_no,
        project_id=d.project_id,
        equipment=cc.equipment_ref(db, item),
        engagement=refs.eng_required(d.engagement_id),
        tag=d.tag,
        sites=[refs.site(s) for s in d.site_ids or []],
        zone=refs.zone(d.zone_id),
        planned_arrival_on=d.planned_arrival_on,
        approved_by=refs.user(d.approved_by_user_id) if d.approved_by_user_id else None,
        approved_at=d.approved_at,
        arrived_at=d.arrived_at,
        arrival_inspection=_inspection_read(db, d, refs),
        arrival_inspection_due_at=due,
        status=d.status,
        demobilised_on=d.demobilised_on,
        sticker_printed_ref=tok.printed_ref if tok else None,
        has_sticker=tok is not None,
        usable=ok and d.status in (DS.approved, DS.on_site),
        not_usable_reason=why
        if not ok
        else (None if d.status in (DS.approved, DS.on_site) else "EQUIPMENT_NOT_DEPLOYED"),
        warnings=warnings,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def read(db: Session, p: Principal, deployment_id: uuid.UUID) -> EquipmentDeploymentRead:
    return dep_read(db, p, get_visible(db, p, deployment_id))


def list_deployments(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    q: str | None = None,
    statuses: list[EquipmentDeploymentStatus] | None = None,
    categories: list[EquipmentCertCategory] | None = None,
    service_statuses: list[ServiceStatus] | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    include_subcontractors: bool = True,
    site_id: uuid.UUID | None = None,
    arrival_inspection_due: bool | None = None,
) -> EquipmentDeploymentPage:
    project = projects.get_visible(db, p, project_id)
    g = p.grant(project.id, C.cert_register_view)
    if g is None:
        raise forbidden_error()
    stmt = (
        select(EquipmentDeployment)
        .join(EquipmentItem, EquipmentItem.id == EquipmentDeployment.equipment_id)
        .where(EquipmentDeployment.project_id == project.id)
    )
    if g.engagement_ids is not None:
        stmt = stmt.where(EquipmentDeployment.engagement_id.in_(list(g.engagement_ids)))
    if g.site_ids is not None:
        stmt = stmt.where(EquipmentDeployment.site_ids.overlap(list(g.site_ids)))
    if q:
        pat = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                EquipmentDeployment.tag.ilike(pat),
                EquipmentItem.equipment_no.ilike(pat),
                EquipmentDeployment.deployment_no.ilike(pat),
            )
        )
    if statuses:
        stmt = stmt.where(EquipmentDeployment.status.in_(statuses))
    if categories:
        stmt = stmt.where(EquipmentItem.category.in_(categories))
    if service_statuses:
        stmt = stmt.where(EquipmentItem.service_status.in_(service_statuses))
    if engagement_ids:
        ids: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                ids |= engagement_descendants(db, e)
        stmt = stmt.where(EquipmentDeployment.engagement_id.in_(ids))
    if site_id:
        stmt = stmt.where(EquipmentDeployment.site_ids.contains([site_id]))
    if arrival_inspection_due is not None:
        cond = (EquipmentDeployment.status == DS.on_site) & (
            EquipmentDeployment.arrival_inspection_passed.is_(False)
        )
        stmt = stmt.where(cond if arrival_inspection_due else ~cond)
    stmt = stmt.order_by(EquipmentDeployment.tag)
    rows, total = paginate(db, stmt, page, page_size)
    refs = Refs(db)
    return EquipmentDeploymentPage(
        items=[dep_read(db, p, d, refs) for d in rows], total=total, page=page, page_size=page_size
    )


# ---- create / update -----------------------------------------------------------------------------


def _tag_taken(db: Session, project_id: uuid.UUID, tag: str, exclude: uuid.UUID | None) -> bool:
    stmt = select(EquipmentDeployment.id).where(
        EquipmentDeployment.project_id == project_id,
        func.upper(EquipmentDeployment.tag) == tag.upper(),
        EquipmentDeployment.status.notin_([DS.demobilised, DS.cancelled]),
    )
    if exclude is not None:
        stmt = stmt.where(EquipmentDeployment.id != exclude)
    return db.scalar(stmt.limit(1)) is not None


def _tag_exists() -> ApiError:
    return ApiError(
        409,
        ErrorCode.TAG_EXISTS,
        "This tag is already used on the project (EM-1).",
        "هذا الوسم مستخدم مسبقاً في المشروع.",
    )


def _check_sites(eng: ProjectEngagement, site_ids: list[uuid.UUID]) -> None:
    if not set(site_ids) <= set(eng.site_ids or []):
        raise validation_error("site_ids", "Sites must be within the engagement's sites (EM-1).")


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: EquipmentDeploymentCreate
) -> EquipmentDeploymentRead:
    project = projects.get_visible(db, p, project_id)
    eng = db.get(ProjectEngagement, body.engagement_id)
    if eng is None or eng.project_id != project.id:
        raise validation_error("engagement_id", "The engagement is not on this project.")
    cc.require(p, project.id, C.equipment_edit, eng.id, body.site_ids)
    if cc.site_engineer_only(p, project.id):
        raise forbidden_error("Site engineers record scaffolds and configuration events only.")
    item = db.get(EquipmentItem, body.equipment_id)
    if item is None:
        raise validation_error("equipment_id", "Unknown equipment item.")
    if item.service_status in (ServiceStatus.retired, ServiceStatus.blacklisted):
        raise ApiError(
            422,
            ErrorCode.EQUIPMENT_BLACKLISTED
            if item.service_status == ServiceStatus.blacklisted
            else ErrorCode.EQUIPMENT_RETIRED,
            "This item cannot be deployed.",
            "لا يمكن تعيين هذه المعدة.",
        )
    live = cc.live_deployment(db, item.id)
    if live is not None:
        raise ApiError(
            422,
            ErrorCode.EQUIPMENT_DEPLOYED_ELSEWHERE,
            "The item already has a live deployment; demobilise it first (EM-4).",
            "للمعدة تعيين قائم؛ يجب تسريحها أولاً.",
            meta={"deployment_no": live.deployment_no},
        )
    if eng.contractor_id != item.owner_contractor_id:
        raise validation_error(
            "engagement_id", "The engagement must be the owner's (or hiring contractor's)."
        )
    if eng.contractor.status != ContractorStatus.approved:
        raise ApiError(
            422,
            ErrorCode.CONTRACTOR_SUSPENDED,
            "The owner contractor is not Approved (EQ-5).",
            "المقاول المالك غير معتمد.",
        )
    _check_sites(eng, body.site_ids)
    if body.zone_id is not None:
        from app.models import Zone  # noqa: PLC0415

        z = db.get(Zone, body.zone_id)
        if z is None or z.site_id not in body.site_ids:
            raise validation_error("zone_id", "The zone must be on one of the sites.")
    tag = body.tag.strip().upper()
    if _tag_taken(db, project.id, tag, None):
        raise _tag_exists()
    seq = (
        db.scalar(
            select(func.max(EquipmentDeployment.seq)).where(
                EquipmentDeployment.project_id == project.id
            )
        )
        or 0
    ) + 1
    d = EquipmentDeployment(
        id=uuid.uuid4(),
        project_id=project.id,
        seq=seq,
        deployment_no=f"EQD-{project.code}-{seq:04d}",
        equipment_id=item.id,
        engagement_id=eng.id,
        tag=tag,
        site_ids=list(body.site_ids),
        zone_id=body.zone_id,
        planned_arrival_on=body.planned_arrival_on,
        status=DS.planned,
        alerts_sent=[],
    )
    cc.stamp(d, p, create=True)
    db.add(d)
    db.flush()
    cc.record(db, p, AuditAction.create, EntityType.equipment_deployment, d, project.id)
    return dep_read(db, p, d)


def update(
    db: Session, p: Principal, deployment_id: uuid.UUID, body: EquipmentDeploymentUpdate
) -> EquipmentDeploymentRead:
    d = get_visible(db, p, deployment_id)
    cc.require(p, d.project_id, C.equipment_edit, d.engagement_id, d.site_ids)
    if cc.site_engineer_only(p, d.project_id):
        raise forbidden_error("Site engineers record scaffolds and configuration events only.")
    if d.status in (DS.demobilised, DS.cancelled):
        raise invalid_transition("Deployment", d.status, "edited")
    before = cc.snap(d)
    ch = body.changes()
    eng = db.get(ProjectEngagement, d.engagement_id)
    assert eng is not None  # noqa: S101
    if "tag" in ch:
        tag = ch["tag"].strip().upper()
        if _tag_taken(db, d.project_id, tag, d.id):
            raise _tag_exists()
        ch["tag"] = tag
    if "site_ids" in ch:
        _check_sites(eng, ch["site_ids"])
        cc.require(p, d.project_id, C.equipment_edit, d.engagement_id, ch["site_ids"])
    for k, v in ch.items():
        setattr(d, k, v)
    cc.stamp(d, p)
    db.flush()
    if "tag" in ch and (tok := acommon.active_qr(db, d.id)) is not None:
        tok.printed_ref = printed_ref(cc.project_code(db, d.project_id), d.tag)
    cc.record(db, p, AuditAction.update, EntityType.equipment_deployment, d, d.project_id, before)
    events.publish(db, "equipment.status_changed", item_ids=[d.equipment_id])
    return dep_read(db, p, d)


# ---- transitions (§4.3) --------------------------------------------------------------------------


ALLOWED: dict[EquipmentDeploymentStatus, set[EquipmentDeploymentStatus]] = {
    DS.planned: {DS.approved, DS.cancelled},
    DS.approved: {DS.on_site, DS.demobilised},
    DS.on_site: {DS.demobilised},
}


def _roles(p: Principal, project_id: uuid.UUID) -> set[Role]:
    return cc.roles_on(p, project_id)


def transition(
    db: Session, p: Principal, deployment_id: uuid.UUID, body: EquipmentDeploymentTransition
) -> EquipmentDeploymentRead:
    d = get_visible(db, p, deployment_id)
    src, dst = d.status, body.to_status
    if dst not in ALLOWED.get(src, set()):
        raise invalid_transition("Deployment", src, dst)
    roles = _roles(p, d.project_id)
    if dst == DS.cancelled:
        try:
            cc.require(p, d.project_id, C.equipment_mobilise, d.engagement_id, d.site_ids)
        except ApiError:
            cc.require(p, d.project_id, C.equipment_edit, d.engagement_id, d.site_ids)
    else:
        cc.require(p, d.project_id, C.equipment_mobilise, d.engagement_id, d.site_ids)
    hse = p.is_manager or Role.hse_officer in roles
    if not hse:
        if dst == DS.on_site and not roles & {Role.site_engineer}:
            raise forbidden_error()
        if dst == DS.approved:
            raise forbidden_error("Mobilisation approval is for HSE staff (row 109).")
        if dst == DS.demobilised and not roles & {Role.contractor_hse_rep}:
            raise forbidden_error()
    item = db.get(EquipmentItem, d.equipment_id)
    assert item is not None  # noqa: S101
    before = cc.snap(d)
    at = now()
    if dst == DS.approved:
        approve_checks(db, d, item)
        d.approved_by_user_id = p.user.id
        d.approved_at = at
        acommon.end_qr(db, d.id, QrTokenStatus.rotated)
        acommon.issue_qr(
            db, QrKind.EQ, d.project_id, d.id, printed_ref(cc.project_code(db, d.project_id), d.tag)
        )
    elif dst == DS.on_site:
        arrived = body.arrived_at or at
        if arrived > at + timedelta(minutes=5):
            raise validation_error("arrived_at", "Cannot be in the future.")
        d.arrived_at = arrived
    elif dst == DS.demobilised:
        d.demobilised_on = body.demobilised_on or today()
        d.status_reason = body.reason
        acommon.end_qr(db, d.id, QrTokenStatus.revoked)
    elif dst == DS.cancelled:
        d.status_reason = body.reason
        acommon.end_qr(db, d.id, QrTokenStatus.revoked)
    d.status = dst
    cc.stamp(d, p)
    db.flush()
    cc.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.equipment_deployment,
        d,
        d.project_id,
        before,
        {"from": src.value, "to": dst.value},
    )
    events.publish(db, "equipment.status_changed", item_ids=[item.id])
    return dep_read(db, p, d)


def approve_checks(db: Session, d: EquipmentDeployment, item: EquipmentItem) -> None:
    """EM-2."""
    if item.service_status != ServiceStatus.in_service:
        reason = (
            item.service_status_reason.value
            if item.service_status_reason
            else item.service_status.value
        )
        raise ApiError(
            422,
            ErrorCode.EQUIPMENT_NOT_IN_SERVICE,
            "The item is not In Service (EM-2).",
            "المعدة ليست في الخدمة.",
            meta={"reason": reason, "service_status": item.service_status.value},
        )
    eng = db.get(ProjectEngagement, d.engagement_id)
    if eng is None or eng.contractor.status in (
        ContractorStatus.suspended,
        ContractorStatus.blacklisted,
    ):
        raise ApiError(
            422,
            ErrorCode.CONTRACTOR_SUSPENDED,
            "The contractor is suspended or blacklisted (EM-2).",
            "المقاول موقوف أو محظور.",
        )
    if item.vehicle_id is not None:
        v = db.get(Vehicle, item.vehicle_id)
        if v is None or v.project_id != d.project_id:
            raise validation_error(
                "vehicle_id", "The linked vehicle is not registered on this project (EM-2)."
            )


def arrive(db: Session, d: EquipmentDeployment, at: datetime, p: Principal | None = None) -> None:
    """GE-3: the first gate `in` scan of an Approved deployment sets On Site."""
    if d.status != DS.approved:
        return
    before = cc.snap(d)
    d.status = DS.on_site
    d.arrived_at = at
    db.flush()
    cc.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.equipment_deployment,
        d,
        d.project_id,
        before,
        {"from": "approved", "to": "on_site", "via": "gate_scan"},
    )
    events.publish(db, "equipment.status_changed", item_ids=[d.equipment_id])


# ---- arrival inspection (EM-3) -------------------------------------------------------------------


def record_arrival_inspection(
    db: Session, p: Principal, deployment_id: uuid.UUID, body: ArrivalInspectionInput
) -> ArrivalInspectionRead:
    d = get_visible(db, p, deployment_id)
    cc.require(p, d.project_id, C.equipment_mobilise, d.engagement_id, d.site_ids)
    roles = _roles(p, d.project_id)
    if not (p.is_manager or roles & {Role.hse_officer, Role.site_engineer}):
        raise forbidden_error()
    if d.status != DS.on_site:
        raise invalid_transition("Deployment", d.status, "arrival_inspection")
    items = [x.item for x in body.checklist]
    if len(set(items)) != len(ArrivalChecklistItem) or set(items) != set(ArrivalChecklistItem):
        raise validation_error("checklist", "Answer every AIC item once.")
    at = body.inspected_at or now()
    if at > now() + timedelta(minutes=5):
        raise validation_error("inspected_at", "Cannot be in the future.")
    failed = [x for x in body.checklist if x.result == ChecklistItemResult.fail]
    for x in failed:
        if x.defect_category is None or not (x.defect_description or "").strip():
            raise validation_error(
                "checklist",
                f"{x.item.value}: a failed item needs a defect category and description.",
            )
    item = db.get(EquipmentItem, d.equipment_id)
    assert item is not None  # noqa: S101
    from app.services.cert import defects  # noqa: PLC0415

    defect_ids: list[str] = []
    for x in failed:
        assert x.defect_category is not None  # noqa: S101
        df = defects.new_defect(
            db,
            d.project_id,
            item=item,
            scaffold=None,
            engagement_id=d.engagement_id,
            source=DefectSource.arrival_inspection,
            category=x.defect_category,
            description_en=f"{x.item.value}: {x.defect_description}",
            raised_at=at,
            p=p,
            source_ref=d.deployment_no,
            physical_tag_applied=True,
        )
        defect_ids.append(str(df.id))
    before = cc.snap(d)
    result = PassFail.fail if failed else PassFail.pass_
    d.arrival_inspection = {
        "at": at.isoformat(),
        "by": str(p.user.id),
        "checklist": [{"item": x.item.value, "result": x.result.value} for x in body.checklist],
        "result": result.value,
        "notes": body.notes,
        "defect_ids": defect_ids,
    }
    d.arrival_inspection_passed = result == PassFail.pass_
    cc.stamp(d, p)
    db.flush()
    cc.record(db, p, AuditAction.update, EntityType.equipment_deployment, d, d.project_id, before)
    events.publish(db, "equipment.status_changed", item_ids=[item.id])
    out = _inspection_read(db, d, Refs(db))
    assert out is not None  # noqa: S101
    return out


# ---- stickers ------------------------------------------------------------------------------------


def sticker_read(db: Session, d: EquipmentDeployment) -> EquipmentStickerRead:
    tok = acommon.active_qr(db, d.id)
    if tok is None:
        raise ApiError(
            409,
            ErrorCode.EQUIPMENT_NOT_APPROVED,
            "The sticker is issued at mobilisation approval (EM-2).",
            "يصدر الملصق عند اعتماد التعبئة.",
        )
    item = db.get(EquipmentItem, d.equipment_id)
    assert item is not None  # noqa: S101
    return EquipmentStickerRead(
        deployment=cc.deployment_ref(d),
        qr_payload=acommon.payload(tok),
        printed_ref=tok.printed_ref,
        category=item.category,
        tag=d.tag,
        owner_short_code=cc.owner_code(db, item.owner_contractor_id) or "",
        issued_at=tok.created_at,
    )


def get_sticker(db: Session, p: Principal, deployment_id: uuid.UUID) -> EquipmentStickerRead:
    return sticker_read(db, get_visible(db, p, deployment_id))


def reissue_sticker(
    db: Session, p: Principal, deployment_id: uuid.UUID, body: StickerReissueRequest
) -> EquipmentStickerRead:
    d = get_visible(db, p, deployment_id)
    cc.require(p, d.project_id, C.equipment_mobilise, d.engagement_id, d.site_ids)
    if d.status not in (DS.approved, DS.on_site):
        raise invalid_transition("Deployment", d.status, "sticker_reissue")
    acommon.end_qr(db, d.id, QrTokenStatus.rotated)
    acommon.issue_qr(
        db, QrKind.EQ, d.project_id, d.id, printed_ref(cc.project_code(db, d.project_id), d.tag)
    )
    cc.record(
        db,
        p,
        AuditAction.update,
        EntityType.equipment_deployment,
        d,
        d.project_id,
        None,
        {"sticker_reissued": body.reason},
        after={"sticker": "rotated"},
    )
    return sticker_read(db, d)


def blacklisted_contractor_job(db: Session) -> int:
    """EM-6: deployments of a Blacklisted contractor (or ended engagement) are Demobilised."""
    n = 0
    d0 = today()
    for d in db.scalars(
        select(EquipmentDeployment).where(EquipmentDeployment.status.in_(cc.LIVE_DEPLOYMENT))
    ):
        eng = db.get(ProjectEngagement, d.engagement_id)
        if eng is None:
            continue
        ended = eng.demobilisation_date is not None and eng.demobilisation_date < d0
        if (
            eng.contractor.status in (ContractorStatus.blacklisted, ContractorStatus.demobilised)
            or ended
        ):
            before = cc.snap(d)
            if d.status == DS.planned:
                d.status = DS.cancelled
            else:
                d.status = DS.demobilised
                d.demobilised_on = d0
            d.status_reason = (
                "contractor_blacklisted"
                if eng.contractor.status == ContractorStatus.blacklisted
                else "engagement_ended"
            )
            acommon.end_qr(db, d.id, QrTokenStatus.revoked)
            cc.record(
                db,
                None,
                AuditAction.status_change,
                EntityType.equipment_deployment,
                d,
                d.project_id,
                before,
                {"system": d.status_reason},
            )
            events.publish(db, "equipment.status_changed", item_ids=[d.equipment_id])
            n += 1
    return n
