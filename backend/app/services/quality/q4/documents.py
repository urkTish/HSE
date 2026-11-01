"""Document control, light (spec 8-quality §E.1, Q-DOC-01…08): controlled documents with
revisions (draft → for review → approved → superseded / obsolete), review and approval sign-offs
through the responsible-person matrix (`document.review`, `document.approve`), distribution and
read-and-acknowledge tasks, review dates, citations through `q_links` ("newer revision
available") and transmittals with an EN / AR cover sheet sent through the email outbox.

Revision codes (Q-DOC-01, D-361): a draft is lettered A, B, … (a revision returned for comments
comes back as the next letter); on approval it takes the next number (0, 1, … with
`letters_then_numbers`; 1, 2, … with `numbers`). Not an EDMS (Q-DOC-08)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Language, Role
from app.core.errors import ErrorCode, not_found
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import QLinkKind, QProfileScope, QRecordType, QSignoffChannel
from app.core.quality.q4 import (
    DOC_PREFIX,
    DOC_TYPE_LABELS,
    QDocType,
    QResponseCode,
    QRevisionScheme,
    QRevStatus,
    QTransmittalItemKind,
    QTransmittalMethod,
    QTransmittalStatus,
    QTransmittalTo,
)
from app.models import Attachment, EmailMessage, Project, ProjectEngagement, RoleAssignment
from app.models.quality import QCustomer, QLink, QPosition, QPositionHolder, QSignoff, QSupplier
from app.models.quality.q4 import (
    QDocAck,
    QDocDistribution,
    QDocument,
    QDocumentRevision,
    QTransmittal,
    QTransmittalItem,
)
from app.services import attachments
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import registry as reg
from app.services.quality import rpm
from app.services.quality.q4 import base as b
from app.services.scorecard import render

C = b.C
RT = QRecordType
RS = QRevStatus
OPEN_REV = (RS.draft, RS.for_review)
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _immutable() -> Any:
    return qc.err(
        409,
        ErrorCode.DOCUMENT_IMMUTABLE,
        "An approved revision cannot be changed; start a new revision.",
        "لا يمكن تعديل مراجعة معتمدة؛ ابدأ مراجعة جديدة.",
    )


# ---- reads ---------------------------------------------------------------------------------------


def _get(db: Session, p: Principal, doc_id: uuid.UUID) -> QDocument:
    d = db.get(QDocument, doc_id)
    if d is None or not p.can_see_project(d.project_id) or not _can_view(db, p, d):
        raise not_found("Document")
    return d


def _can_view(db: Session, p: Principal, d: QDocument) -> bool:
    g = p.grant(d.project_id, C.quality_view)
    if g is not None and g.scope != b.S.responsible:
        return True
    if p.grant(d.project_id, C.document_author) is not None:
        return True
    # distribution members (275) and responsible persons of a pending step (N)
    if db.scalar(
        select(QDocAck.id)
        .join(QDocumentRevision, QDocumentRevision.id == QDocAck.revision_id)
        .where(QDocumentRevision.document_id == d.id, QDocAck.user_id == p.user.id)
        .limit(1)
    ):
        return True
    project = db.get(Project, d.project_id)
    rev = _open_revision(db, d)
    if project is None or rev is None:
        return False
    for step in ("review", "approve"):
        if rpm.resolves(
            db, p, project, RT.document, step, _ctx(rev), record_id=d.id, can_act=False
        ):
            return True
    return False


def _get_rev(db: Session, p: Principal, rev_id: uuid.UUID) -> tuple[QDocumentRevision, QDocument]:
    r = db.get(QDocumentRevision, rev_id)
    if r is None:
        raise not_found("Document revision")
    return r, _get(db, p, r.document_id)


def _open_revision(db: Session, d: QDocument) -> QDocumentRevision | None:
    return db.scalar(
        select(QDocumentRevision)
        .where(QDocumentRevision.document_id == d.id, QDocumentRevision.status.in_(OPEN_REV))
        .limit(1)
    )


def _revisions(db: Session, d: QDocument) -> list[QDocumentRevision]:
    return list(
        db.scalars(
            select(QDocumentRevision)
            .where(QDocumentRevision.document_id == d.id)
            .order_by(QDocumentRevision.rev_index)
        )
    )


def _ctx(r: QDocumentRevision) -> rpm.Ctx:
    return rpm.Ctx(requesters=frozenset(qc.ids(r.author_user_id, r.created_by_user_id)))


def ack_stats(db: Session, rev_id: uuid.UUID) -> dict[str, int | str | None]:
    total, done = db.execute(
        select(func.count(QDocAck.id), func.count(QDocAck.acked_at)).where(
            QDocAck.revision_id == rev_id
        )
    ).one()
    return {"required": int(total), "acked": int(done), "pct": str(b.pct(done, total) or "")}


def _signoffs(db: Session, d: QDocument, r: QDocumentRevision, hide: bool) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(QSignoff)
        .where(QSignoff.record_type == RT.document.value, QSignoff.record_id == r.id)
        .order_by(QSignoff.signed_at)
    )
    return [
        {
            "step": s.step,
            "decision": s.decision,
            "comment": s.comment,
            "signed_at": s.signed_at,
            "signed_by": b.user_ref(db, s.signed_by_user_id, hide),
            "channel": s.channel.value if isinstance(s.channel, QSignoffChannel) else s.channel,
        }
        for s in rows
    ]


def rev_read(db: Session, d: QDocument, r: QDocumentRevision, hide: bool) -> dict[str, Any]:
    return {
        "id": r.id,
        "document_id": d.id,
        "rev_code": r.rev_code,
        "status": r.status,
        "file_attachment_id": r.file_attachment_id,
        "source_attachment_id": r.source_attachment_id,
        "change_summary": r.change_summary,
        "effective_date": r.effective_date,
        "author": b.user_ref(db, r.author_user_id, hide),
        "submitted_at": r.submitted_at,
        "approved_at": r.approved_at,
        "approved_by": b.user_ref(db, r.approved_by_user_id, hide),
        "returned_comment": r.returned_comment,
        "ack_due_on": r.ack_due_on,
        "acks": ack_stats(db, r.id),
        "signoffs": _signoffs(db, d, r, hide),
        "download_name": file_name(db, d, r),
    }


def _list_item(db: Session, d: QDocument, hide: bool, today: date) -> dict[str, Any]:
    cur = db.get(QDocumentRevision, d.current_revision_id) if d.current_revision_id else None
    op = _open_revision(db, d)
    en, ar = DOC_TYPE_LABELS[d.doc_type]
    return {
        "id": d.id,
        "project_id": d.project_id,
        "doc_no": d.doc_no,
        "doc_type": d.doc_type,
        "doc_type_en": en,
        "doc_type_ar": ar,
        "title_en": d.title_en,
        "title_ar": d.title_ar,
        "profile": d.profile,
        "discipline": d.discipline,
        "process_id": d.process_id,
        "owner": b.user_ref(db, d.owner_user_id, hide),
        "status": d.status,
        "current_rev": cur.rev_code if cur else None,
        "open_rev": op.rev_code if op else None,
        "open_rev_status": op.status if op else None,
        "review_due_on": d.review_due_on,
        "review_overdue": bool(d.review_due_on and d.review_due_on < today),
    }


def read(db: Session, p: Principal, doc_id: uuid.UUID) -> dict[str, Any]:
    d = _get(db, p, doc_id)
    project = db.get(Project, d.project_id)
    assert project is not None  # noqa: S101
    hide = b.hide_names(p, d.project_id)
    out = _list_item(db, d, hide, b.today(project))
    out["revisions"] = [rev_read(db, d, r, hide) for r in reversed(_revisions(db, d))]
    dist = db.scalar(select(QDocDistribution).where(QDocDistribution.document_id == d.id))
    out["distribution"] = _dist_read(dist)
    out["status_reason"] = d.status_reason
    out["can_author"] = p.grant(d.project_id, C.document_author) is not None
    op = _open_revision(db, d)
    out["can_review"] = bool(
        op
        and op.status == RS.for_review
        and rpm.resolves(db, p, project, RT.document, "review", _ctx(op), record_id=d.id)
    )
    out["can_approve"] = bool(
        op
        and op.status == RS.for_review
        and rpm.resolves(db, p, project, RT.document, "approve", _ctx(op), record_id=d.id)
    )
    out["my_ack"] = _my_ack(db, p, d)
    return out


def _my_ack(db: Session, p: Principal, d: QDocument) -> dict[str, Any] | None:
    if d.current_revision_id is None:
        return None
    a = db.scalar(
        select(QDocAck).where(
            QDocAck.revision_id == d.current_revision_id, QDocAck.user_id == p.user.id
        )
    )
    if a is None:
        return None
    return {"revision_id": a.revision_id, "due_on": a.due_on, "acked_at": a.acked_at}


def _dist_read(dist: QDocDistribution | None) -> dict[str, Any]:
    if dist is None:
        return {
            "roles": [],
            "positions": [],
            "engagement_ids": [],
            "user_ids": [],
            "ack_required": False,
        }
    return {
        "roles": list(dist.roles or []),
        "positions": list(dist.positions or []),
        "engagement_ids": list(dist.engagement_ids or []),
        "user_ids": list(dist.user_ids or []),
        "ack_required": dist.ack_required,
    }


def list_documents(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    doc_type: QDocType | None,
    status: QRevStatus | None,
    q: str | None,
    page_no: int,
    size: int,
) -> dict[str, Any]:
    project = b.project(db, p, project_id)
    g = p.grant(project.id, C.quality_view)
    if (g is None or g.scope == b.S.responsible) and p.grant(project.id, C.document_author) is None:
        raise forbidden_error()
    stmt = select(QDocument).where(QDocument.project_id == project.id)
    if doc_type:
        stmt = stmt.where(QDocument.doc_type == doc_type)
    if status:
        stmt = stmt.where(QDocument.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                QDocument.doc_no.ilike(like),
                QDocument.title_en.ilike(like),
                QDocument.title_ar.ilike(like),
            )
        )
    rows = list(db.scalars(stmt.order_by(QDocument.doc_no)))
    hide = b.hide_names(p, project.id)
    day = b.today(project)
    return b.page([_list_item(db, d, hide, day) for d in rows], page_no, size)


# ---- create, edit, revisions ---------------------------------------------------------------------


def _scheme(db: Session, project_id: uuid.UUID) -> QRevisionScheme:
    return QRevisionScheme(str(b.setting(db, project_id, "doc_revision_scheme")))


def _next_number(db: Session, d: QDocument) -> str:
    approved = db.scalar(
        select(func.count())
        .select_from(QDocumentRevision)
        .where(
            QDocumentRevision.document_id == d.id,
            QDocumentRevision.approved_at.is_not(None),
        )
    )
    first = 1 if _scheme(db, d.project_id) == QRevisionScheme.numbers else 0
    return str(first + int(approved or 0))


def _member_user(db: Session, project: Project, uid: uuid.UUID, field: str) -> None:
    a = db.scalar(
        select(RoleAssignment.id).where(
            RoleAssignment.user_id == uid,
            RoleAssignment.revoked_at.is_(None),
            or_(RoleAssignment.project_id == project.id, RoleAssignment.role == Role.hse_manager),
        )
    )
    if a is None:
        raise qc.field_err(field, "The user is not on this project.", "المستخدم ليس في المشروع.")


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project, _g = b.writer(db, p, project_id, C.document_author)
    dt = QDocType(body["doc_type"])
    owner = body.get("owner_user_id") or p.user.id
    _member_user(db, project, owner, "owner_user_id")
    doc_no = (body.get("doc_no") or "").strip() or b.number(
        db, project, RT.document, DOC_PREFIX[dt]
    )
    if db.scalar(
        select(QDocument.id).where(QDocument.project_id == project.id, QDocument.doc_no == doc_no)
    ):
        raise qc.err(409, ErrorCode.DUPLICATE_VALUE, f"{doc_no} exists.", "رقم الوثيقة مستخدم.")
    d = QDocument(
        id=uuid.uuid4(),
        project_id=project.id,
        doc_no=doc_no,
        doc_type=dt,
        title_en=body["title_en"].strip(),
        title_ar=(body.get("title_ar") or "").strip(),
        profile=QProfileScope(body.get("profile") or "both"),
        discipline=body.get("discipline"),
        process_id=body.get("process_id"),
        owner_user_id=owner,
        status=RS.draft,
        created_by_user_id=p.user.id,
        alerts_sent=[],
    )
    db.add(d)
    db.flush()
    r = QDocumentRevision(
        id=uuid.uuid4(),
        document_id=d.id,
        rev_code="A",
        rev_index=1,
        status=RS.draft,
        change_summary=body.get("change_summary") or "First issue",
        author_user_id=p.user.id,
        created_by_user_id=p.user.id,
    )
    db.add(r)
    db.flush()
    b.record(db, p, AuditAction.create, RT.document, d, project.id, details={"doc_no": doc_no})
    return read(db, p, d.id)


def update(db: Session, p: Principal, doc_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    d = _get(db, p, doc_id)
    project, _g = b.writer(db, p, d.project_id, C.document_author)
    if d.status == RS.obsolete:
        raise _immutable()
    for k in ("title_en", "title_ar", "discipline", "process_id"):
        if k in body and body[k] is not None:
            setattr(d, k, body[k])
    if body.get("owner_user_id"):
        _member_user(db, project, body["owner_user_id"], "owner_user_id")
        d.owner_user_id = body["owner_user_id"]
    d.updated_by_user_id = p.user.id
    db.flush()
    b.record(db, p, AuditAction.update, RT.document, d, d.project_id)
    return read(db, p, d.id)


def new_revision(db: Session, p: Principal, doc_id: uuid.UUID) -> dict[str, Any]:
    """Q-DOC-03: a new revision starts from the current approved one (summary and source file)."""
    d = _get(db, p, doc_id)
    b.writer(db, p, d.project_id, C.document_author)
    if d.status == RS.obsolete:
        raise _immutable()
    if _open_revision(db, d) is not None:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "A revision is already open.",
            "توجد مراجعة مفتوحة بالفعل.",
        )
    cur = db.get(QDocumentRevision, d.current_revision_id) if d.current_revision_id else None
    n = len(_revisions(db, d)) + 1
    r = QDocumentRevision(
        id=uuid.uuid4(),
        document_id=d.id,
        rev_code="A",
        rev_index=n,
        status=RS.draft,
        source_attachment_id=cur.source_attachment_id if cur else None,
        author_user_id=p.user.id,
        created_by_user_id=p.user.id,
    )
    db.add(r)
    db.flush()
    b.record(db, p, AuditAction.create, RT.document, d, d.project_id, details={"revision": n})
    return read(db, p, d.id)


def update_revision(
    db: Session, p: Principal, rev_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    r, d = _get_rev(db, p, rev_id)
    b.writer(db, p, d.project_id, C.document_author)
    if r.status != RS.draft:
        raise (
            _immutable()
            if r.status not in OPEN_REV
            else qc.err(
                409,
                ErrorCode.INVALID_TRANSITION,
                "Return the revision to Draft to edit it.",
                "أعد المراجعة إلى مسودة لتعديلها.",
            )
        )
    if "file_attachment_id" in body:
        r.file_attachment_id = b.attachment_on(
            db,
            body["file_attachment_id"],
            AttachmentOwner.q_document_file,
            r.id,
            "file_attachment_id",
        )
    if "source_attachment_id" in body:
        r.source_attachment_id = b.attachment_on(
            db,
            body["source_attachment_id"],
            AttachmentOwner.q_document_file,
            r.id,
            "source_attachment_id",
        )
    for k in ("change_summary", "effective_date"):
        if k in body:
            setattr(r, k, body[k])
    r.updated_by_user_id = p.user.id
    db.flush()
    return read(db, p, d.id)


def _is_pdf(db: Session, aid: uuid.UUID | None) -> bool:
    a = db.get(Attachment, aid) if aid else None
    return a is not None and (
        a.content_type == "application/pdf" or a.file_name.lower().endswith(".pdf")
    )


def submit(db: Session, p: Principal, rev_id: uuid.UUID) -> dict[str, Any]:
    r, d = _get_rev(db, p, rev_id)
    b.writer(db, p, d.project_id, C.document_author)
    if r.status != RS.draft:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Only a Draft is sent for review.",
            "تُرسل المسودة فقط للمراجعة.",
        )
    if not _is_pdf(db, r.file_attachment_id):
        raise qc.err(
            422,
            ErrorCode.DOCUMENT_FILE_REQUIRED,
            "Attach the PDF of the revision first.",
            "أرفق ملف PDF للمراجعة أولاً.",
        )
    r.status = RS.for_review
    r.submitted_at = now()
    if d.current_revision_id is None:
        d.status = RS.for_review
    db.flush()
    project = db.get(Project, d.project_id)
    assert project is not None  # noqa: S101
    users = b.resolvers(db, project, RT.document, "review", _ctx(r), record_id=d.id)
    b.send(
        db,
        project,
        users,
        f"doc:{r.id}:review",
        f"{d.doc_no} Rev.{r.rev_code} for review",
        f"{d.doc_no} المراجعة {r.rev_code} للمراجعة",
        rt=RT.document,
        rid=d.id,
        path=f"/quality/documents/{d.id}",
    )
    b.record(
        db,
        p,
        AuditAction.status_change,
        RT.document,
        d,
        d.project_id,
        details={"revision": r.rev_code, "to": "for_review"},
    )
    return read(db, p, d.id)


def _return(db: Session, d: QDocument, r: QDocumentRevision, comment: str) -> None:
    """For Review → Draft; the revision comes back as the next letter (D-361)."""
    r.status = RS.draft
    r.returned_comment = comment
    idx = LETTERS.find(r.rev_code)
    nxt = LETTERS[idx + 1] if 0 <= idx < len(LETTERS) - 1 else r.rev_code + "1"
    r.rev_code = nxt
    if d.current_revision_id is None:
        d.status = RS.draft


def review(db: Session, p: Principal, rev_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """A `document.review` sign-off while For Review (Q-DOC-02); `returned` sends it back."""
    r, d = _get_rev(db, p, rev_id)
    project, _g = b.writer(db, p, d.project_id, C.document_approve, allow_n=True)
    if r.status != RS.for_review:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "The revision is not for review.",
            "المراجعة ليست قيد المراجعة.",
        )
    decision = body.get("decision") or "approved"
    comment = body.get("comment")
    if decision == "returned":
        comment = qc.reason(comment, 20, "comment")
    b.sign(db, p, project, RT.document, r.id, "review", _ctx(r), decision=decision, comment=comment)
    if decision == "returned":
        _return(db, d, r, comment or "")
    db.flush()
    return read(db, p, d.id)


def approve(db: Session, p: Principal, rev_id: uuid.UUID, body: dict[str, Any]) -> dict[str, Any]:
    """For Review → Approved (Q-DOC-02 / -03 / -04 / -05) or → Draft (`returned`)."""
    r, d = _get_rev(db, p, rev_id)
    project, _g = b.writer(db, p, d.project_id, C.document_approve, allow_n=True)
    if r.status != RS.for_review:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "The revision is not for review.",
            "المراجعة ليست قيد المراجعة.",
        )
    decision = body.get("decision") or "approved"
    if decision == "returned":
        comment = qc.reason(body.get("comment"), 20, "comment")
        b.sign(
            db,
            p,
            project,
            RT.document,
            r.id,
            "approve",
            _ctx(r),
            decision="returned",
            comment=comment,
        )
        _return(db, d, r, comment)
        db.flush()
        return read(db, p, d.id)
    if p.user.id in _ctx(r).requesters:
        raise qc.err(
            422,
            ErrorCode.SOD_CONFLICT,
            "The author cannot approve their own revision (Q-RPM-06).",
            "لا يجوز للمؤلف اعتماد مراجعته.",
        )
    if not _is_pdf(db, r.file_attachment_id):
        raise qc.err(
            422,
            ErrorCode.DOCUMENT_FILE_REQUIRED,
            "The revision has no PDF.",
            "لا يوجد ملف PDF للمراجعة.",
        )
    reviewed = db.scalar(
        select(QSignoff.id)
        .where(
            QSignoff.record_type == RT.document.value,
            QSignoff.record_id == r.id,
            QSignoff.step == "review",
            QSignoff.decision.in_(["approved", "approved_with_comments"]),
            QSignoff.signed_at >= (r.submitted_at or r.created_at),
        )
        .limit(1)
    )
    if reviewed is None:
        raise qc.err(
            422,
            ErrorCode.SIGNOFF_REQUIRED,
            "At least one review sign-off is needed before approval (Q-DOC-02).",
            "يلزم توقيع مراجعة واحد على الأقل قبل الاعتماد.",
        )
    b.sign(
        db,
        p,
        project,
        RT.document,
        r.id,
        "approve",
        _ctx(r),
        decision="approved",
        comment=body.get("comment"),
    )
    _approve(db, project, d, r, p.user.id)
    b.record(
        db,
        p,
        AuditAction.status_change,
        RT.document,
        d,
        d.project_id,
        details={"revision": r.rev_code, "to": "approved"},
    )
    return read(db, p, d.id)


def _approve(
    db: Session, project: Project, d: QDocument, r: QDocumentRevision, by: uuid.UUID | None
) -> None:
    t = now()
    day = qc.project_day(project, t)
    r.rev_code = _next_number(db, d)
    r.status = RS.approved
    r.approved_at, r.approved_date, r.approved_by_user_id = t, day, by
    r.effective_date = r.effective_date or day
    prev = db.get(QDocumentRevision, d.current_revision_id) if d.current_revision_id else None
    if prev is not None and prev.status == RS.approved:
        prev.status = RS.superseded
        prev.superseded_at = t
    d.current_revision_id = r.id
    d.status = RS.approved
    d.review_due_on = b.due_after(day, int(b.setting(db, d.project_id, "doc_review_months")))
    d.alerts_sent = [x for x in (d.alerts_sent or []) if not x.startswith("review")]
    db.flush()
    _create_acks(db, project, d, r, day)
    _notify_citers(db, project, d, prev, r)


def _members(db: Session, project: Project, dist: QDocDistribution) -> set[uuid.UUID]:
    day = qc.project_day(project)
    out: set[uuid.UUID] = set(dist.user_ids or [])
    roles = set(dist.roles or [])
    engs = set(dist.engagement_ids or [])
    for a in db.scalars(
        select(RoleAssignment).where(
            RoleAssignment.project_id == project.id, RoleAssignment.revoked_at.is_(None)
        )
    ):
        if not a.is_active_on(day):
            continue
        if a.role.value in roles or (
            a.contractor_engagement_id and a.contractor_engagement_id in engs
        ):
            out.add(a.user_id)
    if dist.positions:
        pos = list(
            db.scalars(
                select(QPosition.id).where(
                    QPosition.project_id == project.id, QPosition.code.in_(dist.positions)
                )
            )
        )
        for h in db.scalars(select(QPositionHolder).where(QPositionHolder.position_id.in_(pos))):
            if h.valid_from <= day and (h.valid_to is None or h.valid_to >= day):
                out.add(h.user_id)
    return {u for u in out if qc.active_user(db, u) is not None}


def _create_acks(
    db: Session, project: Project, d: QDocument, r: QDocumentRevision, day: date
) -> int:
    """Q-DOC-05: one task per distribution member resolved at approval, due in read_ack_days."""
    dist = db.scalar(select(QDocDistribution).where(QDocDistribution.document_id == d.id))
    if dist is None or not dist.ack_required:
        return 0
    due = day + timedelta(days=int(b.setting(db, d.project_id, "read_ack_days")))
    r.ack_due_on = due
    users = _members(db, project, dist)
    for uid in sorted(users):
        db.add(QDocAck(id=uuid.uuid4(), revision_id=r.id, user_id=uid, due_on=due))
    db.flush()
    b.send(
        db,
        project,
        users,
        f"doc-ack:{r.id}",
        f"Read and acknowledge {d.doc_no} Rev.{r.rev_code}",
        f"اطلع وأقر بالوثيقة {d.doc_no} المراجعة {r.rev_code}",
        rt=RT.document,
        rid=d.id,
        path=f"/quality/documents/{d.id}",
    )
    return len(users)


def obsolete(db: Session, p: Principal, doc_id: uuid.UUID, reason: str | None) -> dict[str, Any]:
    d = _get(db, p, doc_id)
    b.writer(db, p, d.project_id, C.quality_settings)
    if d.status != RS.approved:
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Only an approved document is withdrawn.",
            "تُسحب الوثيقة المعتمدة فقط.",
        )
    d.status_reason = qc.reason(reason, 20)
    d.status = RS.obsolete
    cur = db.get(QDocumentRevision, d.current_revision_id) if d.current_revision_id else None
    if cur is not None:
        cur.status = RS.obsolete
    db.flush()
    b.record(
        db, p, AuditAction.status_change, RT.document, d, d.project_id, details={"to": "obsolete"}
    )
    return read(db, p, d.id)


def set_distribution(
    db: Session, p: Principal, doc_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    d = _get(db, p, doc_id)
    project, _g = b.writer(db, p, d.project_id, C.document_author)
    dist = db.scalar(select(QDocDistribution).where(QDocDistribution.document_id == d.id))
    if dist is None:
        dist = QDocDistribution(id=uuid.uuid4(), document_id=d.id, created_by_user_id=p.user.id)
        db.add(dist)
    valid_roles = {r.value for r in Role}
    for x in body.get("roles") or []:
        if x not in valid_roles:
            raise qc.field_err("roles", f"Unknown role {x}.", "دور غير معروف.")
    for eid in body.get("engagement_ids") or []:
        e = db.get(ProjectEngagement, eid)
        if e is None or e.project_id != project.id:
            raise qc.field_err(
                "engagement_ids", "Not an engagement of the project.", "ليس تعاقداً في المشروع."
            )
    for i, uid in enumerate(body.get("user_ids") or []):
        _member_user(db, project, uid, f"user_ids[{i}]")
    dist.roles = list(body.get("roles") or [])
    dist.positions = list(body.get("positions") or [])
    dist.engagement_ids = list(body.get("engagement_ids") or [])
    dist.user_ids = list(body.get("user_ids") or [])
    dist.ack_required = bool(body.get("ack_required"))
    dist.updated_by_user_id = p.user.id
    db.flush()
    return read(db, p, d.id)


def acknowledge(db: Session, p: Principal, rev_id: uuid.UUID) -> dict[str, Any]:
    """275: a named member acknowledges; a second acknowledgement changes nothing (AC-Q4-04)."""
    r = db.get(QDocumentRevision, rev_id)
    if r is None:
        raise not_found("Document revision")
    a = db.scalar(select(QDocAck).where(QDocAck.revision_id == r.id, QDocAck.user_id == p.user.id))
    if a is None:
        raise forbidden_error("Only members named in the distribution acknowledge (275).")
    d = db.get(QDocument, r.document_id)
    assert d is not None  # noqa: S101
    p.ensure_writer()
    if a.acked_at is None:
        a.acked_at = now()
        db.flush()
        b.record(
            db, p, AuditAction.update, RT.document, d, d.project_id, details={"ack": r.rev_code}
        )
    return {"revision_id": r.id, "acked_at": a.acked_at, "acks": ack_stats(db, r.id)}


def my_acks(
    db: Session, p: Principal, project_id: uuid.UUID, pending: bool
) -> list[dict[str, Any]]:
    b.project(db, p, project_id)
    stmt = (
        select(QDocAck, QDocumentRevision, QDocument)
        .join(QDocumentRevision, QDocumentRevision.id == QDocAck.revision_id)
        .join(QDocument, QDocument.id == QDocumentRevision.document_id)
        .where(QDocAck.user_id == p.user.id, QDocument.project_id == project_id)
    )
    if pending:
        stmt = stmt.where(QDocAck.acked_at.is_(None))
    return [
        {
            "document_id": d.id,
            "doc_no": d.doc_no,
            "title_en": d.title_en,
            "title_ar": d.title_ar,
            "revision_id": r.id,
            "rev_code": r.rev_code,
            "revision_status": r.status,
            "file_attachment_id": r.file_attachment_id,
            "due_on": a.due_on,
            "acked_at": a.acked_at,
        }
        for a, r, d in db.execute(stmt.order_by(QDocAck.due_on, QDocument.doc_no))
    ]


def file_name(db: Session, d: QDocument, r: QDocumentRevision) -> str | None:
    """Q-DOC-03: superseded files keep downloading with the suffix `-SUPERSEDED`."""
    if r.file_attachment_id is None:
        return None
    suffix = "-SUPERSEDED" if r.status in (RS.superseded, RS.obsolete) else ""
    return f"{d.doc_no}-Rev{r.rev_code}{suffix}.pdf"


def download(db: Session, p: Principal, rev_id: uuid.UUID) -> tuple[bytes, str]:
    r, d = _get_rev(db, p, rev_id)
    a = db.get(Attachment, r.file_attachment_id) if r.file_attachment_id else None
    name = file_name(db, d, r)
    if a is None or name is None:
        raise not_found("File")
    b.record(db, p, AuditAction.export, RT.document, d, d.project_id, details={"file": name})
    return attachments.read_content(a), name


# ---- citations (Q-DOC-06) ----------------------------------------------------------------------


def _newer(db: Session, r: QDocumentRevision) -> QDocumentRevision | None:
    if r.status not in (RS.superseded, RS.obsolete):
        return None
    d = db.get(QDocument, r.document_id)
    return db.get(QDocumentRevision, d.current_revision_id) if d and d.current_revision_id else None


def citation_title(db: Session, r: QDocumentRevision) -> str:
    d = db.get(QDocument, r.document_id)
    base_ = f"{d.title_en if d else ''} — Rev.{r.rev_code}"
    n = _newer(db, r)
    return f"{base_} (newer revision available: Rev.{n.rev_code})" if n else base_


def citations_of(
    db: Session, p: Principal, rt: QRecordType, rid: uuid.UUID
) -> list[dict[str, Any]]:
    """Documents cited by a record, with "newer revision available" (AC-Q4-05)."""
    ad = reg.RECORD_TYPES.get(rt)
    row = ad.get(db, rid) if ad else None
    if ad is None or row is None or not ad.scope(db, p, row):
        raise not_found("Record")
    out = []
    for ln in db.scalars(
        select(QLink).where(
            or_(
                (QLink.from_type == rt.value)
                & (QLink.from_id == rid)
                & (QLink.to_type == RT.document.value),
                (QLink.to_type == rt.value)
                & (QLink.to_id == rid)
                & (QLink.from_type == RT.document.value),
            )
        )
    ):
        rev_id = ln.to_id if ln.to_type == RT.document.value else ln.from_id
        r = db.get(QDocumentRevision, rev_id)
        if r is None:
            continue
        d = db.get(QDocument, r.document_id)
        n = _newer(db, r)
        out.append(
            {
                "document_id": r.document_id,
                "doc_no": d.doc_no if d else "",
                "revision_id": r.id,
                "rev_code": r.rev_code,
                "status": r.status,
                "newer_revision_available": n is not None,
                "newer_rev_code": n.rev_code if n else None,
            }
        )
    return out


def cite(
    db: Session, p: Principal, rev_id: uuid.UUID, rt: QRecordType, rid: uuid.UUID
) -> list[dict[str, Any]]:
    from app.services.quality import links  # noqa: PLC0415

    r, d = _get_rev(db, p, rev_id)
    b.writer(db, p, d.project_id, C.document_author)
    ad = reg.RECORD_TYPES.get(rt)
    row = ad.get(db, rid) if ad else None
    if ad is None or row is None or ad.project_id(row) != d.project_id or not ad.scope(db, p, row):
        raise links.not_allowed()
    links.add(db, d.project_id, rt, rid, RT.document, r.id, QLinkKind.relates, p.user.id)
    return citations_of(db, p, rt, rid)


def _notify_citers(
    db: Session,
    project: Project,
    d: QDocument,
    prev: QDocumentRevision | None,
    r: QDocumentRevision,
) -> None:
    if prev is None:
        return
    owners: set[uuid.UUID] = set()
    for ln in db.scalars(
        select(QLink).where(QLink.to_type == RT.document.value, QLink.to_id == prev.id)
    ):
        ad = (
            reg.RECORD_TYPES.get(QRecordType(ln.from_type))
            if ln.from_type in RT._value2member_map_
            else None
        )
        row = ad.get(db, ln.from_id) if ad else None
        if row is not None and not ad.voided(row):  # type: ignore[union-attr]
            owners |= {u for u in (getattr(row, "created_by_user_id", None),) if u}
    if owners:
        b.send(
            db,
            project,
            owners,
            f"doc-newer:{prev.id}",
            f"Newer revision of {d.doc_no}: Rev.{r.rev_code}",
            f"مراجعة أحدث للوثيقة {d.doc_no}: {r.rev_code}",
            rt=RT.document,
            rid=d.id,
            path=f"/quality/documents/{d.id}",
            email=False,
        )


# ---- transmittals (Q-DOC-07) --------------------------------------------------------------------


def _get_trm(db: Session, p: Principal, tid: uuid.UUID) -> QTransmittal:
    t = db.get(QTransmittal, tid)
    if t is None or not p.can_see_project(t.project_id):
        raise not_found("Transmittal")
    g = p.grant(t.project_id, C.quality_view)
    if (g is None or g.scope == b.S.responsible) and p.grant(
        t.project_id, C.document_author
    ) is None:
        raise not_found("Transmittal")
    return t


def _to_label(db: Session, t: QTransmittal) -> tuple[str, str]:
    if t.to_kind == QTransmittalTo.engagement and t.to_engagement_id:
        e = db.get(ProjectEngagement, t.to_engagement_id)
        c = e.contractor if e else None
        return (c.legal_name_en, c.legal_name_ar or c.legal_name_en) if c else ("—", "—")
    if t.to_kind == QTransmittalTo.supplier and t.to_supplier_id:
        s = db.get(QSupplier, t.to_supplier_id)
        return (s.legal_name_en, s.legal_name_ar or s.legal_name_en) if s else ("—", "—")
    if t.to_kind == QTransmittalTo.customer and t.to_customer_id:
        cu = db.get(QCustomer, t.to_customer_id)
        return (cu.name_en, cu.name_ar or cu.name_en) if cu else ("—", "—")
    return (t.to_name or "—", t.to_name or "—")


def trm_read(db: Session, t: QTransmittal, hide: bool = False) -> dict[str, Any]:
    en, ar = _to_label(db, t)
    items = list(
        db.scalars(
            select(QTransmittalItem)
            .where(QTransmittalItem.transmittal_id == t.id)
            .order_by(QTransmittalItem.position)
        )
    )
    return {
        "id": t.id,
        "project_id": t.project_id,
        "trm_no": t.trm_no,
        "to_kind": t.to_kind,
        "to_engagement_id": t.to_engagement_id,
        "to_supplier_id": t.to_supplier_id,
        "to_customer_id": t.to_customer_id,
        "to_label_en": en,
        "to_label_ar": ar,
        "to_name": None if hide else t.to_name,
        "to_email": None if hide else t.to_email,
        "purpose": t.purpose,
        "method": t.method,
        "subject": t.subject,
        "note": t.note,
        "sent_at": t.sent_at,
        "response_due_on": t.response_due_on,
        "response_received_on": t.response_received_on,
        "response_name": None if hide else t.response_name,
        "status": t.status,
        "cover_en_id": t.cover_en_id,
        "cover_ar_id": t.cover_ar_id,
        "outbox_id": t.outbox_id,
        "items": [
            {
                "id": i.id,
                "kind": i.kind,
                "revision_id": i.revision_id,
                "record_type": i.record_type,
                "record_id": i.record_id,
                "ref": i.ref,
                "title": i.title,
                "response_code": i.response_code,
                "response_note": i.response_note,
            }
            for i in items
        ],
    }


def list_transmittals(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    status: QTransmittalStatus | None,
    page_no: int,
    size: int,
) -> dict[str, Any]:
    project = b.project(db, p, project_id)
    g = p.grant(project.id, C.quality_view)
    if (g is None or g.scope == b.S.responsible) and p.grant(project.id, C.document_author) is None:
        raise forbidden_error()
    stmt = select(QTransmittal).where(QTransmittal.project_id == project.id)
    if status:
        stmt = stmt.where(QTransmittal.status == status)
    hide = b.hide_names(p, project.id)
    rows = list(db.scalars(stmt.order_by(QTransmittal.created_at.desc())))
    return b.page([trm_read(db, t, hide) for t in rows], page_no, size)


def _item_rows(
    db: Session, project: Project, p: Principal, items: list[dict[str, Any]]
) -> list[QTransmittalItem]:
    out = []
    for i, it in enumerate(items):
        if it.get("revision_id"):
            r = db.get(QDocumentRevision, it["revision_id"])
            d = db.get(QDocument, r.document_id) if r else None
            if r is None or d is None or d.project_id != project.id:
                raise qc.field_err(
                    f"items[{i}].revision_id",
                    "Not a document revision of the project.",
                    "ليست مراجعة وثيقة في المشروع.",
                )
            out.append(
                QTransmittalItem(
                    id=uuid.uuid4(),
                    position=i,
                    kind=QTransmittalItemKind.document_revision,
                    revision_id=r.id,
                    ref=f"{d.doc_no} Rev.{r.rev_code}",
                    title=d.title_en,
                )
            )
            continue
        try:
            rt = QRecordType(str(it.get("record_type")))
        except ValueError as e:
            raise qc.field_err(
                f"items[{i}].record_type", "Unknown record type.", "نوع سجل غير معروف."
            ) from e
        ad = reg.RECORD_TYPES.get(rt)
        row = ad.get(db, it["record_id"]) if ad and it.get("record_id") else None
        if (
            ad is None
            or row is None
            or ad.project_id(row) != project.id
            or not ad.scope(db, p, row)
        ):
            raise qc.field_err(
                f"items[{i}].record_id", "Not a record of the project.", "ليس سجلاً في المشروع."
            )
        out.append(
            QTransmittalItem(
                id=uuid.uuid4(),
                position=i,
                kind=QTransmittalItemKind.record,
                record_type=rt.value,
                record_id=row.id,
                ref=ad.ref(row),
                title=(ad.title(row) or "")[:200],
            )
        )
    return out


def create_transmittal(
    db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    project, _g = b.writer(db, p, project_id, C.document_author)
    to = QTransmittalTo(body["to_kind"])
    t = QTransmittal(
        id=uuid.uuid4(),
        project_id=project.id,
        to_kind=to,
        purpose=body["purpose"],
        method=QTransmittalMethod(body.get("method") or "email"),
        subject=body["subject"].strip(),
        note=body.get("note"),
        response_due_on=body.get("response_due_on"),
        to_name=body.get("to_name"),
        to_email=body.get("to_email"),
        status=QTransmittalStatus.draft,
        created_by_user_id=p.user.id,
        alerts_sent=[],
    )
    if to == QTransmittalTo.engagement:
        e = (
            db.get(ProjectEngagement, body.get("to_engagement_id"))
            if body.get("to_engagement_id")
            else None
        )
        if e is None or e.project_id != project.id:
            raise qc.field_err(
                "to_engagement_id", "Choose an engagement of the project.", "اختر تعاقداً."
            )
        t.to_engagement_id = e.id
    elif to == QTransmittalTo.supplier:
        s = db.get(QSupplier, body.get("to_supplier_id")) if body.get("to_supplier_id") else None
        if s is None:
            raise qc.field_err("to_supplier_id", "Choose a supplier.", "اختر مورداً.")
        t.to_supplier_id = s.id
        t.to_email = t.to_email or s.contact_email
    elif to == QTransmittalTo.customer:
        cu = db.get(QCustomer, body.get("to_customer_id")) if body.get("to_customer_id") else None
        if cu is None or cu.project_id != project.id:
            raise qc.field_err("to_customer_id", "Choose a customer of the project.", "اختر عميلاً.")
        t.to_customer_id = cu.id
    elif not (t.to_name or "").strip():
        raise qc.field_err("to_name", "Name the external organisation.", "اذكر اسم الجهة الخارجية.")
    if t.method == QTransmittalMethod.email and not (t.to_email or "").strip():
        raise qc.field_err(
            "to_email", "An email transmittal needs an address.", "أدخل البريد الإلكتروني."
        )
    db.add(t)
    db.flush()
    items = _item_rows(db, project, p, body.get("items") or [])
    if not items:
        raise qc.field_err("items", "Add at least one item.", "أضف بنداً واحداً على الأقل.")
    for it in items:
        it.transmittal_id = t.id
        db.add(it)
    db.flush()
    b.record(db, p, AuditAction.create, RT.transmittal, t, project.id)
    return trm_read(db, t)


def cover_doc(db: Session, t: QTransmittal, project: Project) -> render.Doc:
    en, ar = _to_label(db, t)
    day = qc.project_day(project, t.sent_at or now())
    items = list(
        db.scalars(
            select(QTransmittalItem)
            .where(QTransmittalItem.transmittal_id == t.id)
            .order_by(QTransmittalItem.position)
        )
    )
    rows = [
        {"no": i.position + 1, "ref": i.ref, "title": i.title, "code": i.response_code or ""}
        for i in items
    ]
    ctl: list[tuple[str, ...]] = [
        ("Transmittal", "مذكرة الإحالة", t.trm_no or "—"),
        ("Project", "المشروع", project.code),
        ("To", "إلى", en, ar),
        ("Purpose", "الغرض", t.purpose.value.replace("_", " ")),
        ("Method", "الطريقة", t.method.value),
        ("Response due", "موعد الرد", t.response_due_on.isoformat() if t.response_due_on else "—"),
        *b.issue_dates(day),
    ]
    digest = hashlib.sha256(json.dumps([ctl, rows], default=str).encode()).hexdigest()
    return render.Doc(
        doc_no=t.trm_no or "TRM",
        revision=0,
        title_en=f"Transmittal {t.trm_no}",
        title_ar=f"مذكرة إحالة {t.trm_no}",
        snapshot_hash=digest,
        control=ctl,
        sections=[
            b.section(
                "items",
                "Items",
                "البنود",
                tables=[
                    b.table(
                        [
                            ("no", "#", "#"),
                            ("ref", "Reference", "المرجع"),
                            ("title", "Title", "العنوان"),
                            ("code", "Response", "الرد"),
                        ],
                        rows,
                    )
                ],
                paras_en=[t.subject, t.note or ""],
                paras_ar=[t.subject, t.note or ""],
            )
        ],
    )


def send_transmittal(db: Session, p: Principal, tid: uuid.UUID) -> dict[str, Any]:
    """Number, cover sheet (EN / AR, Hijri), and for `email` an outbox row with the cover and the
    item files (D-280 20 MB limit) to the external address (AC-Q4-06)."""
    t = _get_trm(db, p, tid)
    project, _g = b.writer(db, p, t.project_id, C.document_author)
    if t.status != QTransmittalStatus.draft:
        raise qc.err(
            409, ErrorCode.INVALID_TRANSITION, "Only a Draft is sent.", "تُرسل المسودة فقط."
        )
    t.trm_no = b.number(db, project, RT.transmittal)
    t.sent_at = now()
    t.status = QTransmittalStatus.sent
    db.flush()
    doc = cover_doc(db, t, project)
    t.cover_en_id, t.cover_ar_id = b.store_pdfs(
        db, AttachmentOwner.q_transmittal, t.id, project.id, doc, t.trm_no, p.user.id
    )
    if t.method == QTransmittalMethod.email:
        files = [str(t.cover_en_id), str(t.cover_ar_id)]
        size = 0
        for it in db.scalars(
            select(QTransmittalItem).where(QTransmittalItem.transmittal_id == t.id)
        ):
            r = db.get(QDocumentRevision, it.revision_id) if it.revision_id else None
            a = db.get(Attachment, r.file_attachment_id) if r and r.file_attachment_id else None
            if a is not None:
                files.append(str(a.id))
                size += a.size_bytes or 0
        if size > 20 * 1024 * 1024:
            raise qc.err(
                422,
                ErrorCode.VALIDATION_ERROR,
                "The files exceed the 20 MB email limit; send by portal or by hand.",
                "الملفات تتجاوز حد 20 ميجابايت.",
            )
        m = EmailMessage(
            to_email=(t.to_email or "").strip(),
            to_user_id=None,
            language=Language.en,
            template="quality_transmittal",
            subject=f"{t.trm_no} — {t.subject}"[:200],
            body=f"Transmittal {t.trm_no} from {project.code}: {t.subject}\n"
            f"Purpose: {t.purpose.value}. Response due: {t.response_due_on or '—'}.\n"
            f"مذكرة إحالة {t.trm_no} — {t.subject}",
            attachment_ids=files,
        )
        db.add(m)
        db.flush()
        t.outbox_id = m.id
    b.record(
        db, p, AuditAction.status_change, RT.transmittal, t, project.id, details={"to": "sent"}
    )
    return trm_read(db, t)


def respond_transmittal(
    db: Session, p: Principal, tid: uuid.UUID, body: dict[str, Any]
) -> dict[str, Any]:
    t = _get_trm(db, p, tid)
    project, _g = b.writer(db, p, t.project_id, C.document_author)
    if t.status not in (QTransmittalStatus.sent, QTransmittalStatus.responded):
        raise qc.err(
            409, ErrorCode.INVALID_TRANSITION, "The transmittal was not sent.", "لم تُرسل المذكرة."
        )
    codes = {str(x["item_id"]): x for x in body.get("items") or []}
    for it in db.scalars(select(QTransmittalItem).where(QTransmittalItem.transmittal_id == t.id)):
        x = codes.get(str(it.id))
        if x is not None:
            it.response_code = QResponseCode(x["response_code"])
            it.response_note = x.get("note")
    t.response_received_on = body.get("received_on") or qc.project_day(project)
    t.response_name = body.get("response_name")
    t.status = QTransmittalStatus.responded
    db.flush()
    b.record(db, p, AuditAction.update, RT.transmittal, t, project.id, details={"to": "responded"})
    return trm_read(db, t)


def cancel_transmittal(
    db: Session, p: Principal, tid: uuid.UUID, reason: str | None
) -> dict[str, Any]:
    t = _get_trm(db, p, tid)
    b.writer(db, p, t.project_id, C.document_author)
    if t.status != QTransmittalStatus.draft:
        raise qc.err(
            409, ErrorCode.INVALID_TRANSITION, "Only a Draft is cancelled.", "تُلغى المسودة فقط."
        )
    t.status_reason = qc.reason(reason, 20)
    t.status = QTransmittalStatus.cancelled
    db.flush()
    return trm_read(db, t)


def read_transmittal(db: Session, p: Principal, tid: uuid.UUID) -> dict[str, Any]:
    t = _get_trm(db, p, tid)
    return trm_read(db, t, b.hide_names(p, t.project_id))


# ---- jobs (§4: document review dates, ack reminders, transmittal responses) ----------------------


def daily(db: Session, at: Any) -> dict[str, int]:
    """Q-DOC-04 review alerts at 30 / 0 days to the owner; Q-DOC-05 one reminder at the due date;
    transmittal response overdue (sender)."""
    n = 0
    for d in db.scalars(
        select(QDocument).where(
            QDocument.status == RS.approved, QDocument.review_due_on.is_not(None)
        )
    ):
        project = db.get(Project, d.project_id)
        if project is None or d.review_due_on is None:
            continue
        day = qc.project_day(project, at)
        for mark, when in (
            ("review30", d.review_due_on - timedelta(days=30)),
            ("review0", d.review_due_on),
        ):
            if day >= when and mark not in (d.alerts_sent or []):
                d.alerts_sent = [*(d.alerts_sent or []), mark]
                n += b.send(
                    db,
                    project,
                    [d.owner_user_id],
                    f"doc:{d.id}:{mark}:{d.review_due_on}",
                    f"{d.doc_no} review due {d.review_due_on.isoformat()}",
                    f"مراجعة الوثيقة {d.doc_no} مستحقة {d.review_due_on.isoformat()}",
                    rt=RT.document,
                    rid=d.id,
                    path=f"/quality/documents/{d.id}",
                )
    for a, _r, d in db.execute(
        select(QDocAck, QDocumentRevision, QDocument)
        .join(QDocumentRevision, QDocumentRevision.id == QDocAck.revision_id)
        .join(QDocument, QDocument.id == QDocumentRevision.document_id)
        .where(QDocAck.acked_at.is_(None), QDocAck.reminded.is_(False))
    ):
        project = db.get(Project, d.project_id)
        if project is None or qc.project_day(project, at) < a.due_on:
            continue
        a.reminded = True
        n += b.send(
            db,
            project,
            [a.user_id],
            f"doc-ack-rem:{a.id}",
            f"Reminder: acknowledge {d.doc_no}",
            f"تذكير: أقر بالوثيقة {d.doc_no}",
            rt=RT.document,
            rid=d.id,
            path=f"/quality/documents/{d.id}",
        )
    for t in db.scalars(
        select(QTransmittal).where(
            QTransmittal.status == QTransmittalStatus.sent,
            QTransmittal.response_due_on.is_not(None),
        )
    ):
        project = db.get(Project, t.project_id)
        if (
            project is None
            or t.response_due_on is None
            or qc.project_day(project, at) <= t.response_due_on
        ):
            continue
        if "overdue" in (t.alerts_sent or []):
            continue
        t.alerts_sent = [*(t.alerts_sent or []), "overdue"]
        if t.created_by_user_id:
            n += b.send(
                db,
                project,
                [t.created_by_user_id],
                f"trm:{t.id}:overdue",
                f"{t.trm_no} response overdue",
                f"تأخر الرد على {t.trm_no}",
                rt=RT.transmittal,
                rid=t.id,
                path=f"/quality/transmittals/{t.id}",
                email=False,
            )
    db.flush()
    return {"q4_documents": n}


def k159(db: Session, project_id: uuid.UUID, as_of: date) -> dict[str, Any]:
    """K-159: approved current documents not past review_due_on ÷ approved current × 100; chip
    read-ack completion of revisions whose ack due ≤ as_of (aggregated in SQL)."""
    total, ok = db.execute(
        select(
            func.count(QDocument.id),
            func.count(QDocument.id).filter(
                or_(QDocument.review_due_on.is_(None), QDocument.review_due_on >= as_of)
            ),
        ).where(QDocument.project_id == project_id, QDocument.status == RS.approved)
    ).one()
    req, done = db.execute(
        select(
            func.count(QDocAck.id),
            func.count(QDocAck.id).filter(QDocAck.acked_at.is_not(None)),
        )
        .join(QDocumentRevision, QDocumentRevision.id == QDocAck.revision_id)
        .join(QDocument, QDocument.id == QDocumentRevision.document_id)
        .where(QDocument.project_id == project_id, QDocAck.due_on <= as_of)
    ).one()
    return {
        "current": int(total),
        "in_date": int(ok),
        "acks_required": int(req),
        "acks_done": int(done),
    }
