"""6b-heat-stress §9 ACs 1-5, 7 (regime table, settings, instruments, points, station device)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.models import AuditEntry, HeatRegimeLimit
from tests.conftest import Api
from tests.heat_helpers import API, err, instrument, local, notified, point, project, zone

pytestmark = pytest.mark.usefixtures("heat_seed", "clock")


def _cell(db: Session) -> HeatRegimeLimit:
    db.expire_all()
    r = db.scalar(
        select(HeatRegimeLimit).where(
            HeatRegimeLimit.basis == "acclimatised",
            HeatRegimeLimit.regime == "R2",
            HeatRegimeLimit.workload == "heavy",
        )
    )
    assert r is not None
    return r


def test_AC1_regime_table_tighten_only(api: Api, db: Session) -> None:
    row = {"basis": "acclimatised", "regime": "R2", "workload": "heavy"}
    pid = project(db, "ANIA-EXP").id
    noura = api.as_("noura.qahtani")
    assert noura.patch(f"{API}/heat-regime-table",
                       json={"rows": [{**row, "limit_c": "28.5"}]}).status_code == 403  # fmt: skip
    assert noura.patch(f"{API}/projects/{pid}/heat-settings",
                       json={"regime_relax_minutes": 45}).status_code == 403  # fmt: skip
    faisal = api.as_("faisal.harbi")
    res = faisal.patch(f"{API}/heat-regime-table", json={"rows": [{**row, "limit_c": "28.5"}]})
    assert res.status_code == 200, res.text
    assert str(_cell(db).limit_c) == "28.5"
    assert db.scalar(select(AuditEntry.id).where(AuditEntry.entity_type == "heat_regime_table"))
    res = faisal.patch(f"{API}/heat-regime-table", json={"rows": [{**row, "limit_c": "29.5"}]})
    assert res.status_code == 422 and err(res) == "REGIME_LOOSENING", res.text


def test_AC2_AC3_settings(api: Api, db: Session) -> None:
    from app.core.heat_enums import AcclimatisationBasis, Regime, Workload
    from app.services.heat import common as hc

    pid = project(db, "ANIA-EXP").id
    faisal = api.as_("faisal.harbi")
    url = f"{API}/projects/{pid}/heat-settings"
    assert faisal.patch(url, json={"wbgt_limit_offset_c": "0.5"}).status_code == 422
    res = faisal.patch(url, json={"wbgt_limit_offset_c": "-1.0"})
    assert res.status_code == 200, res.text
    db.expire_all()
    hc.clear_cache(db)
    c = hc.cfg(db, pid)
    t = hc.table(db)
    from decimal import Decimal

    assert hc.regime_for(
        t, c.offset, AcclimatisationBasis.acclimatised, Workload.moderate, Decimal("27.8")
    ) == (Regime.R1)
    res = faisal.patch(
        url, json={"heat_controls_period": {"start_mmdd": "06-15", "end_mmdd": "09-15"}}
    )
    assert res.status_code == 422 and err(res) in ("PERIOD_TOO_SHORT", "SETTING_LOOSENING")


def test_AC4_instruments_calibration(api: Api, db: Session) -> None:
    from app.heat_jobs import heat_alerts, heat_daily

    pid = project(db, "ANIA-EXP").id
    faisal = api.as_("faisal.harbi")
    res = faisal.post(
        f"{API}/projects/{pid}/heat-instruments",
        json={"kind": "handheld_meter", "make_model": "Cheap meter", "serial_no": "TEST-X1",
              "iso7243_compliant": False, "calibration_valid_until": "2027-06-30",
              "calibration_cert_ref": "TEST-CAL-X1"},
    )  # fmt: skip
    assert res.status_code == 422 and err(res) == "INSTRUMENT_NOT_COMPLIANT", res.text
    sent: list[date] = []
    for d in (date(2026, 9, 20), date(2026, 9, 21), date(2026, 10, 6), date(2026, 10, 13),
              date(2026, 10, 19), date(2026, 10, 20)):  # fmt: skip
        set_now(local(d.year, d.month, d.day, 7, 4))
        before = sum(len(v) for v in notified(db, "heat_calibration_expiry").values())
        heat_alerts(db)
        db.commit()
        after = notified(db, "heat_calibration_expiry")
        if sum(len(v) for v in after.values()) > before:
            sent.append(d)
            assert "noura.qahtani" in after
    assert sent == [date(2026, 9, 20), date(2026, 10, 6), date(2026, 10, 13), date(2026, 10, 20)]
    set_now(local(2026, 10, 21, 0, 7))
    heat_daily(db)
    db.commit()
    db.expire_all()
    assert instrument(db, "HSM-ANIA-EXP-02").status.value == "quarantined"


def test_AC5_zone_already_covered(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    site = point(db, "P-SLAND-M1").site_id
    res = api.as_("noura.qahtani").post(
        f"{API}/projects/{pid}/monitoring-points",
        json={"point_code": "P-SLAND-M2", "site_id": str(site),
              "zone_ids": [str(zone(db, "Z-LAY1").id)], "source_kind": "manual"},
    )  # fmt: skip
    assert res.status_code == 422 and err(res) == "ZONE_ALREADY_COVERED", res.text


def test_AC7_station_device(api: Api, db: Session) -> None:
    ins = instrument(db, "HSM-ANIA-EXP-01")
    faisal = api.as_("faisal.harbi")
    res = faisal.post(f"{API}/heat-instruments/{ins.id}/devices",
                      json={"device_id": "DEV-WS-ANIA-02", "label": "Second station"})  # fmt: skip
    assert res.status_code == 201, res.text
    dev, token = res.json()["device"], res.json()["device_token"]
    s = api.anon.post(f"{API}/heat/station-session", json={"device_token": token})
    assert s.status_code in (200, 201), s.text
    h = {"Authorization": f"Bearer {s.json()['access_token']}"}
    pid = project(db, "ANIA-EXP").id
    assert api.anon.get(f"{API}/projects/{pid}/heat-board", headers=h).status_code == 403
    assert api.anon.get(f"{API}/projects/{pid}/gates", headers=h).status_code in (403, 404)
    body = {"measured_at": local(2026, 10, 6, 9, 59).isoformat(), "wbgt_entered_c": "27.7"}
    r1 = api.anon.post(f"{API}/heat/station-readings", json=body, headers=h)
    assert r1.status_code in (200, 201), r1.text
    r2 = api.anon.post(f"{API}/heat/station-readings", json=body, headers=h)
    assert r2.json()["id"] == r1.json()["id"]  # AC11: idempotent per (device, measured_at)
    rv = faisal.post(f"{API}/heat-instruments/{ins.id}/devices/{dev['id']}/revoke",
                     json={"reason": "Device stolen from the site office"})  # fmt: skip
    assert rv.status_code == 200, rv.text
    body["measured_at"] = local(2026, 10, 6, 9, 58).isoformat()
    assert api.anon.post(f"{API}/heat/station-readings", json=body, headers=h).status_code == 401
