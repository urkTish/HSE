"""Scorecard and report KPIs K-132…K-135 (spec 6g §6.7, GK-1).

Computed from stored cards, watch-list entries, disputes and packs (K-R1), reached through the
per-request facts as the 6f KPIs. Attribution: cards → their month; disputes → the local date of
due_at; packs → due_on. The contractor filter (with descendants, K-R5) applies to K-132 and
K-133."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.hse_enums import KpiKind, KpiMetric, NullReason
from app.core.scorecard_enums import (
    RpType,
    ScCardStatus,
    ScRemarkKind,
    ScRemarkStatus,
    ScScope,
    ScWatchLevel,
)
from app.kpi import engine as engine_mod
from app.kpi.engine import Agg, Component, Engine, Result
from app.kpi.followup import _end, _memo, cutoff, ffacts
from app.models import RpPack, ScCard, ScRemark, ScWatchEntry

M = KpiMetric
D = Decimal


def _months(start: date, end: date) -> list[date]:
    out, m = [], start.replace(day=1)
    while m <= end:
        out.append(m)
        m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return out


def cards(e: Engine, start: date, end: date) -> list[ScCard]:
    """Own cards with a grade of the months in the window (Final revision, else Issued)."""
    f = ffacts(e)
    if f is None:
        return []
    months = _months(start, end)
    rows: list[ScCard] = _memo(
        f,
        ("sc_cards", start, end),
        lambda: list(
            f.db.scalars(
                select(ScCard).where(
                    ScCard.project_id.in_(f.pids),
                    ScCard.scope == ScScope.own,
                    ScCard.month.in_(months),
                    ScCard.status.in_([ScCardStatus.issued, ScCardStatus.final]),
                )
            )
        ),
    )
    return [c for c in rows if e.flt.eng_ok(c.engagement_id)]


def _k132(e: Engine, a: Agg) -> Result:
    cs = [c for c in cards(e, a.window.start, _end(e, a.window))
          if c.grade is not None and c.score is not None]  # fmt: skip
    num = sum((c.score * c.month_man_hours for c in cs if c.score is not None), D(0))
    den = sum((c.month_man_hours for c in cs), D(0))
    if not den:
        return Result(M.K132, None, None, None, NullReason.NO_DENOMINATOR)
    res = Result(M.K132, num / den, num, den)
    mix: dict[str, int] = {}
    for c in cs:
        k = c.grade.value if c.grade else "—"
        mix[k] = mix.get(k, 0) + 1
    res.components = [Component(f"grade_{k}", f"Grade {k}", f"التقدير {k}", D(v), KpiKind.count_)
                      for k, v in sorted(mix.items())]  # fmt: skip
    return res


def entries(e: Engine, as_of: date) -> list[ScWatchEntry]:
    from app.services.scorecard.common import local_day  # noqa: PLC0415

    f = ffacts(e)
    if f is None:
        return []
    rows: list[ScWatchEntry] = _memo(f, "sc_watch", lambda: list(f.db.scalars(
        select(ScWatchEntry).where(ScWatchEntry.project_id.in_(f.pids)))))  # fmt: skip
    return [w for w in rows if e.flt.eng_ok(w.engagement_id) and local_day(w.opened_at) <= as_of
            and (w.closed_at is None or local_day(w.closed_at) > as_of)]  # fmt: skip


def _k133(e: Engine, a: Agg) -> Result:
    ws = entries(e, _end(e, a.window))
    res = e._count(M.K133, len(ws))
    res.components = [Component(lv.value, lv.value, lv.value,
                                D(sum(w.level == lv for w in ws)), KpiKind.count_)
                      for lv in ScWatchLevel]  # fmt: skip
    return res


def _k134(e: Engine, a: Agg) -> Result:
    from app.services.scorecard.common import local_day  # noqa: PLC0415

    f = ffacts(e)
    if f is None:
        return e._pct(M.K134, 0, 0)
    rows: list[ScRemark] = _memo(f, "sc_disputes", lambda: list(f.db.scalars(
        select(ScRemark).where(ScRemark.project_id.in_(f.pids),
                               ScRemark.kind == ScRemarkKind.dispute,
                               ScRemark.status != ScRemarkStatus.withdrawn))))  # fmt: skip
    cut = cutoff(_end(e, a.window))
    den = [r for r in rows if r.due_at is not None and r.due_at <= cut
           and a.window.start <= local_day(r.due_at) <= a.window.end]  # fmt: skip
    num = [r for r in den if r.resolved_at is not None and r.due_at is not None
           and r.resolved_at <= r.due_at and r.status == ScRemarkStatus.resolved]  # fmt: skip
    return e._pct(M.K134, len(num), len(den))


def _k135(e: Engine, a: Agg) -> Result:
    from app.services.scorecard.common import local_day  # noqa: PLC0415

    f = ffacts(e)
    if f is None:
        return e._pct(M.K135, 0, 0)
    rows: list[RpPack] = _memo(
        f,
        "sc_mcr",
        lambda: list(
            f.db.scalars(
                select(RpPack).where(
                    RpPack.project_id.in_(f.pids), RpPack.report_type == RpType.MCR
                )
            )
        ),
    )
    end = min(_end(e, a.window), a.window.end)
    rev0 = {p.doc_no: p for p in rows if p.revision == 0}
    den = [p for p in rev0.values() if p.due_on is not None
           and a.window.start <= p.due_on <= end]  # fmt: skip
    num = [p for p in den if p.issued_at is not None and p.due_on is not None
           and local_day(p.issued_at) <= p.due_on]  # fmt: skip
    return e._pct(M.K135, len(num), len(den))


engine_mod._DISPATCH.update({M.K132: _k132, M.K133: _k133, M.K134: _k134, M.K135: _k135})
