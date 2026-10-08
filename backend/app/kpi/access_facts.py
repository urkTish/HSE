"""Inputs of the access KPIs K-48…K-60 and K-53b (spec 2-access-permits §6.8).

``load_access`` fills ``AccessFacts`` with aggregated SQL for a set of projects (gate checks are
grouped by day × site × zone × engagement × gate × result × first DENY reason, so a month of
75,000 checks is a few thousand rows). The metric functions are pure over those facts and the
engine's filter / window / as_of, like the Phase 1 metrics. Worker-based metrics (K-48…K-51,
K-54…K-57) have no zone and ignore a zone filter; gate, WAP, NOTAM and obstacle metrics apply it.
"""

import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.access_enums import (
    ClearanceReason,
    CredentialAction,
    CredentialKind,
    CredentialReason,
    CustodyStatus,
    DeploymentStatus,
    GateDirection,
    GateResult,
    GateSubjectKind,
    InductionResult,
    InductionStatus,
    InductionType,
    ObstacleDecision,
    ObstacleStatus,
    OffenceStatus,
    PassApplicationStatus,
    ValidityStatus,
    WorkerPersonType,
)
from app.models import (
    AccessSettings,
    Adp,
    AirportPass,
    Avp,
    CredentialEvent,
    CredentialSuspension,
    Deployment,
    GateCheck,
    InductionRecord,
    NotamRequest,
    ObstacleClearance,
    Offence,
    PassApplication,
    Vehicle,
    Wap,
    Worker,
)

UUID = uuid.UUID
RIYADH_OFFSET = timedelta(hours=3)


def _local(ts: datetime | None) -> date | None:
    return None if ts is None else (ts + RIYADH_OFFSET).date()


# ---- facts ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DepFact:
    project: UUID
    eng: UUID | None
    sites: frozenset[UUID]
    start: date | None  # mobilised (None while pending induction)
    end: date | None  # demobilised_on
    worker: bool  # contractor_worker
    gen: tuple[tuple[date, date], ...]  # valid general_site intervals


@dataclass(frozen=True, slots=True)
class AttemptFact:
    d: date
    eng: UUID | None
    first: bool
    passed: bool
    n: int


@dataclass(frozen=True, slots=True)
class CredFact:
    kind: str
    eff: date
    eng: UUID | None
    sites: frozenset[UUID]


@dataclass(frozen=True, slots=True)
class GateAgg:
    d: date
    site: UUID | None
    zone: UUID | None
    eng: UUID | None
    gate: UUID
    denied: bool
    reason: str | None
    n: int


@dataclass(frozen=True, slots=True)
class AdmitAgg:
    d: date
    site: UUID | None
    zone: UUID | None
    eng: UUID | None
    gate: UUID
    n: int


@dataclass(frozen=True, slots=True)
class CustodyFact:
    kind: str
    due: date
    returned: date | None
    lost: bool
    eng: UUID | None


@dataclass(frozen=True, slots=True)
class AppFact:
    eng: UUID | None
    submitted: date | None
    lodged: date | None
    decided: date | None
    issued: date | None
    stale_days: int


@dataclass(frozen=True, slots=True)
class OffFact:
    d: date
    eng: UUID | None
    zone: UUID | None
    code: str
    counted: bool


@dataclass(frozen=True, slots=True)
class AdpFact:
    eng: UUID | None
    issued: date | None
    until: date | None
    ended: date | None  # revoked / withdrawn / expired
    susp: tuple[tuple[date, date | None], ...]


@dataclass(frozen=True, slots=True)
class WapFact:
    eng: UUID
    site: UUID
    zones: frozenset[UUID]
    approved: date | None
    activated: date | None
    ended: date | None
    valid_from: date
    valid_to: date


@dataclass(frozen=True, slots=True)
class WapSusp:
    d: date
    eng: UUID
    site: UUID
    zones: frozenset[UUID]
    reason: str


@dataclass(frozen=True, slots=True)
class NtmFact:
    d: date
    eng: UUID | None
    zones: frozenset[UUID]
    late: bool


@dataclass(frozen=True, slots=True)
class ObsClrFact:
    eng: UUID | None
    zone: UUID | None
    approved: bool
    valid_from: date | None
    valid_to: date | None
    rejected_on: date | None
    penetration: bool


@dataclass
class AccessFacts:
    deps: list[DepFact] = field(default_factory=list)
    attempts: list[AttemptFact] = field(default_factory=list)
    creds: list[CredFact] = field(default_factory=list)
    gate: list[GateAgg] = field(default_factory=list)
    admitted: list[AdmitAgg] = field(default_factory=list)
    custody: list[CustodyFact] = field(default_factory=list)
    apps: list[AppFact] = field(default_factory=list)
    offences: list[OffFact] = field(default_factory=list)
    adps: list[AdpFact] = field(default_factory=list)
    adp_susp: list[tuple[date, UUID | None]] = field(default_factory=list)
    waps: list[WapFact] = field(default_factory=list)
    wap_susp: list[WapSusp] = field(default_factory=list)
    ntms: list[NtmFact] = field(default_factory=list)
    obstacles: list[ObsClrFact] = field(default_factory=list)
    coverage_pct: dict[UUID, int] = field(default_factory=dict)  # E5 threshold per project


# ---- loader --------------------------------------------------------------------------------------


def load_access(db: Session, pids: list[UUID]) -> AccessFacts:
    af = AccessFacts()
    if not pids:
        return af
    # deployments and general_site validity
    gen: dict[tuple[UUID, UUID], list[tuple[date, date]]] = defaultdict(list)
    for wid, pid, vf, vu in db.execute(
        select(
            InductionRecord.worker_id,
            InductionRecord.project_id,
            InductionRecord.valid_from,
            InductionRecord.valid_until,
        ).where(
            InductionRecord.project_id.in_(pids),
            InductionRecord.induction_type == InductionType.general_site,
            InductionRecord.result == InductionResult.passed,
            InductionRecord.status.in_(
                [InductionStatus.valid, InductionStatus.expired, InductionStatus.superseded]
            ),
            InductionRecord.valid_from.is_not(None),
        )
    ):
        if vf is not None and vu is not None:
            gen[(wid, pid)].append((vf, vu))
    dep_sites: dict[UUID, tuple[frozenset[UUID], UUID | None]] = {}
    for did, wid, pid, eng, site_ids, status, mob, demob, ptype in db.execute(
        select(
            Deployment.id,
            Deployment.worker_id,
            Deployment.project_id,
            Deployment.engagement_id,
            Deployment.site_ids,
            Deployment.status,
            Deployment.mobilised_on,
            Deployment.demobilised_on,
            Worker.person_type,
        )
        .join(Worker, Worker.id == Deployment.worker_id)
        .where(Deployment.project_id.in_(pids))
    ):
        sites = frozenset(site_ids or [])
        dep_sites[did] = (sites, eng)
        af.deps.append(
            DepFact(
                project=pid,
                eng=eng,
                sites=sites,
                start=None if status == DeploymentStatus.pending_induction else mob,
                end=demob,
                worker=ptype == WorkerPersonType.contractor_worker,
                gen=tuple(gen.get((wid, pid), [])),
            )
        )
    # induction attempts (K-50)
    first_c = (InductionRecord.attempt_no == literal_column("1")).label("first")
    passed_c = (InductionRecord.result == literal_column("'passed'")).label("passed")
    for d, eng, first, passed, n in db.execute(
        select(
            InductionRecord.delivered_on,
            InductionRecord.engagement_id,
            first_c,
            passed_c,
            func.count(),
        )
        .where(InductionRecord.project_id.in_(pids))
        .group_by(InductionRecord.delivered_on, InductionRecord.engagement_id, first_c, passed_c)
    ):
        af.attempts.append(AttemptFact(d, eng, bool(first), bool(passed), int(n)))
    af.attempts.sort(key=lambda x: x.d)
    # credentials in a valid state (K-51)
    for dep_id, eng_id, vu in db.execute(
        select(
            InductionRecord.deployment_id,
            InductionRecord.engagement_id,
            InductionRecord.valid_until,
        ).where(
            InductionRecord.project_id.in_(pids),
            InductionRecord.status == InductionStatus.valid,
            InductionRecord.valid_until.is_not(None),
        )
    ):
        sites, _ = dep_sites.get(dep_id, (frozenset(), None))
        if vu is not None:
            af.creds.append(CredFact("induction", vu, eng_id, sites))
    live = [ValidityStatus.active, ValidityStatus.suspended]
    cred_models: tuple[tuple[str, Any], ...] = (("airport_pass", AirportPass), ("adp", Adp))
    bg_blobs = dict(
        db.execute(
            select(PassApplication.id, PassApplication.background_enc)
            .join(AirportPass, AirportPass.application_id == PassApplication.id)
            .where(AirportPass.project_id.in_(pids), AirportPass.validity_status.in_(live))
        ).all()
    )
    for kind, model in cred_models:
        for obj in db.scalars(
            select(model).where(model.project_id.in_(pids), model.validity_status.in_(live))
        ):
            if obj.effective_valid_until is None:
                continue
            sites, eng = dep_sites.get(obj.deployment_id, (frozenset(), obj.engagement_id))
            af.creds.append(CredFact(kind, obj.effective_valid_until, obj.engagement_id, sites))
            if kind == "airport_pass":
                blob = bg_blobs.get(obj.application_id)
                due = json.loads(crypto.decrypt(blob)).get("recheck_due") if blob else None
                if due:
                    rd = date.fromisoformat(str(due))
                    af.creds.append(CredFact("bg_recheck", rd, obj.engagement_id, sites))
    for a in db.scalars(select(Avp).where(Avp.project_id.in_(pids), Avp.validity_status.in_(live))):
        if a.effective_valid_until is not None:
            af.creds.append(CredFact("avp", a.effective_valid_until, a.engagement_id, frozenset()))
    for v in db.scalars(select(Vehicle).where(Vehicle.project_id.in_(pids))):
        for dd in (v.istimara_expiry, v.insurance_expiry, v.mvpi_expiry):
            if dd is not None and v.status.value == "active":
                af.creds.append(CredFact("vehicle_document", dd, v.engagement_id, frozenset()))
    for weng, exp in db.execute(
        select(Deployment.engagement_id, Worker.id_expiry_date)
        .join(Worker, Worker.id == Deployment.worker_id)
        .where(
            Deployment.project_id.in_(pids),
            Deployment.status == DeploymentStatus.mobilised,
            Worker.id_expiry_date.is_not(None),
        )
    ):
        if exp is not None:
            af.creds.append(CredFact("worker_id", exp, weng, frozenset()))
    for o in db.scalars(
        select(ObstacleClearance).where(
            ObstacleClearance.project_id.in_(pids),
            ObstacleClearance.status.in_(
                [ObstacleStatus.approved, ObstacleStatus.approved_with_conditions]
            ),
            ObstacleClearance.valid_to.is_not(None),
        )
    ):
        assert o.valid_to is not None  # noqa: S101
        af.creds.append(CredFact("obstacle_clearance", o.valid_to, o.engagement_id, frozenset()))
    # gate checks (in, final) aggregated; admitted despite denial
    G = GateCheck  # noqa: N806
    for gday, site, zone, eng, gate, res, reason, n in db.execute(
        select(
            G.local_date, G.site_id, G.zone_id, G.engagement_id, G.gate_id, G.result,
            G.first_deny_reason, func.count(),
        )
        .where(
            G.project_id.in_(pids), G.direction == GateDirection.in_, G.final.is_(True),
            G.subject_kind != GateSubjectKind.equipment_deployment,  # GE-6: not in K-52 / K-53
        )
        .group_by(
            G.local_date, G.site_id, G.zone_id, G.engagement_id, G.gate_id, G.result,
            G.first_deny_reason,
        )
    ):  # fmt: skip
        if res in (GateResult.WAP_VIEW, GateResult.EXIT_RECORDED):
            continue
        af.gate.append(
            GateAgg(gday, site, zone, eng, gate, res == GateResult.DENIED, reason, int(n))
        )
    af.gate.sort(key=lambda x: x.d)
    for gd, site, zone, eng, gate, n in db.execute(
        select(G.local_date, G.site_id, G.zone_id, G.engagement_id, G.gate_id, func.count())
        .where(G.project_id.in_(pids), G.admitted_despite_denial.is_(True))
        .group_by(G.local_date, G.site_id, G.zone_id, G.engagement_id, G.gate_id)
    ):
        af.admitted.append(AdmitAgg(gd, site, zone, eng, gate, int(n)))
    # custody (K-54, K-55)
    custody_models: tuple[tuple[str, Any], ...] = (
        ("airport_pass", AirportPass), ("adp", Adp), ("avp", Avp),
    )  # fmt: skip
    for ckind, cmodel in custody_models:
        for cobj in db.scalars(
            select(cmodel).where(cmodel.project_id.in_(pids), cmodel.return_due_on.is_not(None))
        ):
            assert cobj.return_due_on is not None  # noqa: S101
            af.custody.append(
                CustodyFact(
                    ckind,
                    cobj.return_due_on,
                    _local(cobj.returned_at),
                    cobj.custody_status == CustodyStatus.lost,
                    cobj.engagement_id,
                )
            )
    # applications (K-56)
    for st in db.scalars(select(AccessSettings).where(AccessSettings.project_id.in_(pids))):
        af.coverage_pct[st.project_id] = st.induction_coverage_warning_pct
    stale = {
        s.project_id: s.application_stale_days
        for s in db.scalars(select(AccessSettings).where(AccessSettings.project_id.in_(pids)))
    }
    for app, issued_on in db.execute(
        select(PassApplication, AirportPass.issued_on)
        .outerjoin(AirportPass, AirportPass.id == PassApplication.issued_pass_id)
        .where(PassApplication.project_id.in_(pids))
    ):
        issued = issued_on if app.status == PassApplicationStatus.issued else None
        af.apps.append(
            AppFact(
                app.sponsor_engagement_id,
                _local(app.submitted_at),
                _local(app.lodged_at),
                _local(app.decided_at),
                issued,
                stale.get(app.project_id, 30),
            )
        )
    # offences, ADPs, ADP suspensions (K-57)
    for off in db.scalars(select(Offence).where(Offence.project_id.in_(pids))):
        af.offences.append(
            OffFact(
                off.offence_date, off.engagement_id, off.zone_id, off.offence_code,
                off.status in (OffenceStatus.recorded, OffenceStatus.upheld),
            )
        )  # fmt: skip
    susp: dict[UUID, list[tuple[date, date | None]]] = defaultdict(list)
    for s in db.scalars(
        select(CredentialSuspension).where(
            CredentialSuspension.project_id.in_(pids),
            CredentialSuspension.credential_kind == CredentialKind.adp,
        )
    ):
        start = _local(s.raised_at)
        assert start is not None  # noqa: S101
        susp[s.credential_id].append((start, _local(s.lifted_at)))
    adp_eng: dict[UUID, UUID | None] = {}
    for ad in db.scalars(select(Adp).where(Adp.project_id.in_(pids))):
        adp_eng[ad.id] = ad.engagement_id
        ended = None
        if ad.validity_status in (ValidityStatus.revoked, ValidityStatus.withdrawn):
            ended = _local(ad.revoked_at) or ad.expired_on
        elif ad.validity_status == ValidityStatus.expired:
            ended = ad.expired_on
        af.adps.append(
            AdpFact(
                ad.engagement_id, ad.issued_on, ad.effective_valid_until, ended,
                tuple(susp[ad.id]),
            )
        )  # fmt: skip
    for adp_id, spans in susp.items():
        for start, _ in spans:
            af.adp_susp.append((start, adp_eng.get(adp_id)))
    # WAPs (K-58)
    waps = list(
        db.scalars(select(Wap).where(Wap.project_id.in_(pids), Wap.revision_of_id.is_(None)))
    )
    wmap = {w.id: w for w in waps}
    for w in waps:
        af.waps.append(
            WapFact(
                w.engagement_id, w.site_id, frozenset(w.zone_ids or []), _local(w.approved_at),
                _local(w.activated_at), _local(w.closed_at) or (
                    w.valid_to + timedelta(days=1)
                    if w.status.value in ("expired", "closed", "cancelled") else None
                ),
                w.valid_from, w.valid_to,
            )
        )  # fmt: skip
    for ev in db.scalars(
        select(CredentialEvent).where(
            CredentialEvent.project_id.in_(pids),
            CredentialEvent.credential_kind == CredentialKind.wap,
            CredentialEvent.action.in_(
                [CredentialAction.auto_suspended, CredentialAction.suspend_confirmed]
            ),
        )
    ):
        w0 = wmap.get(ev.credential_id)
        d0 = _local(ev.occurred_at)
        if w0 is None or d0 is None:
            continue
        af.wap_susp.append(
            WapSusp(d0, w0.engagement_id, w0.site_id, frozenset(w0.zone_ids or []),
                    _wap_reason(ev.reason_code))
        )  # fmt: skip
    # NOTAM requests (K-59)
    for ntm in db.scalars(
        select(NotamRequest).where(
            NotamRequest.project_id.in_(pids), NotamRequest.submitted_to_ops_at.is_not(None)
        )
    ):
        d1 = _local(ntm.submitted_to_ops_at)
        assert d1 is not None  # noqa: S101
        af.ntms.append(
            NtmFact(d1, ntm.engagement_id, frozenset(ntm.zone_ids or []), ntm.late_request)
        )
    # obstacle clearances (K-60)
    for o in db.scalars(select(ObstacleClearance).where(ObstacleClearance.project_id.in_(pids))):
        af.obstacles.append(
            ObsClrFact(
                o.engagement_id, o.zone_id,
                o.status in (ObstacleStatus.approved, ObstacleStatus.approved_with_conditions),
                o.valid_from, o.valid_to,
                _local(o.decided_at) if o.decision == ObstacleDecision.rejected else None,
                ClearanceReason.ols_penetration.value in (o.clearance_reasons or []),
            )
        )  # fmt: skip
    return af


def _wap_reason(r: CredentialReason) -> str:
    if r == CredentialReason.ops_suspension:
        return "ops"
    if r == CredentialReason.violation:
        return "violation"
    if r in (CredentialReason.dependency_invalid, CredentialReason.contractor_suspended):
        return "dependency"
    return "other"
