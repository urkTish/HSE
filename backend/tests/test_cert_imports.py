"""4-third-party-cert §9 ACs 98-102 (certificate imports: dry run, commit, IDs, IM-6, W05)."""

import csv
import io
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now, set_now
from app.models import (
    CertImportBatch,
    CertVerification,
    EquipmentCertificate,
    EquipmentDeployment,
    EquipmentItem,
    PersonnelCertificate,
)
from tests.cert_helpers import API, err_code, project, tpi
from tests.conftest import Api

pytestmark = pytest.mark.usefixtures("cert_seed", "clock")

EQ_HEAD = ["project_code", "tag", "category", "manufacturer", "serial_no", "tpi_code", "cert_no",
           "inspection_type", "inspected_on", "issued_on", "printed_next_due", "result", "swl_t"]  # fmt: skip
CATS = ("lifting_accessory", "mewp", "forklift", "telehandler", "excavator", "mobile_crane")


def to_csv(head: list[str], rows: list[dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=head)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in head})
    return buf.getvalue().encode()


def eq_rows(db: Session, n: int = 120, prefix: str = "AICC-EQ-TEST-26-I") -> list[dict[str, Any]]:
    pid = project(db, "ANIA-EXP").id
    rows = []
    q = (
        select(EquipmentDeployment, EquipmentItem)
        .join(EquipmentItem, EquipmentItem.id == EquipmentDeployment.equipment_id)
        .where(EquipmentDeployment.project_id == pid, EquipmentDeployment.tag.like("FX-%-A%"),
               EquipmentItem.service_status == "in_service")
        .order_by(EquipmentDeployment.tag)
    )  # fmt: skip
    for d, it in db.execute(q).all():
        if it.category.value not in CATS:
            continue
        rows.append({"project_code": "ANIA-EXP", "tag": d.tag, "category": it.category.value,
                     "manufacturer": it.manufacturer, "serial_no": it.serial_no, "tpi_code": "AICC",
                     "cert_no": f"{prefix}{len(rows):03d}", "inspection_type": "periodic",
                     "inspected_on": "2026-10-01", "issued_on": "2026-10-01", "result": "pass",
                     "swl_t": str(it.rated_capacity_t) if it.rated_capacity_t is not None else ""})  # fmt: skip
        if len(rows) == n:
            break
    assert len(rows) == n, len(rows)
    return rows


def upload(api: Api, db: Session, who: str, content: bytes, template: str = "equipment_certificates",
           name: str = "certs.csv", **form: Any) -> Any:  # fmt: skip
    files: dict[str, Any] = {"file": (name, content, "text/csv")}
    if "evidence" in form:
        files["evidence_file"] = ("tpi-email.eml", form.pop("evidence"), "message/rfc822")
    data = {"template": template, **{k: str(v) for k, v in form.items()}}
    return api.as_(who).post(
        f"{API}/projects/{project(db, 'ANIA-EXP').id}/certificate-imports", data=data, files=files
    )


def codes(body: dict[str, Any]) -> list[str]:
    return [c for r in body.get("report", []) for c in r["codes"]]


def test_P4AC98_dry_run_errors_warnings_and_commit_window(api: Api, db: Session) -> None:
    rows = eq_rows(db)
    for r in rows[:3]:
        r["tpi_code"] = "NOPE"
    for r in rows[3:5]:
        r["serial_no"] = r["serial_no"] + "X"
    acc = [r for r in rows[5:] if r["category"] == "lifting_accessory"][:5]
    for r in acc:
        r["printed_next_due"] = "2027-09-30"
    res = upload(api, db, "noura.qahtani", to_csv(EQ_HEAD, rows))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["counts"]["rows_total"] == 120
    assert body["counts"]["rows_error"] == 5, body["counts"]
    assert body["counts"]["rows_warning"] == 5, body["counts"]
    assert sorted(c for c in codes(body) if c.startswith("E")) == ["E04"] * 3 + ["E05"] * 2
    assert codes(body).count("W01") == 5
    bid = body["id"]
    set_now(now() + timedelta(minutes=61))
    late = api.as_("noura.qahtani").post(f"{API}/certificate-imports/{bid}/commit")
    assert late.status_code == 409 and err_code(late) == "IMPORT_EXPIRED", late.text


def test_P4AC99_committed_rows_are_submitted_never_accepted(api: Api, db: Session) -> None:
    rows = eq_rows(db, 6, "AICC-EQ-TEST-26-J")
    res = upload(api, db, "noura.qahtani", to_csv(EQ_HEAD, rows))
    assert res.status_code == 201, res.text
    res = api.as_("noura.qahtani").post(f"{API}/certificate-imports/{res.json()['id']}/commit")
    assert res.status_code == 200, res.text
    db.expire_all()
    certs = db.scalars(
        select(EquipmentCertificate).where(EquipmentCertificate.cert_no.like("AICC-EQ-TEST-26-J%"))
    ).all()
    assert len(certs) == 6
    assert {c.status.value for c in certs} <= {"submitted", "draft"}
    assert all(c.verification_status.value == "not_verified" for c in certs)


PC_HEAD = ["worker_no", "id_type", "id_number", "cert_type", "tpi_code", "cert_no", "issued_on",
           "level", "name_as_printed", "id_on_card"]  # fmt: skip


def test_P4AC100_personnel_ids_masked_and_never_stored(api: Api, db: Session) -> None:
    from tests.cert_helpers import worker

    z = worker(db, "WKR-000019")
    rows = [{"worker_no": "WKR-000019", "id_type": "iqama", "id_number": "2000001019",
             "cert_type": "RIGGER", "tpi_code": "AICC", "cert_no": "AICC-RG-TEST-26-1100",
             "issued_on": "2026-10-01", "level": "2", "name_as_printed": z.full_name_en,
             "id_on_card": "same_as_lookup"}]  # fmt: skip
    content = to_csv(PC_HEAD, rows)
    res = upload(api, db, "noura.qahtani", content, "personnel_certificates")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["sensitive"] is True
    assert "2000001019" not in res.text
    full = api.as_("noura.qahtani").get(
        f"{API}/certificate-imports/{body['id']}", params={"include_ok_rows": "true"}
    )
    assert full.status_code == 200, full.text
    assert "2000001019" not in full.text
    assert full.json()["report"][0]["id_masked"] == "2*******19"
    res = api.as_("noura.qahtani").post(f"{API}/certificate-imports/{body['id']}/commit")
    assert res.status_code == 200, (res.text, full.json()["report"])
    db.expire_all()
    b = db.get(CertImportBatch, body["id"])
    assert b is not None and "2000001019" not in str(b.rows) and "2000001019" not in str(b.report)
    pc = db.scalar(
        select(PersonnelCertificate).where(PersonnelCertificate.cert_no == "AICC-RG-TEST-26-1100")
    )
    assert pc is not None
    assert "2000001019" not in str({k: v for k, v in pc.__dict__.items() if not k.startswith("_")})
    assert pc.id_match_result.value == "matched"


def test_P4AC101_register_file_needs_hse_and_verifies(api: Api, db: Session) -> None:
    rows = eq_rows(db, 2, "AICC-EQ-TEST-26-K")
    content = to_csv(EQ_HEAD, rows)
    t = tpi(db, "AICC")
    email = b"From: AICC Certificates <certs@verify.aicc-test.example>\nSubject: register\n\nList attached."
    res = upload(
        api, db, "ahmed.zahrani", content, source="tpi_register_file", tpi_id=t.id, evidence=email
    )
    assert res.status_code == 403, res.text
    res = upload(
        api, db, "noura.qahtani", content, source="tpi_register_file", tpi_id=t.id, evidence=email
    )
    assert res.status_code == 201, res.text
    bid = res.json()["id"]
    res = api.as_("noura.qahtani").post(f"{API}/certificate-imports/{bid}/commit")
    assert res.status_code == 200, res.text
    db.expire_all()
    b = db.get(CertImportBatch, bid)
    assert b is not None
    for c in db.scalars(
        select(EquipmentCertificate).where(EquipmentCertificate.cert_no.like("AICC-EQ-TEST-26-K%"))
    ):
        v = db.scalar(select(CertVerification).where(CertVerification.cert_id == c.id))
        assert v is not None
        assert (v.method.value, v.outcome.value, v.reference) == (
            "tpi_register_file",
            "confirmed",
            (b.evidence_sha256 or "")[:100],
        )


def test_P4AC102_same_file_twice_warns_w05(api: Api, db: Session) -> None:
    content = to_csv(EQ_HEAD, eq_rows(db, 3, "AICC-EQ-TEST-26-L"))
    first = upload(api, db, "noura.qahtani", content)
    assert first.status_code == 201
    assert (
        api.as_("noura.qahtani")
        .post(f"{API}/certificate-imports/{first.json()['id']}/commit")
        .status_code
        == 200
    )
    res = upload(api, db, "noura.qahtani", content)
    assert res.status_code == 201, res.text
    body = res.json()
    assert "W05" in codes(body) or "W05" in str(body.get("file_issues"))
