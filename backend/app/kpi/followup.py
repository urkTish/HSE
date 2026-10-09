"""Incident follow-up KPIs K-127…K-131 (spec 6f-incident-followup §6.2, FK-1).

Computed from the stored 6f records on the request's session (reached through the per-request heat
facts, as the 6c-6e KPIs). Attribution (FK-1): requirements → local date of due_at, contractor =
the incident's responsible engagement (GOSI → the filer engagement), site = the incident site;
lessons → publish_due_on and the source incident's responsible engagement; distribution items →
ack_due_on and the item engagement; checks → completion date. The contractor filter already holds
the descendants (K-R5). "≤ as_of" for requirements is the earlier of now and the end of as_of."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.hse_enums import ExternalBody, KpiKind, KpiMetric
from app.kpi import engine as engine_mod
from app.kpi.engine import Agg, Component, Engine, Result
from app.kpi.periods import Window

UUID = uuid.UUID
M = KpiMetric
D = Decimal


@dataclass
class FFacts:
    db: Session
    pids: list[UUID]
    memo: dict[Any, Any] = field(default_factory=dict)


def ffacts(e: Engine) -> FFacts | None:
    m: FFacts | None = getattr(e, "_fu_facts", None)
    if m is None:
        hf = getattr(e.facts, "heat", None)
        if hf is None:
            return None
        m = FFacts(hf.db, list(hf.pids))
        e._fu_facts = m  # type: ignore[attr-defined]
    return m


def _memo(f: FFacts, key: Any, fn: Any) -> Any:
    if key not in f.memo:
        f.memo[key] = fn()
    return f.memo[key]


def _end(e: Engine, w: Window) -> date:
    return min(e.as_of, w.end)


def cutoff(d: date) -> datetime:
    from app.services.followup.common import end_of_day  # noqa: PLC0415

    return min(now(), end_of_day(d))


# ---- requirements (K-127, K-128) -----------------------------------------------------------------


@dataclass
class Req:
    id: UUID
    project_id: UUID
    rule_code: str
    body: str
    stage: str
    statutory: bool
    due_at: datetime
    due_day: date
    first_sub: datetime | None
    counted: bool  # not waived, still required
    eng: UUID | None
    site: UUID
    incident_ref: str


def requirements(db: Session, pids: list[UUID]) -> list[Req]:
    from app.core.followup_enums import FuRuleSource  # noqa: PLC0415
    from app.models import FuRequirement, Incident  # noqa: PLC0415
    from app.services.followup import common as fc  # noqa: PLC0415
    from app.services.followup import requirements as rq  # noqa: PLC0415

    rows = list(db.scalars(select(FuRequirement).where(FuRequirement.project_id.in_(pids))))
    subs = rq._valid_subs(db, [r.id for r in rows])
    out = []
    for r in rows:
        inc = db.get(Incident, r.incident_id)
        if inc is None:
            continue
        s = subs.get(r.id, [])
        out.append(
            Req(
                r.id, r.project_id, r.rule_code, r.body.value, r.stage.value,
                r.source == FuRuleSource.statutory, r.due_at, fc.local_day(r.due_at),
                s[0].submitted_at if s else None, r.required and r.waived_at is None,
                r.filer_engagement_id if r.body == ExternalBody.gosi
                else inc.responsible_engagement_id,
                inc.site_id, inc.ref,
            )
        )  # fmt: skip
    return out


def reqs(e: Engine) -> list[Req]:
    f = ffacts(e)
    if f is None:
        return []
    rows: list[Req] = _memo(f, "reqs", lambda: requirements(f.db, f.pids))
    return [r for r in rows if e.flt.site_ok(r.site) and e.flt.eng_ok(r.eng)]


def timeliness(e: Engine, w: Window) -> tuple[list[Req], list[Req]]:
    """(counted requirements due in the window up to as_of, of which first submission on time)."""
    cut = cutoff(_end(e, w))
    den = [r for r in reqs(e) if r.counted and w.start <= r.due_day <= w.end and r.due_at <= cut]
    num = [r for r in den if r.first_sub is not None and r.first_sub <= r.due_at]
    return num, den


def overdue_at(e: Engine, w: Window) -> list[Req]:
    cut = cutoff(_end(e, w))
    return [
        r
        for r in reqs(e)
        if r.counted and r.due_at < cut and (r.first_sub is None or r.first_sub > cut)
    ]


def _pct(n: int, d: int) -> Decimal | None:
    return D(n) * 100 / D(d) if d else None


def _k127(e: Engine, a: Agg) -> Result:
    num, den = timeliness(e, a.window)
    res = e._pct(M.K127, len(num), len(den))
    st_n = sum(r.statutory for r in num)
    st_d = sum(r.statutory for r in den)
    res.components = [
        Component("statutory", "Statutory", "نظامية", _pct(st_n, st_d), KpiKind.percentage, 1),
        Component("client", "Client", "العميل", _pct(len(num) - st_n, len(den) - st_d),
                  KpiKind.percentage, 1),
    ]  # fmt: skip
    return res


def _k128(e: Engine, a: Agg) -> Result:
    od = overdue_at(e, a.window)
    res = e._count(M.K128, len(od))
    res.components = [
        Component("statutory", "Statutory", "نظامية", D(sum(r.statutory for r in od)),
                  KpiKind.count_)
    ]  # fmt: skip
    return res


# ---- lessons (K-129), acknowledgements (K-130), effectiveness (K-131) ----------------------------


@dataclass
class Les:
    lesson_no: str
    project_id: UUID | None
    due: date
    published_on: date | None
    eng: UUID | None


def lessons(db: Session, pids: list[UUID]) -> list[Les]:
    from app.models import FuLesson, Incident  # noqa: PLC0415
    from app.services.followup import common as fc  # noqa: PLC0415

    out = []
    for ls in db.scalars(
        select(FuLesson).where(
            FuLesson.source_project_id.in_(pids),
            FuLesson.required.is_(True),
            FuLesson.publish_due_on.is_not(None),
        )
    ):
        inc = db.get(Incident, ls.incident_id) if ls.incident_id else None
        assert ls.publish_due_on is not None  # noqa: S101
        out.append(
            Les(ls.lesson_no, ls.source_project_id, ls.publish_due_on,
                fc.local_day(ls.published_at) if ls.published_at else None,
                inc.responsible_engagement_id if inc else None)
        )  # fmt: skip
    return out


def lesson_timeliness(e: Engine, w: Window) -> tuple[list[Les], list[Les]]:
    f = ffacts(e)
    if f is None:
        return [], []
    end = _end(e, w)
    rows: list[Les] = _memo(f, "lessons", lambda: lessons(f.db, f.pids))
    den = [
        x
        for x in rows
        if w.start <= x.due <= w.end
        and (x.due <= end or (x.published_on is not None and x.published_on <= end))
        and e.flt.eng_ok(x.eng)
    ]
    num = [x for x in den if x.published_on is not None and x.published_on <= x.due]
    return num, den


def _k129(e: Engine, a: Agg) -> Result:
    num, den = lesson_timeliness(e, a.window)
    return e._pct(M.K129, len(num), len(den))


def ack_items(e: Engine, w: Window) -> tuple[list[Any], list[Any]]:
    from app.core.followup_enums import FuDistributionStatus as DS  # noqa: PLC0415, N814
    from app.models import FuDistribution  # noqa: PLC0415
    from app.services.followup import common as fc  # noqa: PLC0415

    f = ffacts(e)
    if f is None:
        return [], []
    end = _end(e, w)
    rows: list[Any] = _memo(f, "acks", lambda: list(f.db.scalars(
        select(FuDistribution).where(FuDistribution.project_id.in_(f.pids)))))  # fmt: skip
    den = [
        x
        for x in rows
        if x.status != DS.withdrawn
        and w.start <= x.ack_due_on <= w.end
        and x.ack_due_on <= end
        and e.flt.eng_ok(x.engagement_id)
    ]
    num = [
        x
        for x in den
        if x.status in (DS.acknowledged, DS.not_applicable)
        and x.acknowledged_at is not None
        and fc.local_day(x.acknowledged_at) <= x.ack_due_on
    ]
    return num, den


def _k130(e: Engine, a: Agg) -> Result:
    num, den = ack_items(e, a.window)
    return e._pct(M.K130, len(num), len(den))


def checks(e: Engine, w: Window) -> list[Any]:
    from app.core.followup_enums import FuCheckStatus  # noqa: PLC0415
    from app.models import FuEffectivenessCheck, FuLesson, Incident  # noqa: PLC0415

    f = ffacts(e)
    if f is None:
        return []
    end = _end(e, w)
    db = f.db

    def load() -> list[tuple[Any, UUID | None]]:
        out = []
        for ch in db.scalars(
            select(FuEffectivenessCheck).where(
                FuEffectivenessCheck.project_id.in_(f.pids),
                FuEffectivenessCheck.status == FuCheckStatus.completed,
            )
        ):
            ls = db.get(FuLesson, ch.lesson_id)
            inc = db.get(Incident, ls.incident_id) if ls and ls.incident_id else None
            out.append((ch, inc.responsible_engagement_id if inc else None))
        return out

    rows: list[tuple[Any, UUID | None]] = _memo(f, "checks", load)
    return [
        ch
        for ch, eng in rows
        if ch.completed_on is not None and w.start <= ch.completed_on <= end and e.flt.eng_ok(eng)
    ]


def _k131(e: Engine, a: Agg) -> Result:
    from app.core.followup_enums import FuEffectResult  # noqa: PLC0415

    cs = checks(e, a.window)
    res = e._pct(M.K131, sum(c.result == FuEffectResult.effective for c in cs), len(cs))
    rec = sum(len((c.facts or {}).get("recurrences", [])) for c in cs)
    res.components = [Component("recurrences", "Recurrences", "التكرارات", D(rec), KpiKind.count_)]
    return res


engine_mod._DISPATCH.update(
    {M.K127: _k127, M.K128: _k128, M.K129: _k129, M.K130: _k130, M.K131: _k131}
)


# ---- E24 (6f §6.3) -------------------------------------------------------------------------------


def fu_warnings(
    engine: Engine,
    project_id: UUID,
    tree: Any,
    m: Window,
    label_en: str,
    label_ar: str,
    who_en: str,
    who_ar: str,
) -> list[Any]:
    """E24 incident follow-up; unrounded comparisons. T13 inputs: numerators, denominators,
    thresholds, requirement bodies and lesson numbers; never names."""
    from app.core.followup_enums import FuEffectResult  # noqa: PLC0415
    from app.kpi.warnings import HUNDRED, Input, Warn  # noqa: PLC0415
    from app.kpi.warnings import E as Codes  # noqa: PLC0415
    from app.services.followup import common as fc  # noqa: PLC0415

    f = ffacts(engine)
    if f is None or project_id not in f.pids:
        return []
    c = fc.cfg(f.db, project_id)
    cut = cutoff(m.end)
    mine = [r for r in reqs(engine) if r.project_id == project_id]
    stat_over = [
        r
        for r in mine
        if r.statutory
        and r.counted
        and r.due_at < cut
        and (r.first_sub is None or r.first_sub > cut)
    ]
    stat_late = [
        r
        for r in mine
        if r.statutory
        and r.counted
        and r.first_sub is not None
        and r.first_sub > r.due_at
        and m.start <= fc.local_day(r.first_sub) <= m.end
    ]
    num, den = timeliness(engine, m)
    num = [r for r in num if r.project_id == project_id]
    den = [r for r in den if r.project_id == project_id]
    an, ad = ack_items(engine, m)
    an = [x for x in an if x.project_id == project_id]
    ad = [x for x in ad if x.project_id == project_id]
    k127 = D(len(num)) / D(len(den)) * HUNDRED if den else None
    k130 = D(len(an)) / D(len(ad)) * HUNDRED if ad else None
    t127, t130 = c.dec("followup_warning_pct"), c.dec("lesson_ack_warning_pct")
    rows: list[Les] = _memo(f, "lessons", lambda: lessons(f.db, f.pids))
    late_lessons = sorted(
        x.lesson_no
        for x in rows
        if x.project_id == project_id
        and x.due < m.end
        and (x.published_on is None or x.published_on > m.end)
        and engine.flt.eng_ok(x.eng)
    )
    bad = [
        ch for ch in checks(engine, m) if ch.project_id == project_id
        and ch.result == FuEffectResult.not_effective
    ]  # fmt: skip
    if not (
        stat_over
        or stat_late
        or (len(den) >= 5 and k127 is not None and k127 < t127)
        or (len(ad) >= 5 and k130 is not None and k130 < t130)
        or late_lessons
        or bad
    ):
        return []
    bodies = sorted({r.body for r in stat_over + stat_late})
    recs = [f"{r.incident_ref} {r.rule_code}" for r in stat_over + stat_late] + late_lessons
    return [
        Warn(
            Codes.E24, m, project_id, tree,
            f"Incident follow-up warning in {label_en}{who_en}"
            + (f": {', '.join(recs)}" if recs else "")
            + (f" (bodies: {', '.join(bodies)})" if bodies else ""),
            f"إنذار متابعة الحوادث في {label_ar}{who_ar}",
            [Input("statutory_overdue", "Statutory overdue at month end",
                   "إخطارات نظامية متأخرة", D(len(stat_over)), 0),
             Input("statutory_late", "Statutory submitted late", "إخطارات نظامية متأخرة الإرسال",
                   D(len(stat_late)), 0),
             Input("k127", "Notifications on time", "الإخطارات في الموعد", k127, 1, " %"),
             Input("k127_numerator", "On time", "في الموعد", D(len(num)), 0),
             Input("k127_denominator", "Due", "المستحقة", D(len(den)), 0),
             Input("k127_threshold_pct", "Threshold", "الحد", t127, 1, " %"),
             Input("k130", "Lesson acknowledgement on time", "الإقرار بالدروس", k130, 1, " %"),
             Input("k130_numerator", "On time", "في الموعد", D(len(an)), 0),
             Input("k130_denominator", "Due", "المستحقة", D(len(ad)), 0),
             Input("k130_threshold_pct", "Threshold", "الحد", t130, 1, " %"),
             Input("lessons_past_due", "Required lessons past publication date",
                   "دروس متأخرة النشر", D(len(late_lessons)), 0),
             Input("checks_not_effective", "Checks not effective", "دروس غير فعالة",
                   D(len(bad)), 0)],
        )
    ]  # fmt: skip
