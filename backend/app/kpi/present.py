"""Display rules for KPI values, deltas and RAG (K-R8, K-R9, D-4). Pure functions."""

from decimal import Decimal

from app.core.hse_enums import DeltaDirection, KpiBetter, KpiKind, Rag
from app.kpi import fmt
from app.kpi.catalogue import KpiDef

ONE_TWO = Decimal("1.2")
ZERO_EIGHT = Decimal("0.8")


def decimals(defn: KpiDef) -> int:
    k = defn.kind
    if k == KpiKind.rate:
        return 2
    if k == KpiKind.percentage:
        return max(1, defn.decimals)  # 1 dp, K-53 2 dp (2-access-permits §6.8)
    if k == KpiKind.ratio:
        return 1
    if k in (KpiKind.average, KpiKind.hours):
        return defn.decimals  # hours: K-86 2 dp (5-training), K-71 1 dp (3-ptw), others 0
    if k == KpiKind.count_:
        return defn.decimals  # 6e: K-119 tonnes 1 dp; other counts 0
    return 0


def kind_decimals(kind: KpiKind, dp: int = 0) -> int:
    if kind == KpiKind.rate:
        return 2
    if kind in (KpiKind.percentage, KpiKind.ratio):
        return 1
    return dp


def value_str(defn: KpiDef, value: Decimal | None) -> str | None:
    return fmt.dec_str(value, decimals(defn))


def display_kind(kind: KpiKind, value: Decimal | None, dp: int = 0) -> str:
    if value is None:
        return fmt.DASH
    if kind == KpiKind.percentage:
        return fmt.percent(value, max(1, dp))
    if kind == KpiKind.ratio:
        return fmt.ratio(value, 1)
    if kind == KpiKind.rate:
        return fmt.number(value, 2)
    return fmt.number(value, dp)


def display(defn: KpiDef, value: Decimal | None) -> str:
    return display_kind(defn.kind, value, decimals(defn))


def delta_decimals(defn: KpiDef) -> int:
    return 0 if defn.kind in (KpiKind.count_, KpiKind.hours, KpiKind.days) else 2


def delta(
    defn: KpiDef, current: Decimal | None, comparison: Decimal | None
) -> tuple[str | None, str, str | None, str, DeltaDirection]:
    """K-R9 → (abs, abs display, pct, pct display, direction)."""
    if current is None or comparison is None:
        return None, fmt.NA, None, fmt.NA, DeltaDirection.na
    diff = current - comparison
    dp = delta_decimals(defn)
    abs_s = fmt.dec_str(diff, dp)
    abs_d = fmt.signed(diff, dp)
    if comparison == 0:
        pct_s, pct_d = None, fmt.NA
    else:
        pct = diff / comparison * 100
        pct_s = fmt.dec_str(pct, 1)
        pct_d = fmt.signed(pct, 1, " %")
    if diff == 0 or defn.better == KpiBetter.none:
        direction = DeltaDirection.same if diff == 0 else DeltaDirection.na
    elif (diff < 0) == (defn.better == KpiBetter.lower_is_better):
        direction = DeltaDirection.better
    else:
        direction = DeltaDirection.worse
    return abs_s, abs_d, pct_s, pct_d, direction


def rag(defn: KpiDef, value: Decimal | None, target: Decimal | None) -> Rag | None:
    """D-4 on the display-rounded value: green meets target, amber within 20 %, else red."""
    if value is None or target is None or defn.better == KpiBetter.none:
        return None
    v = fmt.rnd(value, decimals(defn))
    if defn.better == KpiBetter.lower_is_better:
        if v <= target:
            return Rag.green
        return Rag.amber if v <= target * ONE_TWO else Rag.red
    if v >= target:
        return Rag.green
    return Rag.amber if v >= target * ZERO_EIGHT else Rag.red
