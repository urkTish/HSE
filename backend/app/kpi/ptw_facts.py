"""PTW facts for K-46, K-46b, K-61…K-71, E8/E9 and the PTW band (3-ptw §6.11, §8.1).

Loaded lazily (``Facts.ptw``) so Phase 1/2 requests never read the permit registers. Dates are
project-local days (Asia/Riyadh); timestamps stay UTC.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ptw_enums import (
    IsolationStatus,
    PermitStatus,
    PermitType,
    PtwAuditStatus,
    PtwAuditType,
    ShiftEndType,
    StatusReason,
)
from app.models import (
    IsolationCertificate,
    Permit,
    PermitShift,
    PermitSuspension,
    PtwAudit,
    PtwSettings,
    SimopsConflict,
)
from app.services.access.common import local_day

UUID = uuid.UUID


@dataclass(frozen=True)
class PermitFact:
    id: UUID
    project: UUID
    eng: UUID
    site: UUID
    zones: frozenset[UUID]
    primary: str
    types: frozenset[str]
    high_risk: bool
    critical_lift: bool
    status: PermitStatus
    status_reason: StatusReason | None
    first_requested_at: datetime | None
    first_issued_at: datetime | None
    issued_d: date | None
    closed_d: date | None
    expired_d: date | None
    end_d: date | None  # closed / expired / cancelled after issue


@dataclass(frozen=True)
class ShiftFact:
    permit: UUID
    started: date
    ended: date | None
    end_type: ShiftEndType | None
    gas_required: bool
    gas_compliant: bool | None


@dataclass(frozen=True)
class SuspFact:
    permit: UUID
    d: date
    reason: StatusReason
    routine: bool
    resumed: date | None


@dataclass(frozen=True)
class AuditFact:
    id: UUID
    project: UUID
    audit_type: PtwAuditType
    counted: bool  # Completed or Locked
    d: date
    permit: UUID | None
    eng: UUID
    site: UUID
    zone: UUID | None
    applicable: int
    compliant: int
    critical: int
    items: tuple[tuple[str, str, str | None], ...]  # (code, answer, severity)


@dataclass(frozen=True)
class IsoFact:
    project: UUID
    eng: UUID | None
    isolated: date | None
    verified_at: datetime | None
    ended: date | None
    permits: frozenset[UUID]
    long_term_days: int


@dataclass(frozen=True)
class ConflictFact:
    project: UUID
    d: date
    result: str
    rule: str
    open_until: date | None  # None = still open
    permits: tuple[UUID, UUID]


@dataclass
class PtwFacts:
    permits: dict[UUID, PermitFact] = field(default_factory=dict)
    shifts: list[ShiftFact] = field(default_factory=list)
    susps: list[SuspFact] = field(default_factory=list)
    audits: list[AuditFact] = field(default_factory=list)
    isos: list[IsoFact] = field(default_factory=list)
    conflicts: list[ConflictFact] = field(default_factory=list)
    settings: dict[UUID, PtwSettings] = field(default_factory=dict)


def _d(at: datetime | None) -> date | None:
    return local_day(at) if at is not None else None


def load_ptw(db: Session, pids: list[UUID]) -> PtwFacts:
    from app.services.ptw import common as ptw_common  # noqa: PLC0415
    from app.services.ptw import facts as ptw_facts  # noqa: PLC0415

    pf = PtwFacts()
    if not pids:
        return pf
    for pid in pids:
        pf.settings[pid] = ptw_common.settings(db, pid)
    iso_permits: dict[UUID, set[UUID]] = defaultdict(set)
    for p in db.scalars(select(Permit).where(Permit.project_id.in_(pids))):
        if p.status == PermitStatus.draft and p.first_requested_at is None:
            continue
        crit = bool(p.critical_lift)
        if PermitType.lifting.value in (p.work_types or []) and not p.seed_fake:
            try:
                crit = ptw_facts.compute(db, p).critical
            except Exception:
                crit = bool(p.critical_lift)
        end = p.closed_at or p.ended_at
        if end is None and p.status == PermitStatus.cancelled and p.first_issued_at is not None:
            end = p.updated_at
        pf.permits[p.id] = PermitFact(
            id=p.id,
            project=p.project_id,
            eng=p.engagement_id,
            site=p.site_id,
            zones=frozenset(p.zone_ids or []),
            primary=p.primary_type.value,
            types=frozenset(p.work_types or []),
            high_risk=bool(p.high_risk),
            critical_lift=crit,
            status=p.status,
            status_reason=p.status_reason,
            first_requested_at=p.first_requested_at,
            first_issued_at=p.first_issued_at,
            issued_d=_d(p.first_issued_at),
            closed_d=_d(p.closed_at) if p.status == PermitStatus.closed else None,
            expired_d=_d(p.ended_at) if p.status == PermitStatus.expired else None,
            end_d=_d(end),
        )
        for cid in p.isolation_cert_ids or []:
            iso_permits[cid].add(p.id)
    for s in db.scalars(select(PermitShift).where(PermitShift.project_id.in_(pids))):
        pf.shifts.append(
            ShiftFact(
                permit=s.permit_id,
                started=local_day(s.started_at),
                ended=_d(s.ended_at),
                end_type=s.end_type,
                gas_required=bool(s.gas_required),
                gas_compliant=s.gas_compliant,
            )
        )
    for sp in db.scalars(select(PermitSuspension).where(PermitSuspension.project_id.in_(pids))):
        pf.susps.append(
            SuspFact(
                permit=sp.permit_id,
                d=local_day(sp.suspended_at),
                reason=sp.reason,
                routine=bool(sp.routine),
                resumed=_d(sp.resumed_at),
            )
        )
    for a in db.scalars(select(PtwAudit).where(PtwAudit.project_id.in_(pids))):
        pf.audits.append(
            AuditFact(
                id=a.id,
                project=a.project_id,
                audit_type=a.audit_type,
                counted=a.status in (PtwAuditStatus.completed, PtwAuditStatus.locked),
                d=local_day(a.audited_at),
                permit=a.permit_id,
                eng=a.engagement_id,
                site=a.site_id,
                zone=a.zone_id,
                applicable=a.applicable_count,
                compliant=a.compliant_count,
                critical=a.critical_count,
                items=tuple(
                    (str(x.get("code")), str(x.get("answer")), x.get("severity"))
                    for x in a.items or []
                ),
            )
        )
    for c in db.scalars(
        select(IsolationCertificate).where(IsolationCertificate.project_id.in_(pids))
    ):
        if c.isolated_at is None:
            continue
        st = pf.settings.get(c.project_id)
        ended = c.deisolated_at or c.cancelled_at
        if ended is None and c.status in (IsolationStatus.deisolated, IsolationStatus.cancelled):
            ended = c.updated_at
        pf.isos.append(
            IsoFact(
                project=c.project_id,
                eng=c.engagement_id,
                isolated=_d(c.isolated_at),
                verified_at=c.verified_at,
                ended=_d(ended),
                permits=frozenset(iso_permits.get(c.id, set())),
                long_term_days=int(st.long_term_isolation_days) if st else 7,
            )
        )
    for k in db.scalars(select(SimopsConflict).where(SimopsConflict.project_id.in_(pids))):
        is_open = k.status.value == "open"
        left = None if is_open else (k.coordinated_at or k.resolved_at or k.detected_at)
        pf.conflicts.append(
            ConflictFact(
                project=k.project_id,
                d=local_day(k.detected_at),
                result=k.result.value,
                rule=k.rule_code,
                open_until=_d(left),
                permits=(k.permit_a_id, k.permit_b_id),
            )
        )
    return pf
