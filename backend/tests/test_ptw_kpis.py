"""3-ptw §9 AC91-AC97 (PTW KPIs, warnings, dashboard, AI T15, expiring items), Y12, Y13."""

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import client as llm
from app.core.clock import set_now
from app.core.hse_enums import KpiMetric
from app.core.ptw_enums import PermitStatus
from app.kpi.facts import Facts
from app.kpi.periods import Window
from app.kpi.ptw_facts import PermitFact, PtwFacts
from app.models import Notification, Permit, PermitCrew, Worker
from tests import kpi_world as w
from tests.conftest import Api, Ids
from tests.fake_llm import FakeLlm, last_results, say, use

API = "/api/v1"
SEED = datetime(2026, 10, 6, 7, 0, tzinfo=UTC)


def _q(month: str) -> dict[str, str]:
    y, m = (int(x) for x in month.split("-"))
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return {"period": "month", "anchor": f"{month}-01", "as_of": str(nxt - timedelta(days=1))}


@pytest.fixture
def seed_now() -> Iterator[None]:
    set_now(SEED)
    yield
    set_now(None)


def kpi(
    api: Api, ids: Ids, project: str, metric: str, month: str = "2026-09", who: str = "faisal.harbi"
) -> dict[str, Any]:
    res = api.as_(who).get(
        f"{API}/kpi/metrics/{metric}", params={"project_id": ids.project(project), **_q(month)}
    )
    assert res.status_code == 200, res.text
    out: dict[str, Any] = res.json()["kpi"]
    return out


def comps(k: dict[str, Any]) -> dict[str, str]:
    return {c["key"]: c["value"] for c in k.get("components") or []}


# ---- AC91 / Y12 ----------------------------------------------------------------------------------

Y12 = {
    "ANIA-EXP": {
        "K-62": ("120", None, None),
        "K-63": ("610", None, None),
        "K-46": ("64", None, None),
        "K-46b": ("44.3 %", "58", "131"),
        "K-61": ("92.5 %", "1361", "1472"),
        "K-64": ("4", "4", "64"),
        "K-65": ("18", "18", "610"),
        "K-66": ("94.8 %", "91", "96"),
        "K-67": ("7", None, None),
        "K-68": ("9", None, None),
        "K-69": ("96.6 %", "113", "117"),
        "K-70": ("5", None, None),
    },
    "RBT-52": {
        "K-62": ("44", None, None),
        "K-63": ("240", None, None),
        "K-46": ("22", None, None),
        "K-46b": ("44.7 %", "21", "47"),
        "K-61": ("93.1 %", "471", "506"),
        "K-64": ("1", "1", "22"),
        "K-65": ("6", "6", "240"),
        "K-66": ("—", "0", "0"),
        "K-67": ("2", None, None),
        "K-68": ("4", None, None),
        "K-69": ("92.7 %", "38", "41"),
        "K-70": ("2", None, None),
    },
}


@pytest.mark.usefixtures("ptw_seed", "seed_now")
def test_AC91_Y12_september_values(api: Api, ids: Ids) -> None:
    for project, rows in Y12.items():
        for metric, (display, num, den) in rows.items():
            k = kpi(api, ids, project, metric)
            assert k["display"] == display, (project, metric, k["display"])
            if num is not None:
                assert (k["numerator"], k["denominator"]) == (num, den), (project, metric, k)
    a62 = comps(kpi(api, ids, "ANIA-EXP", "K-62"))
    assert {k: a62[k] for k in ("general", "hot_work", "work_at_height", "lifting", "excavation", "electrical_isolation", "confined_space", "radiography", "airside_works", "critical_lifts")} == {
        "general": "34", "hot_work": "28", "work_at_height": "22", "lifting": "14", "excavation": "8",
        "electrical_isolation": "6", "confined_space": "4", "radiography": "2", "airside_works": "2", "critical_lifts": "3",
    }  # fmt: skip
    r62 = comps(kpi(api, ids, "RBT-52", "K-62"))
    assert {k: r62[k] for k in ("work_at_height", "hot_work", "lifting", "general", "electrical_isolation", "excavation", "critical_lifts")} == {
        "work_at_height": "14", "hot_work": "12", "lifting": "10", "general": "5", "electrical_isolation": "2", "excavation": "1", "critical_lifts": "4",
    }  # fmt: skip
    a64 = comps(kpi(api, ids, "ANIA-EXP", "K-64"))
    assert (a64["rate"], a64["field"], a64["unpermitted_work"]) == ("6.25", "3", "1")
    assert comps(kpi(api, ids, "RBT-52", "K-64"))["rate"] == "4.55"
    a65 = comps(kpi(api, ids, "ANIA-EXP", "K-65"))
    assert a65["rate"] == "2.95" and a65["routine"] == "41"
    assert {k.split(":", 1)[1]: v for k, v in a65.items() if k.startswith("reason:")} == {
        "ops_suspension": "5", "gas_test_failed": "2", "audit_critical": "3", "stop_work": "4",
        "key_role_ineligible": "1", "wind_limit": "2", "simops_conflict": "1",
    }  # fmt: skip
    assert comps(kpi(api, ids, "RBT-52", "K-65"))["rate"] == "2.50"
    assert comps(kpi(api, ids, "ANIA-EXP", "K-67"))["long_term"] == "2"
    assert comps(kpi(api, ids, "RBT-52", "K-67"))["long_term"] == "0"
    assert comps(kpi(api, ids, "ANIA-EXP", "K-68")) == {
        "prohibited": "2",
        "conditional": "7",
        "open": "0",
    }
    assert comps(kpi(api, ids, "RBT-52", "K-68")) == {
        "prohibited": "0",
        "conditional": "4",
        "open": "0",
    }
    assert comps(kpi(api, ids, "ANIA-EXP", "K-46"))["coverage"] == "44.3"


HISTORY = {
    # month: field audits, K-61, K-64, K-69, K-70
    "ANIA-EXP": {
        "2026-06": ("58", "90.1 %", "1", "97.0 %", "3"),
        "2026-07": ("61", "88.4 %", "2", "95.8 %", "4"),
        "2026-08": ("60", "91.0 %", "2", "96.9 %", "2"),
    },
    "RBT-52": {
        "2026-06": (None, None, None, "96.0 %", "1"),
        "2026-07": (None, None, None, "95.5 %", "2"),
        "2026-08": (None, None, None, "97.1 %", "1"),
    },
}


@pytest.mark.usefixtures("ptw_seed", "seed_now")
def test_AC91_Y12_history(api: Api, ids: Ids) -> None:
    for project, months in HISTORY.items():
        for month, want in months.items():
            got = tuple(
                kpi(api, ids, project, m, month)["display"]
                for m in ("K-46", "K-61", "K-64", "K-69", "K-70")
            )
            for g, x in zip(got, want, strict=True):
                if x is not None:
                    assert g == x, (project, month, got, want)
            if project == "RBT-52":
                k61 = kpi(api, ids, project, "K-61", month)
                assert Decimal(k61["value"]) >= Decimal("92.0")
                assert int(kpi(api, ids, project, "K-64", month)["value"]) <= 1


# ---- AC92 E8 / E9 ----------------------------------------------------------------------------------


@pytest.mark.usefixtures("ptw_seed")
def test_AC92_e8_e9_warnings(api: Api, ids: Ids, db: Session) -> None:
    from app import hse_jobs

    set_now(datetime(2026, 10, 2, 3, 10, tzinfo=UTC))
    try:
        hse_jobs.leading_warnings(db, date(2026, 10, 2))
        db.commit()
        texts = [
            n.title_en
            for n in db.scalars(select(Notification).where(Notification.kind == "leading_warning"))
        ]
        e8 = {t.split(":")[0] for t in texts if ": E8 " in t}
        e9 = {t.split(":")[0] for t in texts if ": E9 " in t}
        assert e8 == {"ANIA-EXP 2026-09"}
        assert e9 == {"RBT-52 2026-09"}
        for project in ("ANIA-EXP", "RBT-52"):
            res = api.as_("faisal.harbi").get(
                f"{API}/kpi/leading-indicators",
                params={
                    "project_id": ids.project(project),
                    "period": "month",
                    "anchor": "2026-09-01",
                    "as_of": "2026-09-30",
                    "months": 4,
                },
            )
            assert res.status_code == 200, res.text
            got = {
                (x["code"], x["month"]) for x in res.json()["warnings"] if x["code"] in ("E8", "E9")
            }
            assert got == ({("E8", "2026-09")} if project == "ANIA-EXP" else {("E9", "2026-09")})
    finally:
        set_now(None)


# ---- AC93 dashboard tiles ----------------------------------------------------------------------------


@pytest.mark.usefixtures("ptw_seed", "seed_now")
def test_AC93_dashboard_ptw_tiles(api: Api, ids: Ids) -> None:
    res = api.as_("faisal.harbi").get(
        f"{API}/kpi/dashboard", params={"project_id": ids.project("ANIA-EXP"), **_q("2026-09")}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    tiles = {t["metric"]: t for t in body["leading"]}
    assert tiles["K-46"]["display"] == "64"
    assert tiles["K-46"].get("null_reason") is None
    for m in ("K-61", "K-64", "K-66", "K-69"):
        assert m in tiles
    assert "K-46" not in json.dumps(body["placeholders"])
    assert body["ptw_band"] is not None


# ---- AC94 / Y13 turnaround median --------------------------------------------------------------------


def _permit_fact(hours: float, d: date) -> PermitFact:
    issued = datetime(d.year, d.month, d.day, 9, 0, tzinfo=UTC)
    return PermitFact(
        id=uuid.uuid4(), project=uuid.uuid4(), eng=w.RAWABI, site=w.S_LAND, zones=frozenset(), primary="general",
        types=frozenset({"general"}), high_risk=False, critical_lift=False, status=PermitStatus.closed, status_reason=None,
        first_requested_at=issued - timedelta(hours=hours), first_issued_at=issued, issued_d=d, closed_d=None,
        expired_d=None, end_d=None,
    )  # fmt: skip


def test_AC94_Y13_turnaround_median() -> None:
    def k71(hours: list[float]) -> Decimal | None:
        facts = Facts(engagements=dict(w.ENGAGEMENTS))
        pf = PtwFacts()
        for i, h in enumerate(hours):
            f = _permit_fact(h, date(2026, 9, 1 + i))
            pf.permits[f.id] = f
        facts._ptw = pf
        e = w.engine(facts)
        return e.result(KpiMetric.K71, e.aggregate(Window(w.SEP_START, w.SEP_END))).value

    six = [2.0, 3.5, 4.0, 5.0, 8.0, 26.0]
    assert k71(six) == Decimal("4.5")
    assert k71([*six, 30.0]) == Decimal("5.0")


# ---- AC95 AI T15 -------------------------------------------------------------------------------------


@pytest.fixture
def fake() -> Iterator[FakeLlm]:
    f = FakeLlm()
    llm.set_client_factory(lambda: f)
    yield f
    llm.set_client_factory(None)


def _personal(db: Session) -> list[str]:
    live = list(db.scalars(select(Permit.id).where(Permit.seed_fake.is_(False))))
    crew = list(db.scalars(select(PermitCrew.worker_id).where(PermitCrew.permit_id.in_(live))))
    out: list[str] = []
    for wk in db.scalars(select(Worker).where(Worker.id.in_(crew))):
        out += [wk.full_name_en, wk.worker_no]
    return out


@pytest.mark.usefixtures("ptw_seed", "seed_now")
def test_AC95_ai_t15_critical_findings(api: Api, ids: Ids, db: Session, fake: FakeLlm) -> None:
    def answer(messages: list[dict[str, Any]]) -> Any:
        for r in last_results(messages):
            for k in r.get("kpis") or []:
                if k["metric"] == "K-64":
                    rate = next(c["value"] for c in k["components"] if c["key"] == "rate")
                    return say(
                        f"We had {k['value']} critical PTW findings in September 2026 ({rate} per 100 field audits) [{k['cite']}]."
                    )
        raise AssertionError("K-64 not in T15 results")

    fake.script(
        use(
            "get_ptw_kpis",
            project_codes=["ANIA-EXP"],
            metrics=["K-64"],
            period={"preset": "month", "anchor": "2026-09-01"},
        ),
        answer,
    )
    res = api.as_("noura.qahtani").post(
        f"{API}/ai/ask",
        json={
            "project_id": ids.project("ANIA-EXP"),
            "language": "en",
            "question": "How many critical PTW findings did we have in September 2026?",
        },
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 200, res.text
    a = res.json()
    assert "4 critical PTW findings" in a["text"] and "6.25 per 100 field audits" in a["text"]
    assert a["citations"][0]["tool"] == "get_ptw_kpis"
    assert a["citations"][0]["metric"] == "K-64"
    sent = fake.sent()
    for s in _personal(db):
        assert s not in sent, s
    assert "signature" not in sent.lower() or "signature_png" not in sent


# ---- AC96 viewer aggregates ----------------------------------------------------------------------------


@pytest.mark.usefixtures("ptw_seed", "seed_now")
def test_AC96_viewer_sees_aggregates_only(api: Api, ids: Ids, db: Session) -> None:
    c = api.as_("sarah.mitchell")
    pid = ids.project("ANIA-EXP")
    res = c.get(
        f"{API}/kpi/ptw",
        params={"project_id": pid, **_q("2026-09"), "group_by": ["type", "contractor", "zone"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["metrics"]
    board = c.get(f"{API}/projects/{pid}/ptw-board")
    assert board.status_code == 200, board.text
    blob = json.dumps(
        [res.json(), board.json(),
         c.get(f"{API}/dashboard/expiring-items", params={"project_id": pid}).json(),
         c.get(f"{API}/dashboard/action-panel", params={"project_id": pid}).json(),
         *(c.get(f"{API}/kpi/charts/{ch}", params={"project_id": pid, **_q("2026-09")}).json() for ch in ("C13", "C14", "C15"))],
        ensure_ascii=False,
    )  # fmt: skip
    for s in _personal(db):
        assert s not in blob, s


# ---- AC97 expiring items ----------------------------------------------------------------------------------


@pytest.mark.usefixtures("ptw_seed")
def test_AC97_expiring_appointments_and_detectors(api: Api, ids: Ids) -> None:
    def items(project: str, day: datetime) -> list[dict[str, Any]]:
        set_now(day)
        res = api.as_("faisal.harbi").get(
            f"{API}/dashboard/expiring-items",
            params={"project_id": ids.project(project), "within_days": 30},
        )
        assert res.status_code == 200, res.text
        out: list[dict[str, Any]] = res.json()["items"]
        return out

    try:
        ania = items("ANIA-EXP", SEED)
        apt = [
            i
            for i in ania
            if i["kind"] == "ptw_appointment_expiry" and i["ref"] == "APT-ANIA-EXP-0011"
        ]
        assert apt and apt[0]["days_left"] == 14
        rbt = items("RBT-52", SEED)
        assert not [
            i
            for i in rbt
            if i["kind"] == "gas_detector_calibration_due" and i["ref"] == "GD-RBT-001"
        ]
        rbt7 = items("RBT-52", SEED + timedelta(days=1))
        hit = [
            i
            for i in rbt7
            if i["kind"] == "gas_detector_calibration_due" and i["ref"] == "GD-RBT-001"
        ]
        assert hit and hit[0]["days_left"] == 30
    finally:
        set_now(None)
