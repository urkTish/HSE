"""Project settings — AC23-AC26, rules 30-34, K1/K2."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import local_date
from app.core.enums import AuditAction
from app.kpi import rate
from app.models import AuditEntry
from tests.conftest import Api, Ids


def test_AC23_ltifr_base_change_audited_and_rate_recomputed(
    api: Api, ids: Ids, db: Session
) -> None:
    c = api.as_("faisal.harbi")
    pid = ids.project("ANIA-EXP")
    before = c.get(f"/api/v1/projects/{pid}/settings").json()
    assert before["ltifr_base_hours"] == 1_000_000
    assert before["ltifr_base_label_en"] == "per 1,000,000 h"
    assert rate(2, before["ltifr_base_hours"], 1_250_000) == Decimal("1.60")
    res = c.patch(f"/api/v1/projects/{pid}/settings", json={"ltifr_base_hours": 200_000})
    assert res.status_code == 200
    after = res.json()
    assert after["ltifr_base_label_en"] == "per 200,000 h"
    assert after["ltifr_base_label_ar"] == "لكل 200,000 ساعة"
    assert rate(2, after["ltifr_base_hours"], 1_250_000) == Decimal("0.32")
    entry = db.scalars(
        select(AuditEntry).where(AuditEntry.action == AuditAction.settings_changed)
    ).one()
    assert entry.before == {"ltifr_base_hours": 1_000_000}
    assert entry.after == {"ltifr_base_hours": 200_000}
    # Officers of the project are notified (§7)
    notes = api.as_("noura.qahtani").get("/api/v1/notifications").json()
    assert notes["unread_count"] >= 1 and notes["items"][0]["kind"] == "settings_changed"


def test_AC24_invalid_kpi_base_rejected(api: Api, ids: Ids) -> None:
    c = api.as_("faisal.harbi")
    pid = ids.project("ANIA-EXP")
    for body in (
        {"ltifr_base_hours": 500_000},
        {"rate_base_hours": 100},
        {"audit_retention_years": 0},
        {"inactive_account_days": 10},
        {"timezone": "Asia/Dubai"},
    ):
        assert c.patch(f"/api/v1/projects/{pid}/settings", json=body).status_code == 422, body


def test_rule30_only_manager_edits_settings(api: Api, ids: Ids) -> None:
    pid = ids.project("ANIA-EXP")
    for who in ("noura.qahtani", "omar.siddiqui", "sarah.mitchell"):
        c = api.as_(who)
        assert c.get(f"/api/v1/projects/{pid}/settings").status_code == 200
        assert (
            c.patch(f"/api/v1/projects/{pid}/settings", json={"show_hijri": False}).status_code
            == 403
        )


def test_K1_zero_hours_is_dash() -> None:
    assert rate(3, 200_000, 0) is None


def test_AC25_riyadh_local_date() -> None:
    ts = datetime(2026, 10, 4, 22, 30, tzinfo=UTC)
    local = ts.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Riyadh"))
    assert local_date(ts).isoformat() == "2026-10-05"
    assert local.strftime("%d %b %Y %H:%M") == "05 Oct 2026 01:30"


def test_AC26_show_hijri_setting_round_trip(api: Api, ids: Ids) -> None:
    # Hijri conversion is a display concern (frontend, ICU islamic-umalqura); the backend
    # stores and serves the flag and calendar.
    c = api.as_("faisal.harbi")
    pid = ids.project("RBT-52")
    s = c.patch(f"/api/v1/projects/{pid}/settings", json={"show_hijri": True}).json()
    assert s["show_hijri"] is True and s["hijri_calendar"] == "umm_al_qura"
