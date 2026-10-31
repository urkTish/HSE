"""Welding: WPS ranges, WPQ continuity, NDT lots with progressive examination, repairs and the
weld NCRs (spec 8-quality §C.6, AC-Q2-27…31)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models.quality import QNcr, QRpRule
from app.services.quality.jobs import run_slot
from tests.conftest import Api, Ids
from tests.quality.q2.h2 import API, attach, err, ok


def _worker(name: str) -> str:
    from app.core.access_enums import WorkerLanguage, WorkerPersonType, WorkerStatus
    from app.models import Worker
    from sqlalchemy import func

    with get_sessionmaker()() as db:
        seq = int(db.scalar(select(func.max(Worker.seq))) or 0) + 1
        w = Worker(
            id=uuid.uuid4(), seq=seq, worker_no=f"WKR-{seq:06d}", person_type=WorkerPersonType.contractor_worker,
            full_name_en=name, full_name_ar=name, adult_attestation=True, primary_language=WorkerLanguage.en,
            status=WorkerStatus.active, search_text=name.lower(),
        )
        db.add(w)
        db.commit()
        return str(w.id)


def _setup(api: Api, ids: Ids, stamps: tuple[str, ...] = ("W-017",), test_date: str = "2026-06-01") -> dict[str, Any]:
    hatem, abdullah, rania = api.as_("hatem.shehri"), api.as_("abdullah.dossary"), api.as_("rania.zahrani")
    pid = ids.project("ANIA-EXP")
    wps = ok(hatem.post(f"{API}/projects/{pid}/quality/wps", json={
        "wps_no": "WPS-NAJD-SMAW-01", "standard": "AWS_D1_1", "processes": ["SMAW"], "joint_types": ["butt"],
        "thickness_min_mm": "5", "thickness_max_mm": "25", "positions": ["1G", "2G", "3G", "4G"], "prequalified": True,
    }), 201)
    ok(hatem.post(f"{API}/quality/wps/{wps['id']}/submit"))
    wps = ok(abdullah.post(f"{API}/quality/wps/{wps['id']}/approve", json={"decision": "approved"}))
    assert wps["status"] == "approved"
    out: dict[str, Any] = {"wps": wps}
    for st in stamps:
        w = ok(hatem.post(f"{API}/projects/{pid}/quality/welders", json={"worker_id": _worker(f"Welder {st}"), "stamp": st, "engagement_id": ids.engagement("NAJD")}), 201)
        q = ok(hatem.post(f"{API}/projects/{pid}/quality/wpqs", json={
            "welder_id": w["id"], "standard": "AWS_D1_1", "process": "SMAW", "test_date": test_date,
            "positions": ["1G", "2G", "3G"], "thickness_min_mm": "3", "thickness_max_mm": "30", "test_method": "RT",
        }), 201)
        q = ok(rania.post(f"{API}/quality/wpqs/{q['id']}/approve", json={"decision": "approved"}))
        assert q["status"] == "active"
        out[st] = {"welder": w, "wpq": q}
    return out


def _weld(c: TestClient, ids: Ids, wps: dict[str, Any], joint: str, stamp: str = "W-017", **kw: Any) -> Any:
    body = {"joint_id": joint, "wps_id": wps["id"], "position": "2G", "thickness_mm": "16", "length_mm": "300",
            "welders": [{"stamp": stamp, "root": True}], "welded_on": "2026-09-02", **kw}
    return c.post(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/welds", json=body)


def test_AC27_wps_range_and_welder_qualification(q2: None, api: Api, ids: Ids) -> None:
    s = _setup(api, ids)
    arun = api.as_("arun.pillai")
    d = err(_weld(arun, ids, s["wps"], "PB-RT-T12-J01", thickness_mm="32"), 422, "WPS_RANGE_EXCEEDED")
    assert "thickness 32" in d["message"]
    ok(api.as_("hatem.shehri").post(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/welders", json={"worker_id": _worker("New welder"), "stamp": "W-099", "engagement_id": ids.engagement("NAJD")}), 201)
    err(_weld(arun, ids, s["wps"], "PB-RT-T12-J02", stamp="W-099"), 422, "WELDER_NOT_QUALIFIED")
    w = ok(_weld(arun, ids, s["wps"], "PB-RT-T12-J03"), 201)
    assert w["status"] == "welded" and w["engagement_id"] == ids.engagement("NAJD")


def test_AC28_qx9_continuity_lapse(q2: None, api: Api, ids: Ids) -> None:
    s = _setup(api, ids, ("W-021",), test_date="2026-01-20")
    arun = api.as_("arun.pillai")
    ok(_weld(arun, ids, s["wps"], "PB-RT-T02-J01", stamp="W-021", welded_on="2026-03-28"), 201)
    q = next(x for x in ok(arun.get(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/wpqs")) if x["stamp"] == "W-021")
    assert q["last_use"] == "2026-03-28" and q["continuity_until"] == "2026-09-27"
    with get_sessionmaker()() as db:
        run_slot(db, "quality_daily", datetime(2026, 9, 27, 0, 21, tzinfo=UTC))
        db.commit()
    assert ok(arun.get(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/wpqs"))[0]["status"] == "active"
    with get_sessionmaker()() as db:
        run_slot(db, "quality_daily", datetime(2026, 9, 28, 0, 21, tzinfo=UTC))
        db.commit()
    assert ok(arun.get(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/wpqs"))[0]["status"] == "lapsed"
    err(_weld(arun, ids, s["wps"], "PB-RT-T02-J02", stamp="W-021", welded_on="2026-10-02"), 422, "WELDER_NOT_QUALIFIED")


def _lot(api: Api, ids: Ids, n: int = 40) -> tuple[dict[str, Any], dict[str, str]]:
    s = _setup(api, ids)
    arun = api.as_("arun.pillai")
    welds = {}
    for i in range(1, n + 1):
        j = f"PB-RT-T12-J{i:02d}"
        w = ok(_weld(arun, ids, s["wps"], j, lot_code="PB-ROOF-RT10", ndt_method="RT", ndt_required_pct="10"), 201)
        ok(arun.post(f"{API}/quality/welds/{w['id']}/visual", json={"result": "accept"}))
        welds[j] = w["id"]
    return s, welds


def _ndt(c: TestClient, wid: str, result: str, **kw: Any) -> dict[str, Any]:
    att = attach(c, "q_weld", wid, "rt-report.pdf")
    body = {"result": result, "report_no": f"DNDT-{wid[:6]}", "attachment_id": att, "examined_length_mm": "300", **kw}
    if result == "reject":
        body |= {"defect_type": "slag inclusion", "defect_length_mm": "12"}
    return ok(c.post(f"{API}/quality/welds/{wid}/ndt", json=body))


def _summary(c: TestClient, ids: Ids) -> dict[str, Any]:
    return ok(c.get(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/weld-lots/PB-ROOF-RT10"))


def test_AC29_qx8_lot_progressive_and_repair_rate(q2: None, api: Api, ids: Ids) -> None:
    _s, welds = _lot(api, ids)
    arun = api.as_("arun.pillai")
    s0 = _summary(arun, ids)
    assert (s0["required"], s0["examined"], s0["shortfall"]) == (4, 0, 4)
    picks = ok(arun.get(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/weld-lots/PB-ROOF-RT10/pick"))
    assert len(picks) == 4
    for j in ("PB-RT-T12-J01", "PB-RT-T12-J07", "PB-RT-T12-J15", "PB-RT-T12-J30"):
        ok(arun.post(f"{API}/quality/welds/{welds[j]}/select", json={"reason": "random"}))
    r = _ndt(arun, welds["PB-RT-T12-J07"], "reject")
    assert r["status"] == "rejected" and len(r["progressive"]) == 2
    prog = [j for j in r["progressive"]]
    for j in ("PB-RT-T12-J01", "PB-RT-T12-J15", "PB-RT-T12-J30", *prog):
        assert _ndt(arun, welds[j], "accept")["status"] == "accepted"
    s = _summary(arun, ids)
    assert (s["required"], s["examined"], s["achieved_pct"], s["progressive"], s["shortfall"]) == (4, 6, "15.0", 2, 0)
    rates = ok(arun.get(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/weld-repair-rates"))
    assert rates[0]["stamp"] == "W-017" and rates[0]["first_examinations"] == 6 and rates[0]["rate_pct"] == "16.7"
    rep = ok(arun.post(f"{API}/quality/welds/{welds['PB-RT-T12-J07']}/repair", json={}))
    assert rep["status"] == "repaired_r1" and rep["repair_count"] == 1
    assert _ndt(arun, welds["PB-RT-T12-J07"], "accept")["status"] == "accepted"
    assert ok(arun.get(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/weld-repair-rates"))[0]["rate_pct"] == "16.7"


def _weld_ncrs() -> list[QNcr]:
    with get_sessionmaker()() as db:
        return list(db.scalars(select(QNcr).where(QNcr.source_type == "weld")))


def test_AC30_progressive_reaches_100pct_and_opens_ncr(q2: None, api: Api, ids: Ids) -> None:
    _s, welds = _lot(api, ids, 20)
    arun = api.as_("arun.pillai")
    ok(arun.post(f"{API}/quality/welds/{welds['PB-RT-T12-J07']}/select", json={"reason": "random"}))
    tier1 = _ndt(arun, welds["PB-RT-T12-J07"], "reject")["progressive"]
    tier2: list[str] = []
    for j in tier1:
        tier2 += _ndt(arun, welds[j], "reject")["progressive"]
    assert len(tier1) == 2 and len(tier2) == 4
    assert _weld_ncrs() == []
    last = _ndt(arun, welds[tier2[0]], "reject")
    remaining = len(welds) - 1 - 2 - 4
    assert len(last["progressive"]) == remaining
    rows = ok(arun.get(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/welds", params={"lot_code": "PB-ROOF-RT10", "page_size": 100}))["items"]
    assert sum(1 for w in rows if w["selection_reason"] == "100pct") == remaining
    assert len(_weld_ncrs()) == 1


def test_AC31_second_repair_needs_the_sign_off_then_cut_out(q2: None, api: Api, ids: Ids) -> None:
    s = _setup(api, ids)
    arun = api.as_("arun.pillai")
    w = ok(_weld(arun, ids, s["wps"], "PB-RT-T12-J07", lot_code="PB-ROOF-RT10", ndt_method="RT", ndt_required_pct="100"), 201)
    wid = w["id"]
    ok(arun.post(f"{API}/quality/welds/{wid}/visual", json={"result": "accept"}))
    ok(arun.post(f"{API}/quality/welds/{wid}/select", json={"reason": "100pct"}))
    _ndt(arun, wid, "reject")
    ok(arun.post(f"{API}/quality/welds/{wid}/repair", json={}))
    _ndt(arun, wid, "reject")
    err(arun.post(f"{API}/quality/welds/{wid}/repair", json={}), 422, "SIGNOFF_REQUIRED")
    sig = {"decision": "approved", "comment": "Second repair approved with the revised excavation procedure."}
    err(api.as_("bilal.qureshi").post(f"{API}/quality/welds/{wid}/sign-repair2", json=sig), 422, "SOD_CONFLICT")
    with get_sessionmaker()() as db:
        for r in db.scalars(select(QRpRule).where(QRpRule.project_id == uuid.UUID(ids.project("ANIA-EXP")), QRpRule.record_type == "weld")):
            r.assignee_kind, r.assignee = "user", ids.user("hatem.shehri")  # type: ignore[assignment]
        db.commit()
    assert api.as_("bilal.qureshi").post(f"{API}/quality/welds/{wid}/sign-repair2", json=sig).status_code == 403
    ok(api.as_("hatem.shehri").post(f"{API}/quality/welds/{wid}/sign-repair2", json=sig))
    r2 = ok(arun.post(f"{API}/quality/welds/{wid}/repair", json={}))
    assert r2["status"] == "repaired_r2" and r2["repair_count"] == 2
    cut = _ndt(arun, wid, "reject")
    assert cut["status"] == "cut_out"
    assert len(_weld_ncrs()) == 1
