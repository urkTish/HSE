"""IR round decision, witness waiver and offline sync (spec 8-quality Q-IR-05, -06, -09, -10, -14,
Q-SHR-04, AC-Q1-09 … -12, -16, -18).

A decision needs the points' checklist responses (6d EXE-2 completeness), every criterion-linked
measurement, a photo when rejected and a comment when approved with comments. A checklist critical
failure or a failed criterion makes approval impossible (`IR_RESULT_INCONSISTENT`). Every
measurement with an instrument writes a `q_mte_usage` row (`MTE_NOT_CALIBRATED` warns or blocks).
A round recorded offline is checked again at sync; when a hold point was voided meanwhile, or an
instrument is now blocked, the round is kept as "needs confirmation" and is not counted as decided
until the inspector confirms it."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import local_date, now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ApiError, ErrorCode
from app.core.field_enums import ResponseOwnerType
from app.core.hse_enums import AttachmentOwner
from app.core.quality.common import (
    QCriterionKind,
    QNcrCategory,
    QNcrClass,
    QNcrSourceType,
    QVerdict,
    label,
)
from app.core.quality.q1 import (
    IR_MAX_PHOTOS,
    QIrCommentStatus,
    QIrResult,
    QIrStatus,
    QPointType,
)
from app.models import Project
from app.models.quality import QCriterion
from app.models.quality.q1 import QIr, QIrComment, QIrRound
from app.schemas.hse_common import ApiWarning
from app.services.common import invalid_transition
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc
from app.services.quality import criteria as qcrit
from app.services.quality import mte as qmte
from app.services.quality import settings as qs
from app.services.quality import signoff
from app.services.quality.q1 import checklists
from app.services.quality.q1 import common as q1c
from app.services.quality.q1 import ir as irs

C = Capability
ST = QIrStatus
R = QIrResult
RT = irs.RT
STEP = irs.STEP
NCR_CATEGORIES = (QNcrCategory.material, QNcrCategory.testing_failure)
RESULT_STATUS = {
    R.approved: ST.approved,
    R.approved_with_comments: ST.approved_with_comments,
    R.rejected: ST.rejected,
    R.not_ready: ST.rejected,
}


def _inconsistent(why_en: str, why_ar: str) -> ApiError:
    return qc.err(
        422,
        ErrorCode.IR_RESULT_INCONSISTENT,
        f"The result does not match the inspection: {why_en} (Q-IR-05).",
        f"النتيجة لا تتوافق مع الفحص: {why_ar}",
    )


def _responses(
    db: Session,
    p: Principal,
    pr: Project,
    ir: QIr,
    rnd: QIrRound,
    answers: dict[str, list[dict[str, Any]]],
    at: datetime,
    photo_ids: list[uuid.UUID],
    required: bool,
) -> tuple[dict[str, str], int]:
    """One 6d response per point that has a template; returns ({seq: response_id}, critical
    fails)."""
    out: dict[str, str] = {}
    crit = 0
    for pt in irs.points(db, ir):
        if not pt.checklist_template_code:
            continue
        given = answers.get(str(pt.seq)) or []
        if not given:
            if required:
                raise qc.field_err(
                    f"answers.{pt.seq}",
                    f"Point {pt.seq}: complete checklist {pt.checklist_template_code}.",
                    f"النقطة {pt.seq}: أكمل قائمة الفحص {pt.checklist_template_code}.",
                )
            continue
        t = checklists.template_for(db, pt.checklist_template_code, "ir_inspection", at)
        if t is None:
            raise qc.field_err(f"answers.{pt.seq}", "The point's checklist is not published.")
        r, sc = checklists.record(
            db,
            p.user.id,
            pr,
            ResponseOwnerType.q_ir_round,
            t,
            given,
            site_id=ir.site_id,
            zone_id=ir.zone_id,
            engagement_id=ir.engagement_id,
            completed_at=at,
            photo_ids=photo_ids,
            fld=f"answers.{pt.seq}",
        )
        out[str(pt.seq)] = str(r.id)
        crit += sc.critical_fails
    return out, crit


def _measurements(
    db: Session,
    p: Principal,
    pr: Project,
    ir: QIr,
    rows: list[dict[str, Any]],
    at: datetime,
    required: bool,
    warnings: list[ApiWarning],
) -> tuple[list[dict[str, Any]], int]:
    """Evaluate measurements against their pinned criterion versions; record M&TE usage."""
    out = []
    failed = 0
    need = {(pt.seq, cid) for pt in irs.points(db, ir) for cid in pt.criteria_ids or []}
    have = set()
    for i, m in enumerate(rows):
        seq = int(m.get("point_seq") or 0)
        cid = m.get("criterion_id")
        verdict = None
        reason_en = reason_ar = None
        c = db.get(QCriterion, uuid.UUID(str(cid))) if cid else None
        if cid and c is None:
            raise qc.field_err(f"measurements[{i}].criterion_id", "Unknown criterion version.")
        if c is not None:
            if c.kind in (QCriterionKind.pass_fail, QCriterionKind.text):
                vals = {"verdict": m.get("verdict")}
            else:
                vals = {"value": m.get("value"), **(m.get("values") or {})}
            v = qcrit.evaluate(c, vals)
            verdict, reason_en, reason_ar = v.verdict.value, v.reason_en, v.reason_ar
            if v.verdict == QVerdict.fail:
                failed += 1
            if v.verdict != QVerdict.not_evaluable or m.get("value") not in (None, ""):
                have.add((seq, c.id))
        mte_no = None
        if m.get("mte_id"):
            u, w = qmte.record_usage(
                db,
                pr,
                uuid.UUID(str(m["mte_id"])),
                RT,
                ir.id,
                p.user.id,
                at,
                f"{m.get('name') or (c.code if c else '')} = {m.get('value')}"[:200],
            )
            warnings += w
            from app.models.quality import QMteItem  # noqa: PLC0415

            mi = db.get(QMteItem, u.mte_id)
            mte_no = mi.mte_no if mi else None
        out.append(
            {
                "point_seq": seq,
                "name": (m.get("name") or (c.title_en if c else "") or "")[:120],
                "value": None if m.get("value") is None else str(m.get("value")),
                "unit": m.get("unit") or (c.unit if c else None),
                "criterion_id": str(c.id) if c else None,
                "criterion_code": c.code if c else None,
                "criterion_version": c.version if c else None,
                "mte_id": str(m["mte_id"]) if m.get("mte_id") else None,
                "mte_no": mte_no,
                "verdict": verdict,
                "reason_en": reason_en,
                "reason_ar": reason_ar,
            }
        )
    if required:
        missing = sorted({s for s, cid in need if (s, cid) not in have})
        if missing:
            raise qc.field_err(
                "measurements",
                f"Enter every criterion-linked measurement (points {missing}).",
                "أدخل جميع القياسات المرتبطة بمعايير القبول.",
            )
    return out, failed


def _offline_times(db: Session, p: Principal, pr: Project, recorded_at: datetime) -> None:
    from app.services.field import execution  # noqa: PLC0415

    execution.check_times(db, p, pr, recorded_at, now(), "recorded_at")


def _photos(
    db: Session, p: Principal, ir: QIr, rnd: QIrRound, photos: list[Any]
) -> list[uuid.UUID]:
    existing = q1c.attachment_ids(db, AttachmentOwner.q_ir_round, rnd.id)
    if len(existing) + len(photos) > IR_MAX_PHOTOS:
        raise qc.field_err(
            "photos", f"At most {IR_MAX_PHOTOS} photos per round.", "الحد الأقصى 20 صورة."
        )
    new = q1c.store_photos(
        db, AttachmentOwner.q_ir_round, rnd.id, ir.project_id, photos, p.user.id, "photos"
    )
    return existing + new


def decide(
    db: Session, p: Principal, ir_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QIr, list[ApiWarning], dict[str, Any]]:
    """Scheduled → Approved / Approved with Comments / Rejected (also for `not_ready`), and
    Witness Waived → the review result. 250 + RPM `ir.inspect` (or a paper sign-off)."""
    ir = irs.get_ir(db, p, ir_id)
    pr = q1c.project(db, ir.project_id)
    q1c.progress_writable(pr, p)
    rnd = irs.current(db, ir)
    cu = body.get("client_uuid")
    if cu is not None:
        dup = db.scalar(select(QIrRound).where(QIrRound.client_uuid == cu))
        if dup is not None:
            return irs.get_row(db, dup.ir_id), [], {}
    if ir.status not in (ST.scheduled, ST.witness_waived) or rnd is None:
        raise invalid_transition("IR", ir.status, body.get("result"))
    result = R(body["result"])
    review = ir.status == ST.witness_waived
    if result == R.waived or (review and result == R.not_ready):
        raise invalid_transition("IR", ir.status, result.value)
    paper = body.get("paper")
    recorded_at: datetime | None = body.get("recorded_at")
    at = recorded_at or now()
    if recorded_at is not None:
        _offline_times(db, p, pr, recorded_at)
    if paper:
        g = p.grant(pr.id, C.ir_inspect)
        if g is None or not qc.covers(g, ir.site_id, ir.engagement_id):
            raise forbidden_error("Recording a paper sign-off needs capability 250.")
    else:
        irs.check_resolver(db, p, pr, ir)
    warnings: list[ApiWarning] = []
    warnings += irs.competence_warnings(db, pr, ir, p.user.id) if not paper else []
    # Q-IR-08 / Q-IR-14: the hold the IR relied on must still be released
    hold = irs.hold_check(db, ir)
    if not hold.ok:
        if recorded_at is not None:
            return _needs_confirmation(db, p, ir, rnd, body, hold.blockers[0].detail_en, warnings)
        raise irs.hold_error(hold)
    if recorded_at is not None and qs.value(db, pr.id, "mte_use_policy") == "block":
        try:
            sp = db.begin_nested()
            _measurements(db, p, pr, ir, list(body.get("measurements") or []), at, False, [])
            sp.rollback()
        except ApiError as e:
            sp.rollback()
            if e.code == ErrorCode.MTE_NOT_CALIBRATED:
                return _needs_confirmation(db, p, ir, rnd, body, e.message, warnings)
            raise
    return _apply_decision(db, p, pr, ir, rnd, body, result, review, at, warnings)


def _apply_decision(
    db: Session,
    p: Principal,
    pr: Project,
    ir: QIr,
    rnd: QIrRound,
    body: dict[str, Any],
    result: QIrResult,
    review: bool,
    at: datetime,
    warnings: list[ApiWarning],
) -> tuple[QIr, list[ApiWarning], dict[str, Any]]:
    required = result != R.not_ready
    photo_ids = _photos(db, p, ir, rnd, list(body.get("photos") or []))
    responses: dict[str, str] = {}
    crit = 0
    if not review:
        responses, crit = _responses(
            db, p, pr, ir, rnd, dict(body.get("answers") or {}), at, photo_ids, required
        )
    measurements, failed = _measurements(
        db, p, pr, ir, list(body.get("measurements") or []), at, required and not review, warnings
    )
    comments = [
        c
        for c in body.get("comments") or []
        if (c.get("text_en") or c.get("text_ar") or "").strip()
    ]
    if result in (R.approved, R.approved_with_comments):
        if crit:
            raise _inconsistent(
                f"{crit} critical checklist item(s) failed", "فشل بند حرج في قائمة الفحص"
            )
        if failed:
            raise _inconsistent(
                f"{failed} measurement(s) fail their criterion", "قياس لا يحقق معيار القبول"
            )
        if result == R.approved_with_comments and not comments:
            raise qc.field_err(
                "comments",
                "Approved with comments needs at least one comment.",
                "أضف ملاحظة واحدة على الأقل.",
            )
    category = body.get("reject_category")
    extra: dict[str, Any] = {}
    if result == R.rejected:
        if not photo_ids:
            raise qc.err(
                422,
                ErrorCode.EVIDENCE_REQUIRED,
                "A rejected round needs at least one photo (Q-IR-05).",
                "الرفض يتطلب صورة واحدة على الأقل.",
            )
        if not category:
            raise qc.field_err(
                "reject_category",
                "Choose the reason category of the rejection.",
                "اختر فئة سبب الرفض.",
            )
        category = QNcrCategory(category)
        must = rnd.round_no >= 2 or category in NCR_CATEGORIES
        if must and not body.get("raise_ncr"):
            raise qc.err(
                422,
                ErrorCode.NCR_REQUIRED,
                "An NCR is required: the IR was rejected again, or for a material or testing "
                "failure (Q-IR-06). Tick 'Raise NCR'.",
                "يلزم رفع تقرير عدم مطابقة لهذا الرفض.",
            )
        extra["ncr_prompt"] = True
    decision = result.value
    text = (body.get("comment") or "").strip() or None
    if result in (R.rejected, R.not_ready):
        text = qc.reason(body.get("comment"), 10, "comment")
    paper = body.get("paper")
    if paper:
        s = signoff.sign_paper(
            db,
            p,
            pr,
            RT,
            ir.id,
            STEP,
            decision,
            text,
            paper,
            irs.ctx(db, ir),
            qualifier=ir.governing_type.value,
        )
    else:
        rule, capacity = irs.check_resolver(db, p, pr, ir)
        s = signoff.sign(db, p, pr, RT, ir.id, STEP, decision, text, rule, capacity)
    if review:
        rnd.review_result = result
        rnd.reviewed_at = at
    else:
        rnd.result = result
        rnd.responses = responses
        rnd.attended_at = rnd.attended_at or at
    rnd.inspected_at = rnd.inspected_at or at
    rnd.measurements = [*(rnd.measurements or []), *measurements] if review else measurements
    rnd.reject_category = category if result == R.rejected else None
    rnd.comment = text
    rnd.close_comments_before_next_hold = (
        bool(body.get("close_comments_before_next_hold")) and result == R.approved_with_comments
    )
    rnd.signoff_id = s.id
    rnd.decided_by_user_id = p.user.id
    rnd.decided_date = local_date(at, qc.tz(pr))
    rnd.client_uuid = body.get("client_uuid") or rnd.client_uuid
    rnd.inspector_id = rnd.inspector_id if paper else p.user.id
    rnd.needs_confirmation = False
    rnd.pending_decision = None
    if body.get("recorded_at"):
        rnd.recorded_offline_at = body["recorded_at"]
    rnd.warnings = [w.model_dump() for w in warnings]
    ir.decided_at = at
    ir.decided_date = rnd.decided_date
    ir.reblocked_at = None
    days = int(qs.value(db, pr.id, "ir_comment_close_days"))
    for c in comments:
        db.add(
            QIrComment(
                ir_id=ir.id,
                round_id=rnd.id,
                project_id=ir.project_id,
                text_en=(c.get("text_en") or "").strip() or None,
                text_ar=(c.get("text_ar") or "").strip() or None,
                status=QIrCommentStatus.open,
                due_on=rnd.decided_date + timedelta(days=days),
                created_by_user_id=p.user.id,
            )
        )
    irs.set_status(
        db, p, ir, RESULT_STATUS[result], result=result.value, round=rnd.round_no, signoff=str(s.id)
    )
    if result == R.rejected and body.get("raise_ncr"):
        n = raise_ncr(db, p, pr, ir, rnd, body.get("ncr_owner_id"), category)
        extra["ncr_id"] = str(n.id)
    if result == R.rejected:
        extra["ncr_required_next"] = True  # a second rejection needs an NCR
    _notify_decided(db, pr, ir, result)
    return ir, warnings, extra


def raise_ncr(
    db: Session, p: Principal, pr: Project, ir: QIr, rnd: QIrRound, owner_id: Any, category: Any
) -> Any:
    """Q-IR-06: "Raise NCR" from a rejected round (source `ir`, minor proposed, category from the
    rejection); owner = the named user or the requester."""
    from app.services.quality.ncr import core  # noqa: PLC0415

    p.require(pr.id, C.ncr_raise)
    owner = uuid.UUID(str(owner_id)) if owner_id else ir.requested_by_user_id
    return core.auto_raise(
        db,
        pr,
        QNcrSourceType.ir,
        ir.id,
        raised_by=p.user.id,
        owner_id=owner,
        classification=QNcrClass.minor,
        category=QNcrCategory(category) if category else QNcrCategory.workmanship,
        title=f"{ir.ir_no} round {rnd.round_no} rejected — {ir.location_ref}"[:150],
    )


def _notify_decided(db: Session, pr: Project, ir: QIr, result: QIrResult) -> None:
    from app.services.quality.ncr import core  # noqa: PLC0415

    to = {ir.requested_by_user_id} | core.engagement_contacts(db, pr, ir.engagement_id)
    qc.send(
        db,
        to,
        f"{ir.ir_no}: {label('ir_result', result)}",
        f"{ir.ir_no}: {label('ir_result', result, True)}",
        body_en=ir.location_ref,
        body_ar=ir.location_ref,
        entity_type=EntityType.q_ir,
        entity_id=ir.id,
        project_id=ir.project_id,
        key=f"ir_decided:{ir.id}:{ir.current_round}:{result.value}",
        path=f"/quality/inspection-requests/{ir.id}",
    )


def _needs_confirmation(
    db: Session,
    p: Principal,
    ir: QIr,
    rnd: QIrRound,
    body: dict[str, Any],
    why: str,
    warnings: list[ApiWarning],
) -> tuple[QIr, list[ApiWarning], dict[str, Any]]:
    """Q-IR-14: keep the offline round for the inspector to confirm; it is not decided."""
    data = {k: v for k, v in body.items() if k != "photos"}
    data = _jsonable(data)
    photo_ids = _photos(db, p, ir, rnd, list(body.get("photos") or []))
    rnd.needs_confirmation = True
    rnd.pending_decision = {**data, "photo_ids": [str(x) for x in photo_ids], "conflict": why}
    rnd.recorded_offline_at = body.get("recorded_at")
    rnd.client_uuid = body.get("client_uuid") or rnd.client_uuid
    rnd.inspector_id = p.user.id
    w = qc.warning(
        "IR_NEEDS_CONFIRMATION",
        f"Recorded offline; a check changed since then ({why}). Confirm the round when the "
        "conflict is resolved.",
        "سُجّلت الجولة دون اتصال وتغيّر أحد الشروط منذ ذلك الحين؛ أكّد الجولة بعد حل التعارض.",
    )
    warnings.append(w)
    rnd.warnings = [x.model_dump() for x in warnings]
    db.flush()
    irs._audit(db, p, ir, AuditAction.update, details={"offline_round_needs_confirmation": why})
    return ir, warnings, {}


def _jsonable(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if hasattr(v, "value"):
        return v.value
    return v if isinstance(v, (str, int, float, bool)) or v is None else str(v)


def confirm_offline(
    db: Session, p: Principal, ir_id: uuid.UUID, discard: bool = False
) -> tuple[QIr, list[ApiWarning], dict[str, Any]]:
    """The inspector confirms (or discards) a round kept as "needs confirmation"; the hold and
    M&TE checks run again now."""
    ir = irs.get_ir(db, p, ir_id)
    pr = q1c.project(db, ir.project_id)
    q1c.progress_writable(pr, p)
    rnd = irs.current(db, ir)
    if rnd is None or not rnd.needs_confirmation or not rnd.pending_decision:
        raise invalid_transition("IR round", "decided", "confirmed")
    irs.check_resolver(db, p, pr, ir)
    if discard:
        rnd.needs_confirmation = False
        rnd.pending_decision = None
        db.flush()
        irs._audit(db, p, ir, AuditAction.update, details={"offline_round_discarded": True})
        return ir, [], {}
    hold = irs.hold_check(db, ir)
    if not hold.ok:
        raise irs.hold_error(hold)
    body = dict(rnd.pending_decision)
    body.pop("conflict", None)
    body.pop("photo_ids", None)
    body.pop("client_uuid", None)
    recorded = body.pop("recorded_at", None)
    at = datetime.fromisoformat(recorded) if isinstance(recorded, str) else now()
    body["photos"] = []
    return _apply_decision(
        db, p, pr, ir, rnd, body, R(body["result"]), ir.status == ST.witness_waived, at, []
    )


def waive(
    db: Session, p: Principal, ir_id: uuid.UUID, body: dict[str, Any]
) -> tuple[QIr, list[ApiWarning]]:
    """Scheduled → Witness Waived (249): governing W only (H → HOLD_NOT_WAIVABLE), no attendance
    by scheduled_at + `witness_wait_minutes`; the requester's own checklist and ≥ 1 photo."""
    ir = irs.get_ir(db, p, ir_id)
    pr = q1c.project(db, ir.project_id)
    q1c.progress_writable(pr, p)
    rnd = irs.current(db, ir)
    if ir.governing_type == QPointType.H:
        raise qc.err(
            422,
            ErrorCode.HOLD_NOT_WAIVABLE,
            "Hold points are never waived; the responsible person must inspect (Q-IR-09).",
            "لا يجوز التنازل عن نقاط التوقف؛ يجب أن يفحص الشخص المسؤول.",
        )
    if (
        ir.status != ST.scheduled
        or rnd is None
        or rnd.scheduled_at is None
        or ir.governing_type != QPointType.W
    ):
        raise invalid_transition("IR", ir.status, "witness_waived")
    g = p.require(pr.id, C.ir_submit)
    if p.user.id != ir.requested_by_user_id and not qc.covers(g, ir.site_id, ir.engagement_id):
        raise forbidden_error()
    wait = int(qs.value(db, pr.id, "witness_wait_minutes"))
    at = body.get("recorded_at") or now()
    if rnd.attended_at is not None and rnd.attended_at <= rnd.scheduled_at + timedelta(
        minutes=wait
    ):
        raise invalid_transition("IR", "attended", "witness_waived")
    if at < rnd.scheduled_at + timedelta(minutes=wait):
        raise qc.err(
            422,
            ErrorCode.WITNESS_WAIT_NOT_OVER,
            f"The witness may still come: wait until "
            f"{(rnd.scheduled_at + timedelta(minutes=wait)).isoformat(timespec='minutes')} "
            "(Q-IR-10).",
            f"لم تنته مدة انتظار الشاهد ({wait} دقيقة).",
        )
    photos = list(body.get("photos") or [])
    if not photos:
        raise qc.err(
            422,
            ErrorCode.EVIDENCE_REQUIRED,
            "A waived witness needs at least one photo (Q-IR-10).",
            "التنازل يتطلب صورة واحدة على الأقل.",
        )
    photo_ids = _photos(db, p, ir, rnd, photos)
    responses, _crit = _responses(
        db, p, pr, ir, rnd, dict(body.get("answers") or {}), at, photo_ids, True
    )
    warnings: list[ApiWarning] = []
    measurements, _failed = _measurements(
        db, p, pr, ir, list(body.get("measurements") or []), at, False, warnings
    )
    rnd.result = R.waived
    rnd.responses = responses
    rnd.measurements = measurements
    rnd.waived_by_user_id = p.user.id
    rnd.waived_at = at
    rnd.comment = (body.get("comment") or "").strip() or None
    irs.set_status(db, p, ir, ST.witness_waived, round=rnd.round_no)
    res = irs.resolvers(db, pr, ir)
    qc.send(
        db,
        [u for u in res.users if u not in irs.requesters(db, ir)],
        f"{ir.ir_no}: witness waived — review within "
        f"{qs.value(db, pr.id, 'witness_review_days')} days",
        f"{ir.ir_no}: تم التنازل عن الشهادة — راجع السجلات",
        entity_type=EntityType.q_ir,
        entity_id=ir.id,
        project_id=ir.project_id,
        key=f"ir_waived:{ir.id}:{rnd.round_no}",
        path=f"/quality/inspection-requests/{ir.id}",
    )
    return ir, warnings
