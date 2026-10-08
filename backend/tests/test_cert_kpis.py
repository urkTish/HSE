"""4-third-party-cert §9 AC103-AC106 (Z11 KPIs, E10/E11, Z12 rounding, AI T16), the C16-C18 charts,
the dashboard tiles / certification band and the §8.2 / §8.3 panels."""

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import client as llm
from app.core.clock import set_now
from app.core.hse_enums import KpiMetric
from app.kpi import fmt
from app.models import Notification, PersonnelCertificate, Worker
from tests.conftest import Api, Ids
from tests.fake_llm import FakeLlm, last_results, say, use

API = "/api/v1"
SEP = {"period": "month", "anchor": "2026-09-01", "as_of": "2026-09-30"}

Z11: dict[str, dict[str, tuple[str, dict[str, str]]]] = {
    "ANIA-EXP": {
        "K-72": ("97.3 %", {}),
        "K-73": ("11", {}),
        "K-74": ("3", {"out_of_service": "3", "a_defects": "4"}),
        "K-75": ("5", {"equipment": "2", "scaffolds": "3"}),
        "K-76": ("95.0 %", {}),
        "K-77": ("17", {}),
        "K-78": ("3", {"equipment": "1", "persons": "1", "tpis": "1"}),
        "K-79": ("88.5 %", {"failed": "1"}),
        "K-80": ("83.3 %", {}),
        "K-81": ("96.9 %", {}),
    },
    "RBT-52": {
        "K-72": ("98.0 %", {}),
        "K-73": ("4", {}),
        "K-74": ("0", {"out_of_service": "0", "a_defects": "0"}),
        "K-75": ("1", {"equipment": "1", "scaffolds": "0"}),
        "K-76": ("95.8 %", {}),
        "K-77": ("5", {}),
        "K-78": ("1", {"equipment": "0", "persons": "0", "tpis": "1"}),
        "K-79": ("92.5 %", {"failed": "0"}),
        "K-80": ("100.0 %", {}),
        "K-81": ("100.0 %", {}),
    },
}
FRACTIONS = {
    ("ANIA-EXP", "K-72"): ("181", "186"),
    ("ANIA-EXP", "K-76"): ("209", "220"),
    ("ANIA-EXP", "K-79"): ("131", "148"),
    ("ANIA-EXP", "K-80"): ("10", "12"),
    ("ANIA-EXP", "K-81"): ("93", "96"),
    ("RBT-52", "K-72"): ("49", "50"),
    ("RBT-52", "K-76"): ("46", "48"),
    ("RBT-52", "K-79"): ("37", "40"),
    ("RBT-52", "K-80"): ("3", "3"),
    ("RBT-52", "K-81"): ("22", "22"),
}


def cert_kpis(api: Api, ids: Ids, project: str, who: str = "faisal.harbi", **extra: Any) -> Any:
    res = api.as_(who).get(
        f"{API}/kpi/certification", params={"project_id": ids.project(project), **SEP, **extra}
    )
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.usefixtures("cert_seed", "clock")
def test_P4AC103_Z11_september_kpis_to_the_decimal(api: Api, ids: Ids) -> None:
    for project, rows in Z11.items():
        body = cert_kpis(api, ids, project)
        got = {m["metric"]: m for m in body["metrics"]}
        for metric, (display, parts) in rows.items():
            k = got[metric]
            assert k["display"] == display, (project, metric, k["display"])
            comps = {c["key"]: c["value"] for c in k["components"]}
            for key, v in parts.items():
                assert comps[key] == v, (project, metric, key, comps)
            if (project, metric) in FRACTIONS:
                assert (k["numerator"], k["denominator"]) == FRACTIONS[(project, metric)]
    a76 = {c["key"]: c["display"] for c in {m["metric"]: m for m in cert_kpis(api, ids, "ANIA-EXP")["metrics"]}["K-76"]["components"]}  # fmt: skip
    assert set(a76) == {"cert_type:CRANE-OPERATOR", "cert_type:RIGGER", "cert_type:SCAFFOLDER"}


@pytest.mark.usefixtures("cert_seed")
def test_P4AC104_E10_E11_for_ania_and_rawabi_tree_not_rbt(api: Api, ids: Ids, db: Session) -> None:
    from app import hse_jobs

    set_now(datetime(2026, 10, 2, 4, 0, tzinfo=UTC))  # 07:00 Riyadh
    try:
        hse_jobs.leading_warnings(db, date(2026, 10, 2))
        db.commit()
        texts = [
            n.title_en
            for n in db.scalars(select(Notification).where(Notification.kind == "leading_warning"))
        ]
        e10 = [t for t in texts if ": E10 " in t]
        e11 = [t for t in texts if ": E11 " in t]
        assert any(t.startswith("ANIA-EXP 2026-09") for t in e10)
        assert any(t.startswith("ANIA-EXP 2026-09") for t in e11)
        assert any("RAWABI" in t for t in e10) and any("RAWABI" in t for t in e11)
        assert not [t for t in e10 + e11 if t.startswith("RBT-52")]
        for project, want in (("ANIA-EXP", {"E10", "E11"}), ("RBT-52", set())):
            res = api.as_("faisal.harbi").get(
                f"{API}/kpi/leading-indicators",
                params={"project_id": ids.project(project), **SEP, "months": 1},
            )
            assert res.status_code == 200, res.text
            got = {
                x["code"]
                for x in res.json()["warnings"]
                if x["code"] in ("E10", "E11") and x["month"] == "2026-09"
            }
            assert got == want, (project, got)
    finally:
        set_now(None)


def test_P4AC105_Z12_rounding_and_E10_unrounded(monkeypatch: pytest.MonkeyPatch) -> None:
    import uuid

    from app.kpi import cert as kc
    from app.kpi import warnings as kw
    from app.kpi.periods import Window

    def show(num: int, den: int) -> tuple[str, Decimal]:
        v = kc.pct(KpiMetric.K72, num, den).value
        assert v is not None
        return fmt.percent(v), v

    assert show(197, 200)[0] == "98.5 %"
    assert show(1961, 2000)[0] == "98.1 %"
    assert show(1959, 2000)[0] == "98.0 %"

    pid = uuid.uuid4()
    settings = SimpleNamespace(
        equipment_cert_warning_pct=Decimal("98.0"),
        personnel_cert_warning_pct=Decimal("95.0"),
        scaffold_tag_warning_pct=Decimal("95.0"),
        dangerous_defect_warning_count=3,
    )
    monkeypatch.setattr(kc, "facts", lambda e: SimpleNamespace(settings={pid: settings}))
    monkeypatch.setattr(kc, "failed_verifications", lambda e, a, o=None: [])
    monkeypatch.setattr(kc, "a_defects", lambda e, a: [])

    class Eng:
        def __init__(self, k72: Decimal) -> None:
            self.k72 = k72

        def aggregate(self, m: Any) -> None:
            return None

        def result(self, metric: KpiMetric, a: Any) -> Any:
            return SimpleNamespace(value=self.k72 if metric == KpiMetric.K72 else Decimal(100))

    w = Window(date(2026, 9, 1), date(2026, 9, 30))

    def e10(k72: Decimal) -> bool:
        out = kw.cert_warnings(Eng(k72), pid, None, w, "Sep 2026", "", "", "")  # type: ignore[arg-type]
        return any(x.code.value == "E10" for x in out)

    assert e10(show(1961, 2000)[1]) is False  # 98.05 ≥ 98.0
    assert e10(show(1959, 2000)[1]) is True  # 97.95 < 98.0 although shown 98.0 %
    assert e10(show(197, 200)[1]) is False


@pytest.fixture
def fake() -> Iterator[FakeLlm]:
    f = FakeLlm()
    llm.set_client_factory(lambda: f)
    yield f
    llm.set_client_factory(None)


def _personal(db: Session) -> list[str]:
    out: list[str] = []
    for pc in db.scalars(select(PersonnelCertificate)):
        w = db.get(Worker, pc.worker_id)
        if w is not None:
            out += [w.full_name_en, w.worker_no]
        if pc.cert_no:
            out.append(pc.cert_no)
    return out


@pytest.mark.usefixtures("cert_seed", "clock")
@pytest.mark.parametrize("who", ["noura.qahtani", "sarah.mitchell"])
def test_P4AC106_ai_t16_aggregates_only(
    api: Api, ids: Ids, db: Session, fake: FakeLlm, who: str
) -> None:
    def answer(messages: list[dict[str, Any]]) -> Any:
        for r in last_results(messages):
            for k in r.get("kpis") or []:
                if k["metric"] == "K-72":
                    return say(f"Equipment certificate compliance was {k['value']} [{k['cite']}].")
        raise AssertionError("K-72 not in T16 results")

    fake.script(
        use(
            "get_certification_kpis",
            project_codes=["ANIA-EXP"],
            metrics=["K-72", "K-76", "K-79"],
            group_by=["contractor", "cert_type", "reason_code"],
            period={"preset": "month", "anchor": "2026-09-01"},
        ),
        answer,
    )
    res = api.as_(who).post(
        f"{API}/ai/ask",
        json={
            "project_id": ids.project("ANIA-EXP"),
            "language": "en",
            "question": "What was equipment certificate compliance in September 2026?",
        },
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 200, res.text
    a = res.json()
    assert "97.3 %" in a["text"]
    assert a["citations"][0]["tool"] == "get_certification_kpis"
    sent = fake.sent()
    for s in _personal(db):
        assert s not in sent, s
    for word in ("forged_certificate", "reason_text", "id_number", "not_found"):
        assert word not in sent, word


@pytest.mark.usefixtures("cert_seed", "clock")
def test_T13_returns_E10_E11(db: Session, ids: Ids) -> None:
    from app.ai import tools
    from tests.cert_helpers import P, project

    p = P(db, "faisal.harbi")
    ctx = tools.ToolContext(db=db, p=p, project=project(db, "ANIA-EXP"), as_of=date(2026, 10, 2))
    set_now(datetime(2026, 10, 2, 4, 0, tzinfo=UTC))
    try:
        out, _ = tools.t_get_leading_warnings(ctx, {"project_code": "ANIA-EXP", "months": 2})
    finally:
        set_now(None)
    codes = {w["code"] for w in out["warnings"]}
    assert {"E10", "E11"} <= codes, out


@pytest.mark.usefixtures("cert_seed", "clock")
def test_dashboard_tiles_band_and_charts(api: Api, ids: Ids) -> None:
    c = api.as_("faisal.harbi")
    pid = ids.project("ANIA-EXP")
    body = c.get(f"{API}/kpi/dashboard", params={"project_id": pid, **SEP}).json()
    tiles = {t["metric"]: t for t in body["leading"]}
    for m in ("K-72", "K-76", "K-74", "K-80", "K-81"):
        assert m in tiles, m
    assert tiles["K-72"]["display"] == "97.3 %"
    assert body["cert_band"] is not None
    band = body["cert_band"]
    assert band["on_site_out_of_service"] == 3
    assert any(s["kind"] == "personnel_certificate" for s in band["hook_stages"])
    for ch in ("C16", "C17", "C18"):
        res = c.get(f"{API}/kpi/charts/{ch}", params={"project_id": pid, **SEP})
        assert res.status_code == 200, (ch, res.text)
        assert res.json()["chart"]["series"], ch
    c16 = c.get(f"{API}/kpi/charts/C16", params={"project_id": pid, **SEP}).json()
    assert json.dumps(c16).count("98.0") >= 1  # E10 reference line


@pytest.mark.usefixtures("cert_seed", "clock")
def test_expiring_items_and_action_panel(api: Api, ids: Ids) -> None:
    pid = ids.project("ANIA-EXP")
    items = (
        api.as_("faisal.harbi")
        .get(f"{API}/dashboard/expiring-items", params={"project_id": pid, "within_days": 30})
        .json()["items"]
    )
    kinds = {i["kind"] for i in items}
    assert {"equipment_cert_expiry", "personnel_cert_expiry", "scaffold_inspection_due",
            "defect_rectification_due", "hook_block_date"} <= kinds  # fmt: skip
    rw = [i for i in items if i["kind"] == "equipment_cert_expiry" and i["ref"] == "RW-MC-03"]
    assert rw and rw[0]["days_left"] == 30
    hook = [i for i in items if i["kind"] == "hook_block_date"]
    assert hook and min(i["due_date"] for i in hook) == "2026-10-08"
    # Viewer/Client sees counts only (KC-5): no refs, ids or names
    viewer = (
        api.as_("sarah.mitchell")
        .get(f"{API}/dashboard/expiring-items", params={"project_id": pid, "within_days": 30})
        .json()["items"]
    )
    cert = [i for i in viewer if i["kind"] in ("equipment_cert_expiry", "personnel_cert_expiry")]
    assert cert and all(i["ref"] is None and i["entity_id"] is None for i in cert)
    panel = (
        api.as_("faisal.harbi")
        .get(f"{API}/dashboard/action-panel", params={"project_id": pid})
        .json()["items"]
    )
    got = {i["key"]: i["count"] for i in panel}
    assert got["a_defects_open"] >= 2  # RW-MEWP-07 and FX-TH-04
    assert got["scaffolds_tag_not_valid"] == 3
    assert "hook_block_soon_not_ready" in got
    # VF-6: Nadeem's failed verification was decided (Rejected), so it is not undecided
    assert got["verification_failed_undecided"] == 0


def test_kpi_cache_ignores_the_session_heartbeat(db: Session) -> None:
    """The 30-second last_seen_at heartbeat must not invalidate the KPI facts cache (the
    dashboard fires every chart at once; a rebuild per request made it time out)."""
    import uuid as _uuid
    from datetime import timedelta

    from sqlalchemy import select as sel

    from app.core.clock import now
    from app.models import Project as Pr
    from app.models import User, UserSession

    u = db.scalar(sel(User).limit(1))
    assert u is not None
    s = UserSession(id=_uuid.uuid4(), user_id=u.id, created_at=now(), last_seen_at=now(),
                    expires_at=now() + timedelta(hours=8), last_authenticated_at=now())  # fmt: skip
    db.add(s)
    db.flush()
    db.info.pop("kpi_wrote", None)
    s.last_seen_at = s.last_seen_at + timedelta(seconds=31)
    db.flush()
    assert "kpi_wrote" not in db.info
    pr = db.scalar(sel(Pr).limit(1))
    assert pr is not None
    pr.name_en = pr.name_en + " "
    db.flush()
    assert db.info.get("kpi_wrote") is True
