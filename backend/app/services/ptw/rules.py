"""Pure PTW calculations (spec 3-ptw §6, §5.1-§5.8): risk bands, gas limits and results, gas
requirement, lift capacity and criticality, voltage class, radiography barrier, fall clearance,
high-risk conditions, mandatory roles / documents / hazards, midday ban and distances.

Inputs are plain values or the JSON type sections stored on the permit; no database access."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any

from app.core.ptw_enums import (
    DocumentType,
    Exposure,
    GasFailCode,
    Hazard,
    HazardousAreaClass,
    LiftCriticalReason,
    PermitType,
    PtwCrewRole,
    RiskBand,
    VoltageClass,
    WorkCondition,
)
from app.services.access.common import at_local, local_day
from app.services.ptw.reference import BANDS, GAMMA, TYPES

T = PermitType
R = PtwCrewRole
D = DocumentType
H = Hazard
ONE_DP = Decimal("0.1")
TWO_DP = Decimal("0.01")
THREE_DP = Decimal("0.001")


def dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))


def q1(v: Decimal) -> Decimal:
    return v.quantize(ONE_DP, rounding=ROUND_HALF_UP)


def ceil1(v: Decimal) -> Decimal:
    """PT-21: computed minimum distances round up to 0.1 m."""
    return v.quantize(ONE_DP, rounding=ROUND_CEILING)


def floor1(v: Decimal) -> Decimal:
    return v.quantize(ONE_DP, rounding=ROUND_FLOOR)


# ---- §6.1 risk -----------------------------------------------------------------------------------


def band(score: int) -> RiskBand:
    for b, lo, hi, *_ in BANDS:
        if lo <= score <= hi:
            return b
    raise ValueError(score)


BAND_RANK = {RiskBand.low: 0, RiskBand.medium: 1, RiskBand.high: 2, RiskBand.extreme: 3}


# ---- §6.2 gas limits -----------------------------------------------------------------------------

PROFILE_OF = {T.confined_space: "confined_space", T.hot_work: "hot_work"}


@dataclass(frozen=True)
class Limits:
    o2_min: Decimal
    o2_max: Decimal
    lel_below: Decimal
    h2s_below: Decimal
    co_below: Decimal
    profiles: tuple[str, ...]
    other: tuple[dict[str, Any], ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {
            "o2_min_pct": str(self.o2_min),
            "o2_max_pct": str(self.o2_max),
            "lel_below_pct": str(self.lel_below),
            "h2s_below_ppm": str(self.h2s_below),
            "co_below_ppm": str(self.co_below),
            "profiles": list(self.profiles),
            "other_toxics": list(self.other),
        }


def gas_limits(types: Iterable[str], gas_limits_setting: dict[str, Any]) -> Limits:
    """Strictest value of each gas across the permit's work types (CSE + hot work → LEL < 1)."""
    by = gas_limits_setting["by_profile"]
    profiles = sorted({PROFILE_OF.get(PermitType(t), "general") for t in types} or {"general"})
    sets = [by[p] for p in profiles]
    return Limits(
        o2_min=max(Decimal(s["o2_min_pct"]) for s in sets),
        o2_max=min(Decimal(s["o2_max_pct"]) for s in sets),
        lel_below=min(Decimal(s["lel_below_pct"]) for s in sets),
        h2s_below=min(Decimal(s["h2s_below_ppm"]) for s in sets),
        co_below=min(Decimal(s["co_below_ppm"]) for s in sets),
        profiles=tuple(profiles),
        other=tuple(gas_limits_setting.get("other_toxics") or []),
    )


def evaluate_readings(readings: Sequence[dict[str, Any]], lim: Limits) -> list[GasFailCode]:
    """GT-6: pass iff every reading at every point is within the limits; returns every failing
    gas code (empty = pass)."""
    fails: list[GasFailCode] = []

    def add(c: GasFailCode) -> None:
        if c not in fails:
            fails.append(c)

    others = {str(o["gas"]).lower(): Decimal(str(o["below"])) for o in lim.other}
    for r in readings:
        o2 = dec(r.get("o2_pct"))
        if o2 is not None and not (lim.o2_min <= o2 <= lim.o2_max):
            add(GasFailCode.O2_OUT_OF_RANGE)
        lel = dec(r.get("lel_pct"))
        if lel is not None and lel >= lim.lel_below:
            add(GasFailCode.LEL_ABOVE_LIMIT)
        h2s = dec(r.get("h2s_ppm"))
        if h2s is not None and h2s >= lim.h2s_below:
            add(GasFailCode.H2S_ABOVE_LIMIT)
        co = dec(r.get("co_ppm"))
        if co is not None and co >= lim.co_below:
            add(GasFailCode.CO_ABOVE_LIMIT)
        for o in r.get("other") or []:
            limit = others.get(str(o.get("gas", "")).lower())
            if limit is not None and Decimal(str(o["value"])) >= limit:
                add(GasFailCode.OTHER_ABOVE_LIMIT)
    order = list(GasFailCode)
    return sorted(fails, key=order.index)


def required_sensors(types: Iterable[str]) -> list[str]:
    """GT-5: O₂ and LEL always (CSE / hot work need them explicitly); H₂S and CO for CSE and
    excavation."""
    ts = set(types)
    out = ["o2", "lel"]
    if T.confined_space.value in ts or T.excavation.value in ts:
        out += ["h2s", "co"]
    return out


# ---- GT-1 gas requirement ------------------------------------------------------------------------


@dataclass(frozen=True)
class ZoneFacts:
    """Zone + PTW profile facts the rules need."""

    id: Any
    code: str
    airside: bool
    in_movement_area: bool
    gas_test_zone: bool
    hazardous: HazardousAreaClass
    fod_control_required: bool
    max_equipment_height_m: Decimal | None


def gas_types(
    types: Sequence[str],
    sections: dict[str, dict[str, Any]],
    zones: Sequence[ZoneFacts],
    flammables_in_use: bool,
    ex_depth_m: Decimal,
) -> list[str]:
    """GT-1: the permit's work types that require gas testing."""
    ts = set(types)
    gas_zone = any(z.gas_test_zone for z in zones)
    hazardous = any(z.hazardous != HazardousAreaClass.none for z in zones)
    out: list[str] = []
    if T.confined_space.value in ts:
        out.append(T.confined_space.value)
    if T.hot_work.value in ts:
        aw = sections.get(T.airside_works.value) or {}
        near_pit = aw.get("hydrant_pit_distance_m") is not None
        if gas_zone or hazardous or T.confined_space.value in ts or near_pit:
            out.append(T.hot_work.value)
    if T.excavation.value in ts:
        ex = sections.get(T.excavation.value) or {}
        depth = dec(ex.get("max_depth_m")) or Decimal(0)
        if depth >= ex_depth_m and (gas_zone or bool(ex.get("atmosphere_hazard"))):
            out.append(T.excavation.value)
    if T.general.value in ts and flammables_in_use and gas_zone:
        out.append(T.general.value)
    return out


def retest_interval(gas_required_types: Sequence[str], setting: dict[str, int]) -> int | None:
    vals = [int(setting.get(t, setting.get("general", 240))) for t in gas_required_types]
    return min(vals) if vals else None


# ---- §6.6 lifting --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Lift:
    gross_t: Decimal
    capacity_pct: Decimal  # unrounded
    critical: bool
    reasons: list[LiftCriticalReason]

    @property
    def capacity_display(self) -> Decimal:
        return q1(self.capacity_pct)


def lift(
    sec: dict[str, Any],
    zones: Sequence[ZoneFacts],
    critical_pct: int,
    critical_weight_t: Decimal,
) -> Lift:
    gross = (dec(sec.get("load_weight_t")) or Decimal(0)) + (
        dec(sec.get("rigging_weight_t")) or Decimal(0)
    )
    rated = dec(sec.get("rated_capacity_t")) or Decimal(1)
    pct = gross / rated * 100
    reasons: list[LiftCriticalReason] = []
    if pct >= critical_pct:
        reasons.append(LiftCriticalReason.capacity)
    if sec.get("tandem"):
        reasons.append(LiftCriticalReason.tandem)
    if sec.get("personnel_lift"):
        reasons.append(LiftCriticalReason.personnel_lift)
    if gross >= critical_weight_t:
        reasons.append(LiftCriticalReason.gross_weight)
    if any(z.in_movement_area for z in zones) or sec.get("within_15m_of_operational_airside"):
        reasons.append(LiftCriticalReason.airside_movement_area)
    if sec.get("overhead_lines_within_6m"):
        reasons.append(LiftCriticalReason.overhead_lines)
    if sec.get("passes_over_occupied_or_live"):
        reasons.append(LiftCriticalReason.over_occupied_or_live)
    return Lift(gross.quantize(THREE_DP), pct, bool(reasons), reasons)


def wind_limit(sec: dict[str, Any], default_ms: Decimal, man_basket_ms: Decimal) -> Decimal:
    lim = dec(sec.get("wind_limit_ms")) or default_ms
    if sec.get("personnel_lift"):
        lim = min(lim, man_basket_ms)
    return lim


WAH_WIND_LIMIT_MS = Decimal("10.0")  # WH-7 ASSUMPTION


# ---- §3.7.5 electrical ---------------------------------------------------------------------------


def voltage_class(volts: int, dc: bool = False) -> VoltageClass:
    if volts <= (120 if dc else 50):
        return VoltageClass.elv
    if volts <= (1500 if dc else 1000):
        return VoltageClass.lv
    return VoltageClass.hv


# ---- §6.7 radiography ----------------------------------------------------------------------------


def dose_rate_1m(sec: dict[str, Any]) -> Decimal:
    src = str(sec.get("source_type"))
    if src == "x_ray":
        return dec(sec.get("xray_dose_rate_1m_usv_h")) or Decimal(0)
    return GAMMA[src] * (dec(sec.get("activity_gbq")) or Decimal(0)) * 1000


def barrier_m(sec: dict[str, Any], limit_usv_h: Decimal) -> Decimal:
    d1 = dose_rate_1m(sec)
    t = dec(sec.get("collimator_transmission")) or Decimal(1)
    return ceil1((d1 * t / limit_usv_h).sqrt())


# ---- §6.9 fall clearance -------------------------------------------------------------------------


def required_clearance(sec: dict[str, Any]) -> Decimal | None:
    fp = sec.get("fall_protection")
    if fp == "arrest_lanyard":
        lanyard = dec(sec.get("lanyard_length_m"))
        if lanyard is None:
            return None
        decel = max(Decimal("1.07"), dec(sec.get("manufacturer_deceleration_m")) or Decimal(0))
        return (lanyard + decel + Decimal("0.30") + Decimal("1.50") + Decimal("0.90")).quantize(
            TWO_DP
        )
    if fp == "arrest_srl":
        return dec(sec.get("srl_required_clearance_m"))
    return None


def clearance_ok(sec: dict[str, Any]) -> bool | None:
    req = required_clearance(sec)
    avail = dec(sec.get("available_clearance_m"))
    if req is None or avail is None:
        return None if sec.get("fall_protection") not in ("arrest_lanyard", "arrest_srl") else False
    return req <= avail


ARREST = {"arrest_lanyard", "arrest_srl", "rope_access_two_rope"}


def wah_arrest(sec: dict[str, Any]) -> bool:
    access = set(sec.get("access_method") or [])
    return (
        sec.get("fall_protection") in ARREST
        or "rope_access" in access
        or "suspended_platform_bmu" in access
    )


# ---- §3.1 high risk (PT-9) -----------------------------------------------------------------------


def high_risk_reasons(
    types: Sequence[str],
    sections: dict[str, dict[str, Any]],
    zones: Sequence[ZoneFacts],
    lift_critical: bool,
    ex_depth_m: Decimal,
) -> list[str]:
    ts = set(types)
    out: list[str] = []
    if T.confined_space.value in ts:
        out.append("Confined space entry")
    if T.radiography.value in ts:
        out.append("Industrial radiography")
    if T.hot_work.value in ts:
        hw = sections.get(T.hot_work.value) or {}
        if any(z.gas_test_zone for z in zones):
            out.append("Hot work in a gas-test zone")
        if any(z.hazardous != HazardousAreaClass.none for z in zones):
            out.append("Hot work in a hazardous area")
        if hw.get("fire_system_impairment"):
            out.append("Hot work with fire-system impairment")
        if any(z.airside for z in zones):
            out.append("Airside hot work")
    if T.work_at_height.value in ts and wah_arrest(sections.get(T.work_at_height.value) or {}):
        out.append("Working at height with fall arrest, rope or suspended access")
    if T.excavation.value in ts:
        depth = dec((sections.get(T.excavation.value) or {}).get("max_depth_m")) or Decimal(0)
        if depth >= ex_depth_m:
            out.append(f"Excavation ≥ {ex_depth_m} m")
    if T.electrical_isolation.value in ts:
        el = sections.get(T.electrical_isolation.value) or {}
        if el.get("system_voltage_v"):
            vc = voltage_class(int(el["system_voltage_v"]), bool(el.get("dc")))
            if vc == VoltageClass.hv:
                out.append("High-voltage electrical work")
        if el.get("work_condition") == WorkCondition.energized.value:
            out.append("Energized electrical work")
    if T.lifting.value in ts and lift_critical:
        out.append("Critical lift")
    if T.airside_works.value in ts and any(z.in_movement_area for z in zones):
        out.append("Airside works in the movement area")
    cs = sections.get(T.confined_space.value) or {}
    if cs.get("ventilation") == "none_justified" and "Confined space entry" not in out:
        out.append("Confined space without ventilation")
    return out


# ---- mandatory roles / documents / hazards -------------------------------------------------------


def mandatory_roles(types: Sequence[str], sections: dict[str, dict[str, Any]]) -> list[R]:
    out: list[R] = []
    for t in types:
        for r in TYPES[PermitType(t)].roles:
            if r not in out:
                out.append(r)
    ts = set(types)
    if T.confined_space.value in ts:
        cs = sections.get(T.confined_space.value) or {}
        if cs.get("rescue_method") != "external_rescue_service" and R.rescue_lead not in out:
            out.append(R.rescue_lead)
    wah = sections.get(T.work_at_height.value) or {}
    if T.work_at_height.value in ts and wah_arrest(wah) and R.competent_person not in out:
        out.append(R.competent_person)
    if T.radiography.value in ts and R.rpo not in out:
        out.append(R.rpo)
    return out


def mandatory_documents(
    types: Sequence[str],
    sections: dict[str, dict[str, Any]],
    lift_critical: bool,
    pe_depth_m: Decimal,
) -> list[D]:
    out: list[D] = []

    def add(d: D) -> None:
        if d not in out:
            out.append(d)

    ts = set(types)
    for t in types:
        for d in TYPES[PermitType(t)].documents:
            add(d)
    if T.work_at_height.value in ts and wah_arrest(sections.get(T.work_at_height.value) or {}):
        add(D.rescue_plan)
    if T.excavation.value in ts:
        depth = dec((sections.get(T.excavation.value) or {}).get("max_depth_m")) or Decimal(0)
        if depth >= pe_depth_m:
            add(D.pe_design)
    if T.electrical_isolation.value in ts:
        el = sections.get(T.electrical_isolation.value) or {}
        if el.get("system_voltage_v") and (
            voltage_class(int(el["system_voltage_v"]), bool(el.get("dc"))) == VoltageClass.hv
        ):
            add(D.switching_programme)
    if T.lifting.value in ts and lift_critical:
        add(D.critical_lift_plan)
    return out


def in_season(d: date, start_mmdd: str, end_mmdd: str) -> bool:
    md = d.strftime("%m-%d")
    if start_mmdd <= end_mmdd:
        return start_mmdd <= md <= end_mmdd
    return md >= start_mmdd or md <= end_mmdd


def permit_dates(valid_from: datetime, valid_to: datetime) -> list[date]:
    d, last = local_day(valid_from), local_day(valid_to - timedelta(seconds=1))
    out = []
    while d <= last:
        out.append(d)
        d += timedelta(days=1)
    return out


def mandatory_hazards(
    types: Sequence[str],
    sections: dict[str, dict[str, Any]],
    exposure: Exposure,
    dates: Sequence[date],
    heat_season: tuple[str, str],
    extra: dict[str, list[str]] | None = None,
) -> list[H]:
    out: list[H] = []

    def add(h: H) -> None:
        if h not in out:
            out.append(h)

    ts = set(types)
    for t in types:
        for h in TYPES[PermitType(t)].hazards:
            add(h)
        for code in (extra or {}).get(t, []):
            add(H(code))
    cs = sections.get(T.confined_space.value) or {}
    if T.confined_space.value in ts and "engulfment" in (cs.get("space_hazards") or []):
        add(H.engulfment)
    el = sections.get(T.electrical_isolation.value) or {}
    if T.electrical_isolation.value in ts and (
        el.get("work_condition") == WorkCondition.energized.value
        or int(el.get("system_voltage_v") or 0) >= 400
    ):
        add(H.arc_flash)
    aw = sections.get(T.airside_works.value) or {}
    if T.airside_works.value in ts and aw.get("aircraft_proximity") == "live_stand_adjacent":
        add(H.aircraft_jet_blast)
    if exposure == Exposure.outdoor_direct_sun and any(
        in_season(d, heat_season[0], heat_season[1]) for d in dates
    ):
        add(H.heat_stress)
    return out


# ---- HT midday ban -------------------------------------------------------------------------------


def ban_interval(d: date, hours: dict[str, str]) -> tuple[datetime, datetime]:
    return (
        at_local(d, time.fromisoformat(hours["start_local"])),
        at_local(d, time.fromisoformat(hours["end_local"])),
    )


def overlaps_ban(
    start: datetime, end: datetime, period: dict[str, str], hours: dict[str, str]
) -> date | None:
    """First ban date whose ban hours intersect [start, end)."""
    d = local_day(start) - timedelta(days=1)
    last = local_day(end)
    while d <= last:
        if in_season(d, period["start_mmdd"], period["end_mmdd"]):
            bs, be = ban_interval(d, hours)
            if start < be and bs < end:
                return d
        d += timedelta(days=1)
    return None


# ---- §6.4 distance -------------------------------------------------------------------------------


def distance(ax: Decimal, ay: Decimal, bx: Decimal, by: Decimal) -> Decimal:
    dx, dy = ax - bx, ay - by
    return (dx * dx + dy * dy).sqrt()


def audit_score(compliant: int, applicable: int) -> Decimal | None:
    if applicable == 0:
        return None
    return q1(Decimal(compliant) * 100 / Decimal(applicable))


def median(values: Sequence[float]) -> float | None:
    v = sorted(values)
    n = len(v)
    if n == 0:
        return None
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
