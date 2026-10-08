"""5-training §9 ACs 84, 114-120 (training record / attendance imports, IM5-1…IM5-7)."""

from __future__ import annotations

import io
import zipfile
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now, set_now
from app.models import (
    AuditEntry,
    Contractor,
    Deployment,
    ProjectEngagement,
    TrainingImportBatch,
    TrainingRecord,
    TrainingVerification,
)
from tests.cert_helpers import PDF
from tests.conftest import Api
from tests.train_helpers import API, project, provider, riyadh, session, to_csv

pytestmark = pytest.mark.usefixtures("train_seed", "clock")

REC_HEAD = [
    "worker_no", "id_type", "id_number", "course_code", "provider_code", "certificate_no",
    "completed_on", "printed_expiry", "name_as_printed", "id_on_card",
]  # fmt: skip


def row(**kw: str) -> dict[str, str]:
    base = {"course_code": "FIRST-AID", "provider_code": "HAYAT", "completed_on": "2026-09-01"}
    return {**base, **kw}


def upload(
    c: TestClient, db: Session, content: bytes, template: str = "training_records",
    pcode: str = "ANIA-EXP", name: str = "records.csv", **extra: Any,
) -> Any:  # fmt: skip
    pid = project(db, pcode).id
    files: dict[str, Any] = {"file": (name, content, "text/csv")}
    for k in ("scans_zip", "evidence_file"):
        if k in extra:
            files[k] = extra.pop(k)
    data = {"template": template, **{k: str(v) for k, v in extra.items()}}
    return c.post(f"{API}/projects/{pid}/training-imports", files=files, data=data)


def full(c: TestClient, bid: str) -> dict[str, Any]:
    res = c.get(f"{API}/training-imports/{bid}", params={"include_ok_rows": "true"})
    assert res.status_code == 200, res.text
    return res.json()  # type: ignore[no-any-return]


def scans(*names: str) -> tuple[str, bytes, str]:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n in names:
            z.writestr(f"{n}.pdf", PDF)
    return ("scans.zip", buf.getvalue(), "application/zip")


def existing_cert(db: Session) -> TrainingRecord:
    r = db.scalars(
        select(TrainingRecord)
        .where(
            TrainingRecord.project_id == project(db, "ANIA-EXP").id,
            TrainingRecord.course_code == "FIRST-AID",
            TrainingRecord.status == "accepted",
        )
        .order_by(TrainingRecord.record_no)
    ).first()
    assert r is not None
    return r


def test_P5AC114_dry_run_and_commit(api: Api, db: Session) -> None:
    dup = existing_cert(db)
    from app.models import TrainingProvider

    dup_pv = db.get(TrainingProvider, dup.provider_id)
    assert dup_pv is not None
    rows = [
        row(id_type="iqama", id_number="2000001017", certificate_no="HY-FA-IMP-0001",
            name_as_printed="Biju Thomas"),
        row(worker_no="WKR-999999", certificate_no="HY-FA-IMP-0002"),
        row(worker_no="WKR-000001", provider_code=dup_pv.provider_code,
            certificate_no=dup.certificate_no, name_as_printed="Imran Hussain"),
    ]  # fmt: skip
    noura = api.as_("noura.qahtani")
    res = upload(noura, db, to_csv(REC_HEAD, rows), scans_zip=scans("HY-FA-IMP-0001"))
    assert res.status_code == 201, res.text
    b = full(noura, res.json()["id"])
    assert b["status"] == "validated" and b["sensitive"] is True
    rep = {r["row_no"]: r for r in b["report"]}
    assert rep[1]["status"] != "error", rep[1]
    assert rep[1]["id_masked"] == "2*******17", rep[1]
    assert "2000001017" not in str(b)
    assert "E01" in rep[2]["codes"], rep[2]
    assert "E04" in rep[3]["codes"], rep[3]
    res = noura.post(f"{API}/training-imports/{b['id']}/commit")
    assert res.status_code == 200, res.text
    assert res.json()["counts"]["records_created"] == 1
    created = db.scalars(
        select(TrainingRecord).where(TrainingRecord.certificate_no == "HY-FA-IMP-0001")
    ).all()
    assert [r.status.value for r in created] == ["submitted"]


def test_P5AC115_commit_after_60_minutes(api: Api, db: Session) -> None:
    noura = api.as_("noura.qahtani")
    content = to_csv(REC_HEAD, [row(worker_no="WKR-000017", certificate_no="HY-FA-IMP-0003")])
    res = upload(noura, db, content)
    assert res.status_code == 201, res.text
    b = db.get(TrainingImportBatch, res.json()["id"])
    assert b is not None
    b.created_at = now() - timedelta(minutes=61)
    b.expires_at = now() - timedelta(minutes=1)
    db.commit()
    res = noura.post(f"{API}/training-imports/{b.id}/commit")
    assert res.status_code == 409, res.text


def test_P5AC116_printed_expiry_beyond_validity(api: Api, db: Session) -> None:
    noura = api.as_("noura.qahtani")
    r0 = row(worker_no="WKR-000017", certificate_no="HY-FA-IMP-0004",
             printed_expiry="2031-09-01", name_as_printed="Biju Thomas")  # fmt: skip
    content = to_csv(REC_HEAD, [r0])
    res = upload(noura, db, content)
    assert res.status_code == 201, res.text
    r = full(noura, res.json()["id"])["report"][0]
    assert "W01" in r["codes"], r
    assert r["status"] == "warning", r


def test_P5AC117_contractor_row_outside_scope(api: Api, db: Session) -> None:
    qimma_dep = db.scalars(
        select(Deployment)
        .join(ProjectEngagement, ProjectEngagement.id == Deployment.engagement_id)
        .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
        .where(Contractor.short_code == "QIMMA")
    ).first()
    assert qimma_dep is not None
    from app.models import Worker

    w = db.get(Worker, qimma_dep.worker_id)
    assert w is not None
    ahmed = api.as_("ahmed.zahrani")
    content = to_csv(REC_HEAD, [row(worker_no=w.worker_no, certificate_no="HY-FA-IMP-0005")])
    res = upload(ahmed, db, content)
    assert res.status_code == 201, res.text
    rep = full(ahmed, res.json()["id"])["report"][0]
    assert "E08" in rep["codes"], rep


def test_P5AC118_attendance_minutes_above_day(api: Api, db: Session) -> None:
    s = session(db, "TRS-ANIA-EXP-2026-00057")
    set_now(riyadh(2026, 10, 7, 17))
    noura = api.as_("noura.qahtani")
    noms = noura.get(f"{API}/training-sessions/{s.id}/nominations").json()["items"]
    wno = noms[0]["worker"]["worker_no"]
    head = ["worker_no", "day_no", "minutes"]
    content = to_csv(head, [{"worker_no": wno, "day_no": "1", "minutes": "500"}])
    res = upload(noura, db, content, template="session_attendance", session_id=s.id)
    assert res.status_code == 201, res.text
    rep = full(noura, res.json()["id"])["report"][0]
    assert "E10" in rep["codes"], rep


def test_P5AC119_missing_column_rejects_file(api: Api, db: Session) -> None:
    head = [h for h in REC_HEAD if h != "course_code"]
    content = to_csv(head, [{"worker_no": "WKR-000017", "provider_code": "HAYAT",
                             "certificate_no": "X-1", "completed_on": "2026-09-01"}])  # fmt: skip
    res = upload(api.as_("noura.qahtani"), db, content)
    assert res.status_code == 422, res.text
    assert "E12" in res.text


def test_P5AC120_id_file_deleted_at_commit(api: Api, db: Session) -> None:
    noura = api.as_("noura.qahtani")
    r0 = row(id_type="iqama", id_number="2000001017", certificate_no="HY-FA-IMP-0006",
             name_as_printed="Biju Thomas")  # fmt: skip
    content = to_csv(REC_HEAD, [r0])
    res = upload(noura, db, content)
    assert res.status_code == 201, res.text
    bid = res.json()["id"]
    res = noura.post(f"{API}/training-imports/{bid}/commit")
    assert res.status_code == 200, res.text
    db.expire_all()
    b = db.get(TrainingImportBatch, bid)
    assert b is not None and b.rows == [] and b.sensitive
    audits = db.scalars(select(AuditEntry).where(AuditEntry.entity_id == b.id)).all()
    assert audits
    blob = " ".join(str(a.details) + str(a.after) for a in audits)
    assert "2000001017" not in blob


def test_P5AC84_provider_register_file(api: Api, db: Session) -> None:
    noura = api.as_("noura.qahtani")
    pv = provider(db, "HAYAT")
    content = to_csv(REC_HEAD, [row(worker_no="WKR-000017", certificate_no="HY-FA-IMP-0007",
                                    name_as_printed="Biju Thomas")])  # fmt: skip
    bad = (
        "mail.eml",
        b"From: someone@elsewhere-test.example\nSubject: register\n\nok",
        "text/plain",
    )
    res = upload(noura, db, content, source="provider_register_file", provider_id=pv.id,
                 evidence_file=bad)  # fmt: skip
    assert res.status_code == 422 and "EVIDENCE_DOMAIN_MISMATCH" in res.text, res.text
    good = (
        "mail.eml",
        b"From: registrar@hayat-test.example\nSubject: register\n\nok",
        "text/plain",
    )
    res = upload(noura, db, content, source="provider_register_file", provider_id=pv.id,
                 evidence_file=good, scans_zip=scans("HY-FA-IMP-0007"))  # fmt: skip
    assert res.status_code == 201, res.text
    res = noura.post(f"{API}/training-imports/{res.json()['id']}/commit")
    assert res.status_code == 200, res.text
    r = db.scalar(select(TrainingRecord).where(TrainingRecord.certificate_no == "HY-FA-IMP-0007"))
    assert r is not None and r.status.value == "submitted"
    v = db.scalars(select(TrainingVerification).where(TrainingVerification.record_id == r.id)).all()
    assert [(x.method.value, x.outcome.value) for x in v] == [
        ("provider_register_file", "confirmed")
    ]
    # contractor reps cannot use the provider source
    res = upload(api.as_("ahmed.zahrani"), db, content, source="provider_register_file",
                 provider_id=pv.id, evidence_file=good)  # fmt: skip
    assert res.status_code == 403, res.text
