"""TPI organisations, accreditations and client approvals (spec 4-third-party-cert §3.1-§3.3,
§4.1, TP-1…TP-8, BL-6…BL-8)."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.cert_enums import (
    AccreditationBody,
    AccreditationStandard,
    CertificateStatus,
    CertStatusReason,
    ClientApprovalStatus,
    EquipmentCertCategory,
    TpiBlacklistScope,
    TpiKind,
    TpiStatus,
)
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.ptw_enums import DetectorStatus, QuarantineReason
from app.core.text import like_pattern, normalize
from app.models import (
    Contractor,
    EquipmentCertificate,
    EquipmentCertLine,
    EquipmentDeployment,
    EquipmentItem,
    GasDetector,
    PersonnelCertificate,
    Tpi,
    TpiAccreditation,
    TpiClientApproval,
    Worker,
)
from app.schemas.cert_config import ClientApprovalImpactItem
from app.schemas.tpi import (
    AccreditationCreate,
    AccreditationRead,
    AccreditationUpdate,
    ClientApprovalCreate,
    ClientApprovalList,
    ClientApprovalRead,
    ClientApprovalUpdate,
    RegisterCheckInput,
    TpiCreate,
    TpiImpact,
    TpiImpactHolder,
    TpiImpactItem,
    TpiListItem,
    TpiPage,
    TpiRead,
    TpiTransitionRequest,
    TpiUpdate,
)
from app.services import projects
from app.services.access import common as acommon
from app.services.cert import alerts, events, validity
from app.services.cert import common as cc
from app.services.cert import reference as ref
from app.services.cert import settings as cset
from app.services.common import duplicate, invalid_transition, paginate
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error

C = Capability
S = TpiStatus
EQUIPMENT_STANDARDS = (AccreditationStandard.iso_iec_17020, AccreditationStandard.client_scheme)
PERSONNEL_STANDARDS = (AccreditationStandard.iso_iec_17024, AccreditationStandard.client_scheme)
KIND_STANDARD: dict[AccreditationStandard, set[TpiKind]] = {
    AccreditationStandard.iso_iec_17020: {TpiKind.inspection_body},
    AccreditationStandard.iso_iec_17024: {TpiKind.personnel_certification_body, TpiKind.ndt_body},
    AccreditationStandard.iso_iec_17025: {TpiKind.calibration_lab},
    AccreditationStandard.client_scheme: {TpiKind.client_scheme},
}
REASON_TEXT: dict[str, tuple[str, str]] = {
    "TPI_NOT_APPROVED": ("The TPI is not approved.", "الجهة غير معتمدة."),
    "TPI_SUSPENDED": ("The TPI was suspended on that date.", "الجهة كانت موقوفة في ذلك التاريخ."),
    "TPI_BLACKLISTED": ("The TPI is blacklisted.", "الجهة محظورة."),
    "TPI_ACCREDITATION_INVALID": (
        "No counted accreditation of the TPI was valid on that date.",
        "لا يوجد اعتماد سارٍ ومتحقق منه للجهة في ذلك التاريخ.",
    ),
    "TPI_SCOPE_NOT_COVERED": (
        "The TPI's accreditation scope does not cover it.",
        "نطاق اعتماد الجهة لا يشمله.",
    ),
    "TPI_NOT_CLIENT_APPROVED": (
        "The TPI has no client approval for this project covering it.",
        "لا توجد موافقة العميل على الجهة لهذا المشروع تشمله.",
    ),
}


# ---- access --------------------------------------------------------------------------------------


def _view(p: Principal) -> None:
    if not p.has_any(C.cert_register_view):
        raise forbidden_error()


def _edit(p: Principal) -> None:
    p.require_any(C.tpi_edit)


def _decide(p: Principal) -> None:
    p.require_any(C.cert_blacklist)


def get(db: Session, tpi_id: uuid.UUID) -> Tpi:
    t = db.get(Tpi, tpi_id)
    if t is None:
        raise not_found("TPI")
    return t


def _hse_viewer(p: Principal) -> bool:
    return p.is_manager or p.has_role_anywhere(Role.hse_officer)


# ---- accreditation predicates (TP-3, TP-4) -------------------------------------------------------


def counts(a: TpiAccreditation, d: date | None = None) -> bool:
    """TP-3: register checked and d ≤ valid_until (valid_from ≤ d)."""
    d = d or today()
    return a.register_checked_at is not None and a.valid_from <= d <= a.valid_until


def accreditations(db: Session, tpi_id: uuid.UUID) -> list[TpiAccreditation]:
    return list(
        db.scalars(
            select(TpiAccreditation)
            .where(TpiAccreditation.tpi_id == tpi_id)
            .order_by(TpiAccreditation.valid_until.desc())
        )
    )


def lapsed(db: Session, t: Tpi, d: date | None = None) -> bool:
    """§4.1 derived: no accreditation valid today for any kind."""
    return not any(counts(a, d) for a in accreditations(db, t.id))


def _suspended_on(t: Tpi, d: date) -> bool:
    for per in t.suspension_periods or []:
        f = date.fromisoformat(per["from"])
        to = date.fromisoformat(per["to"]) if per.get("to") else None
        if f <= d and (to is None or d <= to):
            return True
    return False


@dataclass
class Acceptability:
    ok: bool
    reason: str | None = None


def acceptability(
    db: Session,
    t: Tpi,
    d: date,
    *,
    categories: Iterable[str] = (),
    cert_type: str | None = None,
    project_id: uuid.UUID | None = None,
) -> Acceptability:
    """TP-4 / TP-5 / BL-6 at the inspection (equipment) or issue (personnel) date d."""
    cats = sorted(set(categories))
    if t.status in (S.draft, S.pending_approval):
        return Acceptability(False, "TPI_NOT_APPROVED")
    if t.status == S.blacklisted and (
        t.blacklist_scope != TpiBlacklistScope.issued_from
        or t.blacklist_from is None
        or d >= t.blacklist_from
    ):
        return Acceptability(False, "TPI_BLACKLISTED")
    if _suspended_on(t, d) or (t.status == S.suspended and not (t.suspension_periods or [])):
        return Acceptability(False, "TPI_SUSPENDED")
    standards = PERSONNEL_STANDARDS if cert_type is not None else EQUIPMENT_STANDARDS
    accs = [a for a in accreditations(db, t.id) if a.standard in standards]
    valid = [
        a for a in accs if a.register_checked_at is not None and a.valid_from <= d <= a.valid_until
    ]
    covered = False
    if cert_type is not None:
        p = ref.PCT.get(cert_type)
        names = {cert_type, *(p.satisfies if p else ())}
        covered = any(names & set(a.scope_cert_types or []) for a in valid)
    else:
        covered = any(set(cats) <= set(a.scope_categories or []) for a in valid)
    if not covered and TpiKind.client_scheme.value in (t.kinds or []) and project_id is not None:
        ap = _client_approval(db, project_id, t.id)
        if ap is not None and ap.status == ClientApprovalStatus.active and ap.valid_until >= d:
            covered = (
                cert_type in (ap.scope_cert_types or [])
                if cert_type is not None
                else set(cats) <= set(ap.scope_categories or [])
            )
            if covered:
                valid = valid or [ap]  # type: ignore[list-item]
    if not valid:
        return Acceptability(False, "TPI_ACCREDITATION_INVALID")
    if not covered:
        return Acceptability(False, "TPI_SCOPE_NOT_COVERED")
    if project_id is not None:
        s = cset.get(db, project_id)
        if s.require_client_approved_tpi:
            ok = (
                _approval_covers(db, s, project_id, t.id, d, cert_type=cert_type)
                if cert_type is not None
                else all(_approval_covers(db, s, project_id, t.id, d, category=c) for c in cats)
            )
            if not ok:
                return Acceptability(False, "TPI_NOT_CLIENT_APPROVED")
    return Acceptability(True)


def not_acceptable(reason: str, field: str | None = None) -> ApiError:
    en, ar = REASON_TEXT[reason]
    return ApiError(
        422,
        ErrorCode.TPI_NOT_ACCEPTABLE,
        f"TPI not acceptable: {en}",
        f"الجهة غير مقبولة: {ar}",
        meta={"reason": reason, **({"field": field} if field else {})},
    )


def require_acceptable(
    db: Session,
    t: Tpi,
    d: date,
    *,
    categories: Iterable[str] = (),
    cert_type: str | None = None,
    project_id: uuid.UUID | None = None,
) -> None:
    res = acceptability(db, t, d, categories=categories, cert_type=cert_type, project_id=project_id)
    if not res.ok:
        raise not_acceptable(res.reason or "TPI_NOT_APPROVED")


def accreditation_lapsed_note(db: Session, t: Tpi, inspected_on: date) -> bool:
    """TP-7: the certificate was issued under a valid accreditation that has since lapsed."""
    return lapsed(db, t) and not lapsed(db, t, inspected_on)


def independent(db: Session, t: Tpi, contractor_ids: Iterable[uuid.UUID | None]) -> bool:
    """TP-6: not affiliated with, and no shared CR number with, the owner / employer."""
    for cid in {c for c in contractor_ids if c is not None}:
        if cid in (t.affiliated_contractor_ids or []):
            return False
        c = db.get(Contractor, cid)
        if c is not None and t.cr_number and c.cr_number == t.cr_number:
            return False
    return True


def require_independent(db: Session, t: Tpi, contractor_ids: Iterable[uuid.UUID | None]) -> None:
    if not independent(db, t, contractor_ids):
        raise ApiError(
            422,
            ErrorCode.TPI_NOT_INDEPENDENT,
            "The TPI is not independent of the equipment owner or the holder's employer (TP-6).",
            "الجهة غير مستقلة عن مالك المعدة أو صاحب عمل حامل الشهادة.",
        )


# ---- channels (VF-3, VF-4) -----------------------------------------------------------------------


def host_of(value: str) -> str:
    v = value.strip().lower()
    if "@" in v and "://" not in v:
        return v.rsplit("@", 1)[1]
    if "://" in v:
        return (urlparse(v).hostname or "").lower()
    return v.split("/", 1)[0]


def domain_registered(t: Tpi, host: str) -> bool:
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in t.verification_domains or [])


# ---- reads ---------------------------------------------------------------------------------------


def accreditation_read(a: TpiAccreditation, refs: Refs) -> AccreditationRead:
    from app.core.cert_enums import EquipmentCertCategory as Q  # noqa: PLC0415

    return AccreditationRead(
        id=a.id,
        tpi_id=a.tpi_id,
        accreditation_body=a.accreditation_body,
        standard=a.standard,
        accreditation_no=a.accreditation_no,
        scope_categories=[Q(x) for x in a.scope_categories or []],
        scope_cert_types=list(a.scope_cert_types or []),
        valid_from=a.valid_from,
        valid_until=a.valid_until,
        days_left=(a.valid_until - today()).days,
        certificate_attachment_id=a.certificate_attachment_id,
        register_checked_at=a.register_checked_at,
        register_checked_by=refs.user(a.register_checked_by_user_id)
        if a.register_checked_by_user_id
        else None,
        counts=counts(a),
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def tpi_read(db: Session, p: Principal, t: Tpi) -> TpiRead:
    hse = _hse_viewer(p)
    contact = p.has_any(C.tpi_edit)
    refs = Refs(db)
    accs = accreditations(db, t.id)
    return TpiRead(
        id=t.id,
        tpi_code=t.tpi_code,
        legal_name_en=t.legal_name_en,
        legal_name_ar=t.legal_name_ar,
        kinds=[TpiKind(k) for k in t.kinds or []],
        country=t.country,
        cr_number=t.cr_number,
        foreign_reg_no=t.foreign_reg_no,
        verification_portal_url=t.verification_portal_url,
        verification_domains=list(t.verification_domains or []),
        verification_email=t.verification_email,
        verification_phone=t.verification_phone,
        contact_name=t.contact_name if contact else None,
        contact_mobile=t.contact_mobile if contact else None,
        affiliated_contractor_ids=list(t.affiliated_contractor_ids or []) if hse else [],
        status=t.status if hse or not _contractor_only_anywhere(p) else None,
        accepted_for_use=cc.tpi_accepted(t),
        status_reason=t.status_reason if hse else None,
        blacklist_scope=t.blacklist_scope if hse else None,
        blacklist_from=t.blacklist_from if hse else None,
        accreditation_lapsed=lapsed(db, t),
        accreditations=[accreditation_read(a, refs) for a in accs],
        approved_by=refs.user(t.approved_by_user_id) if t.approved_by_user_id else None,
        approved_at=t.approved_at,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def _contractor_only_anywhere(p: Principal) -> bool:
    if p.is_manager:
        return False
    roles = {r for s in p.projects.values() for r in s.roles}
    return bool(roles) and roles <= cc.CONTRACTOR_ROLES


def read(db: Session, p: Principal, tpi_id: uuid.UUID) -> TpiRead:
    _view(p)
    return tpi_read(db, p, get(db, tpi_id))


def list_tpis(
    db: Session,
    p: Principal,
    page: int,
    page_size: int,
    q: str | None = None,
    statuses: list[TpiStatus] | None = None,
    kinds: list[TpiKind] | None = None,
    category: EquipmentCertCategory | None = None,
    cert_type: str | None = None,
    project_id: uuid.UUID | None = None,
    accreditation_expiring_days: int | None = None,
) -> TpiPage:
    _view(p)
    hse = _hse_viewer(p) or not _contractor_only_anywhere(p)
    stmt = select(Tpi)
    if q:
        pat = like_pattern(q)
        stmt = stmt.where(
            or_(
                Tpi.tpi_code.ilike(f"%{q.strip()}%"),
                Tpi.name_norm_en.ilike(pat),
                Tpi.name_norm_ar.ilike(pat),
            )
        )
    if statuses and hse:
        stmt = stmt.where(Tpi.status.in_(statuses))
    if kinds:
        stmt = stmt.where(Tpi.kinds.overlap([k.value for k in kinds]))
    d = today()
    if category is not None or cert_type is not None or accreditation_expiring_days is not None:
        acc = select(TpiAccreditation.tpi_id).where(
            TpiAccreditation.register_checked_at.is_not(None),
            TpiAccreditation.valid_from <= d,
            TpiAccreditation.valid_until >= d,
        )
        if category is not None:
            acc = acc.where(TpiAccreditation.scope_categories.contains([category.value]))
        if cert_type is not None:
            acc = acc.where(TpiAccreditation.scope_cert_types.contains([cert_type]))
        if accreditation_expiring_days is not None:
            acc = acc.where(
                TpiAccreditation.valid_until <= d + timedelta(days=accreditation_expiring_days)
            )
        stmt = stmt.where(Tpi.id.in_(acc))
    stmt = stmt.order_by(Tpi.tpi_code)
    rows, total = paginate(db, stmt, page, page_size)
    items = []
    for t in rows:
        accs = accreditations(db, t.id)
        nxt = min((a.valid_until for a in accs if counts(a)), default=None)
        accepted = cc.tpi_accepted(t)
        if project_id is not None and accepted:
            accepted = acceptability(
                db,
                t,
                d,
                categories=[category.value] if category else (),
                cert_type=cert_type,
                project_id=project_id,
            ).ok or (category is None and cert_type is None)
        items.append(
            TpiListItem(
                id=t.id,
                tpi_code=t.tpi_code,
                legal_name_en=t.legal_name_en,
                legal_name_ar=t.legal_name_ar,
                kinds=[TpiKind(k) for k in t.kinds or []],
                country=t.country,
                status=t.status if hse else None,
                accepted_for_use=accepted,
                accreditation_lapsed=not any(counts(a) for a in accs),
                next_accreditation_expiry=nxt,
            )
        )
    return TpiPage(items=items, total=total, page=page, page_size=page_size)


# ---- create / update -----------------------------------------------------------------------------


def _check_fields(t: Tpi) -> None:
    if t.country == "SA" and not t.cr_number:
        raise validation_error("cr_number", "CR number is required for Saudi TPIs.")
    if t.country != "SA" and not t.foreign_reg_no:
        raise validation_error("foreign_reg_no", "Registration number is required.")
    doms = [d.lower() for d in t.verification_domains or []]
    t.verification_domains = doms
    import re  # noqa: PLC0415

    from app.schemas.tpi import FQDN  # noqa: PLC0415

    for d in doms:
        if not re.match(FQDN, d):
            raise validation_error("verification_domains", f"Not a domain: {d}")
    if t.verification_portal_url:
        u = urlparse(t.verification_portal_url)
        if u.scheme != "https" or not u.hostname or not domain_registered(t, u.hostname):
            raise validation_error(
                "verification_portal_url",
                "The portal must be https on one of the verification domains.",
            )
    if t.verification_email and not domain_registered(t, host_of(t.verification_email)):
        raise validation_error(
            "verification_email", "The email domain must be one of the verification domains."
        )


def _names_unique(db: Session, t: Tpi) -> None:
    t.name_norm_en = normalize(t.legal_name_en)
    t.name_norm_ar = normalize(t.legal_name_ar)
    for fld, val, col in (
        ("legal_name_en", t.name_norm_en, Tpi.name_norm_en),
        ("legal_name_ar", t.name_norm_ar, Tpi.name_norm_ar),
    ):
        other = db.scalar(select(Tpi).where(col == val, Tpi.id != t.id))
        if other is not None:
            raise duplicate(fld, "A TPI with this name already exists.")


def create(db: Session, p: Principal, body: TpiCreate) -> TpiRead:
    _edit(p)
    if db.scalar(select(Tpi).where(Tpi.tpi_code == body.tpi_code)) is not None:
        raise duplicate("tpi_code", "TPI code already exists.")
    data = body.model_dump()
    data["kinds"] = [k.value for k in body.kinds]
    t = Tpi(id=uuid.uuid4(), status=S.draft, suspension_periods=[], **data)
    _check_fields(t)
    _names_unique(db, t)
    cc.stamp(t, p, create=True)
    db.add(t)
    db.flush()
    cc.record(db, p, AuditAction.create, EntityType.tpi, t, None)
    return tpi_read(db, p, t)


def update(db: Session, p: Principal, tpi_id: uuid.UUID, body: TpiUpdate) -> TpiRead:
    _edit(p)
    t = get(db, tpi_id)
    before = cc.snap(t)
    ch = body.changes()
    if "kinds" in ch:
        ch["kinds"] = [getattr(k, "value", k) for k in ch["kinds"]]
    for k, v in ch.items():
        setattr(t, k, v)
    _check_fields(t)
    _names_unique(db, t)
    cc.stamp(t, p)
    db.flush()
    cc.record(db, p, AuditAction.update, EntityType.tpi, t, None, before)
    return tpi_read(db, p, t)


# ---- transitions (§4.1) --------------------------------------------------------------------------


ALLOWED: dict[TpiStatus, set[TpiStatus]] = {
    S.draft: {S.pending_approval},
    S.pending_approval: {S.approved, S.draft},
    S.approved: {S.suspended, S.blacklisted},
    S.suspended: {S.approved, S.blacklisted},
    S.blacklisted: {S.suspended},
}


def _reason(body: TpiTransitionRequest, n: int = 1) -> str:
    r = (body.reason or "").strip()
    if len(r) < n:
        raise validation_error("reason", f"Give a reason (≥ {n} characters).")
    return r


def transition(db: Session, p: Principal, tpi_id: uuid.UUID, body: TpiTransitionRequest) -> TpiRead:
    t = get(db, tpi_id)
    src, dst = t.status, body.to_status
    if dst not in ALLOWED.get(src, set()):
        raise invalid_transition("TPI", src.value, dst.value)
    if src == S.draft:
        _edit(p)
    else:
        _decide(p)
    before = cc.snap(t)
    d = today()
    details: dict[str, Any] = {"from": src.value, "to": dst.value}
    if src == S.draft:
        ok = any(a.register_checked_at is not None for a in accreditations(db, t.id))
        if not ok and TpiKind.client_scheme.value in (t.kinds or []):
            ok = (
                db.scalar(
                    select(func.count())
                    .select_from(TpiClientApproval)
                    .where(TpiClientApproval.tpi_id == t.id)
                )
                or 0
            ) > 0
        if not ok:
            raise ApiError(
                422,
                ErrorCode.TPI_ACCREDITATION_REQUIRED,
                "Record at least one accreditation checked on the register (TP-3).",
                "سجّل اعتماداً واحداً على الأقل متحققاً منه في السجل.",
            )
        t.status_reason = None
    elif src == S.pending_approval and dst == S.approved:
        t.approved_by_user_id = p.user.id
        t.approved_at = now()
        t.status_reason = None
    elif src == S.pending_approval and dst == S.draft:
        t.status_reason = _reason(body, 10)
    elif dst == S.suspended and src == S.approved:
        t.status_reason = _reason(body)
        t.suspension_periods = [*(t.suspension_periods or []), {"from": d.isoformat(), "to": None}]
    elif src == S.suspended and dst == S.approved:
        t.status_reason = _reason(body)
        t.suspension_periods = _close_periods(t.suspension_periods or [], d)
    elif dst == S.blacklisted:
        r = _reason(body, 20)
        if body.blacklist_scope is None:
            raise ApiError(
                422,
                ErrorCode.TPI_BLACKLIST_SCOPE_REQUIRED,
                "Choose the blacklist scope.",
                "اختر نطاق الحظر.",
            )
        if body.blacklist_scope == TpiBlacklistScope.issued_from and body.blacklist_from is None:
            raise validation_error("blacklist_from", "Give the date from which certificates fail.")
        t.status_reason = r
        t.blacklist_scope = body.blacklist_scope
        t.blacklist_from = (
            body.blacklist_from if body.blacklist_scope == TpiBlacklistScope.issued_from else None
        )
        t.blacklisted_on = d
        details["blacklist_scope"] = body.blacklist_scope.value
    elif src == S.blacklisted and dst == S.suspended:
        t.status_reason = _reason(body)
        t.blacklist_scope = None
        t.blacklist_from = None
        t.suspension_periods = [*(t.suspension_periods or []), {"from": d.isoformat(), "to": None}]
        details["lift_blacklist"] = True
    t.status = dst
    cc.stamp(t, p)
    db.flush()
    cc.record(db, p, AuditAction.status_change, EntityType.tpi, t, None, before, details)
    if dst == S.blacklisted:
        blacklist_cascade(db, t, p)
    if dst in (S.suspended, S.blacklisted):
        _alert_status(db, t)
    if src in (S.approved, S.suspended, S.blacklisted) or dst in (S.approved,):
        events.publish(db, "tpi.status_changed")
    return tpi_read(db, p, t)


def _close_periods(periods: list[dict[str, Any]], d: date) -> list[dict[str, Any]]:
    out = []
    for per in periods:
        if per.get("to") is None:
            end = d - timedelta(days=1)
            if end < date.fromisoformat(per["from"]):
                continue
            out.append({**per, "to": end.isoformat()})
            continue
        out.append(per)
    return out


# ---- BL-7 cascade --------------------------------------------------------------------------------


def _in_scope(t: Tpi, d: date) -> bool:
    return validity.tpi_blacklisted_for(t, d)


def blacklist_cascade(db: Session, t: Tpi, p: Principal | None) -> dict[str, int]:
    """BL-7: revoke certificates in scope (Submitted / Draft → Rejected), recompute items,
    quarantine Phase 3 detectors calibrated in scope."""
    from app.services.cert import equipment  # noqa: PLC0415

    d = today()
    at = now()
    items: set[uuid.UUID] = set()
    workers: set[uuid.UUID] = set()
    revoked = 0
    for c in db.scalars(select(EquipmentCertificate).where(EquipmentCertificate.tpi_id == t.id)):
        if not _in_scope(t, c.inspected_on):
            continue
        new = _end_status(c.status)
        if new is None:
            continue
        before = cc.snap(c)
        c.status = new
        c.status_reason = CertStatusReason.tpi_blacklisted
        c.ended_on = d
        revoked += 1
        cc.record(
            db,
            p,
            AuditAction.status_change,
            EntityType.equipment_certificate,
            c,
            c.project_id,
            before,
            {"cascade": "tpi_blacklisted", "tpi": t.tpi_code},
        )
        items |= set(
            db.scalars(
                select(EquipmentCertLine.equipment_id).where(
                    EquipmentCertLine.certificate_id == c.id
                )
            )
        )
    for pc in db.scalars(select(PersonnelCertificate).where(PersonnelCertificate.tpi_id == t.id)):
        if not _in_scope(t, pc.issued_on):
            continue
        new = _end_status(pc.status)
        if new is None:
            continue
        before = cc.snap(pc)
        pc.status = new
        pc.status_reason = CertStatusReason.tpi_blacklisted
        pc.ended_on = d
        revoked += 1
        workers.add(pc.worker_id)
        cc.record(
            db,
            p,
            AuditAction.status_change,
            EntityType.personnel_certificate,
            pc,
            pc.project_id,
            before,
            {"cascade": "tpi_blacklisted", "tpi": t.tpi_code},
        )
    db.flush()
    for iid in items:
        item = db.get(EquipmentItem, iid)
        if item is not None:
            equipment.recompute(db, item, at)
    detectors = 0
    from app.services.ptw import gas  # noqa: PLC0415

    for gd in db.scalars(select(GasDetector).where(GasDetector.calibration_body_id == t.id)):
        if gd.status == DetectorStatus.retired or not _in_scope(t, gd.calibrated_on):
            continue
        if gd.status != DetectorStatus.quarantined:
            gas.quarantine(db, gd, QuarantineReason.calibration_body_blacklisted)
            detectors += 1
    events.publish(db, "cert.status_changed", worker_ids=workers, item_ids=items)
    return {"revoked": revoked, "items": len(items), "detectors": detectors}


def _end_status(s: CertificateStatus) -> CertificateStatus | None:
    if s in (CertificateStatus.accepted, CertificateStatus.suspended):
        return CertificateStatus.revoked
    if s in (CertificateStatus.submitted, CertificateStatus.draft):
        return CertificateStatus.rejected
    return None


def _affected_projects(db: Session, t: Tpi) -> set[uuid.UUID]:
    pids = set(
        db.scalars(
            select(EquipmentCertificate.project_id).where(EquipmentCertificate.tpi_id == t.id)
        )
    )
    pids |= set(
        db.scalars(
            select(PersonnelCertificate.project_id).where(PersonnelCertificate.tpi_id == t.id)
        )
    )
    return pids


def _alert_status(db: Session, t: Tpi) -> None:
    """BL-2: HSE Officers of affected projects; Contractor HSE Reps see 'not accepted' only."""
    word = "blacklisted" if t.status == S.blacklisted else "suspended"
    word_ar = "محظورة" if t.status == S.blacklisted else "موقوفة"
    for pid in _affected_projects(db, t):
        alerts.send(
            db,
            alerts.officers(db, pid),
            NotificationKind.blacklist_changed,
            f"TPI {t.tpi_code} {word}",
            f"الجهة {t.tpi_code} {word_ar}",
            EntityType.tpi,
            t.id,
            pid,
            email=True,
        )
        engs = set(
            db.scalars(
                select(EquipmentDeployment.engagement_id)
                .join(
                    EquipmentCertLine,
                    EquipmentCertLine.equipment_id == EquipmentDeployment.equipment_id,
                )
                .join(
                    EquipmentCertificate,
                    EquipmentCertificate.id == EquipmentCertLine.certificate_id,
                )
                .where(EquipmentCertificate.tpi_id == t.id, EquipmentDeployment.project_id == pid)
            )
        )
        reps: set[uuid.UUID] = set()
        for e in engs:
            reps |= alerts.reps(db, pid, e)
        alerts.send(
            db,
            reps,
            NotificationKind.blacklist_changed,
            f"TPI {t.tpi_code}: not accepted",
            f"الجهة {t.tpi_code}: غير مقبولة",
            EntityType.tpi,
            t.id,
            pid,
            email=True,
        )


# ---- impact (BL-7 list) --------------------------------------------------------------------------


def impact(db: Session, p: Principal, tpi_id: uuid.UUID) -> TpiImpact:
    if not (p.is_manager or p.has_role_anywhere(Role.hse_officer)):
        raise forbidden_error()
    t = get(db, tpi_id)
    revoked = 0
    eq: list[TpiImpactItem] = []
    for c in db.scalars(
        select(EquipmentCertificate).where(
            EquipmentCertificate.tpi_id == t.id,
            EquipmentCertificate.status_reason == CertStatusReason.tpi_blacklisted,
        )
    ):
        revoked += 1
        for line in db.scalars(
            select(EquipmentCertLine).where(EquipmentCertLine.certificate_id == c.id)
        ):
            item = db.get(EquipmentItem, line.equipment_id)
            if item is None:
                continue
            deps = list(
                db.scalars(
                    select(EquipmentDeployment).where(
                        EquipmentDeployment.equipment_id == item.id,
                        EquipmentDeployment.status.in_(cc.LIVE_DEPLOYMENT),
                    )
                )
            )
            eq.append(
                TpiImpactItem(
                    equipment=cc.equipment_ref(db, item),
                    cert_no=c.cert_no,
                    tags=[x.tag for x in deps],
                    project_ids=sorted({x.project_id for x in deps}, key=str),
                )
            )
    holders: list[TpiImpactHolder] = []
    for pc in db.scalars(
        select(PersonnelCertificate).where(
            PersonnelCertificate.tpi_id == t.id,
            PersonnelCertificate.status_reason == CertStatusReason.tpi_blacklisted,
        )
    ):
        revoked += 1
        w = db.get(Worker, pc.worker_id)
        if w is None:
            continue
        names = acommon.can_see_names(p, pc.project_id)
        from app.models import Deployment  # noqa: PLC0415

        pids = sorted(
            set(db.scalars(select(Deployment.project_id).where(Deployment.worker_id == w.id))),
            key=str,
        )
        holders.append(
            TpiImpactHolder(
                worker_id=w.id,
                worker_no=w.worker_no,
                full_name_en=w.full_name_en if names else None,
                full_name_ar=w.full_name_ar if names else None,
                cert_type=pc.cert_type,
                cert_no=pc.cert_no or "—",
                project_ids=pids,
            )
        )
    detectors = list(
        db.scalars(select(GasDetector.id).where(GasDetector.calibration_body_id == t.id))
    )
    return TpiImpact(
        tpi=cc.tpi_ref(t, p),
        revoked_certificates=revoked,
        equipment=eq,
        holders=holders,
        gas_detector_ids=detectors,
    )


# ---- accreditations ------------------------------------------------------------------------------


def _check_accreditation(db: Session, t: Tpi, a: TpiAccreditation) -> None:
    kinds = {TpiKind(k) for k in t.kinds or []}
    if not KIND_STANDARD[a.standard] & kinds:
        raise ApiError(
            422,
            ErrorCode.STANDARD_KIND_MISMATCH,
            "The standard does not correspond to the TPI's kinds.",
            "المعيار لا يتوافق مع أنواع الجهة.",
        )
    if (a.standard == AccreditationStandard.client_scheme) != (
        a.accreditation_body == AccreditationBody.client
    ):
        raise validation_error(
            "accreditation_body",
            "Accreditation body 'client' goes with the client_scheme standard.",
        )
    if a.valid_until < a.valid_from:
        raise validation_error("valid_until", "valid_until must be on or after valid_from.")
    if a.standard in (AccreditationStandard.iso_iec_17020, AccreditationStandard.iso_iec_17025):
        if not a.scope_categories:
            raise validation_error("scope_categories", "Give the accredited categories.")
    elif a.standard == AccreditationStandard.iso_iec_17024 and not a.scope_cert_types:
        raise validation_error("scope_cert_types", "Give the accredited certificate types.")
    elif a.standard == AccreditationStandard.client_scheme and not (
        a.scope_cert_types or a.scope_categories
    ):
        raise validation_error("scope_cert_types", "Give the scope.")
    for code in a.scope_cert_types or []:
        if not cset.is_type(db, code):
            raise validation_error("scope_cert_types", f"Unknown certificate type {code}.")
    other = db.scalar(
        select(TpiAccreditation).where(
            TpiAccreditation.accreditation_body == a.accreditation_body,
            TpiAccreditation.accreditation_no == a.accreditation_no,
            TpiAccreditation.id != a.id,
        )
    )
    if other is not None:
        raise duplicate("accreditation_no", "This accreditation number is already recorded.")


def create_accreditation(
    db: Session, p: Principal, tpi_id: uuid.UUID, body: AccreditationCreate
) -> AccreditationRead:
    _edit(p)
    t = get(db, tpi_id)
    data = body.model_dump()
    data["scope_categories"] = [c.value for c in body.scope_categories]
    a = TpiAccreditation(id=uuid.uuid4(), tpi_id=t.id, **data)
    _check_accreditation(db, t, a)
    cc.stamp(a, p, create=True)
    db.add(a)
    db.flush()
    cc.record(db, p, AuditAction.create, EntityType.tpi_accreditation, a, None)
    return accreditation_read(a, Refs(db))


def _get_acc(db: Session, accreditation_id: uuid.UUID) -> TpiAccreditation:
    a = db.get(TpiAccreditation, accreditation_id)
    if a is None:
        raise not_found("Accreditation")
    return a


def update_accreditation(
    db: Session, p: Principal, accreditation_id: uuid.UUID, body: AccreditationUpdate
) -> AccreditationRead:
    _edit(p)
    a = _get_acc(db, accreditation_id)
    t = get(db, a.tpi_id)
    before = cc.snap(a)
    ch = body.changes()
    if "scope_categories" in ch:
        ch["scope_categories"] = [getattr(c, "value", c) for c in ch["scope_categories"] or []]
    for k, v in ch.items():
        setattr(a, k, v if v is not None or k not in ("scope_cert_types",) else [])
    if ch.keys() & {"accreditation_no", "accreditation_body", "valid_from", "valid_until"}:
        a.register_checked_at = None  # changed facts must be checked on the register again
        a.register_checked_by_user_id = None
    _check_accreditation(db, t, a)
    cc.stamp(a, p)
    db.flush()
    cc.record(db, p, AuditAction.update, EntityType.tpi_accreditation, a, None, before)
    return accreditation_read(a, Refs(db))


def register_check(
    db: Session, p: Principal, accreditation_id: uuid.UUID, body: RegisterCheckInput
) -> AccreditationRead:
    _edit(p)
    a = _get_acc(db, accreditation_id)
    before = cc.snap(a)
    at = body.checked_at or now()
    if at > now() + timedelta(minutes=5):
        raise validation_error("checked_at", "Cannot be in the future.")
    a.register_checked_at = at
    a.register_checked_by_user_id = p.user.id
    a.register_check_note = body.note
    cc.stamp(a, p)
    db.flush()
    cc.record(db, p, AuditAction.update, EntityType.tpi_accreditation, a, None, before)
    events.publish(db, "tpi.status_changed")
    return accreditation_read(a, Refs(db))


# ---- client approvals (§3.3) ---------------------------------------------------------------------


def _client_approval(
    db: Session, project_id: uuid.UUID, tpi_id: uuid.UUID
) -> TpiClientApproval | None:
    return db.scalar(
        select(TpiClientApproval).where(
            TpiClientApproval.project_id == project_id, TpiClientApproval.tpi_id == tpi_id
        )
    )


def approval_read(db: Session, p: Principal, a: TpiClientApproval) -> ClientApprovalRead:
    t = get(db, a.tpi_id)
    return ClientApprovalRead(
        id=a.id,
        project_id=a.project_id,
        tpi=cc.tpi_ref(t, p, a.project_id),
        approval_ref=a.approval_ref,
        scope_categories=[EquipmentCertCategory(x) for x in a.scope_categories or []],
        scope_cert_types=list(a.scope_cert_types or []),
        valid_until=a.valid_until,
        days_left=(a.valid_until - today()).days,
        status=a.status,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def list_approvals(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    statuses: list[ClientApprovalStatus] | None = None,
    tpi_id: uuid.UUID | None = None,
) -> ClientApprovalList:
    project = projects.get_visible(db, p, project_id)
    if p.grant(project.id, C.cert_register_view) is None:
        raise forbidden_error()
    stmt = select(TpiClientApproval).where(TpiClientApproval.project_id == project.id)
    if statuses:
        stmt = stmt.where(TpiClientApproval.status.in_(statuses))
    if tpi_id:
        stmt = stmt.where(TpiClientApproval.tpi_id == tpi_id)
    rows = db.scalars(stmt.order_by(TpiClientApproval.valid_until)).all()
    return ClientApprovalList(items=[approval_read(db, p, a) for a in rows])


def _check_approval_scope(db: Session, t: Tpi, a: TpiClientApproval) -> None:
    if not (a.scope_categories or a.scope_cert_types):
        raise validation_error("scope_categories", "Give at least one category or type.")
    if TpiKind.client_scheme.value in (t.kinds or []):
        return
    accs = [x for x in accreditations(db, t.id) if x.register_checked_at is not None]
    cats = {c for x in accs for c in x.scope_categories or []}
    types = {c for x in accs for c in x.scope_cert_types or []}
    if not set(a.scope_categories or []) <= cats or not set(a.scope_cert_types or []) <= types:
        raise ApiError(
            422,
            ErrorCode.SCOPE_EXCEEDS_ACCREDITATION,
            "The approval scope exceeds the TPI's accredited scope.",
            "نطاق الموافقة يتجاوز نطاق اعتماد الجهة.",
        )


def create_approval(
    db: Session, p: Principal, project_id: uuid.UUID, body: ClientApprovalCreate
) -> ClientApprovalRead:
    project = projects.get_visible(db, p, project_id)
    p.require(project.id, C.tpi_edit)
    t = get(db, body.tpi_id)
    if _client_approval(db, project.id, t.id) is not None:
        raise duplicate("tpi_id", "This TPI already has a client approval on the project.")
    a = TpiClientApproval(
        id=uuid.uuid4(),
        project_id=project.id,
        tpi_id=t.id,
        approval_ref=body.approval_ref,
        scope_categories=[c.value for c in body.scope_categories],
        scope_cert_types=list(body.scope_cert_types),
        valid_until=body.valid_until,
        status=ClientApprovalStatus.active,
    )
    _check_approval_scope(db, t, a)
    cc.stamp(a, p, create=True)
    db.add(a)
    db.flush()
    cc.record(db, p, AuditAction.create, EntityType.tpi_client_approval, a, project.id)
    events.publish(db, "tpi.status_changed", project_id=project.id, project_wide=True)
    return approval_read(db, p, a)


def update_approval(
    db: Session, p: Principal, approval_id: uuid.UUID, body: ClientApprovalUpdate
) -> ClientApprovalRead:
    a = db.get(TpiClientApproval, approval_id)
    if a is None:
        raise not_found("Client approval")
    projects.get_visible(db, p, a.project_id)
    p.require(a.project_id, C.tpi_edit)
    if a.status == ClientApprovalStatus.withdrawn:
        raise invalid_transition("Client approval", "withdrawn", "withdrawn")
    before = cc.snap(a)
    ch = body.changes()
    if "scope_categories" in ch:
        ch["scope_categories"] = [getattr(c, "value", c) for c in ch["scope_categories"] or []]
    for k, v in ch.items():
        setattr(a, k, v if v is not None else [])
    _check_approval_scope(db, get(db, a.tpi_id), a)
    cc.stamp(a, p)
    db.flush()
    cc.record(db, p, AuditAction.update, EntityType.tpi_client_approval, a, a.project_id, before)
    events.publish(db, "tpi.status_changed", project_id=a.project_id, project_wide=True)
    return approval_read(db, p, a)


def client_approval_impact(
    db: Session, project_id: uuid.UUID, from_date: date
) -> list[ClientApprovalImpactItem]:
    """TP-5: in-force certificates of the project whose TPI has no active client approval
    covering them; they stop counting from `from_date` unless covered."""
    from app.services.cert import validity as v  # noqa: PLC0415

    s = cset.get(db, project_id)
    at = now()
    out: list[ClientApprovalImpactItem] = []
    deps = db.scalars(
        select(EquipmentDeployment).where(
            EquipmentDeployment.project_id == project_id,
            EquipmentDeployment.status.in_(cc.LIVE_DEPLOYMENT),
        )
    ).all()
    for dep in deps:
        item = db.get(EquipmentItem, dep.equipment_id)
        if item is None:
            continue
        ic = v.current_line(db, item.id, at)
        if not ic.ev.in_force or ic.cert is None:
            continue
        tpi = get(db, ic.cert.tpi_id)
        if not _approval_covers(db, s, project_id, tpi.id, from_date, category=item.category.value):
            out.append(
                ClientApprovalImpactItem(
                    cert_kind="equipment",
                    certificate_id=ic.cert.id,
                    cert_no=ic.cert.cert_no,
                    tpi_code=tpi.tpi_code,
                    subject_ref=dep.tag,
                    code=item.category.value,
                    not_in_force_from=from_date,
                )
            )
    for pc in db.scalars(
        select(PersonnelCertificate).where(
            PersonnelCertificate.project_id == project_id,
            PersonnelCertificate.status == CertificateStatus.accepted,
        )
    ):
        if not v.eval_personnel(db, pc, at, s).in_force:
            continue
        tpi = get(db, pc.tpi_id)
        if not _approval_covers(db, s, project_id, tpi.id, from_date, cert_type=pc.cert_type):
            w = db.get(Worker, pc.worker_id)
            out.append(
                ClientApprovalImpactItem(
                    cert_kind="personnel",
                    certificate_id=pc.id,
                    cert_no=pc.cert_no or "—",
                    tpi_code=tpi.tpi_code,
                    subject_ref=w.worker_no if w else "—",
                    code=pc.cert_type,
                    not_in_force_from=from_date,
                )
            )
    return out


def _approval_covers(
    db: Session,
    s: Any,
    project_id: uuid.UUID,
    tpi_id: uuid.UUID,
    d: date,
    category: str | None = None,
    cert_type: str | None = None,
) -> bool:
    a = _client_approval(db, project_id, tpi_id)
    if a is None or a.status != ClientApprovalStatus.active or a.valid_until < d:
        return False
    if category is not None:
        return category in (a.scope_categories or [])
    return cert_type in (a.scope_cert_types or [])


def by_code(db: Session, code: str) -> Tpi | None:
    return db.scalar(select(Tpi).where(Tpi.tpi_code == code.strip().upper()))
