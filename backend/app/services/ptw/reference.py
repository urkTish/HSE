# ruff: noqa: E501
"""Static reference data of spec 3-ptw: §3.1 permit-type rows, lists C / X / A / B / SR,
HK3-2 hook requirements, SM-3 default SIMOPS matrix, §6.1 risk bands and §6.2 gas limits."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.core.access_enums import HookKind
from app.core.ptw_enums import (
    AppointmentFunction,
    AuditFindingSeverity,
    ClosureItem,
    DocumentType,
    EquipmentCategory,
    Hazard,
    PermitBlocker,
    PermitType,
    PermitWarningCode,
    PreIssueItem,
    PtwCrewRole,
    RevalidationRule,
    RiskBand,
    SimopsCondition,
    SimopsResult,
    SimopsTypeSelector,
    StatusReason,
)

T = PermitType
R = PtwCrewRole
D = DocumentType
H = Hazard
P = PreIssueItem
X = ClosureItem
HK = HookKind
B = PermitBlocker
W = PermitWarningCode
SEV = AuditFindingSeverity

ALL_TYPES: tuple[PermitType, ...] = tuple(PermitType)


@dataclass(frozen=True)
class TypeInfo:
    label_en: str
    label_ar: str
    max_days: int
    revalidation: RevalidationRule
    gas_en: str
    gas_ar: str
    hse_en: str
    hse_ar: str
    roles: tuple[PtwCrewRole, ...]
    documents: tuple[DocumentType, ...]
    pre_issue: tuple[PreIssueItem, ...]
    closure: tuple[ClosureItem, ...]
    hazards: tuple[Hazard, ...]
    crew_hooks: dict[PtwCrewRole, tuple[tuple[HookKind, str], ...]] = field(default_factory=dict)


GAS_HOOKS = ((HK.personnel_certificate, "GAS-TESTER"), (HK.training_course, "GAS-TEST"))
BASE_X = (X.X_01, X.X_02, X.X_03)

TYPES: dict[PermitType, TypeInfo] = {
    T.general: TypeInfo(
        "General / cold work", "أعمال عامة (باردة)", 7, RevalidationRule.each_shift,
        "If a zone is a gas-test zone and flammables are in use",
        "إذا كانت المنطقة تتطلب فحص غاز مع استخدام مواد قابلة للاشتعال",
        "Not required", "غير مطلوبة",
        (R.supervisor,), (D.method_statement,), (P.GW_01, P.GW_02, P.GW_03), BASE_X, (),
        {R.gas_tester: GAS_HOOKS},
    ),
    T.hot_work: TypeInfo(
        "Hot work", "أعمال ساخنة", 1, RevalidationRule.one_handover,
        "If a zone is a gas-test zone or hazardous area, or inside a confined space",
        "إذا كانت المنطقة تتطلب فحص غاز أو مصنفة خطرة أو داخل مكان محصور",
        "If gas-test zone, hazardous area, fire-system impairment or airside",
        "عند منطقة فحص غاز أو منطقة خطرة أو تعطيل نظام الحريق أو الجانب الجوي",
        (R.fire_watch, R.hot_work_operative), (D.method_statement,),
        (P.HW_01, P.HW_02, P.HW_03, P.HW_04, P.HW_05, P.HW_06, P.HW_07),
        (*BASE_X, X.X_06), (H.fire_explosion, H.hot_surfaces_burns),
        {R.fire_watch: ((HK.training_course, "FIRE-WATCH"),), R.gas_tester: GAS_HOOKS},
    ),
    T.confined_space: TypeInfo(
        "Confined space entry", "دخول الأماكن المحصورة", 1, RevalidationRule.one_handover,
        "Always (pre-entry, continuous and recorded)", "دائماً (قبل الدخول ومستمر ومسجل)",
        "Always", "دائماً",
        (R.standby_person, R.gas_tester, R.entrant), (D.rescue_plan, D.method_statement),
        (P.CS_01, P.CS_02, P.CS_03, P.CS_04, P.CS_05), (*BASE_X, X.X_07, X.X_08),
        (H.toxic_atmosphere, H.oxygen_deficiency),
        {
            R.entrant: ((HK.training_course, "CSE-ENTRANT"), (HK.medical_fitness, "CSE-ENTRY-FIT")),
            R.standby_person: ((HK.training_course, "CSE-ATTENDANT"),),
            R.rescue_lead: ((HK.training_course, "CSE-RESCUE"),),
            R.rescue_member: ((HK.training_course, "CSE-RESCUE"),),
            R.gas_tester: GAS_HOOKS,
        },
    ),
    T.work_at_height: TypeInfo(
        "Working at height", "العمل على ارتفاع", 7, RevalidationRule.each_shift,
        "Not required", "غير مطلوب",
        "If fall arrest, rope access or suspended access", "عند استخدام إيقاف السقوط أو الحبال أو المنصات المعلقة",
        (R.supervisor,), (D.method_statement,), (P.WH_01, P.WH_02, P.WH_03, P.WH_04),
        (*BASE_X, X.X_08), (H.fall_from_height, H.falling_objects),
    ),
    T.excavation: TypeInfo(
        "Excavation", "الحفر", 7, RevalidationRule.each_shift,
        "If depth ≥ 1.2 m and gas-test zone or atmosphere hazard",
        "إذا كان العمق ≥ 1.2 م مع منطقة فحص غاز أو احتمال جو خطر",
        "If depth ≥ 1.2 m", "إذا كان العمق ≥ 1.2 م",
        (R.competent_person,), (D.excavation_plan,), (P.EX_01, P.EX_02, P.EX_03, P.EX_04, P.EX_05),
        (*BASE_X, X.X_09), (H.excavation_collapse, H.buried_services),
        {R.gas_tester: GAS_HOOKS},
    ),
    T.electrical_isolation: TypeInfo(
        "Electrical work / isolation (LOTO)", "الأعمال الكهربائية والعزل", 7,
        RevalidationRule.each_shift, "Not required", "غير مطلوب",
        "If HV or energized work", "عند الجهد العالي أو العمل المكهرب",
        (), (), (P.EL_01, P.EL_02, P.EL_03, P.EL_04), (*BASE_X, X.X_04, X.X_05),
        (H.electric_shock,),
        {R.electrician: ((HK.training_course, "LOTO"), (HK.training_course, "ELEC-QUALIFIED"))},
    ),
    T.lifting: TypeInfo(
        "Lifting operations", "عمليات الرفع", 7, RevalidationRule.each_shift,
        "Not required", "غير مطلوب", "If critical", "عند الرفع الحرج",
        (R.crane_operator, R.lift_supervisor), (D.lift_plan,),
        (P.LF_01, P.LF_02, P.LF_03, P.LF_04, P.LF_05, P.LF_06), (*BASE_X, X.X_10),
        (H.struck_by_load, H.crane_overturn),
        {
            R.crane_operator: ((HK.personnel_certificate, "CRANE-OPERATOR"),),
            R.rigger: ((HK.personnel_certificate, "RIGGER"),),
            R.signaller: ((HK.personnel_certificate, "SIGNALLER"),),
        },
    ),
    T.radiography: TypeInfo(
        "Industrial radiography", "التصوير الإشعاعي الصناعي", 1, RevalidationRule.none,
        "Not required", "غير مطلوب", "Always", "دائماً",
        (R.radiographer,), (D.nrrc_licence, D.radiation_protection_plan),
        (P.RG_01, P.RG_02, P.RG_03), (*BASE_X, X.X_11), (H.ionising_radiation,),
        {R.radiographer: ((HK.personnel_certificate, "RADIOGRAPHER"),)},
    ),
    T.airside_works: TypeInfo(
        "Airside works", "أعمال الجانب الجوي", 7, RevalidationRule.each_shift,
        "Not required (hot work near hydrants: AW-6)", "غير مطلوب (العمل الساخن قرب فتحات الوقود: AW-6)",
        "If any zone is in the movement area", "إذا كانت أي منطقة ضمن منطقة الحركة",
        (R.supervisor,), (), (P.AW_01, P.AW_02, P.AW_03, P.AW_04, P.AW_05), (*BASE_X, X.X_12),
        (H.fod, H.moving_plant),
    ),
}  # fmt: skip

EQUIPMENT_HOOKS: dict[EquipmentCategory, tuple[tuple[HookKind, str], ...]] = {
    EquipmentCategory.tower_crane: ((HK.equipment_certificate, "CRANE-TPI"),),
    EquipmentCategory.mobile_crane: ((HK.equipment_certificate, "CRANE-TPI"),),
    EquipmentCategory.crawler_crane: ((HK.equipment_certificate, "CRANE-TPI"),),
    EquipmentCategory.lifting_accessory: ((HK.equipment_certificate, "LIFTING-ACCESSORY-TPI"),),
    EquipmentCategory.spreader_beam: ((HK.equipment_certificate, "LIFTING-ACCESSORY-TPI"),),
    EquipmentCategory.man_basket: ((HK.equipment_certificate, "MAN-BASKET-TPI"),),
    EquipmentCategory.mewp: ((HK.equipment_certificate, "MEWP-TPI"),),
    EquipmentCategory.scaffold: ((HK.equipment_certificate, "SCAFFOLD-TAG"),),
}
CRANE_CATEGORIES = frozenset(
    {EquipmentCategory.tower_crane, EquipmentCategory.mobile_crane, EquipmentCategory.crawler_crane}
)
WAH_ARREST_HOOK = (HK.training_course, "WAH")
RESCUE_FIRST_AID_HOOK = (HK.training_course, "FIRST-AID")  # 3-ptw v1.2 §11.4
APPOINTMENT_HOOKS: dict[AppointmentFunction, tuple[tuple[HookKind, str], ...]] = {
    AppointmentFunction.issuer: ((HK.training_course, "PTW-ISSUER"),),
    AppointmentFunction.isolation_authority: ((HK.training_course, "LOTO-AUTHORITY"),),
}
RECEIVER_HOOK = (HK.training_course, "PTW-RECEIVER")

# Roles that need a matching appointment (PR-4) → (function, disciplines)
ROLE_APPOINTMENT: dict[PtwCrewRole, tuple[AppointmentFunction, tuple[str, ...]]] = {
    R.gas_tester: (AppointmentFunction.gas_tester, ()),
    R.competent_person: (
        AppointmentFunction.authorised_person,
        ("excavation_competent_person", "fall_protection_competent_person"),
    ),
    R.rpo: (AppointmentFunction.authorised_person, ("radiation_protection_officer",)),
    R.lift_supervisor: (AppointmentFunction.authorised_person, ("lift_supervisor",)),
}
# PR-10 "one key role at a time" (supervisor handled separately: up to 3 permits)
BUSY_ROLES = frozenset(
    {
        R.fire_watch, R.standby_person, R.entrant, R.crane_operator, R.signaller,
        R.radiographer, R.lift_supervisor,
    }
)  # fmt: skip
SUPERVISOR_MAX_PERMITS = 3

# ---- list C (pre-issue) -------------------------------------------------------------------------

PRE_ISSUE: dict[PreIssueItem, tuple[str, str, bool]] = {
    P.GW_01: ("Area inspected by issuer and receiver", "تم فحص الموقع من المُصدِر والمستلم", False),
    P.GW_02: ("Barricades / signage in place", "الحواجز واللوحات التحذيرية في مكانها", False),
    P.GW_03: ("PPE specified", "تم تحديد معدات الوقاية الشخصية", False),
    P.HW_01: ("Combustibles cleared ≥ 11 m or protected", "إزالة المواد القابلة للاشتعال ≥ 11 م أو حمايتها", False),
    P.HW_02: ("Extinguishers ≤ 9 m and fire blanket", "طفايات حريق ≤ 9 م وبطانية حريق", False),
    P.HW_03: ("Fire watch briefed and equipped", "مراقب الحريق مُوعّى ومجهز", False),
    P.HW_04: ("Openings / drains below covered", "تغطية الفتحات والمصارف السفلية", True),
    P.HW_05: ("Cylinders upright, secured, flashback arrestors both ends", "الأسطوانات قائمة ومثبتة مع مانع ارتداد في الطرفين", True),
    P.HW_06: ("Welding return lead at the work piece", "سلك الرجوع للحام عند قطعة العمل", False),
    P.HW_07: ("Fire system status checked / impairment approved", "تم التحقق من نظام الحريق أو اعتماد التعطيل", False),
    P.CS_01: ("Space isolated & blinded where required", "عزل المكان وتركيب السدادات عند الحاجة", True),
    P.CS_02: ("Ventilation running", "التهوية تعمل", False),
    P.CS_03: ("Standby person at entry, entrant log ready", "الشخص المناوب عند المدخل وسجل الدخول جاهز", False),
    P.CS_04: ("Rescue equipment rigged and tested", "معدات الإنقاذ مركبة ومختبرة", False),
    P.CS_05: ("Communication tested", "تم اختبار وسيلة الاتصال", False),
    P.WH_01: ("Access equipment inspected / tagged", "معدات الوصول مفحوصة وموسومة", False),
    P.WH_02: ("Edge protection / nets in place or anchor certified", "حماية الحواف أو الشبكات أو نقطة تثبيت معتمدة", False),
    P.WH_03: ("Drop zone barricaded", "تسييج منطقة سقوط الأجسام", False),
    P.WH_04: ("Rescue kit at level", "معدات الإنقاذ في نفس المستوى", True),
    P.EX_01: ("Utility clearance on site, services marked", "تصريح الخدمات في الموقع والخدمات معلمة", False),
    P.EX_02: ("Protective system installed", "نظام الحماية مركب", False),
    P.EX_03: ("Spoil ≥ 0.6 m, edge barriers", "الأتربة ≥ 0.6 م وحواجز الحافة", False),
    P.EX_04: ("Egress ladder within 7.5 m", "سلم خروج ضمن 7.5 م", False),
    P.EX_05: ("Competent-person inspection done today", "تم فحص الشخص الكفء اليوم", False),
    P.EL_01: ("Isolation certificate verified", "شهادة العزل متحقق منها", False),
    P.EL_02: ("Test for dead (live-dead-live) done", "تم التحقق من انعدام الجهد", False),
    P.EL_03: ("Earths applied (HV)", "تطبيق التأريض (جهد عالٍ)", True),
    P.EL_04: ("Personal locks applied by all crew", "الأقفال الشخصية مطبقة من جميع الطاقم", False),
    P.LF_01: ("Lift plan briefed", "تمت التوعية بخطة الرفع", False),
    P.LF_02: ("Exclusion zone barricaded", "تسييج منطقة الحظر", False),
    P.LF_03: ("Gear tags checked", "فحص بطاقات أدوات الرفع", False),
    P.LF_04: ("Ground / outrigger mats checked", "فحص التربة وقواعد الأرجل", True),
    P.LF_05: ("Wind within limit", "الرياح ضمن الحد", False),
    P.LF_06: ("Obstacle-clearance conditions applied", "تطبيق شروط موافقة العائق", True),
    P.RG_01: ("Barrier at planned distance, warning lights / signs", "الحاجز على المسافة المخططة مع إنارة وإشارات تحذير", False),
    P.RG_02: ("Area cleared and radio announced", "إخلاء المنطقة والإعلان باللاسلكي", False),
    P.RG_03: ("Survey meter checked", "فحص جهاز قياس الإشعاع", False),
    P.AW_01: ("WAP Active and crew on WAP", "تصريح دخول المنطقة ساري والطاقم مدرج", False),
    P.AW_02: ("FOD controls in place", "ضوابط الأجسام الغريبة مطبقة", False),
    P.AW_03: ("Vehicle beacons / AVP checked", "فحص الإنارة الدوارة وتصاريح المركبات", False),
    P.AW_04: ("Escort arrangements", "ترتيبات المرافقة", False),
    P.AW_05: ("ATC / AOCC contact confirmed", "تأكيد الاتصال مع البرج أو مركز العمليات", True),
}  # fmt: skip

PRE_ISSUE_TYPE: dict[PreIssueItem, PermitType | None] = {
    c: (None if c.value.startswith("GW") else next(
        t for t, i in TYPES.items() if c in i.pre_issue
    ))
    for c in PreIssueItem
}  # fmt: skip

CLOSURE: dict[ClosureItem, tuple[str, str]] = {
    X.X_01: ("Work complete / stopped and made safe", "اكتمل العمل أو أوقف وتم تأمينه"),
    X.X_02: ("Tools, materials, waste removed", "إزالة الأدوات والمواد والمخلفات"),
    X.X_03: ("Barricades removed or left with reason", "إزالة الحواجز أو إبقاؤها مع ذكر السبب"),
    X.X_04: ("Personal locks removed", "إزالة الأقفال الشخصية"),
    X.X_05: ("Isolations retained or de-isolation requested", "إبقاء العزل أو طلب إعادة التشغيل"),
    X.X_06: ("Fire watch completed", "اكتمال مراقبة الحريق"),
    X.X_07: ("All entrants out — log reconciled", "خروج جميع الداخلين ومطابقة السجل"),
    X.X_08: ("Covers / edge protection reinstated", "إعادة الأغطية وحماية الحواف"),
    X.X_09: ("Excavation backfilled or barricaded and lit", "ردم الحفرية أو تسييجها وإنارتها"),
    X.X_10: ("Load landed, crane made safe", "إنزال الحمولة وتأمين الرافعة"),
    X.X_11: ("Source returned and verified", "إعادة المصدر والتحقق منه"),
    X.X_12: (
        "FOD check clear and area handed back",
        "فحص الأجسام الغريبة سليم وتسليم المنطقة للعمليات",
    ),
}
CLOSURE_TYPE: dict[ClosureItem, PermitType | None] = {
    X.X_01: None, X.X_02: None, X.X_03: None, X.X_04: T.electrical_isolation,
    X.X_05: T.electrical_isolation, X.X_06: T.hot_work, X.X_07: T.confined_space,
    X.X_08: T.confined_space, X.X_09: T.excavation, X.X_10: T.lifting, X.X_11: T.radiography,
    X.X_12: T.airside_works,
}  # fmt: skip

# ---- list A (audit items) -----------------------------------------------------------------------

AUDIT_ITEMS: dict[str, tuple[str, str, AuditFindingSeverity]] = {
    "A00": ("Work requiring a permit done without one", "عمل يتطلب تصريحاً نُفذ دون تصريح", SEV.critical),
    "A01": ("Permit displayed and legible", "التصريح معروض وواضح", SEV.minor),
    "A02": ("Work matches permit scope and location", "العمل مطابق لنطاق وموقع التصريح", SEV.critical),
    "A03": ("Permit valid now — status, window, shift", "التصريح ساري الآن (الحالة، الفترة، الوردية)", SEV.critical),
    "A04": ("Crew on site = crew on permit, briefed", "الطاقم في الموقع مطابق للتصريح ومُوعّى", SEV.major),
    "A05": ("JSA at site, crew aware of key hazards", "تحليل السلامة في الموقع والطاقم على علم بالمخاطر", SEV.major),
    "A06": ("Gas test valid and within interval", "فحص الغاز ساري وضمن الفترة", SEV.critical),
    "A07": ("Isolations, locks and tags match the certificate", "العزل والأقفال والبطاقات مطابقة للشهادة", SEV.critical),
    "A08": ("Fire watch present and equipped", "مراقب الحريق حاضر ومجهز", SEV.critical),
    "A09": ("Combustibles and extinguishers", "المواد القابلة للاشتعال وطفايات الحريق", SEV.major),
    "A10": ("Standby person at entry, rescue set ready", "الشخص المناوب عند المدخل ومعدات الإنقاذ جاهزة", SEV.critical),
    "A11": ("Fall protection as permitted", "الحماية من السقوط كما في التصريح", SEV.critical),
    "A12": ("Excavation protection, spoil, egress", "حماية الحفرية والأتربة ووسيلة الخروج", SEV.major),
    "A13": ("Lifting exclusion zone, gear tags, signaller", "منطقة حظر الرفع وبطاقات الأدوات وموجه الإشارات", SEV.major),
    "A14": ("Barricades and signage", "الحواجز واللوحات", SEV.minor),
    "A15": ("PPE as specified", "معدات الوقاية كما هو محدد", SEV.minor),
    "A16": ("Housekeeping", "النظافة والترتيب", SEV.minor),
    "A17": ("Radiography barrier and survey", "حاجز التصوير الإشعاعي والقياس", SEV.critical),
    "A18": ("Airside: WAP, escort, FOD, beacons", "الجانب الجوي: التصريح والمرافقة والأجسام الغريبة والإنارة", SEV.major),
    "A19": ("Heat controls: water, shade, rest", "ضوابط الحرارة: الماء والظل والراحة", SEV.major),
    "A20": ("Equipment inspection tags", "بطاقات فحص المعدات", SEV.major),
}  # fmt: skip
AUDIT_ALWAYS = ("A01", "A02", "A03", "A04", "A05", "A14", "A15", "A16", "A20")
AUDIT_TYPE_ITEMS: dict[PermitType, tuple[str, ...]] = {
    T.hot_work: ("A08", "A09"),
    T.confined_space: ("A10",),
    T.work_at_height: ("A11",),
    T.excavation: ("A12",),
    T.lifting: ("A13",),
    T.radiography: ("A17",),
    T.airside_works: ("A18",),
}

# ---- list B (blockers) --------------------------------------------------------------------------

BLOCKER_TEXT: dict[PermitBlocker, tuple[str, str]] = {
    B.JSA_MISSING: ("No JSA attached", "لا يوجد تحليل سلامة عمل"),
    B.JSA_NOT_APPROVED: ("JSA not approved", "تحليل سلامة العمل غير معتمد"),
    B.JSA_RESIDUAL_EXTREME: ("A JSA line has an Extreme residual risk", "خطر متبقٍ حرج في تحليل السلامة"),
    B.RESIDUAL_ACCEPTANCE_MISSING: ("Residual risk acceptance missing", "قبول المخاطر المتبقية غير مكتمل"),
    B.HSE_REVIEW_MISSING: ("HSE review of the high-risk permit missing", "مراجعة السلامة للتصريح عالي الخطورة غير موجودة"),
    B.DOCUMENT_MISSING: ("Mandatory document missing", "مستند إلزامي غير موجود"),
    B.CHECKLIST_INCOMPLETE: ("Pre-issue checklist incomplete", "قائمة التحقق قبل الإصدار غير مكتملة"),
    B.ROLE_MISSING: ("Mandatory crew role missing", "دور إلزامي في الطاقم غير موجود"),
    B.APPOINTMENT_INVALID: ("Required appointment not valid", "التعيين المطلوب غير ساري"),
    B.KEY_ROLE_INELIGIBLE: ("A key-role crew member is not eligible", "أحد أصحاب الأدوار الرئيسية غير مؤهل"),
    B.NO_ELIGIBLE_CREW: ("No eligible crew", "لا يوجد طاقم مؤهل"),
    B.HOOK_NOT_MET: ("Certificate / training requirement not met", "متطلب شهادة أو تدريب غير مستوفى"),
    B.GAS_TEST_REQUIRED: ("Gas test required", "فحص الغاز مطلوب"),
    B.GAS_TEST_FAILED: ("Latest gas test failed", "آخر فحص غاز فشل"),
    B.GAS_TEST_EXPIRED: ("Gas test no longer valid for start", "فحص الغاز لم يعد صالحاً لبدء العمل"),
    B.ISOLATION_NOT_VERIFIED: ("Linked isolation not verified", "العزل المرتبط غير متحقق منه"),
    B.PERSONAL_LOCKS_MISSING: ("Personal locks missing on the lockbox", "أقفال شخصية ناقصة على صندوق الأقفال"),
    B.SIMOPS_PROHIBITED: ("Prohibited SIMOPS conflict", "تعارض عمليات متزامنة محظور"),
    B.SIMOPS_COORDINATION_REQUIRED: ("SIMOPS coordination record required", "مطلوب سجل تنسيق للعمليات المتزامنة"),
    B.WAP_NOT_ACTIVE: ("No Active work-area access permit", "لا يوجد تصريح دخول منطقة ساري"),
    B.WAP_CREW_MISSING: ("Crew member not on the WAP", "عضو طاقم غير مدرج في تصريح دخول المنطقة"),
    B.OUTSIDE_WAP_WINDOW: ("Permit window outside the WAP windows", "فترة التصريح خارج فترات تصريح دخول المنطقة"),
    B.NOTAM_NOT_IN_EFFECT: ("NOTAM not in effect", "إشعار NOTAM غير ساري"),
    B.OBS_CLEARANCE_REQUIRED: ("Obstacle clearance required", "موافقة العائق مطلوبة"),
    B.WIND_LIMIT_EXCEEDED: ("Wind above the limit", "سرعة الرياح فوق الحد"),
    B.MIDDAY_BAN: ("Midday outdoor work ban", "حظر العمل وقت الظهيرة"),
    B.OUTSIDE_WINDOW: ("Outside the permit's work windows", "خارج فترات العمل للتصريح"),
    B.CONTRACTOR_SUSPENDED: ("Contractor suspended or blacklisted", "المقاول موقوف أو محظور"),
    B.LICENCE_INVALID: ("Radiography licence / RPO not valid", "رخصة التصوير الإشعاعي أو مسؤول الحماية غير ساري"),
    B.BARRIER_NOT_VERIFIED: ("Radiography barrier not verified by survey", "لم يتم التحقق من حاجز الإشعاع بالقياس"),
    B.FIRE_IMPAIRMENT_NOT_APPROVED: ("Fire-system impairment not approved", "تعطيل نظام الحريق غير معتمد"),
    B.UTILITY_CLEARANCE_MISSING: ("Utility clearance reference missing", "مرجع تصريح الخدمات المدفونة غير موجود"),
    B.FALL_CLEARANCE_INSUFFICIENT: ("Fall clearance insufficient", "الخلوص أسفل نقطة العمل غير كافٍ"),
}  # fmt: skip
BLOCKER_ORDER = {b: i for i, b in enumerate(PermitBlocker)}
APPROVE_TIME: frozenset[PermitBlocker] = frozenset(
    {
        B.JSA_MISSING, B.JSA_NOT_APPROVED, B.JSA_RESIDUAL_EXTREME, B.RESIDUAL_ACCEPTANCE_MISSING,
        B.HSE_REVIEW_MISSING, B.DOCUMENT_MISSING, B.ROLE_MISSING, B.APPOINTMENT_INVALID,
        B.SIMOPS_PROHIBITED, B.CONTRACTOR_SUSPENDED, B.LICENCE_INVALID,
        B.UTILITY_CLEARANCE_MISSING, B.FALL_CLEARANCE_INSUFFICIENT,
        B.FIRE_IMPAIRMENT_NOT_APPROVED, B.MIDDAY_BAN,
    }
)  # fmt: skip
# SH-2: blocker on an Active permit → suspension reason
BLOCKER_REASON: dict[PermitBlocker, StatusReason] = {
    B.GAS_TEST_FAILED: StatusReason.gas_test_failed,
    B.WAP_NOT_ACTIVE: StatusReason.wap_suspended,
    B.WAP_CREW_MISSING: StatusReason.wap_suspended,
    B.NOTAM_NOT_IN_EFFECT: StatusReason.notam_not_in_effect,
    B.OBS_CLEARANCE_REQUIRED: StatusReason.obs_not_active,
    B.SIMOPS_PROHIBITED: StatusReason.simops_conflict,
    B.KEY_ROLE_INELIGIBLE: StatusReason.key_role_ineligible,
    B.NO_ELIGIBLE_CREW: StatusReason.key_role_ineligible,
    B.HOOK_NOT_MET: StatusReason.hook_not_met,
    B.WIND_LIMIT_EXCEEDED: StatusReason.wind_limit,
    B.CONTRACTOR_SUSPENDED: StatusReason.contractor_suspended,
    B.ISOLATION_NOT_VERIFIED: StatusReason.isolation_breach,
}
# blockers that suspend an Active permit automatically (SH-2); others only gate the next start
AUTO_SUSPEND = frozenset(BLOCKER_REASON)

WARNING_TEXT: dict[PermitWarningCode, tuple[str, str]] = {
    W.HOOK_NOT_AVAILABLE: ("Certificate / training check not available yet", "فحص الشهادة أو التدريب غير متاح بعد"),
    W.EXPIRING_7D: ("A crew requirement expires within 7 days", "متطلب لأحد أفراد الطاقم ينتهي خلال 7 أيام"),
    W.EXPIRES_DURING_SHIFT: ("A crew requirement expires before the shift ends", "متطلب لأحد أفراد الطاقم ينتهي قبل نهاية الوردية"),
    W.APPOINTMENT_EXPIRES: ("An appointment expires before the permit ends", "تعيين ينتهي قبل انتهاء التصريح"),
    W.SEVERITY_REDUCED_WITHOUT_HIGHER_CONTROL: ("Severity reduced without a higher-level control", "خفض الشدة دون ضابط من مستوى أعلى"),
    W.HOT_WORK_LATE: ("Hot work ended later than allowed", "انتهى العمل الساخن بعد الوقت المسموح"),
    W.POST_EXPIRY_CHECK_PENDING: ("Post-expiry check pending", "فحص ما بعد الانتهاء معلق"),
    W.MIDDAY_BAN_PREWARN: ("Midday ban starts soon", "يبدأ حظر الظهيرة قريباً"),
    W.EXEMPTION_ACTIVE: ("An exemption is active", "يوجد استثناء ساري"),
    W.CREW_EXCLUDED: ("Crew member excluded", "تم استبعاد عضو من الطاقم"),
    W.SIMOPS_CONDITIONAL: ("Conditional SIMOPS conflict (coordinated)", "تعارض مشروط (منسق)"),
    W.ISOLATIONS_STILL_APPLIED: ("Isolations still applied", "العزل ما زال مطبقاً"),
    W.POSSIBLE_ID_NUMBER: ("Possible ID number in free text", "احتمال وجود رقم هوية في النص"),
    W.HOOK_NOT_MET_WARN: ("Certificate requirement not met (warning stage)", "متطلب الشهادة غير مستوفى (مرحلة التحذير)"),
    W.CERT_UNVERIFIED: ("Certificate not yet verified with the issuer", "الشهادة لم يتم التحقق منها بعد لدى الجهة المصدرة"),
    W.CARD_RESTRICTION_REVIEW: ("Card restriction needs HSE review", "قيد على البطاقة يحتاج مراجعة السلامة"),
}  # fmt: skip

REASON_TEXT: dict[StatusReason, tuple[str, str]] = {
    StatusReason.shift_end: ("Shift end", "نهاية الوردية"),
    StatusReason.midday_ban: ("Midday ban", "حظر العمل وقت الظهيرة"),
    StatusReason.shift_lapsed: ("Shift lapsed", "انقضاء الوردية دون تسليم"),
    StatusReason.gas_test_failed: ("Gas test failed", "فشل فحص الغاز"),
    StatusReason.gas_retest_overdue: ("Gas re-test overdue", "تأخر إعادة فحص الغاز"),
    StatusReason.gas_alarm: ("Gas alarm", "إنذار غاز"),
    StatusReason.wap_suspended: ("WAP suspended", "إيقاف تصريح دخول المنطقة"),
    StatusReason.ops_suspension: ("Operational suspension", "إيقاف تشغيلي"),
    StatusReason.notam_not_in_effect: ("NOTAM not in effect", "NOTAM غير ساري"),
    StatusReason.obs_not_active: ("Obstacle clearance not active", "موافقة العائق غير سارية"),
    StatusReason.simops_conflict: ("SIMOPS conflict", "تعارض عمليات متزامنة"),
    StatusReason.key_role_ineligible: ("Key role ineligible", "عدم أهلية دور رئيسي"),
    StatusReason.hook_not_met: ("Certificate / training not met", "متطلب شهادة/تدريب غير مستوفى"),
    StatusReason.wind_limit: ("Wind limit", "تجاوز حد الرياح"),
    StatusReason.weather: ("Weather", "الطقس"),
    StatusReason.audit_critical: ("Critical audit finding", "مخالفة حرجة في التدقيق"),
    StatusReason.stop_work: ("Stop work", "إيقاف العمل"),
    StatusReason.emergency: ("Emergency", "حالة طوارئ"),
    StatusReason.contractor_suspended: ("Contractor suspended", "المقاول موقوف"),
    StatusReason.contractor_blacklisted: ("Contractor blacklisted", "المقاول محظور"),
    StatusReason.isolation_breach: ("Isolation breach", "خلل في العزل"),
    StatusReason.rejected: ("Rejected", "مرفوض"),
    StatusReason.not_required: ("Not required", "غير مطلوب"),
    StatusReason.duplicate: ("Duplicate", "مكرر"),
    StatusReason.other: ("Other", "أخرى"),
}

TYPE_LABEL_AR = {t: i.label_ar for t, i in TYPES.items()}

# ---- risk (§6.1, JS-2, JS-7) --------------------------------------------------------------------

BANDS: list[tuple[RiskBand, int, int, str, str, str, str]] = [
    (RiskBand.low, 1, 4, "Low", "منخفض", "Receiver", "المستلم"),
    (RiskBand.medium, 5, 9, "Medium", "متوسط", "Issuer", "المُصدِر"),
    (RiskBand.high, 10, 14, "High", "مرتفع", "Issuer and HSE Officer / Manager (ALARP)",
     "المُصدِر ومسؤول/مدير السلامة (مع مبرر ALARP)"),
    (RiskBand.extreme, 15, 25, "Extreme", "حرج", "Not acceptable — redesign the task",
     "غير مقبول — يجب إعادة تصميم المهمة"),
]  # fmt: skip

# ---- gas (§6.2, §3.17) --------------------------------------------------------------------------

GAS_LIMITS_DEFAULT: dict[str, Any] = {
    "by_profile": {
        "general": {
            "o2_min_pct": "19.5", "o2_max_pct": "23.5", "lel_below_pct": "10.0",
            "h2s_below_ppm": "1.0", "co_below_ppm": "25.0",
        },
        "confined_space": {
            "o2_min_pct": "19.5", "o2_max_pct": "23.5", "lel_below_pct": "5.0",
            "h2s_below_ppm": "1.0", "co_below_ppm": "25.0",
        },
        "hot_work": {
            "o2_min_pct": "19.5", "o2_max_pct": "23.5", "lel_below_pct": "1.0",
            "h2s_below_ppm": "1.0", "co_below_ppm": "25.0",
        },
    },
    "other_toxics": [],
}  # fmt: skip
GAS_RETEST_DEFAULT = {"confined_space": 60, "hot_work": 120, "excavation": 120, "general": 240}
TYPE_MAX_DAYS_DEFAULT = {t.value: i.max_days for t, i in TYPES.items()}
TYPE_MAX_ALLOWED: dict[PermitType, tuple[int, int]] = {
    T.general: (1, 14), T.work_at_height: (1, 14), T.excavation: (1, 14),
    T.electrical_isolation: (1, 14), T.airside_works: (1, 14), T.lifting: (1, 14),
    T.hot_work: (1, 7), T.confined_space: (1, 1), T.radiography: (1, 1),
}  # fmt: skip
MIDDAY_PERIOD_DEFAULT = {"start_mmdd": "06-15", "end_mmdd": "09-15"}
MIDDAY_HOURS_DEFAULT = {"start_local": "12:00", "end_local": "15:00"}

# ---- radiography (§6.7) -------------------------------------------------------------------------

GAMMA: dict[str, Decimal] = {
    "ir_192": Decimal("0.13"),
    "se_75": Decimal("0.054"),
    "co_60": Decimal("0.35"),
}

# ---- SIMOPS default matrix (SM-3) ---------------------------------------------------------------

S = SimopsTypeSelector
C = SimopsCondition
SR = SimopsResult


@dataclass(frozen=True)
class RuleDef:
    code: str
    type_a: SimopsTypeSelector
    type_b: SimopsTypeSelector
    condition: SimopsCondition
    threshold: Decimal | None
    result: SimopsResult
    controls_en: str | None
    controls_ar: str | None


SIMOPS_DEFAULTS: list[RuleDef] = [
    RuleDef("SM-R01", S.radiography, S.any, C.within_barrier, None, SR.prohibited, None, None),
    RuleDef("SM-R02", S.hot_work, S.confined_space, C.within_threshold, Decimal("15.0"),
            SR.conditional,
            "Ventilation intakes away from hot work; continuous LEL monitoring at both",
            "إبعاد مداخل التهوية عن العمل الساخن؛ مراقبة مستمرة لنسبة LEL في الموقعين"),
    RuleDef("SM-R03", S.hot_work, S.flammables_in_use, C.within_combustible_clearance, None,
            SR.prohibited, None, None),
    RuleDef("SM-R04", S.hot_work, S.gas_test_required, C.within_threshold, Decimal("15.0"),
            SR.conditional, "LEL test at hot-work point", "فحص LEL عند نقطة العمل الساخن"),
    RuleDef("SM-R05a", S.crane, S.any, C.within_exclusion_radius, None, SR.prohibited, None, None),
    RuleDef("SM-R05b", S.crane, S.any, C.within_slew_radius, None, SR.conditional,
            "No load over B; banksman; B informed of lift times",
            "عدم تمرير الحمولة فوق B؛ منظم حركة؛ إبلاغ B بأوقات الرفع"),
    RuleDef("SM-R06", S.work_at_height, S.any, C.above_within_drop_zone, None, SR.conditional,
            "Drop-zone barricade or overhead protection for B; tool tethering for A",
            "تسييج منطقة السقوط أو حماية علوية لـ B؛ ربط الأدوات لـ A"),
    RuleDef("SM-R07", S.hot_work, S.any, C.hot_work_above_within_clearance, None,
            SR.conditional, "Spark containment; fire watch covers B's level",
            "احتواء الشرر؛ مراقب الحريق يغطي مستوى B"),
    RuleDef("SM-R08", S.excavation, S.lifting_or_excavating_plant, C.within_surcharge_zone,
            None, SR.conditional, "Engineering check of surcharge on the protective system",
            "تحقق هندسي من الأحمال الإضافية على نظام الحماية"),
    RuleDef("SM-R09", S.confined_space, S.combustion_engine_plant, C.within_threshold,
            Decimal("10.0"), SR.conditional, "Exhaust away from openings; CO monitoring",
            "إبعاد العادم عن الفتحات؛ مراقبة CO"),
    RuleDef("SM-R10", S.energized_electrical, S.any, C.same_zone, None, SR.conditional,
            "Approach boundaries barricaded", "تسييج حدود الاقتراب"),
    RuleDef("SM-R11", S.crane, S.crane, C.slew_overlap, None, SR.conditional,
            "Anti-collision zoning / operator radio protocol",
            "تقسيم مناطق منع التصادم وبروتوكول اتصال المشغلين"),
    RuleDef("SM-R12", S.any, S.other_contractor_movement_area, C.same_zone, None,
            SR.conditional, "Single works coordinator named in agreed controls",
            "تسمية منسق أعمال واحد في الضوابط المتفق عليها"),
]  # fmt: skip
DEFAULT_RULE_CODES = frozenset(r.code for r in SIMOPS_DEFAULTS)
CONDITION_TEXT: dict[SimopsCondition, tuple[str, str]] = {
    C.within_barrier: ("distance ≤ A's planned barrier", "المسافة ≤ حاجز A المخطط"),
    C.within_threshold: ("distance ≤ threshold", "المسافة ≤ الحد"),
    C.within_combustible_clearance: (
        "distance ≤ hw_combustible_clearance_m",
        "المسافة ≤ مسافة إزالة المواد القابلة للاشتعال",
    ),
    C.within_exclusion_radius: (
        "B within A's exclusion radius of the landing point",
        "B ضمن نصف قطر الحظر حول نقطة الإنزال",
    ),
    C.within_slew_radius: (
        "B within A's slew radius of the appliance",
        "B ضمن نصف قطر دوران الرافعة",
    ),
    C.above_within_drop_zone: (
        "A above B, horizontal distance ≤ drop_zone_radius_m",
        "A أعلى من B والمسافة الأفقية ≤ نصف قطر منطقة السقوط",
    ),
    C.hot_work_above_within_clearance: (
        "hot work at height above B, distance ≤ hw_combustible_clearance_m",
        "عمل ساخن على ارتفاع فوق B والمسافة ≤ مسافة إزالة المواد",
    ),
    C.within_surcharge_zone: ("distance ≤ A's max depth", "المسافة ≤ أقصى عمق للحفرية"),
    C.same_zone: ("same zone", "نفس المنطقة"),
    C.slew_overlap: (
        "appliance distance ≤ sum of slew radii",
        "المسافة بين الرافعتين ≤ مجموع نصفي قطر الدوران",
    ),
}
RESULT_RANK = {SR.allowed: 0, SR.conditional: 1, SR.prohibited: 2}
