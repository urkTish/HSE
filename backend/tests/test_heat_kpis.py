"""6b-heat-stress §9 ACs 6, 47, 54-59 (KPIs K-97…K-103, E16/E17, season report, action panel)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BanPatrol
from tests.conftest import Api
from tests.heat_helpers import API, eng, err, kpi, point, project, zone

pytestmark = pytest.mark.usefixtures("heat_seed", "clock")

HS7 = {
    "ANIA-EXP": {"K97": "97.0 %", "K98": "141.0", "K99": "96.7 %", "K100": "2",
                 "K101": "97.1 %", "K102": "91.7 %", "K103": "1"},
    "RBT-52": {"K97": "93.9 %", "K98": "76.0", "K99": "100.0 %", "K100": "0",
               "K101": "97.6 %", "K102": "100.0 %", "K103": "0"},
}  # fmt: skip


def heat(c: Any, db: Session, pcode: str, **params: Any) -> dict[str, Any]:
    q = {"project_id": str(project(db, pcode).id), "as_of": "2026-09-30", "period": "month",
         "anchor": "2026-09-30", **params}  # fmt: skip
    res = c.get(f"{API}/kpi/heat-stress", params=q)
    assert res.status_code == 200, res.text
    return res.json()  # type: ignore[no-any-return]


def comps(m: dict[str, Any]) -> dict[str, str]:
    return {c["key"]: c["display"] for c in m["components"]}


@pytest.mark.parametrize("code", ["ANIA-EXP", "RBT-52"])
def test_AC54_hs7(api: Api, db: Session, code: str) -> None:
    body = heat(api.as_("faisal.harbi"), db, code, group_by=["zone", "contractor"])
    for metric, display in HS7[code].items():
        assert kpi(body, metric)["display"].startswith(display), (metric, kpi(body, metric))
    k100, k101, k103 = (comps(kpi(body, m)) for m in ("K100", "K101", "K103"))
    if code == "ANIA-EXP":
        assert k100["rate_per_100_patrols"] == "2.86" and k101["station_days_checked_pct"] == "96.7 %"
        assert (k103["rate"], k103["recordable"], k103["recordable_rate"]) == ("0.23", "1", "0.23")
        k97 = kpi(body, "K97")
        assert (k97["numerator"], k97["denominator"]) == ("640", "660")
    else:
        assert k100["rate_per_100_patrols"] == "0.00" and k101["station_days_checked_pct"] == "100.0 %"
    assert body["breakdowns"], "zone/contractor breakdowns"


def test_AC59_small_cells(api: Api, db: Session) -> None:
    """HM-3: K-103 of 1–2 shows "<3" below the HSE Manager; exact for Faisal."""
    noura = heat(api.as_("noura.qahtani"), db, "ANIA-EXP", group_by=["zone"])
    assert kpi(noura, "K103")["display"] == "<3" and kpi(noura, "K103")["value"] is None
    rows = [r for b in noura["breakdowns"] if b["metric"] == "K-103" for r in b["rows"]]
    assert any(r["display"] == "<3" for r in rows) and not any(r["value"] == "1" for r in rows)
    assert kpi(heat(api.as_("faisal.harbi"), db, "ANIA-EXP"), "K103")["display"] == "1"


def test_AC55_e16_e17(db: Session) -> None:
    from app.hse_jobs import project_scope
    from app.kpi import warnings as kwarn
    from app.kpi.periods import Window

    found: dict[str, dict[tuple[str, str | None], Any]] = {}
    for code in ("ANIA-EXP", "RBT-52"):
        sc = project_scope(db, project(db, code), date(2026, 10, 2))
        ws = kwarn.evaluate(sc, [Window(date(2026, 9, 1), date(2026, 9, 30))])
        found[code] = {
            (w.code.value, w.engagement.code if w.engagement else None): w
            for w in ws
            if w.code.value in ("E16", "E17")
        }
    assert set(found["ANIA-EXP"]) == {("E16", None), ("E16", "RAWABI"), ("E17", None),
                                      ("E17", "RAWABI")}  # fmt: skip
    assert set(found["RBT-52"]) == {("E17", None), ("E17", "QIMMA")}
    e16 = {i.key: i.value for i in found["ANIA-EXP"][("E16", None)].inputs}
    assert e16["k100_violations"] == 2
    e17 = {i.key: i.value for i in found["ANIA-EXP"][("E17", None)].inputs}
    assert e17["control_gap_entries"] == 1
    rbt = {i.key: i.value for i in found["RBT-52"][("E17", None)].inputs}
    assert rbt["control_gap_entries"] == 0 and rbt["k97"] is not None
    assert Decimal(rbt["k97"]) < Decimal("95.0")
    text = " ".join(w.message_en for w in found["ANIA-EXP"].values())
    assert "Ganesh" not in text and "WKR-" not in text


def test_AC56_hs9a_rounding() -> None:
    """94.95 displays as 95.0 % while the unrounded value stays below the 95.0 threshold."""
    from app.core.hse_enums import KpiMetric
    from app.kpi import present
    from app.kpi.catalogue import CATALOGUE

    v = Decimal(9495) / Decimal(10000) * 100
    assert present.display(CATALOGUE[KpiMetric.K97], v) == "95.0 %"
    assert v < Decimal("95.0")


def test_AC57_AC58_season_report(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    url = f"{API}/projects/{pid}/heat-season-reports"
    faisal = api.as_("faisal.harbi")
    body = faisal.get(url, params={"season_year": 2026}).json()
    m = body["draft"]["metrics"]
    assert m["k01_man_hours"].startswith("4210000")
    hi = m["heat_illness"]
    assert (hi["cases"], hi["rate"], hi["recordable"], hi["recordable_rate"]) == (
        "16",
        "0.76",
        "6",
        "0.29",
    )
    assert m["season"]["K-99"]["display"] == "96.8 %"
    assert m["midday_ban"]["violations"] == 9
    assert hi["previous_season"] is None
    # issue r1 → Noura 403, Sarah sees issued only
    assert api.as_("noura.qahtani").post(url, json={"season_year": 2026}).status_code == 403
    r1 = faisal.post(url, json={"season_year": 2026, "comments_en": "Season closed."})
    assert r1.status_code == 201, r1.text
    assert r1.json()["report_no"] == "HSR-ANIA-EXP-2026-r1"
    frozen = r1.json()["metrics"]["season"]["K-99"]["display"]
    # a later void of a September patrol changes the draft, not r1
    p = db.scalar(select(BanPatrol).where(BanPatrol.patrol_no == "MBP-ANIA-EXP-2026-00188"))
    assert p is not None
    v = faisal.post(f"{API}/ban-patrols/{p.id}/void", json={"reason": "Recorded on the wrong zone"})
    assert v.status_code == 200, v.text
    after = faisal.get(url, params={"season_year": 2026}).json()
    assert after["draft"]["metrics"]["midday_ban"]["violations"] == 8
    assert after["issued"][0]["metrics"]["season"]["K-99"]["display"] == frozen
    assert after["issued"][0]["metrics"]["midday_ban"]["violations"] == 9
    # re-issue: reason needed, r2 supersedes r1
    assert faisal.post(url, json={"season_year": 2026}).status_code == 422
    r2 = faisal.post(url, json={"season_year": 2026, "reason": "Patrol MBP-00188 was voided"})
    assert r2.status_code == 201 and r2.json()["revision"] == 2
    sarah = api.as_("sarah.mitchell").get(url, params={"season_year": 2026}).json()
    assert sarah["draft"] is None
    assert [(x["revision"], x["status"]) for x in sarah["issued"]] == [
        (2, "issued"), (1, "superseded")
    ]  # fmt: skip


def test_AC6_AC47_action_panel(api: Api, db: Session) -> None:
    pid = project(db, "RBT-52").id
    faisal = api.as_("faisal.harbi")
    pt = point(db, "P-STWR-M1")
    res = faisal.patch(f"{API}/monitoring-points/{pt.id}",
                       json={"zone_ids": [str(zone(db, "Z-TC01").id)]})  # fmt: skip
    assert res.status_code == 200, res.text
    res = faisal.patch(f"{API}/projects/{pid}/heat-settings",
                       json={"heat_ptw_enforcement_from": "2026-10-07"})  # fmt: skip
    assert res.status_code == 422 and err(res) == "HEAT_COVERAGE_INCOMPLETE", res.text
    assert "Z-FAC" in res.text
    panel = faisal.get(f"{API}/projects/{pid}/heat-action-panel").json()
    items = {i["kind"]: i for i in panel["items"]}
    assert items["required_zone_without_point"]["refs"] == ["Z-FAC"]
    # MB-4: a violation with a permit_id lists the patrol
    ania = project(db, "ANIA-EXP").id
    p = db.scalar(select(BanPatrol).where(BanPatrol.patrol_no == "MBP-ANIA-EXP-2026-00214"))
    assert p is not None
    from app.models import Permit

    permit = db.scalar(select(Permit).where(Permit.project_id == ania))
    assert permit is not None
    p.permit_id = permit.id
    p.checked_at = p.checked_at.replace(month=10, day=5)
    db.commit()
    panel = faisal.get(f"{API}/projects/{ania}/heat-action-panel").json()
    items = {i["kind"]: i for i in panel["items"]}
    assert items["permit_ban_violation"]["refs"] == ["MBP-ANIA-EXP-2026-00214"]
    assert items["r4_permit_not_suspended"]["count"] == 0
    assert eng(db, "ANIA-EXP", "RAWABI") is not None
