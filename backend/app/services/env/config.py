"""6e reference lists and project settings (spec 6e-environmental §3.16, §3.17).

Settings are edited by the HSE Manager only (213); "Allowed" ranges are enforced by the schema,
loosening values answer 422 SETTING_LOOSENING; every change is audited."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.core.access_enums import OpsEventType
from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.env_enums import (
    AspectCondition,
    Averaging,
    BackgroundSource,
    ComplaintCategory,
    ComplaintChannel,
    LimitSource,
    NoisePeriod,
    Parameter,
    PointSource,
    Schedule,
    SpillSource,
    SpillSurface,
    WaterSource,
)
from app.core.errors import ErrorCode, validation_error
from app.schemas.env import EnvReference, EnvRefItem, EnvSettingsRead, EnvSettingsUpdate, LimitRow
from app.services.env import common as ec
from app.services.env import reference as rf
from app.services.permissions import Principal

C = Capability


def _items(labels: Any) -> list[EnvRefItem]:
    return [
        EnvRefItem(code=getattr(k, "value", k), label_en=v[0], label_ar=v[1])
        for k, v in labels.items()
    ]


PLAIN_AR: dict[str, dict[str, str]] = {
    "condition": {"normal": "عادية", "abnormal": "غير عادية", "emergency": "طارئة"},
    "schedule": {"continuous": "مستمر", "daily": "يومي", "weekly": "أسبوعي", "monthly": "شهري",
                 "campaign": "حسب الحاجة"},
    "period": {"any": "أي وقت", "day": "نهار", "night": "ليل"},
    "averaging": {"15min": "15 دقيقة", "1h": "ساعة", "24h": "24 ساعة", "spot": "عينة لحظية",
                  "measurement": "قياس"},
    "limit_source": {"ncec": "المركز الوطني للرقابة على الالتزام البيئي", "municipality": "البلدية",
                     "permit_condition": "اشتراط التصريح", "client": "العميل",
                     "project_trigger": "حد المشروع"},
    "point_source": {"manual": "يدوي", "station": "محطة", "visual": "مرئي"},
    "spill_source": {"plant_leak": "تسرب من معدة", "refuelling": "تزويد بالوقود",
                     "container_failure": "تلف حاوية", "tanker": "صهريج", "other": "أخرى"},
    "surface": {"paved": "سطح مرصوف", "unpaved_soil": "تربة غير مرصوفة", "drain": "مصرف",
                "water_body": "مسطح مائي"},
    "water_source": {"network": "شبكة", "tanker": "صهريج",
                     "groundwater_dewatering_reuse": "إعادة استخدام مياه النزح",
                     "treated_effluent": "مياه معالجة"},
    "complaint_channel": {"phone": "هاتف", "email": "بريد إلكتروني", "in_person": "حضورياً",
                          "via_client": "عن طريق العميل", "via_authority": "عن طريق جهة رسمية"},
    "complaint_category": {"dust": "غبار", "noise": "ضوضاء", "odour": "روائح", "waste": "نفايات",
                           "water": "مياه", "mud_on_road": "طين على الطريق", "light": "إضاءة",
                           "other": "أخرى"},
    "background_source": {"ncm_warning": "إنذار المركز الوطني للأرصاد",
                          "aocc": "مركز عمليات المطار",
                          "visual_regional": "غبار إقليمي مرئي", "other": "أخرى"},
}  # fmt: skip
PLAIN: dict[str, type[Enum]] = {
    "condition": AspectCondition,
    "schedule": Schedule,
    "period": NoisePeriod,
    "averaging": Averaging,
    "limit_source": LimitSource,
    "point_source": PointSource,
    "spill_source": SpillSource,
    "surface": SpillSurface,
    "water_source": WaterSource,
    "complaint_channel": ComplaintChannel,
    "complaint_category": ComplaintCategory,
    "background_source": BackgroundSource,
}


def _plain(name: str) -> list[EnvRefItem]:
    ar = PLAIN_AR[name]
    return [
        EnvRefItem(code=str(m.value), label_en=str(m.value).replace("_", " ").capitalize(),
                   label_ar=ar[str(m.value)])
        for m in PLAIN[name]
    ]  # fmt: skip


def limit_library() -> list[LimitRow]:
    out = []
    for (pa, av), (al, li, lo, hi, src, _ref) in rf.DL.items():
        out.append(
            LimitRow(
                parameter=pa, averaging=av, alert_value=ec.s1(al), limit_value=ec.s1(li),
                limit_min=ec.s1(lo), limit_max=ec.s1(hi), source=LimitSource(src),
            )
        )  # fmt: skip
    for na, (_en, _ar, day, night) in rf.NA.items():
        for per, lim in ((NoisePeriod.day, day), (NoisePeriod.night, night)):
            out.append(
                LimitRow(
                    parameter=Parameter.laeq, averaging=Averaging.h1, period=per,
                    noise_area_category=na, alert_value=ec.s1(lim - 3), limit_value=ec.s1(lim),
                    source=LimitSource.ncec,
                )
            )  # fmt: skip
    return out


def reference(db: Session, p: Principal) -> EnvReference:
    lists: dict[str, list[EnvRefItem]] = {
        "aspects": _items(rf.AS_LABELS),
        "impacts": _items(rf.IM_LABELS),
        "permit_types": [
            EnvRefItem(code=k.value, label_en=v[0], label_ar=v[1],
                       detail=f"{v[2]} · {'expires' if v[3] else 'no expiry'}")
            for k, v in rf.PT_INFO.items()
        ],
        "issuers": _items(rf.IS_LABELS),
        "provider_kinds": _items(rf.PK_LABELS),
        "licence_activities": _items(rf.LA_LABELS),
        "waste_classes": _items(rf.WC_LABELS),
        "routes": _items(rf.TR_LABELS),
        "streams": [
            EnvRefItem(code=k, label_en=v[0], label_ar=v[1],
                       detail=f"{v[2].value} · {v[3].value} · {v[4]}")
            for k, v in rf.WS.items()
        ],
        "storage_area_types": _items(rf.SA_LABELS),
        "instrument_kinds": _items(rf.IK_LABELS),
        "point_kinds": _items(rf.MPK_LABELS),
        "parameters": [
            EnvRefItem(code=k.value, label_en=v[0], label_ar=v[1], detail=f"{v[2]} · {v[3]}–{v[4]}")
            for k, v in rf.PA.items()
        ],
        "noise_areas": [
            EnvRefItem(code=k.value, label_en=v[0], label_ar=v[1], detail=f"{v[2]} / {v[3]}")
            for k, v in rf.NA.items()
        ],
        "spill_substances": _items(rf.SS_LABELS),
        "exceedance_causes": _items(rf.EC_LABELS),
        **{name: _plain(name) for name in PLAIN},
    }  # fmt: skip
    return EnvReference(lists=lists, limit_library=limit_library())


# ---- settings ------------------------------------------------------------------------------------


def settings_read(db: Session, project_id: uuid.UUID) -> EnvSettingsRead:
    c = ec.cfg(db, project_id)
    v = c.v
    return EnvSettingsRead(
        project_id=project_id,
        env_notifications_from=c.notifications_from,
        **{k: (str(ec.q1(Decimal(str(x)))) if k.endswith("_pct") or k == "spill_reportable_l"
               else x) for k, x in v.items()},
    )  # fmt: skip


def get_settings(db: Session, p: Principal, project_id: uuid.UUID) -> EnvSettingsRead:
    ec.view_grant(db, p, project_id)
    return settings_read(db, project_id)


# key → direction: "lower" (only lower), "raise" (only raise), "add" (set may only grow),
# "remove" (set may only shrink), "true" (true only)
TIGHTEN = {
    "manifest_return_days": "lower",
    "weight_discrepancy_pct": "lower",
    "mwan_manifest_required_for": "add",
    "haz_storage_max_days": "lower",
    "containment_min_pct": "raise",
    "spill_reportable_l": "lower",
    "airside_spill_always_reportable": "true",
    "data_capture_pct": "raise",
    "background_ops_event_types": "remove",
    "post_storm_check_hours": "lower",
    "exceedance_review_days": "lower",
    "complaint_response_days": "lower",
    "authority_complaint_response_days": "lower",
    "aspect_review_months": "lower",
    "diversion_target_pct": "raise",
    "permit_alert_days": "add",
    "provider_licence_alert_days": "add",
}


def _loose(k: str) -> Any:
    return ec.err(
        422, ErrorCode.SETTING_LOOSENING, f"{k} may only be tightened.",
        f"لا يمكن تخفيف الإعداد {k}.", k,
    )  # fmt: skip


def update_settings(
    db: Session, p: Principal, project_id: uuid.UUID, body: EnvSettingsUpdate
) -> EnvSettingsRead:
    ec.project(db, p, project_id)
    p.require(project_id, C.env_settings)
    data = body.model_dump(exclude_unset=True)
    row = ec.settings_row(db, project_id)
    cur = ec.cfg(db, project_id)
    before = {**cur.v, "env_notifications_from": cur.notifications_from}
    vals = dict(row.values or {})
    for k, new in data.items():
        if k == "env_notifications_from":
            if new is None or (cur.notifications_from is not None and new > cur.notifications_from):
                raise _loose(k)
            row.env_notifications_from = new
            continue
        old = cur.v[k]
        rule = TIGHTEN.get(k)
        if k in ("permit_alert_days", "provider_licence_alert_days"):
            if any(not 0 <= int(x) <= 180 for x in new):
                raise validation_error(k, "Days must be between 0 and 180.")
            new = sorted({int(x) for x in new}, reverse=True)  # noqa: PLW2901
        if k == "background_ops_event_types":
            allowed = {t.value for t in OpsEventType}
            if any(x not in allowed for x in new):
                raise validation_error(k, "Use Phase 2 ops event types.")
        if k == "mwan_manifest_required_for":
            new = sorted({getattr(x, "value", x) for x in new})  # noqa: PLW2901
        if rule == "lower" and Decimal(str(new)) > Decimal(str(old)):
            raise _loose(k)
        if rule == "raise" and Decimal(str(new)) < Decimal(str(old)):
            raise _loose(k)
        if rule == "add" and not set(old) <= set(new):
            raise _loose(k)
        if rule == "remove" and not set(new) <= set(old):
            raise _loose(k)
        if rule == "true" and new is not True:
            raise _loose(k)
        if k == "noise_night_start" and new > old:
            raise _loose(k)
        if k == "noise_day_start" and new < old:
            raise _loose(k)
        if k in ("monitoring_warning_pct", "custody_warning_pct") and Decimal(str(new)) < Decimal(
            str(old)
        ):
            raise _loose(k)
        vals[k] = str(new) if isinstance(new, Decimal) else new
    row.values = vals
    row.updated_at = now()
    row.updated_by_user_id = p.user.id
    db.flush()
    ec.clear_cache(db)
    after = {**ec.cfg(db, project_id).v, "env_notifications_from": row.env_notifications_from}
    from app.services import audit  # noqa: PLC0415

    audit.record(
        db, AuditAction.update, p.actor(project_id), entity_type=EntityType.env_settings,
        entity_id=project_id, project_id=project_id,
        before={k: _j(before.get(k)) for k in data}, after={k: _j(after.get(k)) for k in data},
    )  # fmt: skip
    return settings_read(db, project_id)


def _j(v: Any) -> Any:
    return v.isoformat() if isinstance(v, date) else v
