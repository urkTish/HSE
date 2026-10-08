"""5-training §9 session-side ACs not covered elsewhere: 7, 24, 25, 27, 47, 49, 52, 58, 59, 60,
62, 88, 144, 145 (catalogue modes, trainers, nominations, attempts, close, plan)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.models import Notification, TrainingNomination, TrainingSession, User
from tests.conftest import Api
from tests.train_helpers import API, P, err_code, project, provider, riyadh, session, worker

pytestmark = pytest.mark.usefixtures("train_seed", "clock")


def uid(db: Session, login: str) -> str:
    u = db.scalar(select(User).where(User.email == f"{login}@example.com"))
    assert u is not None, login
    return str(u.id)


def body(db: Session, course: str, trainer: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return {
        "course_code": course, "provider_id": str(provider(db, "INT-HSE").id),
        "delivery_mode": "classroom", "trainers": [trainer],
        "location": {"offsite_text": "Training room B"}, "language": "en",
        "interpreter_languages": [],
        "days": [{"date": "2026-10-20", "start_time": "07:00", "end_time": "16:00",
                  "break_minutes": 60}],
        "capacity": 10, **kw,
    }  # fmt: skip


def one(d: str, start: str = "07:00", end: str = "08:45", brk: int = 15) -> list[dict[str, Any]]:
    return [{"date": d, "start_time": start, "end_time": end, "break_minutes": brk}]


def salem(*roles: str) -> dict[str, Any]:
    return {"worker_id": None, "roles": list(roles or ("trainer", "assessor"))}


def create(c: TestClient, db: Session, b: dict[str, Any], pcode: str = "ANIA-EXP") -> Any:
    for t in b["trainers"]:
        if t.get("worker_id", "x") is None:
            t["worker_id"] = str(worker(db, "WKR-000018").id)
    return c.post(f"{API}/projects/{project(db, pcode).id}/training-sessions", json=b)


def ok(res: Any) -> dict[str, Any]:
    assert res.status_code in (200, 201), res.text
    return res.json()  # type: ignore[no-any-return]


def nominate(c: TestClient, sid: str, *wids: uuid.UUID) -> Any:
    return c.post(f"{API}/training-sessions/{sid}/nominations",
                  json={"worker_ids": [str(w) for w in wids]})  # fmt: skip


def test_P5AC7_practical_required_blocks_e_learning(api: Api, db: Session) -> None:
    c = api.as_("noura.qahtani")
    res = create(c, db, body(db, "CSE-ENTRANT", salem(), delivery_mode="e_learning"))
    assert res.status_code == 422 and err_code(res) == "PRACTICAL_REQUIRED", res.text
    ok(create(c, db, body(db, "CSE-ENTRANT", salem(), delivery_mode="blended")))


def test_P5AC24_trainer_own_record_expired(api: Api, db: Session) -> None:
    """Noura's WAH record runs to 2028-01-31; her authorisation to 2028-02-29."""
    c = api.as_("faisal.harbi")
    noura = {"user_id": uid(db, "noura.qahtani"), "roles": ["trainer", "assessor"]}
    late = [{"date": "2028-02-10", "start_time": "07:00", "end_time": "16:00", "break_minutes": 60}]
    res = create(c, db, body(db, "WAH", noura, days=late))
    assert res.status_code == 422 and err_code(res) == "TRAINER_NOT_TRAINED", res.text
    ok(create(c, db, body(db, "WAH", dict(noura))))


def test_P5AC25_trainer_cannot_attend_own_session(db: Session) -> None:
    from app.services.train import common, sessions

    s = session(db, "TRS-RBT-52-2026-00022")
    c = common.course_or_404(db, s.course_code)
    hamza = worker(db, "WKR-000105")
    errs = sessions._nominee_errors(db, P(db, "lina.haddad"), s, c, hamza, 0)
    assert "SOD_CONFLICT" in {e["code"] for e in errs}, errs


def test_P5AC27_authorisation_expiry_flags_session(api: Api, db: Session) -> None:
    from app.models import TrainerAuthorisation
    from app.train_jobs import training_daily

    c = api.as_("noura.qahtani")
    later = one("2026-10-22")
    s = ok(create(c, db, body(db, "HEAT-AWR", salem(), days=later)))
    res = c.post(f"{API}/training-sessions/{s['id']}/transitions", json={"action": "schedule"})
    assert res.status_code == 200 and res.json()["status"] == "scheduled", res.text
    ta = db.scalar(
        select(TrainerAuthorisation).where(
            TrainerAuthorisation.authorisation_no == "TA-ANIA-EXP-0003"
        )
    )
    assert ta is not None
    ta.valid_to = date(2026, 10, 20)
    db.commit()
    out = training_daily(db, riyadh(2026, 10, 21, 0, 6))
    assert out["trainer_authorisations_expired"] >= 1, out
    db.commit()
    sent = db.scalars(
        select(Notification).where(Notification.kind == "trainer_authorisation_lapsed_sessions")
    ).all()
    assert sent, "HSE Officers alerted"
    set_now(riyadh(2026, 10, 21, 9))
    seen = api.as_("noura.qahtani").get(f"{API}/training-sessions/{s['id']}").json()
    assert "TRAINER_NOT_AUTHORISED" in str(seen["blockers"]), seen


def test_P5AC47_P5AC75_banned_worker(api: Api, db: Session) -> None:
    from app.models import TrainingRecord

    w = worker(db, "WKR-000017")
    before = {
        r.id: (r.status, r.valid_until)
        for r in db.scalars(select(TrainingRecord).where(TrainingRecord.worker_id == w.id))
    }
    res = api.as_("faisal.harbi").post(
        f"{API}/workers/{w.id}/transitions",
        json={"to_status": "banned", "reason": "Repeated serious safety breach TEST"},
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    after = {
        r.id: (r.status, r.valid_until)
        for r in db.scalars(select(TrainingRecord).where(TrainingRecord.worker_id == w.id))
    }
    assert after == before  # AC75 (TR-15)
    c = api.as_("noura.qahtani")
    s = ok(create(c, db, body(db, "HEAT-AWR", salem(), days=one("2026-10-21"))))
    res = nominate(c, s["id"], w.id)
    assert res.status_code == 422 and "WORKER_BANNED" in res.text, res.text


def _deliver_00058(db: Session) -> TrainingSession:
    from app.train_jobs import training_minute

    s = session(db, "TRS-ANIA-EXP-2026-00058")
    training_minute(db, riyadh(2026, 10, 8, 6, 0))
    training_minute(db, riyadh(2026, 10, 8, 23, 59))
    db.commit()
    assert s.status.value == "delivered", s.status
    return s


def test_P5AC49_trainer_cannot_close(api: Api, db: Session) -> None:
    """Salem (00057) has no platform user, so the user-trainer case is shown on 00058, where
    Noura is trainer and assessor: she cannot close it; Faisal may."""
    s = _deliver_00058(db)
    set_now(riyadh(2026, 10, 9, 9))
    res = api.as_("noura.qahtani").post(f"{API}/training-sessions/{s.id}/close", json={})
    assert res.status_code == 422 and err_code(res) == "SOD_CONFLICT", res.text
    res = api.as_("faisal.harbi").post(f"{API}/training-sessions/{s.id}/close", json={})
    assert err_code(res) != "SOD_CONFLICT", res.text


def test_P5AC52_close_due_alerts_and_panel(api: Api, db: Session) -> None:
    from app.services.train import sessions as ssvc
    from app.train_jobs import training_alerts, training_minute

    s = session(db, "TRS-ANIA-EXP-2026-00057")
    training_minute(db, riyadh(2026, 10, 7, 7, 0))
    training_minute(db, riyadh(2026, 10, 7, 16, 0))
    db.commit()
    assert s.status.value == "delivered"
    assert ssvc._close_due(db, s) == date(2026, 10, 10)

    def close_due_count() -> int:
        return len(db.scalars(
            select(Notification).where(
                Notification.kind == "training_session_close_due", Notification.entity_id == s.id
            )
        ).all())  # fmt: skip

    fired = []
    for d in range(8, 12):
        before = close_due_count()
        training_alerts(db, riyadh(2026, 10, d, 7, 0))
        db.commit()
        fired.append(close_due_count() > before)
    # 10-08 (day after delivery), 10-10 (deadline) and overdue from 10-11; not 10-09
    assert fired == [True, False, True, True], fired

    def panel(d: int) -> int:
        set_now(riyadh(2026, 10, d, 9))
        res = api.as_("faisal.harbi").get(
            f"{API}/dashboard/action-panel", params={"project_id": str(s.project_id)}
        )
        assert res.status_code == 200, res.text
        items = {i["key"]: i["count"] for i in res.json()["items"]}
        return int(items.get("training_sessions_not_closed", 0))

    assert panel(10) == 0
    assert panel(11) >= 1


def test_P5AC58_effective_pass_mark(db: Session) -> None:
    from app.services.train import common

    c = common.course_or_404(db, "HEAT-AWR")
    st = common.settings(db, project(db, "ANIA-EXP").id)
    c.pass_mark_pct = 70
    st.training_pass_mark_pct = 80
    assert common.effective_pass_mark(c, st) == 80
    st.training_pass_mark_pct = 60
    assert common.effective_pass_mark(c, st) == 70


def test_P5AC59_practical_by_assessor_only(api: Api, db: Session) -> None:
    """Noura is trainer only (no assessor role); Salem assesses. Noura cannot record the
    practical result."""
    from app.models import TrainerAuthorisation
    from app.train_jobs import training_minute

    ta = db.scalar(
        select(TrainerAuthorisation).where(
            TrainerAuthorisation.authorisation_no == "TA-ANIA-EXP-0003"
        )
    )
    assert ta is not None
    ta.course_codes = [*ta.course_codes, "FIRE-WATCH"]
    db.commit()

    c = api.as_("faisal.harbi")
    noura = {"user_id": uid(db, "noura.qahtani"), "roles": ["trainer"]}
    sal = {"worker_id": str(worker(db, "WKR-000018").id), "roles": ["assessor"]}
    days = [{"date": "2026-10-07", "start_time": "07:00", "end_time": "16:00", "break_minutes": 60}]
    b = body(db, "FIRE-WATCH", noura, days=days)
    b["trainers"].append(sal)
    s = ok(create(c, db, b))
    res = nominate(c, s["id"], worker(db, "WKR-000004").id)
    assert res.status_code in (200, 201), res.text
    res = c.post(f"{API}/training-sessions/{s['id']}/transitions", json={"action": "schedule"})
    assert res.status_code == 200, res.text
    training_minute(db, riyadh(2026, 10, 7, 7, 0))
    db.commit()
    nom = c.get(f"{API}/training-sessions/{s['id']}/nominations").json()["items"][0]
    res = api.as_("noura.qahtani").put(
        f"{API}/training-sessions/{s['id']}/assessments",
        json={"entries": [{"nomination_id": nom["id"], "practical_result": "pass"}]},
    )
    assert res.status_code == 422 and err_code(res) == "ASSESSOR_REQUIRED", res.text


def test_P5AC60_attempts_exceeded_until_note(api: Api, db: Session) -> None:
    from app.core.train_enums import AttendanceResult, NominationStatus, UnderstoodLanguage

    biju = worker(db, "WKR-000017")
    for no in ("00027", "00030", "00034"):  # WAH 2026-09-15 / 16 / 17
        s = session(db, f"TRS-ANIA-EXP-2026-{no}")
        db.add(TrainingNomination(
            id=uuid.uuid4(), session_id=s.id, worker_id=biju.id, status=NominationStatus.attended,
            understood_language=UnderstoodLanguage.session_language, minutes_by_day={"1": 480},
            result=AttendanceResult.failed, attempt_no=1,
        ))  # fmt: skip
    db.commit()
    c = api.as_("faisal.harbi")
    noura = {"user_id": uid(db, "noura.qahtani"), "roles": ["trainer", "assessor"]}
    s2 = ok(create(c, db, body(db, "WAH", noura)))
    res = nominate(c, s2["id"], biju.id)
    assert res.status_code == 422 and "TRAINING_ATTEMPTS_EXCEEDED" in res.text, res.text
    pid = str(project(db, "ANIA-EXP").id)
    res = api.as_("noura.qahtani").post(
        f"{API}/workers/{biju.id}/training-retraining-notes",
        json={"project_id": pid, "course_code": "WAH",
              "note": "Re-training on harness inspection completed with the supervisor"},
    )  # fmt: skip
    assert res.status_code in (200, 201), res.text
    set_now(riyadh(2026, 10, 6, 10, 5))
    res = nominate(c, s2["id"], biju.id)
    assert res.status_code in (200, 201), res.text


def test_P5AC62_language_mismatch_warning(api: Api, db: Session) -> None:
    c = api.as_("noura.qahtani")
    days = [{"date": "2026-10-21", "start_time": "07:00", "end_time": "08:45", "break_minutes": 15}]
    s = ok(create(c, db, body(db, "HEAT-AWR", salem(), days=days, language="ar")))
    res = nominate(c, s["id"], worker(db, "WKR-000006").id)  # Suman Tamang, ne
    assert res.status_code in (200, 201), res.text
    assert "LANGUAGE_MISMATCH" in res.text, res.text


def test_P5AC88_session_from_plan(api: Api, db: Session) -> None:
    """FIRE-WATCH holders in the seed plan are all booked (Ahmed Raza on 00058), so the GP-4
    pre-fill is shown on HEAT-AWR (279 not_booked items): capped at the session capacity
    (≤ max_class_size) and every nominee passes SS-6 at Schedule."""
    c = api.as_("noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    fields = body(db, "HEAT-AWR", salem(), days=one("2026-10-21"))
    fields["trainers"][0]["worker_id"] = str(worker(db, "WKR-000018").id)
    fields.pop("course_code")
    res = c.post(f"{API}/projects/{pid}/training-sessions/from-plan",
                 json={"course_code": "HEAT-AWR", "session": fields})  # fmt: skip
    s = ok(res)
    assert s["status"] == "draft"
    noms = c.get(f"{API}/training-sessions/{s['id']}/nominations").json()["items"]
    assert len(noms) == 10, len(noms)
    res = c.post(f"{API}/training-sessions/{s['id']}/transitions", json={"action": "schedule"})
    assert res.status_code == 200, res.text


def test_P5AC144_iqama_like_text_warning(api: Api, db: Session) -> None:
    c = api.as_("noura.qahtani")
    b = body(db, "HEAT-AWR", salem(), days=one("2026-10-21"))
    b["location"] = {"offsite_text": "Room of worker 2123456789 near gate"}
    s = ok(create(c, db, b))
    assert "POSSIBLE_ID_NUMBER" in str(s), s


def test_P5AC145_suspended_contractor_rep(api: Api, db: Session) -> None:
    from app.models import Contractor

    rep = P(db, "ahmed.zahrani")
    cid = rep.user.employer_contractor_id
    k = db.get(Contractor, cid)
    assert k is not None
    k.status = "suspended"
    db.commit()
    s = session(db, "TRS-ANIA-EXP-2026-00059")
    c = api.as_("ahmed.zahrani")
    res = nominate(c, str(s.id), worker(db, "WKR-000004").id)
    assert res.status_code == 403, res.text
    res = c.get(f"{API}/training-sessions/{s.id}")
    assert res.status_code == 200, res.text
