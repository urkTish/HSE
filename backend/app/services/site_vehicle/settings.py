"""§3.5 Phase 7b project settings (capability 237, HSE Manager; audited)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode
from app.core.hse_enums import Weekday
from app.core.site_vehicle_enums import SiteVehDriverGroup, SiteVehPolicy
from app.models import TrainingCourse
from app.schemas.site_vehicle import SiteVehSettingsRead, SiteVehSettingsUpdate
from app.services import audit
from app.services.hse_common import Refs
from app.services.permissions import Principal, forbidden_error
from app.services.site_vehicle import common as c

C = Capability


def _range_err(key: str, lo: Any, hi: Any) -> Any:
    return c.err(
        422,
        ErrorCode.SETTING_OUT_OF_RANGE,
        f"{key} must be between {lo} and {hi}.",
        f"يجب أن تكون قيمة {key} بين {lo} و{hi}.",
        key,
        key=key,
        min=str(lo),
        max=str(hi),
    )


def settings_read(db: Any, project_id: uuid.UUID) -> SiteVehSettingsRead:
    s = c.settings_row(db, project_id)
    cf = c.cfg(db, project_id)
    return SiteVehSettingsRead(
        project_id=project_id,
        live=cf.live,
        site_vehicles_from=cf.live_from,
        driver_auth_validity_months=int(cf["driver_auth_validity_months"]),
        defensive_driving_code=cf["defensive_driving_code"],
        bus_driving_code=cf["bus_driving_code"],
        driver_hook_policy=cf.hook_policy,
        driver_auth_policy=cf.auth_policy,
        pre_use_required_groups=[SiteVehDriverGroup(g) for g in cf["pre_use_required_groups"]],
        rest_weekday=Weekday(cf["rest_weekday"]),
        journey_hint_km=int(cf["journey_hint_km"]),
        journey_hint_night_from=cf["journey_hint_night_from"],
        journey_hint_night_to=cf["journey_hint_night_to"],
        updated_at=s.updated_at,
        updated_by=Refs(db).user(s.updated_by_user_id),
    )


def get_settings(db: Any, p: Principal, project_id: uuid.UUID) -> SiteVehSettingsRead:
    c.project(db, p, project_id)
    if p.grant(project_id, C.site_vehicle_view) is None and (
        p.grant(project_id, C.site_vehicle_settings) is None
    ):
        raise forbidden_error()
    return settings_read(db, project_id)


def update_settings(
    db: Any, p: Principal, project_id: uuid.UUID, body: SiteVehSettingsUpdate
) -> SiteVehSettingsRead:
    c.project(db, p, project_id)
    p.require(project_id, C.site_vehicle_settings)
    s = c.settings_row(db, project_id)
    before: dict[str, Any] = {"site_vehicles_from": s.site_vehicles_from, **(s.values or {})}
    ch = body.changes()
    vals = dict(s.values or {})
    for key, (lo, hi) in c.RANGES.items():
        if key in ch and not lo <= ch[key] <= hi:
            raise _range_err(key, lo, hi)
    if "site_vehicles_from" in ch:
        d = ch.pop("site_vehicles_from")
        if d is not None and d > c.local_day() + timedelta(days=30):
            raise _range_err("site_vehicles_from", "—", "today + 30")
        s.site_vehicles_from = d
        if d is not None:
            c.ensure_courses(db)
    for code_key in ("defensive_driving_code", "bus_driving_code"):
        if code_key in ch:
            c.ensure_courses(db)
            known = db.scalar(select(TrainingCourse.id).where(TrainingCourse.code == ch[code_key]))
            if known is None:
                raise c.err(
                    422,
                    ErrorCode.SETTING_OUT_OF_RANGE,
                    "Not a course of the Phase 5 catalogue.",
                    "ليست دورة في كتالوج المرحلة 5.",
                    code_key,
                    key=code_key,
                )
    for k, val in ch.items():
        if k == "pre_use_required_groups":
            vals[k] = [SiteVehDriverGroup(g).value for g in dict.fromkeys(val)]
        else:
            vals[k] = val.value if isinstance(val, SiteVehPolicy | Weekday) else val
    s.values = vals
    s.updated_at = now()
    s.updated_by_user_id = p.user.id
    db.flush()
    c.clear_cache(db)
    after: dict[str, Any] = {"site_vehicles_from": s.site_vehicles_from, **vals}
    bf, af = audit.diff(before, after)
    if af or bf:
        audit.record(
            db,
            AuditAction.update,
            p.actor(project_id),
            entity_type=EntityType.site_vehicle_settings,
            entity_id=project_id,
            project_id=project_id,
            before=bf,
            after=af,
        )
    return settings_read(db, project_id)
