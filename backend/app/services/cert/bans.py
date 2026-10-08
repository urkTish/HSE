"""Certification bans (persons) and the blacklist / ban register (spec 4-third-party-cert §3.12,
§4.7, §8.4, BL-2, BL-4, BL-5, PC-11, P4-1, P4-4).

DECISIONS (Phase 4 #8): HSE Officers see ban details and the register like the HSE Manager;
only the HSE Manager (capability 115) bans and lifts. Contractor roles see the BL-5 "not
accepted" text without reasons."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cert_enums import (
    BanStatus,
    BlacklistSubject,
    ServiceStatus,
    TpiStatus,
)
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import not_found, validation_error
from app.kpi.periods import add_months
from app.models import (
    CertificationBan,
    Deployment,
    EquipmentBlacklistEvent,
    EquipmentItem,
    Tpi,
    Worker,
)
from app.schemas.personnel_certs import (
    NOT_ACCEPTED_AR,
    NOT_ACCEPTED_EN,
    BlacklistRegister,
    BlacklistRegisterRow,
    CertificationBanCreate,
    CertificationBanLift,
    CertificationBanPage,
    CertificationBanRead,
)
from app.services.access import common as acommon
from app.services.cert import alerts, events
from app.services.cert import common as cc
from app.services.cert import settings as cset
from app.services.common import invalid_transition, paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error

C = Capability


def hse_viewer(p: Principal) -> bool:
    """HSE Manager or an HSE Officer anywhere (decision 8)."""
    return p.is_manager or any(cc.is_hse(p, pid) for pid in p.projects)


def _worker_projects(db: Session, worker_id: uuid.UUID) -> set[uuid.UUID]:
    return set(db.scalars(select(Deployment.project_id).where(Deployment.worker_id == worker_id)))


def _visible_worker(db: Session, p: Principal, worker_id: uuid.UUID) -> bool:
    for dep in db.scalars(select(Deployment).where(Deployment.worker_id == worker_id)):
        g = p.grant(dep.project_id, C.personnel_cert_view)
        if g is not None and acommon.grant_covers(g, dep.site_ids, dep.engagement_id):
            return True
    return False


def ban_read(
    db: Session, p: Principal, b: CertificationBan, refs: Refs | None = None
) -> CertificationBanRead:
    refs = refs or Refs(db)
    w = db.get(Worker, b.worker_id)
    assert w is not None  # noqa: S101
    full = hse_viewer(p)
    names = full or any(acommon.can_see_names(p, pid) for pid in _worker_projects(db, b.worker_id))
    return CertificationBanRead(
        id=b.id,
        worker=acommon.worker_ref(w, names),
        scope_all=b.scope_all,
        cert_types=list(b.cert_types or []),
        reason_code=b.reason_code if full else None,
        reason_text=b.reason_text if full else None,
        from_date=b.from_date,
        review_due_on=b.review_due_on,
        status=b.status,
        message_en=NOT_ACCEPTED_EN,
        message_ar=NOT_ACCEPTED_AR,
        created_by=refs.user(b.created_by_user_id),
        lifted_at=b.lifted_at,
        lifted_by=refs.user(b.lifted_by_user_id),
        lift_reason=b.lift_reason if full else None,
        created_at=b.created_at,
    )


def _audit_read(db: Session, p: Principal, b: CertificationBan) -> None:
    from app.services import audit  # noqa: PLC0415

    if hse_viewer(p):
        audit.record(
            db,
            AuditAction.sensitive_field_read,
            p.actor(None),
            entity_type=EntityType.certification_ban,
            entity_id=b.id,
            fields_read=["ban_reason"],
        )


def get(db: Session, p: Principal, ban_id: uuid.UUID) -> CertificationBanRead:
    b = db.get(CertificationBan, ban_id)
    if b is None or not (hse_viewer(p) or _visible_worker(db, p, b.worker_id)):
        raise not_found("Ban")
    _audit_read(db, p, b)
    return ban_read(db, p, b)


def list_bans(
    db: Session,
    p: Principal,
    page: int,
    page_size: int,
    statuses: list[BanStatus] | None = None,
    worker_id: uuid.UUID | None = None,
    review_due: bool | None = None,
) -> CertificationBanPage:
    if not (hse_viewer(p) or p.has_any(C.personnel_cert_view)):
        raise forbidden_error()
    stmt = select(CertificationBan)
    if statuses:
        stmt = stmt.where(CertificationBan.status.in_(statuses))
    if worker_id:
        stmt = stmt.where(CertificationBan.worker_id == worker_id)
    if review_due is not None:
        cond = (CertificationBan.status == BanStatus.active) & (
            CertificationBan.review_due_on <= today()
        )
        stmt = stmt.where(cond if review_due else ~cond)
    stmt = stmt.order_by(CertificationBan.from_date.desc())
    refs = Refs(db)
    if hse_viewer(p):
        rows, total = paginate(db, stmt, page, page_size)
        items = [ban_read(db, p, b, refs) for b in rows]
    else:
        vis = [b for b in db.scalars(stmt) if _visible_worker(db, p, b.worker_id)]
        total = len(vis)
        items = [ban_read(db, p, b, refs) for b in vis[(page - 1) * page_size : page * page_size]]
    return CertificationBanPage(items=items, total=total, page=page, page_size=page_size)


def _review_months(db: Session, worker_id: uuid.UUID) -> int:
    pids = sorted(_worker_projects(db, worker_id))
    return cset.get(db, pids[0]).ban_review_months if pids else 6


def _alert(db: Session, b: CertificationBan, w: Worker, lifted: bool) -> None:
    """BL-2: HSE Officers of every project where the person is deployed (+ BL-5 text to the
    contractor HSE Reps)."""
    verb_en, verb_ar = ("lifted", "رُفع") if lifted else ("recorded", "سُجّل")
    for dep in db.scalars(select(Deployment).where(Deployment.worker_id == w.id)):
        alerts.send(
            db,
            alerts.officers(db, dep.project_id),
            NotificationKind.blacklist_changed,
            f"Certification ban {verb_en}: {w.worker_no}",
            f"{verb_ar} حظر الشهادات: {w.worker_no}",
            EntityType.certification_ban,
            b.id,
            dep.project_id,
            email=True,
        )
        if not lifted:
            alerts.send(
                db,
                alerts.reps(db, dep.project_id, dep.engagement_id),
                NotificationKind.blacklist_changed,
                f"{w.worker_no}: {NOT_ACCEPTED_EN}",
                f"{w.worker_no}: {NOT_ACCEPTED_AR}",
                EntityType.worker,
                w.id,
                dep.project_id,
                email=True,
            )


def create(db: Session, p: Principal, body: CertificationBanCreate) -> CertificationBanRead:
    p.require_any(C.cert_blacklist)
    w = db.get(Worker, body.worker_id)
    if w is None:
        raise not_found("Worker")
    if not body.scope_all:
        if not body.cert_types:
            raise validation_error("cert_types", "List the certificate types, or ban all types.")
        for t in body.cert_types:
            if not cset.is_type(db, t):
                raise validation_error("cert_types", f"Unknown certificate type {t}.")
    if body.from_date > today():
        raise validation_error("from_date", "Cannot be in the future.")
    b = CertificationBan(
        id=uuid.uuid4(),
        worker_id=w.id,
        scope_all=body.scope_all,
        cert_types=[] if body.scope_all else list(dict.fromkeys(body.cert_types)),
        reason_code=body.reason_code,
        reason_text=body.reason_text.strip(),
        from_date=body.from_date,
        review_due_on=add_months(body.from_date, _review_months(db, w.id)),
        status=BanStatus.active,
        alerts_sent=[],
    )
    cc.stamp(b, p, create=True)
    db.add(b)
    db.flush()
    cc.record(db, p, AuditAction.create, EntityType.certification_ban, b, None)
    _alert(db, b, w, False)
    events.publish(db, "holder.ban_changed", worker_ids=[w.id])
    return ban_read(db, p, b)


def lift(
    db: Session, p: Principal, ban_id: uuid.UUID, body: CertificationBanLift
) -> CertificationBanRead:
    p.require_any(C.cert_blacklist)
    b = db.get(CertificationBan, ban_id)
    if b is None:
        raise not_found("Ban")
    if b.status != BanStatus.active:
        raise invalid_transition("Ban", b.status.value, BanStatus.lifted.value)
    before = cc.snap(b)
    b.status = BanStatus.lifted
    b.lifted_at = now()
    b.lifted_by_user_id = p.user.id
    b.lift_reason = body.reason.strip()
    cc.stamp(b, p)
    db.flush()
    cc.record(db, p, AuditAction.status_change, EntityType.certification_ban, b, None, before)
    w = db.get(Worker, b.worker_id)
    if w is not None:
        _alert(db, b, w, True)
    events.publish(db, "holder.ban_changed", worker_ids=[b.worker_id])
    return ban_read(db, p, b)


def review_job(db: Session, d: date | None = None) -> int:
    """BL-4: review_due_on reminder to the HSE Manager (once)."""
    d = d or today()
    n = 0
    for b in db.scalars(
        select(CertificationBan).where(
            CertificationBan.status == BanStatus.active, CertificationBan.review_due_on <= d
        )
    ):
        if "review" in (b.alerts_sent or []):
            continue
        w = db.get(Worker, b.worker_id)
        alerts.send(
            db,
            alerts.managers(db),
            NotificationKind.ban_review_due,
            f"Certification ban review due: {w.worker_no if w else ''}",
            f"موعد مراجعة حظر الشهادات: {w.worker_no if w else ''}",
            EntityType.certification_ban,
            b.id,
            None,
        )
        b.alerts_sent = [*(b.alerts_sent or []), "review"]
        n += 1
    return n


# ---- register (§8.4) -----------------------------------------------------------------------------


def register(
    db: Session,
    p: Principal,
    subjects: list[BlacklistSubject] | None = None,
    project_id: uuid.UUID | None = None,
    active_only: bool = True,
) -> BlacklistRegister:
    full = hse_viewer(p)
    if not full and not (p.has_any(C.cert_register_view) or p.has_any(C.personnel_cert_view)):
        raise forbidden_error()
    want = set(subjects or list(BlacklistSubject))
    rows: list[BlacklistRegisterRow] = []
    if BlacklistSubject.equipment in want:
        stmt = select(EquipmentBlacklistEvent).order_by(EquipmentBlacklistEvent.from_date.desc())
        if active_only:
            stmt = stmt.where(EquipmentBlacklistEvent.lifted_at.is_(None))
        for ev in db.scalars(stmt):
            item = db.get(EquipmentItem, ev.equipment_id)
            if item is None:
                continue
            from app.services.cert import equipment as esvc  # noqa: PLC0415

            pids = sorted({d.project_id for d in esvc.deployments(db, item.id)})
            if project_id and project_id not in pids:
                continue
            if not full and not esvc.can_see(db, p, item):
                continue
            rows.append(
                BlacklistRegisterRow(
                    subject=BlacklistSubject.equipment,
                    subject_id=item.id,
                    ref=item.equipment_no,
                    label_en=f"{item.manufacturer} {item.model} SN {item.serial_no}",
                    label_ar=f"{item.manufacturer} {item.model} رقم {item.serial_no}",
                    reason_code=ev.reason_code.value if full else None,
                    from_date=ev.from_date,
                    review_due_on=None,
                    status="blacklisted"
                    if ev.lifted_at is None and item.service_status == ServiceStatus.blacklisted
                    else "lifted",
                    project_ids=pids,
                )
            )
    if BlacklistSubject.person in want:
        bstmt = select(CertificationBan).order_by(CertificationBan.from_date.desc())
        if active_only:
            bstmt = bstmt.where(CertificationBan.status == BanStatus.active)
        for b in db.scalars(bstmt):
            pids = sorted(_worker_projects(db, b.worker_id))
            if project_id and project_id not in pids:
                continue
            if not full and not _visible_worker(db, p, b.worker_id):
                continue
            w = db.get(Worker, b.worker_id)
            if w is None:
                continue
            names = full or any(acommon.can_see_names(p, pid) for pid in pids)
            rows.append(
                BlacklistRegisterRow(
                    subject=BlacklistSubject.person,
                    subject_id=w.id,
                    ref=w.worker_no,
                    label_en=w.full_name_en if names else w.worker_no,
                    label_ar=w.full_name_ar if names else w.worker_no,
                    reason_code=b.reason_code.value if full else None,
                    from_date=b.from_date,
                    review_due_on=b.review_due_on if full else None,
                    status=b.status.value,
                    project_ids=pids,
                )
            )
    if BlacklistSubject.tpi in want:
        tstmt = select(Tpi).order_by(Tpi.tpi_code)
        if active_only:
            tstmt = tstmt.where(Tpi.status == TpiStatus.blacklisted)
        else:
            tstmt = tstmt.where(Tpi.blacklisted_on.is_not(None))
        for t in db.scalars(tstmt):
            rows.append(
                BlacklistRegisterRow(
                    subject=BlacklistSubject.tpi,
                    subject_id=t.id,
                    ref=t.tpi_code,
                    label_en=t.legal_name_en,
                    label_ar=t.legal_name_ar,
                    reason_code=(t.blacklist_scope.value if t.blacklist_scope else None)
                    if full
                    else None,
                    from_date=t.blacklisted_on or t.blacklist_from or today(),
                    review_due_on=None,
                    status=t.status.value
                    if full
                    else ("blacklisted" if t.status == TpiStatus.blacklisted else "not_accepted"),
                    project_ids=[],
                )
            )
    return BlacklistRegister(items=rows)
