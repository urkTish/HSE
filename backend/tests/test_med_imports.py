"""6a-occupational-health §9 ACs 22, 111, 114, 116-123, 128-129 (imports, PDPL, alerts)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now, set_now
from app.core.enums import AuditAction
from app.models import (
    AuditEntry,
    Contractor,
    FitnessAssessment,
    MedicalImportBatch,
    Notification,
    User,
)
from tests.conftest import Api
from tests.med_helpers import API, ok, project, provider, riyadh, worker

pytestmark = pytest.mark.usefixtures("med_seed", "clock")
HEAD = "worker_no,provider_code,examiner_no,assessment_type,examined_on,certificate_no,code,outcome"


def _upload(c: Any, db: Session, rows: list[str], source: str, prov: str | None = None) -> Any:
    data = {"source": source}
    if prov:
        data["provider_id"] = str(provider(db, prov).id)
    csv = "\n".join([HEAD, *rows]).encode()
    return c.post(
        f"{API}/projects/{project(db, 'ANIA-EXP').id}/medical-imports",
        data=data,
        files={"file": ("fitness.csv", csv, "text/csv")},
    )


def _codes(batch: dict[str, Any]) -> list[list[str]]:
    return [[i["code"] for i in r["issues"]] for r in batch["rows"]]


def _notes(db: Session, who: str, kind: str) -> list[Notification]:
    u = db.scalar(select(User).where(User.email == f"{who}@example.com"))
    assert u is not None
    return list(
        db.scalars(
            select(Notification).where(Notification.user_id == u.id, Notification.kind == kind)
        )
    )


# ---- imports (IM6-3, IM6-4) ----------------------------------------------------------------------


def test_AC116_AC121_clinic_register_commit(api: Api, db: Session) -> None:
    huda = api.as_("huda.mansour")
    rows = [
        "WKR-000016,SALAMA,EXR-0003,periodic,2026-10-01,SAL-TEST-26-7001,GEN-FIT,fit",
        "WKR-999999,SALAMA,EXR-0003,periodic,2026-10-01,SAL-TEST-26-7002,GEN-FIT,fit",
        "WKR-000014,SALAMA,EXR-0003,periodic,2026-10-01,SAL-TEST-26-7003,RAD-WORKER-FIT,fit",
    ]
    b = ok(_upload(huda, db, rows, "clinic_register_file", "SALAMA"))
    assert b["status"] == "validated"
    codes = _codes(b)
    assert codes[0] == [] and "E01" in codes[1] and "E04" in codes[2], codes
    b = ok(huda.post(f"{API}/medical-imports/{b['id']}/commit"))
    assert b["status"] == "committed"
    db.expire_all()
    (a,) = db.scalars(
        select(FitnessAssessment).where(FitnessAssessment.certificate_no == "SAL-TEST-26-7001")
    )
    assert a.status.value == "accepted" and a.verification_status.value == "verified"
    row = db.get(MedicalImportBatch, b["id"])
    assert row is not None and row.rows_enc is None
    audits = list(db.scalars(select(AuditEntry).where(AuditEntry.entity_id == row.id)))
    assert all("SAL-TEST" not in str(x.details) for x in audits)
    assert any("sha256" in (x.details or {}) for x in audits)


def test_AC117_AC118_AC120_contractor_file(api: Api, db: Session) -> None:
    from app.models import Deployment, ProjectEngagement, Worker

    qno = db.scalar(  # a QIMMA worker (RBT-52 only): outside Ahmed's scope on ANIA-EXP
        select(Worker.worker_no)
        .join(Deployment, Deployment.worker_id == Worker.id)
        .join(ProjectEngagement, ProjectEngagement.id == Deployment.engagement_id)
        .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
        .where(Contractor.short_code == "QIMMA")
        .order_by(Worker.worker_no)
        .limit(1)
    )
    assert qno is not None
    ahmed = api.as_("ahmed.zahrani")
    rows = [
        "WKR-000016,SALAMA,EXR-0003,periodic,2026-10-01,SAL-TEST-26-7101,GEN-FIT,fit",
        f"{qno},SALAMA,EXR-0003,periodic,2026-10-01,SAL-TEST-26-7102,GEN-FIT,fit",
        "WKR-000034,SHIFA-ANIA,EXR-0005,periodic,2026-10-01,SAL-TEST-26-7103,WAH-FIT,"
        "permanently_unfit",
    ]
    b = ok(_upload(ahmed, db, rows, "contractor_file"))
    codes = _codes(b)
    assert codes[0] == [] and "E08" in codes[1] and "W04" in codes[2], codes
    ok(ahmed.post(f"{API}/medical-imports/{b['id']}/commit"))
    db.expire_all()
    a = db.scalar(
        select(FitnessAssessment).where(FitnessAssessment.certificate_no == "SAL-TEST-26-7101")
    )
    assert a is not None and a.status.value == "draft"
    assert len(_notes(db, "faisal.harbi", "fitness_permanently_unfit")) >= 1


def test_AC119_commit_after_60_minutes(api: Api, db: Session) -> None:
    ahmed = api.as_("ahmed.zahrani")
    row = "WKR-000016,SALAMA,EXR-0003,periodic,2026-10-01,SAL-TEST-26-7201,GEN-FIT,fit"
    b = ok(_upload(ahmed, db, [row], "contractor_file"))
    set_now(now() + timedelta(minutes=61))
    res = api.as_("ahmed.zahrani").post(f"{API}/medical-imports/{b['id']}/commit")
    assert res.status_code == 409, res.text


# ---- PDPL (P6-5, P6-9, rule 28) ------------------------------------------------------------------


def test_AC122_AC123_scan_url(api: Api, db: Session) -> None:
    from tests.cert_helpers import upload_pdf
    from tests.med_helpers import body, fit, post

    ahmed = api.as_("ahmed.zahrani")
    ext = {"source": "external_certificate", "certificate_no": "SAL-TEST-26-7401"}
    made = ok(post(ahmed, db, body(db, "WKR-000016", [fit()], prov="SALAMA", examiner=3, **ext)))
    upload_pdf(ahmed, "fitness_scan", made["id"])
    a = db.get(FitnessAssessment, made["id"])
    assert a is not None
    url = f"{API}/fitness-assessments/{a.id}/scan-url"
    huda = api.as_("huda.mansour")
    assert huda.post(url, json={}).status_code == 422
    res = huda.post(url, json={"reason": "verification"})
    assert res.status_code == 200, res.text
    body = res.json()
    from datetime import datetime

    assert datetime.fromisoformat(body["expires_at"]) <= now() + timedelta(minutes=5)
    reads = db.scalars(
        select(AuditEntry).where(
            AuditEntry.entity_id == a.id, AuditEntry.action == AuditAction.sensitive_field_read
        )
    )
    assert any(r.fields_read == ["fitness_scan"] for r in reads)
    assert api.as_("noura.qahtani").post(url, json={"reason": "verification"}).status_code == 403


def test_AC128_data_subject_report(api: Api, db: Session) -> None:
    w = worker(db, "WKR-000009")
    res = api.as_("faisal.harbi").get(f"{API}/workers/{w.id}/fitness-report")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["assessments"] and body["assessments"][0]["lines"]
    ex = db.scalars(
        select(AuditEntry).where(
            AuditEntry.entity_id == w.id, AuditEntry.action == AuditAction.export
        )
    )
    assert any((x.details or {}).get("purpose") == "data_subject_request" for x in ex)


def test_AC129_suspended_contractor_rep_reads_only(api: Api, db: Session) -> None:
    from app.core.enums import ContractorStatus

    raw = db.scalar(select(Contractor).where(Contractor.short_code == "RAWABI"))
    assert raw is not None
    raw.status = ContractorStatus.suspended
    db.commit()
    ahmed = api.as_("ahmed.zahrani")
    w = worker(db, "WKR-000016")
    pid = project(db, "ANIA-EXP").id
    res = ahmed.post(
        f"{API}/projects/{pid}/fitness-assessments",
        json={"worker_id": str(w.id), "assessment_type": "periodic",
              "source": "external_certificate", "provider_id": str(provider(db, "SALAMA").id),
              "examiner_id": str(w.id), "examined_on": "2026-10-04",
              "certificate_no": "SAL-TEST-26-7301", "purpose_notice_given": True,
              "lines": [{"code": "GEN-FIT", "outcome": "fit"}]},
    )  # fmt: skip
    assert res.status_code == 403, res.text
    res = ahmed.get(f"{API}/workers/{w.id}/fitness", params={"project_id": str(pid)})
    assert res.status_code == 200, res.text


# ---- alerts (MF6, §7) ----------------------------------------------------------------------------


def test_AC22_AC111_AC114_alert_schedule_once(db: Session) -> None:
    from app import med_jobs

    set_now(riyadh(2026, 10, 9, 7, 3))
    first = med_jobs.medical_alerts(db)
    assert first["fitness_expiry"] >= 1 and first["licences"] >= 0
    again = med_jobs.medical_alerts(db)
    assert again["fitness_expiry"] == 0 and again["licences"] == 0  # AC114
    zaheer = worker(db, "WKR-000019")
    noura = _notes(db, "noura.qahtani", "fitness_expiry")
    assert any(n.entity_id == zaheer.id and "CRANE-OPERATOR-FIT" in n.title_en for n in noura)
    faisal = _notes(db, "faisal.harbi", "fitness_expiry")
    assert any(n.entity_id == zaheer.id for n in faisal)  # critical code at 0 days
    set_now(riyadh(2026, 10, 13, 7, 3))
    med_jobs.medical_alerts(db)
    lic = _notes(db, "faisal.harbi", "medical_licence_expiry")
    assert any("EXR-0002" in n.title_en and "(7 days)" in n.title_en for n in lic), [
        n.title_en for n in lic
    ]
