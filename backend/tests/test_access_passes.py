"""Spec 2-access-permits §9 AC19-AC31 (zone profiles, hooks, airport passes) and X2."""

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.access_enums import (
    CredentialReason,
    CustodyStatus,
    HookKind,
    HookProviderStatus,
    LimitingFactor,
    PassApplicationStatus,
    ValidityStatus,
)
from app.core.clock import now
from app.core.enums import AuditAction
from app.core.hse_enums import AttachmentOwner
from app.models import AccessSettings, Attachment, AuditEntry, PassApplication, Zone
from app.services import attachments
from app.services.access import hooks, passes
from tests.access_api import PDF, png, transition, upload
from tests.access_helpers import API, adp, airport_pass, deployment, project_id, worker
from tests.conftest import Api, Ids

pytestmark = pytest.mark.usefixtures("access_seed", "noon")


def zone_id(db: Session, code: str) -> uuid.UUID:
    z = db.scalar(select(Zone.id).where(Zone.code == code))
    assert z is not None
    return z


def application(db: Session, suffix: str) -> PassApplication:
    a = db.scalar(select(PassApplication).where(PassApplication.application_no.like(f"%{suffix}")))
    assert a is not None, suffix
    return a


# ---- zone profiles and hooks ---------------------------------------------------------------------


def test_P2AC19_new_taxiway_strip_zone_gets_strict_profile(api: Api, ids: Ids) -> None:
    f = api.as_("faisal.harbi")
    res = f.post(
        f"{API}/sites/{ids.site('S-AIR')}/zones",
        json={
            "code": "Z-TWX",
            "name_en": "Taxiway X strip",
            "name_ar": "شريط الممر X",
            "zone_type": "airside",
            "airside": {
                "airside_area": "taxiway_strip",
                "in_movement_area": True,
                "security_restricted_area": True,
                "escort_required": False,
                "adp_required": True,
            },
        },
    )
    assert res.status_code == 201, res.text
    prof = f.get(f"{API}/zones/{res.json()['id']}/access-profile")
    assert prof.status_code == 200, prof.text
    p = prof.json()
    assert p["required_inductions"] == ["GEN", "AIR"]
    assert p["access_permit_required"] is True
    assert p["adp_category_required"] == "manoeuvring"
    assert p["lvp_withdrawal_required"] is True


def test_P2AC20_profile_cannot_be_loosened(api: Api, db: Session) -> None:
    res = api.as_("noura.qahtani").patch(
        f"{API}/zones/{zone_id(db, 'Z-TWB')}/access-profile",
        json={"access_permit_required": False},
    )
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "PROFILE_LOOSENING"


def eligibility(api: Api, db: Session, name: str, zone: str) -> dict[str, object]:
    res = api.as_("noura.qahtani").get(
        f"{API}/workers/{worker(db, name).id}/eligibility",
        params={"zone_id": str(zone_id(db, zone)), "context": "check"},
    )
    assert res.status_code == 200, res.text
    out: dict[str, object] = res.json()
    return out


def test_P2AC21_hook_warn_when_provider_missing(api: Api, db: Session) -> None:
    e = eligibility(api, db, "Saad Al-Dosari", "Z-APR-21")
    hook = [i for i in e["items"] if i["kind"] == "hook" and i["code"] == "AVSEC-AWR"]  # type: ignore[attr-defined,index]
    assert hook and hook[0]["status"] == "warn"
    assert hook[0]["reason_code"] == "HOOK_NOT_AVAILABLE"
    assert e["eligible"] is True


def test_P2AC22_block_policy_needs_provider(api: Api, ids: Ids) -> None:
    res = api.as_("faisal.harbi").patch(
        f"{API}/projects/{ids.project('ANIA-EXP')}/access-settings",
        json={"hook_policy": {"training_course": "block"}},
    )
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "HOOK_PROVIDER_MISSING"


class NotMet:
    def check(self, subject_type, subject_id, kind, code, at):  # type: ignore[no-untyped-def]
        return hooks.HookCheck(HookProviderStatus.not_met, reason_code="NOT_TRAINED")


def test_P2AC23_provider_not_met_blocks(api: Api, ids: Ids, db: Session) -> None:
    hooks.register_provider(HookKind.training_course, NotMet())
    try:
        res = api.as_("faisal.harbi").patch(
            f"{API}/projects/{ids.project('ANIA-EXP')}/access-settings",
            json={"hook_policy": {"training_course": "block"}},
        )
        assert res.status_code == 200, res.text
        e = eligibility(api, db, "Saad Al-Dosari", "Z-APR-21")
        assert e["eligible"] is False
        codes = [i["reason_code"] for i in e["items"]]  # type: ignore[attr-defined]
        assert "HOOK_NOT_MET" in codes
    finally:
        hooks.unregister_provider(HookKind.training_course)


# ---- airport passes ------------------------------------------------------------------------------


def app_body(db: Session, name: str, **over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "application_type": "renewal",
        "deployment_id": str(deployment(db, name).id),
        "sponsor_letter_ref": "SPL-TEST-001",
        "pass_category": "PERM",
        "requested_area_codes": ["A"],
        "requested_valid_until": "2027-03-14",
        "justification": "Continued airside works on the expansion package",
    }
    body.update(over)
    return body


def test_P2AC24_not_airport_project(api: Api, ids: Ids, db: Session) -> None:
    res = api.as_("faisal.harbi").post(
        f"{API}/projects/{ids.project('RBT-52')}/pass-applications",
        json=app_body(db, "Imtiaz Ahmed"),
    )
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "NOT_AIRPORT_PROJECT"


def test_P2AC25_validity_capped_by_iqama(api: Api, ids: Ids, db: Session) -> None:
    n = api.as_("noura.qahtani")
    url = f"{API}/projects/{ids.project('ANIA-EXP')}/pass-applications"
    res = n.post(url, json=app_body(db, "Rajesh Nair", requested_valid_until="2027-05-31"))
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "VALIDITY_EXCEEDS_LIMIT"
    assert "worker.id_expiry_date" in res.text
    res = n.post(url, json=app_body(db, "Rajesh Nair", requested_valid_until="2027-03-14"))
    assert res.status_code == 201, res.text


def test_P2AC26_approval_needs_cleared_background(api: Api, db: Session) -> None:
    a = application(db, "2026-0142")
    n = api.as_("noura.qahtani")
    res = transition(n, a.id, "approved")
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "BACKGROUND_NOT_CLEARED"
    res = n.put(
        f"{API}/pass-applications/{a.id}/background-check",
        json={"status": "cleared", "check_date": "2026-10-06"},
    )
    assert res.status_code == 200, res.text
    res = transition(n, a.id, "approved")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"


def submitted_application(api: Api, ids: Ids, db: Session, submitter: str) -> str:
    c = api.as_(submitter)
    res = c.post(
        f"{API}/projects/{ids.project('ANIA-EXP')}/pass-applications",
        json=app_body(db, "Saad Al-Dosari", requested_valid_until="2027-09-30",
                      requested_area_codes=["A", "M"]),
    )  # fmt: skip
    assert res.status_code == 201, res.text
    aid = res.json()["id"]
    w = worker(db, "Saad Al-Dosari")
    up = upload(c, "worker_photo", w.id, "saad.png", png())
    assert up.status_code == 201, up.text
    up = upload(c, "pass_application_id_copy", aid, "id.pdf", PDF)
    assert up.status_code == 201, up.text
    res = transition(c, aid, "submitted")
    assert res.status_code == 200, res.text
    return str(aid)


def test_P2AC27_submitter_cannot_endorse(api: Api, ids: Ids, db: Session) -> None:
    aid = submitted_application(api, ids, db, "noura.qahtani")
    res = transition(api.as_("noura.qahtani"), aid, "endorsed")
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "ENDORSER_NOT_ALLOWED"


def test_P2AC28_refused_application_visibility(api: Api, db: Session) -> None:
    a = application(db, "2026-0118")
    res = api.as_("ahmed.zahrani").get(f"{API}/pass-applications/{a.id}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status_label_en"] == "Refused by issuing authority"
    assert body.get("background_check") is None
    assert "not_cleared" not in res.text
    res = api.as_("noura.qahtani").get(f"{API}/pass-applications/{a.id}")
    assert res.status_code == 200, res.text
    assert res.json()["background_check"]["status"] == "not_cleared"
    db.expire_all()
    row = db.scalar(
        select(AuditEntry).where(
            AuditEntry.action == AuditAction.sensitive_field_read, AuditEntry.entity_id == a.id
        )
    )
    assert row is not None


def test_P2AC29_X2_X3_pass_and_adp_effective_validity(api: Api, db: Session) -> None:
    ps = airport_pass(db, "Rajesh Nair")
    assert ps.effective_valid_until == date(2027, 3, 14)
    assert ps.limiting_factor == LimitingFactor.worker_id_expiry_date
    assert adp(db, "Rajesh Nair").effective_valid_until == date(2027, 3, 14)
    w = worker(db, "Rajesh Nair")
    res = api.as_("noura.qahtani").patch(
        f"{API}/workers/{w.id}", json={"id_expiry_date": "2028-03-14"}
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    ps = airport_pass(db, "Rajesh Nair")
    assert ps.effective_valid_until == date(2027, 5, 20)
    assert ps.limiting_factor == LimitingFactor.background_recheck_due
    assert adp(db, "Rajesh Nair").effective_valid_until == date(2027, 5, 20)


def test_P2AC30_renewal_supersedes_previous_pass(api: Api, ids: Ids, db: Session) -> None:
    old = airport_pass(db, "Saad Al-Dosari")
    aid = submitted_application(api, ids, db, "ahmed.zahrani")
    n = api.as_("noura.qahtani")
    res = transition(n, aid, "endorsed", client_sponsor_user_id=ids.user("noura.qahtani"))
    assert res.status_code == 200, res.text
    res = transition(n, aid, "lodged", authority_ref="AUTH-TEST-0001")
    assert res.status_code == 200, res.text
    res = n.put(
        f"{API}/pass-applications/{aid}/background-check",
        json={"status": "cleared", "check_date": "2026-10-06"},
    )
    assert res.status_code == 200, res.text
    assert transition(n, aid, "approved").status_code == 200
    res = n.post(
        f"{API}/pass-applications/{aid}/issue",
        json={"pass_no": "ANIA-AP-26-TEST-9001", "area_codes": ["A", "M"],
              "issued_on": "2026-10-06", "card_expiry_date": "2027-09-30"},
    )  # fmt: skip
    assert res.status_code in (200, 201), res.text
    db.expire_all()
    db.refresh(old)
    assert old.validity_status == ValidityStatus.revoked
    assert old.revoked_reason == CredentialReason.superseded
    assert old.custody_status == CustodyStatus.return_due
    assert old.return_due_on == date(2026, 10, 9)


def test_P2AC31_id_copy_deleted_after_retention(db: Session) -> None:
    a = db.scalar(
        select(PassApplication).where(
            PassApplication.status == PassApplicationStatus.issued,
            PassApplication.project_id == project_id(db, "ANIA-EXP"),
        )
    )
    assert a is not None
    s = db.get(AccessSettings, a.project_id)
    assert s is not None
    att = attachments.store(
        db, AttachmentOwner.pass_application_id_copy, a.id, a.project_id, "id.pdf", PDF,
        "application/pdf", a.created_by_user_id or uuid.uuid4(),
    )  # fmt: skip
    db.execute(
        update(PassApplication)
        .where(PassApplication.id == a.id)
        .values(closed_at=now() - timedelta(days=s.id_copy_retention_days + 1),
                id_copy_deleted_at=None)
    )  # fmt: skip
    db.commit()
    assert passes.delete_id_copies(db) >= 1
    db.commit()
    assert db.get(Attachment, att.id) is None
    db.expire_all()
    assert db.get(PassApplication, a.id).id_copy_deleted_at is not None  # type: ignore[union-attr]
    row = db.scalar(
        select(AuditEntry).where(AuditEntry.entity_id == a.id, AuditEntry.action == AuditAction.archive)
    )
    assert row is not None and row.details["id_copy_deleted"] == 1
    _ = datetime
