"""Calibration, M&TE status, OOT reviews, label and range check; competence (spec 8-quality §C.4,
§C.5, AC-Q2-20…26)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.clock import now
from app.db.session import get_sessionmaker
from app.models import Notification, Project
from app.models.quality import QMteItem, QNcr, QRpRule
from app.services.quality import mte as qmte
from app.services.quality.jobs import run_slot
from app.services.quality.q2 import calibration as cal
from tests.conftest import Api, Ids
from tests.quality.q2.h2 import API, attach, err, ok, supplier


def _item(c: TestClient, ids: Ids, project: str = "ANIA-EXP", **kw: Any) -> dict[str, Any]:
    body = {
        "mte_type": "thermometer",
        "description": "Concrete thermometer",
        "interval_months": 12,
        "tolerance_value": "0.5",
        "tolerance_unit": "°C",
        **kw,
    }
    return ok(c.post(f"{API}/projects/{ids.project(project)}/quality/mte", json=body), 201)


def _cal(
    c: TestClient, mte_id: str, d: str, points: list[dict[str, Any]], cert: bool = True, **kw: Any
) -> dict[str, Any]:
    body = {
        "cal_date": d,
        "provider_supplier_id": supplier("CAL-NMS"),
        "certificate_no": f"NMS-{d}",
        "points": points,
        **kw,
    }
    x = ok(c.post(f"{API}/quality/mte/{mte_id}/calibrations", json=body), 201)
    if cert:
        attach(c, "q_calibration_cert", x["id"], "certificate.pdf")
    return x


def test_AC20_due_date_and_status_bands(q2: None, api: Api, ids: Ids) -> None:
    mazen, rania = api.as_("mazen.harbi"), api.as_("rania.zahrani")
    m = _item(mazen, ids)
    assert m["cal_status"] == "overdue" and m["cal_status_reason"] == "Never calibrated."
    c = _cal(mazen, m["id"], "2026-01-15", [{"nominal": "20", "as_found": "20.1"}])
    err(
        mazen.post(f"{API}/quality/calibrations/{c['id']}/decide", json={"decision": "approved"}),
        422,
        "SOD_CONFLICT",
    )
    a = ok(
        rania.post(f"{API}/quality/calibrations/{c['id']}/decide", json={"decision": "approved"})
    )
    assert (
        a["status"] == "accepted"
        and a["next_due"] == "2027-01-14"
        and a["cal_no"] == "CAL-ANIA-EXP-2026-0001"
    )
    item = ok(mazen.get(f"{API}/quality/mte/{m['id']}"))
    assert item["cal_due_on"] == "2027-01-14" and item["cal_status"] == "calibrated"
    with get_sessionmaker()() as db:
        row = db.get(QMteItem, uuid.UUID(m["id"]))
        assert row is not None
        assert cal.compute_status(db, row, date(2026, 12, 14))[0].value == "calibrated"
        assert cal.compute_status(db, row, date(2026, 12, 15))[0].value == "due_soon"
        assert cal.compute_status(db, row, date(2027, 1, 14))[0].value == "due_soon"
        assert cal.compute_status(db, row, date(2027, 1, 15))[0].value == "overdue"
        assert cal.due_on(date(2026, 1, 31), 1) == date(2026, 2, 27)  # month-end clamp − 1 day


def test_AC21_as_left_out_of_tolerance_is_out_of_service(q2: None, api: Api, ids: Ids) -> None:
    mazen, rania, hatem = api.as_("mazen.harbi"), api.as_("rania.zahrani"), api.as_("hatem.shehri")
    m = _item(mazen, ids)
    c = _cal(
        mazen, m["id"], "2026-09-01", [{"nominal": "20", "as_found": "21.0", "as_left": "20.9"}]
    )
    assert c["as_found_ok"] is False and c["as_left_ok"] is False
    ok(rania.post(f"{API}/quality/calibrations/{c['id']}/decide", json={"decision": "approved"}))
    item = ok(mazen.get(f"{API}/quality/mte/{m['id']}"))
    assert item["cal_status"] == "out_of_service"
    u = ok(
        mazen.post(
            f"{API}/quality/mte/{m['id']}/usage", json={"record_type": "mte", "record_id": m["id"]}
        ),
        201,
    )
    assert u["verdict"] == "warned"
    pid = ids.project("ANIA-EXP")
    ok(
        hatem.patch(
            f"{API}/projects/{pid}/quality/settings", json={"values": {"mte_use_policy": "block"}}
        )
    )
    err(
        mazen.post(
            f"{API}/quality/mte/{m['id']}/usage", json={"record_type": "mte", "record_id": m["id"]}
        ),
        422,
        "MTE_NOT_CALIBRATED",
    )
    # a manual override wins; clearing it returns to the computed status
    o = ok(
        mazen.put(
            f"{API}/quality/mte/{m['id']}/cal-override",
            json={"status": "limited_use", "reason": "Use above 10 °C only"},
        )
    )
    assert o["cal_status"] == "limited_use"
    assert (
        ok(mazen.put(f"{API}/quality/mte/{m['id']}/cal-override", json={"status": None}))[
            "cal_status"
        ]
        == "out_of_service"
    )


def test_AC22_qx11_out_of_tolerance_review(q2: None, api: Api, ids: Ids) -> None:
    reem, imran = api.as_("reem.mutairi"), api.as_("imran.siddiq")
    with get_sessionmaker()() as db:  # RUH-CCH has no quality engineer: the project names Reem
        for r in db.scalars(
            select(QRpRule).where(
                QRpRule.project_id == uuid.UUID(ids.project("RUH-CCH")),
                QRpRule.record_type == "calibration",
            )
        ):
            r.assignee_kind, r.assignee = "user", ids.user("reem.mutairi")  # type: ignore[assignment]
        db.commit()
    m = _item(
        imran,
        ids,
        "RUH-CCH",
        mte_type="temp_probe",
        description="Receiving probe",
        interval_months=6,
        site_id=ids.site("S-DC1"),
    )
    c1 = _cal(
        imran,
        m["id"],
        "2026-03-08",
        [{"nominal": "-18", "as_found": "-18.2"}, {"nominal": "0", "as_found": "0.1"}],
    )
    ok(reem.post(f"{API}/quality/calibrations/{c1['id']}/decide", json={"decision": "approved"}))
    with get_sessionmaker()() as db:
        project = db.get(Project, uuid.UUID(ids.project("RUH-CCH")))
        assert project is not None
        for i in range(37):
            day = datetime(2026, 3, 9, 5, tzinfo=UTC) + timedelta(days=i * 5)
            note = "value=-18.4;lo=-30;hi=-18" if i in (11, 29) else "value=-21.0;lo=-30;hi=-18"
            qmte.record_usage(
                db,
                project,
                uuid.UUID(m["id"]),
                "receipt",
                uuid.uuid4(),
                uuid.UUID(ids.user("imran.siddiq")),
                day,
                note,
            )
        db.commit()
    c2 = _cal(
        imran,
        m["id"],
        "2026-09-10",
        [
            {"nominal": "-18", "as_found": "-17.9"},
            {"nominal": "0", "as_found": "1.2", "as_left": "0.1"},
        ],
    )
    assert (
        c2["as_found_ok"] is False and c2["as_left_ok"] is True and c2["max_found_error"] == "1.2"
    )
    ok(reem.post(f"{API}/quality/calibrations/{c2['id']}/decide", json={"decision": "approved"}))
    lst = ok(reem.get(f"{API}/projects/{ids.project('RUH-CCH')}/quality/oot-reviews"))
    assert len(lst) == 1
    r = ok(reem.get(f"{API}/quality/oot-reviews/{lst[0]['id']}"))
    assert (r["period_from"], r["period_to"], r["item_count"], r["proposed_no_impact"]) == (
        "2026-03-08",
        "2026-09-10",
        37,
        35,
    )
    assert ok(imran.get(f"{API}/quality/mte/{m['id']}"))["cal_status"] == "calibrated"
    err(
        reem.post(f"{API}/quality/oot-reviews/{r['id']}/close", json={}),
        422,
        "OOT_REVIEW_INCOMPLETE",
    )
    near = [i for i in r["items"] if i["proposed"] == "recheck"]
    assert len(near) == 2 and near[0]["margin"] == "0.400000"
    n = ok(
        reem.post(
            f"{API}/quality/oot-items/{near[0]['id']}/decision",
            json={
                "decision": "ncr",
                "justification": "Frozen line at −18.4 °C recorded; true value may be −17.2 °C.",
            },
        )
    )
    with get_sessionmaker()() as db:
        ncr = db.get(QNcr, uuid.UUID(n["ncr_id"]))
        assert (
            ncr is not None
            and ncr.source_type.value == "oot_review"
            and ncr.classification.value == "major"
        )
    ok(
        reem.post(
            f"{API}/quality/oot-items/{near[1]['id']}/decision",
            json={"decision": "recheck", "recheck_ref": "RCV-RUH-CCH-2026-01877 re-measured"},
        )
    )
    assert (
        ok(
            reem.post(
                f"{API}/quality/oot-reviews/{r['id']}/accept-proposals",
                json={"justification": "Margin larger than the as-found error."},
            )
        )["decided"]
        == 35
    )
    closed = ok(reem.post(f"{API}/quality/oot-reviews/{r['id']}/close", json={}))
    assert (
        closed["status"] == "closed" and closed["decided_count"] == 37 and closed["ncr_count"] == 1
    )


def test_AC23_logger_range_not_covered(q2: None, api: Api, ids: Ids) -> None:
    imran, reem = api.as_("imran.siddiq"), api.as_("reem.mutairi")
    with get_sessionmaker()() as db:
        for r in db.scalars(
            select(QRpRule).where(
                QRpRule.project_id == uuid.UUID(ids.project("RUH-CCH")),
                QRpRule.record_type == "calibration",
            )
        ):
            r.assignee_kind, r.assignee = "user", ids.user("reem.mutairi")  # type: ignore[assignment]
        db.commit()
    m = _item(imran, ids, "RUH-CCH", mte_type="temp_logger", description="Logger")
    c = _cal(
        imran,
        m["id"],
        "2026-03-01",
        [{"nominal": "5", "as_found": "5.0"}, {"nominal": "25", "as_found": "25.1"}],
    )
    ok(reem.post(f"{API}/quality/calibrations/{c['id']}/decide", json={"decision": "approved"}))
    w = ok(imran.get(f"{API}/quality/mte/{m['id']}/range-check", params={"lo": "-25", "hi": "-18"}))
    assert [x["code"] for x in w] == ["CAL_RANGE_NOT_COVERED"]
    assert (
        ok(imran.get(f"{API}/quality/mte/{m['id']}/range-check", params={"lo": "2", "hi": "8"}))
        == []
    )


def test_AC24_certificate_required_for_calibration_not_for_verification(
    q2: None, api: Api, ids: Ids
) -> None:
    mazen, rania = api.as_("mazen.harbi"), api.as_("rania.zahrani")
    m = _item(mazen, ids)
    c = _cal(mazen, m["id"], "2026-09-01", [{"nominal": "20", "as_found": "20.0"}], cert=False)
    err(
        rania.post(f"{API}/quality/calibrations/{c['id']}/decide", json={"decision": "approved"}),
        422,
        "CALIBRATION_CERT_REQUIRED",
    )
    cone = _item(
        mazen,
        ids,
        mte_type="slump_cone",
        description="Slump cone",
        check_kind="verification",
        interval_months=1,
    )
    v = ok(
        mazen.post(
            f"{API}/quality/mte/{cone['id']}/calibrations",
            json={
                "cal_date": "2026-10-01",
                "in_house": True,
                "verification_note": "Dimensions 100 / 200 / 300 mm within ±3 mm.",
            },
        ),
        201,
    )
    assert v["kind"] == "verification"
    a = ok(
        rania.post(f"{API}/quality/calibrations/{v['id']}/decide", json={"decision": "approved"})
    )
    assert a["status"] == "accepted" and a["next_due"] == "2026-10-31"
    lab = ok(mazen.get(f"{API}/quality/mte/{cone['id']}/label"))
    assert (
        lab["colour"] == "amber"
        and lab["status_ar"] == "قريب الاستحقاق"
        and lab["path"].endswith(cone["id"])
    )
    assert ok(mazen.post(f"{API}/quality/mte/{cone['id']}/label"))["printed_at"] is not None


def test_AC25_competence_through_the_hook_providers(q2: None, api: Api, ids: Ids) -> None:
    hatem = api.as_("hatem.shehri")
    pid = ids.project("ANIA-EXP")
    q = {"user_id": ids.user("mazen.harbi"), "code": "NDT-RT-L2"}
    before = ok(
        hatem.get(
            f"{API}/projects/{pid}/quality/competence/check", params={**q, "on": "2026-09-15"}
        )
    )
    assert before["met"] is True and before["valid_until"] == "2026-09-30"
    after = ok(hatem.get(f"{API}/projects/{pid}/quality/competence/check", params=q))
    assert after["met"] is False and after["code"] == "COMPETENCE_NOT_MET"
    nobody = ok(
        hatem.get(
            f"{API}/projects/{pid}/quality/competence/check",
            params={"user_id": ids.user("faisal.harbi"), "code": "NDT-RT-L2"},
        )
    )
    assert nobody["met"] is False and nobody["code"] == "HOLDER_NOT_LINKED"
    with get_sessionmaker()() as db:
        from app.services.quality import registry as reg

        assert (
            reg.competence_check(
                db, uuid.UUID(ids.user("arun.pillai")), "CWI", date(2026, 10, 6)
            ).met
            is True
        )
        assert (
            reg.competence_check(
                db, uuid.UUID(ids.user("arun.pillai")), "NO-SUCH", date(2026, 10, 6)
            ).met
            is None
        )


def test_AC26_matrix_expiring_and_alerts(q2: None, api: Api, ids: Ids) -> None:
    joseph = ids.user("joseph.mathew.qc")
    with get_sessionmaker()() as db:
        run_slot(db, "quality_daily", datetime(2026, 9, 20, 0, 21, tzinfo=UTC))
        db.commit()
    mx = ok(
        api.as_("hatem.shehri").get(
            f"{API}/projects/{ids.project('ANIA-EXP')}/quality/competence/matrix"
        )
    )
    cell = next(c for c in mx["cells"] if c["user_id"] == joseph and c["code"] == "CONC-FIELD-TECH")
    assert cell["state"] == "expiring" and cell["valid_until"] == "2026-10-20"
    arun_cwi = next(
        c for c in mx["cells"] if c["user_id"] == ids.user("arun.pillai") and c["code"] == "CWI"
    )
    assert arun_cwi["state"] == "met"
    with get_sessionmaker()() as db:
        run_slot(db, "quality_daily", now())
        db.commit()
        titles = [
            n.title_en
            for n in db.scalars(
                select(Notification).where(Notification.user_id == uuid.UUID(joseph))
            )
        ]
    assert sum("CONC-FIELD-TECH ends 2026-10-20 (30-day" in t for t in titles) == 1
    assert not any("(7-day" in t for t in titles)
