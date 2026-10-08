"""Training records: external certificates, review, suspension / revocation, verification with
the provider or awarding body, scans, certificate print and QR, the worker passport and the
data-subject report (spec 5-training §3.8, §3.9, §4.6, TR-1…TR-16, VR-1…VR-8, P5-1…P5-9).

TR-6: the ID number typed from the certificate is compared through the Phase 2 blind index and
never stored; a mismatch is audited with the masked value only."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.access_enums import QrKind, QrTokenStatus
from app.core.cert_enums import IdMatchResult, NameMatch, ScanReason, VerificationStatus
from app.core.clock import now, today
from app.core.enums import AuditAction, AuditResult, Capability, EntityType, NotificationKind
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import AttachmentOwner
from app.core.train_enums import (
    CourseCategory,
    DataSubjectPurpose,
    NominationStatus,
    TrainingRecordAction,
    TrainingRecordSource,
    TrainingRecordStatus,
    TrainingStatusReason,
    TrainingVerificationMethod,
    TrainingVerificationOutcome,
)
from app.models import (
    Attachment,
    Deployment,
    ProjectEngagement,
    QrToken,
    TrainingCourse,
    TrainingNomination,
    TrainingProvider,
    TrainingRecord,
    TrainingSession,
    TrainingVerification,
    User,
    Worker,
    WorkerIdHistory,
)
from app.schemas.attachments import SignedUrlRead
from app.schemas.hse_common import ApiWarning
from app.schemas.personnel_certs import IdOnCard
from app.schemas.training_common import NOT_ACCEPTED_AR, NOT_ACCEPTED_EN, TrainingValidity
from app.schemas.training_records import (
    CertificateReissue,
    DataSubjectReport,
    PassportEntry,
    TrainingCertificatePrint,
    TrainingPassport,
    TrainingRecordCreate,
    TrainingRecordListItem,
    TrainingRecordPage,
    TrainingRecordPreview,
    TrainingRecordPreviewRequest,
    TrainingRecordRead,
    TrainingRecordTransition,
    TrainingRecordUpdate,
    TrainingReportAttendance,
    TrainingScanUrlRequest,
    TrainingVerificationCreate,
    TrainingVerificationList,
    TrainingVerificationLogItem,
    TrainingVerificationLogPage,
    TrainingVerificationRead,
)
from app.services import audit
from app.services.access import common as acommon
from app.services.cert import alerts
from app.services.cert import common as cc
from app.services.cert.personnel import name_match
from app.services.common import invalid_transition, paginate
from app.services.hse_common import Refs, id_warnings
from app.services.permissions import Principal, engagement_descendants, forbidden_error
from app.services.train import common, providers, recordops
from app.services.train import hook as thook
from app.services.train import reference as ref
from app.services.train import validity as tval

C = Capability
RS = TrainingRecordStatus
VS = VerificationStatus
A = TrainingRecordAction
M = TrainingVerificationMethod
O = TrainingVerificationOutcome  # noqa: E741
SRC = TrainingRecordSource
SCAN_TTL = 300
EDIT_LOCK = timedelta(hours=24)
COUNTING = frozenset(
    {
        M.provider_portal,
        M.provider_qr_url,
        M.provider_email,
        M.provider_phone,
        M.provider_register_file,
        M.awarding_body_portal,
    }
)
FAILING = frozenset({O.not_found, O.details_differ, O.revoked_by_provider})
NO_RESPONSE_GAP = timedelta(hours=24)
ENDED = (RS.expired, RS.superseded, RS.revoked, RS.rejected)


# ---- access (TR-1, TR-16) -----------------------------------------------------------------------


def get_row(db: Session, record_id: uuid.UUID) -> TrainingRecord:
    r = db.get(TrainingRecord, record_id)
    if r is None:
        raise not_found("Training record")
    return r


def _dep(db: Session, r: TrainingRecord) -> Deployment | None:
    return common.deployment(db, r.worker_id, r.project_id) if r.project_id else None


def get_visible(db: Session, p: Principal, record_id: uuid.UUID) -> TrainingRecord:
    """Records follow the worker (TR-16): visible with capability 136 covering any deployment
    of the holder."""
    if not p.has_any(C.training_record_view):
        raise forbidden_error()
    r = get_row(db, record_id)
    w = db.get(Worker, r.worker_id)
    if w is None or not common.can_see_worker(db, p, w):
        raise not_found("Training record")
    return r


def _covers(db: Session, p: Principal, r: TrainingRecord, cap: Capability) -> bool:
    if r.project_id is None:
        return p.is_manager
    return common.covers_dep(p.grant(r.project_id, cap), _dep(db, r))


def _require(db: Session, p: Principal, r: TrainingRecord, cap: Capability) -> None:
    p.ensure_writer()
    if not _covers(db, p, r, cap):
        raise forbidden_error()


def _require_holder(
    db: Session, p: Principal, project_id: uuid.UUID, worker_id: uuid.UUID, write: bool = True
) -> tuple[Worker, Deployment]:
    """TR-1: a Contractor HSE Rep only for C-scope workers; HSE Officers for any worker with a
    deployment on their project (404 otherwise)."""
    common.visible_project(db, p, project_id)
    g = common.need(p, project_id, C.training_record_submit, write)
    w = db.get(Worker, worker_id)
    dep = common.deployment(db, worker_id, project_id)
    if w is None or dep is None or not common.covers_dep(g, dep):
        raise not_found("Worker")
    common.active_worker(db, worker_id)
    return w, dep


def _sees_scores(db: Session, p: Principal, r: TrainingRecord) -> bool:
    """AT-7 / P5-5: HSE Manager / Officer, the session's trainers, the worker's Contractor HSE
    Rep."""
    if p.is_manager or common.is_hse(p, r.project_id):
        return True
    if r.session_id is not None:
        from app.services.train import sessions  # noqa: PLC0415

        s = db.get(TrainingSession, r.session_id)
        if s is not None and p.user.id in sessions.trainer_user_ids(db, s):
            return True
    from app.core.enums import Role  # noqa: PLC0415

    if Role.contractor_hse_rep in common.roles_on(p, r.project_id):
        return _covers(db, p, r, C.training_record_view)
    return False


# ---- TR-6 identity ------------------------------------------------------------------------------


def id_match(
    db: Session, p: Principal | None, w: Worker, card: IdOnCard, project_id: uuid.UUID
) -> IdMatchResult:
    if not card.shown:
        return IdMatchResult.not_shown
    if card.id_type is None or not card.id_number:
        raise validation_error("id_on_card.id_number", "Type the ID number shown on the card.")
    try:
        bidx = acommon.blind_index(card.id_type, card.id_number, card.passport_country)
    except Exception:
        bidx = ""
    if bidx and w.id_number_bidx and bidx == w.id_number_bidx:
        return IdMatchResult.matched
    for h in db.scalars(select(WorkerIdHistory).where(WorkerIdHistory.worker_id == w.id)):
        try:
            old = crypto.decrypt(h.id_number_enc)
        except Exception:  # noqa: S112
            continue
        if bidx and acommon.blind_index(h.id_type, old, h.passport_country) == bidx:
            return IdMatchResult.matched_previous_id
    audit.record(
        db,
        AuditAction.update,
        p.actor(project_id) if p is not None else audit.SYSTEM,
        entity_type=EntityType.training_record,
        entity_id=w.id,
        project_id=project_id,
        details={
            "cert_id_mismatch": acommon.mask_worker_id(card.id_type, card.id_number),
            "worker_no": w.worker_no,
        },
        result=AuditResult.failed,
        defer=True,  # kept although the request is rolled back (nothing else is stored)
    )
    raise ApiError(
        422,
        ErrorCode.CERT_ID_MISMATCH,
        "The ID number on the certificate does not match this worker.",
        "رقم الهوية في الشهادة لا يطابق هذا العامل.",
        meta={"field": "id_on_card.id_number"},
    )


# ---- validation (TR-1…TR-11) --------------------------------------------------------------------

Err = tuple[int, str, str, str, str | None, dict[str, Any] | None]


@dataclass
class Checked:
    errors: list[Err] = field(default_factory=list)
    warnings: list[ApiWarning] = field(default_factory=list)
    provider_reason: str | None = None
    validity: tuple[date | None, Any] | None = None
    name_match: NameMatch = NameMatch.none
    reused: Worker | None = None

    def err(
        self,
        st: int,
        code: str,
        en: str,
        ar: str,
        fld: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.errors.append((st, code, en, ar, fld, meta))

    def drop(self, *codes: str) -> None:
        self.errors = [e for e in self.errors if e[1] not in codes]

    def raise_first(self) -> None:
        if not self.errors:
            return
        st, code, en, ar, fld, meta = sorted(
            self.errors, key=lambda e: {404: 0, 409: 1}.get(e[0], 2)
        )[0]
        if code == ErrorCode.VALIDATION_ERROR:
            raise validation_error(fld or "body", en)
        m = dict(meta or {})
        if fld:
            m.setdefault("field", fld)
        raise ApiError(st, ErrorCode(code), en, ar, meta=m or None)

    def error_warnings(self) -> list[ApiWarning]:
        return [cc.warn(code, en, ar, fld) for _st, code, en, ar, fld, _m in self.errors]


def _host(url: str | None) -> str:
    from urllib.parse import urlsplit  # noqa: PLC0415

    if not url:
        return ""
    u = url.strip().lower()
    if "@" in u and "://" not in u:
        return u.rsplit("@", 1)[1]
    if "://" not in u:
        u = "https://" + u
    return (urlsplit(u).hostname or "").lower()


def _domain_ok(host: str, domains: list[str] | tuple[str, ...]) -> bool:
    host = host.lower()
    return bool(host) and any(
        host == d.lower() or host.endswith("." + d.lower()) for d in domains or []
    )


def foreign_url(pv: TrainingProvider, url: str | None) -> bool:
    """VR-4: a provider QR URL whose host is not a registered verification domain."""
    if not url:
        return False
    host = _host(url)
    if pv.verification_portal_url and host == _host(pv.verification_portal_url):
        return False
    return not _domain_ok(host, list(pv.verification_domains or []))


def _foreign_warning(pv: TrainingProvider, url: str | None) -> list[ApiWarning]:
    if not foreign_url(pv, url):
        return []
    return [
        cc.warn(
            "VERIFICATION_URL_FOREIGN_DOMAIN",
            "The verification link is not on the provider's registered domains — possible fake QR.",
            "رابط التحقق ليس ضمن نطاقات الجهة المسجلة — احتمال رمز QR مزوّر.",
            "provider_verification_url",
        )
    ]


def _refresher_ok(
    db: Session, w: Worker, c: TrainingCourse, d: date, project_id: uuid.UUID | None
) -> bool:
    """TR-11: on d an in-force record of the target course (or of the refresher), or one that
    ended no more than refresher_max_lapse_days before."""
    targets = set(c.satisfies or []) | {c.code}
    for t in list(targets):
        targets |= set(common.satisfiers(db, t))
    lapse = common.settings(db, project_id).refresher_max_lapse_days if project_id else 0
    ctx = thook.eval_ctx(db, project_id)
    for r in thook.worker_records(db, w.id):
        if r.course_code not in targets or r.anonymised or r.historic:
            continue
        v = tval.evaluate(r, d, ctx)
        if v.in_force:
            return True
        if v.reason == tval.R.TRAINING_EXPIRED and r.status in tval.LIVE:
            vu = v.eff.valid_until
            if vu is not None and vu < d and (d - vu).days <= lapse:
                return True
    return False


def prerequisites_missing(
    db: Session, r: TrainingRecord, c: TrainingCourse, project_id: uuid.UUID | None
) -> list[str]:
    """TR-9: each prerequisite in force on completed_on (induction_link via Phase 2)."""
    if not c.prerequisite_codes or r.prerequisite_evidenced:
        return []
    ctx = thook.eval_ctx(db, project_id)
    recs = [x for x in thook.worker_records(db, r.worker_id) if x.id != r.id]
    out = []
    for code in c.prerequisite_codes:
        pc = common.course(db, code)
        if pc is not None and pc.category == CourseCategory.induction_link:
            if thook.induction_valid(db, r.worker_id, project_id, pc, r.completed_on) is None:
                out.append(code)
            continue
        if not tval.best(recs, common.satisfiers(db, code), r.completed_on, ctx).met:
            out.append(code)
    return out


def check(
    db: Session,
    project_id: uuid.UUID,
    w: Worker,
    data: dict[str, Any],
    *,
    record_id: uuid.UUID | None = None,
    submit: bool = False,
    historic: bool = False,
) -> Checked:
    out = Checked()
    d0 = today()
    c = common.course(db, str(data["course_code"]))
    if c is None or not c.active:
        out.err(
            422, ErrorCode.VALIDATION_ERROR, "Unknown course.", "دورة غير معروفة.", "course_code"
        )
        return out
    if c.category == CourseCategory.induction_link:
        out.err(
            422,
            ErrorCode.INDUCTION_OWNED_BY_PHASE2,
            "Inductions are recorded in the induction module.",
            "تسجل التعريفات في وحدة التعريف.",
            "course_code",
        )
        return out
    pv = db.get(TrainingProvider, data["provider_id"])
    if pv is None:
        out.err(404, ErrorCode.NOT_FOUND, "Provider not found.", "الجهة غير موجودة.", "provider_id")
        return out
    completed: date = data["completed_on"]
    expiry: date | None = data.get("printed_expiry")
    if completed > d0:
        out.err(
            422,
            ErrorCode.VALIDATION_ERROR,
            "completed_on cannot be in the future.",
            "",
            "completed_on",
        )
    if expiry is not None and expiry <= completed:
        out.err(
            422,
            ErrorCode.VALIDATION_ERROR,
            "printed_expiry must be after completed_on.",
            "",
            "printed_expiry",
        )
    # TR-5
    cert_no = str(data["certificate_no"]).strip().upper()
    q = select(TrainingRecord).where(
        TrainingRecord.provider_id == pv.id,
        TrainingRecord.course_code == c.code,
        func.upper(TrainingRecord.certificate_no) == cert_no,
    )
    if record_id is not None:
        q = q.where(TrainingRecord.id != record_id)
    for other in db.scalars(q):
        if other.worker_id == w.id:
            out.err(
                409,
                ErrorCode.CERT_EXISTS,
                "This certificate is already recorded.",
                "هذه الشهادة مسجلة مسبقاً.",
                "certificate_no",
            )
            break
        ow = db.get(Worker, other.worker_id)
        out.reused = ow
        out.err(
            409,
            ErrorCode.CERT_NO_REUSED,
            "This certificate number is recorded for another worker — possible fake certificate.",
            "رقم الشهادة مسجل لعامل آخر — احتمال شهادة مزورة.",
            "certificate_no",
            {"existing_worker_no": ow.worker_no if ow else None},
        )
        break
    # TR-2
    acc = providers.acceptable(db, pv, c, completed, project_id, [w.id])
    if not acc.ok:
        e = providers.unacceptable_error(acc)
        out.provider_reason = acc.reason.value if acc.reason else None
        out.err(
            422,
            ErrorCode.PROVIDER_NOT_ACCEPTABLE,
            e.message,
            e.message_ar or e.message,
            "provider_id",
            {"reason": out.provider_reason},
        )
    # TR-4 / §6.1
    vu, lf = tval.stored_validity(c, completed, expiry)
    out.validity = (vu, lf)
    if expiry is not None and vu is not None and vu < expiry:
        out.warnings.append(
            cc.warn(
                "W01",
                f"Shortened by the course validity: valid until {vu.isoformat()}.",
                f"مدة الصلاحية محدودة بصلاحية الدورة: صالحة حتى {vu.isoformat()}.",
                "printed_expiry",
            )
        )
    # TR-3
    if vu is not None and vu < d0 and not historic:
        out.err(
            422,
            ErrorCode.RECORD_ALREADY_EXPIRED,
            "This training has already expired.",
            "انتهت صلاحية هذا التدريب.",
            "completed_on",
        )
    # TR-11
    if c.renews_only and not _refresher_ok(db, w, c, completed, project_id):
        out.err(
            422,
            ErrorCode.REFRESHER_NOT_ELIGIBLE,
            "Refresher not eligible: the full course is required.",
            "التجديد غير مؤهل: يلزم حضور الدورة الكاملة.",
            "course_code",
        )
    # TH-3
    sponsored = bool(data.get("project_sponsored"))
    sp = data.get("sponsoring_project_id")
    if sponsored and data.get("hours") is None:
        out.err(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Hours are required for project-sponsored training.",
            "",
            "hours",
        )
    if sponsored != (sp is not None):
        out.err(
            422,
            ErrorCode.VALIDATION_ERROR,
            "sponsoring_project_id is required iff project_sponsored.",
            "",
            "sponsoring_project_id",
        )
    elif sponsored and sp is not None:
        dep = common.deployment_on(db, w.id, sp, completed)
        if dep is None or not common.mobilised_on(dep, completed):
            out.err(
                422,
                ErrorCode.VALIDATION_ERROR,
                "The worker was not mobilised on the sponsoring project on completed_on.",
                "",
                "sponsoring_project_id",
            )
    # TR-6 name
    out.name_match = name_match(str(data["name_as_printed"]), w)
    if out.name_match != NameMatch.exact:
        out.warnings.append(
            cc.warn(
                "W02",
                f"Name on the certificate matches the worker: {out.name_match.value}.",
                f"تطابق الاسم في الشهادة مع العامل: {out.name_match.value}.",
                "name_as_printed",
            )
        )
    out.warnings += _foreign_warning(pv, data.get("provider_verification_url"))
    if submit and not data.get("scan_attachment_id"):
        out.err(
            422,
            ErrorCode.SCAN_REQUIRED,
            "Attach the certificate scan before submitting.",
            "أرفق نسخة الشهادة قبل التقديم.",
            "scan_attachment_id",
        )
    return out


def _fields(body: Any) -> dict[str, Any]:
    data: dict[str, Any] = body.model_dump(
        exclude={"worker_id", "project_id", "id_on_card", "historic"}
    )
    data["certificate_no"] = str(data["certificate_no"]).strip()
    data["prerequisite_evidenced"] = bool(data.pop("prerequisite_evidenced_on_certificate", False))
    return data


def _data_of(r: TrainingRecord) -> dict[str, Any]:
    return {col.key: getattr(r, col.key) for col in r.__table__.columns}


def _check_scan(db: Session, aid: uuid.UUID | None, record_id: uuid.UUID | None) -> None:
    if aid is None:
        return
    a = db.get(Attachment, aid)
    if (
        a is None
        or a.owner_type != AttachmentOwner.training_record_scan
        or (record_id is not None and a.owner_id != record_id)
    ):
        raise validation_error("scan_attachment_id", "Upload the scan to this record first.")


# ---- reads --------------------------------------------------------------------------------------


def validity_read(
    db: Session, r: TrainingRecord, project_id: uuid.UUID | None, d: date | None = None
) -> TrainingValidity:
    d = d or today()
    ctx = thook.eval_ctx(db, project_id)
    v = tval.evaluate(r, d, ctx, now() if d == today() else None)
    vu = v.eff.valid_until
    in_force = v.in_force and r.status not in (RS.draft, RS.rejected)
    return TrainingValidity(
        project_id=project_id,
        as_of=d,
        valid_until=vu,
        stored_valid_until=r.valid_until,
        limiting_factor=v.eff.limiting,
        course_end=v.eff.course_end,
        printed_expiry=r.printed_expiry,
        days_left=(vu - d).days if vu is not None else None,
        in_force=in_force,
        not_in_force_reason=None if in_force else v.reason,
        expiring=in_force and vu is not None and vu <= d + timedelta(days=30),
        expiring_hook=in_force and vu is not None and vu <= d + timedelta(days=7),
        unverified_window_until=v.unverified_until if in_force else None,
    )


_ACTIONS: dict[RS, tuple[A, ...]] = {
    RS.draft: (A.submit,),
    RS.submitted: (A.return_, A.accept, A.reject),
    RS.accepted: (A.suspend, A.revoke),
    RS.suspended: (A.reinstate, A.revoke),
}
_ACTION_CAP = {
    A.submit: C.training_record_submit,
    A.return_: C.training_record_review,
    A.accept: C.training_record_review,
    A.reject: C.training_record_review,
    A.suspend: C.training_record_suspend,
    A.reinstate: C.training_record_suspend,
    A.revoke: C.training_record_suspend,
}


def allowed(db: Session, p: Principal, r: TrainingRecord) -> list[TrainingRecordAction]:
    try:
        p.ensure_writer()
    except ApiError:
        return []
    out = []
    contractor = common.contractor_only(p, r.project_id)
    for a in _ACTIONS.get(r.status, ()):
        if not _covers(db, p, r, _ACTION_CAP[a]):
            continue
        if a == A.accept and (contractor or r.submitted_by_user_id == p.user.id):
            continue
        out.append(a)
    return out


def record_read(
    db: Session,
    p: Principal,
    r: TrainingRecord,
    project_id: uuid.UUID | None = None,
    prompts: list[ApiWarning] | None = None,
) -> TrainingRecordRead:
    pid = project_id or r.project_id
    refs = Refs(db).load(users=[r.submitted_by_user_id, r.reviewed_by_user_id])
    w = db.get(Worker, r.worker_id)
    assert w is not None  # noqa: S101
    pv = common.provider_or_404(db, r.provider_id)
    hse = common.is_hse(p, r.project_id)
    warnings: list[ApiWarning] = []
    if r.status in (RS.draft, RS.submitted) and r.project_id is not None:
        ch = check(db, r.project_id, w, _data_of(r), record_id=r.id, historic=r.historic)
        warnings = ch.warnings + [
            x for x in ch.error_warnings() if x.code == ErrorCode.CERT_NO_REUSED
        ]
    else:
        warnings = _foreign_warning(pv, r.provider_verification_url)
    val = validity_read(db, r, pid)
    if val.unverified_window_until is not None:
        warnings.append(
            cc.warn(
                "TRAINING_UNVERIFIED",
                "Accepted but not yet verified with the provider.",
                "مقبول ولم يتم التحقق منه لدى الجهة بعد.",
            )
        )
    scores = _sees_scores(db, p, r)
    not_acc = not hse and r.status in (RS.rejected, RS.revoked, RS.suspended)
    sensitive_reason = r.status_reason in (
        TrainingStatusReason.verification_failed,
        TrainingStatusReason.hse_suspension,
        TrainingStatusReason.hse_revocation,
    )
    s = db.get(TrainingSession, r.session_id) if r.session_id else None
    extra: dict[str, Any] = {}
    if scores:
        extra["theory_score_pct"] = r.theory_score_pct
        extra["practical_result"] = r.practical_result
    if hse:
        extra["status_reason_text"] = r.status_reason_text
        warnings.extend(id_warnings(status_reason_text=r.status_reason_text))
    if not_acc:
        extra["not_accepted_message_en"] = NOT_ACCEPTED_EN
        extra["not_accepted_message_ar"] = NOT_ACCEPTED_AR
    return TrainingRecordRead(
        id=r.id,
        record_no=r.record_no,
        project_id=r.project_id,
        worker=common.worker_ref(w, common.names(p, pid)),
        engagement=refs.eng(r.engagement_id),
        course=common.course_ref_code(db, r.course_code),
        source=r.source,
        provider=common.provider_ref(pv, p, pid),
        session=common.session_ref(s) if s is not None else None,
        certificate_no=r.certificate_no,
        completed_on=r.completed_on,
        printed_expiry=r.printed_expiry,
        valid_until=r.valid_until,
        limiting_factor=r.limiting_factor,
        validity=val,
        hours=r.hours,
        project_sponsored=r.project_sponsored,
        sponsoring_project_id=r.sponsoring_project_id,
        name_as_printed=r.name_as_printed if not r.anonymised else None,
        name_match=r.name_match,
        id_match_result=r.id_match_result,
        identity_confirmed_by_provider=r.identity_confirmed_by_provider,
        has_scan=_scan_id(db, r) is not None,
        provider_verification_url=r.provider_verification_url,
        has_qr=_token(db, r) is not None,
        status=r.status,
        status_reason=r.status_reason if hse or not sensitive_reason else None,
        verification_status=r.verification_status
        if hse or r.verification_status != VS.failed
        else VS.not_verified,
        verification_due_on=r.verification_due_on,
        historic=r.historic,
        prerequisite_evidenced_on_certificate=r.prerequisite_evidenced,
        superseded_by_id=r.superseded_by_id,
        submitted_by=refs.user(r.submitted_by_user_id),
        submitted_at=r.submitted_at,
        reviewed_by=refs.user(r.reviewed_by_user_id),
        reviewed_at=r.reviewed_at,
        warnings=warnings,
        prompts=prompts or [],
        allowed_actions=allowed(db, p, r),
        created_at=r.created_at,
        updated_at=r.updated_at,
        **extra,
    )


def read(
    db: Session, p: Principal, record_id: uuid.UUID, project_id: uuid.UUID | None = None
) -> TrainingRecordRead:
    r = get_visible(db, p, record_id)
    if project_id is not None:
        common.visible_project(db, p, project_id)
    return record_read(db, p, r, project_id)


def list_item(
    db: Session, r: TrainingRecord, project_id: uuid.UUID, show_names: bool, refs: Refs
) -> TrainingRecordListItem:
    w = db.get(Worker, r.worker_id)
    assert w is not None  # noqa: S101
    c = common.course(db, r.course_code)
    pv = common.provider_or_404(db, r.provider_id)
    v = validity_read(db, r, project_id)
    dep = common.deployment(db, r.worker_id, project_id)
    return TrainingRecordListItem(
        id=r.id,
        record_no=r.record_no,
        worker=common.worker_ref(w, show_names),
        engagement=refs.eng(dep.engagement_id if dep else r.engagement_id),
        course_code=r.course_code,
        course_name_en=c.name_en if c else r.course_code,
        course_name_ar=c.name_ar if c else r.course_code,
        provider_code=pv.provider_code,
        source=r.source,
        certificate_no=r.certificate_no,
        completed_on=r.completed_on,
        valid_until=v.valid_until,
        limiting_factor=v.limiting_factor,
        days_left=v.days_left,
        in_force=v.in_force,
        expiring=v.expiring,
        status=r.status,
        verification_status=r.verification_status,
        historic=r.historic,
    )


def list_records(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    q: str | None = None,
    course_codes: list[str] | None = None,
    statuses: list[TrainingRecordStatus] | None = None,
    verification_statuses: list[VerificationStatus] | None = None,
    sources: list[TrainingRecordSource] | None = None,
    provider_id: uuid.UUID | None = None,
    worker_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    include_subcontractors: bool = True,
    in_force: bool | None = None,
    expiring_days: int | None = None,
    awaiting_review: bool | None = None,
    verification_overdue: bool | None = None,
    historic: bool | None = None,
) -> TrainingRecordPage:
    common.visible_project(db, p, project_id)
    g = p.grant(project_id, C.training_record_view)
    if g is None:
        raise forbidden_error()
    dep_q = select(Deployment.worker_id).where(Deployment.project_id == project_id)
    if g.engagement_ids is not None:
        dep_q = dep_q.where(Deployment.engagement_id.in_(list(g.engagement_ids)))
    if g.site_ids is not None:
        dep_q = dep_q.where(Deployment.site_ids.overlap(list(g.site_ids)))
    if engagement_ids:
        ids: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                ids |= engagement_descendants(db, e)
        dep_q = dep_q.where(Deployment.engagement_id.in_(ids))
    stmt = (
        select(TrainingRecord)
        .join(Worker, Worker.id == TrainingRecord.worker_id)
        .where(TrainingRecord.worker_id.in_(dep_q))
    )
    if q:
        pat = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Worker.worker_no.ilike(pat),
                TrainingRecord.record_no.ilike(pat),
                TrainingRecord.certificate_no.ilike(pat),
            )
        )
    if course_codes:
        stmt = stmt.where(TrainingRecord.course_code.in_(course_codes))
    if statuses:
        stmt = stmt.where(TrainingRecord.status.in_(statuses))
    if verification_statuses:
        stmt = stmt.where(TrainingRecord.verification_status.in_(verification_statuses))
    if sources:
        stmt = stmt.where(TrainingRecord.source.in_(sources))
    if provider_id:
        stmt = stmt.where(TrainingRecord.provider_id == provider_id)
    if worker_id:
        stmt = stmt.where(TrainingRecord.worker_id == worker_id)
    if session_id:
        stmt = stmt.where(TrainingRecord.session_id == session_id)
    if historic is not None:
        stmt = stmt.where(TrainingRecord.historic.is_(historic))
    if awaiting_review is not None:
        cond = TrainingRecord.status == RS.submitted
        stmt = stmt.where(cond if awaiting_review else ~cond)
    d0 = today()
    if verification_overdue is not None:
        cond = (
            TrainingRecord.status.in_([RS.submitted, RS.accepted])
            & TrainingRecord.verification_status.in_([VS.not_verified, VS.unable_to_verify])
            & (TrainingRecord.verification_due_on < d0)
        )
        stmt = stmt.where(cond if verification_overdue else ~cond)
    stmt = stmt.order_by(
        Worker.worker_no, TrainingRecord.course_code, TrainingRecord.completed_on.desc()
    )
    refs = Refs(db)
    show = common.names(p, project_id)
    if in_force is None and expiring_days is None:
        rows, total = paginate(db, stmt, page, page_size)
        items = [list_item(db, r, project_id, show, refs) for r in rows]
    else:
        every = [list_item(db, r, project_id, show, refs) for r in db.scalars(stmt)]
        if in_force is not None:
            every = [i for i in every if i.in_force == in_force]
        if expiring_days is not None:
            lim = d0 + timedelta(days=expiring_days)
            every = [i for i in every if i.in_force and i.valid_until and i.valid_until <= lim]
        total = len(every)
        items = every[(page - 1) * page_size : page * page_size]
    return TrainingRecordPage(items=items, total=total, page=page, page_size=page_size)


# ---- create / preview / update ------------------------------------------------------------------


def _alert_reused(db: Session, project_id: uuid.UUID, cert_no: str, w: Worker) -> None:
    """TR-5: the alert is committed in its own transaction, because the request then fails with
    409 CERT_NO_REUSED and its own transaction is rolled back."""
    from app.db.session import get_sessionmaker  # noqa: PLC0415

    with get_sessionmaker()() as own:
        _send_reused(own, project_id, cert_no, w)
        own.commit()


def _send_reused(db: Session, project_id: uuid.UUID, cert_no: str, w: Worker) -> None:
    alerts.send(
        db,
        alerts.officers(db, project_id),
        NotificationKind.training_cert_no_reused,
        f"Training certificate number {cert_no} presented for another worker ({w.worker_no})",
        f"رقم شهادة التدريب {cert_no} مقدم لعامل آخر ({w.worker_no})",
        EntityType.worker,
        w.id,
        project_id,
    )


def create(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    body: TrainingRecordCreate,
    *,
    source: TrainingRecordSource = SRC.external_certificate,
    batch_id: uuid.UUID | None = None,
) -> TrainingRecordRead:
    w, dep = _require_holder(db, p, project_id, body.worker_id)
    if body.historic and not common.covers_dep(p.grant(project_id, C.training_record_review), dep):
        raise forbidden_error("Historic records need capability 138.")
    data = _fields(body)
    ch = check(db, project_id, w, data, historic=body.historic)
    if ch.reused is not None:  # TR-5 (unique per provider / course): 409, as Phase 4
        _alert_reused(db, project_id, str(data["certificate_no"]), w)
    ch.raise_first()
    _check_scan(db, data.get("scan_attachment_id"), None)
    idm = id_match(db, p, w, body.id_on_card, project_id)
    r = new_external(db, p, project_id, w, dep, data, idm, ch.name_match, body.historic)
    r.source = source
    r.import_batch_id = batch_id
    return record_read(db, p, r)


def new_external(
    db: Session,
    p: Principal | None,
    project_id: uuid.UUID,
    w: Worker,
    dep: Deployment | None,
    data: dict[str, Any],
    idm: IdMatchResult,
    nm: NameMatch,
    historic: bool = False,
) -> TrainingRecord:
    c = common.course_or_404(db, data["course_code"])
    r = recordops.new_record(
        db,
        w.id,
        c,
        SRC.external_certificate,
        data["provider_id"],
        data["completed_on"],
        data["certificate_no"],
        RS.draft,
        project_id,
        dep.engagement_id if dep else None,
        data.get("printed_expiry"),
    )
    for k in (
        "theory_score_pct",
        "practical_result",
        "hours",
        "project_sponsored",
        "sponsoring_project_id",
        "name_as_printed",
        "scan_attachment_id",
        "provider_verification_url",
        "prerequisite_evidenced",
    ):
        if k in data:
            setattr(r, k, data[k])
    r.project_sponsored = bool(r.project_sponsored)
    r.prerequisite_evidenced = bool(r.prerequisite_evidenced)
    r.historic = historic
    r.id_match_result = idm
    r.name_match = nm
    cc.stamp(r, p, create=True)
    db.flush()
    if r.scan_attachment_id is not None:
        a = db.get(Attachment, r.scan_attachment_id)
        if a is not None:
            a.owner_id = r.id
    recordops.audit(db, p, AuditAction.create, r, details={"source": r.source.value})
    return r


def preview(
    db: Session, p: Principal, project_id: uuid.UUID, body: TrainingRecordPreviewRequest
) -> TrainingRecordPreview:
    w, _dep = _require_holder(db, p, project_id, body.worker_id, write=False)
    ch = check(db, project_id, w, _fields(body))
    c = common.course(db, body.course_code)
    vu, lf = ch.validity or (None, None)
    d0 = today()
    s = common.settings(db, project_id)
    ce = None
    if c is not None:
        ce = tval.course_end(body.completed_on, c.validity_months)
        ov = tval.override_months(c, s)
        if ov is not None:
            ov_end = tval.course_end(body.completed_on, ov)
            if ov_end is not None and (vu is None or ov_end < vu):
                vu, lf = ov_end, tval.LF.project_override
    return TrainingRecordPreview(
        validity=TrainingValidity(
            project_id=project_id,
            as_of=d0,
            valid_until=vu,
            stored_valid_until=(ch.validity or (None, None))[0],
            limiting_factor=lf or tval.LF.none,
            course_end=ce,
            printed_expiry=body.printed_expiry,
            days_left=(vu - d0).days if vu else None,
            in_force=False,
            not_in_force_reason=None,
            expiring=False,
            expiring_hook=False,
        ),
        name_match=ch.name_match,
        provider_acceptable=ch.provider_reason is None,
        provider_reason=ch.provider_reason,
        errors=ch.error_warnings(),
        warnings=ch.warnings,
    )


def update(
    db: Session, p: Principal, record_id: uuid.UUID, body: TrainingRecordUpdate
) -> TrainingRecordRead:
    r = get_visible(db, p, record_id)
    changes = body.changes()
    reason = changes.pop("reason", None)
    card = changes.pop("id_on_card", None)
    if r.status == RS.draft:
        _require(db, p, r, C.training_record_submit)
    elif r.status == RS.accepted:
        locked = r.reviewed_at is not None and now() - r.reviewed_at > EDIT_LOCK
        if locked and not p.is_manager:
            raise ApiError(
                409,
                ErrorCode.RECORD_EDIT_LOCKED,
                "Accepted more than 24 hours ago: only the HSE Manager can edit, with a reason.",
                "مضى على القبول أكثر من 24 ساعة: التعديل للمدير فقط مع ذكر السبب.",
            )
        _require(db, p, r, C.training_record_review)
        common.reason(reason, 10)
    else:
        raise invalid_transition("Training record", r.status.value, "edit")
    before = recordops.snap(r)
    for k, raw in changes.items():
        key = "prerequisite_evidenced" if k == "prerequisite_evidenced_on_certificate" else k
        v = str(raw).strip() if k == "certificate_no" else raw
        setattr(r, key, v)
    if "scan_attachment_id" in changes:
        _check_scan(db, r.scan_attachment_id, r.id)
    w = db.get(Worker, r.worker_id)
    assert w is not None  # noqa: S101
    if r.project_id is not None and r.source != SRC.session:
        ch = check(db, r.project_id, w, _data_of(r), record_id=r.id, historic=r.historic)
        if r.status == RS.accepted:
            ch.drop(ErrorCode.RECORD_ALREADY_EXPIRED, ErrorCode.PROVIDER_NOT_ACCEPTABLE)
        ch.raise_first()
        r.name_match = ch.name_match
    if card is not None and body.id_on_card is not None and r.project_id is not None:
        r.id_match_result = id_match(db, p, w, body.id_on_card, r.project_id)
    c = common.course_or_404(db, r.course_code)
    r.valid_until, r.limiting_factor = tval.stored_validity(c, r.completed_on, r.printed_expiry)
    cc.stamp(r, p)
    db.flush()
    recordops.audit(db, p, AuditAction.update, r, before, {"reason": reason} if reason else None)
    if r.status == RS.accepted:
        _publish(db, r)
    return record_read(db, p, r)


# ---- transitions (§4.6) -------------------------------------------------------------------------


def _publish(db: Session, r: TrainingRecord) -> None:
    from app.services.cert import events  # noqa: PLC0415

    events.publish(db, "training.record_changed", worker_ids=[r.worker_id])


def _scan_id(db: Session, r: TrainingRecord) -> uuid.UUID | None:
    if r.scans_deleted_at is not None:
        return None
    if r.scan_attachment_id is not None:
        return r.scan_attachment_id
    return db.scalar(
        select(Attachment.id)
        .where(
            Attachment.owner_type == AttachmentOwner.training_record_scan,
            Attachment.owner_id == r.id,
        )
        .order_by(Attachment.created_at)
        .limit(1)
    )


def _alert_status(
    db: Session, r: TrainingRecord, users: set[uuid.UUID], en: str, ar: str, why: str | None = None
) -> None:
    if users:
        alerts.send(
            db,
            users,
            NotificationKind.training_record_status,
            en,
            ar,
            EntityType.training_record,
            r.id,
            r.project_id,
            body_en=why,
            body_ar=why,
        )


def _reps(db: Session, r: TrainingRecord) -> set[uuid.UUID]:
    if r.project_id is None:
        return set()
    dep = _dep(db, r)
    return alerts.reps(db, r.project_id, dep.engagement_id if dep else r.engagement_id)


def _not_accepted(db: Session, r: TrainingRecord) -> None:
    """TR-13 / P5-4: the Contractor HSE Rep is told "not accepted" without the reason."""
    _alert_status(
        db,
        r,
        _reps(db, r),
        f"{NOT_ACCEPTED_EN} ({r.record_no})",
        f"{NOT_ACCEPTED_AR} ({r.record_no})",
    )


def transition(
    db: Session, p: Principal, record_id: uuid.UUID, body: TrainingRecordTransition
) -> TrainingRecordRead:
    r = get_visible(db, p, record_id)
    src = r.status
    a = body.action
    if a not in _ACTIONS.get(src, ()):
        raise invalid_transition("Training record", src.value, a.value)
    _require(db, p, r, _ACTION_CAP[a])
    before = recordops.snap(r)
    at = now()
    w = db.get(Worker, r.worker_id)
    assert w is not None  # noqa: S101
    prompts: list[ApiWarning] = []
    if a == A.submit:
        sid = _scan_id(db, r)
        if sid is not None:
            r.scan_attachment_id = sid
        assert r.project_id is not None  # noqa: S101
        ch = check(db, r.project_id, w, _data_of(r), record_id=r.id, submit=True)
        ch.drop(ErrorCode.RECORD_ALREADY_EXPIRED) if r.historic else None
        if ch.reused is not None:
            _alert_reused(db, r.project_id, r.certificate_no, w)
        ch.raise_first()
        submit(db, p, r, at)
    elif a == A.return_:
        if common.contractor_only(p, r.project_id):
            raise forbidden_error()
        r.status_reason_text = common.reason(body.reason, 10)
        r.status = RS.draft
        if r.submitted_by_user_id:
            _alert_status(
                db,
                r,
                {r.submitted_by_user_id},
                f"Training record {r.record_no} returned",
                f"أعيد السجل التدريبي {r.record_no}",
                r.status_reason_text,
            )
    elif a == A.accept:
        if common.contractor_only(p, r.project_id):
            raise forbidden_error()
        if r.submitted_by_user_id == p.user.id:
            raise common.sod("The reviewer cannot be the submitter.")
        if r.source != SRC.session and r.project_id is not None:
            ch = check(db, r.project_id, w, _data_of(r), record_id=r.id, historic=r.historic)
            ch.drop(ErrorCode.RECORD_ALREADY_EXPIRED)
            ch.raise_first()
        if r.name_match == NameMatch.none:
            if not body.identity_confirmed_by_provider:
                raise ApiError(
                    422,
                    ErrorCode.NAME_MISMATCH_CONFIRMATION,
                    "The name does not match: confirm the identity with the provider to accept.",
                    "الاسم غير مطابق: أكّد الهوية مع الجهة للقبول.",
                )
            r.identity_confirmed_by_provider = True
        c = common.course_or_404(db, r.course_code)
        missing = prerequisites_missing(db, r, c, r.project_id)
        if missing:
            raise ApiError(
                422,
                ErrorCode.TRAINING_PREREQUISITE,
                "The holder did not have the prerequisite training in force on completion.",
                "لم يكن لدى المتدرب التدريب المسبق سارياً عند الإتمام.",
                meta={"missing": missing},
            )
        accept(db, p, r, at)
    elif a == A.reject:
        if common.contractor_only(p, r.project_id):
            raise forbidden_error()
        r.status_reason_text = common.reason(body.reason, 1)
        r.status_reason = body.reason_code or TrainingStatusReason.document_review
        r.status = RS.rejected
        r.reviewed_by_user_id, r.reviewed_at = p.user.id, at
        r.ended_on = today()
        if r.submitted_by_user_id:
            _alert_status(
                db,
                r,
                {r.submitted_by_user_id},
                f"Training record {r.record_no} rejected",
                f"رُفض السجل التدريبي {r.record_no}",
                r.status_reason_text if common.is_hse(p, r.project_id) else None,
            )
    elif a == A.suspend:
        r.status_reason_text = common.reason(body.reason, 20)
        r.status_reason = body.reason_code or TrainingStatusReason.hse_suspension
        r.status = RS.suspended
        _not_accepted(db, r)
    elif a == A.reinstate:
        r.status_reason_text = common.reason(body.reason, 1)
        r.status_reason = None
        r.status = RS.accepted
    elif a == A.revoke:
        r.status_reason_text = common.reason(body.reason, 20)
        r.status_reason = body.reason_code or TrainingStatusReason.hse_revocation
        r.status = RS.revoked
        r.ended_on = today()
        _revoke_tokens(db, r, at)
        _not_accepted(db, r)
    r.status_changed_at = at
    cc.stamp(r, p)
    db.flush()
    recordops.audit(
        db, p, AuditAction.status_change, r, before, {"from": src.value, "to": r.status.value}
    )
    if r.status != src and (src != RS.draft or r.status != RS.submitted):
        _publish(db, r)
    elif r.status == RS.submitted:
        _publish(db, r)  # TRAINING_PENDING_REVIEW on the hook
    return record_read(db, p, r, prompts=prompts)


def submit(db: Session, p: Principal | None, r: TrainingRecord, at: datetime) -> None:
    assert r.project_id is not None  # noqa: S101
    s = common.settings(db, r.project_id)
    r.status = RS.submitted
    r.status_reason_text = None
    if p is not None:
        r.submitted_by_user_id = p.user.id
    r.submitted_at = at
    r.verification_due_on = acommon.local_day(at) + timedelta(days=s.training_verification_due_days)
    alerts.send(
        db,
        alerts.officers(db, r.project_id),
        NotificationKind.training_record_submitted,
        f"Training record {r.record_no} ({r.course_code}) submitted",
        f"قُدم السجل التدريبي {r.record_no} ({r.course_code})",
        EntityType.training_record,
        r.id,
        r.project_id,
    )


def accept(db: Session, p: Principal | None, r: TrainingRecord, at: datetime) -> None:
    r.status = RS.accepted
    r.status_reason = None
    r.reviewed_by_user_id = p.user.id if p is not None else None
    r.reviewed_at = at
    db.flush()
    maybe_in_force(db, p, r)


def maybe_in_force(db: Session, p: Principal | None, r: TrainingRecord) -> None:
    """TR-10 / TR-8: accepted and verified → in force; older records of the course are
    superseded only then (no gap)."""
    if r.status != RS.accepted or r.verification_status != VS.verified or r.historic:
        return
    if r.in_force_from is None:
        r.in_force_from = max(x for x in (r.reviewed_at, r.verified_at, now()) if x is not None)
        if r.reviewed_at is not None and r.verified_at is not None:
            r.in_force_from = max(r.reviewed_at, r.verified_at)
    db.flush()
    recordops.supersede_older(db, p, r)


def _token(db: Session, r: TrainingRecord, active_only: bool = True) -> QrToken | None:
    if r.source != SRC.session:
        return None
    q = select(QrToken).where(QrToken.kind == QrKind.TR, QrToken.subject_id == r.id)
    if active_only:
        q = q.where(QrToken.status == QrTokenStatus.active)
    return db.scalar(q.order_by(QrToken.created_at.desc()).limit(1))


def _revoke_tokens(db: Session, r: TrainingRecord, at: datetime) -> None:
    for t in db.scalars(
        select(QrToken).where(
            QrToken.kind == QrKind.TR,
            QrToken.subject_id == r.id,
            QrToken.status == QrTokenStatus.active,
        )
    ):
        t.status = QrTokenStatus.revoked
        t.ended_at = at


# ---- verification (VR) --------------------------------------------------------------------------


def _ver_read(
    db: Session, p: Principal | None, v: TrainingVerification, r: TrainingRecord, refs: Refs
) -> dict[str, Any]:
    hide = p is not None and not common.is_hse(p, r.project_id)
    return {
        "id": v.id,
        "record_id": r.id,
        "record_no": r.record_no,
        "certificate_no": r.certificate_no,
        "method": v.method,
        "channel_used": v.channel_used,
        "outcome": None if hide else v.outcome,
        "differences": [] if hide else list(v.differences or []),
        "differences_text": None if hide else v.differences_text,
        "reference": v.reference,
        "evidence_attachment_id": v.evidence_attachment_id,
        "performed_by": refs.user(v.performed_by_user_id),
        "performed_at": v.performed_at,
        "counts_as_verification": v.counts_as_verification,
        "verification_status_after": v.verification_status_after,
    }


def _history(db: Session, record_id: uuid.UUID) -> list[TrainingVerification]:
    return list(
        db.scalars(
            select(TrainingVerification)
            .where(TrainingVerification.record_id == record_id)
            .order_by(TrainingVerification.performed_at, TrainingVerification.created_at)
        )
    )


def verifications(db: Session, p: Principal, record_id: uuid.UUID) -> TrainingVerificationList:
    r = get_visible(db, p, record_id)
    refs = Refs(db)
    return TrainingVerificationList(
        items=[TrainingVerificationRead(**_ver_read(db, p, v, r, refs)) for v in _history(db, r.id)]
    )


def channel_registered(
    db: Session, pv: TrainingProvider, c: TrainingCourse | None, method: M, channel: str
) -> bool:
    """VR-3: a channel on the provider record or the awarding body's domain (list ACB)."""
    ch = channel.strip().lower()
    if method == M.original_sighted:
        return bool(ch)
    if method == M.awarding_body_portal:
        bodies = set(c.accreditation_bodies_required or []) if c is not None else set()
        bodies |= {a.accreditation_body for a in providers.accreditations(db, pv.id)}
        host = _host(ch)
        return any(_domain_ok(host, ref.BODY_DOMAINS.get(ref.ACB(b), ())) for b in bodies)
    if method == M.provider_phone:
        digits = "".join(x for x in ch if x.isdigit())
        reg = "".join(x for x in (pv.verification_phone or "") if x.isdigit())
        return bool(reg) and digits.endswith(reg[-9:])
    if method in (M.provider_email, M.provider_register_file) and "@" in ch and "://" not in ch:
        if pv.verification_email and ch == pv.verification_email.strip().lower():
            return True
        return _domain_ok(_host(ch), list(pv.verification_domains or []))
    host = _host(ch)
    if not host:
        return False
    if pv.verification_portal_url and host == _host(pv.verification_portal_url):
        return True
    return _domain_ok(host, list(pv.verification_domains or []))


def _employer(db: Session, r: TrainingRecord) -> uuid.UUID | None:
    dep = _dep(db, r)
    eid = dep.engagement_id if dep else r.engagement_id
    if eid is None:
        return None
    eng = db.get(ProjectEngagement, eid)
    return eng.contractor_id if eng else None


def verify(
    db: Session, p: Principal, record_id: uuid.UUID, body: TrainingVerificationCreate
) -> TrainingVerificationRead:
    r = get_visible(db, p, record_id)
    _require(db, p, r, C.training_record_review)  # 403 before any content check
    if body.method == M.session_record:
        raise validation_error("method", "session_record is recorded by the system only.")
    if r.status not in (RS.submitted, RS.accepted, RS.suspended) or r.verification_status in (
        VS.verified,
        VS.failed,
    ):
        raise ApiError(
            409,
            ErrorCode.VERIFICATION_CLOSED,
            "This record can no longer be verified.",
            "لم يعد بالإمكان التحقق من هذا السجل.",
        )
    # VR-2
    if r.submitted_by_user_id == p.user.id:
        raise common.sod("The verifier cannot be the submitter.")
    emp = p.user.employer_contractor_id
    if emp is not None and emp == _employer(db, r):
        raise common.sod("The verifier cannot be employed by the holder's employer.")
    pv = common.provider_or_404(db, r.provider_id)
    c = common.course(db, r.course_code)
    if body.method == M.provider_qr_url and foreign_url(pv, body.channel_used):
        raise ApiError(
            422,
            ErrorCode.CHANNEL_NOT_REGISTERED,
            "This link is not on the provider's registered domains and cannot be used "
            "(possible fake QR).",
            "هذا الرابط ليس ضمن نطاقات الجهة المسجلة ولا يمكن استخدامه (احتمال رمز مزوّر).",
        )
    if not channel_registered(db, pv, c, body.method, body.channel_used):
        raise ApiError(
            422,
            ErrorCode.CHANNEL_NOT_REGISTERED,
            "Use a verification channel registered on the provider or the awarding body.",
            "استخدم قناة تحقق مسجلة لدى الجهة أو جهة المنح.",
        )
    if body.outcome == O.details_differ and not body.differences:
        raise validation_error("differences", "List what differs.")
    if body.outcome != O.details_differ and body.differences:
        raise validation_error("differences", "Differences apply to details_differ only.")
    if body.method == M.provider_phone:
        if len(body.reference.strip()) < 20:
            raise ApiError(
                422,
                ErrorCode.EVIDENCE_REQUIRED_FOR_METHOD,
                "For a phone verification give the provider person's role and reference "
                "(≥ 20 characters).",
                "للتحقق الهاتفي اذكر صفة الشخص لدى الجهة والمرجع (20 حرفاً على الأقل).",
            )
    else:
        a = db.get(Attachment, body.evidence_attachment_id) if body.evidence_attachment_id else None
        if body.evidence_attachment_id is None:
            raise ApiError(
                422,
                ErrorCode.EVIDENCE_REQUIRED_FOR_METHOD,
                "Attach the verification evidence (screenshot, e-mail or register extract).",
                "أرفق دليل التحقق (لقطة شاشة أو بريد أو مستخرج السجل).",
            )
        if (
            a is None
            or a.owner_type != AttachmentOwner.training_verification_evidence
            or a.owner_id != r.id
        ):
            raise validation_error(
                "evidence_attachment_id", "Upload the evidence to this record first."
            )
    at = body.performed_at or now()
    if at > now() + timedelta(minutes=5):
        raise validation_error("performed_at", "Cannot be in the future.")
    v = record_verification(
        db,
        p,
        r,
        body.method,
        body.channel_used,
        body.outcome,
        body.reference,
        at,
        differences=[x.value for x in body.differences],
        differences_text=body.differences_text,
        evidence_attachment_id=body.evidence_attachment_id,
    )
    return TrainingVerificationRead(**_ver_read(db, p, v, r, Refs(db)))


def record_verification(
    db: Session,
    p: Principal | None,
    r: TrainingRecord,
    method: M,
    channel: str,
    outcome: O,
    reference: str,
    at: datetime,
    *,
    differences: list[str] | None = None,
    differences_text: str | None = None,
    evidence_attachment_id: uuid.UUID | None = None,
) -> TrainingVerification:
    """VR-3…VR-6 effects (also used by provider_register_file imports, VR-8)."""
    before = r.verification_status
    counts = method in COUNTING and outcome != O.no_response
    after = before
    if method == M.original_sighted:
        counts = False
        if outcome in FAILING:  # a sighted original that differs is still a red flag
            after, counts = VS.failed, True
    elif outcome == O.confirmed:
        after = VS.verified
    elif outcome in FAILING:
        after = VS.failed
    elif outcome == O.no_response:
        prev = [x.performed_at for x in _history(db, r.id) if x.outcome == O.no_response]
        if any(abs(at - x) >= NO_RESPONSE_GAP for x in prev):
            after = VS.unable_to_verify
    v = TrainingVerification(
        id=uuid.uuid4(),
        record_id=r.id,
        project_id=r.project_id,
        provider_id=r.provider_id,
        method=method,
        channel_used=channel.strip(),
        outcome=outcome,
        differences=differences or [],
        differences_text=differences_text,
        reference=reference.strip(),
        evidence_attachment_id=evidence_attachment_id,
        performed_by_user_id=p.user.id if p is not None else None,
        performed_at=at,
        counts_as_verification=counts,
        verification_status_after=after,
        created_at=now(),
    )
    db.add(v)
    db.flush()
    cc.record(
        db,
        p,
        AuditAction.create,
        EntityType.training_verification,
        v,
        r.project_id,
        details={"record": r.record_no, "from": before.value, "to": after.value},
    )
    if after == before:
        return v
    rb = recordops.snap(r)
    r.verification_status = after
    holder = r.record_no
    w = db.get(Worker, r.worker_id)
    if w is not None:
        holder = w.worker_no
    hse = alerts.managers(db) | (alerts.officers(db, r.project_id) if r.project_id else set())
    if after == VS.verified:
        r.verified_at = at
        maybe_in_force(db, p, r)
    elif after == VS.failed:
        if r.status == RS.submitted:
            r.status = RS.rejected
        elif r.status in (RS.accepted, RS.suspended):
            r.status = RS.revoked
            _revoke_tokens(db, r, at)
        r.status_reason = TrainingStatusReason.verification_failed
        r.status_changed_at = at
        r.ended_on = r.ended_on or today()
        alerts.send(
            db,
            hse,
            NotificationKind.training_verification_failed,
            f"Verification failed: training certificate {r.certificate_no} ({holder})",
            f"فشل التحقق: شهادة التدريب {r.certificate_no} ({holder})",
            EntityType.training_record,
            r.id,
            r.project_id,
            email=True,
        )
        _not_accepted(db, r)
    elif after == VS.unable_to_verify:
        alerts.send(
            db,
            alerts.managers(db),
            NotificationKind.training_verification_unable,
            f"Unable to verify training certificate {r.certificate_no} ({holder})",
            f"تعذر التحقق من شهادة التدريب {r.certificate_no} ({holder})",
            EntityType.training_record,
            r.id,
            r.project_id,
            email=True,
        )
    db.flush()
    recordops.audit(
        db, p, AuditAction.status_change, r, rb, {"verification": f"{before.value}→{after.value}"}
    )
    _publish(db, r)
    return v


def verification_log(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    methods: list[TrainingVerificationMethod] | None = None,
    failed_only: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
) -> TrainingVerificationLogPage:
    common.visible_project(db, p, project_id)
    g = p.grant(project_id, C.training_record_review)
    if g is None:
        raise forbidden_error()
    stmt = (
        select(TrainingVerification, TrainingRecord)
        .join(TrainingRecord, TrainingRecord.id == TrainingVerification.record_id)
        .where(TrainingVerification.project_id == project_id)
    )
    if g.engagement_ids is not None:
        stmt = stmt.where(
            exists(
                select(Deployment.id).where(
                    Deployment.worker_id == TrainingRecord.worker_id,
                    Deployment.project_id == project_id,
                    Deployment.engagement_id.in_(list(g.engagement_ids)),
                )
            )
        )
    if methods:
        stmt = stmt.where(TrainingVerification.method.in_(methods))
    if failed_only:
        stmt = stmt.where(TrainingVerification.outcome.in_(list(FAILING)))
    if date_from is not None:
        stmt = stmt.where(
            TrainingVerification.performed_at >= acommon.local_midnight_utc(date_from)
        )
    if date_to is not None:
        stmt = stmt.where(
            TrainingVerification.performed_at
            < acommon.local_midnight_utc(date_to + timedelta(days=1))
        )
    stmt = stmt.order_by(TrainingVerification.performed_at.desc())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    refs = Refs(db)
    items = []
    for v, r in rows:
        w = db.get(Worker, r.worker_id)
        pv = db.get(TrainingProvider, r.provider_id)
        items.append(
            TrainingVerificationLogItem(
                **_ver_read(db, p, v, r, refs),
                project_id=project_id,
                worker_no=w.worker_no if w else "",
                course_code=r.course_code,
                provider_code=pv.provider_code if pv else "",
            )
        )
    return TrainingVerificationLogPage(items=items, total=total, page=page, page_size=page_size)


# ---- scans (P5-3) -------------------------------------------------------------------------------


def scan_url(
    db: Session, p: Principal, record_id: uuid.UUID, body: TrainingScanUrlRequest
) -> SignedUrlRead:
    from app.core.config import API_PREFIX, get_settings  # noqa: PLC0415

    r = get_visible(db, p, record_id)
    if not _covers(db, p, r, C.training_scan_view):
        raise forbidden_error()
    if body.reason == ScanReason.other and not (body.reason_text or "").strip():
        raise validation_error("reason_text", "Describe the reason.")
    aid = _scan_id(db, r)
    if aid is None:
        raise not_found("Scan")
    expires = int(time.time()) + SCAN_TTL
    sig = crypto.sign(f"{aid}:{expires}", get_settings().attachment_url_secret)
    audit.record(
        db,
        AuditAction.sensitive_field_read,
        p.actor(r.project_id),
        entity_type=EntityType.training_record,
        entity_id=r.id,
        project_id=r.project_id,
        fields_read=["training_scan"],
        details={"reason": body.reason.value, "reason_text": body.reason_text},
    )
    return SignedUrlRead(
        url=f"{API_PREFIX}/attachments/{aid}/content?expires={expires}&signature={sig}",
        expires_at=datetime.fromtimestamp(expires, UTC),
    )


# ---- certificate print and QR (TR-14, CK5-1) ----------------------------------------------------


def _trainer_names(db: Session, s: TrainingSession) -> list[str]:
    from app.services.train import sessions  # noqa: PLC0415

    out = []
    for uid in sessions.trainer_user_ids(db, s):
        u = db.get(User, uid)
        if u is not None:
            out.append(u.full_name_en)
    for wid in sessions.trainer_worker_ids(db, s):
        w = db.get(Worker, wid)
        if w is not None:
            out.append(w.full_name_en)
    return out


def certificate(db: Session, p: Principal, record_id: uuid.UUID) -> TrainingCertificatePrint:
    r = get_visible(db, p, record_id)
    t = _token(db, r)
    s = db.get(TrainingSession, r.session_id) if r.session_id else None
    if r.source != SRC.session or t is None or s is None:
        raise not_found("Certificate")
    w = db.get(Worker, r.worker_id)
    assert w is not None  # noqa: S101
    c = common.course_or_404(db, r.course_code)
    pv = common.provider_or_404(db, r.provider_id)
    return TrainingCertificatePrint(
        record_id=r.id,
        record_no=r.record_no,
        certificate_no=r.certificate_no,
        worker_no=w.worker_no,
        worker_name_en=w.full_name_en,
        worker_name_ar=w.full_name_ar or None,
        course_code=c.code,
        course_name_en=c.name_en,
        course_name_ar=c.name_ar,
        completed_on=r.completed_on,
        valid_until=r.valid_until,
        provider_code=pv.provider_code,
        provider_name_en=pv.legal_name_en,
        provider_name_ar=pv.legal_name_ar,
        trainer_names=_trainer_names(db, s),
        session_no=s.session_no,
        qr_payload=f"HSE2:TR:{t.token}",
        printed_ref=t.printed_ref,
        issued_at=t.created_at,
    )


def reissue(
    db: Session, p: Principal, record_id: uuid.UUID, body: CertificateReissue
) -> TrainingCertificatePrint:
    r = get_visible(db, p, record_id)
    _require(db, p, r, C.training_record_review)
    if r.source != SRC.session or r.project_id is None:
        raise not_found("Certificate")
    if r.status not in (RS.accepted, RS.suspended, RS.expired, RS.superseded):
        raise invalid_transition("Training record", r.status.value, "reissue")
    at = now()
    _revoke_tokens(db, r, at)
    db.add(
        QrToken(
            id=uuid.uuid4(),
            token=acommon.new_qr_token(),
            kind=QrKind.TR,
            project_id=r.project_id,
            subject_id=r.id,
            printed_ref=r.certificate_no,
            status=QrTokenStatus.active,
            created_at=at,
        )
    )
    db.flush()
    recordops.audit(db, p, AuditAction.update, r, details={"qr_reissued": body.reason})
    return certificate(db, p, record_id)


def qr_status(db: Session, r: TrainingRecord, t: QrToken) -> tuple[str, str]:
    """CK5-1 status and colour of a TR scan."""
    if t.status != QrTokenStatus.active or r.status in (RS.revoked, RS.rejected):
        return "revoked", "red"
    v = validity_read(db, r, t.project_id)
    if v.in_force:
        return "in_force", "green"
    if r.status in (RS.expired, RS.superseded) or v.not_in_force_reason == tval.R.TRAINING_EXPIRED:
        return "expired", "amber"
    return "not_in_force", "red"


# ---- passport (TR-16) and data-subject report (P5-9) --------------------------------------------


def _visible_worker(db: Session, p: Principal, worker_id: uuid.UUID) -> Worker:
    if not p.has_any(C.training_record_view):
        raise forbidden_error()
    w = db.get(Worker, worker_id)
    if w is None or not common.can_see_worker(db, p, w):
        raise not_found("Worker")
    return w


def _requirements(db: Session, w: Worker, project_id: uuid.UUID, d: date) -> list[Any]:
    from app.services.train import gaps  # noqa: PLC0415
    from app.services.train import requirements as reqs  # noqa: PLC0415

    dep = common.deployment(db, w.id, project_id)
    if dep is None:
        return []
    f = reqs.load(
        db, project_id, d, deployment_ids=[dep.id], mobilised_only=False, enforcement=True,
        bookings=True,
    )  # fmt: skip
    return [gaps.requirement_status(db, x) for x in reqs.evaluate_dep(f, dep, True)]


def passport(
    db: Session,
    p: Principal,
    worker_id: uuid.UUID,
    project_id: uuid.UUID | None,
    as_of: date | None,
) -> TrainingPassport:
    w = _visible_worker(db, p, worker_id)
    if project_id is not None:
        common.visible_project(db, p, project_id)
    d = as_of or today()
    entries = []
    for r in sorted(
        thook.worker_records(db, w.id), key=lambda x: (x.course_code, x.completed_on), reverse=True
    ):
        if r.status == RS.draft:
            continue
        v = validity_read(db, r, project_id, d)
        pv = common.provider_or_404(db, r.provider_id)
        entries.append(
            PassportEntry(
                record_id=r.id,
                record_no=r.record_no,
                course=common.course_ref_code(db, r.course_code),
                provider_code=pv.provider_code,
                source=r.source,
                completed_on=r.completed_on,
                valid_until=v.valid_until,
                in_force=v.in_force,
                status=r.status,
                has_qr=_token(db, r) is not None,
            )
        )
    entries.sort(key=lambda e: (e.course.code, e.completed_on), reverse=False)
    names_pid = project_id or next(iter(common.worker_projects(db, w.id)), None)
    return TrainingPassport(
        worker=common.worker_ref(w, common.names(p, names_pid)),
        as_of=d,
        project_id=project_id,
        entries=entries,
        requirements=_requirements(db, w, project_id, d) if project_id else [],
    )


def data_subject_report(
    db: Session, p: Principal, worker_id: uuid.UUID, purpose: DataSubjectPurpose
) -> DataSubjectReport:
    p.ensure_writer()
    if not p.is_manager:
        raise forbidden_error()
    w = common.worker(db, worker_id)
    d = today()
    refs = Refs(db)
    deps = list(db.scalars(select(Deployment).where(Deployment.worker_id == w.id)))
    pid = deps[0].project_id if deps else None
    records = [
        list_item(db, r, r.project_id or pid, True, refs)  # type: ignore[arg-type]
        for r in thook.worker_records(db, w.id)
        if (r.project_id or pid) is not None
    ]
    atts = []
    for n, s in db.execute(
        select(TrainingNomination, TrainingSession)
        .join(TrainingSession, TrainingSession.id == TrainingNomination.session_id)
        .where(TrainingNomination.worker_id == w.id)
        .order_by(TrainingSession.first_day)
    ):
        atts.append(
            TrainingReportAttendance(
                session_no=s.session_no,
                course_code=s.course_code,
                first_day=s.first_day,
                last_day=s.last_day,
                status=n.status.value,
                minutes=sum(int(x) for x in (n.minutes_by_day or {}).values()),
                theory_score_pct=n.theory_score_pct,
                practical_result=n.practical_result,
                result=n.result.value if n.result is not None else "pending",
            )
        )
    reqs_out = []
    for dep in deps:
        if dep.status.value != "demobilised":
            reqs_out += _requirements(db, w, dep.project_id, d)
    audit.record(
        db,
        AuditAction.export,
        p.actor(pid),
        entity_type=EntityType.worker,
        entity_id=w.id,
        project_id=pid,
        details={
            "dataset": "training_report",
            "purpose": purpose.value,
            "records": len(records),
            "attendances": len(atts),
        },
    )
    return DataSubjectReport(
        worker=common.worker_ref(w, True),
        purpose=purpose,
        generated_at=now(),
        records=records,
        attendances=atts,
        requirements=reqs_out,
    )


# ---- jobs (§7, P5-8) ----------------------------------------------------------------------------


def expiry_job(db: Session, d: date | None = None) -> int:
    """Accepted → Expired once today > valid_until (stored org default)."""
    d = d or today()
    n = 0
    workers: set[uuid.UUID] = set()
    for r in db.scalars(
        select(TrainingRecord).where(
            TrainingRecord.status == RS.accepted,
            TrainingRecord.valid_until.is_not(None),
            TrainingRecord.valid_until < d,
        )
    ):
        before = recordops.snap(r)
        r.status = RS.expired
        r.status_changed_at = now()
        r.ended_on = r.ended_on or ((r.valid_until or d) + timedelta(days=1))
        recordops.audit(db, None, AuditAction.status_change, r, before, {"to": "expired"})
        workers.add(r.worker_id)
        n += 1
    if workers:
        from app.services.cert import events  # noqa: PLC0415

        events.publish(db, "training.record_changed", worker_ids=workers)
    return n


def scan_retention_job(db: Session, d: date | None = None) -> int:
    """P5-8: scans deleted training_scan_retention_years after the record ended."""
    from app.services import attachments  # noqa: PLC0415

    d = d or today()
    n = 0
    for r in db.scalars(
        select(TrainingRecord).where(
            TrainingRecord.status.in_(ENDED),
            TrainingRecord.ended_on.is_not(None),
            TrainingRecord.scans_deleted_at.is_(None),
        )
    ):
        years = (
            common.settings(db, r.project_id).training_scan_retention_years if r.project_id else 2
        )
        assert r.ended_on is not None  # noqa: S101
        if common.add_months(r.ended_on, 12 * years) > d:
            continue
        for a in db.scalars(
            select(Attachment).where(
                Attachment.owner_type == AttachmentOwner.training_record_scan,
                Attachment.owner_id == r.id,
            )
        ):
            attachments.erase(db, a)
            n += 1
        r.scans_deleted_at = now()
        r.scan_attachment_id = None
    db.flush()
    return n


def anonymise_worker(db: Session, worker_id: uuid.UUID) -> None:
    """P5-8: name-linked fields removed; course, dates, hours and provider kept."""
    for r in thook.worker_records(db, worker_id):
        r.name_as_printed = None
        r.anonymised = True
    for n in db.scalars(
        select(TrainingNomination).where(TrainingNomination.worker_id == worker_id)
    ):
        n.signature_attachment_id = None
        if n.status == NominationStatus.nominated:
            n.status = NominationStatus.withdrawn
    db.flush()
