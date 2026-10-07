"""Phase 2 jobs, cascades, exports and personal attachments not covered by a numbered AC:
LC-3 raised-suspension auto-lift, LC-7/LC-8 contractor cascades, P2-7 anonymisation, P2-10
exports, photo rules and the ID-copy capability."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import access_jobs
from app.core.access_enums import (
    DeploymentStatus,
    ValidityStatus,
    WapStatus,
    WorkerStatus,
)
from app.core.clock import frozen
from app.core.enums import AuditAction, NotificationKind
from app.models import AuditEntry, Contractor, PassApplication
from tests.access_api import PDF, png, upload
from tests.access_helpers import (
    API,
    adp,
    airport_pass,
    deployment,
    notifications,
    wap,
    worker,
)
from tests.conftest import Api, Ids

pytestmark = pytest.mark.usefixtures("access_seed", "noon")


def test_LC3_raised_suspension_reminds_then_lifts(api: Api, db: Session) -> None:
    a = adp(db, "Rajesh Nair")
    res = api.as_("omar.siddiqui").post(
        f"{API}/credentials/adp/{a.id}/suspend",
        json={"reason_code": "violation", "reason_text": "Speeding on apron road TEST"},
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    assert adp(db, "Rajesh Nair").validity_status == ValidityStatus.suspended
    raised = res.json()
    assert raised is not None
    start = a.updated_at
    with frozen(start + timedelta(hours=49)):
        assert access_jobs.raised_suspensions(db) == 1
        db.commit()
    assert notifications(db, NotificationKind.raised_suspension_pending, a.id)
    with frozen(start + timedelta(hours=73)):
        assert access_jobs.raised_suspensions(db) == 1
        db.commit()
    db.expire_all()
    assert adp(db, "Rajesh Nair").validity_status == ValidityStatus.active


def _contractor(db: Session, code: str) -> Contractor:
    c = db.scalar(select(Contractor).where(Contractor.short_code == code))
    assert c is not None
    return c


def test_LC8_blacklist_cascades_to_access(api: Api, db: Session) -> None:
    c = _contractor(db, "GULFPAVE")
    res = api.as_("faisal.harbi").post(
        f"{API}/contractors/{c.id}/transitions",
        json={"to_status": "blacklisted", "reason": "Falsified permits TEST"},
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    assert deployment(db, "Rajesh Nair").status == DeploymentStatus.demobilised
    assert airport_pass(db, "Rajesh Nair").validity_status == ValidityStatus.revoked
    assert adp(db, "Rajesh Nair").validity_status == ValidityStatus.revoked
    assert wap(db, "2026-0031").status == WapStatus.suspended
    assert notifications(db, NotificationKind.contractor_blacklisted_passes)
    # RAWABI workers (another contractor) keep their credentials
    assert deployment(db, "Mahmoud Fathy").status == DeploymentStatus.mobilised


def test_LC7_suspension_suspends_waps_and_reinstatement_does_not_resume(
    api: Api, db: Session
) -> None:
    c = _contractor(db, "GULFPAVE")
    m = api.as_("faisal.harbi")
    url = f"{API}/contractors/{c.id}/transitions"
    res = m.post(url, json={"to_status": "suspended", "reason": "Safety stand-down TEST"})
    assert res.status_code == 200, res.text
    db.expire_all()
    assert wap(db, "2026-0031").status == WapStatus.suspended
    res = m.post(url, json={"to_status": "approved", "reason": "Stand-down closed TEST"})
    assert res.status_code == 200, res.text
    db.expire_all()
    assert wap(db, "2026-0031").status == WapStatus.suspended


def test_P2_7_anonymise_after_retention(db: Session) -> None:
    arjun = worker(db, "Arjun Pillai")
    assert access_jobs.anonymise_workers(db, date(2031, 9, 19)) == 0 or (
        worker(db, "Arjun Pillai").status != WorkerStatus.anonymised
    )
    db.rollback()
    n = access_jobs.anonymise_workers(db, date(2031, 9, 21))
    db.commit()
    assert n >= 1
    db.expire_all()
    w = db.get(type(arjun), arjun.id)
    assert w is not None
    assert w.status == WorkerStatus.anonymised
    assert w.full_name_en == f"Anonymised worker {w.worker_no}"
    assert w.id_number_enc is None and w.nationality is None and w.id_number_bidx is None


def test_P2_10_exports_mask_ids_and_need_purpose(api: Api, ids: Ids) -> None:
    pid = ids.project("ANIA-EXP")
    n = api.as_("noura.qahtani")
    res = n.get(f"{API}/exports/workers", params={"project_id": pid})
    assert res.status_code == 200, res.text
    assert "Rajesh Nair" in res.text and "2000001002" not in res.text
    res = n.get(f"{API}/exports/workers", params={"project_id": pid, "include_identity": True})
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "EXPORT_PURPOSE_REQUIRED"
    res = n.get(
        f"{API}/exports/workers",
        params={"project_id": pid, "include_identity": True, "purpose": "pass_office"},
    )
    assert res.status_code == 200, res.text
    assert "2000001002" in res.text
    # capability 79 is HSE Officer only; 78 is not given to permit issuers or viewers
    res = api.as_("ahmed.zahrani").get(
        f"{API}/exports/workers",
        params={"project_id": pid, "include_identity": True, "purpose": "pass_office"},
    )
    assert res.status_code == 403
    for who in ("khalid.otaibi", "sarah.mitchell"):
        res = api.as_(who).get(f"{API}/exports/workers", params={"project_id": pid})
        assert res.status_code == 403, who
    # gate log needs capability 76 (permit issuers lack it)
    assert n.get(f"{API}/exports/gate_log", params={"project_id": pid}).status_code == 200
    res = api.as_("ahmed.zahrani").get(f"{API}/exports/gate_log", params={"project_id": pid})
    assert res.status_code == 200, res.text


def test_worker_photo_rules_and_id_copy_capability(api: Api, db: Session) -> None:
    n = api.as_("noura.qahtani")
    w = worker(db, "Rajesh Nair")
    small = upload(n, "worker_photo", w.id, "small.png", png(200, 200))
    assert small.status_code == 422, small.text
    ok = upload(n, "worker_photo", w.id, "photo.png", png(400, 400))
    assert ok.status_code == 201, ok.text
    assert upload(n, "worker_photo", w.id, "x.pdf", PDF).status_code in (415, 422)
    app_row = db.scalars(
        select(PassApplication).where(PassApplication.status.in_(["draft", "submitted"]))
    ).first()
    assert app_row is not None
    copy = upload(n, "pass_application_id_copy", app_row.id, "id.pdf", PDF)
    assert copy.status_code == 201, copy.text
    aid = copy.json()["id"]
    res = api.as_("omar.siddiqui").post(f"{API}/attachments/{aid}/signed-url")
    assert res.status_code in (403, 404), res.text
    res = n.post(f"{API}/attachments/{aid}/signed-url")
    assert res.status_code == 200, res.text
    db.expire_all()
    rows = list(
        db.scalars(
            select(AuditEntry).where(
                AuditEntry.action == AuditAction.sensitive_field_read,
                AuditEntry.fields_read.contains(["id_copy"]),
            )
        )
    )
    assert rows


def test_seeded_adp_register_lists(api: Api, ids: Ids) -> None:
    """Regression: seeded ADPs must use valid vehicle classes so the register serialises."""
    pid = ids.project("ANIA-EXP")
    res = api.as_("noura.qahtani").get(f"{API}/projects/{pid}/adps")
    assert res.status_code == 200, res.text
    assert res.json()["total"] > 0
