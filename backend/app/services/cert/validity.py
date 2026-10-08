"""Validity calculations and in-force predicates (spec 4-third-party-cert §6.1-§6.6, VF-1,
EC-10, PC-9, TP-5, BL-4, BL-7).

`at` is the evaluation instant (UTC); the local date d = local_day(at). For a past `at` (KPI
as-of) acceptance and verification must have happened by `at`; Expired / Superseded statuses
set later than d do not exclude the certificate."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.cert_enums import (
    BanStatus,
    CertificateStatus,
    CertLimitingFactor,
    CertStatusReason,
    DefectCategory,
    EquipmentCertCategory,
    HookReasonCode,
    LineResult,
    TpiBlacklistScope,
    TpiStatus,
    VerificationStatus,
)
from app.kpi.periods import add_months
from app.models import (
    CertificationBan,
    CertSettings,
    EquipmentCertificate,
    EquipmentCertLine,
    EquipmentItem,
    PersonnelCertificate,
    Tpi,
    TpiClientApproval,
)
from app.services.access import common as acommon
from app.services.cert import reference as ref
from app.services.cert import settings as cset

R = HookReasonCode
CS = CertificateStatus
PASSING = (LineResult.pass_, LineResult.pass_with_conditions)
LIVE_STATUSES = (CS.accepted, CS.expired, CS.superseded)


# ---- §6.1-§6.4 -----------------------------------------------------------------------------------


def interval_end(start: date, months: int) -> date:
    return add_months(start, months) - timedelta(days=1)


def line_validity(
    inspected_on: date, printed_next_due: date | None, months: int
) -> tuple[date, CertLimitingFactor, date]:
    """§6.1: valid_until = min(printed_next_due, interval_end); tie → printed_next_due."""
    end = interval_end(inspected_on, months)
    if printed_next_due is not None and printed_next_due <= end:
        return printed_next_due, CertLimitingFactor.printed_next_due, end
    return end, CertLimitingFactor.category_interval, end


def personnel_validity(
    issued_on: date, printed_expiry: date | None, months: int
) -> tuple[date, CertLimitingFactor, date]:
    """§6.2: cap_end = add_months(issued_on, cap) − 1; tie → printed_expiry."""
    end = interval_end(issued_on, months)
    if printed_expiry is not None and printed_expiry <= end:
        return printed_expiry, CertLimitingFactor.printed_expiry, end
    return end, CertLimitingFactor.cap, end


def defect_due(
    category: DefectCategory, raised_day: date, tpi_due: date | None, s: CertSettings
) -> date | None:
    """§6.3."""
    if category != DefectCategory.B:
        return None
    cap = raised_day + timedelta(days=s.defect_b_max_days)
    if tpi_due is not None:
        return min(tpi_due, cap)
    return raised_day + timedelta(days=s.defect_b_default_days)


def scaffold_tag_until(inspection_day: date, s: CertSettings) -> date:
    """§6.4."""
    return inspection_day + timedelta(days=s.scaffold_inspection_interval_days - 1)


# ---- TPI scope (BL-7) and client approval (TP-5) -------------------------------------------------


def tpi_blacklisted_for(t: Tpi | None, cert_day: date) -> bool:
    if t is None or t.status != TpiStatus.blacklisted:
        return False
    if t.blacklist_scope == TpiBlacklistScope.issued_from and t.blacklist_from is not None:
        return cert_day >= t.blacklist_from
    return True


def client_approval_ok(
    db: Session,
    s: CertSettings,
    project_id: uuid.UUID,
    tpi_id: uuid.UUID,
    d: date,
    category: str | None = None,
    cert_type: str | None = None,
) -> bool:
    if not s.require_client_approved_tpi or (
        s.client_approval_required_from is not None and d < s.client_approval_required_from
    ):
        return True
    from app.core.cert_enums import ClientApprovalStatus  # noqa: PLC0415

    a = db.scalar(
        select(TpiClientApproval).where(
            TpiClientApproval.project_id == project_id, TpiClientApproval.tpi_id == tpi_id
        )
    )
    if a is None or a.status != ClientApprovalStatus.active or a.valid_until < d:
        return False
    if category is not None and category not in (a.scope_categories or []):
        return False
    return cert_type is None or cert_type in (a.scope_cert_types or [])


# ---- equipment lines (§6.6) ----------------------------------------------------------------------


@dataclass
class LineEval:
    in_force: bool
    reason: HookReasonCode | None
    valid_until: date | None
    expiring: bool = False
    window_until: datetime | None = None  # VF-1 unverified window
    hard_stop: bool = False


def _window(accepted_at: datetime | None, hours: int) -> datetime | None:
    if accepted_at is None or hours <= 0:
        return None
    return accepted_at + timedelta(hours=hours)


def category_critical(s: CertSettings, category: EquipmentCertCategory) -> bool:
    e = ref.EQC.get(category)
    return bool(e and e.hook_code in cset.critical_codes(s))


def type_critical(s: CertSettings, cert_type: str) -> bool:
    crit = cset.critical_codes(s)
    p = ref.PCT.get(cert_type)
    sat = p.satisfies if p else (cert_type,)
    return any(c in crit for c in sat)


def eval_line(
    db: Session,
    c: EquipmentCertificate,
    line: EquipmentCertLine,
    at: datetime,
    s: CertSettings | None = None,
    project_id: uuid.UUID | None = None,
) -> LineEval:
    s = s or cset.get(db, project_id or c.project_id)
    d = acommon.local_day(at)
    vu = line.valid_until
    tpi = db.get(Tpi, c.tpi_id)
    if c.status == CS.revoked or c.verification_status == VerificationStatus.failed:
        return LineEval(False, R.CERT_REVOKED, vu, hard_stop=True)
    if line.suspended_for_configuration and (line.suspended_at is None or line.suspended_at <= at):
        return LineEval(False, R.CONFIGURATION_CHANGED, vu, hard_stop=True)
    if c.status == CS.suspended:
        return LineEval(False, R.CERT_SUSPENDED, vu, hard_stop=True)
    if tpi_blacklisted_for(tpi, c.inspected_on):
        return LineEval(False, R.TPI_BLACKLISTED, vu, hard_stop=True)
    if line.result not in PASSING:
        return LineEval(False, R.CERT_MISSING, None)
    if c.status not in LIVE_STATUSES or c.accepted_at is None or c.accepted_at > at:
        return LineEval(False, R.CERT_MISSING, vu)
    if c.status == CS.superseded or line.superseded_by_line_id is not None:
        newer = (
            db.get(EquipmentCertLine, line.superseded_by_line_id)
            if line.superseded_by_line_id
            else None
        )
        nc = db.get(EquipmentCertificate, newer.certificate_id) if newer else None
        if nc is None or nc.in_force_from is None or nc.in_force_from <= at:
            return LineEval(False, R.CERT_EXPIRED, vu)
    window = None
    verified = c.verification_status == VerificationStatus.verified and (
        c.verified_at is None or c.verified_at <= at
    )
    if not verified:
        item = db.get(EquipmentItem, line.equipment_id)
        w = _window(c.accepted_at, s.unverified_acceptance_hours)
        crit = item is not None and category_critical(s, item.category)
        if (
            w is None
            or at > w
            or crit
            or c.verification_status
            in (VerificationStatus.failed, VerificationStatus.unable_to_verify)
        ):
            return LineEval(False, R.CERT_UNVERIFIED, vu)
        window = w
    if vu is None or d > vu:
        return LineEval(False, R.CERT_EXPIRED, vu)
    if d < c.inspected_on:
        return LineEval(False, R.CERT_MISSING, vu)
    if project_id is not None:
        item = db.get(EquipmentItem, line.equipment_id)
        if item is not None and not client_approval_ok(
            db, s, project_id, c.tpi_id, d, category=item.category.value
        ):
            return LineEval(False, R.CERT_MISSING, vu)
    return LineEval(True, None, vu, vu <= d + timedelta(days=7), window)


def item_lines(
    db: Session, equipment_id: uuid.UUID
) -> list[tuple[EquipmentCertificate, EquipmentCertLine]]:
    rows = db.execute(
        select(EquipmentCertificate, EquipmentCertLine)
        .join(EquipmentCertLine, EquipmentCertLine.certificate_id == EquipmentCertificate.id)
        .where(
            EquipmentCertLine.equipment_id == equipment_id,
            EquipmentCertificate.status.notin_([CS.draft, CS.historic]),
        )
        .order_by(EquipmentCertificate.inspected_on.desc(), EquipmentCertificate.created_at.desc())
    ).all()
    return [(c, line) for c, line in rows]


@dataclass
class ItemCert:
    cert: EquipmentCertificate | None
    line: EquipmentCertLine | None
    ev: LineEval


def current_line(
    db: Session, equipment_id: uuid.UUID, at: datetime, project_id: uuid.UUID | None = None
) -> ItemCert:
    """The item's in-force line with the latest inspection; else the most relevant failing
    one (latest accepted / suspended / revoked, then latest submitted). EC-10: a newer
    accepted failed line wins over an older valid one (the item is out of service)."""
    rows = item_lines(db, equipment_id)
    if not rows:
        return ItemCert(None, None, LineEval(False, R.CERT_MISSING, None))
    s = None
    best: ItemCert | None = None
    first_fail: ItemCert | None = None
    for c, line in rows:
        if c.accepted_at is not None and c.accepted_at > at:
            continue
        s = s or cset.get(db, project_id or c.project_id)
        ev = eval_line(db, c, line, at, s, project_id)
        if ev.in_force:
            best = best or ItemCert(c, line, ev)
        elif first_fail is None and c.status != CS.submitted:
            first_fail = ItemCert(c, line, ev)
    if best is not None:
        if first_fail and first_fail.cert and best.cert and first_fail.ev.hard_stop:  # noqa: SIM102
            # a hard stop on a line of the same or a later inspection wins (CF-1 / revocation)
            if first_fail.cert.inspected_on >= best.cert.inspected_on and first_fail.ev.reason in (
                R.CONFIGURATION_CHANGED,
            ):
                return first_fail
        return best
    if first_fail is not None:
        return first_fail
    c, line = rows[0]
    return ItemCert(c, line, LineEval(False, R.CERT_MISSING, line.valid_until))


# ---- personnel certificates (§6.6) ---------------------------------------------------------------


def active_ban(
    db: Session, worker_id: uuid.UUID, cert_type: str | None, d: date
) -> CertificationBan | None:
    for b in db.scalars(select(CertificationBan).where(CertificationBan.worker_id == worker_id)):
        if b.from_date > d:
            continue
        if (
            b.status == BanStatus.lifted
            and b.lifted_at is not None
            and acommon.local_day(b.lifted_at) <= d
        ):
            continue
        if b.scope_all or cert_type is None or cert_type in (b.cert_types or []):
            return b
    return None


def eval_personnel(
    db: Session,
    pc: PersonnelCertificate,
    at: datetime,
    s: CertSettings | None = None,
    critical: bool | None = None,
    project_id: uuid.UUID | None = None,
) -> LineEval:
    s = s or cset.get(db, project_id or pc.project_id)
    d = acommon.local_day(at)
    vu = pc.valid_until
    tpi = db.get(Tpi, pc.tpi_id)
    if active_ban(db, pc.worker_id, pc.cert_type, d) is not None:
        return LineEval(False, R.CERT_HOLDER_BANNED, vu, hard_stop=True)
    if (
        pc.status in (CS.revoked, CS.rejected)
        and pc.status_reason
        in (
            CertStatusReason.verification_failed,
            CertStatusReason.tpi_blacklisted,
            CertStatusReason.tpi_revocation_notice,
        )
    ) or pc.verification_status == VerificationStatus.failed:
        return LineEval(False, R.CERT_REVOKED, vu, hard_stop=True)
    if pc.status == CS.revoked:
        return LineEval(False, R.CERT_REVOKED, vu, hard_stop=True)
    if pc.status == CS.suspended:
        return LineEval(False, R.CERT_SUSPENDED, vu, hard_stop=True)
    if tpi_blacklisted_for(tpi, pc.issued_on):
        return LineEval(False, R.TPI_BLACKLISTED, vu, hard_stop=True)
    if pc.status not in LIVE_STATUSES or pc.accepted_at is None or pc.accepted_at > at:
        return LineEval(False, R.CERT_MISSING, vu)
    if pc.status == CS.superseded or pc.superseded_by_id is not None:
        newer = db.get(PersonnelCertificate, pc.superseded_by_id) if pc.superseded_by_id else None
        if newer is None or newer.in_force_from is None or newer.in_force_from <= at:
            return LineEval(False, R.CERT_EXPIRED, vu)
    window = None
    verified = pc.verification_status == VerificationStatus.verified and (
        pc.verified_at is None or pc.verified_at <= at
    )
    if not verified:
        crit = type_critical(s, pc.cert_type) if critical is None else critical
        w = _window(pc.accepted_at, s.unverified_acceptance_hours)
        if (
            w is None
            or at > w
            or crit
            or pc.verification_status
            in (VerificationStatus.failed, VerificationStatus.unable_to_verify)
        ):
            return LineEval(False, R.CERT_UNVERIFIED, vu)
        window = w
    if vu is None or d > vu:
        return LineEval(False, R.CERT_EXPIRED, vu)
    if d < pc.issued_on:
        return LineEval(False, R.CERT_MISSING, vu)
    if project_id is not None and not client_approval_ok(
        db, s, project_id, pc.tpi_id, d, cert_type=pc.cert_type
    ):
        return LineEval(False, R.CERT_MISSING, vu)
    return LineEval(True, None, vu, vu <= d + timedelta(days=7), window)


def worker_certs(
    db: Session, worker_id: uuid.UUID, types: list[str] | None = None
) -> list[PersonnelCertificate]:
    stmt = select(PersonnelCertificate).where(
        PersonnelCertificate.worker_id == worker_id,
        PersonnelCertificate.status.notin_([CS.draft, CS.historic]),
    )
    if types is not None:
        stmt = stmt.where(PersonnelCertificate.cert_type.in_(types))
    return list(
        db.scalars(
            stmt.order_by(
                PersonnelCertificate.issued_on.desc(), PersonnelCertificate.created_at.desc()
            )
        )
    )


@dataclass
class PersonCert:
    cert: PersonnelCertificate | None
    ev: LineEval


def best_personnel(
    db: Session,
    worker_id: uuid.UUID,
    types: list[str],
    at: datetime,
    project_id: uuid.UUID | None = None,
    critical: bool | None = None,
) -> PersonCert:
    """In-force certificate of any of `types` with the latest valid_until; else the most
    relevant failing one (a hard stop first)."""
    s = None
    best: PersonCert | None = None
    hard: PersonCert | None = None
    other: PersonCert | None = None
    for pc in worker_certs(db, worker_id, types):
        s = s or cset.get(db, project_id or pc.project_id)
        ev = eval_personnel(db, pc, at, s, critical, project_id)
        if ev.in_force:
            if best is None or (ev.valid_until or date.min) > (best.ev.valid_until or date.min):
                best = PersonCert(pc, ev)
        elif ev.hard_stop and hard is None:
            hard = PersonCert(pc, ev)
        elif other is None and pc.status != CS.submitted:
            other = PersonCert(pc, ev)
    if hard is not None and hard.ev.reason in (R.CERT_HOLDER_BANNED,):
        return hard
    if best is not None:
        return best
    if hard is not None:
        return hard
    if other is not None:
        return other
    d = acommon.local_day(at)
    if active_ban(db, worker_id, types[0] if len(types) == 1 else None, d) is not None:
        return PersonCert(None, LineEval(False, R.CERT_HOLDER_BANNED, None, hard_stop=True))
    return PersonCert(None, LineEval(False, R.CERT_MISSING, None))
