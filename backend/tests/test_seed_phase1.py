"""Phase 1 demo seed (spec 1-dashboard Appendix A) and the seed-based acceptance criteria."""

import json
import re
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.hse_enums import KpiMetric as M
from app.hse_jobs import project_scope
from app.kpi import service, views
from app.kpi.periods import Window, month_end
from app.models import CorrectiveAction, HseSettings, InjuryCase, Project
from app.seed_hse import A3, PEOPLE, W3
from tests.conftest import Api, Ids

API = "/api/v1"
pytestmark = pytest.mark.usefixtures("hse_seed")
SEED_NAMES = [n for p in PEOPLE for n in p[:2]]
SEP = {"period": "month", "anchor": "2026-09-01", "as_of": "2026-10-05"}


def _project(db: Session, code: str) -> Project:
    p = db.scalar(select(Project).where(Project.code == code))
    assert p is not None
    return p


def test_AC78_seed_ids_fake_and_monthly_totals_exact(db: Session) -> None:
    cases = list(db.scalars(select(InjuryCase)))
    assert cases
    numbers = [crypto.decrypt(c.id_number_enc) for c in cases]
    assert all(re.fullmatch(r"[12]0{5}\d{4}", n) for n in numbers)
    assert len(set(numbers)) == len(numbers)
    assert all(c.seed_fake for c in cases)
    assert all(ca.seed_fake for ca in db.scalars(select(CorrectiveAction)))
    named = [c for c in cases if c.person_name.startswith("Imran Hussain")]
    assert any(crypto.decrypt(c.id_number_enc) == "2000000017" for c in named)

    p = _project(db, "ANIA-EXP")
    late = project_scope(db, p, date(2026, 10, 5))
    metrics = [M.K01, M.K06, M.K07, M.K08, M.K09, M.K12, M.K13, M.K14, M.K15, M.K16, M.K36]
    for m, w in W3.items():
        a3 = A3[m]
        win = Window(m, month_end(m))
        sc = project_scope(db, p, month_end(m))
        vals = {v.metric: v.value for v in service.metric_list(sc, metrics)}
        got = [vals[k] for k in metrics]
        assert [str(x).split(".")[0] for x in got] == [str(x) for x in (*w, *a3[8:12])], m
        agg = late.engine.aggregate(win)
        assert (agg.obs_total, agg.obs_unsafe) == (a3[0] + a3[1], a3[1]), m
        assert sc.engine.aggregate(win).overdue == a3[7], m  # overdue at month end
        assert agg.raised == a3[6], m


def test_seed_inspections_and_completeness(db: Session) -> None:
    p = _project(db, "ANIA-EXP")
    sc = project_scope(db, p, date(2026, 10, 5))
    for m, a3 in A3.items():
        agg = sc.engine.aggregate(Window(m, month_end(m)))
        assert agg.late_insp == a3[4], m
    # A.4 (5): July 2026 152 / 155 = 98.1 % (no banner)
    july = Window(date(2026, 7, 1), date(2026, 7, 31))
    assert sc.engine.completeness(july) == (155, 152)


def test_completeness_banner_gulfpave_july(api: Api, ids: Ids) -> None:
    c = api.as_("noura.qahtani")
    q = {"project_id": ids.project("ANIA-EXP"), "period": "month", "anchor": "2026-07-01"}
    q["as_of"] = "2026-10-05"
    all_ = c.get(f"{API}/kpi/dashboard", params=q).json()["context"]
    assert all_["data_completeness_display"] == "98.1 %"
    assert all_["completeness_below_threshold"] is False
    gp = c.get(
        f"{API}/kpi/dashboard", params={**q, "engagement_id": ids.engagement("GULFPAVE")}
    ).json()["context"]
    assert gp["data_completeness_display"] == "90.3 %"
    assert gp["completeness_below_threshold"] is True


def test_AC58_E1_only_for_july_2026(db: Session) -> None:
    p = _project(db, "ANIA-EXP")
    sc = project_scope(db, p, date(2026, 9, 30))
    found = views.leading_indicators(sc, 3).warnings
    e1 = {w.month for w in found if w.code.value == "E1" and w.engagement is None}
    assert e1 == {"2026-07"}


def test_AC59_yousef_sees_qimma_tree_only(api: Api, ids: Ids) -> None:
    c = api.as_("yousef.ghamdi")
    res = c.get(f"{API}/kpi/dashboard", params={"project_id": ids.project("RBT-52"), **SEP})
    assert res.status_code == 200, res.text
    f = res.json()["context"]["filters"]
    assert set(f["effective_engagement_ids"]) == {
        ids.engagement("QIMMA"),
        ids.engagement("DLIFT"),
    }
    assert f["scope_narrowed"] is True
    other = c.get(f"{API}/kpi/dashboard", params={"project_id": ids.project("ANIA-EXP"), **SEP})
    assert other.status_code == 404
    mine = c.get(f"{API}/projects").json()
    codes = {x["code"] for x in mine.get("items", mine)}
    assert "ANIA-EXP" not in codes


def test_AC60_ramesh_sees_najd_only(api: Api, ids: Ids) -> None:
    c = api.as_("ramesh.kumar")
    pid = ids.project("ANIA-EXP")
    res = c.get(f"{API}/kpi/metrics", params={"project_id": pid, "metric": "K-01", **SEP})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["context"]["filters"]["effective_engagement_ids"] == [ids.engagement("NAJD")]
    assert body["context"]["filters"]["scope_narrowed"] is True
    assert body["kpis"][0]["display"] == "240,000"  # W1/W2 "NAJD only" man-hours
    mgr = api.as_("faisal.harbi").get(
        f"{API}/kpi/metrics", params={"project_id": pid, "metric": "K-01", **SEP}
    )
    assert mgr.json()["context"]["filters"]["scope_narrowed"] is False
    assert mgr.json()["kpis"][0]["display"] == "870,000"


def test_seed_records_fake_ai_approval(db: Session) -> None:
    rows = list(db.scalars(select(HseSettings)))
    assert rows
    for s in rows:
        assert s.ai_enabled
        assert s.ai_approval_reference == "SEED-FAKE-AI-APPROVAL"
        assert "seed-fake" in (s.ai_approver_name or "")


def test_AC55_all_projects_mixed_bases_banner(api: Api) -> None:
    res = api.as_("faisal.harbi").get(f"{API}/kpi/dashboard", params={"all_projects": True, **SEP})
    assert res.status_code == 200, res.text
    b = res.json()["context"]["bases"]
    assert b["mixed_projects"] is True
    text = json.dumps(b)
    assert "1,000,000" in text and "200,000" in text


def test_AC56_kpi_values_carry_inputs(api: Api, ids: Ids) -> None:
    res = api.as_("noura.qahtani").get(
        f"{API}/kpi/metrics", params={"project_id": ids.project("ANIA-EXP"), **SEP}
    )
    body = res.json()
    ctx = body["context"]
    assert "data_completeness_display" in ctx and "provisional_cases_count" in ctx
    for k in body["kpis"]:
        for f in ("value", "numerator", "denominator", "base"):
            assert f in k, (k["metric"], f)
    trir = next(k for k in body["kpis"] if k["metric"] == "K-21")
    assert (trir["value"], trir["numerator"], trir["base"]) == ("0.92", "4", 200000)


def test_AC61_viewer_no_demographics_no_names(api: Api, ids: Ids) -> None:
    c = api.as_("sarah.mitchell")
    q = {"project_id": ids.project("ANIA-EXP"), **SEP}
    for dim in ("nationality", "age_band"):
        res = c.get(
            f"{API}/kpi/breakdowns", params={**q, "measure": "injury_cases", "dimension": dim}
        )
        assert res.status_code == 403, dim
    blob = json.dumps(
        [
            c.get(f"{API}/kpi/dashboard", params=q).json(),
            c.get(f"{API}/kpi/breakdowns", params={**q, "dimension": "mechanism"}).json(),
            c.get(f"{API}/kpi/leading-indicators", params=q).json(),
            c.get(f"{API}/dashboard/action-panel", params={"project_id": q["project_id"]}).json(),
        ],
        ensure_ascii=False,
    )
    for name in SEED_NAMES:
        assert name not in blob, name
