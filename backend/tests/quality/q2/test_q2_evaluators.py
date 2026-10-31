"""Coded criteria evaluators (spec 8-quality Q-TST-08, Q-TST-14): worked examples QX4…QX7,
AC-Q2-01, -03, -04 (cores), -05. Pure functions; no database needed beyond the shared fixture."""

from app.core.quality.common import QVerdict
from app.services.quality.q2 import evaluators as ev

P, F = QVerdict.pass_, QVerdict.fail


def _aci(fc: int, tests: list[str]) -> list[tuple[QVerdict, str | None]]:
    out = []
    for i in range(len(tests)):
        v = ev.aci318_strength({"fc": fc}, {"tests": tests[: i + 1]})
        out.append((v.verdict, v.detail.get("clause")))
    return out


def test_AC01_qx4_aci318_strength_window() -> None:
    res = _aci(32, ["34.1", "31.2", "33.0", "30.4", "27.9"])
    assert res == [(P, None), (P, None), (P, None), (F, "a"), (F, "b")]
    v1 = ev.aci318_strength({"fc": 32}, {"tests": ["34.1"]})
    assert v1.detail["a"] == "pending" and v1.detail["limit_b"] == "28.5"
    v3 = ev.aci318_strength({"fc": 32}, {"tests": ["34.1", "31.2", "33.0"]})
    assert v3.detail["mean3"] == "32.77"
    v4 = ev.aci318_strength({"fc": 32}, {"tests": ["34.1", "31.2", "33.0", "30.4"]})
    assert v4.detail["mean3"] == "31.53"
    v5 = ev.aci318_strength({"fc": 32}, {"tests": ["34.1", "31.2", "33.0", "30.4", "27.9"]})
    assert v5.detail["a"] == "fail" and v5.detail["mean3"] == "30.43"


def test_AC02_variant_fc40_limit_b_is_0_9_fc() -> None:
    v = ev.aci318_strength({"fc": 40}, {"tests": ["33.2"]})
    assert v.verdict == F and v.detail["clause"] == "b"
    assert v.detail["limit_b"] == "36.00"


def test_AC03_qx5_en206() -> None:
    assert ev.en206_strength({"fck": 50}, {"tests": ["58.5", "55.0", "51.5"]}).verdict == P
    bad = ev.en206_strength({"fck": 50}, {"tests": ["53.0", "54.5", "52.0"]})
    assert bad.verdict == F and bad.detail["clause"] == "mean" and bad.detail["mean3"] == "53.17"


def test_AC04_qx6_cores_acceptable() -> None:
    v = ev.aci318_cores({"fc": 40}, {"cores": ["36.1", "34.9", "33.6"]})
    assert v.verdict == P and v.detail["mean"] == "34.87"


def test_AC05_qx7_slump_compaction_dft() -> None:
    s = {"target": 100}
    assert [ev.slump_astm_c94(s, {"value": x}).verdict for x in ("75", "125", "130")] == [P, P, F]
    r = {"min_pct": 95, "num": "dry_density", "den": "mdd"}
    ok = ev.ratio_min(r, {"dry_density": "2.068", "mdd": "2.150"})
    assert ok.verdict == P and ok.detail["pct"] == "96.19"
    no = ev.ratio_min(r, {"dry_density": "2.030", "mdd": "2.150"})
    assert no.verdict == F and no.detail["pct"] == "94.42"
    d = {"min": 125, "max": 200}
    good = ev.sspc_pa2(d, {"spot_means": ["124", "141", "132", "119", "136"]})
    assert good.verdict == P and good.detail["area_mean"] == "130.40"
    assert ev.sspc_pa2(d, {"spot_means": ["124", "141", "96", "119", "136"]}).verdict == F
    # spots given as three gauge readings each
    assert ev.sspc_pa2(d, {"spots": [["120", "125", "127"], ["140", "141", "142"]]}).verdict == P


def test_pressure_hold_and_missing_inputs() -> None:
    p = {"factor": 1.5, "hold_min": 10}
    ok = {"test_pressure": "15", "design_pressure": "10", "hold_minutes": "10", "pressure_drop": "0", "leak": "no"}
    assert ev.pressure_hold(p, ok).verdict == P
    assert ev.pressure_hold(p, {**ok, "test_pressure": "14"}).verdict == F
    assert ev.pressure_hold(p, {**ok, "leak": "yes"}).verdict == F
    assert ev.aci318_strength({"fc": 40}, {}).verdict == QVerdict.not_evaluable
    assert ev.slump_astm_c94({"target": 100}, {}).verdict == QVerdict.not_evaluable
