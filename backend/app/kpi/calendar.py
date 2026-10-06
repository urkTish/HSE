"""Analysis calendars and bands (spec 1-dashboard §6.8): heat season, Ramadan, hour bands,
weekday, days-on-site bands."""

from datetime import date

# Umm al-Qura Ramadan dates (first and last day). Approximate to ±1 day (moon sighting);
# 2025 and 2026 as in spec A.4.2. VERIFY against the Umm al-Qura library before go-live.
RAMADAN: dict[int, tuple[date, date]] = {
    2023: (date(2023, 3, 23), date(2023, 4, 20)),
    2024: (date(2024, 3, 11), date(2024, 4, 9)),
    2025: (date(2025, 3, 1), date(2025, 3, 29)),
    2026: (date(2026, 2, 18), date(2026, 3, 19)),
    2027: (date(2027, 2, 8), date(2027, 3, 9)),
    2028: (date(2028, 1, 28), date(2028, 2, 26)),
}

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
    span = RAMADAN.get(d.year)
    return span is not None and span[0] <= d <= span[1]


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
