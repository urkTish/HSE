"""Fitness assessments (spec 6a-occupational-health §3.6, §4.3, FA-1…FA-16) and verification
of external certificates (§5.6, FV-1…FV-6), scans (P6-5) and the tiered reads (OH-2).

Site-clinic records saved by the examiner's linked user are signed on save (step-up re-auth,
DECISIONS #56) and verified (`site_clinic_record`); other recorders leave them Awaiting Sign-off.
External certificates go Draft → Submitted (scan) → Accepted (reviewer ≠ submitter) and are in
force only once verified (FV-1)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.access_enums import WorkerIdType
from app.core.cert_enums import IdMatchResult, NameMatch, VerificationStatus
from app.core.clock import now, today
from app.core.enums import AuditAction, AuditResult, EntityType, NotificationKind, Role
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import AttachmentOwner
from app.core.med_enums import (
    AssessmentAction,
    AssessmentSource,
    AssessmentStatus,
    AssessmentType,
    ExaminerClass,
    FitnessOutcome,
    FitnessVerificationMethod,
    FitnessVerificationOutcome,
    HoldReason,
    HoldStatus,
    ReferralStatus,
    RestrictionCode,
)
from app.models import (
    Attachment,
    Deployment,
    FitnessAssessment,
    FitnessHold,
    FitnessLine,
    FitnessReferral,
    FitnessVerification,
    MedicalExaminer,
    MedicalProvider,
    Project,
    ProjectEngagement,
    User,
    Worker,
)
from app.schemas.attachments import SignedUrlRead
from app.schemas.hse_common import ApiWarning
from app.schemas.medical import (
    FitnessAssessmentCreate,
    FitnessAssessmentPage,
    FitnessAssessmentRead,
    FitnessAssessmentTransition,
    FitnessAssessmentUpdate,
    FitnessLineInput,
    FitnessLineRead,
    FitnessScanUrlRequest,
    FitnessVerificationCreate,
    FitnessVerificationList,
    FitnessVerificationRead,
    RestrictionRead,
    RevokeInfo,
)
from app.services import audit
from app.services.access import common as acommon
from app.services.cert import common as cc
from app.services.common import invalid_transition, paginate
from app.services.hse_common import id_warnings, make_ref, next_seq
from app.services.med import alerts, common, engine, providers
from app.services.med import reference as ref
from app.services.permissions import Principal, deny, forbidden_error

C = common.C
S = AssessmentStatus
SRC = AssessmentSource
OUT = FitnessOutcome
VS = VerificationStatus
K = NotificationKind
LOCK_HOURS = 24
SKIP_SNAP = ("status_reason_enc",)

# ---- access --------------------------------------------------------------------------------------


def _dep(db: Session, a: FitnessAssessment) -> Deployment | None:
    return common.deployment(db, a.worker_id, a.project_id)


def get(db: Session, assessment_id: uuid.UUID) -> FitnessAssessment:
    a = db.get(FitnessAssessment, assessment_id)
    if a is None:
        raise not_found("Fitness assessment")
    return a


def _visible(db: Session, p: Principal, a: FitnessAssessment) -> int:
    """→ the caller's tier on the record (≥ 2: assessments are tier-2 data), else 404."""
    dep = _dep(db, a)
    t = common.tier(p, a.project_id, dep)
    involved = p.user.id in (a.recorded_by_user_id, a.submitted_by_user_id, a.signed_by_user_id)
    if t < 2 and not involved:
        raise deny(db, p, EntityType.fitness_assessment, a.id, a.project_id, "Fitness assessment")
    return max(t, 2)


# ---- reads ---------------------------------------------------------------------------------------


def restriction_read(x: dict[str, Any]) -> RestrictionRead:
    rc = RestrictionCode(x["code"])
    en, ar, _kind, _neg, review = ref.RESTRICTIONS[rc]
    return RestrictionRead(
        code=rc,
        value=x.get("value"),
        text=common.dec(bytes.fromhex(x["text_enc"])) if x.get("text_enc") else None,
        label_en=en,
        label_ar=ar,
        review_required=review,
    )


def line_read(ln: FitnessLine, a: FitnessAssessment, c: engine.Ctx, tier: int) -> FitnessLineRead:
    vu, factor = engine.effective_until(c, engine.Row(ln, a))
    out = FitnessLineRead(
        id=ln.id,
        code=ln.code,
        valid_until=ln.valid_until,
        effective_valid_until=vu,
        line_state=ln.line_state,
    )
    if tier >= 2:
        out.outcome = ln.outcome
        out.restrictions = [restriction_read(x) for x in ln.restrictions or []]
        out.restriction_review_date = ln.restriction_review_date
        out.unfit_review_date = ln.unfit_review_date
        out.printed_next_due = ln.printed_next_due
        out.limiting_factor = factor
    return out


def _lines(db: Session, a: FitnessAssessment) -> list[FitnessLine]:
    return list(
        db.scalars(
            select(FitnessLine).where(FitnessLine.assessment_id == a.id).order_by(FitnessLine.code)
        )
    )


def _allowed(db: Session, p: Principal, a: FitnessAssessment, tier: int) -> list[AssessmentAction]:
    out: list[AssessmentAction] = []
    sc = p.projects.get(a.project_id)
    if sc is not None and sc.read_only:
        return out
    x = db.get(MedicalExaminer, a.examiner_id)
    linked = x is not None and x.user_id == p.user.id
    review = p.grant(a.project_id, C.fitness_review) is not None
    if a.status in (S.draft, S.awaiting_signoff) and a.source == SRC.site_clinic and linked:
        out.append(AssessmentAction.sign)
    if a.status == S.awaiting_signoff and linked:
        out.append(AssessmentAction.return_)
    submitter = p.grant(a.project_id, C.fitness_submit_external) is not None
    if a.status == S.draft and a.source != SRC.site_clinic and submitter:
        out.append(AssessmentAction.submit)
    if a.status == S.submitted and review and a.submitted_by_user_id != p.user.id:
        out += [AssessmentAction.accept, AssessmentAction.reject, AssessmentAction.return_]
    if a.status == S.accepted and tier >= 3:
        out.append(AssessmentAction.revoke)
    return out


def read_model(
    db: Session,
    p: Principal | None,
    a: FitnessAssessment,
    tier: int | None = None,
    audit_read: bool = True,
) -> FitnessAssessmentRead:
    dep = _dep(db, a)
    t = tier if tier is not None else common.tier(p, a.project_id, dep)
    c = engine.ctx_for(db, a.project_id)
    w = db.get(Worker, a.worker_id)
    assert w is not None  # noqa: S101
    eng = db.get(ProjectEngagement, a.engagement_id) if a.engagement_id else None
    out = FitnessAssessmentRead(
        id=a.id,
        tier=common.tier_enum(t),
        assessment_no=a.assessment_no,
        worker=common.worker_ref(w, common.names(p, a.project_id)),
        project_id=a.project_id,
        engagement_short_code=eng.contractor.short_code if eng else None,
        source=a.source,
        status=a.status,
        examined_on=a.examined_on,
        certificate_no=a.certificate_no,
        lines=[line_read(ln, a, c, t) for ln in _lines(db, a)],
        purpose_notice_given=a.purpose_notice_given,
        historic=a.historic,
        accepted_at=a.accepted_at,
        has_scan=a.scan_attachment_id is not None and a.scan_deleted_at is None,
    )
    out.signed_by = common.user_ref(db, a.signed_by_user_id)
    out.signed_at = a.signed_at
    out.recorded_by = common.user_ref(db, a.recorded_by_user_id)
    out.submitted_by = common.user_ref(db, a.submitted_by_user_id)
    out.submitted_at = a.submitted_at
    fields = ["outcome", "restrictions", "status"]
    if t >= 3:
        pv = db.get(MedicalProvider, a.provider_id)
        x = db.get(MedicalExaminer, a.examiner_id)
        out.assessment_type = a.assessment_type
        out.provider = common.provider_ref(pv) if pv else None
        out.examiner = common.examiner_ref(x) if x else None
        out.verification_status = a.verification_status
        out.verification_due_on = a.verification_due_on
        if a.related_hold_id:
            h = db.get(FitnessHold, a.related_hold_id)
            out.related_hold_no = h.hold_no if h else None
        if a.related_referral_id:
            r = db.get(FitnessReferral, a.related_referral_id)
            out.related_referral_no = r.referral_no if r else None
        out.name_as_printed = a.name_as_printed
        out.name_match = a.name_match
        out.id_match_result = a.id_match_result
        out.clinical_data_present = a.clinical_data_present
        out.status_reason = common.dec(a.status_reason_enc)
        out.reviewed_by = common.user_ref(db, a.reviewed_by_user_id)
        out.reviewed_at = a.reviewed_at
        if a.revoked_at is not None:
            out.revoke = RevokeInfo(
                reason=common.dec(a.status_reason_enc),
                code=a.revoke_code,
                by=common.user_ref(db, a.revoked_by_user_id),
                at=a.revoked_at,
            )
        fields += ["assessment_type", "provider", "examiner", "verification_status"]
    if p is not None:
        out.allowed_actions = _allowed(db, p, a, t)
        if audit_read:
            common.sensitive_read(db, p, EntityType.fitness_assessment, a.id, a.project_id, fields)
    return out


def read(db: Session, p: Principal, assessment_id: uuid.UUID) -> FitnessAssessmentRead:
    a = get(db, assessment_id)
    return read_model(db, p, a, _visible(db, p, a))


def list_assessments(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    q: str | None,
    status: list[AssessmentStatus] | None,
    source: list[AssessmentSource] | None,
    assessment_type: list[AssessmentType] | None,
    verification_status: list[VerificationStatus] | None,
    worker_id: uuid.UUID | None,
    awaiting_signoff_mine: bool,
) -> FitnessAssessmentPage:
    common.visible_project(db, p, project_id)
    g = p.grant(project_id, C.fitness_functional_view)
    if g is None:
        raise forbidden_error()
    t3 = p.grant(project_id, C.fitness_clinical_view) is not None
    stmt = (
        select(FitnessAssessment)
        .where(FitnessAssessment.project_id == project_id)
        .order_by(FitnessAssessment.created_at.desc())
    )
    if g.engagement_ids is not None:
        stmt = stmt.where(
            FitnessAssessment.engagement_id.in_(g.engagement_ids or {uuid.UUID(int=0)})
        )
    if q:
        sub = select(Worker.id).where(Worker.worker_no.ilike(f"%{q}%"))
        stmt = stmt.where(
            or_(
                FitnessAssessment.assessment_no.ilike(f"%{q}%"),
                FitnessAssessment.certificate_no.ilike(f"%{q}%"),
                FitnessAssessment.worker_id.in_(sub),
            )
        )
    if status:
        stmt = stmt.where(FitnessAssessment.status.in_(status))
    if source:
        stmt = stmt.where(FitnessAssessment.source.in_(source))
    if assessment_type and t3:
        stmt = stmt.where(FitnessAssessment.assessment_type.in_(assessment_type))
    if verification_status and t3:
        stmt = stmt.where(FitnessAssessment.verification_status.in_(verification_status))
    if worker_id is not None:
        stmt = stmt.where(FitnessAssessment.worker_id == worker_id)
    if awaiting_signoff_mine:
        x = providers.linked_examiner(db, p.user.id)
        stmt = stmt.where(
            FitnessAssessment.status == S.awaiting_signoff,
            FitnessAssessment.examiner_id == (x.id if x else uuid.UUID(int=0)),
        )
    rows, total = paginate(db, stmt, page, page_size)
    items = []
    for a in rows:
        dep = _dep(db, a)
        if g.site_ids is not None and not common.covers_dep(g, dep):
            continue
        items.append(read_model(db, p, a, common.tier(p, project_id, dep), audit_read=False))
    common.sensitive_read(
        db, p, EntityType.fitness_assessment, None, project_id, ["outcome", "restrictions"]
    )
    return FitnessAssessmentPage(items=items, total=total, page=page, page_size=page_size)


# ---- validation (FA-1…FA-12) ---------------------------------------------------------------------


@dataclass
class Prepared:
    lines: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[ApiWarning] = field(default_factory=list)


def _e(code: ErrorCode, en: str, ar: str, status: int = 422, **meta: Any) -> ApiError:
    return common.err(status, code, en, ar, **meta)


def _restrictions(ln: FitnessLineInput, i: int, warnings: list[ApiWarning]) -> list[dict[str, Any]]:
    out = []
    for r in ln.restrictions:
        kind = ref.RESTRICTIONS[r.code][2]
        item: dict[str, Any] = {"code": r.code.value}
        if kind == "int_kg":
            if r.value is None or not 5 <= r.value <= 25:
                raise validation_error(f"lines[{i}].restrictions", "Lifting limit 5–25 kg.")
            item["value"] = r.value
        elif r.value is not None:
            raise validation_error(f"lines[{i}].restrictions", "No value for this restriction.")
        if kind == "text":
            if not r.text or len(r.text) > 100:
                raise validation_error(
                    f"lines[{i}].restrictions", "Describe the functional limit (≤ 100 chars)."
                )
            enc = common.enc(r.text)
            item["text_enc"] = enc.hex() if enc else None
            warnings.extend(id_warnings(**{f"lines[{i}].restrictions.text": r.text}))
        elif r.text:
            raise validation_error(f"lines[{i}].restrictions", "No text for this restriction.")
        out.append(item)
    return out


def _second_opinion(
    db: Session, worker_id: uuid.UUID, code: str, x: MedicalExaminer, at: datetime
) -> None:
    """FA-12: after a governing permanently_unfit line, a fit line needs another occupational
    physician."""
    wf = engine.load_one(db, worker_id)
    gov = engine.governing(wf.lines.get(code, []), at)
    if gov is None or gov.line.outcome != OUT.permanently_unfit:
        return
    if x.classification != ExaminerClass.occupational_physician or x.id == gov.a.examiner_id:
        raise _e(
            ErrorCode.SECOND_OPINION_REQUIRED,
            "A different occupational physician must clear a permanently unfit outcome.",
            "يجب أن يعتمد طبيب صحة مهنية آخر إلغاء عدم اللياقة النهائي.",
            line_code=code,
        )


def prepare(
    db: Session,
    p: Principal | None,
    project_id: uuid.UUID,
    worker_id: uuid.UUID,
    source: AssessmentSource,
    pv: MedicalProvider,
    x: MedicalExaminer,
    examined_on: Any,
    lines: list[FitnessLineInput],
    historic: bool = False,
) -> Prepared:
    s = common.settings(db, project_id)
    d = today()
    out = Prepared()
    if examined_on > d:
        raise validation_error("examined_on", "The examination date cannot be in the future.")
    if source == SRC.site_clinic and examined_on < d - timedelta(
        days=s.assessment_backdate_max_days
    ):
        raise _e(
            ErrorCode.BACKDATED_ASSESSMENT,
            f"Site-clinic records may be back-dated by {s.assessment_backdate_max_days} days "
            "at most.",
            f"لا يجوز تسجيل فحص سابق بأكثر من {s.assessment_backdate_max_days} أيام.",
        )
    seen: set[str] = set()
    all_expired = True
    for i, ln in enumerate(lines):
        if ln.code in seen:
            raise _e(
                ErrorCode.DUPLICATE_CODE_LINE,
                "One line per fitness code.",
                "بند واحد لكل رمز.",
                line_code=ln.code,
            )
        seen.add(ln.code)
        fc = common.code(db, ln.code)
        if fc is None or not fc.active:
            raise validation_error(f"lines[{i}].code", "Unknown or inactive fitness code.")
        bad = providers.unacceptable(db, pv, fc, worker_id, project_id, examined_on)
        if bad is not None:
            raise providers.unacceptable_error(bad, ln.code)
        prob = providers.examiner_problem(x, pv, fc, examined_on)
        if prob is not None:
            raise providers.examiner_error(prob, ln.code)
        rs = _restrictions(ln, i, out.warnings)
        if ln.outcome == OUT.fit_with_restrictions and not rs:
            raise _e(
                ErrorCode.RESTRICTIONS_REQUIRED,
                "Give at least one functional restriction.",
                "أدخل قيداً وظيفياً واحداً على الأقل.",
                line_code=ln.code,
            )
        if ln.outcome != OUT.fit_with_restrictions and rs:
            raise _e(
                ErrorCode.RESTRICTIONS_NOT_ALLOWED,
                "Restrictions apply only to fit with restrictions.",
                "القيود تخص نتيجة لائق مع قيود فقط.",
                line_code=ln.code,
            )
        needs_review = any(ref.review_required(r["code"]) for r in rs)
        review = ln.restriction_review_date
        if needs_review and (
            review is None
            or review <= examined_on
            or review > examined_on + timedelta(days=s.restriction_review_max_days)
        ):
            raise _e(
                ErrorCode.REVIEW_DATE_INVALID,
                f"Set a restriction review date within {s.restriction_review_max_days} days.",
                f"حدد تاريخ مراجعة القيود خلال {s.restriction_review_max_days} يوماً.",
                line_code=ln.code,
            )
        if not needs_review:
            review = None
        unfit_review = ln.unfit_review_date
        if ln.outcome == OUT.temporarily_unfit:
            if (
                unfit_review is None
                or unfit_review <= examined_on
                or unfit_review > examined_on + timedelta(days=s.unfit_review_max_days)
            ):
                raise _e(
                    ErrorCode.REVIEW_DATE_INVALID,
                    f"Set a reassessment date within {s.unfit_review_max_days} days.",
                    f"حدد تاريخ إعادة التقييم خلال {s.unfit_review_max_days} يوماً.",
                    line_code=ln.code,
                )
        else:
            unfit_review = None
        if (
            ln.outcome == OUT.permanently_unfit
            and x.classification != ExaminerClass.occupational_physician
        ):
            raise providers.examiner_error(ErrorCode.EXAMINER_NOT_QUALIFIED, ln.code)
        if ln.printed_next_due is not None and ln.printed_next_due <= examined_on:
            raise validation_error(f"lines[{i}].printed_next_due", "Must be after examined_on.")
        if ln.outcome in ref.FIT:
            _second_opinion(db, worker_id, ln.code, x, now())
        vu, factor = engine.stored_validity(
            fc, examined_on, ln.outcome, rs, review, ln.printed_next_due
        )
        if vu is None or vu >= d:
            all_expired = False
        out.lines.append(
            {
                "code": ln.code,
                "outcome": ln.outcome,
                "restrictions": rs,
                "restriction_codes": [r["code"] for r in rs],
                "restriction_review_date": review,
                "unfit_review_date": unfit_review,
                "printed_next_due": ln.printed_next_due,
                "valid_until": vu,
                "limiting_factor": factor,
            }
        )
    if source == SRC.external_certificate and all_expired and not historic:
        raise _e(
            ErrorCode.FITNESS_ALREADY_EXPIRED,
            "Every line of this certificate has already expired.",
            "انتهت صلاحية جميع بنود هذه الشهادة.",
        )
    return out


def _cert_unique(
    db: Session,
    p: Principal | None,
    pv: MedicalProvider,
    cert_no: str,
    worker_id: uuid.UUID,
    project_id: uuid.UUID,
    self_id: uuid.UUID | None = None,
) -> None:
    """FA-10: (provider, certificate_no) unique; another worker → 409 CERT_NO_REUSED."""
    other = db.scalar(
        select(FitnessAssessment).where(
            FitnessAssessment.provider_id == pv.id,
            FitnessAssessment.certificate_no == cert_no,
            FitnessAssessment.id != (self_id or uuid.UUID(int=0)),
        )
    )
    if other is None:
        return
    if other.worker_id != worker_id:
        alerts.send(
            db,
            alerts.oh(db, project_id),
            K.fitness_cert_no_reused,
            f"Certificate number {cert_no} ({pv.provider_code}) presented for another worker",
            f"رقم الشهادة {cert_no} ({pv.provider_code}) قُدم لعامل آخر",
            project_id,
            email=False,
        )
        raise _e(
            ErrorCode.CERT_NO_REUSED,
            "This certificate number belongs to another worker.",
            "رقم الشهادة هذا يخص عاملاً آخر.",
            409,
        )
    raise _e(ErrorCode.CERT_EXISTS, "This certificate is already recorded.", "الشهادة مسجلة.", 409)


def _id_match(
    db: Session, p: Principal, w: Worker, typed: str | None, project_id: uuid.UUID
) -> IdMatchResult:
    if not typed:
        return IdMatchResult.not_shown
    id_type = w.id_type or WorkerIdType.iqama
    try:
        bidx = acommon.blind_index(id_type, typed, w.passport_country)
    except Exception:
        bidx = ""
    if bidx and w.id_number_bidx and bidx == w.id_number_bidx:
        return IdMatchResult.matched
    audit.record(
        db,
        AuditAction.update,
        p.actor(project_id),
        entity_type=EntityType.fitness_assessment,
        entity_id=w.id,
        project_id=project_id,
        details={
            "cert_id_mismatch": acommon.mask_worker_id(id_type, typed),
            "worker_no": w.worker_no,
        },
        result=AuditResult.failed,
        defer=True,
    )
    raise ApiError(
        422,
        ErrorCode.CERT_ID_MISMATCH,
        "The ID number on the certificate does not match this worker.",
        "رقم الهوية في الشهادة لا يطابق هذا العامل.",
        meta={"field": "id_on_card"},
    )


def _name_match(printed: str | None, w: Worker) -> NameMatch | None:
    if not printed:
        return None
    from app.services.cert.personnel import name_match  # noqa: PLC0415

    return name_match(printed, w)


def _related(
    db: Session, body: FitnessAssessmentCreate, worker_id: uuid.UUID, lines: list[dict[str, Any]]
) -> None:
    """FA-5: return_to_work → an Active rtw/heat hold; referral → an Open referral; GEN-FIT line
    examined on or after the start date."""
    bad = ApiError(
        422,
        ErrorCode.HOLD_REFERENCE_INVALID,
        "Reference the worker's active hold or open referral and include a GEN-FIT line examined "
        "on or after its start.",
        "اربط الإيقاف الساري أو الإحالة المفتوحة للعامل وأضف بند GEN-FIT بتاريخ لاحق لبدايتها.",
    )
    start: datetime | None = None
    if body.assessment_type == AssessmentType.return_to_work:
        h = db.get(FitnessHold, body.related_hold_id) if body.related_hold_id else None
        if (
            h is None
            or h.worker_id != worker_id
            or h.status != HoldStatus.active
            or h.reason
            not in (HoldReason.rtw_after_injury, HoldReason.heat_illness, HoldReason.manual)
        ):
            raise bad
        start = h.started_at
    elif body.assessment_type == AssessmentType.referral:
        r = db.get(FitnessReferral, body.related_referral_id) if body.related_referral_id else None
        h = db.get(FitnessHold, body.related_hold_id) if body.related_hold_id else None
        if r is not None:
            if r.worker_id != worker_id or r.status != ReferralStatus.open:
                raise bad
            start = r.raised_at
        elif h is not None and h.reason == HoldReason.manual and h.status == HoldStatus.active:
            start = h.started_at
        else:
            raise bad
    else:
        return
    if ref.GEN not in {x["code"] for x in lines} or body.examined_on < common.local_day(start):
        raise bad


def _engagement(db: Session, worker_id: uuid.UUID, project_id: uuid.UUID) -> uuid.UUID | None:
    dep = common.deployment(db, worker_id, project_id)
    return dep.engagement_id if dep else None


def _number(db: Session, project_id: uuid.UUID, prefix: str = "MFA") -> tuple[int, int, str, str]:
    pr = db.get(Project, project_id)
    assert pr is not None  # noqa: S101
    y = today().year
    seq = next_seq(db, FitnessAssessment, project_id, y)
    return y, seq, make_ref("MFA", pr.code, y, seq, 5), make_ref("MFC", pr.code, y, seq, 5)


def _write_lines(db: Session, a: FitnessAssessment, lines: list[dict[str, Any]]) -> None:
    for ln in _lines(db, a):
        db.delete(ln)
    db.flush()
    for x in lines:
        db.add(
            FitnessLine(
                id=uuid.uuid4(), assessment_id=a.id, worker_id=a.worker_id, alerts_sent=[], **x
            )
        )
    db.flush()


def create(
    db: Session, p: Principal, project_id: uuid.UUID, body: FitnessAssessmentCreate
) -> FitnessAssessmentRead:
    common.visible_project(db, p, project_id)
    if body.source == SRC.import_:
        raise validation_error("source", "Imported records are created by the import only.")
    cap = C.fitness_record_clinic if body.source == SRC.site_clinic else C.fitness_submit_external
    g = p.require(project_id, cap)
    dep = common.open_deployment(db, body.worker_id, project_id)
    if not common.covers_dep(g, dep):
        raise forbidden_error()
    if body.historic and p.grant(project_id, C.fitness_clinical_view) is None:
        raise forbidden_error("Only tier-3 users may attach a historic certificate.")
    if not body.purpose_notice_given:
        raise _e(
            ErrorCode.PURPOSE_NOTICE_REQUIRED,
            "Give the worker the purpose notice first (P6-3).",
            "قدّم إشعار الغرض للعامل أولاً.",
        )
    pv = common.provider_or_404(db, body.provider_id)
    x = common.examiner_or_404(db, body.examiner_id)
    w = common.worker(db, body.worker_id)
    if body.source == SRC.site_clinic and x.user_id is None:
        raise _e(
            ErrorCode.EXAMINER_NOT_LINKED,
            "This examiner cannot sign on the platform; record the findings as an external "
            "certificate with the scan.",
            "لا يمكن لهذا الفاحص التوقيع على المنصة؛ سجّل النتائج كشهادة خارجية مع نسخة الشهادة.",
        )
    prep = prepare(
        db,
        p,
        project_id,
        body.worker_id,
        body.source,
        pv,
        x,
        body.examined_on,
        body.lines,
        body.historic,
    )
    _related(db, body, body.worker_id, prep.lines)
    s = common.settings(db, project_id)
    y, seq, a_no, c_no = _number(db, project_id)
    signing = body.source == SRC.site_clinic and x.user_id == p.user.id
    if body.source == SRC.external_certificate:
        if not body.certificate_no:
            raise validation_error("certificate_no", "Enter the certificate number as printed.")
        _cert_unique(db, p, pv, body.certificate_no, body.worker_id, project_id)
        id_res = _id_match(db, p, w, body.id_on_card, project_id)
        cert_no = body.certificate_no
    else:
        id_res = None
        cert_no = c_no
    if signing:
        from app.services.ptw.common import require_reauth  # noqa: PLC0415

        require_reauth(db, p, project_id)
    at = now()
    a = FitnessAssessment(
        id=uuid.uuid4(),
        year=y,
        seq=seq,
        assessment_no=a_no,
        worker_id=body.worker_id,
        project_id=project_id,
        engagement_id=dep.engagement_id,
        assessment_type=body.assessment_type,
        source=body.source,
        provider_id=pv.id,
        examiner_id=x.id,
        examined_on=body.examined_on,
        certificate_no=cert_no,
        related_hold_id=body.related_hold_id,
        related_referral_id=body.related_referral_id,
        purpose_notice_given=True,
        purpose_notice_version=s.worker_purpose_notice_version,
        name_as_printed=body.name_as_printed,
        name_match=_name_match(body.name_as_printed, w),
        id_match_result=id_res,
        historic=body.historic,
        status=S.draft if body.source != SRC.site_clinic else S.awaiting_signoff,
        status_changed_at=at,
        recorded_by_user_id=p.user.id,
        alerts_sent=[],
    )
    cc.stamp(a, p, create=True)
    db.add(a)
    db.flush()
    _write_lines(db, a, prep.lines)
    common.record(db, p, AuditAction.create, EntityType.fitness_assessment, a, project_id)
    if signing:
        _sign(db, p, a, at)
    elif a.status == S.awaiting_signoff:
        engine.refresh_states(db, a.worker_id)
    out = read_model(db, p, a, common.tier(p, project_id, dep))
    out.warnings = prep.warnings
    return out


# ---- update (FA-14) ------------------------------------------------------------------------------


def update(
    db: Session, p: Principal, assessment_id: uuid.UUID, body: FitnessAssessmentUpdate
) -> FitnessAssessmentRead:
    a = get(db, assessment_id)
    _visible(db, p, a)
    p.ensure_writer()
    if a.status == S.accepted:
        if a.accepted_at is not None and now() - a.accepted_at > timedelta(hours=LOCK_HOURS):
            raise _e(
                ErrorCode.ASSESSMENT_LOCKED,
                "Accepted assessments are locked after 24 h: revoke and record a new one.",
                "يُقفل التقييم المقبول بعد 24 ساعة: ألغه وسجّل تقييماً جديداً.",
                409,
            )
        if p.grant(a.project_id, C.fitness_clinical_view) is None:
            raise forbidden_error()
    elif a.status in (S.draft, S.awaiting_signoff):
        cap = C.fitness_record_clinic if a.source == SRC.site_clinic else C.fitness_submit_external
        p.require(a.project_id, cap)
    else:
        raise invalid_transition("Fitness assessment", a.status, a.status)
    before = common.snap(a)
    data = body.model_dump(exclude_unset=True)
    if "examined_on" in data and data["examined_on"] is not None:
        a.examined_on = data["examined_on"]
    if "name_as_printed" in data:
        a.name_as_printed = data["name_as_printed"]
        a.name_match = _name_match(a.name_as_printed, common.worker(db, a.worker_id))
    if data.get("certificate_no") and a.source != SRC.site_clinic:
        pv = common.provider_or_404(db, a.provider_id)
        _cert_unique(db, p, pv, data["certificate_no"], a.worker_id, a.project_id, a.id)
        a.certificate_no = data["certificate_no"]
    warnings: list[ApiWarning] = []
    if body.lines is not None or "examined_on" in data:
        lines = body.lines
        if lines is None:
            lines = [
                FitnessLineInput(
                    code=ln.code,
                    outcome=ln.outcome,
                    restrictions=[],
                    restriction_review_date=ln.restriction_review_date,
                    unfit_review_date=ln.unfit_review_date,
                    printed_next_due=ln.printed_next_due,
                )
                for ln in _lines(db, a)
            ]
        prep = prepare(
            db,
            p,
            a.project_id,
            a.worker_id,
            a.source,
            common.provider_or_404(db, a.provider_id),
            common.examiner_or_404(db, a.examiner_id),
            a.examined_on,
            lines,
            a.historic,
        )
        warnings = prep.warnings
        _write_lines(db, a, prep.lines)
    cc.stamp(a, p)
    db.flush()
    common.record(db, p, AuditAction.update, EntityType.fitness_assessment, a, a.project_id, before)
    if a.status == S.accepted:
        _changed(db, a)
    out = read_model(db, p, a)
    out.warnings = warnings
    return out


# ---- status changes ------------------------------------------------------------------------------


def set_status(db: Session, a: FitnessAssessment, st: AssessmentStatus, at: datetime) -> None:
    a.status = st
    a.status_changed_at = at
    db.flush()


def _changed(db: Session, a: FitnessAssessment) -> None:
    from app.services.cert import events  # noqa: PLC0415

    common.clear_cache(db)
    engine.refresh_states(db, a.worker_id)
    events.publish(db, "medical.fitness_changed", worker_ids=[a.worker_id])


def _verification_row(
    db: Session,
    a: FitnessAssessment,
    p: Principal | None,
    method: FitnessVerificationMethod,
    channel: str,
    outcome: FitnessVerificationOutcome,
    reference: str,
    at: datetime,
    counts: bool,
    after: VerificationStatus,
) -> FitnessVerification:
    v = FitnessVerification(
        id=uuid.uuid4(),
        assessment_id=a.id,
        project_id=a.project_id,
        provider_id=a.provider_id,
        method=method,
        channel_used=channel,
        outcome=outcome,
        reference=reference,
        performed_by_user_id=p.user.id if p else None,
        performed_at=at,
        counts_as_verification=counts,
        verification_status_after=after,
    )
    db.add(v)
    return v


def _sign(db: Session, p: Principal, a: FitnessAssessment, at: datetime) -> None:
    """FA-6 / FV-6: signature by the linked examiner → Accepted and verified."""
    a.signed_by_user_id = p.user.id
    a.signed_at = at
    a.verification_status = VS.verified
    a.verified_at = at
    _verification_row(
        db,
        a,
        p,
        FitnessVerificationMethod.site_clinic_record,
        "site clinic",
        FitnessVerificationOutcome.confirmed,
        a.certificate_no,
        at,
        True,
        VS.verified,
    )
    accept(db, p, a, at)


def accept(db: Session, p: Principal | None, a: FitnessAssessment, at: datetime) -> None:
    """Accepted: line states, holds (FH-3), referrals (RF-4), events and alerts."""
    from app.services.med import holds  # noqa: PLC0415

    before = common.snap(a)
    a.accepted_at = at
    set_status(db, a, S.accepted, at)
    if a.source != SRC.site_clinic and a.verification_status != VS.verified:
        s = common.settings(db, a.project_id)
        a.verification_due_on = common.local_day(at) + timedelta(
            days=s.fitness_verification_due_days
        )
    common.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.fitness_assessment,
        a,
        a.project_id,
        before,
        {"to": "accepted"},
    )
    _changed(db, a)
    holds.on_assessment_accepted(db, a)
    lines = _lines(db, a)
    if any(ln.outcome == OUT.permanently_unfit for ln in lines):
        n = alerts.wno(db, a.worker_id)
        alerts.send(
            db,
            alerts.managers(db),
            K.fitness_permanently_unfit,
            f"Fitness outcome recorded for {n} ({a.assessment_no})",
            f"تم تسجيل نتيجة لياقة للعامل {n} ({a.assessment_no})",
            a.project_id,
            email=False,
        )
    if any(ln.outcome in ref.FIT for ln in lines) and _had_permanent(db, a, lines):
        alerts.send(
            db,
            alerts.managers(db),
            K.fitness_second_opinion,
            f"Second opinion recorded ({a.assessment_no})",
            f"تم تسجيل رأي ثانٍ ({a.assessment_no})",
            a.project_id,
            email=False,
        )


def _had_permanent(db: Session, a: FitnessAssessment, lines: list[FitnessLine]) -> bool:
    codes = [ln.code for ln in lines if ln.outcome in ref.FIT]
    return (
        db.scalar(
            select(FitnessLine.id).where(
                FitnessLine.worker_id == a.worker_id,
                FitnessLine.code.in_(codes),
                FitnessLine.outcome == OUT.permanently_unfit,
                FitnessLine.assessment_id != a.id,
            )
        )
        is not None
    )


def revoke_system(
    db: Session,
    a: FitnessAssessment,
    p: Principal | None,
    code: str,
    at: datetime,
    reason: str | None = None,
) -> None:
    before = common.snap(a)
    a.revoked_at = at
    a.revoked_by_user_id = p.user.id if p else None
    a.revoke_code = code
    if reason:
        a.status_reason_enc = common.enc(reason)
    set_status(db, a, S.revoked, at)
    common.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.fitness_assessment,
        a,
        a.project_id,
        before,
        {"to": "revoked", "code": code},
    )
    _changed(db, a)


def _delete_scan(db: Session, a: FitnessAssessment, why: str) -> None:
    from app.services.attachments import erase  # noqa: PLC0415

    if a.scan_attachment_id is None:
        return
    att = db.get(Attachment, a.scan_attachment_id)
    if att is not None:
        erase(db, att)
    a.scan_deleted_at = now()
    audit.record(
        db,
        AuditAction.retention_purge,
        audit.SYSTEM,
        entity_type=EntityType.fitness_assessment,
        entity_id=a.id,
        project_id=a.project_id,
        details={"reason": why, "file": "fitness_scan"},
    )


def scan_id(db: Session, a: FitnessAssessment) -> uuid.UUID | None:
    if a.scan_attachment_id is not None:
        return a.scan_attachment_id
    att = db.scalar(
        select(Attachment)
        .where(Attachment.owner_type == AttachmentOwner.fitness_scan, Attachment.owner_id == a.id)
        .order_by(Attachment.created_at.desc())
    )
    if att is not None:
        a.scan_attachment_id = att.id
    return a.scan_attachment_id


def transition(
    db: Session, p: Principal, assessment_id: uuid.UUID, body: FitnessAssessmentTransition
) -> FitnessAssessmentRead:
    a = get(db, assessment_id)
    _visible(db, p, a)
    p.ensure_writer()
    at = now()
    act = body.action
    x = db.get(MedicalExaminer, a.examiner_id)
    linked = x is not None and x.user_id == p.user.id
    before = common.snap(a)
    if act == AssessmentAction.sign:
        if a.source != SRC.site_clinic or a.status not in (S.draft, S.awaiting_signoff):
            raise invalid_transition("Fitness assessment", a.status, S.accepted)
        if not linked:
            raise forbidden_error("Only the examiner's linked user signs (FA-6, OH-4).")
        p.require(a.project_id, C.fitness_record_clinic)
        from app.services.ptw.common import require_reauth  # noqa: PLC0415

        require_reauth(db, p, a.project_id)
        assert x is not None  # noqa: S101
        prepare(
            db,
            p,
            a.project_id,
            a.worker_id,
            a.source,
            common.provider_or_404(db, a.provider_id),
            x,
            a.examined_on,
            _inputs(db, a),
            a.historic,
        )
        _sign(db, p, a, at)
    elif act == AssessmentAction.return_:
        r = common.reason(body.reason, 10)
        if a.status == S.awaiting_signoff and linked:
            pass
        elif a.status == S.submitted:
            p.require(a.project_id, C.fitness_review)
            if a.submitted_by_user_id == p.user.id:
                raise common.sod()
        else:
            raise invalid_transition("Fitness assessment", a.status, S.draft)
        a.status_reason_enc = common.enc(r)
        set_status(db, a, S.draft, at)
        _record(db, p, a, before, "draft")
    elif act == AssessmentAction.submit:
        if a.source == SRC.site_clinic or a.status != S.draft:
            raise invalid_transition("Fitness assessment", a.status, S.submitted)
        g = p.require(a.project_id, C.fitness_submit_external)
        if not common.covers_dep(g, _dep(db, a)):
            raise forbidden_error()
        if scan_id(db, a) is None:
            raise _e(
                ErrorCode.SCAN_REQUIRED,
                "Attach the certificate scan before submitting.",
                "أرفق نسخة الشهادة قبل التقديم.",
            )
        common.open_deployment(db, a.worker_id, a.project_id)
        prepare(
            db,
            p,
            a.project_id,
            a.worker_id,
            a.source,
            common.provider_or_404(db, a.provider_id),
            common.examiner_or_404(db, a.examiner_id),
            a.examined_on,
            _inputs(db, a),
            a.historic,
        )
        a.submitted_by_user_id = p.user.id
        a.submitted_at = at
        a.status_reason_enc = None
        set_status(db, a, S.submitted, at)
        _record(db, p, a, before, "submitted")
        engine.refresh_states(db, a.worker_id)
        common.clear_cache(db)
        alerts.send(
            db,
            alerts.oh(db, a.project_id),
            K.fitness_certificate_submitted,
            f"External fitness certificate submitted ({a.assessment_no})",
            f"قُدمت شهادة لياقة خارجية ({a.assessment_no})",
            a.project_id,
            EntityType.fitness_assessment,
            a.id,
            email=False,
        )
    elif act in (AssessmentAction.accept, AssessmentAction.reject):
        if a.status != S.submitted:
            raise invalid_transition("Fitness assessment", a.status, S.accepted)
        p.require(a.project_id, C.fitness_review)
        if a.submitted_by_user_id == p.user.id:
            raise common.sod("The reviewer cannot be the submitter (FA-8).")
        if body.clinical_data_present is None:
            raise validation_error(
                "clinical_data_present", "Answer whether the scan shows clinical data (FA-9)."
            )
        a.clinical_data_present = body.clinical_data_present
        a.reviewed_by_user_id = p.user.id
        a.reviewed_at = at
        if body.clinical_data_present:
            _reject(db, p, a, at, before, "CLINICAL_DATA_IN_SCAN")
            _delete_scan(db, a, "clinical_data")
            if a.submitted_by_user_id:
                alerts.send(
                    db,
                    [a.submitted_by_user_id],
                    K.fitness_clinical_data_rejected,
                    f"{a.assessment_no} rejected: the scan shows clinical data. Use the platform's "
                    "fitness certificate form (outcomes and functional restrictions only).",
                    f"رُفض {a.assessment_no}: النسخة تحتوي بيانات سريرية. استخدم نموذج شهادة "
                    "اللياقة الخاص بالمنصة.",
                    a.project_id,
                    EntityType.fitness_assessment,
                    a.id,
                )
        elif act == AssessmentAction.reject:
            _reject(db, p, a, at, before, common.reason(body.reason, 1))
        else:
            accept(db, p, a, at)
    elif act == AssessmentAction.revoke:
        if a.status != S.accepted:
            raise invalid_transition("Fitness assessment", a.status, S.revoked)
        p.require(a.project_id, C.fitness_clinical_view)
        r = common.reason(body.reason, 20)
        revoke_system(db, a, p, "revoked", at, r)
    db.flush()
    return read_model(db, p, a)


def _record(
    db: Session, p: Principal, a: FitnessAssessment, before: dict[str, Any], to: str
) -> None:
    common.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.fitness_assessment,
        a,
        a.project_id,
        before,
        {"to": to},
    )


def _reject(
    db: Session,
    p: Principal | None,
    a: FitnessAssessment,
    at: datetime,
    before: dict[str, Any],
    reason: str,
) -> None:
    a.status_reason_enc = common.enc(reason)
    set_status(db, a, S.rejected, at)
    if p is not None:
        _record(db, p, a, before, "rejected")
    _changed(db, a)


def _inputs(db: Session, a: FitnessAssessment) -> list[FitnessLineInput]:
    from app.schemas.medical import RestrictionInput  # noqa: PLC0415

    out = []
    for ln in _lines(db, a):
        rs = []
        for x in ln.restrictions or []:
            txt = common.dec(bytes.fromhex(x["text_enc"])) if x.get("text_enc") else None
            rs.append(RestrictionInput(code=x["code"], value=x.get("value"), text=txt))
        out.append(
            FitnessLineInput(
                code=ln.code,
                outcome=ln.outcome,
                restrictions=rs,
                restriction_review_date=ln.restriction_review_date,
                unfit_review_date=ln.unfit_review_date,
                printed_next_due=ln.printed_next_due,
            )
        )
    return out


# ---- verification (FV) ---------------------------------------------------------------------------


def _verification_read(
    db: Session, v: FitnessVerification, a: FitnessAssessment
) -> FitnessVerificationRead:
    return FitnessVerificationRead(
        id=v.id,
        assessment_id=a.id,
        assessment_no=a.assessment_no,
        method=v.method,
        channel_used=v.channel_used,
        outcome=v.outcome,
        reference=v.reference,
        performed_by=common.user_ref(db, v.performed_by_user_id),
        performed_at=v.performed_at,
        counts_as_verification=v.counts_as_verification,
        verification_status_after=v.verification_status_after,
    )


def list_verifications(
    db: Session, p: Principal, assessment_id: uuid.UUID
) -> FitnessVerificationList:
    a = get(db, assessment_id)
    _visible(db, p, a)
    if p.grant(a.project_id, C.fitness_clinical_view) is None:
        raise forbidden_error()
    rows = db.scalars(
        select(FitnessVerification)
        .where(FitnessVerification.assessment_id == a.id)
        .order_by(FitnessVerification.performed_at)
    )
    common.sensitive_read(
        db, p, EntityType.fitness_assessment, a.id, a.project_id, ["verification"]
    )
    return FitnessVerificationList(items=[_verification_read(db, v, a) for v in rows])


def _channel_ok(pv: MedicalProvider, method: FitnessVerificationMethod, channel: str) -> bool:
    domains = list(pv.verification_domains or [])
    ch = channel.strip().lower()
    if method == FitnessVerificationMethod.clinic_portal:
        from urllib.parse import urlparse  # noqa: PLC0415

        host = (urlparse(ch).hostname or "").lower()
        return ch.startswith("https://") and bool(host) and providers.domain_ok(host, domains)
    if method == FitnessVerificationMethod.clinic_email:
        return "@" in ch and providers.domain_ok(ch.rsplit("@", 1)[-1], domains)
    if method == FitnessVerificationMethod.clinic_phone:
        return bool(pv.verification_phone) and ch.replace(" ", "") == pv.verification_phone
    return False


def verify(
    db: Session, p: Principal, assessment_id: uuid.UUID, body: FitnessVerificationCreate
) -> FitnessVerificationRead:
    a = get(db, assessment_id)
    _visible(db, p, a)
    p.require(a.project_id, C.fitness_review)
    if a.source == SRC.site_clinic or a.status not in (S.submitted, S.accepted):
        raise invalid_transition("Fitness assessment", a.status, a.status)
    if a.submitted_by_user_id == p.user.id:
        raise common.sod("The verifier cannot be the submitter (FV-2).")
    u = db.get(User, p.user.id)
    dep = _dep(db, a)
    if u is not None and u.employer_contractor_id is not None and dep is not None:
        eng = db.get(ProjectEngagement, dep.engagement_id) if dep.engagement_id else None
        if eng is not None and eng.contractor_id == u.employer_contractor_id:
            raise common.sod("The verifier cannot be employed by the worker's employer (FV-2).")
    pv = common.provider_or_404(db, a.provider_id)
    if body.method in (
        FitnessVerificationMethod.site_clinic_record,
        FitnessVerificationMethod.clinic_register_file,
    ) or not _channel_ok(pv, body.method, body.channel_used):
        raise _e(
            ErrorCode.CHANNEL_NOT_REGISTERED,
            "Use the clinic's registered portal, domain email or phone.",
            "استخدم بوابة العيادة أو بريدها أو هاتفها المسجل.",
        )
    at = body.performed_at or now()
    before = common.snap(a)
    after = a.verification_status
    counts = False
    if body.outcome == FitnessVerificationOutcome.confirmed:
        after, counts = VS.verified, True
        a.verified_at = now()
    elif body.outcome == FitnessVerificationOutcome.no_response:
        prior = [
            v.performed_at
            for v in db.scalars(
                select(FitnessVerification).where(
                    FitnessVerification.assessment_id == a.id,
                    FitnessVerification.outcome == FitnessVerificationOutcome.no_response,
                )
            )
        ]
        if any(at - t >= timedelta(hours=24) for t in prior):
            after = VS.unable_to_verify
    else:
        after = VS.failed
    a.verification_status = after
    v = _verification_row(
        db, a, p, body.method, body.channel_used, body.outcome, body.reference, at, counts, after
    )
    db.flush()
    common.record(
        db,
        p,
        AuditAction.update,
        EntityType.fitness_assessment,
        a,
        a.project_id,
        before,
        {"verification": body.outcome.value, "status_after": after.value},
    )
    n = alerts.wno(db, a.worker_id)
    if after == VS.unable_to_verify:
        alerts.send(
            db,
            alerts.managers(db) | alerts.oh(db, a.project_id),
            K.fitness_verification_unable,
            f"Fitness certificate {a.assessment_no} ({n}) could not be verified",
            f"تعذر التحقق من شهادة اللياقة {a.assessment_no} ({n})",
            a.project_id,
        )
    elif after == VS.failed:
        if a.status == S.submitted:
            _reject(db, p, a, now(), before, "verification_failed")
        else:
            revoke_system(db, a, p, "verification_failed", now())
        alerts.send(
            db,
            alerts.managers(db) | alerts.oh(db, a.project_id),
            K.fitness_verification_failed,
            f"Fitness certificate {a.assessment_no} ({n}) failed verification",
            f"فشل التحقق من شهادة اللياقة {a.assessment_no} ({n})",
            a.project_id,
        )
    else:
        _changed(db, a)
    return _verification_read(db, v, a)


# ---- scans (P6-5) --------------------------------------------------------------------------------

SCAN_TTL = 300


def scan_owner(
    db: Session, p: Principal, owner_id: uuid.UUID, write: bool
) -> tuple[uuid.UUID, bool]:
    """Attachment owner check for `fitness_scan`: upload by the submitter side (153) while
    Draft; reads only through `scan_url` (160 with a reason)."""
    a = get(db, owner_id)
    if write:
        p.ensure_writer()
        g = p.grant(a.project_id, C.fitness_submit_external)
        if not common.covers_dep(g, _dep(db, a)):
            raise forbidden_error()
        return a.project_id, a.status == S.draft and a.source != SRC.site_clinic
    if p.grant(a.project_id, C.fitness_scan_view) is None:
        raise forbidden_error()
    return a.project_id, a.status == S.draft


def scan_url(
    db: Session, p: Principal, assessment_id: uuid.UUID, body: FitnessScanUrlRequest
) -> SignedUrlRead:
    from app.services.attachments import raw_signed_url  # noqa: PLC0415

    a = get(db, assessment_id)
    _visible(db, p, a)
    p.require(a.project_id, C.fitness_scan_view)
    if body.reason.value == "other" and not (body.reason_text or "").strip():
        raise validation_error("reason_text", "Describe the reason.")
    sid = scan_id(db, a)
    if sid is None or a.scan_deleted_at is not None:
        raise not_found("Scan")
    audit.record(
        db,
        AuditAction.sensitive_field_read,
        p.actor(a.project_id),
        entity_type=EntityType.fitness_assessment,
        entity_id=a.id,
        project_id=a.project_id,
        fields_read=["fitness_scan"],
        details={"reason": body.reason.value},
    )
    return SignedUrlRead(
        url=raw_signed_url(sid, SCAN_TTL), expires_at=now() + timedelta(seconds=SCAN_TTL)
    )


def is_oh_role(roles: set[Role]) -> bool:
    return Role.oh_practitioner in roles
