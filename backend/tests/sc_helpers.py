"""Helpers for Phase 6g tests (6g Appendix A world, clock 2026-10-12 10:00 Riyadh). Tests use the
``sc_seed`` fixture (Phase 0-6f template + the 6g seed, cloned per test) and ``sc_clock``."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.scorecard_enums import ScLineStatus, ScScope
from app.models import RpPack, ScCard, ScLine
from app.services.scorecard import calc
from app.services.scorecard import common as cm
from tests.cert_helpers import API, P, expect, project
from tests.heat_helpers import eng, local, notified, tick, uid

__all__ = [
    "API",
    "P",
    "card",
    "eng",
    "expect",
    "line",
    "local",
    "notified",
    "pack",
    "project",
    "sg1",
    "tick",
    "uid",
]

CLOCK = datetime(2026, 10, 12, 7, 0, tzinfo=UTC)  # 10:00 Asia/Riyadh
SEP = date(2026, 9, 1)


def card(
    db: Session, pcode: str, short: str, month: str = "2026-09", scope: ScScope = ScScope.own
) -> ScCard:
    from app.services.scorecard import cards

    m = cm.parse_month(month)
    e = eng(db, pcode, short)
    for c in cards.current(db, project(db, pcode).id, m, scope):
        if c.engagement_id == e.id:
            return c
    raise AssertionError((pcode, short, month))


def line(db: Session, c: ScCard, code: str) -> ScLine:
    x = db.scalar(select(ScLine).where(ScLine.card_id == c.id, ScLine.metric_code == code))
    assert x is not None, code
    return x


def pack(db: Session, doc_no: str, rev: int | None = None) -> RpPack:
    stmt = select(RpPack).where(RpPack.doc_no == doc_no).order_by(RpPack.revision.desc())
    for x in db.scalars(stmt):
        if rev is None or x.revision == rev:
            return x
    raise AssertionError(doc_no)


SG1_VALUES = {
    "SM-TRIR": "0.24",
    "SM-LTIFR": "0.40",
    "SM-LTISR": "1.60",
    "SM-HIPO": "0.16",
    "SM-OBS": "125",
    "SM-UNSAFE-CLOSE": "95",
    "SM-CA-ONTIME": "75",
    "SM-CA-OVERDUE": "0.375",
    "SM-PTW-AUDIT": "90",
    "SM-PTW-CRIT": str(Decimal(100) / 12),
    "SM-PTW-CLOSE": "100",
    "SM-EQ-CERT": "100",
    "SM-PERS-CERT": "95",
    "SM-TRAIN": "97",
    "SM-INDUCT": "99",
    "SM-FIT": "98",
    "SM-HEAT-WELF": "96",
    "SM-HEAT-BAN": "0",
    "SM-EMG-COVER": "100",
    "SM-CHECKLIST": "92",
    "SM-INSP-COVER": "100",
    "SM-TBT": "90",
    "SM-SPILL": "0",
}
SG1_STATUS = {
    "SM-SCAF-TAG": ScLineStatus.not_applicable,
    "SM-EMG-EQUIP": ScLineStatus.not_applicable,
    "SM-WASTE-COC": ScLineStatus.not_applicable,
    "SM-AUDIT": ScLineStatus.insufficient_volume,
    "SM-NOTIF": ScLineStatus.source_not_live,
    "SM-LESSON-ACK": ScLineStatus.source_not_live,
}


def sg1(
    values: dict[str, str] | None = None,
    status: dict[str, ScLineStatus] | None = None,
    caps: list | None = None,
) -> calc.CardResult:  # type: ignore[type-arg]
    from app.core.scorecard_enums import ScGrade

    vals = {**SG1_VALUES, **(values or {})}
    st = {**SG1_STATUS, **(status or {})}
    lines = [
        calc.Line(
            m.code.value,
            m.pillar.value,
            Decimal(m.weight),
            Decimal(m.good),
            Decimal(m.bad),
            st.get(m.code.value, ScLineStatus.scored),
            Decimal(vals[m.code.value]) if m.code.value in vals else None,
        )
        for m in cm.METRICS
    ]
    return calc.compute(
        lines,
        {p.value: Decimal(w) for p, w in cm.PILLARS.items()},
        [(g, Decimal(s)) for g, s in cm.BANDS],
        caps if caps is not None else [ScGrade.C],
        Decimal(60),
    )
