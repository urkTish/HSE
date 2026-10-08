"""Certification KPI page (GET /kpi/certification), dashboard certification band and tiles,
charts C16-C18 (4-third-party-cert §6.7, §8.1, KC-1…KC-5). Engine values only; aggregates only
(equipment tags and TPI codes may appear as group keys; never names, worker_no, cert numbers,
ID data, ban reasons or verification-failure details, KC-4)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import HookKind
from app.core.cert_enums import (
    CertificateStatus,
    CertKpiGroupBy,
    DefectCategory,
    HookStage,
    ServiceStatus,
    VerificationStatus,
)
from app.core.enums import Capability
from app.core.hse_enums import AxisKind, ChartId, ChartKind, KpiMetric, SeriesKind
from app.kpi import cert as kc
from app.kpi import charts as ch
from app.kpi import fmt, present, service
from app.kpi.catalogue import CATALOGUE
from app.kpi.cert_facts import EqDepFact, SubFact
from app.kpi.engine import Agg, Engine
from app.kpi.facts import Filter
from app.kpi.periods import Window, fmt_month, month_key, months_ending
from app.kpi.scope import Scope
from app.models import EquipmentCertificate, PersonnelCertificate, Project
from app.schemas.cert_kpi import CertBreakdown, CertBreakdownRow, CertKpiResponse
from app.schemas.kpi import (
    CertBand,
    CertBandHookStage,
    ChartAxis,
    ChartCategory,
    ChartReferenceLine,
    ChartSpec,
    ChartXAxis,
)

M = KpiMetric
G = CertKpiGroupBy
CERT_METRICS = [M.K72, M.K73, M.K74, M.K75, M.K76, M.K77, M.K78, M.K79, M.K80, M.K81]
EQUIPMENT_METRICS = [M.K72, M.K73, M.K74, M.K75]
PERSONNEL_METRICS = [M.K76, M.K77]


def has_cert(scope: Scope) -> bool:
    return any(scope.p.grant(x.id, Capability.cert_kpi_view) is not None for x in scope.projects)


def cert_engine(scope: Scope, e: Engine | None = None) -> Engine:
    e = e or scope.engine
    q = scope.query
    cats = frozenset(c.value for c in getattr(q, "equipment_categories", []) or [])
    types = frozenset(getattr(q, "cert_types", []) or [])
    e.equipment_categories = cats or None  # type: ignore[attr-defined]
    e.cert_types = types or None  # type: ignore[attr-defined]
    return e


def _sub(scope: Scope, flt: Filter, **attrs: frozenset[str] | None) -> Engine:
    e = cert_engine(scope, scope.sub_engine(flt))
    for k, v in attrs.items():
        setattr(e, k, v)
    return e


def _row(metric: KpiMetric, key: str, en: str, ar: str, e: Engine, w: Window) -> CertBreakdownRow:
    r = e.result(metric, e.aggregate(w))
    defn = CATALOGUE[metric]
    return CertBreakdownRow(
        key=key,
        label_en=en,
        label_ar=ar,
        value=present.value_str(defn, r.value),
        display=present.display(defn, r.value),
        numerator=fmt.exact(r.numerator),
        denominator=fmt.exact(r.denominator),
    )


def _count_row(key: str, en: str, ar: str, n: int) -> CertBreakdownRow:
    return CertBreakdownRow(
        key=key, label_en=en, label_ar=ar, value=str(n), display=fmt.number(Decimal(n))
    )


def _pct_row(key: str, en: str, ar: str, num: int, den: int) -> CertBreakdownRow:
    v = Decimal(num) / Decimal(den) * 100 if den else None
    return CertBreakdownRow(
        key=key,
        label_en=en,
        label_ar=ar,
        value=fmt.dec_str(v, 1) if v is not None else None,
        display=fmt.percent(v, 1) if v is not None else fmt.DASH,
        numerator=str(num),
        denominator=str(den),
    )


def k79_counts(e: Engine, a: Agg, keep: Callable[[SubFact], bool]) -> tuple[int, int]:
    d = kc.day(e, a)
    num = den = 0
    for s in kc.subs(e, a):
        if not keep(s):
            continue
        done = s.conclusive is not None and s.conclusive <= d
        if not done and s.due >= d:
            continue
        den += 1
        if done and s.conclusive is not None and s.conclusive <= s.due:
            num += 1
    return num, den


def not_valid_reason(e: Engine, x: EqDepFact, d: date) -> str:
    cf = kc.facts(e)
    lines = cf.lines.get(x.item, [])
    if any(
        ln.config_suspended is not None and ln.config_suspended <= d
        for ln in lines
        if ln.superseded is None or ln.superseded > d
    ):
        return "CONFIGURATION_CHANGED"
    it = cf.items.get(x.item)
    if it is not None and it.status_on(d) == ServiceStatus.out_of_service:
        return "OUT_OF_SERVICE"
    latest = cf.latest_line(x.item, d)
    if latest is None:
        return "CERT_MISSING"
    if latest.ended is not None and latest.ended <= d:
        return "CERT_REVOKED"
    if latest.tpi_blocked is not None and latest.tpi_blocked <= d:
        return "TPI_BLACKLISTED"
    if latest.valid_until is not None and latest.valid_until < d:
        return "CERT_EXPIRED"
    if latest.verified is None or latest.verified > d:
        return "CERT_UNVERIFIED"
    return "CERT_MISSING"


def _breakdowns(
    scope: Scope, e: Engine, metrics: list[KpiMetric], group_by: list[CertKpiGroupBy]
) -> list[CertBreakdown]:
    w = scope.window
    a = e.aggregate(w)
    cf = kc.facts(e)
    out: list[CertBreakdown] = []
    for g in dict.fromkeys(group_by):
        if g == G.category:
            cats = sorted(
                {x.category for x in cf.eq_deps if x.category != kc.SCAFFOLD}
                | ({kc.SCAFFOLD} if cf.scaffolds else set())
            )
            for m in [x for x in metrics if x in (*EQUIPMENT_METRICS, M.K80)]:
                rows = [
                    _row(
                        m,
                        c,
                        *kc.label(c),
                        _sub(scope, scope.flt, equipment_categories=frozenset({c})),
                        w,
                    )
                    for c in cats
                ]
                out.append(CertBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.cert_type:
            types = sorted(
                {c for _w, c in kc.mobilised(e, a)}
                | {pc.cert_type for v in cf.pcs.values() for pc in v}
            )
            for m in [x for x in metrics if x in PERSONNEL_METRICS]:
                rows = [
                    _row(m, t, t, t, _sub(scope, scope.flt, cert_types=frozenset({t})), w)
                    for t in types
                ]
                out.append(CertBreakdown(metric=m.value, group_by=g, rows=rows))
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
                out.append(CertBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.month:
            for m in metrics:
                rows = []
                for mw in months_ending(w.end, 12):
                    if mw.end < w.start:
                        continue
                    en, ar = fmt_month(mw.start)
                    rows.append(_row(m, month_key(mw.start), en, ar, e, mw))
                out.append(CertBreakdown(metric=m.value, group_by=g, rows=rows))
        elif g == G.tpi:
            codes = sorted({s.tpi for s in kc.subs(e, a) if s.tpi})
            rows = []
            for code in codes:
                num, den = k79_counts(e, a, lambda s, c=code: s.tpi == c)  # type: ignore[misc]
                rows.append(_pct_row(code, code, code, num, den))
            out.append(CertBreakdown(metric=M.K79.value, group_by=g, rows=rows))
        elif g == G.defect_category:
            by = Counter(
                x.category.value
                for x in cf.defects
                if kc._in(e, a, x.raised) and kc.defect_ok(e, x) and x.status.value != "cancelled"
            )
            rows = [
                _count_row(c.value, f"Category {c.value}", f"الفئة {c.value}", by.get(c.value, 0))
                for c in DefectCategory
            ]
            out.append(CertBreakdown(metric=M.K74.value, group_by=g, rows=rows))
        elif g == G.reason_code:
            d = kc.day(e, a)
            reasons = Counter(
                not_valid_reason(e, x, d) for x in kc.on_site(e, a) if not cf.item_valid(x.item, d)
            )
            rows = [
                _count_row(k, k, k, v)
                for k, v in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))
            ]
            out.append(CertBreakdown(metric=M.K72.value, group_by=g, rows=rows))
    return out


def cert_kpis(
    db: Session,
    scope: Scope,
    metrics: list[KpiMetric] | None,
    group_by: list[CertKpiGroupBy] | None,
) -> CertKpiResponse:
    wanted = [m for m in (metrics or CERT_METRICS) if m in CERT_METRICS] or CERT_METRICS
    e = cert_engine(scope)
    return CertKpiResponse(
        context=service.context(scope),
        band=cert_band(db, scope),
        metrics=[service.kpi_value(scope, m, engine=e) for m in wanted],
        breakdowns=_breakdowns(scope, e, wanted, group_by or []),
    )


# ---- dashboard band (§8.1 item 2) ----


def _project(scope: Scope) -> Project | None:
    p = scope.single_project
    if p is None or scope.p.grant(p.id, Capability.cert_kpi_view) is None:
        return None
    return p


def hook_stages(scope: Scope, project: Project, d: date) -> list[CertBandHookStage]:
    cf = kc.facts(scope.engine)
    out = []
    for st in sorted(cf.hook_states.get(project.id, []), key=lambda s: s.kind.value):
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
        out.append(
            CertBandHookStage(
                kind=HookKind(st.kind), stage=st.stage, next_block_date=nxt, next_block_scope=scope_
            )
        )
    return out


def cert_band(db: Session, scope: Scope) -> CertBand | None:
    proj = _project(scope)
    if proj is None:
        return None
    e = cert_engine(scope)
    cf = kc.facts(e)
    if proj.id not in cf.enabled:
        return None
    a = e.aggregate(scope.window)
    d = kc.day(e, a)
    rows = [x for x in kc.on_site(e, a) if x.project == proj.id]
    st = Counter(cf.items[x.item].status_on(d) for x in rows if x.item in cf.items)

    def count(model: Any, *conds: Any) -> int:
        stmt = select(func.count()).select_from(model).where(model.project_id == proj.id, *conds)
        return int(db.scalar(stmt) or 0)

    awaiting_review = count(
        EquipmentCertificate, EquipmentCertificate.status == CertificateStatus.submitted
    ) + count(PersonnelCertificate, PersonnelCertificate.status == CertificateStatus.submitted)
    pending = (VerificationStatus.not_verified,)
    awaiting_ver = count(
        EquipmentCertificate,
        EquipmentCertificate.status.in_([CertificateStatus.submitted, CertificateStatus.accepted]),
        EquipmentCertificate.verification_status.in_(pending),
    ) + count(
        PersonnelCertificate,
        PersonnelCertificate.status.in_([CertificateStatus.submitted, CertificateStatus.accepted]),
        PersonnelCertificate.verification_status.in_(pending),
    )
    overdue = count(
        EquipmentCertificate,
        EquipmentCertificate.status.in_([CertificateStatus.submitted, CertificateStatus.accepted]),
        EquipmentCertificate.verification_status.in_(pending),
        EquipmentCertificate.verification_due_on < d,
    ) + count(
        PersonnelCertificate,
        PersonnelCertificate.status.in_([CertificateStatus.submitted, CertificateStatus.accepted]),
        PersonnelCertificate.verification_status.in_(pending),
        PersonnelCertificate.verification_due_on < d,
    )
    kv = service.kpi_value
    return CertBand(
        project_id=proj.id,
        as_of=d,
        on_site_in_service=st.get(ServiceStatus.in_service, 0),
        on_site_quarantined=st.get(ServiceStatus.quarantined, 0),
        on_site_out_of_service=st.get(ServiceStatus.out_of_service, 0),
        awaiting_review=awaiting_review,
        awaiting_verification=awaiting_ver,
        verification_overdue=overdue,
        equipment_expiring_30d=kv(scope, M.K73, engine=e, with_comparisons=False),
        personnel_expiring_30d=kv(scope, M.K77, engine=e, with_comparisons=False),
        inspections_overdue=kv(scope, M.K75, engine=e, with_comparisons=False),
        blacklisted_banned=kv(scope, M.K78, engine=e, with_comparisons=False),
        hook_stages=hook_stages(scope, proj, d),
    )


# ---- charts C16-C18 ----


def _axis(id_: str, en: str, ar: str, unit: str | None = None) -> ChartAxis:
    return ChartAxis(id=id_, label_en=en, label_ar=ar, unit_en=unit, unit_ar=unit)


def _thresholds(scope: Scope, e: Engine) -> tuple[Decimal, Decimal]:
    cf = kc.facts(e)
    proj = scope.single_project or (scope.projects[0] if scope.projects else None)
    s = cf.settings.get(proj.id) if proj is not None else None
    if s is None:
        return Decimal("98.0"), Decimal("95.0")
    return Decimal(s.equipment_cert_warning_pct), Decimal(s.personnel_cert_warning_pct)


def _ref(value: Decimal, en: str, ar: str) -> ChartReferenceLine:
    return ChartReferenceLine(
        y_axis="left",
        value=fmt.dec_str(value, 1) or "",
        display=fmt.percent(value, 1),
        label_en=en,
        label_ar=ar,
        color_role="target",
    )


def c16(scope: Scope, e: Engine) -> ChartSpec:
    wins = months_ending(scope.window.end, 12)
    keys = [month_key(w.start) for w in wins]
    k72 = [e.result(M.K72, e.aggregate(w)).value for w in wins]
    k76 = [e.result(M.K76, e.aggregate(w)).value for w in wins]
    eq_t, pc_t = _thresholds(scope, e)
    return ch._spec(
        scope,
        ChartId.C16,
        ChartKind.line,
        ("Certification compliance by month", "الامتثال للشهادات حسب الشهر"),
        x_axis=ch._month_axis(wins),
        y_axes=[_axis("left", "Compliance", "الامتثال", "%")],
        series=[
            ch._series(
                "k72",
                "Equipment (K-72)",
                "المعدات",
                SeriesKind.line,
                "left",
                "series-1",
                [ch._pt(k, v, 1, "percent") for k, v in zip(keys, k72, strict=True)],
            ),
            ch._series(
                "k76",
                "Personnel (K-76)",
                "الأفراد",
                SeriesKind.line,
                "left",
                "series-2",
                [ch._pt(k, v, 1, "percent") for k, v in zip(keys, k76, strict=True)],
            ),
        ],
        refs=[
            _ref(eq_t, "Equipment warning (E10)", "حد تحذير المعدات"),
            _ref(pc_t, "Personnel warning (E10)", "حد تحذير الأفراد"),
        ],
        metric=M.K72,
    )


def c17(scope: Scope, e: Engine) -> ChartSpec:
    wins = months_ending(scope.window.end, 12)
    keys = [month_key(w.start) for w in wins]
    cf = kc.facts(e)
    per: list[Counter[str]] = []
    k80 = []
    for w in wins:
        a = e.aggregate(w)
        per.append(
            Counter(
                x.category.value
                for x in cf.defects
                if kc._in(e, a, x.raised) and kc.defect_ok(e, x) and x.status.value != "cancelled"
            )
        )
        k80.append(e.result(M.K80, a).value)
    colors = {"A": "unsafe", "B": "series-3", "C": "series-4"}
    series = [
        ch._series(
            c.value,
            f"Category {c.value}",
            f"الفئة {c.value}",
            SeriesKind.bar,
            "left",
            colors[c.value],
            [ch._pt(k, p.get(c.value, 0), 0) for k, p in zip(keys, per, strict=True)],
            stack="defects",
        )
        for c in DefectCategory
    ]
    series.append(
        ch._series(
            "k80",
            "Rectified on time (K-80)",
            "الإصلاح في الموعد",
            SeriesKind.line,
            "right",
            "leading",
            [ch._pt(k, v, 1, "percent") for k, v in zip(keys, k80, strict=True)],
        )
    )
    return ch._spec(
        scope,
        ChartId.C17,
        ChartKind.combo,
        ("Defects raised by month", "العيوب المسجلة حسب الشهر"),
        x_axis=ch._month_axis(wins),
        y_axes=[
            _axis("left", "Defects", "العيوب"),
            _axis("right", "Rectified on time", "الإصلاح في الموعد", "%"),
        ],
        series=series,
        metric=M.K80,
    )


def expiry_profile(scope: Scope, e: Engine) -> list[tuple[date, date, int, int]]:
    """C18: 13 weekly buckets from as_of covering the next 90 days → (start, end, eq, pc)."""
    cf = kc.facts(e)
    a = e.aggregate(scope.window)
    d = kc.day(e, a)
    eq_dates = [cf.item_valid_until(x.item, d) for x in kc.on_site(e, a)]
    pc_dates: list[date] = []
    seen: set[tuple[object, object]] = set()
    types = kc._types(e)
    for w in cf.worker_deps:
        if not w.mobilised(d) or not kc.worker_ok(e, w) or (w.project, w.worker) in seen:
            continue
        seen.add((w.project, w.worker))
        for pc in cf.pcs.get(w.worker, []):
            if types is not None and pc.cert_type not in types:
                continue
            if pc.in_force(d, cf.banned(w.worker, d, pc.cert_type)) and pc.valid_until:
                pc_dates.append(pc.valid_until)
    end = d + timedelta(days=90)
    out = []
    start = d
    while start <= end:
        stop = min(start + timedelta(days=6), end)
        out.append(
            (
                start,
                stop,
                sum(1 for v in eq_dates if v is not None and start <= v <= stop),
                sum(1 for v in pc_dates if start <= v <= stop),
            )
        )
        start = stop + timedelta(days=1)
    return out


def c18(scope: Scope, e: Engine) -> ChartSpec:
    rows = expiry_profile(scope, e)
    cats = [
        ChartCategory(key=s.isoformat(), label_en=f"Week of {s:%d %b}", label_ar=f"أسبوع {s:%d/%m}")
        for s, _e, _q, _p in rows
    ]
    return ch._spec(
        scope,
        ChartId.C18,
        ChartKind.stacked_bar,
        ("Certificate expiry profile (next 90 days)", "انتهاء الشهادات خلال 90 يوماً"),
        x_axis=ChartXAxis(
            kind=AxisKind.period, label_en="Week", label_ar="الأسبوع", categories=cats
        ),
        y_axes=[_axis("left", "Certificates", "الشهادات")],
        series=[
            ch._series(
                "equipment",
                "Equipment",
                "المعدات",
                SeriesKind.bar,
                "left",
                "series-1",
                [ch._pt(s.isoformat(), q, 0) for s, _e, q, _p in rows],
                stack="expiry",
            ),
            ch._series(
                "personnel",
                "Personnel",
                "الأفراد",
                SeriesKind.bar,
                "left",
                "series-2",
                [ch._pt(s.isoformat(), p, 0) for s, _e, _q, p in rows],
                stack="expiry",
            ),
        ],
        metric=M.K73,
    )


CERT_CHARTS = {ChartId.C16: c16, ChartId.C17: c17, ChartId.C18: c18}


def chart(scope: Scope, chart_id: ChartId) -> ChartSpec:
    return CERT_CHARTS[chart_id](scope, cert_engine(scope))
