"""Helpers shared by the Option 7b services (spec 7b-fleet-driver v2.0, Prototype): settings
(§3.5 defaults merged over the stored values), the live switch (`SITE_VEHICLES_NOT_LIVE`), scope
helpers (P7b-1), readiness (§4.1, derivable for any day), authorisation coverage (PU-6),
numbering, the Phase 5 courses DEF-DRV / BUS-DRV and the shared recipients."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.access_enums import PlateType, VehicleStatus
from app.core.cert_enums import ServiceStatus
from app.core.clock import now
from app.core.enums import Capability, CapabilityScope, Role
from app.core.errors import ApiError, ErrorCode, not_found
from app.core.hse_enums import Weekday
from app.core.site_vehicle_enums import (
    OPERATING_CARD_CLASSES,
    SITE_SCOPES,
    SiteVehAuthStatus,
    SiteVehDriverGroup,
    SiteVehPolicy,
    SiteVehReadiness,
)
from app.models import (
    Deployment,
    DriverAuthorisation,
    EquipmentItem,
    Project,
    ProjectEngagement,
    SiteVehicleSettings,
    Vehicle,
    VehicleCheck,
    Worker,
)
from app.schemas.access_common import WorkerRef
from app.services.access import common as acommon
from app.services.heat.common import err, officers, once, record, reps, send
from app.services.permissions import Grant, Principal, forbidden_error

# re-exported for the 7b services
__all__ = ["err", "officers", "once", "record", "reps", "send"]

C = Capability
R = SiteVehReadiness
G = SiteVehDriverGroup

DEFAULTS: dict[str, Any] = {
    "driver_auth_validity_months": 24,
    "defensive_driving_code": "DEF-DRV",
    "bus_driving_code": "BUS-DRV",
    "driver_hook_policy": SiteVehPolicy.warn.value,
    "driver_auth_policy": SiteVehPolicy.warn.value,
    "pre_use_required_groups": [g.value for g in SiteVehDriverGroup],
    "rest_weekday": Weekday.friday.value,
    "journey_hint_km": 150,
    "journey_hint_night_from": "22:00",
    "journey_hint_night_to": "05:00",
}
RANGES: dict[str, tuple[int, int]] = {
    "driver_auth_validity_months": (12, 36),
    "journey_hint_km": (50, 500),
}
TEMPLATE_BY_GROUP = {G.light: "VPU-L", G.bus: "VPU-B", G.heavy: "VPU-H", G.plant: "VPU-H"}
WEEKDAY_INDEX = {
    Weekday.monday: 0,
    Weekday.tuesday: 1,
    Weekday.wednesday: 2,
    Weekday.thursday: 3,
    Weekday.friday: 4,
    Weekday.saturday: 5,
    Weekday.sunday: 6,
}
MEDICAL_CODE = "DRIVER-FIT"
# Phase 5 catalogue rows added by 7b (§11.5; validity 36 months ASSUMPTION)
COURSES: dict[str, tuple[str, str]] = {
    "DEF-DRV": ("Defensive driving", "القيادة الوقائية"),
    "BUS-DRV": ("Crew bus driving", "قيادة حافلات العمال"),
}
COURSE_VALIDITY_MONTHS = 36


# ---- settings ------------------------------------------------------------------------------------


@dataclass
class Cfg:
    project_id: uuid.UUID
    live_from: date | None
    v: dict[str, Any]

    def __getitem__(self, k: str) -> Any:
        return self.v[k]

    @property
    def live(self) -> bool:
        return self.live_from is not None

    @property
    def hook_policy(self) -> SiteVehPolicy:
        return SiteVehPolicy(self.v["driver_hook_policy"])

    @property
    def auth_policy(self) -> SiteVehPolicy:
        return SiteVehPolicy(self.v["driver_auth_policy"])

    @property
    def required_groups(self) -> set[SiteVehDriverGroup]:
        return {SiteVehDriverGroup(g) for g in self.v["pre_use_required_groups"]}

    @property
    def rest_index(self) -> int:
        return WEEKDAY_INDEX[Weekday(self.v["rest_weekday"])]

    def working_day(self, d: date) -> bool:
        return d.weekday() != self.rest_index

    @property
    def night(self) -> tuple[time, time]:
        return (
            time.fromisoformat(self.v["journey_hint_night_from"]),
            time.fromisoformat(self.v["journey_hint_night_to"]),
        )


def settings_row(db: Session, project_id: uuid.UUID) -> SiteVehicleSettings:
    s = db.get(SiteVehicleSettings, project_id)
    if s is None:
        s = SiteVehicleSettings(project_id=project_id, values={})
        db.add(s)
        db.flush()
    return s


def cfg(db: Session, project_id: uuid.UUID) -> Cfg:
    cache: dict[uuid.UUID, Cfg] = db.info.setdefault("sv_cfg", {})
    if project_id not in cache:
        s = db.get(SiteVehicleSettings, project_id)
        cache[project_id] = Cfg(
            project_id,
            s.site_vehicles_from if s else None,
            {**DEFAULTS, **((s.values or {}) if s else {})},
        )
    return cache[project_id]


def clear_cache(db: Session) -> None:
    db.info.pop("sv_cfg", None)


def live_project_ids(db: Session) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(SiteVehicleSettings.project_id).where(
                SiteVehicleSettings.site_vehicles_from.is_not(None)
            )
        )
    )


def not_live() -> ApiError:
    return ApiError(
        422,
        ErrorCode.SITE_VEHICLES_NOT_LIVE,
        "Site vehicle readiness is not switched on for this project (site_vehicles_from).",
        "جاهزية مركبات الموقع غير مفعّلة لهذا المشروع.",
    )


def require_live(db: Session, project_id: uuid.UUID) -> Cfg:
    c = cfg(db, project_id)
    if not c.live:
        raise not_live()
    return c


# ---- time ----------------------------------------------------------------------------------------


def local_day(at: datetime | None = None) -> date:
    return acommon.local_day(at or now())


def day_end(d: date) -> datetime:
    return acommon.local_midnight_utc(d + timedelta(days=1))


# ---- scope (P7b-1) -------------------------------------------------------------------------------


def project(db: Session, p: Principal, project_id: uuid.UUID) -> Project:
    x = db.get(Project, project_id)
    if x is None or not p.can_see_project(project_id):
        raise not_found("Project")
    return x


def is_viewer(p: Principal, project_id: uuid.UUID) -> bool:
    """Viewer / Client holds 233 for aggregates only (P7b-1)."""
    if p.is_manager:
        return False
    s = p.projects.get(project_id)
    return s is not None and s.read_only


def view_grant(p: Principal, project_id: uuid.UUID, registers: bool = True) -> Grant:
    """233 grant; `registers` refuses the Viewer / Client (aggregates only)."""
    g = p.grant(project_id, C.site_vehicle_view)
    if g is None or (registers and is_viewer(p, project_id)):
        raise forbidden_error()
    return g


def status_only(p: Principal, project_id: uuid.UUID) -> bool:
    """Site engineers (S scope) see authorisation status only (AC12)."""
    g = p.grant(project_id, C.site_vehicle_view)
    return g is not None and g.scope == CapabilityScope.sites


def names_visible(p: Principal, project_id: uuid.UUID) -> bool:
    g = p.grant(project_id, C.site_vehicle_view)
    if g is not None and g.scope != CapabilityScope.sites:
        return True
    return acommon.can_see_names(p, project_id)


def eng_sites(db: Session, engagement_id: uuid.UUID | None) -> list[uuid.UUID]:
    cache: dict[uuid.UUID, list[uuid.UUID]] = db.info.setdefault("sv_eng_sites", {})
    if engagement_id is None:
        return []
    if engagement_id not in cache:
        e = db.get(ProjectEngagement, engagement_id)
        cache[engagement_id] = list(e.site_ids or []) if e else []
    return cache[engagement_id]


def covers_eng(db: Session, g: Grant | None, engagement_id: uuid.UUID | None) -> bool:
    """Vehicles and drivers have no site of their own: S scope uses the engagement's sites."""
    if g is None:
        return False
    if g.site_ids is not None:
        sites = eng_sites(db, engagement_id)
        if not any(s in g.site_ids for s in sites):
            return False
    return g.engagement_ids is None or (
        engagement_id is not None and engagement_id in g.engagement_ids
    )


def covers_any(db: Session, g: Grant | None, engs: Iterable[uuid.UUID | None]) -> bool:
    return any(covers_eng(db, g, e) for e in engs)


def register_engs(p: Principal, project_id: uuid.UUID) -> set[uuid.UUID] | None:
    """SV-4 / AC4: reps list and register their own engagement's vehicles (234 scope)."""
    if p.is_manager:
        return None
    s = p.projects.get(project_id)
    if s is None:
        return set()
    if Role.contractor_hse_rep in s.roles and Role.hse_officer not in s.roles:
        g = s.grants.get(C.site_vehicle_manage)
        if g is not None and g.engagement_ids is not None:
            return set(g.engagement_ids)
    g = s.grants.get(C.site_vehicle_view)
    return None if g is None or g.engagement_ids is None else set(g.engagement_ids)


def is_rep_only(p: Principal, project_id: uuid.UUID) -> bool:
    """A contractor rep without an officer role on the project (C scope: propose, no verify)."""
    if p.is_manager:
        return False
    s = p.projects.get(project_id)
    return s is not None and Role.hse_officer not in s.roles


def worker_ref(w: Worker, names: bool) -> WorkerRef:
    return acommon.worker_ref(w, names)


# ---- vehicles and readiness (§4.1) ---------------------------------------------------------------


def is_site(v: Vehicle) -> bool:
    return v.site_scope in SITE_SCOPES


def site_vehicle(db: Session, vehicle_id: uuid.UUID) -> Vehicle:
    v = db.get(Vehicle, vehicle_id)
    if v is None or not is_site(v):
        raise not_found("Site vehicle")
    return v


def phase4_items(db: Session, vehicle_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, EquipmentItem]:
    ids = list(vehicle_ids)
    if not ids:
        return {}
    rows = db.scalars(select(EquipmentItem).where(EquipmentItem.vehicle_id.in_(ids)))
    return {i.vehicle_id: i for i in rows if i.vehicle_id is not None}


def hold_checks(
    db: Session, vehicle_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[VehicleCheck]]:
    ids = list(vehicle_ids)
    out: dict[uuid.UUID, list[VehicleCheck]] = {}
    if not ids:
        return out
    for c in db.scalars(
        select(VehicleCheck)
        .where(VehicleCheck.vehicle_id.in_(ids), VehicleCheck.hold_set.is_(True))
        .order_by(VehicleCheck.completed_at)
    ):
        out.setdefault(c.vehicle_id, []).append(c)
    return out


def hold_on(holds: list[VehicleCheck], d: date) -> VehicleCheck | None:
    """PU-3 hold in force on day d (set on or before d, not cleared before the end of d)."""
    for c in reversed(holds):
        if c.check_date <= d and (c.hold_cleared_at is None or local_day(c.hold_cleared_at) > d):
            return c
    return None


def active_hold(db: Session, vehicle_id: uuid.UUID) -> VehicleCheck | None:
    return db.scalar(
        select(VehicleCheck)
        .where(
            VehicleCheck.vehicle_id == vehicle_id,
            VehicleCheck.hold_set.is_(True),
            VehicleCheck.hold_cleared_at.is_(None),
        )
        .order_by(VehicleCheck.completed_at.desc())
        .limit(1)
    )


def documents(v: Vehicle) -> list[tuple[str, date]]:
    """Road documents judged for readiness (SV-2): plated vehicles only (plant without a plate
    has no road documents, its readiness comes from Phase 4)."""
    if v.plate_type == PlateType.none:
        return []
    docs = [("istimara", v.istimara_expiry), ("insurance", v.insurance_expiry),
            ("mvpi", v.mvpi_expiry), ("operating_card", v.operating_card_expiry)]  # fmt: skip
    return [(k, d) for k, d in docs if d is not None]


def operating_card_required(v: Vehicle) -> bool:
    return (
        v.use_class in OPERATING_CARD_CLASSES
        and v.plate_type != PlateType.none
        and v.use_class is not None
    )


def withdrawn_on(v: Vehicle, d: date) -> bool:
    if v.status != VehicleStatus.withdrawn:
        return False
    return v.withdrawn_on is None or v.withdrawn_on <= d


def idle_on(v: Vehicle, d: date) -> bool:
    return v.idle_from is not None and v.idle_from <= d and (v.idle_to is None or d <= v.idle_to)


def readiness_on(
    v: Vehicle, d: date, item: EquipmentItem | None, holds: list[VehicleCheck]
) -> tuple[SiteVehReadiness, list[str]]:
    """§4.1 (first matching state wins) with the reasons. The Phase 4 status is the current one
    (DECISIONS: Phase 4 history is not replayed)."""
    if withdrawn_on(v, d):
        return R.withdrawn, ["withdrawn"]
    if idle_on(v, d):
        return R.idle, ["idle"]
    h = hold_on(holds, d)
    if h is not None:
        return R.defect_hold, [f"defect_hold:{h.check_no}"]
    if item is not None and item.service_status != ServiceStatus.in_service:
        return R.not_certified, [f"phase4:{item.service_status.value}"]
    expired = [f"{k}:{x.isoformat()}" for k, x in documents(v) if x < d]
    if expired:
        return R.docs_expired, expired
    return R.ready, []


def readiness(db: Session, v: Vehicle, d: date | None = None) -> tuple[SiteVehReadiness, list[str]]:
    d = d or local_day()
    return readiness_on(
        v, d, phase4_items(db, [v.id]).get(v.id), hold_checks(db, [v.id]).get(v.id, [])
    )


def refresh(db: Session, v: Vehicle) -> SiteVehReadiness:
    """Store the derived readiness (daily and on change, §4.1)."""
    if not is_site(v):
        return v.readiness or R.ready
    r, _ = readiness(db, v)
    v.readiness = r
    v.readiness_on = local_day()
    return r


# ---- authorisations (PU-6) ----


def covering_auth(
    db: Session,
    project_id: uuid.UUID,
    worker_id: uuid.UUID,
    group: SiteVehDriverGroup | None,
    d: date,
) -> DriverAuthorisation | None:
    """An Active authorisation covering the group on day d (PU-6)."""
    if group is None:
        return None
    for a in db.scalars(
        select(DriverAuthorisation).where(
            DriverAuthorisation.project_id == project_id,
            DriverAuthorisation.worker_id == worker_id,
            DriverAuthorisation.status == SiteVehAuthStatus.active,
        )
    ):
        if group.value not in (a.groups or []):
            continue
        if a.issued_on > d:
            continue
        if a.effective_valid_until is not None and a.effective_valid_until < d:
            continue
        return a
    return None


def mobilised_deployment(db: Session, project_id: uuid.UUID, worker_id: uuid.UUID) -> Deployment:
    from app.core.access_enums import DeploymentStatus  # noqa: PLC0415
    from app.core.errors import validation_error  # noqa: PLC0415

    dep = db.scalar(
        select(Deployment).where(
            Deployment.project_id == project_id,
            Deployment.worker_id == worker_id,
            Deployment.status == DeploymentStatus.mobilised,
        )
    )
    if dep is None:
        raise validation_error(
            "worker_id", "The worker has no Mobilised deployment on this project."
        )
    return dep


def deployment_engagement(
    db: Session, project_id: uuid.UUID, worker_id: uuid.UUID
) -> uuid.UUID | None:
    return db.scalar(
        select(Deployment.engagement_id)
        .where(Deployment.project_id == project_id, Deployment.worker_id == worker_id)
        .order_by(Deployment.mobilised_on.desc())
        .limit(1)
    )


# ---- numbering -----------------------------------------------------------------------------------


def pcode(db: Session, project_id: uuid.UUID) -> str:
    pr = db.get(Project, project_id)
    return pr.code if pr else "?"


def lock_project(db: Session, project_id: uuid.UUID) -> None:
    db.execute(select(Project.id).where(Project.id == project_id).with_for_update())


def next_auth_no(db: Session, project_id: uuid.UUID) -> tuple[int, str]:
    lock_project(db, project_id)
    n = (
        int(
            db.scalar(
                select(func.max(DriverAuthorisation.seq)).where(
                    DriverAuthorisation.project_id == project_id
                )
            )
            or 0
        )
        + 1
    )
    return n, f"DA-{pcode(db, project_id)}-{n:04d}"


def next_check_no(db: Session, project_id: uuid.UUID, d: date) -> tuple[int, str]:
    lock_project(db, project_id)
    n = (
        int(
            db.scalar(
                select(func.max(VehicleCheck.seq)).where(
                    VehicleCheck.project_id == project_id, VehicleCheck.check_date == d
                )
            )
            or 0
        )
        + 1
    )
    return n, f"VPC-{pcode(db, project_id)}-{d:%Y%m%d}-{n:04d}"


# ---- Phase 5 courses (§11.5) ---------------------------------------------------------------------


def ensure_courses(db: Session) -> None:
    """DEF-DRV and BUS-DRV exist in the Phase 5 catalogue (created once when 7b is switched on
    or seeded; then edited in Phase 5 like any course)."""
    from app.core.train_enums import CourseCategory, DeliveryMode  # noqa: PLC0415
    from app.models import TrainingCourse  # noqa: PLC0415

    have = set(db.scalars(select(TrainingCourse.code).where(TrainingCourse.code.in_(COURSES))))
    added = False
    for code, (en, ar) in COURSES.items():
        if code in have:
            continue
        db.add(
            TrainingCourse(
                id=uuid.uuid4(),
                code=code,
                name_en=en,
                name_ar=ar,
                category=CourseCategory.high_risk_task,
                induction_project_codes={},
                validity_months=COURSE_VALIDITY_MONTHS,
                min_duration_hours=Decimal("8.00"),
                delivery_modes=[DeliveryMode.classroom.value, DeliveryMode.practical.value],
                theory_required=True,
                pass_mark_pct=80,
                practical_required=True,
                prerequisite_codes=[],
                satisfies=[],
                internal_allowed=True,
                contractor_delivery_allowed=True,
                accreditation_bodies_required=[],
                languages_offered=["ar", "en", "ur", "hi"],
                active=True,
                seeded=False,
                seed_fake=False,
            )
        )
        added = True
    if added:
        db.flush()
        db.info.pop("train_courses", None)
        from app.services.train import common as tcommon  # noqa: PLC0415

        tcommon.clear_cache(db)


# ---- recipients ----------------------------------------------------------------------------------


def rep_users(
    db: Session, project_id: uuid.UUID, engagement_id: uuid.UUID | None
) -> set[uuid.UUID]:
    return set(reps(db, project_id, engagement_id)) if engagement_id else set()


def officer_users(db: Session, project_id: uuid.UUID) -> set[uuid.UUID]:
    return set(officers(db, project_id))


def site_vehicle_query(project_id: uuid.UUID) -> Any:
    return select(Vehicle).where(
        Vehicle.project_id == project_id,
        or_(*[Vehicle.site_scope == s for s in SITE_SCOPES]),
    )
