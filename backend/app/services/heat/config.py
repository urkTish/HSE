"""Phase 6b reference lists, project settings (§3.14, HS-1, HS-6, HS-7) and the org-wide regime
table (§3.4, HS-5)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType
from app.core.errors import ErrorCode, validation_error
from app.core.heat_enums import Regime, Workload
from app.models import HeatRegimeLimit, HseSettings
from app.schemas.heat import (
    HeatReference,
    HeatRefItem,
    HeatSettingsRead,
    HeatSettingsUpdate,
    RegimeLimitRow,
    RegimeTableRead,
    RegimeTableUpdate,
)
from app.services import audit
from app.services.heat import common as hc
from app.services.heat import reference as ref
from app.services.permissions import Principal, forbidden_error

C = Capability


def _items(m: Mapping[Any, tuple[str, str]], **extra: Any) -> list[HeatRefItem]:
    out = []
    for k, v in m.items():
        out.append(HeatRefItem(code=k.value, label_en=v[0], label_ar=v[1], **extra))
    return out


def reference() -> HeatReference:
    return HeatReference(
        workloads=[
            HeatRefItem(code=k.value, label_en=en, label_ar=ar, value=w)
            for k, (en, ar, w) in ref.WORKLOADS.items()
        ],
        clothing=[
            HeatRefItem(code=k.value, label_en=en, label_ar=ar, value=str(hc.CAF[k]))
            for k, (en, ar) in ref.CLOTHING.items()
        ],
        hood_adjustment_c=str(hc.HOOD),
        regimes=[
            HeatRefItem(
                code=k.value,
                label_en=en,
                label_ar=ar,
                value=str(hc.REST_MIN[k]) if k in hc.REST_MIN else None,
            )
            for k, (en, ar) in ref.REGIMES.items()
        ],
        plan_types=_items(ref.PLAN_TYPES),
        welfare_items=[
            HeatRefItem(
                code=k.value,
                label_en=en,
                label_ar=ar,
                critical=k in ref.CRITICAL,
                na_allowed=k in ref.NA_ALLOWED,
            )
            for k, (en, ar) in ref.WELFARE.items()
        ],
        patrol_outcomes=_items(ref.OUTCOMES),
        review_questions=_items(ref.QUESTIONS),
        station_types=_items(ref.STATION_TYPES),
        cooling=_items(ref.COOLING),
        exemption_reasons=_items(ref.EXEMPTION_REASONS),
        water_advice_en=hc.WATER[0],
        water_advice_ar=hc.WATER[1],
    )


# ---- settings ------------------------------------------------------------------------------------


def settings_read(db: Session, project_id: uuid.UUID) -> HeatSettingsRead:
    c = hc.cfg(db, project_id)
    v = c.v
    return HeatSettingsRead.model_validate(
        {
            "project_id": project_id,
            "heat_register_from": c.register_from,
            "heat_ptw_enforcement_from": c.enforcement_from,
            **{k: v[k] for k in hc.DEFAULTS},
            "wbgt_limit_offset_c": str(hc.q1(c.dec("wbgt_limit_offset_c"))),
            "wbgt_component_tolerance_c": str(hc.q1(c.dec("wbgt_component_tolerance_c"))),
            "standard_shift_hours": str(hc.q1(c.dec("standard_shift_hours"))),
            "cool_water_max_c": str(hc.q1(c.dec("cool_water_max_c"))),
            "wbgt_coverage_warning_pct": str(hc.q1(c.dec("wbgt_coverage_warning_pct"))),
            "welfare_compliance_warning_pct": str(hc.q1(c.dec("welfare_compliance_warning_pct"))),
            "ban_patrol_coverage_warning_pct": str(hc.q1(c.dec("ban_patrol_coverage_warning_pct"))),
            "trade_workload_defaults": {
                **hc.TRADE_DEFAULTS,
                **(v["trade_workload_defaults"] or {}),
            },
            "midday_ban_period": c.ban_period,
            "midday_ban_hours": c.ban_hours,
            "midday_ban_prewarn_minutes": c.ban_prewarn,
        }
    )


def read_settings(db: Session, p: Principal, project_id: uuid.UUID) -> HeatSettingsRead:
    hc.project(db, p, project_id)
    hc.need(p, project_id, C.heat_view, write=False)
    return settings_read(db, project_id)


def _loose(key: str) -> Any:
    return hc.err(
        422,
        ErrorCode.SETTING_LOOSENING,
        f"{key} may only be tightened.",
        "يسمح بتشديد هذا الإعداد فقط.",
        field=key,
    )


def _contains(outer: dict[str, str], inner: tuple[str, str]) -> bool:
    """MM-DD range `outer` contains `inner` (no year wrap in the seeded data)."""
    return outer["start_mmdd"] <= inner[0] and inner[1] <= outer["end_mmdd"]


def coverage_gaps(db: Session, project_id: uuid.UUID) -> list[str]:
    zones = hc.zone_map(db, project_id)
    cov = hc.covering(db, project_id)
    return [zones[z].code for z in hc.required_zone_ids(db, project_id) if z not in cov]


def update_settings(
    db: Session, p: Principal, project_id: uuid.UUID, body: HeatSettingsUpdate
) -> HeatSettingsRead:
    pr = hc.project(db, p, project_id)
    p.require(project_id, C.heat_settings_edit)
    s = hc.settings_row(db, project_id)
    cur = hc.cfg(db, project_id)
    before = {
        "heat_register_from": s.heat_register_from,
        "heat_ptw_enforcement_from": s.heat_ptw_enforcement_from,
        **dict(s.values or {}),
    }
    data = body.model_dump(exclude_unset=True, mode="json")
    vals = dict(s.values or {})
    today = hc.local_day()
    for k, raw in data.items():
        v: Any = raw
        if k == "heat_register_from":
            if v is None:
                if s.heat_register_from is not None:
                    raise _loose(k)
                continue
            d = body.heat_register_from
            assert d is not None  # noqa: S101
            if d > today or d < pr.start_date:
                raise validation_error(k, "Between the project start and today.")
            if s.heat_register_from is not None and d > s.heat_register_from:
                raise _loose(k)
            s.heat_register_from = d
            continue
        if k == "heat_ptw_enforcement_from":
            d = body.heat_ptw_enforcement_from
            if d is None:
                s.heat_ptw_enforcement_from = None
                continue
            reg = s.heat_register_from
            if reg is None or d < reg:
                raise validation_error(k, "On or after heat_register_from.")
            gaps = coverage_gaps(db, project_id)
            if gaps:
                raise hc.err(
                    422,
                    ErrorCode.HEAT_COVERAGE_INCOMPLETE,
                    "Every required zone needs an active monitoring point: " + ", ".join(gaps),
                    "كل منطقة مطلوبة تحتاج نقطة قياس فعالة: " + "، ".join(gaps),
                    zones=gaps,
                )
            s.heat_ptw_enforcement_from = d
            continue
        if v is None:
            continue
        old = cur.v[k]
        if k == "heat_controls_period":
            if not _contains(v, (old["start_mmdd"], old["end_mmdd"])):
                raise _loose(k)
            hs = db.get(HseSettings, project_id)
            season = (
                (hs.heat_season_start or "06-01", hs.heat_season_end or "09-30")
                if hs
                else ("06-01", "09-30")
            )
            ban = (cur.ban_period["start_mmdd"], cur.ban_period["end_mmdd"])
            if not (_contains(v, season) and _contains(v, ban)):
                raise hc.err(
                    422,
                    ErrorCode.PERIOD_TOO_SHORT,
                    "The controls period must contain the heat season and the midday-ban period.",
                    "يجب أن تشمل فترة الضوابط موسم الحرارة وفترة حظر الظهيرة.",
                    field=k,
                )
        elif k == "heat_monitoring_hours":
            if v["start_local"] > old["start_local"] or v["end_local"] < old["end_local"]:
                raise _loose(k)
        elif k == "wbgt_limit_offset_c":
            dv = Decimal(str(v))
            if not Decimal("-3.0") <= dv <= Decimal("0.0"):
                raise validation_error(k, "−3.0 … 0.0.")
            v = str(hc.q1(dv))
        elif k == "headline_workload":
            if v == Workload.light.value:
                raise validation_error(k, "moderate, heavy or very_heavy.")
        elif k == "trade_workload_defaults":
            base = {**hc.TRADE_DEFAULTS, **(old or {})}
            for trade, wl in v.items():
                prev = Workload(base.get(trade, "moderate"))
                if hc.WL_RANK[Workload(wl)] < hc.WL_RANK[prev]:
                    raise _loose(k)
            v = {**(old or {}), **v}
        elif k == "acclimatisation_schedules":
            for t in ("new_worker", "returner"):
                o, n = list(old[t]), list(v[t])
                if len(n) < len(o) or any(not 0 < x <= 100 for x in n):
                    raise _loose(k)
                if any(n[i] > o[i] for i in range(len(o))):
                    raise _loose(k)
        elif k == "heat_fitness_required":
            if old and not v:
                raise _loose(k)
        elif k in (
            "wbgt_component_tolerance_c",
            "standard_shift_hours",
            "cool_water_max_c",
            "wbgt_coverage_warning_pct",
            "welfare_compliance_warning_pct",
            "ban_patrol_coverage_warning_pct",
        ):
            v = str(hc.q1(Decimal(str(v))))
        vals[k] = v
    s.values = vals
    s.updated_at = now()
    s.updated_by_user_id = p.user.id
    db.flush()
    hc.clear_cache(db)
    after = {
        "heat_register_from": s.heat_register_from,
        "heat_ptw_enforcement_from": s.heat_ptw_enforcement_from,
        **dict(s.values or {}),
    }
    if after != before:
        audit.record(
            db,
            AuditAction.update,
            p.actor(project_id),
            entity_type=EntityType.heat_settings,
            entity_id=project_id,
            project_id=project_id,
            before={k: str(x) if x is not None else None for k, x in before.items()},
            after={k: str(x) if x is not None else None for k, x in after.items()},
        )
    return settings_read(db, project_id)


# ---- regime table --------------------------------------------------------------------------------


def _rows(db: Session) -> RegimeTableRead:
    t = hc.table(db)
    rows = [
        RegimeLimitRow(basis=b, regime=r, workload=w, limit_c=str(hc.q1(v)))
        for (b, r, w), v in sorted(
            t.items(),
            key=lambda kv: (kv[0][0].value, hc.ORDER[kv[0][1]], hc.WL_RANK[kv[0][2]]),
        )
    ]
    return RegimeTableRead(rows=rows)


def read_regime_table(db: Session, p: Principal) -> RegimeTableRead:
    if not p.has_any(C.heat_view):
        raise forbidden_error()
    return _rows(db)


def update_regime_table(db: Session, p: Principal, body: RegimeTableUpdate) -> RegimeTableRead:
    if not p.is_manager:
        raise forbidden_error()
    hc.ensure_table(db)
    from sqlalchemy import select  # noqa: PLC0415

    rows = {(r.basis, r.regime, r.workload): r for r in db.scalars(select(HeatRegimeLimit))}
    changes: list[tuple[HeatRegimeLimit, Decimal]] = []
    for x in body.rows:
        if x.regime in (Regime.R4, Regime.unknown):
            raise validation_error("rows", "Only R0…R3 have limits.")
        r = rows[(x.basis, x.regime, x.workload)]
        nv = hc.q1(x.limit_c)
        if nv > r.limit_c:
            raise hc.err(
                422,
                ErrorCode.REGIME_LOOSENING,
                "Regime limits may only be lowered (HS-5).",
                "يمكن خفض حدود نظام العمل فقط.",
                field="rows",
            )
        if nv != r.limit_c:
            changes.append((r, nv))
    for r, nv in changes:
        before = {"limit_c": str(r.limit_c)}
        r.limit_c = nv
        r.changed_at = now()
        r.changed_by_user_id = p.user.id
        audit.record(
            db,
            AuditAction.update,
            p.actor(None),
            entity_type=EntityType.heat_regime_table,
            entity_id=r.id,
            before={**before, "cell": f"{r.basis.value}.{r.regime.value}.{r.workload.value}"},
            after={"limit_c": str(nv)},
        )
    db.flush()
    db.info.pop("heat_table", None)
    return _rows(db)
