# ruff: noqa: E501, RUF015
"""Phase 6e instruments, points, limits, readings and exceedances (6e §9 AC 20-33, 45)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.env_enums import Averaging, EnvReadingSource, Parameter
from app.env_jobs import env_alerts, env_daily
from app.models import CorrectiveAction, EnvExceedance, EnvInstrument, EnvReading, WorkforceReturn
from app.schemas.env import (
    EnvDeviceCreate,
    EnvInstrumentCreate,
    EnvPermitUpdate,
    EnvPointUpdate,
    EnvReadingCreate,
    ExceedanceReview,
)
from app.services.env import exceedances, monitoring, register
from tests.conftest import Api
from tests.env_helpers import (
    API,
    D,
    P,
    eng,
    exd,
    expect,
    kpi,
    kpis,
    local,
    notified,
    permit,
    point,
    project,
    prov,
    tick,
    uid,
)
from tests.env_helpers import fresh as _fresh


def _reading(db: Session, code: str, param: str, avg: str, ws: datetime, we: datetime,
             value: str, **kw: object) -> EnvReadingCreate:  # fmt: skip
    return EnvReadingCreate.model_validate({
        "point_id": point(db, code).id, "parameter": param, "averaging": avg,
        "window_start": ws, "window_end": we, "value": D(value), **kw,
    })  # fmt: skip


def test_calibration_expiry(env_seed: None, db: Session) -> None:
    """AC 20: reading after calibration end → 422; quarantined on 10-06; alerts 30/14/7/0."""
    tick(2026, 9, 1, 9)
    p = P(db, "noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    ins = monitoring.create_instrument(db, p, pid, EnvInstrumentCreate(
        kind="pm_sampler_24h", make_model="MiniVol (TEST)", serial_no="SN-TEST-CAL",
        calibration_valid_until=date(2026, 10, 5), calibration_cert_ref="CAL-TEST-9"))  # fmt: skip
    sent = []
    for d in (date(2026, 9, 5), date(2026, 9, 21), date(2026, 9, 28), date(2026, 10, 5),
              date(2026, 10, 1)):  # fmt: skip
        n0 = len(notified(db, "env_instrument_calibration").get("noura.qahtani", []))
        tick(d.year, d.month, d.day, 7, 8)
        env_alerts(db)
        sent.append(len(notified(db, "env_instrument_calibration").get("noura.qahtani", [])) - n0)
    assert sent == [1, 1, 1, 1, 0]
    tick(2026, 10, 6, 0, 11)
    env_daily(db)
    x = db.get(EnvInstrument, ins.id)
    assert x is not None and x.status.value == "quarantined"
    tick(2026, 10, 6, 10)
    body = _reading(db, "D-SLAND-01", "pm10", "24h", local(2026, 10, 5, 9), local(2026, 10, 6, 9),
                    "120", instrument_id=str(ins.id))  # fmt: skip
    expect("INSTRUMENT_CALIBRATION_EXPIRED",
           lambda: monitoring.create_reading(db, p, pid, body))  # fmt: skip


def test_manual_reading_rules(env_seed: None, clock: None, db: Session) -> None:
    """AC 21: field calibration, 72 h back-dating, value range."""
    p = P(db, "noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    noise = _reading(db, "N-SLAND-01", "laeq", "measurement", local(2026, 10, 6, 9),
                     local(2026, 10, 6, 9, 30), "64")  # fmt: skip
    expect("FIELD_CALIBRATION_REQUIRED", lambda: monitoring.create_reading(db, p, pid, noise))
    old = _reading(db, "D-SLAND-01", "pm10", "24h", local(2026, 10, 1, 1), local(2026, 10, 2, 22),
                   "120")  # fmt: skip
    expect("BACKDATED_READING", lambda: monitoring.create_reading(db, p, pid, old))
    big = _reading(db, "D-SLAND-01", "pm10", "24h", local(2026, 10, 5, 9), local(2026, 10, 6, 9),
                   "25000")  # fmt: skip
    expect("VALUE_OUT_OF_RANGE", lambda: monitoring.create_reading(db, p, pid, big))
    ok = monitoring.create_reading(db, p, pid, noise.model_copy(
        update={"field_calibration_checked": True}))  # fmt: skip
    assert ok.result == "ok" and ok.period == "day"


def test_limits_tighten_only_and_permit_condition(env_seed: None, clock: None, db: Session) -> None:
    """AC 22: LIMIT_LOOSENING; 300 saved and audited; a permit condition of 280 wins."""
    from app.models import AuditEntry as AuditLog

    p = P(db, "noura.qahtani")
    pt = point(db, "D-SAIR-01")

    def reqs(lim: str) -> EnvPointUpdate:
        return EnvPointUpdate.model_validate({"requirements": [
            {"parameter": "pm10", "averaging": "1h", "schedule": "continuous"},
            {"parameter": "pm10", "averaging": "24h", "schedule": "continuous", "limit_value": lim},
        ]})  # fmt: skip

    expect("LIMIT_LOOSENING", lambda: monitoring.update_point(db, p, pt.id, reqs("400")))
    out = monitoring.update_point(db, p, pt.id, reqs("300"))
    row = [r for r in out.requirements if r.averaging == "24h"][0]
    assert D(row.limit_value or 0) == 300
    assert db.scalar(select(AuditLog.id).where(AuditLog.entity_id == pt.id)) is not None
    pm = permit(db, "ENVP-TEST-0001")
    register.update_permit(db, p, pm.id, EnvPermitUpdate.model_validate({"conditions": [{
        "code": "C-07", "text_en": "PM10 24-h at the taxiway ≤ 280", "point_id": str(pt.id),
        "parameter": "pm10", "averaging": "24h", "limit_value": "280"}]}))  # fmt: skip
    _fresh(db)
    out = monitoring.read_point(db, p, pt.id)
    row = [r for r in out.requirements if r.averaging == "24h"][0]
    assert D(row.effective_limit or 0) == 280 and row.effective_source == "permit_condition"


def _hour(db: Session, code: str, d: date, h: int, value: str) -> EnvReading:
    pt = point(db, code)
    ws = local(d.year, d.month, d.day, h)
    return monitoring.make_reading(db, pt, Parameter.pm10, Averaging.h1, ws, ws + timedelta(hours=1),
                                   D(value), EnvReadingSource.derived)  # fmt: skip


def test_station_exceedance_and_airside_alert(env_seed: None, api: Api, db: Session) -> None:
    """AC 23, 33: EV2 through the station (640.0, 28.0 %), officer / engineer and airside alerts;
    duplicates ignored; the env_monitor token is refused at gate checks."""
    since = tick(2026, 10, 6, 9, 5)
    pt = point(db, "D-SAIR-01")
    reg = monitoring.register_device(db, P(db, "noura.qahtani"), pt.instrument_id,
                                     EnvDeviceCreate(device_id="DEV-EM-TEST", label="Test"))  # fmt: skip
    db.commit()
    c = api.anon
    r = c.post(f"{API}/env/station-session", json={"device_token": reg.device_token})
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    vals = [{"parameter": "pm10", "window_start": (local(2026, 10, 6, 8) + timedelta(minutes=15 * i)).isoformat(),
             "value": v} for i, v in enumerate(("610", "655", "640", "655"))]  # fmt: skip
    r = c.post(f"{API}/env/station-readings", json={"values": vals}, headers=h)
    assert r.status_code == 200, r.text
    r2 = c.post(f"{API}/env/station-readings", json={"values": vals[:1]}, headers=h)
    assert r2.json()["duplicates"] == 1 and r2.json()["accepted"] == 0
    db.expire_all()
    x = db.scalar(select(EnvExceedance).where(EnvExceedance.day == date(2026, 10, 6),
                                              EnvExceedance.point_id == pt.id))  # fmt: skip
    assert x is not None and D(x.peak_value) == D("640") and D(x.margin_pct) == D("28.0")
    got = notified(db, "env_exceedance", since)
    assert {"noura.qahtani", "omar.siddiqui"} <= set(got), got
    air = notified(db, "airside_dust_alert", since)
    assert {"khalid.otaibi", "faisal.harbi"} <= set(air), air
    r = c.get(f"{API}/gate-checks/context", headers=h)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "GATE_DEVICE_FORBIDDEN"


def test_episodes(env_seed: None, clock: None, db: Session) -> None:
    """AC 24: three exceeding hours, one compliant, one exceeding → two exceedances (3 + 1)."""
    d = date(2026, 10, 6)
    for h, v in enumerate(("600", "610", "620", "200", "630")):
        _hour(db, "D-SAIR-01", d, h, v)
    xs = db.scalars(select(EnvExceedance).where(EnvExceedance.day == d)
                    .order_by(EnvExceedance.started_at)).all()  # fmt: skip
    assert [len(x.reading_ids) for x in xs] == [3, 1]
    assert D(xs[0].peak_value) == 620


def test_background_auto_review_and_reclassify(
    env_seed: None, clock: None, api: Api, db: Session
) -> None:
    """AC 25-26: EV2b background (OPS-0009), auto-reviewed, not in K-123; reclassified → CA high,
    counted. BGD-RBT-52-2026-001 flags the D-STWR-01 sample, not a noise reading."""
    x = exd(db, "ENX-ANIA-EXP-2026-0018")
    assert x.background_ref == "OPS-ANIA-EXP-2026-0009" and x.ca_id is None
    x.status, x.cause, x.reviewed_at = "open", None, None
    db.flush()
    exceedances.daily(db, x.project_id, date(2026, 10, 1))
    assert (x.status.value, x.cause.value if x.cause else None) == ("closed", "background_natural")
    db.commit()
    f = api.as_("faisal.harbi")
    assert kpi(kpis(f, x.project_id), "K123")["value"] == "1"
    exceedances.review(db, P(db, "noura.qahtani"), x.id, ExceedanceReview(
        cause="project_activity", responsible_engagement_id=eng(db, "ANIA-EXP", "GULFPAVE").id,
        activity_en="Night milling", immediate_action_en="Stopped the milling"))  # fmt: skip
    ca = db.get(CorrectiveAction, x.ca_id)
    assert ca is not None and ca.priority.value == "high"
    db.commit()
    assert kpi(kpis(f, x.project_id), "K123")["value"] == "2"
    d03 = db.scalar(select(EnvReading).where(
        EnvReading.point_id == point(db, "D-STWR-01").id, EnvReading.day == date(2026, 9, 3)))  # fmt: skip
    assert d03 is not None and d03.background and d03.background_ref == "BGD-RBT-52-2026-001"
    n03 = db.scalar(select(EnvReading).where(
        EnvReading.point_id == point(db, "N-STWR-01").id,
        EnvReading.window_start == local(2026, 9, 3, 12), EnvReading.averaging == "1h"))  # fmt: skip
    assert n03 is not None and not n03.background


def test_data_capture_24h(env_seed: None, clock: None, api: Api, db: Session) -> None:
    """AC 27: 17 hours → no 24-h value (slot unmet); 18 hours → 24-h value, slot met."""
    pt = point(db, "D-SAIR-01")
    d = date(2026, 9, 5)

    def h24() -> EnvReading | None:
        return db.scalar(select(EnvReading).where(EnvReading.point_id == pt.id,
                                                  EnvReading.day == d, EnvReading.averaging == "24h"))  # fmt: skip

    upto = local(2026, 9, 6, 0, 30)
    monitoring.derive(db, pt, upto)
    assert h24() is None
    _hour(db, "D-SAIR-01", d, 20, "180")
    monitoring.derive(db, pt, upto)
    assert h24() is not None
    db.commit()
    assert kpi(kpis(api.as_("faisal.harbi"), pt.project_id), "K122")["value"] == "98.0"


def test_noise_ev3(env_seed: None, db: Session) -> None:
    """AC 28: 61.3 dB(A) night exceedance; the 21:00 hour is an alert only."""
    pt = point(db, "N-STWR-01")
    rs = {r.window_start: r for r in db.scalars(select(EnvReading).where(
        EnvReading.point_id == pt.id, EnvReading.day == date(2026, 9, 10),
        EnvReading.averaging == "1h"))}  # fmt: skip
    r23, r21 = rs[local(2026, 9, 10, 23)], rs[local(2026, 9, 10, 21)]
    assert D(r23.value).quantize(D("0.1")) == D("61.3") and r23.period.value == "night"
    assert r23.result.value == "exceedance" and r23.exceedance_id is not None
    assert (r21.result.value, r21.period.value, r21.exceedance_id) == ("alert", "day", None)
    assert monitoring.mean(Parameter.laeq, [D(60), D(62), D(61), D(62)]).quantize(D("0.1")) == D(
        "61.3"
    )


def test_visual_review_and_overdue_review(env_seed: None, clock: None, db: Session) -> None:
    """AC 29-30: visual 3 → exceedance + airside alert; 2 → alert only; review rules; daily
    review reminders after 3 days."""
    since = tick(2026, 10, 6, 10)
    p = P(db, "omar.siddiqui")
    pid = project(db, "ANIA-EXP").id
    two = monitoring.create_reading(db, p, pid, _reading(
        db, "V-SAIR", "visual_dust", "spot", local(2026, 10, 6, 9, 40), local(2026, 10, 6, 9, 45), "2"))  # fmt: skip
    assert (two.result, two.exceedance_id) == ("alert", None)
    three = monitoring.create_reading(db, p, pid, _reading(
        db, "V-SAIR", "visual_dust", "spot", local(2026, 10, 6, 9, 50), local(2026, 10, 6, 9, 55), "3"))  # fmt: skip
    assert three.result == "exceedance" and three.exceedance_id is not None
    assert "faisal.harbi" in notified(db, "airside_dust_alert", since)
    noura = P(db, "noura.qahtani")
    bad = ExceedanceReview(cause="project_activity", immediate_action_en="Watered the road")
    expect("ENGAGEMENT_REQUIRED", lambda: exceedances.review(db, noura, three.exceedance_id, bad))
    # unreviewed: reminders from the deadline, daily
    counts = []
    for d in (8, 9, 10, 11):
        n0 = len(notified(db, "env_exceedance").get("noura.qahtani", []))
        tick(2026, 10, d, 7, 8)
        env_alerts(db)
        counts.append(len(notified(db, "env_exceedance").get("noura.qahtani", [])) - n0)
    assert counts == [0, 1, 1, 1]
    out = exceedances.review(db, noura, three.exceedance_id, bad.model_copy(update={
        "responsible_engagement_id": eng(db, "ANIA-EXP", "GULFPAVE").id}))  # fmt: skip
    ca = db.get(CorrectiveAction, out.ca_id)
    assert (
        ca is not None and ca.priority.value == "high" and ca.owner_id == uid(db, "ahmed.zahrani")
    )


def test_lab_results(env_seed: None, clock: None, db: Session) -> None:
    """AC 31, 45: late lab TSS → exceedance dated at sampling, labelled late; pH limits."""
    x = exd(db, "ENX-RBT-52-2026-0006")
    assert (x.day, x.late_result) == (date(2026, 9, 24), True)
    since = tick(2026, 10, 6, 10)
    p = P(db, "lina.haddad")
    pid = project(db, "RBT-52").id
    lab = {"lab_provider_id": str(prov(db, "ENVLAB").id), "lab_report_ref": "ENVLAB-TEST-X"}
    t = monitoring.create_reading(db, p, pid, _reading(
        db, "W-SPOD-01", "tss", "spot", local(2026, 10, 2, 8), local(2026, 10, 2, 8, 15), "90", **lab))  # fmt: skip
    xe = db.get(EnvExceedance, t.exceedance_id)
    assert xe is not None and xe.late_result and xe.day == date(2026, 10, 2)
    assert "lina.haddad" in notified(db, "env_exceedance", since)
    results = []
    for i, v in enumerate(("9.4", "5.8", "7.5")):
        r = monitoring.create_reading(db, p, pid, _reading(
            db, "W-SPOD-01", "ph", "spot", local(2026, 10, 3, 8, i), local(2026, 10, 3, 8, 10 + i), v,
            **lab))  # fmt: skip
        results.append(r.result)
    assert results == ["exceedance", "exceedance", "ok"]


def test_no_work_no_slot(env_seed: None, clock: None, api: Api, db: Session) -> None:
    """AC 32: a day without a daily return on the site creates no slot (V-SLAND 09-19)."""
    pid = project(db, "ANIA-EXP").id
    f = api.as_("faisal.harbi")
    assert kpi(kpis(f, pid), "K122")["value"] == "96.9"
    site = point(db, "V-SLAND").site_id
    for w in db.scalars(select(WorkforceReturn).where(
            WorkforceReturn.site_id == site, WorkforceReturn.work_date == date(2026, 9, 19))):  # fmt: skip
        w.headcount = 0
    db.commit()
    k = kpi(kpis(f, pid), "K122")
    assert (k["numerator"], k["denominator"], k["value"]) == ("95", "97", "97.9")
