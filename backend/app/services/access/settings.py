"""Phase 2 project settings (spec 2-access-permits §3.22; capability 80, audited; HK-4)."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.access_enums import HookKind, HookPolicy
from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ApiError, ErrorCode, field_error
from app.models import AccessSettings
from app.schemas.access_common import HookRequirementRead
from app.schemas.access_settings import AccessSettingsRead, AccessSettingsUpdate
from app.schemas.inductions import HookProviderInfo
from app.services import audit, projects
from app.services.access import common, hooks
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error

MAPS = (
    "hook_requirements_by_adp_category",
    "hook_requirements_by_vehicle_category",
    "hook_requirements_by_crew_role",
)
PLAIN = [
    c.key
    for c in AccessSettings.__table__.columns
    if c.key not in ("project_id", "updated_at", "updated_by_user_id", "hook_policy", *MAPS)
]


def _providers(db: Session, s: AccessSettings) -> list[HookProviderInfo]:
    return [
        HookProviderInfo(
            kind=k,
            registered=hooks.registered_on_project(db, s.project_id, k),
            policy=HookPolicy((s.hook_policy or {}).get(k.value, HookPolicy.warn.value)),
            available_from_phase=hooks.AVAILABLE_FROM_PHASE[k],
        )
        for k in HookKind
    ]


def _map(m: dict[str, Any] | None) -> dict[Any, list[HookRequirementRead]]:
    return {k: [HookRequirementRead(**h) for h in v] for k, v in (m or {}).items()}


def to_read(db: Session, s: AccessSettings) -> AccessSettingsRead:
    data = {k: getattr(s, k) for k in PLAIN}
    return AccessSettingsRead(
        project_id=s.project_id,
        **data,
        hook_policy={
            k: HookPolicy((s.hook_policy or {}).get(k.value, HookPolicy.warn.value))
            for k in HookKind
        },
        hook_providers=_providers(db, s),
        hook_requirements_by_adp_category=_map(s.hook_requirements_by_adp_category),
        hook_requirements_by_vehicle_category=_map(s.hook_requirements_by_vehicle_category),
        hook_requirements_by_crew_role=_map(s.hook_requirements_by_crew_role),
        updated_at=s.updated_at,
        updated_by=Refs(db).user(s.updated_by_user_id),
    )


def read(db: Session, p: Principal, project_id: uuid.UUID) -> AccessSettingsRead:
    project = projects.get_visible(db, p, project_id)
    # Read is open to anyone who can see the project's access module (capability 46/73/75).
    if (
        not p.is_manager
        and p.grant(project.id, Capability.access_settings_edit) is None
        and not any(
            p.grant(project.id, c) is not None
            for c in (Capability.worker_view, Capability.access_works_view, Capability.gate_manage)
        )
    ):
        raise forbidden_error()
    return to_read(db, common.settings(db, project.id))


def _snap(s: AccessSettings) -> dict[str, Any]:
    return common.jsonable({k: getattr(s, k) for k in (*PLAIN, "hook_policy", *MAPS)})


def update(
    db: Session, p: Principal, project_id: uuid.UUID, body: AccessSettingsUpdate
) -> AccessSettingsRead:
    project = projects.get_visible(db, p, project_id)
    p.ensure_writer()
    p.require(project.id, Capability.access_settings_edit)
    s = common.settings(db, project.id)
    before = _snap(s)
    ch = body.changes()
    if "hook_policy" in ch:
        policy = {
            getattr(k, "value", k): getattr(v, "value", v) for k, v in ch.pop("hook_policy").items()
        }
        for k, v in policy.items():
            registered = hooks.registered_on_project(db, project.id, HookKind(k))
            if v == HookPolicy.block.value and not registered:
                raise ApiError(
                    422,
                    ErrorCode.HOOK_PROVIDER_MISSING,
                    f"No provider is registered for {k}; it can only warn until its module is live "
                    "(HK-4).",
                    "لا يوجد مزوّد مسجل لهذا المتطلب؛ يبقى تنبيهًا حتى تشغيل الوحدة.",
                    errors=[
                        field_error(
                            f"hook_policy.{k}", "Provider missing.", "HOOK_PROVIDER_MISSING"
                        )
                    ],
                )
        s.hook_policy = {**(s.hook_policy or {}), **policy}
    for key in MAPS:
        if key in ch:
            raw = ch.pop(key)
            setattr(
                s,
                key,
                {
                    getattr(k, "value", k): [
                        common.jsonable(h if isinstance(h, dict) else h.model_dump()) for h in v
                    ]
                    for k, v in raw.items()
                },
            )
    for k in ("alert_schedule_long_days", "alert_schedule_short_hours"):
        if k in ch:
            vals = sorted({int(x) for x in ch[k]}, reverse=True)
            if any(x < 0 for x in vals):
                raise ApiError(
                    422, ErrorCode.VALIDATION_ERROR, "Alert offsets cannot be negative.",
                    errors=[field_error(k, "Alert offsets cannot be negative.")],
                )  # fmt: skip
            ch[k] = vals
    for k, v in ch.items():
        setattr(s, k, v)
    s.updated_at = now()
    s.updated_by_user_id = p.user.id
    db.flush()
    bf, af = audit.diff(before, _snap(s))
    if af:
        audit.record(
            db,
            AuditAction.settings_changed,
            p.actor(project.id),
            entity_type=EntityType.access_settings,
            entity_id=project.id,
            project_id=project.id,
            before=bf,
            after=af,
            details={"scope": "access_settings"},
        )
    return to_read(db, s)
