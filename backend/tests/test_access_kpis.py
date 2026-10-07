"""Spec 2-access-permits §9 AC67-AC73 (access KPIs, warnings, expiring items, AI T14), X6-X11."""

import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import client as llm
from app.core.hse_enums import KpiMetric
from app.kpi.access_facts import AccessFacts, AttemptFact
from app.kpi.facts import Facts
from app.kpi.periods import Window
from app.models import Vehicle, Worker
from app.services.access import common
from tests import kpi_world as w
from tests.access_helpers import API
from tests.conftest import Api, Ids
from tests.fake_llm import FakeLlm, say, use

SEP = {"period": "month", "anchor": "2026-09-01", "as_of": "2026-09-30"}


def metric(api: Api, ids: Ids, who: str, project: str, m: str) -> dict[str, Any]:
    res = api.as_(who).get(
        f"{API}/kpi/metrics/{m}", params={"project_id": ids.project(project), **SEP}
    )
    assert res.status_code == 200, res.text
    out: dict[str, Any] = res.json()["kpi"]
    return out


def warnings(api: Api, ids: Ids, project: str) -> list[dict[str, Any]]:
    res = api.as_("faisal.harbi").get(
        f"{API}/kpi/leading-indicators",
        params={"project_id": ids.project(project), **SEP, "months": 1},
    )
    assert res.status_code == 200, res.text
    out: list[dict[str, Any]] = res.json()["warnings"]
    return out


@pytest.mark.usefixtures("access_seed", "noon")
def test_P2AC67_X6_induction_coverage_and_e5(api: Api, ids: Ids) -> None:
    ania = metric(api, ids, "faisal.harbi", "ANIA-EXP", "K-49")
    rbt = metric(api, ids, "faisal.harbi", "RBT-52", "K-49")
    assert (ania["display"], ania["numerator"], ania["denominator"]) == ("98.8 %", "3371", "3412")
    assert (rbt["display"], rbt["numerator"], rbt["denominator"]) == ("97.9 %", "640", "654")
    assert not [x for x in warnings(api, ids, "ANIA-EXP") if x["code"] == "E5"]
    e5 = [x for x in warnings(api, ids, "RBT-52") if x["code"] == "E5"]
    assert e5 and {x["month"] for x in e5} == {"2026-09"}


@pytest.mark.usefixtures("access_seed", "noon")
def test_P2AC68_X7_gate_denial_rate_no_e6(api: Api, ids: Ids) -> None:
    ania = metric(api, ids, "faisal.harbi", "ANIA-EXP", "K-53")
    rbt = metric(api, ids, "faisal.harbi", "RBT-52", "K-53")
    assert (ania["display"], ania["numerator"], ania["denominator"]) == ("0.60 %", "449", "74880")
    assert (rbt["display"], rbt["numerator"], rbt["denominator"]) == ("0.46 %", "62", "13520")
    for p in ("ANIA-EXP", "RBT-52"):
        assert not [x for x in warnings(api, ids, p) if x["code"] == "E6"]


@pytest.mark.usefixtures("access_seed", "noon")
def test_P2AC69_X8_X10_returns_offences_notams(api: Api, ids: Ids) -> None:
    k54 = metric(api, ids, "faisal.harbi", "ANIA-EXP", "K-54")
    assert (k54["display"], k54["numerator"], k54["denominator"]) == ("75.0 %", "9", "12")
    assert metric(api, ids, "faisal.harbi", "ANIA-EXP", "K-55")["value"] in ("2", "2.0")
    k57 = metric(api, ids, "faisal.harbi", "ANIA-EXP", "K-57")
    assert k57["display"] == "1.69" and (k57["numerator"], k57["denominator"]) == ("4", "236")
    k59 = metric(api, ids, "faisal.harbi", "ANIA-EXP", "K-59")
    assert (k59["display"], k59["numerator"], k59["denominator"]) == ("83.3 %", "5", "6")
    assert not [x for x in warnings(api, ids, "ANIA-EXP") if x["code"] == "E7"]


def test_P2AC70_X11_k50_first_attempt_pass_rate() -> None:
    eng = next(iter(w.ENGAGEMENTS))
    attempts = [AttemptFact(date(2026, 9, 10), eng, True, True, 37),
                AttemptFact(date(2026, 9, 11), eng, True, False, 3),
                AttemptFact(date(2026, 9, 12), eng, False, True, 2),
                AttemptFact(date(2026, 9, 13), eng, False, False, 1),
                AttemptFact(date(2026, 8, 31), eng, True, False, 5)]  # fmt: skip
    facts = Facts(engagements=dict(w.ENGAGEMENTS))
    facts.access = AccessFacts(attempts=attempts)
    e = w.engine(facts)
    res = e.result(KpiMetric.K50, e.aggregate(Window(w.SEP_START, w.SEP_END)))
    assert (res.numerator, res.denominator) == (37, 40)
    assert res.value == Decimal("92.5")


@pytest.mark.usefixtures("access_seed", "noon")
def test_P2AC71_expiring_items(api: Api, ids: Ids, db: Session) -> None:
    q = {"project_id": ids.project("ANIA-EXP"), "within_days": 30}
    res = api.as_("noura.qahtani").get(f"{API}/dashboard/expiring-items", params=q)
    assert res.status_code == 200, res.text
    items = res.json()["items"]

    def find(kind: str, needle: str) -> dict[str, Any]:
        hit = [i for i in items if i["kind"] == kind and needle in i["title_en"]]
        assert hit, (kind, needle, [(i["kind"], i["title_en"]) for i in items][:40])
        return hit[0]

    assert find("induction_expiry", "Abdul Karim")["days_left"] == 7
    assert find("worker_id_expiry", "Osman")["days_left"] == 14
    avp = find("avp_expiry", "VEH-0002")
    assert avp["days_left"] == 14 and avp["limiting_factor"] == "insurance_expiry"
    res = api.as_("ahmed.zahrani").get(f"{API}/dashboard/expiring-items", params=q)
    assert res.status_code == 200, res.text
    assert not [i for i in res.json()["items"] if i["kind"] == "bg_recheck_due"]


def _personal(db: Session) -> list[str]:
    names = [n for (n,) in db.execute(select(Worker.full_name_en).limit(400))]
    nos = [n for (n,) in db.execute(select(Worker.worker_no).limit(400))]
    plates = [common.plate_display(v) for v in db.scalars(select(Vehicle))]
    return [*names, *nos, *(p for p in plates if p)]


@pytest.mark.usefixtures("access_seed", "noon")
def test_P2AC72_viewer_aggregates_only(api: Api, ids: Ids, db: Session) -> None:
    c = api.as_("sarah.mitchell")
    pid = ids.project("ANIA-EXP")
    groups = ["kind", "contractor", "reason_code"]
    res = c.get(f"{API}/kpi/access", params={"project_id": pid, **SEP, "group_by": groups})
    assert res.status_code == 200, res.text
    assert res.json()["metrics"]
    blob = json.dumps(
        [
            res.json(),
            c.get(f"{API}/dashboard/expiring-items", params={"project_id": pid}).json(),
            c.get(f"{API}/dashboard/action-panel", params={"project_id": pid}).json(),
            *(c.get(f"{API}/kpi/charts/{ch}", params={"project_id": pid, **SEP}).json()
              for ch in ("C10", "C11", "C12")),
        ],
        ensure_ascii=False,
    )  # fmt: skip
    for s in _personal(db):
        assert s not in blob, s


@pytest.fixture
def fake() -> Iterator[FakeLlm]:
    f = FakeLlm()
    llm.set_client_factory(lambda: f)
    yield f
    llm.set_client_factory(None)


@pytest.mark.usefixtures("access_seed", "noon")
def test_P2AC73_ai_t14_sends_no_personal_data(
    api: Api, ids: Ids, db: Session, fake: FakeLlm
) -> None:
    fake.script(
        use("get_access_kpis", project_codes=["ANIA-EXP"], metrics=["K-51"],
            group_by=["kind"], period={"preset": "month", "anchor": "2026-10-01"}),
        use("get_expiring_items", project_codes=["ANIA-EXP"], within_days=30),
        say("Airport passes expiring this month are shown in the access KPIs [S1]."),
    )  # fmt: skip
    res = api.as_("noura.qahtani").post(
        f"{API}/ai/ask",
        json={"project_id": ids.project("ANIA-EXP"), "language": "en",
              "question": "How many airport passes expire this month?"},
        headers={"Accept": "application/json"},
    )  # fmt: skip
    assert res.status_code == 200, res.text
    assert "get_access_kpis" in fake.calls[0]["tools"]
    sent = fake.sent()
    assert "K-51" in sent
    for s in _personal(db):
        assert s not in sent, s
    for marker in ("2000001", "1000001", "WKR-0"):
        assert marker not in sent
