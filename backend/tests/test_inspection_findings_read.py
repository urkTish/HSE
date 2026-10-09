"""Phase 1 inspection findings are read in the stored shape (id, description, severity,
ca_required, ca_id); legacy rows without an id must not break the register or the detail."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Inspection
from tests.conftest import Api, Ids

API = "/api/v1"


def test_seeded_findings_read_on_register_and_detail(
    api: Api, ids: Ids, db: Session, hse_seed: None
) -> None:
    ins = db.scalars(select(Inspection).where(Inspection.findings != [])).first()
    assert ins is not None
    f = ins.findings[0]
    assert {"id", "description", "severity", "ca_required", "ca_id"} <= set(f)
    c = api.as_("faisal.harbi")
    res = c.get(f"{API}/projects/{ids.project('ANIA-EXP')}/inspections", params={"page_size": 100})
    assert res.status_code == 200, res.text
    res = c.get(f"{API}/inspections/{ins.id}")
    assert res.status_code == 200, res.text
    assert res.json()["findings"][0]["description"] == f["description"]


def test_legacy_finding_without_id_reads(api: Api, db: Session, hse_seed: None) -> None:
    ins = db.scalars(select(Inspection).where(Inspection.findings != [])).first()
    assert ins is not None
    ins.findings = [{"item": "Deficiency noted", "severity": "medium", "ca_id": None}]
    db.commit()
    c = api.as_("faisal.harbi")
    first = c.get(f"{API}/inspections/{ins.id}")
    assert first.status_code == 200, first.text
    got = first.json()["findings"][0]
    assert got["description"] == "Deficiency noted"
    assert got["ca_required"] is False
    # the derived id is stable between reads
    assert c.get(f"{API}/inspections/{ins.id}").json()["findings"][0]["id"] == got["id"]
