"""Quality alerts (spec 8-quality §A.10.2, Q-OBS-03…05): draft (242) → issued (RPM
`quality_alert.issue`, number assigned, distribution notified in-app and by email) → expired
(System, after valid_until) · withdrawn (239, reason). With `ack_required` each member
acknowledges once (275, idempotent); members who have not acknowledged after 3 days are reminded
once. A `stop_use` alert shows a red banner on the Quality home of its sites; alerts block nothing
else (Q-OBS-05)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, Role
from app.core.errors import not_found
from app.core.quality.common import QAlertSeverity, QAlertStatus, QRecordType
from app.models import Project, RoleAssignment
from app.models.quality import QAlert, QAlertAck, QPosition, QPositionHolder
from app.services import audit
from app.services.common import invalid_transition, paginate
from app.services.hse_common import id_warnings
from app.services.permissions import Principal, deny, forbidden_error
from app.services.quality import common as qc
from app.services.quality import numbering, rpm, signoff

C = Capability
AS = QAlertStatus
RT = QRecordType.quality_alert
FIELDS = (
    "title_en",
    "title_ar",
    "message_en",
    "message_ar",
    "applies_to",
    "site_ids",
    "supplier_ids",
    "lot_refs",
    "valid_until",
    "dist_roles",
    "dist_positions",
    "dist_engagement_ids",
    "dist_user_ids",
    "ack_required",
)


def can_view(p: Principal, a: QAlert) -> bool:
    if a.status == AS.draft:
        return p.user.id == a.created_by_user_id or p.grant(a.project_id, C.ncr_manage) is not None
    return p.user.id in (a.recipients or []) or p.grant(a.project_id, C.quality_view) is not None


def get_alert(db: Session, p: Principal, alert_id: uuid.UUID) -> QAlert:
    a = db.get(QAlert, alert_id)
    if a is None or not p.can_see_project(a.project_id) or not can_view(p, a):
        raise deny(
            db,
            p,
            EntityType.q_quality_alert,
            alert_id,
            a.project_id if a else None,
            "Quality alert",
        )
    return a


def _acks(db: Session, a: QAlert) -> list[QAlertAck]:
    return list(db.scalars(select(QAlertAck).where(QAlertAck.alert_id == a.id)))


def read(db: Session, p: Principal, a: QAlert) -> dict[str, Any]:
    acks = _acks(db, a)
    acked = {x.user_id for x in acks}
    n = len(a.recipients or [])
    return {
        "id": a.id,
        "project_id": a.project_id,
        "alert_no": a.alert_no,
        **{k: getattr(a, k) for k in FIELDS},
        "severity": a.severity,
        "status": a.status,
        "status_reason": a.status_reason,
        "issued_at": a.issued_at,
        "recipient_count": n,
        "ack_count": len(acked),
        "ack_pct": f"{(len(acked) / n * 100):.1f}" if n and a.ack_required else None,
        "i_am_recipient": p.user.id in (a.recipients or []),
        "i_acked": p.user.id in acked,
        "can_ack": a.status == AS.issued
        and a.ack_required
        and p.user.id in (a.recipients or [])
        and p.user.id not in acked,
    }


def _check(db: Session, project: Project, a: QAlert) -> None:
    from app.models import Site  # noqa: PLC0415

    for sid in a.site_ids or []:
        s = db.get(Site, sid)
        if s is None or s.project_id != project.id:
            raise qc.field_err("site_ids", "Every site must belong to the project.")
    for r in a.dist_roles or []:
        Role(r)


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    qc.require_profile(db, project)
    p.require(project.id, C.ncr_manage)
    a = QAlert(
        project_id=project.id,
        severity=QAlertSeverity(body["severity"]),
        status=AS.draft,
        created_by_user_id=p.user.id,
        recipients=[],
        alerts_sent=[],
    )
    for k in FIELDS:
        if k in body and body[k] is not None:
            setattr(a, k, body[k])
    _check(db, project, a)
    db.add(a)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.q_quality_alert,
        entity_id=a.id,
        project_id=project.id,
        after={"title": a.title_en, "severity": a.severity},
    )
    out = read(db, p, a)
    out["warnings"] = [
        w.model_dump() for w in id_warnings(message_en=a.message_en, message_ar=a.message_ar)
    ]
    return out


def update(db: Session, p: Principal, alert_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    a = get_alert(db, p, alert_id)
    project = qc.get_project(db, p, a.project_id)
    qc.writable(project, p)
    p.require(project.id, C.ncr_manage)
    if a.status != AS.draft:
        raise invalid_transition("Quality alert", a.status, "edited")
    for k in FIELDS:
        if k in body:
            setattr(a, k, body[k])
    if body.get("severity"):
        a.severity = QAlertSeverity(body["severity"])
    _check(db, project, a)
    db.flush()
    return read(db, p, a)


def recipients(db: Session, project: Project, a: QAlert) -> list[uuid.UUID]:
    day = qc.project_day(project)
    out: set[uuid.UUID] = set(a.dist_user_ids or [])
    rows = db.scalars(
        select(RoleAssignment).where(
            RoleAssignment.project_id == project.id, RoleAssignment.revoked_at.is_(None)
        )
    )
    for ra in rows:
        if not ra.is_active_on(day):
            continue
        if ra.role.value in (a.dist_roles or []):
            if a.site_ids and ra.site_ids and not set(ra.site_ids) & set(a.site_ids):
                continue
            out.add(ra.user_id)
        if ra.contractor_engagement_id and ra.contractor_engagement_id in (
            a.dist_engagement_ids or []
        ):
            out.add(ra.user_id)
    for code in a.dist_positions or []:
        pos = db.scalar(
            select(QPosition).where(QPosition.project_id == project.id, QPosition.code == code)
        )
        if pos is None:
            continue
        for h in db.scalars(select(QPositionHolder).where(QPositionHolder.position_id == pos.id)):
            if h.valid_from <= day and (h.valid_to is None or h.valid_to >= day):
                out.add(h.user_id)
    return sorted(out)


def issue(db: Session, p: Principal, alert_id: uuid.UUID, comment: str | None) -> dict[str, Any]:
    a = get_alert(db, p, alert_id)
    project = qc.get_project(db, p, a.project_id)
    qc.writable(project, p)
    if a.status != AS.draft:
        raise invalid_transition("Quality alert", a.status, AS.issued)
    if not (a.title_en and a.title_ar and a.message_en and a.message_ar):
        raise qc.field_err("message_ar", "EN and AR title and message are required to issue.")
    ctx = rpm.Ctx(None, None, qc.ids(a.created_by_user_id))
    rule, capacity = rpm.check_signer(db, p, project, RT, "issue", ctx, record_id=a.id)
    who = recipients(db, project, a)
    if not who:
        raise qc.field_err("dist_roles", "The distribution has no members on the project.")
    signoff.sign(db, p, project, RT, a.id, "issue", "approved", comment, rule, capacity)
    a.alert_no = numbering.assign(db, project, RT)
    a.status = AS.issued
    a.issued_at = now()
    a.issued_by_user_id = p.user.id
    a.recipients = who
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(project.id),
        entity_type=EntityType.q_quality_alert,
        entity_id=a.id,
        project_id=project.id,
        before={"status": AS.draft},
        after={"status": AS.issued},
        details={"recipients": len(who)},
    )
    qc.send(
        db,
        who,
        f"Quality alert {a.alert_no}: {a.title_en}",
        f"تنبيه جودة {a.alert_no}: {a.title_ar}",
        body_en=a.message_en,
        body_ar=a.message_ar,
        entity_type=EntityType.q_quality_alert,
        entity_id=a.id,
        project_id=project.id,
        key=f"alert_issued:{a.id}",
        path=f"/quality/alerts/{a.id}",
    )
    return read(db, p, a)


def ack(db: Session, p: Principal, alert_id: uuid.UUID) -> dict[str, Any]:
    a = get_alert(db, p, alert_id)
    project = qc.get_project(db, p, a.project_id)
    p.ensure_writer()
    if a.status != AS.issued or not a.ack_required:
        raise invalid_transition("Quality alert", a.status, "acknowledged")
    if p.user.id not in (a.recipients or []):
        raise forbidden_error("Only members of the distribution acknowledge the alert.")
    p.require(project.id, C.quality_acknowledge)
    exists = db.scalar(
        select(QAlertAck).where(QAlertAck.alert_id == a.id, QAlertAck.user_id == p.user.id)
    )
    if exists is None:  # Q-OBS-04: idempotent
        db.add(QAlertAck(alert_id=a.id, user_id=p.user.id, acked_at=now()))
        db.flush()
        audit.record(
            db,
            AuditAction.update,
            p.actor(project.id),
            entity_type=EntityType.q_quality_alert,
            entity_id=a.id,
            project_id=project.id,
            details={"acknowledged": True},
        )
    return read(db, p, a)


def withdraw(db: Session, p: Principal, alert_id: uuid.UUID, why: str | None) -> dict[str, Any]:
    a = get_alert(db, p, alert_id)
    project = qc.get_project(db, p, a.project_id)
    qc.writable(project, p)
    p.require(project.id, C.quality_settings)
    if a.status not in (AS.draft, AS.issued):
        raise invalid_transition("Quality alert", a.status, AS.withdrawn)
    src = a.status
    a.status = AS.withdrawn
    a.status_reason = qc.reason(why, 20)
    db.flush()
    audit.record(
        db,
        AuditAction.status_change,
        p.actor(project.id),
        entity_type=EntityType.q_quality_alert,
        entity_id=a.id,
        project_id=project.id,
        before={"status": src},
        after={"status": AS.withdrawn},
    )
    return read(db, p, a)


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    statuses: list[QAlertStatus] | None = None,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    stmt = select(QAlert).where(QAlert.project_id == project.id)
    if statuses:
        stmt = stmt.where(QAlert.status.in_(statuses))
    if p.grant(project.id, C.quality_view) is None:
        stmt = stmt.where(QAlert.recipients.contains([p.user.id]))
    rows = [a for a in db.scalars(stmt.order_by(QAlert.created_at.desc())) if can_view(p, a)]
    total = len(rows)
    rows = rows[(page - 1) * page_size : page * page_size]
    _ = paginate
    return {
        "items": [read(db, p, a) for a in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def banners(db: Session, p: Principal, project: Project, day: date) -> list[dict[str, Any]]:
    """Q-OBS-03: issued stop_use alerts of the user's sites, until expiry."""
    g = p.grant(project.id, C.quality_view)
    out = []
    for a in db.scalars(
        select(QAlert).where(
            QAlert.project_id == project.id,
            QAlert.status == AS.issued,
            QAlert.severity == QAlertSeverity.stop_use,
        )
    ):
        if a.valid_until is not None and a.valid_until < day:
            continue
        mine = p.user.id in (a.recipients or [])
        if not mine and g is None:
            continue
        if (
            a.site_ids
            and g is not None
            and g.site_ids is not None
            and not mine
            and not set(g.site_ids) & set(a.site_ids)
        ):
            continue
        out.append(
            {
                "id": a.id,
                "alert_no": a.alert_no,
                "title_en": a.title_en,
                "title_ar": a.title_ar,
                "valid_until": a.valid_until,
            }
        )
    return out


# ---- jobs ----------------------------------------------------------------------------------------


def expire(db: Session, at: datetime) -> int:
    n = 0
    for a in db.scalars(select(QAlert).where(QAlert.status == AS.issued)):
        project = db.get(Project, a.project_id)
        if project is None or a.valid_until is None:
            continue
        if a.valid_until < qc.project_day(project, at):
            a.status = AS.expired
            audit.record(
                db,
                AuditAction.status_change,
                audit.SYSTEM,
                entity_type=EntityType.q_quality_alert,
                entity_id=a.id,
                project_id=a.project_id,
                before={"status": AS.issued},
                after={"status": AS.expired},
            )
            n += 1
    db.flush()
    return n


def remind(db: Session, at: datetime) -> int:
    """Members who have not acknowledged after 3 days get one reminder."""
    sent = 0
    for a in db.scalars(
        select(QAlert).where(QAlert.status == AS.issued, QAlert.ack_required.is_(True))
    ):
        if a.issued_at is None or at < a.issued_at + timedelta(days=3):
            continue
        acked = {x.user_id for x in _acks(db, a)}
        todo = [u for u in a.recipients or [] if u not in acked]
        sent += qc.send(
            db,
            todo,
            f"Reminder: acknowledge quality alert {a.alert_no}",
            f"تذكير: أقرّ بالاطلاع على تنبيه الجودة {a.alert_no}",
            entity_type=EntityType.q_quality_alert,
            entity_id=a.id,
            project_id=a.project_id,
            key=f"alert_reminder:{a.id}",
            path=f"/quality/alerts/{a.id}",
        )
    return sent


def get_row(db: Session, alert_id: uuid.UUID) -> QAlert:
    a = db.get(QAlert, alert_id)
    if a is None:
        raise not_found("Quality alert")
    return a
