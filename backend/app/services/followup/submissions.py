"""Submission evidence and acknowledgements (spec 6f-incident-followup §3.5, §4.3, SB-1…SB-5).

The first valid submission of a body fills the Phase 1 `notified_at`, `reference_no` and
`notified_by` read fields (SB-4, one source of truth); voiding it moves them to the next valid
submission of the body, or clears them."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.followup_enums import FuChannel, FuFiler, FuPackStatus, FuStage, FuSubmissionStatus
from app.core.hse_enums import AttachmentOwner, ExternalBody
from app.models import (
    ExternalNotification,
    FuPack,
    FuRequirement,
    FuSubmission,
    Incident,
)
from app.schemas.followup import (
    FuSubmissionAck,
    FuSubmissionCreate,
    FuSubmissionPage,
    FuSubmissionRead,
    FuSubmissionUpdate,
    FuSubmissionVoid,
)
from app.services.common import invalid_transition
from app.services.followup import common as fc
from app.services.followup import requirements as rq
from app.services.permissions import Principal, forbidden_error

C = Capability
ET = EntityType
SS = FuSubmissionStatus
VERBAL_ONLY = {FuChannel.phone_radio, FuChannel.meeting}
EDIT_HOURS = 24


def to_read(db: Session, s: FuSubmission, viewer: bool = False) -> FuSubmissionRead:
    req = db.get(FuRequirement, s.requirement_id)
    inc = db.get(Incident, req.incident_id) if req else None
    pk = db.get(FuPack, s.pack_id) if s.pack_id else None
    return FuSubmissionRead(
        id=s.id, submission_no=s.submission_no, project_id=s.project_id,
        requirement_id=s.requirement_id, incident_ref=inc.ref if inc else "?",
        body=req.body if req else ExternalBody.client, stage=req.stage if req else FuStage.written,
        pack_id=s.pack_id, pack_no=pk.pack_no if pk else None, channel=s.channel,
        submitted_at=s.submitted_at, contacted_desk_en=s.contacted_desk_en,
        contacted_desk_ar=s.contacted_desk_ar, reference_no=s.reference_no,
        call_note=s.call_note,
        evidence_file_ids=None if viewer else list(s.evidence_file_ids or []),
        has_external_document=s.external_document_id is not None,
        acknowledged_at=s.acknowledged_at, ack_reference=s.ack_reference, on_time=s.on_time,
        status=s.status, void_reason=s.void_reason,
        recorded_by=None if viewer else fc.user_ref(db, s.created_by_user_id),
        created_at=s.created_at,
    )  # fmt: skip


def _evidence_err(field: str, en: str, ar: str) -> Any:
    return fc.code_err(ErrorCode.EVIDENCE_REQUIRED, en, ar, field)


def _phase1_sync(db: Session, inc: Incident, body: ExternalBody) -> None:
    """SB-4: the Phase 1 notified fields follow the first valid submission of the body."""
    reqs = [
        r.id
        for r in db.scalars(
            select(FuRequirement).where(
                FuRequirement.incident_id == inc.id, FuRequirement.body == body
            )
        )
    ]
    first = (
        db.scalars(
            select(FuSubmission)
            .where(FuSubmission.requirement_id.in_(reqs), FuSubmission.status != SS.voided)
            .order_by(FuSubmission.submitted_at)
        ).first()
        if reqs
        else None
    )
    row = db.get(ExternalNotification, (inc.id, body))
    if first is None:
        if row is not None:
            db.delete(row)
        return
    if row is None:
        row = ExternalNotification(incident_id=inc.id, body=body, alerts_sent=[])
        db.add(row)
    row.notified_at = first.submitted_at
    row.reference_no = first.reference_no
    row.notified_by_user_id = first.created_by_user_id


def record(
    db: Session, p: Principal, req_id: uuid.UUID, body: FuSubmissionCreate
) -> FuSubmissionRead:
    req, inc = rq.get_req(db, p, req_id, C.followup_record)
    from app.services.common import ensure_open  # noqa: PLC0415

    ensure_open(fc.project(db, p, req.project_id))
    t = now()
    if body.submitted_at < inc.occurred_at or body.submitted_at > t + timedelta(minutes=5):
        raise fc.code_err(
            ErrorCode.SUBMITTED_AT_INVALID,
            "The submission time must be after the incident and not in the future.",
            "يجب أن يكون وقت الإرسال بعد الحادثة وليس في المستقبل.",
            "submitted_at",
        )
    verbal = req.stage == FuStage.verbal
    if body.channel in VERBAL_ONLY and not verbal:
        raise fc.code_err(ErrorCode.CHANNEL_NOT_ALLOWED,
                          "Phone, radio and meetings are accepted for verbal stages only.",
                          "الهاتف واللاسلكي والاجتماع للمرحلة الشفهية فقط.", "channel")  # fmt: skip
    pk = None
    if body.pack_id is not None:
        pk = db.get(FuPack, body.pack_id)
        if pk is None or pk.requirement_id != req.id:
            raise validation_error("pack_id", "The pack belongs to another requirement.")
    operator_files = req.filer == FuFiler.airport_operator and bool(body.evidence_files)
    if (
        not verbal
        and not operator_files
        and body.external_document is None
        and (pk is None or pk.status != FuPackStatus.approved)
    ):
        raise fc.code_err(
            ErrorCode.PACK_NOT_APPROVED,
            "Name an Approved pack of this requirement or attach the document sent (SB-2).",
            "اختر حزمة معتمدة أو أرفق المستند المرسل.",
            "pack_id",
        )
    if verbal:
        if not (body.contacted_desk_en or body.contacted_desk_ar):
            raise _evidence_err("contacted_desk_en", "Record the desk or role contacted (SB-3).",
                                "سجّل الجهة أو المكتب الذي تم الاتصال به.")  # fmt: skip
        if not (body.reference_no or body.call_note):
            raise _evidence_err("reference_no", "Record the reference or a call-time note (SB-3).",
                                "سجّل الرقم المرجعي أو ملاحظة وقت الاتصال.")  # fmt: skip
    else:
        if not body.reference_no and not body.evidence_files:
            raise _evidence_err("evidence_files", "Record the reference or attach evidence (SB-3).",
                                "سجّل الرقم المرجعي أو أرفق دليلاً.")  # fmt: skip
        if body.channel == FuChannel.hand_delivered and body.stamped_copy is None:
            raise _evidence_err("stamped_copy", "Attach the stamped copy (SB-3).",
                                "أرفق النسخة المختومة.")  # fmt: skip
    year = fc.local_day().year
    from app.services.hse_common import next_seq  # noqa: PLC0415

    seq = next_seq(db, FuSubmission, req.project_id, year)
    s = FuSubmission(
        id=uuid.uuid4(), project_id=req.project_id, year=year, seq=seq,
        submission_no=f"NS-{fc.pcode(db, req.project_id)}-{year}-{seq:04d}",
        requirement_id=req.id, pack_id=pk.id if pk else None, channel=body.channel,
        submitted_at=body.submitted_at, contacted_desk_en=body.contacted_desk_en,
        contacted_desk_ar=body.contacted_desk_ar, reference_no=body.reference_no,
        call_note=body.call_note, evidence_file_ids=[], on_time=body.submitted_at <= req.due_at,
        status=SS.recorded, created_by_user_id=p.user.id,
    )  # fmt: skip
    db.add(s)
    db.flush()
    s.evidence_file_ids = [
        fc.store_file(db, f, AttachmentOwner.fu_evidence, s.id, s.project_id, p.user.id,
                      f"evidence_files.{i}")
        for i, f in enumerate(body.evidence_files)
    ]  # fmt: skip
    if body.stamped_copy is not None:
        s.stamped_copy_file_id = fc.store_file(
            db, body.stamped_copy, AttachmentOwner.fu_evidence, s.id, s.project_id, p.user.id,
            "stamped_copy",
        )  # fmt: skip
    if body.external_document is not None:
        s.external_document_id = fc.store_file(
            db, body.external_document, AttachmentOwner.fu_evidence, s.id, s.project_id,
            p.user.id, "external_document",
        )  # fmt: skip
    if pk is not None and pk.status == FuPackStatus.approved:
        pk.status = FuPackStatus.submitted
    db.flush()
    _phase1_sync(db, inc, req.body)
    db.flush()
    fc.record(db, p, AuditAction.create, ET.followup_submission, s, s.project_id)
    return to_read(db, s)


def record_phase1(
    db: Session, p: Principal, inc: Incident, body: ExternalBody, payload: Any
) -> None:
    """SB-4: the Phase 1 notification endpoint on an incident under the profile creates an
    `email` submission with no pack and needs an evidence file."""
    if payload.evidence_file is None:
        raise _evidence_err("evidence_file", "Attach the evidence (the sent email or letter).",
                            "أرفق الدليل (البريد أو الخطاب المرسل).")  # fmt: skip
    rq.derive(db, inc)
    reqs = sorted(
        db.scalars(
            select(FuRequirement).where(
                FuRequirement.incident_id == inc.id, FuRequirement.body == body
            )
        ),
        key=lambda r: (r.stage == FuStage.verbal, r.due_at),
    )
    subs = rq._valid_subs(db, [r.id for r in reqs])
    target = next((r for r in reqs if rq.is_open(r, subs.get(r.id, []))), None)
    if target is None:
        raise validation_error("body", "No open requirement of this body on the incident.")
    record(
        db, p, target.id,
        FuSubmissionCreate(
            channel=FuChannel.email, submitted_at=payload.notified_at,
            reference_no=payload.reference_no, evidence_files=[payload.evidence_file],
            external_document=payload.evidence_file,
        ),
    )  # fmt: skip


def _get(
    db: Session, p: Principal, sid: uuid.UUID, cap: Capability
) -> tuple[FuSubmission, FuRequirement, Incident]:
    s = db.get(FuSubmission, sid)
    if s is None or not p.can_see_project(s.project_id):
        raise not_found("Submission")
    req, inc = rq.get_req(db, p, s.requirement_id, cap)
    return s, req, inc


def list_submissions(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    req_id: uuid.UUID | None,
    page: int,
    size: int,
) -> FuSubmissionPage:
    g = fc.view_grant(db, p, project_id)
    viewer = fc.is_viewer(p, project_id)
    stmt = select(FuSubmission).where(FuSubmission.project_id == project_id)
    if req_id:
        stmt = stmt.where(FuSubmission.requirement_id == req_id)
    out = []
    for s in db.scalars(stmt.order_by(FuSubmission.submitted_at.desc())):
        req = db.get(FuRequirement, s.requirement_id)
        inc = db.get(Incident, req.incident_id) if req else None
        if req is None or inc is None or not rq.scope_ok(g, inc, req):
            continue
        out.append(s)
    items = [to_read(db, s, viewer) for s in out[(page - 1) * size : page * size]]
    return FuSubmissionPage(items=items, total=len(out), page=page, page_size=size)


def update(db: Session, p: Principal, sid: uuid.UUID, body: FuSubmissionUpdate) -> FuSubmissionRead:
    s, req, inc = _get(db, p, sid, C.followup_record)
    if s.status == SS.voided:
        raise invalid_transition("Submission", s.status, "edited")
    if s.created_by_user_id != p.user.id:
        raise forbidden_error("Only the recorder edits a submission (SB-5).")
    if now() > s.created_at + timedelta(hours=EDIT_HOURS):
        raise fc.err(409, ErrorCode.SUBMISSION_LOCKED,
                     "Submissions are editable for 24 h; void it instead (SB-5).",
                     "يمكن تعديل الإرسال خلال 24 ساعة فقط؛ ألغه بدلاً من ذلك.")  # fmt: skip
    data = body.model_dump(exclude_unset=True)
    if "submitted_at" in data and (
        data["submitted_at"] is None
        or data["submitted_at"] < inc.occurred_at
        or data["submitted_at"] > now() + timedelta(minutes=5)
    ):
        raise fc.code_err(ErrorCode.SUBMITTED_AT_INVALID, "Invalid submission time.",
                          "وقت الإرسال غير صالح.", "submitted_at")  # fmt: skip
    before = {k: getattr(s, k) for k in data}
    for k, v in data.items():
        setattr(s, k, v)
    s.on_time = s.submitted_at <= req.due_at
    s.updated_by_user_id = p.user.id
    db.flush()
    _phase1_sync(db, inc, req.body)
    fc.record(db, p, AuditAction.update, ET.followup_submission, s, s.project_id, before=before)
    return to_read(db, s)


def acknowledge(
    db: Session, p: Principal, sid: uuid.UUID, body: FuSubmissionAck
) -> FuSubmissionRead:
    s, _req, _inc = _get(db, p, sid, C.followup_record)
    if s.status == SS.voided:
        raise invalid_transition("Submission", s.status, SS.acknowledged)
    if body.acknowledged_at < s.submitted_at or body.acknowledged_at > now() + timedelta(minutes=5):
        raise validation_error("acknowledged_at", "On or after the submission, not in the future.")
    before = {"status": s.status.value}
    s.acknowledged_at = body.acknowledged_at
    s.ack_reference = body.ack_reference
    if body.ack_file is not None:
        s.ack_file_id = fc.store_file(db, body.ack_file, AttachmentOwner.fu_evidence, s.id,
                                      s.project_id, p.user.id, "ack_file")  # fmt: skip
    s.status = SS.acknowledged
    s.updated_by_user_id = p.user.id
    db.flush()
    fc.record(db, p, AuditAction.status_change, ET.followup_submission, s, s.project_id,
              before=before)  # fmt: skip
    return to_read(db, s)


def void(db: Session, p: Principal, sid: uuid.UUID, body: FuSubmissionVoid) -> FuSubmissionRead:
    s, req, inc = _get(db, p, sid, C.followup_approve)
    if s.status == SS.voided:
        raise invalid_transition("Submission", s.status, SS.voided)
    before = {"status": s.status.value}
    s.status = SS.voided
    s.void_reason = fc.reason(body.reason, 20)
    s.updated_by_user_id = p.user.id
    if s.pack_id:
        pk = db.get(FuPack, s.pack_id)
        others = db.scalars(
            select(FuSubmission).where(
                FuSubmission.pack_id == s.pack_id,
                FuSubmission.id != s.id,
                FuSubmission.status != SS.voided,
            )
        ).first()
        if pk is not None and pk.status == FuPackStatus.submitted and others is None:
            pk.status = FuPackStatus.approved
    db.flush()
    _phase1_sync(db, inc, req.body)
    db.flush()
    fc.record(db, p, AuditAction.status_change, ET.followup_submission, s, s.project_id,
              before=before)  # fmt: skip
    return to_read(db, s)
