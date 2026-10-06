"""Rounding and display text (spec 1-dashboard K-R8, K-R9, W-11).

Everything is computed with exact decimals from unrounded sums and rounded only here, half-up.
Display strings use western digits; the frontend may re-map digits only.
"""

from decimal import ROUND_HALF_UP, Decimal

MINUS = "−"  # U+2212, used in signed deltas ("−0.01")
DASH = "—"
NA = "n/a"


def rnd(value: Decimal, dp: int) -> Decimal:
    """Round half-up to ``dp`` decimals (0.125 → 0.13, never banker's rounding)."""
    return value.quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP)


def dec_str(value: Decimal | None, dp: int) -> str | None:
    """API decimal string, rounded half-up."""
    if value is None:
        return None
    return format(rnd(value, dp), "f")


def exact(value: Decimal | int | None) -> str | None:
    """Numerator/denominator string: counts as integers, sums (man-hours, SAR, training hours)
    with their stored 2 decimals. These are the unrounded inputs of the KPI."""
    if value is None:
        return None
    if isinstance(value, int):
        return str(value)
    return format(rnd(value, 2), "f")


def number(value: Decimal | int, dp: int = 0) -> str:
    """Thousands separators, half-up: 870000 → '870,000'; 1.149 (dp 2) → '1.15'."""
    return format(rnd(Decimal(value), dp), f",.{dp}f")


def percent(value: Decimal, dp: int = 1) -> str:
    return f"{number(value, dp)} %"


def ratio(value: Decimal, dp: int = 1) -> str:
    return f"{number(value, dp)} : 1"


def signed(value: Decimal, dp: int, suffix: str = "") -> str:
    """'+0.26', '−0.01', '0.00' (zero has no sign)."""
    r = rnd(value, dp)
    text = format(abs(r), f",.{dp}f")
    if r > 0:
        return f"+{text}{suffix}"
    if r < 0:
        return f"{MINUS}{text}{suffix}"
    return f"{text}{suffix}"


def hours_label(base: int) -> tuple[str, str]:
    """'per 200,000 h' / 'لكل 200,000 ساعة' (K-R15)."""
    return f"per {base:,} h", f"لكل {base:,} ساعة"
