# ruff: noqa: E501
"""Phase 6e templates, KPIs, warnings, scope, PDPL and AR labels (6e §9 AC 48-52, 54, 57-58).
AC 53 (AI tool T22) and the exports half of AC 54 are parked (docs/PROGRESS.md)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChecklistTemplate, InspectionPlan
from app.services.env import waste
from tests.conftest import Api
from tests.env_helpers import API, P, area, eng, kpi, kpis, local, project
from tests.field_helpers import body as fbody
from tests.field_helpers import submit

pytestmark = pytest.mark.usefixtures("env_seed", "clock")

EV9 = {
    "ANIA-EXP": {"K118": "100.0 %", "K119": "717.4", "K120": "89.5 %", "K121": "97.8 %",
                 "K122": "96.9 %", "K123": "1", "K124": "4", "K125": "91.7 %", "K126": "6,960"},
    "RBT-52": {"K118": "75.0 %", "K119": "186.0", "K120": "52.9 %", "K121": "93.3 %",
               "K122": "96.0 %", "K123": "2", "K124": "1", "K125": "100.0 %", "K126": "1,215"},
}  # fmt: skip
CHIPS = {
    "ANIA-EXP": {"hazardous_t": "2.4", "intensity": "82.46", "sewage_m3": "310",
                 "l_per_mh": "8.00", "treated_pct": "62.5 %", "reportable": "1", "background": "1"},
    "RBT-52": {"hazardous_t": "3.6", "intensity": "137.78", "l_per_mh": "9.00",
               "treated_pct": "0.0 %", "reportable": "0", "background": "1"},
}  # fmt: skip


@pytest.mark.parametrize("code", ["ANIA-EXP", "RBT-52"])
def test_ev9(api: Api, db: Session, code: str) -> None:
    """AC 50 (EV9 for September 2026) with breakdowns that carry no personal data (EK-2)."""
    body = kpis(api.as_("faisal.harbi"), project(db, code).id,
                group_by=["stream", "transporter", "cause", "substance", "month"])  # fmt: skip
    got = {m: kpi(body, m)["display"] for m in EV9[code]}
    assert got == EV9[code]
    chips = {c["key"]: c["display"] for m in body["metrics"] for c in m.get("components") or []}
    assert {k: chips.get(k) for k in CHIPS[code]} == CHIPS[code]
    if code == "ANIA-EXP":
        tr = next(b for b in body["breakdowns"] if b["group_by"] == "transporter")
        assert tr["rows"][0]["key"] == "GREENHAUL"
    assert "Driver" not in str(body) and "Hamad" not in str(body)


def test_k34_k35_k110_k107_unchanged(api: Api, db: Session) -> None:
    """AC 48, 57: ENV v2 / WSA / DSN published, v1 superseded, WSA-07 airside only, plans from
    10-01; 6d K-34 / K-35 / K-110 and 6c K-107 for September unchanged; K-16 = 1."""
    rows = {(t.template_code, t.version): t.status.value for t in db.scalars(select(ChecklistTemplate))
            if t.template_code in ("ENV", "WSA", "DSN")}  # fmt: skip
    assert rows == {("ENV", 1): "superseded", ("ENV", 2): "published", ("WSA", 1): "published",
                    ("DSN", 1): "published"}  # fmt: skip
    wsa = db.scalar(select(ChecklistTemplate).where(ChecklistTemplate.template_code == "WSA"))
    assert wsa is not None
    assert [i["item_code"] for i in wsa.items if i["airside_only"]] == ["WSA-07"]
    plans = db.scalars(
        select(InspectionPlan).where(InspectionPlan.template_code.in_(("WSA", "DSN")))
    ).all()
    assert plans and all(p.start_date == date(2026, 10, 1) for p in plans)
    f = api.as_("faisal.harbi")
    q = {"as_of": "2026-09-30", "period": "month", "anchor": "2026-09-30"}
    ania = str(project(db, "ANIA-EXP").id)
    r = f.get(f"{API}/kpi/field-assurance", params={"project_id": ania, **q})
    assert r.status_code == 200, r.text
    fa = {m["metric"]: m for m in r.json()["metrics"]}
    assert (fa["K-34"]["display"], fa["K-35"]["display"]) == ("85.0 %", "92.5 %")
    # K-110 follows the generated inspections (DECISIONS #185)
    from sqlalchemy import func

    from app.models import ChecklistResponse as R

    sept = (R.project_id == project(db, "ANIA-EXP").id, R.owner_type == "inspection",
            R.voided.is_(False), R.completed_date >= date(2026, 9, 1),
            R.completed_date <= date(2026, 9, 30))  # fmt: skip
    ew, aw = db.execute(
        select(func.sum(R.earned_weight), func.sum(R.applicable_weight)).where(*sept)
    ).one()
    from decimal import Decimal

    assert (Decimal(fa["K-110"]["numerator"]), Decimal(fa["K-110"]["denominator"])) == (ew, aw)
    for code, want in (("ANIA-EXP", "96.6 %"), ("RBT-52", "94.2 %")):
        r = f.get(f"{API}/kpi/emergency", params={"project_id": str(project(db, code).id), **q})
        assert kpi(r.json(), "K107")["display"] == want
    r = f.get(f"{API}/kpi/metrics", params={"project_id": ania, "metric": "K-16", **q})
    assert r.json()["kpis"][0]["value"] == "1"


def test_wsa_answers_on_area(db: Session) -> None:
    """AC 49: a WSA-03 non-compliant answer on Z-LAY1 is listed first on HWS-SLAND-01 with its CA."""
    b = fbody(db, "WSA", nc={"WSA-03"}, site="S-LAND", zone_code="Z-LAY1", eng_code="RAWABI",
              completed=local(2026, 10, 6, 9, 30))  # fmt: skip
    submit(db, "noura.qahtani", b)
    a = waste.read_area(db, P(db, "noura.qahtani"), area(db, "HWS-SLAND-01").id)
    first = a.inspection_answers[0]
    assert (first.template_code, first.item_code, first.compliant) == ("WSA", "WSA-03", False)
    assert first.ca_id is not None


def test_warnings(db: Session) -> None:
    """AC 51: E22 / E23 exactly as EV9; T13 inputs carry no names."""
    from app.hse_jobs import project_scope
    from app.kpi import warnings as kwarn
    from app.kpi.periods import Window
    from app.models import Project

    got = set()
    for p in db.scalars(select(Project)):
        sc = project_scope(db, p, date(2026, 10, 2))
        for w in kwarn.evaluate(sc, [Window(date(2026, 9, 1), date(2026, 9, 30))]):
            if w.code.value in ("E22", "E23"):
                got.add((p.code, w.code.value, w.engagement.code if w.engagement else "-"))
                assert "Hamad" not in str(w.inputs) and "Driver" not in str(w.inputs)
    assert got == {
        ("ANIA-EXP", "E23", "-"), ("ANIA-EXP", "E23", "RAWABI"),
        ("RBT-52", "E22", "-"), ("RBT-52", "E22", "QIMMA"),
        ("RBT-52", "E23", "-"), ("RBT-52", "E23", "QIMMA"),
    }  # fmt: skip


def test_rawabi_tree_filter(api: Api, db: Session) -> None:
    """AC 52: Ahmed with the RAWABI tree filter; K-118 shows "—"."""
    pid = project(db, "ANIA-EXP").id
    body = kpis(api.as_("ahmed.zahrani"), pid, engagement_id=str(eng(db, "ANIA-EXP", "RAWABI").id))
    assert kpi(body, "K118")["display"] == "—"
    # every ANIA-EXP generator (RAWABI, GULFPAVE, NAJD, SAHARA) is in the RAWABI tree
    assert kpi(body, "K119")["display"] == "717.4" and kpi(body, "K123")["display"] == "1"
    other = kpis(
        api.as_("faisal.harbi"), pid, engagement_id=str(eng(db, "ANIA-EXP", "GULFPAVE").id)
    )
    assert kpi(other, "K119")["display"] == "150.0" and kpi(other, "K118")["display"] == "—"


def test_viewer_redaction(api: Api, db: Session) -> None:
    """AC 54: Sarah sees KPIs and registers without driver names, plates or complainant data."""
    s = api.as_("sarah.mitchell")
    pid = project(db, "ANIA-EXP").id
    assert kpis(s, pid)["metrics"]
    r = s.get(f"{API}/projects/{pid}/waste-consignments", params={"page_size": 50})
    assert r.status_code == 200, r.text
    items: list[dict[str, Any]] = r.json()["items"]
    assert items and all(i["driver_name"] is None and i["vehicle_plate"] is None for i in items)
    rbt = project(db, "RBT-52").id
    r = s.get(f"{API}/projects/{rbt}/env-complaints")
    assert r.status_code == 200 and all(i["complainant_name"] is None for i in r.json()["items"])
    r = s.get(f"{API}/projects/{pid}/spills")
    assert r.status_code == 200 and all(not i.get("photo_ids") for i in r.json()["items"])


def test_arabic_labels(api: Api) -> None:
    """AC 58: every 6e list value has its AR label."""
    r = api.as_("faisal.harbi").get(f"{API}/env-reference")
    assert r.status_code == 200, r.text
    lists = r.json()["lists"]
    assert len(lists) >= 15
    missing = [(k, i["code"]) for k, v in lists.items() for i in v if not i["label_ar"].strip()]
    assert missing == []
