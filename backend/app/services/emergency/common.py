"""Helpers shared by the Phase 6c services (spec 6c-emergency-drills): settings (§3.15 defaults
merged over the stored values), shifts, presence (EO-4), qualification (EO-3), the coverage
calculation (§6.2), minutes (§6.1), visibility, numbering and corrective actions."""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus, GateDirection, GateResult, GateStatus
from app.core.clock import now
from app.core.emergency_enums import (
    CoverageState,
    DrillShift,
    DrillType,
    EmergencyRole,
    ErpStatus,
    RosterShift,
)
from app.core.enums import AuditAction, EntityType, ProjectType, Role
from app.core.hse_enums import Shift, WorkforceStatus
from app.models import (
    AssemblyPoint,
    Deployment,
    EmergencySettings,
    Erp,
    Gate,
    GateCheck,
    Project,
    ProjectEngagement,
    RosterAssignment,
    Site,
    Worker,
    WorkforceReturn,
    Zone,
    ZoneEmergencyProfile,
)
from app.services import audit
from app.services.access import common as acommon
from app.services.emergency import reference as ref
from app.services.heat.common import (
    at_local,
    audit_change,
    contractor_code,
    day_start,
    err,
    local_day,
    managers,
    need,
    next_seq,
    officers,
    pcode,
    project,
    reason,
    record,
    reps,
    send,
    site_engagements,
    site_engineers,
    site_in_scope,
    site_reps,
    tier1_on_site,
    user_ref,
    zone_map,
)
from app.services.heat.common import once as _once
from app.services.permissions import Grant, Principal

__all__ = [  # helpers re-exported from heat.common (the rest are defined here)
    "at_local",
    "audit_change",
    "contractor_code",
    "day_start",
    "err",
    "local_day",
    "managers",
    "need",
    "next_seq",
    "officers",
    "pcode",
    "project",
    "reason",
    "record",
    "reps",
    "send",
    "site_engagements",
    "site_engineers",
    "site_in_scope",
    "site_reps",
    "tier1_on_site",
    "user_ref",
    "zone_map",
]

D = Decimal
LIVE_GATE = (GateResult.GRANTED, GateResult.GRANTED_WITH_WARNING)
HSE_ROLES = frozenset({Role.hse_officer})

DEFAULTS: dict[str, Any] = {
    "erp_review_months": 12,
    "erp_client_acceptance_required": None,  # None → true on airport projects (§3.15)
    "first_aider_ratio": 50,
    "warden_ratio": 50,
    "coordinator_required_per_shift": True,
    "shift_start_times": {"day": "06:00", "night": "18:00"},
    "coverage_check_offset_minutes": 60,
    "drill_minimums": {k.value: v[2] for k, v in ref.DRILL_TYPES.items() if v[2] is not None},
    "first_drill_grace_days": 30,
    "repeat_drill_days": 30,
    "evacuation_target_minutes": 10,
    "headcount_target_minutes": 20,
    "response_target_minutes": 4,
    "rescue_target_minutes": {"confined_space": 15, "height": 10},
    "drill_evaluation_days": 3,
    "event_review_days": 7,
    "muster_roll_window_hours": 16,
    "asset_check_intervals": {k.value: v[2] for k, v in ref.ASSET_TYPES.items()},
    "min_extinguishers_per_zone": 2,
    "min_first_aid_kits_per_zone": 1,
    "min_aed_per_site": 1,
    "rescue_team_min_members": {"confined_space": 3, "height": 2},
    "drill_compliance_warning_pct": "90.0",
    "coverage_warning_pct": "95.0",
    "equipment_readiness_warning_pct": "95.0",
    "muster_detail_retention_months": 12,
    "emergency_record_retention_years": 5,
    "gate_presence_excluded_site_ids": [],
}


@dataclass
class Cfg:
    project_id: uuid.UUID
    airport: bool
    register_from: date | None
    enforcement_from: date | None
    v: dict[str, Any]

    def __getitem__(self, k: str) -> Any:
        return self.v[k]

    def dec(self, k: str) -> Decimal:
        return D(str(self.v[k]))

    def active_on(self, d: date) -> bool:
        """ER-1: 6c runs from emergency_register_from."""
        return self.register_from is not None and d >= self.register_from

    def enforced_on(self, d: date) -> bool:
        """3-ptw v1.4 §11.4 item 6: Phase 3 items from emergency_ptw_enforcement_from."""
        return self.enforcement_from is not None and d >= self.enforcement_from

    @property
    def client_acceptance(self) -> bool:
        v = self.v["erp_client_acceptance_required"]
        return self.airport if v is None else bool(v)

    def minimum(self, t: DrillType) -> int | None:
        m = self.v["drill_minimums"].get(t.value)
        return int(m) if m is not None else None

    def interval(self, asset_type: Any) -> int:
        return int(self.v["asset_check_intervals"][getattr(asset_type, "value", asset_type)])

    def excluded(self, site_id: uuid.UUID) -> bool:
        return str(site_id) in {str(x) for x in self.v["gate_presence_excluded_site_ids"] or []}

    def shift_start(self, s: DrillShift) -> time:
        return time.fromisoformat(self.v["shift_start_times"][s.value])

    def shift_of(self, at: datetime) -> tuple[date, DrillShift]:
        """The (shift date, shift) a moment belongs to; night after midnight → previous day."""
        loc = at.astimezone(acommon.RIYADH)
        t = loc.time()
        day0, night0 = self.shift_start(DrillShift.day), self.shift_start(DrillShift.night)
        if day0 <= t < night0:
            return loc.date(), DrillShift.day
        if t >= night0:
            return loc.date(), DrillShift.night
        return loc.date() - timedelta(days=1), DrillShift.night

    def shift_begin(self, d: date, s: DrillShift) -> datetime:
        return acommon.at_local(d, self.shift_start(s))


def settings_row(db: Session, project_id: uuid.UUID) -> EmergencySettings:
    s = db.get(EmergencySettings, project_id)
    if s is None:
        s = EmergencySettings(project_id=project_id, values={})
        db.add(s)
        db.flush()
    return s


def cfg(db: Session, project_id: uuid.UUID) -> Cfg:
    cache: dict[uuid.UUID, Cfg] = db.info.setdefault("em_cfg", {})
    c = cache.get(project_id)
    if c is not None:
        return c
    s = db.get(EmergencySettings, project_id)
    pr = db.get(Project, project_id)
    stored = dict((s.values if s else None) or {})
    v = {**DEFAULTS, **stored}
    v["drill_minimums"] = {**DEFAULTS["drill_minimums"], **(stored.get("drill_minimums") or {})}
    v["asset_check_intervals"] = {
        **DEFAULTS["asset_check_intervals"],
        **(stored.get("asset_check_intervals") or {}),
    }
    c = Cfg(
        project_id=project_id,
        airport=pr is not None and pr.project_type == ProjectType.airport,
        register_from=s.emergency_register_from if s else None,
        enforcement_from=s.emergency_ptw_enforcement_from if s else None,
        v=v,
    )
    cache[project_id] = c
    return c


def clear_cache(db: Session) -> None:
    for k in ("em_cfg", "em_present", "em_records"):
        db.info.pop(k, None)


def enabled(db: Session, project_id: uuid.UUID, d: date | None = None) -> bool:
    return cfg(db, project_id).active_on(d or local_day())


# ---- minutes, rounding ---------------------------------------------------------------------------


def minutes(a: datetime | None, b: datetime | None) -> Decimal | None:
    """§6.1 (unrounded)."""
    if a is None or b is None:
        return None
    return D(str((b - a).total_seconds())) / D(60)


def q1(v: Decimal) -> Decimal:
    return v.quantize(D("0.1"), rounding=ROUND_HALF_UP)


def mstr(v: Decimal | None) -> str | None:
    return None if v is None else str(q1(v))


def dt(v: Any) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v))


def median(xs: list[Decimal]) -> Decimal | None:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


# ---- recipients, alerts --------------------------------------------------------------------------


def once(db: Session, key: str) -> bool:
    return _once(db, f"em:{key}")


def coordinators(
    db: Session, project_id: uuid.UUID, site_id: uuid.UUID, at: datetime
) -> set[uuid.UUID]:
    """Users rostered as emergency coordinator for the site and the current shift."""
    c = cfg(db, project_id)
    d, s = c.shift_of(at)
    out: set[uuid.UUID] = set()
    for a in roster(db, project_id, site_id, d, EmergencyRole.emergency_coordinator):
        if a.user_id is not None and a.shift in (RosterShift.both, RosterShift(s.value)):
            out.add(a.user_id)
    return out


# ---- access helpers ------------------------------------------------------------------------------


def is_hse(p: Principal, project_id: uuid.UUID) -> bool:
    """HSE Manager or HSE Officer on the project (P6c-4 'HSE roles')."""
    if p.is_manager:
        return True
    sc = p.projects.get(project_id)
    return sc is not None and bool(sc.roles & HSE_ROLES)


def has_role(p: Principal, project_id: uuid.UUID, role: Role) -> bool:
    sc = p.projects.get(project_id)
    return sc is not None and role in sc.roles


def covers_dep(g: Grant, dep: Deployment) -> bool:
    if g.engagement_ids is not None and dep.engagement_id not in g.engagement_ids:
        return False
    return g.site_ids is None or bool(set(dep.site_ids or []) & g.site_ids)


def get(db: Session, model: Any, obj_id: uuid.UUID, label: str) -> Any:
    from app.core.errors import not_found  # noqa: PLC0415

    x = db.get(model, obj_id)
    if x is None:
        raise not_found(label)
    return x


def site_or_422(db: Session, project_id: uuid.UUID, site_id: uuid.UUID) -> Site:
    from app.core.errors import validation_error  # noqa: PLC0415

    s = db.get(Site, site_id)
    if s is None or s.project_id != project_id:
        raise validation_error("site_id", "Choose a site of the project.")
    return s


def zones_of_site(
    db: Session, site_id: uuid.UUID, zone_ids: Iterable[uuid.UUID], fld: str = "zone_ids"
) -> list[Zone]:
    from app.core.errors import validation_error  # noqa: PLC0415

    out = []
    for zid in zone_ids:
        z = db.get(Zone, zid)
        if z is None or z.site_id != site_id:
            raise validation_error(fld, "Choose zones of the site.")
        out.append(z)
    return out


def codes(db: Session, ids: Iterable[uuid.UUID], model: Any = Zone) -> list[str]:
    out = []
    for i in ids:
        x = db.get(model, i)
        if x is not None:
            out.append(x.code)
    return out


def site_code(db: Session, site_id: uuid.UUID | None) -> str | None:
    s = db.get(Site, site_id) if site_id else None
    return s.code if s else None


def worker_of(db: Session, dep_id: uuid.UUID | None) -> Worker | None:
    dep = db.get(Deployment, dep_id) if dep_id else None
    return db.get(Worker, dep.worker_id) if dep else None


def eng_code(db: Session, engagement_id: uuid.UUID | None) -> str | None:
    return contractor_code(db, engagement_id)


# ---- ERP in force --------------------------------------------------------------------------------


def erp_in_force(db: Session, project_id: uuid.UUID) -> Erp | None:
    """ER-7: the Approved (non-superseded) revision; an overdue ERP stays the plan in force."""
    return db.scalar(
        select(Erp)
        .where(Erp.project_id == project_id, Erp.status == ErpStatus.approved)
        .order_by(Erp.revision.desc())
    )


def erp_overdue(e: Erp | None, d: date) -> bool:
    return e is not None and e.review_due_on is not None and d > e.review_due_on


def add_review_trigger(
    db: Session, project_id: uuid.UUID, kind: str, ref_: str | None, alert: bool = True
) -> None:
    """ER-8: sets review_required on the plan in force and alerts the HSE Manager."""
    from app.core.enums import NotificationKind  # noqa: PLC0415

    e = erp_in_force(db, project_id)
    if e is None:
        return
    e.review_required = True
    e.review_triggers = [
        *(e.review_triggers or []),
        {"kind": kind, "ref": ref_, "at": now().isoformat()},
    ]
    db.flush()
    if alert:
        send(
            db,
            managers(db) | officers(db, project_id),
            NotificationKind.emergency_erp_review,
            f"{e.erp_no}: review required ({kind}{' ' + ref_ if ref_ else ''})",
            f"{e.erp_no}: مطلوب مراجعة الخطة",
            project_id,
            EntityType.erp,
            e.id,
            email=True,
        )


# ---- assembly points -----------------------------------------------------------------------------


def active_aps(db: Session, project_id: uuid.UUID, site_id: uuid.UUID | None = None) -> list[Any]:
    from app.core.emergency_enums import ActiveStatus  # noqa: PLC0415

    q = select(AssemblyPoint).where(
        AssemblyPoint.project_id == project_id, AssemblyPoint.status == ActiveStatus.active
    )
    if site_id is not None:
        q = q.where(AssemblyPoint.site_id == site_id)
    return list(db.scalars(q.order_by(AssemblyPoint.ap_code)))


def zone_profiles(db: Session, project_id: uuid.UUID) -> dict[uuid.UUID, ZoneEmergencyProfile]:
    return {
        p.zone_id: p
        for p in db.scalars(
            select(ZoneEmergencyProfile).where(ZoneEmergencyProfile.project_id == project_id)
        )
    }


def warden_required(prof: ZoneEmergencyProfile | None) -> bool:
    return prof is None or prof.warden_required


# ---- roster, presence (EO-4), qualification (EO-3) -----------------------------------------------


def roster(
    db: Session,
    project_id: uuid.UUID,
    site_id: uuid.UUID | None,
    d: date,
    role: EmergencyRole | None = None,
) -> list[RosterAssignment]:
    q = select(RosterAssignment).where(
        RosterAssignment.project_id == project_id,
        RosterAssignment.valid_from <= d,
        (RosterAssignment.valid_to.is_(None)) | (RosterAssignment.valid_to >= d),
    )
    if site_id is not None:
        q = q.where(RosterAssignment.site_id == site_id)
    if role is not None:
        q = q.where(RosterAssignment.role == role)
    return list(db.scalars(q.order_by(RosterAssignment.seq)))


def has_gates(db: Session, project_id: uuid.UUID, site_id: uuid.UUID) -> bool:
    """MU-1 / EO-4: the site has ≥ 1 active gate (and is not excluded by the setting)."""
    if cfg(db, project_id).excluded(site_id):
        return False
    return (
        db.scalar(
            select(Gate.id)
            .where(Gate.site_id == site_id, Gate.status == GateStatus.active)
            .limit(1)
        )
        is not None
    )


def present_map(
    db: Session, project_id: uuid.UUID, site_id: uuid.UUID, d0: date, d1: date
) -> dict[date, set[uuid.UUID]]:
    """EO-4 / 6b AP-4: local date → deployments with an `in` check GRANTED / GRANTED_WITH_WARNING
    or admitted despite denial at a gate of the site."""
    key = (site_id, d0, d1)
    cache: dict[Any, dict[date, set[uuid.UUID]]] = db.info.setdefault("em_present", {})
    if key in cache:
        return cache[key]
    out: dict[date, set[uuid.UUID]] = defaultdict(set)
    rows = db.execute(
        select(
            GateCheck.local_date,
            GateCheck.deployment_id,
            GateCheck.result,
            GateCheck.admitted_despite_denial,
        )
        .join(Gate, Gate.id == GateCheck.gate_id)
        .where(
            Gate.site_id == site_id,
            GateCheck.project_id == project_id,
            GateCheck.direction == GateDirection.in_,
            GateCheck.local_date >= d0,
            GateCheck.local_date <= d1,
            GateCheck.deployment_id.is_not(None),
        )
    )
    for d, dep, res, adm in rows:
        if dep is not None and (res in LIVE_GATE or adm):
            out[d].add(dep)
    cache[key] = out
    return out


@dataclass
class Quals:
    """Batch qualification checks (EO-3) through the Phase 5 training check (HK5-6)."""

    db: Session
    project_id: uuid.UUID
    records: dict[uuid.UUID, list[Any]] = field(default_factory=dict)
    memo: dict[Any, bool] = field(default_factory=dict)

    def load(self, worker_ids: Iterable[uuid.UUID]) -> None:
        from app.models import TrainingRecord  # noqa: PLC0415

        want = [w for w in set(worker_ids) if w not in self.records]
        if not want:
            return
        for w in want:
            self.records[w] = []
        for r in self.db.scalars(select(TrainingRecord).where(TrainingRecord.worker_id.in_(want))):
            self.records[r.worker_id].append(r)

    def ok(self, worker_id: uuid.UUID, code: str, d: date) -> bool:
        key = (worker_id, code, d)
        if key not in self.memo:
            self.memo[key] = self.best(worker_id, code, d).met
        return self.memo[key]

    def best(self, worker_id: uuid.UUID, code: str, d: date) -> Any:
        from app.services.train import common as tcommon  # noqa: PLC0415
        from app.services.train import hook  # noqa: PLC0415
        from app.services.train import validity as v  # noqa: PLC0415

        self.load([worker_id])
        ctx = hook.eval_ctx(self.db, self.project_id)
        return v.best(self.records[worker_id], tcommon.satisfiers(self.db, code), d, ctx)


def dep_worker(db: Session, dep_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
    ids = list(set(dep_ids))
    if not ids:
        return {}
    return dict(
        db.execute(select(Deployment.id, Deployment.worker_id).where(Deployment.id.in_(ids))).all()
    )


# ---- coverage (§6.2) -----------------------------------------------------------------------------


@dataclass
class CovResult:
    state: CoverageState
    rfa: int
    rw: int
    fa: int
    wardens: int
    zones_without: list[uuid.UUID]
    coordinator_ok: bool
    reasons: list[str]


def coverage_calc(
    hc: int,
    zones_work: Iterable[uuid.UUID],
    warden_zones_required: Iterable[uuid.UUID],
    fa_counted: int,
    warden_zone_lists: list[list[uuid.UUID]],
    coordinator_ok: bool,
    fa_ratio: int,
    w_ratio: int,
) -> CovResult:
    """§6.2 for one site-shift-day. `warden_zone_lists` = the zones of each counted warden."""
    if hc <= 0:
        return CovResult(CoverageState.not_required, 0, 0, 0, 0, [], True, [])
    req_z = [z for z in dict.fromkeys(zones_work) if z in set(warden_zones_required)]
    rfa = math.ceil(hc / fa_ratio)
    rw = max(math.ceil(hc / w_ratio), len(req_z))
    covered_z = {z for zs in warden_zone_lists for z in zs}
    without = [z for z in req_z if z not in covered_z]
    reasons = []
    if fa_counted < rfa:
        reasons.append("first_aider")
    if len(warden_zone_lists) < rw:
        reasons.append("fire_warden")
    if without:
        reasons.append("zone")
    if not coordinator_ok:
        reasons.append("coordinator")
    state = CoverageState.short if reasons else CoverageState.covered
    return CovResult(
        state, rfa, rw, fa_counted, len(warden_zone_lists), without, coordinator_ok, reasons
    )


@dataclass
class SiteDay:
    site_id: uuid.UUID
    day: date
    shift: DrillShift
    hc: int
    zones_work: list[uuid.UUID]
    result: CovResult
    not_qualified: list[uuid.UUID]  # deployment ids rostered and present but not qualified


def returns_by_site_day(
    db: Session, project_id: uuid.UUID, d0: date, d1: date, site_id: uuid.UUID | None = None
) -> dict[tuple[uuid.UUID, date, DrillShift], tuple[int, list[uuid.UUID]]]:
    """EO-5: (site, date, shift) → (HC, zones with work); returns Submitted or later; shift `all`
    counts in day."""
    q = select(
        WorkforceReturn.site_id,
        WorkforceReturn.work_date,
        WorkforceReturn.shift,
        WorkforceReturn.zone_id,
        WorkforceReturn.headcount,
    ).where(
        WorkforceReturn.project_id == project_id,
        WorkforceReturn.work_date >= d0,
        WorkforceReturn.work_date <= d1,
        WorkforceReturn.status != WorkforceStatus.draft,
        WorkforceReturn.no_work.is_(False),
    )
    if site_id is not None:
        q = q.where(WorkforceReturn.site_id == site_id)
    acc: dict[tuple[uuid.UUID, date, DrillShift], list[Any]] = {}
    for s, d, sh, z, n in db.execute(q):
        k = (s, d, DrillShift.night if sh == Shift.night else DrillShift.day)
        cur = acc.setdefault(k, [0, []])
        cur[0] += int(n or 0)
        if z is not None and (n or 0) > 0 and z not in cur[1]:
            cur[1].append(z)
    return {k: (v[0], v[1]) for k, v in acc.items()}


def coverage_days(
    db: Session,
    project_id: uuid.UUID,
    d0: date,
    d1: date,
    site_id: uuid.UUID | None = None,
    shift: DrillShift | None = None,
    hc_override: dict[tuple[uuid.UUID, date, DrillShift], tuple[int, list[uuid.UUID]]]
    | None = None,
) -> list[SiteDay]:
    """§6.2 per (site, date, shift) with work (or the override, EO-7 live)."""
    c = cfg(db, project_id)
    data = (
        hc_override
        if hc_override is not None
        else returns_by_site_day(db, project_id, d0, d1, site_id)
    )
    profs = zone_profiles(db, project_id)
    quals = Quals(db, project_id)
    rost = list(
        db.scalars(
            select(RosterAssignment).where(
                RosterAssignment.project_id == project_id,
                RosterAssignment.valid_from <= d1,
                (RosterAssignment.valid_to.is_(None)) | (RosterAssignment.valid_to >= d0),
            )
        )
    )
    wmap = dep_worker(db, [a.deployment_id for a in rost if a.deployment_id])
    quals.load(wmap.values())
    zmap = zone_map(db, project_id)
    out: list[SiteDay] = []
    gated: dict[uuid.UUID, bool] = {}
    for (s, d, sh), (hc, zw) in sorted(data.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        if shift is not None and sh != shift:
            continue
        if not c.active_on(d):
            continue
        if s not in gated:
            gated[s] = has_gates(db, project_id, s)
        present = present_map(db, project_id, s, d0, d1).get(d, set()) if gated[s] else None
        fa = 0
        wardens: list[list[uuid.UUID]] = []
        coord = False
        nq: list[uuid.UUID] = []
        for a in rost:
            if a.site_id != s or a.valid_from > d or (a.valid_to is not None and a.valid_to < d):
                continue
            if a.shift not in (RosterShift.both, RosterShift(sh.value)):
                continue
            if a.role == EmergencyRole.emergency_coordinator:
                coord = True
                continue
            code = ref.ROLES[a.role][2]
            if code is None or a.deployment_id is None:
                continue
            if present is not None and a.deployment_id not in present:
                continue
            w = wmap.get(a.deployment_id)
            if w is None or not quals.ok(w, code, d):
                nq.append(a.deployment_id)
                continue
            if a.role == EmergencyRole.first_aider:
                fa += 1
            elif a.role == EmergencyRole.fire_warden:
                wardens.append(list(a.zone_ids or []))
        req = [z for z in zw if warden_required(profs.get(z)) and z in zmap]
        res = coverage_calc(
            hc,
            zw,
            req,
            fa,
            wardens,
            coord or not c["coordinator_required_per_shift"],
            int(c["first_aider_ratio"]),
            int(c["warden_ratio"]),
        )
        out.append(SiteDay(s, d, sh, hc, zw, res, nq))
    return out


# ---- corrective actions --------------------------------------------------------------------------


def make_ca(
    db: Session,
    project_id: uuid.UUID,
    source_id: uuid.UUID,
    site_id: uuid.UUID,
    zone_id: uuid.UUID | None,
    engagement_id: uuid.UUID | None,
    title: str,
    description: str,
    due: date,
    created_by: uuid.UUID | None,
    priority: str = "high",
) -> Any:
    """A Phase 1 CA with source `emergency` (1-dashboard v1.6 §3.8). Owner: the engagement's
    Contractor HSE Rep (else an HSE Officer); verifier: an HSE Officer."""
    from app.core.hse_enums import CaPriority, CaSourceType, CaStatus, ControlLevel  # noqa: PLC0415
    from app.models import CorrectiveAction  # noqa: PLC0415
    from app.services.hse_common import make_ref  # noqa: PLC0415

    eng = engagement_id or tier1_on_site(db, project_id, site_id)
    offs = sorted(officers(db, project_id))
    owners = sorted(reps(db, project_id, eng)) or offs or sorted(managers(db))
    verifier = (offs or sorted(managers(db)))[0]
    created = local_day()
    seq = next_seq(db, CorrectiveAction, project_id, created.year)
    ca = CorrectiveAction(
        id=uuid.uuid4(),
        project_id=project_id,
        ref=make_ref("CA", pcode(db, project_id), created.year, seq, 5),
        year=created.year,
        seq=seq,
        source_type=CaSourceType.emergency,
        source_id=source_id,
        site_id=site_id,
        zone_id=zone_id,
        responsible_engagement_id=eng,
        title=title[:150],
        description=description,
        control_level=ControlLevel.administrative,
        priority=CaPriority(priority),
        owner_id=owners[0],
        verifier_id=verifier,
        created_date=created,
        due_date=max(due, created),
        original_due_date=max(due, created),
        status=CaStatus.open,
        created_by_user_id=created_by,
        alerts_sent=[],
    )
    db.add(ca)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        audit.SYSTEM,
        entity_type=EntityType.corrective_action,
        entity_id=ca.id,
        project_id=project_id,
        after={"ref": ca.ref, "source_type": "emergency"},
    )
    return ca


def ca_ref(db: Session, ca_id: uuid.UUID | None) -> str | None:
    from app.models import CorrectiveAction  # noqa: PLC0415

    ca = db.get(CorrectiveAction, ca_id) if ca_id else None
    return ca.ref if ca else None


def mobilised(db: Session, dep_id: uuid.UUID, project_id: uuid.UUID, fld: str) -> Deployment:
    from app.core.errors import validation_error  # noqa: PLC0415

    dep = db.get(Deployment, dep_id)
    if dep is None or dep.project_id != project_id or dep.status != DeploymentStatus.mobilised:
        raise validation_error(fld, "Choose a deployment Mobilised on the project.")
    return dep


def engagement_on(db: Session, project_id: uuid.UUID, eid: uuid.UUID, fld: str) -> Any:
    from app.core.errors import validation_error  # noqa: PLC0415

    e = db.get(ProjectEngagement, eid)
    if e is None or e.project_id != project_id:
        raise validation_error(fld, "Choose an engagement of the project.")
    return e
