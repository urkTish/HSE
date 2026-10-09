"""Phase 6c reference lists (§3.14) and project settings (§3.15, ER-2, ER-9)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.emergency_enums import AssetType, DrillType
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, validation_error
from app.schemas.emergency import EmergencyReference, EmergencySettingsRead, EmergencySettingsUpdate
from app.schemas.emergency import EmRefItem as Item
from app.services import audit
from app.services.emergency import common as ec
from app.services.emergency import reference as ref
from app.services.permissions import Principal

C = Capability
PCT = ("drill_compliance_warning_pct", "coverage_warning_pct", "equipment_readiness_warning_pct")
ONLY_LOWER = ("first_aider_ratio", "warden_ratio")  # ER-9 'only lower'
ONLY_RAISE = ("min_extinguishers_per_zone", "min_first_aid_kits_per_zone", "min_aed_per_site")
BOOL_TRUE_ONLY = ("erp_client_acceptance_required", "coordinator_required_per_shift")


def reference() -> EmergencyReference:
    def items(m: dict[Any, tuple[str, ...]]) -> list[Item]:
        return [Item(code=k.value, label_en=v[0], label_ar=v[1]) for k, v in m.items()]

    mand = set(ref.MANDATORY) | set(ref.AIRPORT_MANDATORY)
    return EmergencyReference(
        scenarios=[
            Item(code=k.value, label_en=en, label_ar=ar, critical=k in mand)
            for k, (en, ar) in ref.SCENARIOS.items()
        ],
        event_types=items(ref.EVENT_TYPES),
        drill_types=[
            Item(
                code=k.value,
                label_en=v[0],
                label_ar=v[1],
                value=str(v[2]) if v[2] is not None else None,
                applies_to=list(v[4]),
            )
            for k, v in ref.DRILL_TYPES.items()
        ],
        agencies=[
            Item(code=k.value, label_en=v[0], label_ar=v[1], value=v[2])
            for k, v in ref.AGENCIES.items()
        ],
        roles=[
            Item(code=k.value, label_en=v[0], label_ar=v[1], value=v[2])
            for k, v in ref.ROLES.items()
        ],
        asset_types=[
            Item(code=k.value, label_en=v[0], label_ar=v[1], value=str(v[2]))
            for k, v in ref.ASSET_TYPES.items()
        ],
        check_items=[
            Item(
                code=k.value,
                label_en=v[0],
                label_ar=v[1],
                critical=v[2],
                applies_to=[t.value for t, a in ref.ASSET_TYPES.items() if k in a[4]],
            )
            for k, v in ref.CHECK_ITEMS.items()
        ],
        criteria=[
            Item(
                code=k.value,
                label_en=v[0],
                label_ar=v[1],
                critical=v[2],
                applies_to=[t.value for t, cs in ref.RELEVANT_DC.items() if k in cs],
            )
            for k, v in ref.CRITERIA.items()
        ],
        finding_categories=items(ref.FINDINGS),
        entry_states=items(ref.ENTRY_STATES),
        resolution_reasons=items(ref.RESOLUTIONS),
        response_types=items(ref.RESPONSES),
    )


# ---- settings ------------------------------------------------------------------------------------


def settings_read(db: Session, project_id: uuid.UUID) -> EmergencySettingsRead:
    c = ec.cfg(db, project_id)
    v = c.v
    return EmergencySettingsRead.model_validate(
        {
            "project_id": project_id,
            "emergency_register_from": c.register_from,
            "emergency_ptw_enforcement_from": c.enforcement_from,
            **{k: v[k] for k in ec.DEFAULTS},
            "erp_client_acceptance_required": c.client_acceptance,
            **{k: str(ec.q1(c.dec(k))) for k in PCT},
        }
    )


def read_settings(db: Session, p: Principal, project_id: uuid.UUID) -> EmergencySettingsRead:
    ec.project(db, p, project_id)
    ec.need(p, project_id, C.emergency_view, write=False)
    return settings_read(db, project_id)


def _loose(key: str) -> Any:
    return ec.err(
        422,
        ErrorCode.SETTING_LOOSENING,
        f"{key} may only be tightened (ER-9).",
        "يسمح بتشديد هذا الإعداد فقط.",
        field=key,
    )


def update_settings(
    db: Session, p: Principal, project_id: uuid.UUID, body: EmergencySettingsUpdate
) -> EmergencySettingsRead:
    pr = ec.project(db, p, project_id)
    p.require(project_id, C.erp_approve)
    s = ec.settings_row(db, project_id)
    cur = ec.cfg(db, project_id)
    before = {
        "emergency_register_from": s.emergency_register_from,
        "emergency_ptw_enforcement_from": s.emergency_ptw_enforcement_from,
        **dict(s.values or {}),
    }
    data = body.model_dump(exclude_unset=True, mode="json")
    vals = dict(s.values or {})
    today = ec.local_day()
    for k, raw in data.items():
        v: Any = raw
        if k == "emergency_register_from":
            d = body.emergency_register_from
            if d is None:
                if s.emergency_register_from is not None:
                    raise _loose(k)
                continue
            if d > today or d < pr.start_date:
                raise validation_error(k, "Between the project start and today.")
            if s.emergency_register_from is not None and d > s.emergency_register_from:
                raise _loose(k)
            s.emergency_register_from = d
            continue
        if k == "emergency_ptw_enforcement_from":
            d = body.emergency_ptw_enforcement_from
            if d is None:
                s.emergency_ptw_enforcement_from = None
                continue
            reg = s.emergency_register_from
            if reg is None or d < reg:
                raise validation_error(k, "On or after emergency_register_from.")
            erp = ec.erp_in_force(db, project_id)
            if erp is None or ec.erp_overdue(erp, today):
                raise ec.err(
                    422,
                    ErrorCode.ERP_NOT_APPROVED,
                    "Enforcement needs an Approved emergency response plan that is not overdue "
                    "(ER-2).",
                    "يتطلب الربط خطة استجابة للطوارئ معتمدة وغير متأخرة المراجعة.",
                    field=k,
                )
            s.emergency_ptw_enforcement_from = d
            continue
        if v is None:
            continue
        old = cur.v[k]
        if k in ONLY_LOWER and int(v) > int(old):
            raise _loose(k)
        if k in ONLY_RAISE and int(v) < int(old):
            raise _loose(k)
        if k in BOOL_TRUE_ONLY:
            was = cur.client_acceptance if k == "erp_client_acceptance_required" else bool(old)
            if was and not v:
                raise _loose(k)
        if k == "drill_minimums":
            for t, n in v.items():
                base = cur.minimum(DrillType(t))
                if n < 1 or (base is not None and n > base):
                    raise _loose(k)
            v = {**old, **v}
        if k == "asset_check_intervals":
            for t, n in v.items():
                if n < 1 or n > cur.interval(AssetType(t)):
                    raise _loose(k)
            v = {**old, **v}
        if k == "rescue_target_minutes":
            for t, n in v.items():
                if not 5 <= n <= 30 or n > int(old[t]):
                    raise _loose(k)
        if k == "rescue_team_min_members":
            for t, n in v.items():
                if not 2 <= n <= 8 or n < int(old[t]):
                    raise _loose(k)
        if k in PCT:
            v = str(ec.q1(Decimal(str(v))))
        if k == "gate_presence_excluded_site_ids":
            for sid in v:
                ec.site_or_422(db, project_id, uuid.UUID(str(sid)))
        vals[k] = v
    s.values = vals
    s.updated_at = now()
    s.updated_by_user_id = p.user.id
    db.flush()
    ec.clear_cache(db)
    after = {
        "emergency_register_from": s.emergency_register_from,
        "emergency_ptw_enforcement_from": s.emergency_ptw_enforcement_from,
        **dict(s.values or {}),
    }
    if after != before:
        audit.record(
            db,
            AuditAction.update,
            p.actor(project_id),
            entity_type=EntityType.emergency_settings,
            entity_id=project_id,
            project_id=project_id,
            before={k: str(x) if x is not None else None for k, x in before.items()},
            after={k: str(x) if x is not None else None for k, x in after.items()},
        )
    return settings_read(db, project_id)
