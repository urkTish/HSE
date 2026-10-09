"""6c-emergency-drills §9 ACs 23-29 (emergency equipment, checks, provision gaps)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.emergency_enums import AssetStatus, AssetType, NotReadyReason
from app.emergency_jobs import SHORT, emergency_alerts
from app.models import CorrectiveAction, EmergencyAsset
from app.services.cert.alerts import scheduled_steps
from app.services.emergency import assets as em
from tests.conftest import Api
from tests.emer_helpers import API, asset, err, notified, project, tick, zone

pytestmark = pytest.mark.usefixtures("emergency_seed", "clock")
NR = NotReadyReason
FE_ITEMS = ("EC01", "EC02", "EC03", "EC04", "EC09", "EC10")


def answers(**fails: str) -> list[dict[str, str]]:
    return [{"item": i, "answer": fails.get(i, "pass")} for i in FE_ITEMS]


def check(c: Any, db: Session, body: dict[str, Any]) -> Any:
    return c.post(f"{API}/projects/{project(db, 'ANIA-EXP').id}/emergency-asset-checks", json=body)


def test_AC23_ed6a(db: Session) -> None:
    a = asset(db, "FE-SLAND-0142")
    assert em.readiness(db, a, date(2026, 9, 30)).ready
    r = em.readiness(db, a, date(2026, 10, 6))
    assert NR.CHECK_OVERDUE in r.reasons and not r.ready
    assert (r.service_due, r.hydro_due) == (date(2026, 10, 9), date(2031, 12, 31))
    assert scheduled_steps(r.service_due, SHORT) == [date(2026, 9, 9), date(2026, 10, 2),
                                                     date(2026, 10, 9)]  # fmt: skip
    t = tick(2026, 10, 9, 7, 5)
    emergency_alerts(db, t)
    db.commit()
    titles = [x for v in notified(db, "emergency_asset_due", t).values() for x in v]
    assert any(x.startswith("FE-SLAND-0142: service due 2026-10-09 (0 days)") for x in titles)


def test_AC24_ed6b_ed6c(db: Session) -> None:
    aed = asset(db, "AED-SAIR-01")
    assert NR.CONSUMABLE_EXPIRED not in em.readiness(db, aed, date(2026, 10, 31)).reasons
    assert NR.CONSUMABLE_EXPIRED in em.readiness(db, aed, date(2026, 11, 1)).reasons
    kits = list(db.scalars(select(EmergencyAsset).where(
        EmergencyAsset.asset_type == AssetType.first_aid_kit,
        EmergencyAsset.status == AssetStatus.in_service)))  # fmt: skip
    kit = next(k for k in kits if em.readiness(db, k, date(2026, 10, 6)).ready)
    last = em.last_checks(db, [kit.id])[kit.id]
    due = local_day(last.checked_at) + timedelta(days=7)
    assert em.readiness(db, kit, due).ready
    assert em.readiness(db, kit, due + timedelta(days=1)).reasons == [NR.CHECK_OVERDUE]


def local_day(t: Any) -> date:
    from app.services.emergency import common as ec

    return ec.local_day(t)


def test_AC25_failed_scan_then_pass(api: Api, db: Session) -> None:
    fahad = api.as_("fahad.mutairi")
    a = asset(db, "FE-SLAND-0142")
    payload = fahad.get(f"{API}/emergency-assets/{a.id}").json()["sticker_payload"]
    t = now()
    res = check(fahad, db, {"sticker_payload": payload, "outcome": "checked",
                            "items": answers(EC03="fail")})  # fmt: skip
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["result"] == "fail" and body["method"] == "qr_scan" and body["ca_ref"]
    db.expire_all()
    assert asset(db, "FE-SLAND-0142").status == AssetStatus.out_of_service
    ca = db.scalar(select(CorrectiveAction).where(CorrectiveAction.ref == body["ca_ref"]))
    assert ca is not None
    assert getattr(ca.priority, "value", ca.priority) == "high"
    assert getattr(ca.source_type, "value", ca.source_type) == "emergency"
    got = notified(db, "emergency_asset_failed", t)
    assert {"fahad.mutairi", "ahmed.zahrani", "noura.qahtani"} <= set(got), got
    res = check(fahad, db, {"sticker_payload": payload, "outcome": "checked", "items": answers()})
    assert res.status_code == 201 and res.json()["result"] == "pass"
    db.expire_all()
    assert asset(db, "FE-SLAND-0142").status == AssetStatus.in_service


def test_AC26_non_critical_and_missing(api: Api, db: Session) -> None:
    noura = api.as_("noura.qahtani")
    a = asset(db, "FE-SLAND-0142")
    res = check(noura, db, {"asset_id": str(a.id), "outcome": "checked",
                            "items": answers(EC09="fail"), "fixed_on_spot": True})  # fmt: skip
    assert res.status_code == 201, res.text
    assert (res.json()["result"], res.json()["ca_ref"]) == ("pass", None)
    res = check(noura, db, {"asset_id": str(a.id), "outcome": "missing"})
    assert res.status_code == 201 and res.json()["ca_ref"]
    db.expire_all()
    assert asset(db, "FE-SLAND-0142").status == AssetStatus.missing


def test_AC27_manual_and_backdated(api: Api, db: Session) -> None:
    ramesh = api.as_("ramesh.kumar")
    a = asset(db, "FE-SLAND-0142")
    res = check(ramesh, db, {"asset_id": str(a.id), "outcome": "checked", "items": answers()})
    assert res.status_code == 201, res.text
    assert [w["code"] for w in res.json()["warnings"]] == ["CHECK_WITHOUT_SCAN"]
    old = (now() - timedelta(hours=73)).isoformat()
    res = check(ramesh, db, {"asset_id": str(a.id), "outcome": "checked", "items": answers(),
                             "checked_at": old})  # fmt: skip
    assert res.status_code == 422 and err(res) == "CHECK_BACKDATED"


def test_AC28_provision_gap(api: Api, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 1 returns carry no zone (§6.2: such rows add no zone), so Z-LAY1 is given as the
    zone with work."""
    from app.services.emergency import board as em_board

    tick(2026, 9, 30, 10)
    lay1 = zone(db, "Z-LAY1").id
    fes = list(db.scalars(select(EmergencyAsset).where(
        EmergencyAsset.zone_id == lay1,
        EmergencyAsset.asset_type == AssetType.fire_extinguisher)))  # fmt: skip
    ready = [x for x in fes if em.readiness(db, x, date(2026, 9, 30)).ready]
    for x in ready[1:]:
        x.status = AssetStatus.out_of_service
        x.status_changed_on = None
    db.commit()
    pid = project(db, "ANIA-EXP").id
    land_id = asset(db, "FE-SLAND-0142").site_id
    monkeypatch.setattr(em_board, "_today_zones", lambda *_: {land_id: [lay1]})
    noura = api.as_("noura.qahtani")
    board = noura.get(f"{API}/projects/{pid}/emergency-board").json()
    land = next(s for s in board["sites"] if s["site_code"] == "S-LAND")
    assert "Z-LAY1: ready extinguishers 1 < 2" in land["provision_gaps"], land
    panel = noura.get(f"{API}/projects/{pid}/emergency-action-panel").json()
    gap = next(i for i in panel["items"] if i["kind"] == "provision_gaps")
    assert any("Z-LAY1" in r for r in gap["refs"])


def test_AC29_not_a_phase4_item(api: Api, db: Session) -> None:
    from app.core.cert_enums import EquipmentCertCategory

    assert "fire_extinguisher" not in {c.value for c in EquipmentCertCategory}
    # BD6c-3: K-72 / K-74 are computed from Phase 4 tables only
    from app.kpi import engine as eng_mod

    src = " ".join(str(getattr(f, "__module__", "")) for k, f in eng_mod._DISPATCH.items()
                   if str(k).endswith(("72", "74")))  # fmt: skip
    assert "emergency" not in src
