"""Spec 2-access-permits §9 AC1-AC8 (worker register & PDPL) and the seed CI checks (A.1, AC64)."""

import re

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.enums import AuditAction
from app.models import AuditEntry, QrToken, Vehicle, Worker
from app.services.access import common
from tests.access_helpers import API, worker
from tests.conftest import Api, Ids

pytestmark = pytest.mark.usefixtures("access_seed", "noon")


def new_worker(ids: Ids, id_number: str, **over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "person_type": "contractor_worker",
        "full_name_en": "Test Person",
        "full_name_ar": "شخص تجريبي",
        "id_type": "iqama",
        "id_number": id_number,
        "id_expiry_date": "2028-01-01",
        "nationality": "IN",
        "adult_attestation": True,
        "primary_language": "hi",
        "deployment": {
            "project_id": ids.project("ANIA-EXP"),
            "engagement_id": ids.engagement("GULFPAVE"),
            "trade": "labourer",
            "site_ids": [ids.site("S-LAND")],
            "mobilised_on": "2026-10-06",
        },
    }
    body.update(over)
    return body


def test_P2AC1_duplicate_iqama_in_scope_names_existing_worker(api: Api, ids: Ids) -> None:
    res = api.as_("ahmed.zahrani").post(f"{API}/workers", json=new_worker(ids, "2000001002"))
    assert res.status_code == 409, res.text
    d = res.json()["detail"]
    assert d["code"] == "WORKER_EXISTS"
    assert d["meta"]["worker_no"] == "WKR-000002"


def test_P2AC2_duplicate_out_of_scope_reveals_nothing(api: Api, ids: Ids) -> None:
    body = new_worker(
        ids,
        "2000001002",
        deployment={
            "project_id": ids.project("RBT-52"),
            "engagement_id": ids.engagement("QIMMA"),
            "trade": "labourer",
            "site_ids": [ids.site("S-TWR")],
            "mobilised_on": "2026-10-06",
        },
    )
    res = api.as_("yousef.ghamdi").post(f"{API}/workers", json=body)
    assert res.status_code == 409, res.text
    d = res.json()["detail"]
    assert d["code"] == "WORKER_EXISTS_OUT_OF_SCOPE"
    text = res.text
    for leak in ("WKR-000002", "Rajesh", "GULFPAVE", "راجيش"):
        assert leak not in text


def test_P2AC3_list_shows_masked_id_only(api: Api, ids: Ids) -> None:
    res = api.as_("noura.qahtani").get(
        f"{API}/workers", params={"project_id": ids.project("ANIA-EXP"), "q": "Rajesh"}
    )
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert items and items[0]["id_number_masked"] == "2*******02"
    assert "2000001002" not in res.text


def test_P2AC4_unmask_returns_number_and_audits(api: Api, ids: Ids, db: Session) -> None:
    w = worker(db, "Rajesh Nair")
    res = api.as_("noura.qahtani").post(
        f"{API}/workers/{w.id}/id-number/unmask", json={"reason": "pass_application"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["id_number"] == "2000001002"
    db.expire_all()
    row = db.scalar(
        select(AuditEntry).where(
            AuditEntry.action == AuditAction.sensitive_field_read, AuditEntry.entity_id == w.id
        )
    )
    assert row is not None and row.fields_read == ["id_number"]


def test_P2AC5_engineer_cannot_unmask_and_viewer_cannot_list(
    api: Api, ids: Ids, db: Session
) -> None:
    w = worker(db, "Rajesh Nair")
    res = api.as_("omar.siddiqui").post(
        f"{API}/workers/{w.id}/id-number/unmask", json={"reason": "pass_application"}
    )
    assert res.status_code == 403, res.text
    res = api.as_("sarah.mitchell").get(
        f"{API}/workers", params={"project_id": ids.project("ANIA-EXP")}
    )
    assert res.status_code == 403, res.text


def test_P2AC6_adult_attestation_required(api: Api, ids: Ids) -> None:
    body = new_worker(ids, "2000009990", adult_attestation=False)
    res = api.as_("noura.qahtani").post(f"{API}/workers", json=body)
    assert res.status_code == 422, res.text
    assert res.json()["detail"]["code"] == "ADULT_ATTESTATION_REQUIRED"


def test_P2AC7_partial_id_never_matches(api: Api, ids: Ids) -> None:
    for who in ("noura.qahtani", "faisal.harbi"):
        res = api.as_(who).get(f"{API}/workers", params={"q": "2000001"})
        assert res.status_code == 200, res.text
        assert res.json()["items"] == []
    res = api.as_("noura.qahtani").post(
        f"{API}/workers/lookup", json={"id_type": "iqama", "id_number": "2000001"}
    )
    assert res.status_code in (200, 422), res.text
    if res.status_code == 200:
        assert not res.json().get("found")


def test_P2AC8_id_numbers_encrypted_at_rest(db: Session) -> None:
    rows = db.execute(
        select(Worker.worker_no, Worker.id_number_enc, Worker.id_type, Worker.id_number_bidx)
    ).all()
    assert len(rows) > 3000
    for no, enc, id_type, bidx in rows[:500]:
        assert enc is not None and bidx is not None, no
        plain = crypto.decrypt(enc)
        assert plain.encode() not in enc
        assert bidx != plain
    seeded = {"WKR-000002": "2000001002", "WKR-000007": "1000001007"}
    for no, number in seeded.items():
        enc = db.scalar(select(Worker.id_number_enc).where(Worker.worker_no == no))
        assert enc is not None and crypto.decrypt(enc) == number and number.encode() not in enc


ID_RE = re.compile(r"^([12]0{5}\d{4}|TEST\d{5})$")


def test_seed_ids_and_plates_follow_appendix_a1(db: Session) -> None:
    """A.1: CI check rejects any other ID or plate in the seed."""
    for (enc,) in db.execute(select(Worker.id_number_enc).where(Worker.seed_fake.is_(True))):
        assert enc is not None
        assert ID_RE.match(crypto.decrypt(enc))
    for v in db.scalars(select(Vehicle).where(Vehicle.seed_fake.is_(True))):
        if v.plate_digits:
            assert 9001 <= int(v.plate_digits) <= 9099, v.vehicle_no
        assert v.serial_or_vin.startswith(("TESTVIN", "TESTSN")), v.vehicle_no


QR_RE = re.compile(r"^HSE2:(AC|VS|WP):[A-Za-z0-9_-]{22}$")


def test_P2AC64_seed_qr_payloads_are_opaque(db: Session) -> None:
    names = {n.lower() for (n,) in db.execute(select(Worker.full_name_en)).all()}
    tokens = list(db.scalars(select(QrToken)))
    assert len(tokens) > 3000
    for t in tokens:
        p = common.payload(t)
        assert QR_RE.match(p), p
        assert not any(ch.isdigit() for ch in p[8:]) or not re.search(r"\d{10}", p)
    assert all(t.token.lower() not in names for t in tokens[:50])
