"""3-ptw §6.13 worked examples as pure-function tests: Y1, Y2, Y7, Y8 (distances), Y9, Y10, Y14."""

from decimal import Decimal
from typing import Any

from app.core.hse_enums import ControlLevel
from app.core.ptw_enums import GasFailCode, HazardousAreaClass, LiftCriticalReason, RiskBand
from app.services.ptw import jsa, reference, rules

D = Decimal


def line(il: int, is_: int, rl: int, rs: int, *levels: str) -> dict[str, Any]:
    return {
        "hazard_code": "fall_from_height", "description": "x", "initial_l": il, "initial_s": is_,
        "residual_l": rl, "residual_s": rs, "controls": [{"text": lv, "level": lv} for lv in levels],
    }  # fmt: skip


def test_Y1_jsa_risk_bands() -> None:
    l1 = jsa.line_facts(line(4, 5, 2, 5, "engineering", "administrative", "ppe"))
    assert (l1["initial_score"], l1["initial_band"], l1["residual_score"], l1["residual_band"]) == (
        20,
        RiskBand.extreme,
        10,
        RiskBand.high,
    )
    l2 = jsa.line_facts(line(3, 4, 1, 4, "engineering", "administrative"))
    assert (l2["initial_score"], l2["initial_band"], l2["residual_score"], l2["residual_band"]) == (
        12,
        RiskBand.high,
        4,
        RiskBand.low,
    )
    assert rules.band(15) == RiskBand.extreme
    ppe = jsa.line_facts(line(3, 3, 1, 3, "ppe"))
    assert ppe["ppe_only"] and ppe["initial_band"] == RiskBand.medium
    assert jsa.line_facts(line(3, 3, 2, 3, "ppe"))["residual_band"] == RiskBand.medium
    admin = jsa.line_facts(line(3, 4, 2, 3, "administrative"))
    assert [w.value for w in admin["warnings"]] == ["SEVERITY_REDUCED_WITHOUT_HIGHER_CONTROL"]
    assert ControlLevel.engineering.value == "engineering"


def _lim(*types: str) -> rules.Limits:
    return rules.gas_limits(types, reference.GAS_LIMITS_DEFAULT)


def rd(o2: str, lel: str, h2s: str, co: str) -> dict[str, str]:
    return {"o2_pct": o2, "lel_pct": lel, "h2s_ppm": h2s, "co_ppm": co}


Y2 = [rd("20.9", "0", "0", "3"), rd("20.8", "0", "0", "4"), rd("20.6", "2", "0", "6")]


def test_Y2_gas_acceptance() -> None:
    assert rules.evaluate_readings(Y2, _lim("confined_space")) == []
    assert rules.evaluate_readings(Y2, _lim("confined_space", "hot_work")) == [
        GasFailCode.LEL_ABOVE_LIMIT
    ]
    low_o2 = [*Y2[:2], rd("19.4", "2", "0", "6")]
    assert rules.evaluate_readings(low_o2, _lim("confined_space")) == [GasFailCode.O2_OUT_OF_RANGE]
    h2s = [*Y2[:2], rd("20.6", "2", "1", "6")]
    assert rules.evaluate_readings(h2s, _lim("confined_space")) == [GasFailCode.H2S_ABOVE_LIMIT]
    assert rules.evaluate_readings(Y2, _lim("general")) == []


def zf(movement: bool = False) -> rules.ZoneFacts:
    return rules.ZoneFacts(
        None, "Z", movement, movement, False, HazardousAreaClass.none, False, None
    )


def test_Y7_lifting_capacity() -> None:
    a = rules.lift(
        {"load_weight_t": "4.200", "rigging_weight_t": "0.150", "rated_capacity_t": "5.000"},
        [zf()],
        75,
        D("20"),
    )
    assert (a.gross_t, a.capacity_display, a.critical, a.reasons) == (
        D("4.350"),
        D("87.0"),
        True,
        [LiftCriticalReason.capacity],
    )
    b = rules.lift(
        {"load_weight_t": "6.800", "rigging_weight_t": "0.350", "rated_capacity_t": "12.400"},
        [zf(True)],
        75,
        D("20"),
    )
    assert (b.gross_t, b.capacity_display, b.reasons) == (
        D("7.150"),
        D("57.7"),
        [LiftCriticalReason.airside_movement_area],
    )
    c = rules.lift({"load_weight_t": "2.200", "rated_capacity_t": "9.800"}, [zf()], 75, D("20"))
    assert (c.capacity_display, c.critical) == (D("22.4"), False)
    d = rules.lift(
        {"load_weight_t": "4.900", "rigging_weight_t": "0.150", "rated_capacity_t": "5.000"},
        [zf()],
        75,
        D("20"),
    )
    assert d.capacity_display == D("101.0")
    e = rules.lift({"load_weight_t": "4.550", "rated_capacity_t": "5.000"}, [zf()], 75, D("20"))
    assert e.capacity_display == D("91.0")
    assert rules.wind_limit({"wind_limit_ms": "13.0"}, D("9.8"), D("7.0")) == D("13.0")
    assert rules.wind_limit({"personnel_lift": True}, D("9.8"), D("7.0")) == D("7.0")


def _d(ax: str, ay: str, bx: str, by: str) -> Decimal:
    return rules.q1(rules.distance(D(ax), D(ay), D(bx), D(by)))


def test_Y8_Y9_distances() -> None:
    assert _d("120.0", "45.0", "126.0", "53.0") == D("10.0")
    assert _d("120.0", "45.0", "130.0", "52.5") == D("12.5")
    assert _d("120.0", "45.0", "128.0", "51.0") == D("10.0")
    assert _d("40.0", "18.0", "42.0", "20.0") == D("2.8")
    assert _d("45.0", "22.0", "40.0", "18.0") == D("6.4")
    assert _d("60.0", "30.0", "40.0", "18.0") == D("23.3")
    assert _d("45.0", "22.0", "42.0", "20.0") == D("3.6")
    assert _d("300.0", "200.0", "320.0", "180.0") == D("28.3")
    assert _d("300.0", "200.0", "330.0", "230.0") == D("42.4")


def test_Y9_radiography_barrier() -> None:
    sec = {"source_type": "ir_192", "activity_gbq": "1110.0"}
    assert rules.dose_rate_1m(sec) == D("144300.0") or rules.dose_rate_1m(sec) == D(144300)
    assert rules.barrier_m(sec, D("7.5")) == D("138.8")
    assert rules.barrier_m({**sec, "collimator_transmission": "0.0625"}, D("7.5")) == D("34.7")


def test_Y10_fall_clearance() -> None:
    lan = {
        "fall_protection": "arrest_lanyard",
        "lanyard_length_m": "1.80",
        "available_clearance_m": "4.00",
    }
    assert rules.required_clearance(lan) == D("5.57") and rules.clearance_ok(lan) is False
    short = {**lan, "lanyard_length_m": "1.20"}
    assert rules.required_clearance(short) == D("4.97") and rules.clearance_ok(short) is False
    srl = {
        "fall_protection": "arrest_srl",
        "srl_required_clearance_m": "2.40",
        "available_clearance_m": "4.00",
    }
    assert rules.clearance_ok(srl) is True
    assert rules.clearance_ok({**lan, "available_clearance_m": "6.00"}) is True


def test_Y14_audit_score() -> None:
    assert rules.audit_score(10, 11) == D("90.9")
    assert rules.audit_score(9, 11) == D("81.8")
    assert rules.audit_score(17, 18) == D("94.4")
    assert rules.audit_score(0, 0) is None
