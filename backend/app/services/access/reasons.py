"""EN/AR texts for gate reason codes (GC-6), WAP blockers (WA-13) and hook messages (HK-4)."""

from app.core.access_enums import (
    GATE_WARN_CODES,
    GateReasonCode,
    GateReasonSeverity,
    HookKind,
    WapBlocker,
)
from app.schemas.gates import GateReason
from app.services.access.hooks import AVAILABLE_FROM_PHASE

G = GateReasonCode

GATE_TEXT: dict[GateReasonCode, tuple[str, str]] = {
    G.TOKEN_UNKNOWN: ("Unknown or invalid code", "رمز غير معروف أو غير صالح"),
    G.OUT_OF_SCOPE: ("Outside your scope", "خارج نطاق صلاحيتك"),
    G.WORKER_NOT_DEPLOYED: ("Not deployed on this site", "غير معيّن في هذا الموقع"),
    G.WORKER_BANNED: ("Worker banned", "العامل محظور"),
    G.CONTRACTOR_SUSPENDED: ("Contractor suspended", "المقاول موقوف"),
    G.CONTRACTOR_BLACKLISTED: ("Contractor blacklisted", "المقاول محظور"),
    G.ID_EXPIRED: ("ID (Iqama) expired", "الهوية (الإقامة) منتهية"),
    G.INDUCTION_MISSING: ("Induction missing", "التعريف بالسلامة غير موجود"),
    G.INDUCTION_EXPIRED: ("Induction expired", "التعريف بالسلامة منتهي"),
    G.INDUCTION_SUSPENDED: ("Induction suspended", "التعريف بالسلامة موقوف"),
    G.INDUCTION_ABSENCE: (
        "Re-induction required after absence",
        "يلزم إعادة التعريف بعد الغياب",
    ),
    G.PASS_MISSING: ("Airport pass missing", "تصريح المطار غير موجود"),
    G.PASS_AREA_NOT_COVERED: ("Pass does not cover this area", "التصريح لا يشمل هذه المنطقة"),
    G.PASS_SUSPENDED: ("Airport pass suspended", "تصريح المطار موقوف"),
    G.PASS_EXPIRED: ("Airport pass expired", "تصريح المطار منتهي"),
    G.CREDENTIAL_REVOKED: ("Card revoked or replaced", "البطاقة ملغاة أو مستبدلة"),
    G.CREDENTIAL_LOST: ("Card reported lost", "البطاقة مبلغ عن فقدها"),
    G.ESCORT_REQUIRED: ("Escort required", "يتطلب مرافقة"),
    G.ESCORT_INVALID: ("Escort not valid", "المرافق غير مؤهل"),
    G.ESCORT_RATIO_EXCEEDED: ("Escort limit reached", "تجاوز الحد الأقصى للمرافقة"),
    G.WAP_MISSING: ("No work-area permit", "لا يوجد تصريح دخول منطقة"),
    G.WAP_NOT_ACTIVE: ("Work-area permit not active", "تصريح دخول المنطقة غير ساري"),
    G.WAP_SUSPENDED: ("Work-area permit suspended", "تصريح دخول المنطقة موقوف"),
    G.WAP_OUTSIDE_WINDOW: ("Outside permitted working hours", "خارج فترة العمل المسموحة"),
    G.CREW_EXCLUDED: ("Excluded from the permit crew", "مستبعد من طاقم التصريح"),
    G.ADP_MISSING: ("Airside driving permit missing", "تصريح القيادة غير موجود"),
    G.ADP_CATEGORY: ("Driving permit category too low", "فئة تصريح القيادة غير كافية"),
    G.ADP_SUSPENDED: ("Driving permit suspended", "تصريح القيادة موقوف"),
    G.AVP_MISSING: ("Vehicle permit missing", "تصريح المركبة غير موجود"),
    G.AVP_AREA: ("Vehicle permit does not cover this area", "تصريح المركبة لا يشمل المنطقة"),
    G.AVP_SUSPENDED: ("Vehicle permit suspended", "تصريح المركبة موقوف"),
    G.VEHICLE_DOC_EXPIRED: ("Vehicle document expired", "وثيقة المركبة منتهية"),
    G.HEIGHT_CLEARANCE_REQUIRED: (
        "Height clearance required",
        "يتطلب موافقة الارتفاع",
    ),
    G.HOOK_NOT_MET: ("Requirement not met", "متطلب غير مستوفى"),
    G.EXPIRING_7D: ("Expires within 7 days", "ينتهي خلال 7 أيام"),
    G.HOOK_NOT_AVAILABLE: ("Check not available yet", "الفحص غير متاح بعد"),
    G.LANGUAGE_MISMATCH: (
        "Induction not given in the worker's language",
        "التعريف لم يُقدَّم بلغة العامل",
    ),
    # v1.2 (4-third-party-cert §11.3 GC-6, GE-2, HK4-4)
    G.HOOK_NOT_MET_WARN: (
        "Requirement not met (warning until the block date)",
        "متطلب غير مستوفى (تحذير حتى تاريخ الحظر)",
    ),
    G.EQUIPMENT_BLACKLISTED: ("Equipment blacklisted", "المعدة محظورة"),
    G.EQUIPMENT_NOT_DEPLOYED: (
        "Equipment not deployed on this project",
        "المعدة غير معيّنة في هذا المشروع",
    ),
    G.EQUIPMENT_NOT_APPROVED: (
        "Equipment not approved for mobilisation",
        "المعدة غير معتمدة للتعبئة",
    ),
    G.EQUIPMENT_OUT_OF_SERVICE: ("OUT OF SERVICE", "خارج الخدمة"),
    G.EQUIPMENT_QUARANTINED: ("Equipment quarantined", "المعدة معزولة عن الاستخدام"),
    G.ARRIVAL_INSPECTION_DUE: ("Arrival inspection due", "فحص الوصول مستحق"),
    G.ALSO_SCAN_VEHICLE_STICKER: ("Also scan the vehicle sticker", "امسح ملصق المركبة أيضاً"),
}

HOOK_TEXT: dict[HookKind, tuple[str, str]] = {
    HookKind.training_course: ("Training check", "فحص التدريب"),
    HookKind.personnel_certificate: ("Personnel certificate check", "فحص شهادة الشخص"),
    HookKind.equipment_certificate: ("Equipment certificate check", "فحص شهادة المعدة"),
    HookKind.medical_fitness: ("Medical fitness check", "فحص اللياقة الطبية"),
}


def hook_message(kind: HookKind) -> tuple[str, str]:
    """HK-4: "Training check available from Phase 5 / فحص التدريب متاح من المرحلة 5"."""
    en, ar = HOOK_TEXT[kind]
    n = AVAILABLE_FROM_PHASE[kind]
    return f"{en} available from Phase {n}", f"{ar} متاح من المرحلة {n}"


BLOCKER_TEXT: dict[WapBlocker, tuple[str, str]] = {
    WapBlocker.NOTAM_NOT_ISSUED: ("Linked NOTAM not issued", "إشعار NOTAM المرتبط لم يصدر"),
    WapBlocker.NOTAM_NOT_COVERING_WINDOW: (
        "NOTAM does not cover every window",
        "إشعار NOTAM لا يغطي جميع فترات العمل",
    ),
    WapBlocker.ILS_OUTAGE_NOTAM_REQUIRED: (
        "ILS outage NOTAM required",
        "يتطلب NOTAM لتعطيل ILS",
    ),
    WapBlocker.HEIGHT_CLEARANCE_REQUIRED: (
        "Obstacle (height) clearance required",
        "يتطلب موافقة العوائق (الارتفاع)",
    ),
    WapBlocker.OBS_NOT_ACTIVE: ("Obstacle clearance not active", "موافقة العوائق غير سارية"),
    WapBlocker.WSP_REQUIRED: ("Works safety plan required", "يتطلب خطة سلامة الأعمال"),
    WapBlocker.SUPERVISOR_INELIGIBLE: ("Supervisor not eligible", "المشرف غير مؤهل"),
    WapBlocker.NO_ELIGIBLE_CREW: ("No eligible crew", "لا يوجد طاقم مؤهل"),
    WapBlocker.CONTRACTOR_SUSPENDED: ("Contractor suspended", "المقاول موقوف"),
    WapBlocker.OPS_SUSPENSION_ACTIVE: (
        "Operational suspension in force",
        "إيقاف تشغيلي ساري",
    ),
}


def severity(code: GateReasonCode, warn_codes: frozenset[GateReasonCode] | None = None) -> str:
    return "warn" if code in (warn_codes or GATE_WARN_CODES) else "deny"


def gate_reason(code: GateReasonCode, warn: bool | None = None) -> GateReason:
    en, ar = GATE_TEXT[code]
    sev = (
        GateReasonSeverity.warn
        if (warn if warn is not None else code in GATE_WARN_CODES)
        else GateReasonSeverity.deny
    )
    return GateReason(code=code, severity=sev, message_en=en, message_ar=ar)
