"""Helpers for Phase 4 tests (4-third-party-cert Appendix A world, clock 2026-10-06 10:00 Riyadh).

Tests use the ``cert_seed`` fixture (Phase 0-3 template + the Phase 4 seed, cloned per test) and
``clock`` (pins HSE_CLOCK_AT). Service calls take a Principal from ``P(db, "noura.qahtani")``;
API calls use ``tests.conftest.Api``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import set_now
from app.core.errors import ApiError
from app.models import (
    EquipmentCertificate,
    EquipmentDeployment,
    EquipmentItem,
    Gate,
    PersonnelCertificate,
    Project,
    QrToken,
    Scaffold,
    Tpi,
    User,
    UserSession,
    Worker,
)

API = "/api/v1"
CLOCK = datetime(2026, 10, 6, 7, 0, tzinfo=UTC)  # 10:00 Asia/Riyadh


def riyadh(y: int, m: int, d: int, h: int = 10, mi: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=UTC) - timedelta(hours=3)


def at(d: date, h: int = 10) -> None:
    """Move the pinned clock to local day `d` at hour `h`."""
    set_now(riyadh(d.year, d.month, d.day, h))


def P(db: Session, who: str) -> Any:
    from app.services.permissions import build_principal

    email = who if "@" in who else f"{who}@example.com"
    u = db.scalar(select(User).where(User.email == email))
    assert u is not None, who
    from app.core.clock import now

    sess = UserSession(
        id=uuid.uuid4(),
        user_id=u.id,
        created_at=now(),
        last_seen_at=now(),
        expires_at=now() + timedelta(hours=8),
        last_authenticated_at=now(),
    )
    return build_principal(db, u, sess)


def project(db: Session, code: str) -> Project:
    p = db.scalar(select(Project).where(Project.code == code))
    assert p is not None, code
    return p


def tpi(db: Session, code: str) -> Tpi:
    t = db.scalar(select(Tpi).where(Tpi.tpi_code == code))
    assert t is not None, code
    return t


def dep(db: Session, tag: str) -> EquipmentDeployment:
    d = db.scalar(
        select(EquipmentDeployment)
        .where(EquipmentDeployment.tag == tag)
        .order_by(EquipmentDeployment.created_at.desc())
    )
    assert d is not None, tag
    return d


def item(db: Session, tag: str) -> EquipmentItem:
    it = db.get(EquipmentItem, dep(db, tag).equipment_id)
    assert it is not None, tag
    return it


def worker(db: Session, no: str) -> Worker:
    w = db.scalar(select(Worker).where(Worker.worker_no == no))
    assert w is not None, no
    return w


def ecert(db: Session, cert_no: str) -> EquipmentCertificate:
    c = db.scalar(select(EquipmentCertificate).where(EquipmentCertificate.cert_no == cert_no))
    assert c is not None, cert_no
    return c


def pcert(db: Session, cert_no: str) -> PersonnelCertificate:
    c = db.scalar(select(PersonnelCertificate).where(PersonnelCertificate.cert_no == cert_no))
    assert c is not None, cert_no
    return c


def scaffold(db: Session, tag: str) -> Scaffold:
    s = db.scalar(select(Scaffold).where(Scaffold.tag == tag))
    assert s is not None, tag
    return s


def gate(db: Session, code: str) -> Gate:
    g = db.scalar(select(Gate).where(Gate.gate_code == code))
    assert g is not None, code
    return g


def eq_payload(db: Session, tag: str) -> str:
    from app.services.access import common

    t = db.scalar(
        select(QrToken)
        .where(QrToken.subject_id == dep(db, tag).id)
        .order_by(QrToken.created_at.desc())
    )
    assert t is not None, tag
    return common.payload(t)


def expect(code: str, fn: Callable[[], Any], status: int | None = None) -> ApiError:
    with pytest.raises(ApiError) as ei:
        fn()
    err = ei.value
    assert err.code.value == code, (err.code.value, err.message, err.meta)
    if status is not None:
        assert err.status_code == status, (err.status_code, err.message)
    return err


def err_code(res: Any) -> str:
    body = res.json()
    d = body.get("detail", body)
    return str(d.get("code") if isinstance(d, dict) else d)


def scan(c: TestClient, db: Session, gate_code: str, **body: Any) -> dict[str, Any]:
    payload = {"gate_id": str(gate(db, gate_code).id), **body}
    res = c.post(f"{API}/gate-checks", json=payload)
    assert res.status_code == 200, res.text
    out: dict[str, Any] = res.json()
    return out


def reasons(r: dict[str, Any]) -> list[str]:
    return [x["code"] for x in r["reasons"]]


# ---- certificate flows (API) ---------------------------------------------------------------------

PDF = b"%PDF-1.4\n" + b"0" * 64


def contractor(db: Session, code: str) -> Any:
    from app.models import Contractor

    c = db.scalar(select(Contractor).where(Contractor.short_code == code))
    assert c is not None, code
    return c


def line(db: Session, tag: str, **kw: Any) -> dict[str, Any]:
    it = item(db, tag)
    swl = {"swl_t": str(it.rated_capacity_t)} if it.rated_capacity_t is not None else {}
    return {"equipment_id": str(it.id), "serial_as_printed": it.serial_no, "result": "pass",
            **swl, **kw}  # fmt: skip


def ec_body(
    db: Session,
    tpi_code: str,
    cert_no: str,
    inspected: date,
    lines: list[dict[str, Any]],
    **kw: Any,
) -> dict[str, Any]:
    return {
        "tpi_id": str(tpi(db, tpi_code).id),
        "cert_no": cert_no,
        "inspection_type": kw.pop("inspection_type", "periodic"),
        "inspected_on": inspected.isoformat(),
        "issued_on": kw.pop("issued_on", inspected).isoformat(),
        "inspector_name": "Test Inspector",
        "lines": lines,
        **{k: (v.isoformat() if isinstance(v, date) else v) for k, v in kw.items()},
    }


def upload_pdf(c: TestClient, owner_type: str, owner_id: Any) -> str:
    res = c.post(
        f"{API}/attachments",
        data={"owner_type": owner_type, "owner_id": str(owner_id)},
        files={"file": ("scan.pdf", PDF, "application/pdf")},
    )
    assert res.status_code in (200, 201), res.text
    return str(res.json()["id"])


def ec_submitted(c: TestClient, db: Session, pcode: str, body: dict[str, Any]) -> dict[str, Any]:
    """Create a draft, attach its scan and Submit it (as the client's user)."""
    pid = project(db, pcode).id
    res = c.post(f"{API}/projects/{pid}/equipment-certificates", json=body)
    assert res.status_code in (200, 201), res.text
    cid = res.json()["id"]
    scan_id = upload_pdf(c, "equipment_certificate_scan", cid)
    res = c.patch(f"{API}/equipment-certificates/{cid}", json={"scan_attachment_id": scan_id})
    assert res.status_code == 200, res.text
    res = c.post(f"{API}/equipment-certificates/{cid}/transitions", json={"to_status": "submitted"})
    assert res.status_code == 200, res.text
    out: dict[str, Any] = res.json()
    return out


def verify_body(c: TestClient, kind: str, cid: Any, **kw: Any) -> dict[str, Any]:
    """A confirmed portal verification (AICC portal channel) with evidence."""
    ev = upload_pdf(c, "verification_evidence", cid)
    return {
        "method": "tpi_portal",
        "channel_used": "verify.aicc-test.example",
        "outcome": "confirmed",
        "reference": "AICC portal ref TEST-77812",
        "evidence_attachment_id": ev,
        **kw,
    }
