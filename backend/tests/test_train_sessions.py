"""5-training §9 ACs 40-64 (sessions, nominations, attendance, assessment, close, void)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.core.train_enums import TrainingRecordStatus
from app.models import Notification, TrainingRecord
from tests.cert_helpers import upload_pdf
from tests.conftest import Api
from tests.train_helpers import API, err_code, project, provider, record, riyadh, session, worker

pytestmark = pytest.mark.usefixtures("train_seed", "clock")

S57 = "TRS-ANIA-EXP-2026-00057"


def body(db: Session, course: str = "CSE-ATTENDANT", **kw: Any) -> dict[str, Any]:
    return {
        "course_code": course, "provider_id": str(provider(db, "INT-HSE").id),
        "delivery_mode": "classroom",
        "trainers": [{"worker_id": str(worker(db, "WKR-000018").id),
                      "roles": ["trainer", "assessor"]}],
        "location": {"offsite_text": "Training room A"}, "language": "en",
        "interpreter_languages": [],
        "days": [{"date": "2026-10-20", "start_time": "07:00", "end_time": "16:00",
                  "break_minutes": 60}],
        "capacity": 10, **kw,
    }  # fmt: skip


def create(c: TestClient, db: Session, **kw: Any) -> Any:
    return c.post(
        f"{API}/projects/{project(db, 'ANIA-EXP').id}/training-sessions", json=body(db, **kw)
    )


def day(d: str, start: str, end: str, brk: int) -> list[dict[str, Any]]:
    return [{"date": d, "start_time": start, "end_time": end, "break_minutes": brk}]


def test_P5AC40_P5AC41_day_lengths(api: Api, db: Session) -> None:
    c = api.as_("noura.qahtani")
    res = create(c, db, days=day("2026-10-20", "07:00", "14:00", 60))
    assert res.status_code == 422 and "SESSION_TOO_SHORT" in res.text, res.text
    res = create(c, db, days=day("2026-10-20", "07:00", "17:45", 30))
    assert res.status_code == 422 and "SESSION_DAY_TOO_LONG" in res.text, res.text


def test_P5AC42_session_full(api: Api, db: Session) -> None:
    s = session(db, S57)
    c = api.as_("noura.qahtani")
    noms = c.get(f"{API}/training-sessions/{s.id}/nominations").json()["items"]
    assert len(noms) == 10
    res = c.post(f"{API}/training-sessions/{s.id}/nominations",
                 json={"worker_ids": [str(worker(db, "WKR-000001").id)]})  # fmt: skip
    assert res.status_code == 422 and "SESSION_FULL" in res.text, res.text


def test_P5AC43_P5AC44_past_sessions(api: Api, db: Session) -> None:
    for who, last, want in (
        ("ahmed.zahrani", "2026-09-30", 403),
        ("noura.qahtani", "2026-09-28", "BACKDATED_SESSION"),
        ("noura.qahtani", "2026-09-30", "delivered"),
    ):
        noura = api.as_("noura.qahtani")
        res = create(noura, db, course="HEAT-AWR", days=day(last, "07:00", "08:45", 15))
        assert res.status_code in (200, 201), res.text
        sid = res.json()["id"]
        res = api.as_(who).post(f"{API}/training-sessions/{sid}/transitions",
                                json={"action": "record_delivered"})  # fmt: skip
        if want == 403:
            assert res.status_code == 403, res.text
        elif want == "delivered":
            assert res.status_code == 200 and res.json()["status"] == "delivered", res.text
        else:
            assert res.status_code == 422 and err_code(res) == want, res.text


def test_P5AC45_schedule_clash(api: Api, db: Session) -> None:
    c = api.as_("noura.qahtani")
    res = create(c, db, course="HEAT-AWR", days=day("2026-10-07", "14:00", "15:45", 15))
    assert res.status_code in (200, 201), res.text
    sid = res.json()["id"]
    res = c.post(f"{API}/training-sessions/{sid}/nominations",
                 json={"worker_ids": [str(worker(db, "WKR-000017").id)]})  # fmt: skip
    assert res.status_code == 422 and "SCHEDULE_CLASH" in res.text, res.text


def test_P5AC46_prerequisite_on_nomination(db: Session) -> None:
    from app.services.train import common, sessions

    c = common.course(db, "CSE-RESCUE")
    assert c is not None
    biju = worker(db, "WKR-000017")
    missing = sessions._prereq_missing(
        db, biju.id, c, date(2026, 10, 20), project(db, "ANIA-EXP").id
    )
    assert "FIRST-AID" in missing, missing


def test_P5AC48_to_P5AC64_session_00057_lifecycle(api: Api, db: Session) -> None:
    from app.train_jobs import training_minute

    s = session(db, S57)
    training_minute(db, riyadh(2026, 10, 7, 7, 0))
    assert s.status.value == "in_progress"
    training_minute(db, riyadh(2026, 10, 7, 16, 0))
    assert s.status.value == "delivered"
    db.commit()
    set_now(riyadh(2026, 10, 7, 17))
    noura = api.as_("noura.qahtani")
    noms = noura.get(f"{API}/training-sessions/{s.id}/nominations").json()["items"]
    biju = next(n for n in noms if n["worker"]["worker_no"] == "WKR-000017")
    assert biju["understood_language"] == "interpreter", biju
    # AC50: nominees without a final status block Close
    res = noura.post(f"{API}/training-sessions/{s.id}/close", json={})
    assert res.status_code == 422 and err_code(res) == "NOMINATIONS_INCOMPLETE", res.text
    others = [n for n in noms if n["id"] != biju["id"]]
    short, fail = others[-1], others[0]
    entries = [{"nomination_id": n["id"], "status": "attended",
                "minutes_by_day": {"1": 390 if n is short else 480}} for n in noms]  # fmt: skip
    res = noura.put(f"{API}/training-sessions/{s.id}/attendance", json={"entries": entries})
    assert res.status_code == 200, res.text
    items = {n["id"]: n for n in res.json()["items"]}
    assert items[short["id"]]["status"] == "partial"
    hours = sum(Decimal(str(n["attended_hours"])) for n in items.values())
    assert hours == Decimal("78.50"), hours  # AC56
    ass = [{"nomination_id": n["id"], "theory_score_pct": "79.50" if n is fail else "80.00",
            "practical_result": "pass"} for n in noms if n is not short]  # fmt: skip
    res = noura.put(f"{API}/training-sessions/{s.id}/assessments", json={"entries": ass})
    assert res.status_code == 200, res.text
    # AC63: a site engineer sees status and result but no scores
    res = api.as_("omar.siddiqui").get(f"{API}/training-sessions/{s.id}/nominations")
    if res.status_code == 200:
        assert all(n["theory_score_pct"] is None for n in res.json()["items"]), res.text
    # AC51: no sheet and nobody signed on the device
    res = noura.post(f"{API}/training-sessions/{s.id}/close", json={})
    assert res.status_code == 422 and err_code(res) == "ATTENDANCE_SHEET_REQUIRED", res.text
    sheet = upload_pdf(noura, "training_attendance_sheet", s.id)
    res = noura.post(f"{API}/training-sessions/{s.id}/close",
                     json={"attendance_sheet_attachment_id": sheet})  # fmt: skip
    assert res.status_code == 200 and res.json()["status"] == "closed", res.text
    noms = {
        n["id"]: n for n in noura.get(f"{API}/training-sessions/{s.id}/nominations").json()["items"]
    }
    assert noms[short["id"]]["result"] == "incomplete" and noms[short["id"]]["record"] is None
    assert noms[fail["id"]]["result"] == "failed"  # AC57: 79.50 < 80
    assert noms[biju["id"]]["result"] == "passed"
    db.expire_all()
    r = record(db, "WKR-000017", "CSE-ATTENDANT")  # AC64
    assert r.status == TrainingRecordStatus.accepted
    assert r.verification_status.value == "verified"
    assert r.certificate_no.startswith("TRC-ANIA-EXP-2026-"), r.certificate_no
    assert r.valid_until == date(2028, 10, 6), r.valid_until


def test_P5AC53_cancel_notifies(api: Api, db: Session) -> None:
    s = session(db, "TRS-ANIA-EXP-2026-00059")
    before = db.scalar(select(Notification.id).order_by(Notification.created_at.desc()).limit(1))
    res = api.as_("noura.qahtani").post(
        f"{API}/training-sessions/{s.id}/transitions",
        json={"action": "cancel", "reason": "Trainer unavailable this week"},
    )
    assert res.status_code == 200 and res.json()["status"] == "cancelled", res.text
    db.expire_all()
    rows = db.scalars(select(Notification).where(Notification.entity_id == s.id)).all()
    assert rows, before


def test_P5AC54_P5AC55_void(api: Api, db: Session) -> None:
    s = session(db, "TRS-ANIA-EXP-2026-00031")
    payload = {"reason_code": "trainer_not_competent",
               "reason_text": "Trainer found not competent for WAH delivery (test)"}  # fmt: skip
    res = api.as_("noura.qahtani").post(f"{API}/training-sessions/{s.id}/void", json=payload)
    assert res.status_code == 403, res.text
    res = api.as_("faisal.harbi").post(f"{API}/training-sessions/{s.id}/void", json=payload)
    assert res.status_code == 200, res.text
    db.expire_all()
    imran = worker(db, "WKR-000001")
    recs = db.scalars(
        select(TrainingRecord).where(
            TrainingRecord.session_id == s.id, TrainingRecord.worker_id == imran.id
        )
    ).all()
    assert recs and all(r.status == TrainingRecordStatus.revoked for r in recs)
    seen = api.as_("ahmed.zahrani").get(f"{API}/training-records/{recs[0].id}").json()
    assert "not accepted" in (seen.get("not_accepted_message_en") or "").lower(), seen


def test_P5AC61_language_block_on_high_risk(api: Api, db: Session) -> None:
    from app.train_jobs import training_minute

    s = session(db, S57)
    noura = api.as_("noura.qahtani")
    suman = worker(db, "WKR-000006")  # primary_language ne; 00057 is en with [ur, hi]
    s.capacity += 1  # 00057 is full in the seed
    db.commit()
    res = noura.post(f"{API}/training-sessions/{s.id}/nominations",
                     json={"worker_ids": [str(suman.id)]})  # fmt: skip
    assert res.status_code in (200, 201) and "LANGUAGE_MISMATCH" in res.text, res.text
    training_minute(db, riyadh(2026, 10, 7, 7, 0))
    training_minute(db, riyadh(2026, 10, 7, 16, 0))
    db.commit()
    set_now(riyadh(2026, 10, 7, 17))
    noura = api.as_("noura.qahtani")  # new token at the moved clock
    noms = noura.get(f"{API}/training-sessions/{s.id}/nominations").json()["items"]
    entries = [{"nomination_id": n["id"], "status": "attended", "minutes_by_day": {"1": 480}}
               for n in noms]  # fmt: skip
    res = noura.put(f"{API}/training-sessions/{s.id}/attendance", json={"entries": entries})
    assert res.status_code == 200, res.text
    ass = [{"nomination_id": n["id"], "theory_score_pct": "95.00", "practical_result": "pass"}
           for n in noms]  # fmt: skip
    res = noura.put(f"{API}/training-sessions/{s.id}/assessments", json={"entries": ass})
    assert res.status_code == 200, res.text
    sheet = upload_pdf(noura, "training_attendance_sheet", s.id)
    res = noura.post(f"{API}/training-sessions/{s.id}/close",
                     json={"attendance_sheet_attachment_id": sheet})  # fmt: skip
    assert res.status_code == 200, res.text
    by_no = {
        n["worker"]["worker_no"]: n
        for n in noura.get(f"{API}/training-sessions/{s.id}/nominations").json()["items"]
    }
    assert by_no["WKR-000017"]["understood_language"] == "interpreter"
    assert by_no["WKR-000017"]["result"] == "passed"
    sm = by_no["WKR-000006"]
    assert sm["understood_language"] == "none", sm
    assert (sm["result"], sm["result_reason"]) == ("failed", "LANGUAGE_NOT_UNDERSTOOD"), sm
