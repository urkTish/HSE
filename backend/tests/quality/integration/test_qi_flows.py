"""Cross-package flows where the Quality packages meet (spec 8-quality §6 items 1–4, handover §7.5;
decision D-370). Every test runs on the integrated registries: Q1, Q2, Q3 and Q4 are all
registered, so a record of one part is seen by the others through `RECORD_TYPES`, `NCR_SOURCES`,
`HOLD_CHECKS`, `DOSSIER_SECTIONS` and the OOT sources. Clock HSE_CLOCK_AT 2026-10-06 10:00."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.core.clock import set_now
from app.core.hse_enums import CaSourceType
from app.core.quality.q3 import QReadingSource, QReadingTarget
from app.db.session import get_sessionmaker
from app.models import CorrectiveAction, User
from app.models.quality import QMteItem, QMteUsage, QNcr, QRpRule
from app.models.quality.q3 import QMonitoringPoint, QReading, QStorageZone
from tests.conftest import Api, Ids
from tests.quality.q0.qh import API, attach, ca_body, err, ok, sign, to_proposed
from tests.quality.q1.q1h import (
    approved_itp,
    decide_body,
    photo,
    schedule,
    stc_points,
    submit_ir,
)
from tests.quality.q2.h2 import new_test, results, specimen_values, supplier, to_lab
from tests.quality.q3.h3 import L, R

D = Decimal


def _email(uid: Any) -> str:
    with get_sessionmaker()() as db:
        u = db.get(User, uuid.UUID(str(uid)))
        assert u is not None
        return u.email


def _dossier(api: Api, ids: Ids) -> tuple[Any, dict[str, Any]]:
    hatem = api.as_("hatem.shehri")
    d = ok(
        hatem.post(
            f"{API}/projects/{ids.project('ANIA-EXP')}/quality/dossiers",
            json={
                "title_en": "Pier B level 3",
                "title_ar": "الرصيف B المستوى 3",
                "zone_ids": [ids.zone("Z-PIERB")],
            },
        ),
        201,
    )
    return hatem, d


def _blocker_text(c: Any, dossier_id: str) -> str:
    dd = ok(c.get(f"{API}/quality/dossiers/{dossier_id}"))
    return " ".join(b["detail_en"] for b in dd["blockers"])


# ---- §6 item 1: failed lab test (Q2) on an IR (Q1) → NCR (Q0) → CA (Phase 1) → dossier (Q1) ----


def test_failed_test_on_an_ir_raises_ncr_ca_and_blocks_the_dossier(
    qi_libs: None, api: Api, ids: Ids
) -> None:
    itp = approved_itp(api, ids)
    joseph = api.as_("joseph.mathew.qc")
    ir = ok(submit_ir(joseph, ids, itp, [30]), 201)
    t = to_lab(joseph, new_test(joseph, ids, ir_id=ir["id"], zone_id=ids.zone("Z-PIERB")))
    r = ok(results(joseph, t, specimen_values(t, 28, ["33.0", "33.4"])))
    assert r["verdict"] == "fail" and r["ncr_decision"]["mode"] == "raised"  # Q-TST-06
    nid = r["ncr_decision"]["ncr_id"]
    with get_sessionmaker()() as db:
        n = db.get(QNcr, uuid.UUID(nid))
        assert n is not None
        assert n.source_type.value == "test_result" and n.classification.value == "critical"
        assert n.status.value == "open" and n.zone_id == uuid.UUID(ids.zone("Z-PIERB"))
        ncr_no, owner = n.ncr_no, n.owner_id
    # the IR shows the failed test through the Q2 → Q1 link (§3.4, RECORD_TYPES of Q1 and Q2)
    ird = ok(joseph.get(f"{API}/quality/inspection-requests/{ir['id']}"))
    tl = [x for x in ird["links"] if x["record_type"] == "test_request"]
    assert len(tl) == 1 and tl[0]["visible"] and tl[0]["ref"] == r["test_no"]
    # Q-CAP-02: the CA is a Phase 1 corrective action with the quality source
    ow = api.as_(_email(owner))
    ca = ok(ow.post(f"{API}/quality/ncrs/{nid}/actions", json=ca_body(ids)), 201)["actions"][0]
    with get_sessionmaker()() as db:
        row = db.get(CorrectiveAction, uuid.UUID(ca["id"]))
        assert row is not None and row.source_type == CaSourceType.quality_ncr
    # Q-DOS-03 (b): the Q2-sourced NCR blocks the Q1 dossier of its zone until it closes
    hatem, d = _dossier(api, ids)
    assert ncr_no in _blocker_text(hatem, d["id"])
    with get_sessionmaker()() as db:
        n = db.get(QNcr, uuid.UUID(nid))
        assert n is not None
        n.status = "closed"  # type: ignore[assignment]  # the close-out itself is Q0's (AC-Q0-36)
        n.closed_date = date(2026, 10, 6)
        db.commit()
    assert ncr_no not in _blocker_text(hatem, d["id"])


# ---- §6 item 2: pour (Q2) against the pre-pour hold IR (Q1) through HOLD_CHECKS --------------


def test_pour_start_follows_the_real_q1_hold_point(qi_libs: None, api: Api, ids: Ids) -> None:
    itp = approved_itp(api, ids)
    joseph, abd = api.as_("joseph.mathew.qc"), api.as_("abdullah.dossary")
    ir = ok(submit_ir(joseph, ids, itp, [30]), 201)
    body = {
        "element": "Pier B level 3 slab",
        "site_id": ids.site("S-LAND"),
        "zone_id": ids.zone("Z-PIERB"),
        "engagement_id": ids.engagement("RAWABI"),
        "grade": "C40",
        "volume_m3": "186",
        "location_ref": "Level 3 slab, grid C14–C20",
        "pre_pour_ir_id": ir["id"],
    }
    p = ok(joseph.post(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/pours", json=body), 201)
    p30 = next(x for x in itp["points"] if x["seq"] == 30)
    assert p["itp_point_id"] == p30["id"]  # D-370: the IR's hold point
    schedule(abd, ir["id"])
    rej = decide_body([30], "rejected", cover="33", fail="RB-03")
    ok(abd.post(f"{API}/quality/inspection-requests/{ir['id']}/decide", json=rej))
    err(
        joseph.post(f"{API}/quality/pours/{p['id']}/start", json={}), 422, "HOLD_POINT_NOT_RELEASED"
    )
    # a re-inspection round approves the hold → the same pour starts without a warning
    ok(
        joseph.post(
            f"{API}/quality/inspection-requests/{ir['id']}/reinspection",
            json={"note": "Spacers added and cover checked at every bar.", "photos": [photo()]},
        )
    )
    schedule(abd, ir["id"])
    ok(
        abd.post(
            f"{API}/quality/inspection-requests/{ir['id']}/decide",
            json=decide_body([30], raise_ncr=False),
        )
    )
    st = ok(joseph.post(f"{API}/quality/pours/{p['id']}/start", json={}))
    assert st["status"] == "started"
    assert "HOLD_STATUS_UNKNOWN" not in {w["code"] for w in st["warnings"]}


# ---- §6 item 3: calibration out of tolerance (Q2) over Q1, Q2 and Q3 measurements ------------


def _accept_cal(c: Any, signer: Any, mte_id: str, d: str, points: list[dict[str, Any]]) -> Any:
    x = ok(
        c.post(
            f"{API}/quality/mte/{mte_id}/calibrations",
            json={
                "cal_date": d,
                "provider_supplier_id": supplier("CAL-NMS"),
                "certificate_no": f"NMS-{d}-{mte_id[:4]}",
                "points": points,
            },
        ),
        201,
    )
    attach(c, "q_calibration_cert", x["id"], "certificate.pdf")
    return ok(
        signer.post(f"{API}/quality/calibrations/{x['id']}/decide", json={"decision": "approved"})
    )


def test_oot_review_lists_ir_measurements_and_test_sampling(
    qi_libs: None, api: Api, ids: Ids
) -> None:
    """Construction: the thermometer's usages by Q1 (IR measurement, structured value and the
    criterion limit, D-370) and Q2 (test sampling, `value_note` fallback, D-342)."""
    mazen, rania = api.as_("mazen.harbi"), api.as_("rania.zahrani")
    pid = ids.project("ANIA-EXP")
    m = ok(
        mazen.post(
            f"{API}/projects/{pid}/quality/mte",
            json={
                "mte_type": "thermometer",
                "description": "Concrete thermometer",
                "interval_months": 12,
                "tolerance_value": "0.5",
                "tolerance_unit": "°C",
            },
        ),
        201,
    )
    _accept_cal(mazen, rania, m["id"], "2026-03-01", [{"nominal": "20", "as_found": "20.1"}])
    itp = approved_itp(api, ids, points=stc_points(rebar_type="W"))
    joseph, abd = api.as_("joseph.mathew.qc"), api.as_("abdullah.dossary")
    ir = ok(submit_ir(joseph, ids, itp, [50], loc="Level 2 slab"), 201)
    schedule(abd, ir["id"])
    body = decide_body([50], temp="31.6")
    body["measurements"][0]["mte_id"] = m["id"]
    ok(abd.post(f"{API}/quality/inspection-requests/{ir['id']}/decide", json=body))
    with get_sessionmaker()() as db:
        u = db.scalar(select(QMteUsage).where(QMteUsage.record_id == uuid.UUID(ir["id"])))
        assert u is not None and (u.value, u.limit_high, u.unit) == (D("31.6"), D("32"), "°C")
    t = new_test(joseph, ids, "SLUMP", zone_id=ids.zone("Z-PIERB"))
    to_lab(joseph, t, mte_ids=[m["id"]], mte_notes={m["id"]: "value=29.0;hi=32"})
    c2 = _accept_cal(
        mazen,
        rania,
        m["id"],
        "2026-10-06",
        [{"nominal": "30", "as_found": "30.8", "as_left": "30.1"}],
    )
    assert c2["as_found_ok"] is False
    lst = ok(rania.get(f"{API}/projects/{pid}/quality/oot-reviews"))
    rv = ok(rania.get(f"{API}/quality/oot-reviews/{lst[0]['id']}"))
    by_type = {i["record_type"]: i for i in rv["items"]}
    assert set(by_type) == {"ir", "test_request"}
    assert D(by_type["ir"]["margin"]) == D("0.4") and by_type["ir"]["proposed"] == "recheck"
    assert by_type["ir"]["ref"] == ir["ir_no"]
    assert D(by_type["test_request"]["margin"]) == D("3")
    assert by_type["test_request"]["proposed"] == "no_impact"


def test_oot_review_lists_receiving_checks_and_logger_readings(
    qi_libs: None, api: Api, ids: Ids
) -> None:
    """Logistics: a probe's receiving checks (Q3 receipt lines with the arrival band, D-370) and a
    logger's readings of the monitoring point it was assigned to (Q3 `OOT_SOURCES`, one item per
    point and day); Q3's own usage rows of the point are not listed twice."""
    imran, reem = api.as_("imran.siddiq"), api.as_("reem.mutairi")
    pid = ids.project("RUH-CCH")
    with get_sessionmaker()() as db:  # RUH-CCH has no quality engineer: the project names Reem
        for rule in db.scalars(
            select(QRpRule).where(
                QRpRule.project_id == uuid.UUID(pid), QRpRule.record_type == "calibration"
            )
        ):
            rule.assignee_kind, rule.assignee = "user", ids.user("reem.mutairi")  # type: ignore[assignment]
        db.commit()
    with get_sessionmaker()() as db:
        r = R(db)
        logger = db.scalar(
            select(QMteItem).where(
                QMteItem.project_id == uuid.UUID(pid), QMteItem.mte_no == "MTE-0101"
            )
        )
        assert logger is not None
        lid = str(logger.id)
        pt = next(
            x
            for x in db.scalars(select(QMonitoringPoint))
            if any(str(lg.get("mte_id")) == lid for lg in x.loggers or [])
        )
        pt_id, pt_code = pt.id, pt.code
        zone = db.get(QStorageZone, pt.zone_id)
        assert zone is not None and zone.temp_max is not None
        hi = zone.temp_max
        frz_lines = {"zone": r.zone("Z-DOCK"), "customer": r.customer("GFF")}
        chicken = r.product("GFF-2001")
        probe = r.mte("MTE-0042")
    sp = [{"nominal": "-20", "as_found": "-20.1", "tolerance": "0.5"}]
    _accept_cal(imran, reem, lid, "2026-09-01", sp)
    _accept_cal(imran, reem, probe, "2026-09-01", sp)
    # logger readings of its point on two days (imported rows carry no instrument)
    with get_sessionmaker()() as db:
        days = (
            (date(2026, 9, 10), (hi - 3, hi - D("2.5"))),
            (date(2026, 9, 11), (hi - 3, hi - D("0.3"))),
        )
        for day, temps in days:
            for i, v in enumerate(temps):
                db.add(
                    QReading(
                        project_id=uuid.UUID(pid),
                        target_type=QReadingTarget.point,
                        target_id=pt_id,
                        channel="",
                        measured_at=L(day, 8 + i),
                        temperature_c=D(str(v)),
                        source=QReadingSource.import_,
                        probe_fault=False,
                        voided=False,
                        created_at=L(day, 12),
                    )
                )
        db.commit()
    # a receiving check with the probe on 2026-09-12: frozen chicken at −18.4 °C (band ≤ −18.0)
    set_now(L(date(2026, 9, 12), 7))
    rec = ok(
        imran.post(
            f"{API}/projects/{pid}/quality/receipts",
            json={
                "site_id": ids.site("S-DC1"),
                "dock_zone_id": frz_lines["zone"],
                "customer_id": frz_lines["customer"],
                "arrived_at": L(date(2026, 9, 12), 6, 10).isoformat(),
                "unload_start": L(date(2026, 9, 12), 6, 25).isoformat(),
                "unload_end": L(date(2026, 9, 12), 6, 48).isoformat(),
                "lines": [
                    {
                        "product_id": chicken,
                        "batch": "GFF-C-2611",
                        "expiry_date": "2027-03-01",
                        "qty_received": 480,
                        "product_temp_c": "-18.4",
                        "mte_id": probe,
                    }
                ],
            },
        ),
        201,
    )
    set_now(datetime(2026, 10, 6, 7, 0, tzinfo=UTC))
    with get_sessionmaker()() as db:
        u = db.scalar(select(QMteUsage).where(QMteUsage.record_id == uuid.UUID(rec["id"])))
        assert u is not None and (u.value, u.limit_low, u.limit_high) == (
            D("-18.4"),
            None,
            D("-18.0"),
        )
    bad = [{"nominal": "-20", "as_found": "-20.8", "as_left": "-20.1", "tolerance": "0.5"}]
    _accept_cal(imran, reem, lid, "2026-09-15", bad)
    _accept_cal(imran, reem, probe, "2026-09-15", bad)
    reviews = {
        x["mte_no"]: x
        for x in ok(reem.get(f"{API}/projects/{pid}/quality/oot-reviews"))
        if x["mte_no"] in ("MTE-0101", "MTE-0042")
    }
    lg = ok(reem.get(f"{API}/quality/oot-reviews/{reviews['MTE-0101']['id']}"))
    assert [i["record_type"] for i in lg["items"]] == ["monitoring_point", "monitoring_point"]
    d10, d11 = lg["items"]
    assert d10["ref"].startswith(f"{pt_code} · 2026-09-10") and D(d10["value"]) == hi - D("2.5")
    assert d10["proposed"] == "no_impact" and D(d11["value"]) == hi - D("0.3")
    assert d11["proposed"] == "recheck" and D(d11["limit_high"]) == hi
    pr = ok(reem.get(f"{API}/quality/oot-reviews/{reviews['MTE-0042']['id']}"))
    rc = [i for i in pr["items"] if i["record_type"] == "receipt"]
    assert len(rc) == 1 and rc[0]["record_id"] == rec["id"] and rc[0]["proposed"] == "recheck"
    # an item decided `ncr` raises the NCR from the OOT review (source oot_review)
    n = ok(
        reem.post(
            f"{API}/quality/oot-items/{d11['id']}/decision",
            json={
                "decision": "ncr",
                "justification": "Frozen zone reading near the limit; true value may be −17.5 °C.",
            },
        )
    )
    with get_sessionmaker()() as db:
        x = db.get(QNcr, uuid.UUID(n["ncr_id"]))
        assert x is not None and x.source_type.value == "oot_review"


# ---- §6 item 4: excursion (Q3) → NCR (Q0) disposition → hold release (Q3) ----------------------


def test_excursion_ncr_disposition_releases_the_hold(qi_libs: None, api: Api, ids: Ids) -> None:
    from tests.quality.q3.test_q3_cold_chain import _qx13

    with get_sessionmaker()() as db:
        r = R(db)
        imran, saad = api.as_("imran.siddiq"), api.as_("saad.anazi")
        x = _qx13(imran, r, db)
    nid, hold_id = x["ncr"]["id"], x["hold"]["id"]
    ok(imran.post(f"{API}/quality/excursions/{x['id']}/cause", json={"cause": "defrost"}))
    x = ok(saad.get(f"{API}/quality/excursions/{x['id']}"))
    owner_file = attach(saad, "q_hold", hold_id, "gff-decision.pdf")
    lines = [
        {
            "hold_line_id": ln["hold_line"]["id"],
            "decision": "release",
            "justification": "Within the owner's frozen-poultry time and temperature budget of 6 "
            "h at −12 °C.",
            "owner_decision_attachment_id": owner_file,
        }
        for ln in x["impact_lines"]
    ]
    ok(saad.post(f"{API}/quality/excursions/{x['id']}/assess", json={"lines": lines}))
    d = err(
        saad.post(f"{API}/quality/holds/{hold_id}/decide", json={"action": "release"}),
        422,
        "HOLD_RELEASE_BLOCKED",
    )
    assert d["meta"]["blockers"][0]["code"] == "NCR_DISPOSITION_NOT_APPROVED"
    # the real Q0 path: containment, RCA, CA, disposition proposed and approved by the matrix
    with get_sessionmaker()() as db:
        n = db.get(QNcr, uuid.UUID(nid))
        assert n is not None
        owner = n.owner_id
    ow = api.as_(_email(owner))
    nd = ok(ow.get(f"{API}/quality/ncrs/{nid}"))
    body_ca = ca_body(ids, owner_id=ids.user("imran.siddiq"), verifier_id=ids.user("reem.mutairi"))
    nid_ = nd["id"]
    ok(
        ow.put(
            f"{API}/quality/ncrs/{nid_}/containment",
            json={"containment_en": "Zone stock held and tagged; defrost stopped.", "done": True},
        )
    )
    ok(
        ow.put(
            f"{API}/quality/ncrs/{nid_}/rca",
            json={
                "method": "five_why",
                "cause_category": "machine",
                "data": {
                    "whys": [
                        "The defrost cycle did not stop.",
                        "The defrost timer relay stuck closed.",
                        "The relay was past its replacement interval.",
                    ],
                    "root_cause": "No preventive replacement interval for defrost relays.",
                },
            },
        )
    )
    ok(ow.post(f"{API}/quality/ncrs/{nid_}/actions", json=body_ca), 201)
    attach(ow, "q_ncr_evidence", nid_, "impact-assessment.pdf")
    ok(
        ow.put(
            f"{API}/quality/ncrs/{nid_}/disposition",
            json={
                "lines": [{"disposition": "use_as_is", "note": "Released per the assessment."}],
                "disposition_justification_en": "The signed impact assessment keeps every line "
                "inside the owner's time and temperature budget.",
            },
        )
    )
    ok(ow.post(f"{API}/quality/ncrs/{nid_}/propose"))
    ok(sign(api.as_("reem.mutairi"), nid_, "disposition"))
    # use as is needs the concession of the logistics position WAREHOUSE_MGR (Saad)
    signed = ok(sign(saad, nid_, "concession"))
    assert signed["status"] == "disposition_approved"
    h = ok(saad.post(f"{API}/quality/holds/{hold_id}/decide", json={"action": "release"}))
    assert {ln["line_status"] for ln in h["lines"]} == {"released"}
    _ = to_proposed
