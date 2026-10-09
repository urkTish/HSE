"""Helpers shared by the Phase 6b services (spec 6b-heat-stress): settings (§3.14 defaults merged
over the stored values), the regime table (§3.4, seeded on first use), the WBGT and regime
calculations (§6.1, §6.2), calendar windows (controls period, monitoring hours, the Phase 3 midday
ban), required zones (HS-3), days with work (§6.5), recipients and numbering."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus
from app.core.clock import now
from app.core.enums import AuditAction, EntityType, Role
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.heat_enums import AcclimatisationBasis, Clothing, PointSourceKind, Regime, Workload
from app.core.hse_enums import WorkforceStatus
from app.core.ptw_enums import Exposure
from app.models import (
    HeatRegimeLimit,
    HeatSettings,
    MonitoringPoint,
    Project,
    RoleAssignment,
    Site,
    WorkforceReturn,
    Zone,
    ZonePtwProfile,
)
from app.services import audit
from app.services.access import common as acommon
from app.services.permissions import Grant, Principal, forbidden_error

D = Decimal
AB = AcclimatisationBasis
R = Regime
REGIMES = [R.R0, R.R1, R.R2, R.R3]
ORDER = {R.unknown: -1, R.R0: 0, R.R1: 1, R.R2: 2, R.R3: 3, R.R4: 4}
REST_MIN = {R.R0: 0, R.R1: 15, R.R2: 30, R.R3: 45, R.R4: 60}
WORKLOADS = list(Workload)
CAF = {
    Clothing.work_clothes: D("0.0"),
    Clothing.cloth_coveralls: D("0.0"),
    Clothing.double_layer_woven: D("3.0"),
    Clothing.sms_coveralls: D("0.5"),
    Clothing.polyolefin_coveralls: D("1.0"),
    Clothing.vapour_barrier_coveralls: D("11.0"),
}
HOOD = D("1.0")
WL_RANK = {Workload.light: 0, Workload.moderate: 1, Workload.heavy: 2, Workload.very_heavy: 3}

# §3.4 seed (ACGIH TLV / Action Limit, VERIFY R3): basis → regime → workload limits
SEED_TABLE: dict[AB, dict[Regime, tuple[str, str, str, str]]] = {
    AB.acclimatised: {
        R.R0: ("31.0", "28.0", "25.0", "23.0"),
        R.R1: ("31.0", "29.0", "27.5", "25.5"),
        R.R2: ("32.0", "30.0", "29.0", "28.0"),
        R.R3: ("32.5", "31.5", "30.5", "30.0"),
    },
    AB.unacclimatised: {
        R.R0: ("28.0", "25.0", "22.5", "21.0"),
        R.R1: ("28.5", "26.0", "24.0", "23.0"),
        R.R2: ("29.5", "27.0", "25.5", "24.5"),
        R.R3: ("30.0", "29.0", "28.0", "27.0"),
    },
}

HEAVY_TRADES = ("labourer", "steel_fixer", "steel_erector", "scaffolder", "mason")
LIGHT_TRADES = (
    "plant_operator", "crane_operator", "driver", "flagman", "supervisor", "engineer", "hse_staff",
)  # fmt: skip
TRADE_DEFAULTS: dict[str, str] = {
    **dict.fromkeys(HEAVY_TRADES, "heavy"),
    **dict.fromkeys(LIGHT_TRADES, "light"),
}
DEFAULTS: dict[str, Any] = {
    "heat_controls_period": {"start_mmdd": "05-01", "end_mmdd": "09-30"},
    "heat_monitoring_hours": {"start_local": "07:00", "end_local": "18:00"},
    "reading_valid_minutes": {"manual": 60, "station": 20},
    "regime_relax_minutes": 30,
    "wbgt_limit_offset_c": "0.0",
    "headline_workload": "heavy",
    "trade_workload_defaults": {},
    "reading_backdate_max_hours": 24,
    "wbgt_component_tolerance_c": "0.5",
    "acclimatisation_schedules": {
        "new_worker": [20, 40, 60, 80, 100],
        "returner": [50, 60, 80, 100],
    },
    "standard_shift_hours": "10.0",
    "deacclimatisation_days": 7,
    "acclimatisation_restart_gap_days": 4,
    "plan_confirmation_hours": 24,
    "cool_water_max_c": "15.0",
    "welfare_checks_per_station_day": 1,
    "ban_patrols_per_zone_day": 1,
    "heat_illness_review_days": 3,
    "heat_case_merge_hours": 48,
    "wbgt_coverage_warning_pct": "95.0",
    "welfare_compliance_warning_pct": "95.0",
    "ban_patrol_coverage_warning_pct": "95.0",
    "heat_fitness_required": False,
    "heat_photo_retention_months": 24,
    "heat_record_retention_years": 5,
}
WATER = (
    "Drink 1 cup (250 mL) of cool water every 15–20 minutes",
    "اشرب كوباً من الماء البارد كل 15–20 دقيقة",
)

# ---- settings -----------------------------------------------------------------------------------


@dataclass
class Cfg:
    project_id: uuid.UUID
    register_from: date | None
    enforcement_from: date | None
    v: dict[str, Any]
    ban_period: dict[str, str]
    ban_hours: dict[str, str]
    ban_prewarn: int

    def __getitem__(self, k: str) -> Any:
        return self.v[k]

    def dec(self, k: str) -> Decimal:
        return D(str(self.v[k]))

    @property
    def relax(self) -> timedelta:
        return timedelta(minutes=int(self.v["regime_relax_minutes"]))

    def valid_for(self, kind: str) -> timedelta:
        return timedelta(minutes=int(self.v["reading_valid_minutes"][kind]))

    @property
    def offset(self) -> Decimal:
        return self.dec("wbgt_limit_offset_c")

    @property
    def headline(self) -> Workload:
        return Workload(self.v["headline_workload"])

    def trade_workload(self, trade: str | None) -> Workload:
        m = {**TRADE_DEFAULTS, **(self.v.get("trade_workload_defaults") or {})}
        return Workload(m.get(trade or "other", "moderate"))

    def active_on(self, d: date) -> bool:
        """HS-1: 6b runs from heat_register_from."""
        return self.register_from is not None and d >= self.register_from

    def enforced_on(self, d: date) -> bool:
        """§11.4 item 9: the Phase 3 items apply from heat_ptw_enforcement_from."""
        return self.enforcement_from is not None and d >= self.enforcement_from

    def in_controls(self, d: date) -> bool:
        p = self.v["heat_controls_period"]
        return in_mmdd(d, p["start_mmdd"], p["end_mmdd"])

    def controls_window(self, year: int) -> tuple[date, date]:
        p = self.v["heat_controls_period"]
        return mmdd_date(year, p["start_mmdd"]), mmdd_date(year, p["end_mmdd"])

    def monitoring(self, d: date) -> tuple[datetime, datetime]:
        h = self.v["heat_monitoring_hours"]
        return at_local(d, h["start_local"]), at_local(d, h["end_local"])

    def in_monitoring(self, at: datetime) -> bool:
        s, e = self.monitoring(local_day(at))
        return s <= at < e

    def monitoring_hours(self) -> int:
        h = self.v["heat_monitoring_hours"]
        return int(h["end_local"][:2]) - int(h["start_local"][:2])

    def ban_date(self, d: date) -> bool:
        return in_mmdd(d, self.ban_period["start_mmdd"], self.ban_period["end_mmdd"])

    def ban_window(self, d: date) -> tuple[datetime, datetime] | None:
        if not self.ban_date(d):
            return None
        return at_local(d, self.ban_hours["start_local"]), at_local(d, self.ban_hours["end_local"])

    def in_ban(self, at: datetime) -> bool:
        """Ban hours inclusive at both ends (HS9b, as HT-1)."""
        w = self.ban_window(local_day(at))
        return w is not None and w[0] <= at <= w[1]


def in_mmdd(d: date, start: str, end: str) -> bool:
    md = d.strftime("%m-%d")
    return start <= md <= end if start <= end else (md >= start or md <= end)


def mmdd_date(year: int, mmdd: str) -> date:
    return date(year, int(mmdd[:2]), int(mmdd[3:]))


def settings_row(db: Session, project_id: uuid.UUID) -> HeatSettings:
    s = db.get(HeatSettings, project_id)
    if s is None:
        s = HeatSettings(project_id=project_id, values={})
        db.add(s)
        db.flush()
    return s


def cfg(db: Session, project_id: uuid.UUID) -> Cfg:
    cache: dict[uuid.UUID, Cfg] = db.info.setdefault("heat_cfg", {})
    c = cache.get(project_id)
    if c is not None:
        return c
    from app.services.ptw import common as pcommon  # noqa: PLC0415

    s = db.get(HeatSettings, project_id)
    v = {**DEFAULTS, **((s.values if s else None) or {})}
    ps = pcommon.settings(db, project_id)
    c = Cfg(
        project_id=project_id,
        register_from=s.heat_register_from if s else None,
        enforcement_from=s.heat_ptw_enforcement_from if s else None,
        v=v,
        ban_period=dict(ps.midday_ban_period),
        ban_hours=dict(ps.midday_ban_hours),
        ban_prewarn=int(ps.midday_ban_prewarn_minutes),
    )
    cache[project_id] = c
    return c


def clear_cache(db: Session) -> None:
    for k in ("heat_cfg", "heat_table", "heat_points", "heat_required", "heat_enabled"):
        db.info.pop(k, None)


# ---- regime table and calculations (§6.1, §6.2) --------------------------------------------------

Table = dict[tuple[AB, Regime, Workload], Decimal]


def ensure_table(db: Session) -> None:
    if db.scalar(select(func.count(HeatRegimeLimit.id))):
        return
    for basis, rows in SEED_TABLE.items():
        for rg, vals in rows.items():
            for wl, v in zip(WORKLOADS, vals, strict=True):
                db.add(
                    HeatRegimeLimit(
                        id=uuid.uuid4(), basis=basis, regime=rg, workload=wl, limit_c=D(v)
                    )
                )
    db.flush()


def table(db: Session) -> Table:
    t: Table | None = db.info.get("heat_table")
    if t is None:
        ensure_table(db)
        t = {
            (r.basis, r.regime, r.workload): r.limit_c for r in db.scalars(select(HeatRegimeLimit))
        }
        db.info["heat_table"] = t
    return t


def q1(v: Decimal) -> Decimal:
    return v.quantize(D("0.1"), rounding=ROUND_HALF_UP)


def wbgt(
    tnwb: Decimal | None, tg: Decimal | None, ta: Decimal | None, solar: bool
) -> Decimal | None:
    """§6.1 ISO 7243 (unrounded); None when the components are incomplete."""
    if tnwb is None or tg is None or (solar and ta is None):
        return None
    if solar:
        assert ta is not None  # noqa: S101
        return D("0.7") * tnwb + D("0.2") * tg + D("0.1") * ta
    return D("0.7") * tnwb + D("0.3") * tg


def effective(
    w: Decimal, clothing: Clothing = Clothing.work_clothes, hood: bool = False
) -> Decimal:
    return w + CAF[clothing] + (HOOD if hood else D(0))


def regime_for(t: Table, offset: Decimal, basis: AB, workload: Workload, eff: Decimal) -> Regime:
    """WR-2: the first of R0…R3 whose limit (+ the project offset, ≤ 0) ≥ eff; else R4."""
    e = q1(eff)
    for rg in REGIMES:
        if e <= t[(basis, rg, workload)] + offset:
            return rg
    return R.R4


def cell_key(basis: AB, workload: Workload) -> str:
    return f"{basis.value}.{workload.value}"


def cells(t: Table, offset: Decimal, w: Decimal) -> dict[str, str]:
    """WR-5: the regime per (basis × workload) for work clothes."""
    return {cell_key(b, wl): regime_for(t, offset, b, wl, w).value for b in AB for wl in WORKLOADS}


def worst(xs: Iterable[Regime]) -> Regime:
    out = R.unknown
    for x in xs:
        if ORDER[x] > ORDER[out]:
            out = x
    return out


# ---- time ---------------------------------------------------------------------------------------


def local_day(at: datetime | None = None) -> date:
    return acommon.local_day(at or now())


def at_local(d: date, hhmm: str) -> datetime:
    return acommon.at_local(d, time.fromisoformat(hhmm))


def day_start(d: date) -> datetime:
    return acommon.local_midnight_utc(d)


def days(d0: date, d1: date) -> list[date]:
    return [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]


# ---- zones, points and days with work (HS-3, §6.5) -----------------------------------------------


def required_zone_ids(db: Session, project_id: uuid.UUID) -> list[uuid.UUID]:
    """HS-3: zones whose Phase 3 default_exposure is outdoor_direct_sun."""
    cache: dict[uuid.UUID, list[uuid.UUID]] = db.info.setdefault("heat_required", {})
    if project_id not in cache:
        cache[project_id] = list(
            db.scalars(
                select(ZonePtwProfile.zone_id)
                .join(Zone, Zone.id == ZonePtwProfile.zone_id)
                .where(
                    ZonePtwProfile.project_id == project_id,
                    ZonePtwProfile.default_exposure == Exposure.outdoor_direct_sun,
                )
                .order_by(Zone.code)
            )
        )
    return cache[project_id]


def points(db: Session, project_id: uuid.UUID) -> list[MonitoringPoint]:
    return list(
        db.scalars(
            select(MonitoringPoint)
            .where(MonitoringPoint.project_id == project_id)
            .order_by(MonitoringPoint.point_code)
        )
    )


def covering(db: Session, project_id: uuid.UUID) -> dict[uuid.UUID, MonitoringPoint]:
    """zone_id → its active covering point (HS-3: at most one)."""
    out: dict[uuid.UUID, MonitoringPoint] = {}
    for pt in points(db, project_id):
        if pt.active:
            for z in pt.zone_ids or []:
                out[z] = pt
    return out


def point_kind(pt: MonitoringPoint) -> str:
    return "station" if pt.source_kind == PointSourceKind.station else "manual"


def days_with_work(
    db: Session, project_id: uuid.UUID, d0: date, d1: date
) -> dict[uuid.UUID, set[date]]:
    """§6.5: site → local dates with a daily return (Submitted or later) with headcount > 0."""
    out: dict[uuid.UUID, set[date]] = {}
    rows = db.execute(
        select(WorkforceReturn.site_id, WorkforceReturn.work_date)
        .where(
            WorkforceReturn.project_id == project_id,
            WorkforceReturn.work_date >= d0,
            WorkforceReturn.work_date <= d1,
            WorkforceReturn.headcount > 0,
            WorkforceReturn.status != WorkforceStatus.draft,
        )
        .distinct()
    )
    for site, d in rows:
        out.setdefault(site, set()).add(d)
    return out


def zone_map(db: Session, project_id: uuid.UUID) -> dict[uuid.UUID, Zone]:
    return {
        z.id: z
        for z in db.scalars(
            select(Zone).join(Site, Site.id == Zone.site_id).where(Site.project_id == project_id)
        )
    }


# ---- recipients ---------------------------------------------------------------------------------


def site_engineers(db: Session, project_id: uuid.UUID, site_id: uuid.UUID | None) -> set[uuid.UUID]:
    day = local_day()
    out: set[uuid.UUID] = set()
    for a in db.scalars(
        select(RoleAssignment).where(
            RoleAssignment.project_id == project_id,
            RoleAssignment.role == Role.site_engineer,
            RoleAssignment.revoked_at.is_(None),
        )
    ):
        if a.is_active_on(day) and (not a.site_ids or site_id is None or site_id in a.site_ids):
            out.add(a.user_id)
    return out


def officers(db: Session, project_id: uuid.UUID) -> set[uuid.UUID]:
    from app.services.cert import alerts  # noqa: PLC0415

    return alerts.officers(db, project_id)


def managers(db: Session) -> set[uuid.UUID]:
    from app.services.cert import alerts  # noqa: PLC0415

    return alerts.managers(db)


def reps(db: Session, project_id: uuid.UUID, engagement_id: uuid.UUID | None) -> set[uuid.UUID]:
    from app.services.cert import alerts  # noqa: PLC0415

    return alerts.reps(db, project_id, engagement_id)


def site_engagements(db: Session, project_id: uuid.UUID, site_id: uuid.UUID) -> set[uuid.UUID]:
    """Engagements with Mobilised deployments on the site."""
    from app.models import Deployment  # noqa: PLC0415

    rows = db.scalars(
        select(Deployment.engagement_id).where(
            Deployment.project_id == project_id,
            Deployment.status == DeploymentStatus.mobilised,
            Deployment.site_ids.any(site_id),  # type: ignore[arg-type]
        )
    )
    return {e for e in rows if e is not None}


def site_reps(db: Session, project_id: uuid.UUID, site_id: uuid.UUID) -> set[uuid.UUID]:
    out: set[uuid.UUID] = set()
    for e in site_engagements(db, project_id, site_id):
        out |= reps(db, project_id, e)
    return out


def send(
    db: Session,
    users: Iterable[uuid.UUID],
    kind: Any,
    en: str,
    ar: str,
    project_id: uuid.UUID | None,
    entity_type: EntityType | None = None,
    entity_id: uuid.UUID | None = None,
    email: bool = False,
) -> int:
    from app.services.cert import alerts  # noqa: PLC0415

    return alerts.send(db, users, kind, en, ar, entity_type, entity_id, project_id, email=email)


def once(db: Session, key: str) -> bool:
    from app.services.cert import alerts  # noqa: PLC0415

    return alerts.once(db, key)


# ---- access, numbering, misc --------------------------------------------------------------------


def project(db: Session, p: Principal | None, project_id: uuid.UUID) -> Project:
    x = db.get(Project, project_id)
    if x is None or (p is not None and not p.can_see_project(project_id)):
        raise not_found("Project")
    return x


def need(p: Principal, project_id: uuid.UUID, cap: Any, write: bool = True) -> Grant:
    if write:
        return p.require(project_id, cap)
    g = p.grant(project_id, cap)
    if g is None:
        raise forbidden_error()
    return g


def site_ok(g: Grant, site_id: uuid.UUID | None) -> bool:
    return g.covers_site(site_id)


def next_seq(db: Session, model: Any, project_id: uuid.UUID, year: int) -> int:
    from app.services.hse_common import next_seq as ns  # noqa: PLC0415

    return ns(db, model, project_id, year)


def reason(text: str | None, minimum: int, field: str = "reason") -> str:
    if not text or len(text.strip()) < minimum:
        raise validation_error(field, f"Give a reason of at least {minimum} characters.")
    return text.strip()


def err(
    status: int, code: ErrorCode, en: str, ar: str, field: str | None = None, **meta: Any
) -> ApiError:
    from app.core.errors import field_error  # noqa: PLC0415

    errors = [field_error(field, en, "value_error", ar)] if field else None
    return ApiError(status, code, en, ar, errors=errors, meta=meta or None)


def record(
    db: Session,
    p: Principal | None,
    action: AuditAction,
    entity_type: EntityType,
    obj: Any,
    project_id: uuid.UUID | None,
    before: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    from app.services.cert import common as cc  # noqa: PLC0415

    cc.record(db, p, action, entity_type, obj, project_id, before, details, after=cc.snap(obj))


def audit_change(
    db: Session,
    p: Principal | None,
    entity_type: EntityType,
    entity_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    audit.record(
        db,
        AuditAction.update,
        p.actor(project_id) if p else audit.SYSTEM,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        before=before,
        after=after,
    )


def user_ref(db: Session, uid: uuid.UUID | None) -> Any:
    from app.services.med import common as mcommon  # noqa: PLC0415

    return mcommon.user_ref(db, uid)


def dstr(v: Decimal | None) -> str | None:
    return None if v is None else str(q1(D(v)))


def site_in_scope(db: Session, g: Grant, project_id: uuid.UUID, site_id: uuid.UUID) -> bool:
    """S scope by site; C / C1 scopes: sites where one of the engagements is Mobilised (RS-4)."""
    if not g.covers_site(site_id):
        return False
    if g.engagement_ids is None:
        return True
    return bool(site_engagements(db, project_id, site_id) & set(g.engagement_ids))


def pcode(db: Session, project_id: uuid.UUID) -> str:
    pr = db.get(Project, project_id)
    return pr.code if pr else "?"


def enabled(db: Session, project_id: uuid.UUID) -> bool:
    """6b is in use on the project (HS-1: heat_register_from set)."""
    cache: dict[uuid.UUID, bool] = db.info.setdefault("heat_enabled", {})
    if project_id not in cache:
        s = db.get(HeatSettings, project_id)
        cache[project_id] = s is not None and s.heat_register_from is not None
    return cache[project_id]


def tier1_on_site(db: Session, project_id: uuid.UUID, site_id: uuid.UUID) -> uuid.UUID | None:
    """RS-3 fallback: the tier-1 engagement working on the site."""
    from app.models import ProjectEngagement  # noqa: PLC0415

    rows = sorted(
        db.scalars(
            select(ProjectEngagement).where(
                ProjectEngagement.project_id == project_id, ProjectEngagement.tier == 1
            )
        ),
        key=lambda e: e.mobilisation_date,
    )
    for e in rows:
        if site_id in (e.site_ids or []):
            return e.id
    return rows[0].id if rows else None


def contractor_code(db: Session, engagement_id: uuid.UUID | None) -> str | None:
    from app.models import ProjectEngagement  # noqa: PLC0415

    e = db.get(ProjectEngagement, engagement_id) if engagement_id else None
    return e.contractor.short_code if e is not None and e.contractor is not None else None


def make_ca(
    db: Session,
    project_id: uuid.UUID,
    source_id: uuid.UUID,
    site_id: uuid.UUID,
    zone_id: uuid.UUID | None,
    engagement_id: uuid.UUID,
    title: str,
    description: str,
    due: date,
    created_by: uuid.UUID | None,
) -> Any:
    """A Phase 1 CA with source `heat_check`, priority high (RS-3, MB-3). Owner: the
    engagement's Contractor HSE Rep (else an HSE Officer); verifier: an HSE Officer."""
    from app.core.hse_enums import CaPriority, CaSourceType, CaStatus, ControlLevel  # noqa: PLC0415
    from app.models import CorrectiveAction  # noqa: PLC0415
    from app.services.hse_common import make_ref  # noqa: PLC0415

    offs = sorted(officers(db, project_id))
    owners = sorted(reps(db, project_id, engagement_id)) or offs or sorted(managers(db))
    verifier = (offs or sorted(managers(db)))[0]
    created = local_day()
    seq = next_seq(db, CorrectiveAction, project_id, created.year)
    ca = CorrectiveAction(
        id=uuid.uuid4(),
        project_id=project_id,
        ref=make_ref("CA", pcode(db, project_id), created.year, seq, 5),
        year=created.year,
        seq=seq,
        source_type=CaSourceType.heat_check,
        source_id=source_id,
        site_id=site_id,
        zone_id=zone_id,
        responsible_engagement_id=engagement_id,
        title=title[:150],
        description=description,
        control_level=ControlLevel.administrative,
        priority=CaPriority.high,
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
        after={"ref": ca.ref, "source_type": "heat_check"},
    )
    return ca
