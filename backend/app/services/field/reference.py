"""Phase 6d reference lists (spec 6d-field-assurance §3.15) with EN / AR labels."""

from __future__ import annotations

from decimal import Decimal

from app.core.field_enums import (
    AuditGrade,
    AuditType,
    CampaignReason,
    FindingSeverity,
    InstructedRole,
    ItemType,
    TopicCategory,
)

ITEM_TYPES: dict[ItemType, tuple[str, str]] = {
    ItemType.yes_no: ("Yes / No", "نعم/لا"),
    ItemType.rating_0_3: ("Rating 0–3", "تقييم 0–3"),
    ItemType.numeric: ("Numeric value", "قيمة رقمية"),
    ItemType.single_select: ("Single choice", "اختيار"),
    ItemType.text: ("Text", "نص"),
    ItemType.photo: ("Photo", "صورة"),
    ItemType.count_: ("Count", "عدد"),
}

SEVERITIES: dict[FindingSeverity, tuple[str, str]] = {
    FindingSeverity.minor: ("Minor", "بسيطة"),
    FindingSeverity.major: ("Major", "جوهرية"),
    FindingSeverity.critical: ("Critical", "حرجة"),
}

AUDIT_FINDINGS: dict[FindingSeverity, tuple[str, str]] = {
    FindingSeverity.major_nc: ("Major nonconformity", "عدم مطابقة رئيسية"),
    FindingSeverity.minor_nc: ("Minor nonconformity", "عدم مطابقة ثانوية"),
    FindingSeverity.observation: ("Observation", "ملاحظة"),
    FindingSeverity.ofi: ("Opportunity for improvement", "فرصة للتحسين"),
}

AUDIT_TYPES: dict[AuditType, tuple[str, str]] = {
    AuditType.contractor_hse: ("Contractor HSE audit", "تدقيق السلامة للمقاول"),
    AuditType.system_iso45001: ("ISO 45001 internal audit", "تدقيق داخلي لنظام ISO 45001"),
    AuditType.client_requested: ("Client-requested audit", "تدقيق بطلب العميل"),
}

# AG (ASSUMPTION): lower bound of each grade, by unrounded score
AUDIT_GRADES: dict[AuditGrade, tuple[str, str, Decimal]] = {
    AuditGrade.A: ("Good", "جيد", Decimal("90.0")),
    AuditGrade.B: ("Satisfactory", "مُرضٍ", Decimal("75.0")),
    AuditGrade.C: ("Needs improvement", "يحتاج إلى تحسين", Decimal("60.0")),
    AuditGrade.D: ("Poor", "ضعيف", Decimal("0")),
}

INSTRUCTED_ROLES: dict[InstructedRole, tuple[str, str]] = {
    InstructedRole.supervisor: ("Supervisor", "المشرف"),
    InstructedRole.foreman: ("Foreman", "رئيس العمال"),
    InstructedRole.operator: ("Operator", "المشغل"),
    InstructedRole.permit_receiver: ("Permit receiver", "مستلم التصريح"),
    InstructedRole.other: ("Other", "أخرى"),
}

CAMPAIGN_REASONS: dict[CampaignReason, tuple[str, str]] = {
    CampaignReason.incident: ("Incident", "حادث"),
    CampaignReason.lesson: ("Lesson learned", "درس مستفاد"),
    CampaignReason.client_instruction: ("Client instruction", "تعليمات العميل"),
    CampaignReason.regulatory: ("Regulatory", "متطلب نظامي"),
    CampaignReason.seasonal: ("Seasonal", "موسمي"),
    CampaignReason.audit_finding: ("Audit finding", "ملاحظة تدقيق"),
}

_EXTRA_CATEGORIES = {
    TopicCategory.general: ("General", "عام"),
    TopicCategory.emergency: ("Emergency", "طوارئ"),
    TopicCategory.health: ("Health", "صحة"),
}


def topic_categories() -> dict[TopicCategory, tuple[str, str]]:
    from app.core.hse_enums import ReferenceList  # noqa: PLC0415
    from app.data.reference import REFERENCE  # noqa: PLC0415

    obs = {r[0]: (r[1], r[2]) for r in REFERENCE[ReferenceList.observation_category]}
    return {
        c: _EXTRA_CATEGORIES.get(c) or obs.get(c.value) or (c.value, c.value) for c in TopicCategory
    }


def grade_for(score: Decimal | None, capped: bool) -> AuditGrade | None:
    """AG on the unrounded score; a major_nc on a critical item caps the grade at C (§6.2)."""
    if score is None:
        return None
    g = AuditGrade.D
    for k, (_, _, lo) in AUDIT_GRADES.items():
        if score >= lo:
            g = k
            break
    if capped and g in (AuditGrade.A, AuditGrade.B):
        g = AuditGrade.C
    return g
