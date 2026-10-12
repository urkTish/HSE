"""EN/AR labels of the 7b lists (spec 7b-fleet-driver §3.6, §4, §5.9). Codes are immutable."""

from collections.abc import Mapping
from typing import Any

from app.core.site_vehicle_enums import (
    OPERATING_CARD_CLASSES,
    SEATED_CLASSES,
    USE_CLASS_GROUP,
    SiteVehAuthStatus,
    SiteVehDriverGroup,
    SiteVehJourneyStatus,
    SiteVehLimitingFactor,
    SiteVehReadiness,
    SiteVehUseClass,
    SiteVehWarning,
)
from app.schemas.site_vehicle import SiteVehLabel, SiteVehReference, SiteVehUseClassRead

U = SiteVehUseClass
USE_CLASS: dict[SiteVehUseClass, tuple[str, str]] = {
    U.pool_car: ("Pool car", "سيارة عامة"),
    U.crew_pickup: ("Crew pickup", "بيك أب للطاقم"),
    U.crew_bus: ("Crew bus", "حافلة العمال"),
    U.tipper: ("Tipper", "قلاب"),
    U.goods_heavy: ("Heavy goods", "نقل ثقيل"),
    U.water_tanker: ("Water tanker", "صهريج مياه"),
    U.earthmoving_plant: ("Earthmoving plant", "معدات ترابية"),
    U.other_plant: ("Other plant", "معدة أخرى"),
}
GROUP: dict[SiteVehDriverGroup, tuple[str, str]] = {
    SiteVehDriverGroup.light: ("Light vehicle", "مركبة خفيفة"),
    SiteVehDriverGroup.bus: ("Bus", "حافلة"),
    SiteVehDriverGroup.heavy: ("Heavy vehicle", "مركبة ثقيلة"),
    SiteVehDriverGroup.plant: ("Plant operator", "مشغل معدات"),
}
READINESS: dict[SiteVehReadiness, tuple[str, str]] = {
    SiteVehReadiness.withdrawn: ("Withdrawn", "مسحوبة"),
    SiteVehReadiness.idle: ("Idle", "متوقفة مؤقتاً"),
    SiteVehReadiness.defect_hold: ("Defect hold", "إيقاف بسبب عيب"),
    SiteVehReadiness.not_certified: ("Not certified (Phase 4)", "غير معتمدة (المرحلة 4)"),
    SiteVehReadiness.docs_expired: ("Documents expired", "مستندات منتهية"),
    SiteVehReadiness.ready: ("Ready", "جاهزة"),
}
AUTH_STATUS: dict[SiteVehAuthStatus, tuple[str, str]] = {
    SiteVehAuthStatus.draft: ("Draft", "مسودة"),
    SiteVehAuthStatus.active: ("Active", "ساري"),
    SiteVehAuthStatus.suspended: ("Suspended", "موقوف"),
    SiteVehAuthStatus.expired: ("Expired", "منتهي"),
    SiteVehAuthStatus.revoked: ("Revoked", "ملغى"),
}
JOURNEY_STATUS: dict[SiteVehJourneyStatus, tuple[str, str]] = {
    SiteVehJourneyStatus.planned: ("Planned", "مخططة"),
    SiteVehJourneyStatus.arrived: ("Arrived", "وصلت"),
    SiteVehJourneyStatus.cancelled: ("Cancelled", "ملغاة"),
}
LIMITING: dict[SiteVehLimitingFactor, tuple[str, str]] = {
    SiteVehLimitingFactor.own_validity: ("Authorisation validity", "صلاحية التفويض"),
    SiteVehLimitingFactor.licence: ("Driving licence", "رخصة القيادة"),
    SiteVehLimitingFactor.worker_id: ("Worker ID / Iqama", "هوية العامل / الإقامة"),
    SiteVehLimitingFactor.deployment_end: ("Deployment end", "نهاية التكليف"),
    SiteVehLimitingFactor.training: ("Training (Phase 5)", "التدريب (المرحلة 5)"),
    SiteVehLimitingFactor.medical: ("Medical fitness (6a)", "اللياقة الطبية (6أ)"),
    SiteVehLimitingFactor.operator_certificate: ("Operator certificate (Phase 4)",
                                                 "شهادة المشغل (المرحلة 4)"),
}  # fmt: skip
WARNING: dict[SiteVehWarning, tuple[str, str]] = {
    SiteVehWarning.VEHICLE_DOCS_UNVERIFIED: (
        "Vehicle documents not yet verified by an HSE Officer.",
        "لم يتحقق مسؤول السلامة من مستندات المركبة بعد.",
    ),
    SiteVehWarning.DRIVER_NOT_AUTHORISED_WARN: (
        "The driver holds no Active authorisation for this vehicle group.",
        "لا يحمل السائق تفويضاً سارياً لفئة هذه المركبة.",
    ),
    SiteVehWarning.HOOK_NOT_MET_WARN: (
        "A training, medical or operator requirement is not met (policy warn).",
        "أحد متطلبات التدريب أو اللياقة الطبية أو شهادة المشغل غير مستوفى (سياسة تحذير).",
    ),
    SiteVehWarning.JOURNEY_PLAN_RECOMMENDED: (
        "A journey plan is recommended.",
        "يوصى بإعداد خطة رحلة.",
    ),
}
PROTOTYPE = ("Prototype", "نموذج أولي")
DOC_LABEL = {
    "istimara": ("Istimara", "الاستمارة"),
    "insurance": ("Insurance", "التأمين"),
    "mvpi": ("MVPI (Fahas)", "الفحص الدوري"),
    "operating_card": ("Operating card", "بطاقة التشغيل"),
}


def _labels(m: Mapping[Any, tuple[str, str]]) -> list[SiteVehLabel]:
    return [SiteVehLabel(code=str(k), label_en=en, label_ar=ar) for k, (en, ar) in m.items()]


def reference() -> SiteVehReference:
    return SiteVehReference(
        use_classes=[
            SiteVehUseClassRead(
                code=u.value,
                label_en=en,
                label_ar=ar,
                driver_group=USE_CLASS_GROUP[u],
                seats_required=u in SEATED_CLASSES,
                operating_card_required=u in OPERATING_CARD_CLASSES,
            )
            for u, (en, ar) in USE_CLASS.items()
        ],
        driver_groups=_labels(GROUP),
        readiness=_labels(READINESS),
        authorisation_statuses=_labels(AUTH_STATUS),
        journey_statuses=_labels(JOURNEY_STATUS),
        limiting_factors=_labels(LIMITING),
        warnings=_labels(WARNING),
        prototype_badge=SiteVehLabel(
            code="prototype", label_en=PROTOTYPE[0], label_ar=PROTOTYPE[1]
        ),
    )
