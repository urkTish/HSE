"""Part B counts that the Q4 KPI catalogue builds on (spec 8-quality §E.4 K-141, K-142, K-149
`ir_inspection`, K-156; Q-IR-12, Q-PUN-03): first-time pass, IR rejection rate, the 6d checklist
opportunities and defects of decided rounds, and punch closure. Q4 owns the KPI engine
(`app/kpi/quality.py`); these functions give it, the Quality home and the Q1 tests one definition.

Rounds kept as "needs confirmation" (Q-IR-14) and round 0 (contractor pre-inspection) are never
counted; voided IRs leave the KPIs (§B.4.2)."""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.quality.q1 import DECIDED_RESULTS, QIrResult, QIrStatus, QPunchStatus
from app.models.field import ChecklistResponse
from app.models.quality import QSignoff
from app.models.quality.q1 import QIr, QIrRound, QPunchItem

R = QIrResult
Ids = Collection[uuid.UUID] | None


def _pct(n: int, d: int) -> Decimal | None:
    if not d:
        return None
    return (Decimal(n) * 100 / Decimal(d)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


@dataclass
class IrCounts:
    first_rounds: int = 0  # K-141 denominator
    first_passes: int = 0  # K-141 numerator
    rounds_decided: int = 0  # K-142 denominator
    rounds_failed: int = 0  # K-142 numerator (rejected or not ready)
    waived: int = 0  # chip
    short_notice: int = 0  # chip
    paper_signoffs: int = 0  # chip (decided rounds signed on paper)
    opportunities: int = 0  # K-149 ir_inspection (applicable scored checklist items)
    defects: int = 0  # K-149 (non-compliant scored items)
    ir_ids: set[uuid.UUID] = field(default_factory=set)

    @property
    def ftpr(self) -> Decimal | None:
        return _pct(self.first_passes, self.first_rounds)

    @property
    def rejection_rate(self) -> Decimal | None:
        return _pct(self.rounds_failed, self.rounds_decided)


def _within(col_site: Any, col_eng: Any, sites: Ids, engs: Ids) -> list[Any]:
    """Grant narrowing (Q-ROL-02 engagement tree, Phase 0 rule 11 sites); None = no narrowing."""
    cs: list[Any] = []
    if sites is not None:
        cs.append(col_site.in_(list(sites) or [uuid.uuid4()]))
    if engs is not None:
        cs.append(col_eng.in_(list(engs) or [uuid.uuid4()]))
    return cs


def ir_counts(
    db: Session,
    project_id: uuid.UUID,
    start: date,
    end: date,
    *,
    site_ids: Ids = None,
    engagement_ids: Ids = None,
) -> IrCounts:
    """Rounds decided in [start, end] (local dates), optionally narrowed to sites / engagements."""
    c = IrCounts()
    rows = db.execute(
        select(QIrRound, QIr)
        .join(QIr, QIr.id == QIrRound.ir_id)
        .where(
            QIr.project_id == project_id,
            QIr.status != QIrStatus.voided,
            QIrRound.decided_date >= start,
            QIrRound.decided_date <= end,
            QIrRound.needs_confirmation.is_(False),
            QIrRound.round_no >= 1,
            *_within(QIr.site_id, QIr.engagement_id, site_ids, engagement_ids),
        )
    ).all()
    for rnd, ir in rows:
        if rnd.result == R.waived:
            c.waived += 1
            continue
        if rnd.result not in DECIDED_RESULTS:
            continue
        c.rounds_decided += 1
        c.ir_ids.add(ir.id)
        if rnd.result in (R.rejected, R.not_ready):
            c.rounds_failed += 1
        if rnd.round_no == 1:
            c.first_rounds += 1
            if rnd.result in (R.approved, R.approved_with_comments):
                c.first_passes += 1
            if ir.short_notice:
                c.short_notice += 1
        if rnd.signoff_id is not None:
            s = db.get(QSignoff, rnd.signoff_id)
            if s is not None and s.channel.value == "paper":
                c.paper_signoffs += 1
        for rid in (rnd.responses or {}).values():
            r = db.get(ChecklistResponse, uuid.UUID(str(rid)))
            if r is not None and not r.voided:
                c.opportunities += r.applicable_count
                c.defects += r.applicable_count - r.compliant_count
    return c


@dataclass
class PunchCounts:
    with_target: int = 0
    closed_on_time: int = 0
    open_a: int = 0
    open_b: int = 0

    @property
    def closure_pct(self) -> Decimal | None:
        return _pct(self.closed_on_time, self.with_target)


def punch_counts(
    db: Session,
    project_id: uuid.UUID,
    start: date,
    end: date,
    as_of: date,
    *,
    site_ids: Ids = None,
    engagement_ids: Ids = None,
) -> PunchCounts:
    """K-156: items closed on or before target with target in the period (≤ as_of) ÷ items with
    target in the period (≤ as_of); chips open A / open B."""
    c = PunchCounts()
    for it in db.scalars(
        select(QPunchItem).where(
            QPunchItem.project_id == project_id,
            QPunchItem.status != QPunchStatus.voided,
            QPunchItem.target_date >= start,
            QPunchItem.target_date <= min(end, as_of),
            *_within(
                QPunchItem.site_id, QPunchItem.responsible_engagement_id, site_ids, engagement_ids
            ),
        )
    ):
        c.with_target += 1
        if (
            it.status == QPunchStatus.closed
            and it.closed_date
            and it.closed_date <= it.target_date
            and it.closed_date <= as_of
        ):
            c.closed_on_time += 1
        if it.status in (QPunchStatus.open, QPunchStatus.ready_for_review):
            if it.category.value == "A":
                c.open_a += 1
            else:
                c.open_b += 1
    return c
