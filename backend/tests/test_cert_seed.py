"""Phase 4 seed self-test: every Phase 4 list and detail GET answers 200 for every seeded row
(seeded JSON matches the readers), and the seed is idempotent and gate-consistent."""

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CertificationBan,
    EquipmentCertificate,
    EquipmentDefect,
    EquipmentDeployment,
    EquipmentItem,
    PersonnelCertificate,
    Project,
    Scaffold,
    Tpi,
    TpiClientApproval,
)
from tests.cert_helpers import API, eq_payload, reasons, scan
from tests.conftest import Api

pytestmark = pytest.mark.usefixtures("cert_seed", "clock")

PROJECT_LISTS = [
    "equipment-deployments",
    "equipment-certificates",
    "personnel-certificates",
    "scaffolds",
    "scaffold-board",
    "defects",
    "verification-log",
    "tpi-approvals",
    "certificate-imports",
    "cert-settings",
    "hook-policy",
]


def test_every_phase4_get_answers_200_for_every_seeded_row(api: Api, db: Session) -> None:
    c = api.as_("faisal.harbi")
    bad: list[tuple[str, int, str]] = []

    def get(path: str, **params: Any) -> Any:
        res = c.get(f"{API}{path}", params=params)
        if res.status_code != 200:
            bad.append((path, res.status_code, res.text[:200]))
        return res

    for pid in db.scalars(select(Project.id)):
        for sub in PROJECT_LISTS:
            res = get(f"/projects/{pid}/{sub}", page_size=200)
            body = res.json() if res.status_code == 200 else None
            if isinstance(body, dict) and "total" in body:
                for pg in range(2, (body["total"] + 199) // 200 + 1):
                    get(f"/projects/{pid}/{sub}", page_size=200, page=pg)
        for kind in ("personnel_certificate", "equipment_certificate"):
            get(f"/projects/{pid}/hook-readiness", kind=kind)
        get("/kpi/certification", project_id=pid)
        for ch in ("C16", "C17", "C18"):
            get(f"/kpi/charts/{ch}", project_id=pid)
        get("/dashboard/action-panel", project_id=pid)
        get("/dashboard/expiring-items", project_id=pid, within_days=90, include_overdue="true")
        get("/kpi/dashboard", project_id=pid)
    for path in ("/tpis", "/equipment", "/certification-bans", "/cert-catalogue"):
        get(path, page_size=200)
    for t in db.scalars(select(Tpi.id)):
        get(f"/tpis/{t}")
        get(f"/tpis/{t}/affected")
    for a in db.scalars(select(TpiClientApproval.id)):
        get(f"/tpi-approvals/{a}")
    for x in db.scalars(select(EquipmentItem.id)):
        get(f"/equipment/{x}")
        get(f"/equipment/{x}/status-events")
        get(f"/equipment/{x}/configuration-events")
    for x in db.scalars(select(EquipmentDeployment.id)):
        get(f"/equipment-deployments/{x}")
    for x in db.scalars(select(EquipmentCertificate.id)):
        get(f"/equipment-certificates/{x}")
        get(f"/equipment-certificates/{x}/verifications")
    for x in db.scalars(select(PersonnelCertificate.id)):
        get(f"/personnel-certificates/{x}")
        get(f"/personnel-certificates/{x}/verifications")
    for x in db.scalars(select(Scaffold.id)):
        get(f"/scaffolds/{x}")
        get(f"/scaffolds/{x}/inspections")
    for x in db.scalars(select(EquipmentDefect.id)):
        get(f"/defects/{x}")
    for x in db.scalars(select(CertificationBan.id)):
        get(f"/certification-bans/{x}")
    for w in set(db.scalars(select(PersonnelCertificate.worker_id))):
        get(f"/workers/{w}/certificates")
    assert bad == []


def test_seed_is_idempotent(db: Session) -> None:
    from app.seed_cert import seed_cert_data

    before = db.scalar(select(func.count()).select_from(EquipmentCertificate))
    seed_cert_data(db)
    db.flush()
    assert db.scalar(select(func.count()).select_from(EquipmentCertificate)) == before


def test_P4AC22_P4AC94_seeded_stickers_at_the_gate(api: Api, db: Session) -> None:
    """SH-TH-02's old sticker was revoked at demobilisation (CREDENTIAL_REVOKED, before
    EQUIPMENT_BLACKLISTED, GE-2); RW-MEWP-07 is DENIED out of service."""
    c = api.as_("faisal.harbi")
    r = scan(c, db, "G-ANIA-01", printed_ref="ANIA-EXP-SH-TH-02")
    assert r["result"] == "DENIED"
    assert reasons(r)[0] == "CREDENTIAL_REVOKED"
    r = scan(c, db, "G-ANIA-01", payload=eq_payload(db, "SH-TH-02"))
    assert reasons(r)[0] == "CREDENTIAL_REVOKED"
    r = scan(c, db, "G-ANIA-01", payload=eq_payload(db, "RW-MEWP-07"))
    assert r["result"] == "DENIED"
    assert "EQUIPMENT_OUT_OF_SERVICE" in reasons(r)
