"""6b-heat-stress §9 ACs 38-45 (welfare checks, midday-ban patrols and exemptions)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.heat_enums import WelfareItem
from app.models import CorrectiveAction, RestStation
from tests.conftest import Api
from tests.heat_helpers import API, eng, err, local, notified, project, station, tick, zone

pytestmark = pytest.mark.usefixtures("heat_seed", "clock")


def items(**over: str) -> list[dict[str, str]]:
    return [{"item": i.value, "answer": over.get(i.value, "pass")} for i in WelfareItem]


def check(c: Any, db: Session, code: str, at: datetime, pcode: str = "ANIA-EXP", **kw: Any) -> Any:
    pid = project(db, pcode).id
    body = {"station_id": str(station(db, code).id), "checked_at": at.isoformat(),
            "items": items(**kw.pop("over", {})), **kw}  # fmt: skip
    return c.post(f"{API}/projects/{pid}/heat-welfare-checks", json=body)


def test_AC38_AC39_welfare_fail(api: Api, db: Session) -> None:
    omar = api.as_("omar.siddiqui")
    since = local(2026, 10, 6, 10)
    res = check(omar, db, "RS-SAIR-01", local(2026, 10, 6, 9, 30), over={"HW05": "fail"},
                water_temp_c="12.0")  # fmt: skip
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["critical_fail"] is True and len(body["ca_refs"]) == 1
    ca = db.scalar(select(CorrectiveAction).where(CorrectiveAction.ref == body["ca_refs"][0]))
    assert ca is not None
    assert (ca.source_type.value, ca.priority.value) == ("heat_check", "high")
    assert ca.due_date.isoformat() == "2026-10-07"
    got = notified(db, "heat_welfare_fail", since)
    assert {"omar.siddiqui", "noura.qahtani"} <= set(got)
    res = check(omar, db, "RS-SAIR-01", local(2026, 10, 6, 9, 40), over={"HW07": "fail"})
    assert res.status_code == 201 and res.json()["ca_refs"] == []
    res = check(omar, db, "RS-SAIR-01", local(2026, 10, 6, 9, 45), water_temp_c="18.0")
    hw02 = next(i for i in res.json()["items"] if i["item"] == "HW02")
    assert hw02["answer"] == "fail"


def test_AC40_AC41_na_and_scope(api: Api, db: Session) -> None:
    omar = api.as_("omar.siddiqui")
    res = check(omar, db, "RS-SAIR-01", local(2026, 10, 6, 10, 0), over={"HW10": "na"})
    assert res.status_code == 422 and err(res) == "NA_NOT_ALLOWED", res.text
    res = check(omar, db, "RS-SAIR-01", local(2026, 10, 6, 6, 15), over={"HW10": "na"})
    assert res.status_code == 201, res.text
    st = db.scalar(select(RestStation).where(RestStation.station_code == "RS-SAIR-02"))
    assert st is not None
    st.active = False
    db.commit()
    res = check(omar, db, "RS-SAIR-02", local(2026, 10, 6, 9))
    assert res.status_code == 422 and err(res) == "STATION_INACTIVE", res.text
    ramesh = api.as_("ramesh.kumar")
    assert check(ramesh, db, "RS-SLAND-01", local(2026, 10, 6, 9)).status_code == 201
    assert check(ramesh, db, "RS-TWR-01", local(2026, 10, 6, 9)).status_code == 404


def patrol(c: Any, db: Session, z: str, at: datetime, outcome: str, **kw: Any) -> Any:
    pid = project(db, "ANIA-EXP").id
    body = {"zone_id": str(zone(db, z).id), "checked_at": at.isoformat(), "outcome": outcome,
            **kw}  # fmt: skip
    return c.post(f"{API}/projects/{pid}/ban-patrols", json=body)


def test_AC42_hs9b_window(api: Api, db: Session) -> None:
    tick(2026, 9, 15, 15, 5)
    noura = api.as_("noura.qahtani")
    assert patrol(noura, db, "Z-LAY1", local(2026, 9, 15, 15, 0, 0),
                  "no_outdoor_work").status_code == 201  # fmt: skip
    res = patrol(noura, db, "Z-LAY1", local(2026, 9, 15, 15, 0, 1), "no_outdoor_work")
    assert res.status_code == 422 and err(res) == "NOT_IN_BAN_WINDOW", res.text
    tick(2026, 9, 16, 13, 5)
    res = patrol(api.as_("noura.qahtani"), db, "Z-LAY1", local(2026, 9, 16, 13), "no_outdoor_work")
    assert res.status_code == 422 and err(res) == "NOT_IN_BAN_WINDOW", res.text


def test_AC43_violation(api: Api, db: Session) -> None:
    tick(2027, 7, 14, 12, 45)
    assert patrol(api.as_("ahmed.zahrani"), db, "Z-LAY1", local(2027, 7, 14, 12, 40),
                  "no_outdoor_work").status_code == 403  # fmt: skip
    fahad = api.as_("fahad.mutairi")
    sahara = str(eng(db, "ANIA-EXP", "SAHARA").id)
    res = patrol(fahad, db, "Z-LAY1", local(2027, 7, 14, 12, 40), "violation",
                 engagement_id=sahara, activity="loading scaffold tubes")  # fmt: skip
    assert res.status_code == 422, res.text
    since = local(2027, 7, 14, 12, 0)
    res = patrol(fahad, db, "Z-LAY1", local(2027, 7, 14, 12, 40), "violation",
                 engagement_id=sahara, headcount=4, activity="loading scaffold tubes")  # fmt: skip
    assert res.status_code == 201, res.text
    ca = db.scalar(select(CorrectiveAction).where(CorrectiveAction.ref == res.json()["ca_ref"]))
    assert ca is not None and ca.due_date.isoformat() == "2027-07-15"
    got = notified(db, "heat_ban_violation", since)
    assert {"ahmed.zahrani", "noura.qahtani", "faisal.harbi"} <= set(got)


def test_AC44_AC45_exemptions(api: Api, db: Session) -> None:
    tick(2027, 7, 14, 9)
    pid = project(db, "ANIA-EXP").id
    url = f"{API}/projects/{pid}/ban-exemptions"
    body = {"engagement_id": str(eng(db, "ANIA-EXP", "RAWABI").id),
            "zone_ids": [str(zone(db, "Z-LAY1").id)], "date_from": "2027-07-20",
            "date_to": "2027-07-21", "reason": "emergency_repair",
            "controls_en": "Shade canopy, 15/45 regime and a paramedic on standby"}  # fmt: skip
    assert api.as_("noura.qahtani").post(url, json=body).status_code == 403
    faisal = api.as_("faisal.harbi")
    res = faisal.post(url, json={**body, "date_to": "2027-08-03"})
    assert res.status_code == 422, res.text
    res = faisal.post(url, json={**body, "date_from": "2027-09-20", "date_to": "2027-09-21"})
    assert res.status_code == 422 and err(res) == "OUTSIDE_BAN_PERIOD", res.text
    res = faisal.post(url, json=body)
    assert res.status_code == 201 and res.json()["status"] == "active", res.text
    panel = faisal.get(f"{API}/projects/{pid}/heat-action-panel").json()
    act = next(i for i in panel["items"] if i["kind"] == "active_ban_exemption")
    assert res.json()["exemption_no"] in act["refs"]
    tick(2027, 7, 20, 13, 5)
    fahad = api.as_("fahad.mutairi")
    gp = str(eng(db, "ANIA-EXP", "GULFPAVE").id)
    res = patrol(fahad, db, "Z-LAY1", local(2027, 7, 20, 13), "exempt_work", engagement_id=gp,
                 headcount=3, activity="pipe repair")  # fmt: skip
    assert res.status_code == 422 and err(res) == "NO_ACTIVE_EXEMPTION", res.text
    rawabi = body["engagement_id"]
    res = patrol(fahad, db, "Z-LAY1", local(2027, 7, 20, 13), "exempt_work",
                 engagement_id=rawabi, headcount=3, activity="pipe repair")  # fmt: skip
    assert res.status_code == 201, res.text
