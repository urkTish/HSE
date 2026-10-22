"""Gregorian → Hijri (Umm al-Qura) for documents the server renders (D-303).

The frontend formats Hijri dates with ICU's `islamic-umalqura` calendar; this module gives the
same answer on the server so government-form packs, report packs and PDFs agree with the screens.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from hijridate import Gregorian

HIJRI_MONTHS_AR = [
    "محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان",
    "رمضان", "شوال", "ذو القعدة", "ذو الحجة",
]  # fmt: skip
HIJRI_MONTHS_EN = [
    "Muharram", "Safar", "Rabi al-Awwal", "Rabi al-Thani", "Jumada al-Ula", "Jumada al-Akhirah",
    "Rajab", "Shaban", "Ramadan", "Shawwal", "Dhu al-Qadah", "Dhu al-Hijjah",
]  # fmt: skip


def _tabular(d: date) -> tuple[int, int, int]:
    """Civil (tabular) Islamic calendar: only outside the Umm al-Qura table's range."""
    jd = d.toordinal() + 1721425
    l_ = jd - 1948440 + 10632
    n = (l_ - 1) // 10631
    l_ = l_ - 10631 * n + 354
    j = ((10985 - l_) // 5316) * ((50 * l_) // 17719) + (l_ // 5670) * ((43 * l_) // 15238)
    l_ = l_ - ((30 - j) // 15) * ((17719 * j) // 50) - (j // 16) * ((15238 * j) // 43) + 29
    m = (24 * l_) // 709
    day = l_ - (709 * m) // 24
    y = 30 * n + j - 30
    return y, m, day


@lru_cache(maxsize=8192)
def to_hijri(d: date) -> tuple[int, int, int]:
    try:
        h = Gregorian(d.year, d.month, d.day).to_hijri()
    except (OverflowError, ValueError):
        return _tabular(d)
    return h.year, h.month, h.day


def hijri_ar(d: date) -> str:
    """`11 جمادى الأولى 1448 هـ`"""
    y, m, day = to_hijri(d)
    return f"{day} {HIJRI_MONTHS_AR[m - 1]} {y} هـ"


def hijri_en(d: date) -> str:
    """`11 Jumada al-Ula 1448 AH`"""
    y, m, day = to_hijri(d)
    return f"{day} {HIJRI_MONTHS_EN[m - 1]} {y} AH"
