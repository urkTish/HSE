"""KPI page, SPC, sigma, packs, exports and AI tools (spec 8-quality §E.4–§E.9; AC-Q4-20,
-22…-34 and AC-Q0-03 for the KPI page)."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import make_transient

from app.core.quality.q4 import QSpcType
from app.db.session import get_sessionmaker
from app.kpi import quality as qk
from app.models import Project, User
from app.services.quality.q4 import spc
from tests.conftest import Api, Ids
from tests.quality.q0.qh import API, err, ok

D = Decimal


# ---- pure maths ----------------------------------------------------------------------------------


def test_AC20_sigma_and_dpmo() -> None:
    assert qk.dpmo_of(31, 4820) == D("6431.5")
    assert qk.sigma_level(D("6431.5"))[0] == D("3.99")
    assert qk.sigma_level(D("6210"))[0] == D("4.00")
    assert qk.sigma_level(D("66807"))[0] == D("3.00")
    assert qk.sigma_level(D("233"))[0] == D("5.00")
    assert qk.sigma_level(D("3.4"))[0] == D("6.00")
    assert qk.sigma_level(D("0")) == (None, "> 6.0")


def test_AC21_pareto() -> None:
    par = qk.pareto(
        {
            "workmanship": 6,
            "material": 3,
            "design_documentation": 2,
            "testing_failure": 1,
            "dimensional": 1,
            "other": 1,
        }
    )
    assert [r["cumulative_pct"] for r in par["rows"]] == [
        "42.9",
        "64.3",
        "78.6",
        "85.7",
        "92.9",
        "100.0",
    ]
    assert par["vital_few"] == 4


def test_AC22_xbar_r_and_capability() -> None:
    from app.seed_quality_q4 import qx22_sets

    sets = qx22_sets()
    pts = [spc.Point(str(i), str(i), v) for i, v in enumerate(sets)]
    r = spc.evaluate(QSpcType.xbar_r, pts, None, 20, lsl=40.0)
    assert (r["cl"], r["ucl"], r["lcl"]) == ("46.800", "49.971", "43.629")
    assert r["r_cl"] == "3.100" and r["r_ucl"] == "7.979" and r["r_lcl"] == "0.000"
    assert r["provisional"] is False and r["capability"]["cpk"] == "1.24"
    assert D(r["ucl"]).quantize(D("0.01")) == D("49.97") and D(r["lcl"]).quantize(D("0.01")) == D(
        "43.63"
    )


def test_AC23_p_chart_limits() -> None:
    pb = 27 / 141
    u35, l35 = spc.p_limits(pb, 35)
    u40, l40 = spc.p_limits(pb, 40)
    assert round(u35, 3) == 0.391 and l35 == 0
    assert round(u40, 3) == 0.378 and round(l40, 3) == 0.005


def test_AC24_provisional_and_no_limits() -> None:
    pts = [spc.Point(str(i), str(i), [10.0 + (i % 3) * 0.1]) for i in range(12)]
    r = spc.evaluate(QSpcType.imr, pts, None, 20)
    assert r["provisional"] is True and r["limits_drawn"] is True
    r6 = spc.evaluate(QSpcType.imr, pts[:6], None, 20)
    assert r6["limits_drawn"] is False and "ucl" not in r6


def test_AC25_signals() -> None:
    base = [10.0, 10.4, 9.6, 10.2, 9.8, 10.1, 9.9, 10.3, 9.7, 10.0]
    r8 = spc.signals(base + [10.1] * 8, 10.0, [0.2] * 18, [10.6] * 18, [9.4] * 18)
    assert (17, 4) in r8
    r1 = spc.signals(base + [11.0], 10.0, [0.2] * 11, [10.6] * 11, [9.4] * 11)
    assert (10, 1) in r1
    r2 = spc.signals(base + [10.5, 10.1, 10.5], 10.0, [0.2] * 13, [10.6] * 13, [9.4] * 13)
    assert (12, 2) in r2


def test_AC25_signal_notifies_owner_no_ncr(q_seed: None) -> None:
    from sqlalchemy import func

    from app.models import Notification
    from app.models.quality import QNcr
    from app.models.quality.q4 import QSpcChart

    with get_sessionmaker()() as db:
        ch = db.scalar(select(QSpcChart).where(QSpcChart.code == "C40-STRENGTH"))
        assert ch is not None
        res = spc.chart_read(db, ch)["result"]
        assert res["cl"] == "46.800" and res["provisional"] is False
        assert res["capability"]["cpk"] == "1.24"
        ch.baseline, ch.baseline_keys = "frozen", [p["key"] for p in res["points"][:20]]  # type: ignore[assignment]
        ncr0 = db.scalar(select(func.count()).select_from(QNcr))
        ch.usl = None
        ch.signals_sent = []
        # an out-of-control point: lower every specimen of the last set
        from app.models.quality.q2 import QTestSpecimen

        last = res["points"][-1]["key"]
        for s in db.scalars(
            select(QTestSpecimen).where(
                QTestSpecimen.test_request_id == last, QTestSpecimen.age_days == 28
            )
        ):
            s.values = {"strength": "41.0"}
        db.flush()
        n0 = db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == ch.owner_user_id)
        )
        out = spc.signal_job(db, None)
        assert out["q4_spc"] >= 1
        n1 = db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == ch.owner_user_id)
        )
        assert (n1 or 0) > (n0 or 0)
        assert db.scalar(select(func.count()).select_from(QNcr)) == ncr0
        db.rollback()


# ---- KPI page --------------------------------------------------------------------------------------


def test_kpi_page_profiles_and_scope(q_seed: None, api: Api, ids: Ids) -> None:
    """AC-Q4-33 tiles by profile; AC-Q0-03 the scope-N-only user gets 403; Viewer: no costs."""
    hatem, reem = api.as_("hatem.shehri"), api.as_("reem.mutairi")
    q = {"date_from": "2026-09-01", "date_to": "2026-09-30"}
    a = ok(hatem.get(f"{API}/projects/{ids.project('ANIA-EXP')}/quality/kpis", params=q))
    kp = {t["kpi"] for t in a["tiles"]}
    assert "K-141" in kp and "K-160" not in kp and "K-146" in kp
    k141 = next(t for t in a["tiles"] if t["kpi"] == "K-141")
    assert k141["display"] == "80.0 %" and k141["target"] == "90.000" and k141["rag"] == "red"
    assert [w["code"] for w in a["warnings"]] == ["E27"]
    assert a["charts"]["C43"]["vital_few"] == 4 and len(a["charts"]["C42"]) == 12
    r = ok(reem.get(f"{API}/projects/{ids.project('RUH-CCH')}/quality/kpis", params=q))
    kr = {t["kpi"] for t in r["tiles"]}
    assert "K-160" in kr and "K-141" not in kr and "C49" in r["charts"]
    err(
        api.as_("abdullah.dossary").get(
            f"{API}/projects/{ids.project('ANIA-EXP')}/quality/kpis", params=q
        ),
        403,
        "FORBIDDEN",
    )
    s = ok(
        api.as_("sarah.mitchell").get(
            f"{API}/projects/{ids.project('ANIA-EXP')}/quality/kpis", params=q
        )
    )
    k148 = next(t for t in s["tiles"] if t["kpi"] == "K-148")
    assert k148["value"] is None and "C45" not in s["charts"]


def test_AC27_dismissed_excursion(q_seed: None) -> None:
    from app.models import Zone
    from app.models.quality.q3 import QExcursion

    with get_sessionmaker()() as db:
        p = db.scalar(select(Project).where(Project.code == "RUH-CCH"))
        dock = db.scalar(select(Zone.id).where(Zone.code == "Z-DOCK"))
        x = db.scalar(
            select(QExcursion)
            .where(QExcursion.zone_id == dock, QExcursion.transient.is_(False))
            .order_by(QExcursion.started_at)
            .limit(1)
        )
        assert p is not None and x is not None
        x.status = "dismissed"  # type: ignore[assignment]
        db.flush()
        e = qk.Engine(db, p, date(2026, 9, 1), date(2026, 9, 30), date(2026, 10, 6))
        r = e.result(qk.K.K161)
        assert (
            r.numerator == 4
            and next(c["value"] for c in r.chips if c["code"] == "dismissed") == "1"
        )
        db.rollback()


def test_AC28_critical_excursion_raises_E28(q_seed: None) -> None:
    from app.models.quality.q3 import QExcursion

    with get_sessionmaker()() as db:
        p = db.scalar(select(Project).where(Project.code == "RUH-CCH"))
        assert p is not None and qk.warnings(db, p, date(2026, 9, 1)) == []
        x = db.scalar(
            select(QExcursion)
            .where(
                QExcursion.project_id == p.id,
                QExcursion.kind == "storage",
                QExcursion.transient.is_(False),
            )
            .limit(1)
        )
        assert x is not None
        db.expunge(x)
        make_transient(x)
        x.id = None  # type: ignore[assignment]
        x.exc_no = "EXC-RUH-CCH-2026-0099"
        from app.core.quality.q3 import QExcursionSeverity

        x.severity = QExcursionSeverity.critical
        x.started_at = x.started_at.replace(day=25)
        x.ended_at = x.started_at + timedelta(hours=3)
        x.ncr_id = None
        x.hold_id = None
        db.add(x)
        db.flush()
        codes = [w["code"] for w in qk.warnings(db, p, date(2026, 9, 1))]
        assert codes == ["E28"]
        db.rollback()


# ---- packs, exports ---------------------------------------------------------------------------


def test_AC29_qmr_pack_with_hijri(q_seed: None, api: Api, ids: Ids) -> None:
    from app.models.scorecard import RpPack
    from app.services.scorecard import packs

    hatem, rania = api.as_("hatem.shehri"), api.as_("rania.zahrani")
    pk = ok(
        hatem.post(
            f"{API}/report-packs",
            json={"report_type": "QMR", "project_id": ids.project("ANIA-EXP"), "month": "2026-09"},
        ),
        201,
    )
    assert pk["doc_no"] == "QMR-ANIA-EXP-2026-09"
    ok(
        hatem.post(
            f"{API}/report-packs/{pk['id']}/transitions", json={"action": "submit_for_review"}
        )
    )
    ok(rania.post(f"{API}/report-packs/{pk['id']}/transitions", json={"action": "review"}))
    done = ok(hatem.post(f"{API}/report-packs/{pk['id']}/transitions", json={"action": "issue"}))
    assert done["status"] == "issued" and {"pdf_en", "pdf_ar"} <= {f["kind"] for f in done["files"]}
    with get_sessionmaker()() as db:
        row = db.get(RpPack, pk["id"])
        assert row is not None
        ctl = packs.to_doc(db, row).control
        assert any("Hijri" in c[0] for c in ctl) and any(c[0] == "Issue date" for c in ctl)
        keys = [s["key"] for s in row.snapshot["sections"]]
        assert keys[:2] == ["summary", "ncrs"] and "construction" in keys
    # the Viewer reads issued packs only and cannot prepare (280 R)
    sarah = api.as_("sarah.mitchell")
    assert sarah.get(f"{API}/report-packs/{pk['id']}").status_code == 200
    err(
        sarah.post(
            f"{API}/report-packs",
            json={"report_type": "QNCR", "project_id": ids.project("ANIA-EXP"), "month": "2026-09"},
        ),
        403,
        "FORBIDDEN",
    )


def test_AC30_q4_exports(q_seed: None, api: Api, ids: Ids) -> None:
    pid = ids.project("RUH-CCH")
    for ds in ("quality_documents", "quality_audits"):
        res = api.as_("reem.mutairi").post(
            f"{API}/exports", json={"dataset": ds, "project_id": pid}
        )
        assert res.status_code == 201, res.text


# ---- AI tools -----------------------------------------------------------------------------------------


def _ctx(db: object, email: str, code: str) -> object:
    from app.ai.tools import ToolContext
    from app.services.permissions import build_principal

    u = db.scalar(select(User).where(User.email == email))  # type: ignore[attr-defined]
    p = db.scalar(select(Project).where(Project.code == code))  # type: ignore[attr-defined]
    return ToolContext(db, build_principal(db, u, None), p, date(2026, 10, 6))  # type: ignore[arg-type]


def test_AC31_AC32_ai_tools(q_seed: None) -> None:
    from app.ai import tools

    with get_sessionmaker()() as db:
        c = _ctx(db, "faisal.harbi@example.com", "ANIA-EXP")
        out = tools.run(
            c,
            "get_quality_kpis",
            {
                "period": {"start": "2026-07-01", "end": "2026-09-30"},  # type: ignore[arg-type]
                "metrics": ["K-143"],
                "group_by": "supplier",
            },
        )
        groups = out["projects"][0]["groups"]
        assert groups and {"key", "supplier", "ncrs_raised"} <= set(groups[0])
        s = tools.run(c, "search_ncrs", {"filters": {"opened_from": "2026-09-29"}})  # type: ignore[arg-type]
        n44 = next(x for x in s["ncrs"] if x["ncr_no"] == "NCR-ANIA-EXP-2026-0044")
        names = {u.full_name_en for u in db.scalars(select(User))}
        assert not any(v in names for v in n44.values() if isinstance(v, str))
        assert "raised_by" not in n44 and "owner" not in n44
        sarah = _ctx(db, "sarah.mitchell@example.com", "ANIA-EXP")
        r = tools.run(sarah, "search_ncrs", {})  # type: ignore[arg-type]
        assert r.get("no_access") is True
        k = tools.run(
            sarah, "get_quality_kpis", {"period": {"start": "2026-09-01", "end": "2026-09-30"}}
        )  # type: ignore[arg-type]
        assert "projects" in k
        rc = _ctx(db, "faisal.harbi@example.com", "RUH-CCH")
        cc = tools.run(
            rc, "get_cold_chain_summary", {"period": {"start": "2026-09-01", "end": "2026-09-30"}}
        )  # type: ignore[arg-type]
        pr = cc["projects"][0]
        assert pr["k161"] == "0.71" and pr["k162"] == "0.21 %"
        frz = next(z for z in pr["zones"] if z["zone"] == "Z-FRZ1")
        assert frz["excursions"].get("major") == 1
        assert next(z for z in pr["zones"] if z["zone"] == "Z-PHR1")["mkt_c_by_point"]
        st = tools.run(rc, "get_spc_status", {})  # type: ignore[arg-type]
        assert {x["code"] for x in st["charts"]} == {"RCV-REJECT-WK", "FRZ1-DAILY"}
        lw = tools.run(c, "get_leading_warnings", {})  # type: ignore[arg-type]
        assert any(w["code"] == "E27" for w in lw.get("quality_warnings", []))
        db.rollback()
