"""Monitoring-gap alerts, pending runs that end as transients, humidity excursions, hold deadlines
on read and the QX16 mock recall on the seed (spec 8-quality Q-STO-04, Q-EXC-03, Q-HLD-02 / -03,
AC-Q3-31, AC-Q3-35; D-351, D-352, D-355). Clock 2026-10-06 10:00 Riyadh."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.quality.common import QNcrStatus
from app.models import Notification, User
from app.models.quality import QNcr
from app.models.quality.q3 import (
    QDamageReport,
    QExcursion,
    QHold,
    QMonitoringGap,
    QStorageZone,
)
from app.services.quality.q3 import engine as eng
from tests.conftest import Api
from tests.quality.q3.h3 import API, RIYADH, L, R, err, import_readings, ok, readings_csv, series

D = Decimal
UTC_MIN = timedelta(minutes=1)


def test_pending_run_is_not_an_excursion_yet() -> None:
    """An out run still open at the end of the data and shorter than the alarm delay is pending,
    neither transient nor an excursion (Q-EXC-03)."""
    t0 = datetime(2026, 10, 5, 6, 0, tzinfo=RIYADH)
    pid = __import__("uuid").uuid4()
    rows = [eng.Reading(pid, t0 + timedelta(minutes=15 * i), D(v)) for i, v in enumerate([3, 3, 9])]
    lim = eng.Limits(D(0), D(4))
    g = eng.grid(rows, {pid: 15}, D(2), lim, t0, t0 + timedelta(minutes=45))
    (run,) = eng.runs(g, eng.Bands(30, D(2), D(5), 60, 240), lim)
    assert run.ongoing and run.pending and not run.transient and run.duration == 15


def _notes(db, title_part: str) -> list[Notification]:  # type: ignore[no-untyped-def]
    db.expire_all()
    return [n for n in db.scalars(select(Notification)) if n.title_en and title_part in n.title_en]


def test_monitoring_gap_alert_once(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    """Q-STO-04: a 65-minute hole in Z-CHL1 opens one gap entry and alerts the 266 holders once,
    without e-mail; a later import around it does not alert again."""
    r = R(db)
    c = api.as_("imran.siddiq")
    pt = r.point("CHL1-P1")
    day = date(2026, 10, 5)
    before = series(L(day, 6), [3.0] * 9)  # 06:00 … 08:00, the last covers to 08:15
    after = series(L(day, 9, 20), [3.0] * 4)  # 09:20 … 10:05
    ok(import_readings(c, r.pid, "point", pt, readings_csv(before + after)), 201)
    gaps = list(db.scalars(select(QMonitoringGap)))
    assert [(g.started_at, g.ended_at, g.minutes) for g in gaps] == [
        (L(day, 8, 15), L(day, 9, 20), 65)
    ]
    sent = _notes(db, "Monitoring gap in Z-CHL1")
    assert sent and len({n.user_id for n in sent}) == len(sent)  # one per recipient
    holders = {n.user_id for n in sent}
    reem = db.scalar(select(User.id).where(User.email == "reem.mutairi@example.com"))
    assert reem in holders
    ok(
        import_readings(
            c, r.pid, "point", pt, readings_csv(series(L(day, 10, 20), [3.0] * 3)), name="b.csv"
        ),
        201,
    )
    assert len(_notes(db, "Monitoring gap in Z-CHL1")) == len(sent)
    rep = ok(
        c.get(
            f"{API}/quality/storage-zones/{r.zone('Z-CHL1')}/report",
            params={"start": L(day).isoformat(), "end": L(day + timedelta(days=1)).isoformat()},
        )
    )
    assert [g["minutes"] for g in rep["gaps"]] == [65]


def test_live_excursion_that_ends_as_transient_voids_its_ncr_and_hold(
    q3setup: None, api: Api, db
) -> None:  # type: ignore[no-untyped-def]
    """A manual reading makes a short open run an excursion at once (critical → draft NCR and a
    hold); when the next logger reading is back in range the run ended within the alarm delay:
    it becomes a transient and its automatic NCR and hold are voided (D-352)."""
    r = R(db)
    c = api.as_("imran.siddiq")
    pt = r.point("FRZ1-P1")
    day = date(2026, 10, 6)
    ok(import_readings(c, r.pid, "point", pt, readings_csv(series(L(day, 8), [-20.0] * 5))), 201)
    ok(
        c.post(
            f"{API}/quality/monitoring-points/{pt}/readings",
            json={
                "measured_at": L(day, 9, 15).isoformat(),
                "temperature_c": -10,
                "mte_id": r.mte("MTE-0042"),
            },
        ),
        201,
    )
    db.expire_all()
    x = db.scalar(select(QExcursion).where(QExcursion.transient.is_(False)))
    assert x is not None and x.severity.value == "critical" and x.exc_no
    assert x.ncr_id is not None and x.hold_id is not None
    ncr_id, hold_id = x.ncr_id, x.hold_id
    ok(
        import_readings(
            c, r.pid, "point", pt, readings_csv(series(L(day, 9, 30), [-20.0] * 2)), name="b.csv"
        ),
        201,
    )
    db.expire_all()
    x = db.get(QExcursion, x.id)
    assert x is not None and x.transient and x.duration_min == 15
    assert x.ncr_id is None and x.hold_id is None
    n = db.get(QNcr, ncr_id)
    assert n is not None and n.status == QNcrStatus.voided
    assert "transient" in (n.status_reason or "")
    h = db.get(QHold, hold_id)
    assert h is not None and h.status.value == "voided"
    listed = ok(c.get(f"{API}/projects/{r.pid}/quality/excursions"))
    assert listed["total"] == 0


def test_humidity_excursion_in_the_dry_zone(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    """Z-DRY1 (dry, RH ≤ 65 %): 120 min at 72 %RH is a humidity excursion; 7 %RH beyond the limit
    is major on the class's RH bands (5 / 15), so it opens an NCR and a hold."""
    r = R(db)
    z = db.scalar(select(QStorageZone).where(QStorageZone.zone_id == r.zone("Z-DRY1")))
    assert z is not None and z.humidity_max == D("65")
    c = api.as_("imran.siddiq")
    day = date(2026, 10, 5)
    rh = [50.0] * 5 + [72.0] * 8 + [50.0] * 2  # 06:00 … 09:30
    lines = ["time,temperature,humidity"]
    for i, v in enumerate(rh):
        t = (L(day, 6) + timedelta(minutes=15 * i)).astimezone(RIYADH)
        lines.append(f"{t:%Y-%m-%d %H:%M},22.0,{v}")
    content = ("\n".join(lines) + "\n").encode()
    res = ok(import_readings(c, r.pid, "point", r.point("DRY1-P1"), content), 201)
    assert len(res["excursions"]) == 1
    x = ok(c.get(f"{API}/quality/excursions/{res['excursions'][0]['id']}"))
    assert x["kind"] == "humidity" and x["severity"] == "major"
    assert x["duration_min"] == 120 and D(x["peak_value"]) == D("72")
    assert D(x["max_deviation"]) == D("7")
    assert x["ncr"] is not None and x["hold"] is not None
    n = ok(c.get(f"{API}/quality/ncrs/{x['ncr']['id']}"))
    assert n["category"] == "other"
    temp = db.scalar(
        select(QExcursion).where(QExcursion.zone_id == z.zone_id, QExcursion.kind == "storage")
    )
    assert temp is None


def test_ac31_hold_deadline_alert_on_list_read(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    """AC-Q3-31 without an hourly slot: reading the hold list at 09:00 the next day sends the
    "no lines" alert (once), as the home tiles do (D-355)."""
    from app.core.clock import set_now

    r = R(db)
    set_now(L(date(2026, 10, 5), 9))
    c = api.as_("imran.siddiq")
    h = ok(
        c.post(
            f"{API}/projects/{r.pid}/quality/holds",
            json={
                "site_id": str(db.scalar(select(QStorageZone.site_id))),
                "reason": "contamination",
                "zone_level": True,
                "zone_id": r.zone("Z-CHL1"),
            },
        ),
        201,
    )
    set_now(L(date(2026, 10, 6), 9))
    c = api.as_("imran.siddiq")
    ok(c.get(f"{API}/projects/{r.pid}/quality/holds"))
    ok(c.get(f"{API}/projects/{r.pid}/quality/holds"))
    db.expire_all()
    rows = [
        n
        for n in db.scalars(select(Notification).where(Notification.entity_id == h["id"]))
        if "no lines" in n.title_en
    ]
    assert rows and len({n.user_id for n in rows}) == len(rows)


def test_ac35_qx16_mock_recall_on_the_seed(q_seed: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    """QX16: received 4,800, on hand 1,150, shipped 3,620 → 99.4 % before the damage report;
    closing below the target needs a 50-character justification; 30 units destroyed on the spot
    → 100.0 %; trace 09:00 → 11:35 = 2 h 35 min within 4 h."""
    r = R(db)
    dmg = db.scalar(select(QDamageReport).where(QDamageReport.dmg_no == "DMG-RUH-CCH-2026-00207"))
    assert dmg is not None and dmg.qty == D("30")
    dmg.destroyed_on_spot = False  # as before the damage report was linked
    db.commit()
    site = str(dmg.site_id)
    c = api.as_("imran.siddiq")
    rc = ok(
        c.post(
            f"{API}/projects/{r.pid}/quality/recalls",
            json={
                "site_id": site,
                "recall_type": "mock",
                "items": [{"product_id": r.product("NDC-Y"), "batch": "NDC-Y-2609"}],
                "reason": "Mock recall of a chilled dairy batch (Q-RCL-05).",
                "initiated_at": L(date(2026, 9, 8), 9).isoformat(),
            },
        ),
        201,
    )
    t = ok(
        c.post(
            f"{API}/quality/recalls/{rc['id']}/trace",
            json={"completed_at": L(date(2026, 9, 8), 11, 35).isoformat()},
        )
    )
    assert D(t["trace"]["received"]) == D("4800") and D(t["trace"]["on_hand"]) == D("1150")
    assert D(t["trace"]["shipped"]) == D("3620") and D(t["trace"]["destroyed"]) == 0
    assert D(t["effectiveness_pct"]) == D("99.4")
    assert t["trace_minutes"] == 155 and t["trace_slow"] is False
    err(
        c.post(f"{API}/quality/recalls/{rc['id']}/close", json={"justification": "short"}),
        422,
        "RECALL_TARGET_NOT_MET",
    )
    ok(
        c.post(
            f"{API}/projects/{r.pid}/quality/damage-reports",
            json={
                "site_id": site,
                "stage": "delivery",
                "product_id": r.product("NDC-Y"),
                "batch": "NDC-Y-2609",
                "qty": 30,
                "cause": "temperature",
                "destroyed_on_spot": True,
                "reported_at": L(date(2026, 9, 8), 10).isoformat(),
                "owner_notified_at": L(date(2026, 9, 8), 10, 5).isoformat(),
            },
        ),
        201,
    )
    now = ok(c.get(f"{API}/quality/recalls/{rc['id']}"))
    assert D(now["effectiveness_pct"]) == D("100.0")
    closed = ok(api.as_("reem.mutairi").post(f"{API}/quality/recalls/{rc['id']}/close", json={}))
    assert closed["status"] == "closed"


def test_seed_hold_0112_released_and_destroyed(q_seed: None, db) -> None:  # type: ignore[no-untyped-def]
    """D-358: NCR-0034's disposition approved on 2026-09-24 through the Q0 services; 12 lines
    released, 2 rejected and destroyed with a certificate (Appendix A.6)."""
    h = db.scalar(select(QHold).where(QHold.hold_no == "HLD-RUH-CCH-2026-0112"))
    assert h is not None
    from app.services.quality.q3 import holds

    lines = holds.lines_of(db, h)
    assert sorted(ln.line_status.value for ln in lines).count("released") == 12
    rej = [ln for ln in lines if ln.line_status.value == "rejected"]
    assert len(rej) == 2 and all(ln.final_outcome and ln.evidence_attachment_id for ln in rej)
    assert h.status.value == "closed"
    n = db.scalar(select(QNcr).where(QNcr.ncr_no == "NCR-RUH-CCH-2026-0034"))
    assert n is not None and n.status == QNcrStatus.disposition_approved
    assert n.disposition_approved_at is not None
    assert n.disposition_approved_at.astimezone(RIYADH).date() == date(2026, 9, 24)
    _ = UTC_MIN
