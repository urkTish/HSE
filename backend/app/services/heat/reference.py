"""Phase 6b reference lists with EN/AR labels (spec 6b-heat-stress §3.13)."""

from __future__ import annotations

from app.core.heat_enums import (
    BanExemptionReason,
    Clothing,
    Cooling,
    PatrolOutcome,
    PlanType,
    Regime,
    ReviewQuestion,
    StationType,
    WelfareItem,
    Workload,
)

WORKLOADS: dict[Workload, tuple[str, str, str]] = {
    Workload.light: ("Light", "خفيف", "< 180 W"),
    Workload.moderate: ("Moderate", "متوسط", "180–300 W"),
    Workload.heavy: ("Heavy", "شاق", "300–415 W"),
    Workload.very_heavy: ("Very heavy", "شاق جداً", "> 415 W"),
}
CLOTHING: dict[Clothing, tuple[str, str]] = {
    Clothing.work_clothes: ("Work clothes", "ملابس العمل"),
    Clothing.cloth_coveralls: ("Cloth coveralls", "أفرول قماش"),
    Clothing.double_layer_woven: ("Double-layer woven clothing", "طبقتان منسوجتان"),
    Clothing.sms_coveralls: ("SMS coveralls", "أفرول SMS"),
    Clothing.polyolefin_coveralls: ("Polyolefin coveralls", "أفرول بولي أوليفين"),
    Clothing.vapour_barrier_coveralls: ("Vapour-barrier coveralls", "أفرول عازل للبخار"),
}
REGIMES: dict[Regime, tuple[str, str]] = {
    Regime.R0: ("Continuous work with water", "عمل مستمر مع شرب الماء"),
    Regime.R1: ("45 min work / 15 min rest", "45 عمل / 15 راحة"),
    Regime.R2: ("30 min work / 30 min rest", "30 عمل / 30 راحة"),
    Regime.R3: ("15 min work / 45 min rest", "15 عمل / 45 راحة"),
    Regime.R4: ("Stop outdoor work", "إيقاف العمل الخارجي"),
    Regime.unknown: ("No reading", "لا توجد قراءة"),
}
PLAN_TYPES: dict[PlanType, tuple[str, str]] = {
    PlanType.new_worker: ("New worker", "عامل جديد"),
    PlanType.returner: ("Returner after absence", "عائد بعد غياب"),
    PlanType.post_heat_illness: ("After heat illness", "بعد إجهاد حراري"),
    PlanType.period_start: ("Start of controls period", "بداية فترة الضوابط"),
}
CRITICAL = {WelfareItem.HW01, WelfareItem.HW05, WelfareItem.HW08, WelfareItem.HW10}
NA_ALLOWED = {WelfareItem.HW02, WelfareItem.HW06, WelfareItem.HW10}
WELFARE: dict[WelfareItem, tuple[str, str]] = {
    WelfareItem.HW01: ("Cool drinking water available at or near the station",
                       "مياه شرب باردة متوفرة عند المحطة أو بقربها"),
    WelfareItem.HW02: ("Water temperature within the limit", "حرارة الماء ضمن الحد"),
    WelfareItem.HW03: ("Cups or bottles and refill available",
                       "أكواب أو عبوات وإعادة تعبئة متوفرة"),
    WelfareItem.HW04: ("Electrolyte / ORS sachets available", "أملاح الإماهة متوفرة"),
    WelfareItem.HW05: ("Shade adequate for the persons present", "ظل كافٍ للحاضرين"),
    WelfareItem.HW06: ("Cooling working", "التبريد يعمل"),
    WelfareItem.HW07: ("Seating available", "مقاعد متوفرة"),
    WelfareItem.HW08: ("Heat first-aid kit and emergency number posted",
                       "حقيبة إسعاف حراري ورقم الطوارئ معلق"),
    WelfareItem.HW09: ("Current regime posted", "نظام العمل الحالي معلق"),
    WelfareItem.HW10: ("Workers observed following the rest regime",
                       "العمال يلتزمون بنظام الراحة"),
}  # fmt: skip
OUTCOMES: dict[PatrolOutcome, tuple[str, str]] = {
    PatrolOutcome.no_outdoor_work: ("No outdoor work", "لا يوجد عمل خارجي"),
    PatrolOutcome.compliant_shaded_or_indoor: ("Work in shade or indoors",
                                               "العمل في الظل أو داخل المبنى"),
    PatrolOutcome.exempt_work: ("Exempt work", "عمل مستثنى"),
    PatrolOutcome.violation: ("Violation", "مخالفة"),
}  # fmt: skip
QUESTIONS: dict[ReviewQuestion, tuple[str, str]] = {
    ReviewQuestion.HC1: ("Water available at the workface", "الماء متوفر في موقع العمل"),
    ReviewQuestion.HC2: ("Shade / rest station within reach", "الظل أو محطة الراحة قريبة"),
    ReviewQuestion.HC3: ("Regime in force was followed", "تم اتباع نظام العمل المعمول به"),
    ReviewQuestion.HC4: ("Acclimatisation plan followed", "تم اتباع خطة التأقلم"),
    ReviewQuestion.HC5: ("Buddy / supervisor checks done", "تمت متابعة الزميل أو المشرف"),
    ReviewQuestion.HC6: ("Clothing and PPE appropriate to the regime",
                         "الملابس ومعدات الوقاية مناسبة"),
}  # fmt: skip
STATION_TYPES: dict[StationType, tuple[str, str]] = {
    StationType.cooled_cabin: ("Cooled cabin", "كابينة مكيفة"),
    StationType.shaded_shelter: ("Shaded shelter", "مظلة"),
    StationType.mobile_shade_unit: ("Mobile shade unit", "وحدة تظليل متنقلة"),
    StationType.indoor_rest_area: ("Indoor rest area", "استراحة داخلية"),
}
COOLING: dict[Cooling, tuple[str, str]] = {
    Cooling.none: ("None", "لا يوجد"),
    Cooling.fans: ("Fans", "مراوح"),
    Cooling.misting: ("Misting", "رذاذ"),
    Cooling.air_conditioning: ("Air conditioning", "تكييف"),
}
EXEMPTION_REASONS: dict[BanExemptionReason, tuple[str, str]] = {
    BanExemptionReason.emergency_repair: ("Emergency repair", "إصلاح طارئ"),
    BanExemptionReason.exempt_activity_mhrsd: ("Exempt activity (MHRSD)", "نشاط مستثنى"),
    BanExemptionReason.shaded_and_cooled_workplace: (
        "Shaded and cooled workplace", "موقع عمل مظلل ومبرد",
    ),
}  # fmt: skip
