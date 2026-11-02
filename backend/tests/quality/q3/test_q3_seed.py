"""Appendix A.6 / A.8 values of the Q3 seed for September 2026 (RUH-CCH): K-160…K-168 inputs,
QX18 coverage and time out of range, QX13 hold, QX16 mock recall (spec 8-quality §E.4)."""

from decimal import Decimal

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models import Project, Zone
from app.models.quality.q3 import QExcursion, QHold, QRecall, QStorageZone
from app.services.quality.q3 import holds as hold_svc
from app.services.quality.q3 import metrics, storage

D = Decimal


def test_september_metrics(q_seed: None) -> None:
    with get_sessionmaker()() as db:
        p = db.scalar(select(Project).where(Project.code == "RUH-CCH"))
        assert p is not None
        m = metrics.month(db, p, 2026, 9)
        assert m["k160"]["receipts"] == 640 and m["k160"]["rejected"] == 12
        assert m["k160"]["value"] == D("1.9") and m["k160"]["deviation_rate"] == D("3.9")
        assert m["k161"]["excursions"] == 5 and m["k161"]["zone_months"] == 7
        assert m["k161"]["value"] == D("0.71")
        assert m["k162"]["monitored_minutes"] == 301_980 and m["k162"]["out_minutes"] == 640
        assert m["k162"]["value"] == D("0.21")
        assert m["k163"] == {
            "shipments": 1250,
            "on_time": 1190,
            "in_full": 1210,
            "otif": 1165,
            "value": D("93.2"),
        }
        assert m["k164"]["value"] == D("0.022") and m["k164"]["ppm"] == D("221.5")
        assert m["k165"]["value"] == D("97.0")
        assert m["k166"]["value"] == D("97.0")
        assert m["k167"]["value"] == D("98.9") and m["k167"]["with_data"] == 380
        assert m["k168"] == {"done": 114, "due": 120, "value": D("95.0")}


def test_qx18_chilled_zone_and_named_records(q_seed: None) -> None:
    """AC-Q3-21: Z-CHL1 September monitored 43,110 min, TOR 0.31 %, coverage 99.8 %."""
    with get_sessionmaker()() as db:
        z = db.scalar(
            select(QStorageZone)
            .join(Zone, Zone.id == QStorageZone.zone_id)
            .where(Zone.code == "Z-CHL1")
        )
        assert z is not None
        period, mon, out = storage.month_tor(db, z, 2026, 9)
        assert (period, mon, out) == (43_200, 43_110, 135)
        assert (D(out) * 100 / mon).quantize(D("0.01")) == D("0.31")
        assert (D(mon) * 100 / period).quantize(D("0.1")) == D("99.8")
        x = db.scalar(select(QExcursion).where(QExcursion.exc_no == "EXC-RUH-CCH-2026-0041"))
        assert x is not None and x.severity.value == "major" and x.duration_min == 210
        assert x.max_deviation == D("4.20")
        h = db.get(QHold, x.hold_id)
        assert h is not None and h.hold_no == "HLD-RUH-CCH-2026-0112"
        assert len(hold_svc.lines_of(db, h)) == 14
        r = db.scalar(select(QRecall).where(QRecall.rcl_no == "RCL-RUH-CCH-2026-0002"))
        assert r is not None and r.effectiveness_pct == D("100.0")
