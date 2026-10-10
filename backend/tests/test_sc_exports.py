"""Phase 6g generic exports (6g §9 AC 43-50)."""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import get_settings
from app.core.enums import AuditAction
from app.core.scorecard_enums import XpFormat, XpFrequency, XpJobStatus, XpPurpose
from app.models import Attachment, AuditEntry, XpJob
from app.schemas.scorecard import XpExportRequest, XpSubscriptionCreate
from app.services.attachments import ENCRYPTED
from app.services.scorecard import datasets, exports
from tests.conftest import Api
from tests.sc_helpers import API, P, expect, notified, project, tick

pytestmark = pytest.mark.usefixtures("sc_seed", "sc_clock")


def _req(db: Session, who: str, ds: str, **kw: object) -> XpJob:
    out = exports.request(
        db, P(db, who), XpExportRequest(dataset=ds, project_id=project(db, "ANIA-EXP").id, **kw)
    )  # type: ignore[arg-type]
    job = db.get(XpJob, out.id)
    assert job is not None
    return job


def _csv(db: Session, job: XpJob) -> tuple[bytes, list[list[str]]]:
    a = db.get(Attachment, job.attachment_id)
    assert a is not None
    raw = (Path(get_settings().storage_dir) / a.storage_key).read_bytes()
    if a.storage_bucket in ENCRYPTED:
        raw = crypto.decrypt_bytes(raw)
    return raw, list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))


def _col(rows: list[list[str]], name: str) -> list[str]:
    heads = [h.lower() for h in rows[0]]
    i = (
        heads.index(name)
        if name in heads
        else next(i for i, h in enumerate(heads) if h.startswith(name))
    )
    return [r[i] for r in rows[1:] if len(r) > i and not r[0].startswith("Exported ")]


def test_incident_register_ac43_46(db: Session) -> None:
    last = db.scalar(select(func.max(AuditEntry.seq))) or 0
    job = _req(db, "omar.siddiqui", "incidents")
    # D-225: the wrapped Phase 1 exporter's own entry is muted; the job writes the one entry
    rows_ = db.scalars(
        select(AuditEntry).where(AuditEntry.action == AuditAction.export, AuditEntry.seq > last)
    ).all()
    assert [r.entity_id for r in rows_] == [job.id]
    ds = datasets.get("incidents")
    assert ds is not None and (ds.en, ds.ar) == ("Incidents", "الحوادث")
    assert job.status == XpJobStatus.ready
    raw, rows = _csv(db, job)
    assert raw.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM (AC46)
    sites = {s for s in _col(rows, "site") if s}
    assert sites and all("S-AIR" in s for s in sites)
    persons = [x for x in _col(rows, "person") if x]
    assert persons and all(
        (x.startswith("Person ") and x.count(" · ") == 2) or x == "Privacy case" for x in persons
    )
    a = db.scalar(
        select(AuditEntry).where(
            AuditEntry.action == AuditAction.export, AuditEntry.entity_id == job.id
        )
    )
    assert a is not None and {"columns", "filters", "row_count", "export_id"} <= set(a.details)
    assert exports.guard('=HYPERLINK("x")') == '\'=HYPERLINK("x")' and exports.guard("ok") == "ok"


def test_purpose_and_column_rules_ac44_45(db: Session) -> None:
    cols = ["person_name", "id_number"]
    expect("PURPOSE_REQUIRED", lambda: _req(db, "noura.qahtani", "incidents", columns=cols))
    t = tick(2026, 10, 12, 11)
    job = _req(db, "noura.qahtani", "incidents", columns=cols, purpose=XpPurpose.gosi)
    assert job.contains_sensitive and job.expires_at == t + timedelta(hours=24)
    assert db.scalar(
        select(AuditEntry.id).where(
            AuditEntry.action == AuditAction.sensitive_field_read, AuditEntry.entity_id == job.id
        )
    )
    expect(
        "COLUMN_NOT_PERMITTED", lambda: _req(db, "ahmed.zahrani", "workers", columns=["id_number"])
    )
    expect(
        "COLUMN_NOT_EXPORTABLE",
        lambda: _req(
            db,
            "noura.qahtani",
            "incidents",
            columns=["medical_attachments"],
            purpose=XpPurpose.gosi,
        ),
    )
    expect(
        "COLUMN_NOT_EXPORTABLE",
        lambda: _req(db, "noura.qahtani", "gas_tests", columns=["readings"]),
    )
    plain = _req(db, "noura.qahtani", "permits")
    assert plain.expires_at == t + timedelta(days=7)


def test_job_limits_ac47(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    job = _req(db, "noura.qahtani", "observations")
    assert job.status == XpJobStatus.queued  # > 5,000 rows -> background job
    t = tick(2026, 10, 12, 10, 5)
    assert exports.run_queue(db, t) >= 1 and job.status == XpJobStatus.ready
    assert "noura.qahtani" in notified(db, "export_ready", t)
    monkeypatch.setattr(exports, "JOB_MAX", 10)
    expect("EXPORT_TOO_LARGE", lambda: _req(db, "noura.qahtani", "observations"))
    monkeypatch.setattr(exports, "DAILY_LIMIT", 0)
    expect("EXPORT_RATE_LIMIT", lambda: _req(db, "noura.qahtani", "permits"))


def test_viewer_aggregates_ac48(db: Session) -> None:
    job = _req(db, "sarah.mitchell", "heat_patrols")
    _, rows = _csv(db, job)
    assert [h.lower() for h in rows[0][:3]] == ["month", "contractor", "records"]
    assert not any("photo" in h.lower() for h in rows[0])
    permits = _req(db, "sarah.mitchell", "permits")
    _, prow = _csv(db, permits)
    assert not any("name" in h.lower() for h in prow[0])


def test_subscriptions_ac49(db: Session) -> None:
    n = P(db, "noura.qahtani")
    pid = project(db, "ANIA-EXP").id
    expect(
        "SUBSCRIPTION_PERSONAL_DATA",
        lambda: exports.subscribe(
            db,
            n,
            XpSubscriptionCreate(
                dataset="permits",
                project_id=pid,
                columns=["receiver_name"],
                frequency=XpFrequency.weekly,
            ),
        ),
    )
    t = tick(2026, 10, 18, 5, 30)  # Sunday
    assert exports.run_subscriptions(db, t) >= 1
    jobs = db.scalars(
        select(XpJob).where(XpJob.subscription_id.is_not(None), XpJob.created_at >= t)
    ).all()
    assert jobs and all(
        j.status == XpJobStatus.ready and j.requested_by_user_id == n.user.id for j in jobs
    )
    assert "noura.qahtani" in notified(db, "export_ready", t)


NATIVE = [
    "fitness_status",
    "heat_patrols",
    "emergency_drills",
    "field_inspections",
    "field_audits",
    "toolbox_talks",
    "waste_consignments",
    "notification_requirements",
    "lessons",
]


def test_parked_datasets_and_dashboard_print_ac50(db: Session, api: Api) -> None:
    for code in NATIVE:
        job = _req(db, "faisal.harbi", code, format=XpFormat.xlsx)
        assert job.status in (XpJobStatus.ready, XpJobStatus.queued), code
    pid = project(db, "ANIA-EXP").id
    db.commit()  # release the export-number lock before the API request's own session
    r = api.as_("faisal.harbi").get(
        f"{API}/dashboard-print",
        params={
            "project_id": str(pid),
            "period": "custom",
            "start": "2026-09-01",
            "end": "2026-09-30",
        },
    )
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"%PDF")
    assert db.scalar(
        select(AuditEntry.id).where(
            AuditEntry.action == AuditAction.export,
            AuditEntry.details["dataset"].astext == "dashboard_pdf",
        )
    )
