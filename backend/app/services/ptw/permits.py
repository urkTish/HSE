# ruff: noqa: E501
"""Permit register and form (spec 3-ptw §3.5-§3.7, PT-2…PT-13, PT-18, CL-4): create, edit,
delete, copy, list; crew, equipment and document lines; type sections with their save-time
rules (HW-2, HW-6, HW-7, HW-9, CS-1, CS-4, WH-4, WH-6, EX-2, EX-4, EX-5, EL-3, LF-3, LF-7,
RG-3, AW-6); the pre-issue and closure checklists."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import (
    AuditAction,
    Capability,
    ContractorStatus,
    EntityType,
    Role,
    SiteStatus,
    ZoneType,
)
from app.core.errors import ApiError, ErrorCode, field_error, not_found, validation_error
from app.core.ptw_enums import (
    KEY_CREW_ROLES,
    PERMIT_TERMINAL,
    ChecklistAnswer,
    ChecklistKind,
    CrewLineStatus,
    DocumentType,
    EquipmentCategory,
    EquipmentUse,
    HazardousAreaClass,
    PermitBlocker,
    PermitRegisterSort,
    PermitStatus,
    PermitType,
    PreIssueItem,
    PtwCrewRole,
    StatusReason,
    VoltageClass,
)
from app.models import (
    GasDetector,
    IsolationCertificate,
    Jsa,
    ObstacleClearance,
    Permit,
    PermitCrew,
    PermitDocument,
    PermitEquipment,
    PermitRecord,
    PermitShift,
    PermitSignature,
    Site,
    Vehicle,
    Wap,
    Worker,
)
from app.schemas.common import Page
from app.schemas.jsa import JsaInstanceCreate
from app.schemas.permits import (
    ChecklistInput,
    ChecklistRead,
    PermitCopyInput,
    PermitCreate,
    PermitCrewInput,
    PermitCrewRead,
    PermitCrewUpdate,
    PermitDocumentInput,
    PermitDocumentRead,
    PermitEquipmentInput,
    PermitEquipmentRead,
    PermitListItem,
    PermitRead,
    PermitUpdate,
    SectionsInput,
)
from app.services import audit, projects
from app.services.access import common as acommon
from app.services.common import paginate
from app.services.hse_common import Refs, id_warnings, make_ref, next_seq, user_roles
from app.services.permissions import Principal, forbidden_error
from app.services.ptw import checks, common, evaluation, lifecycle, rules, views
from app.services.ptw import facts as facts_mod
from app.services.ptw import reference as ref

C = Capability
T = PermitType
S = PermitStatus
R = PtwCrewRole
B = PermitBlocker

KEY_FIELDS = {
    "zone_ids",
    "location_desc",
    "grid_x_m",
    "grid_y_m",
    "level_code",
    "elevation_m",
    "work_types",
    "primary_type",
    "windows",
    "valid_from_at",
    "valid_to_at",
    "receiver_user_id",
    "engagement_id",
}
EDITABLE = (S.draft, S.requested, S.reviewed, S.approved, S.issued, S.suspended, S.active)
HOT_WORK_RUNTIME = ("hot_work_ended_at", "fire_watch_until")
PLAN_DOCS = {
    DocumentType.lift_plan,
    DocumentType.critical_lift_plan,
    DocumentType.rescue_plan,
    DocumentType.pe_design,
}
SLOPE_MIN = {
    "type_c": Decimal("1.50"),
    "type_b": Decimal("1.00"),
    "type_a": Decimal("0.75"),
    "rock": Decimal("0"),
}
CRANES = {EquipmentCategory.mobile_crane, EquipmentCategory.crawler_crane}


def _audit(
    db: Session,
    p: Principal,
    permit: Permit,
    action: AuditAction,
    before: Any,
    after: Any,
    details: Any = None,
) -> None:
    audit.record(
        db,
        action,
        p.actor(permit.project_id),
        entity_type=EntityType.permit,
        entity_id=permit.id,
        project_id=permit.project_id,
        before=before,
        after=after,
        details=details,
    )


def read_only(permit: Permit) -> Any:
    return common.err(
        ErrorCode.PERMIT_READ_ONLY,
        f"{permit.permit_no} is {permit.status.value}: this part of the permit can no longer be changed.",
        f"التصريح {permit.permit_no} في حالة لا تسمح بهذا التعديل.",
        status=409,
    )


def _prep(p: Principal, permit: Permit) -> None:
    """Capability 83 (preparer / receiver) or 87 (issuer conditions) in scope."""
    pid = permit.project_id
    if p.grant(pid, C.permit_prepare) is not None:
        acommon.require_cap(p, pid, C.permit_prepare, [permit.site_id], permit.engagement_id)
    else:
        acommon.require_cap(p, pid, C.permit_issue, [permit.site_id], None)


def _refresh(db: Session, permit: Permit) -> None:
    evaluation.refresh(db, permit, run_simops=permit.status != S.draft)


def _get(db: Session, p: Principal, permit_id: uuid.UUID) -> Permit:
    return common.get_permit(db, p, permit_id)


# ---- section rules (save time) -------------------------------------------------------------------


def _bad(field: str, msg: str) -> Any:
    return validation_error(field, msg)


def validate_section(
    db: Session, permit: Permit, t: str, sec: dict[str, Any], f: facts_mod.Facts, i: int = 0
) -> None:
    s = f.settings
    fld = f"sections.{i}"
    d = rules.dec
    if t == T.hot_work.value:
        for z in f.zone_facts:
            if z.hazardous in (HazardousAreaClass.zone_0, HazardousAreaClass.zone_1):
                raise common.err(
                    ErrorCode.HAZARDOUS_AREA_PROHIBITED,
                    f"Hot work is prohibited in {z.hazardous.value} hazardous areas ({z.code}, HW-9).",
                    f"العمل الساخن محظور في المناطق الخطرة {z.hazardous.value} ({z.code}).",
                    field=fld,
                )
        radius = d(sec.get("combustibles_cleared_radius_m")) or Decimal(0)
        if radius < s.hw_combustible_clearance_m and not sec.get("combustibles_protected_method"):
            raise _bad(
                f"{fld}.combustibles_cleared_radius_m",
                f"Clear combustibles to ≥ {s.hw_combustible_clearance_m} m or give the protection method (HW-2).",
            )
        ext = sec.get("fire_extinguishers") or []
        if not any(
            (d(e.get("distance_m")) or Decimal(999)) <= s.hw_extinguisher_max_m for e in ext
        ):
            raise _bad(
                f"{fld}.fire_extinguishers",
                f"At least one extinguisher within {s.hw_extinguisher_max_m} m (HW-2).",
            )
        if not sec.get("fire_blanket"):
            raise _bad(f"{fld}.fire_blanket", "A fire blanket is required (HW-2).")
        if (d(sec.get("work_height_above_floor_m")) or Decimal(0)) > 0 and sec.get(
            "openings_below_protected"
        ) != "yes":
            raise _bad(
                f"{fld}.openings_below_protected",
                "Work above floor level needs openings below protected (HW-6).",
            )
        if sec.get("cylinders") == "oxy_fuel" and not sec.get("flashback_arrestors_both_ends"):
            raise _bad(
                f"{fld}.flashback_arrestors_both_ends",
                "Oxy-fuel needs flashback arrestors at both ends (HW-7).",
            )
        if sec.get("fire_system_impairment") and not sec.get("impairment_hours_24h"):
            raise _bad(f"{fld}.impairment_hours_24h", "Give the impairment hours in 24 h (HW-8).")
    elif t == T.confined_space.value:
        if (
            sec.get("ventilation") == "none_justified"
            and len((sec.get("ventilation_justification") or "").strip()) < 30
        ):
            raise _bad(
                f"{fld}.ventilation_justification",
                "No ventilation needs a justification of at least 30 characters (CS-4).",
            )
        if sec.get("rescue_method") == "external_rescue_service":
            m = sec.get("rescue_response_minutes")
            if m is None or int(m) > s.cse_rescue_max_minutes:
                raise _bad(
                    f"{fld}.rescue_response_minutes",
                    f"External rescue needs a documented response ≤ {s.cse_rescue_max_minutes} min (CS-1).",
                )
        if not sec.get("rescue_equipment_checked"):
            raise _bad(
                f"{fld}.rescue_equipment_checked", "Rescue equipment must be checked (CS-1)."
            )
        det = db.get(GasDetector, uuid.UUID(str(sec["continuous_monitor_detector_id"])))
        if det is None or det.project_id != permit.project_id:
            raise _bad(
                f"{fld}.continuous_monitor_detector_id", "Gas detector not found on this project."
            )
    elif t == T.work_at_height.value:
        fp = sec.get("fall_protection")
        arrest = fp in ("arrest_lanyard", "arrest_srl", "rope_access_two_rope")
        if arrest:
            kn = d(sec.get("anchor_rating_kn"))
            if (kn is None or kn < Decimal("22.2")) and not sec.get("engineered_anchor_cert_ref"):
                raise _bad(
                    f"{fld}.anchor_rating_kn",
                    "Anchors must be rated ≥ 22.2 kN per person or a certified engineered system (WH-4).",
                )
        if fp == "arrest_lanyard" and sec.get("lanyard_length_m") is None:
            raise _bad(f"{fld}.lanyard_length_m", "Give the lanyard length (WH-5).")
        if fp == "arrest_srl" and sec.get("srl_required_clearance_m") is None:
            raise _bad(
                f"{fld}.srl_required_clearance_m", "Give the SRL's required clearance (WH-5)."
            )
        if fp in ("arrest_lanyard", "arrest_srl") and sec.get("available_clearance_m") is None:
            raise _bad(
                f"{fld}.available_clearance_m",
                "Give the clearance available below the work point (WH-5).",
            )
        if "scaffold" in (sec.get("access_method") or []) and not sec.get("scaffold_tag_ref"):
            raise _bad(
                f"{fld}.scaffold_tag_ref",
                "Scaffold access needs the scaffold tag reference (WH-6).",
            )
        if not sec.get("drop_zone_controlled"):
            raise _bad(f"{fld}.drop_zone_controlled", "The drop zone must be controlled.")
        if (d(sec.get("max_fall_height_m")) or Decimal(0)) > Decimal("6.0") and not sec.get(
            "tool_tethering"
        ):
            raise _bad(f"{fld}.tool_tethering", "Tool tethering is required above 6.0 m.")
    elif t == T.excavation.value:
        depth = d(sec.get("max_depth_m")) or Decimal(0)
        ps = sec.get("protective_system")
        if depth >= s.ex_protective_system_depth_m and ps == "none_lt_1_2m":
            raise _bad(
                f"{fld}.protective_system",
                f"Depth ≥ {s.ex_protective_system_depth_m} m needs a protective system (EX-2).",
            )
        if ps == "sloping":
            ratio = d(sec.get("slope_ratio_h_v"))
            need = SLOPE_MIN.get(str(sec.get("soil_type") or "type_c"), Decimal("1.50"))
            if ratio is None or ratio < need:
                raise _bad(
                    f"{fld}.slope_ratio_h_v",
                    f"Sloping on {sec.get('soil_type')} needs a ratio ≥ {need} : 1 (EX-2).",
                )
        if depth >= s.ex_pe_design_depth_m and (
            ps != "engineered_design" or not sec.get("pe_design_ref")
        ):
            raise _bad(
                f"{fld}.protective_system",
                f"Depth ≥ {s.ex_pe_design_depth_m} m needs an engineered design with its reference (EX-2).",
            )
        if sec.get("services_within_hand_dig_zone") and sec.get("method") not in (
            "hand_dig",
            "vacuum",
        ):
            raise common.err(
                ErrorCode.MECHANICAL_NEAR_SERVICE,
                f"Within {s.ex_hand_dig_distance_m} m of a located service dig by hand or vacuum (EX-4).",
                "ضمن مسافة الحفر اليدوي من الخدمات المدفونة يجب الحفر يدوياً أو بالشفط.",
                field=f"{fld}.method",
            )
        if (d(sec.get("spoil_setback_m")) or Decimal(0)) < s.ex_spoil_setback_m:
            raise _bad(
                f"{fld}.spoil_setback_m",
                f"Spoil must be ≥ {s.ex_spoil_setback_m} m from the edge (EX-5).",
            )
        travel = d(sec.get("egress_travel_m"))
        if (
            depth >= s.ex_protective_system_depth_m
            and travel is not None
            and travel > s.ex_egress_max_m
        ):
            raise _bad(
                f"{fld}.egress_travel_m",
                f"Egress within {s.ex_egress_max_m} m lateral travel (EX-5).",
            )
    elif t == T.electrical_isolation.value:
        vc = rules.voltage_class(int(sec.get("system_voltage_v") or 0), bool(sec.get("dc")))
        if sec.get("work_condition") == "energized":
            if vc == VoltageClass.hv:
                raise common.err(
                    ErrorCode.ENERGIZED_HV_PROHIBITED,
                    "Energized work on high voltage is prohibited (EL-3).",
                    "العمل المكهرب على الجهد العالي محظور.",
                    field=f"{fld}.work_condition",
                )
            if not sec.get("energized_justification"):
                raise _bad(
                    f"{fld}.energized_justification", "Energized work needs a justification (EL-3)."
                )
            if sec.get("limited_approach_m") is None or sec.get("restricted_approach_m") is None:
                raise _bad(f"{fld}.limited_approach_m", "Give the approach boundaries (EL-3).")
            ie = d(sec.get("incident_energy_cal_cm2"))
            if ie is None and sec.get("arc_ppe_category") is None:
                raise _bad(
                    f"{fld}.incident_energy_cal_cm2",
                    "Give the incident energy or the arc PPE category (EL-3).",
                )
            rating = d(sec.get("arc_ppe_rating_cal_cm2"))
            if ie is not None and (rating is None or rating < ie):
                raise _bad(
                    f"{fld}.arc_ppe_rating_cal_cm2",
                    "Arc-rated PPE must be ≥ the incident energy (EL-3).",
                )
        if vc == VoltageClass.hv:
            if (
                sec.get("work_condition", "electrically_safe") == "electrically_safe"
                and sec.get("hv_earths_applied") is False
            ):
                raise _bad(f"{fld}.hv_earths_applied", "HV work needs earths applied (EL-1).")
            if not sec.get("switching_programme_ref"):
                raise _bad(
                    f"{fld}.switching_programme_ref",
                    "HV work needs a switching programme reference (IS-10).",
                )
    elif t == T.lifting.value:
        lift = rules.lift(sec, f.zone_facts, s.critical_lift_capacity_pct, s.critical_lift_weight_t)
        if lift.capacity_pct > 100:
            raise common.err(
                ErrorCode.CAPACITY_EXCEEDED,
                f"The lift is at {lift.capacity_display} % of rated capacity (> 100 %, LF-3).",
                f"الرفع بنسبة {lift.capacity_display} % من الحمولة المقررة (أكثر من 100 %).",
                field=f"{fld}.rated_capacity_t",
                meta={"capacity_pct": str(lift.capacity_display)},
            )
        if sec.get("personnel_lift"):
            if len((sec.get("personnel_lift_justification") or "").strip()) < 10:
                raise _bad(
                    f"{fld}.personnel_lift_justification",
                    "Personnel lifts need a justification (LF-7).",
                )
            if lift.capacity_pct > 50:
                raise _bad(
                    f"{fld}.rated_capacity_t",
                    "Personnel lifts are limited to 50 % of capacity (LF-7).",
                )
            wl = d(sec.get("wind_limit_ms"))
            if wl is not None and wl > s.man_basket_wind_limit_ms:
                raise _bad(
                    f"{fld}.wind_limit_ms",
                    f"Personnel lifts: wind limit ≤ {s.man_basket_wind_limit_ms} m/s (LF-7).",
                )
        lines = {e.id: e for e in evaluation.equipment_lines(db, permit.id)}
        for j, eid in enumerate(sec.get("appliance_equipment_ids") or []):
            e = lines.get(uuid.UUID(str(eid)))
            if e is None or e.use != EquipmentUse.lifting_appliance:
                raise _bad(
                    f"{fld}.appliance_equipment_ids.{j}",
                    "Not a lifting-appliance equipment line of this permit.",
                )
            if e.category in CRANES and sec.get("ground_bearing_checked") is False:
                raise _bad(
                    f"{fld}.ground_bearing_checked",
                    "Mobile and crawler cranes need the ground bearing checked.",
                )
    elif t == T.radiography.value:
        src = sec.get("source_type")
        if src == "x_ray" and not sec.get("xray_dose_rate_1m_usv_h"):
            raise _bad(f"{fld}.xray_dose_rate_1m_usv_h", "X-ray sets need the dose rate at 1 m.")
        if src != "x_ray" and not sec.get("activity_gbq"):
            raise _bad(f"{fld}.activity_gbq", "Isotope sources need the activity (GBq).")
        computed = rules.barrier_m(sec, s.rg_barrier_limit_usv_h)
        if (d(sec.get("planned_barrier_m")) or Decimal(0)) < computed:
            raise common.err(
                ErrorCode.BARRIER_TOO_SMALL,
                f"The planned barrier must be ≥ the computed {computed} m (RG-3).",
                f"يجب أن تكون مسافة الحاجز ≥ {computed} م المحسوبة.",
                field=f"{fld}.planned_barrier_m",
                meta={"computed_barrier_m": str(computed)},
            )
        if not sec.get("dosimetry_confirmed"):
            raise _bad(
                f"{fld}.dosimetry_confirmed",
                "Confirm personal dosimetry for each radiographer (RG-6).",
            )
    elif t == T.airside_works.value:
        if any(z.fod_control_required for z in f.zone_facts) and not sec.get("fod_control_plan"):
            raise _bad(f"{fld}.fod_control_plan", "A FOD control plan is required in this zone.")
        wid = sec.get("wap_id")
        if wid:
            w = db.get(Wap, uuid.UUID(str(wid)))
            if w is None or w.project_id != permit.project_id:
                raise _bad(f"{fld}.wap_id", "WAP not found on this project.")


def aw6(db: Session, permit: Permit, f: facts_mod.Facts) -> None:
    """AW-6: hot work on an apron zone: no live stand adjacent, separation from hydrant pits."""
    if not (f.has(T.hot_work) and f.has(T.airside_works)):
        return
    aw = f.sec(T.airside_works)
    if not aw:
        return
    aprons = [
        z
        for z in f.zones
        if z.zone_type == ZoneType.airside
        and z.airside_area is not None
        and z.airside_area.value == "apron"
    ]
    if not aprons:
        return
    if aw.get("aircraft_proximity") == "live_stand_adjacent":
        raise common.err(
            ErrorCode.AIRCRAFT_PROXIMITY,
            "Hot work on an apron needs the stand closed or no stand in the zone (AW-6).",
            "العمل الساخن على ساحة الطائرات يتطلب إغلاق الموقف أو عدم وجود موقف في المنطقة.",
            field="sections",
        )
    dist = rules.dec(aw.get("hydrant_pit_distance_m"))
    if dist is not None and dist < f.settings.airside_hotwork_separation_m:
        raise common.err(
            ErrorCode.AIRCRAFT_PROXIMITY,
            f"Hot work must be ≥ {f.settings.airside_hotwork_separation_m} m from hydrant pits and fuelling vehicles (AW-6).",
            "يجب أن يبعد العمل الساخن عن فتحات الوقود ومركبات التزويد المسافة المحددة.",
            field="sections",
        )


def _store_section(permit: Permit, t: str, data: dict[str, Any]) -> None:
    secs = dict(permit.sections or {})
    old = secs.get(t) or {}
    if t == T.hot_work.value:
        for k in HOT_WORK_RUNTIME:
            if old.get(k):
                data[k] = old[k]
    secs[t] = data
    permit.sections = secs


def apply_sections(
    db: Session, permit: Permit, sections: list[Any], creating: bool = False
) -> None:
    seen: set[str] = set()
    for sec in sections:
        t = sec.work_type
        if t not in permit.work_types:
            raise validation_error("sections", f"{t} is not one of the permit's work types.")
        if t in seen:
            raise validation_error("sections", f"{t} is given twice.")
        seen.add(t)
        data = sec.model_dump(mode="json")
        if t == T.lifting.value and creating:
            ids = {
                str(e.id)
                for e in evaluation.equipment_lines(db, permit.id)
                if e.use == EquipmentUse.lifting_appliance
            }
            if not all(i in ids for i in data.get("appliance_equipment_ids") or []):
                data["appliance_equipment_ids"] = sorted(ids) or data.get("appliance_equipment_ids")
        _store_section(permit, t, data)
    db.flush()
    f = facts_mod.compute(db, permit)
    for i, sec in enumerate(sections):
        validate_section(db, permit, sec.work_type, f.sections[sec.work_type], f, i)
    aw6(db, permit, f)


# ---- links --------------------------------------------------------------------------------------


def _check_links(
    db: Session,
    project_id: uuid.UUID,
    wap_ids: list[uuid.UUID],
    obs_ids: list[uuid.UUID],
    iso_ids: list[uuid.UUID],
) -> None:
    for i, x in enumerate(wap_ids):
        w = db.get(Wap, x)
        if w is None or w.project_id != project_id:
            raise validation_error(f"linked_wap_ids.{i}", "WAP not found on this project.")
    for i, x in enumerate(obs_ids):
        o = db.get(ObstacleClearance, x)
        if o is None or o.project_id != project_id:
            raise validation_error(
                f"linked_obs_ids.{i}", "Obstacle clearance not found on this project."
            )
    for i, x in enumerate(iso_ids):
        c = db.get(IsolationCertificate, x)
        if c is None or c.project_id != project_id:
            raise validation_error(
                f"isolation_cert_ids.{i}", "Isolation certificate not found on this project."
            )


def _grid(permit: Permit) -> None:
    if (permit.grid_x_m is None) != (permit.grid_y_m is None):
        raise validation_error("grid_x_m", "Give both grid coordinates or neither.")
    if permit.level_code and permit.elevation_m is None:
        raise validation_error("elevation_m", "Give the elevation with the level code.")


def _types(permit: Permit, zones: list[Any]) -> None:
    types = list(dict.fromkeys(permit.work_types or []))
    if any(z.zone_type == ZoneType.airside for z in zones) and T.airside_works.value not in types:
        types.append(T.airside_works.value)
    permit.work_types = types
    if permit.primary_type.value not in types:
        raise validation_error("primary_type", "The primary type must be one of the work types.")


def _contractor(db: Session, engagement_id: uuid.UUID) -> None:
    con = acommon.engagement_contractor(db, engagement_id)
    if con is None:
        return
    if con.status in (ContractorStatus.suspended, ContractorStatus.blacklisted):
        lifecycle.contractor_status_ok(con)
    if con.status != ContractorStatus.approved:
        raise common.err(
            ErrorCode.CONTRACTOR_NOT_APPROVED,
            f"{con.short_code} is not an approved contractor.",
            "المقاول غير معتمد.",
            field="engagement_id",
        )


def _validate_people(db: Session, permit: Permit) -> None:
    checks.people_sod(db, permit)
    if permit.supervisor_worker_id:
        sup = [
            x
            for x in evaluation.crew_lines(db, permit.id)
            if x.worker_id == permit.supervisor_worker_id and x.crew_role == R.supervisor
        ]
        if not sup:
            raise validation_error(
                "supervisor_worker_id",
                "The supervisor must be a crew member with the role supervisor.",
            )


def _save_checks(db: Session, permit: Permit) -> None:
    db.flush()
    f = facts_mod.compute(db, permit)
    checks.validity_ok(db, permit, f)
    checks.midday_window_ok(db, permit, f)
    checks.wap_window_ok(db, permit, f)


# ---- create -------------------------------------------------------------------------------------


def next_permit_no(db: Session, project_id: uuid.UUID, at: datetime) -> tuple[int, int, str]:
    year = acommon.local_day(at).year
    seq = next_seq(db, Permit, project_id, year)
    return year, seq, make_ref("PTW", common.project_code(db, project_id), year, seq, 4)


def create(db: Session, p: Principal, project_id: uuid.UUID, body: PermitCreate) -> PermitRead:
    project = projects.get_visible(db, p, project_id)
    acommon.require_cap(p, project_id, C.permit_prepare, [body.site_id], body.engagement_id)
    from app.services.common import ensure_open  # noqa: PLC0415
    from app.services.hse_common import check_engagement  # noqa: PLC0415

    ensure_open(project)
    site = db.get(Site, body.site_id)
    if site is None or site.project_id != project_id:
        raise validation_error("site_id", "The site does not belong to this project.")
    if site.status != SiteStatus.active:
        raise common.err(
            ErrorCode.SITE_INACTIVE, "The site is inactive.", "الموقع غير نشط.", field="site_id"
        )
    check_engagement(db, project, body.engagement_id)
    _contractor(db, body.engagement_id)
    zones = checks.zones_ok(db, project_id, body.site_id, list(body.zone_ids))
    at = now()
    year, seq, no = next_permit_no(db, project_id, at)
    prof = common.profile(db, zones[0])
    area = body.area_authority_user_id or (
        prof.default_area_authority_ids[0] if prof.default_area_authority_ids else None
    )
    permit = Permit(
        id=uuid.uuid4(),
        permit_no=no,
        year=year,
        seq=seq,
        project_id=project_id,
        site_id=body.site_id,
        zone_ids=list(body.zone_ids),
        location_desc=body.location_desc,
        grid_x_m=body.grid_x_m,
        grid_y_m=body.grid_y_m,
        level_code=body.level_code,
        elevation_m=body.elevation_m,
        engagement_id=body.engagement_id,
        work_types=[t.value for t in body.work_types],
        primary_type=body.primary_type,
        title=body.title,
        scope_en=body.scope_en,
        scope_ar=body.scope_ar,
        exposure=body.exposure or prof.default_exposure,
        flammables_in_use=body.flammables_in_use,
        combustion_engine_plant=body.combustion_engine_plant,
        valid_from_at=body.valid_from_at,
        valid_to_at=body.valid_to_at,
        windows=[w.model_dump(mode="json") for w in body.windows],
        receiver_user_id=body.receiver_user_id,
        area_authority_user_id=area,
        issuer_user_id=body.issuer_user_id,
        hse_reviewer_user_id=body.hse_reviewer_user_id,
        supervisor_worker_id=None,
        linked_wap_ids=list(body.linked_wap_ids),
        linked_obs_ids=list(body.linked_obs_ids),
        isolation_cert_ids=list(body.isolation_cert_ids),
        conditions_en=body.conditions_en,
        conditions_ar=body.conditions_ar,
        copied_conditions=[],
        emergency_info=body.emergency_info,
        sections={},
        checklists={},
        blockers=[],
        warnings=[],
        status=S.draft,
        alerts_sent=[],
        created_by_user_id=p.user.id,
        updated_by_user_id=p.user.id,
    )
    _types(permit, zones)
    _grid(permit)
    _check_links(
        db, project_id, permit.linked_wap_ids, permit.linked_obs_ids, permit.isolation_cert_ids
    )
    checks.receiver_ok(db, permit, permit.receiver_user_id)
    db.add(permit)
    db.flush()
    for i, c in enumerate(body.crew):
        _add_crew(db, p, permit, c, f"crew.{i}")
    if body.supervisor_worker_id:
        permit.supervisor_worker_id = body.supervisor_worker_id
    else:
        sup = [x for x in evaluation.crew_lines(db, permit.id) if x.crew_role == R.supervisor]
        permit.supervisor_worker_id = sup[0].worker_id if sup else None
    for i, e in enumerate(body.equipment):
        _add_equipment(db, permit, e, f"equipment.{i}")
    for d in body.documents:
        _add_document(db, p, permit, d)
    if body.sections:
        apply_sections(db, permit, list(body.sections), creating=True)
    _validate_people(db, permit)
    _save_checks(db, permit)
    if body.jsa_template_id:
        from app.services.ptw import jsa  # noqa: PLC0415

        jsa.create_instance(db, p, permit.id, JsaInstanceCreate(template_id=body.jsa_template_id))
    _audit(
        db,
        p,
        permit,
        AuditAction.create,
        None,
        {"permit_no": permit.permit_no, "work_types": permit.work_types},
    )
    _refresh(db, permit)
    warns = id_warnings(
        scope_en=body.scope_en,
        scope_ar=body.scope_ar,
        location_desc=body.location_desc,
        conditions_en=body.conditions_en,
        emergency_info=body.emergency_info,
    )
    return views.permit_read(db, p, permit, warns)


# ---- read / list ----------------------------------------------------------------------------------


def read(db: Session, p: Principal, permit_id: uuid.UUID) -> PermitRead:
    permit = _get(db, p, permit_id)
    if permit.status not in PERMIT_TERMINAL:
        evaluation.refresh(db, permit, run_simops=False, evaluate_crew=False, auto_suspend=False)
    return views.permit_read(db, p, permit)


def awaiting(db: Session, p: Principal, permit: Permit) -> bool:
    uid = p.user.id
    st = permit.status
    if st == S.draft:
        return uid == permit.receiver_user_id
    if st == S.requested:
        return uid == permit.area_authority_user_id
    if st == S.reviewed:
        if permit.high_risk and (permit.hse_review or {}).get("decision") != "accepted":
            return uid == permit.hse_reviewer_user_id or (
                permit.hse_reviewer_user_id is None
                and p.grant(permit.project_id, C.permit_hse_review) is not None
            )
        return uid == permit.issuer_user_id or (
            permit.issuer_user_id is None
            and Role.permit_issuer in user_roles(db, uid, permit.project_id)
        )
    if st == S.approved:
        return uid == permit.issuer_user_id
    if st == S.issued:
        return uid == permit.receiver_user_id
    if st == S.suspended:
        return uid == permit.issuer_user_id
    return False


def list_permits(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    *,
    statuses: list[PermitStatus] | None = None,
    work_types: list[PermitType] | None = None,
    site_id: uuid.UUID | None = None,
    zone_ids: list[uuid.UUID] | None = None,
    engagement_ids: list[uuid.UUID] | None = None,
    include_subcontractors: bool = True,
    issuer_user_id: uuid.UUID | None = None,
    receiver_user_id: uuid.UUID | None = None,
    worker_id: uuid.UUID | None = None,
    live_on: Any = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    status_reason: StatusReason | None = None,
    blocker: PermitBlocker | None = None,
    awaiting_me: bool = False,
    simops_open: bool | None = None,
    isolation_id: uuid.UUID | None = None,
    wap_id: uuid.UUID | None = None,
    q: str | None = None,
    sort: PermitRegisterSort = PermitRegisterSort.newest,
) -> Page[PermitListItem]:
    g = common.view_grant(db, p, project_id)
    stmt = select(Permit).where(Permit.project_id == project_id)
    if g.site_ids is not None:
        stmt = stmt.where(Permit.site_id.in_(list(g.site_ids)))
    if g.engagement_ids is not None:
        stmt = stmt.where(Permit.engagement_id.in_(list(g.engagement_ids)))
    if statuses:
        stmt = stmt.where(Permit.status.in_(statuses))
    if work_types:
        stmt = stmt.where(Permit.work_types.overlap([t.value for t in work_types]))
    if site_id:
        stmt = stmt.where(Permit.site_id == site_id)
    if zone_ids:
        stmt = stmt.where(Permit.zone_ids.overlap(list(zone_ids)))
    if engagement_ids:
        ids: set[uuid.UUID] = set(engagement_ids)
        if include_subcontractors:
            from app.services.permissions import engagement_descendants  # noqa: PLC0415

            for e in list(engagement_ids):
                ids |= engagement_descendants(db, e)
        stmt = stmt.where(Permit.engagement_id.in_(list(ids)))
    if issuer_user_id:
        stmt = stmt.where(Permit.issuer_user_id == issuer_user_id)
    if receiver_user_id:
        stmt = stmt.where(Permit.receiver_user_id == receiver_user_id)
    if worker_id:
        stmt = stmt.where(
            Permit.id.in_(
                select(PermitCrew.permit_id).where(
                    PermitCrew.worker_id == worker_id, PermitCrew.status != CrewLineStatus.removed
                )
            )
        )
    if live_on:
        lo = acommon.local_midnight_utc(live_on)
        stmt = stmt.where(Permit.valid_from_at < lo + timedelta(days=1), Permit.valid_to_at > lo)
    if valid_from:
        stmt = stmt.where(Permit.valid_to_at > valid_from)
    if valid_to:
        stmt = stmt.where(Permit.valid_from_at < valid_to)
    if status_reason:
        stmt = stmt.where(Permit.status_reason == status_reason)
    if blocker:
        stmt = stmt.where(Permit.blockers.contains([{"code": blocker.value}]))
    if isolation_id:
        stmt = stmt.where(Permit.isolation_cert_ids.contains([isolation_id]))
    if wap_id:
        stmt = stmt.where(Permit.linked_wap_ids.contains([wap_id]))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Permit.permit_no.ilike(like),
                Permit.title.ilike(like),
                Permit.location_desc.ilike(like),
            )
        )
    orders: dict[PermitRegisterSort, list[Any]] = {
        PermitRegisterSort.newest: [Permit.created_at.desc(), Permit.permit_no.desc()],
        PermitRegisterSort.valid_from: [Permit.valid_from_at.desc(), Permit.permit_no.desc()],
        PermitRegisterSort.valid_to: [Permit.valid_to_at.asc(), Permit.permit_no.asc()],
        PermitRegisterSort.permit_no: [Permit.permit_no.desc()],
    }
    order = orders[sort]
    stmt = stmt.order_by(*order)
    at = now()
    refs = Refs(db)
    if awaiting_me or simops_open is not None:
        rows = list(db.scalars(stmt))
        if awaiting_me:
            rows = [x for x in rows if awaiting(db, p, x)]
        items = [views.list_item(db, x, refs, at) for x in rows]
        if simops_open is not None:
            items = [i for i in items if (i.simops_open > 0) == simops_open]
        total = len(items)
        items = items[(page - 1) * page_size : page * page_size]
        return Page[PermitListItem](items=items, total=total, page=page, page_size=page_size)
    rows2, total = paginate(db, stmt, page, page_size)
    return Page[PermitListItem](
        items=[views.list_item(db, x, refs, at) for x in rows2],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---- update (PT-13) -------------------------------------------------------------------------------


def update(db: Session, p: Principal, permit_id: uuid.UUID, body: PermitUpdate) -> PermitRead:
    permit = _get(db, p, permit_id)
    _prep(p, permit)
    if permit.status in PERMIT_TERMINAL:
        raise read_only(permit)
    sent = body.model_fields_set
    changed: dict[str, Any] = {}
    before: dict[str, Any] = {}
    for name in sent:
        new = getattr(body, name)
        if name == "work_types" and new is not None:
            new = [t.value for t in new]
        if name == "windows" and new is not None:
            new = [w.model_dump(mode="json") for w in new]
        old = getattr(permit, name)
        if old != new:
            changed[name] = new
            before[name] = (
                acommon.jsonable({name: old})[name]
                if not isinstance(old, list)
                else [str(x) for x in old]
            )
    if not changed:
        return views.permit_read(db, p, permit)
    key = set(changed) & KEY_FIELDS
    if key and permit.status == S.active:
        raise read_only(permit)
    if permit.status != S.draft and set(changed) & {"receiver_user_id"}:
        lifecycle._receiver_only(p, permit, "changes are made by")
    for name, v in changed.items():
        setattr(permit, name, v)
    permit.updated_by_user_id = p.user.id
    zones = checks.zones_ok(db, permit.project_id, permit.site_id, list(permit.zone_ids or []))
    _types(permit, zones)
    _grid(permit)
    _check_links(
        db,
        permit.project_id,
        permit.linked_wap_ids or [],
        permit.linked_obs_ids or [],
        permit.isolation_cert_ids or [],
    )
    if "receiver_user_id" in changed:
        checks.receiver_ok(db, permit, permit.receiver_user_id)
    if "work_types" in changed:
        secs = {k: v for k, v in (permit.sections or {}).items() if k in permit.work_types}
        permit.sections = secs
    _validate_people(db, permit)
    _save_checks(db, permit)
    if permit.status in (S.draft, S.requested):
        pass
    elif key:
        lifecycle.back_to_requested(db, p, permit, "changed " + ", ".join(sorted(key)))
    _audit(
        db,
        p,
        permit,
        AuditAction.update,
        before,
        acommon.jsonable(
            {k: (v if not isinstance(v, list) else [str(x) for x in v]) for k, v in changed.items()}
        ),
    )
    _refresh(db, permit)
    warns = id_warnings(
        **{
            k: v
            for k, v in changed.items()
            if k
            in (
                "scope_en",
                "scope_ar",
                "location_desc",
                "conditions_en",
                "conditions_ar",
                "emergency_info",
            )
            and isinstance(v, str)
        }
    )
    return views.permit_read(db, p, permit, warns)


# ---- delete (PT-18) ------------------------------------------------------------------------------


def delete(db: Session, p: Principal, permit_id: uuid.UUID) -> None:
    permit = _get(db, p, permit_id)
    acommon.require_cap(
        p, permit.project_id, C.permit_prepare, [permit.site_id], permit.engagement_id
    )
    if permit.status != S.draft or permit.first_requested_at is not None:
        raise common.err(
            ErrorCode.INVALID_TRANSITION,
            "Only a Draft never requested can be deleted; cancel it instead (PT-18).",
            "يمكن حذف المسودة التي لم تُطلب فقط؛ استخدم الإلغاء.",
            status=409,
        )
    if permit.created_by_user_id != p.user.id:
        raise forbidden_error("Only the preparer deletes a Draft (PT-18).")
    if now() - permit.created_at > timedelta(days=7):
        raise common.err(
            ErrorCode.INVALID_TRANSITION,
            "Drafts may be deleted within 7 days of creation; cancel it instead (PT-18).",
            "يمكن حذف المسودة خلال 7 أيام فقط؛ استخدم الإلغاء.",
            status=409,
        )
    _audit(
        db, p, permit, AuditAction.archive, {"permit_no": permit.permit_no}, None, {"deleted": True}
    )
    for model in (PermitCrew, PermitEquipment, PermitDocument, PermitRecord, PermitSignature):
        for row in db.scalars(select(model).where(model.permit_id == permit.id)):
            db.delete(row)
    if permit.jsa_id:
        j = db.get(Jsa, permit.jsa_id)
        if j is not None:
            db.delete(j)
    db.flush()
    db.delete(permit)
    db.flush()


# ---- crew (§3.6) ---------------------------------------------------------------------------------


def _add_crew(
    db: Session, p: Principal, permit: Permit, body: PermitCrewInput, fld: str = "worker_id"
) -> PermitCrew:
    w = db.get(Worker, body.worker_id)
    if w is None:
        raise validation_error(
            f"{fld}.worker_id" if fld != "worker_id" else fld, "Worker not found."
        )
    if not checks.in_tree(db, permit, body.worker_id):
        raise common.err(
            ErrorCode.CREW_NOT_IN_TREE,
            f"{w.worker_no} is not deployed with this contractor or its parent (PT-7).",
            f"العامل {w.worker_no} لا يتبع المقاول المنفذ أو المقاول الرئيسي.",
            field=fld,
        )
    checks.crew_sod(db, permit, body.worker_id, body.crew_role)
    if permit.status in (S.issued, S.active, S.suspended):
        other = checks.busy_elsewhere(db, permit, body.worker_id, body.crew_role)
        if other:
            raise checks.busy_error(db, body.worker_id, body.crew_role, other)
    if body.crew_role in ref.ROLE_APPOINTMENT and body.appointment_id is None:
        raise validation_error(
            f"{fld}.appointment_id" if fld != "worker_id" else "appointment_id",
            f"{body.crew_role.value} needs the person's appointment (PR-4).",
        )
    if body.escort_worker_id and db.get(Worker, body.escort_worker_id) is None:
        raise validation_error("escort_worker_id", "Escort worker not found.")
    line = PermitCrew(
        id=uuid.uuid4(),
        permit_id=permit.id,
        worker_id=body.worker_id,
        crew_role=body.crew_role,
        appointment_id=body.appointment_id,
        escort_worker_id=body.escort_worker_id,
        status=CrewLineStatus.listed,
        eligibility=[],
    )
    db.add(line)
    db.flush()
    return line


def _crew_writable(p: Principal, permit: Permit) -> None:
    acommon.require_cap(
        p, permit.project_id, C.permit_prepare, [permit.site_id], permit.engagement_id
    )
    if permit.status in PERMIT_TERMINAL:
        raise read_only(permit)


def add_crew(
    db: Session, p: Principal, permit_id: uuid.UUID, body: PermitCrewInput
) -> PermitCrewRead:
    permit = _get(db, p, permit_id)
    _crew_writable(p, permit)
    line = _add_crew(db, p, permit, body)
    if body.crew_role == R.supervisor and permit.supervisor_worker_id is None:
        permit.supervisor_worker_id = body.worker_id
    key = body.crew_role in KEY_CREW_ROLES
    _audit(
        db,
        p,
        permit,
        AuditAction.update,
        None,
        {"crew_added": {"worker_id": str(body.worker_id), "role": body.crew_role.value}},
    )
    if key and permit.status in (S.approved, S.issued):
        lifecycle.back_to_requested(db, p, permit, f"key crew role {body.crew_role.value} added")
    _refresh(db, permit)
    db.refresh(line)
    return views.crew_read(db, p, line, evaluation.current_shift(db, permit))


def _line(db: Session, permit: Permit, line_id: uuid.UUID) -> PermitCrew:
    line = db.get(PermitCrew, line_id)
    if line is None or line.permit_id != permit.id:
        raise not_found("Crew line")
    return line


def update_crew(
    db: Session, p: Principal, permit_id: uuid.UUID, line_id: uuid.UUID, body: PermitCrewUpdate
) -> PermitCrewRead:
    permit = _get(db, p, permit_id)
    _crew_writable(p, permit)
    line = _line(db, permit, line_id)
    if line.status == CrewLineStatus.removed:
        raise read_only(permit)
    sent = body.model_fields_set
    before = {"crew_role": line.crew_role.value}
    role_change = (
        "crew_role" in sent and body.crew_role is not None and body.crew_role != line.crew_role
    )
    if role_change:
        assert body.crew_role is not None  # noqa: S101
        key = body.crew_role in KEY_CREW_ROLES or line.crew_role in KEY_CREW_ROLES
        if key and permit.status == S.active:
            raise read_only(permit)
        checks.crew_sod(db, permit, line.worker_id, body.crew_role, skip_line=line.id)
        if permit.status in (S.issued, S.active, S.suspended):
            other = checks.busy_elsewhere(db, permit, line.worker_id, body.crew_role)
            if other:
                raise checks.busy_error(db, line.worker_id, body.crew_role, other)
        line.crew_role = body.crew_role
    if "appointment_id" in sent:
        line.appointment_id = body.appointment_id
    if "escort_worker_id" in sent:
        line.escort_worker_id = body.escort_worker_id
    if line.crew_role in ref.ROLE_APPOINTMENT and line.appointment_id is None:
        raise validation_error(
            "appointment_id", f"{line.crew_role.value} needs the person's appointment (PR-4)."
        )
    line.eligible = None if permit.status == S.draft else line.eligible
    db.flush()
    _audit(
        db,
        p,
        permit,
        AuditAction.update,
        {"crew": before},
        {"crew": {"line": str(line.id), "crew_role": line.crew_role.value}},
    )
    if (
        role_change
        and permit.status in (S.approved, S.issued)
        and (
            line.crew_role in KEY_CREW_ROLES
            or before["crew_role"] in {r.value for r in KEY_CREW_ROLES}
        )
    ):
        lifecycle.back_to_requested(db, p, permit, "key crew role changed")
    _refresh(db, permit)
    db.refresh(line)
    return views.crew_read(db, p, line, evaluation.current_shift(db, permit))


def delete_crew(db: Session, p: Principal, permit_id: uuid.UUID, line_id: uuid.UUID) -> None:
    permit = _get(db, p, permit_id)
    _crew_writable(p, permit)
    line = _line(db, permit, line_id)
    if any(r.worker_id == line.worker_id for r in lifecycle.persons_inside(db, permit.id)):
        lifecycle.entrants_inside_error(db, permit)
    key = line.crew_role in KEY_CREW_ROLES
    if permit.status in (S.issued, S.active, S.suspended):
        line.status = CrewLineStatus.removed
        line.removed_at = now()
    else:
        db.delete(line)
    if permit.supervisor_worker_id == line.worker_id and line.crew_role == R.supervisor:
        permit.supervisor_worker_id = None
    db.flush()
    _audit(db, p, permit, AuditAction.update, {"crew_removed": str(line.worker_id)}, None)
    if key and permit.status in (S.approved, S.issued):
        lifecycle.back_to_requested(db, p, permit, "key crew member removed")
    _refresh(db, permit)


# ---- equipment ------------------------------------------------------------------------------------


def _add_equipment(
    db: Session, permit: Permit, body: PermitEquipmentInput, fld: str = "equipment"
) -> PermitEquipment:
    if (body.vehicle_id is None) == (body.equipment_tag is None):
        raise validation_error(fld, "Give either vehicle_id or equipment_tag.")
    e = PermitEquipment(
        id=uuid.uuid4(),
        permit_id=permit.id,
        use=body.use,
        hooks=[],
        operator_hooks=[],
        conditions=[],
    )
    if body.vehicle_id is not None:
        v = db.get(Vehicle, body.vehicle_id)
        tree = acommon.engagement_ancestors(db, permit.engagement_id)
        if v is None or v.project_id != permit.project_id or v.engagement_id not in tree:
            raise validation_error(
                f"{fld}.vehicle_id", "Vehicle not registered for this contractor or its parent."
            )
        e.vehicle_id = v.id
    else:
        tag = body.equipment_tag
        assert tag is not None  # noqa: S101
        e.category = tag.category
        e.tag = tag.tag
        e.description = tag.description
        e.max_working_height_m = tag.max_working_height_m
    _bind_phase4(db, permit, e, body, fld)
    db.add(e)
    db.flush()
    return e


def _bind_phase4(
    db: Session, permit: Permit, e: PermitEquipment, body: PermitEquipmentInput, fld: str
) -> None:
    """3-ptw v1.1 §11.4 item 1 (4-third-party-cert HK4-9): the Phase 4 item (given or resolved
    from the tag) and the operator, required for categories with an EQC operator code once
    Phase 4 is enabled on the project (422 OPERATOR_REQUIRED)."""
    from app.models import EquipmentItem  # noqa: PLC0415
    from app.services.cert import policy as cpolicy  # noqa: PLC0415

    if body.equipment_item_id is not None:
        if db.get(EquipmentItem, body.equipment_item_id) is None:
            raise validation_error(f"{fld}.equipment_item_id", "Equipment item not found.")
        e.equipment_item_id = body.equipment_item_id
    if body.operator_worker_id is not None:
        if db.get(Worker, body.operator_worker_id) is None:
            raise validation_error(f"{fld}.operator_worker_id", "Worker not found.")
        e.operator_worker_id = body.operator_worker_id
    if not cpolicy.enabled(db, permit.project_id):
        return
    evaluation.resolve_line_item(db, permit, e)
    if e.operator_worker_id is None and evaluation.operator_code(db, e):
        msg = "This equipment category needs a named operator (HK4-9)."
        msg_ar = "تتطلب فئة المعدة هذه تسمية المشغل."
        raise ApiError(
            422,
            ErrorCode.OPERATOR_REQUIRED,
            msg,
            msg_ar,
            errors=[field_error(f"{fld}.operator_worker_id", msg, "missing", msg_ar)],
        )


def _equipment_writable(p: Principal, permit: Permit) -> None:
    _crew_writable(p, permit)
    if permit.status == S.active:
        raise read_only(permit)


def add_equipment(
    db: Session, p: Principal, permit_id: uuid.UUID, body: PermitEquipmentInput
) -> PermitEquipmentRead:
    permit = _get(db, p, permit_id)
    _equipment_writable(p, permit)
    e = _add_equipment(db, permit, body)
    _audit(db, p, permit, AuditAction.update, None, {"equipment_added": str(e.id)})
    if permit.status in (S.reviewed, S.approved, S.issued, S.suspended):
        lifecycle.back_to_requested(db, p, permit, "equipment added")
    _refresh(db, permit)
    db.refresh(e)
    return views.equipment_read(db, e, views.names_ok(p, permit.project_id))


def delete_equipment(
    db: Session, p: Principal, permit_id: uuid.UUID, equipment_id: uuid.UUID
) -> None:
    permit = _get(db, p, permit_id)
    _equipment_writable(p, permit)
    e = db.get(PermitEquipment, equipment_id)
    if e is None or e.permit_id != permit.id:
        raise not_found("Equipment line")
    lf = (permit.sections or {}).get(T.lifting.value)
    if lf and str(e.id) in [str(x) for x in lf.get("appliance_equipment_ids") or []]:
        ids = [x for x in lf["appliance_equipment_ids"] if str(x) != str(e.id)]
        if not ids:
            raise validation_error(
                "equipment_id",
                "This is the lift's only appliance: change the lifting section first.",
            )
        secs = dict(permit.sections)
        secs[T.lifting.value] = {**lf, "appliance_equipment_ids": ids}
        permit.sections = secs
    db.delete(e)
    db.flush()
    _audit(db, p, permit, AuditAction.update, {"equipment_removed": str(equipment_id)}, None)
    if permit.status in (S.reviewed, S.approved, S.issued, S.suspended):
        lifecycle.back_to_requested(db, p, permit, "equipment removed")
    _refresh(db, permit)


# ---- documents --------------------------------------------------------------------------------------


def _doc_rules(body: PermitDocumentInput) -> None:
    if body.doc_type in PLAN_DOCS and not body.approved_by_text:
        raise validation_error(
            "approved_by_text",
            "Lift, critical-lift, rescue and PE-design plans need who approved them.",
        )


def _add_document(
    db: Session, p: Principal, permit: Permit, body: PermitDocumentInput
) -> PermitDocument:
    _doc_rules(body)
    d = PermitDocument(
        id=uuid.uuid4(),
        permit_id=permit.id,
        doc_type=body.doc_type,
        ref=body.ref,
        revision=body.revision,
        attachment_id=body.attachment_id,
        approved_by_text=body.approved_by_text,
        valid_until=body.valid_until,
        added_by_user_id=p.user.id,
        added_at=now(),
    )
    db.add(d)
    db.flush()
    return d


def add_document(
    db: Session, p: Principal, permit_id: uuid.UUID, body: PermitDocumentInput
) -> PermitDocumentRead:
    permit = _get(db, p, permit_id)
    _crew_writable(p, permit)
    d = _add_document(db, p, permit, body)
    _audit(
        db,
        p,
        permit,
        AuditAction.update,
        None,
        {"document_added": f"{body.doc_type.value} {body.ref} rev {body.revision}"},
    )
    _refresh(db, permit)
    return views.document_read(db, d, Refs(db), p.user.id)


def _doc(db: Session, permit: Permit, document_id: uuid.UUID) -> PermitDocument:
    d = db.get(PermitDocument, document_id)
    if d is None or d.permit_id != permit.id:
        raise not_found("Document")
    return d


def update_document(
    db: Session,
    p: Principal,
    permit_id: uuid.UUID,
    document_id: uuid.UUID,
    body: PermitDocumentInput,
) -> PermitDocumentRead:
    permit = _get(db, p, permit_id)
    _crew_writable(p, permit)
    d = _doc(db, permit, document_id)
    _doc_rules(body)
    before = {"ref": d.ref, "revision": d.revision}
    d.doc_type = body.doc_type
    d.ref = body.ref
    d.revision = body.revision
    d.attachment_id = body.attachment_id
    d.approved_by_text = body.approved_by_text
    d.valid_until = body.valid_until
    db.flush()
    _audit(
        db,
        p,
        permit,
        AuditAction.update,
        {"document": before},
        {"document": {"ref": d.ref, "revision": d.revision}},
    )
    _refresh(db, permit)
    return views.document_read(db, d, Refs(db), p.user.id)


def delete_document(
    db: Session, p: Principal, permit_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    permit = _get(db, p, permit_id)
    _crew_writable(p, permit)
    d = _doc(db, permit, document_id)
    _audit(
        db, p, permit, AuditAction.update, {"document_removed": f"{d.doc_type.value} {d.ref}"}, None
    )
    db.delete(d)
    db.flush()
    _refresh(db, permit)


# ---- sections / checklist ----------------------------------------------------------------------------


def put_sections(
    db: Session, p: Principal, permit_id: uuid.UUID, body: SectionsInput
) -> PermitRead:
    permit = _get(db, p, permit_id)
    _prep(p, permit)
    if permit.status in PERMIT_TERMINAL or permit.status == S.active:
        raise read_only(permit)
    before = dict(permit.sections or {})
    apply_sections(db, permit, list(body.sections))
    _save_checks(db, permit)
    _audit(
        db,
        p,
        permit,
        AuditAction.update,
        {"sections": list(before)},
        {"sections": [s.work_type for s in body.sections]},
    )
    if permit.status in (S.approved, S.issued, S.suspended):
        lifecycle.back_to_requested(db, p, permit, "type section changed")
    _refresh(db, permit)
    return views.permit_read(db, p, permit)


def put_checklist(
    db: Session, p: Principal, permit_id: uuid.UUID, body: ChecklistInput
) -> ChecklistRead:
    permit = _get(db, p, permit_id)
    pid = permit.project_id
    if p.grant(pid, C.permit_receive) is not None or p.grant(pid, C.permit_prepare) is not None:
        acommon.require_cap(
            p,
            pid,
            C.permit_prepare if p.grant(pid, C.permit_prepare) else C.permit_receive,
            [permit.site_id],
            permit.engagement_id,
        )
    else:
        acommon.require_cap(p, pid, C.permit_issue, [permit.site_id], None)
    if permit.status in PERMIT_TERMINAL:
        raise read_only(permit)
    kind = body.kind
    if kind == ChecklistKind.closure and permit.status not in (S.issued, S.active, S.suspended):
        raise lifecycle.invalid(permit, "closure checklist")
    items = (
        evaluation.pre_issue_items(db, permit)
        if kind == ChecklistKind.pre_issue
        else evaluation.closure_items(db, permit)
    )
    codes = {c.value: c for c in items}
    store = dict((permit.checklists or {}).get(kind.value) or {})
    at = now()
    for i, a in enumerate(body.answers):
        code = a.code.value
        if code not in codes:
            raise validation_error(
                f"answers.{i}.code", f"{code} is not on this permit's {kind.value} checklist."
            )
        if (
            a.answer == ChecklistAnswer.na
            and kind == ChecklistKind.pre_issue
            and not ref.PRE_ISSUE[PreIssueItem(code)][2]
        ):
            raise validation_error(f"answers.{i}.answer", f"{code} cannot be answered n.a.")
        store[code] = {
            "answer": a.answer.value,
            "note": a.note,
            "by_user_id": str(p.user.id),
            "at": at.isoformat(),
        }
    cl = dict(permit.checklists or {})
    cl[kind.value] = store
    permit.checklists = cl
    db.flush()
    _audit(
        db,
        p,
        permit,
        AuditAction.update,
        None,
        {"checklist": kind.value, "answers": len(body.answers)},
    )
    _refresh(db, permit)
    return views.checklist_read(db, permit, kind, Refs(db))


# ---- copy (CL-4) ------------------------------------------------------------------------------------------


def copy(db: Session, p: Principal, permit_id: uuid.UUID, body: PermitCopyInput) -> PermitRead:
    src = _get(db, p, permit_id)
    acommon.require_cap(p, src.project_id, C.permit_prepare, [src.site_id], src.engagement_id)
    _contractor(db, src.engagement_id)
    at = now()
    year, seq, no = next_permit_no(db, src.project_id, at)
    sections = {}
    for t, sec in (src.sections or {}).items():
        sections[t] = {k: v for k, v in sec.items() if k not in HOT_WORK_RUNTIME}
    permit = Permit(
        id=uuid.uuid4(),
        permit_no=no,
        year=year,
        seq=seq,
        project_id=src.project_id,
        site_id=src.site_id,
        zone_ids=list(src.zone_ids),
        location_desc=src.location_desc,
        grid_x_m=src.grid_x_m,
        grid_y_m=src.grid_y_m,
        level_code=src.level_code,
        elevation_m=src.elevation_m,
        engagement_id=src.engagement_id,
        work_types=list(src.work_types),
        primary_type=src.primary_type,
        title=src.title,
        scope_en=src.scope_en
        if not (src.closure_request or {}).get("remaining_work")
        else f"{src.scope_en}"[:1000],
        scope_ar=src.scope_ar,
        exposure=src.exposure,
        flammables_in_use=src.flammables_in_use,
        combustion_engine_plant=src.combustion_engine_plant,
        valid_from_at=body.valid_from_at,
        valid_to_at=body.valid_to_at,
        windows=list(src.windows),
        receiver_user_id=src.receiver_user_id,
        area_authority_user_id=src.area_authority_user_id,
        issuer_user_id=None,
        hse_reviewer_user_id=src.hse_reviewer_user_id,
        supervisor_worker_id=src.supervisor_worker_id,
        linked_wap_ids=list(src.linked_wap_ids or []),
        linked_obs_ids=list(src.linked_obs_ids or []),
        isolation_cert_ids=[],
        conditions_en=src.conditions_en,
        conditions_ar=src.conditions_ar,
        copied_conditions=[],
        emergency_info=src.emergency_info,
        sections=sections,
        checklists={},
        blockers=[],
        warnings=[],
        status=S.draft,
        alerts_sent=[],
        copied_from_id=src.id,
        created_by_user_id=p.user.id,
        updated_by_user_id=p.user.id,
    )
    db.add(permit)
    db.flush()
    for x in evaluation.crew_lines(db, src.id):
        db.add(
            PermitCrew(
                id=uuid.uuid4(),
                permit_id=permit.id,
                worker_id=x.worker_id,
                crew_role=x.crew_role,
                appointment_id=x.appointment_id,
                escort_worker_id=x.escort_worker_id,
                status=CrewLineStatus.listed,
                eligibility=[],
            )
        )
    idmap: dict[str, str] = {}
    for e in evaluation.equipment_lines(db, src.id):
        n = PermitEquipment(
            id=uuid.uuid4(),
            permit_id=permit.id,
            vehicle_id=e.vehicle_id,
            category=e.category,
            tag=e.tag,
            description=e.description,
            max_working_height_m=e.max_working_height_m,
            use=e.use,
            hooks=[],
            equipment_item_id=e.equipment_item_id,
            deployment_id=e.deployment_id,
            operator_worker_id=e.operator_worker_id,
            operator_hooks=[],
            conditions=[],
        )
        idmap[str(e.id)] = str(n.id)
        db.add(n)
    for d in evaluation.documents(db, src.id):
        db.add(
            PermitDocument(
                id=uuid.uuid4(),
                permit_id=permit.id,
                doc_type=d.doc_type,
                ref=d.ref,
                revision=d.revision,
                attachment_id=d.attachment_id,
                approved_by_text=d.approved_by_text,
                valid_until=d.valid_until,
                added_by_user_id=p.user.id,
                added_at=at,
            )
        )
    lf = sections.get(T.lifting.value)
    if lf:
        lf["appliance_equipment_ids"] = [
            idmap.get(str(i), str(i)) for i in lf.get("appliance_equipment_ids") or []
        ]
        permit.sections = {**sections, T.lifting.value: lf}
    db.flush()
    checks.validity_ok(db, permit)
    sj = db.get(Jsa, src.jsa_id) if src.jsa_id else None
    if sj is not None:
        from app.services.ptw import jsa  # noqa: PLC0415

        j = Jsa(
            id=uuid.uuid4(),
            project_id=permit.project_id,
            jsa_no=jsa.instance_no(permit),
            seq=permit.seq,
            revision=0,
            is_template=False,
            template_id=sj.template_id,
            engagement_id=permit.engagement_id,
            permit_id=permit.id,
            work_types=list(sj.work_types),
            title_en=sj.title_en,
            title_ar=sj.title_ar,
            steps=jsa._copy_steps(sj.steps),
            residual_acceptances=[],
            crew_briefings=[],
            created_by_user_id=p.user.id,
            updated_by_user_id=p.user.id,
        )
        db.add(j)
        db.flush()
        permit.jsa_id = j.id
    _audit(
        db,
        p,
        permit,
        AuditAction.create,
        None,
        {"permit_no": permit.permit_no, "copied_from": src.permit_no},
    )
    _refresh(db, permit)
    return views.permit_read(db, p, permit)


_ = (PermitShift, B)
