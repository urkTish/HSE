"""Zone access profiles (spec 2-access-permits §3.5, ZP-1, ZP-2, IN-3)."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import AreaCategory, InductionDelivererRole, InductionType
from app.core.clock import now
from app.core.enums import AirsideArea, AuditAction, Capability, EntityType, ZoneType
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.models import AccessSettings, InductionCourse, PassArea, Project, Zone, ZoneAccessProfile
from app.schemas.access_common import HookRequirementRead
from app.schemas.inductions import (
    ZoneAccessProfileList,
    ZoneAccessProfileRead,
    ZoneAccessProfileUpdate,
)
from app.services import audit, projects
from app.services.access import common
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error

MANOEUVRING = {
    AirsideArea.runway,
    AirsideArea.runway_strip,
    AirsideArea.resa,
    AirsideArea.taxiway,
    AirsideArea.taxiway_strip,
    AirsideArea.ils_critical,
    AirsideArea.ils_sensitive,
}
CATEGORY_RANK = {AreaCategory.airside_roads: 1, AreaCategory.apron: 2, AreaCategory.manoeuvring: 3}


def area_category(zone: Zone) -> AreaCategory | None:
    if zone.airside_area in MANOEUVRING:
        return AreaCategory.manoeuvring
    if zone.airside_area == AirsideArea.apron:
        return AreaCategory.apron
    if zone.airside_area == AirsideArea.airside_road:
        return AreaCategory.airside_roads
    return None


def covers(have: AreaCategory | str, need: AreaCategory | str | None) -> bool:
    """DP-1: manoeuvring ⊇ apron ⊇ airside_roads."""
    if need is None:
        return True
    return CATEGORY_RANK[AreaCategory(have)] >= CATEGORY_RANK[AreaCategory(need)]


def setting_ratio(s: AccessSettings, cat: AreaCategory | None) -> int:
    if cat == AreaCategory.manoeuvring:
        return s.escort_ratio_max_manoeuvring
    if cat == AreaCategory.apron:
        return s.escort_ratio_max_apron
    return s.escort_ratio_max_other


def course_code(db: Session, project_id: uuid.UUID, kind: InductionType) -> str | None:
    return db.scalar(
        select(InductionCourse.code)
        .where(
            InductionCourse.project_id == project_id,
            InductionCourse.induction_type == kind,
            InductionCourse.active.is_(True),
        )
        .order_by(InductionCourse.created_at)
        .limit(1)
    )


def defaults(db: Session, zone: Zone) -> dict[str, Any]:
    """ZP-1."""
    s = common.settings(db, zone.project_id)
    gen = course_code(db, zone.project_id, InductionType.general_site)
    out: dict[str, Any] = {
        "required_inductions": [gen] if gen else [],
        "airport_pass_area_code": None,
        "access_permit_required": False,
        "adp_category_required": None,
        "avp_area_required": None,
        "escort_ratio_max": None,
        "lvp_withdrawal_required": False,
        "ils_outage_notam_required": False,
    }
    if zone.zone_type != ZoneType.airside:
        return out
    air = course_code(db, zone.project_id, InductionType.airside)
    if air:
        out["required_inductions"] = [*out["required_inductions"], air]
    cat = area_category(zone)
    if zone.security_restricted_area:
        out["airport_pass_area_code"] = db.scalar(
            select(PassArea.code).where(
                PassArea.project_id == zone.project_id, PassArea.zone_ids.contains([zone.id])
            )
        )
    out["access_permit_required"] = bool(zone.security_restricted_area or zone.in_movement_area)
    if zone.adp_required:
        out["adp_category_required"] = cat
    out["avp_area_required"] = cat
    out["lvp_withdrawal_required"] = zone.airside_area in MANOEUVRING
    out["ils_outage_notam_required"] = zone.airside_area == AirsideArea.ils_critical
    out["escort_ratio_max"] = setting_ratio(s, cat)
    return out


def ensure(db: Session, zone: Zone) -> ZoneAccessProfile:
    prof = db.get(ZoneAccessProfile, zone.id)
    if prof is None:
        prof = ZoneAccessProfile(
            zone_id=zone.id, project_id=zone.project_id, hook_requirements=[], **defaults(db, zone)
        )
        db.add(prof)
        db.flush()
    return prof


def on_zone_saved(db: Session, zone: Zone, created: bool) -> None:
    """Zone created → profile with defaults; airside attributes changed → re-apply the derived
    defaults (inductions and hooks are kept, the airside course is re-added)."""
    prof = db.get(ZoneAccessProfile, zone.id)
    if prof is None or created:
        ensure(db, zone)
        return
    d = defaults(db, zone)
    for k, v in d.items():
        if k == "required_inductions":
            prof.required_inductions = list(dict.fromkeys([*v, *prof.required_inductions]))
        else:
            setattr(prof, k, v)
    prof.updated_at = now()


def _read(db: Session, prof: ZoneAccessProfile, zone: Zone) -> ZoneAccessProfileRead:
    refs = Refs(db)
    zr = refs.zone(zone.id)
    assert zr is not None  # noqa: S101
    return ZoneAccessProfileRead(
        zone=zr,
        site_id=zone.site_id,
        required_inductions=list(prof.required_inductions or []),
        airport_pass_area_code=prof.airport_pass_area_code,
        access_permit_required=prof.access_permit_required,
        adp_category_required=prof.adp_category_required,
        avp_area_required=prof.avp_area_required,
        escort_ratio_max=prof.escort_ratio_max,
        lvp_withdrawal_required=prof.lvp_withdrawal_required,
        ils_outage_notam_required=prof.ils_outage_notam_required,
        hook_requirements=[HookRequirementRead(**h) for h in prof.hook_requirements or []],
        updated_at=prof.updated_at,
        updated_by=refs.user(prof.updated_by_user_id),
    )


def _zone(db: Session, p: Principal, zone_id: uuid.UUID) -> tuple[Zone, Project]:
    zone = db.get(Zone, zone_id)
    if zone is None:
        raise not_found("Zone")
    project = projects.get_visible(db, p, zone.project_id)
    return zone, project


def read(db: Session, p: Principal, zone_id: uuid.UUID) -> ZoneAccessProfileRead:
    zone, _ = _zone(db, p, zone_id)
    return _read(db, ensure(db, zone), zone)


def list_for(
    db: Session, p: Principal, project_id: uuid.UUID, site_id: uuid.UUID | None = None
) -> ZoneAccessProfileList:
    project = projects.get_visible(db, p, project_id)
    stmt = select(Zone).where(Zone.project_id == project.id).order_by(Zone.code)
    if site_id:
        stmt = stmt.where(Zone.site_id == site_id)
    return ZoneAccessProfileList(items=[_read(db, ensure(db, z), z) for z in db.scalars(stmt)])


def _snapshot(prof: ZoneAccessProfile) -> dict[str, Any]:
    return {
        "required_inductions": list(prof.required_inductions or []),
        "airport_pass_area_code": prof.airport_pass_area_code,
        "access_permit_required": prof.access_permit_required,
        "adp_category_required": prof.adp_category_required,
        "avp_area_required": prof.avp_area_required,
        "escort_ratio_max": prof.escort_ratio_max,
        "lvp_withdrawal_required": prof.lvp_withdrawal_required,
        "ils_outage_notam_required": prof.ils_outage_notam_required,
        "hook_requirements": list(prof.hook_requirements or []),
    }


def loosening(what: str) -> ApiError:
    return ApiError(
        422,
        ErrorCode.PROFILE_LOOSENING,
        f"Profile changes may only tighten the zone's requirements ({what}). Change the zone's "
        "own attributes to loosen them.",
        "يسمح فقط بتشديد متطلبات المنطقة. لتخفيفها يجب تعديل خصائص المنطقة نفسها.",
    )


def update(
    db: Session, p: Principal, zone_id: uuid.UUID, body: ZoneAccessProfileUpdate
) -> ZoneAccessProfileRead:
    zone, project = _zone(db, p, zone_id)
    p.require(project.id, Capability.zone_profile_edit)
    g = p.grant(project.id, Capability.zone_profile_edit)
    if g is not None and not g.covers_site(zone.site_id):
        raise forbidden_error("This zone is outside your scope.")
    prof = ensure(db, zone)
    before = _snapshot(prof)
    ch = body.changes()
    d = defaults(db, zone)
    s = common.settings(db, project.id)
    if "required_inductions" in ch:
        codes = list(dict.fromkeys(ch["required_inductions"]))
        courses = {
            c.code: c
            for c in db.scalars(
                select(InductionCourse).where(InductionCourse.project_id == project.id)
            )
        }
        for c in codes:
            if c not in courses:
                raise validation_error("required_inductions", f"Unknown course {c}.")
        missing = [c for c in d["required_inductions"] if c not in codes]
        if missing:
            raise loosening(f"{', '.join(missing)} is required by the zone")
        if zone.zone_type == ZoneType.airside:
            for c in codes:
                course = courses[c]
                if (
                    course.induction_type == InductionType.zone_specific
                    and InductionDelivererRole.contractor_hse_rep.value
                    in (course.delivered_by_roles or [])
                ):
                    raise ApiError(
                        422,
                        ErrorCode.DELIVERER_NOT_ALLOWED,
                        f"{c} lists Contractor HSE Reps as deliverers and cannot be used on an "
                        "airside zone (IN-3).",
                        "لا يسمح بتقديم هذه الدورة من ممثل المقاول في منطقة جوية.",
                    )
        prof.required_inductions = codes
    if "access_permit_required" in ch:
        if not ch["access_permit_required"] and d["access_permit_required"]:
            raise loosening("work-area permit required on a movement-area / SRA zone")
        prof.access_permit_required = ch["access_permit_required"]
    if "airport_pass_area_code" in ch:
        code = ch["airport_pass_area_code"]
        if code is None and zone.security_restricted_area and d["airport_pass_area_code"]:
            raise loosening("airport pass area required on an SRA zone")
        if code is not None and not db.scalar(
            select(PassArea.id).where(PassArea.project_id == project.id, PassArea.code == code)
        ):
            raise validation_error("airport_pass_area_code", f"Unknown area code {code}.")
        prof.airport_pass_area_code = code
    for key in ("adp_category_required", "avp_area_required"):
        if key in ch:
            new, dflt = ch[key], d[key]
            if dflt is not None and (new is None or not covers(new, dflt)):
                raise loosening(f"{key} below {dflt}")
            setattr(prof, key, new)
    if "escort_ratio_max" in ch:
        new = ch["escort_ratio_max"]
        limit = setting_ratio(s, area_category(zone))
        if new is None and d["escort_ratio_max"] is not None:
            raise loosening("escort ratio required")
        if new is not None and new > limit:
            raise loosening(f"escort ratio above the setting ({limit})")
        prof.escort_ratio_max = new
    for key in ("lvp_withdrawal_required", "ils_outage_notam_required"):
        if key in ch:
            if not ch[key] and d[key]:
                raise loosening(key)
            setattr(prof, key, ch[key])
    if "hook_requirements" in ch:
        from app.services.cert import settings as cset  # noqa: PLC0415

        for h in ch["hook_requirements"]:
            if str(getattr(h["kind"], "value", h["kind"])) == "training_course":
                cset.require_not_cert_type(db, h["code"], "hook_requirements")
        prof.hook_requirements = [
            {"kind": h["kind"].value if hasattr(h["kind"], "value") else h["kind"],
             "code": h["code"],
             "trades": [str(getattr(t, "value", t)) for t in h.get("trades") or []]}
            for h in ch["hook_requirements"]
        ]  # fmt: skip
    prof.updated_at = now()
    prof.updated_by_user_id = p.user.id
    db.flush()
    bf, af = audit.diff(before, _snapshot(prof))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(project.id),
            entity_type=EntityType.zone_access_profile,
            entity_id=zone.id,
            project_id=project.id,
            before=bf,
            after=af,
        )
    return _read(db, prof, zone)
