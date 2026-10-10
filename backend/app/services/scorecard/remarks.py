"""Comments and disputes on Issued scorecards (spec 6g §3.4, §4.2, DP-1…DP-5, P6g-4): the rep's
comment window, officers' internal comments, P1-8 / identity checks, resolution with a data
correction (the card recomputes, revision unchanged), metric exclusion (HSE Manager only),
rejection, withdrawal and the due / overdue alerts."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import String, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, EntityType, NotificationKind
from app.core.errors import ErrorCode, validation_error
from app.core.hse_enums import AttachmentOwner
from app.core.scorecard_enums import (
    ScCap,
    ScCardStatus,
    ScRemarkKind,
    ScRemarkStatus,
    ScResolution,
)
from app.db.base import Base
from app.models import Incident, ScCard, ScLine, ScRemark
from app.schemas.scorecard import ScRemarkCreate, ScRemarkPage, ScRemarkRead, ScRemarkResolve
from app.services.permissions import Principal, deny, forbidden_error
from app.services.scorecard import cards
from app.services.scorecard import common as cm

MAX_FILE = 10 * 1024 * 1024
TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
         ".jpeg": "image/jpeg"}  # fmt: skip


def _final_err() -> Exception:
    return cm.err(409, ErrorCode.SCORECARD_FINAL, "The scorecard is Final.", "البطاقة معتمدة.")


def _store(db: Session, card: ScCard, rid: uuid.UUID, f: Any, uid: uuid.UUID, i: int) -> uuid.UUID:
    from app.services import attachments  # noqa: PLC0415

    fld = f"files[{i}]"
    try:
        content = base64.b64decode(f.content_base64, validate=True)
    except ValueError as e:
        raise validation_error(fld, "The file is not valid base64.") from e
    if not content or len(content) > MAX_FILE:
        raise validation_error(fld, "Files must be between 1 byte and 10 MB.")
    ext = "." + f.file_name.rsplit(".", 1)[-1].lower() if "." in f.file_name else ""
    ctype = f.content_type or TYPES.get(ext)
    if ctype not in TYPES.values():
        raise validation_error(fld, "Use PDF, PNG or JPEG.")
    a = attachments.store(db, AttachmentOwner.sc_remark_file, rid, card.project_id, f.file_name,
                          content, str(ctype), uid)  # fmt: skip
    return a.id


def _identity(db: Session, card: ScCard, text: str) -> None:
    """P6g-4: names / ID numbers of injured persons of incidents attributed to the engagement."""
    from app.services.followup.common import check_identity  # noqa: PLC0415

    since = cm.add_months(card.month, -12)
    for inc_id in db.scalars(select(Incident.id).where(
            Incident.project_id == card.project_id,
            Incident.responsible_engagement_id == card.engagement_id,
            Incident.occurred_date >= since)):  # fmt: skip
        check_identity(db, inc_id, {"text": text})


def to_read(db: Session, r: ScRemark) -> ScRemarkRead:
    from app.services.followup.common import p18_warnings  # noqa: PLC0415

    card = db.get(ScCard, r.card_id)
    assert card is not None  # noqa: S101
    return ScRemarkRead(
        id=r.id, card_id=r.card_id, scorecard_no=card.scorecard_no,
        engagement_code=cm.eng_code(db, r.engagement_id), kind=r.kind, internal=r.internal,
        target_code=r.target_code, reason_code=r.reason_code, text=r.text,
        file_ids=list(r.file_ids or []), raised_by=cm.user_ref(db, r.raised_by_user_id),
        raised_at=r.raised_at, due_at=r.due_at, resolution=r.resolution,
        resolution_text=r.resolution_text, corrected_record_ref=r.corrected_record_ref,
        old_points=cm.s(r.old_points), new_points=cm.s(r.new_points),
        old_score=cm.s(r.old_score), new_score=cm.s(r.new_score),
        resolved_by=cm.user_ref(db, r.resolved_by_user_id), resolved_at=r.resolved_at,
        status=r.status, warnings=p18_warnings({"text": r.text}),
    )  # fmt: skip


def create(db: Session, p: Principal, card_id: uuid.UUID, body: ScRemarkCreate) -> ScRemarkRead:
    raw = db.get(ScCard, card_id)
    if raw is not None and p.can_see_project(raw.project_id) and not p.is_manager:
        g0 = p.grant(raw.project_id, cm.C.scorecard_comment)
        if g0 is None or not g0.covers_engagement(raw.engagement_id):
            raise forbidden_error("Commenting needs capability 227.")
    card = cards.get_card(db, p, card_id)
    g = p.grant(card.project_id, cm.C.scorecard_comment)
    if g is None or not g.covers_engagement(card.engagement_id):
        raise forbidden_error("Commenting needs capability 227.")
    staff = cm.staff(db, p, card.project_id)
    internal = staff and not p.is_manager
    if internal and body.kind == ScRemarkKind.dispute:
        raise forbidden_error("HSE Officers add internal comments only (227 P).")
    if card.status != ScCardStatus.issued:
        raise _final_err()
    t = now()
    if not staff and card.comment_until is not None and t > card.comment_until:
        raise cm.code_err(ErrorCode.COMMENT_WINDOW_CLOSED, "The comment window has closed (DP-1).",
                          "انتهت فترة الملاحظات.")  # fmt: skip
    text = cm.reason(body.text, 20, "text")
    target = body.target_code
    if (
        target is not None
        and target not in cm.METRIC_BY_CODE
        and target not in {c.value for c in ScCap}
    ):
        raise validation_error("target_code", "Name a metric (SM-…) or cap (CP-…) code.")
    if body.kind == ScRemarkKind.dispute:
        if target is None:
            raise validation_error("target_code", "A dispute names a line or a cap (DP-2).")
        if body.reason_code is None:
            raise validation_error("reason_code", "A dispute needs a reason code (DP-2).")
    _identity(db, card, text)
    days = int(cm.cfg(db, card.project_id)["dispute_resolution_days"])
    r = ScRemark(
        id=uuid.uuid4(), card_id=card.id, project_id=card.project_id,
        engagement_id=card.engagement_id, target_code=target, kind=body.kind, internal=internal,
        reason_code=body.reason_code if body.kind == ScRemarkKind.dispute else None, text=text,
        file_ids=[], warnings=[], raised_by_user_id=p.user.id, raised_at=t,
        due_at=cm.end_of_day(cm.local_day(t) + timedelta(days=days))
        if body.kind == ScRemarkKind.dispute else None,
        status=ScRemarkStatus.open if body.kind == ScRemarkKind.dispute
        else ScRemarkStatus.resolved,
        created_by_user_id=p.user.id,
    )  # fmt: skip
    db.add(r)
    db.flush()
    r.file_ids = [_store(db, card, r.id, f, p.user.id, i) for i, f in enumerate(body.files)]
    cm.record(db, p, AuditAction.create, EntityType.scorecard_remark, r, card.project_id)
    if body.kind == ScRemarkKind.dispute:
        cm.send(db, cm.officers(db, card.project_id) | cm.managers(db),
                NotificationKind.scorecard_dispute,
                f"{card.scorecard_no}: dispute on {target} ({r.reason_code}), due "
                f"{cm.local_day(r.due_at or t)}",
                f"{card.scorecard_no}: اعتراض على {target}", card.project_id,
                EntityType.scorecard_remark, r.id, email=True)  # fmt: skip
    db.flush()
    return to_read(db, r)


def _visible(db: Session, p: Principal, r: ScRemark) -> bool:
    card = db.get(ScCard, r.card_id)
    if card is None or not cards.visible(db, p, card) or cm.is_viewer(p, r.project_id):
        return False
    return not (r.internal and not cm.staff(db, p, r.project_id))


def _get(db: Session, p: Principal, remark_id: uuid.UUID) -> ScRemark:
    r = db.get(ScRemark, remark_id)
    if r is None or not _visible(db, p, r):
        raise deny(db, p, EntityType.scorecard_remark, remark_id, r.project_id if r else None,
                   "Remark")  # fmt: skip
    return r


def list_remarks(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    month: str | None,
    kind: ScRemarkKind | None,
    status: ScRemarkStatus | None,
    card_id: uuid.UUID | None,
    page: int,
    size: int,
) -> ScRemarkPage:
    cm.view_grant(db, p, project_id)
    if cm.is_viewer(p, project_id):
        raise forbidden_error("Disputes are not shown to Viewer / Client (RK-4).")
    stmt = select(ScRemark).where(ScRemark.project_id == project_id)
    if kind is not None:
        stmt = stmt.where(ScRemark.kind == kind)
    if status is not None:
        stmt = stmt.where(ScRemark.status == status)
    if card_id is not None:
        stmt = stmt.where(ScRemark.card_id == card_id)
    if month:
        m = cm.parse_month(month)
        stmt = stmt.where(
            ScRemark.card_id.in_(
                select(ScCard.id).where(ScCard.project_id == project_id, ScCard.month == m)
            )
        )
    rows = [r for r in db.scalars(stmt.order_by(ScRemark.raised_at.desc())) if _visible(db, p, r)]
    items = [to_read(db, r) for r in rows[(page - 1) * size : page * size]]
    return ScRemarkPage(items=items, total=len(rows), page=page, page_size=size)


def find_record(db: Session, project_id: uuid.UUID, ref: str) -> tuple[Any, str] | None:
    """DP-3: a record of any module by its reference (a string `ref` / `*_no` column)."""
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if not hasattr(cls, "updated_at"):
            continue
        for col in mapper.columns:
            name = col.key
            if not isinstance(col.type, String) or not (name == "ref" or name.endswith("_no")):
                continue
            stmt = select(cls).where(getattr(cls, name) == ref)
            if hasattr(cls, "project_id"):
                stmt = stmt.where(cls.project_id == project_id)
            obj = db.scalars(stmt.limit(1)).first()
            if obj is not None:
                return obj, cls.__name__
    return None


def _points(db: Session, card: ScCard, code: str | None) -> Decimal | None:
    if code is None or code not in cm.METRIC_BY_CODE:
        return None
    return db.scalar(select(ScLine.points).where(ScLine.card_id == card.id,
                                                 ScLine.metric_code == code))  # fmt: skip


def resolve(db: Session, p: Principal, remark_id: uuid.UUID, body: ScRemarkResolve) -> ScRemarkRead:
    r = _get(db, p, remark_id)
    p.require(r.project_id, cm.C.scorecard_resolve)
    if body.resolution == ScResolution.upheld_metric_excluded:
        cm.require_manager(p)
    if r.kind != ScRemarkKind.dispute or r.status != ScRemarkStatus.open:
        raise cm.err(409, ErrorCode.INVALID_TRANSITION, "Only an open dispute can be resolved.",
                     "يمكن البت في الاعتراضات المفتوحة فقط.")  # fmt: skip
    card = db.get(ScCard, r.card_id)
    assert card is not None  # noqa: S101
    if card.status != ScCardStatus.issued:
        raise _final_err()
    text = cm.reason(body.resolution_text, 20, "resolution_text")
    r.old_points, r.old_score = _points(db, card, r.target_code), card.score
    if body.resolution == ScResolution.upheld_data_corrected:
        ref = (body.corrected_record_ref or "").strip()
        if not ref:
            raise validation_error("corrected_record_ref", "Give the corrected record's ref.")
        hit = find_record(db, r.project_id, ref)
        upd = getattr(hit[0], "updated_at", None) if hit else None
        if hit is None or upd is None or upd <= r.raised_at:
            raise cm.code_err(ErrorCode.CORRECTION_NOT_FOUND,
                              "No record with that ref was changed after the dispute (DP-3).",
                              "لا يوجد سجل بهذا المرجع عُدّل بعد الاعتراض.",
                              "corrected_record_ref")  # fmt: skip
        r.corrected_record_ref = ref
        cards.recompute(db, card)
    elif body.resolution == ScResolution.upheld_metric_excluded:
        if r.target_code is None or r.target_code not in cm.METRIC_BY_CODE:
            raise cm.code_err(ErrorCode.CAP_NOT_EXCLUDABLE,
                              "Caps cannot be excluded; correct the data instead (DP-4).",
                              "لا يمكن استبعاد الحدود؛ صحّح البيانات.")  # fmt: skip
        card.excluded_metrics = sorted({*(card.excluded_metrics or []), r.target_code})
        cards.recompute(db, card)
    db.flush()
    r.new_points, r.new_score = _points(db, card, r.target_code), card.score
    r.resolution = body.resolution
    r.resolution_text = text
    r.resolved_by_user_id = p.user.id
    r.resolved_at = now()
    r.status = ScRemarkStatus.resolved
    r.updated_by_user_id = p.user.id
    cm.record(db, p, AuditAction.status_change, EntityType.scorecard_remark, r, r.project_id)
    cm.send(db, [r.raised_by_user_id], NotificationKind.scorecard_dispute,
            f"{card.scorecard_no}: your dispute on {r.target_code} was {body.resolution.value}",
            f"{card.scorecard_no}: تم البت في اعتراضك", r.project_id,
            EntityType.scorecard_remark, r.id, email=True)  # fmt: skip
    db.flush()
    return to_read(db, r)


def withdraw(db: Session, p: Principal, remark_id: uuid.UUID) -> ScRemarkRead:
    r = _get(db, p, remark_id)
    if r.raised_by_user_id != p.user.id:
        raise forbidden_error("Only the raiser withdraws a dispute.")
    if r.kind != ScRemarkKind.dispute or r.status != ScRemarkStatus.open:
        raise cm.err(409, ErrorCode.INVALID_TRANSITION, "Only an open dispute can be withdrawn.",
                     "يمكن سحب الاعتراضات المفتوحة فقط.")  # fmt: skip
    r.status = ScRemarkStatus.withdrawn
    r.resolved_at = now()
    cm.record(db, p, AuditAction.status_change, EntityType.scorecard_remark, r, r.project_id)
    db.flush()
    return to_read(db, r)


def daily(db: Session, t: datetime) -> int:
    """Dispute due (at due_at) and overdue (daily after) to the HSE Officers and the Manager."""
    n = 0
    today = cm.local_day(t)
    for r in db.scalars(
        select(ScRemark).where(
            ScRemark.kind == ScRemarkKind.dispute, ScRemark.status == ScRemarkStatus.open
        )
    ):
        if r.due_at is None or t < r.due_at - timedelta(hours=24):
            continue
        overdue = t > r.due_at
        key = f"sc_dispute:{r.id}:" + (str(today) if overdue else "due")
        if not cm.once(db, key):
            continue
        card = db.get(ScCard, r.card_id)
        no = card.scorecard_no if card else "?"
        word = "overdue" if overdue else "due"
        n += cm.send(db, cm.officers(db, r.project_id) | cm.managers(db),
                     NotificationKind.scorecard_dispute,
                     f"{no}: dispute on {r.target_code} {word} ({cm.local_day(r.due_at)})",
                     f"{no}: اعتراض مستحق البت", r.project_id, EntityType.scorecard_remark, r.id,
                     email=True)  # fmt: skip
    return n
