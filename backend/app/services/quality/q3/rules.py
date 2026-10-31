"""Q3 criteria evaluators (registry `CRITERIA_EVALUATORS`, spec 8-quality §A.6 kind `rule`):
`arrival_temperature` (Q-RCV-01), `remaining_shelf_life` (Q-RCV-01) and `precool_setpoint`
(Q-TRN-02). The numbers below are only the defaults of the seeded criteria ARR-FROZEN,
ARR-CHILLED, ARR-PHARMA, RSL-60 and PRECOOL-FRZ; every limit can be overridden in the criterion's
params (Q-CRT-03). Comparisons use unrounded values; boundaries are inclusive (Q-CRT-01)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.core.quality.common import QVerdict
from app.services.quality import registry as reg

D = Decimal
V = QVerdict

# class → (accept_min, accept_max, deviation_min, deviation_max, outside) ASSUMPTION [VERIFY]
ARRIVAL_DEFAULTS: dict[str, tuple[D | None, D | None, D | None, D | None, str]] = {
    "frozen": (None, D("-18.0"), None, D("-15.0"), "reject"),
    "chilled": (D("-1.0"), D("5.0"), D("-1.0"), D("7.0"), "reject"),
    "pharma_2_8": (D("2.0"), D("8.0"), D("2.0"), D("8.0"), "quarantine"),
}


def _d(v: Any) -> D | None:
    return None if v is None or v == "" else D(str(v))


def arrival_temperature(params: dict[str, Any], values: dict[str, Any]) -> reg.Verdict:
    """Accept band, deviation band, then reject (or quarantine for medicines)."""
    t = _d(values.get("temperature_c"))
    if t is None:
        return reg.Verdict(V.not_evaluable, "No product temperature.", "لا توجد حرارة المنتج.")
    cls = str(params.get("class") or values.get("storage_class") or "")
    dflt = ARRIVAL_DEFAULTS.get(cls)
    if dflt is None:
        return reg.Verdict(
            V.pass_,
            "No arrival limit for this class.",
            "لا حد وصول لهذه الفئة.",
            {"decision": "accept"},
        )
    a_min = _d(params.get("accept_min")) if "accept_min" in params else dflt[0]
    a_max = _d(params.get("accept_max")) if "accept_max" in params else dflt[1]
    v_min = _d(params.get("deviation_min")) if "deviation_min" in params else dflt[2]
    v_max = _d(params.get("deviation_max")) if "deviation_max" in params else dflt[3]
    outside = str(params.get("outside") or dflt[4])

    def inside(lo: D | None, hi: D | None) -> bool:
        return (lo is None or t >= lo) and (hi is None or t <= hi)

    if inside(a_min, a_max):
        return reg.Verdict(
            V.pass_,
            f"{t} °C within the acceptance band.",
            f"{t} °م ضمن نطاق القبول.",
            {"decision": "accept"},
        )
    if inside(v_min, v_max):
        return reg.Verdict(
            V.fail,
            f"{t} °C in the deviation band.",
            f"{t} °م ضمن نطاق الانحراف.",
            {"decision": "accept_with_deviation"},
        )
    return reg.Verdict(
        V.fail, f"{t} °C outside the limits.", f"{t} °م خارج الحدود.", {"decision": outside}
    )


def remaining_shelf_life(params: dict[str, Any], values: dict[str, Any]) -> reg.Verdict:
    pct = _d(values.get("remaining_pct"))
    if pct is None:
        return reg.Verdict(
            V.not_evaluable, "No expiry or shelf life.", "لا يوجد تاريخ انتهاء أو عمر."
        )
    lim = _d(values.get("min_pct")) or _d(params.get("min_pct")) or D(60)
    if pct >= lim:
        return reg.Verdict(
            V.pass_,
            f"Remaining shelf life {pct} % ≥ {lim} %.",
            f"الصلاحية المتبقية {pct} % ≥ {lim} %.",
            {"decision": "accept"},
        )
    return reg.Verdict(
        V.fail,
        f"Remaining shelf life {pct} % < {lim} %.",
        f"الصلاحية المتبقية {pct} % < {lim} %.",
        {"decision": "accept_with_deviation"},
    )


def precool_setpoint(params: dict[str, Any], values: dict[str, Any]) -> reg.Verdict:
    """Q-TRN-02: frozen box temperature at loading ≤ setpoint + margin."""
    t, sp = _d(values.get("box_temp_c")), _d(values.get("setpoint_c"))
    if t is None or sp is None:
        return reg.Verdict(
            V.not_evaluable,
            "No box temperature or setpoint.",
            "لا توجد حرارة الصندوق أو درجة الضبط.",
        )
    margin = _d(params.get("margin")) or D("2.0")
    if t <= sp + margin:
        return reg.Verdict(
            V.pass_, f"Box {t} °C ≤ setpoint + {margin}.", f"الصندوق {t} °م ضمن الحد."
        )
    return reg.Verdict(
        V.fail, f"Box {t} °C above setpoint {sp} + {margin} °C.", f"الصندوق {t} °م أعلى من الحد."
    )


def register() -> None:
    reg.CRITERIA_EVALUATORS.update(
        {
            "arrival_temperature": arrival_temperature,
            "remaining_shelf_life": remaining_shelf_life,
            "precool_setpoint": precool_setpoint,
        }
    )
