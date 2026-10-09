"""6d-field-assurance §9 ACs 9, 49-56, 58-61 (register switch, KPIs, warnings, PDPL, retention,
Arabic). AC 57 (AI tool T21) is parked (PROGRESS)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.models import Attachment, ChecklistResponse, ToolboxTalk, WorkforceReturn
from app.services.field import common as fc
from tests.conftest import Api
from tests.field_helpers import API, P, eng, kpi, local, project

pytestmark = pytest.mark.usefixtures("field_seed", "clock")

# FD9 as reproduced by the seed (DECISIONS: counts follow the Phase 1 inspections; K-112 and
# K-116 differ from the printed table).
FD9 = {
    "ANIA-EXP": {"K34": "85.0 %", "K35": "92.5 %", "K36": "520", "K111": "2", "K113": "95.0 %", "K114": "50.0 %", "K115": "82.4 %",
                 "K116": "93.4 %", "K117": "80.0 %"},
    "RBT-52": {"K36": "67", "K111": "0", "K113": "100.0 %",
               "K114": "—", "K115": "—", "K116": "—", "K117": "—"},
}  # fmt: skip


def field(c: Any, db: Session, pcode: str, **params: Any) -> dict[str, Any]:
    q = {"project_id": str(project(db, pcode).id), "as_of": "2026-09-30", "period": "month",
         "anchor": "2026-09-30", **params}  # fmt: skip
    res = c.get(f"{API}/kpi/field-assurance", params=q)
    assert res.status_code == 200, res.text
    return res.json()  # type: ignore[no-any-return]


def comps(m: dict[str, Any]) -> dict[str, str]:
    return {c["key"]: c["display"] for c in m.get("components") or []}


@pytest.mark.parametrize("code", ["ANIA-EXP", "RBT-52"])
def test_AC54_AC52_fd9(api: Api, db: Session, code: str) -> None:
    body = field(api.as_("faisal.harbi"), db, code,
                 group_by=["month", "contractor", "item_code", "language", "zone"])  # fmt: skip
    got = {m: kpi(body, m)["display"] for m in FD9[code]}
    assert got == FD9[code]
    # K-110 / K-112 follow the generated Phase 1 inspections: pooled weights and repeat share
    pid = project(db, code).id
    R = ChecklistResponse  # noqa: N806
    sept = (R.project_id == pid, R.owner_type == "inspection", R.voided.is_(False),
            R.completed_date >= date(2026, 9, 1), R.completed_date <= date(2026, 9, 30))  # fmt: skip
    ew, aw = db.execute(
        select(func.sum(R.earned_weight), func.sum(R.applicable_weight)).where(*sept)
    ).one()
    k110 = kpi(body, "K110")
    assert (Decimal(k110["numerator"]), Decimal(k110["denominator"])) == (ew, aw)
    from app.models import FieldFinding as F

    fs = list(db.execute(select(F.repeat_of_id).join(R, R.id == F.response_id).where(
        *sept, F.item_code.is_not(None), F.voided.is_(False))))  # fmt: skip
    k112 = kpi(body, "K112")
    assert (int(k112["numerator"]), int(k112["denominator"])) == (
        sum(1 for (x,) in fs if x is not None),
        len(fs),
    )
    if code == "ANIA-EXP":
        assert comps(kpi(body, "K36"))["attendees"] == "13,000"
        k115 = comps(kpi(body, "K115"))
        assert (k115["major_nc"], k115["minor_nc"]) == ("3", "7")
        assert comps(kpi(body, "K111"))["stop_work_orders"] == "1"
        assert "K-36 source: Toolbox register" in body["notes"]
        assert not any("differ" in n for n in body["notes"])
        # K-35b unchanged and no audit / 6b / 6c / PTW record counted in K-34 / K-35
        res = api.as_("faisal.harbi").get(f"{API}/kpi/metrics/K-35b", params={
            "project_id": str(project(db, code).id), "as_of": "2026-09-30", "period": "month",
            "anchor": "2026-09-30"})  # fmt: skip
        assert res.status_code == 200, res.text
        from app.models import Inspection as Ins

        done = db.scalar(select(func.count()).select_from(Ins).where(
            Ins.project_id == pid, Ins.status == "completed", Ins.completed_date >= date(2026, 9, 1),
            Ins.completed_date <= date(2026, 9, 30)))  # fmt: skip
        assert res.json()["kpi"]["display"] == str(done)  # inspections only (D-185)
    item = next(b for b in body["breakdowns"] if b["group_by"] == "item_code")
    assert item["rows"] and all("-" in r["key"] for r in item["rows"])
    assert "WKR-" not in str(body) and "@example.com" not in str(body)


def test_AC9_fd7_coverage(db: Session) -> None:
    from app.hse_jobs import project_scope
    from app.kpi import field as kf
    from app.kpi.periods import Window

    sc = project_scope(db, project(db, "ANIA-EXP"), date(2026, 10, 2))
    us = kf.coverage_units(sc.engine, Window(date(2026, 9, 1), date(2026, 9, 30)))
    miss = [(u.eng, u.site, u.week) for u in us if not u.covered]
    sahara = eng(db, "ANIA-EXP", "SAHARA").id
    assert len(us) == 20 and len(miss) == 1
    assert miss[0][0] == sahara and miss[0][2] + timedelta(days=6) == date(2026, 9, 26)
    assert max(u.week for u in us) + timedelta(days=6) == date(2026, 9, 26)


def _ania_cfg(db: Session, **kw: Any) -> None:
    row = fc.settings_row(db, project(db, "ANIA-EXP").id)
    for k, v in kw.items():
        setattr(row, k, v)
    fc.clear_cache(db)
    db.commit()


def test_AC49_register_switch(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    W = WorkforceReturn  # noqa: N806
    dr_t, dr_a = db.execute(select(func.sum(W.toolbox_talks), func.sum(W.toolbox_attendees)).where(
        W.project_id == pid, W.work_date >= date(2026, 9, 1), W.work_date <= date(2026, 9, 15),
    )).one()  # fmt: skip
    late = list(db.scalars(select(ToolboxTalk).where(
        ToolboxTalk.project_id == pid, ToolboxTalk.delivered_date >= date(2026, 9, 16),
        ToolboxTalk.delivered_date <= date(2026, 9, 30))))  # fmt: skip
    dr_late = db.scalar(select(func.sum(W.toolbox_attendees)).where(
        W.project_id == pid, W.work_date >= date(2026, 9, 16), W.work_date <= date(2026, 9, 30)))  # fmt: skip
    extra = int(Decimal(dr_late) * Decimal("0.06")) + len(late)
    per, rest = divmod(extra, len(late))
    for i, t in enumerate(late):  # register attendees 6 % above the daily returns
        t.unnamed_count += per + (1 if i < rest else 0)
    _ania_cfg(db, toolbox_register_from=date(2026, 9, 16))
    c = api.as_("faisal.harbi")
    body = field(c, db, "ANIA-EXP")
    k36 = kpi(body, "K36")
    reg_att = db.scalar(select(func.sum(ToolboxTalk.unnamed_count)).where(
        ToolboxTalk.id.in_([t.id for t in late])))  # fmt: skip
    from app.models import TalkAttendance

    named = db.scalar(select(func.count()).select_from(TalkAttendance).where(
        TalkAttendance.talk_id.in_([t.id for t in late]),
        TalkAttendance.counted_person_type == "contractor_worker"))  # fmt: skip
    assert k36["display"] == str(int(dr_t) + len(late))
    assert comps(k36)["attendees"] == f"{int(dr_a) + int(reg_att) + int(named):,}"
    assert any("Mixed" in n for n in body["notes"])
    assert any("(attendees)" in n and "talks" not in n for n in body["notes"]), body["notes"]
    _ania_cfg(db, toolbox_register_from=None)
    body = field(c, db, "ANIA-EXP")
    assert kpi(body, "K36")["display"] == "520"
    assert comps(kpi(body, "K36"))["attendees"] == "13,000"


def test_AC50_AC51_w08_and_switch_loosening(api: Api, db: Session) -> None:
    from tests.emer_helpers import site
    from tests.train_helpers import to_csv

    pid = project(db, "ANIA-EXP").id
    head = ["project_code", "site_code", "contractor_code", "work_date", "shift", "headcount",
            "man_hours", "toolbox_talks", "toolbox_attendees"]  # fmt: skip
    content = to_csv(head, [{"project_code": "ANIA-EXP", "site_code": site(db, "S-LAND").code,
                              "contractor_code": "NAJD", "work_date": "2026-09-20", "shift": "day",
                              "headcount": "10", "man_hours": "100", "toolbox_talks": "4",
                              "toolbox_attendees": "40"}])  # fmt: skip
    c = api.as_("faisal.harbi")
    res = c.post(f"{API}/projects/{pid}/workforce-imports",
                 files={"file": ("dr.csv", content, "text/csv")}, data={"mode": "upsert"})  # fmt: skip
    assert res.status_code in (200, 201), res.text
    rows = res.json()["report"]
    assert "W08" in {x for r in rows for x in r["codes"]}, rows
    assert all(r["status"] != "error" for r in rows), rows
    res = c.patch(f"{API}/projects/{pid}/field-settings",
                  json={"toolbox_register_from": "2026-09-10"})  # fmt: skip
    assert res.status_code == 422 and "SETTING_LOOSENING" in res.text, res.text
    res = c.patch(f"{API}/projects/{pid}/field-settings",
                  json={"toolbox_register_from": "2026-08-20"})  # fmt: skip
    assert res.status_code == 200, res.text


def test_AC53_fd6_reach() -> None:
    from uuid import uuid4

    from app.kpi.field import ReachUnit

    u = [ReachUnit(uuid4(), uuid4(), uuid4(), date(2026, 9, 13), Decimal(h), b)
         for h, b in ((800, 742 + 30), (600, 510), (300, 290 + 40))]  # fmt: skip
    assert u[2].reach == 300
    pooled = sum((x.reach for x in u), Decimal(0)) * 100 / sum((x.h for x in u), Decimal(0))
    assert pooled.quantize(Decimal("0.1")) == Decimal("93.1")


def _warns(db: Session, code: str, d: date = date(2026, 10, 2)) -> dict[Any, Any]:
    from app.hse_jobs import project_scope
    from app.kpi import warnings as kwarn
    from app.kpi.periods import Window

    sc = project_scope(db, project(db, code), d)
    ws = kwarn.evaluate(sc, [Window(date(2026, 9, 1), date(2026, 9, 30))])
    return {(w.code.value, w.engagement.code if w.engagement else None): w
            for w in ws if w.code.value in ("E20", "E21")}  # fmt: skip


def test_AC55_e20_e21(db: Session) -> None:
    ania = _warns(db, "ANIA-EXP")
    assert {("E20", None), ("E20", "RAWABI"), ("E21", None), ("E21", "RAWABI")} <= set(ania)
    assert _warns(db, "RBT-52") == {}
    e20 = {i.key: i.value for i in ania[("E20", None)].inputs}
    assert (e20["k114_numerator"], e20["k114_denominator"]) == (1, 2)
    e21 = {i.key: i.value for i in ania[("E21", None)].inputs}
    assert Decimal(str(e21["k117"])) == Decimal("80.0")
    text = " ".join(w.message_en + str([i.value for i in w.inputs]) for w in ania.values())
    assert "WKR-" not in text and "Noura" not in text


def test_AC56_e20_active_order(db: Session) -> None:
    from tests.field_helpers import body, stop_fields, submit

    set_now(local(2026, 9, 21, 10))
    from tests.field_helpers import answers

    a = answers(db, "GSI", {"GSI-05"})
    submit(db, "lina.haddad", body(db, site="S-TWR", zone_code="Z-CORE", eng_code="QIMMA",
                                   pcode="RBT-52", answer_list=a, stop=stop_fields()), "RBT-52")  # fmt: skip
    db.commit()
    set_now(local(2026, 10, 6, 10))
    w = _warns(db, "RBT-52")
    assert ("E20", None) in w
    inputs = {i.key: i.value for i in w[("E20", None)].inputs}
    assert inputs["stop_work_active_over_7d"] == 1


def test_AC58_viewer_and_rep_redaction(api: Api, db: Session) -> None:
    from app.services.field import execution, talks

    body = field(api.as_("sarah.mitchell"), db, "ANIA-EXP")
    assert {m["metric"] for m in body["metrics"]} >= {f"K-{n}" for n in range(110, 118)}
    r = db.scalar(select(ChecklistResponse).where(
        ChecklistResponse.critical_fail_count > 0, ChecklistResponse.owner_type == "inspection"))  # fmt: skip
    assert r is not None
    rv = execution.read_response(db, P(db, "sarah.mitchell"), r.id)
    assert all(not a.photo_ids for a in rv.answers)
    from app.models import TalkAttendance

    tid = db.scalar(select(TalkAttendance.talk_id).where(TalkAttendance.deployment_id.is_not(None)))
    assert tid is not None
    tv = talks.read_talk(db, P(db, "sarah.mitchell"), tid)
    assert all(a.name_en is None and a.worker_no is None for a in tv.attendance)
    tr = talks.read_talk(db, P(db, "ahmed.zahrani"), tid) if _rawabi_tree(db, tid) else None
    if tr is not None:
        tree = fc.tree_of(db, eng(db, "ANIA-EXP", "RAWABI").id)
        for a in tr.attendance:
            assert (a.name_en is not None) == (a.engagement is not None and a.engagement.id in tree)


def _rawabi_tree(db: Session, tid: Any) -> bool:
    t = db.get(ToolboxTalk, tid)
    return t is not None and t.host_engagement_id in fc.tree_of(db, eng(db, "ANIA-EXP",
                                                                        "RAWABI").id)  # fmt: skip


def test_AC59_offline_pack(api: Api, db: Session) -> None:
    res = api.as_("noura.qahtani").get(
        f"{API}/projects/{project(db, 'ANIA-EXP').id}/field-offline-pack"
    )
    assert res.status_code == 200, res.text
    pack = res.json()
    assert "HSE2:" not in res.text and "id_number" not in res.text
    from datetime import datetime

    gen, exp = (datetime.fromisoformat(pack[k]) for k in ("generated_at", "expires_at"))
    assert exp - gen == timedelta(hours=72)


def test_AC60_photo_retention(db: Session) -> None:
    from app.core.hse_enums import AttachmentOwner
    from app.field_jobs import field_daily

    q = (
        select(func.count())
        .select_from(Attachment)
        .where(Attachment.owner_type == AttachmentOwner.field_photo)
    )
    n0 = db.scalar(q)
    assert n0
    scores = dict(db.execute(select(ChecklistResponse.id, ChecklistResponse.score_pct)).all())
    set_now(local(2028, 10, 7, 0, 9))
    out = field_daily(db)
    assert out["photos_deleted"] > 0
    assert db.scalar(q) < n0
    assert (
        dict(db.execute(select(ChecklistResponse.id, ChecklistResponse.score_pct)).all()) == scores
    )


def test_AC61_arabic_reference(db: Session) -> None:
    from app.services.field import board, config

    ref = config.reference().model_dump()
    for group in ref.values():
        for it in group:
            assert it["label_ar"], it
    assert all(ar for _en, ar in board.LABELS.values())
    panel = board.action_panel(db, P(db, "noura.qahtani"), project(db, "ANIA-EXP").id)
    assert all(i.label_ar for i in panel.items)
