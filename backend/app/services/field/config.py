"""Phase 6d reference lists (§3.15) and project settings (§3.14): tighten-only values and the two
register switches (ISP-1 / EXE-3 and SRC-2), edited by the HSE Manager (193)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ApiError, ErrorCode, validation_error
from app.schemas.field import FieldReference, FieldSettingsRead, FieldSettingsUpdate
from app.schemas.field import FieldRefItem as Item
from app.services import audit
from app.services.field import common as fc
from app.services.field import reference as ref
from app.services.permissions import Principal

C = Capability
ONLY_RAISE = ("inspection_pass_mark_pct", "repeat_finding_days", "tbt_min_minutes")
ONLY_LOWER = ("contractor_audit_months", "system_audit_months", "first_audit_grace_days")
RANGES: dict[str, tuple[Decimal, Decimal]] = {
    "inspection_pass_mark_pct": (Decimal(50), Decimal(100)),
    "repeat_finding_days": (Decimal(14), Decimal(90)),
    "contractor_audit_months": (Decimal(3), Decimal(12)),
    "system_audit_months": (Decimal(6), Decimal(12)),
    "first_audit_grace_days": (Decimal(30), Decimal(90)),
    "tbt_min_minutes": (Decimal(5), Decimal(30)),
}
DATES = ("inspection_template_required_from", "toolbox_register_from")


def reference() -> FieldReference:
    def items(m: Mapping[Any, tuple[str, ...]]) -> list[Item]:
        return [Item(code=k.value, label_en=v[0], label_ar=v[1]) for k, v in m.items()]

    return FieldReference(
        item_types=items(ref.ITEM_TYPES),
        finding_severities=items(ref.SEVERITIES),
        audit_types=items(ref.AUDIT_TYPES),
        audit_finding_grades=items(ref.AUDIT_FINDINGS),
        audit_grades=[
            Item(code=k.value, label_en=v[0], label_ar=v[1], value=str(v[2]))
            for k, v in ref.AUDIT_GRADES.items()
        ],
        topic_categories=items(ref.topic_categories()),
        instructed_roles=items(ref.INSTRUCTED_ROLES),
        campaign_reasons=items(ref.CAMPAIGN_REASONS),
    )


def settings_read(db: Session, project_id: uuid.UUID) -> FieldSettingsRead:
    c = fc.cfg(db, project_id)
    return FieldSettingsRead.model_validate(
        {
            "project_id": project_id,
            "inspection_template_required_from": c.template_from,
            "toolbox_register_from": c.toolbox_from,
            **{k: c.v[k] for k in fc.DEFAULTS},
            **{
                k: str(fc.q1(c.dec(k))) for k in fc.PCT_KEYS if k != "critical_fail_warning_per_100"
            },
            "critical_fail_warning_per_100": str(c.dec("critical_fail_warning_per_100")),
        }
    )


def read_settings(db: Session, p: Principal, project_id: uuid.UUID) -> FieldSettingsRead:
    fc.project(db, p, project_id)
    fc.need(p, project_id, C.field_library_view, write=False)
    return settings_read(db, project_id)


def _loose(key: str) -> ApiError:
    return fc.err(
        422,
        ErrorCode.SETTING_LOOSENING,
        f"{key} may only be tightened (§3.14).",
        "يسمح بتشديد هذا الإعداد فقط.",
        field=key,
    )


def update_settings(
    db: Session, p: Principal, project_id: uuid.UUID, body: FieldSettingsUpdate
) -> FieldSettingsRead:
    pr = fc.project(db, p, project_id)
    p.require(project_id, C.field_library_publish)
    s = fc.settings_row(db, project_id)
    cur = fc.cfg(db, project_id)
    before: dict[str, Any] = {k: getattr(s, k) for k in DATES} | dict(s.values or {})
    data = body.model_dump(exclude_unset=True, mode="json")
    vals = dict(s.values or {})
    today = fc.local_day()
    for k, raw in data.items():
        if k in DATES:
            d = getattr(body, k)
            old = getattr(s, k)
            if d is None:
                if old is not None:
                    raise _loose(k)
                continue
            if d > today or d < pr.start_date:
                raise validation_error(k, "Between the project start and today.")
            if old is not None and d > old:
                raise _loose(k)
            setattr(s, k, d)
            continue
        if raw is None:
            continue
        v = Decimal(str(raw))
        if k in RANGES:
            lo, hi = RANGES[k]
            if not lo <= v <= hi:
                raise validation_error(k, f"Allowed {lo}–{hi}.")
        old_v = cur.dec(k)
        if k in ONLY_RAISE and v < old_v:
            raise _loose(k)
        if k in ONLY_LOWER and v > old_v:
            raise _loose(k)
        if k in fc.PCT_KEYS:
            vals[k] = str(v.quantize(Decimal("0.01") if "per_100" in k else Decimal("0.1")))
        else:
            vals[k] = int(v)
    s.values = vals
    s.updated_at = now()
    s.updated_by_user_id = p.user.id
    db.flush()
    fc.clear_cache(db)
    after: dict[str, Any] = {k: getattr(s, k) for k in DATES} | dict(s.values or {})
    if after != before:
        audit.record(
            db,
            AuditAction.update,
            p.actor(project_id),
            entity_type=EntityType.field_settings,
            entity_id=project_id,
            project_id=project_id,
            before={k: str(x) if x is not None else None for k, x in before.items()},
            after={k: str(x) if x is not None else None for k, x in after.items()},
        )
    return settings_read(db, project_id)
