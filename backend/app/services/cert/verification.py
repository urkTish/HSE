"""Verification of equipment and personnel certificates with the issuing TPI (spec
4-third-party-cert §3.10, §4.4, VF-1…VF-7). Shared by `equipment_certs` and `personnel`.

The platform never opens external URLs (VF-4): the verifier opens the TPI page on their own
device and records the outcome here."""

import uuid
from collections.abc import Callable, Iterable
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cert_enums import (
    CertificateStatus,
    CertKind,
    CertStatusReason,
    CertVerificationMethod,
    VerificationDifference,
    VerificationOutcome,
    VerificationStatus,
)
from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.hse_enums import AttachmentOwner
from app.models import Attachment, CertVerification, Tpi
from app.schemas.cert_common import (
    VerificationCreate,
    VerificationList,
    VerificationLogItem,
    VerificationLogPage,
    VerificationRead,
)
from app.services import projects
from app.services.cert import alerts
from app.services.cert import common as cc
from app.services.cert import tpis as tsvc
from app.services.common import paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error

C = Capability
M = CertVerificationMethod
O = VerificationOutcome  # noqa: E741
VS = VerificationStatus
CS = CertificateStatus

COUNTING = frozenset(
    {M.tpi_portal, M.tpi_qr_url, M.tpi_email, M.tpi_phone, M.tpi_register_file, M.client_register}
)
FAILING = frozenset({O.not_found, O.details_differ, O.revoked_by_tpi})
NO_RESPONSE_GAP = timedelta(hours=24)


def channel_registered(t: Tpi, method: CertVerificationMethod, channel: str) -> bool:
    """VF-3: the channel must be on the TPI record."""
    ch = channel.strip().lower()
    if method == M.original_sighted:
        return True
    if method in (M.client_register,):
        return bool(ch)
    if method == M.tpi_phone:
        digits = "".join(c for c in ch if c.isdigit())
        reg = "".join(c for c in (t.verification_phone or "") if c.isdigit())
        return bool(reg) and digits.endswith(reg[-9:])
    if method == M.tpi_email:
        if t.verification_email and ch == t.verification_email.strip().lower():
            return True
        return "@" in ch and tsvc.domain_registered(t, tsvc.host_of(ch))
    host = tsvc.host_of(ch)
    if not host:
        return False
    if t.verification_portal_url and host == tsvc.host_of(t.verification_portal_url):
        return True
    return tsvc.domain_registered(t, host)


def foreign_url(t: Tpi, url: str | None) -> bool:
    """VF-4: a URL read from the TPI's QR whose host is not a registered verification domain."""
    if not url:
        return False
    host = tsvc.host_of(url)
    portal = tsvc.host_of(t.verification_portal_url) if t.verification_portal_url else None
    return not (host == portal or tsvc.domain_registered(t, host))


def foreign_url_warning(t: Tpi, url: str | None) -> list[Any]:
    if not foreign_url(t, url):
        return []
    return [
        cc.warn(
            "VERIFICATION_URL_FOREIGN_DOMAIN",
            "The verification link is not on the TPI's registered domains — possible fake QR.",
            "رابط التحقق ليس ضمن نطاقات الجهة المسجلة — احتمال رمز QR مزوّر.",
            "tpi_verification_url",
        )
    ]


def history(db: Session, kind: CertKind, cert_id: uuid.UUID) -> list[CertVerification]:
    return list(
        db.scalars(
            select(CertVerification)
            .where(CertVerification.cert_kind == kind, CertVerification.cert_id == cert_id)
            .order_by(CertVerification.performed_at, CertVerification.created_at)
        )
    )


def _sensitive_visible(p: Principal | None, project_id: uuid.UUID) -> bool:
    return p is not None and cc.is_hse(p, project_id)


def read(
    db: Session,
    p: Principal | None,
    v: CertVerification,
    cert_no: str,
    refs: Refs | None = None,
) -> VerificationRead:
    refs = refs or Refs(db)
    hide = v.cert_kind == CertKind.personnel and not _sensitive_visible(p, v.project_id)
    return VerificationRead(
        id=v.id,
        cert_kind=v.cert_kind,
        cert_id=v.cert_id,
        cert_no=cert_no,
        method=v.method,
        channel_used=v.channel_used,
        outcome=None if hide else v.outcome,
        differences=[] if hide else [VerificationDifference(x) for x in v.differences or []],
        differences_text=None if hide else v.differences_text,
        reference=v.reference,
        evidence_attachment_id=v.evidence_attachment_id,
        performed_by=refs.user(v.performed_by_user_id) or cc.UNKNOWN_USER,
        performed_at=v.performed_at,
        counts_as_verification=v.counts_as_verification,
        verification_status_after=v.verification_status_after,
    )


def list_for(db: Session, p: Principal, kind: CertKind, cert: Any) -> VerificationList:
    refs = Refs(db)
    return VerificationList(
        items=[read(db, p, v, cert.cert_no or "", refs) for v in history(db, kind, cert.id)]
    )


def _check_evidence(db: Session, body: VerificationCreate, cert_id: uuid.UUID) -> None:
    if body.method == M.tpi_phone:
        if len(body.reference.strip()) < 20:
            raise ApiError(
                422,
                ErrorCode.EVIDENCE_REQUIRED_FOR_METHOD,
                "For a phone verification give the TPI person's role and "
                "reference (≥ 20 characters).",
                "للتحقق الهاتفي اذكر صفة الشخص لدى الجهة والمرجع (20 حرفاً على الأقل).",
            )
        return
    if body.evidence_attachment_id is None:
        raise ApiError(
            422,
            ErrorCode.EVIDENCE_REQUIRED_FOR_METHOD,
            "Attach the verification evidence (screenshot, e-mail or register extract).",
            "أرفق دليل التحقق (لقطة شاشة أو بريد أو مستخرج السجل).",
        )
    a = db.get(Attachment, body.evidence_attachment_id)
    if a is None or a.owner_type != AttachmentOwner.verification_evidence or a.owner_id != cert_id:
        raise validation_error(
            "evidence_attachment_id", "Upload the evidence to this certificate first."
        )


def record(
    db: Session,
    p: Principal,
    kind: CertKind,
    cert: Any,
    body: VerificationCreate,
    *,
    holder_contractors: Iterable[uuid.UUID | None],
    on_change: Callable[[VerificationStatus, VerificationStatus, CertVerification], None],
    holder_ref: str,
) -> VerificationRead:
    """VF-2…VF-7. `on_change(before, after, record)` applies the certificate effects."""
    cc.require(p, cert.project_id, C.cert_verify)
    if cert.status not in (CS.submitted, CS.accepted, CS.suspended):
        raise ApiError(
            409,
            ErrorCode.VERIFICATION_CLOSED,
            "This certificate can no longer be verified.",
            "لم يعد بالإمكان التحقق من هذه الشهادة.",
        )
    if cert.verification_status in (VS.verified, VS.failed):
        raise ApiError(
            409,
            ErrorCode.VERIFICATION_CLOSED,
            "Verification is already concluded for this certificate.",
            "تم إنهاء التحقق من هذه الشهادة.",
        )
    # VF-2
    if cert.submitted_by_user_id == p.user.id:
        raise cc.sod()
    emp = p.user.employer_contractor_id
    if emp is not None and emp in {c for c in holder_contractors if c is not None}:
        raise cc.sod()
    t = tsvc.get(db, cert.tpi_id)
    if body.method == M.client_register and "client_scheme" not in _standards(db, t):
        raise validation_error(
            "method", "Client register verification is for client-scheme TPIs only."
        )
    if body.method == M.tpi_qr_url and foreign_url(t, body.channel_used):
        raise ApiError(
            422,
            ErrorCode.CHANNEL_NOT_REGISTERED,
            "This link is not on the TPI's registered domains and cannot be used "
            "(possible fake QR).",
            "هذا الرابط ليس ضمن نطاقات الجهة المسجلة ولا يمكن استخدامه (احتمال رمز مزوّر).",
        )
    if not channel_registered(t, body.method, body.channel_used):
        raise ApiError(
            422,
            ErrorCode.CHANNEL_NOT_REGISTERED,
            "Use a verification channel registered on the TPI record.",
            "استخدم قناة تحقق مسجلة في سجل الجهة.",
        )
    if body.outcome == O.details_differ and not body.differences:
        raise validation_error("differences", "List what differs.")
    if body.outcome != O.details_differ and body.differences:
        raise validation_error("differences", "Differences apply to details_differ only.")
    _check_evidence(db, body, cert.id)
    at = body.performed_at or now()
    if at > now() + timedelta(minutes=5):
        raise validation_error("performed_at", "Cannot be in the future.")
    before = cert.verification_status
    counts = body.method in COUNTING and body.outcome != O.no_response
    after = before
    if body.method == M.original_sighted:
        counts = False
    elif body.outcome == O.confirmed:
        after = VS.verified
    elif body.outcome in FAILING:
        after = VS.failed
    elif body.outcome == O.no_response:
        prev = [v.performed_at for v in history(db, kind, cert.id) if v.outcome == O.no_response]
        if any(abs(at - x) >= NO_RESPONSE_GAP for x in prev):
            after = VS.unable_to_verify
    if body.method == M.original_sighted and body.outcome in FAILING:
        # an original sighted that differs is still a red flag (VF-6 applies)
        after = VS.failed
        counts = True
    v = CertVerification(
        id=uuid.uuid4(),
        cert_kind=kind,
        cert_id=cert.id,
        project_id=cert.project_id,
        tpi_id=cert.tpi_id,
        method=body.method,
        channel_used=body.channel_used.strip(),
        outcome=body.outcome,
        differences=[d.value for d in body.differences],
        differences_text=body.differences_text,
        reference=body.reference.strip(),
        evidence_attachment_id=body.evidence_attachment_id,
        performed_by_user_id=p.user.id,
        performed_at=at,
        counts_as_verification=counts,
        verification_status_after=after,
    )
    db.add(v)
    db.flush()
    entity = EntityType.cert_verification
    cc.record(
        db,
        p,
        AuditAction.create,
        entity,
        v,
        cert.project_id,
        details={
            "cert_kind": kind.value,
            "cert_id": str(cert.id),
            "from": before.value,
            "to": after.value,
        },
    )
    if after != before:
        cert.verification_status = after
        if after == VS.verified:
            cert.verified_at = at
        on_change(before, after, v)
        if after == VS.unable_to_verify:
            alerts.send(
                db,
                alerts.managers(db) | alerts.officers(db, cert.project_id),
                NotificationKind.verification_unable,
                f"Unable to verify certificate {cert.cert_no} ({holder_ref})",
                f"تعذر التحقق من الشهادة {cert.cert_no} ({holder_ref})",
                _entity(kind),
                cert.id,
                cert.project_id,
                email=True,
            )
        if after == VS.failed:
            alerts.send(
                db,
                alerts.managers(db) | alerts.officers(db, cert.project_id),
                NotificationKind.verification_failed,
                f"Verification failed: certificate {cert.cert_no} ({holder_ref})",
                f"فشل التحقق: الشهادة {cert.cert_no} ({holder_ref})",
                _entity(kind),
                cert.id,
                cert.project_id,
                email=True,
            )
    return read(db, p, v, cert.cert_no or "")


def _entity(kind: CertKind) -> EntityType:
    return (
        EntityType.equipment_certificate
        if kind == CertKind.equipment
        else EntityType.personnel_certificate
    )


def _standards(db: Session, t: Tpi) -> set[str]:
    return {a.standard.value for a in tsvc.accreditations(db, t.id)}


def fail_effects(cert: Any) -> CertStatusReason:
    """VF-6: Submitted → Rejected, Accepted/Suspended → Revoked (verification_failed)."""
    if cert.status == CS.submitted:
        cert.status = CS.rejected
    elif cert.status in (CS.accepted, CS.suspended):
        cert.status = CS.revoked
    cert.status_reason = CertStatusReason.verification_failed
    cert.ended_on = cert.ended_on or date.today()
    return CertStatusReason.verification_failed


def due_on(submitted_day: date, days: int) -> date:
    return submitted_day + timedelta(days=days)


# ---- verification log (P4-4: HSE Manager / Officer only) -----------------------------------------


def log(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    cert_kind: CertKind | None = None,
    outcomes: list[VerificationOutcome] | None = None,
    tpi_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> VerificationLogPage:
    from app.models import (  # noqa: PLC0415
        EquipmentCertificate,
        EquipmentCertLine,
        PersonnelCertificate,
        Worker,
    )
    from app.services.access import common as acommon  # noqa: PLC0415

    project = projects.get_visible(db, p, project_id)
    if not cc.is_hse(p, project.id):
        raise forbidden_error()
    stmt = select(CertVerification).where(CertVerification.project_id == project.id)
    if cert_kind is not None:
        stmt = stmt.where(CertVerification.cert_kind == cert_kind)
    if outcomes:
        stmt = stmt.where(CertVerification.outcome.in_(outcomes))
    if tpi_id is not None:
        stmt = stmt.where(CertVerification.tpi_id == tpi_id)
    if date_from is not None:
        stmt = stmt.where(CertVerification.performed_at >= acommon.local_midnight_utc(date_from))
    if date_to is not None:
        stmt = stmt.where(
            CertVerification.performed_at < acommon.local_midnight_utc(date_to + timedelta(days=1))
        )
    stmt = stmt.order_by(CertVerification.performed_at.desc())
    rows, total = paginate(db, stmt, page, page_size)
    refs = Refs(db)
    items = []
    for v in rows:
        cert_no, holder = "", ""
        if v.cert_kind == CertKind.equipment:
            c = db.get(EquipmentCertificate, v.cert_id)
            cert_no = c.cert_no if c else ""
            if c is not None:
                line = db.scalar(
                    select(EquipmentCertLine)
                    .where(EquipmentCertLine.certificate_id == c.id)
                    .limit(1)
                )
                dep = cc.latest_deployment_on(db, line.equipment_id, c.project_id) if line else None
                holder = dep.tag if dep else ""
        else:
            pc = db.get(PersonnelCertificate, v.cert_id)
            cert_no = (pc.cert_no or "") if pc else ""
            w = db.get(Worker, pc.worker_id) if pc else None
            holder = w.worker_no if w else ""
        base = read(db, p, v, cert_no, refs)
        items.append(
            VerificationLogItem(
                **base.model_dump(), project_id=v.project_id, holder_or_item_ref=holder
            )
        )
    return VerificationLogPage(items=items, total=total, page=page, page_size=page_size)
