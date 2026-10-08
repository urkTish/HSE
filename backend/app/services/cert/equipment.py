"""Equipment register (org-wide), service status engine, tag-out, return to service,
retirement, equipment blacklist and configuration events (spec 4-third-party-cert §3.4, §3.7,
§3.13, §4.2, EQ-1…EQ-4, EQ-6, CF-1…CF-4, DF-6, DF-8, BL-3)."""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.access_enums import QrTokenStatus
from app.core.cert_enums import (
    CertificateStatus,
    CertInspectionType,
    CertStatusReason,
    ConfigurationEventType,
    DefectCategory,
    DefectStatus,
    EquipmentCertCategory,
    EquipmentDeploymentStatus,
    HookReasonCode,
    ServiceStatus,
    ServiceStatusReason,
)
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.models import (
    ConfigurationEvent,
    Contractor,
    EquipmentBlacklistEvent,
    EquipmentCertificate,
    EquipmentCertLine,
    EquipmentDefect,
    EquipmentDeployment,
    EquipmentItem,
    EquipmentStatusEvent,
    GasDetector,
    ObstacleClearance,
    Project,
    ProjectEngagement,
    Vehicle,
)
from app.schemas.access_common import VehicleRef
from app.schemas.equipment import (
    ConfigurationEventCreate,
    ConfigurationEventList,
    ConfigurationEventRead,
    EquipmentBlacklistRead,
    EquipmentBlacklistRequest,
    EquipmentCreate,
    EquipmentDeploymentSummary,
    EquipmentDocumentRead,
    EquipmentLineSummary,
    EquipmentListItem,
    EquipmentLookupRequest,
    EquipmentLookupResult,
    EquipmentPage,
    EquipmentRead,
    EquipmentStatusEventList,
    EquipmentUpdate,
    LiftBlacklistRequest,
    PressureFieldsRead,
    RetireRequest,
    ReturnToServiceRequest,
    TagOutRequest,
)
from app.schemas.equipment import EquipmentStatusEvent as EquipmentStatusEventRead
from app.services.access import common as acommon
from app.services.cert import alerts, events, validity
from app.services.cert import common as cc
from app.services.cert import reference as ref
from app.services.common import paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error

C = Capability
SS = ServiceStatus
SSR = ServiceStatusReason
Q = EquipmentCertCategory
R = HookReasonCode
UNUSABLE = (SS.out_of_service, SS.blacklisted, SS.retired)
REASON_TO_SSR: dict[HookReasonCode | None, ServiceStatusReason] = {
    R.CERT_EXPIRED: SSR.certificate_expired,
    R.CERT_SUSPENDED: SSR.certificate_suspended,
    R.CERT_REVOKED: SSR.certificate_revoked,
    R.CERT_UNVERIFIED: SSR.certificate_unverified,
    R.CONFIGURATION_CHANGED: SSR.configuration_changed,
    R.TPI_BLACKLISTED: SSR.tpi_blacklisted,
    R.CERT_MISSING: SSR.certificate_expired,
}


# ---- lookups / scope -----------------------------------------------------------------------------


def get_row(db: Session, equipment_id: uuid.UUID) -> EquipmentItem:
    item = db.get(EquipmentItem, equipment_id)
    if item is None:
        raise not_found("Equipment item")
    return item


def deployments(db: Session, item_id: uuid.UUID) -> list[EquipmentDeployment]:
    return list(
        db.scalars(
            select(EquipmentDeployment)
            .where(EquipmentDeployment.equipment_id == item_id)
            .order_by(EquipmentDeployment.created_at.desc())
        )
    )


def _dep_covered(p: Principal, d: EquipmentDeployment, cap: Capability) -> bool:
    return acommon.grant_covers(p.grant(d.project_id, cap), d.site_ids, d.engagement_id)


def _owner_contractors(db: Session, p: Principal, cap: Capability) -> set[uuid.UUID] | None:
    """Contractors whose items the caller may handle without a deployment (None = any)."""
    grants = p.project_grants(cap)
    if grants is None:
        return None
    out: set[uuid.UUID] = set()
    for g in grants.values():
        if g.engagement_ids is None and g.site_ids is None:
            return None
        cs = cc.grant_contractors(db, g)
        if cs is None:
            continue
        out |= cs
    return out


def can_see(db: Session, p: Principal, item: EquipmentItem) -> bool:
    if p.is_manager:
        return True
    deps = deployments(db, item.id)
    if any(_dep_covered(p, d, C.cert_register_view) for d in deps):
        return True
    owners = _owner_contractors(db, p, C.cert_register_view)
    if owners is None:
        return bool(p.project_grants(C.cert_register_view))
    return item.owner_contractor_id in owners


def can_edit(db: Session, p: Principal, item: EquipmentItem) -> bool:
    if p.is_manager:
        return True
    if any(_dep_covered(p, d, C.equipment_edit) for d in deployments(db, item.id)):
        return not _site_engineer_everywhere(p)
    owners = _owner_contractors(db, p, C.equipment_edit)
    if owners is None:
        return bool(p.project_grants(C.equipment_edit)) and not _site_engineer_everywhere(p)
    return item.owner_contractor_id in owners


def _site_engineer_everywhere(p: Principal) -> bool:
    """Row 106 'S (scaffolds, configuration events)' when site engineer is the only writer
    role."""
    if p.is_manager:
        return False
    for s in p.projects.values():
        if s.roles & {Role.hse_officer, Role.contractor_hse_rep}:
            return False
    return any(Role.site_engineer in s.roles for s in p.projects.values())


def get_visible(db: Session, p: Principal, equipment_id: uuid.UUID) -> EquipmentItem:
    item = get_row(db, equipment_id)
    if not can_see(db, p, item):
        raise not_found("Equipment item")
    return item


# ---- reads ---------------------------------------------------------------------------------------


def line_summary(
    db: Session, item: EquipmentItem, at: datetime | None = None
) -> tuple[EquipmentLineSummary | None, validity.ItemCert]:
    at = at or now()
    ic = validity.current_line(db, item.id, at)
    if ic.cert is None or ic.line is None:
        return None, ic
    from app.services.cert import tpis  # noqa: PLC0415

    t = tpis.get(db, ic.cert.tpi_id)
    d = acommon.local_day(at)
    return (
        EquipmentLineSummary(
            line=cc.line_ref(db, ic.line),
            inspected_on=ic.cert.inspected_on,
            result=ic.line.result.value,
            swl_t=ic.line.swl_t,
            limitations=cc.limitation_reads(ic.line.limitations),
            in_force=ic.ev.in_force,
            expiring=ic.ev.expiring,
            days_left=(ic.line.valid_until - d).days if ic.line.valid_until else None,
            tpi_accreditation_lapsed=ic.ev.in_force
            and tpis.accreditation_lapsed_note(db, t, ic.cert.inspected_on),
        ),
        ic,
    )


def open_defects(db: Session, item_id: uuid.UUID) -> list[EquipmentDefect]:
    return list(
        db.scalars(
            select(EquipmentDefect)
            .where(
                EquipmentDefect.equipment_id == item_id,
                EquipmentDefect.status.in_([DefectStatus.open, DefectStatus.rectified]),
            )
            .order_by(EquipmentDefect.raised_at)
        )
    )


def config_suspended(db: Session, item_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(func.count())
            .select_from(ConfigurationEvent)
            .where(
                ConfigurationEvent.equipment_id == item_id,
                ConfigurationEvent.cleared_at.is_(None),
                func.cardinality(ConfigurationEvent.suspended_line_ids) > 0,
            )
        )
        or 0
    ) > 0


def _blacklist_row(db: Session, item_id: uuid.UUID) -> EquipmentBlacklistEvent | None:
    return db.scalar(
        select(EquipmentBlacklistEvent)
        .where(EquipmentBlacklistEvent.equipment_id == item_id)
        .order_by(EquipmentBlacklistEvent.created_at.desc())
        .limit(1)
    )


def item_read(db: Session, p: Principal, item: EquipmentItem) -> EquipmentRead:
    refs = Refs(db)
    summary, ic = line_summary(db, item)
    deps = deployments(db, item.id)
    pcodes = {
        pr.id: pr.code
        for pr in db.scalars(select(Project).where(Project.id.in_({d.project_id for d in deps})))
    }
    bl = _blacklist_row(db, item.id)
    hse = cc.is_hse(p)
    v = db.get(Vehicle, item.vehicle_id) if item.vehicle_id else None
    e = ref.EQC.get(item.category)
    return EquipmentRead(
        id=item.id,
        equipment_no=item.equipment_no,
        category=item.category,
        subtype=item.subtype,
        manufacturer=item.manufacturer,
        model=item.model,
        serial_no=item.serial_no,
        serial_norm=item.serial_norm,
        year_of_manufacture=item.year_of_manufacture,
        owner_contractor_id=item.owner_contractor_id,
        owner_short_code=cc.owner_code(db, item.owner_contractor_id) or "",
        hired_from=item.hired_from,
        owner_fleet_no=item.owner_fleet_no,
        vehicle=VehicleRef(
            id=v.id, vehicle_no=v.vehicle_no, fleet_no=v.fleet_no, category=v.category
        )
        if v
        else None,
        rated_capacity_t=item.rated_capacity_t,
        max_radius_m=item.max_radius_m,
        max_height_m=item.max_height_m,
        persons_capacity=item.persons_capacity,
        pressure=PressureFieldsRead(**item.pressure) if item.pressure else None,
        lifting_duty=item.lifting_duty,
        safety_devices=list(item.safety_devices or []),
        documents=[EquipmentDocumentRead(**x) for x in item.documents or []],
        service_status=item.service_status,
        service_status_reason=item.service_status_reason,
        service_status_text=item.service_status_text
        if hse or item.service_status_reason != SSR.blacklisted
        else None,
        service_status_since=item.service_status_since,
        has_valid_certificate=ic.ev.in_force,
        configuration_suspended=config_suspended(db, item.id),
        current_line=summary,
        open_defects=[cc.defect_ref(x) for x in open_defects(db, item.id)],
        deployments=[
            EquipmentDeploymentSummary(
                id=d.id,
                deployment_no=d.deployment_no,
                project_id=d.project_id,
                project_code=pcodes.get(d.project_id, ""),
                tag=d.tag,
                status=d.status,
            )
            for d in deps
        ],
        blacklist=EquipmentBlacklistRead(
            reason_code=bl.reason_code if hse else None,
            reason_text=bl.reason_text if hse else None,
            from_date=bl.from_date,
            by=refs.user(bl.by_user_id) if bl.by_user_id else None,
            lifted_at=bl.lifted_at,
            lifted_by=refs.user(bl.lifted_by_user_id) if bl.lifted_by_user_id else None,
            lift_reason=bl.lift_reason if hse else None,
        )
        if bl
        else None,
        hook_code=e.hook_code if e else None,
        operator_code=e.operator_code if e else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def read(db: Session, p: Principal, equipment_id: uuid.UUID) -> EquipmentRead:
    if not p.has_any(C.cert_register_view):
        raise forbidden_error()
    return item_read(db, p, get_visible(db, p, equipment_id))


def list_items(
    db: Session,
    p: Principal,
    page: int,
    page_size: int,
    q: str | None = None,
    project_id: uuid.UUID | None = None,
    categories: list[EquipmentCertCategory] | None = None,
    statuses: list[ServiceStatus] | None = None,
    owner_contractor_id: uuid.UUID | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    expiring_days: int | None = None,
) -> EquipmentPage:
    if not p.has_any(C.cert_register_view):
        raise forbidden_error()
    stmt = select(EquipmentItem)
    if not p.is_manager:
        grants = p.project_grants(C.cert_register_view) or {}
        conds: list[Any] = []
        for pid, g in grants.items():
            dc = [EquipmentDeployment.project_id == pid]
            if g.engagement_ids is not None:
                dc.append(EquipmentDeployment.engagement_id.in_(list(g.engagement_ids)))
            if g.site_ids is not None:
                dc.append(EquipmentDeployment.site_ids.overlap(list(g.site_ids)))
            conds.append(EquipmentItem.id.in_(select(EquipmentDeployment.equipment_id).where(*dc)))
        owners = _owner_contractors(db, p, C.cert_register_view)
        if owners is None:
            conds.append(
                EquipmentItem.id.notin_(
                    select(EquipmentDeployment.equipment_id).where(
                        EquipmentDeployment.status.in_(cc.LIVE_DEPLOYMENT)
                    )
                )
            )
        elif owners:
            conds.append(EquipmentItem.owner_contractor_id.in_(owners))
        if not conds:
            return EquipmentPage(items=[], total=0, page=page, page_size=page_size)
        stmt = stmt.where(or_(*conds))
    if project_id is not None:
        stmt = stmt.where(
            EquipmentItem.id.in_(
                select(EquipmentDeployment.equipment_id).where(
                    EquipmentDeployment.project_id == project_id
                )
            )
        )
    if engagement_ids:
        stmt = stmt.where(
            EquipmentItem.id.in_(
                select(EquipmentDeployment.equipment_id).where(
                    EquipmentDeployment.engagement_id.in_(engagement_ids)
                )
            )
        )
    if q:
        pat = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                EquipmentItem.equipment_no.ilike(pat),
                EquipmentItem.serial_no.ilike(pat),
                EquipmentItem.model.ilike(pat),
                EquipmentItem.serial_norm.ilike(f"%{cc.serial_norm(q)}%"),
                EquipmentItem.id.in_(
                    select(EquipmentDeployment.equipment_id).where(
                        EquipmentDeployment.tag.ilike(pat)
                    )
                ),
            )
        )
    if categories:
        stmt = stmt.where(EquipmentItem.category.in_(categories))
    if statuses:
        stmt = stmt.where(EquipmentItem.service_status.in_(statuses))
    if owner_contractor_id:
        stmt = stmt.where(EquipmentItem.owner_contractor_id == owner_contractor_id)
    stmt = stmt.order_by(EquipmentItem.seq)
    at = now()
    d = today()
    if expiring_days is not None:
        rows_all = db.scalars(stmt).all()
        keep = []
        for it in rows_all:
            ic = validity.current_line(db, it.id, at)
            if (
                ic.ev.in_force
                and ic.ev.valid_until
                and ic.ev.valid_until <= d + timedelta(days=expiring_days)
            ):
                keep.append(it)
        total = len(keep)
        rows = keep[(page - 1) * page_size : page * page_size]
    else:
        rows_seq, total = paginate(db, stmt, page, page_size)
        rows = list(rows_seq)
    items = []
    for it in rows:
        ic = validity.current_line(db, it.id, at)
        dep = cc.live_deployment(db, it.id)
        items.append(
            EquipmentListItem(
                id=it.id,
                equipment_no=it.equipment_no,
                category=it.category,
                subtype=it.subtype,
                manufacturer=it.manufacturer,
                model=it.model,
                serial_no=it.serial_no,
                owner_short_code=cc.owner_code(db, it.owner_contractor_id) or "",
                service_status=it.service_status,
                service_status_reason=it.service_status_reason,
                current_tag=dep.tag if dep else None,
                current_project_code=cc.project_code(db, dep.project_id) if dep else None,
                valid_until=ic.ev.valid_until if ic.line else None,
                swl_t=ic.line.swl_t if ic.line else None,
            )
        )
    return EquipmentPage(items=items, total=total, page=page, page_size=page_size)


def status_events(db: Session, p: Principal, equipment_id: uuid.UUID) -> EquipmentStatusEventList:
    if not p.has_any(C.cert_register_view):
        raise forbidden_error()
    item = get_visible(db, p, equipment_id)
    refs = Refs(db)
    rows = db.scalars(
        select(EquipmentStatusEvent)
        .where(EquipmentStatusEvent.equipment_id == item.id)
        .order_by(EquipmentStatusEvent.occurred_at.desc())
    ).all()
    hse = cc.is_hse(p)
    return EquipmentStatusEventList(
        items=[
            EquipmentStatusEventRead(
                id=e.id,
                occurred_at=e.occurred_at,
                from_status=e.from_status,
                to_status=e.to_status,
                reason=e.reason,
                text=e.text if hse or e.reason != SSR.blacklisted else None,
                actor=refs.user(e.actor_user_id) if e.actor_user_id else None,
                ref=e.ref,
            )
            for e in rows
        ]
    )


# ---- EQ-1 duplicates -----------------------------------------------------------------------------


def _duplicate(db: Session, p: Principal, manufacturer: str, serial: str) -> EquipmentItem | None:
    mn, sn = cc.manufacturer_norm(manufacturer), cc.serial_norm(serial)
    black = db.scalar(
        select(EquipmentItem).where(
            EquipmentItem.serial_norm == sn, EquipmentItem.service_status == SS.blacklisted
        )
    )
    if black is not None:
        raise ApiError(
            409,
            ErrorCode.EQUIPMENT_BLACKLISTED,
            "This serial belongs to a blacklisted item and cannot be registered (EQ-1, BL-3).",
            "هذا الرقم التسلسلي لمعدة محظورة ولا يمكن تسجيله.",
        )
    return db.scalar(
        select(EquipmentItem).where(
            EquipmentItem.manufacturer_norm == mn, EquipmentItem.serial_norm == sn
        )
    )


def _exists_error(db: Session, p: Principal, item: EquipmentItem) -> ApiError:
    if can_see(db, p, item):
        return ApiError(
            409,
            ErrorCode.EQUIPMENT_EXISTS,
            f"This item is already registered as {item.equipment_no}.",
            f"هذه المعدة مسجلة مسبقاً برقم {item.equipment_no}.",
            meta={"equipment_no": item.equipment_no, "equipment_id": str(item.id)},
        )
    return ApiError(
        409,
        ErrorCode.EQUIPMENT_EXISTS_OUT_OF_SCOPE,
        "This item is already registered by another organisation.",
        "هذه المعدة مسجلة مسبقاً لدى جهة أخرى.",
    )


def lookup(db: Session, p: Principal, body: EquipmentLookupRequest) -> EquipmentLookupResult:
    if not p.has_any(C.equipment_edit) and not p.has_any(C.cert_register_view):
        raise forbidden_error()
    sn = cc.serial_norm(body.serial_no)
    black = db.scalar(
        select(EquipmentItem).where(
            EquipmentItem.serial_norm == sn, EquipmentItem.service_status == SS.blacklisted
        )
    )
    item = db.scalar(
        select(EquipmentItem).where(
            EquipmentItem.manufacturer_norm == cc.manufacturer_norm(body.manufacturer),
            EquipmentItem.serial_norm == sn,
        )
    )
    found = item or black
    return EquipmentLookupResult(
        exists=item is not None,
        blacklisted=black is not None,
        equipment=cc.equipment_ref(db, found) if found and can_see(db, p, found) else None,
    )


# ---- create / update -----------------------------------------------------------------------------


def _validate(db: Session, item: EquipmentItem, data: dict[str, Any]) -> None:
    if item.category == Q.scaffold:
        raise validation_error("category", "Scaffolds are registered in the scaffold register.")
    e = ref.EQC[item.category]
    if e.subtype_required and item.subtype is None:
        raise validation_error("subtype", "A subtype is required for this category.")
    if item.subtype is not None and e.subtypes and item.subtype not in e.subtypes:
        raise validation_error("subtype", "Subtype not allowed for this category.")
    if item.subtype is not None and not e.subtypes:
        raise validation_error("subtype", "This category has no subtypes.")
    words = f"{item.manufacturer} {item.model}".lower()
    detector = db.scalar(
        select(GasDetector.id).where(func.upper(GasDetector.serial) == item.serial_no.upper())
    )
    if detector is not None or "gas detector" in words or "gas monitor" in words:
        raise ApiError(
            422,
            ErrorCode.USE_DETECTOR_REGISTER,
            "Gas detectors stay in the PTW detector register (EQ-3).",
            "تبقى أجهزة كشف الغاز في سجل أجهزة تصاريح العمل.",
        )
    pr = item.pressure
    if pr is not None and float(pr["relief_set_bar"]) > float(pr["mawp_bar"]):
        raise ApiError(
            422,
            ErrorCode.RELIEF_ABOVE_MAWP,
            "The relief valve set pressure must not exceed MAWP.",
            "ضغط صمام الأمان يجب ألا يتجاوز أقصى ضغط تشغيل مسموح.",
        )
    if pr is not None and item.category != Q.pressure_vessel:
        raise validation_error("pressure", "Pressure fields are for pressure vessels only.")
    if item.lifting_duty and item.category not in ref.LIFTING_DUTY_CATEGORIES:
        raise validation_error("lifting_duty", "Only excavators, loaders and telehandlers.")
    owner = db.get(Contractor, item.owner_contractor_id)
    if owner is None:
        raise validation_error("owner_contractor_id", "Unknown contractor.")
    if item.vehicle_id is not None:
        v = db.get(Vehicle, item.vehicle_id)
        if v is None:
            raise validation_error("vehicle_id", "Unknown vehicle.")
        if not ref.vc_allows(v.category, item.category):
            raise ApiError(
                422,
                ErrorCode.CATEGORY_MISMATCH,
                "The equipment category does not pair with the vehicle category (EQ-2).",
                "فئة المعدة لا تتوافق مع فئة المركبة.",
            )
        other = db.scalar(
            select(EquipmentItem).where(
                EquipmentItem.vehicle_id == v.id, EquipmentItem.id != item.id
            )
        )
        if other is not None:
            raise ApiError(
                422,
                ErrorCode.VEHICLE_ALREADY_LINKED,
                "This vehicle is already linked to another equipment item (EQ-2).",
                "هذه المركبة مرتبطة بمعدة أخرى.",
            )


def _require_owner_scope(db: Session, p: Principal, owner_id: uuid.UUID) -> None:
    p.require_any(C.equipment_edit)
    if _site_engineer_everywhere(p):
        raise forbidden_error("Site engineers record scaffolds and configuration events only.")
    owners = _owner_contractors(db, p, C.equipment_edit)
    if owners is not None and owner_id not in owners:
        raise cc.outside_scope()


def _norms(item: EquipmentItem) -> None:
    item.manufacturer_norm = cc.manufacturer_norm(item.manufacturer)
    item.serial_norm = cc.serial_norm(item.serial_no)


def _dump(body: Any, exclude: set[str] | None = None) -> dict[str, Any]:
    data: dict[str, Any] = body.model_dump(exclude=exclude or set())
    if "pressure" in data and data["pressure"] is not None:
        data["pressure"] = {k: str(v) for k, v in data["pressure"].items()}
    if "documents" in data and data["documents"] is not None:
        data["documents"] = [
            {
                **x,
                "doc_type": getattr(x["doc_type"], "value", x["doc_type"]),
                "attachment_id": str(x["attachment_id"]) if x.get("attachment_id") else None,
            }
            for x in data["documents"]
        ]
    if "safety_devices" in data and data["safety_devices"] is not None:
        data["safety_devices"] = [getattr(x, "value", x) for x in data["safety_devices"]]
    return data


def next_no(db: Session) -> tuple[int, str]:
    seq = (db.scalar(select(func.max(EquipmentItem.seq))) or 0) + 1
    return seq, f"EQP-{seq:06d}"


def create(db: Session, p: Principal, body: EquipmentCreate) -> EquipmentRead:
    _require_owner_scope(db, p, body.owner_contractor_id)
    existing = _duplicate(db, p, body.manufacturer, body.serial_no)
    if existing is not None:
        raise _exists_error(db, p, existing)
    seq, no = next_no(db)
    item = EquipmentItem(
        id=uuid.uuid4(),
        seq=seq,
        equipment_no=no,
        service_status=SS.awaiting_certificate,
        service_status_reason=SSR.awaiting_certificate,
        service_status_since=now(),
        **_dump(body),
    )
    _norms(item)
    _validate(db, item, {})
    cc.stamp(item, p, create=True)
    db.add(item)
    db.flush()
    _event(db, item, None, SS.awaiting_certificate, SSR.awaiting_certificate, None, p, None)
    cc.record(db, p, AuditAction.create, EntityType.equipment_item, item, None)
    return item_read(db, p, item)


def has_submitted_cert(db: Session, item_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(func.count())
            .select_from(EquipmentCertLine)
            .join(EquipmentCertificate, EquipmentCertificate.id == EquipmentCertLine.certificate_id)
            .where(
                EquipmentCertLine.equipment_id == item_id,
                EquipmentCertificate.status != CertificateStatus.draft,
            )
        )
        or 0
    ) > 0


def update(
    db: Session, p: Principal, equipment_id: uuid.UUID, body: EquipmentUpdate
) -> EquipmentRead:
    item = get_visible(db, p, equipment_id)
    p.require_any(C.equipment_edit)
    if not can_edit(db, p, item):
        raise cc.outside_scope()
    before = cc.snap(item)
    ch = _dump_changes(body)
    if ("serial_no" in ch or "manufacturer" in ch) and has_submitted_cert(db, item.id):
        raise validation_error(
            "serial_no", "Serial and manufacturer are locked once a certificate is submitted."
        )
    if "owner_contractor_id" in ch:
        _require_owner_scope(db, p, ch["owner_contractor_id"])
    for k, v in ch.items():
        setattr(item, k, v)
    _norms(item)
    if "serial_no" in ch or "manufacturer" in ch:
        dup = db.scalar(
            select(EquipmentItem).where(
                EquipmentItem.manufacturer_norm == item.manufacturer_norm,
                EquipmentItem.serial_norm == item.serial_norm,
                EquipmentItem.id != item.id,
            )
        )
        if dup is not None:
            raise _exists_error(db, p, dup)
    _validate(db, item, ch)
    cc.stamp(item, p)
    db.flush()
    cc.record(db, p, AuditAction.update, EntityType.equipment_item, item, None, before)
    if "vehicle_id" in ch or "rated_capacity_t" in ch or "lifting_duty" in ch:
        events.publish(db, "equipment.status_changed", item_ids=[item.id])
    return item_read(db, p, item)


def _dump_changes(body: EquipmentUpdate) -> dict[str, Any]:
    ch = body.changes()
    if "pressure" in ch and ch["pressure"] is not None:
        ch["pressure"] = {k: str(v) for k, v in dict(ch["pressure"]).items()}
    if "documents" in ch:
        ch["documents"] = [
            {
                "doc_type": getattr(x["doc_type"], "value", x["doc_type"]),
                "ref": x["ref"],
                "attachment_id": str(x["attachment_id"]) if x.get("attachment_id") else None,
            }
            for x in (ch["documents"] or [])
        ]
    if "safety_devices" in ch:
        ch["safety_devices"] = [getattr(x, "value", x) for x in ch["safety_devices"] or []]
    return ch


# ---- status engine (§4.2) ------------------------------------------------------------------------


def _event(
    db: Session,
    item: EquipmentItem,
    src: ServiceStatus | None,
    dst: ServiceStatus,
    reason: ServiceStatusReason | None,
    text: str | None,
    p: Principal | None,
    ref_: str | None,
    at: datetime | None = None,
) -> None:
    db.add(
        EquipmentStatusEvent(
            id=uuid.uuid4(),
            equipment_id=item.id,
            occurred_at=at or now(),
            from_status=src,
            to_status=dst,
            reason=reason,
            text=text,
            actor_user_id=p.user.id if p is not None else None,
            ref=ref_,
            seed_fake=item.seed_fake,
        )
    )


def set_status(
    db: Session,
    item: EquipmentItem,
    dst: ServiceStatus,
    reason: ServiceStatusReason | None,
    p: Principal | None = None,
    text: str | None = None,
    ref_: str | None = None,
    at: datetime | None = None,
) -> bool:
    if item.service_status == dst and item.service_status_reason == reason:
        return False
    src = item.service_status
    before = cc.snap(item)
    item.service_status = dst
    item.service_status_reason = reason
    item.service_status_text = text
    item.service_status_since = at or now()
    if p is not None:
        item.updated_by_user_id = p.user.id
    _event(db, item, src, dst, reason, text, p, ref_, at)
    db.flush()
    cc.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.equipment_item,
        item,
        None,
        before,
        {
            "from": src.value,
            "to": dst.value,
            "reason": reason.value if reason else None,
            "ref": ref_,
        },
    )
    events.publish(db, "equipment.status_changed", item_ids=[item.id])
    return True


def recompute(
    db: Session, item: EquipmentItem, at: datetime | None = None, p: Principal | None = None
) -> bool:
    """System transitions of §4.2 (Awaiting/Quarantined ↔ In Service). Out of Service,
    Blacklisted and Retired change only by explicit actions."""
    if item.service_status in UNUSABLE:
        return False
    at = at or now()
    ic = validity.current_line(db, item.id, at)
    if ic.ev.in_force:
        return set_status(
            db, item, SS.in_service, None, p, ref_=ic.cert.cert_no if ic.cert else None, at=at
        )
    if item.service_status == SS.awaiting_certificate and (
        ic.cert is None or ic.cert.status == CertificateStatus.submitted
    ):
        return False
    reason = REASON_TO_SSR.get(ic.ev.reason, SSR.certificate_expired)
    if ic.cert is None:
        reason = SSR.awaiting_certificate
    return set_status(
        db, item, SS.quarantined, reason, p, ref_=ic.cert.cert_no if ic.cert else None, at=at
    )


def stop_use_recipients(db: Session, item: EquipmentItem) -> dict[uuid.UUID, set[uuid.UUID]]:
    """Per project: owner's Contractor HSE Rep + HSE Officers (+ managers for cranes, hoists,
    man-baskets, MEWPs) + receivers / issuers of live permits naming the item."""
    from app.models import Permit  # noqa: PLC0415

    out: dict[uuid.UUID, set[uuid.UUID]] = {}
    for d in deployments(db, item.id):
        if d.status not in cc.LIVE_DEPLOYMENT:
            continue
        users = alerts.reps(db, d.project_id, d.engagement_id) | alerts.officers(db, d.project_id)
        if item.category in ref.CRANES | ref.HOISTS | {Q.man_basket, Q.mewp}:
            users |= alerts.managers(db)
        for pid in events.permits_for_items(db, {item.id}):
            pm = db.get(Permit, pid)
            if pm is not None and pm.project_id == d.project_id:
                users |= {u for u in (pm.receiver_user_id, pm.issuer_user_id) if u}
        out[d.project_id] = users
    return out


def tag_out(
    db: Session, p: Principal, equipment_id: uuid.UUID, body: TagOutRequest
) -> EquipmentRead:
    """DF-8: never blocked by a rule (only by permissions)."""
    item = get_row(db, equipment_id)
    dep = cc.deployment_on(db, item.id, body.project_id) or cc.latest_deployment_on(
        db, item.id, body.project_id
    )
    cc.require(
        p,
        body.project_id,
        C.defect_raise,
        dep.engagement_id if dep else None,
        dep.site_ids if dep else None,
    )
    if not body.physical_tag_applied:
        raise ApiError(
            422,
            ErrorCode.PHYSICAL_TAG_REQUIRED,
            "Apply the physical 'Do not use' tag first.",
            "ضع بطاقة «ممنوع الاستخدام» على المعدة أولاً.",
        )
    item.tagged_out_by_user_id = p.user.id
    if item.service_status not in (SS.blacklisted, SS.retired):
        set_status(db, item, SS.out_of_service, SSR.manual_tag_out, p, body.reason)
    else:
        cc.record(
            db,
            p,
            AuditAction.update,
            EntityType.equipment_item,
            item,
            body.project_id,
            None,
            {"tag_out": body.reason},
        )
    tag = dep.tag if dep else item.equipment_no
    for pid, users in stop_use_recipients(db, item).items():
        alerts.send(
            db,
            users,
            NotificationKind.equipment_stop_use,
            f"{tag} tagged out — do not use",
            f"{tag} موسومة بعدم الاستخدام — لا تستخدم",
            EntityType.equipment_item,
            item.id,
            pid,
            email=True,
        )
    return item_read(db, p, item)


def _closure_needed(db: Session, item: EquipmentItem) -> list[EquipmentDefect]:
    d = today()
    out = []
    for x in open_defects(db, item.id):
        if x.category == DefectCategory.A or (
            x.category == DefectCategory.B and x.due_date is not None and x.due_date < d
        ):
            out.append(x)
    return out


def return_to_service(
    db: Session, p: Principal, equipment_id: uuid.UUID, body: ReturnToServiceRequest
) -> EquipmentRead:
    item = get_visible(db, p, equipment_id)
    dep = cc.live_deployment(db, item.id)
    if dep is None:
        p.require_any(C.defect_close)
    else:
        cc.require(p, dep.project_id, C.defect_close, dep.engagement_id, dep.site_ids)
    if item.service_status != SS.out_of_service:
        from app.services.common import invalid_transition  # noqa: PLC0415

        raise invalid_transition("Equipment", item.service_status, "in_service")
    if _sod_employer(db, p, item.owner_contractor_id):
        raise cc.sod()
    rectifiers = {
        x.rectified_by_user_id
        for x in db.scalars(select(EquipmentDefect).where(EquipmentDefect.equipment_id == item.id))
        if x.rectified_by_user_id
    }
    if p.user.id in rectifiers:
        raise cc.sod()
    pending = _closure_needed(db, item)
    if pending:
        raise ApiError(
            422,
            ErrorCode.DEFECTS_OPEN,
            "Close every category A and overdue category B defect first (DF-6).",
            "أغلق جميع عيوب الفئة A وعيوب الفئة B المتأخرة أولاً.",
            meta={"defects": [x.defect_no for x in pending]},
        )
    bl = _blacklist_row(db, item.id)
    ic = validity.current_line(db, item.id, now())
    if (
        bl is not None
        and bl.lifted_at is not None
        and item.service_status_reason == SSR.blacklisted
        and (
            not ic.ev.in_force
            or ic.cert is None
            or ic.cert.inspected_on < acommon.local_day(bl.lifted_at)
        )
    ):
        raise ApiError(
            422,
            ErrorCode.TPI_REINSPECTION_REQUIRED,
            "A new TPI certificate is needed after a lifted blacklist.",
            "يلزم شهادة جديدة من جهة الفحص بعد رفع الحظر.",
        )
    if item.service_status_reason == SSR.failed_inspection and not ic.ev.in_force:
        raise ApiError(
            422,
            ErrorCode.TPI_REINSPECTION_REQUIRED,
            "A passing TPI certificate is needed after a failed inspection.",
            "يلزم شهادة فحص ناجحة من جهة الفحص بعد فشل الفحص.",
        )
    target = SS.in_service if ic.ev.in_force else SS.quarantined
    reason = None if ic.ev.in_force else REASON_TO_SSR.get(ic.ev.reason, SSR.certificate_expired)
    item.tagged_out_by_user_id = None
    set_status(db, item, target, reason, p, body.note)
    return item_read(db, p, item)


def _sod_employer(db: Session, p: Principal, contractor_id: uuid.UUID | None) -> bool:
    """VF-2 / DF-6: the user is employed by (a user of) the given contractor."""
    if contractor_id is None or p.is_manager:
        return False
    return p.user.employer_contractor_id == contractor_id


def end_deployments(
    db: Session, item: EquipmentItem, reason: str, p: Principal | None = None
) -> list[EquipmentDeployment]:
    out = []
    d = today()
    for dep in deployments(db, item.id):
        if dep.status in (EquipmentDeploymentStatus.planned,):
            dep.status = EquipmentDeploymentStatus.cancelled
        elif dep.status in (EquipmentDeploymentStatus.approved, EquipmentDeploymentStatus.on_site):
            dep.status = EquipmentDeploymentStatus.demobilised
            dep.demobilised_on = d
        else:
            continue
        dep.status_reason = reason
        acommon.end_qr(db, dep.id, QrTokenStatus.revoked)
        out.append(dep)
        cc.record(
            db,
            p,
            AuditAction.status_change,
            EntityType.equipment_deployment,
            dep,
            dep.project_id,
            None,
            {"to": dep.status.value, "reason": reason},
            after={"status": dep.status.value},
        )
    return out


def retire(
    db: Session, p: Principal, equipment_id: uuid.UUID, body: RetireRequest
) -> EquipmentRead:
    item = get_visible(db, p, equipment_id)
    dep = cc.live_deployment(db, item.id)
    if dep is None:
        p.require_any(C.defect_close)
    else:
        cc.require(p, dep.project_id, C.defect_close, dep.engagement_id, dep.site_ids)
    if item.service_status == SS.retired:
        from app.services.common import invalid_transition  # noqa: PLC0415

        raise invalid_transition("Equipment", "retired", "retired")
    end_deployments(db, item, f"retired: {body.reason.value}", p)
    set_status(db, item, SS.retired, SSR(body.reason.value), p, body.reason_text)
    return item_read(db, p, item)


def retire_destroyed(
    db: Session, item: EquipmentItem, p: Principal | None, ref_: str, at: datetime | None = None
) -> None:
    """DF-7 closure 'destroyed / returned to manufacturer'."""
    end_deployments(db, item, "retired_destroyed", p)
    set_status(db, item, SS.retired, SSR.retired_destroyed, p, None, ref_, at)


def blacklist(
    db: Session, p: Principal, equipment_id: uuid.UUID, body: EquipmentBlacklistRequest
) -> EquipmentRead:
    p.require_any(C.cert_blacklist)
    item = get_row(db, equipment_id)
    if item.service_status in (SS.blacklisted, SS.retired):
        from app.services.common import invalid_transition  # noqa: PLC0415

        raise invalid_transition("Equipment", item.service_status, "blacklisted")
    ev = EquipmentBlacklistEvent(
        id=uuid.uuid4(),
        equipment_id=item.id,
        reason_code=body.reason_code,
        reason_text=body.reason_text,
        from_date=today(),
        by_user_id=p.user.id,
    )
    cc.stamp(ev, p, create=True)
    db.add(ev)
    affected = [d for d in deployments(db, item.id) if d.status in cc.LIVE_DEPLOYMENT]
    end_deployments(db, item, "equipment_blacklisted", p)
    set_status(db, item, SS.blacklisted, SSR.blacklisted, p, body.reason_text)
    for d in affected:
        alerts.send(
            db,
            alerts.officers(db, d.project_id),
            NotificationKind.blacklist_changed,
            f"Equipment {d.tag} blacklisted",
            f"المعدة {d.tag} محظورة",
            EntityType.equipment_item,
            item.id,
            d.project_id,
            email=True,
        )
        alerts.send(
            db,
            alerts.reps(db, d.project_id, d.engagement_id),
            NotificationKind.blacklist_changed,
            f"Equipment {d.tag}: not accepted on this organisation's projects",
            f"المعدة {d.tag}: غير مقبولة في مشاريع هذه الجهة",
            EntityType.equipment_item,
            item.id,
            d.project_id,
            email=True,
        )
    return item_read(db, p, item)


def lift_blacklist(
    db: Session, p: Principal, equipment_id: uuid.UUID, body: LiftBlacklistRequest
) -> EquipmentRead:
    p.require_any(C.cert_blacklist)
    item = get_row(db, equipment_id)
    if item.service_status != SS.blacklisted:
        from app.services.common import invalid_transition  # noqa: PLC0415

        raise invalid_transition("Equipment", item.service_status, "out_of_service")
    ev = _blacklist_row(db, item.id)
    if ev is not None:
        before = cc.snap(ev)
        ev.lifted_at = now()
        ev.lifted_by_user_id = p.user.id
        ev.lift_reason = body.reason
        cc.stamp(ev, p)
        db.flush()
        cc.record(db, p, AuditAction.update, EntityType.equipment_item, ev, None, before)
    set_status(db, item, SS.out_of_service, SSR.blacklisted, p, "Blacklist lifted: " + body.reason)
    return item_read(db, p, item)


# ---- configuration events (CF-1…CF-4) ------------------------------------------------------------


CF_LIMITED_TYPES = frozenset(
    {
        ConfigurationEventType.major_repair,
        ConfigurationEventType.storm_exceedance,
        ConfigurationEventType.boom_configuration_change,
    }
)


def config_read(db: Session, ev: ConfigurationEvent) -> ConfigurationEventRead:
    refs = Refs(db)
    lines = [db.get(EquipmentCertLine, lid) for lid in ev.suspended_line_ids or []]
    cleared = db.get(EquipmentCertLine, ev.cleared_by_line_id) if ev.cleared_by_line_id else None
    by = refs.user(ev.created_by_user_id) if ev.created_by_user_id else None
    from app.schemas.hse_common import UserRef  # noqa: PLC0415

    return ConfigurationEventRead(
        id=ev.id,
        equipment_id=ev.equipment_id,
        project_id=ev.project_id,
        event_type=ev.event_type,
        occurred_at=ev.occurred_at,
        new_configuration=ev.new_configuration,
        new_height_m=ev.new_height_m,
        recorded_by=by
        or UserRef(id=uuid.UUID(int=0), full_name_en="System", full_name_ar="النظام"),
        recorded_at=ev.created_at,
        late_record=ev.late_record,
        suspended_lines=[cc.line_ref(db, x) for x in lines if x is not None],
        cleared_by=cc.line_ref(db, cleared) if cleared else None,
        cleared_at=ev.cleared_at,
        obstacle_clearances_rechecked=list(ev.obstacle_refs or []),
    )


def list_config(db: Session, p: Principal, equipment_id: uuid.UUID) -> ConfigurationEventList:
    if not p.has_any(C.cert_register_view):
        raise forbidden_error()
    item = get_visible(db, p, equipment_id)
    rows = db.scalars(
        select(ConfigurationEvent)
        .where(ConfigurationEvent.equipment_id == item.id)
        .order_by(ConfigurationEvent.occurred_at.desc())
    ).all()
    return ConfigurationEventList(items=[config_read(db, x) for x in rows])


def open_config_event(db: Session, item_id: uuid.UUID) -> ConfigurationEvent | None:
    return db.scalar(
        select(ConfigurationEvent)
        .where(ConfigurationEvent.equipment_id == item_id, ConfigurationEvent.cleared_at.is_(None))
        .order_by(ConfigurationEvent.occurred_at.desc())
        .limit(1)
    )


def create_config(
    db: Session, p: Principal, equipment_id: uuid.UUID, body: ConfigurationEventCreate
) -> ConfigurationEventRead:
    item = get_row(db, equipment_id)
    dep = cc.deployment_on(db, item.id, body.project_id)
    if dep is None:
        raise ApiError(
            422,
            ErrorCode.EQUIPMENT_NOT_DEPLOYED,
            "The item is not deployed on this project.",
            "المعدة غير معيّنة في هذا المشروع.",
        )
    cc.require(p, body.project_id, C.equipment_edit, dep.engagement_id, dep.site_ids)
    if item.category not in ref.CF1_ANY and not (
        item.category in ref.CF1_LIMITED and body.event_type in CF_LIMITED_TYPES
    ):
        raise ApiError(
            422,
            ErrorCode.CONFIGURATION_EVENT_NOT_ALLOWED,
            "This event type is not a configuration change for this category (CF-1).",
            "نوع الحدث ليس تغييراً في التهيئة لهذه الفئة.",
        )
    at = now()
    occurred = body.occurred_at
    if occurred > at + timedelta(minutes=5) or occurred < at - timedelta(hours=24):
        raise ApiError(
            422,
            ErrorCode.BACKDATED_EVENT,
            "The event time must be within the last 24 hours (CF-2).",
            "يجب أن يكون وقت الحدث خلال آخر 24 ساعة.",
        )
    late = at - occurred > timedelta(hours=1)
    ev = ConfigurationEvent(
        id=uuid.uuid4(),
        equipment_id=item.id,
        project_id=body.project_id,
        event_type=body.event_type,
        occurred_at=occurred,
        new_configuration=body.new_configuration,
        new_height_m=body.new_height_m,
        late_record=late,
        suspended_line_ids=[],
        obstacle_refs=[],
    )
    cc.stamp(ev, p, create=True)
    db.add(ev)
    apply_config_event(db, item, ev, p)
    if body.new_height_m is not None:
        _cf4(db, item, ev, p)
    db.flush()
    cc.record(db, p, AuditAction.create, EntityType.configuration_event, ev, body.project_id)
    users = (
        alerts.officers(db, dep.project_id)
        | alerts.managers(db)
        | alerts.reps(db, dep.project_id, dep.engagement_id)
    )
    from app.models import Permit  # noqa: PLC0415

    for pid in events.permits_for_items(db, {item.id}):
        pm = db.get(Permit, pid)
        if pm is not None and pm.receiver_user_id:
            users.add(pm.receiver_user_id)
    late_en = " (recorded late)" if late else ""
    late_ar = " (سُجّل متأخراً)" if late else ""
    alerts.send(
        db,
        users,
        NotificationKind.configuration_event,
        f"{dep.tag}: configuration change — re-examination required{late_en}",
        f"{dep.tag}: تغيير في التهيئة — يلزم إعادة الفحص{late_ar}",
        EntityType.configuration_event,
        ev.id,
        dep.project_id,
        email=True,
    )
    return config_read(db, ev)


def apply_config_event(
    db: Session, item: EquipmentItem, ev: ConfigurationEvent, p: Principal | None
) -> None:
    """CF-1: suspend every in-force line at occurred_at; quarantine the item."""
    suspended: list[uuid.UUID] = []
    certs: set[uuid.UUID] = set()
    for c, line in validity.item_lines(db, item.id):
        if line.suspended_for_configuration:
            continue
        ev_line = validity.eval_line(db, c, line, ev.occurred_at)
        if not ev_line.in_force and not (
            c.status == CertificateStatus.accepted and ev_line.reason == R.CERT_UNVERIFIED
        ):
            continue
        line.suspended_for_configuration = True
        line.suspended_at = ev.occurred_at
        suspended.append(line.id)
        certs.add(c.id)
    for cid in certs:
        cert = db.get(EquipmentCertificate, cid)
        if cert is None:
            continue
        lines = db.scalars(
            select(EquipmentCertLine).where(EquipmentCertLine.certificate_id == cid)
        ).all()
        if (
            all(x.suspended_for_configuration for x in lines)
            and cert.status == CertificateStatus.accepted
        ):
            before = cc.snap(cert)
            cert.status = CertificateStatus.suspended
            cert.status_reason = CertStatusReason.configuration_changed
            cc.record(
                db,
                p,
                AuditAction.status_change,
                EntityType.equipment_certificate,
                cert,
                cert.project_id,
                before,
                {"cascade": "configuration_event"},
            )
    ev.suspended_line_ids = suspended
    db.flush()
    if item.service_status not in UNUSABLE:
        set_status(
            db,
            item,
            SS.quarantined,
            SSR.configuration_changed,
            p,
            ev.new_configuration,
            ev.event_type.value,
            ev.occurred_at,
        )
    events.publish(db, "cert.status_changed", item_ids=[item.id])


def _cf4(db: Session, item: EquipmentItem, ev: ConfigurationEvent, p: Principal | None) -> None:
    """CF-4: new height → item max_height_m (and the linked vehicle's working height) and the
    linked obstacle clearances re-checked (approved height < new height listed)."""
    item.max_height_m = ev.new_height_m
    if item.vehicle_id:
        v = db.get(Vehicle, item.vehicle_id)
        if v is not None and ev.new_height_m is not None:
            v.max_working_height_m_agl = ev.new_height_m
    refs = []
    for o in db.scalars(
        select(ObstacleClearance).where(ObstacleClearance.equipment_item_id == item.id)
    ):
        refs.append(o.obs_no)
        if (
            ev.new_height_m is not None
            and o.approved_max_height_m_agl is not None
            and o.approved_max_height_m_agl < ev.new_height_m
        ):
            refs[-1] = f"{o.obs_no} (HEIGHT_CLEARANCE_REQUIRED)"
    ev.obstacle_refs = refs


def clear_config_events(
    db: Session, item: EquipmentItem, line: EquipmentCertLine, c: EquipmentCertificate
) -> None:
    """A line of type after_configuration_change / after_repair inspected on/after the event
    came into force: the event is cleared (CF-1)."""
    if c.inspection_type not in (
        CertInspectionType.after_configuration_change,
        CertInspectionType.after_repair,
    ):
        return
    for ev in db.scalars(
        select(ConfigurationEvent).where(
            ConfigurationEvent.equipment_id == item.id, ConfigurationEvent.cleared_at.is_(None)
        )
    ):
        if c.inspected_on >= acommon.local_day(ev.occurred_at):
            ev.cleared_by_line_id = line.id
            ev.cleared_at = c.in_force_from or now()


def engagement_for(
    db: Session, item: EquipmentItem, project_id: uuid.UUID
) -> ProjectEngagement | None:
    dep = cc.latest_deployment_on(db, item.id, project_id)
    return db.get(ProjectEngagement, dep.engagement_id) if dep else None
