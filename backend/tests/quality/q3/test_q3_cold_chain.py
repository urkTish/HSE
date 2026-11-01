"""Imports, readings, excursions and mapping through the API (spec 8-quality §D.1.4, §D.3–§D.5;
AC-Q3-01…04, 11, 13, 16…20, 22…25). Clock: 2026-10-06 10:00 Riyadh (`clock` via `qsetup`)."""

import hashlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.clock import set_now
from app.models import Attachment, Notification, User
from app.models.quality import QMteItem, QNcr
from app.models.quality.q3 import QExcursion, QReading, QStorageZone
from tests.conftest import Api
from tests.quality.q3.h3 import (
    API,
    RIYADH,
    L,
    R,
    attach,
    err,
    import_kind,
    import_readings,
    ok,
    readings_csv,
    series,
)

D = Decimal


def _users(db, *emails: str) -> set:  # type: ignore[no-untyped-def]
    return {db.scalar(select(User.id).where(User.email == f"{e}@example.com")) for e in emails}


def test_ac01_ac02_ac03_imports(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    imran = api.as_("imran.siddiq")
    start = L(date(2026, 9, 1))
    rows = series(start, [3.0] * 2880)
    content = readings_csv(rows)
    lines = content.decode().splitlines()
    lines[10] = "not-a-date,3.0"
    lines[20] = f"{lines[20].split(',')[0]},95.0"  # outside −80…+80
    lines[30] = lines[29]  # repeated time
    content = ("\n".join(lines) + "\n").encode()
    res = ok(import_readings(imran, r.pid, "point", r.point("CHL1-P2"), content), 201)
    assert res["rows_read"] == 2880 and res["rows_accepted"] == 2877 and res["rows_rejected"] == 3
    assert [e["row"] for e in res["errors"]] == [11, 21, 31]
    a = db.get(Attachment, res["attachment_id"])
    assert a is not None and a.sha256 == hashlib.sha256(content).hexdigest() == res["sha256"]
    err(
        import_readings(imran, r.pid, "point", r.point("CHL1-P2"), content),
        409,
        "IMPORT_DUPLICATE_FILE",
    )
    # all-or-nothing snapshot
    snap = (
        b"owner,sku,batch,location,zone,qty\nNDC,NDC-Y,B1,L1,Z-CHL1,10\nNDC,NDC-Y,B2,L2,Z-CHL1,-5\n"
    )
    d = err(
        import_kind(
            imran, r.pid, "stock_snapshot", str(db.scalar(select(QStorageZone.site_id))), snap
        ),
        422,
        "IMPORT_ROWS_INVALID",
    )
    assert d["meta"]["errors"][0]["row"] == 3
    # °F and UTC
    prof = '{"unit": "F", "timezone": "UTC"}'
    res = ok(
        import_readings(
            imran,
            r.pid,
            "point",
            r.point("CHL1-P3"),
            b"time,temperature\n2026-09-02 05:15,39.2\n",
            prof,
        ),
        201,
    )
    rd = db.scalar(select(QReading).where(QReading.batch_id == res["id"]))
    assert rd.temperature_c == D("4.00")
    assert rd.measured_at == datetime(2026, 9, 2, 5, 15, tzinfo=UTC)
    assert L(date(2026, 9, 2), 8, 15) == rd.measured_at  # shown 08:15 Riyadh


def test_ac04_void_within_24h_and_no_edit_route(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    reem = api.as_("reem.mutairi")
    content = readings_csv(series(L(date(2026, 10, 5), 6), [3.0, 4.6, 4.8, 4.9, 4.7, 3.0, 3.0]))
    res = ok(import_readings(reem, r.pid, "point", r.point("CHL1-P1"), content), 201)
    assert len(res["excursions"]) == 1
    xid = res["excursions"][0]["id"]
    err(
        reem.post(f"{API}/quality/imports/{res['id']}/void", json={"reason": "short"}),
        422,
        "VALIDATION_ERROR",
    )
    v = ok(
        reem.post(
            f"{API}/quality/imports/{res['id']}/void",
            json={"reason": "Mapped to the wrong point by the logger software."},
        )
    )
    assert v["status"] == "voided"
    db.expire_all()
    assert db.get(QExcursion, xid).status.value == "voided"
    res2 = ok(import_readings(reem, r.pid, "point", r.point("CHL1-P2"), content), 201)
    set_now(datetime(2026, 10, 7, 9, 0, tzinfo=UTC))
    reem = api.as_("reem.mutairi")
    err(
        reem.post(
            f"{API}/quality/imports/{res2['id']}/void",
            json={"reason": "Mapped to the wrong point by the logger software."},
        ),
        409,
        "INVALID_TRANSITION",
    )
    rid = db.scalar(select(QReading.id).limit(1))
    assert reem.patch(f"{API}/quality/readings/{rid}", json={"temperature_c": 1}).status_code in (
        404,
        405,
    )


def test_ac11_qx12_minor_no_ncr(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    c = api.as_("imran.siddiq")
    vals = [3.0, 3.1, 3.2, 3.3, 3.6, 4.4, 5.1, 5.6, 4.8, 3.9, 3.5]
    res = ok(
        import_readings(
            c,
            r.pid,
            "point",
            r.point("CHL1-P2"),
            readings_csv(series(L(date(2026, 9, 17), 7), vals)),
        ),
        201,
    )
    x = ok(c.get(f"{API}/quality/excursions/{res['excursions'][0]['id']}"))
    assert x["started_at"].startswith("2026-09-17T05:15") and x["duration_min"] == 60
    assert D(x["max_deviation"]) == D("1.6") and D(x["degree_minutes"]) == D("58.5")
    assert x["severity"] == "minor" and x["ncr"] is None and x["hold"] is None


def _qx13(c, r: R, db) -> dict:  # type: ignore[no-untyped-def]
    site = str(db.scalar(select(QStorageZone.site_id)))
    rows = ["owner,sku,batch,expiry,location,zone,qty"]
    for i in range(14):
        sku = "GFF-2001" if i % 2 else "GFF-2105"
        rows.append(f"GFF,{sku},GFF-B{i:02d},2027-01-{i + 1:02d},FRZ1-{i:02d},Z-FRZ1,{100 + i}")
    rows.append("NDC,NDC-Y,NDC-Y-1,2026-10-30,CHL1-01,Z-CHL1,50")
    ok(
        import_kind(
            c,
            r.pid,
            "stock_snapshot",
            site,
            ("\n".join(rows) + "\n").encode(),
            L(date(2026, 9, 21), 23),
        ),
        201,
    )
    vals = [
        -22.0,
        -22.0,
        -22.0,
        -22.0,
        -17.6,
        -17.0,
        -16.4,
        -15.8,
        -15.1,
        -14.6,
        -14.2,
        -13.8,
        -14.0,
        -14.5,
        -15.2,
        -16.0,
        -16.9,
        -17.6,
        -19.2,
        -21.0,
    ]
    res = ok(
        import_readings(
            c,
            r.pid,
            "point",
            r.point("FRZ1-P1"),
            readings_csv(series(L(date(2026, 9, 22), 1), vals)),
        ),
        201,
    )
    return ok(c.get(f"{API}/quality/excursions/{res['excursions'][0]['id']}"))


def test_ac13_qx13_major_ncr_hold_alerts(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    x = _qx13(api.as_("imran.siddiq"), r, db)
    assert (
        x["severity"] == "major" and x["duration_min"] == 210 and D(x["peak_value"]) == D("-13.8")
    )
    n = db.get(QNcr, x["ncr"]["id"])
    assert (
        n.source_type.value == "excursion"
        and n.classification.value == "major"
        and n.category.value == "temperature"
    )
    assert n.status.value == "open"
    assert x["hold"]["zone_level"] is False
    h = ok(api.as_("reem.mutairi").get(f"{API}/quality/holds/{x['hold']['id']}"))
    assert len(h["lines"]) == 14 and h["reason"] == "excursion"
    got = set(db.scalars(select(Notification.user_id).where(Notification.entity_id == x["id"])))
    assert _users(db, "reem.mutairi", "imran.siddiq", "saad.anazi") <= got
    assert _users(db, "lama.qarni").isdisjoint(got)


def test_ac16_pharma_minor_needs_assessment(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    c = api.as_("imran.siddiq")
    res = ok(
        import_readings(
            c,
            r.pid,
            "point",
            r.point("PHR1-P1"),
            readings_csv(series(L(date(2026, 9, 5), 6), [5.0, 8.4, 8.5, 5.0, 5.0])),
        ),
        201,
    )
    x = ok(
        c.post(
            f"{API}/quality/excursions/{res['excursions'][0]['id']}/cause",
            json={"cause": "door_open"},
        )
    )
    assert (
        x["severity"] == "minor"
        and x["impact_required"] is True
        and "close_no_impact" not in x["allowed_actions"]
    )
    err(
        c.post(
            f"{API}/quality/excursions/{x['id']}/close",
            json={"note": "Door left open during the putaway."},
        ),
        422,
        "IMPACT_LINES_INCOMPLETE",
    )
    res = ok(
        import_readings(
            c,
            r.pid,
            "point",
            r.point("AMB1-P1"),
            readings_csv(series(L(date(2026, 9, 5), 6), [20.0, 25.5, 25.6, 25.4, 20.0, 20.0])),
        ),
        201,
    )
    xid = res["excursions"][0]["id"]
    ok(c.post(f"{API}/quality/excursions/{xid}/cause", json={"cause": "door_open"}))
    x = ok(
        c.post(
            f"{API}/quality/excursions/{xid}/close",
            json={"note": "Door left open during the putaway; product unaffected."},
        )
    )
    assert x["status"] == "closed"


def test_ac17_ac18_impact_assessment(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    imran, saad = api.as_("imran.siddiq"), api.as_("saad.anazi")
    x = _qx13(imran, r, db)
    ok(imran.post(f"{API}/quality/excursions/{x['id']}/cause", json={"cause": "defrost"}))
    x = ok(saad.get(f"{API}/quality/excursions/{x['id']}"))
    assert "assess" in x["allowed_actions"]
    lines = [ln["hold_line"] for ln in x["impact_lines"]]
    hold_id = x["hold"]["id"]
    owner_file = attach(saad, "q_hold", hold_id, "gff-decision.pdf")
    full = [
        {
            "hold_line_id": ln["id"],
            "decision": "release",
            "justification": "Within the owner's frozen-poultry time and temperature budget of 6 "
            "h at −12 °C.",
            "owner_decision_attachment_id": owner_file,
        }
        for ln in lines
    ]
    err(
        saad.post(f"{API}/quality/excursions/{x['id']}/assess", json={"lines": full[:13]}),
        422,
        "IMPACT_LINES_INCOMPLETE",
    )
    bad = [dict(full[0], justification="Looks fine to me ok."), *full[1:]]
    bad[0].pop("owner_decision_attachment_id")
    bad[0]["owner_decision_attachment_id"] = owner_file
    err(
        saad.post(f"{API}/quality/excursions/{x['id']}/assess", json={"lines": bad}),
        422,
        "IMPACT_EVIDENCE_REQUIRED",
    )
    no_owner = [dict(full[0]), *full[1:]]
    no_owner[0].pop("owner_decision_attachment_id")
    err(
        saad.post(f"{API}/quality/excursions/{x['id']}/assess", json={"lines": no_owner}),
        422,
        "OWNER_DECISION_REQUIRED",
    )
    done = ok(saad.post(f"{API}/quality/excursions/{x['id']}/assess", json={"lines": full}))
    assert done["status"] == "assessed" and done["signoffs"][0]["step"] == "impact"
    h = ok(saad.get(f"{API}/quality/holds/{hold_id}"))
    assert {ln["proposed_decision"] for ln in h["lines"]} == {"release"}
    # AC-Q3-30: the NCR disposition is not approved yet → the release is blocked
    d = err(
        saad.post(f"{API}/quality/holds/{hold_id}/decide", json={"action": "release"}),
        422,
        "HOLD_RELEASE_BLOCKED",
    )
    assert d["meta"]["blockers"][0]["code"] == "NCR_DISPOSITION_NOT_APPROVED"
    n = db.get(QNcr, x["ncr"]["id"])
    n.status = "disposition_approved"  # type: ignore[assignment]
    db.commit()
    h = ok(saad.post(f"{API}/quality/holds/{hold_id}/decide", json={"action": "release"}))
    assert {ln["line_status"] for ln in h["lines"]} == {"released"} and h["signoffs"][0][
        "step"
    ] == "release"


def test_ac30_release_blocked_before_assessment(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    x = _qx13(api.as_("imran.siddiq"), r, db)
    d = err(
        api.as_("saad.anazi").post(
            f"{API}/quality/holds/{x['hold']['id']}/decide", json={"action": "release"}
        ),
        422,
        "HOLD_RELEASE_BLOCKED",
    )
    assert {b["code"] for b in d["meta"]["blockers"]} == {
        "NCR_DISPOSITION_NOT_APPROVED",
        "EXCURSION_NOT_ASSESSED",
    }
    # Warehouse QC places holds only
    assert (
        api.as_("imran.siddiq")
        .post(f"{API}/quality/holds/{x['hold']['id']}/decide", json={"action": "release"})
        .status_code
        == 403
    )


def test_ac19_dismissal_probe_fault(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    imran, saad = api.as_("imran.siddiq"), api.as_("saad.anazi")
    pt = r.point("CHL1-P4")
    probe = r.mte("MTE-0051")
    for k, v in enumerate((6.0, 6.2, 6.1)):
        body = {
            "measured_at": (L(date(2026, 10, 6), 8) + timedelta(minutes=15 * k)).isoformat(),
            "temperature_c": v,
            "mte_id": probe,
        }
        res = ok(imran.post(f"{API}/quality/monitoring-points/{pt}/readings", json=body), 201)
    xid = res["excursions"][0]["id"]
    x = ok(
        saad.post(
            f"{API}/quality/excursions/{xid}/dismiss",
            json={
                "evidence_kind": "calibration_check",
                "mte_id": probe,
                "error_c": "3.0",
                "note": "Check against the reference thermometer: +3.0 °C high.",
            },
        )
    )
    assert x["status"] == "dismissed" and x["dismissal"]["readings_flagged"] >= 3
    db.expire_all()
    assert all(
        rd.probe_fault for rd in db.scalars(select(QReading).where(QReading.mte_id == probe))
    )
    assert db.get(QMteItem, probe).cal_status.value == "out_of_service"
    from app.services.quality.q3 import metrics

    m = metrics.month(db, r.project, 2026, 10)
    assert m["k161"]["excursions"] == 0 and m["k161"]["dismissed"] == 1


def test_ac22_manual_reading_age_and_skew(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    c = api.as_("imran.siddiq")
    pt = r.point("CHL1-P1")
    now = L(date(2026, 10, 6), 10)
    probe = r.mte("MTE-0042")
    err(
        c.post(
            f"{API}/quality/monitoring-points/{pt}/readings",
            json={
                "measured_at": (now - timedelta(hours=80)).isoformat(),
                "temperature_c": 3,
                "mte_id": probe,
            },
        ),
        422,
        "READING_TOO_OLD",
    )
    err(
        c.post(
            f"{API}/quality/monitoring-points/{pt}/readings",
            json={
                "measured_at": (now + timedelta(minutes=10)).isoformat(),
                "temperature_c": 3,
                "mte_id": probe,
            },
        ),
        422,
        "CLOCK_SKEW",
    )
    err(
        c.post(
            f"{API}/quality/monitoring-points/{pt}/readings",
            json={"measured_at": now.isoformat(), "temperature_c": 3},
        ),
        422,
        "MTE_REQUIRED",
    )
    res = ok(
        c.post(
            f"{API}/quality/monitoring-points/{pt}/readings",
            json={"measured_at": now.isoformat(), "temperature_c": 3, "mte_id": probe},
        ),
        201,
    )
    assert res["reading"]["source"] == "manual"


def _study(db, r: R, end: datetime, start: datetime, loggers: list[str]):  # type: ignore[no-untyped-def]
    return {
        "zone_id": r.zone("Z-FRZ1"),
        "purpose": "periodic",
        "season": "summer",
        "load_state": "loaded",
        "planned_start": start.isoformat(),
        "planned_end": end.isoformat(),
        "interval_minutes": 5,
        "loggers": [
            {"mte_id": r.mte(m), "position_code": f"L{i + 1:02d}"} for i, m in enumerate(loggers)
        ],
    }


def test_ac23_mapping_design_checks(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    c = api.as_("imran.siddiq")
    loggers = [f"MTE-{n:04d}" for n in range(101, 110)]
    m = db.scalar(select(QMteItem).where(QMteItem.mte_no == "MTE-0101"))
    m.cal_due_on = date(2026, 9, 25)
    db.commit()
    body = _study(db, r, L(date(2026, 9, 26), 8), L(date(2026, 9, 22), 8), loggers)
    d = err(
        c.post(f"{API}/projects/{r.pid}/quality/mapping-studies", json=body),
        422,
        "MAPPING_LOGGER_NOT_CALIBRATED",
    )
    assert d["meta"]["loggers"] == ["MTE-0101"]
    body = _study(db, r, L(date(2026, 9, 14), 8), L(date(2026, 9, 12), 8), loggers)
    d = err(
        c.post(f"{API}/projects/{r.pid}/quality/mapping-studies", json=body),
        422,
        "MAPPING_DESIGN_INSUFFICIENT",
    )
    assert "duration 48 h" in d["message"]


def test_ac24_ac25_mapping_pass_approval_and_validity(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    imran, reem = api.as_("imran.siddiq"), api.as_("reem.mutairi")
    start = L(date(2026, 7, 14), 8)
    loggers = [f"MTE-{n:04d}" for n in range(101, 110)]
    body = _study(db, r, start + timedelta(hours=72), start, loggers)
    body["test_windows"] = [
        {
            "kind": "door_open",
            "from": (start + timedelta(hours=10)).isoformat(),
            "to": (start + timedelta(hours=11)).isoformat(),
        }
    ]
    s = ok(imran.post(f"{API}/projects/{r.pid}/quality/mapping-studies", json=body), 201)
    lines = ["time,temperature,channel"]
    for i in range(9):
        for k in range(72 * 12 + 1):
            t = start + timedelta(minutes=5 * k)
            v = -21.0 if not (timedelta(hours=10) <= t - start < timedelta(hours=11)) else -15.0
            lines.append(
                f"{t.astimezone(RIYADH).strftime('%Y-%m-%d %H:%M')},{v - i * 0.1:.1f},L{i + 1:02d}"
            )
    res = ok(
        import_readings(imran, r.pid, "mapping_study", s["id"], ("\n".join(lines) + "\n").encode()),
        201,
    )
    assert res["rows_accepted"] == 9 * 865
    ev = ok(imran.post(f"{API}/quality/mapping-studies/{s['id']}/evaluate"))
    assert (
        ev["passed"] is True
        and ev["results"]["hot_spot"] == "L01"
        and ev["results"]["cold_spot"] == "L09"
    )
    err(imran.post(f"{API}/quality/mapping-studies/{s['id']}/approve", json={}), 403, "FORBIDDEN")
    ap = ok(
        reem.post(
            f"{API}/quality/mapping-studies/{s['id']}/approve", json={"approved_on": "2026-07-28"}
        )
    )
    assert ap["valid_until"] == "2028-07-27" and ap["status"] == "approved"
    z = ok(reem.get(f"{API}/quality/storage-zones/{r.zone('Z-FRZ1')}"))
    assert z["mapping_state"] == "mapped" and z["mapped_until"] == "2028-07-27"
    # AC-Q3-25: Z-PHR1 valid until 2026-10-20 → 30-day alert on 2026-09-20; a range change re-maps
    from app.services.quality.q3 import mapping

    zp = db.get(QStorageZone, r.zone("Z-PHR1"))
    zp.mapped_until = date(2026, 10, 20)
    db.commit()
    assert mapping.validity_alerts(db, L(date(2026, 9, 20), 7, 12)) >= 1
    db.commit()
    keys = [
        n.title_en
        for n in db.scalars(select(Notification).where(Notification.title_en.like("Z-PHR1:%")))
    ]
    assert any("(30 days)" in k for k in keys)
    z = ok(reem.patch(f"{API}/quality/storage-zones/{r.zone('Z-PHR1')}", json={"temp_max": "7.5"}))
    assert z["mapping_state"] == "remap_required"
