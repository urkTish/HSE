"""Training KPI page (GET /kpi/training), dashboard training tiles and band, charts C19-C21
(5-training §6.8, §8.1, TK-1…TK-5). Engine values only; aggregates only (course codes,
categories, contractor short codes, trades, provider codes and months as keys; never names,
worker_no, certificate numbers, scores, ID data or verification-failure details, TK-4)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.cert_enums import HookStage, VerificationStatus
from app.core.enums import Capability
from app.core.hse_enums import AxisKind, ChartId, ChartKind, KpiMetric, SeriesKind
from app.core.train_enums import (
    CourseCategory,
    SessionStatus,
    TrainingKpiGroupBy,
    TrainingRecordSource,
    TrainingRecordStatus,
)
from app.kpi import charts as ch
from app.kpi import fmt, present, service
from app.kpi import training as kt
from app.kpi.catalogue import CATALOGUE
from app.kpi.engine import Engine
from app.kpi.facts import Filter
from app.kpi.periods import Window, fmt_month, month_key, months_ending
from app.kpi.scope import Scope
from app.models import Project, TrainingRecord, TrainingSession
from app.schemas.kpi import (
    ChartAxis,
    ChartCategory,
    ChartReferenceLine,
    ChartSpec,
    ChartXAxis,
    TrainingBand,
    TrainingBandHookStage,
)
from app.schemas.training_kpi import TrainingBreakdown, TrainingBreakdownRow, TrainingKpiResponse
from app.services.train import reference as tref

M = KpiMetric
G = TrainingKpiGroupBy
TRAINING_METRICS = [M.K37, M.K82, M.K83, M.K84, M.K85, M.K86, M.K87, M.K88]
REQ_METRICS = [M.K82, M.K83, M.K84, M.K85, M.K88]
DEFAULT_THRESHOLD = Decimal("98.0")


def has_training(scope: Scope) -> bool:
    return any(
        scope.p.grant(x.id, Capability.training_kpi_view) is not None for x in scope.projects
    )


def _vals(xs: Any) -> frozenset[str] | None:
    out = frozenset(getattr(x, "value", x) for x in xs or [])
    return out or None


def train_engine(scope: Scope, e: Engine | None = None) -> Engine:
    e = e or scope.engine
    q = scope.query
    e.trades = _vals(getattr(q, "trades", []))  # type: ignore[attr-defined]
    e.course_codes = _vals(getattr(q, "course_codes", []))  # type: ignore[attr-defined]
    e.course_categories = _vals(getattr(q, "course_categories", []))  # type: ignore[attr-defined]
    return e


def _sub(scope: Scope, flt: Filter, **attrs: frozenset[str] | None) -> Engine:
    e = train_engine(scope, scope.sub_engine(flt))
    for k, v in attrs.items():
        setattr(e, k, v)
    return e


def _row(
    metric: KpiMetric, key: str, en: str, ar: str, e: Engine, w: Window
) -> TrainingBreakdownRow:
    r = e.result(metric, e.aggregate(w))
    defn = CATALOGUE[metric]
    return TrainingBreakdownRow(
        key=key,
        label_en=en,
        label_ar=ar,
        value=present.value_str(defn, r.value),
        display=present.display(defn, r.value),
        numerator=fmt.exact(r.numerator),
        denominator=fmt.exact(r.denominator),
    )


def _hours_row(key: str, en: str, ar: str, h: Decimal) -> TrainingBreakdownRow:
    return TrainingBreakdownRow(
        key=key,
        label_en=en,
        label_ar=ar,
        value=fmt.dec_str(h, 2),
        display=fmt.number(h, 2),
        numerator=fmt.exact(h),
    )


def _course_label(e: Engine, code: str) -> tuple[str, str]:
    tf = kt.tfacts(e)
    c = tf.courses.get(code) if tf is not None else None
    return (c.name_en, c.name_ar) if c is not None else (code, code)


def _cat_label(cat: str) -> tuple[str, str]:
    try:
        return tref.CATEGORY_LABELS[CourseCategory(cat)]
    except (KeyError, ValueError):
        return cat, cat


def _breakdowns(
    scope: Scope, e: Engine, metrics: list[KpiMetric], group_by: list[TrainingKpiGroupBy]
) -> list[TrainingBreakdown]:
    w = scope.window
    a = e.aggregate(w)
    out: list[TrainingBreakdown] = []
    tf = kt.tfacts(e)
    hour_rows = kt.hour_rows(e, a)
    for g in dict.fromkeys(group_by):
        if g == G.course:
            r = kt.req_kpis(e, a)
            codes = sorted(set(r.by_course) | {h.course for h in hour_rows})
            for m in metrics:
                if m == M.K37:
                    continue
                rows = [
                    _row(
                        m,
                        c,
                        *_course_label(e, c),
                        _sub(scope, scope.flt, course_codes=frozenset({c})),
                        w,
                    )
                    for c in codes
                ]
                out.append(TrainingBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.course_category:
            cats = sorted(
                {h.category for h in hour_rows}
                | (
                    {
                        tf.courses[c].category.value
                        for c in kt.req_kpis(e, a).by_course
                        if c in tf.courses
                    }
                    if tf is not None
                    else set()
                )
            )
            for m in metrics:
                if m == M.K37:
                    continue
                rows = [
                    _row(
                        m,
                        c,
                        *_cat_label(c),
                        _sub(scope, scope.flt, course_categories=frozenset({c})),
                        w,
                    )
                    for c in cats
                ]
                out.append(TrainingBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.trade:
            r = kt.req_kpis(e, a)
            trades = sorted(r.by_trade)
            for m in [x for x in metrics if x in REQ_METRICS]:
                rows = [
                    _row(m, t, t, t, _sub(scope, scope.flt, trades=frozenset({t})), w)
                    for t in trades
                ]
                out.append(TrainingBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.contractor:
            tops = sorted(
                (
                    x
                    for x in scope.facts.engagements.values()
                    if x.tier == 1 and (scope.flt.engs is None or x.id in scope.flt.engs)
                ),
                key=lambda x: x.code,
            )
            for m in metrics:
                rows = [
                    _row(
                        m,
                        top.code,
                        top.name_en,
                        top.name_ar,
                        _sub(
                            scope,
                            scope.narrowed_filter(engs=frozenset(scope.facts.descendants(top.id))),
                        ),
                        w,
                    )
                    for top in tops
                ]
                out.append(TrainingBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.month:
            for m in metrics:
                rows = []
                for mw in months_ending(w.end, 12):
                    if mw.end < w.start:
                        continue
                    en, ar = fmt_month(mw.start)
                    rows.append(_row(m, month_key(mw.start), en, ar, e, mw))
                out.append(TrainingBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g in (G.provider, G.source):
            codes_of = _provider_codes(scope, tf)
            by: dict[str, Decimal] = defaultdict(Decimal)
            for h in hour_rows:
                if h.staff:
                    continue
                key = codes_of.get(h.provider, "") if g == G.provider else h.source
                by[key] += h.hours
            rows = [_hours_row(k, k, k, v) for k, v in sorted(by.items())]
            out.append(TrainingBreakdown(metric=M.K86.value, group_by=g, rows=rows))
            if g == G.provider and M.K87 in metrics:
                passed: Counter[str] = Counter()
                total: Counter[str] = Counter()
                for x in kt.assess_rows(e, a):
                    k = codes_of.get(x.provider, "")
                    total[k] += 1
                    passed[k] += int(x.passed)
                prow = []
                for k in sorted(total):
                    v = Decimal(passed[k]) / Decimal(total[k]) * 100
                    prow.append(
                        TrainingBreakdownRow(
                            key=k,
                            label_en=k,
                            label_ar=k,
                            value=fmt.dec_str(v, 1),
                            display=fmt.percent(v, 1),
                            numerator=str(passed[k]),
                            denominator=str(total[k]),
                        )
                    )
                out.append(TrainingBreakdown(metric=M.K87.value, group_by=g, rows=prow))
    return out


def _provider_codes(scope: Scope, tf: Any) -> dict[Any, str]:
    from app.services.train import hook as thook  # noqa: PLC0415

    db = tf.db if tf is not None else None
    if db is None:
        return {}
    return {pid: pv.provider_code for pid, pv in thook.providers(db).items()}


def training_kpis(
    db: Session,
    scope: Scope,
    metrics: list[KpiMetric] | None,
    group_by: list[TrainingKpiGroupBy] | None,
) -> TrainingKpiResponse:
    wanted = [m for m in (metrics or TRAINING_METRICS) if m in TRAINING_METRICS]
    wanted = wanted or TRAINING_METRICS
    e = train_engine(scope)
    return TrainingKpiResponse(
        context=service.context(scope),
        band=training_band(db, scope),
        metrics=[service.kpi_value(scope, m, engine=e) for m in wanted],
        breakdowns=_breakdowns(scope, e, wanted, group_by or []),
    )


# ---- dashboard band (§8.1 item 2) ----


def _project(scope: Scope) -> Project | None:
    p = scope.single_project
    if p is None or scope.p.grant(p.id, Capability.training_kpi_view) is None:
        return None
    return p


def hook_stage(e: Engine, project: Project, d: date) -> TrainingBandHookStage | None:
    tf = kt.tfacts(e)
    st = tf.hook_states.get(project.id) if tf is not None else None
    if st is None:
        return None
    nxt: date | None
    scope_: str | None
    if st.stage == HookStage.block or st.all_switched_at is not None:
        nxt, scope_ = None, None
    elif d < st.critical_block_from:
        nxt, scope_ = st.critical_block_from, "critical"
    elif d < st.general_block_from:
        nxt, scope_ = st.general_block_from, "general"
    else:
        nxt, scope_ = None, None
    stage = st.stage
    if d >= st.general_block_from:
        stage = HookStage.block
    return TrainingBandHookStage(stage=stage, next_block_date=nxt, next_block_scope=scope_)


def hook_gaps_on_live_work(db: Session, e: Engine, project: Project, d: date) -> int:
    from app.services.train import gaps  # noqa: PLC0415

    tf = kt.tfacts(e)
    if tf is None:
        return 0
    pe = tf.peval(project.id, d)
    keep = kt._req_keep(e)
    hooked = [
        r
        for r in pe.reqs
        if r.counted
        and r.state.value == "gap"
        and keep(r)
        and any(c in pe.f.hook_codes and c in tref.HOOK_CODES_TODAY for c in r.codes)
    ]
    permits, waps = gaps.live_work(db, project.id, {r.dep.worker_id for r in hooked})
    return sum(1 for r in hooked if permits.get(r.dep.worker_id) or waps.get(r.dep.worker_id))


def training_band(db: Session, scope: Scope) -> TrainingBand | None:
    proj = _project(scope)
    if proj is None:
        return None
    e = train_engine(scope)
    a = e.aggregate(scope.window)
    d = kt.day(e, a)
    tf = kt.tfacts(e)
    st = tf.settings.get(proj.id) if tf is not None else None
    deadline = st.session_close_deadline_days if st is not None else 3

    def n_sessions(*conds: Any) -> int:
        stmt = (
            select(func.count())
            .select_from(TrainingSession)
            .where(TrainingSession.project_id == proj.id, *conds)
        )
        return int(db.scalar(stmt) or 0)

    def n_records(*conds: Any) -> int:
        stmt = (
            select(func.count())
            .select_from(TrainingRecord)
            .where(TrainingRecord.project_id == proj.id, *conds)
        )
        return int(db.scalar(stmt) or 0)

    pending = [VerificationStatus.not_verified, VerificationStatus.unable_to_verify]
    live = [TrainingRecordStatus.submitted, TrainingRecordStatus.accepted]
    ext = TrainingRecord.source != TrainingRecordSource.session
    return TrainingBand(
        project_id=proj.id,
        as_of=d,
        sessions_this_week_scheduled=n_sessions(
            TrainingSession.status == SessionStatus.scheduled,
            TrainingSession.first_day >= d,
            TrainingSession.first_day <= d + timedelta(days=6),
        ),
        sessions_in_progress=n_sessions(TrainingSession.status == SessionStatus.in_progress),
        sessions_awaiting_close=n_sessions(TrainingSession.status == SessionStatus.delivered),
        sessions_close_overdue=n_sessions(
            TrainingSession.status == SessionStatus.delivered,
            TrainingSession.last_day < d - timedelta(days=deadline),
        ),
        records_awaiting_review=n_records(TrainingRecord.status == TrainingRecordStatus.submitted),
        records_awaiting_verification=n_records(
            ext, TrainingRecord.status.in_(live), TrainingRecord.verification_status.in_(pending)
        ),
        verification_overdue=n_records(
            ext,
            TrainingRecord.status.in_(live),
            TrainingRecord.verification_status.in_(pending),
            TrainingRecord.verification_due_on < d,
        ),
        expiring_30d=service.kpi_value(scope, M.K85, engine=e, with_comparisons=False),
        hook_gaps_on_live_work=hook_gaps_on_live_work(db, e, proj, d),
        hook_stage=hook_stage(e, proj, d),
    )


# ---- charts C19-C21 ----


def _axis(id_: str, en: str, ar: str, unit: str | None = None) -> ChartAxis:
    return ChartAxis(id=id_, label_en=en, label_ar=ar, unit_en=unit, unit_ar=unit)


def threshold(scope: Scope, e: Engine) -> Decimal:
    tf = kt.tfacts(e)
    proj = scope.single_project or (scope.projects[0] if scope.projects else None)
    st = tf.settings.get(proj.id) if tf is not None and proj is not None else None
    return Decimal(st.training_matrix_warning_pct) if st is not None else DEFAULT_THRESHOLD


def c19(scope: Scope, e: Engine) -> ChartSpec:
    wins = months_ending(scope.window.end, 12)
    keys = [month_key(w.start) for w in wins]
    k82 = [e.result(M.K82, e.aggregate(w)).value for w in wins]
    k83 = [e.result(M.K83, e.aggregate(w)).value for w in wins]
    t = threshold(scope, e)
    return ch._spec(
        scope,
        ChartId.C19,
        ChartKind.line,
        ("Training compliance by month", "الامتثال للتدريب حسب الشهر"),
        x_axis=ch._month_axis(wins),
        y_axes=[_axis("left", "Compliance", "الامتثال", "%")],
        series=[
            ch._series(
                "k82",
                "Matrix compliance (K-82)",
                "امتثال المصفوفة",
                SeriesKind.line,
                "left",
                "series-1",
                [ch._pt(k, v, 1, "percent") for k, v in zip(keys, k82, strict=True)],
            ),
            ch._series(
                "k83",
                "Workers fully trained (K-83)",
                "مستوفون بالكامل",
                SeriesKind.line,
                "left",
                "series-2",
                [ch._pt(k, v, 1, "percent") for k, v in zip(keys, k83, strict=True)],
            ),
        ],
        refs=[
            ChartReferenceLine(
                y_axis="left",
                value=fmt.dec_str(t, 1) or "",
                display=fmt.percent(t, 1),
                label_en="Warning threshold (E12)",
                label_ar="حد التحذير",
                color_role="target",
            )
        ],
        metric=M.K82,
    )


def c20(scope: Scope, e: Engine) -> ChartSpec:
    wins = months_ending(scope.window.end, 12)
    keys = [month_key(w.start) for w in wins]
    per: list[dict[str, Decimal]] = []
    k37 = []
    for w in wins:
        a = e.aggregate(w)
        by: dict[str, Decimal] = defaultdict(Decimal)
        for h in kt.hour_rows(e, a):
            if not h.staff and not kt._voided_by(h, e.as_of):
                by[h.category] += h.hours
        per.append(by)
        k37.append(e.result(M.K37, a).value)
    cats = sorted({c for p in per for c in p})
    series = [
        ch._series(
            c,
            *_cat_label(c),
            SeriesKind.bar,
            "left",
            f"series-{i % 6 + 1}",
            [ch._pt(k, p.get(c, Decimal(0)), 2) for k, p in zip(keys, per, strict=True)],
            stack="hours",
        )
        for i, c in enumerate(cats)
    ]
    series.append(
        ch._series(
            "k37",
            "Training hours per worker (K-37)",
            "ساعات التدريب لكل عامل",
            SeriesKind.line,
            "right",
            "leading",
            [ch._pt(k, v, 2) for k, v in zip(keys, k37, strict=True)],
        )
    )
    return ch._spec(
        scope,
        ChartId.C20,
        ChartKind.combo,
        ("Training person-hours by month", "ساعات التدريب حسب الشهر"),
        x_axis=ch._month_axis(wins),
        y_axes=[
            _axis("left", "Person-hours", "ساعات التدريب", "h"),
            _axis("right", "Hours per worker", "ساعات لكل عامل", "h"),
        ],
        series=series,
        metric=M.K86,
    )


def expiry_profile(scope: Scope, e: Engine) -> list[tuple[date, date, int, int]]:
    """C21: 13 weekly buckets from as_of over the next 90 days → (start, end, booked, not)."""
    tf = kt.tfacts(e)
    a = e.aggregate(scope.window)
    d = kt.day(e, a)
    end = d + timedelta(days=90)
    recs: dict[Any, tuple[date, bool]] = {}
    if tf is not None:
        keep = kt._req_keep(e)
        for pid in tf.pids:
            for r in tf.peval(pid, d).reqs:
                if not r.counted or r.record is None or r.valid_until is None or not keep(r):
                    continue
                if r.state.value not in ("met", "expiring") or not (d <= r.valid_until <= end):
                    continue
                booked = r.booked is not None and r.booked.last_day <= r.valid_until
                prev = recs.get(r.record.id)
                recs[r.record.id] = (r.valid_until, booked or (prev is not None and prev[1]))
    out = []
    start = d
    while start <= end:
        stop = min(start + timedelta(days=6), end)
        inb = [b for vu, b in recs.values() if start <= vu <= stop]
        out.append((start, stop, sum(1 for b in inb if b), sum(1 for b in inb if not b)))
        start = stop + timedelta(days=1)
    return out


def c21(scope: Scope, e: Engine) -> ChartSpec:
    rows = expiry_profile(scope, e)
    cats = [
        ChartCategory(key=s.isoformat(), label_en=f"Week of {s:%d %b}", label_ar=f"أسبوع {s:%d/%m}")
        for s, _e, _b, _n in rows
    ]
    return ch._spec(
        scope,
        ChartId.C21,
        ChartKind.stacked_bar,
        ("Training expiry profile (next 90 days)", "انتهاء التدريب خلال 90 يوماً"),
        x_axis=ChartXAxis(
            kind=AxisKind.period, label_en="Week", label_ar="الأسبوع", categories=cats
        ),
        y_axes=[_axis("left", "Records", "السجلات")],
        series=[
            ch._series(
                "booked",
                "Booked",
                "محجوز",
                SeriesKind.bar,
                "left",
                "series-1",
                [ch._pt(s.isoformat(), b, 0) for s, _e, b, _n in rows],
                stack="expiry",
            ),
            ch._series(
                "not_booked",
                "Not booked",
                "غير محجوز",
                SeriesKind.bar,
                "left",
                "series-2",
                [ch._pt(s.isoformat(), n, 0) for s, _e, _b, n in rows],
                stack="expiry",
            ),
        ],
        metric=M.K85,
    )


TRAINING_CHARTS = {ChartId.C19: c19, ChartId.C20: c20, ChartId.C21: c21}


def chart(scope: Scope, chart_id: ChartId) -> ChartSpec:
    return TRAINING_CHARTS[chart_id](scope, train_engine(scope))
