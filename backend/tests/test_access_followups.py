"""Backend issues reported by the frontend agent (docs/PROGRESS.md) and coordinator follow-ups."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.core.access_enums import InductionType
from app.models import InductionCourse
from tests.access_helpers import API, gate, project_id, vehicle, wap, worker
from tests.conftest import Api, Ids
from tests.test_access_gates import card, codes, scan

pytestmark = pytest.mark.usefixtures("access_seed", "noon")


def test_history_serves_phase2_entity_types(api: Api, db: Session) -> None:
    n = api.as_("noura.qahtani")
    w = worker(db, "Rajesh Nair")
    res = n.patch(f"{API}/workers/{w.id}", json={"primary_language": "en"})
    assert res.status_code == 200, res.text
    res = n.get(f"{API}/history/worker/{w.id}")
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert items and items[0]["action"] == "update"
    for et, oid in (
        ("gate", gate(db, "G-AAP3").id),
        ("vehicle", vehicle(db, "VEH-0002").id),
        ("wap", wap(db, "2026-0031").id),
    ):
        res = n.get(f"{API}/history/{et}/{oid}")
        assert res.status_code == 200, (et, res.text)
    # a record outside the caller's projects stays hidden
    res = n.get(f"{API}/history/gate/{gate(db, 'G-RBT-01').id}")
    assert res.status_code in (403, 404), res.text
    res = n.get(f"{API}/history/wap/{uuid.uuid4()}")
    assert res.status_code == 404


def test_wap_supervisor_hidden_without_worker_view(api: Api, db: Session) -> None:
    w = wap(db, "2026-0031")
    body = api.as_("sarah.mitchell").get(f"{API}/waps/{w.id}").json()
    assert body.get("supervisor") is None and body["crew"] == []
    full = api.as_("noura.qahtani").get(f"{API}/waps/{w.id}").json()
    assert full["supervisor"]["worker_no"].startswith("WKR-")


def test_site_gate_accepts_any_active_general_course(api: Api, db: Session) -> None:
    """GC-4: a second general_site course (created first, inactive or not taken) must not make
    GEN holders fail with INDUCTION_MISSING."""
    pid = project_id(db, "ANIA-EXP")
    for code, active in (("A-GEN", True), ("0-GEN", False)):
        db.add(
            InductionCourse(
                id=uuid.uuid4(), project_id=pid, code=code,
                induction_type=InductionType.general_site,
                name_en=f"{code} TEST", name_ar=f"{code} اختبار", version="1",
                validity_months=12, min_duration_minutes=30, test_required=False, active=active,
                created_at=datetime(2020, 1, 1, tzinfo=UTC),
            )
        )  # fmt: skip
    db.commit()
    r = scan(api.as_("noura.qahtani"), db, "G-ANIA-01", payload=card(db, "Waleed Saleh"))
    assert r["result"] in ("GRANTED", "GRANTED_WITH_WARNING"), r
    assert "INDUCTION_MISSING" not in codes(r)


def test_banned_worker_scans_worker_banned(api: Api, db: Session) -> None:
    n = api.as_("faisal.harbi")
    payload = card(db, "Waleed Saleh")
    w = worker(db, "Waleed Saleh")
    res = n.post(
        f"{API}/workers/{w.id}/transitions",
        json={"to_status": "banned", "reason": "Repeated serious safety breach TEST"},
    )
    assert res.status_code == 200, res.text
    r = scan(n, db, "G-ANIA-01", payload=payload)
    assert r["result"] == "DENIED" and codes(r) == ["WORKER_BANNED"], r


def test_field_errors_carry_arabic(api: Api, ids: Ids) -> None:
    n = api.as_("noura.qahtani")
    res = n.post(f"{API}/projects/{ids.project('ANIA-EXP')}/gates", json={"gate_code": ""})
    assert res.status_code == 422
    errs = res.json()["detail"]["errors"]
    assert errs and all(e["msg_ar"] for e in errs)
    assert any(e["type"] == "missing" and e["msg_ar"] == "هذا الحقل مطلوب." for e in errs)
    res = n.post(f"{API}/gate-checks", json={"gate_id": str(uuid.uuid4())})
    assert res.status_code in (404, 422)
    w = n.get(f"{API}/workers", params={"page_size": 1}).json()["items"][0]
    res = n.post(
        f"{API}/workers/{w['id']}/transitions", json={"to_status": "banned", "reason": "short"}
    )
    assert res.status_code == 422
    assert all(e.get("msg_ar") for e in res.json()["detail"]["errors"])
