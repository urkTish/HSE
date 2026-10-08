"""Phase 4 project settings (spec 4-third-party-cert §3.17): defaults, read, tighten-only update,
TP-5 client-approval impact; catalogue (§3.16) and certificate types (BD-3)."""

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind
from app.core.cert_enums import CertLevel, EquipmentCertCategory
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.ptw_enums import EquipmentCategory
from app.models import CertSettings, CertType, InductionCourse, ZoneAccessProfile
from app.schemas.cert_config import (
    CategoryMapping,
    CertCatalogue,
    CertSettingsRead,
    CertSettingsUpdate,
    CertSettingsUpdateResult,
    CertTypeCreate,
    CertTypeInfo,
    CertTypeUpdate,
    ColourPeriod,
    ColourSchemeRead,
    EquipmentCategoryInfo,
)
from app.services import audit, projects
from app.services.cert import reference as ref
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error

C = Capability
Q = EquipmentCertCategory


def defaults_interval() -> dict[str, int]:
    return {c.value: e.interval_months for c, e in ref.EQC.items() if e.interval_months}


def get(db: Session, project_id: uuid.UUID) -> CertSettings:
    s = db.get(CertSettings, project_id)
    if s is None:
        s = CertSettings(project_id=project_id)
        for col in CertSettings.__table__.columns:
            if getattr(s, col.key) is None and col.default is not None:
                arg = col.default.arg
                setattr(s, col.key, arg(None) if callable(arg) else arg)
        s.equipment_interval_months = defaults_interval()
        s.personnel_cert_cap_months = {}
        s.trade_cert_requirements = dict(ref.DEFAULT_TRADE_REQUIREMENTS)
        s.hook_critical_codes = list(ref.DEFAULT_CRITICAL_CODES)
        s.lifting_gear_colour_scheme = {"enabled": False, "periods": []}
        s.alert_schedule_long_days = list(ref.ALERT_SCHEDULE_LONG)
        db.add(s)
        db.flush()
    return s


def interval_months(s: CertSettings, category: EquipmentCertCategory | str) -> int | None:
    key = getattr(category, "value", category)
    v = (s.equipment_interval_months or {}).get(key)
    if v:
        return int(v)
    e = ref.EQC.get(Q(key))
    return e.interval_months if e else None


def custom_types(db: Session) -> dict[str, CertType]:
    return {t.code: t for t in db.scalars(select(CertType))}


def type_default_cap(db: Session, code: str) -> int | None:
    if code in ref.PCT:
        return ref.PCT[code].cap_months
    t = db.get(CertType, code)
    return t.cap_months if t else None


def cap_months(db: Session, s: CertSettings, cert_type: str) -> int | None:
    v = (s.personnel_cert_cap_months or {}).get(cert_type)
    return int(v) if v else type_default_cap(db, cert_type)


def is_type(db: Session, code: str) -> bool:
    return code in ref.PCT or db.get(CertType, code) is not None


def critical_codes(s: CertSettings) -> set[str]:
    return set(s.hook_critical_codes or ref.DEFAULT_CRITICAL_CODES)


# ---- read / update -------------------------------------------------------------------------------


def _view(p: Principal, project_id: uuid.UUID) -> None:
    for cap in (C.cert_register_view, C.cert_kpi_view, C.cert_settings_edit):
        if p.grant(project_id, cap) is not None:
            return
    raise forbidden_error()


def settings_read(db: Session, project_id: uuid.UUID) -> CertSettingsRead:
    s = get(db, project_id)
    refs = Refs(db)
    caps_default = {c: t.cap_months for c, t in ref.PCT.items()}
    caps_default.update(
        {c: t.cap_months for c, t in custom_types(db).items() if c not in caps_default}
    )
    caps = {c: int((s.personnel_cert_cap_months or {}).get(c, v)) for c, v in caps_default.items()}
    scheme = s.lifting_gear_colour_scheme or {"enabled": False, "periods": []}
    return CertSettingsRead(
        project_id=project_id,
        equipment_interval_months={**defaults_interval(), **(s.equipment_interval_months or {})},
        equipment_interval_defaults=defaults_interval(),
        personnel_cert_cap_months=caps,
        personnel_cert_cap_defaults=caps_default,
        require_client_approved_tpi=s.require_client_approved_tpi,
        unverified_acceptance_hours=s.unverified_acceptance_hours,
        verification_due_days=s.verification_due_days,
        defect_b_max_days=s.defect_b_max_days,
        defect_b_default_days=s.defect_b_default_days,
        scaffold_inspection_interval_days=s.scaffold_inspection_interval_days,
        scaffold_design_height_m=s.scaffold_design_height_m,
        arrival_inspection_hours=s.arrival_inspection_hours,
        rigger_level_critical_min=s.rigger_level_critical_min,
        trade_cert_requirements=dict(s.trade_cert_requirements or {}),
        hook_transition_days=s.hook_transition_days,
        hook_critical_codes=list(s.hook_critical_codes or []),
        hook_critical_transition_days=s.hook_critical_transition_days,
        lifting_gear_colour_scheme=ColourSchemeRead(
            enabled=bool(scheme.get("enabled")),
            periods=[ColourPeriod(**x) for x in scheme.get("periods", [])],
        ),
        equipment_cert_warning_pct=s.equipment_cert_warning_pct,
        personnel_cert_warning_pct=s.personnel_cert_warning_pct,
        scaffold_tag_warning_pct=s.scaffold_tag_warning_pct,
        dangerous_defect_warning_count=s.dangerous_defect_warning_count,
        ban_review_months=s.ban_review_months,
        cert_scan_retention_years=s.cert_scan_retention_years,
        alert_schedule_long_days=list(s.alert_schedule_long_days or ref.ALERT_SCHEDULE_LONG),
        updated_at=s.updated_at,
        updated_by=refs.user(s.updated_by_user_id),
    )


def read(db: Session, p: Principal, project_id: uuid.UUID) -> CertSettingsRead:
    project = projects.get_visible(db, p, project_id)
    _view(p, project.id)
    return settings_read(db, project.id)


def _loosening(field: str, msg: str) -> ApiError:
    return ApiError(
        422,
        ErrorCode.SETTING_LOOSENING,
        msg,
        "لا يمكن تخفيف هذا الإعداد؛ يسمح بالتشديد فقط.",
        meta={"field": field},
    )


def _snapshot(s: CertSettings) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for c in CertSettings.__table__.columns:
        if c.key in ("project_id", "updated_at", "updated_by_user_id"):
            continue
        v = getattr(s, c.key)
        out[c.key] = (
            str(v) if isinstance(v, Decimal) else (v.isoformat() if hasattr(v, "isoformat") else v)
        )
    return out


def update(
    db: Session, p: Principal, project_id: uuid.UUID, body: CertSettingsUpdate
) -> CertSettingsUpdateResult:
    from app.services.cert import tpis  # noqa: PLC0415

    project = projects.get_visible(db, p, project_id)
    p.require(project.id, C.cert_settings_edit)
    s = get(db, project.id)
    before = _snapshot(s)
    ch = body.changes()
    impact = None
    if "equipment_interval_months" in ch:
        new = {
            getattr(k, "value", k): int(v) for k, v in ch.pop("equipment_interval_months").items()
        }
        for k, v in new.items():
            default = ref.EQC[Q(k)].interval_months
            if default is None:
                raise validation_error(
                    f"equipment_interval_months.{k}",
                    "Scaffolds use scaffold_inspection_interval_days.",
                )
            if not 1 <= v <= default:
                raise _loosening(
                    f"equipment_interval_months.{k}",
                    f"{k}: allowed 1–{default} months (shorten only).",
                )
        s.equipment_interval_months = {**(s.equipment_interval_months or {}), **new}
    if "personnel_cert_cap_months" in ch:
        new = {k: int(v) for k, v in ch.pop("personnel_cert_cap_months").items()}
        for k, v in new.items():
            default = type_default_cap(db, k)
            if default is None:
                raise validation_error(f"personnel_cert_cap_months.{k}", f"Unknown type {k}.")
            if not 6 <= v <= default:
                raise _loosening(
                    f"personnel_cert_cap_months.{k}",
                    f"{k}: allowed 6–{default} months (shorten only).",
                )
        s.personnel_cert_cap_months = {**(s.personnel_cert_cap_months or {}), **new}
    if "trade_cert_requirements" in ch:
        new_t: dict[str, str] = {
            str(getattr(k, "value", k)): str(v)
            for k, v in ch.pop("trade_cert_requirements").items()
        }
        cur = dict(s.trade_cert_requirements or {})
        for tk, tv in new_t.items():
            if not is_type(db, tv):
                raise validation_error(f"trade_cert_requirements.{tk}", f"Unknown type {tv}.")
            if tk in cur and cur[tk] != tv and tk in ref.DEFAULT_TRADE_REQUIREMENTS:
                raise _loosening(f"trade_cert_requirements.{tk}", "Add or tighten only.")
        s.trade_cert_requirements = {**cur, **new_t}
    if "hook_critical_codes" in ch:
        new_codes = list(ch.pop("hook_critical_codes") or [])
        missing = set(s.hook_critical_codes or []) - set(new_codes)
        if missing:
            raise _loosening(
                "hook_critical_codes", f"Critical codes can only be added ({sorted(missing)})."
            )
        s.hook_critical_codes = sorted(set(new_codes))
    if "rigger_level_critical_min" in ch:
        v = ch.pop("rigger_level_critical_min")
        if v < s.rigger_level_critical_min and s.rigger_level_critical_min > 1:
            raise _loosening("rigger_level_critical_min", "Raise only once set above 1.")
        s.rigger_level_critical_min = v
    if "lifting_gear_colour_scheme" in ch:
        sc = ch.pop("lifting_gear_colour_scheme")
        s.lifting_gear_colour_scheme = {
            "enabled": bool(sc["enabled"]),
            "periods": [
                {
                    "from_mmdd": x["from_mmdd"],
                    "to_mmdd": x["to_mmdd"],
                    "colour": getattr(x["colour"], "value", x["colour"]),
                }
                for x in sc.get("periods", [])
            ],
        }
    if "defect_b_default_days" in ch or "defect_b_max_days" in ch:
        mx = ch.get("defect_b_max_days", s.defect_b_max_days)
        dflt = ch.get("defect_b_default_days", s.defect_b_default_days)
        if dflt > mx:
            raise validation_error("defect_b_default_days", "Must be ≤ defect_b_max_days.")
    if "require_client_approved_tpi" in ch:
        new_v = bool(ch.pop("require_client_approved_tpi"))
        if new_v and not s.require_client_approved_tpi:
            s.require_client_approved_tpi = True
            s.client_approval_required_from = today() + timedelta(days=7)
            impact = tpis.client_approval_impact(db, project.id, s.client_approval_required_from)
        elif not new_v and s.require_client_approved_tpi:
            raise _loosening(
                "require_client_approved_tpi", "The client-approved TPI rule cannot be relaxed."
            )
    for k, v in ch.items():
        setattr(s, k, v)
    s.updated_at = now()
    s.updated_by_user_id = p.user.id
    db.flush()
    after = _snapshot(s)
    diff_b, diff_a = audit.diff(before, after)
    if diff_a:
        audit.record(
            db,
            AuditAction.settings_changed,
            p.actor(project.id),
            entity_type=EntityType.cert_settings,
            entity_id=project.id,
            project_id=project.id,
            before=diff_b,
            after=diff_a,
        )
    from app.services.cert import events  # noqa: PLC0415

    events.publish(db, "hook_policy.changed", project_id=project.id)
    return CertSettingsUpdateResult(
        settings=settings_read(db, project.id), client_approval_impact=impact
    )


# ---- catalogue (§3.16, BD-3) ---------------------------------------------------------------------


def _type_info(
    db: Session, code: str, s: CertSettings | None, custom: dict[str, CertType]
) -> CertTypeInfo:
    builtin = ref.PCT.get(code)
    row = custom.get(code)
    crit = critical_codes(s) if s else set(ref.DEFAULT_CRITICAL_CODES)
    if builtin:
        default = builtin.cap_months
        label_en = row.label_en if row else builtin.label_en
        label_ar = row.label_ar if row else builtin.label_ar
        scope = sorted(builtin.scope_allowed, key=list(Q).index)
        levels = list(builtin.levels)
        level_required = builtin.level_required
        satisfies = list(builtin.satisfies)
        seeded = True
    else:
        assert row is not None  # noqa: S101
        default = row.cap_months
        label_en, label_ar = row.label_en, row.label_ar
        scope = [Q(x) for x in row.scope_categories_allowed]
        levels = [CertLevel(x) for x in row.levels_allowed]
        level_required = False
        satisfies = [code]
        seeded = False
    cap = int((s.personnel_cert_cap_months or {}).get(code, default)) if s else default
    return CertTypeInfo(
        code=code,
        label_en=label_en,
        label_ar=label_ar,
        default_cap_months=default,
        cap_months=cap,
        satisfies=satisfies,
        scope_categories_allowed=scope,
        levels_allowed=levels,
        level_required=level_required,
        seeded=seeded,
        critical=code in crit,
    )


def type_label(db: Session, code: str) -> tuple[str, str]:
    row = db.get(CertType, code)
    if row:
        return row.label_en, row.label_ar
    b = ref.PCT.get(code)
    return (b.label_en, b.label_ar) if b else (code, code)


def catalogue(db: Session, p: Principal, project_id: uuid.UUID | None) -> CertCatalogue:
    s = None
    if project_id is not None:
        project = projects.get_visible(db, p, project_id)
        s = get(db, project.id)
    elif not any(
        p.has_any(c) for c in (C.cert_register_view, C.personnel_cert_view, C.cert_kpi_view)
    ):
        raise forbidden_error()
    custom = custom_types(db)
    crit = critical_codes(s) if s else set(ref.DEFAULT_CRITICAL_CODES)
    cats = []
    for code, e in ref.EQC.items():
        cats.append(
            EquipmentCategoryInfo(
                code=code,
                label_en=e.label_en,
                label_ar=e.label_ar,
                default_interval_months=e.interval_months,
                interval_months=interval_months(s, code)
                if s and e.interval_months
                else e.interval_months,
                configuration_change_rule=e.cf1,
                hook_code=e.hook_code,
                operator_code=e.operator_code,
                subtypes=list(e.subtypes),
                subtype_required=e.subtype_required,
            )
        )
    codes = list(ref.PCT) + sorted(c for c in custom if c not in ref.PCT)
    types = [_type_info(db, c, s, custom) for c in codes]
    vmaps = [
        CategoryMapping(
            vehicle_category=vc, eqc=sorted(v, key=list(Q).index) if v is not None else []
        )
        for vc, v in ref.VC_TO_EQC.items()
        if v is None or v
    ]
    pmaps = [
        CategoryMapping(ptw_equipment_category=EquipmentCategory(k), eqc=[q] if q else [])
        for k, q in ref.PTW_TO_EQC.items()
    ]
    personnel_codes = list(ref.PERSONNEL_HOOK_CODES) + sorted(c for c in custom if c not in ref.PCT)
    return CertCatalogue(
        equipment_categories=cats,
        cert_types=types,
        personnel_hook_codes=personnel_codes,
        equipment_hook_codes=list(ref.EQUIPMENT_HOOK_CODE_LIST),
        critical_codes=sorted(crit),
        vehicle_mappings=vmaps,
        ptw_mappings=pmaps,
    )


def training_codes(db: Session) -> set[str]:
    """BD-3 data source until Phase 5: training_course codes used by hook attach points and
    the Phase 2 induction course codes, plus the Phase 5 seeded catalogue."""
    from app.services.ptw import reference as ptw_ref  # noqa: PLC0415

    out = set(ref.PHASE5_COURSE_CODES)
    for info in ptw_ref.TYPES.values():
        for items in info.crew_hooks.values():
            out.update(code for kind, code in items if kind == HookKind.training_course)
    for items in ptw_ref.APPOINTMENT_HOOKS.values():
        out.update(code for kind, code in items if kind == HookKind.training_course)
    out.add(ptw_ref.RECEIVER_HOOK[1])
    out.add(ptw_ref.WAH_ARREST_HOOK[1])
    for prof in db.scalars(select(ZoneAccessProfile)):
        for h in prof.hook_requirements or []:
            if h.get("kind") == HookKind.training_course.value and h.get("code"):
                out.add(str(h["code"]))
    out.update(db.scalars(select(InductionCourse.code)))
    return {c for c in out if c}


def create_type(db: Session, p: Principal, body: CertTypeCreate) -> CertTypeInfo:
    p.ensure_writer()
    if not p.is_manager:
        raise forbidden_error()
    if body.code in training_codes(db):
        raise ApiError(
            422,
            ErrorCode.CODE_IN_OTHER_CATALOGUE,
            f"{body.code} is a training course code (Phase 5 catalogue); a credential type "
            "exists in exactly one catalogue (BD-3).",
            "هذا الرمز مستخدم في فهرس الدورات التدريبية؛ لا يجوز تكراره (BD-3).",
        )
    if is_type(db, body.code):
        from app.services.common import duplicate  # noqa: PLC0415

        raise duplicate("code", "This certificate type already exists.")
    row = CertType(
        code=body.code,
        label_en=body.label_en,
        label_ar=body.label_ar,
        cap_months=body.cap_months,
        scope_categories_allowed=[c.value for c in body.scope_categories_allowed],
        levels_allowed=[x.value for x in body.levels_allowed],
        seeded=False,
        updated_by_user_id=p.user.id,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        AuditAction.create,
        p.actor(),
        entity_type=EntityType.cert_type,
        details={"code": row.code},
        after={"code": row.code, "label_en": row.label_en, "cap_months": row.cap_months},
    )
    return _type_info(db, row.code, None, custom_types(db))


def update_type(db: Session, p: Principal, code: str, body: CertTypeUpdate) -> CertTypeInfo:
    p.ensure_writer()
    if not p.is_manager:
        raise forbidden_error()
    builtin = ref.PCT.get(code)
    row = db.get(CertType, code)
    if builtin is None and row is None:
        raise not_found("Certificate type")
    ch = body.changes()
    if row is None:
        assert builtin is not None  # noqa: S101
        row = CertType(
            code=code,
            label_en=builtin.label_en,
            label_ar=builtin.label_ar,
            cap_months=builtin.cap_months,
            scope_categories_allowed=[c.value for c in builtin.scope_allowed],
            levels_allowed=[x.value for x in builtin.levels],
            seeded=True,
        )
        db.add(row)
    before = {"label_en": row.label_en, "label_ar": row.label_ar}
    for k, v in ch.items():
        setattr(row, k, v)
    row.updated_at = now()
    row.updated_by_user_id = p.user.id
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        p.actor(),
        entity_type=EntityType.cert_type,
        details={"code": code},
        before=before,
        after={"label_en": row.label_en, "label_ar": row.label_ar},
    )
    return _type_info(db, code, None, custom_types(db))
