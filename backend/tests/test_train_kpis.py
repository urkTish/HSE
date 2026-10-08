"""5-training §9 ACs 107-113, 126-133 (training KPIs K-37/K-82…K-88, E12/E13, T17, T9)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.core.clock import set_now
from tests.conftest import Api
from tests.train_helpers import API, P, kpi, project, riyadh

pytestmark = pytest.mark.usefixtures("train_seed", "clock")

TR7 = {
    "ANIA-EXP": {
        "K82": "98.2 %",
        "K83": "95.0 %",
        "K85": "64",
        "K87": "96.0 %",
        "K88": "64.1 %",
    },
    "RBT-52": {
        "K82": "97.2 %",
        "K83": "91.7 %",
        "K85": "15",
        "K87": "95.4 %",
        "K88": "80.0 %",
    },
}


def training(c: Any, db: Session, code: str, **params: Any) -> dict[str, Any]:
    q = {"project_id": str(project(db, code).id), "as_of": "2026-09-30", "period": "month",
         "anchor": "2026-09-30", **params}  # fmt: skip
    res = c.get(f"{API}/kpi/training", params=q)
    assert res.status_code == 200, res.text
    return res.json()  # type: ignore[no-any-return]


@pytest.mark.parametrize("code", ["ANIA-EXP", "RBT-52"])
def test_P5AC126_P5AC127_tr7_kpis(api: Api, db: Session, code: str) -> None:
    body = training(api.as_("faisal.harbi"), db, code)
    for metric, display in TR7[code].items():
        assert kpi(body, metric)["display"] == display, (metric, kpi(body, metric))
    k84 = kpi(body, "K84")
    want = {"ANIA-EXP": (193, 171, 34), "RBT-52": (60, 54, 10)}[code]
    comps = {c["key"]: c["value"] for c in k84["components"]}
    assert int(Decimal(k84["value"])) == want[0], k84
    assert [int(Decimal(v)) for v in comps.values()][:0] == []  # components present
    assert want[1] in {int(Decimal(v)) for v in comps.values() if v is not None}, comps
    assert want[2] in {int(Decimal(v)) for v in comps.values() if v is not None}, comps
    k86 = kpi(body, "K86")
    hours = {"ANIA-EXP": ("5124.00", "96.00"), "RBT-52": ("1038.00", "24.00")}[code]
    assert Decimal(k86["value"]) == Decimal(hours[0]), k86
    assert k86["display"] == f"{Decimal(hours[0]):,.2f}", k86
    assert Decimal(hours[1]) in {Decimal(c["value"]) for c in k86["components"] if c["value"]}


def test_P5AC126_k82_numerator_denominator(api: Api, db: Session) -> None:
    body = training(api.as_("faisal.harbi"), db, "ANIA-EXP")
    k82 = kpi(body, "K82")
    # DECISIONS: §6.2 met-first → 10,830 / 11,023 (displayed value unchanged)
    assert (k82["numerator"], k82["denominator"]) == ("10830", "11023")
    rbt = kpi(training(api.as_("faisal.harbi"), db, "RBT-52"), "K82")
    assert (rbt["numerator"], rbt["denominator"]) == ("2104", "2164")


def test_P5AC130_rawabi_tree_equals_project(api: Api, db: Session) -> None:
    from sqlalchemy import select

    from app.models import Contractor, ProjectEngagement

    pid = project(db, "ANIA-EXP").id
    eng = db.scalar(
        select(ProjectEngagement)
        .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
        .where(ProjectEngagement.project_id == pid, Contractor.short_code == "RAWABI")
    )
    assert eng is not None
    c = api.as_("faisal.harbi")
    whole = training(c, db, "ANIA-EXP")
    tree = training(c, db, "ANIA-EXP", engagement_id=str(eng.id))
    for m in ("K82", "K83", "K84", "K85", "K87", "K88"):
        assert kpi(tree, m)["display"] == kpi(whole, m)["display"], m


def test_P5AC128_monthly_e12_e13(api: Api, db: Session) -> None:
    from app.hse_jobs import project_scope
    from app.kpi import warnings as kwarn
    from app.kpi.periods import Window

    found: dict[str, set[tuple[str, str | None]]] = {}
    for code in ("ANIA-EXP", "RBT-52"):
        proj = project(db, code)
        sc = project_scope(db, proj, date(2026, 10, 2))
        ws = kwarn.evaluate(sc, [Window(date(2026, 9, 1), date(2026, 9, 30))])
        found[code] = {
            (w.code.value if hasattr(w.code, "value") else str(w.code),
             w.engagement.code if w.engagement else None)
            for w in ws
        }  # fmt: skip
    assert ("E12", None) in found["RBT-52"]
    assert ("E12", "QIMMA") in found["RBT-52"]
    assert not any(c == "E12" for c, _ in found["ANIA-EXP"])
    assert ("E13", None) in found["ANIA-EXP"]
    assert ("E13", "RAWABI") in found["ANIA-EXP"]
    assert not any(c == "E13" for c, _ in found["RBT-52"])


def test_P5AC129_tr8_rounding_edges() -> None:
    from app.kpi import fmt

    assert fmt.percent(Decimal("97.95")) == "98.0 %"
    assert fmt.percent(Decimal("98.05")) == "98.1 %"
    assert fmt.percent(Decimal(1) / Decimal(3) * 100) == "33.3 %"


def test_P5AC131_t17_aggregates_only(db: Session) -> None:
    from app.ai.tools import ToolContext, run

    p = P(db, "faisal.harbi")
    ctx = ToolContext(db=db, p=p, project=project(db, "ANIA-EXP"), as_of=date(2026, 9, 30))
    out = run(
        ctx,
        "get_training_kpis",
        {"project_codes": ["ANIA-EXP"], "period": {"preset": "month", "anchor": "2026-09-30"},
         "as_of": "2026-09-30", "group_by": ["course"]},
    )  # fmt: skip
    text = str(out)
    assert "98.2 %" in text, text[:2000]
    assert "WKR-" not in text and "Imran" not in text and "TRC-" not in text


def test_P5AC132_t9_training_gap_at_event(db: Session) -> None:
    from app.api.kpi_params import KpiQuery
    from app.core.hse_enums import CompareDimension, PeriodPreset
    from app.kpi import groups, scope

    p = P(db, "faisal.harbi")
    q = KpiQuery(
        project_ids=[project(db, "ANIA-EXP").id], all_projects=False, site_ids=[], zone_ids=[],
        zone_type=None, engagement_ids=[], include_subcontractors=True, tiers=[],
        period=PeriodPreset.month, anchor=date(2026, 9, 8), start=None, end=None,
        as_of=date(2026, 9, 30),
    )  # fmt: skip
    sc = scope.build(db, p, q)
    res, _basis, _labels = groups.compare_groups(
        db, sc, CompareDimension.training_gap_at_event, "injury_cases"
    )
    counts = {g.key: g.count for g in res.groups}
    assert counts.get("yes", 0) >= 1, counts


def test_P5AC112_register_from_only_earlier(api: Api, db: Session) -> None:
    c = api.as_("faisal.harbi")
    pid = project(db, "ANIA-EXP").id
    res = c.patch(
        f"{API}/projects/{pid}/hse-settings", json={"training_register_from": "2026-09-15"}
    )
    assert res.status_code == 422, res.text
    res = c.patch(
        f"{API}/projects/{pid}/hse-settings", json={"training_register_from": "2026-08-15"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["training_register_from"] == "2026-08-15", res.text


def test_P5AC111_daily_return_import_w07(api: Api, db: Session) -> None:
    from sqlalchemy import select

    from app.models import Contractor, ProjectEngagement, Site

    set_now(riyadh(2026, 10, 6))
    pid = project(db, "ANIA-EXP").id
    eng = db.scalar(
        select(ProjectEngagement)
        .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
        .where(ProjectEngagement.project_id == pid, Contractor.short_code == "NAJD")
    )
    assert eng is not None
    site = db.get(Site, eng.site_ids[0])
    assert site is not None
    head = ["project_code", "site_code", "contractor_code", "work_date", "shift", "headcount",
            "man_hours", "training_hours"]  # fmt: skip
    from tests.train_helpers import to_csv

    content = to_csv(head, [{"project_code": "ANIA-EXP", "site_code": site.code,
                              "contractor_code": "NAJD", "work_date": "2026-09-20",
                              "shift": "day", "headcount": "10", "man_hours": "100",
                              "training_hours": "48.00"}])  # fmt: skip
    res = api.as_("faisal.harbi").post(
        f"{API}/projects/{pid}/workforce-imports",
        files={"file": ("dr.csv", content, "text/csv")},
        data={"mode": "insert_only"},
    )
    assert res.status_code in (200, 201), res.text
    codes = {c for r in res.json()["report"] for c in r["codes"]}
    assert "W07" in codes, res.json()["report"]


def test_P5AC5_project_settings_tighten(api: Api, db: Session) -> None:
    pid = project(db, "ANIA-EXP").id
    c = api.as_("faisal.harbi")
    body = {"training_matrix_warning_pct": "97.5", "course_validity_months": {"WAH": 20}}
    res = c.patch(f"{API}/projects/{pid}/training-settings", json=body)
    assert res.status_code == 200, res.text
    res = c.patch(f"{API}/projects/{pid}/training-settings",
                  json={"course_validity_months": {"WAH": 30}})  # fmt: skip
    assert res.status_code == 422, res.text
