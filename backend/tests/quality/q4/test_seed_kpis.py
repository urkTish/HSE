"""Appendix A.8: every September 2026 KPI value of both seed projects (spec 8-quality §E.10,
AC-Q4-17…-21, AC-Q4-26, AC-Q4-28). "Generator value" rows are asserted as computed once and
recorded in D-367."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.quality.q4 import QKpi as K
from app.db.session import get_sessionmaker
from app.kpi import quality as qk
from app.models import Project

D = Decimal


def _engine(db: object, code: str) -> qk.Engine:
    p = db.scalar(select(Project).where(Project.code == code))  # type: ignore[attr-defined]
    return qk.Engine(db, p, date(2026, 9, 1), date(2026, 9, 30), date(2026, 10, 6))  # type: ignore[arg-type]


def chip(r: qk.Result, code: str) -> str | None:
    return next(c["value"] for c in r.chips if c["code"] == code)


def test_ania_september(q_seed: None) -> None:
    with get_sessionmaker()() as db:
        e = _engine(db, "ANIA-EXP")
        r = e.result
        assert r(K.K141).value == D("80.0") and r(K.K142).value == D("19.1")  # QX2, AC-Q4-17
        k143 = r(K.K143)
        assert k143.extra["by_class"] == {"minor": 9, "major": 4, "critical": 1}
        assert k143.extra["open"] == 11
        assert r(K.K144).extra["buckets"] == {"0_30": 8, "31_60": 2, "61_90": 1, "over_90": 0}
        assert r(K.K145).value == D("12") and r(K.K146).value == D("80.0")  # AC-Q4-18
        assert r(K.K147).value == D("7.1")
        k148 = r(K.K148)  # QX26, AC-Q4-19
        assert k148.value == D("186450.00")
        assert chip(k148, "internal") == "171200.00" and chip(k148, "external") == "15250.00"
        assert chip(k148, "recovered") == "22600.00" and chip(k148, "copq_pct") == "0.38"
        ir = e.dpmo()["ir_inspection"]  # QX24, AC-Q4-20
        assert (ir["opportunities"], ir["defects"]) == (4820, 31)
        assert ir["dpmo"] == "6431.5" and ir["sigma"] == "3.99"
        par = r(K.K150).extra["pareto"]  # QX25, AC-Q4-21
        assert [x["cumulative_pct"] for x in par["rows"]] == [
            "42.9",
            "64.3",
            "78.6",
            "85.7",
            "92.9",
            "100.0",
        ]
        assert par["vital_few"] == 4
        assert (r(K.K151).numerator, r(K.K151).denominator, r(K.K151).value) == (2, 38, D("5.3"))
        assert (r(K.K152).numerator, r(K.K152).denominator, r(K.K152).value) == (6, 212, D("2.8"))
        assert (r(K.K153).numerator, r(K.K153).denominator, r(K.K153).value) == (5, 120, D("4.2"))
        assert (r(K.K154).numerator, r(K.K154).denominator, r(K.K154).value) == (46, 48, D("95.8"))
        assert (r(K.K155).numerator, r(K.K155).denominator, r(K.K155).value) == (60, 64, D("93.8"))
        assert (r(K.K156).numerator, r(K.K156).denominator, r(K.K156).value) == (24, 46, D("52.2"))
        assert r(K.K158).value == D("100.0") and r(K.K158).denominator == 2
        assert r(K.K159).value == D("100.0")
        assert r(K.K169).value == 1
        p = e.project
        codes = [x["code"] for x in qk.warnings(db, p, date(2026, 9, 1))]
        assert codes == ["E27"]  # AC-Q4-28


def test_ruh_september(q_seed: None) -> None:
    with get_sessionmaker()() as db:
        e = _engine(db, "RUH-CCH")
        r = e.result
        assert r(K.K143).extra["by_class"] == {"minor": 6, "major": 3, "critical": 0}
        k160 = r(K.K160)
        assert (k160.numerator, k160.denominator, k160.value) == (12, 640, D("1.9"))
        assert chip(k160, "deviation") == "3.9"
        assert r(K.K161).value == D("0.71") and r(K.K162).value == D("0.21")
        assert r(K.K163).value == D("93.2") and r(K.K164).value == D("0.022")
        assert r(K.K165).value == D("97.0") and r(K.K166).value == D("97.0")
        assert r(K.K167).value == D("98.9") and r(K.K167).numerator == 376
        assert r(K.K168).value == D("95.0") and r(K.K168).denominator == 120
        k169 = r(K.K169)
        assert k169.value == 3 and chip(k169, "per_1000") == "2.40"
        assert r(K.K158).value == D("100.0") and r(K.K158).denominator == 2
        # generator values (D-367)
        assert r(K.K154).value == D("100.0")
        assert r(K.K155).value == D("100.0")
        assert {k: v["dpmo"] for k, v in e.dpmo().items()} == {
            "receiving": "1171.9",
            "picking_fefo": "30000.0",
            "delivery": "40000.0",
            "inventory": "30000.0",
        }
        assert qk.warnings(db, e.project, date(2026, 9, 1)) == []  # AC-Q4-28


def test_supplier_scores_and_targets(q_seed: None) -> None:
    from app.models.quality import QSupplier
    from app.models.quality.q4 import QSupplierScore

    with get_sessionmaker()() as db:
        rmx = db.scalar(select(QSupplier).where(QSupplier.supplier_code == "RMX"))
        s = db.scalar(select(QSupplierScore).where(QSupplierScore.supplier_id == rmx.id))  # type: ignore[union-attr]
        assert s is not None and s.score == D("72.2") and s.band == "B"  # QX19
        e = _engine(db, "ANIA-EXP")
        assert qk.target_of(db, e.project.id, K.K141, date(2026, 9, 30)) == D("90")
        assert qk.rag(K.K141, D("80.0"), D("90")) == "red"
        assert qk.rag(K.K141, D("82.0"), D("90")) == "amber"
        assert qk.rag(K.K141, D("90.0"), D("90")) == "green"
        k148 = e.result(K.K148)  # the K-148 objective is COPQ % of work value (A.7)
        assert qk.rag_for(k148, D("0.5")) == "green"
