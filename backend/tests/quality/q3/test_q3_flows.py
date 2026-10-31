"""Receiving, holds, stock, returns, recalls, transport and profile gating through the API (spec
8-quality §D.2, §D.6–§D.9; AC-Q3-05…10, 26…29, 31…34, 36…40, 42). Clock 2026-10-06 10:00."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.models import Notification, Site, User
from app.models.quality.q3 import QHold, QShipment, QStorageZone
from tests.conftest import Api, Ids
from tests.quality.q3.h3 import (
    API,
    L,
    R,
    answers,
    attach,
    err,
    import_kind,
    import_readings,
    ok,
    readings_csv,
    series,
)

D = Decimal


def _site(db) -> str:  # type: ignore[no-untyped-def]
    return str(db.scalar(select(QStorageZone.site_id)))


def _receipt(c, r: R, db, customer: str, lines: list[dict[str, Any]], **kw: Any) -> dict:  # type: ignore[no-untyped-def]
    arrived = kw.pop("arrived", L(date(2026, 9, 14), 6, 10))
    body = {
        "site_id": _site(db),
        "dock_zone_id": r.zone("Z-DOCK"),
        "customer_id": r.customer(customer),
        "arrived_at": arrived.isoformat(),
        "unload_start": (arrived + timedelta(minutes=15)).isoformat(),
        "unload_end": (arrived + timedelta(minutes=38)).isoformat(),
        "lines": lines,
        **kw,
    }
    rec = ok(c.post(f"{API}/projects/{r.pid}/quality/receipts", json=body), 201)
    ok(
        c.post(
            f"{API}/quality/receipts/{rec['id']}/vehicle-check", json={"answers": answers("QRCV")}
        )
    )
    return ok(c.post(f"{API}/quality/receipts/{rec['id']}/inspect"))


def _chicken(r: R) -> dict[str, Any]:
    return {
        "product_id": r.product("GFF-2001"),
        "batch": "GFF-C-2614",
        "expiry_date": "2026-12-20",
        "qty_received": 480,
        "product_temp_c": "-16.5",
        "mte_id": r.mte("MTE-0042"),
    }


def _yoghurt(r: R) -> dict[str, Any]:
    return {
        "product_id": r.product("NDC-Y"),
        "batch": "NDC-Y-2618",
        "expiry_date": "2026-10-15",
        "qty_received": 960,
        "product_temp_c": "11.0",
        "mte_id": r.mte("MTE-0042"),
    }


def test_ac05_proposals_qx14(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    c = api.as_("imran.siddiq")
    rec = _receipt(c, r, db, "GFF", [_chicken(r)])
    ln = rec["lines"][0]
    assert rec["rcv_no"].startswith("RCV-RUH-CCH-2026-") and D(ln["remaining_shelf_life_pct"]) == D(
        "53.9"
    )
    assert ln["proposed_decision"] == "accept_with_deviation"
    assert {x["code"] for x in ln["proposal_reasons"]} == {
        "arrival_temperature",
        "remaining_shelf_life",
    }
    rec = _receipt(c, r, db, "NDC", [_yoghurt(r)], arrived=L(date(2026, 9, 21), 7, 5))
    assert rec["lines"][0]["proposed_decision"] == "reject"


def test_ac06_ac07_ac08_decisions(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    imran, reem = api.as_("imran.siddiq"), api.as_("reem.mutairi")
    rec = _receipt(imran, r, db, "NDC", [_yoghurt(r)], arrived=L(date(2026, 9, 21), 7, 5))
    lid = rec["lines"][0]["id"]
    err(
        imran.post(f"{API}/quality/receipt-lines/{lid}/decide", json={"decision": "accept"}),
        422,
        "DECISION_BETTER_THAN_CRITERIA",
    )
    why = "Supplier re-measured the core at 4.1 °C with a calibrated probe."
    assert (
        imran.post(
            f"{API}/quality/receipt-lines/{lid}/decide", json={"decision": "accept", "reason": why}
        ).status_code
        == 403
    )
    pend = ok(
        imran.post(
            f"{API}/quality/receipt-lines/{lid}/decide",
            json={"decision": "accept", "reason": why, "request": True},
        )
    )
    assert pend["lines"][0]["requested_decision"] == "accept"
    aw = ok(reem.get(f"{API}/projects/{r.pid}/quality/awaiting"))
    assert any(i["record_id"] == rec["id"] and i["step"] == "deviation" for i in aw["items"])
    done = ok(reem.post(f"{API}/quality/receipt-lines/{lid}/decide", json={}))
    assert done["lines"][0]["decision"] == "accept" and done["status"] == "decided"
    assert done["signoffs"][0]["step"] == "deviation"
    # AC-Q3-07: Gulf Frozen Foods approves deviations on its goods
    rec = _receipt(imran, r, db, "GFF", [_chicken(r)])
    lid = rec["lines"][0]["id"]
    err(
        reem.post(
            f"{API}/quality/receipt-lines/{lid}/decide",
            json={
                "decision": "accept_with_deviation",
                "reason": "Within the GFF deviation agreement.",
            },
        ),
        422,
        "OWNER_DECISION_REQUIRED",
    )
    f = attach(imran, "q_receipt", rec["id"], "gff-approval.pdf")
    ok(
        reem.post(
            f"{API}/quality/receipt-lines/{lid}/decide",
            json={
                "decision": "accept_with_deviation",
                "reason": "Within the GFF deviation agreement.",
                "owner_approval_attachment_id": f,
            },
        )
    )
    # AC-Q3-08: quarantine → hold; reject needs an NCR or a claim
    damaged = {
        **_chicken(r),
        "batch": "GFF-C-2700",
        "product_temp_c": "-20.0",
        "expiry_date": "2027-03-01",
        "condition": "damaged",
    }
    rec = _receipt(
        imran,
        r,
        db,
        "GFF",
        [
            damaged,
            {
                **_chicken(r),
                "batch": "GFF-C-2701",
                "product_temp_c": "-14.0",
                "expiry_date": "2027-03-01",
            },
        ],
    )
    q = rec["lines"][0]
    assert q["proposed_decision"] == "quarantine"
    done = ok(
        imran.post(f"{API}/quality/receipt-lines/{q['id']}/decide", json={"decision": "quarantine"})
    )
    hid = done["lines"][0]["hold_id"]
    h = ok(imran.get(f"{API}/quality/holds/{hid}"))
    assert h["reason"] == "receiving" and h["lines"][0]["batch"] == "GFF-C-2700"
    rj = rec["lines"][1]["id"]
    err(
        reem.post(f"{API}/quality/receipt-lines/{rj}/decide", json={"decision": "reject"}),
        422,
        "REJECT_NEEDS_NCR_OR_CLAIM",
    )
    done = ok(
        reem.post(
            f"{API}/quality/receipt-lines/{rj}/decide",
            json={"decision": "reject", "raise_ncr": True, "reason": "Above −15 °C on arrival."},
        )
    )
    n = ok(reem.get(f"{API}/quality/ncrs/{done['lines'][1]['ncr_id']}"))
    assert n["source_type"] == "receipt" and n["classification"] == "major"


def test_ac09_ac10_mte_and_dwell(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    c = api.as_("imran.siddiq")
    arrived = L(date(2026, 9, 14), 6, 10)
    body = {
        "site_id": _site(db),
        "dock_zone_id": r.zone("Z-DOCK"),
        "customer_id": r.customer("NDC"),
        "arrived_at": arrived.isoformat(),
        "lines": [
            {
                "product_id": r.product("NDC-1001"),
                "batch": "L1",
                "expiry_date": "2026-09-27",
                "qty_received": 10,
                "product_temp_c": "3.0",
            }
        ],
    }
    err(c.post(f"{API}/projects/{r.pid}/quality/receipts", json=body), 422, "MTE_REQUIRED")
    body["lines"][0]["mte_id"] = r.mte("MTE-0042")
    rec = ok(c.post(f"{API}/projects/{r.pid}/quality/receipts", json=body), 201)
    assert any(
        w["code"] == "MTE_NOT_CALIBRATED" for w in rec["warnings"]
    )  # Q2 not installed: unknown warns
    from app.models.quality import QMteUsage

    assert (
        db.scalar(select(QMteUsage).where(QMteUsage.record_id == rec["id"])).verdict.value
        == "warned"
    )
    upd = ok(
        c.patch(
            f"{API}/quality/receipts/{rec['id']}",
            json={
                "unload_start": L(date(2026, 9, 14), 6, 25).isoformat(),
                "unload_end": L(date(2026, 9, 14), 7, 5).isoformat(),
            },
        )
    )
    assert upd["dwell_minutes"] == 40 and any(
        w["code"] == "DOCK_DWELL_LONG" for w in upd["warnings"]
    )


def test_ac42_construction_project_refuses(q3setup: None, api: Api, ids: Ids) -> None:
    c = api.as_("faisal.harbi")
    body = {
        "site_id": ids.site("S-LAND"),
        "dock_zone_id": ids.zone("Z-APR-21"),
        "customer_id": ids.user("faisal.harbi"),
    }
    err(
        c.post(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/receipts", json=body),
        409,
        "PROFILE_INACTIVE",
    )


def test_ac31_ac32_hold_deadlines_and_close(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    from app.core.clock import set_now
    from app.services.quality.q3 import holds

    r = R(db)
    set_now(L(date(2026, 10, 5), 9))
    c = api.as_("imran.siddiq")
    h = ok(
        c.post(
            f"{API}/projects/{r.pid}/quality/holds",
            json={
                "site_id": _site(db),
                "reason": "contamination",
                "zone_level": True,
                "zone_id": r.zone("Z-CHL1"),
            },
        ),
        201,
    )
    assert holds.deadlines(db, L(date(2026, 10, 5), 12, 59)) == 0
    db.commit()
    assert holds.deadlines(db, L(date(2026, 10, 5), 13)) >= 1  # segregation photo missing at 4 h
    db.commit()
    assert holds.deadlines(db, L(date(2026, 10, 6), 8, 59)) == 0
    assert holds.deadlines(db, L(date(2026, 10, 6), 9)) >= 1  # no lines after 24 h
    db.commit()
    titles = {
        n.title_en
        for n in db.scalars(select(Notification).where(Notification.entity_id == h["id"]))
    }
    assert any("no lines" in t for t in titles) and any("segregation" in t for t in titles)
    set_now(L(date(2026, 10, 6), 10))
    c = api.as_("imran.siddiq")
    ok(
        c.post(
            f"{API}/quality/holds/{h['id']}/lines",
            json={"lines": [{"product_id": r.product("NDC-Y"), "batch": "Y1", "qty": 50}]},
        )
    )
    saad = api.as_("saad.anazi")
    hh = ok(
        saad.post(
            f"{API}/quality/holds/{h['id']}/decide",
            json={"action": "reject", "reason": "Product contaminated by a leaking pallet above."},
        )
    )
    assert hh["status"] == "rejected"
    err(c.post(f"{API}/quality/holds/{h['id']}/close"), 422, "VALIDATION_ERROR")
    ln = hh["lines"][0]["id"]
    err(
        c.post(
            f"{API}/quality/hold-lines/{ln}/outcome",
            json={
                "outcome": "destroyed",
                "evidence_attachment_id": "00000000-0000-0000-0000-000000000000",
            },
        ),
        422,
        "VALIDATION_ERROR",
    )
    ev = attach(c, "q_hold", h["id"], "destruction.pdf")
    done = ok(
        c.post(
            f"{API}/quality/hold-lines/{ln}/outcome",
            json={"outcome": "destroyed", "evidence_attachment_id": ev},
        )
    )
    assert done["status"] == "closed"
    csv = c.get(f"{API}/projects/{r.pid}/quality/holds/export.csv")
    assert csv.status_code == 200 and "Y1" in csv.text and h["hold_no"] in csv.text


def test_ac26_hygiene_overdue_and_ac27_pest(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    from app.services.quality.q3 import hygiene

    r = R(db)
    assert hygiene.overdue_alerts(db, L(date(2026, 10, 4), 7, 12)) >= 1
    db.commit()
    imran = db.scalar(select(User.id).where(User.email == "imran.siddiq@example.com"))
    titles = [
        n.title_en for n in db.scalars(select(Notification).where(Notification.user_id == imran))
    ]
    assert any("Z-CHL1" in t and "2026-09-27" in t for t in titles)
    c = api.as_("reem.mutairi")
    sch = ok(c.get(f"{API}/projects/{r.pid}/quality/check-schedules"))
    chl = next(s for s in sch if s["zone"] and s["zone"]["code"] == "Z-CHL1")
    assert any(p["to"] == "2026-10-03" for p in chl["overdue"])
    run = ok(
        c.post(
            f"{API}/quality/check-schedules/{chl['id']}/checks",
            json={"answers": answers("QHYG", fail=(1,))},
        ),
        201,
    )
    assert run["passed"] is False and run["proposals"][0]["source_type"] == "hygiene_pest"
    st = {s["code"]: s for s in ok(c.get(f"{API}/projects/{r.pid}/quality/pest-stations"))}
    site = _site(db)
    allst = [{"station_id": s["id"], "activity": "none"} for s in st.values()]
    act = [dict(x, activity="low") if x["station_id"] == st["RB-14"]["id"] else x for x in allst]
    v1 = ok(
        c.post(
            f"{API}/projects/{r.pid}/quality/pest-visits",
            json={
                "site_id": site,
                "visited_at": L(date(2026, 8, 30), 10).isoformat(),
                "station_results": act,
            },
        ),
        201,
    )
    assert v1["proposals"] == []
    v2 = ok(
        c.post(
            f"{API}/projects/{r.pid}/quality/pest-visits",
            json={
                "site_id": site,
                "visited_at": L(date(2026, 9, 27), 10).isoformat(),
                "station_results": act[:-1],
            },
        ),
        201,
    )
    assert (
        v2["proposals"][0]["station"] == "RB-14"
        and "activity on 2 consecutive visits" in v2["proposals"][0]["why"]
    )
    assert any(w["code"] == "STATION_NOT_SERVICED" for w in v2["warnings"])
    chl_station = next(s for s in st.values() if s["zone"]["code"] == "Z-CHL1")
    act3 = [dict(x, activity="low") if x["station_id"] == chl_station["id"] else x for x in allst]
    v3 = ok(
        c.post(
            f"{API}/projects/{r.pid}/quality/pest-visits",
            json={
                "site_id": site,
                "visited_at": L(date(2026, 10, 1), 10).isoformat(),
                "station_results": act3,
            },
        ),
        201,
    )
    assert v3["proposals"] and "activity in a chilled zone" in v3["proposals"][0]["why"]


def test_ac28_ac29_near_expiry_and_fefo(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    from app.services.quality.q3 import stock

    r = R(db)
    c = api.as_("imran.siddiq")
    site = _site(db)
    snap = (
        "owner,sku,batch,expiry,location,zone,qty\n"
        "NDC,NDC-5001,B1,2026-11-05,A1,Z-AMB1,10\n"
        "NDC,NDC-5001,B2,2026-11-30,A2,Z-AMB1,10\n"
        "NDC,NDC-1001,OLD,2026-10-01,C1,Z-CHL1,5\n"
    )
    ok(import_kind(c, r.pid, "stock_snapshot", site, snap.encode(), L(date(2026, 10, 5), 23)), 201)
    ne = ok(c.get(f"{API}/projects/{r.pid}/quality/near-expiry"))
    kinds = {i["batch"]: i["kind"] for i in ne["items"]}
    assert kinds["OLD"] == "expired" and kinds["B1"] == "near_expiry" and "B2" not in kinds
    assert stock.expired_alerts(db, L(date(2026, 10, 6), 7, 12)) >= 1
    db.commit()
    body = {
        "site_id": site,
        "product_id": r.product("NDC-5001"),
        "picked_batch": "B2",
        "picked_expiry": "2026-11-30",
    }
    f = ok(c.post(f"{API}/projects/{r.pid}/quality/fefo-checks", json=body), 201)
    assert f["result"] == "non_compliant" and f["eligible_batch"] == "B1"
    old = next(i for i in ne["items"] if i["batch"] == "B1")
    ok(
        c.post(
            f"{API}/projects/{r.pid}/quality/near-expiry/hold",
            json={"stock_line_ids": [old["stock_line_id"]]},
        ),
        201,
    )
    f = ok(c.post(f"{API}/projects/{r.pid}/quality/fefo-checks", json=body), 201)
    assert f["result"] == "compliant"


def test_ac33_cold_return_and_ac34_ira(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    c, reem = api.as_("imran.siddiq"), api.as_("reem.mutairi")
    ret = ok(
        c.post(
            f"{API}/projects/{r.pid}/quality/returns",
            json={
                "site_id": _site(db),
                "customer_id": r.customer("NDC"),
                "lines": [
                    {"product_id": r.product("NDC-Y"), "batch": "Y9", "qty": 20},
                    {"product_id": r.product("NDC-5001"), "batch": "U9", "qty": 5},
                ],
            },
        ),
        201,
    )
    by = {ln["batch"]: ln["id"] for ln in ret["lines"]}
    a, b2 = by["Y9"], by["U9"]
    err(
        c.post(
            f"{API}/quality/returns/{ret['id']}/grade",
            json={"lines": [{"line_id": a, "grade": "A"}]},
        ),
        422,
        "COLD_RETURN_NO_HISTORY",
    )
    g = ok(
        c.post(
            f"{API}/quality/returns/{ret['id']}/grade",
            json={"lines": [{"line_id": a, "grade": "C"}, {"line_id": b2, "grade": "A"}]},
        )
    )
    assert g["status"] == "graded"
    conf = ok(reem.post(f"{API}/quality/returns/{ret['id']}/confirm", json={}))
    assert conf["status"] == "confirmed" and conf["hold_id"]
    lines = [
        {
            "sku": "NDC-5001",
            "location": f"L{i}",
            "system_qty": 10,
            "counted_qty": 10 if i >= 12 else 11,
        }
        for i in range(400)
    ]
    cc = ok(
        c.post(
            f"{API}/projects/{r.pid}/quality/cycle-counts",
            json={"site_id": _site(db), "lines": lines},
        ),
        201,
    )
    assert (
        cc["lines_counted"] == 400 and cc["lines_within"] == 388 and D(cc["ira_pct"]) == D("97.0")
    )


def test_ac35_mock_recall_and_ac36_real_recall_hold(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    c, reem = api.as_("imran.siddiq"), api.as_("reem.mutairi")
    site = _site(db)
    ok(
        import_kind(
            c,
            r.pid,
            "stock_snapshot",
            site,
            b"owner,sku,batch,location,zone,qty\nNDC,NDC-Y,NDC-Y-2611,C2,Z-CHL1,600\n",
            L(date(2026, 10, 5), 23),
        ),
        201,
    )
    rc = ok(
        reem.post(
            f"{API}/projects/{r.pid}/quality/recalls",
            json={
                "site_id": site,
                "recall_type": "supplier",
                "recall_class": "II",
                "items": [{"product_id": r.product("NDC-Y"), "batch": "NDC-Y-2611"}],
                "reason": "Supplier notice: packaging seal defect.",
            },
        ),
        201,
    )
    assert rc["trace"]["on_hand"] == "600.000" and rc["hold_id"] and rc["ncr_id"]
    h = ok(reem.get(f"{API}/quality/holds/{rc['hold_id']}"))
    assert h["lines"][0]["qty"] == "600.000"
    d = err(
        api.as_("saad.anazi").post(
            f"{API}/quality/holds/{rc['hold_id']}/decide", json={"action": "release"}
        ),
        422,
        "HOLD_RELEASE_BLOCKED",
    )
    assert any(b["code"] == "BATCH_IN_OPEN_RECALL" for b in d["meta"]["blockers"])
    n = ok(api.as_("reem.mutairi").get(f"{API}/quality/ncrs/{rc['ncr_id']}"))
    assert (
        n["classification"] == "critical"
        and n["source_type"] == "recall"
        and n["status"] == "draft"
    )
    err(
        reem.post(
            f"{API}/projects/{r.pid}/quality/recalls",
            json={
                "site_id": site,
                "recall_type": "regulator",
                "items": [{"sku": "NDC-Y", "batch": "X"}],
                "reason": "Regulator notice received.",
            },
        ),
        422,
        "VALIDATION_ERROR",
    )


def _trip(c, r: R, db, classes: list[str], comps: list[dict] | None = None) -> dict:  # type: ignore[no-untyped-def]
    site = _site(db)
    rows = ["shipment_ref,owner,consignee,sku,batch,ordered_qty,promised_at"]
    for i, sku in enumerate(classes):
        rows.append(f"S-{sku}-{i},{sku.split('-')[0]},Store {i},{sku},B{i},10,2026-10-06 14:00")
    ok(import_kind(c, r.pid, "shipments", site, ("\n".join(rows) + "\n").encode()), 201)
    ships = [
        s
        for s in ok(c.get(f"{API}/projects/{r.pid}/quality/shipments?unassigned=true"))
        if s["shipment_ref"].startswith("S-")
    ]
    body = {
        "site_id": site,
        "carrier_id": None,
        "plate_text": "1234 ABC",
        "compartments": comps or [{"code": "C1", "setpoint": "-20"}],
        "shipments": [{"shipment_id": s["id"], "compartment": "C1"} for s in ships],
    }
    return c.post(f"{API}/projects/{r.pid}/quality/trips", json=body)


def test_ac37_ac38_transport_dispatch(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    imran, naveen = api.as_("imran.siddiq"), api.as_("naveen.kumar")
    err(_trip(imran, r, db, ["GFF-2001", "NDC-Y"]), 422, "INCOMPATIBLE_LOAD")
    from app.models.quality.q3 import QShipmentLine

    for sl in db.scalars(select(QShipmentLine)):
        db.delete(sl)
    db.flush()
    for s in db.scalars(select(QShipment)):
        db.delete(s)
    db.commit()
    t = ok(_trip(imran, r, db, ["GFF-2001"]), 201)
    sid = t["shipments"][0]["id"]
    pre = {
        "answers": answers("QRPL"),
        "box_temp_c": "-12",
        "loading_temps": [{"shipment_id": sid, "temp_c": "-19", "mte_id": r.mte("MTE-0051")}],
    }
    t = ok(imran.post(f"{API}/quality/trips/{t['id']}/preload", json=pre))
    assert t["preload_passed"] is False and "PRECOOL:C1" in t["preload_failures"]
    err(imran.post(f"{API}/quality/trips/{t['id']}/dispatch", json={}), 422, "PRELOAD_FAILED")
    assert (
        imran.post(
            f"{API}/quality/trips/{t['id']}/dispatch",
            json={"override_reason": "Box re-cooled and checked again at −19 °C."},
        ).status_code
        == 403
    )
    d = ok(
        naveen.post(
            f"{API}/quality/trips/{t['id']}/dispatch",
            json={"override_reason": "Box re-cooled and checked again at −19 °C."},
        )
    )
    assert d["status"] == "dispatched" and d["signoffs"][0]["step"] == "dispatch_override"
    # AC-Q3-40: POD_REQUIRED, then deliver
    err(imran.post(f"{API}/quality/trips/{t['id']}/deliver"), 422, "POD_REQUIRED")
    sig = attach(imran, "q_pod", t["id"], "pod.pdf")
    ok(
        imran.post(
            f"{API}/quality/trips/{t['id']}/pods",
            json={
                "shipment_id": sid,
                "receiver_name": "Store keeper",
                "signature_attachment_id": sig,
            },
        ),
        201,
    )
    dl = ok(imran.post(f"{API}/quality/trips/{t['id']}/deliver"))
    assert dl["status"] == "closed"  # no logger named → closes with the PODs
    # medicines: no override
    for s in db.scalars(select(QShipment)):
        s.trip_id = None
        s.delivered_at = datetime(2026, 10, 1)  # type: ignore[assignment]
    db.commit()
    t = ok(_trip(imran, r, db, ["SAHM-3001"], [{"code": "C1", "setpoint": "5"}]), 201)
    sid = t["shipments"][0]["id"]
    ok(
        imran.post(
            f"{API}/quality/trips/{t['id']}/preload",
            json={
                "answers": answers("QRPL", fail=(1,)),
                "loading_temps": [{"shipment_id": sid, "temp_c": "5", "mte_id": r.mte("MTE-0051")}],
            },
        )
    )
    err(
        naveen.post(
            f"{API}/quality/trips/{t['id']}/dispatch",
            json={"override_reason": "Box re-cooled and checked again at 5 °C."},
        ),
        422,
        "OVERRIDE_NOT_ALLOWED",
    )


def test_ac40_transit_excursion_ncr_and_notify(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    imran = api.as_("imran.siddiq")
    t = ok(_trip(imran, r, db, ["GFF-2001"]), 201)
    sid = t["shipments"][0]["id"]
    ok(
        imran.post(
            f"{API}/quality/trips/{t['id']}/preload",
            json={
                "answers": answers("QRPL"),
                "box_temp_c": "-21",
                "loading_temps": [
                    {"shipment_id": sid, "temp_c": "-20", "mte_id": r.mte("MTE-0051")}
                ],
            },
        )
    )
    ok(imran.post(f"{API}/quality/trips/{t['id']}/dispatch", json={}))
    vals = [-21.0] * 6 + [-14.0] * 24 + [-20.0] * 6
    res = ok(
        import_readings(
            imran,
            r.pid,
            "trip",
            t["id"],
            readings_csv(series(L(date(2026, 10, 6), 6), vals, step=5)),
        ),
        201,
    )
    x = res["excursions"][0]
    assert x["severity"] == "major"
    full = ok(imran.get(f"{API}/quality/excursions/{x['id']}"))
    assert full["kind"] == "transit" and full["ncr"] is not None
    n = ok(imran.get(f"{API}/quality/ncrs/{full['ncr']['id']}"))
    assert n["source_type"] == "trip"
    tr = ok(imran.get(f"{API}/quality/trips/{t['id']}"))
    assert tr["shipments"][0]["notify_consignee"] is True and tr["transit_data"] is True


def test_ac39_vehicle_readiness_warning(q3setup: None, api: Api, db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Q-TRN-04: a named site vehicle that is not ready warns VEHICLE_NOT_READY; nothing in 7b is
    created and the trip is not blocked."""
    from app.core.site_vehicle_enums import SiteVehReadiness
    from app.models import Vehicle
    from app.models.quality.q3 import QTrip
    from app.models.site_vehicle import VehicleCheck
    from app.services.quality.q3 import transport
    from app.services.site_vehicle import common as sv

    v = db.scalar(select(Vehicle).limit(1))
    if v is None:
        return
    monkeypatch.setattr(sv, "is_site", lambda _v: True)
    monkeypatch.setattr(
        sv,
        "readiness",
        lambda _db, _v, _d=None: (SiteVehReadiness.docs_expired, ["istimara:2026-09-30"]),
    )
    before = db.scalar(select(VehicleCheck.id).limit(1))
    t = QTrip(
        project_id=v.project_id,
        vehicle_id=v.id,
        compartments=[],
        site_id=db.scalar(select(Site.id).limit(1)),
    )
    info, warnings = transport.readiness(db, t)
    assert info and info["readiness"] == "docs_expired"
    assert [w.code for w in warnings] == ["VEHICLE_NOT_READY"]
    assert db.scalar(select(VehicleCheck.id).limit(1)) == before


def test_holds_hidden_from_viewer_photos_and_rp_scope(q3setup: None, api: Api, db) -> None:  # type: ignore[no-untyped-def]
    r = R(db)
    c = api.as_("imran.siddiq")
    h = ok(
        c.post(
            f"{API}/projects/{r.pid}/quality/holds",
            json={
                "site_id": _site(db),
                "reason": "other",
                "lines": [{"product_id": r.product("NDC-Y"), "batch": "Z1", "qty": 1}],
            },
        ),
        201,
    )
    sarah = api.as_("sarah.mitchell")
    read = ok(sarah.get(f"{API}/quality/holds/{h['id']}"))
    assert read["placed_by"] is None
    assert (
        sarah.post(
            f"{API}/projects/{r.pid}/quality/holds",
            json={
                "site_id": _site(db),
                "reason": "other",
                "lines": [{"batch": "Z", "sku": "X", "qty": 1}],
            },
        ).status_code
        == 403
    )
    # Lama (RESP_PHARMACIST) does not resolve for a food hold → it is not visible to her
    assert api.as_("lama.qarni").get(f"{API}/quality/holds/{h['id']}").status_code == 404
    assert db.get(QHold, h["id"]) is not None
