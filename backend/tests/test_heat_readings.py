"""6b-heat-stress §9 ACs 8-17 (WBGT, regime cells, zone state, readings, HA-1/HA-3)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.core.heat_enums import AcclimatisationBasis, Clothing, ReadingSource, Regime, Workload
from app.schemas.heat import ReadingComponents
from app.services.heat import common as hc
from app.services.heat import readings, state
from tests.conftest import Api
from tests.heat_helpers import (
    API,
    err,
    expect,
    instrument,
    local,
    notified,
    point,
    project,
    reading,
    zone,
)

pytestmark = pytest.mark.usefixtures("heat_seed", "clock")
AB = AcclimatisationBasis
W = Workload
D = Decimal


def comps(**kw: str) -> ReadingComponents:
    return ReadingComponents(**{k: D(v) for k, v in kw.items()})


def test_AC8_hs1_formula() -> None:
    tol = D("0.5")
    assert readings.compute_wbgt(comps(tnwb_c="22.4", tg_c="52.0", ta_c="41.0"), True, tol)[0] == (
        D("30.2")
    )
    assert readings.compute_wbgt(comps(tnwb_c="24.0", tg_c="34.0"), False, tol)[0] == D("27.0")
    w, warns = readings.compute_wbgt(
        comps(tnwb_c="22.4", tg_c="52.0", ta_c="41.0", wbgt_entered_c="31.0"), True, tol
    )
    assert w == D("30.2") and [x.code for x in warns] == ["WBGT_COMPONENT_MISMATCH"]
    expect("WBGT_REQUIRED", lambda: readings.compute_wbgt(comps(ta_c="44.0"), True, tol))
    expect("VALUE_OUT_OF_RANGE", lambda: readings.compute_wbgt(comps(wbgt_entered_c="46.0"),
                                                               True, tol))  # fmt: skip


HS2 = {
    "27.8": "R0 R0 R2 R2 R0 R3 R3 R4",
    "30.2": "R0 R3 R3 R4 R4 R4 R4 R4",
    "31.4": "R2 R3 R4 R4 R4 R4 R4 R4",
    "32.1": "R3 R4 R4 R4 R4 R4 R4 R4",
}


def test_AC12_hs2_cells(db: Session) -> None:
    t = hc.table(db)
    for w, row in HS2.items():
        got = [hc.regime_for(t, D(0), b, wl, D(w)).value for b in AB for wl in W]
        assert " ".join(got) == row, w
    eff = hc.effective(D("28.0"), Clothing.double_layer_woven, False)
    assert hc.regime_for(t, D(0), AB.acclimatised, W.moderate, eff) == Regime.R3
    eff = hc.effective(D("28.0"), Clothing.vapour_barrier_coveralls, False)
    assert eff == D("39.0")
    assert all(hc.regime_for(t, D(0), b, wl, eff) == Regime.R4 for b in AB for wl in W)
    assert hc.regime_for(t, D("-1.0"), AB.acclimatised, W.moderate, D("27.8")) == Regime.R1


def _headline(db: Session, at: datetime) -> tuple[str, Regime]:
    pid = project(db, "ANIA-EXP").id
    db.expire_all()
    hc.clear_cache(db)
    zs = state.zone_state(db, pid, zone(db, "Z-APR-21").id, at)
    return zs.state.value, state.headline(zs, hc.cfg(db, pid))


def _station(db: Session, at: datetime, w: str, alert: bool = True) -> Any:
    pt = point(db, "P-SAIR-STN")
    ins = instrument(db, "HSM-ANIA-EXP-01")
    set_now(at)
    m = readings.make(db, pt, ins, comps(wbgt_entered_c=w), at, ReadingSource.station,
                      alert=alert)  # fmt: skip
    db.commit()
    return m.reading


def test_AC13_AC14_AC15_hs3_state(db: Session) -> None:
    assert _headline(db, local(2026, 10, 6, 9, 59)) == ("current", Regime.R1)
    assert _headline(db, local(2026, 10, 6, 10, 0)) == ("current", Regime.R2)
    # WR-9: no reading after 10:00 → stale after 10:20 with R2 kept
    assert _headline(db, local(2026, 10, 6, 10, 21)) == ("stale", Regime.R2)
    # WR-8: a 10:15 R1 reading keeps R2 until 10:30:00
    _station(db, local(2026, 10, 6, 10, 15), "27.0")
    assert _headline(db, local(2026, 10, 6, 10, 29, 59)) == ("current", Regime.R2)
    assert _headline(db, local(2026, 10, 6, 10, 30, 1)) == ("current", Regime.R1)
    pid = project(db, "ANIA-EXP").id
    zs = state.zone_state(db, pid, zone(db, "Z-PIERB").id, local(2026, 10, 6, 10))
    assert zs.state.value == "unknown"
    assert zone(db, "Z-PIERB").id not in hc.required_zone_ids(db, pid)


def test_AC13_AC16_AC17_alert_and_void(api: Api, db: Session) -> None:
    r = reading(db, "WBG-ANIA-EXP-20261006-0017")
    assert str(r.wbgt_c) == "27.8"
    noura = api.as_("noura.qahtani")
    res = noura.post(f"{API}/wbgt-readings/{r.id}/void", json={"reason": "wrong one"})
    assert res.status_code == 422, res.text
    res = noura.post(f"{API}/wbgt-readings/{r.id}/void",
                     json={"reason": "Sensor shaded by a parked truck"})  # fmt: skip
    assert res.status_code == 200, res.text
    assert _headline(db, local(2026, 10, 6, 10, 0)) == ("current", Regime.R1)
    since = local(2026, 10, 6, 10, 0)
    for mi in (0, 5, 10):  # HA-3: one alert per (zone, regime, direction) per 60 min
        _station(db, local(2026, 10, 6, 10, mi), "27.8")
    got = notified(db, "heat_regime_raised", since)
    assert {"omar.siddiqui", "ahmed.zahrani", "noura.qahtani"} <= set(got)
    assert all(len([t for t in got[u] if "Z-APR-21" in t]) == 1 for u in got)


def test_AC9_AC10_manual_entry(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    omar = api.as_("omar.siddiqui")
    base = {"point_id": str(point(db, "P-SAIR-STN").id),
            "instrument_id": str(instrument(db, "HSM-ANIA-EXP-01").id)}  # fmt: skip
    url = f"{API}/projects/{pid}/wbgt-readings"
    res = omar.post(url, json={**base, "measured_at": local(2026, 10, 6, 9).isoformat(),
                               "ta_c": "44.0"})  # fmt: skip
    assert res.status_code == 422 and err(res) == "WBGT_REQUIRED", res.text
    res = omar.post(url, json={**base, "measured_at": local(2026, 10, 5, 9).isoformat(),
                               "wbgt_entered_c": "28.0"})  # fmt: skip
    assert res.status_code == 422 and err(res) == "BACKDATED_READING", res.text
    since = local(2026, 10, 6, 10)
    res = omar.post(url, json={**base, "measured_at": local(2026, 10, 6, 7).isoformat(),
                               "wbgt_entered_c": "31.5"})  # fmt: skip
    assert res.status_code == 201, res.text
    assert res.json()["late_entry"] is True
    assert notified(db, "heat_regime_raised", since) == {}
