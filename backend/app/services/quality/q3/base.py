"""Helpers shared by the Q3 logistics services (spec 8-quality Part D): profile-gated writes
(Q-PRF-04), visibility with the responsible-person scope N (Q-ROL-04), "place only" for Warehouse
QC (capability 270), sign-off of matrix steps (Q-RPM-03…06), numbers, references and alerts."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import Capability, CapabilityScope, EntityType, Role
from app.core.errors import ErrorCode
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QRecordType
from app.models import Attachment, Project, ProjectEngagement, RoleAssignment, Site, Zone
from app.models.quality import QCustomer, QMteItem, QRpRule, QSignoff, QSupplier
from app.schemas.hse_common import ApiWarning
from app.services import audit
from app.services.permissions import Grant, Principal, deny, forbidden_error
from app.services.quality import common as qc
from app.services.quality import numbering, rpm, signoff
from app.services.quality import settings as qs

C = Capability
S = CapabilityScope
RT = QRecordType
RIYADH = ZoneInfo("Asia/Riyadh")


# ---- projects and permissions -----------------------------------------------------------------


def project_for_create(
    db: Session, p: Principal, project_id: uuid.UUID, rt: QRecordType, cap: Capability
) -> tuple[Project, Grant]:
    """A new Q3 record: open project, writer, logistics profile (Q-PRF-04) and the capability
    with a real (not N) grant."""
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    qc.ensure_profile_for(db, project, rt)
    g = p.require(project.id, cap)
    if g.scope == S.responsible:
        raise forbidden_error("A responsible person signs steps; they do not create records.")
    return project, g


def project_for_progress(
    db: Session, p: Principal, project_id: uuid.UUID, cap: Capability, *, allow_n: bool = False
) -> tuple[Project, Grant]:
    """Progressing an existing record: no profile check (Q-PRF-04: open records of the other
    profile may still be finished)."""
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    g = p.require(project.id, cap)
    if g.scope == S.responsible and not allow_n:
        raise forbidden_error("This action is not part of a responsible-person step.")
    return project, g


def site_ok(g: Grant | None, site_id: uuid.UUID | None) -> bool:
    if g is None or g.scope == S.responsible:
        return False
    return site_id is None or g.covers_site(site_id)


def require_site(g: Grant, site_id: uuid.UUID | None) -> None:
    if not site_ok(g, site_id):
        raise forbidden_error("This site is outside your scope.")


def place_only(db: Session, p: Principal, project_id: uuid.UUID) -> bool:
    """Capability 270 is "P (place only)" for Warehouse QC: a user whose only role on the project
    granting 270 is warehouse_qc may place holds but not release or reject them."""
    if p.is_manager:
        return False
    roles = {a.role for a in p.active_assignments if a.project_id == project_id}
    granting = {r for r in roles if r in (Role.qa_qc_manager, Role.quality_engineer)}
    return not granting and Role.responsible_person not in roles


def hide_names(p: Principal, project_id: uuid.UUID) -> bool:
    from app.services.quality.ncr.core import read_only_viewer  # noqa: PLC0415

    return read_only_viewer(p, project_id)


def signed_by(db: Session, rt: QRecordType, rid: uuid.UUID, uid: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(QSignoff.id).where(
                QSignoff.record_type == rt.value,
                QSignoff.record_id == rid,
                QSignoff.signed_by_user_id == uid,
            )
        )
        is not None
    )


StepList = Sequence[tuple[str, rpm.Ctx, str | None]]


def can_view(
    db: Session,
    p: Principal,
    project: Project,
    rt: QRecordType,
    rid: uuid.UUID,
    site_id: uuid.UUID | None,
    steps: Callable[..., StepList] | None = None,
) -> bool:
    g = p.grant(project.id, C.quality_view)
    if g is None:
        return False
    if g.scope != S.responsible:
        return site_id is None or g.covers_site(site_id)
    # Q-ROL-04: a responsible person reads only records with a step they resolve for or signed
    if signed_by(db, rt, rid, p.user.id):
        return True
    for step, ctx, qual in steps() if steps else []:
        if rpm.resolves(db, p, project, rt, step, ctx, qualifier=qual, record_id=rid, can_act=False):
            return True
    return False


def not_found(db: Session, p: Principal, rt: QRecordType, rid: uuid.UUID, pid: Any) -> Any:
    from app.core.quality.common import entity_type_value  # noqa: PLC0415

    return deny(db, p, EntityType(entity_type_value(rt)), rid, pid, rt.value)


def list_grant(p: Principal, project_id: uuid.UUID) -> Grant:
    return p.require(project_id, C.quality_view)


# ---- sign-offs ----------------------------------------------------------------------------------


def sign(
    db: Session,
    p: Principal,
    project: Project,
    rt: QRecordType,
    rid: uuid.UUID,
    step: str,
    ctx: rpm.Ctx,
    *,
    decision: str = "approved",
    comment: str | None = None,
    qualifier: str | None = None,
    evidence: list[uuid.UUID] | None = None,
) -> QSignoff:
    """The caller must resolve for the step (Q-RPM-03) and not be the requester (Q-RPM-06)."""
    rule, capacity = rpm.check_signer(
        db, p, project, rt, step, ctx, qualifier=qualifier, record_id=rid
    )
    return signoff.sign(
        db, p, project, rt, rid, step, decision, comment, rule, capacity, evidence_ids=evidence
    )


def resolves(
    db: Session,
    p: Principal,
    project: Project,
    rt: QRecordType,
    rid: uuid.UUID | None,
    step: str,
    ctx: rpm.Ctx,
    qualifier: str | None = None,
) -> bool:
    return rpm.resolves(db, p, project, rt, step, ctx, qualifier=qualifier, record_id=rid)


def resolvers(
    db: Session,
    project: Project,
    rt: QRecordType,
    step: str,
    ctx: rpm.Ctx,
    *,
    qualifier: str | None = None,
    record_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    res = rpm.resolve(db, project, rt, step, ctx, qualifier=qualifier, record_id=record_id)
    return list(res.users)


def rule_for(
    db: Session, project: Project, rt: QRecordType, step: str, qualifier: str | None = None
) -> QRpRule | None:
    return rpm.effective_rule(db, project.id, rt, step, qualifier=qualifier)


# ---- people -------------------------------------------------------------------------------------


def holders(db: Session, project: Project, cap: Capability, site_id: uuid.UUID | None = None) -> set[uuid.UUID]:
    """Real holders of a capability on the project (not the responsible-person scope N; the
    HSE Manager included), limited to a site when the assignment is site-limited."""
    from app.services.permissions import MATRIX  # noqa: PLC0415

    day = qc.project_day(project)
    out: set[uuid.UUID] = set()
    for a in db.scalars(
        select(RoleAssignment).where(
            RoleAssignment.revoked_at.is_(None),
            (RoleAssignment.project_id == project.id) | (RoleAssignment.role == Role.hse_manager),
        )
    ):
        if not a.is_active_on(day) or a.role == Role.responsible_person:
            continue
        if a.role != Role.hse_manager and cap not in MATRIX.get(a.role, {}):
            continue
        if site_id is not None and a.site_ids and site_id not in a.site_ids:
            continue
        out.add(a.user_id)
    return out


def ncr_owner(db: Session, project: Project, actor: uuid.UUID | None) -> uuid.UUID:
    """Owner of an auto-raised NCR: the acting user when they manage NCRs, else the project's
    first QA/QC Manager, else any 242 holder."""
    from app.services.permissions import MATRIX  # noqa: PLC0415

    day = qc.project_day(project)
    rows = [
        a
        for a in db.scalars(
            select(RoleAssignment)
            .where(RoleAssignment.project_id == project.id, RoleAssignment.revoked_at.is_(None))
            .order_by(RoleAssignment.created_at)
        )
        if a.is_active_on(day)
    ]
    if actor is not None and any(
        a.user_id == actor and C.ncr_manage in MATRIX.get(a.role, {}) for a in rows
    ):
        return actor
    for role in (Role.qa_qc_manager, Role.quality_engineer, Role.warehouse_qc):
        for a in rows:
            if a.role == role:
                return a.user_id
    if actor is not None:
        return actor
    raise qc.err(
        422,
        ErrorCode.RESPONSIBLE_PERSON_NOT_SET,
        "No Quality user can own the NCR on this project.",
        "لا يوجد مستخدم جودة يمكنه تولي التقرير في هذا المشروع.",
    )


def operator_engagement(db: Session, project: Project) -> uuid.UUID | None:
    """The warehouse operator's engagement (the project's first tier-1 engagement): the
    responsible party of logistics NCRs (Q-NCR-03 needs one)."""
    return db.scalar(
        select(ProjectEngagement.id)
        .where(ProjectEngagement.project_id == project.id)
        .order_by(ProjectEngagement.tier, ProjectEngagement.created_at)
        .limit(1)
    )


def send(
    db: Session,
    project: Project,
    users: Iterable[uuid.UUID],
    key: str,
    title_en: str,
    title_ar: str,
    *,
    body_en: str | None = None,
    body_ar: str | None = None,
    rt: QRecordType | None = None,
    rid: uuid.UUID | None = None,
    path: str | None = None,
    email: bool = True,
) -> int:
    from app.core.quality.common import entity_type_value  # noqa: PLC0415

    return qc.send(
        db,
        users,
        title_en,
        title_ar,
        body_en=body_en,
        body_ar=body_ar,
        entity_type=EntityType(entity_type_value(rt)) if rt else None,
        entity_id=rid,
        project_id=project.id,
        email=email,
        key=key,
        path=path,
    )


# ---- numbers, settings, refs ---------------------------------------------------------------------


def number(db: Session, project: Project, rt: QRecordType, at: datetime | None = None) -> str:
    site = db.scalar(select(Site.code).where(Site.project_id == project.id).limit(1))
    return numbering.assign(db, project, rt, on=qc.project_day(project, at), site_code=site)


def setting(db: Session, project_id: uuid.UUID, key: str) -> Any:
    return qs.value(db, project_id, key)


def dsetting(db: Session, project_id: uuid.UUID, key: str) -> Decimal:
    return Decimal(str(qs.value(db, project_id, key)))


def local(dt: datetime) -> datetime:
    return dt.astimezone(RIYADH)


def local_day(dt: datetime) -> date:
    return dt.astimezone(RIYADH).date()


def day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=RIYADH).astimezone(UTC)


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = day_start(date(year, month, 1))
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return start, day_start(nxt)


def floor_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def q2(v: Decimal | float | int | None) -> Decimal | None:
    if v is None:
        return None
    return Decimal(str(v)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def q1(v: Decimal | float | int | None) -> Decimal | None:
    if v is None:
        return None
    return Decimal(str(v)).quantize(Decimal("0.1"), ROUND_HALF_UP)


def site_of(db: Session, project: Project, site_id: uuid.UUID) -> Site:
    s = db.get(Site, site_id)
    if s is None or s.project_id != project.id:
        raise qc.field_err("site_id", "The site is not on this project.", "الموقع ليس في المشروع.")
    return s


def zone_of(db: Session, project: Project, zone_id: uuid.UUID, field: str = "zone_id") -> Zone:
    z = db.get(Zone, zone_id)
    if z is None or db.get(Site, z.site_id) is None or db.get(Site, z.site_id).project_id != project.id:  # type: ignore[union-attr]
        raise qc.field_err(field, "The zone is not on this project.", "المنطقة ليست في المشروع.")
    return z


def customer_of(db: Session, project: Project, cid: uuid.UUID, field: str = "customer_id") -> QCustomer:
    c = db.get(QCustomer, cid)
    if c is None or c.project_id != project.id:
        raise qc.field_err(field, "The customer is not on this project.", "العميل ليس في المشروع.")
    return c


def mte_of(db: Session, project: Project, mid: uuid.UUID, field: str = "mte_id") -> QMteItem:
    m = db.get(QMteItem, mid)
    if m is None or m.project_id != project.id:
        raise qc.field_err(field, "The instrument is not registered on this project.", "الجهاز غير مسجل في المشروع.")
    return m


def supplier_warnings(db: Session, sid: uuid.UUID | None) -> list[ApiWarning]:
    from app.services.quality import suppliers  # noqa: PLC0415

    return suppliers.check_use(db, sid) if sid else []


def attachment_on(
    db: Session,
    aid: uuid.UUID | None,
    owner: AttachmentOwner,
    owner_id: uuid.UUID,
    field: str,
) -> uuid.UUID | None:
    """An attachment id given in a request must belong to the record (uploaded first through
    `POST /attachments` with this owner type)."""
    if aid is None:
        return None
    a = db.get(Attachment, aid)
    if a is None or a.owner_type != owner or a.owner_id != owner_id:
        raise qc.field_err(
            field,
            "Upload the file to this record first (owner type " + owner.value + ").",
            "ارفع الملف إلى هذا السجل أولاً.",
        )
    return aid


def customer_ref(db: Session, cid: uuid.UUID | None) -> dict[str, Any] | None:
    c = db.get(QCustomer, cid) if cid else None
    if c is None:
        return None
    return {
        "id": c.id,
        "code": c.code,
        "name_en": c.name_en,
        "name_ar": c.name_ar,
        "owner_release_approval": c.owner_release_approval,
    }


def supplier_ref(db: Session, sid: uuid.UUID | None) -> dict[str, Any] | None:
    s = db.get(QSupplier, sid) if sid else None
    if s is None:
        return None
    return {
        "id": s.id,
        "code": s.supplier_code,
        "name_en": s.legal_name_en,
        "name_ar": s.legal_name_ar,
        "status": s.status,
    }


def zone_ref(db: Session, zid: uuid.UUID | None) -> dict[str, Any] | None:
    z = db.get(Zone, zid) if zid else None
    if z is None:
        return None
    return {"id": z.id, "code": z.code, "name_en": z.name_en, "name_ar": z.name_ar}


def site_ref(db: Session, sid: uuid.UUID | None) -> dict[str, Any] | None:
    s = db.get(Site, sid) if sid else None
    if s is None:
        return None
    return {"id": s.id, "code": s.code, "name_en": s.name_en, "name_ar": s.name_ar}


def mte_ref(db: Session, mid: uuid.UUID | None) -> dict[str, Any] | None:
    m = db.get(QMteItem, mid) if mid else None
    if m is None:
        return None
    return {
        "id": m.id,
        "mte_no": m.mte_no,
        "description": m.description,
        "cal_status": m.cal_status,
        "cal_due_on": m.cal_due_on,
    }


def user_ref(db: Session, uid: uuid.UUID | None, hide: bool = False) -> dict[str, Any] | None:
    from app.services.hse_common import Refs  # noqa: PLC0415

    if uid is None or hide:
        return None
    u = Refs(db).user(uid)
    return u.model_dump() if u else None


def audit_status(
    db: Session,
    p: Principal | None,
    project: Project,
    rt: QRecordType,
    rid: uuid.UUID,
    before: Any,
    after: Any,
    **details: Any,
) -> None:
    from app.core.enums import AuditAction  # noqa: PLC0415
    from app.core.quality.common import entity_type_value  # noqa: PLC0415
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(project.id) if p else audit.SYSTEM,
        entity_type=EntityType(entity_type_value(rt)),
        entity_id=rid,
        project_id=project.id,
        before={"status": str(before)} if before is not None else None,
        after={"status": str(after)},
        details=details or None,
    )


def audit_create(
    db: Session, p: Principal | None, project: Project, rt: QRecordType, rid: uuid.UUID, **after: Any
) -> None:
    from app.core.enums import AuditAction  # noqa: PLC0415
    from app.core.quality.common import entity_type_value  # noqa: PLC0415
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id) if p else audit.SYSTEM,
        entity_type=EntityType(entity_type_value(rt)),
        entity_id=rid,
        project_id=project.id,
        after={k: str(v) for k, v in after.items()},
    )


def warn_dump(ws: list[ApiWarning]) -> list[dict[str, Any]]:
    return [w.model_dump() for w in ws]


def page(items: list[Any], page_no: int, size: int) -> dict[str, Any]:
    start = (page_no - 1) * size
    return {"items": items[start : start + size], "total": len(items), "page": page_no, "page_size": size}


def minutes(a: datetime, b: datetime) -> int:
    return int((b - a) / timedelta(minutes=1))


_ = now
