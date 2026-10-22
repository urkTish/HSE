"""Analysis calendars and bands (spec 1-dashboard §6.8): heat season, Ramadan, hour bands,
weekday, days-on-site bands."""

from datetime import date

WEEKDAYS = [
    ("monday", "Monday", "الاثنين"),
    ("tuesday", "Tuesday", "الثلاثاء"),
    ("wednesday", "Wednesday", "الأربعاء"),
    ("thursday", "Thursday", "الخميس"),
    ("friday", "Friday", "الجمعة"),
    ("saturday", "Saturday", "السبت"),
    ("sunday", "Sunday", "الأحد"),
]
DAYS_ON_SITE_BANDS = [(0, 7, "0-7"), (8, 30, "8-30"), (31, 90, "31-90"), (91, 365, "91-365")]


def in_ramadan(d: date) -> bool:
    """Ramadan by the Umm al-Qura calendar (D-303; it replaced the 2023-2028 table, which agreed
    for 2023-2026 and was a day long in 2027)."""
    from app.core.hijri import to_hijri  # noqa: PLC0415

    return to_hijri(d)[1] == 9


def in_heat_season(d: date, start: str = "06-01", end: str = "09-30") -> bool:
    """``start``/``end`` are MM-DD (inclusive); a season may wrap the year end."""
    md = d.strftime("%m-%d")
    if start <= end:
        return start <= md <= end
    return md >= start or md <= end


def hour_band(hour: int | None) -> str | None:
    if hour is None:
        return None
    lo = (hour // 2) * 2
    return f"{lo:02d}-{lo + 2:02d}"


def weekday(d: date) -> str:
    return WEEKDAYS[d.weekday()][0]


def days_on_site_band(days: int | None) -> str | None:
    if days is None:
        return None
    for lo, hi, key in DAYS_ON_SITE_BANDS:
        if lo <= days <= hi:
            return key
    return ">365"
