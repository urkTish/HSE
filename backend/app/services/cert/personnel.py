"""Personnel certificates (spec 4-third-party-cert §3.9, §4.4, §6.2, PC-1…PC-13, VF, P4-1…P4-6).

PC-3: the ID number typed from the card is compared through the Phase 2 blind index and never
stored; a mismatch is audited with the masked value only."""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.access_enums import WorkerStatus
from app.core.cert_enums import (
    CertificateStatus,
    CertKind,
    CertSource,
    CertStatusReason,
    CertVerificationMethod,
    IdMatchResult,
    NameMatch,
    ScanReason,
    ScanSide,
    VerificationStatus,
)
from app.core.clock import now, today
from app.core.enums import AuditAction, AuditResult, Capability, EntityType, NotificationKind
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import AttachmentOwner
from app.core.text import normalize
from app.models import Attachment, Deployment, PersonnelCertificate, Tpi, Worker, WorkerIdHistory
from app.schemas.attachments import SignedUrlRead
from app.schemas.cert_common import (
    AllowedCertAction,
    CertTransitionRequest,
    CertValidity,
    VerificationCreate,
    VerificationList,
    VerificationRead,
)
from app.schemas.hse_common import ApiWarning
from app.schemas.personnel_certs import (
    NOT_ACCEPTED_AR,
    NOT_ACCEPTED_EN,
    AssessmentRead,
    IdOnCard,
    PersonnelCertCreate,
    PersonnelCertListItem,
    PersonnelCertPage,
    PersonnelCertPreview,
    PersonnelCertPreviewRequest,
    PersonnelCertRead,
    PersonnelCertUpdate,
    RestrictionReviewRequest,
    ScanUrlRequest,
    WorkerCertificates,
    WorkerCertLine,
)
from app.services import audit, projects
from app.services.access import common as acommon
from app.services.cert import alerts, events, validity
from app.services.cert import common as cc
from app.services.cert import reference as ref
from app.services.cert import settings as cset
from app.services.cert import tpis as tsvc
from app.services.cert import verification as vf
from app.services.common import invalid_transition, paginate
from app.services.hse_common import Refs
from app.services.permissions import Grant, Principal, engagement_descendants, forbidden_error

C = Capability
CS = CertificateStatus
VS = VerificationStatus
SCAN_TTL = 300
NOT_SHOWN_METHODS = frozenset(
    {
        CertVerificationMethod.tpi_portal,
        CertVerificationMethod.tpi_qr_url,
        CertVerificationMethod.tpi_email,
        CertVerificationMethod.tpi_register_file,
    }
)


# ---- access (PC-1, P4-1) -------------------------------------------------------------------------


def get_row(db: Session, certificate_id: uuid.UUID) -> PersonnelCertificate:
    pc = db.get(PersonnelCertificate, certificate_id)
    if pc is None:
        raise not_found("Certificate")
    return pc


def deployment(db: Session, worker_id: uuid.UUID, project_id: uuid.UUID) -> Deployment | None:
    return db.scalar(
        select(Deployment)
        .where(Deployment.worker_id == worker_id, Deployment.project_id == project_id)
        .order_by(Deployment.mobilised_on.desc())
        .limit(1)
    )


def _covers(db: Session, g: Grant | None, worker_id: uuid.UUID, project_id: uuid.UUID) -> bool:
    if g is None:
        return False
    if g.engagement_ids is None and g.site_ids is None:
        return deployment(db, worker_id, project_id) is not None or g.engagement_ids is None
    dep = deployment(db, worker_id, project_id)
    return dep is not None and acommon.grant_covers(g, dep.site_ids, dep.engagement_id)


def _can_view(db: Session, p: Principal, pc: PersonnelCertificate) -> bool:
    return (
        _covers(db, p.grant(pc.project_id, C.personnel_cert_view), pc.worker_id, pc.project_id)
        and p.grant(pc.project_id, C.worker_view) is not None
    )


def get_visible(db: Session, p: Principal, certificate_id: uuid.UUID) -> PersonnelCertificate:
    pc = get_row(db, certificate_id)
    if p.grant(pc.project_id, C.personnel_cert_view) is None:
        raise not_found("Certificate")
    if not _can_view(db, p, pc):
        if p.grant(pc.project_id, C.worker_view) is None:
            raise forbidden_error()
        raise not_found("Certificate")
    return pc


def _require(db: Session, p: Principal, pc: PersonnelCertificate, cap: Capability) -> None:
    p.ensure_writer()
    if not _covers(db, p.grant(pc.project_id, cap), pc.worker_id, pc.project_id):
        raise forbidden_error()


def _require_holder(
    db: Session, p: Principal, project_id: uuid.UUID, worker_id: uuid.UUID
) -> Worker:
    """PC-1: a Contractor HSE Rep only for workers deployed in their C scope; HSE Officers for
    any worker with a deployment on their project (404 otherwise)."""
    projects.get_visible(db, p, project_id)
    g = cc.require(p, project_id, C.personnel_cert_submit)
    w = db.get(Worker, worker_id)
    dep = deployment(db, worker_id, project_id)
    if w is None or dep is None or not acommon.grant_covers(g, dep.site_ids, dep.engagement_id):
        raise not_found("Worker")
    if w.status == WorkerStatus.anonymised:
        raise validation_error("worker_id", "This worker record is anonymised.")
    return w


# ---- PC-3 / PC-4 ---------------------------------------------------------------------------------


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
    masked = acommon.mask_worker_id(card.id_type, card.id_number)
    audit.record(
        db,
        AuditAction.update,
        p.actor(project_id) if p is not None else audit.SYSTEM,
        entity_type=EntityType.personnel_certificate,
        entity_id=w.id,
        project_id=project_id,
        details={"cert_id_mismatch": masked, "worker_no": w.worker_no},
        result=AuditResult.failed,
        defer=True,  # persisted although the request is rolled back (nothing else is stored)
    )
    raise ApiError(
        422,
        ErrorCode.CERT_ID_MISMATCH,
        "The ID number on the card does not match this worker.",
        "رقم الهوية في البطاقة لا يطابق هذا العامل.",
        meta={"field": "id_on_card.id_number"},
    )


def name_match(printed: str, w: Worker) -> NameMatch:
    """PC-4: token-wise after rule-45 normalisation; the better of EN / AR."""
    pt = normalize(printed).split()
    best = NameMatch.none
    for full in (w.full_name_en, w.full_name_ar):
        wt = normalize(full).split()
        if not wt or not pt:
            continue
        if sorted(pt) == sorted(wt):
            return NameMatch.exact
        common = len(set(pt) & set(wt))
        if common >= 2:
            best = NameMatch.partial
    return best


# ---- validation ----------------------------------------------------------------------------------


@dataclass
class Checked:
    errors: list[tuple[int, str, str, str, str | None, dict[str, Any] | None]] = field(
        default_factory=list
    )
    warnings: list[ApiWarning] = field(default_factory=list)
    tpi_reason: str | None = None
    validity: tuple[date, Any, date] | None = None
    name_match: NameMatch = NameMatch.none

    def raise_first(self) -> None:
        if self.errors:
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


def check(
    db: Session,
    project_id: uuid.UUID,
    w: Worker,
    data: dict[str, Any],
    *,
    cert_id: uuid.UUID | None = None,
    submit: bool = False,
) -> Checked:
    out = Checked()
    s = cset.get(db, project_id)
    d0 = today()
    ctype = data["cert_type"]

    def err(
        st: int,
        code: str,
        en: str,
        ar: str,
        fld: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        out.errors.append((st, code, en, ar, fld, meta))

    if not cset.is_type(db, ctype):
        err(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Unknown certificate type.",
            "نوع شهادة غير معروف.",
            "cert_type",
        )
        return out
    if cset.training_codes(db) and ctype in cset.training_codes(db) and ctype not in ref.PCT:
        err(
            422,
            ErrorCode.CODE_IN_OTHER_CATALOGUE,
            "This code belongs to the training catalogue.",
            "هذا الرمز ضمن دليل التدريب.",
            "cert_type",
        )
    # BL-4
    if validity.active_ban(db, w.id, ctype, d0) is not None:
        err(422, ErrorCode.HOLDER_BANNED, NOT_ACCEPTED_EN, NOT_ACCEPTED_AR, "worker_id")
    issued: date = data["issued_on"]
    expiry: date | None = data.get("printed_expiry")
    if issued > d0:
        err(422, ErrorCode.VALIDATION_ERROR, "issued_on cannot be in the future.", "", "issued_on")
    if expiry is not None and expiry <= issued:
        err(
            422,
            ErrorCode.VALIDATION_ERROR,
            "printed_expiry must be after issued_on.",
            "",
            "printed_expiry",
        )
    # PC-2
    t = db.get(Tpi, data["tpi_id"])
    if t is None:
        err(404, ErrorCode.NOT_FOUND, "TPI not found.", "الجهة غير موجودة.", "tpi_id")
        return out
    q = select(PersonnelCertificate).where(
        PersonnelCertificate.tpi_id == t.id,
        PersonnelCertificate.cert_type == ctype,
        func.upper(PersonnelCertificate.cert_no) == str(data["cert_no"]).strip().upper(),
    )
    if cert_id is not None:
        q = q.where(PersonnelCertificate.id != cert_id)
    other = db.scalar(q.limit(1))
    if other is not None:
        if other.worker_id == w.id:
            err(
                409,
                ErrorCode.CERT_EXISTS,
                "This certificate is already recorded.",
                "هذه الشهادة مسجلة مسبقاً.",
                "cert_no",
            )
        else:
            ow = db.get(Worker, other.worker_id)
            err(
                422,
                ErrorCode.CERT_NO_REUSED,
                "This certificate number is recorded for another worker — "
                "possible fake certificate.",
                "رقم الشهادة مسجل لعامل آخر — احتمال شهادة مزورة.",
                "cert_no",
                {"existing_worker_no": ow.worker_no if ow else None},
            )
    # PC-5
    acc = tsvc.acceptability(db, t, issued, cert_type=ctype, project_id=project_id)
    if not acc.ok:
        out.tpi_reason = acc.reason or "TPI_NOT_APPROVED"
        e = tsvc.not_acceptable(out.tpi_reason, "tpi_id")
        err(
            422,
            ErrorCode.TPI_NOT_ACCEPTABLE,
            e.message,
            e.message_ar or e.message,
            "tpi_id",
            {"reason": out.tpi_reason},
        )
    # PC-7 scope / level
    pct = ref.PCT.get(ctype)
    scope = [getattr(x, "value", x) for x in data.get("scope_categories") or []]
    level = data.get("level")
    if pct is not None:
        if pct.scope_allowed:
            allowed = {q_.value for q_ in pct.scope_allowed}
            if not scope or not set(scope) <= allowed:
                err(
                    422,
                    ErrorCode.CERT_SCOPE_MISMATCH,
                    "Equipment scope must be within the certificate type's categories.",
                    "يجب أن يكون نطاق المعدات ضمن فئات نوع الشهادة.",
                    "scope_categories",
                    {"allowed": sorted(allowed)},
                )
        if level is not None and level in pct.rejected_levels:
            err(
                422,
                ErrorCode.LEVEL_NOT_ACCEPTED,
                "This certification level is not accepted.",
                "مستوى الشهادة هذا غير مقبول.",
                "level",
            )
        elif level is not None and pct.levels and level not in pct.levels:
            err(
                422,
                ErrorCode.VALIDATION_ERROR,
                "Level not valid for this certificate type.",
                "",
                "level",
            )
        elif level is None and pct.level_required:
            err(
                422,
                ErrorCode.LEVEL_REQUIRED,
                "The certification level is required.",
                "مستوى الشهادة مطلوب.",
                "level",
            )
    # §6.2 / W01
    months = cset.cap_months(db, s, ctype) or 36
    vu, lf, end = validity.personnel_validity(issued, expiry, months)
    out.validity = (vu, lf, end)
    if expiry is not None and expiry > end:
        out.warnings.append(
            cc.warn(
                "W01",
                f"Printed expiry is beyond the {months}-month cap: valid until {vu.isoformat()}.",
                f"تاريخ الانتهاء المطبوع يتجاوز حد {months} شهراً: صالحة حتى {vu.isoformat()}.",
                "printed_expiry",
            )
        )
    if vu < d0:
        err(
            422,
            ErrorCode.CERT_ALREADY_EXPIRED,
            "This certificate has already expired.",
            "انتهت صلاحية هذه الشهادة.",
            "printed_expiry",
        )
    # PC-4
    out.name_match = name_match(str(data["name_as_printed"]), w)
    if out.name_match != NameMatch.exact:
        out.warnings.append(
            cc.warn(
                "W02",
                f"Name on the card matches the worker: {out.name_match.value}.",
                f"تطابق الاسم في البطاقة مع العامل: {out.name_match.value}.",
                "name_as_printed",
            )
        )
    for wn in vf.foreign_url_warning(t, data.get("tpi_verification_url")):
        out.warnings.append(wn)
    if submit and not data.get("scan_front_attachment_id"):
        err(
            422,
            ErrorCode.SCAN_REQUIRED,
            "Attach the card scan (front) before submitting.",
            "أرفق صورة البطاقة (الوجه الأمامي) قبل التقديم.",
            "scan_front_attachment_id",
        )
    return out


def _data_of(pc: PersonnelCertificate) -> dict[str, Any]:
    return {c.key: getattr(pc, c.key) for c in pc.__table__.columns}


def _check_scan(db: Session, aid: uuid.UUID | None, cert_id: uuid.UUID | None, fld: str) -> None:
    if aid is None:
        return
    a = db.get(Attachment, aid)
    if (
        a is None
        or a.owner_type != AttachmentOwner.personnel_cert_scan
        or (cert_id is not None and a.owner_id != cert_id)
    ):
        raise validation_error(fld, "Upload the scan to this certificate first.")


# ---- reads ---------------------------------------------------------------------------------------


def validity_read(db: Session, pc: PersonnelCertificate, at: datetime) -> CertValidity:
    d = acommon.local_day(at)
    if (
        pc.status in (CS.draft, CS.historic, CS.rejected)
        and pc.status_reason != CertStatusReason.verification_failed
    ):
        ev = validity.LineEval(False, None, pc.valid_until)
    else:
        ev = validity.eval_personnel(db, pc, at, None, None, pc.project_id)
    return CertValidity(
        valid_until=pc.valid_until,
        limiting_factor=pc.limiting_factor,
        printed_date=pc.printed_expiry,
        platform_end=pc.cap_end,
        days_left=(pc.valid_until - d).days if pc.valid_until else None,
        in_force=ev.in_force,
        not_in_force_reason=ev.reason,
        expiring=ev.expiring,
        in_force_from=pc.in_force_from if ev.in_force else None,
        unverified_window_until=ev.window_until,
    )


_LABELS: dict[CertificateStatus, tuple[str, str]] = {
    CS.submitted: ("Submit", "تقديم"),
    CS.draft: ("Return to submitter", "إعادة لمقدمها"),
    CS.accepted: ("Accept", "قبول"),
    CS.rejected: ("Reject", "رفض"),
    CS.suspended: ("Suspend", "إيقاف"),
    CS.revoked: ("Revoke", "إلغاء"),
}


def allowed(db: Session, p: Principal, pc: PersonnelCertificate) -> list[AllowedCertAction]:
    def has(cap: Capability) -> bool:
        try:
            p.ensure_writer()
        except ApiError:
            return False
        return _covers(db, p.grant(pc.project_id, cap), pc.worker_id, pc.project_id)

    out: list[CertificateStatus] = []
    contractor = cc.contractor_only(p, pc.project_id)
    if pc.status == CS.draft and has(C.personnel_cert_submit):
        out.append(CS.submitted)
    elif pc.status == CS.submitted and has(C.cert_review) and not contractor:
        out += [CS.draft, CS.rejected]
        if pc.submitted_by_user_id != p.user.id:
            out.append(CS.accepted)
    elif pc.status == CS.accepted:
        if has(C.cert_suspend):
            out.append(CS.suspended)
        if has(C.cert_review) and not contractor:
            out.append(CS.revoked)
    elif pc.status == CS.suspended:
        if has(C.cert_suspend):
            out.append(CS.accepted)
        if has(C.cert_review) and not contractor:
            out.append(CS.revoked)
    labels = dict(_LABELS)
    if pc.status == CS.suspended:
        labels[CS.accepted] = ("Reinstate", "إعادة التفعيل")
    return [
        AllowedCertAction(to_status=s, label_en=labels[s][0], label_ar=labels[s][1]) for s in out
    ]


def cert_read(
    db: Session, p: Principal, pc: PersonnelCertificate, prompts: list[ApiWarning] | None = None
) -> PersonnelCertRead:
    at = now()
    refs = Refs(db).load(users=[pc.submitted_by_user_id, pc.reviewed_by_user_id])
    w = db.get(Worker, pc.worker_id)
    assert w is not None  # noqa: S101
    dep = deployment(db, pc.worker_id, pc.project_id)
    t = tsvc.get(db, pc.tpi_id)
    hse = cc.is_hse(p, pc.project_id)
    scan_view = p.grant(pc.project_id, C.personnel_cert_scan_view) is not None
    en, ar = cset.type_label(db, pc.cert_type)
    warnings: list[ApiWarning] = []
    if pc.status in (CS.draft, CS.submitted):
        ch = check(db, pc.project_id, w, _data_of(pc), cert_id=pc.id)
        warnings = ch.warnings + [
            x for x in ch.error_warnings() if x.code == ErrorCode.CERT_NO_REUSED
        ]
    else:
        warnings = vf.foreign_url_warning(t, pc.tpi_verification_url)
    val = validity_read(db, pc, at)
    if val.unverified_window_until is not None:
        warnings.append(
            cc.warn(
                "CERT_UNVERIFIED",
                "Accepted but not yet verified with the TPI.",
                "مقبولة ولم يتم التحقق منها لدى الجهة بعد.",
            )
        )
    banned = validity.active_ban(db, pc.worker_id, pc.cert_type, today()) is not None
    not_acc = not hse and (pc.status in (CS.rejected, CS.revoked) or banned)
    extra: dict[str, Any] = {}
    if scan_view:
        extra["medical_restriction_on_card"] = pc.medical_restriction_on_card
        extra["restriction_reviewed_at"] = pc.restriction_reviewed_at
    return PersonnelCertRead(
        id=pc.id,
        record_no=pc.record_no,
        project_id=pc.project_id,
        worker=acommon.worker_ref(w, True),
        engagement=refs.eng(dep.engagement_id) if dep and dep.engagement_id else None,
        cert_type=pc.cert_type,
        cert_type_label_en=en,
        cert_type_label_ar=ar,
        tpi=cc.tpi_ref(t, p, pc.project_id),
        cert_no=pc.cert_no or "",
        issued_on=pc.issued_on,
        printed_expiry=pc.printed_expiry,
        validity=val,
        scope_categories=list(pc.scope_categories or []),
        max_capacity_t=pc.max_capacity_t,
        level=pc.level,
        limitations=cc.plimitation_reads(pc.limitations),
        name_as_printed=pc.name_as_printed or "",
        id_match_result=pc.id_match_result,
        name_match=pc.name_match,
        identity_confirmed_by_tpi=pc.identity_confirmed_by_tpi,
        assessment=AssessmentRead(**pc.assessment) if pc.assessment else None,
        has_scan_front=pc.scan_front_attachment_id is not None and pc.scans_deleted_at is None,
        has_scan_back=pc.scan_back_attachment_id is not None and pc.scans_deleted_at is None,
        tpi_verification_url=pc.tpi_verification_url,
        status=pc.status,
        status_reason=pc.status_reason
        if hse or pc.status_reason not in _SENSITIVE_REASONS
        else None,
        status_reason_text=pc.status_reason_text if hse else None,
        not_accepted_message_en=NOT_ACCEPTED_EN if not_acc else None,
        not_accepted_message_ar=NOT_ACCEPTED_AR if not_acc else None,
        verification_status=pc.verification_status
        if hse or pc.verification_status != VS.failed
        else VS.not_verified,
        verification_due_on=pc.verification_due_on,
        source=pc.source,
        superseded_by_id=pc.superseded_by_id,
        submitted_by=refs.user(pc.submitted_by_user_id),
        submitted_at=pc.submitted_at,
        reviewed_by=refs.user(pc.reviewed_by_user_id),
        reviewed_at=pc.reviewed_at,
        warnings=warnings,
        prompts=prompts or [],
        allowed_actions=allowed(db, p, pc),
        created_at=pc.created_at,
        updated_at=pc.updated_at,
        **extra,
    )


_SENSITIVE_REASONS = frozenset({CertStatusReason.verification_failed})


def read(db: Session, p: Principal, certificate_id: uuid.UUID) -> PersonnelCertRead:
    return cert_read(db, p, get_visible(db, p, certificate_id))


def _list_item(
    db: Session, pc: PersonnelCertificate, at: datetime, refs: Refs
) -> PersonnelCertListItem:
    w = db.get(Worker, pc.worker_id)
    assert w is not None  # noqa: S101
    dep = deployment(db, pc.worker_id, pc.project_id)
    t = db.get(Tpi, pc.tpi_id)
    v = validity_read(db, pc, at)
    return PersonnelCertListItem(
        id=pc.id,
        record_no=pc.record_no,
        worker=acommon.worker_ref(w, True),
        engagement=refs.eng(dep.engagement_id) if dep and dep.engagement_id else None,
        cert_type=pc.cert_type,
        tpi_code=t.tpi_code if t else "",
        cert_no=pc.cert_no or "",
        issued_on=pc.issued_on,
        valid_until=pc.valid_until,
        limiting_factor=pc.limiting_factor,
        days_left=v.days_left,
        in_force=v.in_force,
        expiring=v.expiring,
        status=pc.status,
        verification_status=pc.verification_status,
        level=pc.level,
        source=pc.source,
    )


def list_certificates(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    q: str | None = None,
    cert_types: list[str] | None = None,
    statuses: list[CertificateStatus] | None = None,
    verification_statuses: list[VerificationStatus] | None = None,
    tpi_id: uuid.UUID | None = None,
    worker_id: uuid.UUID | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    include_subcontractors: bool = True,
    source: CertSource | None = None,
    in_force: bool | None = None,
    expiring_days: int | None = None,
    verification_overdue: bool | None = None,
) -> PersonnelCertPage:
    project = projects.get_visible(db, p, project_id)
    g = p.grant(project.id, C.personnel_cert_view)
    if g is None or p.grant(project.id, C.worker_view) is None:
        raise forbidden_error()
    stmt = (
        select(PersonnelCertificate)
        .join(Worker, Worker.id == PersonnelCertificate.worker_id)
        .where(PersonnelCertificate.project_id == project.id)
    )

    def dep_exists(*conds: Any) -> Any:
        return exists(
            select(Deployment.id).where(
                Deployment.worker_id == PersonnelCertificate.worker_id,
                Deployment.project_id == PersonnelCertificate.project_id,
                *conds,
            )
        )

    if g.engagement_ids is not None:
        stmt = stmt.where(dep_exists(Deployment.engagement_id.in_(list(g.engagement_ids))))
    if g.site_ids is not None:
        stmt = stmt.where(dep_exists(Deployment.site_ids.overlap(list(g.site_ids))))
    if q:
        pat = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Worker.worker_no.ilike(pat),
                PersonnelCertificate.cert_no.ilike(pat),
                PersonnelCertificate.record_no.ilike(pat),
            )
        )
    if cert_types:
        stmt = stmt.where(PersonnelCertificate.cert_type.in_(cert_types))
    if statuses:
        stmt = stmt.where(PersonnelCertificate.status.in_(statuses))
    if verification_statuses:
        stmt = stmt.where(PersonnelCertificate.verification_status.in_(verification_statuses))
    if tpi_id:
        stmt = stmt.where(PersonnelCertificate.tpi_id == tpi_id)
    if worker_id:
        stmt = stmt.where(PersonnelCertificate.worker_id == worker_id)
    if source is not None:
        stmt = stmt.where(PersonnelCertificate.source == source)
    if engagement_ids:
        ids: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            for e in engagement_ids:
                ids |= engagement_descendants(db, e)
        stmt = stmt.where(dep_exists(Deployment.engagement_id.in_(ids)))
    d0 = today()
    if verification_overdue is not None:
        cond = (
            PersonnelCertificate.status.in_([CS.submitted, CS.accepted])
            & PersonnelCertificate.verification_status.in_([VS.not_verified, VS.unable_to_verify])
            & (PersonnelCertificate.verification_due_on < d0)
        )
        stmt = stmt.where(cond if verification_overdue else ~cond)
    stmt = stmt.order_by(
        Worker.worker_no, PersonnelCertificate.cert_type, PersonnelCertificate.issued_on.desc()
    )
    at = now()
    refs = Refs(db)
    if in_force is None and expiring_days is None:
        rows, total = paginate(db, stmt, page, page_size)
        items = [_list_item(db, pc, at, refs) for pc in rows]
    else:
        all_items = [_list_item(db, pc, at, refs) for pc in db.scalars(stmt)]
        if in_force is not None:
            all_items = [i for i in all_items if i.in_force == in_force]
        if expiring_days is not None:
            lim = d0 + timedelta(days=expiring_days)
            all_items = [
                i for i in all_items if i.in_force and i.valid_until and i.valid_until <= lim
            ]
        total = len(all_items)
        items = all_items[(page - 1) * page_size : page * page_size]
    return PersonnelCertPage(items=items, total=total, page=page, page_size=page_size)


# ---- create / update / preview -------------------------------------------------------------------


def _fields(body: Any) -> dict[str, Any]:
    data: dict[str, Any] = dict(
        body.model_dump(exclude={"worker_id", "id_on_card"}, exclude_unset=False)
    )
    data["cert_no"] = str(data["cert_no"]).strip()
    data["scope_categories"] = [getattr(x, "value", x) for x in data.get("scope_categories") or []]
    data["limitations"] = [
        {"code": getattr(x["code"], "value", x["code"]), "text": x.get("text")}
        for x in data.get("limitations") or []
    ]
    if data.get("assessment"):
        a = data["assessment"]
        data["assessment"] = {
            "theory_on": a.get("theory_on").isoformat() if a.get("theory_on") else None,
            "practical_on": a.get("practical_on").isoformat() if a.get("practical_on") else None,
            "language": getattr(a.get("language"), "value", a.get("language")),
        }
    return data


def _apply_validity(db: Session, pc: PersonnelCertificate) -> None:
    s = cset.get(db, pc.project_id)
    months = cset.cap_months(db, s, pc.cert_type) or 36
    pc.valid_until, pc.limiting_factor, pc.cap_end = validity.personnel_validity(
        pc.issued_on, pc.printed_expiry, months
    )


def create(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    body: PersonnelCertCreate,
    *,
    source: CertSource = CertSource.manual,
    batch_id: uuid.UUID | None = None,
) -> PersonnelCertRead:
    w = _require_holder(db, p, project_id, body.worker_id)
    data = _fields(body)
    ch = check(db, project_id, w, data)
    if any(e[1] == ErrorCode.CERT_NO_REUSED for e in ch.errors):
        _alert_reused(db, project_id, data["cert_no"], w)
    ch.raise_first()
    for k in ("scan_front_attachment_id", "scan_back_attachment_id"):
        _check_scan(db, data.get(k), None, k)
    idm = id_match(db, p, w, body.id_on_card, project_id)
    pc = new_row(db, p, project_id, w, data, idm, ch.name_match, source=source, batch_id=batch_id)
    return cert_read(db, p, pc)


def _alert_reused(db: Session, project_id: uuid.UUID, cert_no: str, w: Worker) -> None:
    alerts.send(
        db,
        alerts.officers(db, project_id),
        NotificationKind.verification_failed,
        f"Certificate number {cert_no} presented for another worker ({w.worker_no})",
        f"رقم الشهادة {cert_no} مقدم لعامل آخر ({w.worker_no})",
        EntityType.worker,
        w.id,
        project_id,
    )


def new_row(
    db: Session,
    p: Principal | None,
    project_id: uuid.UUID,
    w: Worker,
    data: dict[str, Any],
    idm: IdMatchResult,
    nm: NameMatch,
    *,
    source: CertSource = CertSource.manual,
    batch_id: uuid.UUID | None = None,
    seed_fake: bool = False,
) -> PersonnelCertificate:
    seq = (db.scalar(select(func.max(PersonnelCertificate.seq))) or 0) + 1
    pc = PersonnelCertificate(
        id=uuid.uuid4(),
        seq=seq,
        record_no=f"PCR-{seq:06d}",
        project_id=project_id,
        worker_id=w.id,
        id_match_result=idm,
        name_match=nm,
        status=CS.draft,
        verification_status=VS.not_verified,
        source=source,
        import_batch_id=batch_id,
        alerts_sent=[],
        **data,
    )
    _apply_validity(db, pc)
    cc.stamp(pc, p, create=True)
    db.add(pc)
    db.flush()
    for k in ("scan_front_attachment_id", "scan_back_attachment_id"):
        aid = getattr(pc, k)
        a = db.get(Attachment, aid) if aid else None
        if a is not None and a.owner_type == AttachmentOwner.personnel_cert_scan:
            a.owner_id = pc.id
    cc.record(db, p, AuditAction.create, EntityType.personnel_certificate, pc, project_id)
    return pc


def preview(
    db: Session, p: Principal, project_id: uuid.UUID, body: PersonnelCertPreviewRequest
) -> PersonnelCertPreview:
    projects.get_visible(db, p, project_id)
    g = cc.require(p, project_id, C.personnel_cert_submit, write=False)
    w = db.get(Worker, body.worker_id)
    dep = deployment(db, body.worker_id, project_id)
    if w is None or dep is None or not acommon.grant_covers(g, dep.site_ids, dep.engagement_id):
        raise not_found("Worker")
    ch = check(db, project_id, w, _fields(body), submit=False)
    d0 = today()
    vu, lf, end = ch.validity or (None, None, None)
    return PersonnelCertPreview(
        validity=CertValidity(
            valid_until=vu,
            limiting_factor=lf,
            printed_date=body.printed_expiry,
            platform_end=end,
            days_left=(vu - d0).days if vu else None,
            in_force=False,
            not_in_force_reason=None,
            expiring=False,
            in_force_from=None,
        ),
        name_match=ch.name_match,
        tpi_acceptable=ch.tpi_reason is None,
        tpi_reason=ch.tpi_reason,
        errors=ch.error_warnings(),
        warnings=ch.warnings,
    )


def update(
    db: Session, p: Principal, certificate_id: uuid.UUID, body: PersonnelCertUpdate
) -> PersonnelCertRead:
    pc = get_visible(db, p, certificate_id)
    _require(db, p, pc, C.personnel_cert_submit)
    if pc.status != CS.draft:
        raise invalid_transition("Certificate", pc.status.value, "edit")
    before = cc.snap(pc)
    ch_ = body.changes()
    card = ch_.pop("id_on_card", None)
    for k, raw in ch_.items():
        v = raw
        if k == "scope_categories":
            v = [getattr(x, "value", x) for x in raw or []]
        elif k == "limitations":
            v = [
                {"code": getattr(x["code"], "value", x["code"]), "text": x.get("text")}
                for x in raw or []
            ]
        elif k == "assessment" and raw:
            v = {
                kk: (vv.isoformat() if isinstance(vv, date) else getattr(vv, "value", vv))
                for kk, vv in raw.items()
            }
        elif k == "cert_no":
            v = str(raw).strip()
        setattr(pc, k, v)
    for k in ("scan_front_attachment_id", "scan_back_attachment_id"):
        if k in ch_:
            _check_scan(db, getattr(pc, k), pc.id, k)
    w = db.get(Worker, pc.worker_id)
    assert w is not None  # noqa: S101
    ch = check(db, pc.project_id, w, _data_of(pc), cert_id=pc.id)
    ch.raise_first()
    pc.name_match = ch.name_match
    if card is not None and body.id_on_card is not None:
        pc.id_match_result = id_match(db, p, w, body.id_on_card, pc.project_id)
    _apply_validity(db, pc)
    cc.stamp(pc, p)
    db.flush()
    cc.record(
        db, p, AuditAction.update, EntityType.personnel_certificate, pc, pc.project_id, before
    )
    return cert_read(db, p, pc)


# ---- transitions ---------------------------------------------------------------------------------


def _reason(body: CertTransitionRequest, n: int = 1) -> str:
    r = (body.reason or "").strip()
    if len(r) < n:
        raise validation_error("reason", f"Give a reason (≥ {n} characters).")
    return r


def _publish(db: Session, pc: PersonnelCertificate) -> None:
    events.publish(db, "cert.status_changed", project_id=pc.project_id, worker_ids=[pc.worker_id])


def consider_ban_prompt() -> ApiWarning:
    """PC-11: no ban is automatic."""
    return cc.warn(
        "CONSIDER_WORKER_BAN",
        "Consider a worker ban under capability 49? (No ban is automatic.)",
        "هل تنظر في حظر العامل (الصلاحية 49)؟ (لا يوجد حظر تلقائي.)",
    )


def transition(
    db: Session, p: Principal, certificate_id: uuid.UUID, body: CertTransitionRequest
) -> PersonnelCertRead:
    pc = get_visible(db, p, certificate_id)
    src, dst = pc.status, body.to_status
    before = cc.snap(pc)
    at = now()
    prompts: list[ApiWarning] = []
    w = db.get(Worker, pc.worker_id)
    assert w is not None  # noqa: S101
    if src == CS.draft and dst == CS.submitted:
        _require(db, p, pc, C.personnel_cert_submit)
        if pc.scan_front_attachment_id is None:
            a = db.scalar(
                select(Attachment)
                .where(
                    Attachment.owner_type == AttachmentOwner.personnel_cert_scan,
                    Attachment.owner_id == pc.id,
                )
                .order_by(Attachment.created_at)
                .limit(1)
            )
            if a is not None:
                pc.scan_front_attachment_id = a.id
        ch = check(db, pc.project_id, w, _data_of(pc), cert_id=pc.id, submit=True)
        if any(e[1] == ErrorCode.CERT_NO_REUSED for e in ch.errors):
            _alert_reused(db, pc.project_id, pc.cert_no or "", w)
        ch.raise_first()
        submit(db, p, pc, at)
    elif src == CS.submitted and dst == CS.draft:
        _require(db, p, pc, C.cert_review)
        pc.status_reason_text = _reason(body, 10)
        pc.status = CS.draft
        if pc.submitted_by_user_id:
            alerts.send(
                db,
                [pc.submitted_by_user_id],
                NotificationKind.certificate_returned,
                f"Certificate {pc.record_no} returned",
                f"أعيدت الشهادة {pc.record_no}",
                EntityType.personnel_certificate,
                pc.id,
                pc.project_id,
                body_en=pc.status_reason_text,
                body_ar=pc.status_reason_text,
            )
    elif src == CS.submitted and dst == CS.accepted:
        _require(db, p, pc, C.cert_review)
        if cc.contractor_only(p, pc.project_id):
            raise forbidden_error()
        if pc.submitted_by_user_id == p.user.id:
            raise cc.sod()
        ch = check(db, pc.project_id, w, _data_of(pc), cert_id=pc.id)
        ch.errors = [e for e in ch.errors if e[1] != ErrorCode.CERT_ALREADY_EXPIRED]
        ch.raise_first()
        if pc.name_match == NameMatch.none:
            if not body.identity_confirmed_by_tpi:
                raise ApiError(
                    422,
                    ErrorCode.NAME_MISMATCH_CONFIRMATION,
                    "The name does not match: confirm the identity with the TPI to accept.",
                    "الاسم غير مطابق: أكّد الهوية مع الجهة للقبول.",
                )
            pc.identity_confirmed_by_tpi = True
        accept(db, p, pc, at)
    elif src == CS.submitted and dst == CS.rejected:
        _require(db, p, pc, C.cert_review)
        pc.status_reason_text = _reason(body)
        pc.status_reason = body.reason_code or CertStatusReason.document_review
        pc.status = CS.rejected
        pc.reviewed_by_user_id, pc.reviewed_at = p.user.id, at
        pc.ended_on = today()
    elif src == CS.accepted and dst == CS.suspended:
        _require(db, p, pc, C.cert_suspend)
        pc.status_reason_text = _reason(body)
        pc.status_reason = body.reason_code or CertStatusReason.hse_suspension
        pc.status = CS.suspended
        prompts.append(consider_ban_prompt())
    elif src == CS.suspended and dst == CS.accepted:
        _require(db, p, pc, C.cert_suspend)
        pc.status_reason_text = _reason(body)
        pc.status_reason = None
        pc.status = CS.accepted
    elif src in (CS.accepted, CS.suspended) and dst == CS.revoked:
        _require(db, p, pc, C.cert_review)
        if cc.contractor_only(p, pc.project_id):
            raise forbidden_error()
        pc.status_reason_text = _reason(body)
        pc.status_reason = body.reason_code or CertStatusReason.tpi_revocation_notice
        pc.status = CS.revoked
        pc.ended_on = today()
        prompts.append(consider_ban_prompt())
    else:
        raise invalid_transition("Certificate", src.value, dst.value)
    cc.stamp(pc, p)
    db.flush()
    cc.record(
        db,
        p,
        AuditAction.status_change,
        EntityType.personnel_certificate,
        pc,
        pc.project_id,
        before,
        {"from": src.value, "to": dst.value},
    )
    if pc.status != src:
        _publish(db, pc)
    return cert_read(db, p, pc, prompts)


def submit(db: Session, p: Principal | None, pc: PersonnelCertificate, at: datetime) -> None:
    s = cset.get(db, pc.project_id)
    pc.status = CS.submitted
    pc.status_reason_text = None
    if p is not None:
        pc.submitted_by_user_id = p.user.id
    pc.submitted_at = at
    pc.verification_due_on = vf.due_on(acommon.local_day(at), s.verification_due_days)
    alerts.send(
        db,
        alerts.officers(db, pc.project_id),
        NotificationKind.certificate_submitted,
        f"Personnel certificate {pc.record_no} ({pc.cert_type}) submitted",
        f"قُدمت شهادة الأفراد {pc.record_no} ({pc.cert_type})",
        EntityType.personnel_certificate,
        pc.id,
        pc.project_id,
    )


def accept(db: Session, p: Principal | None, pc: PersonnelCertificate, at: datetime) -> None:
    pc.status = CS.accepted
    pc.status_reason = None
    pc.reviewed_by_user_id = p.user.id if p is not None else None
    pc.reviewed_at = at
    pc.accepted_at = at
    db.flush()
    maybe_in_force(db, pc, at)


def maybe_in_force(db: Session, pc: PersonnelCertificate, at: datetime) -> None:
    """PC-9: accepted and verified → in force; the older certificate of the same type is
    superseded (no gap)."""
    if (
        pc.status != CS.accepted
        or pc.verification_status != VS.verified
        or pc.in_force_from is not None
    ):
        return
    pc.in_force_from = max(x for x in (pc.accepted_at, pc.verified_at) if x is not None)
    for old in db.scalars(
        select(PersonnelCertificate).where(
            PersonnelCertificate.worker_id == pc.worker_id,
            PersonnelCertificate.cert_type == pc.cert_type,
            PersonnelCertificate.id != pc.id,
            PersonnelCertificate.status == CS.accepted,
            PersonnelCertificate.superseded_by_id.is_(None),
        )
    ):
        if old.issued_on > pc.issued_on:
            continue
        old.superseded_by_id = pc.id
        old.status = CS.superseded
        old.status_reason = CertStatusReason.newer_certificate
        old.ended_on = acommon.local_day(pc.in_force_from)
        cc.record(
            db,
            None,
            AuditAction.status_change,
            EntityType.personnel_certificate,
            old,
            old.project_id,
            details={"from": "accepted", "to": "superseded", "by": pc.record_no},
        )
    db.flush()


# ---- verification --------------------------------------------------------------------------------


def verifications(db: Session, p: Principal, certificate_id: uuid.UUID) -> VerificationList:
    pc = get_visible(db, p, certificate_id)
    return vf.list_for(db, p, CertKind.personnel, pc)


def verify(
    db: Session, p: Principal, certificate_id: uuid.UUID, body: VerificationCreate
) -> VerificationRead:
    pc = get_visible(db, p, certificate_id)
    cc.require(p, pc.project_id, C.cert_verify)  # 403 before any content check (row 108)
    if (
        pc.id_match_result == IdMatchResult.not_shown
        and body.outcome.value == "confirmed"
        and body.method not in NOT_SHOWN_METHODS
        and body.method.value != "original_sighted"  # never verifies (VF-3)
    ):
        raise validation_error(
            "method",
            "The card shows no ID: verify with the TPI portal, QR link, e-mail or register file.",
        )
    dep = deployment(db, pc.worker_id, pc.project_id)
    employer = None
    if dep is not None and dep.engagement_id is not None:
        from app.models import ProjectEngagement  # noqa: PLC0415

        eng = db.get(ProjectEngagement, dep.engagement_id)
        employer = eng.contractor_id if eng else None
    w = db.get(Worker, pc.worker_id)

    def on_change(before: VS, after: VS, rec: Any) -> None:
        if after == VS.verified:
            maybe_in_force(db, pc, rec.performed_at)
        elif after == VS.failed:
            vf.fail_effects(pc)
            pc.ended_on = today()
        _publish(db, pc)

    return vf.record(
        db,
        p,
        CertKind.personnel,
        pc,
        body,
        holder_contractors=[employer],
        on_change=on_change,
        holder_ref=w.worker_no if w else pc.record_no,
    )


# ---- scans (P4-3), restriction review (PC-13) ----------------------------------------------------


def scan_url(
    db: Session, p: Principal, certificate_id: uuid.UUID, body: ScanUrlRequest
) -> SignedUrlRead:
    from app.core.config import API_PREFIX, get_settings  # noqa: PLC0415

    pc = get_visible(db, p, certificate_id)
    if p.grant(pc.project_id, C.personnel_cert_scan_view) is None:
        raise forbidden_error()
    if body.reason == ScanReason.other and not (body.reason_text or "").strip():
        raise validation_error("reason_text", "Describe the reason.")
    aid = pc.scan_front_attachment_id if body.side == ScanSide.front else pc.scan_back_attachment_id
    if aid is None and body.side == ScanSide.front:  # a draft's scan is bound at Submit
        aid = db.scalar(
            select(Attachment.id)
            .where(
                Attachment.owner_type == AttachmentOwner.personnel_cert_scan,
                Attachment.owner_id == pc.id,
            )
            .order_by(Attachment.created_at)
            .limit(1)
        )
    if aid is None or pc.scans_deleted_at is not None:
        raise not_found("Scan")
    import time  # noqa: PLC0415

    expires = int(time.time()) + SCAN_TTL
    sig = crypto.sign(f"{aid}:{expires}", get_settings().attachment_url_secret)
    audit.record(
        db,
        AuditAction.sensitive_field_read,
        p.actor(pc.project_id),
        entity_type=EntityType.personnel_certificate,
        entity_id=pc.id,
        project_id=pc.project_id,
        fields_read=["cert_scan"],
        details={
            "side": body.side.value,
            "reason": body.reason.value,
            "reason_text": body.reason_text,
        },
    )
    from datetime import UTC  # noqa: PLC0415

    return SignedUrlRead(
        url=f"{API_PREFIX}/attachments/{aid}/content?expires={expires}&signature={sig}",
        expires_at=datetime.fromtimestamp(expires, UTC),
    )


def review_restriction(
    db: Session, p: Principal, certificate_id: uuid.UUID, body: RestrictionReviewRequest
) -> PersonnelCertRead:
    pc = get_visible(db, p, certificate_id)
    _require(db, p, pc, C.cert_review)
    if not pc.medical_restriction_on_card:
        raise validation_error("certificate_id", "The card states no restriction.")
    before = cc.snap(pc)
    pc.restriction_reviewed_at = now()
    pc.restriction_reviewed_by_user_id = p.user.id
    db.flush()
    cc.record(
        db,
        p,
        AuditAction.update,
        EntityType.personnel_certificate,
        pc,
        pc.project_id,
        before,
        {"restriction_reviewed": True, "note": body.note},
    )
    _publish(db, pc)
    return cert_read(db, p, pc)


# ---- worker page (PC-12) -------------------------------------------------------------------------


def trade_requirement(db: Session, project_id: uuid.UUID, worker_id: uuid.UUID) -> str | None:
    dep = deployment(db, worker_id, project_id)
    if dep is None:
        return None
    s = cset.get(db, project_id)
    return (s.trade_cert_requirements or {}).get(dep.trade.value)


def worker_certificates(
    db: Session, p: Principal, worker_id: uuid.UUID, project_id: uuid.UUID | None = None
) -> WorkerCertificates:
    w = db.get(Worker, worker_id)
    if w is None:
        raise not_found("Worker")
    grants = p.project_grants(C.personnel_cert_view)
    pids = [project_id] if project_id else None
    deps = list(db.scalars(select(Deployment).where(Deployment.worker_id == worker_id)))
    visible = []
    for dep in deps:
        if pids and dep.project_id not in pids:
            continue
        g = p.grant(dep.project_id, C.personnel_cert_view)
        if (
            g is not None
            and p.grant(dep.project_id, C.worker_view) is not None
            and acommon.grant_covers(g, dep.site_ids, dep.engagement_id)
        ):
            visible.append(dep)
    if not visible and not (grants is None and p.is_manager):
        raise not_found("Worker")
    at = now()
    hse = any(cc.is_hse(p, d.project_id) for d in visible) or p.is_manager
    lines = []
    for pc in validity.worker_certs(db, worker_id):
        if pc.status == CS.superseded:
            continue
        ev = validity.eval_personnel(db, pc, at, None, None, pc.project_id)
        t = db.get(Tpi, pc.tpi_id)
        en, ar = cset.type_label(db, pc.cert_type)
        lines.append(
            WorkerCertLine(
                id=pc.id,
                cert_type=pc.cert_type,
                cert_type_label_en=en,
                cert_type_label_ar=ar,
                cert_no=pc.cert_no or "",
                tpi_code=t.tpi_code if t else "",
                valid_until=pc.valid_until,
                in_force=ev.in_force,
                not_in_force_reason=(ev.reason.value if ev.reason else None)
                if hse or ev.reason not in (ref.R.CERT_HOLDER_BANNED, ref.R.CERT_REVOKED)
                else "NOT_ACCEPTED",
                status=pc.status,
                level=pc.level,
                scope_categories=list(pc.scope_categories or []),
            )
        )
    pid = project_id or (visible[0].project_id if visible else None)
    req = trade_requirement(db, pid, worker_id) if pid else None
    met = None
    if req:
        met = validity.best_personnel(
            db, worker_id, ref.satisfying_types(req) or [req], at, pid
        ).ev.in_force
    banned = validity.active_ban(db, worker_id, None, today()) is not None
    return WorkerCertificates(
        worker=acommon.worker_ref(w, True),
        certificates=lines,
        trade_requirement=req,
        trade_requirement_met=met,
        banned=banned,
        ban_message_en=NOT_ACCEPTED_EN if banned else None,
        ban_message_ar=NOT_ACCEPTED_AR if banned else None,
    )


# ---- jobs ----------------------------------------------------------------------------------------


def expiry_job(db: Session, at: datetime | None = None) -> int:
    """Accepted → Expired when today > valid_until (§4.4)."""
    at = at or now()
    d = acommon.local_day(at)
    n = 0
    for pc in db.scalars(
        select(PersonnelCertificate).where(
            PersonnelCertificate.status == CS.accepted, PersonnelCertificate.valid_until < d
        )
    ):
        pc.status = CS.expired
        pc.ended_on = d
        cc.record(
            db,
            None,
            AuditAction.status_change,
            EntityType.personnel_certificate,
            pc,
            pc.project_id,
            details={"from": "accepted", "to": "expired"},
        )
        _publish(db, pc)
        n += 1
    return n


# ---- retention (P4-7) ----------------------------------------------------------------------------

ENDED = (CS.expired, CS.superseded, CS.revoked, CS.rejected)


def _erase_scans(db: Session, pc: PersonnelCertificate) -> int:
    from app.services import attachments  # noqa: PLC0415

    n = 0
    for a in db.scalars(
        select(Attachment).where(
            Attachment.owner_type == AttachmentOwner.personnel_cert_scan,
            Attachment.owner_id == pc.id,
        )
    ):
        attachments.erase(db, a)
        n += 1
    pc.scan_front_attachment_id = None
    pc.scan_back_attachment_id = None
    pc.scans_deleted_at = now()
    return n


def scan_retention_job(db: Session, day: date | None = None) -> int:
    """P4-7: scans of certificates that ended (Expired / Superseded / Revoked / Rejected) more
    than `cert_scan_retention_years` ago are deleted; the metadata stays; each deletion is
    audited. Certificates referenced by an incident follow Phase 1 P1-5 instead (kept)."""
    from app.kpi.periods import add_months  # noqa: PLC0415

    day = day or today()
    n = 0
    for pc in list(
        db.scalars(
            select(PersonnelCertificate).where(
                PersonnelCertificate.status.in_(ENDED),
                PersonnelCertificate.ended_on.is_not(None),
            )
        )
    ):
        years = cset.get(db, pc.project_id).cert_scan_retention_years
        assert pc.ended_on is not None  # noqa: S101
        if day < add_months(pc.ended_on, 12 * years):
            continue
        has_scan = db.scalar(
            select(Attachment.id)
            .where(
                Attachment.owner_type == AttachmentOwner.personnel_cert_scan,
                Attachment.owner_id == pc.id,
            )
            .limit(1)
        )
        if has_scan is None:
            continue
        files = _erase_scans(db, pc)
        audit.record(
            db,
            AuditAction.retention_purge,
            entity_type=EntityType.personnel_certificate,
            entity_id=pc.id,
            project_id=pc.project_id,
            details={"scans_deleted": files, "retention_years": years, "rule": "P4-7"},
        )
        n += 1
    db.flush()
    return n


def anonymise_worker(db: Session, worker_id: uuid.UUID) -> None:
    """P4-7 with Phase 2 P2-7: the worker's certificates lose cert_no, the printed name and the
    scans; type and validity stay for statistics."""
    for pc in db.scalars(
        select(PersonnelCertificate).where(PersonnelCertificate.worker_id == worker_id)
    ):
        _erase_scans(db, pc)
        pc.cert_no = None
        pc.name_as_printed = None
        pc.tpi_verification_url = None
