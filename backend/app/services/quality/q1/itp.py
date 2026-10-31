"""Inspection and Test Plans (spec 8-quality §B.3, Q-ITP-01…06): drafts and revisions, submit
completeness, approval by the responsible person (`itp.approve`, codes A–D), supersession,
withdrawal, immutability of approved revisions and the coverage grid."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, CapabilityScope, EntityType
from app.core.errors import ErrorCode, not_found
from app.core.field_enums import TemplateKind
from app.core.quality.common import (
    QAssigneeKind,
    QCriterionStatus,
    QDiscipline,
    QLinkKind,
    QRecordType,
    label,
)
from app.core.quality.q1 import (
    QApprovalCode,
    QIrStatus,
    QItpStatus,
    QPointType,
    QVerifyingRecord,
)
from app.models import ProjectEngagement, Zone
from app.models.field import ChecklistTemplate
from app.models.quality import QCriterion, QSystem
from app.models.quality.q1 import QIr, QItp, QItpPoint
from app.services import audit
from app.services.common import invalid_transition
from app.services.hse_common import check_engagement
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import links, rpm, signoff
from app.services.quality import numbering as qnum
from app.services.quality.q1 import common as q1c

C = Capability
S = CapabilityScope
ST = QItpStatus
RT = QRecordType.itp
EDITABLE_STATES = (ST.draft, ST.revise_resubmit)
POINT_FIELDS = (
    "seq",
    "activity_en",
    "activity_ar",
    "characteristic_en",
    "characteristic_ar",
    "point_type",
    "criteria_ids",
    "acceptance_text_en",
    "acceptance_text_ar",
    "reference",
    "verifying_record",
    "checklist_template_code",
    "test_type_codes",
    "frequency_text",
    "frequency_qty",
    "frequency_unit",
    "rp_override",
    "notice_hours",
    "competence_code",
)
HEADER_FIELDS = (
    "title_en",
    "title_ar",
    "discipline",
    "work_package_en",
    "work_package_ar",
    "zone_ids",
    "system_ids",
    "spec_refs",
    "code_refs",
    "method_statement_ref",
    "change_note",
)


# ---- loading and visibility --------------------------------------------------------------------


def points_of(db: Session, itp_id: uuid.UUID) -> list[QItpPoint]:
    return list(
        db.scalars(select(QItpPoint).where(QItpPoint.itp_id == itp_id).order_by(QItpPoint.seq))
    )


def requesters(it: QItp) -> frozenset[uuid.UUID]:
    """Q-RPM-06: the author and the user who submitted never approve."""
    return qc.ids(it.prepared_by_user_id, it.submitted_by_user_id, it.created_by_user_id)


def ctx(it: QItp) -> rpm.Ctx:
    return rpm.Ctx(None, it.engagement_id, requesters(it))


def pending_steps(it: QItp) -> list[str]:
    return ["approve"] if it.status == ST.submitted else []


def can_view(db: Session, p: Principal, it: QItp) -> bool:
    uid = p.user.id
    if it.status == ST.draft and it.revision == 0 and it.itp_no is None:
        if uid in (it.prepared_by_user_id, it.created_by_user_id) or p.is_manager:
            return True
        return qc.covers(p.grant(it.project_id, C.itp_author), None, it.engagement_id)
    if uid in (it.prepared_by_user_id, it.created_by_user_id, it.submitted_by_user_id):
        return True
    g = p.grant(it.project_id, C.quality_view)
    if g is None:
        return False
    if g.scope != S.responsible:
        return qc.covers(g, None, it.engagement_id)
    # Q-ROL-04 with D-331: an approved (or superseded) ITP is the reference of the IR points a
    # responsible person inspects; otherwise only plans they approve or have signed
    if it.status in (ST.approved, ST.superseded):
        return True
    if q1c.signed_by(db, RT, it.id, uid):
        return True
    pr = q1c.project(db, it.project_id)
    return any(
        rpm.resolves(db, p, pr, RT, step, ctx(it), record_id=it.id, can_act=False)
        for step in pending_steps(it)
    )


def get_row(db: Session, itp_id: uuid.UUID) -> QItp:
    it = db.get(QItp, itp_id)
    if it is None:
        raise not_found("ITP")
    return it


def get_itp(db: Session, p: Principal, itp_id: uuid.UUID) -> QItp:
    it = db.get(QItp, itp_id)
    if it is None or not p.can_see_project(it.project_id) or not can_view(db, p, it):
        raise q1c.denied(db, p, EntityType.q_itp, itp_id, it.project_id if it else None, "ITP")
    return it


def current_approved(db: Session, family_id: uuid.UUID) -> QItp | None:
    return db.scalar(
        select(QItp).where(QItp.family_id == family_id, QItp.status == ST.approved).limit(1)
    )


def revisions(db: Session, family_id: uuid.UUID) -> list[QItp]:
    return list(db.scalars(select(QItp).where(QItp.family_id == family_id).order_by(QItp.revision)))


def display_no(it: QItp) -> str:
    return f"{it.itp_no or 'ITP (draft)'} Rev.{it.revision}"


# ---- validation --------------------------------------------------------------------------------


def _immutable() -> Any:
    return qc.err(
        409,
        ErrorCode.ITP_IMMUTABLE,
        "An approved ITP revision cannot be changed; make a new revision with a change note "
        "(Q-ITP-03).",
        "لا يمكن تعديل مراجعة معتمدة؛ أنشئ مراجعة جديدة مع ملاحظة التغيير.",
    )


def _dec(v: Any, fld: str) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError) as exc:
        raise qc.field_err(fld, "A number is required.", "أدخل رقماً.") from exc


def _check_header(db: Session, pr: Any, it: QItp) -> None:
    for i, zid in enumerate(it.zone_ids or []):
        z = db.get(Zone, zid)
        if z is None or z.project_id != pr.id:
            raise qc.field_err(f"zone_ids[{i}]", "The zone is not on this project.")
    for i, sid in enumerate(it.system_ids or []):
        s = db.get(QSystem, sid)
        if s is None or s.project_id != pr.id:
            raise qc.field_err(f"system_ids[{i}]", "The system is not on this project.")
    for f in ("spec_refs", "code_refs"):
        vals = [str(x).strip()[:120] for x in (getattr(it, f) or []) if str(x).strip()]
        if len(vals) > 20:
            raise qc.field_err(f, "At most 20 references.", "الحد الأقصى 20 مرجعاً.")
        setattr(it, f, vals)


def _check_point(db: Session, pr: Any, i: int, pt: dict[str, Any]) -> None:
    fld = f"points[{i}]"
    for j, cid in enumerate(pt.get("criteria_ids") or []):
        c = db.get(QCriterion, cid)
        if c is None or c.status not in (QCriterionStatus.published, QCriterionStatus.superseded):
            raise qc.field_err(
                f"{fld}.criteria_ids[{j}]",
                "Name a published criterion version (criteria library).",
                "اختر نسخة معتمدة من معيار القبول.",
            )
        if c.project_ids and pr.id not in c.project_ids:
            raise qc.field_err(f"{fld}.criteria_ids[{j}]", "The criterion is not for this project.")
    code = pt.get("checklist_template_code")
    if code:
        t = db.scalar(
            select(ChecklistTemplate.id).where(
                ChecklistTemplate.template_code == code,
                ChecklistTemplate.kind == TemplateKind.quality,
                ChecklistTemplate.quality_type == "ir_inspection",
            )
        )
        if t is None:
            raise qc.field_err(
                f"{fld}.checklist_template_code",
                "Name a quality checklist of type ir_inspection.",
                "اختر قائمة فحص جودة من نوع فحص طلب الفحص.",
            )
    ov = pt.get("rp_override")
    if ov:
        kind = QAssigneeKind(ov.get("assignee_kind"))
        if not ov.get("assignee"):
            raise qc.field_err(f"{fld}.rp_override", "Name the assignee.", "حدد المكلَّف.")
        pt["rp_override"] = {"assignee_kind": kind.value, "assignee": str(ov["assignee"])}
    nh = pt.get("notice_hours")
    if nh is not None and not 0 <= int(nh) <= 168:
        raise qc.field_err(f"{fld}.notice_hours", "0–168 hours.", "من 0 إلى 168 ساعة.")


def _set_points(db: Session, pr: Any, it: QItp, rows: list[dict[str, Any]], uid: Any) -> None:
    seqs = [int(r["seq"]) for r in rows]
    if len(seqs) != len(set(seqs)):
        raise qc.field_err("points", "Point seq values must be unique.", "يجب ألا تتكرر الأرقام.")
    for i, r in enumerate(rows):
        _check_point(db, pr, i, r)
    for old in points_of(db, it.id):
        db.delete(old)
    db.flush()
    for r in rows:
        db.add(
            QItpPoint(
                itp_id=it.id,
                seq=int(r["seq"]),
                activity_en=(r.get("activity_en") or "").strip(),
                activity_ar=(r.get("activity_ar") or "").strip(),
                characteristic_en=(r.get("characteristic_en") or "").strip(),
                characteristic_ar=(r.get("characteristic_ar") or "").strip(),
                point_type=QPointType(r["point_type"]),
                criteria_ids=list(r.get("criteria_ids") or []),
                acceptance_text_en=r.get("acceptance_text_en") or None,
                acceptance_text_ar=r.get("acceptance_text_ar") or None,
                reference=r.get("reference") or None,
                verifying_record=QVerifyingRecord(r.get("verifying_record") or "ir"),
                checklist_template_code=r.get("checklist_template_code") or None,
                test_type_codes=list(r.get("test_type_codes") or []),
                frequency_text=r.get("frequency_text") or None,
                frequency_qty=_dec(r.get("frequency_qty"), "frequency_qty"),
                frequency_unit=r.get("frequency_unit") or None,
                rp_override=r.get("rp_override") or None,
                notice_hours=r.get("notice_hours"),
                competence_code=r.get("competence_code") or None,
                created_by_user_id=uid,
            )
        )
    db.flush()


def completeness(db: Session, it: QItp) -> list[str]:
    """Q-ITP-02 problems (empty = complete)."""
    out: list[str] = []
    if not (it.title_en or "").strip() or not (it.title_ar or "").strip():
        out.append("Title in English and Arabic is required.")
    pts = points_of(db, it.id)
    if not pts:
        out.append("At least one point is required.")
    for pt in pts:
        if not (
            (pt.activity_en or pt.activity_ar) and (pt.characteristic_en or pt.characteristic_ar)
        ):
            out.append(f"Point {pt.seq}: activity and characteristic are required.")
        if not pt.criteria_ids and not (pt.acceptance_text_en or pt.acceptance_text_ar):
            out.append(f"Point {pt.seq}: give a criterion or acceptance text.")
    if pts and not any(pt.point_type in (QPointType.H, QPointType.W) for pt in pts):
        out.append("At least one Hold (H) or Witness (W) point is required.")
    if it.revision >= 1 and not (it.change_note or "").strip():
        out.append("A change note is required for revision 1 and later.")
    return out


# ---- writes ------------------------------------------------------------------------------------


def _audit(db: Session, p: Principal, it: QItp, action: AuditAction, **kw: Any) -> None:
    audit.record(
        db,
        action,
        p.actor(it.project_id),
        entity_type=EntityType.q_itp,
        entity_id=it.id,
        project_id=it.project_id,
        **kw,
    )


def _status(db: Session, p: Principal, it: QItp, to: QItpStatus, **details: Any) -> None:
    before = it.status
    it.status = to
    it.status_changed_at = now()
    it.updated_by_user_id = p.user.id
    db.flush()
    _audit(
        db,
        p,
        it,
        AuditAction.status_change,
        before={"status": before.value},
        after={"status": to.value},
        details={k: v for k, v in details.items() if v is not None} or None,
    )


def _author_grant(p: Principal, it_project: uuid.UUID, eng_id: uuid.UUID) -> None:
    g = p.require(it_project, C.itp_author)
    if not qc.covers(g, None, eng_id):
        raise forbidden_error("This contractor is outside your scope.")


def create(db: Session, p: Principal, project_id: uuid.UUID, body: dict[str, Any]) -> QItp:
    pr = qc.get_project(db, p, project_id)
    q1c.writable_construction(db, p, pr, RT)
    eng: ProjectEngagement = check_engagement(db, pr, body["engagement_id"])
    _author_grant(p, pr.id, eng.id)
    it = QItp(
        id=uuid.uuid4(),
        project_id=pr.id,
        family_id=uuid.uuid4(),
        revision=0,
        discipline=QDiscipline(body["discipline"]),
        engagement_id=eng.id,
        prepared_by_user_id=p.user.id,
        status=ST.draft,
        created_by_user_id=p.user.id,
    )
    _apply_header(it, body)
    _check_header(db, pr, it)
    db.add(it)
    db.flush()
    _set_points(db, pr, it, list(body.get("points") or []), p.user.id)
    _audit(db, p, it, AuditAction.create, after={"title": it.title_en, "discipline": it.discipline})
    return it


def _apply_header(it: QItp, body: dict[str, Any]) -> None:
    for k in HEADER_FIELDS:
        if k not in body or body[k] is None:
            continue
        v = body[k]
        if k == "discipline":
            v = QDiscipline(v)
        elif isinstance(v, str):
            v = v.strip()
        setattr(it, k, v)


def update(db: Session, p: Principal, itp_id: uuid.UUID, body: dict[str, Any]) -> QItp:
    it = get_itp(db, p, itp_id)
    pr = q1c.project(db, it.project_id)
    q1c.progress_writable(pr, p)
    _author_grant(p, pr.id, it.engagement_id)
    if it.status in (ST.approved, ST.superseded, ST.withdrawn, ST.rejected):
        raise _immutable()
    if it.status not in EDITABLE_STATES:
        raise invalid_transition("ITP", it.status, "edit")
    if (
        body.get("discipline")
        and it.itp_no is not None
        and QDiscipline(body["discipline"]) != it.discipline
    ):
        raise qc.field_err("discipline", "The discipline is fixed once the ITP is numbered.")
    if body.get("engagement_id") and body["engagement_id"] != it.engagement_id:
        if it.itp_no is not None:
            raise qc.field_err("engagement_id", "The contractor is fixed once numbered (Q-ITP-01).")
        eng = check_engagement(db, pr, body["engagement_id"])
        _author_grant(p, pr.id, eng.id)
        it.engagement_id = eng.id
    _apply_header(it, body)
    _check_header(db, pr, it)
    if body.get("points") is not None:
        _set_points(db, pr, it, list(body["points"]), p.user.id)
    it.updated_by_user_id = p.user.id
    db.flush()
    _audit(db, p, it, AuditAction.update, details={"fields": sorted(body)})
    return it


def submit(db: Session, p: Principal, itp_id: uuid.UUID) -> QItp:
    """Draft / Revise and Resubmit → Submitted (Q-ITP-02); numbered when it first leaves Draft."""
    it = get_itp(db, p, itp_id)
    pr = q1c.project(db, it.project_id)
    if it.revision == 0 and it.itp_no is None:
        q1c.writable_construction(db, p, pr, RT)
    else:
        q1c.progress_writable(pr, p)
    _author_grant(p, pr.id, it.engagement_id)
    if it.status in (ST.approved, ST.superseded, ST.withdrawn, ST.rejected):
        raise (
            _immutable()
            if it.status == ST.approved
            else invalid_transition("ITP", it.status, "submit")
        )
    if it.status not in EDITABLE_STATES:
        raise invalid_transition("ITP", it.status, "submit")
    problems = completeness(db, it)
    if problems:
        raise qc.err(
            422,
            ErrorCode.ITP_INCOMPLETE,
            "The ITP is not complete: " + " ".join(problems),
            "خطة الفحص غير مكتملة: العنوان بالعربية والإنجليزية، نقطة واحدة على الأقل، ولكل نقطة "
            "نشاط وخاصية ومعيار، ونقطة توقف أو شهادة واحدة على الأقل.",
            problems=problems,
        )
    if it.itp_no is None:
        it.itp_no = qnum.assign(db, pr, RT, disc=it.discipline.value)
    it.submitted_at = now()
    it.submitted_by_user_id = p.user.id
    _status(db, p, it, ST.submitted)
    _notify_submitted(db, pr, it)
    return it


def _notify_submitted(db: Session, pr: Any, it: QItp) -> None:
    res = rpm.resolve(db, pr, RT, "approve", ctx(it), record_id=it.id)
    qc.send(
        db,
        [u for u in res.users if u not in requesters(it)],
        f"{display_no(it)} submitted for approval",
        f"{display_no(it)} مقدمة للاعتماد",
        body_en=it.title_en,
        body_ar=it.title_ar,
        entity_type=EntityType.q_itp,
        entity_id=it.id,
        project_id=it.project_id,
        key=f"itp_submitted:{it.id}:{it.submitted_at}",
        path=f"/quality/itps/{it.id}",
    )


CODE_DECISION = {
    QApprovalCode.A: "approved",
    QApprovalCode.B: "approved_with_comments",
    QApprovalCode.C: "returned",
    QApprovalCode.D: "rejected",
}


def decide(
    db: Session,
    p: Principal,
    itp_id: uuid.UUID,
    code: QApprovalCode,
    comment: str | None,
    paper: dict[str, Any] | None = None,
) -> QItp:
    """Submitted → Approved (A / B) · Revise and Resubmit (C) · Rejected (D) by the responsible
    person for `itp.approve` (Q-RPM-03, -06, -07; §B.3.3)."""
    it = get_itp(db, p, itp_id)
    pr = q1c.project(db, it.project_id)
    q1c.progress_writable(pr, p)
    if it.status != ST.submitted:
        raise invalid_transition("ITP", it.status, f"decision {code.value}")
    code = QApprovalCode(code)
    text = (comment or "").strip() or None
    if code == QApprovalCode.B and not text:
        raise qc.field_err("comment", "Code B needs a comment.", "الرمز B يتطلب ملاحظة.")
    if code in (QApprovalCode.C, QApprovalCode.D):
        text = qc.reason(comment, 20, "comment")
    decision = CODE_DECISION[code]
    if paper:
        s = signoff.sign_paper(db, p, pr, RT, it.id, "approve", decision, text, paper, ctx(it))
    else:
        rule, capacity = rpm.check_signer(db, p, pr, RT, "approve", ctx(it), record_id=it.id)
        s = signoff.sign(db, p, pr, RT, it.id, "approve", decision, text, rule, capacity)
    it.approval_code = code
    it.decision_comment = text
    it.decided_at = now()
    if code in (QApprovalCode.A, QApprovalCode.B):
        prev = current_approved(db, it.family_id)
        if prev is not None and prev.id != it.id:
            prev.superseded_at = now()
            _status(db, p, prev, ST.superseded, superseded_by=str(it.id))
            links.add(db, pr.id, RT, it.id, RT, prev.id, QLinkKind.supersedes, p.user.id)
        it.approved_at = now()
        _status(db, p, it, ST.approved, code=code.value, signoff=str(s.id))
    elif code == QApprovalCode.C:
        _status(db, p, it, ST.revise_resubmit, code=code.value, comment=text)
    else:
        _status(db, p, it, ST.rejected, code=code.value, comment=text)
    qc.send(
        db,
        [u for u in (it.prepared_by_user_id, it.submitted_by_user_id) if u],
        f"{display_no(it)}: {label('approval_code', code)}",
        f"{display_no(it)}: {label('approval_code', code, True)}",
        body_en=text,
        body_ar=text,
        entity_type=EntityType.q_itp,
        entity_id=it.id,
        project_id=it.project_id,
        key=f"itp_decided:{it.id}:{s.id}",
        path=f"/quality/itps/{it.id}",
    )
    return it


def new_revision(db: Session, p: Principal, itp_id: uuid.UUID, change_note: str | None) -> QItp:
    """— → Draft: a new revision copied from the current Approved revision (Q-ITP-03)."""
    src = get_itp(db, p, itp_id)
    pr = q1c.project(db, src.project_id)
    q1c.writable_construction(db, p, pr, RT)
    _author_grant(p, pr.id, src.engagement_id)
    cur = current_approved(db, src.family_id)
    if cur is None:
        raise invalid_transition("ITP", src.status, "new revision")
    if (
        db.scalar(
            select(func.count())
            .select_from(QItp)
            .where(
                QItp.family_id == cur.family_id,
                QItp.status.in_([ST.draft, ST.submitted, ST.revise_resubmit]),
            )
        )
        or 0
    ):
        raise qc.err(
            409,
            ErrorCode.INVALID_TRANSITION,
            "A newer revision of this ITP is already being prepared.",
            "توجد مراجعة أحدث قيد الإعداد لهذه الخطة.",
        )
    last = max(r.revision for r in revisions(db, cur.family_id))
    it = QItp(
        id=uuid.uuid4(),
        project_id=cur.project_id,
        family_id=cur.family_id,
        itp_no=cur.itp_no,
        revision=last + 1,
        discipline=cur.discipline,
        engagement_id=cur.engagement_id,
        prepared_by_user_id=p.user.id,
        status=ST.draft,
        created_by_user_id=p.user.id,
        change_note=(change_note or "").strip() or None,
    )
    for k in HEADER_FIELDS:
        if k not in ("change_note", "discipline"):
            setattr(it, k, getattr(cur, k))
    db.add(it)
    db.flush()
    rows = [{f: getattr(pt, f) for f in POINT_FIELDS} for pt in points_of(db, cur.id)]
    for r in rows:
        r["point_type"] = r["point_type"].value
        r["verifying_record"] = r["verifying_record"].value
    _set_points(db, pr, it, rows, p.user.id)
    _audit(
        db, p, it, AuditAction.create, after={"revision_of": str(cur.id), "revision": it.revision}
    )
    return it


def withdraw(db: Session, p: Principal, itp_id: uuid.UUID, why: str | None) -> QItp:
    it = get_itp(db, p, itp_id)
    pr = q1c.project(db, it.project_id)
    q1c.progress_writable(pr, p)
    p.require(pr.id, C.quality_settings)
    if it.status != ST.approved:
        raise invalid_transition("ITP", it.status, "withdraw")
    text = qc.reason(why, 20)
    it.status_reason = text
    _status(db, p, it, ST.withdrawn, reason=text)
    return it


def delete_draft(db: Session, p: Principal, itp_id: uuid.UUID) -> None:
    it = get_itp(db, p, itp_id)
    pr = q1c.project(db, it.project_id)
    q1c.progress_writable(pr, p)
    if it.status != ST.draft or (p.user.id != it.prepared_by_user_id and not p.is_manager):
        raise invalid_transition("ITP", it.status, "delete")
    for pt in points_of(db, it.id):
        db.delete(pt)
    _audit(db, p, it, AuditAction.archive, details={"deleted_draft": True})
    db.delete(it)
    db.flush()


# ---- read --------------------------------------------------------------------------------------


def _crit(db: Session, ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    out = []
    for cid in ids or []:
        c = db.get(QCriterion, cid)
        if c is not None:
            out.append(
                {
                    "id": c.id,
                    "code": c.code,
                    "version": c.version,
                    "title_en": c.title_en,
                    "title_ar": c.title_ar,
                    "kind": c.kind,
                    "unit": c.unit,
                }
            )
    return out


def point_read(db: Session, pt: QItpPoint) -> dict[str, Any]:
    return {
        "id": pt.id,
        "seq": pt.seq,
        "activity_en": pt.activity_en,
        "activity_ar": pt.activity_ar,
        "characteristic_en": pt.characteristic_en,
        "characteristic_ar": pt.characteristic_ar,
        "point_type": pt.point_type,
        "criteria": _crit(db, pt.criteria_ids),
        "criteria_ids": list(pt.criteria_ids or []),
        "acceptance_text_en": pt.acceptance_text_en,
        "acceptance_text_ar": pt.acceptance_text_ar,
        "reference": pt.reference,
        "verifying_record": pt.verifying_record,
        "checklist_template_code": pt.checklist_template_code,
        "test_type_codes": list(pt.test_type_codes or []),
        "frequency_text": pt.frequency_text,
        "frequency_qty": str(pt.frequency_qty) if pt.frequency_qty is not None else None,
        "frequency_unit": pt.frequency_unit,
        "rp_override": pt.rp_override,
        "notice_hours": pt.notice_hours,
        "competence_code": pt.competence_code,
    }


def _eng(db: Session, eid: uuid.UUID | None) -> dict[str, Any] | None:
    e = db.get(ProjectEngagement, eid) if eid else None
    if e is None:
        return None
    return {
        "id": e.id,
        "short_code": e.contractor.short_code,
        "legal_name_en": e.contractor.legal_name_en,
        "legal_name_ar": e.contractor.legal_name_ar,
    }


def list_item(db: Session, it: QItp) -> dict[str, Any]:
    return {
        "id": it.id,
        "family_id": it.family_id,
        "itp_no": it.itp_no,
        "revision": it.revision,
        "display_no": display_no(it),
        "title_en": it.title_en,
        "title_ar": it.title_ar,
        "discipline": it.discipline,
        "engagement": _eng(db, it.engagement_id),
        "status": it.status,
        "approval_code": it.approval_code,
        "point_count": int(
            db.scalar(select(func.count()).select_from(QItpPoint).where(QItpPoint.itp_id == it.id))
            or 0
        ),
        "approved_at": it.approved_at,
        "updated_at": it.updated_at,
    }


def allowed_actions(db: Session, p: Principal, it: QItp) -> list[str]:
    out: list[str] = []
    if q1c.viewer(p, it.project_id):
        return out
    pr = q1c.project(db, it.project_id)
    author = qc.covers(p.grant(it.project_id, C.itp_author), None, it.engagement_id)
    if author and it.status in EDITABLE_STATES:
        out += ["edit", "submit"]
        if it.status == ST.draft and it.revision == 0 and it.itp_no is None:
            out.append("delete")
    if it.status == ST.submitted and rpm.resolves(
        db, p, pr, RT, "approve", ctx(it), record_id=it.id
    ):
        out.append("decide")
    if it.status == ST.submitted and p.grant(it.project_id, C.itp_approve) is not None:
        out.append("paper_signoff")
    if author and it.status == ST.approved:
        out.append("new_revision")
    if it.status == ST.approved and p.grant(it.project_id, C.quality_settings) is not None:
        out.append("withdraw")
    return out


def read(db: Session, p: Principal, it: QItp) -> dict[str, Any]:
    pr = q1c.project(db, it.project_id)
    hide = q1c.viewer(p, it.project_id)
    zones = [db.get(Zone, z) for z in it.zone_ids or []]
    systems = [db.get(QSystem, s) for s in it.system_ids or []]
    res = (
        rpm.resolve(db, pr, RT, "approve", ctx(it), record_id=it.id)
        if it.status == ST.submitted
        else None
    )
    return {
        **list_item(db, it),
        "project_id": it.project_id,
        "work_package_en": it.work_package_en,
        "work_package_ar": it.work_package_ar,
        "zones": [
            {"id": z.id, "code": z.code, "name_en": z.name_en, "name_ar": z.name_ar}
            for z in zones
            if z
        ],
        "systems": [
            {"id": s.id, "code": s.code, "name_en": s.name_en, "name_ar": s.name_ar}
            for s in systems
            if s
        ],
        "spec_refs": list(it.spec_refs or []),
        "code_refs": list(it.code_refs or []),
        "method_statement_ref": it.method_statement_ref,
        "change_note": it.change_note,
        "decision_comment": it.decision_comment,
        "prepared_by": q1c.user_ref(db, it.prepared_by_user_id, hide),
        "submitted_at": it.submitted_at,
        "submitted_by": q1c.user_ref(db, it.submitted_by_user_id, hide),
        "decided_at": it.decided_at,
        "status_reason": it.status_reason,
        "points": [point_read(db, pt) for pt in points_of(db, it.id)],
        "revisions": [
            {"id": r.id, "revision": r.revision, "status": r.status, "approved_at": r.approved_at}
            for r in revisions(db, it.family_id)
            if can_view(db, p, r)
        ],
        "responsible": [
            q1c.user_ref(db, u, hide)
            for u in sorted(res.users)
            if res and q1c.user_ref(db, u, hide)
        ]
        if res
        else [],
        "rp_not_set": bool(res is not None and res.rule is None),
        "signoffs": [
            signoff.read(db, s, show_scans=not hide) for s in signoff.signoffs_for(db, RT, it.id)
        ]
        if not hide
        else [],
        "links": links.links_for(db, p, RT, it.id),
        "allowed_actions": allowed_actions(db, p, it),
        "problems": completeness(db, it) if it.status in EDITABLE_STATES else [],
    }


def list_page(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    *,
    statuses: list[QItpStatus] | None = None,
    discipline: QDiscipline | None = None,
    engagement_id: uuid.UUID | None = None,
    current_only: bool = False,
    q: str | None = None,
) -> dict[str, Any]:
    pr = qc.get_project(db, p, project_id)
    if p.grant(pr.id, C.quality_view) is None and p.grant(pr.id, C.itp_author) is None:
        raise forbidden_error()
    stmt = select(QItp).where(QItp.project_id == pr.id)
    if statuses:
        stmt = stmt.where(QItp.status.in_(statuses))
    if discipline:
        stmt = stmt.where(QItp.discipline == discipline)
    if engagement_id:
        stmt = stmt.where(QItp.engagement_id == engagement_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            QItp.itp_no.ilike(like) | QItp.title_en.ilike(like) | QItp.title_ar.ilike(like)
        )
    rows = [r for r in db.scalars(stmt.order_by(QItp.itp_no, QItp.revision)) if can_view(db, p, r)]
    if current_only:
        latest: dict[uuid.UUID, QItp] = {}
        for r in rows:
            cur = latest.get(r.family_id)
            if cur is None or r.revision > cur.revision:
                latest[r.family_id] = r
        rows = sorted(latest.values(), key=lambda r: (r.itp_no or "~", r.created_at))
    total = len(rows)
    chunk = rows[(page - 1) * page_size : page * page_size]
    return {
        "items": [list_item(db, r) for r in chunk],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ---- coverage grid (Q-ITP-06) ------------------------------------------------------------------


def _cell(st: QIrStatus, round_result: str | None) -> str:
    if st == QIrStatus.approved:
        return "approved"
    if st == QIrStatus.approved_with_comments:
        return "approved_with_comments"
    if st in (QIrStatus.rejected, QIrStatus.reinspection_requested):
        return "rejected"
    if st == QIrStatus.witness_waived:
        return "waived"
    return "scheduled"


def coverage(db: Session, p: Principal, itp_id: uuid.UUID) -> dict[str, Any]:
    it = get_itp(db, p, itp_id)
    pts = points_of(db, it.id)
    irs = list(
        db.scalars(
            select(QIr)
            .where(
                QIr.itp_family_id == it.family_id,
                QIr.status.notin_([QIrStatus.draft, QIrStatus.cancelled, QIrStatus.voided]),
            )
            .order_by(QIr.submitted_at)
        )
    )
    keys: dict[str, str] = {}
    cells: dict[tuple[str, int], tuple[datetime, str, str | None]] = {}
    for ir in irs:
        keys.setdefault(ir.location_key, ir.location_ref)
        at = ir.submitted_at or ir.created_at
        for s in ir.point_seqs or []:
            prev = cells.get((ir.location_key, s))
            if prev is None or at >= prev[0]:
                cells[(ir.location_key, s)] = (at, _cell(ir.status, None), ir.ir_no)
    rows = []
    for k, ref in keys.items():
        rows.append(
            {
                "location_key": k,
                "location_ref": ref,
                "cells": [
                    {
                        "seq": pt.seq,
                        "state": cells[(k, pt.seq)][1] if (k, pt.seq) in cells else "not_started",
                        "ir_no": cells[(k, pt.seq)][2] if (k, pt.seq) in cells else None,
                    }
                    for pt in pts
                ],
            }
        )
    return {
        "itp_id": it.id,
        "points": [
            {
                "seq": pt.seq,
                "point_type": pt.point_type,
                "activity_en": pt.activity_en,
                "activity_ar": pt.activity_ar,
            }
            for pt in pts
        ],
        "rows": rows,
    }
