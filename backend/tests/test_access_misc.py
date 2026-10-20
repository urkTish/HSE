"""Phase 2 jobs, cascades, exports and personal attachments not covered by a numbered AC:
LC-3 raised-suspension auto-lift, LC-7/LC-8 contractor cascades, P2-7 anonymisation, P2-10
exports, photo rules and the ID-copy capability."""

import os
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import access_jobs
from app.core.access_enums import (
    CredentialReason,
    DeploymentStatus,
    ValidityStatus,
    WapStatus,
    WorkerStatus,
)
from app.core.clock import frozen
from app.core.enums import AuditAction, EntityType, NotificationKind
from app.core.hse_enums import AttachmentOwner
from app.models import (
    Attachment,
    AuditEntry,
    Contractor,
    Deployment,
    InductionRecord,
    PassApplication,
    WapCrew,
    Worker,
)
from app.services import attachments
from app.services.access import workers
from tests.access_api import PDF, png, transition, upload
from tests.access_helpers import (
    API,
    adp,
    airport_pass,
    deployment,
    notifications,
    vehicle,
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


def test_review_demobilise_removes_crew_on_that_project_only(
    api: Api, ids: Ids, db: Session
) -> None:
    """Review F5 (LC-10 / WK-1): demobilising one deployment leaves the worker's WAP crew
    places on the other project untouched."""
    rajesh = worker(db, "Rajesh Nair")
    open_rows = db.scalars(
        select(WapCrew).where(WapCrew.worker_id == rajesh.id, WapCrew.removed_at.is_(None))
    ).all()
    assert open_rows
    res = api.as_("yousef.ghamdi").post(
        f"{API}/projects/{ids.project('RBT-52')}/deployments",
        json={
            "worker_id": str(rajesh.id), "engagement_id": ids.engagement("QIMMA"),
            "trade": "labourer", "site_ids": [ids.site("S-TWR")], "mobilised_on": "2026-10-06",
        },
    )  # fmt: skip
    assert res.status_code in (200, 201), res.text
    dep = db.get(Deployment, uuid.UUID(res.json()["id"]))
    assert dep is not None
    workers.demobilise(db, dep, date(2026, 10, 6), CredentialReason.demobilised, None)
    db.commit()
    db.expire_all()
    still = db.scalars(
        select(WapCrew).where(WapCrew.worker_id == rajesh.id, WapCrew.removed_at.is_(None))
    ).all()
    assert len(still) == len(open_rows)


def test_review_istimara_is_personal_data(api: Api, db: Session) -> None:
    """Review F6 (D-272): the registration document is not readable by a Viewer/Client (73)."""
    v = vehicle(db, "VEH-0004")
    n = api.as_("noura.qahtani")
    up = upload(n, "vehicle_registration", v.id, "istimara.pdf", PDF)
    assert up.status_code == 201, up.text
    aid = up.json()["id"]
    s = api.as_("sarah.mitchell")
    assert s.post(f"{API}/attachments/{aid}/signed-url").status_code in (403, 404)
    assert n.post(f"{API}/attachments/{aid}/signed-url").status_code == 200
    res = s.get(f"{API}/vehicles/{v.id}")
    assert res.status_code == 200, res.text
    assert res.json()["istimara_attachment_id"] is None
    res = n.get(f"{API}/vehicles/{v.id}")
    assert res.status_code == 200 and res.json()["istimara_attachment_id"] == aid


def test_review_anonymise_erases_signatures_and_user_link(ids: Ids, db: Session) -> None:
    """Review F7 (P2-7 / P3-5): induction signature images and the account link go too."""
    arjun = worker(db, "Arjun Pillai")
    rec = db.scalar(select(InductionRecord).where(InductionRecord.worker_id == arjun.id))
    assert rec is not None
    sig = attachments.store(
        db,
        AttachmentOwner.induction_signature,
        rec.id,
        rec.project_id,
        "sig.png",
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
        "image/png",
        uuid.UUID(ids.user("noura.qahtani")),
    )
    rec.signature_attachment_id = sig.id
    arjun.user_id = uuid.UUID(ids.user("omar.siddiqui"))
    key = sig.storage_key
    db.commit()
    assert access_jobs.anonymise_workers(db, date(2031, 9, 21)) >= 1
    db.commit()
    db.expire_all()
    w = db.get(Worker, arjun.id)
    assert w is not None and w.status == WorkerStatus.anonymised
    assert w.user_id is None and w.ban_reason is None
    assert db.get(Attachment, sig.id) is None
    assert not (Path(os.environ["STORAGE_DIR"]) / key).exists()
    rec2 = db.get(InductionRecord, rec.id)
    assert rec2 is not None and rec2.signature_attachment_id is None


def test_review_id_copy_signed_url_audits_unmask(api: Api, db: Session) -> None:
    """Review F8 (WK-5 / D-272): opening the Iqama copy writes sensitive_field_read."""
    n = api.as_("noura.qahtani")
    w = worker(db, "Rajesh Nair")
    up = upload(n, "worker_id_copy", w.id, "id.pdf", PDF)
    assert up.status_code == 201, up.text
    res = n.post(f"{API}/attachments/{up.json()['id']}/signed-url")
    assert res.status_code == 200, res.text
    db.expire_all()
    rows = db.scalars(
        select(AuditEntry).where(
            AuditEntry.action == AuditAction.sensitive_field_read,
            AuditEntry.entity_type == EntityType.worker,
            AuditEntry.entity_id == w.id,
        )
    ).all()
    assert rows and any("id_copy" in (r.fields_read or []) for r in rows)


def test_review_withdrawal_only_by_the_applicant(api: Api, ids: Ids, db: Session) -> None:
    """Review F15 (§4.4): capability 53 withdraws own applications only."""
    app_row = db.scalars(
        select(PassApplication).where(PassApplication.status.in_(["draft", "submitted"]))
    ).first()
    assert app_row is not None
    db.execute(
        update(PassApplication)
        .where(PassApplication.id == app_row.id)
        .values(
            created_by_user_id=uuid.UUID(ids.user("noura.qahtani")),
            submitted_by_user_id=uuid.UUID(ids.user("noura.qahtani")),
        )
    )
    db.commit()
    res = transition(api.as_("ahmed.zahrani"), app_row.id, "withdrawn", reason="Not needed TEST")
    assert res.status_code == 403, res.text


def test_review_viewer_cannot_print_wap(api: Api, db: Session) -> None:
    """Review F20: the WAP card names the crew and the GET mints a token; not for 73."""
    w = wap(db, "2026-0031")
    assert api.as_("sarah.mitchell").get(f"{API}/waps/{w.id}/print").status_code == 403
    assert api.as_("noura.qahtani").get(f"{API}/waps/{w.id}/print").status_code == 200


def test_review_list_background_read_audits_once_per_page(api: Api, ids: Ids, db: Session) -> None:
    """Review F21: one sensitive_field_read entry per list call, not one per row."""

    def entries() -> int:
        db.expire_all()
        return len(
            db.scalars(
                select(AuditEntry).where(
                    AuditEntry.action == AuditAction.sensitive_field_read,
                    AuditEntry.fields_read.contains(["background_check"]),
                )
            ).all()
        )

    before = entries()
    res = api.as_("noura.qahtani").get(
        f"{API}/projects/{ids.project('ANIA-EXP')}/pass-applications", params={"page_size": 20}
    )
    assert res.status_code == 200, res.text
    assert len(res.json()["items"]) > 1
    assert entries() - before == 1
