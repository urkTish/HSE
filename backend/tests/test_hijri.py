"""Umm al-Qura Hijri dates on the server (D-303), checked against the official calendar."""

from datetime import date

from app.core.hijri import _tabular, hijri_ar, hijri_en, to_hijri
from app.services.followup import common as fc


def test_umm_al_qura_known_dates() -> None:
    assert to_hijri(date(2024, 3, 11)) == (1445, 9, 1)  # 1 Ramadan 1445
    assert to_hijri(date(2024, 4, 10)) == (1445, 10, 1)  # 1 Shawwal 1445 (Eid al-Fitr)
    assert to_hijri(date(2025, 6, 1)) == (1446, 12, 5)  # matches ICU islamic-umalqura
    assert to_hijri(date(2026, 10, 22)) == (1448, 5, 11)


def test_tabular_was_a_day_off() -> None:
    """The old tabular formula gave 10 Jumada al-Ula for 22 Oct 2026; Umm al-Qura says 11."""
    assert _tabular(date(2026, 10, 22)) == (1448, 5, 10)
    assert fc.hijri(date(2026, 10, 22)) == (1448, 5, 11)


def test_labels_and_out_of_range_fallback() -> None:
    assert hijri_ar(date(2026, 10, 22)) == "11 جمادى الأولى 1448 هـ"
    assert hijri_en(date(2026, 10, 22)) == "11 Jumada al-Ula 1448 AH"
    assert fc.hijri_str(date(2026, 10, 22)) == hijri_ar(date(2026, 10, 22))
    assert to_hijri(date(2200, 1, 1)) == _tabular(date(2200, 1, 1))
