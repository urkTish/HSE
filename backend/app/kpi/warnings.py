"""Leading-indicator warnings E1-E4 (spec 1-dashboard §6.9), E5-E7 (2-access-permits §6.9),
E8-E9 (3-ptw §6.12), E10-E11 (4-third-party-cert §6.9) and E12-E13 (5-training §6.9), evaluated
per complete month per project and per tier-1 contractor tree. Means use unrounded values."""

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.hse_enums import RECORDABLE, KpiMetric, LeadingWarningCode
from app.kpi import fmt
from app.kpi.engine import Engine
from app.kpi.facts import EngFact
from app.kpi.followup import fu_warnings
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
        out += heat_warnings(engine, project_id, tree, m, label_en, label_ar, who_en, who_ar)
        out += emergency_warnings(engine, project_id, tree, m, label_en, label_ar, who_en, who_ar)
        out += field_warnings(engine, project_id, tree, m, label_en, label_ar, who_en, who_ar)
        out += env_warnings(engine, project_id, tree, m, label_en, label_ar, who_en, who_ar)
        out += fu_warnings(engine, project_id, tree, m, label_en, label_ar, who_en, who_ar)
    return out


def heat_warnings(
    engine: Engine,
    project_id: uuid.UUID,
    tree: EngFact | None,
    m: Window,
    label_en: str,
    label_ar: str,
    who_en: str,
    who_ar: str,
) -> list[Warn]:
    """E16-E17 (6b-heat-stress §6.8); unrounded comparisons; months with ban dates (E16), months
    overlapping the controls period or with a heat-illness entry (E17)."""
    from app.kpi import heat as kh  # noqa: PLC0415

    hf = kh.hfacts(engine)
    p = hf.proj(project_id) if hf is not None else None
    if p is None:
        return []
    c = p.cfg
    days = [m.start + timedelta(days=i) for i in range(m.days)]
    if not any(c.active_on(d) for d in days):
        return []
    out: list[Warn] = []
    if any(c.ban_date(d) and c.active_on(d) for d in days):
        b = kh.ban_stats(engine, m)
        k99 = Decimal(b.patrolled) / Decimal(b.required) * HUNDRED if b.required else None
        t99 = c.dec("ban_patrol_coverage_warning_pct")
        if b.violations >= 1 or (k99 is not None and k99 < t99):
            out.append(
                Warn(
                    E.E16, m, project_id, tree,
                    f"Midday-ban violations or low patrol coverage in {label_en}{who_en}",
                    f"مخالفات لحظر الظهيرة أو تغطية جولات منخفضة في {label_ar}{who_ar}",
                    [Input("k100_violations", "Ban violations", "مخالفات الحظر",
                           Decimal(b.violations), 0),
                     Input("k99", "Ban patrol coverage", "تغطية جولات الحظر", k99, 1, " %"),
                     Input("k99_numerator", "Patrolled zone-days", "أيام المناطق المفحوصة",
                           Decimal(b.patrolled), 0),
                     Input("k99_denominator", "Required zone-days", "أيام المناطق المطلوبة",
                           Decimal(b.required), 0),
                     Input("threshold_pct", "Threshold", "الحد", t99, 1, " %")],
                )
            )  # fmt: skip
    in_controls = any(c.in_controls(d) and c.active_on(d) for d in days)
    if in_controls or kh.has_entries(engine, m):
        gaps = kh.e17_gaps(engine, m)
        cov = kh.k97_counts(engine, m)
        k97 = Decimal(cov.covered) / Decimal(cov.required) * HUNDRED if cov.required else None
        wf = kh.welfare_stats(engine, m)
        k101 = Decimal(wf.compliant) / Decimal(wf.applicable) * HUNDRED if wf.applicable else None
        t97 = c.dec("wbgt_coverage_warning_pct")
        t101 = c.dec("welfare_compliance_warning_pct")
        if gaps >= 1 or (k97 is not None and k97 < t97) or (k101 is not None and k101 < t101):
            out.append(
                Warn(
                    E.E17, m, project_id, tree,
                    f"Heat-stress control gap or low monitoring/welfare in {label_en}{who_en}",
                    f"ثغرة في ضوابط الإجهاد الحراري أو انخفاض القياس/الراحة في "
                    f"{label_ar}{who_ar}",
                    [Input("control_gap_entries", "Heat-illness entries with a control gap",
                           "حالات إجهاد حراري مع ثغرة في الضوابط", Decimal(gaps), 0),
                     Input("k97", "WBGT monitoring coverage", "تغطية قياس المؤشر الحراري", k97,
                           1, " %"),
                     Input("k97_threshold_pct", "Coverage threshold", "حد التغطية", t97, 1,
                           " %"),
                     Input("k101", "Heat welfare compliance", "الامتثال لتدابير الراحة", k101,
                           1, " %"),
                     Input("k101_threshold_pct", "Welfare threshold", "حد الراحة", t101, 1,
                           " %")],
                )
            )  # fmt: skip
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


def emergency_warnings(
    engine: Engine,
    project_id: uuid.UUID,
    tree: EngFact | None,
    m: Window,
    label_en: str,
    label_ar: str,
    who_en: str,
    who_ar: str,
) -> list[Warn]:
    """E18-E19 (6c-emergency-drills §6.9); unrounded comparisons; months from
    emergency_register_from. T13 inputs: counts, numerators, denominators, thresholds and drill /
    event numbers only."""
    from app.kpi import emergency as ke  # noqa: PLC0415
    from app.services.emergency import common as ec  # noqa: PLC0415

    ef = ke.efacts(engine)
    if ef is None or project_id not in ef.active():
        return []
    c = ec.cfg(ef.db, project_id)
    if c.register_from is None or c.register_from > m.end:
        return []
    sub = engine
    out: list[Warn] = []

    def pct(num: int, den: int) -> Decimal | None:
        return Decimal(num) / Decimal(den) * HUNDRED if den else None

    items = [x for x in ke.programme_items(sub, m) if x.pid == project_id]
    k104 = pct(sum(1 for x in items if x.met), len(items))
    cov = ke.coverage_stats(sub, m)
    k106 = pct(cov.covered, cov.required)
    rd = ke.readiness_facts(sub, project_id, m)
    t104 = c.dec("drill_compliance_warning_pct")
    t106 = c.dec("coverage_warning_pct")
    if (
        (k104 is not None and k104 < t104)
        or rd.overdue_30
        or (k106 is not None and k106 < t106)
        or rd.erp_overdue
    ):
        out.append(
            Warn(
                E.E18, m, project_id, tree,
                f"Emergency preparedness below target in {label_en}{who_en}",
                f"الجاهزية للطوارئ دون المستهدف في {label_ar}{who_ar}",
                [Input("k104", "Drill programme compliance", "الالتزام ببرنامج التمارين", k104,
                       1, " %"),
                 Input("k104_numerator", "Items met on time", "بنود منفذة في الوقت",
                       Decimal(sum(1 for x in items if x.met)), 0),
                 Input("k104_denominator", "Items due", "البنود المستحقة", Decimal(len(items)), 0),
                 Input("k104_threshold_pct", "Programme threshold", "حد البرنامج", t104, 1, " %"),
                 Input("lines_overdue_30d", "Lines overdue > 30 days",
                       "بنود متأخرة أكثر من 30 يوماً", Decimal(len(rd.overdue_30)), 0),
                 Input("k106", "Emergency team coverage", "تغطية فريق الطوارئ", k106, 1, " %"),
                 Input("k106_threshold_pct", "Coverage threshold", "حد التغطية", t106, 1, " %"),
                 Input("erp_overdue", "ERP overdue", "خطة الطوارئ متأخرة",
                       Decimal(len(rd.erp_overdue)), 0)],
            )
        )  # fmt: skip
    a = ke.asset_stats(sub, m)
    k107 = pct(a.ready, a.total)
    cur, n, _bad = ke.team_stats(sub, m)
    k108 = pct(cur, n)
    t107 = c.dec("equipment_readiness_warning_pct")
    if (
        (k107 is not None and k107 < t107)
        or (k108 is not None and k108 < HUNDRED)
        or rd.headcount_over
        or rd.found
    ):
        refs = sorted(set(rd.headcount_over) | set(rd.found))
        out.append(
            Warn(
                E.E19, m, project_id, tree,
                f"Emergency response readiness below target in {label_en}{who_en}"
                + (f": {', '.join(refs)}" if refs else ""),
                f"جاهزية الاستجابة للطوارئ دون المستهدف في {label_ar}{who_ar}",
                [Input("k107", "Equipment readiness", "جاهزية المعدات", k107, 1, " %"),
                 Input("k107_threshold_pct", "Equipment threshold", "حد المعدات", t107, 1, " %"),
                 Input("k108", "Rescue team readiness", "جاهزية فرق الإنقاذ", k108, 1, " %"),
                 Input("headcount_over_target", "Drills / events over the headcount target",
                       "تمارين / أحداث تجاوزت هدف الحصر", Decimal(len(rd.headcount_over)), 0),
                 Input("found_on_site", "Found on site", "وُجد في الموقع", Decimal(len(rd.found)),
                       0)],
            )
        )  # fmt: skip
    return out


def field_warnings(
    engine: Engine,
    project_id: uuid.UUID,
    tree: EngFact | None,
    m: Window,
    label_en: str,
    label_ar: str,
    who_en: str,
    who_ar: str,
) -> list[Warn]:
    """E20-E21 (6d-field-assurance §6.8); unrounded comparisons. T13 inputs: numerators,
    denominators, thresholds and order / campaign numbers only."""
    from app.core.field_enums import StopOrderStatus  # noqa: PLC0415
    from app.kpi import field as kf  # noqa: PLC0415
    from app.models import StopWorkOrder  # noqa: PLC0415
    from app.services.field import common as fc  # noqa: PLC0415

    ff = kf.ffacts(engine)
    if ff is None or project_id not in ff.pids:
        return []
    db = ff.db
    c = fc.cfg(db, project_id)
    out: list[Warn] = []

    def pct(num: Decimal | int, den: Decimal | int) -> Decimal | None:
        return Decimal(num) / Decimal(den) * HUNDRED if den else None

    us = [u for u in kf.coverage_units(engine, m) if u.pid == project_id]
    cov_n = sum(1 for u in us if u.covered)
    k113 = pct(cov_n, len(us))
    its = [i for i in kf.programme_items(engine, m) if i.pid == project_id]
    met = sum(1 for i in its if i.met)
    k114 = pct(met, len(its))
    rs = [r for r in kf.resp_in(engine, m) if r.pid == project_id]
    crit = sum(r.crit for r in rs)
    rate = pct(crit, len(rs))
    t113 = c.dec("inspection_coverage_warning_pct")
    t114 = c.dec("audit_programme_warning_pct")
    t111 = c.dec("critical_fail_warning_per_100")
    month_end = fc.day_start(m.end + timedelta(days=1))
    long_orders = sorted(
        o.order_no
        for o in db.scalars(
            select(StopWorkOrder).where(
                StopWorkOrder.project_id == project_id,
                StopWorkOrder.status != StopOrderStatus.voided,
                StopWorkOrder.raised_at < month_end - timedelta(days=7),
            )
        )
        if (o.released_at is None or o.released_at >= month_end)
        and engine.flt.eng_ok(o.engagement_id)
    )
    if (
        (k113 is not None and k113 < t113)
        or (k114 is not None and k114 < t114)
        or (len(rs) >= 20 and rate is not None and rate >= t111)
        or long_orders
    ):
        out.append(
            Warn(
                E.E20, m, project_id, tree,
                f"Field assurance below target in {label_en}{who_en}"
                + (f": {', '.join(long_orders)}" if long_orders else ""),
                f"ضمان العمل الميداني دون المستهدف في {label_ar}{who_ar}",
                [Input("k113", "Contractor inspection coverage", "تغطية التفتيش", k113, 1, " %"),
                 Input("k113_numerator", "Covered", "مغطاة", Decimal(cov_n), 0),
                 Input("k113_denominator", "Required", "مطلوبة", Decimal(len(us)), 0),
                 Input("k113_threshold_pct", "Coverage threshold", "حد التغطية", t113, 1, " %"),
                 Input("k114", "Audit programme compliance", "برنامج التدقيق", k114, 1, " %"),
                 Input("k114_numerator", "Met on time", "في الموعد", Decimal(met), 0),
                 Input("k114_denominator", "Items due", "البنود المستحقة", Decimal(len(its)), 0),
                 Input("k114_threshold_pct", "Programme threshold", "حد البرنامج", t114, 1, " %"),
                 Input("k111_per_100", "Critical failures per 100 inspections",
                       "الإخفاقات الحرجة لكل 100 تفتيش", rate, 2),
                 Input("inspections", "Inspections", "عمليات التفتيش", Decimal(len(rs)), 0),
                 Input("k111_threshold", "Critical failure threshold", "حد الإخفاقات", t111, 2),
                 Input("stop_work_active_over_7d", "Stop-work orders active > 7 days",
                       "أوامر إيقاف سارية أكثر من 7 أيام", Decimal(len(long_orders)), 0)],
            )
        )  # fmt: skip
    if c.toolbox_from is None or c.toolbox_from > m.end:
        return out
    r = kf.reach(engine, m)
    units = [u for u in r.units if u.pid == project_id]
    num = sum((u.reach for u in units), Decimal(0))
    den = sum((u.h for u in units), Decimal(0))
    k116 = pct(num, den)
    pairs = kf.campaign_pairs(engine, m)
    ok = sum(1 for _, x in pairs if x)
    k117 = pct(ok, len(pairs))
    t116 = c.dec("tbt_reach_warning_pct")
    if (k116 is not None and k116 < t116) or (k117 is not None and k117 < HUNDRED):
        unmet = sorted({no for no, x in pairs if not x})
        out.append(
            Warn(
                E.E21, m, project_id, tree,
                f"Toolbox engagement below target in {label_en}{who_en}"
                + (f": {', '.join(unmet)}" if unmet else ""),
                f"المشاركة في اجتماعات التوعية دون المستهدف في {label_ar}{who_ar}",
                [Input("k116", "Toolbox weekly reach", "الوصول الأسبوعي", k116, 1, " %"),
                 Input("k116_threshold_pct", "Reach threshold", "حد الوصول", t116, 1, " %"),
                 Input("k117", "Campaign completion", "إنجاز الحملات", k117, 1, " %"),
                 Input("k117_numerator", "Pairs met on time", "أزواج في الموعد", Decimal(ok), 0),
                 Input("k117_denominator", "Pairs due", "الأزواج المستحقة",
                       Decimal(len(pairs)), 0)],
            )
        )  # fmt: skip
    return out


def env_warnings(
    engine: Engine,
    project_id: uuid.UUID,
    tree: EngFact | None,
    m: Window,
    label_en: str,
    label_ar: str,
    who_en: str,
    who_ar: str,
) -> list[Warn]:
    """E22-E23 (6e-environmental §6.8); unrounded comparisons. K-118, K-122, storage deadlines and
    authority complaints at project level only. T13 inputs: numerators, denominators, thresholds
    and record numbers only."""
    from app.core.env_enums import ComplaintChannel, ComplaintStatus  # noqa: PLC0415
    from app.kpi import env as ke  # noqa: PLC0415
    from app.models import EnvComplaint, WasteStorageArea  # noqa: PLC0415
    from app.services.env import common as ec  # noqa: PLC0415
    from app.services.env import waste  # noqa: PLC0415

    f = ke.efacts(engine)
    if f is None or project_id not in f.pids:
        return []
    db = f.db
    c = ec.cfg(db, project_id)
    out: list[Warn] = []
    a = engine.aggregate(m)
    project_level = tree is None

    def pct(num: Decimal | int, den: Decimal | int) -> Decimal | None:
        return Decimal(num) / Decimal(den) * HUNDRED if den else None

    k118 = k122 = None
    n118 = d118 = 0
    haz: list[str] = []
    if project_level:
        n118, d118, _exp = ke.permit_stats(db, [project_id], m.end)
        k118 = pct(n118, d118)
        ss = ke.slots(engine, m)
        k122 = pct(sum(1 for s in ss if s[2]), len(ss))
        for ar in db.scalars(
            select(WasteStorageArea).where(WasteStorageArea.project_id == project_id)
        ):
            haz += [
                f"{ar.area_code}·{h.stream_code}"
                for h in waste.haz_deadlines(db, ar, m.end)
                if m.start <= h.deadline < m.end
            ]
    on, n121, _late = ke.custody(engine, m)
    k121 = pct(on, n121)
    long_cons = sorted(
        x.no
        for x in ke.consignments(f)
        if x.pid == project_id
        and x.status not in ("voided", "rejected")
        and x.d < m.end - timedelta(days=30)
        and (x.received is None or x.received > m.end)
        and engine.flt.eng_ok(x.eng)
    )
    t121, t122 = c.dec("custody_warning_pct"), c.dec("monitoring_warning_pct")
    if (
        (k118 is not None and k118 < 100)
        or (n121 >= 10 and k121 is not None and k121 < t121)
        or (k122 is not None and k122 < t122)
        or haz
        or long_cons
    ):
        recs = haz + long_cons
        out.append(
            Warn(
                E.E22, m, project_id, tree,
                f"Environmental compliance below target in {label_en}{who_en}"
                + (f": {', '.join(recs)}" if recs else ""),
                f"الالتزام البيئي دون المستهدف في {label_ar}{who_ar}",
                [Input("k118", "Permit compliance at month end", "الالتزام بالتصاريح", k118, 1,
                       " %"),
                 Input("k118_numerator", "In force", "سارية", Decimal(n118), 0),
                 Input("k118_denominator", "Applicable", "مطلوبة", Decimal(d118), 0),
                 Input("k121", "Custody on time", "الاستلام في الموعد", k121, 1, " %"),
                 Input("k121_numerator", "On time", "في الموعد", Decimal(on), 0),
                 Input("k121_denominator", "Due", "المستحقة", Decimal(n121), 0),
                 Input("k121_threshold_pct", "Custody threshold", "حد الاستلام", t121, 1, " %"),
                 Input("k122", "Monitoring compliance", "الالتزام بخطة الرصد", k122, 1, " %"),
                 Input("k122_threshold_pct", "Monitoring threshold", "حد الرصد", t122, 1, " %"),
                 Input("haz_deadlines_passed", "Hazardous storage deadlines passed",
                       "تجاوز مهلة التخزين", Decimal(len(haz)), 0),
                 Input("dispatched_over_30d", "Consignments dispatched > 30 days",
                       "إشعارات مرسلة منذ أكثر من 30 يوماً", Decimal(len(long_cons)), 0)],
            )
        )  # fmt: skip
    k123 = engine.result(KpiMetric.K123, a).value or Decimal(0)
    spl = [s for s in ke.spills(engine, m) if s.project_id == project_id and s.reportable]
    k119 = engine.result(KpiMetric.K119, a).value or Decimal(0)
    k120 = engine.result(KpiMetric.K120, a).value
    tdiv = c.dec("diversion_target_pct")
    tcount = int(c["exceedance_warning_count"])
    auth: list[str] = []
    if project_level:
        auth = sorted(
            x.complaint_no
            for x in db.scalars(
                select(EnvComplaint).where(
                    EnvComplaint.project_id == project_id,
                    EnvComplaint.channel == ComplaintChannel.via_authority,
                    EnvComplaint.status != ComplaintStatus.voided,
                    EnvComplaint.received_date >= m.start,
                    EnvComplaint.received_date <= m.end,
                )
            )
        )
    low_div = k119 >= 10 and k120 is not None and k120 < tdiv
    if k123 >= tcount or spl or low_div or auth:
        recs = sorted(s.spill_no for s in spl) + auth
        out.append(
            Warn(
                E.E23, m, project_id, tree,
                f"Environmental performance warning in {label_en}{who_en}"
                + (f": {', '.join(recs)}" if recs else ""),
                f"إنذار الأداء البيئي في {label_ar}{who_ar}",
                [Input("k123", "Project-caused exceedances", "التجاوزات بسبب المشروع", k123, 0),
                 Input("k123_threshold", "Exceedance threshold", "حد التجاوزات",
                       Decimal(tcount), 0),
                 Input("reportable_spills", "Reportable spills", "انسكابات واجبة الإبلاغ",
                       Decimal(len(spl)), 0),
                 Input("k119_t", "Waste generated (t)", "النفايات المتولدة", k119, 1),
                 Input("k120", "Diversion rate", "نسبة التحويل", k120, 1, " %"),
                 Input("k120_target_pct", "Diversion target", "هدف التحويل", tdiv, 1, " %"),
                 Input("authority_complaints", "Complaints via an authority",
                       "شكاوى عن طريق جهة رسمية", Decimal(len(auth)), 0)],
            )
        )  # fmt: skip
    return out
