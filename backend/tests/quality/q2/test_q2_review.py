"""Review follow-ups of package Q2: dossier sections and blockers (§B.7 / Q-DOS-03 e), the MIR
checklist on the 6d engine (§C.3.2, §A.7), PDPL on welder and calibration names, list scoping,
the competence matrix export (Q-CPT-03) and the rules without an acceptance criterion of their own
(Q-MAT-02, -06, -08, Q-WLD-02, -03, -07, -08, Q-TST-02, -05, -13, void, §C.8 alerts)."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from sqlalchemy import func, select

from app.db.session import get_sessionmaker
from app.models import Notification
from app.models.field import ChecklistResponse
from app.models.quality import QNcr, QSupplier
from app.models.quality.q2 import QCompetenceCell
from app.services.quality import ensure_registered
from app.services.quality import registry as reg
from app.services.quality.jobs import run_slot
from tests.conftest import Api, Ids
from tests.quality.q2.h2 import API, err, new_test, ok, results, specimen_values, to_lab
from tests.quality.q2.test_q2_calibration import _cal, _item
from tests.quality.q2.test_q2_materials import _decided_mar, _mir, _submitted_mar
from tests.quality.q2.test_q2_testing import _pour
from tests.quality.q2.test_q2_welding import _lot, _ndt, _setup, _weld, _worker


def _titles(contains: str) -> list[str]:
    with get_sessionmaker()() as db:
        return [
            n.title_en
            for n in db.scalars(
                select(Notification).where(Notification.title_en.contains(contains))
            )
        ]


def _slot(slot: str, at: datetime) -> None:
    with get_sessionmaker()() as db:
        run_slot(db, slot, at)
        db.commit()


def _settings(api: Api, ids: Ids, values: dict[str, Any], project: str = "ANIA-EXP") -> None:
    ok(
        api.as_("hatem.shehri").patch(
            f"{API}/projects/{ids.project(project)}/quality/settings", json={"values": values}
        )
    )


# ---- S1 dossier sections -------------------------------------------------------------------------


def test_dossier_sections_items_and_blockers(q2: None, api: Api, ids: Ids) -> None:
    ensure_registered()
    assert {"mar", "mir", "tests", "welding", "calibration"} <= set(reg.DOSSIER_SECTIONS)
    joseph, abdullah, hatem = (
        api.as_("joseph.mathew.qc"),
        api.as_("abdullah.dossary"),
        api.as_("hatem.shehri"),
    )
    mazen, rania = api.as_("mazen.harbi"), api.as_("rania.zahrani")
    pier, other = ids.zone("Z-PIERB"), ids.zone("Z-MSCP")
    m = _item(mazen, ids, site_id=ids.site("S-LAND"))
    c = _cal(mazen, m["id"], "2026-09-01", [{"nominal": "20", "as_found": "20.1"}])
    ok(rania.post(f"{API}/quality/calibrations/{c['id']}/decide", json={"decision": "approved"}))
    t = to_lab(joseph, new_test(joseph, ids, zone_id=pier), mte_ids=[m["id"]])
    ok(results(joseph, t, specimen_values(t, 28, ["33.0", "33.4"])))  # fails (b) → NCR
    t_out = to_lab(joseph, new_test(joseph, ids, zone_id=other))
    ok(results(joseph, t_out, specimen_values(t_out, 28, ["33.0", "33.4"])))
    mar = _decided_mar(api, ids)
    x = _mir(joseph, ids, mar_id=mar["id"], storage_zone_id=pier)
    ok(joseph.post(f"{API}/quality/mirs/{x['id']}/submit"))
    d = ok(
        abdullah.post(
            f"{API}/quality/mirs/{x['id']}/decide",
            json={
                "result": "rejected",
                "accepted_qty": "0",
                "rejected_qty": "240",
                "comment": "Ovality beyond tolerance on the whole delivery.",
            },
        )
    )
    dos = SimpleNamespace(project_id=uuid.UUID(ids.project("ANIA-EXP")), zone_ids=[pier])
    with get_sessionmaker()() as db:
        sec = reg.DOSSIER_SECTIONS
        tests = sec["tests"].items(db, dos)
        assert [i["ref"] for i in tests] == [t["test_no"]] and tests[0]["status"] == "fail"
        assert tests[0]["files"] and tests[0]["link_path"] == f"/quality/tests/{t['id']}"
        assert [b.code for b in sec["tests"].blockers(db, dos)] == ["TEST_FAILED_NCR_OPEN"]
        assert [i["ref"] for i in sec["mir"].items(db, dos)] == [d["mir_no"]]
        assert [b.code for b in sec["mir"].blockers(db, dos)] == ["MIR_QUARANTINE_OPEN"]
        assert [i["record_id"] for i in sec["mar"].items(db, dos)] == [mar["id"]]
        cal_items = sec["calibration"].items(db, dos)
        assert [i["record_id"] for i in cal_items] == [c["id"]] and cal_items[0]["files"]
        assert sec["welding"].items(db, dos) == []
        empty = SimpleNamespace(project_id=dos.project_id, zone_ids=[], system_ids=[])
        assert sec["tests"].items(db, empty) == [] and sec["mar"].items(db, empty) == []
    qid = d["quarantine_ids"][0]
    ok(
        hatem.post(
            f"{API}/quality/quarantine/{qid}/dispose",
            json={"to_status": "returned", "return_note_no": "RN-GP-0102"},
        )
    )
    with get_sessionmaker()() as db:
        assert reg.DOSSIER_SECTIONS["mir"].blockers(db, dos) == []


# ---- S2 MIR checklist ----------------------------------------------------------------------------


def test_mir_checklist_scored_on_6d_and_warns_on_decide(q2: None, api: Api, ids: Ids) -> None:
    joseph, abdullah = api.as_("joseph.mathew.qc"), api.as_("abdullah.dossary")
    tpl = ok(joseph.get(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/mir-checklist"))
    assert tpl["template_code"] == "QMIR" and len(tpl["items"]) == 8
    x = _mir(
        joseph,
        ids,
        category="consumables",
        engagement_id=ids.engagement("RAWABI"),
        material_description="Welding rods E7018",
        quantity="40",
        unit="box",
    )
    assert "checklist" in x["actions"]
    answers: list[dict[str, Any]] = [
        {"item_code": it["item_code"], "answer": "compliant"} for it in tpl["items"]
    ]
    answers[2] = {"item_code": tpl["items"][2]["item_code"], "answer": "non_compliant"}
    err(
        joseph.put(f"{API}/quality/mirs/{x['id']}/checklist", json={"answers": answers}),
        422,
        "VALIDATION_ERROR",
    )  # a non-compliant answer needs a note (6d EXE-2)
    answers[2]["note"] = "Several boxes crushed and wet on arrival."
    r = ok(joseph.put(f"{API}/quality/mirs/{x['id']}/checklist", json={"answers": answers}))
    ck = r["checklist"]
    assert ck["result"] == "fail" and ck["critical_fail_count"] == 1
    assert "MIR_CHECKLIST_CRITICAL_FAIL" in {w["code"] for w in r["warnings"]}
    with get_sessionmaker()() as db:
        resp = db.get(ChecklistResponse, uuid.UUID(ck["id"]))
        assert resp is not None and resp.owner_type.value == "q_mir"
    ok(joseph.post(f"{API}/quality/mirs/{x['id']}/submit"))
    dec = ok(
        abdullah.post(
            f"{API}/quality/mirs/{x['id']}/decide",
            json={
                "result": "accepted_with_comments",
                "accepted_qty": "30",
                "rejected_qty": "10",
                "comment": "Ten wet boxes rejected; the rest dried and accepted.",
            },
        )
    )
    assert "MIR_CHECKLIST_CRITICAL_FAIL" in {w["code"] for w in dec["warnings"]}
    err(
        joseph.put(f"{API}/quality/mirs/{x['id']}/checklist", json={"answers": answers}),
        409,
        "INVALID_TRANSITION",
    )


# ---- S3 PDPL and S4 list scoping ---------------------------------------------------------------


def test_viewer_sees_no_names_and_lists_follow_the_engagement_tree(
    q2: None, api: Api, ids: Ids
) -> None:
    _setup(api, ids)  # welder W-017 of NAJD with an active WPQ
    sarah, arun, hatem = (
        api.as_("sarah.mitchell"),
        api.as_("arun.pillai"),
        api.as_("hatem.shehri"),
    )
    pid = ids.project("ANIA-EXP")
    full = ok(hatem.get(f"{API}/projects/{pid}/quality/welders"))
    assert full[0]["full_name_en"] == "Welder W-017"
    seen = ok(sarah.get(f"{API}/projects/{pid}/quality/welders"))
    assert seen[0]["stamp"] == "W-017" and seen[0]["full_name_en"] == "—"
    assert seen[0]["worker_no"] is None and seen[0]["full_name_ar"] is None
    # a RAWABI welder (tier 1) is outside the NAJD inspector's tree (NAJD is RAWABI's tier 2)
    w = ok(
        hatem.post(
            f"{API}/projects/{pid}/quality/welders",
            json={
                "worker_id": _worker("Welder W-030"),
                "stamp": "W-030",
                "engagement_id": ids.engagement("RAWABI"),
            },
        ),
        201,
    )
    ok(
        hatem.post(
            f"{API}/projects/{pid}/quality/wpqs",
            json={
                "welder_id": w["id"],
                "standard": "AWS_D1_1",
                "process": "SMAW",
                "test_date": "2026-06-01",
                "positions": ["1G"],
                "thickness_min_mm": "3",
                "thickness_max_mm": "30",
                "test_method": "RT",
            },
        ),
        201,
    )
    assert len(ok(hatem.get(f"{API}/projects/{pid}/quality/wpqs"))) == 2
    assert [x["stamp"] for x in ok(arun.get(f"{API}/projects/{pid}/quality/wpqs"))] == ["W-017"]
    mazen, rania = api.as_("mazen.harbi"), api.as_("rania.zahrani")
    najd = _item(mazen, ids, owner_kind="engagement", owner_engagement_id=ids.engagement("NAJD"))
    raw = _item(mazen, ids, owner_kind="engagement", owner_engagement_id=ids.engagement("RAWABI"))
    own = _item(mazen, ids)
    for m in (najd, raw, own):
        _cal(mazen, m["id"], "2026-09-01", [{"nominal": "20", "as_found": "20.1"}])
    oot = _cal(
        mazen,
        raw["id"],
        "2026-09-20",
        [{"nominal": "20", "as_found": "21.5", "as_left": "20.1"}],
    )
    ok(rania.post(f"{API}/quality/calibrations/{oot['id']}/decide", json={"decision": "approved"}))
    page = ok(arun.get(f"{API}/projects/{pid}/quality/calibrations"))
    assert {c["mte_id"] for c in page["items"]} == {najd["id"], own["id"]}
    assert len(ok(hatem.get(f"{API}/projects/{pid}/quality/calibrations"))["items"]) == 4
    assert ok(arun.get(f"{API}/projects/{pid}/quality/oot-reviews")) == []
    assert len(ok(rania.get(f"{API}/projects/{pid}/quality/oot-reviews"))) == 1
    decided = ok(rania.get(f"{API}/quality/calibrations/{oot['id']}"))
    assert decided["decided_by"]["full_name_en"] == "Rania Al-Zahrani"
    assert ok(sarah.get(f"{API}/quality/calibrations/{oot['id']}"))["decided_by"] is None
    # §C.8: the open review alerts its resolvers the day after its due date, once
    rv = ok(rania.get(f"{API}/projects/{pid}/quality/oot-reviews"))[0]
    due = datetime.fromisoformat(f"{rv['due_on']}T04:12:00+00:00")
    _slot("quality_alerts", due)
    assert _titles("out-of-tolerance review overdue") == []
    _slot("quality_alerts", due + timedelta(days=1))
    sent = _titles(f"{rv['oot_no']}: out-of-tolerance review overdue")
    _slot("quality_alerts", due + timedelta(days=2))
    assert sent and len(_titles("out-of-tolerance review overdue")) == len(sent)


# ---- S6 competence matrix export, N3 member checks ----------------------------------------------


def test_competence_matrix_dataset_and_member_checks(q2: None, api: Api, ids: Ids) -> None:
    from app.services.scorecard import datasets

    ds = datasets.get("quality_competence_matrix")
    assert ds is not None and ds.export_cap.value == "export.quality"
    assert ds.names_cap is not None and ds.names_cap.value == "competence.manage"
    _slot("quality_daily", datetime(2026, 10, 6, 0, 21, tzinfo=UTC))
    with get_sessionmaker()() as db:
        n = db.scalar(
            select(func.count())
            .select_from(QCompetenceCell)
            .where(QCompetenceCell.project_id == uuid.UUID(ids.project("ANIA-EXP")))
        )
        cell = db.scalar(
            select(QCompetenceCell).where(
                QCompetenceCell.holder_user_id == uuid.UUID(ids.user("arun.pillai")),
                QCompetenceCell.requirement_code == "CWI",
            )
        )
    assert n and cell is not None and cell.state.value == "met"
    hatem = api.as_("hatem.shehri")
    err(
        hatem.get(
            f"{API}/projects/{ids.project('ANIA-EXP')}/quality/competence/check",
            params={"user_id": ids.user("imran.siddiq"), "code": "CWI"},
        ),
        422,
        "VALIDATION_ERROR",
    )


# ---- S5 materials rules --------------------------------------------------------------------------


def test_mar_overdue_alert_after_the_review_days(q2: None, api: Api, ids: Ids) -> None:
    m = _submitted_mar(api, ids)  # submitted 2026-10-06; mar_review_days 14
    _slot("quality_alerts", datetime(2026, 10, 19, 4, 12, tzinfo=UTC))
    assert _titles("not decided within") == []
    _slot("quality_alerts", datetime(2026, 10, 20, 4, 12, tzinfo=UTC))
    first = _titles(f"{m['mar_no']} Rev.0: not decided within 14 days")
    _slot("quality_alerts", datetime(2026, 10, 21, 4, 12, tzinfo=UTC))
    assert first and len(_titles("not decided within")) == len(first)  # sent once


def test_failed_test_quarantines_remaining_stock_and_ageing_alert(
    q2: None, api: Api, ids: Ids
) -> None:
    mar = _decided_mar(api, ids, "concrete_mix")
    joseph, abdullah = api.as_("joseph.mathew.qc"), api.as_("abdullah.dossary")
    x = _mir(joseph, ids, mar_id=mar["id"], quantity="120", unit="m3")
    ok(joseph.post(f"{API}/quality/mirs/{x['id']}/submit"))
    ok(
        abdullah.post(
            f"{API}/quality/mirs/{x['id']}/decide",
            json={"result": "accepted", "accepted_qty": "120", "rejected_qty": "0"},
        )
    )
    t = to_lab(joseph, new_test(joseph, ids, mir_id=x["id"]))
    r = ok(results(joseph, t, specimen_values(t, 28, ["33.0", "33.4"])))
    assert r["verdict"] == "fail"
    assert ok(joseph.get(f"{API}/quality/mirs/{x['id']}"))["failed_tests"] == 1
    err(
        joseph.post(f"{API}/quality/mirs/{x['id']}/quarantine", json={"quantity": "121"}),
        422,
        "VALIDATION_ERROR",
    )
    q = ok(
        joseph.post(
            f"{API}/quality/mirs/{x['id']}/quarantine",
            json={"quantity": "40", "location_ref": "Batching yard bay 2"},
        ),
        201,
    )
    assert q["status"] == "quarantined" and q["quantity"] == "40" and q["mir_id"] == x["id"]
    # Q-MAT-08: weekly ageing alert once the item is older than quarantine_ageing_days (14)
    _slot("quality_weekly", datetime(2026, 10, 20, 4, 0, tzinfo=UTC))
    assert _titles(f"{q['tag_no']}: quarantined for") == []
    _slot("quality_weekly", datetime(2026, 10, 21, 4, 0, tzinfo=UTC))
    assert _titles(f"{q['tag_no']}: quarantined for 15 days")


# ---- S5 welding rules ----------------------------------------------------------------------------


def test_override_records_unqualified_welder_with_ncr_and_continuity_upto(
    q2: None, api: Api, ids: Ids
) -> None:
    s = _setup(api, ids, ("W-021",), test_date="2026-01-20")  # continuity until 2026-07-19
    arun, hatem = api.as_("arun.pillai"), api.as_("hatem.shehri")
    why = {"override_reason": "Client instructed the tie-in; welder retest booked for Monday."}
    late = {"stamp": "W-021", "welded_on": "2026-10-01"}
    err(_weld(arun, ids, s["wps"], "TIE-J01", **late), 422, "WELDER_NOT_QUALIFIED")
    assert _weld(arun, ids, s["wps"], "TIE-J01", **late, **why).status_code == 403
    w = ok(_weld(hatem, ids, s["wps"], "TIE-J01", **late, **why), 201)
    assert "WELDER_RECORDED_WITH_OVERRIDE" in {x["code"] for x in w["warnings"]}
    with get_sessionmaker()() as db:
        n = db.scalar(select(QNcr).where(QNcr.source_type == "weld"))
        assert n is not None and n.classification.value == "major"
    # N10: the later weld does not make an August weld qualified after the lapse
    err(
        _weld(arun, ids, s["wps"], "TIE-J02", stamp="W-021", welded_on="2026-08-15"),
        422,
        "WELDER_NOT_QUALIFIED",
    )


def test_wpq_confirmation_extends_continuity_in_confirmation_mode(
    q2: None, api: Api, ids: Ids
) -> None:
    s = _setup(api, ids, ("W-021",), test_date="2026-01-20")
    hatem = api.as_("hatem.shehri")
    qid = s["W-021"]["wpq"]["id"]
    err(
        hatem.post(f"{API}/quality/wpqs/{qid}/confirm", json={"date": "2026-06-01"}),
        422,
        "VALIDATION_ERROR",
    )  # mode weld_log
    _settings(api, ids, {"wpq_confirmation_mode": "weld_log_or_confirmation"})
    err(
        hatem.post(f"{API}/quality/wpqs/{qid}/confirm", json={"date": "2026-12-01"}),
        422,
        "VALIDATION_ERROR",
    )  # future
    c = ok(hatem.post(f"{API}/quality/wpqs/{qid}/confirm", json={"date": "2026-06-01"}))
    assert c["last_use"] == "2026-06-01" and c["continuity_until"] == "2026-11-30"


def test_repair_rate_alert_from_ten_first_examinations(q2: None, api: Api, ids: Ids) -> None:
    _s, welds = _lot(api, ids, 12)
    arun = api.as_("arun.pillai")
    joints = [f"PB-RT-T12-J{i:02d}" for i in range(1, 11)]
    for j in joints:
        ok(arun.post(f"{API}/quality/welds/{welds[j]}/select", json={"reason": "random"}))
    _ndt(arun, welds[joints[0]], "reject")
    for j in joints[1:9]:
        _ndt(arun, welds[j], "accept")
    assert _titles("repair rate") == []  # 9 first examinations
    _ndt(arun, welds[joints[9]], "accept")  # 10th: 1 / 10 = 10.0 % > 5.0 %
    assert any("Welder W-017: repair rate 10.0 %" in t for t in _titles("repair rate"))


def test_ndt_technician_competence_blocks_in_block_mode(q2: None, api: Api, ids: Ids) -> None:
    _s, welds = _lot(api, ids, 1)
    arun = api.as_("arun.pillai")
    wid = welds["PB-RT-T12-J01"]
    ok(arun.post(f"{API}/quality/welds/{wid}/select", json={"reason": "random"}))
    mazen = ids.user("mazen.harbi")  # NDT-RT certificate ended 2026-09-30
    _settings(api, ids, {"competence_policy": "block"})
    from tests.quality.q2.h2 import attach

    att = attach(arun, "q_weld", wid, "rt-report.pdf")
    body = {
        "result": "accept",
        "report_no": "DNDT-0001",
        "attachment_id": att,
        "examined_length_mm": "300",
        "technician_user_id": mazen,
    }
    d = err(arun.post(f"{API}/quality/welds/{wid}/ndt", json=body), 422, "COMPETENCE_NOT_MET")
    assert d["meta"]["requirement"] == "NDT-RT-L2"
    _settings(api, ids, {"competence_policy": "warn"})
    r = ok(arun.post(f"{API}/quality/welds/{wid}/ndt", json=body))
    assert "COMPETENCE_NOT_MET" in {w["code"] for w in r["warnings"]}


# ---- S5 testing rules ----------------------------------------------------------------------------


def test_mix_window_flags_every_pour_of_the_failing_window(q2: None, api: Api, ids: Ids) -> None:
    joseph = api.as_("joseph.mathew.qc")
    a, b = _pour(api, ids), _pour(api, ids, element="Pier B level 4 slab")
    verdicts = []
    for day, pour in ((8, a), (9, a), (10, b)):
        t = to_lab(
            joseph,
            new_test(joseph, ids, pour_id=pour["id"]),
            sampled_at=f"2026-09-{day:02d}T10:40:00+03:00",
        )
        r = ok(results(joseph, t, specimen_values(t, 28, ["37.0", "37.4"])))
        verdicts.append((r["verdict"], r["verdict_detail"].get("clause")))
    assert verdicts[-1] == ("fail", "a") and verdicts[0][0] == "pass"
    mix = ok(joseph.get(f"{API}/quality/pours/{a['id']}"))["mix_status"]
    assert mix["flagged"] is True and set(mix["flagged_pour_ids"]) == {a["id"], b["id"]}


def test_verify_returned_void_and_lab_check_at_sampling(q2: None, api: Api, ids: Ids) -> None:
    joseph, rania, hatem = (
        api.as_("joseph.mathew.qc"),
        api.as_("rania.zahrani"),
        api.as_("hatem.shehri"),
    )
    t = to_lab(joseph, new_test(joseph, ids))
    ok(results(joseph, t, specimen_values(t, 28, ["41.0", "42.0"])))
    url = f"{API}/quality/tests/{t['id']}/verify"
    err(
        rania.post(url, json={"decision": "returned", "comment": "Recheck"}),
        422,
        "VALIDATION_ERROR",
    )
    back = ok(
        rania.post(
            url, json={"decision": "returned", "comment": "Report number does not match the file."}
        )
    )
    assert back["status"] == "at_lab"
    why = {"reason": "Raised against the wrong pour; replaced by a new request."}
    assert joseph.post(f"{API}/quality/tests/{t['id']}/void", json=why).status_code == 403
    v = ok(hatem.post(f"{API}/quality/tests/{t['id']}/void", json=why))
    assert v["status"] == "voided"
    # Q-TST-02: the laboratory is checked again on the sampling date
    t2 = new_test(joseph, ids)
    with get_sessionmaker()() as db:
        s = db.scalar(select(QSupplier).where(QSupplier.supplier_code == "LAB-RGM"))
        assert s is not None
        s.status = "disqualified"  # type: ignore[assignment]
        db.commit()
    err(
        joseph.post(
            f"{API}/quality/tests/{t2['id']}/sample",
            json={"sampled_at": "2026-10-06T09:00:00+03:00", "sample_ref": "S-0001"},
        ),
        422,
        "SUPPLIER_DISQUALIFIED",
    )


def test_calibration_due_alerts_at_30_days_then_overdue(q2: None, api: Api, ids: Ids) -> None:
    mazen, rania = api.as_("mazen.harbi"), api.as_("rania.zahrani")
    m = _item(mazen, ids)
    c = _cal(mazen, m["id"], "2025-11-01", [{"nominal": "20", "as_found": "20.1"}])
    ok(rania.post(f"{API}/quality/calibrations/{c['id']}/decide", json={"decision": "approved"}))
    item = ok(mazen.get(f"{API}/quality/mte/{m['id']}"))
    assert item["cal_due_on"] == "2026-10-31"
    _slot("quality_alerts", datetime(2026, 10, 6, 4, 12, tzinfo=UTC))  # 25 days left: d30
    due = _titles(f"{item['mte_no']}: calibration due 2026-10-31")
    _slot("quality_alerts", datetime(2026, 10, 7, 4, 12, tzinfo=UTC))
    assert due and len(_titles(f"{item['mte_no']}: calibration due")) == len(due)  # once
    _slot("quality_alerts", datetime(2026, 11, 2, 4, 12, tzinfo=UTC))
    assert _titles(f"{item['mte_no']}: calibration overdue 2026-10-31")
