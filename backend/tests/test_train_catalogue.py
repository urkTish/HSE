"""5-training §9 ACs 1-19 (course catalogue, providers and accreditations)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.train_enums import TrainingRecordStatus
from app.models import AuditEntry, TrainingRecord
from tests.cert_helpers import upload_pdf
from tests.conftest import Api
from tests.train_helpers import API, err_code, project, provider, record, worker

pytestmark = pytest.mark.usefixtures("train_seed", "clock")


def new_course(code: str, **kw: Any) -> dict[str, Any]:
    return {
        "code": code, "name_en": f"Test course {code}", "name_ar": f"دورة {code}",
        "category": "awareness", "validity_months": 12, "delivery_modes": ["classroom"],
        "theory_required": True, "practical_required": False, "languages_offered": ["en"],
        "min_duration_hours": "1.00", "max_class_size": 20, "pass_mark_pct": 70,
        **kw,
    }  # fmt: skip


def test_P5AC1_code_in_other_catalogue(api: Api) -> None:
    c = api.as_("faisal.harbi")
    res = c.post(f"{API}/training-courses", json=new_course("GAS-TESTER"))
    assert res.status_code == 422 and err_code(res) == "CODE_IN_OTHER_CATALOGUE", res.text
    res = c.post(f"{API}/training-courses", json=new_course("GAS-TEST"))
    assert res.status_code == 409, res.text


def test_P5AC2_induction_owned_by_phase2(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    res = api.as_("ahmed.zahrani").post(
        f"{API}/projects/{pid}/training-records",
        json={
            "worker_id": str(worker(db, "WKR-000017").id), "project_id": str(pid),
            "course_code": "IND-GENERAL", "provider_id": str(provider(db, "INT-HSE").id),
            "certificate_no": "IND-1", "completed_on": "2026-09-01",
            "name_as_printed": "Biju Thomas", "id_on_card": {"shown": False},
        },
    )  # fmt: skip
    assert res.status_code == 422 and err_code(res) == "INDUCTION_OWNED_BY_PHASE2", res.text


def test_P5AC4_officer_cannot_edit_course(api: Api) -> None:
    res = api.as_("noura.qahtani").patch(
        f"{API}/training-courses/HEAT-AWR", json={"name_en": "Heat stress awareness (x)"}
    )
    assert res.status_code == 403, res.text


def test_P5AC5_validity_loosening_and_recompute(api: Api, db: Session) -> None:
    c = api.as_("faisal.harbi")
    res = c.patch(
        f"{API}/training-courses/WAH",
        json={"validity_months": 36, "reason": "Align with the provider card validity"},
    )
    assert res.status_code == 422 and err_code(res) == "CATALOGUE_LOOSENING", res.text
    res = c.patch(
        f"{API}/training-courses/WAH",
        json={"validity_months": 18, "reason": "Tighter refresher cycle for work at height"},
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    r = record(db, "WKR-000001", "WAH")
    # DECISIONS: Imran's WAH session 00031 moved to 2026-09-29 (spec: 2026-09-20 → 2028-03-19)
    assert r.completed_on == date(2026, 9, 29)
    assert r.valid_until == date(2028, 3, 28), r.valid_until


def test_P5AC6_accredited_provider_required(api: Api) -> None:
    res = api.as_("faisal.harbi").patch(
        f"{API}/training-courses/FIRST-AID",
        json={
            "provider_rule": {"internal_allowed": True, "contractor_delivery_allowed": False,
                              "accreditation_bodies_required": ["srca", "aha", "erc"]},
            "reason": "Allow the project HSE team to deliver first aid",
        },
    )  # fmt: skip
    assert res.status_code == 422 and err_code(res) == "ACCREDITED_PROVIDER_REQUIRED", res.text


def test_P5AC9_prerequisite_cycle(api: Api) -> None:
    c = api.as_("faisal.harbi")
    res = c.post(f"{API}/training-courses", json=new_course("TST-A"))
    assert res.status_code in (200, 201), res.text
    res = c.post(f"{API}/training-courses", json=new_course("TST-B", prerequisite_codes=["TST-A"]))
    assert res.status_code in (200, 201), res.text
    res = c.patch(
        f"{API}/training-courses/TST-A",
        json={"prerequisite_codes": ["TST-B"], "reason": "Test cycle detection between courses"},
    )
    assert res.status_code == 422 and err_code(res) == "PREREQUISITE_CYCLE", res.text


def test_P5AC10_delete_used_course(api: Api, db: Session) -> None:
    c = api.as_("faisal.harbi")
    res = c.delete(f"{API}/training-courses/HEAT-AWR")
    assert res.status_code == 409, res.text
    res = c.patch(
        f"{API}/training-courses/HEAT-AWR",
        json={"active": False, "reason": "Course replaced by the new heat programme"},
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    r = record(db, "WKR-000017", "HEAT-AWR")
    assert r.status == TrainingRecordStatus.accepted


def _new_provider(api: Api) -> str:
    res = api.as_("noura.qahtani").post(
        f"{API}/training-providers",
        json={"provider_code": "TSTPV", "legal_name_en": "Test Provider (test)",
              "legal_name_ar": "جهة اختبار", "kind": "external", "cr_number": "1010009999",
              "country": "SA", "verification_domains": ["tstpv-test.example"]},
    )  # fmt: skip
    assert res.status_code in (200, 201), res.text
    return str(res.json()["id"])


def _accreditation(c: Any, pid: str, body: str, no: str, codes: list[str]) -> str:
    att = upload_pdf(c, "training_accreditation_certificate", pid)
    res = c.post(
        f"{API}/training-providers/{pid}/accreditations",
        json={"accreditation_body": body, "accreditation_no": no, "scope_course_codes": codes,
              "valid_from": "2026-01-01", "valid_until": "2027-12-31",
              "certificate_attachment_id": att},
    )  # fmt: skip
    assert res.status_code in (200, 201), res.text
    return str(res.json()["id"])


def test_P5AC11_P5AC12_approve_and_register_check(api: Api, db: Session) -> None:
    pid = _new_provider(api)
    noura = api.as_("noura.qahtani")
    acc = _accreditation(noura, pid, "srca", "SRCA-TST-1", ["FIRST-AID"])
    res = noura.post(f"{API}/training-provider-accreditations/{acc}/register-check", json={})
    assert res.status_code == 200, res.text
    res = noura.post(f"{API}/training-providers/{pid}/transitions", json={"action": "submit"})
    assert res.status_code == 200, res.text
    res = noura.post(f"{API}/training-providers/{pid}/transitions", json={"action": "approve"})
    assert res.status_code == 403, res.text
    res = api.as_("faisal.harbi").post(
        f"{API}/training-providers/{pid}/transitions", json={"action": "approve"}
    )
    assert res.status_code == 200 and res.json()["status"] == "approved", res.text
    assert db.scalar(select(AuditEntry.id).where(AuditEntry.entity_id == pid)) is not None
    # AC12: an accreditation never checked on the register does not count
    _accreditation(noura, pid, "nebosh", "NEB-TST-1", ["NEBOSH-IGC"])
    res = noura.get(
        f"{API}/training-providers/{pid}/acceptability",
        params={"course_code": "NEBOSH-IGC", "on_date": "2026-09-01"},
    )
    assert res.status_code == 200, res.text
    item = res.json()["items"][0]
    assert item["acceptable"] is False and item["reason"] == "ACCREDITATION_INVALID", item
    res = noura.get(
        f"{API}/training-providers/{pid}/acceptability",
        params={"course_code": "FIRST-AID", "on_date": "2026-09-01"},
    )
    assert res.json()["items"][0]["acceptable"] is True, res.text


def test_P5AC13_accreditation_window(api: Api, db: Session) -> None:
    pv = provider(db, "HAYAT")
    res = api.as_("noura.qahtani").get(
        f"{API}/training-providers/{pv.id}/acceptability",
        params=[("course_code", "FIRST-AID"), ("on_date", "2027-06-30"),
                ("on_date", "2027-07-01"), ("project_id", str(project(db, "ANIA-EXP").id))],
    )  # fmt: skip
    assert res.status_code == 200, res.text
    items = {i["on_date"]: i for i in res.json()["items"]}
    assert items["2027-06-30"]["acceptable"] is True, items
    assert items["2027-07-01"]["acceptable"] is False
    assert items["2027-07-01"]["reason"] == "ACCREDITATION_INVALID"


def test_P5AC15_suspended_provider(api: Api, db: Session) -> None:
    pv = provider(db, "QUICKTRAIN")
    res = api.as_("noura.qahtani").get(
        f"{API}/training-providers/{pv.id}/acceptability",
        params=[("course_code", "FIRST-AID"), ("on_date", "2026-09-22"),
                ("on_date", "2026-09-21"), ("project_id", str(project(db, "ANIA-EXP").id))],
    )  # fmt: skip
    assert res.status_code == 200, res.text
    items = {i["on_date"]: i for i in res.json()["items"]}
    assert items["2026-09-22"]["reason"] == "PROVIDER_SUSPENDED", items
    # the seeded QUICKTRAIN accreditation was never found on the SRCA register (A.3), so 09-21
    # fails on the accreditation only, not on the suspension (TR10b)
    assert items["2026-09-21"]["reason"] != "PROVIDER_SUSPENDED", items


def _session_body(db: Session, course: str, pv: str, trainer: dict[str, Any]) -> dict[str, Any]:
    return {
        "course_code": course, "provider_id": str(provider(db, pv).id),
        "delivery_mode": "classroom", "trainers": [trainer], "location": {"offsite_text": "Room 1"},
        "language": "en", "interpreter_languages": [],
        "days": [{"date": "2026-10-20", "start_time": "07:00", "end_time": "16:00",
                  "break_minutes": 60}],
        "capacity": 10,
    }  # fmt: skip


def test_P5AC16_P5AC17_provider_rules_on_sessions(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    noura = api.as_("noura.qahtani")
    t = {"worker_id": str(worker(db, "WKR-000005").id), "roles": ["trainer", "assessor"]}
    res = noura.post(f"{API}/projects/{pid}/training-sessions",
                     json=_session_body(db, "WAH", "RAWABI-TU", t))  # fmt: skip
    assert res.status_code == 422, res.text
    assert "CONTRACTOR_DELIVERY_NOT_ALLOWED" in res.text, res.text
    t = {"external_name": "Dr. Test Trainer", "roles": ["trainer", "assessor"]}
    b = _session_body(db, "FIRST-AID", "INT-HSE", t)
    b["days"] = [{"date": f"2026-10-{d}", "start_time": "07:00", "end_time": "16:00",
                  "break_minutes": 60} for d in (20, 21)]  # fmt: skip
    res = noura.post(f"{API}/projects/{pid}/training-sessions", json=b)
    assert res.status_code == 422 and "INTERNAL_NOT_ALLOWED" in res.text, res.text


def test_P5AC18_blacklist_all_records(api: Api, db: Session) -> None:
    from app.core.clock import set_now
    from tests.train_helpers import riyadh

    pv = provider(db, "OTCME")
    recs = db.scalars(
        select(TrainingRecord).where(
            TrainingRecord.provider_id == pv.id,
            TrainingRecord.status == TrainingRecordStatus.accepted,
        )
    ).all()
    assert recs
    res = api.as_("faisal.harbi").post(
        f"{API}/training-providers/{pv.id}/transitions",
        json={"action": "blacklist", "blacklist_scope": "all_records",
              "reason": "Cards found to be issued without attendance (test)"},
    )  # fmt: skip
    assert res.status_code == 200, res.text
    set_now(riyadh(2026, 10, 6, 10, 2))
    db.expire_all()
    for r in recs:
        db.refresh(r)
        assert r.status == TrainingRecordStatus.revoked, r.record_no
