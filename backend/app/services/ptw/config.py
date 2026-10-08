"""PTW configuration services (spec 3-ptw §3.1-§3.3, §3.12, §3.17, §6.1): permit types, zone PTW
profiles, zone adjacency, the SIMOPS matrix, the risk matrix and the Phase 3 settings."""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind, HookPolicy
from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, ZoneType
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.ptw_enums import (
    PERMIT_TYPE_LETTERS,
    AppointmentFunction,
    ClosureItem,
    EquipmentCategory,
    Hazard,
    HazardousAreaClass,
    PermitType,
    PreIssueItem,
    PtwCrewRole,
    RiskBand,
    SimopsResult,
    VerticalRelation,
)
from app.models import PermitTypeConfig, SimopsRule, Zone, ZoneAdjacency, ZonePtwProfile
from app.schemas.access_common import HookRequirementRead
from app.schemas.ptw_config import (
    GasLimits,
    MiddayBanHours,
    MiddayBanPeriod,
    PermitTypeConfigList,
    PermitTypeConfigRead,
    PermitTypeConfigUpdate,
    PtwSettingsRead,
    PtwSettingsUpdate,
    RiskBandInfo,
    RiskMatrixCell,
    RiskMatrixRead,
    SimopsRuleCreate,
    SimopsRuleList,
    SimopsRuleRead,
    SimopsRuleUpdate,
    ZoneAdjacencyCreate,
    ZoneAdjacencyRead,
    ZoneAdjacencyUpdate,
    ZonePtwProfileRead,
    ZonePtwProfileUpdate,
)
from app.services import audit, projects
from app.services.access import common as acommon
from app.services.common import duplicate
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error
from app.services.ptw import common
from app.services.ptw import reference as ref
from app.services.ptw.rules import band

C = Capability

# ---- permit types (§3.1) -------------------------------------------------------------------------


def _view(p: Principal, project_id: uuid.UUID) -> None:
    if (
        p.grant(project_id, C.permit_view) is None
        and p.grant(project_id, C.ptw_settings_edit) is None
    ):
        raise forbidden_error()


def _hooks(items: Any) -> list[HookRequirementRead]:
    return [
        HookRequirementRead(kind=HookKind(k), code=c) if isinstance(k, str | HookKind) else k
        for k, c in items
    ]


def _cfg(db: Session, project_id: uuid.UUID, t: PermitType) -> PermitTypeConfig | None:
    return db.get(PermitTypeConfig, (project_id, t))


def training_registered(db: Session, project_id: uuid.UUID) -> bool:
    """Phase 5 registered its `training_course` provider on the project (HK5-1)."""
    from app.services.cert import policy as cpolicy  # noqa: PLC0415

    cache: dict[Any, Any] = db.info.setdefault("hook_states", {})
    key = ("registered", project_id, HookKind.training_course)
    if key not in cache:
        cache[key] = cpolicy.state(db, project_id, HookKind.training_course) is not None
    return bool(cache[key])


def type_lists(db: Session, project_id: uuid.UUID, t: PermitType) -> dict[str, Any]:
    """Defaults + per-project additions of one type."""
    info = ref.TYPES[t]
    cfg = _cfg(db, project_id, t)
    pre = list(info.pre_issue) + [
        PreIssueItem(c) for c in (cfg.extra_pre_issue if cfg else []) if c not in info.pre_issue
    ]
    clo = list(info.closure) + [
        ClosureItem(c) for c in (cfg.extra_closure if cfg else []) if c not in info.closure
    ]
    haz = list(info.hazards) + [
        Hazard(c) for c in (cfg.extra_hazards if cfg else []) if c not in info.hazards
    ]
    crew: dict[PtwCrewRole, list[tuple[HookKind, str]]] = {
        r: list(v) for r, v in info.crew_hooks.items()
    }
    if t == PermitType.work_at_height:
        for r in PtwCrewRole:
            crew.setdefault(r, [])
    if training_registered(db, project_id):
        # 3-ptw v1.2 §11.4 (5-training): WAH for every crew member on a WAH section; rescue
        # lead also needs FIRST-AID — from the day Phase 5 registers its provider
        if t == PermitType.work_at_height:
            for r in PtwCrewRole:
                if ref.WAH_ARREST_HOOK not in crew[r]:
                    crew[r].append(ref.WAH_ARREST_HOOK)
        if (
            PtwCrewRole.rescue_lead in crew
            and ref.RESCUE_FIRST_AID_HOOK not in crew[PtwCrewRole.rescue_lead]
        ):
            crew[PtwCrewRole.rescue_lead] = [
                *crew[PtwCrewRole.rescue_lead],
                ref.RESCUE_FIRST_AID_HOOK,
            ]
    for role, items in ((cfg.extra_crew_hooks if cfg else None) or {}).items():
        lst = crew.setdefault(PtwCrewRole(role), [])
        for h in items:
            pair = (HookKind(h["kind"]), h["code"])
            if pair not in lst:
                lst.append(pair)
    crew = {r: v for r, v in crew.items() if v}
    equip: dict[EquipmentCategory, list[tuple[HookKind, str]]] = {
        c: list(v) for c, v in ref.EQUIPMENT_HOOKS.items()
    }
    for c, items in ((cfg.extra_equipment_hooks if cfg else None) or {}).items():
        lst = equip.setdefault(EquipmentCategory(c), [])
        for h in items:
            pair = (HookKind(h["kind"]), h["code"])
            if pair not in lst:
                lst.append(pair)
    return {"pre": pre, "closure": clo, "hazards": haz, "crew": crew, "equip": equip, "cfg": cfg}


def _type_read(db: Session, project_id: uuid.UUID, t: PermitType) -> PermitTypeConfigRead:
    s = common.settings(db, project_id)
    info = ref.TYPES[t]
    lists = type_lists(db, project_id, t)
    cfg: PermitTypeConfig | None = lists["cfg"]
    return PermitTypeConfigRead(
        project_id=project_id,
        type=t,
        ref_letter=PERMIT_TYPE_LETTERS[t],
        label_en=info.label_en,
        label_ar=info.label_ar,
        max_duration_days=int(s.type_max_duration_days.get(t.value, info.max_days)),
        max_duration_days_critical=1 if t == PermitType.lifting else None,
        max_shift_hours=s.ptw_shift_max_hours,
        revalidation=info.revalidation,
        gas_test_rule_en=info.gas_en,
        gas_test_rule_ar=info.gas_ar,
        hse_review_rule_en=info.hse_en,
        hse_review_rule_ar=info.hse_ar,
        mandatory_crew_roles=list(info.roles),
        mandatory_documents=list(info.documents),
        pre_issue_checklist=lists["pre"],
        closure_checklist=lists["closure"],
        mandatory_hazards=lists["hazards"],
        hook_requirements_by_crew_role={r: _hooks(v) for r, v in lists["crew"].items()},
        hook_requirements_by_equipment={c: _hooks(v) for c, v in lists["equip"].items()},
        updated_at=cfg.updated_at if cfg else None,
        updated_by=Refs(db).user(cfg.updated_by_user_id) if cfg else None,
    )


def list_types(db: Session, p: Principal, project_id: uuid.UUID) -> PermitTypeConfigList:
    project = projects.get_visible(db, p, project_id)
    _view(p, project.id)
    return PermitTypeConfigList(
        items=[_type_read(db, project.id, t) for t in PermitType],
        hook_requirements_by_appointment={
            AppointmentFunction(k): _hooks(v) for k, v in ref.APPOINTMENT_HOOKS.items()
        },
    )


def _locked_removal(field: str, missing: list[str]) -> ApiError:
    return validation_error(
        field,
        f"Spec default items cannot be removed: {', '.join(missing)}.",
        msg_ar="لا يمكن حذف البنود الافتراضية.",
    )


def update_type(
    db: Session, p: Principal, project_id: uuid.UUID, t: PermitType, body: PermitTypeConfigUpdate
) -> PermitTypeConfigRead:
    project = projects.get_visible(db, p, project_id)
    p.require(project.id, C.ptw_settings_edit)
    info = ref.TYPES[t]
    cfg = _cfg(db, project.id, t)
    if cfg is None:
        cfg = PermitTypeConfig(
            project_id=project.id,
            type=t,
            extra_pre_issue=[],
            extra_closure=[],
            extra_hazards=[],
            extra_crew_hooks={},
            extra_equipment_hooks={},
        )
        db.add(cfg)
    before = common_snapshot(cfg)
    ch = body.changes()
    for field, defaults, attr in (
        ("pre_issue_checklist", info.pre_issue, "extra_pre_issue"),
        ("closure_checklist", info.closure, "extra_closure"),
        ("mandatory_hazards", info.hazards, "extra_hazards"),
    ):
        if field in ch:
            vals = [getattr(v, "value", v) for v in ch[field]]
            missing = [d.value for d in defaults if d.value not in vals]
            if missing:
                raise _locked_removal(field, missing)
            setattr(
                cfg, attr, [v for v in dict.fromkeys(vals) if v not in {d.value for d in defaults}]
            )
    for field, base, attr in (
        ("hook_requirements_by_crew_role", info.crew_hooks, "extra_crew_hooks"),
        ("hook_requirements_by_equipment", ref.EQUIPMENT_HOOKS, "extra_equipment_hooks"),
    ):
        if field in ch:
            out: dict[str, list[dict[str, Any]]] = dict(getattr(cfg, attr) or {})
            given = {getattr(k, "value", k): v for k, v in ch[field].items()}
            for key, defaults_ in base.items():
                if key.value not in given:
                    continue
                have = {
                    (str(getattr(h["kind"], "value", h["kind"])), h["code"])
                    for h in given.get(key.value, [])
                }
                missing = [c for k, c in defaults_ if (k.value, c) not in have]
                if missing:
                    raise _locked_removal(field, missing)
            for key, items in given.items():
                defaults_set = {(k.value, c) for k, c in base.get(key, ())}
                extra = [
                    {"kind": str(getattr(h["kind"], "value", h["kind"])), "code": h["code"]}
                    for h in items
                    if (str(getattr(h["kind"], "value", h["kind"])), h["code"]) not in defaults_set
                ]
                if extra:
                    out[key] = extra
                else:
                    out.pop(key, None)
            setattr(cfg, attr, out)
    cfg.updated_at = now()
    cfg.updated_by_user_id = p.user.id
    db.flush()
    bf, af = audit.diff(before, common_snapshot(cfg))
    if af:
        audit.record(
            db,
            AuditAction.settings_changed,
            p.actor(project.id),
            entity_type=EntityType.permit_type_config,
            entity_id=project.id,
            project_id=project.id,
            before=bf,
            after=af,
            details={"type": t.value},
        )
    return _type_read(db, project.id, t)


def common_snapshot(cfg: PermitTypeConfig) -> dict[str, Any]:
    return {
        "extra_pre_issue": list(cfg.extra_pre_issue or []),
        "extra_closure": list(cfg.extra_closure or []),
        "extra_hazards": list(cfg.extra_hazards or []),
        "extra_crew_hooks": dict(cfg.extra_crew_hooks or {}),
        "extra_equipment_hooks": dict(cfg.extra_equipment_hooks or {}),
    }


# ---- zone PTW profile (§3.2) ---------------------------------------------------------------------


def _zone(db: Session, p: Principal, zone_id: uuid.UUID) -> Zone:
    zone = db.get(Zone, zone_id)
    if zone is None:
        raise not_found("Zone")
    projects.get_visible(db, p, zone.project_id)
    return zone


def _profile_read(db: Session, prof: ZonePtwProfile, zone: Zone) -> ZonePtwProfileRead:
    refs = Refs(db)
    zr = refs.zone(zone.id)
    assert zr is not None  # noqa: S101
    return ZonePtwProfileRead(
        zone=zr,
        permit_required_all_work=prof.permit_required_all_work,
        gas_test_zone=prof.gas_test_zone,
        hazardous_area_class=prof.hazardous_area_class,
        hazardous_area_note=prof.hazardous_area_note,
        default_exposure=prof.default_exposure,
        fire_protection_present=prof.fire_protection_present,
        level_datum_note=prof.level_datum_note,
        default_area_authority_ids=list(prof.default_area_authority_ids or []),
        default_area_authorities=[
            u for u in (refs.user(i) for i in prof.default_area_authority_ids or []) if u
        ],
        in_movement_area=bool(zone.in_movement_area),
        updated_at=prof.updated_at,
        updated_by=refs.user(prof.updated_by_user_id),
    )


def read_profile(db: Session, p: Principal, zone_id: uuid.UUID) -> ZonePtwProfileRead:
    zone = _zone(db, p, zone_id)
    return _profile_read(db, common.profile(db, zone), zone)


def _profile_snapshot(prof: ZonePtwProfile) -> dict[str, Any]:
    return acommon.jsonable(
        {
            "permit_required_all_work": prof.permit_required_all_work,
            "gas_test_zone": prof.gas_test_zone,
            "hazardous_area_class": prof.hazardous_area_class.value,
            "hazardous_area_note": prof.hazardous_area_note,
            "default_exposure": prof.default_exposure.value,
            "fire_protection_present": prof.fire_protection_present,
            "level_datum_note": prof.level_datum_note,
            "default_area_authority_ids": list(prof.default_area_authority_ids or []),
        }
    )


def update_profile(
    db: Session, p: Principal, zone_id: uuid.UUID, body: ZonePtwProfileUpdate
) -> ZonePtwProfileRead:
    zone = _zone(db, p, zone_id)
    acommon.require_cap(p, zone.project_id, C.ptw_zone_profile_edit, [zone.site_id])
    prof = common.profile(db, zone)
    before = _profile_snapshot(prof)
    ch = body.changes()
    if (
        ch.get("permit_required_all_work") is False
        and zone.zone_type == ZoneType.airside
        and zone.in_movement_area
    ):
        raise ApiError(
            422,
            ErrorCode.PROFILE_LOOSENING,
            "Movement-area zones always need a permit for all work (PT-3).",
            "مناطق الحركة تتطلب دائماً تصريحاً لكل الأعمال.",
        )
    if "default_area_authority_ids" in ch:
        days = [acommon.local_day(now())]
        for uid in ch["default_area_authority_ids"]:
            if (
                common.find_appointment(
                    db,
                    zone.project_id,
                    AppointmentFunction.area_authority,
                    [],
                    zone.site_id,
                    [zone.id],
                    days,
                    user_id=uid,
                )
                is None
            ):
                raise validation_error(
                    "default_area_authority_ids",
                    "Each default area authority needs an Active area_authority appointment "
                    "covering the zone.",
                )
    for k, v in ch.items():
        setattr(prof, k, v)
    cls = prof.hazardous_area_class
    if cls != HazardousAreaClass.none and not (prof.hazardous_area_note or "").strip():
        raise validation_error(
            "hazardous_area_note", "Describe the hazardous area (required when classified)."
        )
    prof.updated_at = now()
    prof.updated_by_user_id = p.user.id
    db.flush()
    bf, af = audit.diff(before, _profile_snapshot(prof))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(zone.project_id),
            entity_type=EntityType.zone_ptw_profile,
            entity_id=zone.id,
            project_id=zone.project_id,
            before=bf,
            after=af,
        )
    return _profile_read(db, prof, zone)


# ---- zone adjacency (§3.3) -----------------------------------------------------------------------


def _adj_read(db: Session, a: ZoneAdjacency, refs: Refs | None = None) -> ZoneAdjacencyRead:
    refs = refs or Refs(db)
    za, zb = refs.zone(a.zone_a_id), refs.zone(a.zone_b_id)
    assert za is not None and zb is not None  # noqa: S101
    return ZoneAdjacencyRead(
        id=a.id,
        project_id=a.project_id,
        zone_a=za,
        zone_b=zb,
        distance_m=a.distance_m,
        vertical_relation=a.vertical_relation,
        updated_at=a.updated_at,
    )


def list_adjacency(db: Session, p: Principal, project_id: uuid.UUID) -> list[ZoneAdjacencyRead]:
    project = projects.get_visible(db, p, project_id)
    _view(p, project.id)
    rows = list(db.scalars(select(ZoneAdjacency).where(ZoneAdjacency.project_id == project.id)))
    refs = Refs(db).load(zones=[z for a in rows for z in (a.zone_a_id, a.zone_b_id)])
    out = [_adj_read(db, a, refs) for a in rows]
    return sorted(out, key=lambda r: (r.zone_a.code, r.zone_b.code))


def adjacency(db: Session, za: uuid.UUID, zb: uuid.UUID) -> ZoneAdjacency | None:
    lo, hi = sorted([za, zb], key=str)
    return db.scalar(
        select(ZoneAdjacency).where(ZoneAdjacency.zone_a_id == lo, ZoneAdjacency.zone_b_id == hi)
    )


def create_adjacency(
    db: Session, p: Principal, project_id: uuid.UUID, body: ZoneAdjacencyCreate
) -> ZoneAdjacencyRead:
    project = projects.get_visible(db, p, project_id)
    acommon.require_cap(p, project.id, C.ptw_zone_profile_edit)
    if body.zone_a_id == body.zone_b_id:
        raise validation_error("zone_b_id", "The two zones must differ.")
    zs = [db.get(Zone, body.zone_a_id), db.get(Zone, body.zone_b_id)]
    if any(z is None or z.project_id != project.id for z in zs):
        raise validation_error("zone_a_id", "Both zones must belong to the project.")
    if adjacency(db, body.zone_a_id, body.zone_b_id) is not None:
        raise duplicate("zone_b_id", "This zone pair already exists.")
    lo, hi = sorted([body.zone_a_id, body.zone_b_id], key=str)
    rel = body.vertical_relation
    if lo != body.zone_a_id:
        rel = _flip(rel)
    a = ZoneAdjacency(
        id=uuid.uuid4(),
        project_id=project.id,
        zone_a_id=lo,
        zone_b_id=hi,
        distance_m=body.distance_m,
        vertical_relation=rel,
        created_by_user_id=p.user.id,
        updated_by_user_id=p.user.id,
    )
    db.add(a)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.zone_adjacency,
        entity_id=a.id,
        project_id=project.id,
        after={"distance_m": str(a.distance_m), "vertical_relation": rel.value},
    )
    return _adj_read(db, a)


def _flip(rel: VerticalRelation) -> VerticalRelation:
    vr = VerticalRelation
    return {vr.a_above_b: vr.b_above_a, vr.b_above_a: vr.a_above_b}.get(rel, rel)


def _adj_row(db: Session, p: Principal, adjacency_id: uuid.UUID) -> ZoneAdjacency:
    a = db.get(ZoneAdjacency, adjacency_id)
    if a is None:
        raise not_found("Zone adjacency")
    projects.get_visible(db, p, a.project_id)
    return a


def update_adjacency(
    db: Session, p: Principal, adjacency_id: uuid.UUID, body: ZoneAdjacencyUpdate
) -> ZoneAdjacencyRead:
    a = _adj_row(db, p, adjacency_id)
    acommon.require_cap(p, a.project_id, C.ptw_zone_profile_edit)
    before = {"distance_m": str(a.distance_m), "vertical_relation": a.vertical_relation.value}
    for k, v in body.changes().items():
        setattr(a, k, v)
    a.updated_by_user_id = p.user.id
    db.flush()
    after = {"distance_m": str(a.distance_m), "vertical_relation": a.vertical_relation.value}
    bf, af = audit.diff(before, after)
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(a.project_id),
            entity_type=EntityType.zone_adjacency,
            entity_id=a.id,
            project_id=a.project_id,
            before=bf,
            after=af,
        )
    return _adj_read(db, a)


def delete_adjacency(db: Session, p: Principal, adjacency_id: uuid.UUID) -> None:
    a = _adj_row(db, p, adjacency_id)
    acommon.require_cap(p, a.project_id, C.ptw_zone_profile_edit)
    audit.record(
        db,
        AuditAction.archive,
        p.actor(a.project_id),
        entity_type=EntityType.zone_adjacency,
        entity_id=a.id,
        project_id=a.project_id,
        before={"distance_m": str(a.distance_m)},
    )
    db.delete(a)
    db.flush()


# ---- SIMOPS matrix (SM-3) ------------------------------------------------------------------------


def ensure_rules(db: Session, project_id: uuid.UUID) -> list[SimopsRule]:
    rows = {
        r.rule_code: r
        for r in db.scalars(select(SimopsRule).where(SimopsRule.project_id == project_id))
    }
    for d in ref.SIMOPS_DEFAULTS:
        if d.code not in rows:
            r = SimopsRule(
                id=uuid.uuid4(),
                project_id=project_id,
                rule_code=d.code,
                is_default=True,
                type_a=d.type_a,
                type_b=d.type_b,
                condition=d.condition,
                threshold_m=d.threshold,
                result=d.result,
                required_controls_en=d.controls_en,
                required_controls_ar=d.controls_ar,
                active=True,
            )
            db.add(r)
            rows[d.code] = r
    db.flush()
    return sorted(rows.values(), key=lambda r: _code_key(r.rule_code))


def _code_key(code: str) -> tuple[int, str]:
    tail = code.removeprefix("SM-R")
    num = "".join(ch for ch in tail if ch.isdigit())
    return int(num or 0), tail


def _rule_read(db: Session, r: SimopsRule) -> SimopsRuleRead:
    en, ar = ref.CONDITION_TEXT[r.condition]
    return SimopsRuleRead(
        id=r.id,
        project_id=r.project_id,
        rule_code=r.rule_code,
        is_default=r.is_default,
        type_a=r.type_a,
        type_b=r.type_b,
        condition=r.condition,
        condition_en=en,
        condition_ar=ar,
        threshold_m=r.threshold_m,
        result=r.result,
        required_controls_en=r.required_controls_en,
        required_controls_ar=r.required_controls_ar,
        active=r.active,
        updated_at=r.updated_at,
        updated_by=Refs(db).user(r.updated_by_user_id),
    )


def list_rules(db: Session, p: Principal, project_id: uuid.UUID) -> SimopsRuleList:
    project = projects.get_visible(db, p, project_id)
    _view(p, project.id)
    return SimopsRuleList(items=[_rule_read(db, r) for r in ensure_rules(db, project.id)])


def _rule_snapshot(r: SimopsRule) -> dict[str, Any]:
    return {
        "threshold_m": None if r.threshold_m is None else str(r.threshold_m),
        "result": r.result.value,
        "required_controls_en": r.required_controls_en,
        "required_controls_ar": r.required_controls_ar,
        "active": r.active,
    }


def create_rule(
    db: Session, p: Principal, project_id: uuid.UUID, body: SimopsRuleCreate
) -> SimopsRuleRead:
    project = projects.get_visible(db, p, project_id)
    p.require(project.id, C.ptw_settings_edit)
    rules = ensure_rules(db, project.id)
    nxt = max(_code_key(r.rule_code)[0] for r in rules) + 1
    r = SimopsRule(
        id=uuid.uuid4(),
        project_id=project.id,
        rule_code=f"SM-R{nxt:02d}",
        is_default=False,
        type_a=body.type_a,
        type_b=body.type_b,
        condition=body.condition,
        threshold_m=body.threshold_m,
        result=body.result,
        required_controls_en=body.required_controls_en,
        required_controls_ar=body.required_controls_ar,
        active=True,
        created_by_user_id=p.user.id,
        updated_by_user_id=p.user.id,
    )
    db.add(r)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(project.id),
        entity_type=EntityType.simops_rule,
        entity_id=r.id,
        project_id=project.id,
        after={"rule_code": r.rule_code, **_rule_snapshot(r)},
    )
    return _rule_read(db, r)


def _rule_row(db: Session, p: Principal, rule_id: uuid.UUID) -> SimopsRule:
    r = db.get(SimopsRule, rule_id)
    if r is None:
        raise not_found("SIMOPS rule")
    projects.get_visible(db, p, r.project_id)
    return r


def _rule_locked(msg: str) -> ApiError:
    return ApiError(
        422,
        ErrorCode.SIMOPS_RULE_LOCKED,
        msg,
        "قواعد العمليات المتزامنة الافتراضية يمكن تشديدها فقط ولا يمكن حذفها.",
    )


def update_rule(
    db: Session, p: Principal, rule_id: uuid.UUID, body: SimopsRuleUpdate
) -> SimopsRuleRead:
    r = _rule_row(db, p, rule_id)
    p.require(r.project_id, C.ptw_settings_edit)
    before = _rule_snapshot(r)
    ch = body.changes()
    if r.is_default:
        if "active" in ch and ch["active"] is False:
            raise _rule_locked("Default rules cannot be deactivated.")
        if "threshold_m" in ch:
            new = ch["threshold_m"]
            if r.threshold_m is None and new is not None:
                raise _rule_locked(f"{r.rule_code} uses a permit value; no fixed threshold.")
            if r.threshold_m is not None and (new is None or Decimal(new) < r.threshold_m):
                raise _rule_locked(f"{r.rule_code}: the threshold can only be increased.")
        if "result" in ch:
            rank = ref.RESULT_RANK
            if rank[SimopsResult(ch["result"])] < rank[r.result]:
                raise _rule_locked(f"{r.rule_code}: the result can only be made stricter.")
    for k, v in ch.items():
        setattr(r, k, v)
    r.updated_by_user_id = p.user.id
    r.updated_at = now()
    db.flush()
    bf, af = audit.diff(before, _rule_snapshot(r))
    if af:
        audit.record(
            db,
            AuditAction.update,
            p.actor(r.project_id),
            entity_type=EntityType.simops_rule,
            entity_id=r.id,
            project_id=r.project_id,
            before=bf,
            after=af,
            details={"rule_code": r.rule_code},
        )
    return _rule_read(db, r)


def delete_rule(db: Session, p: Principal, rule_id: uuid.UUID) -> None:
    r = _rule_row(db, p, rule_id)
    p.require(r.project_id, C.ptw_settings_edit)
    if r.is_default:
        raise _rule_locked(f"{r.rule_code} is a default rule and cannot be deleted (SM-3).")
    audit.record(
        db,
        AuditAction.archive,
        p.actor(r.project_id),
        entity_type=EntityType.simops_rule,
        entity_id=r.id,
        project_id=r.project_id,
        before={"rule_code": r.rule_code},
    )
    db.delete(r)
    db.flush()


# ---- risk matrix (§6.1) --------------------------------------------------------------------------


def risk_matrix() -> RiskMatrixRead:
    cells = [
        RiskMatrixCell(likelihood=lk, severity=sv, score=lk * sv, band=band(lk * sv))
        for sv in range(5, 0, -1)
        for lk in range(1, 6)
    ]
    bands = [
        RiskBandInfo(
            band=b, min_score=lo, max_score=hi, label_en=en, label_ar=ar,
            acceptance_en=acc_en, acceptance_ar=acc_ar,
        )
        for b, lo, hi, en, ar, acc_en, acc_ar in ref.BANDS
    ]  # fmt: skip
    return RiskMatrixRead(cells=cells, bands=bands)


_ = RiskBand

# ---- Phase 3 settings (§3.17) --------------------------------------------------------------------

PLAIN_SKIP = {"project_id", "updated_at", "updated_by_user_id"}


def settings_read(db: Session, project_id: uuid.UUID) -> PtwSettingsRead:
    from app.models import PtwSettings  # noqa: PLC0415

    s = common.settings(db, project_id)
    a = acommon.settings(db, project_id)
    data = {
        c.key: getattr(s, c.key) for c in PtwSettings.__table__.columns if c.key not in PLAIN_SKIP
    }
    data["type_max_duration_days"] = {
        PermitType(k): int(v) for k, v in (s.type_max_duration_days or {}).items()
    }
    data["gas_retest_interval_minutes"] = {
        PermitType(k): int(v) for k, v in (s.gas_retest_interval_minutes or {}).items()
    }
    data["gas_limits"] = GasLimits.model_validate(s.gas_limits)
    data["midday_ban_period"] = MiddayBanPeriod.model_validate(s.midday_ban_period)
    data["midday_ban_hours"] = MiddayBanHours.model_validate(s.midday_ban_hours)
    return PtwSettingsRead(
        **data,
        project_id=project_id,
        critical_lift_max_duration_days=1,
        hook_policy={
            k: HookPolicy((a.hook_policy or {}).get(k.value, HookPolicy.warn.value))
            for k in HookKind
        },
        updated_at=s.updated_at,
        updated_by=Refs(db).user(s.updated_by_user_id),
    )


def read_settings(db: Session, p: Principal, project_id: uuid.UUID) -> PtwSettingsRead:
    project = projects.get_visible(db, p, project_id)
    _view(p, project.id)
    return settings_read(db, project.id)


def _settings_snapshot(db: Session, project_id: uuid.UUID) -> dict[str, Any]:
    from app.models import PtwSettings  # noqa: PLC0415

    s = common.settings(db, project_id)
    return {
        c.key: (str(v) if isinstance(v := getattr(s, c.key), Decimal) else v)
        for c in PtwSettings.__table__.columns
        if c.key not in PLAIN_SKIP
    }


def _range_error(field: str, msg: str) -> ApiError:
    return validation_error(field, msg, msg_ar="القيمة خارج النطاق المسموح.")


def update_settings(
    db: Session, p: Principal, project_id: uuid.UUID, body: PtwSettingsUpdate
) -> PtwSettingsRead:
    project = projects.get_visible(db, p, project_id)
    p.require(project.id, C.ptw_settings_edit)
    s = common.settings(db, project.id)
    before = _settings_snapshot(db, project.id)
    ch = body.changes()
    if "type_max_duration_days" in ch:
        vals = {getattr(k, "value", k): int(v) for k, v in ch.pop("type_max_duration_days").items()}
        for k, v in vals.items():
            lo, hi = ref.TYPE_MAX_ALLOWED[PermitType(k)]
            if not lo <= v <= hi:
                raise _range_error(
                    f"type_max_duration_days.{k}", f"{k}: allowed {lo}–{hi} day(s), got {v}."
                )
        s.type_max_duration_days = {**(s.type_max_duration_days or {}), **vals}
    if "gas_retest_interval_minutes" in ch:
        vals = {
            getattr(k, "value", k): int(v) for k, v in ch.pop("gas_retest_interval_minutes").items()
        }
        for k, v in vals.items():
            if not 15 <= v <= 240:
                raise _range_error(f"gas_retest_interval_minutes.{k}", "Allowed 15–240 min.")
        s.gas_retest_interval_minutes = {**(s.gas_retest_interval_minutes or {}), **vals}
    if "gas_limits" in ch:
        new = ch.pop("gas_limits")
        cur = s.gas_limits["by_profile"]
        for prof, vals in new["by_profile"].items():
            key = getattr(prof, "value", prof)
            old = cur.get(key)
            if old is None:
                continue
            loosened = (
                Decimal(vals["o2_min_pct"]) < Decimal(old["o2_min_pct"])
                or Decimal(vals["o2_max_pct"]) > Decimal(old["o2_max_pct"])
                or any(
                    Decimal(vals[f]) > Decimal(old[f])
                    for f in ("lel_below_pct", "h2s_below_ppm", "co_below_ppm")
                )
            )
            if loosened:
                raise _range_error(f"gas_limits.{key}", "Gas limits may only be tightened.")
        s.gas_limits = acommon_json(
            {
                "by_profile": {
                    **cur,
                    **{getattr(k, "value", k): v for k, v in new["by_profile"].items()},
                },
                "other_toxics": new.get("other_toxics") or [],
            }
        )
    if "midday_ban_period" in ch:
        new = ch.pop("midday_ban_period")
        old = s.midday_ban_period
        if new["start_mmdd"] > old["start_mmdd"] or new["end_mmdd"] < old["end_mmdd"]:
            raise _range_error("midday_ban_period", "The midday ban period may only widen.")
        s.midday_ban_period = dict(new)
    if "midday_ban_hours" in ch:
        new = ch.pop("midday_ban_hours")
        start, end = new["start_local"].strftime("%H:%M"), new["end_local"].strftime("%H:%M")
        old = s.midday_ban_hours
        if start > old["start_local"] or end < old["end_local"]:
            raise _range_error("midday_ban_hours", "The midday ban hours may only widen.")
        s.midday_ban_hours = {"start_local": start, "end_local": end}
    for k, v in ch.items():
        setattr(s, k, v)
    s.updated_at = now()
    s.updated_by_user_id = p.user.id
    db.flush()
    bf, af = audit.diff(before, _settings_snapshot(db, project.id))
    if af:
        audit.record(
            db,
            AuditAction.settings_changed,
            p.actor(project.id),
            entity_type=EntityType.ptw_settings,
            entity_id=project.id,
            project_id=project.id,
            before=bf,
            after=af,
            details={"scope": "ptw_settings"},
        )
    return settings_read(db, project.id)


def acommon_json(v: Any) -> Any:
    import json  # noqa: PLC0415

    return json.loads(json.dumps(v, default=str))
