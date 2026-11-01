"""Enumerations of package Q3 logistics: receiving, storage and cold chain, stock, recalls,
transport (spec 8-quality Part D), the storage-class defaults (list SCL, §D.1.2) and the EN / AR
labels of every Q3 list (merged into `app.core.quality.common.LABELS` by `q3.register()`, D-327).

Owned by Q3 (stub created by Q0, §3.3a)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

D = Decimal


# ---- storage classes (list SCL, §D.1.2) ----------------------------------------------------------


class QStorageClass(StrEnum):
    frozen = "frozen"
    chilled = "chilled"
    pharma_2_8 = "pharma_2_8"
    ambient_controlled = "ambient_controlled"
    dry = "dry"
    dock_controlled = "dock_controlled"


RH_BAND_1 = Decimal(5)  # %RH beyond the limit: minor up to here
RH_BAND_2 = Decimal(15)  # major up to here, critical beyond


@dataclass(frozen=True)
class StorageClassDef:
    """Defaults copied into a storage zone (Q-STO-01) and used for transit compartments."""

    code: QStorageClass
    temp_min: Decimal | None
    temp_max: Decimal | None
    alarm_delay: int
    d1: Decimal
    d2: Decimal
    t1: int
    t2: int
    humidity_max: Decimal | None
    dispatch_override_allowed: bool
    # relative-humidity deviation bands in %RH for humidity excursions (D-352); the duration
    # bands t1 / t2 and the alarm delay are the class's own
    h1: Decimal = RH_BAND_1
    h2: Decimal = RH_BAND_2


SC = QStorageClass
STORAGE_CLASSES: dict[QStorageClass, StorageClassDef] = {
    SC.frozen: StorageClassDef(SC.frozen, D(-30), D(-18), 30, D(3), D(6), 120, 480, None, True),
    SC.chilled: StorageClassDef(SC.chilled, D(0), D(4), 15, D(2), D(5), 60, 240, None, True),
    SC.pharma_2_8: StorageClassDef(SC.pharma_2_8, D(2), D(8), 10, D(1), D(3), 30, 120, None, False),
    SC.ambient_controlled: StorageClassDef(
        SC.ambient_controlled, D(15), D(25), 30, D(3), D(7), 240, 1440, D(65), True
    ),
    SC.dry: StorageClassDef(SC.dry, None, D(30), 60, D(3), D(7), 480, 2880, D(65), True),
    SC.dock_controlled: StorageClassDef(
        SC.dock_controlled, D(8), D(15), 30, D(3), D(6), 60, 240, None, True
    ),
}
TEMP_CONTROLLED = frozenset({SC.frozen, SC.chilled, SC.pharma_2_8, SC.dock_controlled})
MKT_CLASSES = frozenset({SC.ambient_controlled, SC.pharma_2_8})
# Q-TRN-01: classes that cannot share one compartment (frozen with chilled; medicines with food)
FOOD_CLASSES = frozenset({SC.frozen, SC.chilled, SC.ambient_controlled, SC.dry})


def incompatible(a: QStorageClass, b: QStorageClass) -> bool:
    pair = {a, b}
    if pair == {SC.frozen, SC.chilled}:
        return True
    return SC.pharma_2_8 in pair and bool(pair & FOOD_CLASSES)


# ---- zones, points, readings, imports ------------------------------------------------------------


class QZoneRole(StrEnum):
    storage = "storage"
    quarantine = "quarantine"
    dock = "dock"


class QMappingState(StrEnum):
    mapped = "mapped"
    not_mapped = "not_mapped"
    remap_required = "remap_required"


class QPointPosition(StrEnum):
    hot_spot = "hot_spot"
    cold_spot = "cold_spot"
    general = "general"


class QReadingTarget(StrEnum):
    point = "point"
    trip = "trip"
    mapping_study = "mapping_study"
    receipt = "receipt"  # inbound trip logger file of a receipt (§D.2 transit_data)


class QReadingSource(StrEnum):
    manual = "manual"
    import_ = "import"


class QImportKind(StrEnum):
    readings = "readings"
    stock_snapshot = "stock_snapshot"
    shipments = "shipments"
    products = "products"
    cycle_count = "cycle_count"


class QImportStatus(StrEnum):
    imported = "imported"
    refused = "refused"
    voided = "voided"


class QImportTarget(StrEnum):
    point = "point"
    trip = "trip"
    mapping_study = "mapping_study"
    receipt = "receipt"
    site = "site"


# ---- excursions ----------------------------------------------------------------------------------


class QExcursionKind(StrEnum):
    storage = "storage"
    transit = "transit"
    humidity = "humidity"


class QExcursionSeverity(StrEnum):
    minor = "minor"
    major = "major"
    critical = "critical"


SEVERITY_RANK = {
    QExcursionSeverity.minor: 0,
    QExcursionSeverity.major: 1,
    QExcursionSeverity.critical: 2,
}


class QExcursionCause(StrEnum):
    door_open = "door_open"
    defrost = "defrost"
    power_failure = "power_failure"
    equipment_failure = "equipment_failure"
    overload = "overload"
    loading_delay = "loading_delay"
    probe_fault = "probe_fault"
    unknown = "unknown"
    other = "other"


class QExcursionStatus(StrEnum):
    detected = "detected"
    under_assessment = "under_assessment"
    assessed = "assessed"
    closed = "closed"
    dismissed = "dismissed"
    voided = "voided"  # D-352: the run vanished after a batch void (Q-IMP-05)


EXCURSION_LIVE = frozenset(
    {QExcursionStatus.detected, QExcursionStatus.under_assessment, QExcursionStatus.assessed}
)


class QImpactDecision(StrEnum):
    release = "release"
    extend_hold = "extend_hold"
    destroy = "destroy"
    return_to_owner = "return_to_owner"


# ---- mapping -------------------------------------------------------------------------------------


class QMappingPurpose(StrEnum):
    initial = "initial"
    periodic = "periodic"
    after_change = "after_change"


class QSeason(StrEnum):
    summer = "summer"
    winter = "winter"
    n_a = "n_a"


class QLoadState(StrEnum):
    empty = "empty"
    loaded = "loaded"


class QMappingStatus(StrEnum):
    draft = "draft"
    data_loaded = "data_loaded"
    evaluated = "evaluated"
    approved = "approved"
    rejected = "rejected"


class QTestWindowKind(StrEnum):
    door_open = "door_open"
    power_off = "power_off"
    other = "other"


# ---- hygiene and pest ----------------------------------------------------------------------------


class QCheckFrequency(StrEnum):
    daily = "daily"
    weekly = "weekly"
    fortnightly = "fortnightly"
    monthly = "monthly"


class QCheckType(StrEnum):
    hygiene = "hygiene"
    pest_visit = "pest_visit"


class QPestStationType(StrEnum):
    rodent_bait = "rodent_bait"
    rodent_trap = "rodent_trap"
    insect_light_trap = "insect_light_trap"
    glue_board = "glue_board"
    pheromone_trap = "pheromone_trap"
    bird_deterrent = "bird_deterrent"


class QPestActivity(StrEnum):
    none = "none"
    low = "low"
    medium = "medium"
    high = "high"


class QPestType(StrEnum):
    rodent = "rodent"
    cockroach = "cockroach"
    stored_product_insect = "stored_product_insect"
    flying_insect = "flying_insect"
    bird = "bird"
    other = "other"


# ---- receiving -----------------------------------------------------------------------------------


class QReceiptStatus(StrEnum):
    draft = "draft"
    inspected = "inspected"
    decided = "decided"
    cancelled = "cancelled"


class QLineCondition(StrEnum):
    good = "good"
    damaged = "damaged"
    wet = "wet"
    crushed = "crushed"
    leaking = "leaking"
    pest_signs = "pest_signs"


QUARANTINE_CONDITIONS = frozenset(
    {QLineCondition.damaged, QLineCondition.leaking, QLineCondition.pest_signs}
)


class QLineDecision(StrEnum):
    """List RD (§D.2), best first."""

    accept = "accept"
    accept_with_deviation = "accept_with_deviation"
    quarantine = "quarantine"
    reject = "reject"


DECISION_RANK = {
    QLineDecision.accept: 0,
    QLineDecision.accept_with_deviation: 1,
    QLineDecision.quarantine: 2,
    QLineDecision.reject: 3,
}


# ---- stock ---------------------------------------------------------------------------------------


class QFefoResult(StrEnum):
    compliant = "compliant"
    non_compliant = "non_compliant"
    exception = "exception"


class QFefoException(StrEnum):
    customer_allocation = "customer_allocation"
    batch_reserved = "batch_reserved"
    consignee_min_shelf_life = "consignee_min_shelf_life"
    other = "other"


class QHoldReason(StrEnum):
    excursion = "excursion"
    receiving = "receiving"
    damage = "damage"
    expiry = "expiry"
    recall = "recall"
    pest_hygiene = "pest_hygiene"
    owner_request = "owner_request"
    contamination = "contamination"
    other = "other"


class QSegregation(StrEnum):
    moved_to_quarantine = "moved_to_quarantine"
    tagged_in_place = "tagged_in_place"


class QHoldLineStatus(StrEnum):
    on_hold = "on_hold"
    released = "released"
    rejected = "rejected"


class QHoldOutcome(StrEnum):
    destroyed = "destroyed"
    returned_to_owner = "returned_to_owner"
    returned_to_supplier = "returned_to_supplier"


class QHoldStatus(StrEnum):
    on_hold = "on_hold"
    released = "released"
    rejected = "rejected"
    partly_released = "partly_released"
    closed = "closed"
    voided = "voided"  # an automatic hold whose source no longer needs it (D-352)


HOLD_OPEN = frozenset({QHoldStatus.on_hold})


class QDamageStage(StrEnum):
    receiving = "receiving"
    storage = "storage"
    picking = "picking"
    loading = "loading"
    delivery = "delivery"


class QDamageCause(StrEnum):
    forklift = "forklift"
    stacking_crush = "stacking_crush"
    packaging_failure = "packaging_failure"
    temperature = "temperature"
    water = "water"
    pest = "pest"
    other = "other"


class QReturnGrade(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class QReturnStatus(StrEnum):
    draft = "draft"
    graded = "graded"
    confirmed = "confirmed"


# ---- recalls -------------------------------------------------------------------------------------


class QRecallType(StrEnum):
    supplier = "supplier"
    regulator = "regulator"
    owner = "owner"
    mock = "mock"


class QRecallClass(StrEnum):
    I = "I"  # noqa: E741
    II = "II"
    III = "III"


class QRecallStatus(StrEnum):
    open = "open"
    traced = "traced"
    recovering = "recovering"
    closed = "closed"
    cancelled = "cancelled"


# ---- transport -----------------------------------------------------------------------------------


class QTripStatus(StrEnum):
    planned = "planned"
    preload_checked = "preload_checked"
    dispatched = "dispatched"
    delivered = "delivered"
    closed = "closed"
    cancelled = "cancelled"


class QPodException(StrEnum):
    shortage = "shortage"
    damage = "damage"
    temperature = "temperature"
    refused = "refused"
    other = "other"


# ---- labels (D-327) ------------------------------------------------------------------------------

LABELS_Q3: dict[str, dict[str, tuple[str, str]]] = {
    "storage_class": {
        "frozen": ("Frozen", "مجمد"),
        "chilled": ("Chilled", "مبرد"),
        "pharma_2_8": ("Medicines 2–8 °C", "أدوية 2–8 °م"),
        "ambient_controlled": ("Controlled ambient 15–25 °C", "محيط مضبوط 15–25 °م"),
        "dry": ("Dry ambient", "جاف"),
        "dock_controlled": ("Controlled dock", "رصيف مبرد"),
    },
    "zone_role": {
        "storage": ("Storage", "تخزين"),
        "quarantine": ("Quarantine", "عزل"),
        "dock": ("Dock", "رصيف"),
    },
    "mapping_state": {
        "mapped": ("Mapped", "مدروسة"),
        "not_mapped": ("Not mapped", "غير مدروسة"),
        "remap_required": ("Re-mapping required", "تتطلب دراسة جديدة"),
    },
    "point_position": {
        "hot_spot": ("Hot spot", "نقطة ساخنة"),
        "cold_spot": ("Cold spot", "نقطة باردة"),
        "general": ("General", "عامة"),
    },
    "reading_source": {"manual": ("Manual", "يدوي"), "import": ("Logger import", "استيراد مسجل")},
    "import_kind": {
        "readings": ("Logger readings", "قراءات المسجلات"),
        "stock_snapshot": ("Stock snapshot", "لقطة المخزون"),
        "shipments": ("Shipments", "الشحنات"),
        "products": ("Products", "المنتجات"),
        "cycle_count": ("Cycle count", "الجرد الدوري"),
    },
    "import_status": {
        "imported": ("Imported", "مستورد"),
        "refused": ("Refused", "مرفوض"),
        "voided": ("Voided", "ملغى"),
    },
    "excursion_kind": {
        "storage": ("Storage", "تخزين"),
        "transit": ("Transit", "نقل"),
        "humidity": ("Humidity", "رطوبة"),
    },
    "excursion_severity": {
        "minor": ("Minor", "طفيف"),
        "major": ("Major", "جوهري"),
        "critical": ("Critical", "حرج"),
    },
    "excursion_cause": {
        "door_open": ("Door open", "باب مفتوح"),
        "defrost": ("Defrost", "إذابة الجليد"),
        "power_failure": ("Power failure", "انقطاع الكهرباء"),
        "equipment_failure": ("Equipment failure", "عطل المعدات"),
        "overload": ("Overload", "تحميل زائد"),
        "loading_delay": ("Loading delay", "تأخر التحميل"),
        "probe_fault": ("Probe fault", "عطل المجس"),
        "unknown": ("Unknown", "غير معروف"),
        "other": ("Other", "أخرى"),
    },
    "excursion_status": {
        "detected": ("Detected", "مُكتشف"),
        "under_assessment": ("Under assessment", "قيد التقييم"),
        "assessed": ("Assessed", "مُقيَّم"),
        "closed": ("Closed", "مغلق"),
        "dismissed": ("Dismissed", "مستبعد"),
        "voided": ("Voided (data voided)", "ملغى (أُلغيت البيانات)"),
    },
    "impact_decision": {
        "release": ("Release", "إفراج"),
        "extend_hold": ("Extend hold", "تمديد الحجز"),
        "destroy": ("Destroy", "إتلاف"),
        "return_to_owner": ("Return to owner", "إعادة للمالك"),
    },
    "mapping_purpose": {
        "initial": ("Initial", "أولية"),
        "periodic": ("Periodic", "دورية"),
        "after_change": ("After a change", "بعد تغيير"),
    },
    "season": {
        "summer": ("Summer", "صيف"),
        "winter": ("Winter", "شتاء"),
        "n_a": ("N/A", "لا ينطبق"),
    },
    "load_state": {"empty": ("Empty", "فارغ"), "loaded": ("Loaded", "محمّل")},
    "mapping_status": {
        "draft": ("Draft", "مسودة"),
        "data_loaded": ("Data loaded", "تم تحميل البيانات"),
        "evaluated": ("Evaluated", "مُقيَّمة"),
        "approved": ("Approved", "معتمدة"),
        "rejected": ("Rejected", "مرفوضة"),
    },
    "test_window_kind": {
        "door_open": ("Door open", "فتح الباب"),
        "power_off": ("Power off", "فصل الكهرباء"),
        "other": ("Other", "أخرى"),
    },
    "check_frequency": {
        "daily": ("Daily", "يومي"),
        "weekly": ("Weekly", "أسبوعي"),
        "fortnightly": ("Fortnightly", "كل أسبوعين"),
        "monthly": ("Monthly", "شهري"),
    },
    "check_type": {"hygiene": ("Hygiene", "النظافة"), "pest_visit": ("Pest visit", "زيارة آفات")},
    "pest_station_type": {
        "rodent_bait": ("Rodent bait", "طُعم قوارض"),
        "rodent_trap": ("Rodent trap", "مصيدة قوارض"),
        "insect_light_trap": ("Insect light trap", "مصيدة حشرات ضوئية"),
        "glue_board": ("Glue board", "لوح لاصق"),
        "pheromone_trap": ("Pheromone trap", "مصيدة فرمونية"),
        "bird_deterrent": ("Bird deterrent", "طارد طيور"),
    },
    "pest_activity": {
        "none": ("None", "لا يوجد"),
        "low": ("Low", "منخفض"),
        "medium": ("Medium", "متوسط"),
        "high": ("High", "مرتفع"),
    },
    "pest_type": {
        "rodent": ("Rodent", "قوارض"),
        "cockroach": ("Cockroach", "صراصير"),
        "stored_product_insect": ("Stored-product insect", "حشرات المواد المخزنة"),
        "flying_insect": ("Flying insect", "حشرات طائرة"),
        "bird": ("Bird", "طيور"),
        "other": ("Other", "أخرى"),
    },
    "receipt_status": {
        "draft": ("Draft", "مسودة"),
        "inspected": ("Inspected", "تم الفحص"),
        "decided": ("Decided", "مقرر"),
        "cancelled": ("Cancelled", "ملغى"),
    },
    "line_condition": {
        "good": ("Good", "سليم"),
        "damaged": ("Damaged", "تالف"),
        "wet": ("Wet", "مبلل"),
        "crushed": ("Crushed", "مسحوق"),
        "leaking": ("Leaking", "مسرّب"),
        "pest_signs": ("Pest signs", "آثار آفات"),
    },
    "line_decision": {
        "accept": ("Accept", "قبول"),
        "accept_with_deviation": ("Accept with deviation", "قبول مع انحراف"),
        "quarantine": ("Quarantine", "عزل"),
        "reject": ("Reject", "رفض"),
    },
    "fefo_result": {
        "compliant": ("Compliant", "مطابق"),
        "non_compliant": ("Non-compliant", "غير مطابق"),
        "exception": ("Exception", "استثناء"),
    },
    "fefo_exception": {
        "customer_allocation": ("Customer allocation", "تخصيص للعميل"),
        "batch_reserved": ("Batch reserved", "دفعة محجوزة"),
        "consignee_min_shelf_life": ("Consignee minimum shelf life", "حد صلاحية المستلم"),
        "other": ("Other", "أخرى"),
    },
    "hold_reason": {
        "excursion": ("Temperature excursion", "انحراف حراري"),
        "receiving": ("Receiving", "الاستلام"),
        "damage": ("Damage", "تلف"),
        "expiry": ("Expiry", "انتهاء الصلاحية"),
        "recall": ("Recall", "استدعاء"),
        "pest_hygiene": ("Pest or hygiene", "آفات أو نظافة"),
        "owner_request": ("Owner request", "طلب المالك"),
        "contamination": ("Contamination", "تلوث"),
        "other": ("Other", "أخرى"),
    },
    "segregation": {
        "moved_to_quarantine": ("Moved to quarantine", "نُقل إلى العزل"),
        "tagged_in_place": ("Tagged in place", "وُسم في مكانه"),
    },
    "hold_line_status": {
        "on_hold": ("On hold", "محجوز"),
        "released": ("Released", "مُفرج عنه"),
        "rejected": ("Rejected", "مرفوض"),
    },
    "hold_outcome": {
        "destroyed": ("Destroyed", "أُتلف"),
        "returned_to_owner": ("Returned to owner", "أعيد للمالك"),
        "returned_to_supplier": ("Returned to supplier", "أعيد للمورد"),
    },
    "hold_status": {
        "on_hold": ("On hold", "محجوز"),
        "released": ("Released", "مُفرج عنه"),
        "rejected": ("Rejected", "مرفوض"),
        "partly_released": ("Partly released", "مُفرج جزئياً"),
        "closed": ("Closed", "مغلق"),
        "voided": ("Voided (source became a transient)", "ملغى (أصبح المصدر عابراً)"),
    },
    "damage_stage": {
        "receiving": ("Receiving", "الاستلام"),
        "storage": ("Storage", "التخزين"),
        "picking": ("Picking", "التجهيز"),
        "loading": ("Loading", "التحميل"),
        "delivery": ("Delivery", "التسليم"),
    },
    "damage_cause": {
        "forklift": ("Forklift", "رافعة شوكية"),
        "stacking_crush": ("Stacking crush", "سحق بسبب التكديس"),
        "packaging_failure": ("Packaging failure", "فشل التغليف"),
        "temperature": ("Temperature", "الحرارة"),
        "water": ("Water", "الماء"),
        "pest": ("Pest", "الآفات"),
        "other": ("Other", "أخرى"),
    },
    "return_grade": {
        "A": ("A — resaleable", "أ — قابل للبيع"),
        "B": ("B — repack", "ب — إعادة تغليف"),
        "C": ("C — hold for owner decision", "ج — حجز لقرار المالك"),
        "D": ("D — destroy", "د — إتلاف"),
    },
    "return_status": {
        "draft": ("Draft", "مسودة"),
        "graded": ("Graded", "مصنّف"),
        "confirmed": ("Confirmed", "مؤكَّد"),
    },
    "recall_type": {
        "supplier": ("Supplier", "المورد"),
        "regulator": ("Regulator", "جهة رقابية"),
        "owner": ("Owner", "المالك"),
        "mock": ("Mock recall", "استدعاء تجريبي"),
    },
    "recall_class": {
        "I": ("Class I", "الفئة I"),
        "II": ("Class II", "الفئة II"),
        "III": ("Class III", "الفئة III"),
    },
    "recall_status": {
        "open": ("Open", "مفتوح"),
        "traced": ("Traced", "تم التتبع"),
        "recovering": ("Recovering", "قيد الاسترجاع"),
        "closed": ("Closed", "مغلق"),
        "cancelled": ("Cancelled", "ملغى"),
    },
    "trip_status": {
        "planned": ("Planned", "مخطط"),
        "preload_checked": ("Pre-load checked", "تم الفحص قبل التحميل"),
        "dispatched": ("Dispatched", "انطلقت"),
        "delivered": ("Delivered", "تم التسليم"),
        "closed": ("Closed", "مغلقة"),
        "cancelled": ("Cancelled", "ملغاة"),
    },
    "pod_exception": {
        "shortage": ("Shortage", "نقص"),
        "damage": ("Damage", "تلف"),
        "temperature": ("Temperature", "حرارة"),
        "refused": ("Refused", "مرفوض"),
        "other": ("Other", "أخرى"),
    },
}


def label(kind: str, value: object, ar: bool = False) -> str:
    v = value.value if isinstance(value, StrEnum) else str(value)
    pair = LABELS_Q3.get(kind, {}).get(v)
    if pair is None:
        return v
    return pair[1] if ar else pair[0]
