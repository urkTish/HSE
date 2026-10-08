"""Leading-indicator warnings E1-E4 (spec 1-dashboard §6.9), E5-E7 (2-access-permits §6.9),
E8-E9 (3-ptw §6.12), E10-E11 (4-third-party-cert §6.9) and E12-E13 (5-training §6.9), evaluated
per complete month per project and per tier-1 contractor tree. Means use unrounded values."""

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
        out += ptw_warnings(engine, project_id, tree, m, label_en, label_ar, who_en, who_ar)
        out += cert_warnings(engine, project_id, tree, m, label_en, label_ar, who_en, who_ar)
        out += training_warnings(engine, project_id, tree, m, label_en, label_ar, who_en, who_ar)
    return out


def cert_warnings(
    engine: Engine,
    project_id: uuid.UUID,
    tree: EngFact | None,
    m: Window,
    label_en: str,
    label_ar: str,
    who_en: str,
    who_ar: str,
) -> list[Warn]:
    """E10-E11 (4-third-party-cert §6.9); unrounded comparisons, values at the month end."""
    from app.kpi import cert as kc  # noqa: PLC0415
    from app.kpi.cert_facts import E11_FAILED  # noqa: PLC0415

    cf = kc.facts(engine)
    st = cf.settings.get(project_id)
    if st is None:
        return []
    for attr in ("equipment_categories", "cert_types"):
        if not hasattr(engine, attr):
            setattr(engine, attr, None)
    out: list[Warn] = []
    a = engine.aggregate(m)
    k72 = engine.result(KpiMetric.K72, a).value
    k76 = engine.result(KpiMetric.K76, a).value
    k81 = engine.result(KpiMetric.K81, a).value
    t72 = Decimal(st.equipment_cert_warning_pct)
    t76 = Decimal(st.personnel_cert_warning_pct)
    t81 = Decimal(st.scaffold_tag_warning_pct)
    if (
        (k72 is not None and k72 < t72)
        or (k76 is not None and k76 < t76)
        or (k81 is not None and k81 < t81)
    ):
        out.append(
            Warn(
                E.E10, m, project_id, tree,
                f"Certification compliance below threshold in {label_en}{who_en}",
                f"انخفاض الامتثال للشهادات عن الحد في {label_ar}{who_ar}",
                [Input("k72", "Equipment certificate compliance", "امتثال شهادات المعدات", k72, 1,
                       " %"),
                 Input("k72_threshold_pct", "Equipment threshold", "حد المعدات", t72, 1, " %"),
                 Input("k76", "Personnel certification compliance", "امتثال شهادات الأفراد", k76,
                       1, " %"),
                 Input("k76_threshold_pct", "Personnel threshold", "حد الأفراد", t76, 1, " %"),
                 Input("k81", "Scaffold tag compliance", "امتثال بطاقات السقالات", k81, 1, " %"),
                 Input("k81_threshold_pct", "Scaffold threshold", "حد السقالات", t81, 1, " %")],
            )
        )  # fmt: skip
    failed = len(kc.failed_verifications(engine, a, E11_FAILED))
    a_def = len(kc.a_defects(engine, a))
    limit = int(st.dangerous_defect_warning_count)
    if failed >= 1 or a_def >= limit:
        out.append(
            Warn(
                E.E11, m, project_id, tree,
                f"Failed certificate verification or dangerous defects in {label_en}{who_en}",
                f"تحقق فاشل من شهادة أو عيوب خطيرة في {label_ar}{who_ar}",
                [Input("failed_verifications", "Failed verifications", "تحقق فاشل",
                       Decimal(failed), 0),
                 Input("a_defects", "Category A defects raised", "عيوب الفئة A", Decimal(a_def), 0),
                 Input("a_defects_threshold", "A defects threshold", "حد عيوب الفئة A",
                       Decimal(limit), 0)],
            )
        )  # fmt: skip
    return out


def training_warnings(
    engine: Engine,
    project_id: uuid.UUID,
    tree: EngFact | None,
    m: Window,
    label_en: str,
    label_ar: str,
    who_en: str,
    who_ar: str,
) -> list[Warn]:
    """E12-E13 (5-training §6.9); K-82 unrounded at the month end, denominator 0 → no E12."""
    from app.kpi import training as kt  # noqa: PLC0415

    tf = kt.tfacts(engine)
    if tf is None:
        return []
    for attr in ("trades", "course_codes", "course_categories"):
        if not hasattr(engine, attr):
            setattr(engine, attr, None)
    out: list[Warn] = []
    st = tf.settings.get(project_id)
    t = Decimal(st.training_matrix_warning_pct) if st is not None else Decimal("98.0")
    a = engine.aggregate(m)
    r = kt.req_kpis(engine, a)
    if r.counted > 0:
        k82 = Decimal(r.met) / Decimal(r.counted) * HUNDRED
        if k82 < t:
            out.append(
                Warn(
                    E.E12, m, project_id, tree,
                    f"Training matrix compliance below threshold in {label_en}{who_en}",
                    f"انخفاض الامتثال لمصفوفة التدريب عن الحد في {label_ar}{who_ar}",
                    [Input("k82", "Training matrix compliance", "امتثال مصفوفة التدريب", k82, 1,
                           " %"),
                     Input("k82_numerator", "Met or expiring", "مستوفاة أو قريبة الانتهاء",
                           Decimal(r.met), 0),
                     Input("k82_denominator", "Counted requirements", "المتطلبات المحتسبة",
                           Decimal(r.counted), 0),
                     Input("threshold_pct", "Threshold", "الحد", t, 1, " %")],
                )
            )  # fmt: skip
    ver, void = kt.failures(engine, a)
    if ver or void:
        out.append(
            Warn(
                E.E13, m, project_id, tree,
                f"Failed training verification or voided session in {label_en}{who_en}",
                f"تحقق فاشل من شهادة تدريب أو جلسة ملغاة في {label_ar}{who_ar}",
                [Input("failed_verifications", "Failed training verifications",
                       "تحقق فاشل من شهادات التدريب", Decimal(ver), 0),
                 Input("voided_sessions", "Voided sessions", "جلسات ملغاة", Decimal(void), 0)],
            )
        )  # fmt: skip
    return out


def ptw_warnings(
    engine: Engine,
    project_id: uuid.UUID,
    tree: EngFact | None,
    m: Window,
    label_en: str,
    label_ar: str,
    who_en: str,
    who_ar: str,
) -> list[Warn]:
    """E8-E9 (3-ptw §6.12); unrounded comparisons."""
    from app.kpi import ptw as kp  # noqa: PLC0415

    pf = kp.facts(engine)
    st = pf.settings.get(project_id)
    if st is None:
        return []
    out: list[Warn] = []
    a = engine.aggregate(m)
    # E8 audit compliance / critical findings
    k46 = engine.result(KpiMetric.K46, a).value or Decimal(0)
    k61 = engine.result(KpiMetric.K61, a).value
    k64 = engine.result(KpiMetric.K64, a).value or Decimal(0)
    pct = Decimal(st.ptw_audit_warning_pct)
    crit = Decimal(st.ptw_critical_findings_warning)
    if (k46 >= 10 and k61 is not None and k61 < pct) or k64 >= crit:
        out.append(
            Warn(
                E.E8, m, project_id, tree,
                f"PTW audit compliance low or critical PTW findings high in {label_en}{who_en}",
                "انخفاض الالتزام في تدقيق التصاريح أو ارتفاع المخالفات الحرجة في "
                f"{label_ar}{who_ar}",
                [Input("k46", "Field audits", "التدقيقات الميدانية", k46, 0),
                 Input("k61", "Audit compliance", "الالتزام في التدقيق", k61, 1, " %"),
                 Input("k61_threshold_pct", "Compliance threshold", "حد الالتزام", pct, 1, " %"),
                 Input("k64", "Critical findings", "المخالفات الحرجة", k64, 0),
                 Input("k64_threshold", "Critical findings threshold", "حد المخالفات", crit, 0)],
            )
        )  # fmt: skip
    # E9 closure compliance / shift lapses
    r69 = engine.result(KpiMetric.K69, a)
    ended = Decimal(r69.denominator or 0)
    k69 = r69.value
    cpct = Decimal(st.ptw_closure_warning_pct)
    k70 = engine.result(KpiMetric.K70, a).value or Decimal(0)
    priors = [engine.result(KpiMetric.K70, engine.aggregate(_prior(m, n))).value for n in (3, 2, 1)]
    mean = _mean(priors)
    lapse = mean is not None and k70 >= 2 * mean and k70 >= 5
    if (ended >= 10 and k69 is not None and k69 < cpct) or lapse:
        out.append(
            Warn(
                E.E9, m, project_id, tree,
                f"Permit closure compliance low or shift lapses rising in {label_en}{who_en}",
                f"انخفاض الالتزام بإغلاق التصاريح أو ارتفاع انقضاء الورديات في {label_ar}{who_ar}",
                [Input("k69", "Closure compliance", "الالتزام بالإغلاق", k69, 1, " %"),
                 Input("k69_threshold_pct", "Closure threshold", "حد الإغلاق", cpct, 1, " %"),
                 Input("closed_or_expired", "Permits closed or expired",
                       "التصاريح المغلقة أو المنتهية", ended, 0),
                 Input("k70", "Shift lapses", "انقضاء الورديات", k70, 0),
                 Input("k70_prior3_mean", "Mean of prior 3 months", "متوسط الأشهر الثلاثة السابقة",
                       mean, 2)],
            )
        )  # fmt: skip
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
