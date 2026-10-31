"""Quality settings and the sector profile (spec 8-quality §A.2 Q-PRF, §A.3 Q-SET).

`q_settings.values` holds only the keys a project changed; reads merge them over the registry
defaults of `app.core.quality.common.SETTINGS`, which declares every key of every part, so later
parts add no settings code or UI (Q-SET-01)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, ProjectType
from app.core.errors import ApiError, ErrorCode
from app.core.quality.common import (
    SETTINGS,
    SETTINGS_BY_KEY,
    QSectorProfile,
    QSettingKind,
    SettingDef,
    defaults,
)
from app.models import Project
from app.models.quality import QSettings
from app.services import audit
from app.services.permissions import Principal, forbidden_error
from app.services.quality import common as qc

C = Capability
K = QSettingKind


def values(db: Session, project_id: uuid.UUID) -> dict[str, Any]:
    out = defaults()
    row = db.get(QSettings, project_id)
    if row is not None:
        out.update({k: v for k, v in (row.values or {}).items() if k in SETTINGS_BY_KEY})
    return out


def value(db: Session, project_id: uuid.UUID, key: str) -> Any:
    return values(db, project_id)[key]


def dec(db: Session, project_id: uuid.UUID, key: str) -> Decimal | None:
    v = value(db, project_id, key)
    return None if v is None else Decimal(str(v))


def suggested_profile(project: Project) -> QSectorProfile:
    """Q-PRF-06: a `logistics` project defaults to logistics; every other type to construction."""
    return (
        QSectorProfile.logistics
        if project.project_type == ProjectType.logistics
        else QSectorProfile.construction
    )


def _out_of_range(d: SettingDef, why: str) -> ApiError:
    return qc.err(
        422,
        ErrorCode.SETTING_OUT_OF_RANGE,
        f"{d.key}: {why}",
        f"{d.ar}: القيمة خارج النطاق المسموح.",
        key=d.key,
    )


def _num(d: SettingDef, v: Any, integer: bool) -> Any:
    if isinstance(v, bool):
        raise _out_of_range(d, "a number is required")
    try:
        n = Decimal(str(v))
    except (InvalidOperation, ValueError) as exc:
        raise _out_of_range(d, "a number is required") from exc
    if integer and n != n.to_integral_value():
        raise _out_of_range(d, "a whole number is required")
    if (d.min is not None and n < d.min) or (d.max is not None and n > d.max):
        raise _out_of_range(d, f"allowed {d.min}–{d.max}")
    return int(n) if integer else str(n)


def validate(d: SettingDef, v: Any) -> Any:
    """The stored form of a value, or 422 SETTING_OUT_OF_RANGE (§A.3 "Allowed")."""
    if d.kind == K.int:
        return _num(d, v, True)
    if d.kind == K.decimal:
        return _num(d, v, False)
    if d.kind == K.decimal_or_null:
        return None if v is None else _num(d, v, False)
    if d.kind == K.bool:
        if not isinstance(v, bool):
            raise _out_of_range(d, "true or false")
        return v
    if d.kind == K.enum:
        if v not in d.options:
            raise _out_of_range(d, f"one of {', '.join(d.options)}")
        return v
    if d.kind == K.set:
        if not isinstance(v, list) or any(x not in d.options for x in v):
            raise _out_of_range(d, f"a subset of {', '.join(d.options)}")
        return sorted(set(v), key=list(d.options).index)
    if d.kind == K.map:
        if not isinstance(v, dict) or set(v) != set(d.keys):
            raise _out_of_range(d, f"keys {', '.join(d.keys)}")
        integer = all(isinstance(x, int) for x in (d.default or {}).values())
        return {k: _num(d, v[k], integer) for k in d.keys}
    if d.kind == K.methods_map:
        if not isinstance(v, dict) or set(v) != set(d.keys):
            raise _out_of_range(d, f"keys {', '.join(d.keys)}")
        out = {}
        for k in d.keys:
            ms = v[k]
            if not isinstance(ms, list) or not ms or any(m not in d.options for m in ms):
                raise _out_of_range(d, f"{k}: a non-empty subset of {', '.join(d.options)}")
            out[k] = sorted(set(ms), key=list(d.options).index)
        return out
    if not isinstance(v, (dict, list)):
        raise _out_of_range(d, "JSON object expected")
    return v


def _ensure_row(db: Session, project_id: uuid.UUID) -> QSettings:
    row = db.get(QSettings, project_id)
    if row is None:
        row = QSettings(project_id=project_id, values={})
        db.add(row)
        db.flush()
    return row


def _can_read(p: Principal, project_id: uuid.UUID) -> bool:
    return any(
        p.grant(project_id, c) is not None
        for c in (C.quality_view, C.quality_settings, C.ncr_raise, C.quality_acknowledge)
    )


def read(db: Session, p: Principal, project_id: uuid.UUID) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    if not _can_read(p, project.id):
        raise forbidden_error()
    row = db.get(QSettings, project.id)
    return {
        "project_id": project.id,
        "sector_profile": row.sector_profile if row else None,
        "suggested_profile": suggested_profile(project),
        "quality_start_date": row.quality_start_date if row else None,
        "values": values(db, project.id),
        "changed_keys": sorted((row.values or {}).keys()) if row else [],
        "profile_changed_at": row.profile_changed_at if row else None,
        "updated_at": row.updated_at if row else None,
        "can_edit": p.grant(project.id, C.quality_settings) is not None,
    }


def schema() -> list[dict[str, Any]]:
    return [
        {
            "key": d.key,
            "part": d.part,
            "kind": d.kind,
            "default": d.default,
            "label_en": d.en,
            "label_ar": d.ar,
            "min": str(d.min) if d.min is not None else None,
            "max": str(d.max) if d.max is not None else None,
            "options": list(d.options),
            "keys": list(d.keys),
            "profile": d.profile,
        }
        for d in SETTINGS
    ]


def patch(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    changes: dict[str, Any] | None,
    quality_start_date: date | None = None,
    clear_start: bool = False,
) -> dict[str, Any]:
    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    p.require(project.id, C.quality_settings)
    row = _ensure_row(db, project.id)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    current = values(db, project.id)
    stored = dict(row.values or {})
    for key, raw in (changes or {}).items():
        d = SETTINGS_BY_KEY.get(key)
        if d is None:
            raise qc.err(
                422, ErrorCode.SETTING_OUT_OF_RANGE, f"Unknown setting {key}.", "إعداد غير معروف."
            )
        v = validate(d, raw)
        if v != current.get(key):
            before[key] = current.get(key)
            after[key] = v
            stored[key] = v
    if quality_start_date is not None or clear_start:
        before["quality_start_date"] = row.quality_start_date
        after["quality_start_date"] = None if clear_start else quality_start_date
        row.quality_start_date = None if clear_start else quality_start_date
    row.values = stored
    row.updated_at = now()
    row.updated_by_user_id = p.user.id
    db.flush()
    if after:
        audit.record(
            db,
            AuditAction.settings_changed,
            p.actor(project.id),
            entity_type=EntityType.q_settings,
            project_id=project.id,
            before=before,
            after=after,
        )
    return read(db, p, project.id)


def set_profile(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    profile: QSectorProfile,
    why: str | None,
    quality_start_date: date | None = None,
) -> dict[str, Any]:
    """Q-PRF-01 first choice (no reason) and Q-PRF-03 change (reason ≥ 20, audited old / new).
    Records made under the other profile stay (Q-PRF-04 lets them be finished)."""
    from app.services.quality import rpm  # noqa: PLC0415

    project = qc.get_project(db, p, project_id)
    qc.writable(project, p)
    p.require(project.id, C.quality_settings)
    row = _ensure_row(db, project.id)
    old = row.sector_profile
    if old == profile:
        return read(db, p, project.id)
    details: dict[str, Any] = {}
    if old is not None:
        details["reason"] = qc.reason(why, 20)
        row.profile_changed_at = now()
    row.sector_profile = profile
    if quality_start_date is not None:
        row.quality_start_date = quality_start_date
    row.updated_at = now()
    row.updated_by_user_id = p.user.id
    db.flush()
    rpm.seed_defaults(db, project, profile, p.user.id)
    audit.record(
        db,
        AuditAction.settings_changed,
        p.actor(project.id),
        entity_type=EntityType.q_settings,
        project_id=project.id,
        before={"sector_profile": old},
        after={"sector_profile": profile},
        details=details or None,
    )
    return read(db, p, project.id)
