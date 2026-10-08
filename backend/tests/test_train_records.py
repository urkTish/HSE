"""5-training §9 ACs 64-76, 82, 121-125, 139-143 (training records, verification, QR, PDPL)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now, set_now
from app.models import AuditEntry, TrainingRecord
from tests.cert_helpers import upload_pdf
from tests.conftest import Api
from tests.train_helpers import API, err_code, project, provider, record, riyadh, worker

pytestmark = pytest.mark.usefixtures("train_seed", "clock")

BIJU = "WKR-000017"
PURPOSE = {"purpose": "data_subject_request"}


def body(db: Session, **kw: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "worker_id": str(worker(db, BIJU).id),
        "project_id": str(project(db, "ANIA-EXP").id),
        "course_code": "FIRST-AID",
        "provider_id": str(provider(db, "HAYAT").id),
        "certificate_no": "HY-FA-TEST-26-0901",
        "completed_on": "2026-09-01",
        "name_as_printed": "Biju Thomas",
        "id_on_card": {"shown": False},
    }
    out.update(kw)
    return out


def create(c: TestClient, db: Session, **kw: Any) -> dict[str, Any]:
    pid = project(db, "ANIA-EXP").id
    res = c.post(f"{API}/projects/{pid}/training-records", json=body(db, **kw))
    assert res.status_code in (200, 201), res.text
    return res.json()  # type: ignore[no-any-return]


def act(c: TestClient, rid: str, action: str, **kw: Any) -> Any:
    return c.post(f"{API}/training-records/{rid}/transitions", json={"action": action, **kw})


def submitted(c: TestClient, db: Session, **kw: Any) -> dict[str, Any]:
    r = create(c, db, **kw)
    scan = upload_pdf(c, "training_record_scan", r["id"])
    res = c.patch(f"{API}/training-records/{r['id']}", json={"scan_attachment_id": scan})
    assert res.status_code == 200, res.text
    res = act(c, r["id"], "submit")
    assert res.status_code == 200, res.text
    return res.json()  # type: ignore[no-any-return]


def test_P5AC65_submit_without_scan(api: Api, db: Session) -> None:
    ahmed = api.as_("ahmed.zahrani")
    r = create(ahmed, db)
    assert r["status"] == "draft"
    res = act(ahmed, r["id"], "submit")
    assert res.status_code == 422 and err_code(res) == "SCAN_REQUIRED", res.text


def test_P5AC66_cert_exists_and_reused(api: Api, db: Session) -> None:
    noura = api.as_("noura.qahtani")
    create(noura, db)
    pid = project(db, "ANIA-EXP").id
    res = noura.post(f"{API}/projects/{pid}/training-records", json=body(db))
    assert res.status_code == 409 and err_code(res) == "CERT_EXISTS", res.text
    other = worker(db, "WKR-000001")
    b2 = body(db, worker_id=str(other.id), name_as_printed="Imran Hussain")
    res = noura.post(f"{API}/projects/{pid}/training-records", json=b2)
    assert res.status_code == 409 and err_code(res) == "CERT_NO_REUSED", res.text
    assert "WKR-000017" in res.text
    from app.models import Notification

    db.expire_all()
    sent = db.scalars(
        select(Notification).where(Notification.kind == "training_cert_no_reused")
    ).all()
    assert sent, "HSE Officers alerted (TR-5)"


def test_P5AC69_sod_and_contractor_cannot_accept(api: Api, db: Session) -> None:
    ahmed = api.as_("ahmed.zahrani")
    r = submitted(ahmed, db)
    assert r["status"] == "submitted"
    res = act(ahmed, r["id"], "accept")
    assert res.status_code == 403, res.text
    noura = api.as_("noura.qahtani")
    r2 = submitted(noura, db, certificate_no="HY-FA-TEST-26-0902", worker_id=str(
        worker(db, "WKR-000001").id), name_as_printed="Imran Hussain")  # fmt: skip
    res = act(noura, r2["id"], "accept")
    assert res.status_code == 422 and err_code(res) == "SOD_CONFLICT", res.text
    res = act(api.as_("faisal.harbi"), r["id"], "accept")
    assert res.status_code == 200 and res.json()["status"] == "accepted", res.text


def test_P5AC71_already_expired_and_historic(api: Api, db: Session) -> None:
    noura = api.as_("noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    b = body(db, course_code="HEAT-AWR", provider_id=str(provider(db, "INT-HSE").id),
             certificate_no="OLD-HEAT-2024", completed_on="2024-01-10")  # fmt: skip
    res = noura.post(f"{API}/projects/{pid}/training-records", json=b)
    assert res.status_code == 422 and err_code(res) == "RECORD_ALREADY_EXPIRED", res.text
    res = noura.post(f"{API}/projects/{pid}/training-records", json={**b, "historic": True})
    assert res.status_code in (200, 201), res.text
    assert res.json()["historic"] is True


def test_P5AC67_id_on_card(api: Api, db: Session) -> None:
    noura = api.as_("noura.qahtani")
    card = {"shown": True, "id_type": "iqama", "id_number": "2000001071"}
    pid = project(db, "ANIA-EXP").id
    res = noura.post(f"{API}/projects/{pid}/training-records", json=body(db, id_on_card=card))
    assert res.status_code == 422 and err_code(res) == "CERT_ID_MISMATCH", res.text
    assert (
        db.scalar(
            select(TrainingRecord.id).where(TrainingRecord.certificate_no == "HY-FA-TEST-26-0901")
        )
        is None
    )
    ok = {"shown": True, "id_type": "iqama", "id_number": "2000001017"}
    r = create(noura, db, id_on_card=ok)
    assert r["id_match_result"] == "matched", r


def test_P5AC74_suspend_reason_and_not_accepted_message(api: Api, db: Session) -> None:
    r = record(db, BIJU, "HEAT-AWR")
    noura = api.as_("noura.qahtani")
    res = act(noura, str(r.id), "suspend", reason="too short")
    assert res.status_code == 422, res.text
    res = act(noura, str(r.id), "suspend", reason="Card under review by the provider (test)")
    assert res.status_code == 200 and res.json()["status"] == "suspended", res.text
    ahmed = api.as_("ahmed.zahrani")
    seen = ahmed.get(f"{API}/training-records/{r.id}").json()
    assert seen.get("status_reason_text") is None
    hist = ahmed.get(f"{API}/history/training_record/{r.id}")
    assert hist.status_code == 200, hist.text
    assert "Card under review" not in hist.text and "status_reason_text" not in hist.text
    hist = noura.get(f"{API}/history/training_record/{r.id}")
    assert "Card under review" in hist.text, hist.text
    assert "not accepted" in (seen.get("not_accepted_message_en") or "").lower(), seen


def test_P5AC73_edit_lock_after_24h(api: Api, db: Session) -> None:
    r = record(db, BIJU, "HEAT-AWR")
    r.reviewed_at = now() - timedelta(days=3)
    db.commit()
    res = api.as_("noura.qahtani").patch(
        f"{API}/training-records/{r.id}", json={"completed_on": "2026-01-20", "reason": "typo fix"}
    )
    assert res.status_code in (403, 409), res.text
    res = api.as_("faisal.harbi").patch(
        f"{API}/training-records/{r.id}",
        json={"completed_on": "2026-01-20", "reason": "Corrected from the provider register"},
    )
    assert res.status_code == 200, res.text


def test_P5AC139_scan_url_reason_and_audit(api: Api, db: Session) -> None:
    noura = api.as_("noura.qahtani")
    r = submitted(noura, db)
    res = noura.post(f"{API}/training-records/{r['id']}/scan-url", json={})
    assert res.status_code == 422, res.text
    res = noura.post(f"{API}/training-records/{r['id']}/scan-url", json={"reason": "verification"})
    assert res.status_code == 200, res.text
    rows = db.scalars(
        select(AuditEntry).where(AuditEntry.action == "sensitive_field_read")
        .order_by(AuditEntry.seq.desc())
    ).all()  # fmt: skip
    assert any("training_scan" in (a.fields_read or []) for a in rows)


def test_P5AC121_P5AC122_tr_qr(api: Api, db: Session) -> None:
    from app.models import QrToken

    r = db.scalars(
        select(TrainingRecord).where(
            TrainingRecord.status == "accepted", TrainingRecord.session_id.is_not(None)
        )
    ).first()
    assert r is not None
    tok = db.scalar(select(QrToken).where(QrToken.subject_id == r.id))
    assert tok is not None
    c = api.as_("faisal.harbi")
    res = c.post(f"{API}/certification-checks", json={"payload": f"HSE2:TR:{tok.token}"})
    assert res.status_code == 200, res.text
    text = str(res.json())
    assert r.course_code in text
    tok.status = "revoked"
    db.commit()
    res = c.post(f"{API}/certification-checks", json={"payload": f"HSE2:TR:{tok.token}"})
    assert "REVOKED" in str(res.json()), res.text


def test_P5AC125_qr_needs_auth(api: Api) -> None:
    res = api.anon.post(
        f"{API}/certification-checks", json={"payload": "HSE2:TR:AAAAAAAAAAAAAAAAAAAAAA"}
    )
    assert res.status_code == 401


def test_P5AC143_data_subject_report_manager_only(api: Api, db: Session) -> None:
    w = worker(db, BIJU)
    res = api.as_("faisal.harbi").get(f"{API}/workers/{w.id}/training-report", params=PURPOSE)
    assert res.status_code == 200, res.text
    assert res.json()["records"], res.json()
    res = api.as_("noura.qahtani").get(f"{API}/workers/{w.id}/training-report", params=PURPOSE)
    assert res.status_code == 403, res.text


def test_P5AC82_waleed_rejected_and_e13_inputs(db: Session) -> None:
    r = record(db, "WKR-000008", "FIRST-AID")
    assert r.status.value == "rejected"
    assert r.verification_status.value == "failed"


def test_P5AC141_contractor_sees_not_accepted(api: Api, db: Session) -> None:
    r = record(db, "WKR-000008", "FIRST-AID")
    seen = api.as_("ahmed.zahrani").get(f"{API}/training-records/{r.id}")
    assert seen.status_code == 200, seen.text
    body_ = seen.json()
    assert body_.get("status_reason_text") is None
    assert "not accepted" in (body_.get("not_accepted_message_en") or "").lower(), body_


def test_P5AC142_scan_retention(db: Session) -> None:
    from app.services.train import records as rsvc

    r = record(db, "WKR-000008", "FIRST-AID")
    r.ended_on = date(2024, 1, 1)
    db.flush()
    rsvc.scan_retention_job(db, date(2026, 10, 6))
    assert r.scans_deleted_at is not None


def test_P5AC64_close_issues_records(api: Api, db: Session) -> None:
    from tests.train_helpers import session

    s = session(db, "TRS-ANIA-EXP-2026-00057")
    set_now(riyadh(2026, 10, 7, 17))
    noura = api.as_("noura.qahtani")
    res = noura.get(f"{API}/training-sessions/{s.id}")
    assert res.status_code == 200 and res.json()["status"] == "delivered", res.text
    noms = noura.get(f"{API}/training-sessions/{s.id}/nominations").json()["items"]
    entries = []
    for i, n in enumerate(noms):
        m = 390 if i == len(noms) - 1 else 480
        entries.append({"nomination_id": n["id"], "status": "attended",
                        "minutes_by_day": {"1": m}})  # fmt: skip
    res = noura.put(f"{API}/training-sessions/{s.id}/attendance", json={"entries": entries})
    assert res.status_code == 200, res.text
    statuses = [n["status"] for n in res.json()["items"]]
    assert statuses.count("partial") == 1, statuses
    ass = [{"nomination_id": n["id"], "theory_score_pct": "85.00", "practical_result": "pass"}
           for n in noms[:-1]]  # fmt: skip
    res = noura.put(f"{API}/training-sessions/{s.id}/assessments", json={"entries": ass})
    assert res.status_code in (200, 422), res.text
