# ruff: noqa: E501
"""Isolations / LOTO (spec 3-ptw §3.11, §4.4, §4.5, IS-1…IS-11, §7 isolation alerts)."""

import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import any_, or_, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.ptw_enums import (
    PERMIT_LIVE,
    AppointmentDiscipline,
    AppointmentFunction,
    EnergyType,
    IsolationMethod,
    IsolationStatus,
    LockStatus,
    LockType,
    PermitStatus,
    PersonalLockRemoval,
    StatusReason,
    VerificationMethod,
)
from app.models import (
    Deployment,
    IsolationCertificate,
    IsolationPoint,
    Lock,
    Permit,
    PersonalLockEvent,
    Worker,
)
from app.schemas.isolations import (
    IsolationCreate,
    IsolationPage,
    IsolationPointInput,
    IsolationPointRead,
    IsolationPointUpdate,
    IsolationRead,
    IsolationTransition,
    IsolationUpdate,
    LockCreate,
    LockCutInput,
    LockCutRead,
    LockLostInput,
    LockPage,
    LockRead,
    LockUpdate,
    LongTermReviewInput,
    LongTermReviewRead,
    PersonalLockApply,
    PersonalLockEventRead,
    PersonalLockList,
    PersonalLockRemove,
    PointApplyInput,
    PointRemoveInput,
    PointVerifyInput,
    WorkerInformedInput,
)
from app.services import audit, notify, projects
from app.services.access import common as acommon
from app.services.common import duplicate, invalid_transition, paginate
from app.services.hse_common import Refs, contractor_reps, make_ref, next_seq
from app.services.permissions import Principal, forbidden_error
from app.services.ptw import common
from app.services.ptw.gas import short_code

C = Capability
S = IsolationStatus
LOCK_PREFIX = {LockType.isolation_lock: "L", LockType.personal_lock: "P", LockType.lockbox: "LB"}
OPEN_STATUSES = (S.isolated, S.verified, S.deisolation_requested)
FLUID = {EnergyType.hydraulic, EnergyType.pneumatic, EnergyType.process_fluid, EnergyType.thermal}
FLUID_METHODS = {
    VerificationMethod.pressure_gauge_zero,
    VerificationMethod.visual_air_gap,
    VerificationMethod.other,
}


def _audit(
    db: Session,
    p: Principal | None,
    project_id: uuid.UUID,
    et: EntityType,
    eid: uuid.UUID,
    action: AuditAction,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    details: dict[str, Any] | None = None,
) -> None:
    audit.record(
        db,
        action,
        p.actor(project_id) if p else audit.SYSTEM,
        entity_type=et,
        entity_id=eid,
        project_id=project_id,
        before=before,
        after=after,
        details=details,
    )


# ---- queries -------------------------------------------------------------------------------------


def points(db: Session, c: IsolationCertificate) -> list[IsolationPoint]:
    return list(
        db.scalars(
            select(IsolationPoint)
            .where(IsolationPoint.certificate_id == c.id)
            .order_by(IsolationPoint.point_no)
        )
    )


def linked_permits(db: Session, c: IsolationCertificate) -> list[Permit]:
    return list(
        db.scalars(
            select(Permit).where(any_(Permit.isolation_cert_ids) == c.id).order_by(Permit.permit_no)
        )
    )


def active_personal_locks(db: Session, lockbox_id: uuid.UUID) -> list[PersonalLockEvent]:
    return list(
        db.scalars(
            select(PersonalLockEvent)
            .where(
                PersonalLockEvent.lockbox_id == lockbox_id, PersonalLockEvent.removed_at.is_(None)
            )
            .order_by(PersonalLockEvent.applied_at)
        )
    )


def certs_of(db: Session, permit: Permit) -> list[IsolationCertificate]:
    ids = list(permit.isolation_cert_ids or [])
    if not ids:
        return []
    return list(db.scalars(select(IsolationCertificate).where(IsolationCertificate.id.in_(ids))))


def is_effective(db: Session, c: IsolationCertificate) -> bool:
    """IS-6: Verified, every point locked with an applied isolation lock (IS-11 lost lock → no)."""
    if c.status != S.verified:
        return False
    for pt in points(db, c):
        if pt.removed_at is not None or pt.isolation_lock_id is None or pt.verified_at is None:
            return False
        lk = db.get(Lock, pt.isolation_lock_id)
        if lk is None or lk.status != LockStatus.applied:
            return False
    return True


def long_term(db: Session, c: IsolationCertificate, at: datetime | None = None) -> bool:
    if c.status not in OPEN_STATUSES or c.verified_at is None:
        return False
    days = common.settings(db, c.project_id).long_term_isolation_days
    return (at or now()) - c.verified_at > timedelta(days=days)


def _review_due_at(db: Session, c: IsolationCertificate) -> datetime | None:
    if not long_term(db, c) or c.verified_at is None:
        return None
    days = common.settings(db, c.project_id).long_term_isolation_days
    start = c.verified_at + timedelta(days=days)
    last = c.reviews[-1]["at"] if c.reviews else None
    base = datetime.fromisoformat(last) if last else start
    return base + timedelta(days=7) if last else start


def deisolation_blockers(db: Session, c: IsolationCertificate) -> tuple[list[str], list[str]]:
    """IS-7: (permit numbers still live or expired without post-expiry check, personal locks)."""
    permits = []
    for x in linked_permits(db, c):
        if x.status in (PermitStatus.closed, PermitStatus.cancelled):
            continue
        if x.status == PermitStatus.expired and x.post_expiry_check:
            continue
        permits.append(x.permit_no)
    locks = []
    for e in active_personal_locks(db, c.lockbox_id):
        lk = db.get(Lock, e.lock_id)
        if lk:
            locks.append(lk.lock_no)
    return permits, sorted(locks)


# ---- read models ---------------------------------------------------------------------------------


def _lock_no(db: Session, lock_id: uuid.UUID | None) -> str | None:
    lk = db.get(Lock, lock_id) if lock_id else None
    return lk.lock_no if lk else None


def _point_read(db: Session, pt: IsolationPoint, refs: Refs, names: bool) -> IsolationPointRead:
    w = db.get(Worker, pt.verified_by_worker_id) if pt.verified_by_worker_id else None
    return IsolationPointRead(
        id=pt.id,
        point_no=pt.point_no,
        energy_type=pt.energy_type,
        device_tag=pt.device_tag,
        location=pt.location,
        method=pt.method,
        isolation_lock_no=_lock_no(db, pt.isolation_lock_id),
        tag_no=pt.tag_no,
        applied_by=refs.user(pt.applied_by_user_id),
        applied_at=pt.applied_at,
        verified_by_user=refs.user(pt.verified_by_user_id),
        verified_by_worker=acommon.worker_ref(w, names) if w else None,
        verified_at=pt.verified_at,
        verification_method=pt.verification_method,
        removed_by=refs.user(pt.removed_by_user_id),
        removed_at=pt.removed_at,
    )


def event_read(
    db: Session, p: Principal | None, e: PersonalLockEvent, refs: Refs | None = None
) -> PersonalLockEventRead:
    refs = refs or Refs(db)
    names = acommon.can_see_names(p, e.project_id)
    w = db.get(Worker, e.worker_id)
    permit = db.get(Permit, e.permit_id) if e.permit_id else None
    cut = None
    if e.cut_record:
        r = e.cut_record
        by = refs.user(uuid.UUID(r["approved_by_user_id"]))
        if by:
            cut = LockCutRead(
                approved_by=by,
                supervisor_confirmed_absent_at=datetime.fromisoformat(
                    r["supervisor_confirmed_absent_at"]
                ),
                contact_attempts=r["contact_attempts"],
                worker_informed_at=datetime.fromisoformat(r["worker_informed_at"])
                if r.get("worker_informed_at")
                else None,
                cut_at=datetime.fromisoformat(r["cut_at"]),
            )
    return PersonalLockEventRead(
        id=e.id,
        lock_no=_lock_no(db, e.lock_id) or "",
        lockbox_no=_lock_no(db, e.lockbox_id) or "",
        worker=acommon.worker_ref(w, names) if (w and names) else None,
        permit=common.permit_ref(permit) if permit else None,
        applied_at=e.applied_at,
        removed_at=e.removed_at,
        removed_by=e.removed_by,
        cut=cut,
    )


def to_read(db: Session, p: Principal | None, c: IsolationCertificate) -> IsolationRead:
    refs = Refs(db)
    names = acommon.can_see_names(p, c.project_id)
    ia = refs.user(c.isolation_authority_user_id)
    assert ia is not None  # noqa: S101
    last = None
    if c.reviews:
        r = c.reviews[-1]
        u = refs.user(uuid.UUID(r["by"]))
        if u:
            last = LongTermReviewRead(
                reviewed_by=u,
                reviewed_at=datetime.fromisoformat(r["at"]),
                lock_tag_in_place=r["in_place"],
                note=r.get("note"),
            )
    permits_b, locks_b = deisolation_blockers(db, c)
    blockers = [*permits_b, *locks_b] if c.status == S.verified else []
    return IsolationRead(
        id=c.id,
        project_id=c.project_id,
        iso_no=c.iso_no,
        equipment_desc=c.equipment_desc,
        energy_types=[EnergyType(e) for e in c.energy_types],
        hv=c.hv,
        isolation_authority=ia,
        lockbox_no=_lock_no(db, c.lockbox_id) or "",
        lockbox_id=c.lockbox_id,
        switching_programme_ref=c.switching_programme_ref,
        points=[_point_read(db, pt, refs, names) for pt in points(db, c)],
        personal_locks_applied=[
            event_read(db, p, e, refs) for e in active_personal_locks(db, c.lockbox_id)
        ],
        permits=[common.permit_ref(x) for x in linked_permits(db, c)],
        long_term=long_term(db, c),
        verified_since=c.verified_at if c.status in OPEN_STATUSES else None,
        last_review=last,
        review_due_at=_review_due_at(db, c),
        deisolation_authorised_by=refs.user(c.deisolation_authorised_by_user_id),
        deisolation_authorised_at=c.deisolation_authorised_at,
        deisolation_blockers=blockers,
        status=c.status,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


def lock_read(db: Session, p: Principal | None, lk: Lock) -> LockRead:
    names = acommon.can_see_names(p, lk.project_id)
    w = db.get(Worker, lk.holder_worker_id) if lk.holder_worker_id else None
    return LockRead(
        id=lk.id,
        project_id=lk.project_id,
        lock_no=lk.lock_no,
        lock_type=lk.lock_type,
        holder_worker=acommon.worker_ref(w, names) if w else None,
        status=lk.status,
        applied_on=lk.applied_on,
        updated_at=lk.updated_at,
    )


# ---- access --------------------------------------------------------------------------------------


def _visible(g: Any, db: Session, c: IsolationCertificate) -> bool:
    if g.engagement_ids is None and g.site_ids is None:
        return True
    if c.engagement_id and acommon.grant_covers(g, None, c.engagement_id) and g.site_ids is None:
        return True
    return any(
        acommon.grant_covers(g, [x.site_id], x.engagement_id) for x in linked_permits(db, c)
    ) or (g.engagement_ids is None and not linked_permits(db, c))


def get_cert(db: Session, p: Principal, isolation_id: uuid.UUID) -> IsolationCertificate:
    c = db.get(IsolationCertificate, isolation_id)
    if c is None:
        raise not_found("Isolation certificate")
    g = common.view_grant(db, p, c.project_id)
    if not _visible(g, db, c):
        raise forbidden_error("This isolation is outside your scope.")
    return c


def _require_92(p: Principal, project_id: uuid.UUID) -> None:
    acommon.require_cap(p, project_id, C.isolation_manage)


def _authority_discipline(hv: bool, energy_types: list[str]) -> list[str]:
    if hv:
        return [AppointmentDiscipline.electrical_hv.value]
    if EnergyType.electrical.value in energy_types:
        return [
            AppointmentDiscipline.electrical_lv.value,
            AppointmentDiscipline.electrical_hv.value,
        ]
    return [AppointmentDiscipline.mechanical_process.value]


def _check_authority(
    db: Session, project_id: uuid.UUID, user_id: uuid.UUID, hv: bool, energy: list[str]
) -> None:
    day = acommon.local_day(now())
    needed = _authority_discipline(hv, energy)
    if EnergyType.electrical.value in energy and len(energy) > 1 and not hv:
        needed = [*needed, AppointmentDiscipline.mechanical_process.value]
    ok = any(
        a.status.value == "active" and a.valid_from <= day <= a.valid_to
        for a in common.appointments_of(
            db,
            project_id,
            AppointmentFunction.isolation_authority,
            user_id=user_id,
            disciplines=needed,
        )
    )
    if not ok:
        raise common.err(
            ErrorCode.APPOINTMENT_INVALID,
            "The isolation authority needs an Active isolation_authority appointment with the matching discipline"
            + (" (electrical_hv for HV, IS-10)." if hv else "."),
            "يجب أن يحمل مسؤول العزل تعييناً سارياً بالتخصص المطابق.",
            field="isolation_authority_user_id",
        )


def _lockbox(
    db: Session, project_id: uuid.UUID, lockbox_id: uuid.UUID, cert_no: str | None
) -> Lock:
    lb = db.get(Lock, lockbox_id)
    if lb is None or lb.project_id != project_id or lb.lock_type != LockType.lockbox:
        raise validation_error("lockbox_id", "Choose a lockbox of this project.")
    if lb.status != LockStatus.available and not (cert_no and lb.applied_on == cert_no):
        raise common.err(
            ErrorCode.LOCK_NOT_AVAILABLE,
            f"Lockbox {lb.lock_no} is {lb.status.value}.",
            f"صندوق الأقفال {lb.lock_no} غير متاح.",
            field="lockbox_id",
        )
    return lb


# ---- certificates --------------------------------------------------------------------------------


def list_certs(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    size: int,
    statuses: list[IsolationStatus] | None,
    energy_types: list[EnergyType] | None,
    permit_id: uuid.UUID | None,
    long_term_only: bool | None,
    review_due: bool | None,
    q: str | None,
) -> IsolationPage:
    g = common.view_grant(db, p, project_id)
    stmt = select(IsolationCertificate).where(IsolationCertificate.project_id == project_id)
    if statuses:
        stmt = stmt.where(IsolationCertificate.status.in_(statuses))
    if energy_types:
        stmt = stmt.where(
            IsolationCertificate.energy_types.overlap([e.value for e in energy_types])
        )
    if permit_id:
        permit = db.get(Permit, permit_id)
        stmt = stmt.where(
            IsolationCertificate.id.in_(list(permit.isolation_cert_ids) if permit else [])
        )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                IsolationCertificate.iso_no.ilike(like),
                IsolationCertificate.equipment_desc.ilike(like),
            )
        )
    rows = [
        c
        for c in db.scalars(stmt.order_by(IsolationCertificate.iso_no.desc()))
        if _visible(g, db, c)
    ]
    if long_term_only is not None:
        rows = [c for c in rows if long_term(db, c) == long_term_only]
    if review_due is not None:
        at = now()
        rows = [
            c
            for c in rows
            if ((_review_due_at(db, c) or at + timedelta(days=1)) <= at) == review_due
        ]
    total = len(rows)
    chunk = rows[(page - 1) * size : page * size]
    return IsolationPage(
        items=[to_read(db, p, c) for c in chunk], total=total, page=page, page_size=size
    )


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: IsolationCreate
) -> IsolationRead:
    projects.get_visible(db, p, project_id)
    _require_92(p, project_id)
    energy = [e.value for e in body.energy_types]
    _check_authority(db, project_id, body.isolation_authority_user_id, body.hv, energy)
    if body.hv and not body.switching_programme_ref:
        raise validation_error(
            "switching_programme_ref", "HV isolations need a switching programme (IS-10)."
        )
    if body.hv and not any(pt.method == IsolationMethod.earth_applied for pt in body.points):
        raise validation_error(
            "points", "HV isolations need earths applied as points (method earth_applied, IS-10)."
        )
    year = acommon.local_day(now()).year
    seq = next_seq(db, IsolationCertificate, project_id, year)
    no = make_ref("ISO", common.project_code(db, project_id), year, seq, 4)
    lb = _lockbox(db, project_id, body.lockbox_id, None)
    c = IsolationCertificate(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        seq=seq,
        iso_no=no,
        equipment_desc=body.equipment_desc,
        energy_types=energy,
        hv=body.hv,
        isolation_authority_user_id=body.isolation_authority_user_id,
        lockbox_id=lb.id,
        switching_programme_ref=body.switching_programme_ref,
        status=S.planned,
        reviews=[],
        alerts_sent=[],
        created_by_user_id=p.user.id,
        updated_by_user_id=p.user.id,
    )
    db.add(c)
    db.flush()
    lb.status = LockStatus.applied
    lb.applied_on = no
    for i, pt in enumerate(body.points, start=1):
        _add_point(db, c, i, pt)
    db.flush()
    _audit(
        db,
        p,
        project_id,
        EntityType.isolation_certificate,
        c.id,
        AuditAction.create,
        None,
        {"iso_no": no, "status": "planned"},
    )
    return to_read(db, p, c)


def _add_point(
    db: Session, c: IsolationCertificate, n: int, pt: IsolationPointInput
) -> IsolationPoint:
    row = IsolationPoint(
        id=uuid.uuid4(),
        certificate_id=c.id,
        point_no=n,
        energy_type=pt.energy_type,
        device_tag=pt.device_tag,
        location=pt.location,
        method=pt.method,
    )
    db.add(row)
    return row


def read(db: Session, p: Principal, isolation_id: uuid.UUID) -> IsolationRead:
    return to_read(db, p, get_cert(db, p, isolation_id))


def _planned(c: IsolationCertificate) -> None:
    if c.status != S.planned:
        raise invalid_transition("isolation", c.status, "edit")


def update(
    db: Session, p: Principal, isolation_id: uuid.UUID, body: IsolationUpdate
) -> IsolationRead:
    c = get_cert(db, p, isolation_id)
    _require_92(p, c.project_id)
    _planned(c)
    ch = body.changes()
    before = {
        "equipment_desc": c.equipment_desc,
        "energy_types": list(c.energy_types),
        "lockbox": str(c.lockbox_id),
    }
    if "equipment_desc" in ch and body.equipment_desc:
        c.equipment_desc = body.equipment_desc
    if "energy_types" in ch and body.energy_types:
        c.energy_types = [e.value for e in body.energy_types]
        _check_authority(db, c.project_id, c.isolation_authority_user_id, c.hv, c.energy_types)
    if "lockbox_id" in ch and body.lockbox_id and body.lockbox_id != c.lockbox_id:
        new = _lockbox(db, c.project_id, body.lockbox_id, None)
        old = db.get(Lock, c.lockbox_id)
        if old:
            old.status, old.applied_on = LockStatus.available, None
        new.status, new.applied_on = LockStatus.applied, c.iso_no
        c.lockbox_id = new.id
    if "switching_programme_ref" in ch:
        c.switching_programme_ref = body.switching_programme_ref
    c.updated_by_user_id = p.user.id
    db.flush()
    _audit(
        db,
        p,
        c.project_id,
        EntityType.isolation_certificate,
        c.id,
        AuditAction.update,
        before,
        {
            "equipment_desc": c.equipment_desc,
            "energy_types": list(c.energy_types),
            "lockbox": str(c.lockbox_id),
        },
    )
    return to_read(db, p, c)


def _point(db: Session, c: IsolationCertificate, point_id: uuid.UUID) -> IsolationPoint:
    pt = db.get(IsolationPoint, point_id)
    if pt is None or pt.certificate_id != c.id:
        raise not_found("Isolation point")
    return pt


def add_point(
    db: Session, p: Principal, isolation_id: uuid.UUID, body: IsolationPointInput
) -> IsolationRead:
    c = get_cert(db, p, isolation_id)
    _require_92(p, c.project_id)
    _planned(c)
    n = max([x.point_no for x in points(db, c)] or [0]) + 1
    _add_point(db, c, n, body)
    db.flush()
    _audit(
        db,
        p,
        c.project_id,
        EntityType.isolation_certificate,
        c.id,
        AuditAction.update,
        None,
        {"point_added": n},
    )
    return to_read(db, p, c)


def update_point(
    db: Session,
    p: Principal,
    isolation_id: uuid.UUID,
    point_id: uuid.UUID,
    body: IsolationPointUpdate,
) -> IsolationRead:
    c = get_cert(db, p, isolation_id)
    _require_92(p, c.project_id)
    _planned(c)
    pt = _point(db, c, point_id)
    ch = body.changes()
    for k in ("energy_type", "device_tag", "location", "method"):
        if k in ch and getattr(body, k) is not None:
            setattr(pt, k, getattr(body, k))
    db.flush()
    _audit(
        db,
        p,
        c.project_id,
        EntityType.isolation_certificate,
        c.id,
        AuditAction.update,
        None,
        {"point_updated": pt.point_no},
    )
    return to_read(db, p, c)


def delete_point(db: Session, p: Principal, isolation_id: uuid.UUID, point_id: uuid.UUID) -> None:
    c = get_cert(db, p, isolation_id)
    _require_92(p, c.project_id)
    _planned(c)
    pt = _point(db, c, point_id)
    if len(points(db, c)) <= 1:
        raise validation_error("point_id", "A certificate needs at least one point.")
    n = pt.point_no
    db.delete(pt)
    db.flush()
    _audit(
        db,
        p,
        c.project_id,
        EntityType.isolation_certificate,
        c.id,
        AuditAction.update,
        None,
        {"point_removed": n},
    )


def apply_point(
    db: Session, p: Principal, isolation_id: uuid.UUID, point_id: uuid.UUID, body: PointApplyInput
) -> IsolationRead:
    c = get_cert(db, p, isolation_id)
    _require_92(p, c.project_id)
    if p.user.id != c.isolation_authority_user_id:
        raise forbidden_error("Points are applied by the certificate's isolation authority.")
    pt = _point(db, c, point_id)
    if c.status not in (S.planned, S.isolated, S.verified):
        raise invalid_transition("isolation", c.status, "apply")
    if pt.isolation_lock_id is not None and pt.removed_at is None:
        cur = db.get(Lock, pt.isolation_lock_id)
        if cur and cur.status == LockStatus.applied:
            raise common.err(
                ErrorCode.LOCK_NOT_AVAILABLE,
                "The point already has a lock (IS-2).",
                "النقطة عليها قفل بالفعل.",
            )
    lk = db.get(Lock, body.isolation_lock_id)
    if (
        lk is None
        or lk.project_id != c.project_id
        or lk.lock_type != LockType.isolation_lock
        or lk.status != LockStatus.available
    ):
        raise common.err(
            ErrorCode.LOCK_NOT_AVAILABLE,
            "Choose an available isolation lock of this project (IS-2).",
            "اختر قفل عزل متاحاً في هذا المشروع.",
            field="isolation_lock_id",
        )
    if body.applied_at > now() + timedelta(minutes=2):
        raise validation_error("applied_at", "The time cannot be in the future.")
    relock = pt.applied_at is not None
    lk.status = LockStatus.applied
    lk.applied_on = f"{c.iso_no} point {pt.point_no}"
    pt.isolation_lock_id = lk.id
    pt.tag_no = body.tag_no
    pt.applied_by_user_id = p.user.id
    pt.applied_at = body.applied_at
    if relock:
        pt.verified_at = None
        pt.verified_by_user_id = None
        pt.verified_by_worker_id = None
        if c.status == S.verified:
            c.status = S.isolated
    db.flush()
    _audit(
        db,
        p,
        c.project_id,
        EntityType.isolation_certificate,
        c.id,
        AuditAction.update,
        None,
        {"point_applied": pt.point_no, "lock": lk.lock_no, "tag": body.tag_no},
    )
    _refresh_linked(db, c)
    return to_read(db, p, c)


def verify_point(
    db: Session, p: Principal, isolation_id: uuid.UUID, point_id: uuid.UUID, body: PointVerifyInput
) -> IsolationRead:
    c = get_cert(db, p, isolation_id)
    p.ensure_writer()
    if (
        p.grant(c.project_id, C.isolation_manage) is None
        and p.grant(c.project_id, C.permit_receive) is None
    ):
        raise forbidden_error()
    if c.status not in (S.isolated, S.verified):
        raise invalid_transition("isolation", c.status, "verify")
    pt = _point(db, c, point_id)
    if pt.applied_at is None:
        raise validation_error("point_id", "Apply the lock and tag before verifying.")
    v_user = None if body.verified_by_worker_id else (body.verified_by_user_id or p.user.id)
    v_worker = body.verified_by_worker_id
    applier = pt.applied_by_user_id
    same = v_user is not None and v_user == applier
    if v_worker:
        w = db.get(Worker, v_worker)
        if w is None:
            raise validation_error("verified_by_worker_id", "Worker not found.")
        same = w.user_id is not None and w.user_id == applier
    if same:
        raise common.err(
            ErrorCode.VERIFIER_IS_APPLIER,
            "The verifier must be someone other than the person who applied the point (IS-4).",
            "يجب أن يكون المتحقق شخصاً غير من طبق العزل.",
        )
    if (
        pt.energy_type == EnergyType.electrical
        and body.verification_method != VerificationMethod.test_for_dead
    ):
        raise validation_error(
            "verification_method", "Electrical points are verified by test for dead (IS-4)."
        )
    if pt.energy_type in FLUID and body.verification_method not in FLUID_METHODS:
        raise validation_error(
            "verification_method", "Fluid points are verified by gauge or visual air gap (IS-4)."
        )
    if body.verified_at > now() + timedelta(minutes=2) or body.verified_at < pt.applied_at:
        raise validation_error(
            "verified_at", "Verification is after application and not in the future."
        )
    pt.verified_by_user_id = v_user
    pt.verified_by_worker_id = v_worker
    pt.verified_at = body.verified_at
    pt.verification_method = body.verification_method
    db.flush()
    _audit(
        db,
        p,
        c.project_id,
        EntityType.isolation_certificate,
        c.id,
        AuditAction.update,
        None,
        {"point_verified": pt.point_no, "method": body.verification_method.value},
    )
    if c.status == S.isolated and all(x.verified_at for x in points(db, c)) and _relocked(c):
        c.status = S.verified
        c.verified_at = c.verified_at or body.verified_at
        db.flush()
    _refresh_linked(db, c)
    return to_read(db, p, c)


def _relocked(c: IsolationCertificate) -> bool:
    """A certificate that was Verified before (re-lock after a lost lock) returns to Verified
    automatically once every point is verified again."""
    return c.verified_at is not None


def remove_point(
    db: Session, p: Principal, isolation_id: uuid.UUID, point_id: uuid.UUID, body: PointRemoveInput
) -> IsolationRead:
    c = get_cert(db, p, isolation_id)
    _require_92(p, c.project_id)
    if p.user.id != c.isolation_authority_user_id:
        raise forbidden_error("Points are removed by the certificate's isolation authority.")
    if c.status != S.deisolation_requested or c.deisolation_authorised_at is None:
        raise common.err(
            ErrorCode.TRANSITION_CONDITION_NOT_MET,
            "Points are removed after an issuer authorises the de-isolation (IS-7).",
            "تزال نقاط العزل بعد اعتماد مُصدِر التصريح لإعادة التشغيل.",
            status=409,
        )
    pt = _point(db, c, point_id)
    if pt.removed_at is not None:
        raise validation_error("point_id", "The point is already removed.")
    pt.removed_at = body.removed_at
    pt.removed_by_user_id = p.user.id
    lk = db.get(Lock, pt.isolation_lock_id) if pt.isolation_lock_id else None
    if lk and lk.status == LockStatus.applied:
        lk.status, lk.applied_on = LockStatus.available, None
    db.flush()
    _audit(
        db,
        p,
        c.project_id,
        EntityType.isolation_certificate,
        c.id,
        AuditAction.update,
        None,
        {"point_removed": pt.point_no},
    )
    if all(x.removed_at for x in points(db, c)):
        _deisolate(db, p, c)
    return to_read(db, p, c)


def _deisolate(db: Session, p: Principal | None, c: IsolationCertificate) -> None:
    c.status = S.deisolated
    c.deisolated_at = now()
    lb = db.get(Lock, c.lockbox_id)
    if lb and lb.applied_on == c.iso_no:
        lb.status, lb.applied_on = LockStatus.available, None
    db.flush()
    _audit(
        db,
        p,
        c.project_id,
        EntityType.isolation_certificate,
        c.id,
        AuditAction.status_change,
        {"status": "deisolation_requested"},
        {"status": "deisolated"},
    )


def transition(
    db: Session, p: Principal, isolation_id: uuid.UUID, body: IsolationTransition
) -> IsolationRead:
    c = get_cert(db, p, isolation_id)
    src, to = c.status, body.to_status
    allowed = {
        S.planned: {S.isolated, S.cancelled},
        S.isolated: {S.verified},
        S.verified: {S.deisolation_requested},
        S.deisolation_requested: {S.deisolated},
    }
    if to not in allowed.get(src, set()):
        raise invalid_transition("isolation", src, to)
    pts = points(db, c)
    at = now()
    if to == S.isolated:
        _require_92(p, c.project_id)
        if p.user.id != c.isolation_authority_user_id:
            raise forbidden_error("The isolation authority isolates the certificate.")
        missing = [
            x.point_no
            for x in pts
            if x.applied_at is None or x.isolation_lock_id is None or not x.tag_no
        ]
        if missing:
            raise common.err(
                ErrorCode.TRANSITION_CONDITION_NOT_MET,
                f"Points {missing} have no lock and tag yet (IS-3).",
                f"النقاط {missing} بدون قفل وبطاقة بعد.",
                status=409,
                meta={"points": missing},
            )
        c.isolated_at = at
    elif to == S.verified:
        p.ensure_writer()
        if (
            p.grant(c.project_id, C.isolation_manage) is None
            and p.grant(c.project_id, C.permit_receive) is None
        ):
            raise forbidden_error()
        missing = [x.point_no for x in pts if x.verified_at is None]
        if missing:
            raise common.err(
                ErrorCode.TRANSITION_CONDITION_NOT_MET,
                f"Points {missing} are not verified yet (IS-4).",
                f"النقاط {missing} غير متحقق منها بعد.",
                status=409,
                meta={"points": missing},
            )
        c.verified_at = max(x.verified_at for x in pts if x.verified_at)
    elif to == S.deisolation_requested:
        p.ensure_writer()
        if (
            p.grant(c.project_id, C.isolation_manage) is None
            and p.grant(c.project_id, C.permit_receive) is None
        ):
            raise forbidden_error()
        permits, locks = deisolation_blockers(db, c)
        if permits or locks:
            raise common.err(
                ErrorCode.DEISOLATION_BLOCKED,
                "De-isolation blocked: " + ", ".join([*permits, *locks]) + " (IS-7).",
                "إعادة التشغيل ممنوعة: " + "، ".join([*permits, *locks]),
                status=409,
                meta={"permits": permits, "locks": locks},
            )
        c.deisolation_requested_at = at
    elif to == S.deisolated:
        acommon.require_cap(p, c.project_id, C.deisolation_authorise)
        if not common.find_appointment(
            db,
            c.project_id,
            AppointmentFunction.issuer,
            [],
            None,
            [],
            [acommon.local_day(at)],
            user_id=p.user.id,
        ):
            raise common.err(
                ErrorCode.APPOINTMENT_INVALID,
                "De-isolation is authorised by an appointed issuer.",
                "يعتمد إعادة التشغيل مُصدِر معيَّن.",
            )
        if c.deisolation_authorised_at is None:
            c.deisolation_authorised_at = at
            c.deisolation_authorised_by_user_id = p.user.id
            _audit(
                db,
                p,
                c.project_id,
                EntityType.isolation_certificate,
                c.id,
                AuditAction.update,
                None,
                {"deisolation_authorised": True},
            )
        if not all(x.removed_at for x in pts):
            db.flush()
            notify.notify(
                db,
                [c.isolation_authority_user_id],
                NotificationKind.permit_update,
                f"{c.iso_no}: de-isolation authorised, remove the points",
                f"{c.iso_no}: تم اعتماد إعادة التشغيل، أزل نقاط العزل",
                None,
                None,
                EntityType.isolation_certificate,
                c.id,
                c.project_id,
            )
            return to_read(db, p, c)
        _deisolate(db, p, c)
        return to_read(db, p, c)
    elif to == S.cancelled:
        _require_92(p, c.project_id)
        if any(x.applied_at for x in pts):
            raise validation_error(
                "to_status", "Only a never-applied certificate can be cancelled."
            )
        c.cancelled_at = at
        lb = db.get(Lock, c.lockbox_id)
        if lb and lb.applied_on == c.iso_no:
            lb.status, lb.applied_on = LockStatus.available, None
    c.status = to
    c.updated_by_user_id = p.user.id
    db.flush()
    _audit(
        db,
        p,
        c.project_id,
        EntityType.isolation_certificate,
        c.id,
        AuditAction.status_change,
        {"status": src.value},
        {"status": to.value},
        {"comment": body.comment} if body.comment else None,
    )
    _refresh_linked(db, c)
    return to_read(db, p, c)


def _refresh_linked(db: Session, c: IsolationCertificate) -> None:
    from app.services.ptw import evaluation  # noqa: PLC0415

    for x in linked_permits(db, c):
        if x.status not in (PermitStatus.closed, PermitStatus.cancelled, PermitStatus.expired):
            evaluation.refresh(db, x)


def _breach(db: Session, c: IsolationCertificate, detail: str, ref: str) -> None:
    """IS-8 / IS-11: isolation_breach on every linked live permit."""
    from app.services.ptw import lifecycle  # noqa: PLC0415

    for x in linked_permits(db, c):
        if x.status in (PermitStatus.issued, PermitStatus.active):
            lifecycle.auto_suspend(db, x, StatusReason.isolation_breach, detail, ref)


def review(
    db: Session, p: Principal, isolation_id: uuid.UUID, body: LongTermReviewInput
) -> IsolationRead:
    c = get_cert(db, p, isolation_id)
    _require_92(p, c.project_id)
    if p.user.id != c.isolation_authority_user_id and not p.is_manager:
        raise forbidden_error("The weekly review is recorded by the isolation authority.")
    if c.status not in OPEN_STATUSES:
        raise invalid_transition("isolation", c.status, "review")
    c.reviews = [
        *(c.reviews or []),
        {
            "by": str(p.user.id),
            "at": now().isoformat(),
            "in_place": body.lock_tag_in_place,
            "note": body.note,
        },
    ]
    db.flush()
    _audit(
        db,
        p,
        c.project_id,
        EntityType.isolation_certificate,
        c.id,
        AuditAction.update,
        None,
        {"long_term_review": body.lock_tag_in_place},
    )
    if not body.lock_tag_in_place:
        _breach(db, c, f"{c.iso_no} weekly review: lock/tag not in place", c.iso_no)
    return to_read(db, p, c)


# ---- personal locks (IS-5, IS-9) -----------------------------------------------------------------


def list_personal(db: Session, p: Principal, isolation_id: uuid.UUID) -> PersonalLockList:
    c = get_cert(db, p, isolation_id)
    rows = db.scalars(
        select(PersonalLockEvent)
        .where(PersonalLockEvent.lockbox_id == c.lockbox_id)
        .order_by(PersonalLockEvent.applied_at.desc())
    )
    refs = Refs(db)
    return PersonalLockList(items=[event_read(db, p, e, refs) for e in rows])


def _worker_engagements(
    db: Session, worker_id: uuid.UUID, project_id: uuid.UUID
) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(Deployment.engagement_id).where(
                Deployment.worker_id == worker_id, Deployment.project_id == project_id
            )
        )
    )


def apply_personal(
    db: Session, p: Principal, isolation_id: uuid.UUID, body: PersonalLockApply
) -> PersonalLockEventRead:
    c = get_cert(db, p, isolation_id)
    permit = None
    if body.permit_id:
        permit = db.get(Permit, body.permit_id)
        if permit is None or c.id not in (permit.isolation_cert_ids or []):
            raise validation_error("permit_id", "The permit is not linked to this isolation.")
        acommon.require_cap(
            p, c.project_id, C.personal_lock_record, [permit.site_id], permit.engagement_id
        )
    else:
        acommon.require_cap(p, c.project_id, C.personal_lock_record)
    if c.status not in (S.isolated, S.verified):
        raise invalid_transition("isolation", c.status, "personal_lock")
    lk = db.get(Lock, body.lock_id)
    if (
        lk is None
        or lk.project_id != c.project_id
        or lk.lock_type != LockType.personal_lock
        or lk.status != LockStatus.available
    ):
        raise common.err(
            ErrorCode.LOCK_NOT_AVAILABLE,
            "Choose an available personal lock.",
            "اختر قفلاً شخصياً متاحاً.",
            field="lock_id",
        )
    if lk.holder_worker_id and lk.holder_worker_id != body.worker_id:
        raise common.err(
            ErrorCode.LOCK_NOT_AVAILABLE,
            f"{lk.lock_no} belongs to another worker (one holder, one key).",
            "القفل يخص عاملاً آخر.",
            field="lock_id",
        )
    w = db.get(Worker, body.worker_id)
    if w is None:
        raise validation_error("worker_id", "Worker not found.")
    if any(e.worker_id == w.id for e in active_personal_locks(db, c.lockbox_id)):
        raise duplicate("worker_id", "The worker already has a personal lock on this lockbox.")
    if body.applied_at > now() + timedelta(minutes=2):
        raise validation_error("applied_at", "The time cannot be in the future.")
    lb = db.get(Lock, c.lockbox_id)
    lk.holder_worker_id = w.id
    lk.status = LockStatus.applied
    lk.applied_on = lb.lock_no if lb else c.iso_no
    e = PersonalLockEvent(
        id=uuid.uuid4(),
        project_id=c.project_id,
        lock_id=lk.id,
        lockbox_id=c.lockbox_id,
        certificate_id=c.id,
        worker_id=w.id,
        permit_id=permit.id if permit else None,
        applied_at=body.applied_at,
        applied_by_user_id=p.user.id,
    )
    db.add(e)
    db.flush()
    _audit(
        db,
        p,
        c.project_id,
        EntityType.personal_lock_event,
        e.id,
        AuditAction.create,
        None,
        {"lock": lk.lock_no, "worker": w.worker_no},
    )
    if permit:
        from app.services.ptw import evaluation  # noqa: PLC0415

        evaluation.refresh(db, permit)
    return event_read(db, p, e)


def _event(
    db: Session, p: Principal, event_id: uuid.UUID
) -> tuple[PersonalLockEvent, IsolationCertificate | None]:
    e = db.get(PersonalLockEvent, event_id)
    if e is None:
        raise not_found("Personal lock event")
    common.view_grant(db, p, e.project_id)
    c = db.get(IsolationCertificate, e.certificate_id) if e.certificate_id else None
    return e, c


def _event_scope(db: Session, p: Principal, e: PersonalLockEvent) -> None:
    """Contractor-scoped holders of capability 93 act on events of their own permits / crew."""
    permit = db.get(Permit, e.permit_id) if e.permit_id else None
    if permit is not None:
        acommon.require_cap(
            p, e.project_id, C.personal_lock_record, [permit.site_id], permit.engagement_id
        )
        return
    g = p.grant(e.project_id, C.personal_lock_record)
    if g is not None and g.engagement_ids is None:
        acommon.require_cap(p, e.project_id, C.personal_lock_record)
        return
    from app.models import Deployment  # noqa: PLC0415

    engs = set(
        db.scalars(
            select(Deployment.engagement_id).where(
                Deployment.worker_id == e.worker_id, Deployment.project_id == e.project_id
            )
        )
    )
    for eng in engs:
        try:
            acommon.require_cap(p, e.project_id, C.personal_lock_record, None, eng)
            return
        except ApiError:
            continue
    acommon.require_cap(p, e.project_id, C.personal_lock_record)


def remove_personal(
    db: Session, p: Principal, event_id: uuid.UUID, body: PersonalLockRemove
) -> PersonalLockEventRead:
    e, _c = _event(db, p, event_id)
    _event_scope(db, p, e)
    if e.removed_at is not None:
        raise validation_error("event_id", "The lock is already removed.")
    if body.removed_at < e.applied_at or body.removed_at > now() + timedelta(minutes=2):
        raise validation_error("removed_at", "Removal is after application and not in the future.")
    e.removed_at = body.removed_at
    e.removed_by = PersonalLockRemoval.holder
    lk = db.get(Lock, e.lock_id)
    if lk:
        lk.status, lk.applied_on = LockStatus.available, None
    db.flush()
    _audit(
        db,
        p,
        e.project_id,
        EntityType.personal_lock_event,
        e.id,
        AuditAction.update,
        None,
        {"removed": "holder"},
    )
    _refresh_event_permit(db, e)
    return event_read(db, p, e)


def _refresh_event_permit(db: Session, e: PersonalLockEvent) -> None:
    permit = db.get(Permit, e.permit_id) if e.permit_id else None
    if permit and permit.status not in (
        PermitStatus.closed,
        PermitStatus.cancelled,
        PermitStatus.expired,
    ):
        from app.services.ptw import evaluation  # noqa: PLC0415

        evaluation.refresh(db, permit)


def cut(
    db: Session, p: Principal, event_id: uuid.UUID, body: LockCutInput
) -> PersonalLockEventRead:
    e, c = _event(db, p, event_id)
    p.ensure_writer()
    if p.grant(e.project_id, C.lock_cut_approve) is None:
        raise forbidden_error("A lock cut needs the HSE Manager's approval (capability 95).")
    if e.removed_at is not None:
        raise validation_error("event_id", "The lock is already removed.")
    if not (body.supervisor_worker_id or body.supervisor_user_id):
        raise validation_error(
            "supervisor_user_id", "Name the supervisor who confirmed the holder is not on site."
        )
    at = now()
    e.removed_at = at
    e.removed_by = PersonalLockRemoval.cut
    e.cut_record = {
        "approved_by_user_id": str(p.user.id),
        "supervisor_worker_id": str(body.supervisor_worker_id)
        if body.supervisor_worker_id
        else None,
        "supervisor_user_id": str(body.supervisor_user_id) if body.supervisor_user_id else None,
        "supervisor_confirmed_absent_at": body.supervisor_confirmed_absent_at.isoformat(),
        "contact_attempts": body.contact_attempts,
        "worker_informed_at": body.worker_informed_at.isoformat()
        if body.worker_informed_at
        else None,
        "cut_at": at.isoformat(),
    }
    lk = db.get(Lock, e.lock_id)
    if lk:
        lk.status = LockStatus.cut
        lk.applied_on = None
    db.flush()
    _audit(
        db,
        p,
        e.project_id,
        EntityType.personal_lock_event,
        e.id,
        AuditAction.update,
        None,
        {"removed": "cut"},
        {"contact_attempts": body.contact_attempts},
    )
    users = set(notify.managers(db)) | set(common.officers(db, e.project_id))
    for eng in _worker_engagements(db, e.worker_id, e.project_id):
        users |= set(contractor_reps(db, e.project_id, eng))
    lock_no = lk.lock_no if lk else ""
    notify.notify(
        db,
        users,
        NotificationKind.lock_cut,
        f"Personal lock {lock_no} cut ({c.iso_no if c else ''})",
        f"تم قطع القفل الشخصي {lock_no}",
        None,
        None,
        EntityType.personal_lock_event,
        e.id,
        e.project_id,
    )
    _refresh_event_permit(db, e)
    return event_read(db, p, e)


def worker_informed(
    db: Session, p: Principal, event_id: uuid.UUID, body: WorkerInformedInput
) -> PersonalLockEventRead:
    e, _c = _event(db, p, event_id)
    p.ensure_writer()
    if (
        p.grant(e.project_id, C.lock_cut_approve) is None
        and p.grant(e.project_id, C.personal_lock_record) is None
    ):
        raise forbidden_error()
    if not e.cut_record:
        raise validation_error("event_id", "The lock was not cut.")
    e.cut_record = {**e.cut_record, "worker_informed_at": body.worker_informed_at.isoformat()}
    db.flush()
    _audit(
        db,
        p,
        e.project_id,
        EntityType.personal_lock_event,
        e.id,
        AuditAction.update,
        None,
        {"worker_informed": True},
    )
    return event_read(db, p, e)


# ---- lock register -------------------------------------------------------------------------------


def list_locks(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    size: int,
    lock_types: list[LockType] | None,
    statuses: list[LockStatus] | None,
    holder_worker_id: uuid.UUID | None,
    q: str | None,
) -> LockPage:
    common.view_grant(db, p, project_id)
    stmt = select(Lock).where(Lock.project_id == project_id)
    if lock_types:
        stmt = stmt.where(Lock.lock_type.in_(lock_types))
    if statuses:
        stmt = stmt.where(Lock.status.in_(statuses))
    if holder_worker_id:
        stmt = stmt.where(Lock.holder_worker_id == holder_worker_id)
    if q:
        stmt = stmt.where(Lock.lock_no.ilike(f"%{q.strip()}%"))
    rows, total = paginate(db, stmt.order_by(Lock.lock_type, Lock.lock_no), page, size)
    return LockPage(
        items=[lock_read(db, p, lk) for lk in rows], total=total, page=page, page_size=size
    )


def next_lock_no(db: Session, project_id: uuid.UUID, t: LockType) -> str:
    prefix = f"{LOCK_PREFIX[t]}-{short_code(db, project_id)}-"
    nums = [0]
    for no in db.scalars(
        select(Lock.lock_no).where(Lock.project_id == project_id, Lock.lock_no.like(prefix + "%"))
    ):
        m = re.match(r"^\d+$", no[len(prefix) :])
        if m:
            nums.append(int(no[len(prefix) :]))
    width = 3 if t == LockType.lockbox else 4
    return f"{prefix}{max(nums) + 1:0{width}d}"


def create_lock(db: Session, p: Principal, project_id: uuid.UUID, body: LockCreate) -> LockRead:
    projects.get_visible(db, p, project_id)
    cap = C.personal_lock_record if body.lock_type == LockType.personal_lock else C.isolation_manage
    acommon.require_cap(p, project_id, cap)
    if body.holder_worker_id and body.lock_type != LockType.personal_lock:
        raise validation_error("holder_worker_id", "Only personal locks have a holder.")
    if body.holder_worker_id and db.get(Worker, body.holder_worker_id) is None:
        raise validation_error("holder_worker_id", "Worker not found.")
    no = body.lock_no or next_lock_no(db, project_id, body.lock_type)
    if db.scalar(select(Lock.id).where(Lock.project_id == project_id, Lock.lock_no == no)):
        raise duplicate("lock_no", "This lock number is already registered (IS-2).")
    lk = Lock(
        id=uuid.uuid4(),
        project_id=project_id,
        lock_no=no,
        lock_type=body.lock_type,
        holder_worker_id=body.holder_worker_id,
        status=LockStatus.available,
        created_by_user_id=p.user.id,
        updated_by_user_id=p.user.id,
    )
    db.add(lk)
    db.flush()
    _audit(
        db,
        p,
        project_id,
        EntityType.lock,
        lk.id,
        AuditAction.create,
        None,
        {"lock_no": no, "type": body.lock_type.value},
    )
    return lock_read(db, p, lk)


def _lock(db: Session, p: Principal, lock_id: uuid.UUID) -> Lock:
    lk = db.get(Lock, lock_id)
    if lk is None:
        raise not_found("Lock")
    common.view_grant(db, p, lk.project_id)
    return lk


def update_lock(db: Session, p: Principal, lock_id: uuid.UUID, body: LockUpdate) -> LockRead:
    lk = _lock(db, p, lock_id)
    acommon.require_cap(
        p,
        lk.project_id,
        C.personal_lock_record if lk.lock_type == LockType.personal_lock else C.isolation_manage,
    )
    if lk.lock_type != LockType.personal_lock:
        raise validation_error("holder_worker_id", "Only personal locks have a holder.")
    if lk.status == LockStatus.applied:
        raise validation_error("holder_worker_id", "Remove the lock before changing its holder.")
    before = str(lk.holder_worker_id) if lk.holder_worker_id else None
    if "holder_worker_id" in body.changes():
        if body.holder_worker_id and db.get(Worker, body.holder_worker_id) is None:
            raise validation_error("holder_worker_id", "Worker not found.")
        lk.holder_worker_id = body.holder_worker_id
    lk.updated_by_user_id = p.user.id
    db.flush()
    _audit(
        db,
        p,
        lk.project_id,
        EntityType.lock,
        lk.id,
        AuditAction.update,
        {"holder": before},
        {"holder": str(lk.holder_worker_id) if lk.holder_worker_id else None},
    )
    return lock_read(db, p, lk)


def report_lost(db: Session, p: Principal, lock_id: uuid.UUID, body: LockLostInput) -> LockRead:
    """IS-11: lost → the point loses its lock (re-lock needed); linked permits isolation_breach."""
    lk = _lock(db, p, lock_id)
    p.ensure_writer()
    if (
        p.grant(lk.project_id, C.isolation_manage) is None
        and p.grant(lk.project_id, C.personal_lock_record) is None
    ):
        raise forbidden_error()
    if lk.status in (LockStatus.lost, LockStatus.retired):
        raise validation_error("lock_id", f"The lock is already {lk.status.value}.")
    before = lk.status
    was_applied = before == LockStatus.applied
    lk.status = LockStatus.lost
    lk.lost_detail = body.detail
    db.flush()
    _audit(
        db,
        p,
        lk.project_id,
        EntityType.lock,
        lk.id,
        AuditAction.status_change,
        {"status": before.value},
        {"status": "lost"},
        {"detail": body.detail},
    )
    if was_applied:
        if lk.lock_type == LockType.isolation_lock:
            pt = db.scalars(
                select(IsolationPoint).where(
                    IsolationPoint.isolation_lock_id == lk.id, IsolationPoint.removed_at.is_(None)
                )
            ).first()
            if pt:
                c = db.get(IsolationCertificate, pt.certificate_id)
                if c:
                    _breach(
                        db,
                        c,
                        f"Lock {lk.lock_no} lost on {c.iso_no} point {pt.point_no}",
                        lk.lock_no,
                    )
                    _refresh_linked(db, c)
        elif lk.lock_type == LockType.personal_lock:
            e = db.scalars(
                select(PersonalLockEvent).where(
                    PersonalLockEvent.lock_id == lk.id, PersonalLockEvent.removed_at.is_(None)
                )
            ).first()
            if e:
                permit = db.get(Permit, e.permit_id) if e.permit_id else None
                if permit and permit.status in (PermitStatus.issued, PermitStatus.active):
                    from app.services.ptw import lifecycle  # noqa: PLC0415

                    lifecycle.auto_suspend(
                        db,
                        permit,
                        StatusReason.isolation_breach,
                        f"Personal lock {lk.lock_no} lost",
                        lk.lock_no,
                    )
                e.removed_at = now()
                e.removed_by = PersonalLockRemoval.holder
    return lock_read(db, p, lk)


# ---- jobs ----------------------------------------------------------------------------------------


def is_orphan(db: Session, c: IsolationCertificate, at: datetime) -> bool:
    """Applied with no live (or pending) permit for more than 24 h (§7, §8.3)."""
    if c.status not in OPEN_STATUSES:
        return False
    rows = linked_permits(db, c)
    pending = (
        PermitStatus.approved,
        PermitStatus.reviewed,
        PermitStatus.requested,
        PermitStatus.draft,
    )
    if any(x.status in PERMIT_LIVE or x.status in pending for x in rows):
        return False
    ended = [x.ended_at or x.closed_at for x in rows if x.status not in PERMIT_LIVE]
    since = max([e for e in ended if e] or [c.isolated_at or c.created_at])
    return at - since > timedelta(hours=24)


def review_due_at(db: Session, c: IsolationCertificate) -> datetime | None:
    return _review_due_at(db, c)


def daily_job(db: Session, at: datetime | None = None) -> int:
    """§7: long-term weekly review due / missed (+1 day → HSE Officer) and orphan isolations
    (no live permit > 24 h) daily."""
    at = at or now()
    day = acommon.local_day(at)
    n = 0
    for c in db.scalars(
        select(IsolationCertificate).where(IsolationCertificate.status.in_(list(OPEN_STATUSES)))
    ):
        sent = list(c.alerts_sent or [])
        due = _review_due_at(db, c)
        if due is not None and due <= at:
            key = f"review_{acommon.local_day(due).isoformat()}"
            if key not in sent:
                sent.append(key)
                notify.notify(
                    db,
                    [c.isolation_authority_user_id],
                    NotificationKind.isolation_review_due,
                    f"{c.iso_no} weekly long-term review due",
                    f"المراجعة الأسبوعية للعزل {c.iso_no} مستحقة",
                    None,
                    None,
                    EntityType.isolation_certificate,
                    c.id,
                    c.project_id,
                )
                n += 1
            missed = f"missed_{acommon.local_day(due).isoformat()}"
            if due + timedelta(days=1) <= at and missed not in sent:
                sent.append(missed)
                notify.notify(
                    db,
                    common.officers(db, c.project_id),
                    NotificationKind.isolation_review_due,
                    f"{c.iso_no} weekly review missed",
                    f"فاتت المراجعة الأسبوعية للعزل {c.iso_no}",
                    None,
                    None,
                    EntityType.isolation_certificate,
                    c.id,
                    c.project_id,
                )
        if is_orphan(db, c, at):
            key = f"orphan_{day.isoformat()}"
            if key not in sent:
                sent.append(key)
                users = {c.isolation_authority_user_id} | set(common.officers(db, c.project_id))
                for x in linked_permits(db, c):
                    if x.issuer_user_id:
                        users.add(x.issuer_user_id)
                notify.notify(
                    db,
                    users,
                    NotificationKind.isolation_orphan,
                    f"{c.iso_no} is applied with no live permit",
                    f"العزل {c.iso_no} مطبق دون تصريح ساري",
                    None,
                    None,
                    EntityType.isolation_certificate,
                    c.id,
                    c.project_id,
                )
        c.alerts_sent = sent
    db.flush()

    return n
