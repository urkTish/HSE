"""Coded rule evaluators of the criteria library (spec 8-quality Q-TST-08, Q-TST-14, Q-CRT-01).
Q2 registers them in `registry.CRITERIA_EVALUATORS`; parameters are criterion data (Q-CRT-03),
never constants here. Comparisons use unrounded values and boundaries are inclusive.

`values` keys by rule:
- `aci318_strength` / `en206_strength`: `tests` — the strength tests of one mix in cast-date order;
  the last one is the test being evaluated (the earlier ones form the moving window).
- `aci318_cores`: `cores` — the core strengths of one set.
- `slump_astm_c94`: `value` (mm).
- `ratio_min`: `num` and `den` (e.g. field dry density and maximum dry density), or `pct`.
- `sspc_pa2`: `spot_means` (µm), or `spots` (lists of gauge readings, each spot = their mean).
- `pressure_hold`: `test_pressure`, `design_pressure`, `hold_minutes`, `pressure_drop`, `leak`."""

from __future__ import annotations

from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.core.quality.common import QVerdict
from app.services.quality import registry as reg

V = QVerdict


def d(v: Any) -> Decimal | None:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def r2(v: Decimal) -> str:
    return str(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def mean(xs: list[Decimal]) -> Decimal:
    return sum(xs, Decimal(0)) / Decimal(len(xs))


def _v(verdict: QVerdict, en: str, ar: str, **detail: Any) -> reg.Verdict:
    return reg.Verdict(
        verdict, en, ar, {k: (str(x) if isinstance(x, Decimal) else x) for k, x in detail.items()}
    )


def _nums(values: dict[str, Any], key: str) -> list[Decimal] | None:
    raw = values.get(key)
    if not isinstance(raw, list) or not raw:
        return None
    out = [d(x) for x in raw]
    if any(x is None for x in out):
        return None
    return [x for x in out if x is not None]


def _missing(what: str) -> reg.Verdict:
    return _v(V.not_evaluable, f"Missing input: {what}.", f"مدخلات ناقصة: {what}.")


# ---- concrete strength (Q-TST-08) ------------------------------------------------------------


def aci318_strength(params: dict[str, Any], values: dict[str, Any]) -> reg.Verdict:
    """ACI 318 §26.12.3.1 [VERIFY]: (a) every mean of 3 consecutive tests ≥ f'c; (b) no test
    < f'c − 3.5 MPa when f'c ≤ 35 MPa, or < 0.90 f'c when f'c > 35 MPa. A test fails when it
    breaks (b) or completes a run of 3 that breaks (a); (a) is pending for the first two."""
    fc = d(params.get("fc"))
    tests = _nums(values, "tests")
    if fc is None:
        return _missing("f'c")
    if tests is None:
        return _missing("strength tests")
    limit_b = fc - Decimal("3.5") if fc <= 35 else fc * Decimal("0.90")
    cur = tests[-1]
    b_ok = cur >= limit_b
    mean3 = mean(tests[-3:]) if len(tests) >= 3 else None
    a_state = "pending" if mean3 is None else ("pass" if mean3 >= fc else "fail")
    det: dict[str, Any] = {
        "fc": fc,
        "test": cur,
        "limit_b": limit_b,
        "b": "pass" if b_ok else "fail",
        "a": a_state,
        "mean3": r2(mean3) if mean3 is not None else None,
        "n": len(tests),
    }
    if not b_ok:
        return _v(
            V.fail,
            f"Test {r2(cur)} MPa < {r2(limit_b)} MPa (ACI 318 (b)).",
            f"نتيجة الاختبار {r2(cur)} ميجاباسكال أقل من {r2(limit_b)} (البند ب).",
            clause="b",
            **det,
        )
    if a_state == "fail" and mean3 is not None:
        return _v(
            V.fail,
            f"Mean of 3 consecutive tests {r2(mean3)} MPa < f'c {r2(fc)} MPa (ACI 318 (a)).",
            f"متوسط 3 اختبارات متتالية {r2(mean3)} أقل من المقاومة المطلوبة {r2(fc)} (البند أ).",
            clause="a",
            **det,
        )
    note_en = " (a) pending until 3 tests." if a_state == "pending" else ""
    note_ar = " (البند أ معلّق حتى 3 اختبارات)." if a_state == "pending" else ""
    return _v(
        V.pass_,
        f"Test {r2(cur)} MPa meets ACI 318 (b){'' if note_en else ' and (a)'}.{note_en}",
        f"النتيجة {r2(cur)} مطابقة.{note_ar}",
        clause=None,
        **det,
    )


def en206_strength(params: dict[str, Any], values: dict[str, Any]) -> reg.Verdict:
    """BS EN 206 initial production [VERIFY]: groups of 3 consecutive results — mean ≥ fck + 4 MPa
    and each result ≥ fck − 4 MPa."""
    fck = d(params.get("fck"))
    tests = _nums(values, "tests")
    if fck is None:
        return _missing("fck")
    if tests is None:
        return _missing("strength results")
    group = tests[-3:]
    lo = fck - 4
    low = [x for x in group if x < lo]
    det: dict[str, Any] = {"fck": fck, "limit_each": lo, "limit_mean": fck + 4, "n": len(tests)}
    if low:
        return _v(
            V.fail,
            f"Result {r2(min(low))} MPa < fck − 4 = {r2(lo)} MPa (EN 206).",
            f"نتيجة {r2(min(low))} أقل من fck − 4 = {r2(lo)}.",
            clause="each",
            **det,
        )
    if len(group) < 3:
        return _v(
            V.pass_,
            "Each result ≥ fck − 4; the group mean is pending until 3 results.",
            "كل نتيجة ≥ fck − 4؛ متوسط المجموعة معلّق حتى 3 نتائج.",
            clause=None,
            mean3=None,
            **det,
        )
    m = mean(group)
    det["mean3"] = r2(m)
    if m < fck + 4:
        return _v(
            V.fail,
            f"Group mean {r2(m)} MPa < fck + 4 = {r2(fck + 4)} MPa (EN 206).",
            f"متوسط المجموعة {r2(m)} أقل من fck + 4 = {r2(fck + 4)}.",
            clause="mean",
            **det,
        )
    return _v(
        V.pass_,
        f"Group mean {r2(m)} ≥ {r2(fck + 4)} and each result ≥ {r2(lo)} MPa.",
        f"متوسط المجموعة {r2(m)} وكل نتيجة مطابقة.",
        clause=None,
        **det,
    )


def aci318_cores(params: dict[str, Any], values: dict[str, Any]) -> reg.Verdict:
    """ACI 318 §26.12.6 [VERIFY]: mean of 3 cores ≥ 0.85 f'c and no core < 0.75 f'c."""
    fc = d(params.get("fc"))
    cores = _nums(values, "cores")
    if fc is None:
        return _missing("f'c")
    if cores is None:
        return _missing("core strengths")
    m, lo = mean(cores), min(cores)
    lim_m, lim_each = fc * Decimal("0.85"), fc * Decimal("0.75")
    det = {"fc": fc, "mean": r2(m), "min": lo, "limit_mean": lim_m, "limit_each": lim_each}
    if m >= lim_m and lo >= lim_each:
        return _v(
            V.pass_,
            f"Cores acceptable: mean {r2(m)} ≥ {r2(lim_m)} and min {r2(lo)} ≥ {r2(lim_each)} MPa.",
            f"القلوب مقبولة: المتوسط {r2(m)} ≥ {r2(lim_m)} والأدنى {r2(lo)} ≥ {r2(lim_each)}.",
            **det,
        )
    return _v(
        V.fail,
        f"Cores not acceptable: mean {r2(m)} (≥ {r2(lim_m)}), min {r2(lo)} (≥ {r2(lim_each)}).",
        f"القلوب غير مقبولة: المتوسط {r2(m)} والأدنى {r2(lo)}.",
        **det,
    )


# ---- other evaluators (Q-TST-14) ----------------------------------------------------------------


def slump_astm_c94(params: dict[str, Any], values: dict[str, Any]) -> reg.Verdict:
    """ASTM C94 [VERIFY]: T ≤ 50 mm → ± 15; 50 < T ≤ 100 → ± 25; T > 100 → ± 40."""
    t, v = d(params.get("target")), d(values.get("value"))
    if t is None:
        return _missing("target slump")
    if v is None:
        return _missing("slump")
    tol = Decimal(15) if t <= 50 else Decimal(25) if t <= 100 else Decimal(40)
    lo, hi = t - tol, t + tol
    det = {"target": t, "tolerance": tol, "low": lo, "high": hi, "value": v}
    if lo <= v <= hi:
        return _v(
            V.pass_, f"Slump {v} mm within {lo}–{hi} mm.", f"الهبوط {v} مم ضمن {lo}–{hi}.", **det
        )
    return _v(
        V.fail, f"Slump {v} mm outside {lo}–{hi} mm.", f"الهبوط {v} مم خارج {lo}–{hi}.", **det
    )


def ratio_min(params: dict[str, Any], values: dict[str, Any]) -> reg.Verdict:
    """Ratio as a percentage ≥ x (e.g. field dry density ÷ maximum dry density × 100 ≥ 95)."""
    lim = d(params.get("min_pct"))
    num_k, den_k = str(params.get("num") or "num"), str(params.get("den") or "den")
    pct = d(values.get("pct"))
    if pct is None:
        num, den = d(values.get(num_k)), d(values.get(den_k))
        if num is None or den is None or den == 0:
            return _missing(f"{num_k} / {den_k}")
        pct = num / den * 100
    if lim is None:
        return _missing("minimum %")
    det = {"pct": r2(pct), "min_pct": lim}
    if pct >= lim:
        return _v(V.pass_, f"{r2(pct)} % ≥ {lim} %.", f"{r2(pct)} % ≥ {lim} %.", **det)
    return _v(V.fail, f"{r2(pct)} % < {lim} %.", f"{r2(pct)} % < {lim} %.", **det)


def sspc_pa2(params: dict[str, Any], values: dict[str, Any]) -> reg.Verdict:
    """SSPC-PA 2 [VERIFY]: spot = mean of 3 gauge readings; every spot within
    [0.8 × min, 1.2 × max]; the area mean within [min, max]."""
    lo, hi = d(params.get("min")), d(params.get("max"))
    spots = _nums(values, "spot_means")
    if spots is None and isinstance(values.get("spots"), list):
        groups = [[d(x) for x in g] for g in values["spots"] if isinstance(g, list) and g]
        if groups and all(all(x is not None for x in g) for g in groups):
            spots = [mean([x for x in g if x is not None]) for g in groups]
    if lo is None or hi is None:
        return _missing("DFT range")
    if not spots:
        return _missing("spot measurements")
    s_lo, s_hi = lo * Decimal("0.8"), hi * Decimal("1.2")
    bad = [s for s in spots if s < s_lo or s > s_hi]
    area = mean(spots)
    det = {"spot_low": s_lo, "spot_high": s_hi, "area_mean": r2(area), "min": lo, "max": hi}
    if bad:
        return _v(
            V.fail,
            f"Spot {r2(bad[0])} µm outside {r2(s_lo)}–{r2(s_hi)} µm.",
            f"النقطة {r2(bad[0])} خارج {r2(s_lo)}–{r2(s_hi)} ميكرون.",
            **det,
        )
    if not lo <= area <= hi:
        return _v(
            V.fail,
            f"Area mean {r2(area)} µm outside {lo}–{hi} µm.",
            f"متوسط المساحة {r2(area)} خارج {lo}–{hi}.",
            **det,
        )
    return _v(
        V.pass_,
        f"Every spot within {r2(s_lo)}–{r2(s_hi)}; area mean {r2(area)} within {lo}–{hi} µm.",
        f"كل النقاط ضمن الحدود؛ متوسط المساحة {r2(area)} ضمن {lo}–{hi}.",
        **det,
    )


def pressure_hold(params: dict[str, Any], values: dict[str, Any]) -> reg.Verdict:
    """Test pressure ≥ factor × design pressure, hold ≥ minutes, drop ≤ allowed, no leak."""
    factor, hold = d(params.get("factor")), d(params.get("hold_min"))
    allowed = d(params.get("max_drop")) or Decimal(0)
    tp, dp = d(values.get("test_pressure")), d(values.get("design_pressure"))
    mins, drop = d(values.get("hold_minutes")), d(values.get("pressure_drop")) or Decimal(0)
    leak = str(values.get("leak") or "").lower() in ("true", "yes", "1", "fail", "leak")
    if factor is None or hold is None:
        return _missing("factor / hold")
    if tp is None or dp is None or mins is None:
        return _missing("test pressure, design pressure, hold minutes")
    problems = []
    if tp < factor * dp:
        problems.append(f"test pressure {tp} < {r2(factor * dp)}")
    if mins < hold:
        problems.append(f"hold {mins} min < {hold} min")
    if drop > allowed:
        problems.append(f"drop {drop} > {allowed}")
    if leak:
        problems.append("visible leak")
    det = {"required_pressure": r2(factor * dp), "hold_min": hold, "max_drop": allowed}
    if problems:
        return _v(
            V.fail,
            "Failed: " + "; ".join(problems) + ".",
            "غير مطابق: " + "؛ ".join(problems),
            **det,
        )
    return _v(
        V.pass_, "Pressure, hold time and drop within the criterion; no leak.", "مطابق.", **det
    )


EVALUATORS: dict[str, Callable[[dict[str, Any], dict[str, Any]], reg.Verdict]] = {
    "aci318_strength": aci318_strength,
    "en206_strength": en206_strength,
    "aci318_cores": aci318_cores,
    "slump_astm_c94": slump_astm_c94,
    "ratio_min": ratio_min,
    "sspc_pa2": sspc_pa2,
    "pressure_hold": pressure_hold,
}
# rules whose input is a list built from the specimens (key of the list in `values`)
LIST_RULES = {"aci318_cores": "cores", "sspc_pa2": "spot_means"}
STRENGTH_RULES = frozenset({"aci318_strength", "en206_strength"})
