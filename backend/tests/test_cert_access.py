"""4-third-party-cert §9 ACs 95-97 (gate equipment check) and 107-113 (permissions, PDPL)."""

import uuid
from datetime import date
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Attachment,
    AuditEntry,
    Contractor,
    GateCheck,
    PersonnelCertificate,
    Site,
    Zone,
)
from tests.cert_helpers import (
    API,
    eq_payload,
    err_code,
    item,
    pcert,
    project,
    reasons,
    scaffold,
    scan,
    tpi,
    upload_pdf,
    worker,
)
from tests.conftest import Api

pytestmark = pytest.mark.usefixtures("cert_seed", "clock")


# ---- gate (AC95-97) ---------------------------------------------------------------------------


def test_P4AC95_linked_vehicle_item_also_scan_vehicle_sticker(api: Api, db: Session) -> None:
    z = db.scalar(select(Zone.id).where(Zone.code == "Z-APR-21"))
    r = scan(
        api.as_("noura.qahtani"), db, "G-AAP3", payload=eq_payload(db, "RW-MC-03"), zone_id=str(z)
    )
    assert r["result"] == "GRANTED_WITH_WARNING", r
    assert "ALSO_SCAN_VEHICLE_STICKER" in reasons(r)


def test_P4AC96_eq_scans_are_not_people_checks(api: Api, db: Session) -> None:
    from app.kpi.access_facts import load_access

    pid = project(db, "ANIA-EXP").id

    def gate_total() -> int:
        return sum(g.n for g in load_access(db, [pid]).gate)

    before = gate_total()
    c = api.as_("noura.qahtani")
    for _ in range(40):
        scan(c, db, "G-ANIA-01", payload=eq_payload(db, "RW-MC-03"))
    db.expire_all()
    assert gate_total() == before
    rows = db.scalars(select(GateCheck).where(GateCheck.equipment_deployment_id.is_not(None))).all()
    assert len(rows) >= 40 and {r.subject_kind.value for r in rows} == {"equipment_deployment"}
    res = c.get(f"{API}/projects/{pid}/gate-log", params={"subject_kind": "equipment_deployment"})
    assert res.status_code == 200, res.text
    assert res.json()["total"] >= 40


def test_P4AC97_admitted_despite_denial_for_equipment(api: Api, db: Session) -> None:
    from app.core.enums import NotificationKind
    from app.models import Notification

    c = api.as_("noura.qahtani")
    r = scan(c, db, "G-ANIA-01", payload=eq_payload(db, "RW-MEWP-07"))
    assert r["result"] == "DENIED"
    res = c.post(f"{API}/gate-checks/{r['check_id']}/admitted-despite-denial",
                 json={"reason": "Recovery vehicle collecting the MEWP (test)"})  # fmt: skip
    assert res.status_code in (200, 201), res.text
    db.expire_all()
    row = db.get(GateCheck, uuid.UUID(r["check_id"]))
    assert row is not None and row.admitted_despite_denial is True
    assert db.scalar(
        select(Notification.id).where(Notification.kind == NotificationKind.admitted_despite_denial)
    )


# ---- permissions and PDPL (AC107-113) ---------------------------------------------------------


def test_P4AC107_viewer_cannot_list_personnel_certificates(api: Api, db: Session) -> None:
    res = api.as_("sarah.mitchell").get(
        f"{API}/projects/{project(db, 'ANIA-EXP').id}/personnel-certificates"
    )
    assert res.status_code == 403, res.text


def test_P4AC108_rep_scope_and_scan_url(api: Api, db: Session) -> None:
    from app.models import Deployment, ProjectEngagement

    pid = project(db, "RBT-52").id
    y = api.as_("yousef.ghamdi")
    res = y.get(f"{API}/projects/{pid}/personnel-certificates", params={"page_size": 200})
    assert res.status_code == 200, res.text
    tree = {
        c.id
        for c in db.scalars(select(Contractor).where(Contractor.short_code.in_(["QIMMA", "DLIFT"])))
    }
    for row in res.json()["items"]:
        pc = db.get(PersonnelCertificate, uuid.UUID(row["id"]))
        assert pc is not None
        eng = db.scalar(select(ProjectEngagement.contractor_id).join(
            Deployment, Deployment.engagement_id == ProjectEngagement.id).where(
            Deployment.worker_id == pc.worker_id, Deployment.project_id == pid))  # fmt: skip
        assert eng in tree
    joel = worker(db, "WKR-000108")
    body = {"worker_id": str(joel.id), "cert_type": "SIGNALLER", "tpi_id": str(tpi(db, "AICC").id),
            "cert_no": "AICC-SG-TEST-26-1108", "issued_on": "2026-10-01",
            "name_as_printed": joel.full_name_en, "id_on_card": {"shown": False}}  # fmt: skip
    res = y.post(f"{API}/projects/{pid}/personnel-certificates", json=body)
    assert res.status_code in (200, 201), res.text
    cid = res.json()["id"]
    upload_pdf(y, "personnel_cert_scan", cid)
    url = f"{API}/personnel-certificates/{cid}/scan-url"
    assert y.post(url, json={"side": "front"}).status_code == 422
    res = y.post(url, json={"side": "front", "reason": "verification"})
    assert res.status_code == 200, res.text
    from datetime import UTC, datetime

    exp = datetime.fromisoformat(res.json()["expires_at"].replace("Z", "+00:00"))
    assert (exp - datetime.now(UTC)).total_seconds() <= 300  # signed with the wall clock
    db.expire_all()
    from app.core.enums import AuditAction

    assert db.scalar(select(AuditEntry.id).where(
        AuditEntry.action == AuditAction.sensitive_field_read, AuditEntry.entity_id == uuid.UUID(cid)))  # fmt: skip


def test_P4AC109_site_engineer_inspects_but_cannot_accept(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    land = db.scalar(select(Site.id).where(Site.code == "S-LAND", Site.project_id == pid))
    tags = [f"SC-{n:04d}" for n in range(160, 254)]
    sc = next(s for s in (scaffold(db, t) for t in tags)
              if s.status.value == "in_use" and db.get(Zone, s.zone_id).site_id == land)  # type: ignore[union-attr]  # fmt: skip
    body = {"inspection_type": "periodic", "inspector_worker_id": str(worker(db, "WKR-000023").id),
            "checklist": [{"item": f"SIC-{i:02d}", "result": "pass"} for i in range(1, 12)],
            "result": "green"}  # fmt: skip
    res = api.as_("fahad.mutairi").post(f"{API}/scaffolds/{sc.id}/inspections", json=body)
    assert res.status_code in (200, 201), res.text
    from tests.cert_helpers import ec_body, ec_submitted, line

    cert = ec_submitted(api.as_("noura.qahtani"), db, "ANIA-EXP",
                        ec_body(db, "AICC", "AICC-EQ-TEST-26-1109", date(2026, 10, 5), [line(db, "FX-FL-06")]))  # fmt: skip
    res = api.as_("fahad.mutairi").post(f"{API}/equipment-certificates/{cert['id']}/transitions",
                                        json={"to_status": "accepted"})  # fmt: skip
    assert res.status_code == 403, res.text


def test_P4AC110_suspended_contractor_rep_reads_but_cannot_submit(api: Api, db: Session) -> None:
    from app.core.enums import ContractorStatus

    rw = db.scalar(select(Contractor).where(Contractor.short_code == "RAWABI"))
    assert rw is not None
    rw.status = ContractorStatus.suspended
    db.commit()
    a = api.as_("ahmed.zahrani")
    pid = project(db, "ANIA-EXP").id
    assert a.get(f"{API}/projects/{pid}/personnel-certificates").status_code == 200
    w = worker(db, "WKR-000019")
    body = {"worker_id": str(w.id), "cert_type": "SIGNALLER", "tpi_id": str(tpi(db, "AICC").id),
            "cert_no": "AICC-SG-TEST-26-1110", "issued_on": "2026-10-01",
            "name_as_printed": w.full_name_en, "id_on_card": {"shown": False}}  # fmt: skip
    res = a.post(f"{API}/projects/{pid}/personnel-certificates", json=body)
    assert res.status_code == 403, res.text
    assert err_code(res) == "CONTRACTOR_SUSPENDED"


def test_P4AC111_register_export_without_names(
    api: Api, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.cert import exports

    # Omar holds capability 46 in the Phase 0 seed; the AC is about a caller without it.
    monkeypatch.setattr(exports.acommon, "can_see_names", lambda p, pid: False)
    res = api.as_("omar.siddiqui").get(
        f"{API}/exports/personnel_certificates",
        params={"project_id": str(project(db, "ANIA-EXP").id), "format": "csv"},
    )
    assert res.status_code == 200, res.text
    head = res.text.lstrip("\ufeff").splitlines()[0].lower().split(",")
    assert "worker_no" in head
    bad = [
        h
        for h in head
        if h != "name_match" and any(k in h for k in ("name", "id_number", "scan", "medical"))
    ]
    assert bad == [], head
    assert "Zaheer" not in res.text
    res = api.as_("faisal.harbi").get(
        f"{API}/exports/equipment_certificates",
        params={"project_id": str(project(db, "ANIA-EXP").id), "format": "csv"},
    )
    assert res.status_code == 200, res.text


def test_P4AC112_scan_retention(api: Api, db: Session) -> None:
    from app.services.cert import personnel

    c = api.as_("noura.qahtani")
    w = worker(db, "WKR-000009")
    body = {"worker_id": str(w.id), "cert_type": "SIGNALLER", "tpi_id": str(tpi(db, "AICC").id),
            "cert_no": "AICC-SG-TEST-23-0101", "issued_on": "2026-10-01",
            "name_as_printed": w.full_name_en, "id_on_card": {"shown": False}}  # fmt: skip
    res = c.post(f"{API}/projects/{project(db, 'ANIA-EXP').id}/personnel-certificates", json=body)
    assert res.status_code in (200, 201), res.text
    cid = uuid.UUID(res.json()["id"])
    upload_pdf(c, "personnel_cert_scan", cid)
    from app.core.cert_enums import CertificateStatus

    db.expire_all()
    pc = db.get(PersonnelCertificate, cid)
    assert pc is not None
    pc.status, pc.ended_on = CertificateStatus.expired, date(2024, 10, 5)
    db.commit()
    old = pcert(db, "AICC-RG-TEST-24-0601")  # ended < 2 years ago: untouched
    assert personnel.scan_retention_job(db, date(2026, 10, 6)) == 1
    db.commit()
    db.expire_all()
    pc = db.get(PersonnelCertificate, cid)
    assert (
        pc is not None
        and pc.cert_no == "AICC-SG-TEST-23-0101"
        and pc.scan_front_attachment_id is None
    )
    assert db.scalar(select(Attachment.id).where(Attachment.owner_id == cid)) is None
    from app.core.enums import AuditAction

    assert db.scalar(select(AuditEntry.id).where(
        AuditEntry.action == AuditAction.retention_purge, AuditEntry.entity_id == cid))  # fmt: skip
    _ = old


def test_P4AC113_mutations_audited_without_id_numbers(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    z = worker(db, "WKR-000019")
    body = {"worker_id": str(z.id), "cert_type": "SIGNALLER", "tpi_id": str(tpi(db, "AICC").id),
            "cert_no": "AICC-SG-TEST-26-1113", "issued_on": "2026-10-01",
            "name_as_printed": z.full_name_en,
            "id_on_card": {"shown": True, "id_type": "iqama", "id_number": "2000001019"}}  # fmt: skip
    a = api.as_("ahmed.zahrani")
    res = a.post(f"{API}/projects/{pid}/personnel-certificates", json=body)
    assert res.status_code in (200, 201), res.text
    pc_id = uuid.UUID(res.json()["id"])
    it = item(db, "FX-FL-A018")
    res = api.as_("noura.qahtani").post(
        f"{API}/equipment/{it.id}/tag-out",
        json={
            "project_id": str(pid),
            "reason": "Mast chain damaged (test)",
            "physical_tag_applied": True,
        },
    )
    assert res.status_code == 200, res.text
    db.expire_all()
    for eid in (pc_id, it.id):
        rows = db.scalars(select(AuditEntry).where(AuditEntry.entity_id == eid)).all()
        assert rows and any(r.after for r in rows), eid
    blob: list[Any] = [(r.before, r.after, r.details) for r in db.scalars(select(AuditEntry))]
    assert "2000001019" not in str(blob)
