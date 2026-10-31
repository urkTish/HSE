"""M&TE register and usage (spec 8-quality §A.8.4, Q-SHR-04, AC-Q0-24, AC-Q0-49).

Q0 owns the table, its CRUD and the usage recording so Q2 and Q3 can create and cite instruments
in parallel. Q2 owns calibration records, out-of-tolerance reviews and the status recomputation
(Q-CAL-02); until Q2 is installed `cal_status` stays `unknown`, and `unknown` always warns."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode
from app.core.quality.common import (
    MTE_WARN_STATUSES,
    QCalStatus,
    QMteCheckKind,
    QMteOwnerKind,
    QMteStatus,
    QMteType,
    QMteUseVerdict,
    QRecordType,
)
from app.models import Project, Site, Zone
from app.models.quality import QMteItem, QMteUsage
from app.schemas.hse_common import ApiWarning
from app.services import audit
from app.services.common import paginate
from app.services.permissions import Principal, deny, forbidden_error
from app.services.quality import common as qc
from app.services.quality import numbering
from app.services.quality import settings as qs

C = Capability
EDIT = (
    "mte_type",
    "description",
    "manufacturer",
    "model",
    "serial_no",
    "range_text",
    "resolution",
    "tolerance_value",
    "tolerance_unit",
    "owner_kind",
    "owner_engagement_id",
    "owner_supplier_id",
    "site_id",
    "zone_id",
    "custodian_user_id",
    "check_kind",
    "interval_months",
    "equipment_item_id",
)


def read(db: Session, m: QMteItem) -> dict[str, Any]:
    site = db.get(Site, m.site_id) if m.site_id else None
    zone = db.get(Zone, m.zone_id) if m.zone_id else None
    return {
        "id": m.id,
        "project_id": m.project_id,
        "mte_no": m.mte_no,
        "mte_type": m.mte_type,
        "description": m.description,
        "manufacturer": m.manufacturer,
        "model": m.model,
        "serial_no": m.serial_no,
        "range_text": m.range_text,
        "resolution": m.resolution,
        "tolerance_value": str(m.tolerance_value) if m.tolerance_value is not None else None,
        "tolerance_unit": m.tolerance_unit,
        "owner_kind": m.owner_kind,
        "owner_engagement_id": m.owner_engagement_id,
        "owner_supplier_id": m.owner_supplier_id,
        "site_id": m.site_id,
        "site_code": site.code if site else None,
        "zone_id": m.zone_id,
        "zone_code": zone.code if zone else None,
        "custodian_user_id": m.custodian_user_id,
        "check_kind": m.check_kind,
        "interval_months": m.interval_months,
        "cal_status": m.cal_status,
        "cal_status_reason": m.cal_status_reason,
        "cal_due_on": m.cal_due_on,
        "last_calibration_id": m.last_calibration_id,
        "equipment_item_id": m.equipment_item_id,
        "status": m.status,
        "label_printed_at": m.label_printed_at,
    }


def _view(p: Principal, project_id: uuid.UUID) -> None:
    if p.grant(project_id, C.quality_view) is None and p.grant(project_id, C.mte_manage) is None:
        raise forbidden_error()


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    *,
    cal_statuses: list[QCalStatus] | None = None,
    mte_type: QMteType | None = None,
    status: QMteStatus | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    _view(p, project.id)
    M = QMteItem  # noqa: N806
    stmt = select(M).where(M.project_id == project.id)
    if cal_statuses:
        stmt = stmt.where(M.cal_status.in_(cal_statuses))
    if mte_type:
        stmt = stmt.where(M.mte_type == mte_type)
    if status:
        stmt = stmt.where(M.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            M.mte_no.ilike(like) | M.description.ilike(like) | M.serial_no.ilike(like)
        )
    items, total = paginate(db, stmt.order_by(M.mte_no), page, page_size)
    return {
        "items": [read(db, m) for m in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_item(db: Session, p: Principal, mte_id: uuid.UUID) -> QMteItem:
    m = db.get(QMteItem, mte_id)
    if m is None or not p.can_see_project(m.project_id):
        raise deny(db, p, EntityType.q_mte, mte_id, m.project_id if m else None, "M&TE item")
    _view(p, m.project_id)
    return m


def _validate(db: Session, project: Project, m: QMteItem) -> None:
    if m.site_id is not None:
        s = db.get(Site, m.site_id)
        if s is None or s.project_id != project.id:
            raise qc.field_err("site_id", "The site does not belong to this project.")
    if m.zone_id is not None:
        z = db.get(Zone, m.zone_id)
        if z is None or z.project_id != project.id or (m.site_id and z.site_id != m.site_id):
            raise qc.field_err("zone_id", "The zone does not belong to the site.")
    if m.check_kind != QMteCheckKind.none and not m.interval_months:
        raise qc.field_err("interval_months", "An interval is required for a checked item.")
    if m.interval_months is not None and not 1 <= m.interval_months <= 120:
        raise qc.field_err("interval_months", "Interval: 1–120 months.")
    if m.serial_no:
        clash = db.scalar(
            select(QMteItem.id).where(
                QMteItem.project_id == project.id,
                QMteItem.id != m.id,
                QMteItem.serial_no == m.serial_no,
                QMteItem.manufacturer.is_not_distinct_from(m.manufacturer),
            )
        )
        if clash:
            raise qc.err(
                422,
                ErrorCode.MTE_SERIAL_DUPLICATE,
                "An instrument with this manufacturer and serial number is already registered "
                "on the project.",
                "يوجد جهاز مسجل بنفس الشركة المصنعة والرقم التسلسلي في المشروع.",
            )


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    qc.require_cover(
        p, project.id, C.mte_manage, body.get("site_id"), body.get("owner_engagement_id")
    )
    qc.require_profile(db, project)
    m = QMteItem(
        id=uuid.uuid4(),
        project_id=project.id,
        mte_no="",
        mte_type=QMteType(body["mte_type"]),
        description=body["description"],
        owner_kind=QMteOwnerKind(body.get("owner_kind") or "own"),
        check_kind=QMteCheckKind(body.get("check_kind") or "calibration"),
        cal_status=QCalStatus.unknown,
        status=QMteStatus.active,
        created_by_user_id=p.user.id,
    )
    for k in EDIT:
        if k in body and body[k] is not None and k not in ("mte_type", "owner_kind", "check_kind"):
            setattr(m, k, body[k])
    if m.check_kind == QMteCheckKind.none:
        m.cal_status = QCalStatus.not_required
    _validate(db, project, m)
    m.mte_no = numbering.assign(db, project, QRecordType.mte)
    db.add(m)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.q_mte,
        entity_id=m.id,
        project_id=project.id,
        after={"mte_no": m.mte_no, "type": m.mte_type},
    )
    return read(db, m)


def update(db: Session, p: Principal, mte_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    m = get_item(db, p, mte_id)
    project = qc.get_project(db, p, m.project_id)
    qc.writable(project, p)
    qc.require_cover(p, project.id, C.mte_manage, m.site_id, m.owner_engagement_id)
    before = read(db, m)
    for k in EDIT:
        if k in body and (body[k] is not None or k in ("zone_id", "custodian_user_id")):
            v = body[k]
            if k == "mte_type":
                v = QMteType(v)
            elif k == "owner_kind":
                v = QMteOwnerKind(v)
            elif k == "check_kind":
                v = QMteCheckKind(v)
            setattr(m, k, v)
    if body.get("status") is not None:
        m.status = QMteStatus(body["status"])
    if m.check_kind == QMteCheckKind.none:
        m.cal_status = QCalStatus.not_required
    elif m.cal_status == QCalStatus.not_required:
        m.cal_status = QCalStatus.unknown
    _validate(db, project, m)
    m.updated_by_user_id = p.user.id
    db.flush()
    b, a = audit.diff(before, read(db, m))
    if a:
        audit.record(
            db,
            AuditAction.update,
            p.actor(project.id),
            entity_type=EntityType.q_mte,
            entity_id=m.id,
            project_id=project.id,
            before=b,
            after=a,
        )
    return read(db, m)


def _problem(m: QMteItem) -> bool:
    return (
        m.cal_status in MTE_WARN_STATUSES
        or m.cal_status == QCalStatus.unknown
        or m.status in (QMteStatus.retired, QMteStatus.lost)
    )


def record_usage(
    db: Session,
    project: Project,
    mte_id: uuid.UUID,
    record_type: QRecordType | str,
    record_id: uuid.UUID,
    user_id: uuid.UUID | None,
    used_at: datetime | None = None,
    value_note: str | None = None,
) -> tuple[QMteUsage, list[ApiWarning]]:
    """Q-SHR-04: every part that records a measurement with an instrument calls this. Overdue or
    out-of-service (or a retired / lost item) warns `MTE_NOT_CALIBRATED` (policy `warn`) or
    refuses (policy `block`, 422); `unknown` (Q2 not installed) always warns."""
    m = db.get(QMteItem, mte_id)
    if m is None or m.project_id != project.id:
        raise qc.field_err("mte_id", "The instrument is not registered on this project.")
    warnings: list[ApiWarning] = []
    verdict = QMteUseVerdict.ok
    if _problem(m):
        policy = qs.value(db, project.id, "mte_use_policy")
        if policy == "block" and m.cal_status != QCalStatus.unknown:
            raise qc.err(
                422,
                ErrorCode.MTE_NOT_CALIBRATED,
                f"{m.mte_no} is {m.cal_status.value}; it may not be used (policy block).",
                f"الجهاز {m.mte_no} غير معاير؛ لا يجوز استخدامه.",
                mte_no=m.mte_no,
            )
        verdict = QMteUseVerdict.warned
        warnings.append(
            qc.warning(
                ErrorCode.MTE_NOT_CALIBRATED,
                f"{m.mte_no} is {m.cal_status.value} ({m.status.value}); check the calibration.",
                f"الجهاز {m.mte_no} غير معاير أو حالته غير معروفة؛ تحقق من المعايرة.",
                "mte_id",
            )
        )
    u = QMteUsage(
        mte_id=m.id,
        project_id=project.id,
        record_type=QRecordType(record_type).value,
        record_id=record_id,
        used_at=used_at or now(),
        verdict=verdict,
        cal_status_at_use=m.cal_status,
        value_note=value_note,
        recorded_by_user_id=user_id,
    )
    db.add(u)
    db.flush()
    return u, warnings


def usage_api(db: Session, p: Principal, mte_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    m = get_item(db, p, mte_id)
    project = qc.get_project(db, p, m.project_id)
    qc.writable(project, p)
    p.require(project.id, C.mte_manage)
    u, warnings = record_usage(
        db,
        project,
        m.id,
        body["record_type"],
        body["record_id"],
        p.user.id,
        body.get("used_at"),
        body.get("value_note"),
    )
    return {**usage_read(u), "warnings": [w.model_dump() for w in warnings]}


def usage_read(u: QMteUsage) -> dict[str, Any]:
    return {
        "id": u.id,
        "mte_id": u.mte_id,
        "record_type": u.record_type,
        "record_id": u.record_id,
        "used_at": u.used_at,
        "verdict": u.verdict,
        "cal_status_at_use": u.cal_status_at_use,
        "value_note": u.value_note,
    }


def usage_list(db: Session, p: Principal, mte_id: uuid.UUID) -> list[dict[str, Any]]:
    m = get_item(db, p, mte_id)
    rows = db.scalars(
        select(QMteUsage).where(QMteUsage.mte_id == m.id).order_by(QMteUsage.used_at.desc())
    )
    return [usage_read(u) for u in rows]
