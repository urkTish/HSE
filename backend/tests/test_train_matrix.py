"""5-training §9 ACs 20-39 (trainer authorisations, matrix, profiles, exemptions, due dates)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus
from app.core.hse_enums import Trade
from app.models import Contractor, Deployment, ProjectEngagement, User
from tests.conftest import Api
from tests.train_helpers import API, err_code, project, provider, worker

pytestmark = pytest.mark.usefixtures("train_seed", "clock")


def uid(db: Session, key: str) -> str:
    u = db.scalar(select(User).where(User.email == f"{key}@example.com"))
    assert u is not None, key
    return str(u.id)


def ta_body(db: Session, **kw: Any) -> dict[str, Any]:
    return {
        "provider_id": str(provider(db, "INT-HSE").id), "course_codes": ["HEAT-AWR"],
        "roles": ["trainer"], "basis": "Train-the-trainer course TTT-TEST-0099; 5 years",
        "evidence_attachment_ids": [], "valid_from": "2026-10-06", "valid_to": "2027-10-05",
        **kw,
    }  # fmt: skip


def test_P5AC20_self_authorisation(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    res = api.as_("noura.qahtani").post(
        f"{API}/projects/{pid}/trainer-authorisations",
        json=ta_body(db, trainer_user_id=uid(db, "noura.qahtani")),
    )
    assert res.status_code == 422 and err_code(res) == "SOD_CONFLICT", res.text


def test_P5AC21_evidence_required(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    res = api.as_("noura.qahtani").post(
        f"{API}/projects/{pid}/trainer-authorisations",
        json=ta_body(db, trainer_user_id=uid(db, "lina.haddad"), course_codes=["CSE-ENTRANT"]),
    )
    assert res.status_code == 422 and err_code(res) == "TRAINER_EVIDENCE_REQUIRED", res.text


def test_P5AC22_max_24_months(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    c = api.as_("noura.qahtani")
    body = ta_body(db, trainer_user_id=uid(db, "lina.haddad"), valid_to="2028-10-06")
    res = c.post(f"{API}/projects/{pid}/trainer-authorisations", json=body)
    assert res.status_code == 422 and err_code(res) == "AUTHORISATION_TOO_LONG", res.text
    body["valid_to"] = "2028-10-05"
    res = c.post(f"{API}/projects/{pid}/trainer-authorisations", json=body)
    assert res.status_code in (200, 201), res.text


def session_body(db: Session, course: str, pv: str, trainer: dict[str, Any], **kw: Any) -> Any:
    return {
        "course_code": course, "provider_id": str(provider(db, pv).id),
        "delivery_mode": "classroom", "trainers": [trainer], "location": {"offsite_text": "Room 1"},
        "language": "en", "interpreter_languages": [],
        "days": [{"date": "2026-10-20", "start_time": "07:00", "end_time": "16:00",
                  "break_minutes": 60}],
        "capacity": 10, **kw,
    }  # fmt: skip


def test_P5AC23_trainer_not_authorised(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    t = {"worker_id": str(worker(db, "WKR-000018").id), "roles": ["trainer", "assessor"]}
    res = api.as_("noura.qahtani").post(
        f"{API}/projects/{pid}/training-sessions", json=session_body(db, "WAH", "INT-HSE", t)
    )
    assert res.status_code == 422 and "TRAINER_NOT_AUTHORISED" in res.text, res.text


def test_P5AC26_contractor_rep_trainer(api: Api, db: Session) -> None:
    pid = project(db, "RBT-52").id
    lina = api.as_("lina.haddad")
    body = ta_body(db, trainer_user_id=uid(db, "yousef.ghamdi"),
                   provider_id=str(provider(db, "QIMMA-TU").id), course_codes=["WAH"])  # fmt: skip
    res = lina.post(f"{API}/projects/{pid}/trainer-authorisations", json=body)
    assert res.status_code == 422 and err_code(res) == "TRAINER_NOT_AUTHORISED", res.text
    body["course_codes"] = ["HEAT-AWR"]
    res = lina.post(f"{API}/projects/{pid}/trainer-authorisations", json=body)
    assert res.status_code in (200, 201), res.text


def matrix(c: TestClient, db: Session, pcode: str = "ANIA-EXP", **q: Any) -> list[dict[str, Any]]:
    res = c.get(f"{API}/projects/{project(db, pcode).id}/training-matrix", params=q)
    assert res.status_code == 200, res.text
    return res.json()["lines"]  # type: ignore[no-any-return]


def line(lines: list[dict[str, Any]], code: str, kind: str | None = None) -> dict[str, Any]:
    for ln in lines:
        if ln["requirement"]["course_code"] != code:
            continue
        if kind is None or ln["applies_to_kind"] == kind:
            return ln
    raise AssertionError(code)


def test_P5AC28_wah_line_counts(api: Api, db: Session) -> None:
    lines = matrix(api.as_("faisal.harbi"), db, as_of="2026-09-30", include_counts="true")
    wah = line(lines, "WAH", "trade")
    assert sorted(wah["applies_to_values"]) == ["rigger", "scaffolder", "steel_erector"]
    from app.services.train import requirements as reqs

    pe = reqs.evaluate_project(db, project(db, "ANIA-EXP").id, date(2026, 9, 30))
    rows = [r for r in pe.reqs if r.counted and r.key == "WAH"]
    assert len(rows) == 519, len(rows)
    gaps = [r for r in rows if r.state.value == "gap"]
    assert len(gaps) == 12, len(gaps)


def test_P5AC29_zone_line_derived(api: Api, db: Session) -> None:
    c = api.as_("noura.qahtani")
    lines = matrix(c, db)
    z = [ln for ln in lines if ln["applies_to_kind"] == "zone" and ln["source"] != "manual"]
    assert z, [ln["line_no"] for ln in lines]
    res = c.patch(f"{API}/training-matrix-lines/{z[0]['id']}", json={"due_within_days": 0})
    assert res.status_code == 422 and err_code(res) == "LINE_DERIVED_FROM_HOOK", res.text


def test_P5AC30_crew_role_not_counted(api: Api, db: Session) -> None:
    lines = matrix(api.as_("noura.qahtani"), db)
    crew = [ln for ln in lines if ln["applies_to_kind"] in ("crew_role", "appointment_function")]
    assert crew
    assert all(ln["kpi_counted"] is False for ln in crew)


def new_line(c: TestClient, db: Session, **kw: Any) -> Any:
    body = {"applies_to_kind": "trade", "applies_to_values": ["painter"],
            "requirement": {"course_code": "WAH"}, "level": "mandatory", "due_within_days": 0,
            **kw}  # fmt: skip
    return c.post(f"{API}/projects/{project(db, 'ANIA-EXP').id}/training-matrix/lines", json=body)


def test_P5AC31_due_days_not_allowed(api: Api, db: Session) -> None:
    res = new_line(api.as_("noura.qahtani"), db, due_within_days=30)
    assert res.status_code == 422 and err_code(res) == "DUE_DAYS_NOT_ALLOWED", res.text


def test_P5AC32_any_of(api: Api, db: Session) -> None:
    c = api.as_("noura.qahtani")
    res = new_line(c, db, applies_to_values=["engineer"],
                   requirement={"any_of": ["NEBOSH-IGC", "NEBOSH-ICC", "IOSH-MS", "OSHA-30"]},
                   due_within_days=90)  # fmt: skip
    assert res.status_code in (200, 201), res.text
    res = new_line(c, db, requirement={"any_of": ["WAH", "SCAFF-AWR"]})
    assert res.status_code == 422 and err_code(res) == "ANY_OF_NOT_ALLOWED", res.text


def test_P5AC33_remove_mandatory_line(api: Api, db: Session) -> None:
    heat = line(matrix(api.as_("noura.qahtani"), db), "HEAT-AWR", "all_workers")
    res = api.as_("noura.qahtani").post(
        f"{API}/training-matrix-lines/{heat['id']}/remove", json={"reason": "not needed"}
    )
    assert res.status_code == 422 and err_code(res) == "MATRIX_LOOSENING", res.text
    res = api.as_("faisal.harbi").post(
        f"{API}/training-matrix-lines/{heat['id']}/remove",
        json={"reason": "Heat programme moved to the induction (test)"},
    )
    assert res.status_code == 200, res.text
    res = api.as_("faisal.harbi").get(f"{API}/training-matrix-lines/{heat['id']}/versions")
    assert res.status_code == 200 and res.json()["versions"], res.text
    assert res.json()["versions"][0]["effective_to"] == "2026-10-05", res.text


def dep_of(db: Session, contractor: str, pcode: str = "ANIA-EXP") -> Deployment:
    d = db.scalars(
        select(Deployment)
        .join(ProjectEngagement, ProjectEngagement.id == Deployment.engagement_id)
        .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
        .where(
            Contractor.short_code == contractor,
            Deployment.project_id == project(db, pcode).id,
            Deployment.status == DeploymentStatus.mobilised,
        )
        .order_by(Deployment.mobilised_on)
    ).first()
    assert d is not None, contractor
    return d


def test_P5AC35_profile_scope(api: Api, db: Session) -> None:
    ahmed = api.as_("ahmed.zahrani")
    q = dep_of(db, "QIMMA", "RBT-52")
    res = ahmed.patch(f"{API}/deployments/{q.id}/training-profile",
                      json={"matrix_roles": ["first_aider"]})  # fmt: skip
    assert res.status_code in (403, 404), res.text
    n = dep_of(db, "NAJD")
    res = ahmed.patch(f"{API}/deployments/{n.id}/training-profile",
                      json={"matrix_roles": ["first_aider"]})  # fmt: skip
    assert res.status_code == 200, res.text
    hist = [h for h in res.json()["history"] if h["field"] == "matrix_roles"]
    assert hist[-1]["from_date"] == "2026-10-06" or hist[0]["from_date"] == "2026-10-06", hist


def test_P5AC36_exemptions(api: Api, db: Session) -> None:
    c = api.as_("noura.qahtani")
    lines = matrix(c, db)
    pid = project(db, "ANIA-EXP").id
    d = db.scalars(
        select(Deployment).where(
            Deployment.project_id == pid,
            Deployment.trade == Trade.labourer,
            Deployment.status == DeploymentStatus.mobilised,
        ).order_by(Deployment.mobilised_on)
    ).first()  # fmt: skip
    assert d is not None
    reason = "Works only in the office compound, never near any scaffold (test)"
    for code, kind in (("IND-GENERAL", "all_workers"), ("WAH", "trade")):
        ln = line(lines, code, kind)
        res = c.post(f"{API}/projects/{pid}/training-exemptions",
                     json={"deployment_id": str(d.id), "line_id": ln["id"], "reason": reason,
                           "valid_until": "2026-12-31"})  # fmt: skip
        assert res.status_code == 422 and err_code(res) == "EXEMPTION_NOT_ALLOWED", res.text
    ln = line(lines, "SCAFF-AWR", "trade")
    res = c.post(f"{API}/projects/{pid}/training-exemptions",
                 json={"deployment_id": str(d.id), "line_id": ln["id"], "reason": reason,
                       "valid_until": "2026-12-31"})  # fmt: skip
    assert res.status_code in (200, 201), res.text
    res = c.get(f"{API}/deployments/{d.id}/training-requirements")
    st = [r for r in res.json()["requirements"] if r["requirement"]["course_code"] == "SCAFF-AWR"]
    assert st and st[0]["state"] == "exempt" and st[0]["counted"] is False, st


def test_P5AC37_zone_not_in_sites(api: Api, db: Session) -> None:
    from app.models import Zone

    n = dep_of(db, "NAJD")
    z = db.scalars(select(Zone).where(Zone.site_id.not_in(n.site_ids))).first()
    assert z is not None
    res = api.as_("noura.qahtani").patch(
        f"{API}/deployments/{n.id}/training-profile", json={"work_zone_ids": [str(z.id)]}
    )
    assert res.status_code == 422 and err_code(res) == "ZONE_NOT_IN_DEPLOYMENT_SITES", res.text


def test_P5AC38_imran_wah_due_date(api: Api, db: Session) -> None:
    imran = worker(db, "WKR-000001")
    d = db.scalar(
        select(Deployment).where(
            Deployment.worker_id == imran.id, Deployment.project_id == project(db, "ANIA-EXP").id
        )
    )
    assert d is not None
    c = api.as_("noura.qahtani")

    def wah(as_of: str) -> dict[str, Any]:
        res = c.get(f"{API}/deployments/{d.id}/training-requirements", params={"as_of": as_of})
        assert res.status_code == 200, res.text
        return next(
            r for r in res.json()["requirements"] if r["requirement"]["course_code"] == "WAH"
        )

    r = wah("2026-09-08")
    assert r["due_date"] == "2026-09-01" and r["state"] == "gap", r
    # DECISIONS: his WAH session 00031 moved to 2026-09-29 (spec: met from 2026-09-20)
    assert wah("2026-09-25")["state"] == "gap"
    assert wah("2026-10-01")["state"] in ("met", "expiring")
