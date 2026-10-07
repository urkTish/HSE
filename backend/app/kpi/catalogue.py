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
PHASE2_PENDING: frozenset[KpiMetric] = PHASE2_METRICS
"""Stage 1 (contract only): the access KPIs are listed but not computed yet."""


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
    d.metric: (replace(d, available=False) if d.metric in PHASE2_PENDING else d)
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
               "Σ training_hours ÷ K-03", 2, None, "Σ training hours", "Average headcount"),
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
        KpiDef(M.K46, "PTW audits", "تدقيق تصاريح العمل", "PTW audits", "تدقيق التصاريح",
               K.placeholder, G.leading, NONE, "", "", "Available from Phase 3",
               available=False),
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
    ]
}  # fmt: skip

LAGGING_TILES = [
    M.K05, M.K06, M.K20, M.K10, M.K21, M.K22, M.K23, M.K09, M.K12, M.K24, M.K13, M.K25,
    M.K14, M.K15, M.K16, M.K44,
]  # fmt: skip
LEADING_TILES = [
    M.K30, M.K31, M.K32, M.K34, M.K35, M.K36, M.K37, M.K39, M.K41, M.K42, M.K27,
]  # fmt: skip
PLACEHOLDERS = [M.K46]
RATE_METRICS = frozenset(m for m, d in CATALOGUE.items() if d.kind == K.rate)
