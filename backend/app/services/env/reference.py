"""Phase 6e reference lists (spec 6e-environmental §3.17) with EN/AR labels, the WS stream table,
the DL limit library and the NA noise limits. Codes are immutable; labels feed GET /env-reference
and the AR texts of alerts and errors (AC58)."""

from __future__ import annotations

from decimal import Decimal

from app.core.env_enums import (
    AspectCode,
    Averaging,
    ExceedanceCause,
    ImpactCode,
    InstrumentKind,
    Issuer,
    LicenceActivity,
    NoiseArea,
    Parameter,
    PermitType,
    PointKind,
    ProviderKind,
    SpillSubstance,
    StorageAreaType,
    WasteClass,
    WasteRoute,
)

D = Decimal
WC = WasteClass
TR = WasteRoute

AS_LABELS = {
    AspectCode.dust_emission: ("Dust emission", "انبعاث الغبار"),
    AspectCode.exhaust_emission: ("Exhaust emission", "عوادم"),
    AspectCode.noise_vibration: ("Noise and vibration", "ضوضاء واهتزاز"),
    AspectCode.waste_generation: ("Waste generation", "توليد النفايات"),
    AspectCode.hazardous_material_storage: ("Hazardous material storage", "تخزين المواد الخطرة"),
    AspectCode.fuel_spill_risk: ("Fuel spill risk", "خطر انسكاب الوقود"),
    AspectCode.wastewater_discharge: ("Wastewater discharge", "تصريف المياه"),
    AspectCode.water_consumption: ("Water consumption", "استهلاك المياه"),
    AspectCode.land_disturbance: ("Land disturbance", "تعرية التربة"),
    AspectCode.wildlife_attraction: ("Wildlife attraction", "جذب الحياة البرية"),
    AspectCode.fod_generation: ("FOD generation", "توليد الأجسام الغريبة"),
    AspectCode.light_spill: ("Light spill", "التلوث الضوئي"),
    AspectCode.odour: ("Odour", "الروائح"),
}
IM_LABELS = {
    ImpactCode.air_quality: ("Air quality", "جودة الهواء"),
    ImpactCode.community_nuisance: ("Community nuisance", "إزعاج المجتمع"),
    ImpactCode.soil_contamination: ("Soil contamination", "تلوث التربة"),
    ImpactCode.groundwater_contamination: ("Groundwater contamination", "تلوث المياه الجوفية"),
    ImpactCode.resource_depletion: ("Resource depletion", "استنزاف الموارد"),
    ImpactCode.aviation_safety: ("Aviation safety", "سلامة الطيران"),
    ImpactCode.ecology: ("Ecology", "البيئة الطبيعية"),
    ImpactCode.climate: ("Climate", "المناخ"),
}
# PT: (EN, AR, holder "project" / "provider" / "either", expires)
PT_INFO = {
    PermitType.ncec_env_permit_construction: ("NCEC environmental permit (construction)",
                                              "تصريح بيئي للإنشاء", "project", True),
    PermitType.ncec_env_permit_operation: ("NCEC environmental permit (operation)",
                                           "تصريح بيئي للتشغيل", "project", True),
    PermitType.eia_approval: ("EIA approval", "موافقة دراسة الأثر البيئي", "project", False),
    PermitType.mwan_producer_registration: ("MWAN waste producer registration",
                                            "تسجيل منتج النفايات", "project", True),
    PermitType.municipal_construction_permit: ("Municipal construction permit",
                                               "رخصة البناء البلدية", "project", True),
    PermitType.dewatering_discharge_permit: ("Dewatering discharge permit",
                                             "تصريح تصريف مياه نزح", "project", True),
    PermitType.sewer_discharge_permit: ("Sewer discharge permit", "تصريح تصريف للصرف الصحي",
                                        "project", True),
    PermitType.cemp_approval: ("CEMP approval", "اعتماد خطة الإدارة البيئية", "project", False),
    PermitType.mwan_licence: ("MWAN licence", "ترخيص موان", "provider", True),
    PermitType.facility_authorisation: ("Facility authorisation", "تفويض منشأة", "provider", True),
    PermitType.lab_accreditation: ("Laboratory accreditation", "اعتماد مختبر", "provider", True),
    PermitType.other: ("Other", "أخرى", "either", False),
}  # fmt: skip
IS_LABELS = {
    Issuer.ncec: ("NCEC", "المركز الوطني للرقابة على الالتزام البيئي"),
    Issuer.mwan: ("MWAN", "المركز الوطني لإدارة النفايات"),
    Issuer.momrah_municipality: ("Municipality", "البلدية"),
    Issuer.nwc: ("NWC", "شركة المياه الوطنية"),
    Issuer.mewa: ("MEWA", "وزارة البيئة والمياه والزراعة"),
    Issuer.airport_operator: ("Airport operator", "مشغل المطار"),
    Issuer.gaca: ("GACA", "الهيئة العامة للطيران المدني"),
    Issuer.client: ("Client", "العميل"),
    Issuer.saac: ("SAAC", "المركز السعودي للاعتماد"),
    Issuer.other: ("Other", "أخرى"),
}
PK_LABELS = {
    ProviderKind.transporter: ("Transporter", "ناقل"),
    ProviderKind.recycler: ("Recycler", "منشأة تدوير"),
    ProviderKind.treatment_facility: ("Treatment facility", "منشأة معالجة"),
    ProviderKind.landfill: ("Landfill", "مردم"),
    ProviderKind.sewage_tanker: ("Sewage tanker", "صهريج صرف صحي"),
    ProviderKind.environmental_lab: ("Environmental laboratory", "مختبر بيئي"),
}
LA_LABELS = {
    LicenceActivity.collection_transport: ("Collection and transport", "الجمع والنقل"),
    LicenceActivity.storage: ("Storage", "التخزين"),
    LicenceActivity.sorting: ("Sorting", "الفرز"),
    LicenceActivity.treatment: ("Treatment", "المعالجة"),
    LicenceActivity.recycling: ("Recycling", "التدوير"),
    LicenceActivity.disposal: ("Disposal", "التخلص"),
}
WC_LABELS = {
    WC.inert: ("Inert", "خاملة"),
    WC.non_hazardous: ("Non-hazardous", "غير خطرة"),
    WC.hazardous: ("Hazardous", "خطرة"),
    WC.liquid_sewage: ("Liquid / sewage", "سائلة / صرف صحي"),
}
TR_LABELS = {
    TR.reuse: ("Reuse", "إعادة استخدام"),
    TR.recycle: ("Recycle", "تدوير"),
    TR.recovery: ("Recovery", "استرداد"),
    TR.treatment: ("Treatment", "معالجة"),
    TR.disposal_landfill: ("Landfill", "طمر"),
}
DIVERTED = frozenset({TR.reuse, TR.recycle, TR.recovery})
# TR → facility licence activities accepted
ROUTE_ACTIVITY: dict[WasteRoute, frozenset[str]] = {
    TR.reuse: frozenset({"recycling"}),
    TR.recycle: frozenset({"recycling"}),
    TR.recovery: frozenset({"recycling", "treatment"}),
    TR.treatment: frozenset({"treatment"}),
    TR.disposal_landfill: frozenset({"disposal"}),
}

# WS: code → (EN, AR, class, default route, density, wildlife attractant). Liquids (kg/L): used_oil
# and paint_solvent. Sewage is m³ only (density 1.00 placeholder, never used for tonnes).
WS: dict[str, tuple[str, str, WasteClass, WasteRoute, Decimal, bool]] = {
    "inert_cd": ("Inert C&D waste", "مخلفات بناء وهدم خاملة", WC.inert, TR.recycle, D("1.50"),
                 False),
    "asphalt_planings": ("Asphalt planings", "كشط أسفلت", WC.inert, TR.recycle, D("1.40"), False),
    "surplus_excavated_soil": ("Surplus excavated soil", "فائض تربة", WC.inert,
                               TR.disposal_landfill, D("1.60"), False),
    "metal_scrap": ("Metal scrap", "خردة معدنية", WC.non_hazardous, TR.recycle, D("0.50"), False),
    "wood": ("Wood", "أخشاب", WC.non_hazardous, TR.recycle, D("0.25"), False),
    "packaging": ("Paper and plastic packaging", "تغليف ورق وبلاستيك", WC.non_hazardous,
                  TR.recycle, D("0.10"), False),
    "general_mixed": ("General mixed waste", "نفايات عامة مختلطة", WC.non_hazardous,
                      TR.disposal_landfill, D("0.30"), False),
    "food_domestic": ("Food and domestic waste", "نفايات طعام ومنزلية", WC.non_hazardous,
                      TR.disposal_landfill, D("0.35"), True),
    "used_oil": ("Used oil", "زيوت مستعملة", WC.hazardous, TR.recovery, D("0.90"), False),
    "oily_absorbents": ("Oily absorbents", "مواد ماصة ملوثة", WC.hazardous, TR.treatment,
                        D("0.40"), False),
    "chemical_containers": ("Empty chemical containers", "عبوات كيميائية فارغة", WC.hazardous,
                            TR.treatment, D("0.10"), False),
    "paint_solvent": ("Paints and solvents", "دهانات ومذيبات", WC.hazardous, TR.treatment,
                      D("1.00"), False),
    "batteries": ("Batteries", "بطاريات", WC.hazardous, TR.recycle, D("1.20"), False),
    "e_waste": ("E-waste", "نفايات إلكترونية", WC.hazardous, TR.recycle, D("0.20"), False),
    "contaminated_soil": ("Contaminated soil", "تربة ملوثة", WC.hazardous, TR.treatment,
                          D("1.60"), False),
    "clinical_first_aid": ("Clinic first-aid waste", "نفايات طبية من العيادة", WC.hazardous,
                           TR.treatment, D("0.10"), False),
    "sewage": ("Sewage", "صرف صحي", WC.liquid_sewage, TR.treatment, D("1.00"), False),
}  # fmt: skip
LIQUID_KG_L = frozenset({"used_oil", "paint_solvent"})
CLEANUP_STREAMS = frozenset({"oily_absorbents", "contaminated_soil"})

SA_LABELS = {
    StorageAreaType.skip: ("Open skip", "حاوية مفتوحة"),
    StorageAreaType.segregated_bay: ("Segregated bays", "حجيرات فرز"),
    StorageAreaType.hazardous_store: ("Hazardous waste store", "مخزن نفايات خطرة"),
    StorageAreaType.liquid_store: ("Bunded liquid store", "مخزن سوائل بحوض احتواء"),
    StorageAreaType.compactor: ("Compactor", "كابسة"),
    StorageAreaType.sealed_bin_station: ("Sealed bin station", "محطة حاويات محكمة"),
}
HAZ_STORES = frozenset({StorageAreaType.hazardous_store, StorageAreaType.liquid_store})
AIRSIDE_OK = frozenset(
    {StorageAreaType.sealed_bin_station, StorageAreaType.hazardous_store,
     StorageAreaType.liquid_store}
)  # fmt: skip
ATTRACTANT_OK = frozenset({StorageAreaType.sealed_bin_station, StorageAreaType.compactor})

IK_LABELS = {
    InstrumentKind.pm_station: ("Particulate station", "محطة جسيمات"),
    InstrumentKind.pm_portable: ("Portable particulate meter", "جهاز جسيمات محمول"),
    InstrumentKind.pm_sampler_24h: ("24-hour sampler", "جهاز سحب عينات 24 ساعة"),
    InstrumentKind.sound_level_meter: ("Sound level meter", "مقياس مستوى الصوت"),
    InstrumentKind.noise_station: ("Noise station", "محطة ضوضاء"),
    InstrumentKind.water_quality_meter: ("Water quality meter", "جهاز جودة المياه"),
}
STATION_KINDS = frozenset({InstrumentKind.pm_station, InstrumentKind.noise_station})
MPK_LABELS = {
    PointKind.boundary: ("Site boundary", "حدود الموقع"),
    PointKind.sensitive_receptor: ("Sensitive receptor", "مستقبِل حساس"),
    PointKind.airside: ("Airside", "الجانب الجوي"),
    PointKind.background_upwind: ("Upwind background", "نقطة خلفية"),
    PointKind.discharge: ("Discharge point", "نقطة تصريف"),
    PointKind.work_area: ("Work area", "منطقة العمل"),
}
# PA: code → (EN, AR, unit, min, max)
PA: dict[Parameter, tuple[str, str, str, Decimal, Decimal]] = {
    Parameter.pm10: ("PM10", "الجسيمات PM10", "µg/m³", D(0), D(20000)),
    Parameter.pm2_5: ("PM2.5", "الجسيمات PM2.5", "µg/m³", D(0), D(10000)),
    Parameter.visual_dust: ("Visual dust score", "درجة الغبار المرئي", "score", D(0), D(3)),
    Parameter.laeq: ("LAeq", "مستوى الضوضاء LAeq", "dB(A)", D(20), D(140)),
    Parameter.ph: ("pH", "الأس الهيدروجيني", "", D(0), D(14)),
    Parameter.tss: ("TSS", "المواد الصلبة العالقة", "mg/L", D(0), D(100000)),
    Parameter.oil_grease: ("Oil and grease", "الزيوت والشحوم", "mg/L", D(0), D(10000)),
    Parameter.turbidity: ("Turbidity", "العكارة", "NTU", D(0), D(10000)),
}
DUST_PARAMS = frozenset({Parameter.pm10, Parameter.pm2_5, Parameter.visual_dust})
WATER_PARAMS = frozenset({Parameter.ph, Parameter.tss, Parameter.oil_grease, Parameter.turbidity})
# ASP-3 (a): parameter → aspect flagged on review
PARAM_ASPECT = {
    Parameter.pm10: "dust_emission",
    Parameter.pm2_5: "dust_emission",
    Parameter.visual_dust: "dust_emission",
    Parameter.laeq: "noise_vibration",
    Parameter.ph: "wastewater_discharge",
    Parameter.tss: "wastewater_discharge",
    Parameter.oil_grease: "wastewater_discharge",
    Parameter.turbidity: "wastewater_discharge",
}

# NA: day / night LAeq limits (alert = limit − 3)
NA: dict[NoiseArea, tuple[str, str, Decimal, Decimal]] = {
    NoiseArea.residential: ("Residential", "سكنية", D(55), D(45)),
    NoiseArea.mixed_commercial: ("Mixed / commercial", "مختلطة / تجارية", D(65), D(55)),
    NoiseArea.industrial: ("Industrial", "صناعية", D(70), D(70)),
    NoiseArea.sensitive: ("Sensitive (hospital, school)", "حساسة", D(50), D(40)),
}

# DL: (parameter, averaging) → (alert, limit, limit_min, limit_max, source, ref)
DL: dict[tuple[Parameter, Averaging], tuple[Decimal | None, Decimal | None, Decimal | None,
                                             Decimal | None, str, str]] = {
    (Parameter.pm10, Averaging.h24): (D(250), D(340), None, None, "ncec", "DL-PM10-24H"),
    (Parameter.pm10, Averaging.h1): (D(300), D(500), None, None, "project_trigger", "DL-PM10-1H"),
    (Parameter.pm2_5, Averaging.h24): (D(25), D(35), None, None, "ncec", "DL-PM25-24H"),
    (Parameter.visual_dust, Averaging.spot): (D(2), D(2), None, None, "project_trigger",
                                              "DL-VIS"),
    (Parameter.ph, Averaging.spot): (None, None, D("6.0"), D("9.0"), "permit_condition", "DL-PH"),
    (Parameter.tss, Averaging.spot): (None, D(50), None, None, "permit_condition", "DL-TSS"),
    (Parameter.oil_grease, Averaging.spot): (None, D(10), None, None, "permit_condition",
                                             "DL-OG"),
}  # fmt: skip

SS_LABELS = {
    SpillSubstance.diesel: ("Diesel", "ديزل"),
    SpillSubstance.petrol: ("Petrol", "بنزين"),
    SpillSubstance.hydraulic_oil: ("Hydraulic oil", "زيت هيدروليكي"),
    SpillSubstance.engine_oil: ("Engine oil", "زيت محرك"),
    SpillSubstance.bitumen_emulsion: ("Bitumen emulsion", "مستحلب بيتوميني"),
    SpillSubstance.paint: ("Paint", "دهان"),
    SpillSubstance.solvent: ("Solvent", "مذيب"),
    SpillSubstance.concrete_washout: ("Concrete washout", "مياه غسيل الخرسانة"),
    SpillSubstance.sewage: ("Sewage", "صرف صحي"),
    SpillSubstance.chemical_other: ("Other chemical", "مادة كيميائية أخرى"),
    SpillSubstance.other: ("Other", "أخرى"),
}
EC_LABELS = {
    ExceedanceCause.project_activity: ("Project activity", "نشاط المشروع"),
    ExceedanceCause.background_natural: ("Natural background", "غبار طبيعي/خلفية"),
    ExceedanceCause.third_party: ("Third party", "طرف ثالث"),
    ExceedanceCause.instrument_fault: ("Instrument fault", "عطل الجهاز"),
    ExceedanceCause.unknown: ("Unknown", "غير معروف"),
}


def stream_label(code: str) -> tuple[str, str]:
    x = WS.get(code)
    return (x[0], x[1]) if x else (code, code)


def stream_class(code: str) -> WasteClass:
    return WS[code][2]


def unit_of(p: Parameter) -> str:
    return PA[p][2]


SS_LABELS_BY_CODE = {k.value: v for k, v in SS_LABELS.items()}
