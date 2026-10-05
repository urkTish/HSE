"""KPI engine — the only place rates are computed (build plan, Phase 1).

Phase 0 declares the generic rate K1 so Phase 1 starts from a tested function.
"""

from decimal import ROUND_HALF_UP, Decimal


def rate(count: int, base_hours: int, man_hours: Decimal | int) -> Decimal | None:
    """K1: count × base ÷ man-hours. Returns ``None`` (display "—") when man-hours = 0."""
    hours = Decimal(man_hours)
    if hours <= 0:
        return None
    return (Decimal(count) * Decimal(base_hours) / hours).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
