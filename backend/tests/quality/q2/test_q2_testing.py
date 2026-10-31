"""Test requests, verdicts, NCRs, verification and amendments; pours (spec 8-quality §C.2,
AC-Q2-02, -04, -06…-14)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models import Notification
from app.models.quality import QNcr, QSupplier
from app.services.quality import registry as reg
from app.services.quality.jobs import run_slot
from tests.conftest import Api, Ids
from tests.quality.q2.h2 import API, err, new_test, ok, results, specimen_values, to_lab


def _failed_cyl(api: Api, ids: Ids, values: tuple[str, str] = ("33.0", "33.4")) -> tuple[dict, dict]:
    joseph = api.as_("joseph.mathew.qc")
    t = to_lab(joseph, new_test(joseph, ids))
    r = ok(results(joseph, t, specimen_values(t, 28, list(values))))
    return t, r


def test_AC02_fail_b_opens_critical_ncr_at_results_entered(q2: None, api: Api, ids: Ids) -> None:
    t, r = _failed_cyl(api, ids)
    assert r["status"] == "results_entered" and r["verdict"] == "fail"
    assert r["verdict_detail"]["clause"] == "b" and r["verdict_detail"]["test"] == "33.2"
    assert r["criterion_code"] == "CONC-ACI-40" and r["ncr_decision"]["mode"] == "raised"
    with get_sessionmaker()() as db:
        n = db.get(QNcr, uuid.UUID(r["ncr_decision"]["ncr_id"]))
        assert n is not None
        assert n.classification.value == "critical" and n.status.value == "open"
        assert n.source_type.value == "test_result" and n.category.value == "testing_failure"
        assert n.item_key == "TT:CONC-CYL"


def test_AC07_results_need_the_lab_report_file(q2: None, api: Api, ids: Ids) -> None:
    joseph = api.as_("joseph.mathew.qc")
    t = to_lab(joseph, new_test(joseph, ids))
    res = results(joseph, t, specimen_values(t, 28, ["41.0", "42.0"]), report=False)
    assert "lab report" in str(err(res, 422, "TEST_RESULT_INCOMPLETE")["meta"])
    res2 = results(joseph, t, specimen_values(t, 28, ["41.0"]))  # one 28-day specimen missing
    err(res2, 422, "TEST_RESULT_INCOMPLETE")


def test_AC08_segregation_on_verification(q2: None, api: Api, ids: Ids) -> None:
    t, _r = _failed_cyl(api, ids, ("41.0", "42.0"))
    body = {"decision": "approved"}
    err(api.as_("joseph.mathew.qc").post(f"{API}/quality/tests/{t['id']}/verify", json=body), 422, "SOD_CONFLICT")
    err(api.as_("bilal.qureshi").post(f"{API}/quality/tests/{t['id']}/verify", json=body), 422, "SOD_CONFLICT")
    assert api.as_("hatem.shehri").post(f"{API}/quality/tests/{t['id']}/verify", json=body).status_code == 403
    v = ok(api.as_("rania.zahrani").post(f"{API}/quality/tests/{t['id']}/verify", json=body))
    assert v["status"] == "verified" and v["verified_by"]["full_name_en"] == "Rania Al-Zahrani"
    sig = ok(api.as_("rania.zahrani").get(f"{API}/quality/signoffs", params={"record_type": "test_request", "record_id": t["id"]}))
    assert [s["step"] for s in sig] == ["verify"]


def test_AC09_verified_result_is_amended_never_edited(q2: None, api: Api, ids: Ids) -> None:
    t, r = _failed_cyl(api, ids)
    rania = api.as_("rania.zahrani")
    ok(rania.post(f"{API}/quality/tests/{t['id']}/verify", json={"decision": "approved"}))
    err(rania.patch(f"{API}/quality/tests/{t['id']}", json={"location_ref": "Somewhere else"}), 409, "RESULT_VERIFIED")
    joseph = api.as_("joseph.mathew.qc")
    err(results(joseph, t, specimen_values(t, 28, ["40.0", "41.0"]), report=False), 409, "RESULT_VERIFIED")
    from tests.quality.q2.h2 import attach

    body = {
        "reason": "Lab issued amended report: transcription error on specimen 4.",
        "report_no": "RGM-26-11873-A1",
        "specimens": specimen_values(t, 28, ["33.0", "41.4"]),
    }
    err(rania.post(f"{API}/quality/tests/{t['id']}/amend", json=body), 422, "TEST_RESULT_INCOMPLETE")
    attach(rania, "q_test_report", t["id"], "amended-report.pdf")
    a = ok(rania.post(f"{API}/quality/tests/{t['id']}/amend", json=body))
    assert a["status"] == "amended" and a["result_version"] == 2 and a["verdict"] == "pass"
    assert a["history"][0]["verdict"] == "fail" and a["history"][0]["version"] == 1
    with get_sessionmaker()() as db:
        n = db.get(QNcr, uuid.UUID(r["ncr_decision"]["ncr_id"]))
        assert n is not None and n.status.value == "open"


def test_AC06_early_strength_is_indicative_and_warns(q2: None, api: Api, ids: Ids) -> None:
    joseph = api.as_("joseph.mathew.qc")
    t = to_lab(joseph, new_test(joseph, ids))
    r = ok(joseph.put(f"{API}/quality/tests/{t['id']}/specimens", json={"specimens": specimen_values(t, 7, ["23.5", "24.5"])}))
    assert r["verdict"] == "indicative" and r["verdict_detail"]["indicative"]["7"] == "24.00"
    assert "EARLY_STRENGTH_LOW" in {w["code"] for w in r["warnings"]}
    with get_sessionmaker()() as db:
        n = db.scalar(select(Notification).where(Notification.user_id == uuid.UUID(ids.user("joseph.mathew.qc")), Notification.title_en.contains("early strength")))
        assert n is not None


def test_AC10_prompt_mode_decline_needs_a_reason(q2: None, api: Api, ids: Ids) -> None:
    pid = ids.project("ANIA-EXP")
    ok(api.as_("hatem.shehri").patch(f"{API}/projects/{pid}/quality/settings", json={"values": {"test_auto_ncr": "prompt"}}))
    t, r = _failed_cyl(api, ids)
    assert r["ncr_prompt"] is True and r["ncr_decision"] == {} and "ncr_decision" in r["actions"]
    joseph = api.as_("joseph.mathew.qc")
    err(joseph.post(f"{API}/quality/tests/{t['id']}/ncr-decision", json={"raise_ncr": False}), 422, "VALIDATION_ERROR")
    d = ok(joseph.post(f"{API}/quality/tests/{t['id']}/ncr-decision", json={"raise_ncr": False, "reason": "Set contaminated in transit; resampling the element tomorrow."}))
    assert d["ncr_decision"]["mode"] == "declined"


def test_AC11_lab_scope_warning_and_disqualified_lab(q2: None, api: Api, ids: Ids) -> None:
    joseph = api.as_("joseph.mathew.qc")
    t = new_test(joseph, ids, "CONC-CORE")
    assert "LAB_NOT_ACCREDITED_FOR_SCOPE" in {w["code"] for w in t["warnings"]}
    t2 = new_test(joseph, ids, "CONC-CYL")
    assert "LAB_NOT_ACCREDITED_FOR_SCOPE" not in {w["code"] for w in t2["warnings"]}
    with get_sessionmaker()() as db:
        s = db.scalar(select(QSupplier).where(QSupplier.supplier_code == "LAB-RGM"))
        assert s is not None
        s.status = "disqualified"  # type: ignore[assignment]
        db.commit()
    body = {"test_type_code": "CONC-CYL", "site_id": ids.site("S-LAND"), "engagement_id": ids.engagement("RAWABI"), "lab_supplier_id": str(s.id)}
    err(joseph.post(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/tests", json=body), 422, "SUPPLIER_DISQUALIFIED")


def test_AC12_overdue_specimen_alerts_the_requester_once(q2: None, api: Api, ids: Ids) -> None:
    joseph = api.as_("joseph.mathew.qc")
    t = to_lab(joseph, new_test(joseph, ids), sampled_at="2026-09-06T10:00:00+03:00")
    spec = next(s for s in t["specimens"] if s["age_days"] == 28)
    assert spec["due_on"] == "2026-10-04"
    uid = uuid.UUID(ids.user("joseph.mathew.qc"))

    def count() -> int:
        with get_sessionmaker()() as db:
            return len(list(db.scalars(select(Notification).where(Notification.user_id == uid, Notification.title_en.contains("(28 d) not tested")))))

    with get_sessionmaker()() as db:
        run_slot(db, "quality_alerts", datetime(2026, 10, 5, 4, 12, tzinfo=UTC))
        db.commit()
    assert count() == 0  # 2026-10-05 is still within test_overdue_days (1)
    for _ in range(2):
        with get_sessionmaker()() as db:
            run_slot(db, "quality_alerts", datetime(2026, 10, 6, 4, 12, tzinfo=UTC))
            db.commit()
    assert count() == 2  # one per untested 28-day specimen, sent once


def test_AC04_retest_cores_leave_the_original_fail(q2: None, api: Api, ids: Ids) -> None:
    t, _r = _failed_cyl(api, ids)
    joseph = api.as_("joseph.mathew.qc")
    core = to_lab(joseph, new_test(joseph, ids, "CONC-CORE", retest_of_id=t["id"]))
    rc = ok(results(joseph, core, [{"id": s["id"], "values": {"strength": v}} for s, v in zip(core["specimens"], ["36.1", "34.9", "33.6"], strict=True)]))
    assert rc["verdict"] == "pass" and rc["verdict_detail"]["mean"] == "34.87"
    assert ok(joseph.get(f"{API}/quality/tests/{t['id']}"))["verdict"] == "fail"
    links = ok(joseph.get(f"{API}/quality/links", params={"record_type": "test_request", "record_id": core["id"]}))
    assert any(x["kind"] == "relates" for x in links)


def _pour(api: Api, ids: Ids, **kw: object) -> dict:
    body = {
        "element": "Pier B level 3 slab",
        "site_id": ids.site("S-LAND"),
        "engagement_id": ids.engagement("RAWABI"),
        "grade": "C40",
        "volume_m3": "186",
        "location_ref": "Level 3 slab, grid C14–C20",
        **kw,
    }
    return ok(api.as_("joseph.mathew.qc").post(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/pours", json=body), 201)


def test_AC13_pour_closed_short_of_sets_warns(q2: None, api: Api, ids: Ids) -> None:
    joseph = api.as_("joseph.mathew.qc")
    p = _pour(api, ids)
    assert p["sets_required"] == 4
    st = ok(joseph.post(f"{API}/quality/pours/{p['id']}/start", json={}))
    assert "HOLD_STATUS_UNKNOWN" in {w["code"] for w in st["warnings"]}
    for _ in range(3):
        t = new_test(joseph, ids, pour_id=p["id"])
        assert t["mix_key"] and t["engagement_id"] == ids.engagement("RAWABI")
    c = ok(joseph.post(f"{API}/quality/pours/{p['id']}/close", json={}))
    assert c["sets_taken"] == 3 and "POUR_SAMPLING_SHORT" in {w["code"] for w in c["warnings"]}
    assert "POUR_SAMPLING_SHORT" in c["flags"]


@pytest.fixture
def hold_rejected() -> Iterator[None]:
    reg.HOLD_CHECKS["itp_point"] = lambda _db, _point, _loc: False
    yield
    reg.HOLD_CHECKS.pop("itp_point", None)


def test_AC14_pour_start_blocked_by_rejected_hold_point(q2: None, api: Api, ids: Ids, hold_rejected: None) -> None:
    p = _pour(api, ids, itp_point_id=str(uuid.uuid4()))
    err(api.as_("joseph.mathew.qc").post(f"{API}/quality/pours/{p['id']}/start", json={}), 422, "HOLD_POINT_NOT_RELEASED")


def test_profile_and_logistics_tests(q2: None, api: Api, ids: Ids) -> None:
    """AC-Q2-32 (tests part): an ATP swab on RUH-CCH works; a construction test type is refused."""
    imran = api.as_("imran.siddiq")
    t = new_test(imran, ids, "ATP-SWAB", project="RUH-CCH", location_ref="Dock door 3")
    assert t["test_no"].startswith("TST-RUH-CCH-2026-")
    body = {"test_type_code": "CONC-CYL", "site_id": ids.site("S-DC1"), "lab_supplier_id": t["lab_supplier_id"]}
    err(imran.post(f"{API}/projects/{ids.project('RUH-CCH')}/quality/tests", json=body), 409, "PROFILE_INACTIVE")
    lab = to_lab(imran, t)
    r = ok(results(imran, lab, results={"rlu": "88"}))
    assert r["verdict"] == "pass"
