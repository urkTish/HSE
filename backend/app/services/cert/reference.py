"""Phase 4 reference lists (spec 4-third-party-cert §3.16): EQC categories with intervals, hook
and operator codes; PCT certificate types with caps, satisfied codes, scope and levels; LIM /
LIM-P limitation labels; AIC / SIC checklists; SSR reasons; VC → EQC and PTW EQ → EQC mappings;
the implemented hook codes (HK4-2); EN/AR texts for provider reasons."""

from dataclasses import dataclass, field

from app.core.access_enums import HookKind, VehicleCategory
from app.core.cert_enums import (
    ArrivalChecklistItem,
    CertLevel,
    EquipmentSubtype,
    HookReasonCode,
    LimitationCode,
    PersonnelLimitationCode,
    ScaffoldChecklistItem,
    ServiceStatus,
    ServiceStatusReason,
)
from app.core.cert_enums import EquipmentCertCategory as Q
from app.core.ptw_enums import EquipmentCategory as EQ  # noqa: N814
from app.core.ptw_enums import EquipmentUse

ST = EquipmentSubtype
L = CertLevel


@dataclass(frozen=True)
class Eqc:
    code: Q
    label_en: str
    label_ar: str
    interval_months: int | None  # None = scaffold (days, SF-5)
    cf1: bool
    hook_code: str
    operator_code: str | None
    subtypes: tuple[EquipmentSubtype, ...] = ()
    subtype_required: bool = False


ACCESSORY_SUBTYPES = (
    ST.wire_rope_sling,
    ST.chain_sling,
    ST.synthetic_sling,
    ST.shackle,
    ST.hook,
    ST.eyebolt,
    ST.spreader_beam,
    ST.lifting_beam,
    ST.plate_clamp,
    ST.chain_block,
    ST.lever_hoist,
    ST.beam_clamp,
    ST.other,
)

EQC: dict[Q, Eqc] = {
    e.code: e
    for e in (
        Eqc(
            Q.tower_crane,
            "Tower crane",
            "رافعة برجية",
            12,
            True,
            "CRANE-TPI",
            "CRANE-OPERATOR",
            (ST.flat_top, ST.hammerhead, ST.luffing),
        ),
        Eqc(
            Q.mobile_crane, "Mobile crane", "رافعة متحركة", 12, False, "CRANE-TPI", "CRANE-OPERATOR"
        ),
        Eqc(
            Q.crawler_crane,
            "Crawler crane",
            "رافعة مجنزرة",
            12,
            False,
            "CRANE-TPI",
            "CRANE-OPERATOR",
        ),
        Eqc(
            Q.loader_crane,
            "Lorry loader crane",
            "رافعة محمولة على شاحنة",
            12,
            False,
            "CRANE-TPI",
            "CRANE-OPERATOR",
        ),
        Eqc(
            Q.overhead_gantry_crane,
            "Overhead / gantry crane",
            "رافعة علوية / جسرية",
            12,
            False,
            "CRANE-TPI",
            "CRANE-OPERATOR",
        ),
        Eqc(
            Q.construction_hoist,
            "Construction hoist (persons/materials)",
            "مصعد إنشائي",
            6,
            True,
            "HOIST-TPI",
            "HOIST-OPERATOR",
        ),
        Eqc(
            Q.mast_climber,
            "Mast-climbing work platform",
            "منصة صاعدة على صاري",
            6,
            True,
            "HOIST-TPI",
            "HOIST-OPERATOR",
        ),
        Eqc(
            Q.bmu,
            "Building maintenance unit",
            "وحدة صيانة المباني",
            6,
            True,
            "HOIST-TPI",
            "HOIST-OPERATOR",
        ),
        Eqc(
            Q.mewp,
            "MEWP",
            "منصة رفع أفراد متحركة",
            6,
            False,
            "MEWP-TPI",
            "MEWP-OPERATOR",
            (ST.scissor, ST.boom, ST.vertical_mast),
            True,
        ),
        Eqc(
            Q.man_basket,
            "Crane-suspended man-basket",
            "سلة رفع أفراد",
            6,
            False,
            "MAN-BASKET-TPI",
            None,
        ),
        Eqc(Q.forklift, "Forklift", "رافعة شوكية", 12, False, "FORKLIFT-TPI", "FORKLIFT-OPERATOR"),
        Eqc(
            Q.telehandler,
            "Telehandler",
            "رافعة تلسكوبية",
            12,
            False,
            "TELEHANDLER-TPI",
            "TELEHANDLER-OPERATOR",
        ),
        Eqc(Q.excavator, "Excavator", "حفارة", 12, False, "PLANT-TPI", "PLANT-OPERATOR"),
        Eqc(
            Q.wheel_loader,
            "Wheel loader / backhoe loader",
            "لودر",
            12,
            False,
            "PLANT-TPI",
            "PLANT-OPERATOR",
        ),
        Eqc(
            Q.piling_rig,
            "Piling / drilling rig",
            "حفارة خوازيق",
            12,
            False,
            "PLANT-TPI",
            "PLANT-OPERATOR",
        ),
        Eqc(
            Q.concrete_pump_boom,
            "Concrete pump boom",
            "مضخة خرسانة بذراع",
            12,
            False,
            "PLANT-TPI",
            "PLANT-OPERATOR",
        ),
        Eqc(
            Q.lifting_accessory,
            "Lifting accessory",
            "ملحقات الرفع",
            6,
            False,
            "LIFTING-ACCESSORY-TPI",
            None,
            ACCESSORY_SUBTYPES,
            True,
        ),
        Eqc(
            Q.tripod_winch,
            "CSE rescue tripod / winch",
            "حامل ورافعة إنقاذ",
            6,
            False,
            "RESCUE-WINCH-TPI",
            None,
        ),
        Eqc(
            Q.pressure_vessel,
            "Pressure vessel",
            "وعاء ضغط",
            12,
            False,
            "PRESSURE-TPI",
            None,
            (ST.air_receiver, ST.hydraulic_accumulator, ST.other),
            True,
        ),
        Eqc(Q.scaffold, "Scaffold", "سقالة", None, False, "SCAFFOLD-TAG", None),
    )
}

CRANES = frozenset(
    {Q.tower_crane, Q.mobile_crane, Q.crawler_crane, Q.loader_crane, Q.overhead_gantry_crane}
)
HOISTS = frozenset({Q.construction_hoist, Q.mast_climber, Q.bmu})
CF1_ANY = frozenset({Q.tower_crane, Q.construction_hoist, Q.mast_climber, Q.bmu})
CF1_LIMITED = frozenset({Q.mobile_crane, Q.crawler_crane})
LOAD_TEST_CATEGORIES = CRANES | HOISTS | {Q.man_basket}
LIFTING_DUTY_CATEGORIES = frozenset({Q.excavator, Q.wheel_loader, Q.telehandler})
LIFTING_CATEGORIES = (
    CRANES | HOISTS | {Q.lifting_accessory, Q.man_basket, Q.forklift, Q.telehandler, Q.tripod_winch}
)
# DF-6: A defects on these need a TPI after_repair line (structural / hydraulic / safety device)
TPI_REINSPECTION_CATEGORIES = CRANES | HOISTS | {Q.mewp, Q.man_basket, Q.telehandler, Q.forklift}
DESTROY_ONLY = frozenset({Q.lifting_accessory, Q.tripod_winch})  # DF-7
PERSON_CARRYING = frozenset({Q.mewp, Q.man_basket, Q.construction_hoist, Q.mast_climber, Q.bmu})

EQUIPMENT_HOOK_CODES: dict[str, frozenset[Q]] = {}
for _e in EQC.values():
    EQUIPMENT_HOOK_CODES.setdefault(_e.hook_code, frozenset())
    EQUIPMENT_HOOK_CODES[_e.hook_code] = EQUIPMENT_HOOK_CODES[_e.hook_code] | {_e.code}

# ---- mappings (§3.16) ------------------------------------------------------------------------

VC_TO_EQC: dict[VehicleCategory, frozenset[Q] | None] = {}
for _vc in VehicleCategory:
    VC_TO_EQC[_vc] = frozenset()
VC_TO_EQC.update(
    {
        VehicleCategory.mobile_crane: frozenset({Q.mobile_crane}),
        VehicleCategory.crawler_crane: frozenset({Q.crawler_crane}),
        VehicleCategory.mewp: frozenset({Q.mewp}),
        VehicleCategory.forklift: frozenset({Q.forklift}),
        VehicleCategory.telehandler: frozenset({Q.telehandler}),
        VehicleCategory.excavator: frozenset({Q.excavator}),
        VehicleCategory.wheel_loader: frozenset({Q.wheel_loader}),
        VehicleCategory.truck: frozenset({Q.loader_crane}),
        VehicleCategory.other: None,  # any
    }
)

PTW_TO_EQC: dict[EQ, Q | None] = {
    EQ.tower_crane: Q.tower_crane,
    EQ.mobile_crane: Q.mobile_crane,
    EQ.crawler_crane: Q.crawler_crane,
    EQ.mewp: Q.mewp,
    EQ.man_basket: Q.man_basket,
    EQ.mast_climber: Q.mast_climber,
    EQ.bmu: Q.bmu,
    EQ.scaffold: Q.scaffold,
    EQ.tripod_winch: Q.tripod_winch,
    EQ.lifting_accessory: Q.lifting_accessory,
    EQ.spreader_beam: Q.lifting_accessory,
}

USE_PERSONNEL_LIFT = frozenset({"personnel_lift"})


def vc_allows(vc: VehicleCategory, category: Q) -> bool:
    allowed = VC_TO_EQC.get(vc, frozenset())
    return allowed is None or category in allowed


# ---- PCT (§3.16) --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Pct:
    code: str
    label_en: str
    label_ar: str
    cap_months: int
    satisfies: tuple[str, ...]
    scope_allowed: frozenset[Q] = frozenset()
    levels: tuple[CertLevel, ...] = ()
    level_required: bool = False
    rejected_levels: tuple[CertLevel, ...] = ()
    extra: dict[str, str] = field(default_factory=dict)


PCT: dict[str, Pct] = {
    p.code: p
    for p in (
        Pct("CRANE-OPERATOR", "Crane operator", "مشغل رافعة", 36, ("CRANE-OPERATOR",), CRANES),
        Pct(
            "RIGGER",
            "Rigger",
            "عامل ربط",
            36,
            ("RIGGER",),
            frozenset(),
            (L.level_1, L.level_2, L.level_3),
            True,
        ),
        Pct("SIGNALLER", "Signal person (lifting)", "موجه إشارات الرفع", 36, ("SIGNALLER",)),
        Pct("BANKSMAN", "Banksman / plant marshaller", "منظم حركة المعدات", 36, ("BANKSMAN",)),
        Pct(
            "SIGNALLER-BANKSMAN",
            "Combined signaller & banksman card",
            "بطاقة موجه إشارات ومنظم حركة",
            36,
            ("SIGNALLER", "BANKSMAN"),
        ),
        Pct(
            "MEWP-OPERATOR",
            "MEWP operator",
            "مشغل منصة رفع أفراد",
            60,
            ("MEWP-OPERATOR",),
            frozenset({Q.mewp}),
        ),
        Pct(
            "FORKLIFT-OPERATOR",
            "Forklift operator",
            "مشغل رافعة شوكية",
            36,
            ("FORKLIFT-OPERATOR",),
            frozenset({Q.forklift}),
        ),
        Pct(
            "TELEHANDLER-OPERATOR",
            "Telehandler operator",
            "مشغل رافعة تلسكوبية",
            36,
            ("TELEHANDLER-OPERATOR",),
            frozenset({Q.telehandler}),
        ),
        Pct(
            "PLANT-OPERATOR",
            "Earthmoving / plant operator",
            "مشغل معدات ثقيلة",
            36,
            ("PLANT-OPERATOR",),
            frozenset({Q.excavator, Q.wheel_loader, Q.piling_rig, Q.concrete_pump_boom}),
        ),
        Pct(
            "HOIST-OPERATOR",
            "Hoist / mast-climber / BMU operator",
            "مشغل مصعد إنشائي أو منصة صاعدة",
            36,
            ("HOIST-OPERATOR",),
            HOISTS,
        ),
        Pct(
            "SCAFFOLDER",
            "Scaffolder",
            "عامل سقالات",
            60,
            ("SCAFFOLDER",),
            frozenset(),
            (L.basic, L.advanced),
        ),
        Pct("SCAFFOLD-INSPECTOR", "Scaffold inspector", "مفتش سقالات", 60, ("SCAFFOLD-INSPECTOR",)),
        Pct(
            "GAS-TESTER", "Authorised gas tester card", "بطاقة فاحص غاز معتمد", 24, ("GAS-TESTER",)
        ),
        Pct(
            "RADIOGRAPHER",
            "Industrial radiographer (RT level II/III)",
            "فني تصوير إشعاعي",
            60,
            ("RADIOGRAPHER",),
            frozenset(),
            (L.level_i, L.level_ii, L.level_iii),
            True,
            (L.level_i,),
        ),
        Pct(
            "ROPE-ACCESS",
            "Rope access technician",
            "فني الوصول بالحبال",
            36,
            ("ROPE-ACCESS",),
            frozenset(),
            (L.level_1, L.level_2, L.level_3),
            True,
        ),
        Pct("LIFT-SUPERVISOR", "Lift supervisor", "مشرف رفع", 36, ("LIFT-SUPERVISOR",)),
        Pct(
            "APPOINTED-PERSON-LIFTING",
            "Appointed person (lifting)",
            "الشخص المعيّن لعمليات الرفع",
            60,
            ("APPOINTED-PERSON-LIFTING",),
        ),
        Pct(
            "AP-ELEC-LV",
            "Authorised person, electrical LV",
            "شخص مخوَّل كهربائياً (جهد منخفض)",
            36,
            ("AP-ELEC-LV",),
        ),
        Pct(
            "AP-ELEC-HV",
            "Authorised person, electrical HV",
            "شخص مخوَّل كهربائياً (جهد عالٍ)",
            36,
            ("AP-ELEC-HV",),
        ),
        Pct(
            "CSE-STANDBY-CARD",
            "Confined-space standby/attendant card (third-party)",
            "بطاقة مناوب الأماكن المحصورة",
            24,
            ("CSE-STANDBY-CARD",),
        ),
        Pct(
            "LOTO-AUTHORISED-CARD",
            "Authorised isolator card (third-party)",
            "بطاقة منفذ عزل معتمد",
            36,
            ("LOTO-AUTHORISED-CARD",),
        ),
    )
}

PERSONNEL_HOOK_CODES: tuple[str, ...] = (
    "CRANE-OPERATOR",
    "RIGGER",
    "SIGNALLER",
    "BANKSMAN",
    "GAS-TESTER",
    "RADIOGRAPHER",
    "ROPE-ACCESS",
    "MEWP-OPERATOR",
    "FORKLIFT-OPERATOR",
    "TELEHANDLER-OPERATOR",
    "PLANT-OPERATOR",
    "HOIST-OPERATOR",
    "SCAFFOLDER",
    "SCAFFOLD-INSPECTOR",
    "LIFT-SUPERVISOR",
    "APPOINTED-PERSON-LIFTING",
    "AP-ELEC-LV",
    "AP-ELEC-HV",
    "CSE-STANDBY-CARD",
    "LOTO-AUTHORISED-CARD",
)
EQUIPMENT_HOOK_CODE_LIST: tuple[str, ...] = (
    "CRANE-TPI",
    "MEWP-TPI",
    "FORKLIFT-TPI",
    "TELEHANDLER-TPI",
    "LIFTING-ACCESSORY-TPI",
    "MAN-BASKET-TPI",
    "SCAFFOLD-TAG",
    "HOIST-TPI",
    "PLANT-TPI",
    "RESCUE-WINCH-TPI",
    "PRESSURE-TPI",
)
OPERATOR_CODES = frozenset(e.operator_code for e in EQC.values() if e.operator_code)
KEY_LIFT_ROLES = ("crane_operator", "rigger", "signaller")  # PC-8

DEFAULT_CRITICAL_CODES: tuple[str, ...] = (
    "CRANE-TPI",
    "CRANE-OPERATOR",
    "LIFTING-ACCESSORY-TPI",
    "MAN-BASKET-TPI",
    "MEWP-TPI",
    "HOIST-TPI",
    "RIGGER",
    "SIGNALLER",
)
DEFAULT_TRADE_REQUIREMENTS = {
    "crane_operator": "CRANE-OPERATOR",
    "rigger": "RIGGER",
    "scaffolder": "SCAFFOLDER",
}
ALERT_SCHEDULE_LONG = [30, 14, 7, 0]

# Phase 5 course codes known today (5-training §3.15, BD-3 / BD5-2): a PCT code may not use one.
PHASE5_COURSE_CODES = frozenset(
    {
        "IND-GENERAL",
        "IND-AIRSIDE",
        "IND-ZONE-ILS",
        "IND-ZONE-TC",
        "AVSEC-AWR",
        "AIRSIDE-DRV",
        "AIRSIDE-RTF",
        "WAH",
        "CSE-ENTRANT",
        "CSE-ATTENDANT",
        "CSE-RESCUE",
        "GAS-TEST",
        "H2S-AWR",
        "FIRE-WATCH",
        "FIRE-WARDEN",
        "FIRST-AID",
        "FIRST-AID-R",
        "SCAFF-AWR",
        "LOTO",
        "LOTO-AUTHORITY",
        "ELEC-QUALIFIED",
        "BANKSMAN-AWR",
        "HEAT-AWR",
        "PTW-RECEIVER",
        "PTW-ISSUER",
        "NEBOSH-IGC",
        "NEBOSH-ICC",
        "NEBOSH-DIP",
        "IOSH-MS",
        "IOSH-MS-R",
        "OSHA-30",
    }
)


def satisfying_types(code: str, custom: dict[str, tuple[str, ...]] | None = None) -> list[str]:
    """PCT types whose in-force certificate meets hook `code` (PC types satisfy their own code;
    SIGNALLER-BANKSMAN satisfies both)."""
    out = [p.code for p in PCT.values() if code in p.satisfies]
    for c, sat in (custom or {}).items():
        if code in sat and c not in out:
            out.append(c)
    return out


def operator_types() -> set[str]:
    return {p.code for p in PCT.values() if p.scope_allowed}


# ---- labels -----------------------------------------------------------------------------------

LIM_TEXT: dict[LimitationCode, tuple[str, str]] = {
    LimitationCode.derated_swl: ("Derated SWL", "حمولة مخفّضة"),
    LimitationCode.no_personnel_lifting: ("No personnel lifting", "يمنع رفع الأشخاص"),
    LimitationCode.max_wind_ms: ("Wind limit (m/s)", "حد الرياح"),
    LimitationCode.daylight_only: ("Daylight only", "نهاراً فقط"),
    LimitationCode.fixed_configuration_only: (
        "Inspected configuration only",
        "بالتهيئة المفحوصة فقط",
    ),
    LimitationCode.outriggers_full_extension_only: (
        "Outriggers fully extended only",
        "بالمساند ممتدة بالكامل فقط",
    ),
    LimitationCode.supervised_use_only: ("Supervised use only", "تحت إشراف فقط"),
    LimitationCode.reinspect_after_hours: (
        "Re-inspect after operating hours",
        "إعادة الفحص بعد ساعات تشغيل",
    ),
    LimitationCode.other: ("Other limitation", "قيد آخر"),
}
LIMP_TEXT: dict[PersonnelLimitationCode, tuple[str, str]] = {
    PersonnelLimitationCode.supervised_only: ("Supervised only", "تحت إشراف"),
    PersonnelLimitationCode.trainee_logbook: ("Trainee with logbook", "متدرب بسجل"),
    PersonnelLimitationCode.specific_model_only: ("Specific model only", "طراز محدد فقط"),
    PersonnelLimitationCode.other: ("Other limitation", "قيد آخر"),
}
AIC_TEXT: dict[ArrivalChecklistItem, tuple[str, str]] = {
    ArrivalChecklistItem.AIC_01: (
        "TPI sticker present and number = certificate",
        "ملصق جهة الفحص موجود ورقمه مطابق للشهادة",
    ),
    ArrivalChecklistItem.AIC_02: (
        "Serial plate legible and = register",
        "لوحة الرقم التسلسلي واضحة ومطابقة للسجل",
    ),
    ArrivalChecklistItem.AIC_03: (
        "No visible structural damage, cracks, leaks",
        "لا يوجد ضرر إنشائي أو تشققات أو تسريب ظاهر",
    ),
    ArrivalChecklistItem.AIC_04: (
        "Safety devices functional (LMI/RCI, limits, alarms, emergency stop/lowering)",
        "أجهزة السلامة تعمل (مؤشر الحمولة، المحددات، الإنذارات، الإيقاف/الإنزال الطارئ)",
    ),
    ArrivalChecklistItem.AIC_05: (
        "Load chart and operator manual in cab",
        "جدول الأحمال ودليل المشغل في المقصورة",
    ),
    ArrivalChecklistItem.AIC_06: (
        "Tyres/tracks, outriggers and pads",
        "الإطارات/الجنازير والمساند والقواعد",
    ),
    ArrivalChecklistItem.AIC_07: (
        "Fire extinguisher and spill kit (plant)",
        "طفاية حريق وعدة احتواء الانسكاب (المعدات)",
    ),
    ArrivalChecklistItem.AIC_08: (
        "Lights, beacon, reverse alarm (mobile plant)",
        "الأضواء والمنارة وإنذار الرجوع (المعدات المتحركة)",
    ),
}
SIC_TEXT: dict[ScaffoldChecklistItem, tuple[str, str]] = {
    ScaffoldChecklistItem.SIC_01: (
        "Foundations, base plates, sole boards",
        "الأساسات والألواح القاعدية وألواح الارتكاز",
    ),
    ScaffoldChecklistItem.SIC_02: (
        "Standards plumb, ledgers, transoms",
        "القوائم رأسية والعوارض الطولية والعرضية",
    ),
    ScaffoldChecklistItem.SIC_03: ("Bracing", "التدعيم"),
    ScaffoldChecklistItem.SIC_04: ("Ties/anchors to design", "التثبيت والمراسي حسب التصميم"),
    ScaffoldChecklistItem.SIC_05: (
        "Platforms fully boarded, no gaps",
        "المنصات مغطاة بالكامل بلا فراغات",
    ),
    ScaffoldChecklistItem.SIC_06: (
        "Guardrail (≥ 950 mm), mid-rail, toe board",
        "الحاجز العلوي (≥ 950 مم) والأوسط ولوح القدم",
    ),
    ScaffoldChecklistItem.SIC_07: (
        "Safe access (secured ladder/stair)",
        "وصول آمن (سلم مثبت أو درج)",
    ),
    ScaffoldChecklistItem.SIC_08: (
        "Load class signage and loading within class",
        "لافتة فئة التحميل والتحميل ضمنها",
    ),
    ScaffoldChecklistItem.SIC_09: ("No unauthorised alterations", "لا توجد تعديلات غير مصرح بها"),
    ScaffoldChecklistItem.SIC_10: ("Nets/sheeting secured", "الشباك والأغطية مثبتة"),
    ScaffoldChecklistItem.SIC_11: (
        "Clearance to live services/plant",
        "مسافة آمنة عن الخدمات والمعدات العاملة",
    ),
}
SSR_TEXT: dict[ServiceStatusReason, tuple[str, str]] = {
    ServiceStatusReason.awaiting_certificate: ("Awaiting certificate", "بانتظار الشهادة"),
    ServiceStatusReason.certificate_expired: ("Certificate expired", "الشهادة منتهية"),
    ServiceStatusReason.certificate_suspended: ("Certificate suspended", "الشهادة موقوفة"),
    ServiceStatusReason.certificate_revoked: ("Certificate revoked", "الشهادة ملغاة"),
    ServiceStatusReason.certificate_unverified: (
        "Certificate not verified",
        "الشهادة غير متحقق منها",
    ),
    ServiceStatusReason.configuration_changed: ("Configuration changed", "تغيرت التهيئة"),
    ServiceStatusReason.failed_inspection: ("Failed inspection", "فشل الفحص"),
    ServiceStatusReason.defect_a: ("Category A defect", "عيب من الفئة A"),
    ServiceStatusReason.defect_b_overdue: ("Category B defect overdue", "عيب من الفئة B متأخر"),
    ServiceStatusReason.tpi_blacklisted: ("TPI blacklisted", "جهة الفحص محظورة"),
    ServiceStatusReason.manual_tag_out: ("Tagged out", "موسومة بعدم الاستخدام"),
    ServiceStatusReason.blacklisted: ("Blacklisted", "محظورة"),
    ServiceStatusReason.retired_destroyed: (
        "Destroyed / returned to manufacturer",
        "أُتلفت / أعيدت للمصنع",
    ),
    ServiceStatusReason.retired_sold: ("Sold", "بيعت"),
    ServiceStatusReason.retired_other: ("Retired", "مستبعدة"),
}
SERVICE_TEXT: dict[ServiceStatus, tuple[str, str]] = {
    ServiceStatus.awaiting_certificate: ("Awaiting certificate", "بانتظار الشهادة"),
    ServiceStatus.in_service: ("In service", "في الخدمة"),
    ServiceStatus.quarantined: ("Quarantined", "معزولة عن الاستخدام"),
    ServiceStatus.out_of_service: ("OUT OF SERVICE", "خارج الخدمة"),
    ServiceStatus.blacklisted: ("Blacklisted", "محظورة"),
    ServiceStatus.retired: ("Retired", "مستبعدة"),
}

R = HookReasonCode
REASON_TEXT: dict[str, tuple[str, str]] = {
    R.EQUIPMENT_NOT_REGISTERED: ("Equipment not registered", "المعدة غير مسجلة"),
    R.CATEGORY_MISMATCH: ("Equipment category does not match", "فئة المعدة غير مطابقة"),
    R.EQUIPMENT_BLACKLISTED: ("Equipment blacklisted", "المعدة محظورة"),
    R.EQUIPMENT_RETIRED: ("Equipment retired", "المعدة مستبعدة"),
    R.EQUIPMENT_OUT_OF_SERVICE: ("Equipment out of service", "المعدة خارج الخدمة"),
    R.EQUIPMENT_QUARANTINED: ("Equipment quarantined", "المعدة معزولة عن الاستخدام"),
    R.EQUIPMENT_NOT_DEPLOYED: (
        "Equipment not deployed on this project",
        "المعدة غير معيّنة في هذا المشروع",
    ),
    R.ARRIVAL_INSPECTION_MISSING: ("Arrival inspection not passed", "لم يجتز فحص الوصول"),
    R.CERT_MISSING: ("No certificate", "لا توجد شهادة"),
    R.CERT_EXPIRED: ("Certificate expired", "الشهادة منتهية"),
    R.CERT_UNVERIFIED: (
        "Certificate not verified with the TPI",
        "الشهادة غير متحقق منها لدى الجهة",
    ),
    R.CERT_SUSPENDED: ("Certificate suspended", "الشهادة موقوفة"),
    R.CERT_REVOKED: ("Certificate not accepted", "الشهادة غير مقبولة"),
    R.CONFIGURATION_CHANGED: (
        "Configuration changed — re-examination required",
        "تغيرت التهيئة — يلزم إعادة الفحص",
    ),
    R.SWL_LIMITATION: ("Load above certified SWL", "الحمولة أعلى من الحمولة الآمنة المعتمدة"),
    R.LIMITATION_CONFLICT: (
        "Use conflicts with a certificate limitation",
        "الاستخدام يتعارض مع قيد في الشهادة",
    ),
    R.LIFTING_DUTY_NOT_CERTIFIED: ("Lifting duty not certified", "مهمة الرفع غير معتمدة"),
    R.COLOUR_CODE_OUT_OF_PERIOD: ("Colour code out of period", "رمز اللون خارج الفترة"),
    R.TPI_BLACKLISTED: ("Certificate not accepted", "الشهادة غير مقبولة"),
    R.SCAFFOLD_NOT_REGISTERED: ("Scaffold not registered", "السقالة غير مسجلة"),
    R.SCAFFOLD_INSPECTION_OVERDUE: ("Scaffold inspection overdue", "فحص السقالة متأخر"),
    R.SCAFFOLD_TAG_RED: ("Scaffold red tag — do not use", "بطاقة السقالة حمراء — ممنوع الاستخدام"),
    R.SCAFFOLD_INSPECTION_REQUIRED: ("Scaffold re-inspection required", "السقالة تتطلب إعادة فحص"),
    R.SCAFFOLD_YELLOW_TAG: (
        "Scaffold yellow tag — use with restrictions",
        "بطاقة السقالة صفراء — استخدام بقيود",
    ),
    R.CERT_HOLDER_BANNED: ("Certificate not accepted", "الشهادة غير مقبولة"),
    R.CERT_SCOPE_MISMATCH: (
        "Certificate scope does not cover this use",
        "نطاق الشهادة لا يغطي هذا الاستخدام",
    ),
    R.CERT_LIMITATION: (
        "Certificate limitation not allowed for this role",
        "قيد الشهادة غير مسموح لهذا الدور",
    ),
    R.CARD_RESTRICTION_REVIEW: ("Card restriction to be reviewed", "قيد البطاقة بانتظار المراجعة"),
    R.EXPIRING_7D: ("Expires within 7 days", "تنتهي خلال 7 أيام"),
    R.UNKNOWN_CODE: (
        "Unknown certificate code (configuration error)",
        "رمز شهادة غير معروف (خطأ في الإعداد)",
    ),
}

CHECK_ITEMS_EQ_USE: dict[EquipmentUse, str] = {
    EquipmentUse.lifting_appliance: "lifting_appliance",
    EquipmentUse.lifting_accessory: "lifting_accessory",
    EquipmentUse.access_equipment: "access_equipment",
    EquipmentUse.excavating_plant: "excavating_plant",
    EquipmentUse.rescue_equipment: "rescue_equipment",
}

PHASE4_KINDS = (HookKind.personnel_certificate, HookKind.equipment_certificate)


def eqc_label(code: str) -> tuple[str, str]:
    e = EQC.get(Q(code)) if code in Q.__members__ else None
    return (e.label_en, e.label_ar) if e else (code, code)
