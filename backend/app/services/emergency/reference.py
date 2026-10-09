# ruff: noqa: E501
"""Phase 6c reference lists (spec 6c-emergency-drills §3.14), EN / AR. Codes are immutable.

Per-type applicability (EC items per asset type, DC criteria per drill type, timings per drill
type) is not tabulated in the spec; the choices below are recorded in DECISIONS."""

from __future__ import annotations

from app.core.emergency_enums import (
    Agency,
    AssetType,
    CheckItem,
    Criterion,
    DrillType,
    EmergencyRole,
    EntryState,
    EventType,
    FindingCategory,
    ResolutionReason,
    ResponseType,
    ScenarioType,
    TeamType,
)

ES = ScenarioType
DT = DrillType
AT = AssetType
EC = CheckItem
DC = Criterion

SCENARIOS: dict[ScenarioType, tuple[str, str]] = {
    ES.fire_explosion: ("Fire / explosion", "حريق/انفجار"),
    ES.medical_emergency: ("Medical emergency", "حالة طبية طارئة"),
    ES.severe_weather: ("Severe weather", "طقس شديد"),
    ES.confined_space_rescue: ("Confined space rescue", "إنقاذ من مكان محصور"),
    ES.height_rescue: ("Rescue from height", "إنقاذ من ارتفاع"),
    ES.structural_collapse: ("Structural collapse", "انهيار إنشائي"),
    ES.excavation_collapse: ("Excavation collapse", "انهيار حفرية"),
    ES.gas_release: ("Gas release", "تسرب غاز"),
    ES.electrical_contact: ("Electrical contact", "صعق كهربائي"),
    ES.utility_strike: ("Utility strike", "إصابة خدمات مدفونة"),
    ES.security_threat: ("Security threat", "تهديد أمني"),
    ES.aircraft_emergency: ("Aircraft emergency", "طوارئ طائرة"),
}
MANDATORY = (
    ES.fire_explosion,
    ES.medical_emergency,
    ES.severe_weather,
    ES.confined_space_rescue,
    ES.height_rescue,
)
AIRPORT_MANDATORY = (ES.aircraft_emergency,)
RESCUE_SCENARIOS = {ES.confined_space_rescue: "confined_space", ES.height_rescue: "work_at_height"}

EVENT_TYPES: dict[EventType, tuple[str, str]] = {
    **{EventType(k.value): v for k, v in SCENARIOS.items()},
    EventType.false_alarm: ("False alarm", "إنذار كاذب"),
    EventType.airport_aep_activation: ("Airport AEP activation", "تفعيل خطة طوارئ المطار"),
}
# EV-4: event types that need a Phase 1 incident before review
INCIDENT_REQUIRED = frozenset(
    {
        EventType.fire_explosion, EventType.medical_emergency, EventType.structural_collapse,
        EventType.excavation_collapse, EventType.gas_release, EventType.electrical_contact,
        EventType.utility_strike, EventType.confined_space_rescue, EventType.height_rescue,
    }
)  # fmt: skip
FIRST_RESPONDER_TYPES = frozenset(
    {EventType.medical_emergency, EventType.confined_space_rescue, EventType.height_rescue}
)

RESPONSES: dict[ResponseType, tuple[str, str]] = {
    ResponseType.zone_evacuation: ("Zone evacuation", "إخلاء منطقة"),
    ResponseType.site_evacuation: ("Site evacuation", "إخلاء الموقع"),
    ResponseType.shelter_in_place: ("Shelter in place", "الاحتماء في المكان"),
    ResponseType.local_response: ("Local response", "استجابة موضعية"),
    ResponseType.none: ("None", "لا شيء"),
}
MUSTER_RESPONSES = frozenset(
    {ResponseType.zone_evacuation, ResponseType.site_evacuation, ResponseType.shelter_in_place}
)

# DT: (EN, AR, minimum months or None, scope, required timings)
TL_EVAC = ("alarm_at", "evacuation_complete_at", "headcount_complete_at", "all_clear_at")
TL_RESCUE = ("alarm_at", "casualty_reached_at", "casualty_recovered_at")
DRILL_TYPES: dict[DrillType, tuple[str, str, int | None, str, tuple[str, ...]]] = {
    DT.evacuation_full: ("Full site evacuation", "إخلاء كامل للموقع", 6, "site", TL_EVAC),
    DT.evacuation_partial: ("Partial evacuation", "إخلاء جزئي", None, "site", TL_EVAC),
    DT.shelter_in_place: ("Shelter in place", "احتماء في المكان", 12, "site",
                          ("alarm_at", "headcount_complete_at", "all_clear_at")),
    DT.medical_response: ("Medical response", "استجابة طبية", 6, "site",
                          ("alarm_at", "first_responder_at", "all_clear_at")),
    DT.cse_rescue: ("Confined space rescue", "إنقاذ من مكان محصور", 12, "team", TL_RESCUE),
    DT.height_rescue: ("Rescue from height", "إنقاذ من ارتفاع", 12, "team", TL_RESCUE),
    DT.tabletop: ("Tabletop exercise", "تمرين مكتبي", 12, "project", ()),
    DT.airport_exercise: ("Airport exercise", "تمرين المطار", 12, "project",
                          ("alarm_at", "all_clear_at")),
}  # fmt: skip
EVAC_TYPES = frozenset({DT.evacuation_full, DT.evacuation_partial})
MUSTER_TYPES = frozenset({DT.evacuation_full, DT.evacuation_partial, DT.shelter_in_place})
TEAM_TYPES = {DT.cse_rescue: TeamType.confined_space, DT.height_rescue: TeamType.height}
NIGHT_MINIMUM_MONTHS = 12  # DT: evacuation_full with shift night every 12 months per site
UNANNOUNCED_MINIMUM_MONTHS = 12  # DT: evacuation_full unannounced every 12 months per site

AGENCIES: dict[Agency, tuple[str, str, str | None]] = {
    Agency.civil_defense: ("Civil Defense", "الدفاع المدني", "998"),
    Agency.red_crescent: ("Saudi Red Crescent", "الهلال الأحمر", "997"),
    Agency.police: ("Police", "الشرطة", "999"),
    Agency.unified_911: ("Unified emergency number", "الرقم الموحد", "911"),
    Agency.airport_arff: ("Airport ARFF", "إنقاذ ومكافحة حرائق الطائرات", None),
    Agency.airport_aocc: ("Airport operations centre", "مركز عمليات المطار", None),
    Agency.airport_security: ("Airport security", "أمن المطار", None),
    Agency.site_clinic: ("Site clinic", "عيادة الموقع", None),
    Agency.hospital: ("Hospital", "المستشفى", None),
    Agency.client_emergency: ("Client emergency", "طوارئ العميل", None),
    Agency.electricity_utility: ("Electricity utility", "شركة الكهرباء", "933"),
    Agency.water_utility: ("Water utility", "شركة المياه", "939"),
    Agency.other: ("Other", "أخرى", None),
}

ROLES: dict[EmergencyRole, tuple[str, str, str | None]] = {
    EmergencyRole.emergency_coordinator: ("Emergency coordinator", "منسق الطوارئ", None),
    EmergencyRole.fire_warden: ("Fire warden", "مسؤول إخلاء/حريق", "FIRE-WARDEN"),
    EmergencyRole.first_aider: ("First aider", "مسعف أولي", "FIRST-AID"),
    EmergencyRole.assembly_marshal: ("Assembly marshal", "مسؤول نقطة التجمع", None),
}
MATRIX_ROLE = {EmergencyRole.fire_warden: "fire_warden", EmergencyRole.first_aider: "first_aider"}
TEAM_CODE = {TeamType.confined_space: "CSE-RESCUE", TeamType.height: "WAH-RESCUE"}

ALL_ITEMS = (EC.EC01, EC.EC02, EC.EC04, EC.EC10)
# EAT: (EN, AR, check interval days, service months or None, EC items answered)
ASSET_TYPES: dict[AssetType, tuple[str, str, int, int | None, tuple[CheckItem, ...]]] = {
    AT.fire_extinguisher: ("Fire extinguisher", "طفاية حريق", 30, 12,
                           (*ALL_ITEMS, EC.EC03, EC.EC09)),
    AT.fire_blanket: ("Fire blanket", "بطانية حريق", 30, None, ALL_ITEMS),
    AT.hose_reel: ("Hose reel", "بكرة خرطوم", 30, 12, (*ALL_ITEMS, EC.EC09)),
    AT.alarm_call_point: ("Alarm call point", "نقطة إنذار يدوية", 7, None, (*ALL_ITEMS, EC.EC08)),
    AT.alarm_panel_temporary: ("Temporary alarm panel", "لوحة إنذار مؤقتة", 7, 12,
                               (*ALL_ITEMS, EC.EC08, EC.EC09)),
    AT.siren_air_horn: ("Siren / air horn", "صافرة إنذار", 7, None, (*ALL_ITEMS, EC.EC08)),
    AT.emergency_lighting: ("Emergency lighting", "إنارة طوارئ", 30, 12,
                            (*ALL_ITEMS, EC.EC08, EC.EC09)),
    AT.first_aid_kit: ("First-aid kit", "حقيبة إسعافات أولية", 7, None, (*ALL_ITEMS, EC.EC05)),
    AT.first_aid_room: ("First-aid room", "غرفة إسعاف", 30, None, (*ALL_ITEMS, EC.EC05)),
    AT.aed: ("AED", "جهاز إزالة الرجفان", 30, None, (*ALL_ITEMS, EC.EC06)),
    AT.eyewash_plumbed: ("Eyewash station (plumbed)", "محطة غسيل العين الثابتة", 7, None,
                         (*ALL_ITEMS, EC.EC07)),
    AT.eyewash_portable: ("Eyewash station (portable)", "محطة غسيل العين المتنقلة", 30, None,
                          (*ALL_ITEMS, EC.EC07)),
    AT.safety_shower: ("Safety shower", "دش الطوارئ", 7, None, (*ALL_ITEMS, EC.EC07)),
    AT.stretcher: ("Stretcher", "نقالة", 30, None, ALL_ITEMS),
    AT.rescue_kit_height: ("Height rescue kit", "حقيبة إنقاذ من ارتفاع", 30, 12,
                           (*ALL_ITEMS, EC.EC05, EC.EC09)),
    AT.escape_breathing_set: ("Escape breathing set", "جهاز تنفس للهروب", 30, 12,
                              (*ALL_ITEMS, EC.EC09)),
}  # fmt: skip
SERVICE_REQUIRED = frozenset(
    {AT.fire_extinguisher, AT.hose_reel, AT.alarm_panel_temporary, AT.emergency_lighting}
)
FIRE_TYPES = frozenset({AT.fire_extinguisher, AT.hose_reel, AT.alarm_panel_temporary})
EXPIRY_REQUIRED: dict[AssetType, tuple[str, ...]] = {
    AT.aed: ("pads", "battery"),
    AT.eyewash_portable: ("eyewash_fluid",),
}
# §6.3 hydrostatic test interval (years) by extinguisher subtype (VERIFY R7)
HYDROTEST_YEARS = {"co2": 5, "water": 5, "foam": 5, "dcp_abc": 12, "clean_agent": 12}
EYEWASH = frozenset({AT.eyewash_plumbed, AT.eyewash_portable})

CHECK_ITEMS: dict[CheckItem, tuple[str, str, bool]] = {
    EC.EC01: ("Present at the marked location and unobstructed", "موجودة في مكانها المحدد وغير معاقة", True),
    EC.EC02: ("Signage visible", "اللافتة واضحة", False),
    EC.EC03: ("Seal and tamper indicator intact, gauge in the operable range", "الختم سليم والمؤشر ضمن النطاق", True),
    EC.EC04: ("No damage, corrosion or leakage", "لا يوجد تلف أو صدأ أو تسرب", True),
    EC.EC05: ("Contents complete and in date", "المحتويات كاملة وصالحة", True),
    EC.EC06: ("Status indicator OK, pads and battery in date", "مؤشر الحالة سليم والأقطاب والبطارية صالحة", True),
    EC.EC07: ("Activated, flow clear and adequate", "تم التشغيل والتدفق نظيف وكافٍ", True),
    EC.EC08: ("Tested and working", "تم الاختبار ويعمل", True),
    EC.EC09: ("Inspection tag dated and signed", "بطاقة الفحص مؤرخة وموقعة", False),
    EC.EC10: ("Access path clear and lit", "طريق الوصول خالٍ ومضاء", False),
}  # fmt: skip
CRITICAL_ITEMS = frozenset(k for k, v in CHECK_ITEMS.items() if v[2])

EVAC_DC = (DC.DC01, DC.DC02, DC.DC03, DC.DC04, DC.DC05, DC.DC06, DC.DC07, DC.DC08, DC.DC11,
           DC.DC12)  # fmt: skip
RESCUE_DC = (DC.DC08, DC.DC09, DC.DC10)
CRITERIA: dict[Criterion, tuple[str, str, bool]] = {
    DC.DC01: ("Alarm heard / seen in every zone", "سُمع/شوهد الإنذار في كل منطقة", True),
    DC.DC02: ("Wardens swept their zones and reported clear", "مسح مسؤولو الإخلاء مناطقهم وأبلغوا بخلوها", True),
    DC.DC03: ("Escape routes clear and signed", "طرق الهروب خالية ومعلّمة", False),
    DC.DC04: ("Hot work, plant and lifting made safe; permits suspended", "تأمين الأعمال الساخنة والمعدات والرفع وإيقاف التصاريح", True),
    DC.DC05: ("Workers went to the correct assembly point", "توجه العمال إلى نقطة التجمع الصحيحة", False),
    DC.DC06: ("Assembly-point signage and capacity adequate", "لافتات وسعة نقطة التجمع كافية", False),
    DC.DC07: ("Headcount method worked", "نجحت طريقة الحصر", False),
    DC.DC08: ("Emergency call made or simulated with correct information", "تم الاتصال بالطوارئ بمعلومات صحيحة", False),
    DC.DC09: ("First responder arrived with kit (and AED)", "وصل المسعف الأول بالحقيبة (وجهاز الرجفان)", True),
    DC.DC10: ("Rescue equipment available, serviceable and used correctly", "معدات الإنقاذ متاحة وصالحة واستخدمت بشكل صحيح", True),
    DC.DC11: ("Airside: movement area left as instructed, ARFF routes clear", "الجانب الجوي: إخلاء منطقة الحركة وإبقاء طرق الإطفاء خالية", True),
    DC.DC12: ("Visitors and persons needing help were assisted", "تمت مساعدة الزوار ومن يحتاج المساعدة", False),
}  # fmt: skip
CRITICAL_CRITERIA = frozenset(k for k, v in CRITERIA.items() if v[2])
RELEVANT_DC: dict[DrillType, tuple[Criterion, ...]] = {
    DT.evacuation_full: EVAC_DC,
    DT.evacuation_partial: EVAC_DC,
    DT.shelter_in_place: (DC.DC01, DC.DC02, DC.DC07, DC.DC08, DC.DC12),
    DT.medical_response: (DC.DC08, DC.DC09, DC.DC12),
    DT.cse_rescue: RESCUE_DC,
    DT.height_rescue: RESCUE_DC,
    DT.tabletop: (),
    DT.airport_exercise: (DC.DC01, DC.DC08, DC.DC11),
}

FINDINGS: dict[FindingCategory, tuple[str, str]] = {
    FindingCategory.plan_deficiency: ("Plan deficiency", "خلل في الخطة"),
    FindingCategory.training_competence: ("Training / competence", "التدريب والكفاءة"),
    FindingCategory.equipment: ("Equipment", "المعدات"),
    FindingCategory.communication: ("Communication", "الاتصال"),
    FindingCategory.route_infrastructure: ("Routes / infrastructure", "الطرق والبنية"),
    FindingCategory.behaviour: ("Behaviour", "السلوك"),
    FindingCategory.external_coordination: ("External coordination", "التنسيق الخارجي"),
}
ENTRY_STATES: dict[EntryState, tuple[str, str]] = {
    EntryState.expected: ("Expected", "متوقع"),
    EntryState.accounted: ("Accounted", "حاضر"),
    EntryState.unaccounted: ("Unaccounted", "غير محصور"),
    EntryState.resolved: ("Resolved", "تمت التسوية"),
}
RESOLUTIONS: dict[ResolutionReason, tuple[str, str]] = {
    ResolutionReason.left_site_no_exit_scan: ("Left without exit scan", "غادر دون تسجيل خروج"),
    ResolutionReason.off_site_confirmed: ("Off site (confirmed)", "خارج الموقع (مؤكد)"),
    ResolutionReason.found_on_site: ("Found on site", "وُجد داخل الموقع"),
    ResolutionReason.with_emergency_team: ("With the emergency team", "مع فريق الطوارئ"),
    ResolutionReason.record_error: ("Record error", "خطأ في السجل"),
}
