"""Enumerations of package Q1 construction: ITP, inspection requests, punch lists, handover dossier
(spec 8-quality Part B).

Every class carries the `Q` prefix (no name clash in the OpenAPI contract). The EN / AR labels of
these lists are merged into `app.core.quality.common.LABELS` here (D-327), so
`GET /quality/reference` serves them and the UI never copies them into message files."""

from __future__ import annotations

from enum import StrEnum

from app.core.quality.common import LABELS


class QPointType(StrEnum):
    """List PT (§B.1). Strictness order H > W > R > S."""

    H = "H"
    W = "W"
    R = "R"
    S = "S"


POINT_RANK = {QPointType.H: 3, QPointType.W: 2, QPointType.R: 1, QPointType.S: 0}


def strictest(types: list[QPointType]) -> QPointType:
    return max(types, key=lambda t: POINT_RANK[t])


class QVerifyingRecord(StrEnum):
    """§B.3.1 `verifying_record` of an ITP point."""

    ir = "ir"
    test_request = "test_request"
    mir = "mir"
    document = "document"
    none = "none"


class QItpStatus(StrEnum):
    """§B.3.3."""

    draft = "draft"
    submitted = "submitted"
    revise_resubmit = "revise_resubmit"
    approved = "approved"
    rejected = "rejected"
    superseded = "superseded"
    withdrawn = "withdrawn"


class QApprovalCode(StrEnum):
    """§B.3.1 approval codes A / B / C / D."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"


class QIrStatus(StrEnum):
    """§B.4.2."""

    draft = "draft"
    submitted = "submitted"
    scheduled = "scheduled"
    approved = "approved"
    approved_with_comments = "approved_with_comments"
    rejected = "rejected"
    witness_waived = "witness_waived"
    reinspection_requested = "reinspection_requested"
    cancelled = "cancelled"
    voided = "voided"


IR_APPROVED = frozenset({QIrStatus.approved, QIrStatus.approved_with_comments})
# states in which the `ir.inspect` step waits for a responsible person
IR_PENDING = frozenset(
    {
        QIrStatus.submitted,
        QIrStatus.scheduled,
        QIrStatus.witness_waived,
        QIrStatus.reinspection_requested,
    }
)
IR_FINAL = frozenset({QIrStatus.cancelled, QIrStatus.voided})


class QIrResult(StrEnum):
    """List IRR (§B.4.1)."""

    approved = "approved"
    approved_with_comments = "approved_with_comments"
    rejected = "rejected"
    not_ready = "not_ready"
    waived = "waived"


DECIDED_RESULTS = frozenset(
    {
        QIrResult.approved,
        QIrResult.approved_with_comments,
        QIrResult.rejected,
        QIrResult.not_ready,
    }
)


class QIrCommentStatus(StrEnum):
    open = "open"
    responded = "responded"
    closed = "closed"


class QPunchCategory(StrEnum):
    A = "A"
    B = "B"


class QPunchRaisedDuring(StrEnum):
    walkdown = "walkdown"
    pre_handover = "pre_handover"
    client_inspection = "client_inspection"
    ir = "ir"
    other = "other"


class QPunchStatus(StrEnum):
    open = "open"
    ready_for_review = "ready_for_review"
    closed = "closed"
    voided = "voided"


PUNCH_LIVE = frozenset({QPunchStatus.open, QPunchStatus.ready_for_review})


class QPlanStatus(StrEnum):
    current = "current"
    superseded = "superseded"


class QDossierStatus(StrEnum):
    """§B.7."""

    draft = "draft"
    compiled = "compiled"
    submitted = "submitted"
    accepted = "accepted"
    returned = "returned"


class QAsbuiltStatus(StrEnum):
    submitted = "submitted"
    approved = "approved"


# Q-DOS-03 blocker letters by dossier section (setting `dossier_blockers`); sections of other
# parts not listed here (Q2: mar, mir, tests, welding, calibration) are letter (e).
SECTION_LETTER = {"itp": "a", "ncr": "b", "punch": "c", "ir": "d", "asbuilt": "f"}
Q1_SECTIONS = ("itp", "ir", "punch", "asbuilt")
DOSSIER_MAX_BYTES = 2 * 1024 * 1024 * 1024  # Q-DOS-04: a package over 2 GB is refused
PLAN_MAX_BYTES = 10 * 1024 * 1024  # §B.6
PLAN_MAX_EDGE = 6000
IR_MAX_PHOTOS = 20


LABELS.update(
    {
        "discipline": {
            "CIV": ("Civil works", "أعمال مدنية"),
            "STC": ("Structural concrete", "خرسانة إنشائية"),
            "STL": ("Structural steel", "حديد إنشائي"),
            "ARC": ("Architectural", "معماري"),
            "HVC": ("HVAC", "تكييف وتهوية"),
            "PLB": ("Plumbing and drainage", "سباكة وصرف"),
            "FPS": ("Fire protection", "حماية من الحريق"),
            "ELE": ("Electrical", "كهرباء"),
            "ELV": ("Low current / ELV", "تيار منخفض"),
            "RDS": ("Roads and infrastructure", "طرق وبنية تحتية"),
            "AFP": ("Airfield pavement", "رصف المطارات"),
            "GEO": ("Geotechnical and earthworks", "أعمال ترابية وجيوتقنية"),
            "LSC": ("Landscape", "تنسيق الموقع"),
            "OTH": ("Other", "أخرى"),
        },
        "point_type": {
            "H": ("Hold point", "نقطة توقف"),
            "W": ("Witness point", "نقطة شهادة"),
            "R": ("Review point", "نقطة مراجعة"),
            "S": ("Surveillance", "نقطة مراقبة"),
        },
        "verifying_record": {
            "ir": ("Inspection request", "طلب فحص"),
            "test_request": ("Test request", "طلب اختبار"),
            "mir": ("Material inspection request", "طلب فحص المواد الموردة"),
            "document": ("Document", "وثيقة"),
            "none": ("None", "لا يوجد"),
        },
        "itp_status": {
            "draft": ("Draft", "مسودة"),
            "submitted": ("Submitted", "مُقدَّمة"),
            "revise_resubmit": ("Revise and resubmit", "تعاد للتعديل"),
            "approved": ("Approved", "معتمدة"),
            "rejected": ("Rejected", "مرفوضة"),
            "superseded": ("Superseded", "مستبدلة"),
            "withdrawn": ("Withdrawn", "مسحوبة"),
        },
        "approval_code": {
            "A": ("A — Approved", "A — معتمدة"),
            "B": ("B — Approved as noted", "B — معتمدة مع ملاحظات"),
            "C": ("C — Revise and resubmit", "C — تعاد للتعديل"),
            "D": ("D — Rejected", "D — مرفوضة"),
        },
        "ir_status": {
            "draft": ("Draft", "مسودة"),
            "submitted": ("Submitted", "مُقدَّم"),
            "scheduled": ("Scheduled", "مجدول"),
            "approved": ("Approved", "معتمد"),
            "approved_with_comments": ("Approved with comments", "معتمد مع ملاحظات"),
            "rejected": ("Rejected", "مرفوض"),
            "witness_waived": ("Witness waived", "تم التنازل عن الشهادة"),
            "reinspection_requested": ("Re-inspection requested", "إعادة فحص مطلوبة"),
            "cancelled": ("Cancelled", "ملغى"),
            "voided": ("Voided", "باطل"),
        },
        "ir_result": {
            "approved": ("Approved", "معتمد"),
            "approved_with_comments": ("Approved with comments", "معتمد مع ملاحظات"),
            "rejected": ("Rejected", "مرفوض"),
            "not_ready": ("Not ready", "غير جاهز"),
            "waived": ("Witness waived", "تم التنازل عن الحضور"),
        },
        "ir_comment_status": {
            "open": ("Open", "مفتوحة"),
            "responded": ("Responded", "تم الرد"),
            "closed": ("Closed", "مغلقة"),
        },
        "punch_category": {
            "A": ("A — close before handover", "A — يجب إغلاقه قبل التسليم"),
            "B": ("B — may close after handover", "B — يمكن إغلاقه بعد التسليم"),
        },
        "punch_raised_during": {
            "walkdown": ("Walkdown", "جولة تفقدية"),
            "pre_handover": ("Pre-handover", "قبل التسليم"),
            "client_inspection": ("Client inspection", "فحص العميل"),
            "ir": ("Inspection request", "طلب فحص"),
            "other": ("Other", "أخرى"),
        },
        "punch_status": {
            "open": ("Open", "مفتوح"),
            "ready_for_review": ("Ready for review", "جاهز للمراجعة"),
            "closed": ("Closed", "مغلق"),
            "voided": ("Voided", "ملغى"),
        },
        "plan_status": {
            "current": ("Current", "ساري"),
            "superseded": ("Superseded", "مستبدل"),
        },
        "dossier_status": {
            "draft": ("Draft", "مسودة"),
            "compiled": ("Compiled", "مُجمَّع"),
            "submitted": ("Submitted", "مُقدَّم"),
            "accepted": ("Accepted", "مقبول"),
            "returned": ("Returned", "مُعاد"),
        },
        "asbuilt_status": {
            "submitted": ("Submitted", "مُقدَّم"),
            "approved": ("Approved", "معتمد"),
        },
        "dossier_section": {
            "itp": ("Inspection and test plans", "خطط الفحص والاختبار"),
            "ir": ("Inspection requests", "طلبات الفحص"),
            "punch": ("Punch list", "قائمة النواقص"),
            "asbuilt": ("As-built drawings", "المخططات حسب التنفيذ"),
            "ncr": ("Nonconformance reports", "تقارير عدم المطابقة"),
            "mar": ("Material approvals", "اعتمادات المواد"),
            "mir": ("Material inspections", "فحوص المواد الموردة"),
            "tests": ("Test results", "نتائج الاختبارات"),
            "welding": ("Welding records", "سجلات اللحام"),
            "calibration": ("Calibration certificates", "شهادات المعايرة"),
            "documents": ("Controlled documents", "الوثائق المضبوطة"),
        },
    }
)
