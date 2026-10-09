"""Helpers shared by the Phase 6e services (spec 6e-environmental): settings (§3.16 defaults merged
over the stored values), permit status and requirements in force (§4.2, PRM-2), provider licences
(CON-2), scope and visibility helpers, numbering and the helpers re-exported from the 6b / 6d
common modules."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Capability, EntityType, Role, ZoneType
from app.core.env_enums import NoisePeriod, PermitStatus, PermitType, ProviderStatus
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.models import EnvPermit, EnvProvider, EnvSettings, Project, ProjectEngagement, Site, Zone
from app.services.field.common import (
    ca_info,
    first_rep,
    in_scope,
    is_viewer,
    make_ca,
    p18,
    roles_on,
    store_photos,
    tier1_of,
    tree_of,
)
from app.services.heat.common import (
    at_local,
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
    site_engineers,
    user_ref,
    zone_map,
)
from app.services.heat.common import once as _once
from app.services.permissions import Grant, Principal, forbidden_error

__all__ = [
    "at_local",
    "ca_info",
    "day_start",
    "err",
    "first_rep",
    "in_scope",
    "is_viewer",
    "local_day",
    "make_ca",
    "managers",
    "need",
    "next_seq",
    "officers",
    "p18",
    "pcode",
    "project",
    "reason",
    "record",
    "reps",
    "roles_on",
    "send",
    "site_engineers",
    "store_photos",
    "tier1_of",
    "tree_of",
    "user_ref",
    "zone_map",
]

D = Decimal
PT = TypeVar("PT")
C = Capability
ET = EntityType

DEFAULTS: dict[str, Any] = {
    "permit_alert_days": [90, 60, 30, 14, 7, 0],
    "provider_licence_alert_days": [30, 14, 7, 0],
    "manifest_return_days": 7,
    "weight_discrepancy_pct": "10.0",
    "mwan_manifest_required_for": ["hazardous"],
    "haz_storage_max_days": 90,
    "containment_min_pct": 110,
    "spill_reportable_l": "20.0",
    "airside_spill_always_reportable": True,
    "data_capture_pct": "75.0",
    "noise_day_start": "07:00",
    "noise_night_start": "22:00",
    "background_ops_event_types": ["dust_sandstorm", "lvp"],
    "post_storm_check_hours": 4,
    "exceedance_review_days": 3,
    "complaint_response_days": 7,
    "authority_complaint_response_days": 3,
    "aspect_review_months": 12,
    "diversion_target_pct": "70.0",
    "monitoring_warning_pct": "95.0",
    "custody_warning_pct": "95.0",
    "exceedance_warning_count": 2,
    "photo_retention_months": 24,
    "complainant_retention_months": 12,
}
EXPIRING_DAYS = 30


@dataclass
class Cfg:
    project_id: uuid.UUID
    notifications_from: date | None
    v: dict[str, Any]

    def __getitem__(self, k: str) -> Any:
        return self.v[k]

    def dec(self, k: str) -> Decimal:
        return D(str(self.v[k]))

    def period_of(self, start_local: datetime) -> NoisePeriod:
        """LIM-3: a window belongs to the period of its start time."""
        t = start_local.time()
        day0 = time.fromisoformat(self.v["noise_day_start"])
        night0 = time.fromisoformat(self.v["noise_night_start"])
        return NoisePeriod.day if day0 <= t < night0 else NoisePeriod.night


def settings_row(db: Session, project_id: uuid.UUID) -> EnvSettings:
    s = db.get(EnvSettings, project_id)
    if s is None:
        s = EnvSettings(project_id=project_id, values={})
        db.add(s)
        db.flush()
    return s


def cfg(db: Session, project_id: uuid.UUID) -> Cfg:
    cache: dict[uuid.UUID, Cfg] = db.info.setdefault("env_cfg", {})
    if project_id not in cache:
        s = db.get(EnvSettings, project_id)
        cache[project_id] = Cfg(
            project_id,
            s.env_notifications_from if s else None,
            {**DEFAULTS, **((s.values or {}) if s else {})},
        )
    return cache[project_id]


def clear_cache(db: Session) -> None:
    for k in ("env_cfg", "env_permits"):
        db.info.pop(k, None)


def q1(v: Decimal | None) -> Decimal | None:
    return None if v is None else D(v).quantize(D("0.1"), rounding=ROUND_HALF_UP)


def s1(v: Decimal | None) -> str | None:
    x = q1(v)
    return None if x is None else str(x)


def s3(v: Decimal | None) -> str | None:
    return None if v is None else str(D(v).quantize(D("0.001"), rounding=ROUND_HALF_UP))


def to_local(at: datetime) -> datetime:
    from app.services.access import common as acommon  # noqa: PLC0415

    return at.astimezone(acommon.RIYADH)


# ---- scope ---------------------------------------------------------------------------------------


def view_grant(db: Session, p: Principal, project_id: uuid.UUID) -> Grant:
    project(db, p, project_id)
    return need(p, project_id, C.env_view, write=False)


def require(
    p: Principal,
    project_id: uuid.UUID,
    cap: Capability,
    site_id: uuid.UUID | None = None,
    eng_id: uuid.UUID | None = None,
    check_eng: bool = True,
) -> Grant:
    """A write capability, narrowed to the record's site (S scope) and engagement (C / C1)."""
    g = p.require(project_id, cap)
    if site_id is not None and not g.covers_site(site_id):
        raise forbidden_error("This site is outside your scope.")
    if check_eng and g.engagement_ids is not None and not g.covers_engagement(eng_id):
        raise forbidden_error("This contractor is outside your scope.")
    return g


def eng_of_project(db: Session, project_id: uuid.UUID, eng_id: uuid.UUID | None) -> None:
    e = db.get(ProjectEngagement, eng_id) if eng_id else None
    if eng_id is not None and (e is None or e.project_id != project_id):
        raise validation_error("engagement_id", "The contractor is not engaged on this project.")


def site_of(db: Session, project_id: uuid.UUID, site_id: uuid.UUID) -> Site:
    s = db.get(Site, site_id)
    if s is None or s.project_id != project_id:
        raise validation_error("site_id", "The site does not belong to this project.")
    return s


def zone_of(db: Session, site_id: uuid.UUID, zone_id: uuid.UUID | None) -> Zone | None:
    if zone_id is None:
        return None
    z = db.get(Zone, zone_id)
    if z is None or z.site_id != site_id:
        raise validation_error("zone_id", "The zone does not belong to the site.")
    return z


def is_airside(z: Zone | None) -> bool:
    return z is not None and z.zone_type == ZoneType.airside


def eng_code(db: Session, eng_id: uuid.UUID | None) -> str | None:
    from app.services.heat.common import contractor_code  # noqa: PLC0415

    return contractor_code(db, eng_id)


def is_airport(db: Session, project_id: uuid.UUID) -> bool:
    from app.core.enums import ProjectType  # noqa: PLC0415

    pr = db.get(Project, project_id)
    return pr is not None and pr.project_type == ProjectType.airport


def staff(db: Session, p: Principal, project_id: uuid.UUID) -> bool:
    """HSE Manager / HSE Officer on the project."""
    return p.is_manager or bool(roles_on(db, p.user.id, project_id) & {Role.hse_officer})


def once(db: Session, key: str) -> bool:
    return _once(db, key)


def ref(prefix: str, code: str, year: int, seq: int, width: int) -> str:
    return f"{prefix}-{code}-{year}-{seq:0{width}d}"


def not_found_or(x: Any, what: str) -> Any:
    if x is None:
        raise not_found(what)
    return x


def code_err(code: ErrorCode, en: str, ar: str, field: str | None = None, **meta: Any) -> ApiError:
    return err(422, code, en, ar, field, **meta)


# ---- permits and licences (§4.2, PRM-2, CON-2) ---------------------------------------------------

NO_EXPIRY = frozenset({PermitType.eia_approval, PermitType.cemp_approval, PermitType.other})


def _manual(pm: EnvPermit, d: date) -> PermitStatus | None:
    if pm.manual_status is None:
        return None
    if pm.manual_status == PermitStatus.pending:
        return PermitStatus.pending
    if pm.manual_from is None or pm.manual_from <= d:
        return pm.manual_status
    return None


def in_force(pm: EnvPermit, d: date) -> bool:
    """§4.2: valid_from ≤ d ≤ valid_to (or no expiry), not pending, suspended or cancelled on d."""
    if _manual(pm, d) is not None:
        return False
    if pm.valid_from is not None and d < pm.valid_from:
        return False
    return pm.valid_to is None or d <= pm.valid_to


def project_permits(db: Session, project_id: uuid.UUID) -> list[EnvPermit]:
    cache: dict[uuid.UUID, list[EnvPermit]] = db.info.setdefault("env_permits", {})
    if project_id not in cache:
        cache[project_id] = list(
            db.scalars(
                select(EnvPermit)
                .where(EnvPermit.project_id == project_id)
                .order_by(EnvPermit.record_no)
            )
        )
    return cache[project_id]


def permit_status(db: Session, pm: EnvPermit, d: date) -> PermitStatus:
    m = _manual(pm, d)
    if m is not None:
        return m
    if pm.valid_from is not None and d < pm.valid_from:
        return PermitStatus.pending
    if pm.valid_to is not None and d > pm.valid_to:
        if (
            pm.project_id is not None
            and pm.requirement_code
            and any(
                o.id != pm.id and o.requirement_code == pm.requirement_code and in_force(o, d)
                for o in project_permits(db, pm.project_id)
            )
        ):
            return PermitStatus.superseded
        return PermitStatus.expired
    if pm.valid_to is not None and (pm.valid_to - d).days <= EXPIRING_DAYS:
        return PermitStatus.expiring
    return PermitStatus.valid


def requirements(db: Session, project_id: uuid.UUID) -> dict[str, list[EnvPermit]]:
    """requirement_code → records of required project permits."""
    out: dict[str, list[EnvPermit]] = {}
    for pm in project_permits(db, project_id):
        if pm.required and pm.requirement_code:
            out.setdefault(pm.requirement_code, []).append(pm)
    return out


def applicable(pms: list[EnvPermit], d: date) -> bool:
    """PRM-2: a requirement with applies_from / applies_to is evaluated only inside the window."""
    for pm in pms:
        if (pm.applies_from is None or pm.applies_from <= d) and (
            pm.applies_to is None or d <= pm.applies_to
        ):
            return True
    return False


def requirement_in_force(db: Session, project_id: uuid.UUID, code: str, d: date) -> bool:
    return any(in_force(pm, d) for pm in requirements(db, project_id).get(code, []))


def permit_valid_on(db: Session, pm: EnvPermit | None, d: date) -> bool:
    """WAT-3: the point's permit requirement is in force on d."""
    if pm is None:
        return False
    if pm.requirement_code and pm.project_id:
        return requirement_in_force(db, pm.project_id, pm.requirement_code, d)
    return in_force(pm, d)


def licences(db: Session, provider_id: uuid.UUID) -> list[EnvPermit]:
    return list(
        db.scalars(
            select(EnvPermit)
            .where(EnvPermit.provider_id == provider_id)
            .order_by(EnvPermit.record_no)
        )
    )


def provider_ok(pv: EnvProvider | None, field: str) -> EnvProvider:
    if pv is None:
        raise validation_error(field, "Unknown provider.")
    if pv.status != ProviderStatus.approved:
        raise code_err(
            ErrorCode.PROVIDER_NOT_APPROVED,
            f"{pv.provider_code} is {pv.status.value}; it cannot be named on new records.",
            f"مقدم الخدمة {pv.provider_code} غير معتمد حالياً.",
            field,
        )
    return pv


def licence_for(
    db: Session,
    pv: EnvProvider,
    d: date,
    activities: frozenset[str],
    wclass: str | None,
    field: str,
    types: frozenset[PermitType] | None = None,
    facility_code: str | None = None,
) -> EnvPermit:
    """CON-2: a licence in force on d covering one of the activities and the class."""
    live = [
        x
        for x in licences(db, pv.id)
        if in_force(x, d) and (types is None or x.permit_type in types)
    ]
    if not live:
        raise code_err(
            ErrorCode.PROVIDER_LICENCE_INVALID,
            f"{pv.provider_code} has no licence in force on {d.isoformat()}.",
            f"لا يوجد ترخيص ساري لدى {pv.provider_code} بتاريخ {d.isoformat()}.",
            field,
        )
    for x in live:
        sc = x.scope or {}
        acts = set(sc.get("activities") or [])
        classes = set(sc.get("waste_classes") or [])
        if facility_code and sc.get("facility_code") and sc["facility_code"] != facility_code:
            continue
        if acts & activities and (wclass is None or wclass in classes):
            return x
    raise code_err(
        ErrorCode.LICENCE_SCOPE_MISMATCH,
        f"The licence of {pv.provider_code} does not cover this activity or waste class.",
        f"ترخيص {pv.provider_code} لا يغطي هذا النشاط أو فئة النفايات.",
        field,
    )


def days_between(d0: date, d1: date) -> list[date]:
    return [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]


def paged(cls: type[PT], rows: list[Any], page: int, size: int, fn: Any) -> PT:
    out: PT = cls(  # type: ignore[call-arg]
        items=[fn(x) for x in rows[(page - 1) * size : page * size]],
        total=len(rows),
        page=page,
        page_size=size,
    )
    return out


def scope_ok(g: Grant, site_id: uuid.UUID | None, eng_id: uuid.UUID | None) -> bool:
    """Read scope of a record: S by site, C / C1 by engagement (None engagement → site only)."""
    if site_id is not None and not g.covers_site(site_id):
        return False
    return g.engagement_ids is None or eng_id is None or g.covers_engagement(eng_id)


def warn(code: str, en: str, ar: str, field: str | None = None) -> Any:
    from app.schemas.hse_common import ApiWarning  # noqa: PLC0415

    return ApiWarning(code=code, message=en, message_ar=ar, field=field)


WARNINGS: dict[str, tuple[str, str]] = {
    "AVP_NOT_FOUND": (
        "No Active AVP for this plate on the dispatch date (the vehicle may have been escorted).",
        "لا يوجد تصريح مركبة ساري لهذه اللوحة في تاريخ الإرسال.",
    ),
    "PERMIT_NOT_VALID": (
        "The point's permit requirement is not in force on this date.",
        "التصريح المرتبط بالنقطة غير ساري في هذا التاريخ.",
    ),
}


def warnings_of(codes: list[str] | None) -> list[Any]:
    return [warn(c, *WARNINGS.get(c, (c, c))) for c in codes or []]


def cap_holders(
    db: Session, project_id: uuid.UUID, cap: Capability, site_id: uuid.UUID | None
) -> set[uuid.UUID]:
    """Users whose active role on the project holds the capability for the site (AIR-1: 67)."""
    from app.models import RoleAssignment  # noqa: PLC0415
    from app.services.permissions import MATRIX  # noqa: PLC0415

    day = local_day()
    out: set[uuid.UUID] = set()
    for a in db.scalars(
        select(RoleAssignment).where(
            RoleAssignment.project_id == project_id, RoleAssignment.revoked_at.is_(None)
        )
    ):
        if not a.is_active_on(day) or cap not in MATRIX.get(a.role, {}):
            continue
        if a.site_ids and site_id is not None and site_id not in a.site_ids:
            continue
        out.add(a.user_id)
    return out
