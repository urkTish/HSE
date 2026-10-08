"""Phase 6a reference data (spec 6a-occupational-health §3.10, §3.12, HK6-2, P6-7): the seeded
fitness code catalogue, restriction codes with their `negates` / review flags, EN/AR labels,
the default attach points and the tier-1 texts."""

from __future__ import annotations

from app.core.med_enums import (
    AssessmentType,
    ExaminerClass,
    ExposureGroup,
    FitnessCategory,
    FitnessOutcome,
    HoldReason,
    MedicalProviderKind,
    ReferralReason,
    RestrictionCode,
    TypicalTest,
)

R = RestrictionCode
OP = ExaminerClass.occupational_physician.value
PH = ExaminerClass.physician.value
SITE = MedicalProviderKind.site_clinic.value
EXT = MedicalProviderKind.external_clinic.value
CON = MedicalProviderKind.contractor_clinic.value

# code, en, ar, category, validity months, examiner classes, provider kinds, typical tests
CATALOGUE: list[tuple[str, str, str, FitnessCategory, int, list[str], list[str], list[str]]] = [
    ("GEN-FIT", "General fitness for construction work", "اللياقة العامة لأعمال البناء",
     FitnessCategory.general, 24, [OP, PH], [SITE, EXT, CON],
     ["history_questionnaire", "vision_acuity", "blood_pressure", "musculoskeletal_exam"]),
    ("WAH-FIT", "Working at height fitness", "اللياقة للعمل على ارتفاعات",
     FitnessCategory.task, 12, [OP, PH], [SITE, EXT],
     ["balance_vertigo_screen", "vision_acuity", "cardio_exam"]),
    ("CSE-ENTRY-FIT", "Confined space entry fitness", "اللياقة لدخول الأماكن المحصورة",
     FitnessCategory.task, 12, [OP, PH], [SITE, EXT],
     ["spirometry", "cardio_exam", "claustrophobia_screen"]),
    ("CRANE-OPERATOR-FIT", "Crane operator physical qualification",
     "اللياقة البدنية لمشغل الرافعة", FitnessCategory.task, 12, [OP, PH], [SITE, EXT],
     ["vision_acuity", "colour_vision", "depth_perception", "audiometry"]),
    ("PLANT-OPERATOR-FIT", "Mobile plant / MEWP / hoist operator fitness",
     "لياقة مشغلي المعدات المتحركة", FitnessCategory.task, 24, [OP, PH], [SITE, EXT],
     ["vision_acuity", "depth_perception", "audiometry"]),
    ("DRIVER-FIT", "Driver fitness (heavy and airside vehicles)", "لياقة السائقين",
     FitnessCategory.task, 24, [OP, PH], [SITE, EXT],
     ["vision_acuity", "colour_vision", "audiometry"]),
    ("RESPIRATOR-FIT", "Respirator user medical evaluation",
     "التقييم الطبي لمستخدم جهاز التنفس", FitnessCategory.task, 12, [OP, PH], [SITE, EXT],
     ["respirator_questionnaire", "spirometry"]),
    ("HEAT-EXPOSURE-FIT", "Fitness for work in hot environments",
     "اللياقة للعمل في البيئات الحارة", FitnessCategory.task, 12, [OP, PH], [SITE, EXT],
     ["cardio_exam", "blood_pressure"]),
    ("NOISE-SURV", "Hearing conservation audiometry",
     "فحص السمع ضمن برنامج المحافظة على السمع", FitnessCategory.surveillance, 12, [OP, PH],
     [SITE, EXT], ["audiometry"]),
    ("SILICA-SURV", "Respirable silica health surveillance",
     "المراقبة الصحية للتعرض للسيليكا", FitnessCategory.surveillance, 36, [OP, PH],
     [SITE, EXT], ["spirometry", "chest_xray"]),
    ("RAD-WORKER-FIT", "Radiation worker health surveillance",
     "المراقبة الصحية للعاملين في الإشعاع", FitnessCategory.surveillance, 12, [OP], [SITE, EXT],
     ["blood_count"]),
]  # fmt: skip
CODES = [c[0] for c in CATALOGUE]
GEN = "GEN-FIT"
DEFAULT_CRITICAL = ["CSE-ENTRY-FIT", "CRANE-OPERATOR-FIT", "RESPIRATOR-FIT", "RAD-WORKER-FIT"]

# restriction code → (en, ar, value kind, negates, review_required)
RESTRICTIONS: dict[RestrictionCode, tuple[str, str, str | None, tuple[str, ...], bool]] = {
    R.no_work_at_height: ("No work at height", "لا عمل على ارتفاعات", None, ("WAH-FIT",), True),
    R.no_confined_space: (
        "No confined-space entry", "لا دخول للأماكن المحصورة", None, ("CSE-ENTRY-FIT",), True,
    ),
    R.no_driving: ("No driving", "لا قيادة", None, ("DRIVER-FIT",), True),
    R.no_plant_operation: (
        "No operation of cranes or mobile plant", "لا تشغيل للرافعات أو المعدات", None,
        ("CRANE-OPERATOR-FIT", "PLANT-OPERATOR-FIT"), True,
    ),
    R.no_respirator_use: (
        "No tight-fitting respirator", "لا استخدام لأجهزة التنفس المحكمة", None,
        ("RESPIRATOR-FIT",), True,
    ),
    R.no_heat_exposure: (
        "No outdoor work in direct sun or hot spaces",
        "لا عمل في الشمس المباشرة أو الأماكن الحارة", None, ("HEAT-EXPOSURE-FIT",), True,
    ),
    R.no_noise_exposure: (
        "No work in noise ≥ 85 dBA", "لا عمل في ضوضاء ≥ 85 ديسيبل", None, ("NOISE-SURV",), True,
    ),
    R.no_radiation_work: ("No radiation work", "لا عمل إشعاعي", None, ("RAD-WORKER-FIT",), True),
    R.lifting_limit_kg: ("Manual lifting limit", "حد للرفع اليدوي", "int_kg", (), True),
    R.no_night_work: ("No night work", "لا عمل ليلي", None, (), True),
    R.no_lone_work: ("No lone work", "لا عمل منفرد", None, (), True),
    R.light_duties_only: ("Light duties only", "أعمال خفيفة فقط", None, (), True),
    R.requires_corrective_lenses: (
        "Must wear corrective lenses", "يجب ارتداء النظارات الطبية", None, (), False,
    ),
    R.other_functional: ("Other functional limit", "قيد وظيفي آخر", "text", (), True),
}  # fmt: skip

EXPOSURE_LABELS: dict[ExposureGroup, tuple[str, str]] = {
    ExposureGroup.noise_85: ("Noise ≥ 85 dBA (8-h TWA)", "ضوضاء ≥ 85 ديسيبل"),
    ExposureGroup.silica_rcs: (
        "Respirable crystalline silica", "غبار السيليكا البلورية القابلة للاستنشاق",
    ),
    ExposureGroup.ionising_radiation: ("Ionising radiation", "إشعاع مؤين"),
    ExposureGroup.heat_outdoor: ("Outdoor work in heat", "عمل خارجي في الحرارة"),
}  # fmt: skip
# exposure group → the surveillance code its plan line requires (WP-2)
SURVEILLANCE_OF: dict[str, str] = {
    "noise_85": "NOISE-SURV",
    "silica_rcs": "SILICA-SURV",
    "ionising_radiation": "RAD-WORKER-FIT",
}
OUTCOME_LABELS: dict[FitnessOutcome, tuple[str, str]] = {
    FitnessOutcome.fit: ("Fit", "لائق"),
    FitnessOutcome.fit_with_restrictions: ("Fit with restrictions", "لائق مع قيود"),
    FitnessOutcome.temporarily_unfit: ("Temporarily unfit", "غير لائق مؤقتاً"),
    FitnessOutcome.permanently_unfit: ("Permanently unfit", "غير لائق نهائياً"),
}
TYPE_LABELS: dict[AssessmentType, tuple[str, str]] = {
    AssessmentType.pre_placement: ("Pre-placement", "قبل التعيين"),
    AssessmentType.periodic: ("Periodic", "دوري"),
    AssessmentType.return_to_work: ("Return to work", "العودة للعمل"),
    AssessmentType.referral: ("Referral", "بناءً على إحالة"),
    AssessmentType.change_of_task: ("Change of task", "تغيير المهمة"),
    AssessmentType.post_exposure: ("Post exposure", "بعد التعرض"),
    AssessmentType.exit: ("Exit", "عند انتهاء الخدمة"),
}
EXAMINER_LABELS: dict[ExaminerClass, tuple[str, str]] = {
    ExaminerClass.occupational_physician: ("Occupational physician", "طبيب صحة مهنية"),
    ExaminerClass.physician: ("Physician", "طبيب مرخص"),
    ExaminerClass.nurse: ("Nurse", "ممرض/ممرضة"),
}
CATEGORY_LABELS: dict[FitnessCategory, tuple[str, str]] = {
    FitnessCategory.general: ("General", "عامة"),
    FitnessCategory.task: ("Task", "مهمة محددة"),
    FitnessCategory.surveillance: ("Surveillance", "مراقبة صحية للتعرض"),
}
HOLD_LABELS: dict[HoldReason, tuple[str, str]] = {
    HoldReason.rtw_after_injury: ("Return after injury", "عودة بعد إصابة"),
    HoldReason.heat_illness: ("Heat illness", "إجهاد حراري"),
    HoldReason.referral: ("Referral with removal from work", "إحالة مع إبعاد عن العمل"),
    HoldReason.manual: ("Manual hold for fitness concern", "إيقاف يدوي لمخاوف اللياقة"),
}
REFERRAL_LABELS: dict[ReferralReason, tuple[str, str]] = {
    ReferralReason.observed_unwell: ("Observed unwell", "ظهرت عليه أعراض مرضية"),
    ReferralReason.heat_illness_episode: ("Heat illness episode", "نوبة إجهاد حراري"),
    ReferralReason.self_reported: ("Self-reported", "بلاغ ذاتي من العامل"),
    ReferralReason.return_after_absence: ("Return after absence", "عودة بعد غياب"),
    ReferralReason.post_incident_no_injury: (
        "After an incident without recorded injury", "بعد حادث دون إصابة مسجلة",
    ),
    ReferralReason.certificate_restriction: (
        "Medical restriction on a competency card", "قيد طبي مذكور في بطاقة كفاءة",
    ),
    ReferralReason.supervisor_concern: ("Supervisor concern", "ملاحظة المشرف"),
    ReferralReason.other: ("Other", "أخرى"),
}  # fmt: skip
TEST_LABELS: dict[TypicalTest, tuple[str, str]] = {
    t: (t.value.replace("_", " ").capitalize(), t.value.replace("_", " ")) for t in TypicalTest
}
HINTS: list[tuple[str, str, str]] = [
    ("functional_only", "Functional limit only — no diagnosis", "قيد وظيفي فقط — دون تشخيص"),
    ("referral_note", "Describe what you saw, not a diagnosis", "صف ما شاهدته وليس تشخيصاً"),
    (
        "no_diagnosis_form",
        "No diagnosis or test results on this form",
        "لا يذكر التشخيص أو نتائج الفحوص في هذا النموذج",
    ),
    (
        "prohibited_data",
        "Do not record diagnoses, symptoms, test values, medication or other clinical data",
        "لا تسجل التشخيص أو الأعراض أو نتائج الفحوص أو الأدوية أو أي بيانات سريرية",
    ),
]

# ---- tier-1 texts (P6-7, HK6-7) ------------------------------------------------------------------
NOT_ELIGIBLE = ("Not eligible — HSE check", "غير مؤهل — مراجعة السلامة")
CHECK_DUE = ("HSE check due", "مراجعة السلامة مستحقة")
RESTRICTION_APPLIES = (
    "Work restriction applies — ask your supervisor",
    "يوجد قيد على العمل — راجع المشرف",
)
CLEARED = ("Cleared", "مستوفى")
REQ_NOT_MET = ("Fitness requirement not met", "متطلب اللياقة غير مستوفى")
CERT_DUE = ("Fitness certificate due", "شهادة اللياقة مستحقة")
REVIEW_DUE = ("Fitness review due", "مراجعة اللياقة مستحقة")
REMOVED = (
    "Worker removed from work pending HSE check",
    "تم إبعاد العامل عن العمل لحين مراجعة السلامة",
)

# ---- default attach points (HK6-2) ---------------------------------------------------------------
PROJECT_HOOK_CODES = ["GEN-FIT"]
ZONE_HOOKS = {"Z-TC01": [("crane_operator", "CRANE-OPERATOR-FIT")]}
ADP_HOOKS = {"apron": "DRIVER-FIT", "manoeuvring": "DRIVER-FIT"}
CRANE_CATEGORIES = (
    "tower_crane", "mobile_crane", "crawler_crane", "loader_crane", "overhead_gantry_crane",
)  # fmt: skip
PLANT_CATEGORIES = (
    "construction_hoist", "mast_climber", "bmu", "mewp", "forklift", "telehandler", "excavator",
    "wheel_loader", "piling_rig", "concrete_pump_boom",
)  # fmt: skip

ALERT_SCHEDULE_LONG = [30, 14, 7, 0]
RTW_CATEGORIES = ["LTI", "RWC", "JTC"]
HEAT_NATURES = ["heat_exhaustion", "heat_stroke"]
EG_TRADE_DEFAULTS: dict[str, list[str]] = {
    "noise_85": ["plant_operator", "welder"],
    "silica_rcs": ["mason"],
    "ionising_radiation": [],
    "heat_outdoor": [],
}
UNFIT = (FitnessOutcome.temporarily_unfit, FitnessOutcome.permanently_unfit)
FIT = (FitnessOutcome.fit, FitnessOutcome.fit_with_restrictions)


def negates(code: RestrictionCode | str) -> tuple[str, ...]:
    return RESTRICTIONS[RestrictionCode(code)][3]


def review_required(code: RestrictionCode | str) -> bool:
    return RESTRICTIONS[RestrictionCode(code)][4]
