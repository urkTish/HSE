"""Leading-indicator warnings E1-E4 (spec 1-dashboard §6.9) and E5-E7 (2-access-permits
§6.9), evaluated per complete month per project and per tier-1 contractor tree.
Means use unrounded values."""

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from app.core.hse_enums import RECORDABLE, KpiMetric, LeadingWarningCode
from app.kpi import fmt
from app.kpi.engine import Engine
from app.kpi.facts import EngFact
from app.kpi.periods import Window, add_months, fmt_month, month_end, month_key, month_start
from app.kpi.scope import Scope

E = LeadingWarningCode
HUNDRED = Decimal(100)
THREE = Decimal(3)


@dataclass
class Input:
    key: str
    label_en: str
    label_ar: str
    value: Decimal | None
    dp: int = 2
    suffix: str = ""

    @property
    def display(self) -> str:
        if self.value is None:
            return fmt.DASH
        return fmt.number(self.value, self.dp) + self.suffix


@dataclass
class Warn:
    code: LeadingWarningCode
    month: Window
    project_id: uuid.UUID
    engagement: EngFact | None
    message_en: str
    message_ar: str
    inputs: list[Input] = field(default_factory=list)

    @property
    def month_key(self) -> str:
        return month_key(self.month.start)


def complete_months(scope: Scope, end_month: Window, count: int) -> list[Window]:
    out = []
    m = month_start(end_month.end)
    for i in range(count - 1, -1, -1):
        s = add_months(m, -i)
        w = Window(s, month_end(s))
        if w.end <= scope.as_of:
            out.append(w)
    return out


def _prior(w: Window, n: int) -> Window:
    s = add_months(w.start, -n)
    return Window(s, month_end(s))


def _mean(vals: list[Decimal | None]) -> Decimal | None:
    if any(v is None for v in vals):
        return None
    return sum((v for v in vals if v is not None), Decimal(0)) / Decimal(len(vals))


def evaluate_engine(
    scope: Scope,
    engine: Engine,
    project_id: uuid.UUID,
    tree: EngFact | None,
    months: list[Window],
) -> list[Warn]:
    s = scope.hse[project_id]
    drop = Decimal(s.leading_warning_drop_pct)
    rise = Decimal(s.leading_warning_rise_pct)
    out: list[Warn] = []
    who_en = f" ({tree.code} tree)" if tree else ""
    who_ar = f" (مجموعة {tree.code})" if tree else ""

    def nm_rate(w: Window) -> Decimal | None:
        return engine.result(KpiMetric.K25, engine.aggregate(w)).value

    def overdue(w: Window) -> Decimal:
        return Decimal(engine.aggregate(w).overdue)

    def k34(w: Window) -> Decimal | None:
        return engine.result(KpiMetric.K34, engine.aggregate(w)).value

    for m in months:
        label_en, label_ar = fmt_month(m.start)
        priors = [_prior(m, n) for n in (3, 2, 1)]
        # E1
        nm, nm_mean = nm_rate(m), _mean([nm_rate(p) for p in priors])
        od, od_mean = overdue(m), _mean([overdue(p) for p in priors])
        if (
            nm is not None
            and nm_mean is not None
            and od_mean is not None
            and nm <= (1 - drop / HUNDRED) * nm_mean
            and od >= (1 + rise / HUNDRED) * od_mean
        ):
            nm_chg = (nm - nm_mean) / nm_mean * HUNDRED if nm_mean else None
            od_chg = (od - od_mean) / od_mean * HUNDRED if od_mean else None
            out.append(
                Warn(
                    E.E1, m, project_id, tree,
                    f"Near-miss reporting fell while overdue actions rose in {label_en}{who_en}",
                    f"انخفض الإبلاغ عن الحوادث الوشيكة وارتفعت الإجراءات المتأخرة في "
                    f"{label_ar}{who_ar}",
                    [
                        Input("nm_rate_month", "NM rate (month)",
                              "معدل الحوادث الوشيكة (الشهر)", nm),
                        Input("nm_rate_prior3_mean", "NM rate, mean of prior 3 months",
                              "متوسط معدل الحوادث الوشيكة للأشهر الثلاثة السابقة", nm_mean),
                        Input("nm_rate_change_pct", "NM rate change", "تغير معدل الحوادث الوشيكة",
                              nm_chg, 1, " %"),
                        Input("overdue_end_month", "Overdue CAs at month end",
                              "الإجراءات المتأخرة في نهاية الشهر", od, 0),
                        Input("overdue_prior3_mean", "Overdue CAs, mean of prior 3 month ends",
                              "متوسط المتأخرات لنهايات الأشهر الثلاثة السابقة", od_mean),
                        Input("overdue_change_pct", "Overdue change", "تغير المتأخرات", od_chg, 1,
                              " %"),
                        Input("drop_threshold_pct", "Drop threshold", "حد الانخفاض", drop, 0, " %"),
                        Input("rise_threshold_pct", "Rise threshold", "حد الارتفاع", rise, 0, " %"),
                    ],
                )
            )  # fmt: skip
        # E2
        c_now, c_prev = k34(m), k34(_prior(m, 1))
        if c_now is not None and c_prev is not None and c_now < 80 and c_prev < 80:
            out.append(
                Warn(
                    E.E2, m, project_id, tree,
                    f"Inspection compliance below 80 % for two consecutive months to "
                    f"{label_en}{who_en}",
                    f"الالتزام بالتفتيش أقل من 80 % لشهرين متتاليين حتى {label_ar}{who_ar}",
                    [Input("k34_month", "Inspection compliance (month)",
                           "الالتزام بالتفتيش (الشهر)", c_now, 1, " %"),
                     Input("k34_previous", "Inspection compliance (previous month)",
                           "الالتزام بالتفتيش (الشهر السابق)", c_prev, 1, " %")],
                )
            )  # fmt: skip
        # E3
        a = engine.aggregate(m)
        if a.obs_total >= 50 and Decimal(a.obs_unsafe) * HUNDRED > 40 * Decimal(a.obs_total):
            share = Decimal(a.obs_unsafe) / Decimal(a.obs_total) * HUNDRED
            out.append(
                Warn(
                    E.E3, m, project_id, tree,
                    f"Unsafe observations above 40 % in {label_en}{who_en}",
                    f"الملاحظات غير الآمنة أعلى من 40 % في {label_ar}{who_ar}",
                    [Input("unsafe_share_pct", "Unsafe share", "نسبة غير الآمنة", share, 1, " %"),
                     Input("observations", "Observations", "الملاحظات", Decimal(a.obs_total), 0)],
                )
            )  # fmt: skip
        # E4
        repeats = repeat_events(scope, engine, m)
        if a.hipo >= 2 or repeats:
            out.append(
                Warn(
                    E.E4, m, project_id, tree,
                    f"HiPo or repeat events in {label_en}{who_en}",
                    f"أحداث عالية الخطورة أو متكررة في {label_ar}{who_ar}",
                    [Input("hipo_events", "HiPo events", "أحداث عالية الخطورة", Decimal(a.hipo), 0),
                     Input("repeat_events", "Repeat recordable events (same mechanism and "
                           "contractor tree within 90 days)",
                           "أحداث متكررة (نفس الآلية ونفس مجموعة المقاول خلال 90 يوماً)",
                           Decimal(len(repeats)), 0)],
                )
            )  # fmt: skip
        out += access_warnings(engine, project_id, tree, m, label_en, label_ar, who_en, who_ar)
    return out


def access_warnings(
    engine: Engine,
    project_id: uuid.UUID,
    tree: EngFact | None,
    m: Window,
    label_en: str,
    label_ar: str,
    who_en: str,
    who_ar: str,
) -> list[Warn]:
    """E5-E7 (2-access-permits §6.9); unrounded comparisons."""
    af = getattr(engine.facts, "access", None)
    if af is None:
        return []
    out: list[Warn] = []
    a = engine.aggregate(m)
    # E5 induction coverage at month end
    k49 = engine.result(KpiMetric.K49, a)
    limit = Decimal(af.coverage_pct.get(project_id, 98))
    if k49.value is not None and k49.value < limit:
        out.append(
            Warn(
                E.E5, m, project_id, tree,
                f"Induction coverage below {limit:.0f} % at the end of {label_en}{who_en}",
                f"تغطية التعريف بالسلامة أقل من {limit:.0f} % في نهاية {label_ar}{who_ar}",
                [Input("k49_month_end", "Induction coverage (month end)",
                       "تغطية التعريف (نهاية الشهر)", k49.value, 1, " %"),
                 Input("threshold_pct", "Threshold", "الحد", limit, 0, " %"),
                 Input("deployed", "Active deployed workers", "العمال المعيّنون النشطون",
                       Decimal(k49.denominator or 0), 0)],
            )
        )  # fmt: skip
    # E6 gate denial rate spike
    k53 = engine.result(KpiMetric.K53, a).value
    priors = [engine.result(KpiMetric.K53, engine.aggregate(_prior(m, n))).value for n in (3, 2, 1)]
    mean = _mean(priors)
    if k53 is not None and mean is not None and k53 >= 2 * mean and k53 >= 1:
        out.append(
            Warn(
                E.E6, m, project_id, tree,
                f"Gate denial rate doubled in {label_en}{who_en}",
                f"تضاعفت نسبة الرفض عند البوابات في {label_ar}{who_ar}",
                [Input("k53_month", "Gate denial rate (month)", "نسبة الرفض (الشهر)", k53, 2, " %"),
                 Input("k53_prior3_mean", "Mean of prior 3 months", "متوسط الأشهر الثلاثة السابقة",
                       mean, 2, " %")],
            )
        )  # fmt: skip
    # E7 airside driving
    k57 = engine.result(KpiMetric.K57, a)
    comp = {c.key: c.value or Decimal(0) for c in k57.components}
    off05, susp = comp.get("off05", Decimal(0)), comp.get("suspensions", Decimal(0))
    if off05 >= 1 or susp >= 3:
        out.append(
            Warn(
                E.E7, m, project_id, tree,
                f"Serious airside driving offences or repeated ADP suspensions in "
                f"{label_en}{who_en}",
                f"مخالفات قيادة جوية خطيرة أو إيقافات متكررة لتصاريح القيادة في {label_ar}{who_ar}",
                [Input("off05", "OFF-05 runway incursions", "مخالفات OFF-05", off05, 0),
                 Input("adp_suspensions", "ADP suspensions", "إيقافات تصاريح القيادة", susp, 0)],
            )
        )  # fmt: skip
    return out


def repeat_events(scope: Scope, engine: Engine, m: Window) -> list[str]:
    """Incident refs in month ``m`` repeating a recordable case of the same mechanism in the
    same tier-1 tree within the previous 90 days (§6.9 E4, AI-10 (7))."""
    window = Window(m.start - timedelta(days=90), m.end)
    cases = [c for c in engine.cases if window.contains(c.d) and c.category in RECORDABLE]
    out = []
    for c in cases:
        if not m.contains(c.d) or c.d > engine.as_of:
            continue
        root = scope.facts.root_of(c.eng)
        for o in cases:
            if (
                o.id != c.id
                and o.incident_id != c.incident_id
                and o.mechanism == c.mechanism
                and scope.facts.root_of(o.eng) == root
                and c.d - timedelta(days=90) <= o.d <= c.d
                and (o.d, o.incident_ref) < (c.d, c.incident_ref)
            ):
                out.append(c.incident_ref)
                break
    return sorted(set(out))


def evaluate(scope: Scope, months: list[Window]) -> list[Warn]:
    out: list[Warn] = []
    for proj in scope.projects:
        sites = scope.project_sites.get(proj.id, frozenset())
        base = scope.narrowed_filter(sites=sites)
        project_engine = scope.sub_engine(base)
        out += evaluate_engine(scope, project_engine, proj.id, None, months)
        roots = [
            e for e in scope.facts.engagements.values() if e.project == proj.id and e.parent is None
        ]
        for root in sorted(roots, key=lambda e: e.code):
            tree = frozenset(scope.facts.descendants(root.id))
            flt = scope.narrowed_filter(engs=tree, sites=sites)
            if not flt.engs or flt.engs == base.engs:
                continue
            out += evaluate_engine(scope, scope.sub_engine(flt), proj.id, root, months)
    return out
