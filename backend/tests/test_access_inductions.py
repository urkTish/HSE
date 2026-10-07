"""Spec 2-access-permits §9 AC10-AC18 (site induction) and X1."""

import base64
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import access_jobs
from app.core.access_enums import DeploymentStatus, InductionStatus, QrTokenStatus
from app.core.clock import frozen
from app.models import Deployment, HseSettings, InductionCourse, QrToken
from app.services.access import common
from tests.access_helpers import API, deployment, induction, project_id, riyadh, worker
from tests.conftest import Api, Ids

pytestmark = pytest.mark.usefixtures("access_seed", "noon")

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32).decode()


def course_id(db: Session, project: str, code: str) -> str:
    cid = db.scalar(
        select(InductionCourse.id).where(
            InductionCourse.project_id == project_id(db, project), InductionCourse.code == code
        )
    )
    return str(cid)


def record(c: TestClient, db: Session, project: str, worker_id: Any, code: str, **over: Any) -> Any:
    body: dict[str, Any] = {
        "worker_id": str(worker_id),
        "course_id": course_id(db, project, code),
        "delivered_at": "2026-10-06T06:00:00Z",
        "delivery_language": "ar",
        "interpreter_used": False,
        "duration_minutes": 95,
        "privacy_notice_version": "WPN-1.0",
        "signature_png_base64": PNG,
    }
    body.update(over)
    return c.post(f"{API}/projects/{project_id(db, project)}/inductions", json=body)


def new_rbt_worker(api: Api, ids: Ids, number: str, name: str = "Retest Person") -> str:
    res = api.as_("faisal.harbi").post(
        f"{API}/workers",
        json={
            "person_type": "contractor_worker",
            "full_name_en": name,
            "full_name_ar": "شخص",
            "id_type": "iqama",
            "id_number": number,
            "id_expiry_date": "2028-01-01",
            "nationality": "SA",
            "adult_attestation": True,
            "primary_language": "ar",
        },
    )
    assert res.status_code == 201, res.text
    wid = res.json()["id"]
    res = api.as_("faisal.harbi").post(
        f"{API}/projects/{ids.project('RBT-52')}/deployments",
        json={
            "worker_id": wid,
            "engagement_id": ids.engagement("QIMMA"),
            "trade": "supervisor",
            "site_ids": [ids.site("S-TWR")],
            "mobilised_on": "2026-10-06",
        },
    )
    assert res.status_code == 201, res.text
    return str(wid)


def test_P2AC10_X1_validity_dates() -> None:
    assert common.validity_until(date(2026, 1, 12), 12) == date(2027, 1, 11)
    assert common.validity_until(date(2025, 10, 14), 12) == date(2026, 10, 13)
    assert common.validity_until(date(2026, 8, 31), 6) == date(2027, 2, 27)
    assert common.validity_until(date(2026, 10, 6), None, 1) == date(2026, 10, 6)


def test_P2AC10_seeded_records_match_X1(db: Session) -> None:
    assert induction(db, "Rajesh Nair", "GEN", InductionStatus.valid).valid_until == date(
        2027, 1, 11
    )
    assert induction(db, "Abdul Karim Mia", "AIR").valid_until == date(2026, 10, 13)


def test_P2AC11_retest_fails_then_passes_and_mobilises(api: Api, ids: Ids, db: Session) -> None:
    wid = new_rbt_worker(api, ids, "2000009801")
    n = api.as_("yousef.ghamdi")
    res = record(
        n, db, "RBT-52", wid, "GEN", test_score_pct="65", delivered_at="2026-10-05T06:00:00Z"
    )
    assert res.status_code == 201, res.text
    assert res.json()["result"] == "failed" and res.json()["status"] == "failed"
    dep = db.scalar(select(Deployment).where(Deployment.worker_id == wid))
    assert dep is not None and dep.status == DeploymentStatus.pending_induction
    res = record(n, db, "RBT-52", wid, "GEN", test_score_pct="85")
    assert res.status_code == 201, res.text
    r = res.json()
    assert r["status"] == "valid" and r["attempt_no"] == 2
    assert r["valid_until"] == "2027-10-05"
    db.expire_all()
    dep = db.scalar(select(Deployment).where(Deployment.worker_id == wid))
    assert dep is not None and dep.status == DeploymentStatus.mobilised
    tok = db.scalar(
        select(QrToken).where(QrToken.subject_id == dep.id, QrToken.status == QrTokenStatus.active)
    )
    assert tok is not None


def test_P2AC11_seeded_hamza(db: Session) -> None:
    w = worker(db, "Hamza Al-Shehri")
    recs = sorted(
        (r for r in db.scalars(select(InductionCourse).where(InductionCourse.code == "GEN"))),
        key=lambda c: c.code,
    )
    assert recs
    last = induction(db, "Hamza Al-Shehri", "GEN")
    assert last.valid_until == date(2027, 9, 2) and last.attempt_no == 2
    assert deployment(db, w.full_name_en).status == DeploymentStatus.mobilised


def test_P2AC12_fourth_attempt_blocked(api: Api, ids: Ids, db: Session) -> None:
    wid = new_rbt_worker(api, ids, "2000009802")
    n = api.as_("yousef.ghamdi")
    for day in (1, 2, 3):
        res = record(n, db, "RBT-52", wid, "GEN", test_score_pct="50",
                     delivered_at=f"2026-10-0{day}T06:00:00Z")  # fmt: skip
        assert res.status_code == 201, res.text
    res = record(n, db, "RBT-52", wid, "GEN", test_score_pct="95")
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "INDUCTION_ATTEMPTS_EXCEEDED"


def test_P2AC13_rep_cannot_deliver_air(api: Api, db: Session) -> None:
    w = worker(db, "Saad Al-Dosari")
    res = record(api.as_("ahmed.zahrani"), db, "ANIA-EXP", w.id, "AIR", test_score_pct="90",
                 duration_minutes=65)  # fmt: skip
    assert res.status_code == 403, res.text
    assert res.json()["detail"]["code"] == "DELIVERER_NOT_ALLOWED"


def test_P2AC14_air_needs_valid_gen(api: Api, db: Session) -> None:
    w = worker(db, "Suman Tamang")  # GEN expired 2026-09-30
    res = record(api.as_("noura.qahtani"), db, "ANIA-EXP", w.id, "AIR", test_score_pct="90",
                 duration_minutes=65)  # fmt: skip
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "INDUCTION_PREREQUISITE"


def test_P2AC15_language_mismatch_warning_and_action_panel(api: Api, ids: Ids, db: Session) -> None:
    w = worker(db, "Abdul Karim Mia")
    n = api.as_("noura.qahtani")
    res = record(n, db, "ANIA-EXP", w.id, "GEN", test_score_pct="90", delivery_language="en")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["language_mismatch"] is True
    assert "LANGUAGE_MISMATCH" in [x["code"] for x in body["warnings"]]
    panel = n.get(f"{API}/dashboard/action-panel", params={"project_id": ids.project("ANIA-EXP")})
    assert panel.status_code == 200, panel.text
    items = {i["key"]: i for i in panel.json()["items"]}
    assert items["induction_language_mismatch"]["count"] >= 1


def test_P2AC16_expiry_job_is_idempotent(db: Session) -> None:
    r = induction(db, "Suman Tamang", "GEN")
    db.execute(update(type(r)).where(type(r).id == r.id).values(status=InductionStatus.valid))
    db.commit()
    with frozen(riyadh(2026, 10, 1, 0, 5)):
        first = access_jobs.access_daily(db)
        db.commit()
        second = access_jobs.access_daily(db)
        db.commit()
    db.expire_all()
    assert induction(db, "Suman Tamang", "GEN").status == InductionStatus.expired
    assert first["inductions_expired"] >= 1
    assert second["inductions_expired"] == 0
    assert second["status_notices"] == 0


def test_P2AC17_new_version_sets_reinduction_due(api: Api, db: Session) -> None:
    cid = course_id(db, "ANIA-EXP", "AIR")
    res = api.as_("noura.qahtani").post(
        f"{API}/induction-courses/{cid}/versions",
        json={"version": "3.0", "requires_reinduction": True, "published_on": "2026-10-06"},
    )
    assert res.status_code in (200, 201), res.text
    db.expire_all()
    recs = list(
        db.scalars(
            select(type(induction(db, "Rajesh Nair", "AIR"))).where(
                type(induction(db, "Rajesh Nair", "AIR")).course_id == cid,
                type(induction(db, "Rajesh Nair", "AIR")).status == InductionStatus.valid,
            )
        )
    )
    assert len(recs) > 100
    assert {r.reinduction_due_on for r in recs} == {date(2026, 11, 5)}


def k38(c: TestClient, ids: Ids) -> Any:
    res = c.get(
        f"{API}/kpi/metrics/K-38",
        params={"project_id": ids.project("ANIA-EXP"), "period": "month", "anchor": "2026-09-01",
                "as_of": "2026-09-30"},
    )  # fmt: skip
    assert res.status_code == 200, res.text
    return res.json()


def test_P2AC18_k38_source_switch(api: Api, ids: Ids, db: Session) -> None:
    from app.models import InductionRecord, WorkforceReturn

    pid = project_id(db, "ANIA-EXP")
    passed_gen = len(
        db.scalars(
            select(InductionRecord.id)
            .join(InductionCourse, InductionCourse.id == InductionRecord.course_id)
            .where(
                InductionRecord.project_id == pid,
                InductionCourse.code == "GEN",
                InductionRecord.result == "passed",
                InductionRecord.delivered_on.between(date(2026, 9, 1), date(2026, 9, 30)),
            )
        ).all()
    )
    returns = sum(
        db.scalars(
            select(WorkforceReturn.inductions).where(
                WorkforceReturn.project_id == pid,
                WorkforceReturn.work_date.between(date(2026, 9, 1), date(2026, 9, 30)),
            )
        )
    )
    assert passed_gen == returns > 0
    c = api.as_("faisal.harbi")
    v = k38(c, ids)
    value = v["kpi"]["value"]
    assert int(float(value)) == passed_gen
    assert "reconcil" not in str(v).lower()
    db.execute(
        update(HseSettings)
        .where(HseSettings.project_id == pid)
        .values(induction_register_from=None)
    )
    db.commit()
    v2 = k38(c, ids)
    value2 = v2["kpi"]["value"]
    assert int(float(value2)) == returns
