"""5-training §9 record / verification ACs not covered elsewhere: 68, 70, 72, 76, 78, 79, 80,
81, 83."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind, HookSubjectType, RequirementStatus
from app.core.clock import now, set_now
from app.models import Notification, TrainingRecord
from tests.cert_helpers import upload_pdf
from tests.conftest import Api
from tests.train_helpers import API, err_code, project, provider, record, riyadh, worker

pytestmark = pytest.mark.usefixtures("train_seed", "clock")

BIJU = "WKR-000017"


def body(db: Session, pcode: str = "ANIA-EXP", **kw: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "worker_id": str(worker(db, BIJU).id),
        "project_id": str(project(db, pcode).id),
        "course_code": "FIRST-AID",
        "provider_id": str(provider(db, "HAYAT").id),
        "certificate_no": "HY-FA-MORE-26-0001",
        "completed_on": "2026-09-01",
        "name_as_printed": "Biju Thomas",
        "id_on_card": {"shown": False},
    }
    out.update(kw)
    return out


def create(c: TestClient, db: Session, pcode: str = "ANIA-EXP", **kw: Any) -> Any:
    return c.post(f"{API}/projects/{project(db, pcode).id}/training-records",
                  json=body(db, pcode, **kw))  # fmt: skip


def ok(res: Any) -> dict[str, Any]:
    assert res.status_code in (200, 201), res.text
    return res.json()  # type: ignore[no-any-return]


def act(c: TestClient, rid: str, action: str, **kw: Any) -> Any:
    return c.post(f"{API}/training-records/{rid}/transitions", json={"action": action, **kw})


def submitted(c: TestClient, db: Session, pcode: str = "ANIA-EXP", **kw: Any) -> dict[str, Any]:
    r = ok(create(c, db, pcode, **kw))
    scan = upload_pdf(c, "training_record_scan", r["id"])
    ok(c.patch(f"{API}/training-records/{r['id']}", json={"scan_attachment_id": scan}))
    return ok(act(c, r["id"], "submit"))


def email_check(c: TestClient, rid: str, outcome: str, at: datetime | None = None) -> Any:
    ev = upload_pdf(c, "training_verification_evidence", rid)
    b: dict[str, Any] = {"method": "provider_email", "channel_used": "cards@hayat-test.example",
                         "outcome": outcome, "reference": "HAYAT reply ref 2026/10",
                         "evidence_attachment_id": ev}  # fmt: skip
    if at is not None:
        b["performed_at"] = at.isoformat()
    return c.post(f"{API}/training-records/{rid}/verifications", json=b)


def hook(db: Session, worker_no: str, code: str, at: datetime, pcode: str = "ANIA-EXP") -> Any:
    from app.services.access import common as acommon
    from app.services.access import eligibility as elig
    from app.services.access.hooks import HookContext
    from app.services.cert import policy
    from app.services.train import hook as thook

    pid = project(db, pcode).id
    policy.clear_cache(db)
    thook.clear_cache(db)
    w = worker(db, worker_no)
    return elig.hook_item(db, HookSubjectType.worker, w.id, HookKind.training_course, code, at,
                          acommon.settings(db, pid), HookContext(project_id=pid))  # fmt: skip


def test_P5AC68_name_match_partial_and_none(api: Api, db: Session) -> None:
    noura, faisal = api.as_("noura.qahtani"), api.as_("faisal.harbi")
    # PC-4 counts whole tokens: "B. Thomas" shares one token (none); see PROGRESS open question
    r = submitted(noura, db, name_as_printed="Biju K. Thomas")
    assert r["name_match"] == "partial", r
    assert "W02" in str(r["warnings"]), r["warnings"]
    ok(act(faisal, r["id"], "accept"))
    r2 = submitted(noura, db, name_as_printed="Ramon Cruz", certificate_no="HY-FA-MORE-26-0002",
                   worker_id=str(worker(db, "WKR-000004").id))  # fmt: skip
    assert r2["name_match"] == "none", r2
    res = act(faisal, r2["id"], "accept")
    assert res.status_code == 422 and err_code(res) == "NAME_MISMATCH_CONFIRMATION", res.text
    res = act(faisal, r2["id"], "accept", identity_confirmed_by_provider=True)
    assert res.status_code == 200 and res.json()["status"] == "accepted", res.text


def test_P5AC70_external_prerequisite(api: Api, db: Session) -> None:
    """Biju has neither CSE-ENTRANT nor FIRST-AID: an external CSE-RESCUE is refused unless
    the certificate evidences the prerequisites (TR-9)."""
    noura, faisal = api.as_("noura.qahtani"), api.as_("faisal.harbi")
    r = submitted(noura, db, course_code="CSE-RESCUE", certificate_no="HY-CR-MORE-26-0001")
    res = act(faisal, r["id"], "accept")
    assert res.status_code == 422 and err_code(res) == "TRAINING_PREREQUISITE", res.text
    assert "FIRST-AID" in res.text, res.text
    r2 = submitted(noura, db, course_code="CSE-RESCUE", certificate_no="HY-CR-MORE-26-0002",
                   prerequisite_evidenced_on_certificate=True)  # fmt: skip
    res = act(faisal, r2["id"], "accept")
    assert res.status_code == 200, res.text


def test_P5AC72_refresher_window(api: Api, db: Session) -> None:
    """Rafiq's FIRST-AID runs to 2026-11-15 (refresher_max_lapse_days 0)."""
    set_now(riyadh(2026, 11, 20, 10))
    noura = api.as_("noura.qahtani")
    rafiq = str(worker(db, "WKR-000021").id)
    kw = {"worker_id": rafiq, "name_as_printed": "Rafiq Islam", "course_code": "FIRST-AID-R"}
    r = ok(create(noura, db, completed_on="2026-11-10", certificate_no="HY-FR-1", **kw))
    assert r["valid_until"] == "2028-11-09", r
    res = create(noura, db, completed_on="2026-11-16", certificate_no="HY-FR-2", **kw)
    assert res.status_code == 422 and err_code(res) == "REFRESHER_NOT_ELIGIBLE", res.text
    # the older FIRST-AID is superseded once the refresher is in force
    from app.services.train import recordops

    old = record(db, "WKR-000021", "FIRST-AID")
    new = db.get(TrainingRecord, uuid.UUID(r["id"]))
    assert new is not None
    new.status = "accepted"
    new.verification_status = "verified"
    db.flush()
    gone = recordops.supersede_older(db, None, new)
    assert old.id in {x.id for x in gone}
    assert old.superseded_by_id == new.id


def test_P5AC76_record_follows_worker_with_override(api: Api, db: Session) -> None:
    pid = project(db, "RBT-52").id
    res = api.as_("faisal.harbi").patch(
        f"{API}/projects/{pid}/training-settings", json={"course_validity_months": {"WAH": 12}}
    )
    assert res.status_code == 200, res.text
    at = riyadh(2026, 10, 6, 10)
    rbt = hook(db, "WKR-000001", "WAH", at, "RBT-52")
    ania = hook(db, "WKR-000001", "WAH", at, "ANIA-EXP")
    assert rbt.status == RequirementStatus.met and ania.status == RequirementStatus.met
    assert ania.valid_until == date(2028, 9, 28), ania.valid_until
    assert rbt.valid_until == date(2027, 9, 28), rbt.valid_until


def test_P5AC78_unverified_acceptance_window(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    faisal = api.as_("faisal.harbi")
    ok(faisal.patch(f"{API}/projects/{pid}/training-settings",
                    json={"unverified_training_acceptance_hours": 24}))  # fmt: skip
    noura = api.as_("noura.qahtani")
    r = submitted(noura, db)
    ok(act(faisal, r["id"], "accept"))
    t0 = now()
    assert hook(db, BIJU, "FIRST-AID", t0 + timedelta(hours=1)).status in (
        RequirementStatus.met, RequirementStatus.expiring)  # fmt: skip
    late = hook(db, BIJU, "FIRST-AID", t0 + timedelta(hours=25)).status
    assert late not in (RequirementStatus.met, RequirementStatus.expiring), late
    # a critical code is never in force unverified
    from app.services.train import common
    from app.services.train import hook as thook
    from app.services.train import validity as tval

    rec = db.get(TrainingRecord, uuid.UUID(r["id"]))
    assert rec is not None
    rec.course_code = "CSE-ENTRANT"
    db.flush()
    best = tval.best([rec], common.satisfiers(db, "CSE-ENTRANT"), t0.date(),
                     thook.eval_ctx(db, pid), t0 + timedelta(hours=1))  # fmt: skip
    assert not best.met


def test_P5AC79_verifier_same_employer(api: Api, db: Session) -> None:
    from app.core.enums import Role
    from app.models import RoleAssignment

    pid = project(db, "RBT-52").id
    yousef = db.scalar(select(RoleAssignment.user_id).join(RoleAssignment.user).where(
        RoleAssignment.user.has(email="yousef.ghamdi@example.com")).limit(1))  # fmt: skip
    assert yousef is not None
    db.add(RoleAssignment(id=uuid.uuid4(), user_id=yousef, role=Role.hse_officer, project_id=pid,
                          site_ids=[], valid_from=date(2026, 10, 1)))  # fmt: skip
    db.commit()
    lina = api.as_("lina.haddad")
    r = submitted(lina, db, "RBT-52", worker_id=str(worker(db, "WKR-000101").id),
                  name_as_printed="Imtiaz Ahmed", certificate_no="HY-FA-QIM-1")  # fmt: skip
    res = email_check(api.as_("yousef.ghamdi"), r["id"], "confirmed")
    assert res.status_code == 422 and err_code(res) == "SOD_CONFLICT", res.text


def test_P5AC80_foreign_verification_domain(api: Api, db: Session) -> None:
    noura = api.as_("noura.qahtani")
    url = "https://verify.hayat-fake.example/c/HY-FA-MORE-26-0001"
    r = submitted(noura, db, provider_verification_url=url)
    assert "VERIFICATION_URL_FOREIGN_DOMAIN" in str(r["warnings"]), r["warnings"]
    ev = upload_pdf(api.as_("faisal.harbi"), "training_verification_evidence", r["id"])
    res = api.as_("faisal.harbi").post(
        f"{API}/training-records/{r['id']}/verifications",
        json={"method": "provider_qr_url", "channel_used": url, "outcome": "confirmed",
              "reference": "QR page", "evidence_attachment_id": ev},
    )  # fmt: skip
    assert res.status_code == 422 and err_code(res) == "CHANNEL_NOT_REGISTERED", res.text


def test_P5AC81_two_no_responses(api: Api, db: Session) -> None:
    noura = api.as_("noura.qahtani")
    r = submitted(noura, db)
    faisal = api.as_("faisal.harbi")
    res = email_check(faisal, r["id"], "no_response", riyadh(2026, 10, 1, 9))
    assert res.status_code in (200, 201), res.text
    res = email_check(faisal, r["id"], "no_response", riyadh(2026, 10, 2, 10))
    assert res.status_code in (200, 201), res.text
    db.expire_all()
    rec = db.get(TrainingRecord, uuid.UUID(r["id"]))
    assert rec is not None and rec.verification_status.value == "unable_to_verify"
    sent = db.scalars(
        select(Notification).where(
            Notification.kind == "training_verification_unable", Notification.entity_id == rec.id
        )
    ).all()
    assert sent


def test_P5AC83_renewal_needs_its_own_verification(api: Api, db: Session) -> None:
    noura, faisal = api.as_("noura.qahtani"), api.as_("faisal.harbi")
    first = submitted(noura, db)
    ok(email_check(faisal, first["id"], "confirmed"))
    ok(act(faisal, first["id"], "accept"))
    renewal = submitted(noura, db, certificate_no="HY-FA-MORE-26-0099", completed_on="2026-10-01")
    assert renewal["verification_status"] == "not_verified", renewal
