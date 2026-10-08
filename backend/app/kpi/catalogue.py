"""KPI catalogue §6.1: labels (EN/AR), kind, unit, direction, decimals, base."""

from dataclasses import dataclass, replace

from app.core.hse_enums import KpiBaseKind, KpiBetter, KpiGroup, KpiKind, KpiMetric

M = KpiMetric
K = KpiKind
G = KpiGroup
LOW = KpiBetter.lower_is_better
HIGH = KpiBetter.higher_is_better
NONE = KpiBetter.none
BL = KpiBaseKind.ltifr
BR = KpiBaseKind.rate


PHASE2_METRICS: frozenset[KpiMetric] = frozenset(
    {
        M.K48, M.K49, M.K50, M.K51, M.K52, M.K53, M.K53b, M.K54, M.K55, M.K56, M.K57,
        M.K58, M.K59, M.K60,
    }
)  # fmt: skip
PHASE2_PENDING: frozenset[KpiMetric] = frozenset()
"""Access KPIs not computed yet (none since stage 2)."""
PHASE3_METRICS: frozenset[KpiMetric] = frozenset(
    {
        M.K46b, M.K61, M.K62, M.K63, M.K64, M.K65, M.K66, M.K67, M.K68, M.K69, M.K70,
        M.K71,
    }
)  # fmt: skip
PHASE3_PENDING: frozenset[KpiMetric] = frozenset()
"""PTW KPIs not computed yet (none since Phase 3 stage 2)."""
PHASE4_METRICS: frozenset[KpiMetric] = frozenset(
    {M.K72, M.K73, M.K74, M.K75, M.K76, M.K77, M.K78, M.K79, M.K80, M.K81}
)
PHASE4_PENDING: frozenset[KpiMetric] = frozenset()
"""Certification KPIs not computed yet (none since Phase 4 stage 2)."""
PHASE5_METRICS: frozenset[KpiMetric] = frozenset({M.K82, M.K83, M.K84, M.K85, M.K86, M.K87, M.K88})
PHASE5_PENDING: frozenset[KpiMetric] = frozenset()
"""Training KPIs not computed yet (stage 1: catalogued, value null NOT_AVAILABLE_YET)."""
PHASE6A_METRICS: frozenset[KpiMetric] = frozenset(
    {M.K89, M.K90, M.K91, M.K92, M.K93, M.K94, M.K95, M.K96}
)
PHASE6A_PENDING: frozenset[KpiMetric] = PHASE6A_METRICS
"""Occupational health KPIs not computed yet (stage 1: catalogued, value null)."""
_PENDING = PHASE2_PENDING | PHASE3_PENDING | PHASE4_PENDING | PHASE5_PENDING | PHASE6A_PENDING


@dataclass(frozen=True)
class KpiDef:
    metric: KpiMetric
    label_en: str
    label_ar: str
    short_en: str
    short_ar: str
    kind: KpiKind
    group: KpiGroup
    better: KpiBetter
    unit_en: str
    unit_ar: str
    formula_en: str
    decimals: int = 0
    base_kind: KpiBaseKind | None = None
    numerator_en: str | None = None
    denominator_en: str | None = None
    available: bool = True

    @property
    def spec_ref(self) -> str:
        if self.metric in PHASE2_METRICS:
            return f"2-access-permits §6.8 {self.metric.value}"
        if self.metric in PHASE3_METRICS:
            return f"3-ptw §6.11 {self.metric.value}"
        if self.metric in PHASE4_METRICS:
            return f"4-third-party-cert §6.7 {self.metric.value}"
        if self.metric in PHASE5_METRICS:
            return f"5-training §6.8 {self.metric.value}"
        if self.metric in PHASE6A_METRICS:
            return f"6a-occupational-health §6.6 {self.metric.value}"
        return f"1-dashboard §6.1 {self.metric.value}"


def _count(
    m: KpiMetric,
    en: str,
    ar: str,
    short_en: str,
    short_ar: str,
    group: KpiGroup,
    better: KpiBetter,
    formula: str,
    unit: tuple[str, str] = ("count", "عدد"),
) -> KpiDef:
    return KpiDef(m, en, ar, short_en, short_ar, K.count_, group, better, *unit, formula)


def _rate(
    m: KpiMetric,
    en: str,
    ar: str,
    short_en: str,
    short_ar: str,
    numerator: str,
    better: KpiBetter = LOW,
    base: KpiBaseKind = BR,
    group: KpiGroup = G.lagging,
) -> KpiDef:
    b = "B_L" if base == BL else "B"
    return KpiDef(
        m,
        en,
        ar,
        short_en,
        short_ar,
        K.rate,
        group,
        better,
        "rate",
        "معدل",
        f"{numerator} × {b} ÷ man-hours",
        2,
        base,
        numerator,
        "Man-hours",
    )


def _pct(
    m: KpiMetric,
    en: str,
    ar: str,
    short_en: str,
    short_ar: str,
    formula: str,
    group: KpiGroup = G.leading,
    better: KpiBetter = HIGH,
    numerator: str | None = None,
    denominator: str | None = None,
) -> KpiDef:
    return KpiDef(
        m, en, ar, short_en, short_ar, K.percentage, group, better, "%", "%", formula, 1,
        None, numerator, denominator,
    )  # fmt: skip


CATALOGUE: dict[KpiMetric, KpiDef] = {
    d.metric: (replace(d, available=False) if d.metric in _PENDING else d)
    for d in [
        KpiDef(M.K01, "Man-hours", "ساعات العمل", "Man-hours", "ساعات العمل", K.hours,
               G.exposure, NONE, "h", "ساعة", "Σ man_hours (submitted/verified/locked rows)"),
        _pct(M.K02, "Direct / subcontractor man-hours", "ساعات المباشر والباطن",
             "Direct share", "حصة المباشر", "direct man-hours ÷ K-01 × 100", G.exposure, NONE,
             "Direct man-hours", "Man-hours"),
        KpiDef(M.K03, "Average daily headcount", "متوسط العمالة اليومية", "Avg headcount",
               "متوسط العمالة", K.average, G.exposure, NONE, "workers", "عامل",
               "Σ headcount ÷ dates with headcount > 0", 0, None, "Σ headcount",
               "Dates with headcount > 0"),
        _count(M.K04, "Peak daily headcount", "ذروة العمالة اليومية", "Peak headcount",
               "ذروة العمالة", G.exposure, NONE, "max over dates of Σ headcount",
               ("workers", "عامل")),
        _count(M.K05, "Fatalities", "الوفيات", "FAT", "الوفيات", G.lagging, LOW, "n(FAT)"),
        _count(M.K05b, "Permanent disability cases", "حالات العجز الدائم", "Perm. disability",
               "العجز الدائم", G.lagging, LOW, "n(permanent_disability ≠ none)"),
        _count(M.K06, "LTIs (incl. fatalities)", "الإصابات المضيعة للوقت (شاملة الوفيات)", "LTI",
               "الإصابات المضيعة للوقت", G.lagging, LOW, "n(FAT) + n(LTI)"),
        _count(M.K07, "Restricted work cases", "حالات العمل المقيد", "RWC", "العمل المقيد",
               G.lagging, LOW, "n(RWC)"),
        _count(M.K08, "Job transfer cases", "حالات النقل لعمل آخر", "JTC", "النقل لعمل آخر",
               G.lagging, LOW, "n(JTC)"),
        _count(M.K09, "Medical treatment cases", "حالات العلاج الطبي", "MTC", "العلاج الطبي",
               G.lagging, LOW, "n(MTC)"),
        _count(M.K10, "Total recordable injuries (TRI)", "إجمالي الإصابات المسجلة", "TRI",
               "الإصابات المسجلة", G.lagging, LOW, "n(FAT + LTI + RWC + JTC + MTC)"),
        _count(M.K11, "DART cases", "حالات DART", "DART cases", "حالات DART", G.lagging, LOW,
               "n(LTI + RWC + JTC), fatalities excluded"),
        _count(M.K12, "First aid cases", "حالات الإسعاف الأولي", "FAC", "الإسعاف الأولي",
               G.lagging, LOW, "n(FAC)"),
        _count(M.K13, "Near misses", "الحوادث الوشيكة", "NM", "الحوادث الوشيكة", G.lagging, HIGH,
               "n(events with near_miss)"),
        _count(M.K14, "Dangerous occurrences", "الأحداث الخطيرة", "DO", "الأحداث الخطيرة",
               G.lagging, LOW, "n(events with dangerous_occurrence)"),
        _count(M.K15, "Property damage events", "أضرار الممتلكات", "PD", "أضرار الممتلكات",
               G.lagging, LOW, "n(events with property_damage); Σ estimated cost SAR"),
        _count(M.K16, "Environmental incidents", "الحوادث البيئية", "ENV", "الحوادث البيئية",
               G.lagging, LOW, "n(events with environmental)"),
        KpiDef(M.K17, "Lost days", "أيام العمل الضائعة", "Lost days", "الأيام الضائعة", K.days,
               G.lagging, LOW, "days", "يوم",
               "Σ days away (capped) over LTI cases + fatality charge (§6.3)"),
        KpiDef(M.K18, "Restricted + transfer days", "أيام العمل المقيد والنقل",
               "Restricted days", "أيام العمل المقيد", K.days, G.lagging, LOW, "days", "يوم",
               "Σ restricted_days + transfer_days (capped)"),
        _rate(M.K20, "LTIFR", "معدل تكرار الإصابات المضيعة للوقت", "LTIFR",
              "معدل الإصابات المضيعة للوقت", "LTIs (K-06)", base=BL),
        _rate(M.K21, "TRIR", "معدل الإصابات المسجلة", "TRIR", "معدل الإصابات المسجلة",
              "TRI (K-10)"),
        _rate(M.K22, "DART rate", "معدل DART", "DART", "معدل DART", "DART cases (K-11)"),
        _rate(M.K23, "LTISR (severity)", "معدل شدة الإصابات", "LTISR", "معدل الشدة",
              "Lost days (K-17)"),
        _rate(M.K24, "First aid rate", "معدل الإسعاف الأولي", "FA rate", "معدل الإسعاف الأولي",
              "FAC (K-12)"),
        _rate(M.K25, "Near-miss rate", "معدل الحوادث الوشيكة", "NM rate",
              "معدل الحوادث الوشيكة", "Near misses (K-13)", HIGH),
        _rate(M.K26a, "Dangerous occurrence rate", "معدل الأحداث الخطيرة", "DO rate",
              "معدل الأحداث الخطيرة", "Dangerous occurrences (K-14)"),
        _rate(M.K26b, "Property damage rate", "معدل أضرار الممتلكات", "PD rate",
              "معدل أضرار الممتلكات", "Property damage events (K-15)"),
        _rate(M.K26c, "Environmental incident rate", "معدل الحوادث البيئية", "ENV rate",
              "معدل الحوادث البيئية", "Environmental incidents (K-16)"),
        KpiDef(M.K27, "Near-miss ratio", "نسبة الحوادث الوشيكة إلى الإصابات", "NM ratio",
               "نسبة الحوادث الوشيكة", K.ratio, G.leading, HIGH, "ratio", "نسبة",
               "K-13 ÷ (K-10 + K-12)", 1, None, "Near misses", "TRI + FAC"),
        KpiDef(M.K28, "LTI-free days", "أيام بدون إصابة مضيعة للوقت", "LTI-free days",
               "أيام بدون إصابة", K.days, G.lagging, HIGH, "days", "يوم", "§6.4 at as_of"),
        KpiDef(M.K29, "LTI-free man-hours", "ساعات بدون إصابة مضيعة للوقت", "LTI-free hours",
               "ساعات بدون إصابة", K.hours, G.lagging, HIGH, "h", "ساعة", "§6.4 at as_of"),
        _count(M.K30, "Observations", "الملاحظات", "Observations", "الملاحظات", G.leading, HIGH,
               "n(observations); safe / unsafe by obs_type"),
        _pct(M.K31, "Safe observation share", "نسبة الملاحظات الآمنة", "Safe %",
             "الملاحظات الآمنة %", "safe ÷ total × 100", numerator="Safe observations",
             denominator="Observations"),
        _rate(M.K32, "Observation rate", "معدل الملاحظات", "Obs rate", "معدل الملاحظات",
              "Observations (K-30)", HIGH, group=G.leading),
        _pct(M.K33, "Unsafe observation close-out", "نسبة إغلاق الملاحظات غير الآمنة",
             "Unsafe closed %", "إغلاق غير الآمنة %",
             "unsafe closed at as_of ÷ unsafe observed in period × 100",
             numerator="Unsafe closed", denominator="Unsafe observations"),
        _pct(M.K34, "Inspection compliance (on time)", "الالتزام بالتفتيش في الموعد",
             "Inspections on time", "التفتيش في الموعد", "on time ÷ D_insp × 100",
             numerator="On time", denominator="Planned inspections due (D_insp)"),
        _pct(M.K35, "Inspection completion (incl. late)", "نسبة إنجاز التفتيش (شاملة المتأخر)",
             "Inspections done %", "إنجاز التفتيش", "(on time + late) ÷ D_insp × 100",
             numerator="On time + late", denominator="Planned inspections due (D_insp)"),
        _count(M.K35b, "Inspections done", "عدد عمليات التفتيش المنجزة", "Inspections done",
               "التفتيش المنجز", G.leading, HIGH, "completed (planned + unplanned) in period"),
        _count(M.K36, "Toolbox talks", "اجتماعات التوعية", "Toolbox talks", "اجتماعات التوعية",
               G.leading, HIGH, "Σ toolbox_talks; Σ toolbox_attendees"),
        KpiDef(M.K37, "Training hours per worker", "ساعات التدريب لكل عامل", "Training h/worker",
               "التدريب لكل عامل", K.average, G.leading, HIGH, "h/worker", "ساعة/عامل",
               "Σ training hours ÷ K-03; per day one source (v1.4): the training register for "
               "days ≥ training_register_from, daily-return training_hours before it", 2, None,
               "Σ training hours", "Average headcount"),
        _count(M.K38, "Inductions", "التعريفات بالسلامة", "Inductions", "التعريفات", G.leading,
               NONE, "Σ inductions"),
        _pct(M.K39, "HSE meeting attendance", "نسبة حضور اجتماعات السلامة", "Meeting attendance",
             "حضور الاجتماعات", "Σ attended ÷ Σ invited × 100 (meetings held)",
             numerator="Attended", denominator="Invited"),
        _count(M.K40, "CAs raised / closed", "الإجراءات المنشأة والمغلقة", "CAs raised",
               "الإجراءات المنشأة", G.leading, NONE, "created in period; verified in period"),
        _pct(M.K41, "CA on-time closure", "نسبة إغلاق الإجراءات في الموعد", "CA on time",
             "الإغلاق في الموعد", "closed on time ÷ due in period (≤ as_of) × 100",
             numerator="Closed by due date", denominator="Due in period"),
        _count(M.K42, "Overdue CAs", "الإجراءات المتأخرة", "Overdue CAs", "الإجراءات المتأخرة",
               G.leading, LOW, "open/in progress with as_of > due date"),
        _count(M.K42b, "Verification overdue", "تحقق متأخر", "Verification overdue",
               "تحقق متأخر", G.leading, LOW, "pending verification > completed + 3 days"),
        _pct(M.K43, "Control-level mix (engineering or higher)",
             "توزيع مستويات التحكم (هندسي أو أعلى)", "Higher controls %", "التحكم الأعلى %",
             "CAs created in period at elimination/substitution/engineering ÷ all × 100",
             numerator="Engineering or higher", denominator="CAs created"),
        _count(M.K44, "HiPo events", "أحداث عالية الخطورة المحتملة", "HiPo", "عالية الخطورة",
               G.lagging, NONE, "n(potential_severity ≥ 4)"),
        _pct(M.K45, "Data completeness", "اكتمال البيانات", "Completeness", "اكتمال البيانات",
             "reported engagement-site-days ÷ expected × 100", G.data_quality,
             numerator="Reported engagement-site-days",
             denominator="Expected engagement-site-days"),
        _count(M.K46, "PTW field audits", "تدقيقات تصاريح العمل الميدانية", "PTW field audits",
               "التدقيقات الميدانية", G.leading, HIGH,
               "n(field audits Completed or Locked, audited_at in period); K-46b coverage chip",
               ("audits", "تدقيق")),
        _count(M.K47, "Late reports", "البلاغات المتأخرة", "Late reports", "البلاغات المتأخرة",
               G.data_quality, LOW, "n(reported_at − occurred_at > 24 h)"),
        # ---- Phase 2 access KPIs (2-access-permits §6.8) ----
        _count(M.K48, "Active deployed workers", "العمال المعيّنون النشطون", "Deployed workers",
               "العمال المعيّنون", G.exposure, NONE,
               "n(contractor_worker deployments Mobilised at as_of)", ("workers", "عامل")),
        _pct(M.K49, "Induction coverage", "تغطية التعريف بالسلامة", "Induction coverage",
             "تغطية التعريف", "K-48 with a Valid general_site induction ÷ K-48 × 100",
             numerator="Deployed with valid induction", denominator="Active deployed workers"),
        _pct(M.K50, "Induction first-attempt pass rate", "نسبة النجاح من المحاولة الأولى",
             "First-attempt pass", "النجاح من أول محاولة",
             "first attempts passed ÷ first attempts delivered in period × 100",
             numerator="First attempts passed", denominator="First attempts"),
        _count(M.K51, "Credentials expiring ≤ 30 days", "التصاريح القريبة من الانتهاء",
               "Expiring ≤ 30 d", "تنتهي خلال 30 يوماً", G.leading, LOW,
               "n(valid credentials with eff in [as_of, as_of + 30]) by kind"),
        _count(M.K52, "Gate checks", "عمليات التحقق عند البوابات", "Gate checks",
               "التحقق عند البوابات", G.exposure, NONE, "n(in-direction checks in period)"),
        KpiDef(M.K53, "Gate denial rate", "نسبة الرفض عند البوابات", "Gate denials",
               "الرفض عند البوابات", K.percentage, G.leading, LOW, "%", "%",
               "denied in-checks ÷ K-52 × 100; by first DENY reason", 2, None,
               "Denied checks", "Gate checks"),
        _count(M.K53b, "Admitted despite denial", "دخول رغم الرفض", "Admitted despite denial",
               "دخول رغم الرفض", G.leading, LOW, "n(gate-log rows admitted_despite_denial)"),
        _pct(M.K54, "Pass return compliance", "الالتزام بإرجاع التصاريح", "Pass returns",
             "إرجاع التصاريح",
             "returned by due date ÷ items due in period (≤ as_of) × 100",
             numerator="Returned on time", denominator="Items due"),
        _count(M.K55, "Unreturned overdue", "تصاريح غير مُعادة متأخرة", "Unreturned overdue",
               "غير مُعادة متأخرة", G.leading, LOW,
               "n(custody Return Due and as_of > return_due_on); ageing 1-7, 8-30, > 30"),
        KpiDef(M.K56, "Pass application lead time", "مدة إصدار التصريح", "Pass lead time",
               "مدة الإصدار", K.days, G.leading, LOW, "days", "يوم",
               "median(issued − submitted) over applications issued in period", 1),
        KpiDef(M.K57, "Airside driving offence rate", "معدل مخالفات القيادة الجوية",
               "Offence rate", "معدل المخالفات", K.rate, G.leading, LOW, "per 100 ADPs",
               "لكل 100 تصريح", "offences in period × 100 ÷ Active ADPs at as_of", 2, None,
               "Offences", "Active ADPs"),
        _count(M.K58, "WAP activity", "نشاط تصاريح دخول المناطق", "WAPs approved",
               "التصاريح المعتمدة", G.leading, NONE,
               "approved in period; Active at as_of; suspensions by reason; blocked WAP-days"),
        _pct(M.K59, "NOTAM request lead-time compliance", "الالتزام بمهلة طلب NOTAM",
             "NOTAM lead time", "مهلة NOTAM",
             "NOTAM requests on time ÷ submitted in period × 100",
             numerator="On time", denominator="Submitted"),
        _count(M.K60, "Obstacle clearances", "موافقات العوائق", "Obstacle clearances",
               "موافقات العوائق", G.leading, NONE,
               "active at as_of; expiring ≤ 7 days; rejected in period; active with penetration"),
        # ---- Phase 3 PTW KPIs (3-ptw §6.11) ----
        _pct(M.K46b, "PTW audit coverage", "تغطية تدقيق التصاريح", "Audit coverage",
             "تغطية التدقيق",
             "distinct permits with ≥ 1 field audit ÷ permits Issued/Active/Suspended in "
             "period × 100", numerator="Audited permits", denominator="Live permits"),
        _pct(M.K61, "PTW audit compliance", "نسبة الالتزام في تدقيق التصاريح",
             "Audit compliance", "الالتزام في التدقيق",
             "Σ compliant_count ÷ Σ applicable_count × 100 over field audits in period",
             numerator="Compliant items", denominator="Applicable items"),
        _count(M.K62, "Permits issued", "التصاريح الصادرة", "Permits issued",
               "التصاريح الصادرة", G.exposure, NONE,
               "n(permits with first issued_at in period); by primary type, any type, high-risk",
               ("permits", "تصريح")),
        _count(M.K63, "Permit-shifts", "ورديات التصاريح", "Permit-shifts", "ورديات التصاريح",
               G.exposure, NONE, "n(shift records with started_at in period)",
               ("shifts", "وردية")),
        KpiDef(M.K64, "Critical PTW findings", "المخالفات الحرجة لتصاريح العمل",
               "Critical findings", "المخالفات الحرجة", K.count_, G.leading, LOW, "count", "عدد",
               "critical non-compliant field-audit items + unpermitted_work audits; "
               "rate = count × 100 ÷ K-46", 0, None, "Critical findings", "Field audits"),
        KpiDef(M.K65, "Non-routine suspensions", "الإيقافات غير الاعتيادية",
               "Non-routine suspensions", "الإيقافات غير الاعتيادية", K.count_, G.leading, NONE,
               "count", "عدد",
               "n(suspension events with routine = false); rate = count × 100 ÷ K-63", 0, None,
               "Non-routine suspensions", "Permit-shifts"),
        _pct(M.K66, "Gas-test compliance", "الالتزام بفحص الغاز", "Gas-test compliance",
             "الالتزام بفحص الغاز",
             "compliant gas-required shifts ended ÷ gas-required shifts ended × 100 (§6.3)",
             numerator="Compliant shifts", denominator="Gas-required shifts"),
        _count(M.K67, "Active isolations", "العزل النشط", "Active isolations", "العزل النشط",
               G.leading, NONE,
               "n(certificates Isolated, Verified or De-isolation Requested at as_of); "
               "of which long-term", ("certificates", "شهادة")),
        _count(M.K68, "SIMOPS conflicts", "تعارضات العمليات المتزامنة", "SIMOPS conflicts",
               "تعارضات العمليات", G.leading, NONE,
               "n(conflicts detected in period) by result; n(open at as_of)"),
        _pct(M.K69, "Permit closure compliance", "الالتزام بإغلاق التصاريح",
             "Closure compliance", "الالتزام بالإغلاق",
             "permits Closed ÷ permits Closed or Expired in period × 100",
             numerator="Closed", denominator="Closed or Expired"),
        _count(M.K70, "Shift lapses", "انقضاء الورديات دون تسليم", "Shift lapses",
               "انقضاء الورديات", G.leading, LOW,
               "n(shift records with end_type lapsed and ended_at in period)"),
        KpiDef(M.K71, "Permit turnaround", "مدة إصدار التصريح", "Permit turnaround",
               "مدة الإصدار", K.hours, G.leading, LOW, "h", "ساعة",
               "median(first issued_at − first requested_at) over permits first issued in "
               "period", 1),
        # ---- Phase 4 certification (4-third-party-cert §6.7) ----
        _pct(M.K72, "Equipment certificate compliance", "نسبة المعدات بشهادات سارية",
             "Equipment certified", "المعدات المعتمدة",
             "On Site non-scaffold deployments whose item has a valid certificate ÷ On Site "
             "non-scaffold deployments at as_of × 100; breakdown by category",
             numerator="With valid certificate", denominator="On Site items"),
        _count(M.K73, "Equipment certificates expiring ≤ 30 days",
               "شهادات معدات تنتهي خلال 30 يوماً", "Equipment certs expiring",
               "شهادات معدات تنتهي", G.leading, LOW,
               "n(On Site items with a valid certificate, valid_until ∈ [as_of, as_of + 30]) "
               "by category"),
        _count(M.K74, "Out-of-service equipment", "المعدات خارج الخدمة", "Out of service",
               "خارج الخدمة", G.leading, LOW,
               "n(On Site deployments whose item is Out of Service at as_of); component: "
               "category A defects raised in period"),
        _count(M.K75, "Inspections overdue", "الفحوص المتأخرة", "Inspections overdue",
               "الفحوص المتأخرة", G.leading, LOW,
               "equipment: On Site deployments whose latest line expired and no line in force; "
               "scaffolds: In Use with tag expired (components)"),
        _pct(M.K76, "Personnel certification compliance", "نسبة الأفراد بشهادات سارية",
             "Personnel certified", "الأفراد المعتمدون",
             "Mobilised deployments of mapped trades whose worker holds an in-force "
             "certificate of the mapped type ÷ those deployments × 100; breakdown by type",
             numerator="With in-force certificate", denominator="Mobilised (mapped trades)"),
        _count(M.K77, "Personnel certificates expiring ≤ 30 days",
               "شهادات أفراد تنتهي خلال 30 يوماً", "Personnel certs expiring",
               "شهادات أفراد تنتهي", G.leading, LOW,
               "n(in-force certificates of Mobilised workers, valid_until ∈ [as_of, as_of + "
               "30]) by type"),
        _count(M.K78, "Blacklisted / banned", "المحظورون", "Blacklisted / banned", "المحظورون",
               G.leading, NONE,
               "components at as_of: equipment Blacklisted with a deployment on the project · "
               "workers with an active certification ban and a deployment · TPIs Blacklisted"),
        _pct(M.K79, "Verification timeliness", "الالتزام بمهلة التحقق", "Verification on time",
             "التحقق في الموعد",
             "certificates submitted in period with a conclusive verification within "
             "verification_due_days ÷ eligible certificates submitted in period × 100; "
             "component: failed verifications",
             numerator="Verified in time", denominator="Submitted (eligible)"),
        _pct(M.K80, "Defect rectification on time", "إصلاح العيوب في الموعد",
             "Defects fixed on time", "إصلاح العيوب في الموعد",
             "B defects due in period (≤ as_of) Closed by due_date ÷ B defects due in period "
             "(≤ as_of, not Cancelled) × 100",
             numerator="Closed on time", denominator="B defects due"),
        _pct(M.K81, "Scaffold tag compliance", "امتثال بطاقات السقالات", "Scaffold tags valid",
             "بطاقات السقالات السارية",
             "In Use scaffolds with tag green or yellow ÷ In Use scaffolds (excl. Closed Red, "
             "Under Erection / Alteration) at as_of × 100",
             numerator="Green or yellow", denominator="In Use scaffolds"),
        # ---- Phase 5 training (5-training §6.8) ----
        _pct(M.K82, "Training matrix compliance", "نسبة الامتثال لمصفوفة التدريب",
             "Matrix compliance", "امتثال المصفوفة",
             "counted requirements at as_of met or expiring ÷ counted requirements at as_of × "
             "100; breakdown by course, trade, contractor",
             numerator="Met or expiring", denominator="Counted requirements"),
        _pct(M.K83, "Workers fully trained", "العمال المستوفون لكل متطلباتهم",
             "Fully trained", "مستوفون بالكامل",
             "Mobilised contractor_worker deployments with ≥ 1 counted requirement and no gap ÷ "
             "those with ≥ 1 counted requirement × 100",
             numerator="Without gap", denominator="Workers with requirements"),
        _count(M.K84, "Competency gaps", "الفجوات في الكفاءة", "Gaps", "الفجوات", G.leading,
               LOW,
               "at as_of: counted requirements in state gap; components: workers with ≥ 1 gap · "
               "gaps on hook codes"),
        _count(M.K85, "Training expiring ≤ 30 days", "تدريب ينتهي خلال 30 يوماً",
               "Training expiring", "تدريب ينتهي", G.leading, LOW,
               "distinct in-force records with valid_until ∈ [as_of, as_of + 30] satisfying a "
               "counted requirement of a Mobilised contractor_worker deployment; by course"),
        KpiDef(M.K86, "Training person-hours", "ساعات التدريب الفعلية", "Training hours",
               "ساعات التدريب", K.hours, G.leading, NONE, "h", "ساعة",
               "Σ register hours of the period's days ≥ training_register_from, by course "
               "category; components: voided-session hours · client/PMC staff hours", 2),
        _pct(M.K87, "Assessment pass rate", "نسبة النجاح في التقييم", "Pass rate",
             "نسبة النجاح",
             "passed ÷ (passed + failed) attendances in sessions Closed in the period × 100 "
             "(incomplete excluded)", better=NONE,
             numerator="Passed", denominator="Passed + failed"),
        _pct(M.K88, "Refreshers booked in time", "التجديدات المحجوزة في الوقت",
             "Booked in time", "محجوزة في الوقت",
             "K-85 records with plan state booked_in_time ÷ K-85 × 100; K-85 = 0 → '—'",
             numerator="Booked in time", denominator="Expiring ≤ 30 days"),
        # ---- Phase 6a occupational health (6a-occupational-health §6.6) ----
        _pct(M.K89, "Medical fitness compliance", "نسبة الامتثال للياقة الطبية",
             "Fitness compliance", "امتثال اللياقة",
             "counted requirements at as_of met or expiring ÷ counted requirements at as_of × "
             "100; breakdown by code, trade, contractor",
             numerator="Met or expiring", denominator="Counted requirements"),
        _pct(M.K90, "Workers medically cleared", "العمال المستوفون للياقة",
             "Medically cleared", "مستوفون للياقة",
             "Mobilised contractor_worker deployments with ≥ 1 counted requirement and no gap ÷ "
             "those with ≥ 1 counted requirement × 100",
             numerator="Without gap", denominator="Workers with requirements"),
        _count(M.K91, "Fitness gaps", "فجوات اللياقة", "Fitness gaps", "فجوات اللياقة",
               G.leading, LOW,
               "at as_of: counted requirements in gap; components: workers with ≥ 1 gap · gaps "
               "on hook codes"),
        _count(M.K92, "Fitness expiring ≤ 30 days", "شهادات لياقة تنتهي خلال 30 يوماً",
               "Fitness expiring", "لياقة تنتهي", G.leading, LOW,
               "distinct lines in force at as_of with valid_until ∈ [as_of, as_of + 30] "
               "satisfying a counted requirement"),
        _count(M.K93, "Active fitness holds", "حالات الإيقاف لأسباب اللياقة", "Active holds",
               "حالات الإيقاف", G.leading, LOW,
               "at as_of: Active holds of contractor_worker deployments; component: referral or "
               "manual holds past referral_assessment_hours (MK-3)"),
        _pct(M.K94, "Holds cleared before work", "حالات الإيقاف المرفوعة قبل العودة للعمل",
             "Cleared before work", "مرفوعة قبل العمل",
             "holds Released in period and compliant (no work during hold) ÷ holds Released in "
             "period × 100",
             numerator="Compliant", denominator="Released holds"),
        _pct(M.K95, "Referrals assessed on time", "الإحالات المقيمة في الموعد",
             "Referrals on time", "إحالات في الموعد",
             "counted referrals assessed by due_at ÷ counted referrals (raised in period, not "
             "cancelled, window closed) × 100",
             numerator="On time", denominator="Counted referrals"),
        _count(M.K96, "Workers on work restrictions", "عمال عليهم قيود عمل",
               "On restrictions", "عليهم قيود", G.leading, NONE,
               "at as_of: Mobilised contractor_worker deployments whose worker has ≥ 1 "
               "restriction in force with review_required (MK-3)"),
    ]
}  # fmt: skip

LAGGING_TILES = [
    M.K05, M.K06, M.K20, M.K10, M.K21, M.K22, M.K23, M.K09, M.K12, M.K24, M.K13, M.K25,
    M.K14, M.K15, M.K16, M.K44,
]  # fmt: skip
LEADING_TILES = [
    M.K30, M.K31, M.K32, M.K34, M.K35, M.K36, M.K37, M.K39, M.K41, M.K42, M.K27,
]  # fmt: skip
PTW_TILES = [M.K46, M.K61, M.K64, M.K66, M.K69]  # 3-ptw §8.1 item 1 (capability 103)
CERT_TILES = [M.K72, M.K76, M.K74, M.K80, M.K81]  # 4-third-party-cert §8.1 item 1 (cap 122)
TRAINING_TILES = [M.K82, M.K83, M.K84, M.K88]  # 5-training §8.1 item 1 (capability 143)
PLACEHOLDERS: list[KpiMetric] = []  # K-46 became a live tile in Phase 3
RATE_METRICS = frozenset(m for m, d in CATALOGUE.items() if d.kind == K.rate)
