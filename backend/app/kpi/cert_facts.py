"""Certification facts for K-72…K-81, E10/E11, the certification band and C16-C18
(4-third-party-cert §6.6, §6.7, §6.9, KC-1…KC-3).

Loaded lazily (``Facts.cert``) so earlier-phase requests never read the Phase 4 registers. Every
fact carries project-local days (Asia/Riyadh) so a KPI can be evaluated at any past as_of:
- an equipment line is in force on day d when its certificate was accepted and verified by d, d
  lies in [inspected_on, valid_until], it was not superseded / configuration-suspended / ended
  (suspended, revoked) by d and its TPI was not blacklisted for it (§6.6; the VF-1 unverified
  window is not counted by the KPIs, KC-2 "in force" = verified);
- an item's service status on day d comes from its status events (the current status when it
  has none);
- a scaffold's tag on day d comes from its inspections (its register status is the current one,
  the register keeps no status history).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus
from app.core.cert_enums import (
    BanStatus,
    CertificateStatus,
    CertKind,
    DefectCategory,
    DefectStatus,
    EquipmentDeploymentStatus,
    LineResult,
    ScaffoldInspectionResult,
    ScaffoldStatus,
    ScaffoldTagStatus,
    ServiceStatus,
    TpiBlacklistScope,
    TpiStatus,
    VerificationOutcome,
)
from app.models import (
    CertificationBan,
    CertSettings,
    CertVerification,
    Deployment,
    EquipmentCertificate,
    EquipmentCertLine,
    EquipmentDefect,
    EquipmentDeployment,
    EquipmentItem,
    EquipmentStatusEvent,
    HookPolicyState,
    PersonnelCertificate,
    Scaffold,
    ScaffoldInspection,
    Site,
    Tpi,
)
from app.services.access.common import local_day

UUID = uuid.UUID
CS = CertificateStatus
PASSING = frozenset({LineResult.pass_, LineResult.pass_with_conditions})
ENDING = frozenset({CS.suspended, CS.revoked})
CONCLUSIVE = frozenset(
    {
        VerificationOutcome.confirmed,
        VerificationOutcome.not_found,
        VerificationOutcome.details_differ,
        VerificationOutcome.revoked_by_tpi,
    }
)
FAILED = frozenset(
    {
        VerificationOutcome.not_found,
        VerificationOutcome.details_differ,
        VerificationOutcome.revoked_by_tpi,
    }
)
E11_FAILED = frozenset({VerificationOutcome.not_found, VerificationOutcome.details_differ})


def _d(at: datetime | None) -> date | None:
    return local_day(at) if at is not None else None


@dataclass(frozen=True)
class LineFact:
    item: UUID
    cert: UUID
    tpi: str
    passing: bool
    inspected_on: date
    valid_until: date | None
    accepted: date | None
    verified: date | None
    ended: date | None  # suspended / revoked / verification failed (not expiry)
    superseded: date | None
    config_suspended: date | None
    tpi_blocked: date | None  # TPI blacklisted in scope from this day

    def in_force(self, d: date) -> bool:
        if not self.passing or self.accepted is None or self.verified is None:
            return False
        if max(self.accepted, self.verified) > d:
            return False
        if self.valid_until is None or not (self.inspected_on <= d <= self.valid_until):
            return False
        return all(x is None or x > d for x in (
            self.ended, self.superseded, self.config_suspended, self.tpi_blocked
        ))  # fmt: skip

    def accepted_by(self, d: date) -> bool:
        return self.accepted is not None and self.accepted <= d


@dataclass(frozen=True)
class ItemFact:
    id: UUID
    tag_ref: str
    category: str
    events: tuple[tuple[date, ServiceStatus], ...]
    current: ServiceStatus
    created: date

    def status_on(self, d: date) -> ServiceStatus:
        st: ServiceStatus | None = None
        for day, s in self.events:
            if day <= d:
                st = s
        if st is not None:
            return st
        if self.events:
            return ServiceStatus.awaiting_certificate
        return self.current


@dataclass(frozen=True)
class EqDepFact:
    project: UUID
    item: UUID
    tag: str
    category: str
    eng: UUID
    sites: frozenset[UUID]
    zone: UUID | None
    start: date | None  # arrived (On Site)
    end: date | None  # demobilised_on

    def on_site(self, d: date) -> bool:
        return self.start is not None and self.start <= d and (self.end is None or self.end > d)


@dataclass(frozen=True)
class ScaffoldFact:
    project: UUID
    eng: UUID
    zone: UUID
    status: ScaffoldStatus
    created: date
    inspections: tuple[tuple[date, ScaffoldInspectionResult, date | None], ...]
    required: date | None  # inspection_required_at (local day)
    current_tag: ScaffoldTagStatus

    def tag_on(self, d: date) -> ScaffoldTagStatus:
        last = None
        for day, res, until in self.inspections:
            if day <= d:
                last = (day, res, until)
        if last is None:
            return ScaffoldTagStatus.none
        day, res, until = last
        if self.required is not None and day <= self.required <= d:
            return ScaffoldTagStatus.inspection_required
        if res == ScaffoldInspectionResult.red:
            return ScaffoldTagStatus.red
        if until is None or until < d:
            return ScaffoldTagStatus.expired
        return ScaffoldTagStatus(res.value)

    def in_use(self, d: date) -> bool:
        return self.status == ScaffoldStatus.in_use and self.created <= d


@dataclass(frozen=True)
class PcFact:
    worker: UUID
    project: UUID
    cert_type: str
    tpi: str
    issued_on: date
    valid_until: date | None
    accepted: date | None
    verified: date | None
    ended: date | None
    superseded: date | None
    tpi_blocked: date | None

    def in_force(self, d: date, banned: bool = False) -> bool:
        if banned or self.accepted is None or self.verified is None:
            return False
        if max(self.accepted, self.verified) > d:
            return False
        if self.valid_until is None or not (self.issued_on <= d <= self.valid_until):
            return False
        return all(x is None or x > d for x in (self.ended, self.superseded, self.tpi_blocked))


@dataclass(frozen=True)
class WorkerDepFact:
    project: UUID
    worker: UUID
    eng: UUID | None
    sites: frozenset[UUID]
    trade: str
    start: date | None
    end: date | None

    def mobilised(self, d: date) -> bool:
        return self.start is not None and self.start <= d and (self.end is None or self.end > d)


@dataclass(frozen=True)
class BanFact:
    worker: UUID
    scope_all: bool
    types: frozenset[str]
    start: date
    lifted: date | None

    def active(self, d: date, cert_type: str | None = None) -> bool:
        if self.start > d or (self.lifted is not None and self.lifted <= d):
            return False
        return cert_type is None or self.scope_all or cert_type in self.types


@dataclass(frozen=True)
class SubFact:
    """A certificate submission (K-79)."""

    kind: CertKind
    project: UUID
    eng: UUID | None
    sites: frozenset[UUID]
    category: str | None
    cert_type: str | None
    tpi: str
    submitted: date
    due: date
    conclusive: date | None


@dataclass(frozen=True)
class VerFact:
    project: UUID
    eng: UUID | None
    sites: frozenset[UUID]
    category: str | None
    cert_type: str | None
    tpi: str
    d: date
    outcome: VerificationOutcome


@dataclass(frozen=True)
class DefectFact:
    project: UUID
    eng: UUID | None
    sites: frozenset[UUID]
    zone: UUID | None
    category: DefectCategory
    equipment_category: str | None
    status: DefectStatus
    raised: date
    due: date | None
    closed: date | None


@dataclass
class CertFacts:
    items: dict[UUID, ItemFact] = field(default_factory=dict)
    lines: dict[UUID, list[LineFact]] = field(default_factory=dict)  # by item
    eq_deps: list[EqDepFact] = field(default_factory=list)
    scaffolds: list[ScaffoldFact] = field(default_factory=list)
    pcs: dict[UUID, list[PcFact]] = field(default_factory=dict)  # by worker
    worker_deps: list[WorkerDepFact] = field(default_factory=list)
    bans: dict[UUID, list[BanFact]] = field(default_factory=dict)
    blacklists: dict[UUID, list[tuple[date, date | None]]] = field(default_factory=dict)
    tpis_blacklisted: list[tuple[str, date]] = field(default_factory=list)
    subs: list[SubFact] = field(default_factory=list)
    vers: list[VerFact] = field(default_factory=list)
    defects: list[DefectFact] = field(default_factory=list)
    settings: dict[UUID, CertSettings] = field(default_factory=dict)
    enabled: set[UUID] = field(default_factory=set)
    hook_states: dict[UUID, list[HookPolicyState]] = field(default_factory=dict)
    site_project: dict[UUID, UUID] = field(default_factory=dict)

    def item_valid(self, item: UUID, d: date) -> bool:
        return any(ln.in_force(d) for ln in self.lines.get(item, []))

    def item_valid_until(self, item: UUID, d: date) -> date | None:
        vals = [ln.valid_until for ln in self.lines.get(item, []) if ln.in_force(d)]
        return max((v for v in vals if v is not None), default=None)

    def latest_line(self, item: UUID, d: date) -> LineFact | None:
        rows = [ln for ln in self.lines.get(item, []) if ln.accepted_by(d) and ln.passing]
        return max(rows, key=lambda ln: ln.inspected_on, default=None)

    def banned(self, worker: UUID, d: date, cert_type: str | None = None) -> bool:
        return any(b.active(d, cert_type) for b in self.bans.get(worker, []))

    def worker_holds(self, worker: UUID, cert_type: str, d: date) -> bool:
        if self.banned(worker, d, cert_type):
            return False
        return any(pc.cert_type == cert_type and pc.in_force(d) for pc in self.pcs.get(worker, []))

    def blacklisted_on(self, item: UUID, d: date) -> bool:
        return any(s <= d and (e is None or e > d) for s, e in self.blacklists.get(item, []))


def _tpi_block(t: Tpi | None, cert_day: date) -> date | None:
    if t is None or t.status != TpiStatus.blacklisted:
        return None
    if (
        t.blacklist_scope == TpiBlacklistScope.issued_from
        and t.blacklist_from is not None
        and cert_day < t.blacklist_from
    ):
        return None
    return t.blacklisted_on or t.blacklist_from or local_day(t.updated_at)


def load_cert(db: Session, pids: list[UUID]) -> CertFacts:
    from app.services.cert import settings as cset  # noqa: PLC0415

    cf = CertFacts()
    if not pids:
        return cf
    for pid in pids:
        cf.settings[pid] = cset.get(db, pid)
    for sid, spid in db.execute(select(Site.id, Site.project_id).where(Site.project_id.in_(pids))):
        cf.site_project[sid] = spid
    for st in db.scalars(select(HookPolicyState).where(HookPolicyState.project_id.in_(pids))):
        cf.enabled.add(st.project_id)
        cf.hook_states.setdefault(st.project_id, []).append(st)
    tpis = {t.id: t for t in db.scalars(select(Tpi))}
    for t in tpis.values():
        if t.status == TpiStatus.blacklisted:
            cf.tpis_blacklisted.append(
                (t.tpi_code, t.blacklisted_on or t.blacklist_from or local_day(t.updated_at))
            )
    # equipment deployments (all statuses that reached On Site)
    deps = list(
        db.scalars(select(EquipmentDeployment).where(EquipmentDeployment.project_id.in_(pids)))
    )
    item_ids = {d.equipment_id for d in deps}
    items = {
        i.id: i for i in db.scalars(select(EquipmentItem).where(EquipmentItem.id.in_(item_ids)))
    }
    events: dict[UUID, list[tuple[date, ServiceStatus]]] = defaultdict(list)
    for ev in db.scalars(
        select(EquipmentStatusEvent)
        .where(EquipmentStatusEvent.equipment_id.in_(item_ids))
        .order_by(EquipmentStatusEvent.occurred_at)
    ):
        events[ev.equipment_id].append((local_day(ev.occurred_at), ev.to_status))
        if ev.to_status == ServiceStatus.blacklisted:
            cf.blacklists.setdefault(ev.equipment_id, []).append((local_day(ev.occurred_at), None))
        elif cf.blacklists.get(ev.equipment_id) and cf.blacklists[ev.equipment_id][-1][1] is None:
            bl_from, _bl_to = cf.blacklists[ev.equipment_id][-1]
            cf.blacklists[ev.equipment_id][-1] = (bl_from, local_day(ev.occurred_at))
    dep_by_item: dict[UUID, list[EquipmentDeployment]] = defaultdict(list)
    for dp in deps:
        dep_by_item[dp.equipment_id].append(dp)
    for i in items.values():
        tag = next((d.tag for d in dep_by_item[i.id]), i.equipment_no)
        cf.items[i.id] = ItemFact(
            id=i.id,
            tag_ref=tag,
            category=i.category.value,
            events=tuple(events.get(i.id, [])),
            current=i.service_status,
            created=local_day(i.created_at),
        )
        if i.service_status == ServiceStatus.blacklisted and i.id not in cf.blacklists:
            since = _d(i.service_status_since) or local_day(i.updated_at)
            cf.blacklists[i.id] = [(since, None)]
    for dp in deps:
        it = items.get(dp.equipment_id)
        if it is None or dp.arrived_at is None:
            continue
        if dp.status not in (
            EquipmentDeploymentStatus.on_site,
            EquipmentDeploymentStatus.demobilised,
        ):
            continue
        cf.eq_deps.append(
            EqDepFact(
                project=dp.project_id,
                item=dp.equipment_id,
                tag=dp.tag,
                category=it.category.value,
                eng=dp.engagement_id,
                sites=frozenset(dp.site_ids or []),
                zone=dp.zone_id,
                start=local_day(dp.arrived_at),
                end=dp.demobilised_on,
            )
        )
    # certificate lines of those items (any project: an item's certificate travels with it)
    line_rows = db.execute(
        select(EquipmentCertLine, EquipmentCertificate)
        .join(EquipmentCertificate, EquipmentCertificate.id == EquipmentCertLine.certificate_id)
        .where(EquipmentCertLine.equipment_id.in_(item_ids))
    ).all()
    in_force_of = {c.id: c.in_force_from for _ln, c in line_rows}
    cert_of_line = {ln.id: c.id for ln, c in line_rows}
    for ln, c in line_rows:
        sup = None
        if ln.superseded_by_line_id is not None:
            nc = cert_of_line.get(ln.superseded_by_line_id)
            nf = in_force_of.get(nc) if nc else None
            sup = _d(nf) if nf else _d(c.updated_at)
        ended = (
            c.ended_on if c.status in ENDING or c.verification_status.value == "failed" else None
        )
        if ended is None and (c.status in ENDING or c.verification_status.value == "failed"):
            ended = local_day(c.updated_at)
        cf.lines.setdefault(ln.equipment_id, []).append(
            LineFact(
                item=ln.equipment_id,
                cert=c.id,
                tpi=tpis[c.tpi_id].tpi_code if c.tpi_id in tpis else "",
                passing=ln.result in PASSING and c.status != CS.rejected,
                inspected_on=c.inspected_on,
                valid_until=ln.valid_until,
                accepted=_d(c.accepted_at),
                verified=_d(c.verified_at) if c.verification_status.value == "verified" else None,
                ended=ended,
                superseded=sup,
                config_suspended=_d(ln.suspended_at) if ln.suspended_for_configuration else None,
                tpi_blocked=_tpi_block(tpis.get(c.tpi_id), c.inspected_on),
            )
        )
    # scaffolds
    sc_rows = list(db.scalars(select(Scaffold).where(Scaffold.project_id.in_(pids))))
    insp: dict[UUID, list[tuple[date, ScaffoldInspectionResult, date | None]]] = defaultdict(list)
    for si in db.scalars(
        select(ScaffoldInspection)
        .where(ScaffoldInspection.scaffold_id.in_([s.id for s in sc_rows]))
        .order_by(ScaffoldInspection.inspected_at)
    ):
        insp[si.scaffold_id].append((local_day(si.inspected_at), si.result, si.tag_valid_until))
    for scf in sc_rows:
        cf.scaffolds.append(
            ScaffoldFact(
                project=scf.project_id,
                eng=scf.engagement_id,
                zone=scf.zone_id,
                status=scf.status,
                created=local_day(scf.created_at),
                inspections=tuple(insp.get(scf.id, [])),
                required=_d(scf.inspection_required_at),
                current_tag=scf.tag_status,
            )
        )
    # workers: Phase 2 deployments, personnel certificates, bans
    for dp2 in db.scalars(select(Deployment).where(Deployment.project_id.in_(pids))):
        cf.worker_deps.append(
            WorkerDepFact(
                project=dp2.project_id,
                worker=dp2.worker_id,
                eng=dp2.engagement_id,
                sites=frozenset(dp2.site_ids or []),
                trade=dp2.trade.value,
                start=None
                if dp2.status == DeploymentStatus.pending_induction
                else dp2.mobilised_on,
                end=dp2.demobilised_on,
            )
        )
    wids = {w.worker for w in cf.worker_deps}
    pc_rows = list(
        db.scalars(select(PersonnelCertificate).where(PersonnelCertificate.worker_id.in_(wids)))
    )
    in_force_pc = {pc.id: pc.in_force_from for pc in pc_rows}
    for pc in pc_rows:
        failed = pc.verification_status.value == "failed"
        ended = pc.ended_on if pc.status in ENDING or failed else None
        if ended is None and (pc.status in ENDING or failed):
            ended = local_day(pc.updated_at)
        sup = None
        if pc.superseded_by_id is not None:
            nf = in_force_pc.get(pc.superseded_by_id)
            sup = _d(nf) if nf else pc.ended_on
        cf.pcs.setdefault(pc.worker_id, []).append(
            PcFact(
                worker=pc.worker_id,
                project=pc.project_id,
                cert_type=pc.cert_type,
                tpi=tpis[pc.tpi_id].tpi_code if pc.tpi_id in tpis else "",
                issued_on=pc.issued_on,
                valid_until=pc.valid_until,
                accepted=_d(pc.accepted_at),
                verified=_d(pc.verified_at) if pc.verification_status.value == "verified" else None,
                ended=ended,
                superseded=sup,
                tpi_blocked=_tpi_block(tpis.get(pc.tpi_id), pc.issued_on),
            )
        )
    for b in db.scalars(select(CertificationBan).where(CertificationBan.worker_id.in_(wids))):
        cf.bans.setdefault(b.worker_id, []).append(
            BanFact(
                worker=b.worker_id,
                scope_all=b.scope_all,
                types=frozenset(b.cert_types or []),
                start=b.from_date,
                lifted=_d(b.lifted_at) if b.status == BanStatus.lifted else None,
            )
        )
    # submissions and verifications (K-79, E11)
    eq_eng: dict[UUID, EqDepFact] = {}
    for f in cf.eq_deps:
        eq_eng.setdefault(f.item, f)
    first_item: dict[UUID, UUID] = {}
    for ln, c in line_rows:
        first_item.setdefault(c.id, ln.equipment_id)
    wdep: dict[tuple[UUID, UUID], WorkerDepFact] = {}
    for w in cf.worker_deps:
        wdep.setdefault((w.project, w.worker), w)
    vers = list(db.scalars(select(CertVerification).where(CertVerification.project_id.in_(pids))))
    first_conclusive: dict[UUID, date] = {}
    for v in sorted(vers, key=lambda x: x.performed_at):
        if v.outcome in CONCLUSIVE:
            first_conclusive.setdefault(v.cert_id, local_day(v.performed_at))
    eq_certs = {
        c.id: c
        for c in db.scalars(
            select(EquipmentCertificate).where(EquipmentCertificate.project_id.in_(pids))
        )
    }
    pcs_proj = {pc.id: pc for pc in pc_rows if pc.project_id in set(pids)}

    def eq_attr(cid: UUID) -> tuple[UUID | None, frozenset[UUID], str | None]:
        it = first_item.get(cid)
        dep = eq_eng.get(it) if it else None
        cat = items[it].category.value if it is not None and it in items else None
        return (dep.eng if dep else None), (dep.sites if dep else frozenset()), cat

    def pc_attr(pc: PersonnelCertificate) -> tuple[UUID | None, frozenset[UUID]]:
        w = wdep.get((pc.project_id, pc.worker_id))
        return (w.eng if w else None), (w.sites if w else frozenset())

    for c in eq_certs.values():
        if c.submitted_at is None:
            continue
        eng, sites, cat = eq_attr(c.id)
        sd = local_day(c.submitted_at)
        cf.subs.append(
            SubFact(
                CertKind.equipment, c.project_id, eng, sites, cat, None,
                tpis[c.tpi_id].tpi_code if c.tpi_id in tpis else "", sd,
                c.verification_due_on or sd, first_conclusive.get(c.id),
            )
        )  # fmt: skip
    for pc in pcs_proj.values():
        if pc.submitted_at is None:
            continue
        eng, sites = pc_attr(pc)
        sd = local_day(pc.submitted_at)
        cf.subs.append(
            SubFact(
                CertKind.personnel, pc.project_id, eng, sites, None, pc.cert_type,
                tpis[pc.tpi_id].tpi_code if pc.tpi_id in tpis else "", sd,
                pc.verification_due_on or sd, first_conclusive.get(pc.id),
            )
        )  # fmt: skip
    for v in vers:
        if v.outcome is None:
            continue
        if v.cert_kind == CertKind.equipment:
            eng, sites, cat = eq_attr(v.cert_id)
            ctype = None
        else:
            pcx = pcs_proj.get(v.cert_id)
            eng, sites = pc_attr(pcx) if pcx else (None, frozenset())
            cat, ctype = None, (pcx.cert_type if pcx else None)
        cf.vers.append(
            VerFact(
                v.project_id, eng, sites, cat, ctype,
                tpis[v.tpi_id].tpi_code if v.tpi_id in tpis else "",
                local_day(v.performed_at), v.outcome,
            )
        )  # fmt: skip
    # defects
    for df in db.scalars(select(EquipmentDefect).where(EquipmentDefect.project_id.in_(pids))):
        dep = next(
            (x for x in cf.eq_deps if x.item == df.equipment_id and x.project == df.project_id),
            None,
        )
        it = items.get(df.equipment_id) if df.equipment_id else None
        closed = _d(df.closed_at)
        if closed is None and df.closure:
            closed = _d(df.updated_at) if df.status == DefectStatus.closed else None
        cf.defects.append(
            DefectFact(
                project=df.project_id,
                eng=df.engagement_id or (dep.eng if dep else None),
                sites=dep.sites if dep else frozenset(),
                zone=dep.zone if dep else None,
                category=df.category,
                equipment_category=it.category.value
                if it
                else ("scaffold" if df.scaffold_id else None),
                status=df.status,
                raised=local_day(df.raised_at),
                due=df.due_date,
                closed=closed,
            )
        )
    return cf
