"""Helpers of the Q2 tests."""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models.quality import QSupplier
from tests.conftest import Ids
from tests.quality.q0.qh import API, PDF, attach, err, ok

__all__ = ["API", "PDF", "attach", "err", "ok"]


def supplier(code: str) -> str:
    with get_sessionmaker()() as db:
        sid = db.scalar(select(QSupplier.id).where(QSupplier.supplier_code == code))
        assert sid is not None, code
        return str(sid)


def new_test(c: TestClient, ids: Ids, code: str = "CONC-CYL", project: str = "ANIA-EXP", **kw: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "test_type_code": code,
        "site_id": ids.site("S-LAND" if project == "ANIA-EXP" else "S-DC1"),
        "location_ref": "Level 3 slab, grid C14",
        "lab_supplier_id": supplier("LAB-RGM"),
    }
    if project == "ANIA-EXP":
        body["engagement_id"] = ids.engagement("RAWABI")
    body.update(kw)
    return ok(c.post(f"{API}/projects/{ids.project(project)}/quality/tests", json=body), 201)


def to_lab(c: TestClient, t: dict[str, Any], sampled_at: str = "2026-09-08T10:40:00+03:00", **kw: Any) -> dict[str, Any]:
    body = {"sampled_at": sampled_at, "sample_ref": f"S-{uuid.uuid4().hex[:6]}", **kw}
    ok(c.post(f"{API}/quality/tests/{t['id']}/sample", json=body))
    return ok(c.post(f"{API}/quality/tests/{t['id']}/deliver", json={}))


def specimen_values(t: dict[str, Any], age: int, values: list[str], key: str = "strength") -> list[dict[str, Any]]:
    specs = [s for s in t["specimens"] if s["age_days"] == age and not s["spare"]]
    return [{"id": s["id"], "values": {key: v}} for s, v in zip(specs, values, strict=False)]


def results(c: TestClient, t: dict[str, Any], specimens: list[dict[str, Any]] | None = None, *, report: bool = True, **kw: Any) -> Any:
    if report:
        attach(c, "q_test_report", t["id"], "lab-report.pdf")
    body = {"report_no": "RGM-26-11873", "specimens": specimens or [], **kw}
    return c.post(f"{API}/quality/tests/{t['id']}/results", json=body)
