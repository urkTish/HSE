"""Phase 8 Quality — shared lists and registries owned by Q0 (spec 8-quality §3.1, §A).

Everything every Quality part needs from a shared file lives here, so the wave-2 parts (Q1 ITP /
IR / punch, Q2 materials / testing / welding / calibration, Q3 logistics, Q4 analytics) never edit
this module (§3.1): record types (list QRT) with their steps and default responsible persons,
NCR source types (list NS), the NCR lists, the settings registry of **every** part (Q-SET-01),
numbering defaults (Q-NUM-01) and the EN / AR labels of the lists.

Every class carries the `Q` prefix so no name clashes with earlier modules in the OpenAPI
contract (D-202 pattern)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.core.enums import Capability, Role

C = Capability


# ---- profile ---------------------------------------------------------------------------------


class QSectorProfile(StrEnum):
    """Q-PRF-01 sector profile of a project."""

    construction = "construction"
    logistics = "logistics"


class QProfileScope(StrEnum):
    """Profile of a record type, position, criterion, checklist or setting."""

    both = "both"
    construction = "construction"
    logistics = "logistics"


def profile_allows(scope: QProfileScope | str, profile: QSectorProfile | str | None) -> bool:
    s = QProfileScope(scope)
    return s == QProfileScope.both or (profile is not None and s.value == str(profile))


# ---- record types (list QRT) -------------------------------------------------------------------


class QRecordType(StrEnum):
    """List QRT (§A.4.2). The matrix has one row per type and step."""

    ncr = "ncr"
    observation = "observation"
    quality_alert = "quality_alert"
    complaint = "complaint"
    itp = "itp"
    ir = "ir"
    punch_item = "punch_item"
    dossier = "dossier"
    mar = "mar"
    mir = "mir"
    quarantine = "quarantine"
    test_request = "test_request"
    pour = "pour"
    wps = "wps"
    pqr = "pqr"
    wpq = "wpq"
    weld = "weld"
    mte = "mte"
    calibration = "calibration"
    oot_review = "oot_review"
    receipt = "receipt"
    excursion = "excursion"
    mapping_study = "mapping_study"
    hold = "hold"
    return_ = "return"
    recall = "recall"
    damage_report = "damage_report"
    fefo_check = "fefo_check"
    cycle_count = "cycle_count"
    trip = "trip"
    document = "document"
    transmittal = "transmittal"
    q_audit = "q_audit"
    management_review = "management_review"
    supplier = "supplier"
    supplier_evaluation = "supplier_evaluation"


class QAssigneeKind(StrEnum):
    """§A.4.3 assignee_kind of a matrix row."""

    user = "user"
    role = "role"
    position = "position"


@dataclass(frozen=True)
class StepDef:
    """One step of a record type that needs a responsible person (§A.4.2)."""

    code: str
    capability: Capability
    # default assignee: (kind, value); qualifier rows add more (qualifier, kind, value)
    default: tuple[QAssigneeKind, str] | None
    qualified: tuple[tuple[str, QAssigneeKind, str], ...] = ()
    # construction / logistics override of the default (e.g. ncr.concession)
    by_profile: tuple[tuple[QSectorProfile, QAssigneeKind, str], ...] = ()
    decisions: tuple[str, ...] = ("approved", "rejected")
    en: str = ""
    ar: str = ""


@dataclass(frozen=True)
class RecordTypeDef:
    code: QRecordType
    part: str
    profile: QProfileScope
    prefix: str
    en: str
    ar: str
    steps: tuple[StepDef, ...] = ()
    numbered: bool = True


R = QAssigneeKind.role
P = QAssigneeKind.position
U = QAssigneeKind.user
PB = QProfileScope.both
PC = QProfileScope.construction
PL = QProfileScope.logistics
APPROVE = ("approved", "approved_with_comments", "rejected", "returned")


def _s(
    code: str,
    cap: Capability,
    kind: QAssigneeKind | None,
    value: str | None,
    en: str,
    ar: str,
    *,
    qualified: tuple[tuple[str, QAssigneeKind, str], ...] = (),
    by_profile: tuple[tuple[QSectorProfile, QAssigneeKind, str], ...] = (),
    decisions: tuple[str, ...] = ("approved", "rejected"),
) -> StepDef:
    return StepDef(
        code,
        cap,
        (kind, value) if kind is not None and value is not None else None,
        qualified,
        by_profile,
        decisions,
        en,
        ar,
    )


QA = Role.qa_qc_manager.value
QE = Role.quality_engineer.value
QI = Role.qc_inspector.value
RECORD_TYPES: dict[QRecordType, RecordTypeDef] = {
    d.code: d
    for d in (
        RecordTypeDef(
            QRecordType.ncr,
            "Q0",
            PB,
            "NCR",
            "Nonconformance Report",
            "تقرير عدم مطابقة",
            (
                _s(
                    "disposition",
                    C.ncr_approve,
                    R,
                    QA,
                    "Disposition approval",
                    "اعتماد المعالجة",
                    decisions=("approved", "returned"),
                ),
                _s(
                    "concession",
                    C.ncr_approve,
                    None,
                    None,
                    "Concession (use as is / repair)",
                    "التنازل (استخدام كما هو / إصلاح)",
                    by_profile=(
                        (QSectorProfile.construction, P, "CONSULTANT_RE"),
                        (QSectorProfile.logistics, P, "WAREHOUSE_MGR"),
                    ),
                    decisions=("approved", "rejected"),
                ),
                _s(
                    "close",
                    C.ncr_approve,
                    R,
                    QA,
                    "Verification and close-out",
                    "التحقق والإغلاق",
                    decisions=("approved", "returned"),
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.observation,
            "Q0",
            PB,
            "QOB",
            "Quality Observation",
            "ملاحظة جودة",
            (_s("close", C.ncr_raise, R, QE, "Close", "الإغلاق", decisions=("approved",)),),
        ),
        RecordTypeDef(
            QRecordType.quality_alert,
            "Q0",
            PB,
            "QAL",
            "Quality Alert",
            "تنبيه جودة",
            (_s("issue", C.ncr_approve, R, QA, "Issue", "الإصدار", decisions=("approved",)),),
        ),
        RecordTypeDef(
            QRecordType.complaint,
            "Q0",
            PB,
            "CCM",
            "Customer Complaint",
            "شكوى عميل",
            (
                _s(
                    "response",
                    C.complaint_manage,
                    R,
                    QA,
                    "Response",
                    "الرد",
                    decisions=("approved",),
                ),
                _s("close", C.complaint_manage, R, QA, "Close", "الإغلاق", decisions=("approved",)),
            ),
        ),
        RecordTypeDef(
            QRecordType.itp,
            "Q1",
            PC,
            "ITP",
            "Inspection and Test Plan",
            "خطة الفحص والاختبار",
            (
                _s(
                    "approve",
                    C.itp_approve,
                    P,
                    "CONSULTANT_RE",
                    "Approval",
                    "الاعتماد",
                    decisions=APPROVE,
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.ir,
            "Q1",
            PC,
            "IR",
            "Inspection Request",
            "طلب فحص",
            (
                _s(
                    "inspect",
                    C.ir_inspect,
                    None,
                    None,
                    "Inspection decision",
                    "قرار الفحص",
                    qualified=(
                        ("H", P, "CONSULTANT_RE"),
                        ("W", P, "CONSULTANT_RE"),
                        ("R", R, QE),
                        ("S", R, QI),
                    ),
                    decisions=("approved", "approved_with_comments", "rejected", "not_ready"),
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.punch_item,
            "Q1",
            PC,
            "PCH",
            "Punch Item",
            "بند قائمة النواقص",
            (
                _s(
                    "verify",
                    C.punch_verify,
                    P,
                    "CONSULTANT_RE",
                    "Verification",
                    "التحقق",
                    decisions=("approved", "rejected"),
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.dossier,
            "Q1",
            PC,
            "DOS",
            "Handover Dossier",
            "ملف التسليم",
            (
                _s(
                    "accept",
                    C.dossier_accept,
                    P,
                    "CLIENT_REP",
                    "Acceptance",
                    "القبول",
                    decisions=("approved", "returned"),
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.mar,
            "Q2",
            PC,
            "MAR",
            "Material Approval Request",
            "طلب اعتماد مواد",
            (
                _s(
                    "approve",
                    C.material_decide,
                    P,
                    "CONSULTANT_RE",
                    "Approval",
                    "الاعتماد",
                    decisions=("A", "B", "C", "D"),
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.mir,
            "Q2",
            PC,
            "MIR",
            "Material Inspection Request",
            "طلب فحص المواد الموردة",
            (
                _s(
                    "decide",
                    C.material_decide,
                    P,
                    "CONSULTANT_RE",
                    "Decision",
                    "القرار",
                    decisions=("accepted", "accepted_with_comments", "rejected"),
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.quarantine,
            "Q2",
            PC,
            "QTN",
            "Quarantined Material",
            "مواد محجوزة",
            (
                _s(
                    "dispose",
                    C.material_decide,
                    R,
                    QA,
                    "Disposal",
                    "التصرف",
                    decisions=("approved",),
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.test_request,
            "Q2",
            PB,
            "TST",
            "Test Request",
            "طلب اختبار",
            (
                _s(
                    "verify",
                    C.test_verify,
                    R,
                    QE,
                    "Verification",
                    "التحقق",
                    decisions=("approved", "returned"),
                ),
            ),
        ),
        RecordTypeDef(QRecordType.pour, "Q2", PC, "POUR", "Concrete Pour", "صبّة خرسانية"),
        RecordTypeDef(
            QRecordType.wps,
            "Q2",
            PC,
            "WPS",
            "Welding Procedure Specification",
            "مواصفة إجراء اللحام",
            (
                _s(
                    "approve",
                    C.welding_approve,
                    P,
                    "CONSULTANT_RE",
                    "Approval",
                    "الاعتماد",
                    decisions=APPROVE,
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.pqr,
            "Q2",
            PC,
            "PQR",
            "Procedure Qualification Record",
            "سجل تأهيل الإجراء",
            (
                _s(
                    "approve",
                    C.welding_approve,
                    P,
                    "CONSULTANT_RE",
                    "Approval",
                    "الاعتماد",
                    decisions=APPROVE,
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.wpq,
            "Q2",
            PC,
            "WPQ",
            "Welder Qualification",
            "تأهيل اللحّام",
            (_s("approve", C.welding_approve, R, QE, "Approval", "الاعتماد", decisions=APPROVE),),
        ),
        RecordTypeDef(
            QRecordType.weld,
            "Q2",
            PC,
            "WLD",
            "Weld Joint",
            "وصلة لحام",
            (
                _s(
                    "repair2_approve",
                    C.welding_approve,
                    R,
                    QE,
                    "Second repair approval",
                    "اعتماد الإصلاح الثاني",
                ),
            ),
            numbered=False,
        ),
        RecordTypeDef(
            QRecordType.mte, "Q0", PB, "MTE", "Measuring and Test Equipment", "جهاز قياس واختبار"
        ),
        RecordTypeDef(
            QRecordType.calibration,
            "Q2",
            PB,
            "CAL",
            "Calibration Record",
            "سجل معايرة",
            (_s("accept", C.calibration_decide, R, QE, "Acceptance", "القبول"),),
        ),
        RecordTypeDef(
            QRecordType.oot_review,
            "Q2",
            PB,
            "OOT",
            "Out-of-Tolerance Review",
            "مراجعة الخروج عن التفاوت",
            (
                _s(
                    "decide",
                    C.calibration_decide,
                    R,
                    QA,
                    "Decision",
                    "القرار",
                    decisions=("approved",),
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.receipt,
            "Q3",
            PL,
            "RCV",
            "Receiving Inspection",
            "فحص الاستلام",
            (
                _s("deviation", C.receiving_decide, R, QA, "Deviation decision", "قرار الانحراف"),
                _s("reject", C.receiving_decide, R, QA, "Rejection decision", "قرار الرفض"),
            ),
        ),
        RecordTypeDef(
            QRecordType.excursion,
            "Q3",
            PL,
            "EXC",
            "Temperature Excursion",
            "انحراف حراري",
            (
                _s(
                    "impact",
                    C.excursion_assess,
                    P,
                    "WAREHOUSE_MGR",
                    "Impact assessment",
                    "تقييم الأثر",
                    qualified=(("pharma_2_8", P, "RESP_PHARMACIST"),),
                    decisions=("approved", "returned"),
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.mapping_study,
            "Q3",
            PL,
            "MAP",
            "Temperature Mapping Study",
            "دراسة التوزيع الحراري",
            (
                _s(
                    "approve",
                    C.storage_manage,
                    R,
                    QA,
                    "Approval",
                    "الاعتماد",
                    decisions=("approved", "returned"),
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.hold,
            "Q3",
            PL,
            "HLD",
            "Hold / Quarantine",
            "حجز وعزل",
            (
                _s(
                    "release",
                    C.hold_manage,
                    P,
                    "WAREHOUSE_MGR",
                    "Release",
                    "الإفراج",
                    qualified=(("pharma_2_8", P, "RESP_PHARMACIST"),),
                ),
                _s(
                    "reject",
                    C.hold_manage,
                    P,
                    "WAREHOUSE_MGR",
                    "Rejection",
                    "الرفض",
                    qualified=(("pharma_2_8", P, "RESP_PHARMACIST"),),
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.return_,
            "Q3",
            PL,
            "RET",
            "Return Inspection",
            "فحص المرتجعات",
            (
                _s(
                    "disposition",
                    C.stock_record,
                    R,
                    QA,
                    "Disposition",
                    "المعالجة",
                    decisions=("approved",),
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.recall,
            "Q3",
            PL,
            "RCL",
            "Recall",
            "استدعاء منتج",
            (_s("close", C.recall_manage, R, QA, "Close", "الإغلاق", decisions=("approved",)),),
        ),
        RecordTypeDef(QRecordType.damage_report, "Q3", PL, "DMG", "Damage Report", "بلاغ تلف"),
        RecordTypeDef(QRecordType.fefo_check, "Q3", PL, "FEF", "FEFO Check", "فحص الأقدم انتهاءً"),
        RecordTypeDef(QRecordType.cycle_count, "Q3", PL, "CC", "Cycle Count", "جرد دوري"),
        RecordTypeDef(
            QRecordType.trip,
            "Q3",
            PL,
            "TRP",
            "Transport Trip",
            "رحلة نقل",
            (
                _s(
                    "dispatch_override",
                    C.transport_record,
                    P,
                    "TRANSPORT_SUP",
                    "Dispatch override",
                    "تجاوز منع الإرسال",
                    decisions=("approved",),
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.document,
            "Q4",
            PB,
            "DOC",
            "Controlled Document",
            "وثيقة مضبوطة",
            (
                _s(
                    "review",
                    C.document_approve,
                    R,
                    QE,
                    "Review",
                    "المراجعة",
                    decisions=("approved", "returned"),
                ),
                _s(
                    "approve",
                    C.document_approve,
                    R,
                    QA,
                    "Approval",
                    "الاعتماد",
                    decisions=("approved", "returned"),
                ),
            ),
        ),
        RecordTypeDef(QRecordType.transmittal, "Q4", PB, "TRM", "Transmittal", "مذكرة إحالة"),
        RecordTypeDef(
            QRecordType.q_audit,
            "Q4",
            PB,
            "QAU",
            "Quality Audit",
            "تدقيق الجودة",
            (
                _s(
                    "issue",
                    C.quality_audit_issue,
                    R,
                    QA,
                    "Report issue",
                    "إصدار التقرير",
                    decisions=("approved",),
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.management_review,
            "Q4",
            PB,
            "MRV",
            "Management Review",
            "مراجعة الإدارة",
            (
                _s(
                    "approve",
                    C.quality_audit_issue,
                    R,
                    QA,
                    "Minutes approval",
                    "اعتماد المحضر",
                    decisions=("approved", "returned"),
                ),
            ),
        ),
        RecordTypeDef(
            QRecordType.supplier,
            "Q0",
            PB,
            "SUP",
            "Supplier",
            "مورد",
            (
                _s(
                    "approve",
                    C.supplier_approve,
                    R,
                    QA,
                    "Approval",
                    "الاعتماد",
                    decisions=("approved", "conditional", "returned"),
                ),
                _s(
                    "suspend",
                    C.supplier_approve,
                    R,
                    QA,
                    "Suspension",
                    "الإيقاف",
                    decisions=("approved",),
                ),
            ),
            numbered=False,
        ),
        RecordTypeDef(
            QRecordType.supplier_evaluation,
            "Q4",
            PB,
            "SEV",
            "Supplier Evaluation",
            "تقييم المورد",
            (
                _s(
                    "approve",
                    C.supplier_approve,
                    R,
                    QA,
                    "Approval",
                    "الاعتماد",
                    decisions=("approved", "returned"),
                ),
            ),
        ),
    )
}


def step_def(record_type: QRecordType | str, step: str) -> StepDef | None:
    rt = RECORD_TYPES.get(QRecordType(record_type))
    if rt is None:
        return None
    return next((s for s in rt.steps if s.code == step), None)


def entity_type_value(rt: QRecordType | str) -> str:
    """EntityType value of a record type (audit log): `q_<code>` (q_audit stays q_audit)."""
    v = QRecordType(rt).value
    return v if v.startswith("q_") else f"q_{v}"


# ---- positions (§A.4.1) -----------------------------------------------------------------------

DEFAULT_POSITIONS: tuple[tuple[str, str, str, QProfileScope], ...] = (
    ("CONSULTANT_RE", "Consultant Resident Engineer", "المهندس المقيم للاستشاري", PC),
    ("CONSULTANT_INSP", "Consultant Inspector", "مفتش الاستشاري", PC),
    ("CLIENT_REP", "Client Representative", "ممثل العميل", PC),
    ("WAREHOUSE_MGR", "Warehouse Manager", "مدير المستودع", PL),
    ("RESP_PHARMACIST", "Responsible Pharmacist", "الصيدلي المسؤول", PL),
    ("TRANSPORT_SUP", "Transport Supervisor", "مشرف النقل", PL),
)


# ---- NCR lists (§A.9.2) ---------------------------------------------------------------------


class QNcrSourceType(StrEnum):
    """List NS. Adapters register in `NCR_SOURCES` (app.services.quality.registry)."""

    manual = "manual"
    observation = "observation"
    complaint = "complaint"
    ir = "ir"
    punch_item = "punch_item"
    mir = "mir"
    test_result = "test_result"
    weld = "weld"
    oot_review = "oot_review"
    receipt = "receipt"
    excursion = "excursion"
    stock_check = "stock_check"
    return_ = "return"
    recall = "recall"
    trip = "trip"
    hygiene_pest = "hygiene_pest"
    q_audit_finding = "q_audit_finding"


class QNcrClass(StrEnum):
    """List NC (ordered minor < major < critical)."""

    minor = "minor"
    major = "major"
    critical = "critical"


CLASS_RANK = {QNcrClass.minor: 0, QNcrClass.major: 1, QNcrClass.critical: 2}

# NS source → (part, default class, raise mode)
NCR_SOURCE_DEFS: dict[QNcrSourceType, tuple[str, QNcrClass | None, str]] = {
    QNcrSourceType.manual: ("Q0", None, "manual"),
    QNcrSourceType.observation: ("Q0", QNcrClass.minor, "manual"),
    QNcrSourceType.complaint: ("Q0", QNcrClass.major, "manual"),
    QNcrSourceType.ir: ("Q1", QNcrClass.minor, "prompt"),
    QNcrSourceType.punch_item: ("Q1", QNcrClass.minor, "manual"),
    QNcrSourceType.mir: ("Q2", QNcrClass.major, "auto"),
    QNcrSourceType.test_result: ("Q2", QNcrClass.major, "auto"),
    QNcrSourceType.weld: ("Q2", QNcrClass.major, "auto"),
    QNcrSourceType.oot_review: ("Q2", QNcrClass.major, "decision"),
    QNcrSourceType.receipt: ("Q3", QNcrClass.minor, "prompt"),
    QNcrSourceType.excursion: ("Q3", None, "auto"),
    QNcrSourceType.stock_check: ("Q3", QNcrClass.minor, "manual"),
    QNcrSourceType.return_: ("Q3", QNcrClass.minor, "prompt"),
    QNcrSourceType.recall: ("Q3", QNcrClass.critical, "auto"),
    QNcrSourceType.trip: ("Q3", None, "auto"),
    QNcrSourceType.hygiene_pest: ("Q3", QNcrClass.minor, "prompt"),
    QNcrSourceType.q_audit_finding: ("Q4", QNcrClass.major, "auto"),
}


class QNcrCategory(StrEnum):
    """List NCAT (Pareto dimension; codes fixed)."""

    workmanship = "workmanship"
    material = "material"
    design_documentation = "design_documentation"
    dimensional = "dimensional"
    testing_failure = "testing_failure"
    procedure_not_followed = "procedure_not_followed"
    damage = "damage"
    temperature = "temperature"
    labelling = "labelling"
    expiry_shelf_life = "expiry_shelf_life"
    contamination_hygiene = "contamination_hygiene"
    quantity = "quantity"
    traceability = "traceability"
    packaging = "packaging"
    calibration = "calibration"
    other = "other"


class QDetectionStage(StrEnum):
    """List DS."""

    receiving = "receiving"
    in_process = "in_process"
    final_inspection = "final_inspection"
    internal_audit = "internal_audit"
    storage = "storage"
    at_customer = "at_customer"
    after_handover = "after_handover"
    regulator = "regulator"


INTERNAL_STAGES = frozenset(
    {
        QDetectionStage.receiving,
        QDetectionStage.in_process,
        QDetectionStage.final_inspection,
        QDetectionStage.internal_audit,
        QDetectionStage.storage,
    }
)


class QCauseCategory(StrEnum):
    """List 6M."""

    people = "people"
    machine = "machine"
    method = "method"
    material = "material"
    measurement = "measurement"
    environment = "environment"


class QDisposition(StrEnum):
    """List DP."""

    use_as_is = "use_as_is"
    repair = "repair"
    rework = "rework"
    reject_return = "reject_return"
    reject_scrap = "reject_scrap"


CONCESSION_DISPOSITIONS = frozenset({QDisposition.use_as_is, QDisposition.repair})


class QRcaMethod(StrEnum):
    """List RCA."""

    simple = "simple"
    five_why = "five_why"
    ishikawa = "ishikawa"
    eight_d = "eight_d"


class QNcrStatus(StrEnum):
    """§A.9.3."""

    draft = "draft"
    open = "open"
    disposition_proposed = "disposition_proposed"
    disposition_approved = "disposition_approved"
    pending_verification = "pending_verification"
    closed = "closed"
    voided = "voided"


NCR_LIVE = frozenset(
    {
        QNcrStatus.open,
        QNcrStatus.disposition_proposed,
        QNcrStatus.disposition_approved,
        QNcrStatus.pending_verification,
    }
)


class QCostType(StrEnum):
    """List CT."""

    rework_labour = "rework_labour"
    repair_labour = "repair_labour"
    material = "material"
    plant = "plant"
    retest_reinspection = "retest_reinspection"
    scrap_writeoff = "scrap_writeoff"
    delay = "delay"
    transport_return = "transport_return"
    disposal = "disposal"
    customer_credit = "customer_credit"
    claim_penalty = "claim_penalty"
    other = "other"


class QEffectiveness(StrEnum):
    effective = "effective"
    not_effective = "not_effective"


# ---- shared registers (§A.8) ------------------------------------------------------------------


class QDiscipline(StrEnum):
    """List DSC (§B.1; used by systems in Q0 and by Q1 / Q2)."""

    CIV = "CIV"
    STC = "STC"
    STL = "STL"
    ARC = "ARC"
    HVC = "HVC"
    PLB = "PLB"
    FPS = "FPS"
    ELE = "ELE"
    ELV = "ELV"
    RDS = "RDS"
    AFP = "AFP"
    GEO = "GEO"
    LSC = "LSC"
    OTH = "OTH"


class QActiveStatus(StrEnum):
    active = "active"
    archived = "archived"


class QSupplierCategory(StrEnum):
    """List SC."""

    material_supplier = "material_supplier"
    manufacturer = "manufacturer"
    subcontractor = "subcontractor"
    testing_lab = "testing_lab"
    calibration_lab = "calibration_lab"
    ndt_provider = "ndt_provider"
    carrier = "carrier"
    pest_control = "pest_control"
    cleaning = "cleaning"
    packaging = "packaging"
    shipper = "shipper"
    service = "service"
    other = "other"


class QSupplierStatus(StrEnum):
    """List SS."""

    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    conditional = "conditional"
    suspended = "suspended"
    disqualified = "disqualified"


SUPPLIER_USABLE = frozenset({QSupplierStatus.approved, QSupplierStatus.conditional})


class QAccreditationBody(StrEnum):
    sac = "sac"
    ilac_mra_other = "ilac_mra_other"
    other = "other"


class QAccreditationStandard(StrEnum):
    iso_iec_17025 = "iso_iec_17025"
    iso_iec_17020 = "iso_iec_17020"
    iso_9001 = "iso_9001"
    iso_22000 = "iso_22000"
    other = "other"


class QCustomerKind(StrEnum):
    client = "client"
    depositor = "depositor"
    consignee = "consignee"
    end_user = "end_user"


class QCustomerStatus(StrEnum):
    active = "active"
    inactive = "inactive"


class QMteType(StrEnum):
    """List MT (§C.4)."""

    tape_rule = "tape_rule"
    caliper_micrometer = "caliper_micrometer"
    level_theodolite = "level_theodolite"
    total_station = "total_station"
    gnss_survey = "gnss_survey"
    thermometer = "thermometer"
    temp_probe = "temp_probe"
    temp_logger = "temp_logger"
    humidity_logger = "humidity_logger"
    infrared_thermometer = "infrared_thermometer"
    pressure_gauge = "pressure_gauge"
    torque_wrench = "torque_wrench"
    dft_gauge = "dft_gauge"
    holiday_detector = "holiday_detector"
    hardness_tester = "hardness_tester"
    compression_machine = "compression_machine"
    slump_cone = "slump_cone"
    cube_mould = "cube_mould"
    nuclear_density_gauge = "nuclear_density_gauge"
    scale_balance = "scale_balance"
    multimeter_insulation_tester = "multimeter_insulation_tester"
    ultrasonic_thickness = "ultrasonic_thickness"
    other = "other"


class QCalStatus(StrEnum):
    """List CS (§C.4). `unknown` only until Q2 is installed."""

    calibrated = "calibrated"
    due_soon = "due_soon"
    overdue = "overdue"
    out_of_service = "out_of_service"
    limited_use = "limited_use"
    not_required = "not_required"
    unknown = "unknown"


MTE_WARN_STATUSES = frozenset({QCalStatus.overdue, QCalStatus.out_of_service})


class QMteCheckKind(StrEnum):
    calibration = "calibration"
    verification = "verification"
    none = "none"


class QMteOwnerKind(StrEnum):
    own = "own"
    engagement = "engagement"
    supplier = "supplier"


class QMteStatus(StrEnum):
    active = "active"
    retired = "retired"
    lost = "lost"


class QMteUseVerdict(StrEnum):
    ok = "ok"
    warned = "warned"
    blocked_overridden = "blocked_overridden"


class QLinkKind(StrEnum):
    raised_from = "raised_from"
    relates = "relates"
    evidence = "evidence"
    requires = "requires"
    supersedes = "supersedes"


class QSignoffChannel(StrEnum):
    in_app = "in_app"
    paper = "paper"


class QNumberReset(StrEnum):
    yearly = "yearly"
    never = "never"


# ---- criteria (§A.6) ---------------------------------------------------------------------------


class QCriterionKind(StrEnum):
    """List CK."""

    range = "range"
    min = "min"
    max = "max"
    target_tolerance = "target_tolerance"
    pass_fail = "pass_fail"
    text = "text"
    rule = "rule"


class QCriterionStatus(StrEnum):
    draft = "draft"
    published = "published"
    superseded = "superseded"
    retired = "retired"


class QVerdict(StrEnum):
    """Q-CRT-01."""

    pass_ = "pass"
    fail = "fail"
    indicative = "indicative"
    not_evaluable = "not_evaluable"


# ---- quality checklists on 6d (§A.7) ----------------------------------------------------------


class QChecklistType(StrEnum):
    """List QCT."""

    ir_inspection = "ir_inspection"
    punch_walkdown = "punch_walkdown"
    mir_inspection = "mir_inspection"
    receiving = "receiving"
    reefer_preload = "reefer_preload"
    hygiene = "hygiene"
    pest_visit = "pest_visit"
    return_inspection = "return_inspection"
    q_audit = "q_audit"
    supplier_audit = "supplier_audit"


# ---- observations, alerts, complaints (§A.10) --------------------------------------------------


class QObservationStatus(StrEnum):
    open = "open"
    actioned = "actioned"
    closed = "closed"


class QAlertSeverity(StrEnum):
    info = "info"
    warning = "warning"
    stop_use = "stop_use"


class QAlertStatus(StrEnum):
    draft = "draft"
    issued = "issued"
    expired = "expired"
    withdrawn = "withdrawn"


class QComplaintChannel(StrEnum):
    email = "email"
    phone = "phone"
    letter = "letter"
    meeting = "meeting"
    portal = "portal"
    other = "other"


class QComplaintSeverity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class QComplaintStatus(StrEnum):
    received = "received"
    acknowledged = "acknowledged"
    under_investigation = "under_investigation"
    responded = "responded"
    closed = "closed"
    withdrawn = "withdrawn"


class QJustified(StrEnum):
    yes = "yes"
    no = "no"
    partly = "partly"


class QSatisfaction(StrEnum):
    yes = "yes"
    no = "no"
    no_reply = "no_reply"


# ---- numbering defaults (Q-NUM-01) ------------------------------------------------------------

DEFAULT_FORMAT = "{PFX}-{PROJECT}-{YYYY}-{SEQ4}"
HIGH_VOLUME = frozenset(
    {
        QRecordType.ir,
        QRecordType.punch_item,
        QRecordType.test_request,
        QRecordType.receipt,
        QRecordType.fefo_check,
        QRecordType.trip,
        QRecordType.damage_report,
    }
)
SPECIAL_FORMATS: dict[QRecordType, tuple[str, QNumberReset]] = {
    QRecordType.itp: ("{PFX}-{PROJECT}-{DISC}-{SEQ3}", QNumberReset.never),
    QRecordType.document: ("{PROJECT}-QA-{PFX}-{SEQ3}", QNumberReset.never),
    QRecordType.mte: ("{PFX}-{SEQ4}", QNumberReset.never),
}


def default_numbering(rt: QRecordType) -> tuple[str, QNumberReset]:
    if rt in SPECIAL_FORMATS:
        return SPECIAL_FORMATS[rt]
    if rt in HIGH_VOLUME:
        return "{PFX}-{PROJECT}-{YYYY}-{SEQ5}", QNumberReset.yearly
    return DEFAULT_FORMAT, QNumberReset.yearly


# ---- settings registry (Q-SET-01; every key of every part) ------------------------------------


class QSettingKind(StrEnum):
    int = "int"
    decimal = "decimal"
    decimal_or_null = "decimal_or_null"
    bool = "bool"
    enum = "enum"
    set = "set"
    map = "map"  # fixed keys → numbers in [min, max]
    methods_map = "methods_map"  # NCR class → allowed RCA methods
    json = "json"


@dataclass(frozen=True)
class SettingDef:
    key: str
    part: str
    kind: QSettingKind
    default: Any
    en: str
    ar: str
    min: Decimal | None = None
    max: Decimal | None = None
    options: tuple[str, ...] = ()
    keys: tuple[str, ...] = ()
    profile: QProfileScope = QProfileScope.both
    note: str = ""


def _d(v: str | int | float) -> Decimal:
    return Decimal(str(v))


K = QSettingKind
_CLS = ("critical", "major", "minor")
_RCA = tuple(m.value for m in QRcaMethod)
_MC = (
    "concrete_mix",
    "cement",
    "aggregates",
    "rebar",
    "structural_steel",
    "blockwork",
    "waterproofing",
    "insulation",
    "pipes_fittings",
    "valves",
    "ductwork",
    "cables",
    "electrical_equipment",
    "mechanical_equipment",
    "coatings",
    "finishes",
    "asphalt",
    "consumables",
    "other",
)


def _set(
    key: str,
    part: str,
    kind: QSettingKind,
    default: Any,
    en: str,
    ar: str,
    lo: Any = None,
    hi: Any = None,
    **kw: Any,
) -> SettingDef:
    return SettingDef(
        key,
        part,
        kind,
        default,
        en,
        ar,
        _d(lo) if lo is not None else None,
        _d(hi) if hi is not None else None,
        **kw,
    )


SETTINGS: tuple[SettingDef, ...] = (
    # ---- Q0 (§A.3) ----
    _set(
        "ncr_containment_hours",
        "Q0",
        K.map,
        {"critical": 24, "major": 72, "minor": 168},
        "NCR containment time (hours)",
        "مهلة الاحتواء (ساعات)",
        4,
        720,
        keys=_CLS,
    ),
    _set(
        "ncr_target_close_days",
        "Q0",
        K.map,
        {"critical": 21, "major": 30, "minor": 30},
        "NCR target close (days)",
        "مدة الإغلاق المستهدفة (أيام)",
        3,
        180,
        keys=_CLS,
    ),
    _set(
        "ncr_repeat_days",
        "Q0",
        K.int,
        90,
        "Repeat NCR window (days)",
        "مدة التكرار (أيام)",
        30,
        365,
    ),
    _set(
        "ncr_effectiveness_days",
        "Q0",
        K.int,
        90,
        "Effectiveness check after (days)",
        "موعد فحص الفعالية (أيام)",
        30,
        365,
    ),
    _set(
        "rca_method_by_class",
        "Q0",
        K.methods_map,
        {
            "critical": ["eight_d"],
            "major": ["five_why", "ishikawa", "eight_d"],
            "minor": list(_RCA),
        },
        "Root-cause method by class",
        "طريقة تحليل السبب حسب التصنيف",
        keys=_CLS,
        options=_RCA,
    ),
    _set(
        "quality_ca_due_days",
        "Q0",
        K.map,
        {"critical": 14, "high": 30, "medium": 45, "low": 60},
        "Quality corrective action due days",
        "مدة الإجراءات التصحيحية للجودة (أيام)",
        1,
        180,
        keys=("critical", "high", "medium", "low"),
    ),
    _set(
        "labour_rate_sar_h",
        "Q0",
        K.decimal,
        "85.00",
        "Labour rate (SAR / h)",
        "سعر ساعة العمل (ريال)",
        10,
        1000,
    ),
    _set(
        "plant_rate_sar_h",
        "Q0",
        K.decimal,
        "250.00",
        "Plant rate (SAR / h)",
        "سعر ساعة المعدات (ريال)",
        10,
        5000,
    ),
    _set(
        "delay_rate_sar_day",
        "Q0",
        K.decimal_or_null,
        None,
        "Delay cost (SAR / day)",
        "تكلفة يوم التأخير (ريال)",
        0,
        10_000_000,
    ),
    _set(
        "mte_use_policy",
        "Q0",
        K.enum,
        "warn",
        "Use of uncalibrated M&TE",
        "سياسة استخدام أجهزة غير معايرة",
        options=("warn", "block"),
    ),
    _set(
        "competence_policy",
        "Q0",
        K.enum,
        "warn",
        "Competence policy",
        "سياسة الكفاءة",
        options=("warn", "block"),
    ),
    _set(
        "complaint_ack_hours",
        "Q0",
        K.int,
        24,
        "Complaint acknowledgement (hours)",
        "مهلة الإقرار بالشكوى (ساعات)",
        1,
        168,
    ),
    _set(
        "complaint_response_days",
        "Q0",
        K.int,
        10,
        "Complaint response (days)",
        "مهلة الرد على الشكوى (أيام)",
        1,
        60,
    ),
    _set(
        "paper_signoff_default",
        "Q0",
        K.bool,
        True,
        "Paper sign-off allowed by default",
        "السماح بالتوقيع الورقي",
    ),
    _set(
        "checklist_default",
        "Q0",
        K.json,
        {},
        "Default checklist per record type (Q-CHK-04)",
        "النموذج الافتراضي لكل نوع سجل",
    ),
    # ---- Q1 (§B.2) ----
    _set(
        "ir_notice_hours",
        "Q1",
        K.map,
        {"H": 24, "W": 24},
        "IR advance notice (hours)",
        "مهلة الإشعار المسبق (ساعات)",
        0,
        168,
        keys=("H", "W"),
        profile=PC,
    ),
    _set(
        "ir_schedule_hours",
        "Q1",
        K.int,
        24,
        "IR scheduling time (hours)",
        "مهلة الجدولة (ساعات)",
        2,
        168,
        profile=PC,
    ),
    _set(
        "witness_wait_minutes",
        "Q1",
        K.int,
        60,
        "Witness wait (minutes)",
        "مدة انتظار الشاهد (دقائق)",
        15,
        480,
        profile=PC,
    ),
    _set(
        "witness_review_days",
        "Q1",
        K.int,
        3,
        "Waived witness review (days)",
        "مهلة مراجعة نقطة الشهادة المتنازل عنها (أيام)",
        1,
        14,
        profile=PC,
    ),
    _set(
        "ir_max_points",
        "Q1",
        K.int,
        5,
        "Points per IR",
        "الحد الأقصى للنقاط في الطلب",
        1,
        10,
        profile=PC,
    ),
    _set(
        "ir_comment_close_days",
        "Q1",
        K.int,
        14,
        "Close approval comments (days)",
        "مهلة إغلاق ملاحظات الاعتماد (أيام)",
        1,
        60,
        profile=PC,
    ),
    _set(
        "punch_target_days",
        "Q1",
        K.map,
        {"A": 14, "B": 30},
        "Punch target (days)",
        "مهلة إغلاق النواقص (أيام)",
        1,
        180,
        keys=("A", "B"),
        profile=PC,
    ),
    _set(
        "dossier_blockers",
        "Q1",
        K.set,
        ["a", "b", "c", "d", "e", "f"],
        "Dossier completeness blockers (Q-DOS-03)",
        "شروط اكتمال الملف",
        options=("a", "b", "c", "d", "e", "f"),
        profile=PC,
    ),
    # ---- Q2 (§C.1) ----
    _set(
        "mar_review_days",
        "Q2",
        K.int,
        14,
        "MAR review (days)",
        "مهلة مراجعة طلب الاعتماد",
        3,
        60,
        profile=PC,
    ),
    _set(
        "mar_required_categories",
        "Q2",
        K.set,
        [m for m in _MC if m != "consumables"],
        "Material categories needing a MAR",
        "فئات تتطلب اعتماد مواد",
        options=_MC,
        profile=PC,
    ),
    _set(
        "quarantine_ageing_days",
        "Q2",
        K.int,
        14,
        "Quarantine ageing alert (days)",
        "مدة الحجز قبل التنبيه (أيام)",
        3,
        90,
        profile=PC,
    ),
    _set(
        "test_auto_ncr",
        "Q2",
        K.enum,
        "auto",
        "NCR for a failed test",
        "إنشاء تقرير عدم مطابقة تلقائياً للاختبار الفاشل",
        options=("auto", "prompt"),
    ),
    _set(
        "test_overdue_days",
        "Q2",
        K.int,
        1,
        "Result entry overdue after (days)",
        "مهلة إدخال النتيجة (أيام)",
        0,
        14,
    ),
    _set(
        "early_age_warning_ratio",
        "Q2",
        K.decimal,
        "0.65",
        "Early-age strength warning ratio",
        "نسبة التحذير المبكر للمقاومة",
        "0.40",
        "0.90",
        profile=PC,
    ),
    _set(
        "pour_sampling_m3",
        "Q2",
        K.int,
        50,
        "Pour volume per sample set (m³)",
        "حجم الصبّة لكل مجموعة عينات (م³)",
        10,
        150,
        profile=PC,
    ),
    _set(
        "wpq_continuity_months",
        "Q2",
        K.int,
        6,
        "Welder continuity (months)",
        "مدة استمرارية تأهيل اللحّام (أشهر)",
        3,
        12,
        profile=PC,
    ),
    _set(
        "wpq_confirmation_mode",
        "Q2",
        K.enum,
        "weld_log",
        "Welder continuity confirmation",
        "تأكيد استمرارية اللحّام",
        options=("weld_log", "weld_log_or_confirmation"),
        profile=PC,
    ),
    _set(
        "repair_rate_alert_pct",
        "Q2",
        K.decimal,
        "5.0",
        "Welder repair rate alert (%)",
        "حد نسبة الإصلاح للّحام (%)",
        "1.0",
        "20.0",
        profile=PC,
    ),
    _set(
        "progressive_exam",
        "Q2",
        K.bool,
        True,
        "Progressive examination",
        "الفحص التصاعدي",
        profile=PC,
    ),
    _set(
        "mte_due_soon_days",
        "Q2",
        K.int,
        30,
        "M&TE due soon (days)",
        "تنبيه قرب المعايرة (أيام)",
        7,
        90,
    ),
    _set(
        "oot_review_days",
        "Q2",
        K.int,
        14,
        "Out-of-tolerance review (days)",
        "مهلة مراجعة الخروج عن التفاوت (أيام)",
        3,
        60,
    ),
    _set(
        "competence_expiry_warning_days",
        "Q2",
        K.int,
        30,
        "Competence expiry warning (days)",
        "تنبيه انتهاء الكفاءة (أيام)",
        7,
        90,
    ),
    # ---- Q3 (§D.1.1) ----
    _set(
        "reading_gap_factor",
        "Q3",
        K.decimal,
        "2.0",
        "Reading gap factor",
        "معامل فجوة القراءات",
        "1.5",
        "5.0",
        profile=PL,
    ),
    _set(
        "monitoring_gap_alert_minutes",
        "Q3",
        K.int,
        60,
        "Monitoring gap alert (minutes)",
        "تنبيه انقطاع المراقبة (دقائق)",
        15,
        1440,
        profile=PL,
    ),
    _set(
        "manual_reading_max_age_hours",
        "Q3",
        K.int,
        72,
        "Oldest manual reading (hours)",
        "أقدم قراءة يدوية مسموحة (ساعات)",
        1,
        168,
        profile=PL,
    ),
    _set(
        "excursion_auto_hold",
        "Q3",
        K.bool,
        True,
        "Automatic hold on excursion",
        "حجز تلقائي عند الانحراف",
        profile=PL,
    ),
    _set(
        "pharma_impact_all_excursions",
        "Q3",
        K.bool,
        True,
        "Assess every medicines excursion",
        "تقييم كل انحرافات الأدوية",
        profile=PL,
    ),
    _set(
        "min_remaining_shelf_life_pct",
        "Q3",
        K.int,
        60,
        "Minimum remaining shelf life (%)",
        "الحد الأدنى للصلاحية المتبقية (%)",
        10,
        100,
        profile=PL,
    ),
    _set(
        "near_expiry_days",
        "Q3",
        K.int,
        30,
        "Near expiry (days)",
        "قرب انتهاء الصلاحية (أيام)",
        1,
        365,
        profile=PL,
    ),
    _set(
        "near_expiry_pct",
        "Q3",
        K.int,
        20,
        "Near expiry (% of shelf life)",
        "قرب انتهاء الصلاحية (% من العمر)",
        1,
        90,
        profile=PL,
    ),
    _set(
        "dock_dwell_max_minutes",
        "Q3",
        K.int,
        30,
        "Maximum dock dwell (minutes)",
        "أقصى مدة على الرصيف (دقائق)",
        5,
        180,
        profile=PL,
    ),
    _set(
        "hold_ageing_days",
        "Q3",
        K.int,
        7,
        "Hold ageing alert (days)",
        "تنبيه تقادم الحجز (أيام)",
        1,
        60,
        profile=PL,
    ),
    _set(
        "fefo_checks_per_week",
        "Q3",
        K.int,
        20,
        "FEFO checks per week",
        "عدد فحوص FEFO الأسبوعية",
        0,
        500,
        profile=PL,
    ),
    _set(
        "cycle_count_tolerance_units",
        "Q3",
        K.int,
        0,
        "Cycle count tolerance (units)",
        "تفاوت الجرد (وحدات)",
        0,
        100,
        profile=PL,
    ),
    _set(
        "recall_trace_target_hours",
        "Q3",
        K.int,
        4,
        "Recall trace target (hours)",
        "زمن التتبع المستهدف (ساعات)",
        1,
        48,
        profile=PL,
    ),
    _set(
        "recall_effectiveness_target_pct",
        "Q3",
        K.decimal,
        "100.0",
        "Recall effectiveness target (%)",
        "فعالية الاستدعاء المستهدفة (%)",
        "90.0",
        "100.0",
        profile=PL,
    ),
    _set(
        "mock_recall_months",
        "Q3",
        K.int,
        12,
        "Mock recall every (months)",
        "دورية الاستدعاء التجريبي (أشهر)",
        3,
        24,
        profile=PL,
    ),
    _set(
        "mapping_validity_months",
        "Q3",
        K.int,
        24,
        "Mapping study validity (months)",
        "صلاحية دراسة التوزيع الحراري (أشهر)",
        6,
        60,
        profile=PL,
    ),
    _set(
        "mapping_min_hours",
        "Q3",
        K.int,
        72,
        "Mapping minimum duration (hours)",
        "أقل مدة لدراسة التوزيع (ساعات)",
        24,
        336,
        profile=PL,
    ),
    _set(
        "mapping_max_interval_minutes",
        "Q3",
        K.int,
        5,
        "Mapping maximum interval (minutes)",
        "أقصى فاصل قراءات للدراسة (دقائق)",
        1,
        15,
        profile=PL,
    ),
    _set(
        "mapping_min_loggers",
        "Q3",
        K.int,
        9,
        "Mapping minimum loggers",
        "أقل عدد مسجلات للدراسة",
        3,
        200,
        profile=PL,
    ),
    _set(
        "otif_window_minutes",
        "Q3",
        K.int,
        60,
        "On-time window (minutes)",
        "نافذة التسليم في الموعد (دقائق)",
        0,
        1440,
        profile=PL,
    ),
    _set(
        "transit_data_due_hours",
        "Q3",
        K.int,
        48,
        "Transit data due (hours)",
        "مهلة بيانات الرحلة (ساعات)",
        4,
        168,
        profile=PL,
    ),
    _set(
        "import_max_rows",
        "Q3",
        K.int,
        200_000,
        "Import maximum rows",
        "الحد الأقصى للصفوف",
        1000,
        1_000_000,
        profile=PL,
    ),
    # ---- Q4 (§E.1.1) ----
    _set(
        "doc_review_months",
        "Q4",
        K.int,
        24,
        "Document review every (months)",
        "دورية مراجعة الوثائق (أشهر)",
        6,
        60,
    ),
    _set(
        "doc_revision_scheme",
        "Q4",
        K.enum,
        "letters_then_numbers",
        "Revision numbering",
        "نظام ترقيم المراجعات",
        options=("letters_then_numbers", "numbers"),
    ),
    _set(
        "read_ack_days",
        "Q4",
        K.int,
        7,
        "Read-and-acknowledge (days)",
        "مهلة الإقرار بالاطلاع (أيام)",
        1,
        30,
    ),
    _set(
        "q_audit_frequency",
        "Q4",
        K.map,
        {"high": "2", "medium": "1", "low": "0.5"},
        "Audits per year by risk",
        "تكرار التدقيق حسب المخاطر",
        "0.25",
        4,
        keys=("high", "medium", "low"),
    ),
    _set(
        "q_audit_report_days",
        "Q4",
        K.int,
        7,
        "Audit report due (days)",
        "مهلة إصدار تقرير التدقيق (أيام)",
        3,
        30,
    ),
    _set(
        "mgmt_review_months",
        "Q4",
        K.int,
        12,
        "Management review every (months)",
        "دورية مراجعة الإدارة (أشهر)",
        3,
        12,
    ),
    _set(
        "supplier_reeval_months",
        "Q4",
        K.int,
        12,
        "Supplier re-evaluation (months)",
        "دورية إعادة تقييم الموردين (أشهر)",
        3,
        36,
    ),
    _set(
        "supplier_score_period",
        "Q4",
        K.enum,
        "quarter",
        "Scorecard period",
        "فترة بطاقة الأداء",
        options=("month", "quarter"),
    ),
    _set(
        "supplier_score_weights",
        "Q4",
        K.json,
        {"M1": 30, "M2": 20, "M3": 20, "M4": 15, "M5": 10, "M6": 5},
        "Supplier score weights",
        "أوزان بطاقة أداء المورد",
    ),
    _set(
        "supplier_score_anchors",
        "Q4",
        K.json,
        {
            "M1": [100, 90],
            "M2": [0, 5],
            "M3": [98, 80],
            "M4": [100, 90],
            "M5": [100, 50],
            "M6": [100, 90],
        },
        "Supplier score anchors (good, bad)",
        "مراجع بطاقة أداء المورد",
    ),
    _set(
        "supplier_score_bands",
        "Q4",
        K.json,
        {"A": "85.0", "B": "70.0", "C": "50.0"},
        "Supplier score bands",
        "فئات بطاقة أداء المورد",
    ),
    _set(
        "spc_min_subgroups",
        "Q4",
        K.int,
        20,
        "SPC minimum subgroups",
        "الحد الأدنى للمجموعات الفرعية",
        8,
        50,
    ),
    _set(
        "pareto_include_observations",
        "Q4",
        K.bool,
        False,
        "Pareto includes observations",
        "تضمين الملاحظات في باريتو",
    ),
    _set(
        "dpmo_processes",
        "Q4",
        K.json,
        {
            "ir_inspection": "items",
            "mir_inspection": "items",
            "receiving": 4,
            "picking_fefo": 1,
            "delivery": 2,
            "inventory": 1,
        },
        "DPMO processes (opportunities per unit)",
        "تعريف الفرص",
    ),
    _set(
        "ncr_ontime_warning_pct",
        "Q4",
        K.decimal,
        "80.0",
        "NCR on-time warning (%)",
        "حد إنذار إغلاق التقارير (%)",
        0,
        100,
    ),
    _set(
        "ftpr_warning_pct",
        "Q4",
        K.decimal,
        "85.0",
        "First-time pass warning (%)",
        "حد إنذار النجاح من أول مرة (%)",
        0,
        100,
        profile=PC,
    ),
    _set(
        "test_fail_warning_pct",
        "Q4",
        K.decimal,
        "5.0",
        "Test failure warning (%)",
        "حد إنذار فشل الاختبارات (%)",
        0,
        100,
    ),
    _set(
        "tor_warning_pct",
        "Q4",
        K.decimal,
        "0.50",
        "Time out of range warning (%)",
        "حد إنذار الزمن خارج النطاق (%)",
        0,
        100,
        profile=PL,
    ),
    _set(
        "transport_compliance_warning_pct",
        "Q4",
        K.decimal,
        "98.0",
        "Transport compliance warning (%)",
        "حد إنذار الالتزام الحراري في النقل (%)",
        0,
        100,
        profile=PL,
    ),
)
SETTINGS_BY_KEY: dict[str, SettingDef] = {s.key: s for s in SETTINGS}


def defaults() -> dict[str, Any]:
    return {s.key: s.default for s in SETTINGS}


# ---- list labels (EN / AR) for the reference endpoint, PDFs and emails ------------------------

LABELS: dict[str, dict[str, tuple[str, str]]] = {
    "profile": {
        "construction": ("Construction", "إنشاءات"),
        "logistics": ("Logistics", "لوجستيات"),
        "both": ("Both", "كلاهما"),
    },
    "ncr_status": {
        "draft": ("Draft", "مسودة"),
        "open": ("Open", "مفتوح"),
        "disposition_proposed": ("Disposition proposed", "معالجة مقترحة"),
        "disposition_approved": ("Disposition approved", "معالجة معتمدة"),
        "pending_verification": ("Pending verification", "بانتظار التحقق"),
        "closed": ("Closed", "مغلق"),
        "voided": ("Voided", "ملغى"),
    },
    "ncr_class": {
        "minor": ("Minor", "طفيفة"),
        "major": ("Major", "جوهرية"),
        "critical": ("Critical", "حرجة"),
    },
    "ncr_source": {
        "manual": ("Manual", "يدوي"),
        "observation": ("Escalated observation", "ملاحظة مُصعّدة"),
        "complaint": ("Customer complaint", "شكوى عميل"),
        "ir": ("Inspection request rejected", "رفض طلب فحص"),
        "punch_item": ("Escalated punch item", "بند نواقص مُصعّد"),
        "mir": ("Material rejected on delivery", "رفض مواد موردة"),
        "test_result": ("Failed test result", "نتيجة اختبار فاشلة"),
        "weld": ("Weld repair limit or lot expansion", "تجاوز حد إصلاح اللحام"),
        "oot_review": ("Out-of-tolerance impact", "أثر الخروج عن التفاوت"),
        "receipt": ("Receiving deviation or rejection", "انحراف أو رفض عند الاستلام"),
        "excursion": ("Temperature excursion", "انحراف حراري"),
        "stock_check": ("FEFO, expiry, damage, cycle count", "فحص المخزون"),
        "return": ("Return inspection", "فحص المرتجعات"),
        "recall": ("Recall", "استدعاء"),
        "trip": ("Transport", "النقل"),
        "hygiene_pest": ("Hygiene or pest finding", "نظافة أو آفات"),
        "q_audit_finding": ("Quality audit finding", "ملاحظة تدقيق جودة"),
    },
    "ncr_category": {
        "workmanship": ("Workmanship", "جودة التنفيذ"),
        "material": ("Material", "المواد"),
        "design_documentation": ("Design and documentation", "التصميم والوثائق"),
        "dimensional": ("Dimensional", "الأبعاد"),
        "testing_failure": ("Testing failure", "فشل الاختبار"),
        "procedure_not_followed": ("Procedure not followed", "عدم اتباع الإجراء"),
        "damage": ("Damage", "تلف"),
        "temperature": ("Temperature", "الحرارة"),
        "labelling": ("Labelling", "الملصقات"),
        "expiry_shelf_life": ("Expiry / shelf life", "الصلاحية"),
        "contamination_hygiene": ("Contamination / hygiene", "التلوث والنظافة"),
        "quantity": ("Quantity", "الكمية"),
        "traceability": ("Traceability", "التتبع"),
        "packaging": ("Packaging", "التغليف"),
        "calibration": ("Calibration", "المعايرة"),
        "other": ("Other", "أخرى"),
    },
    "detection_stage": {
        "receiving": ("Receiving", "الاستلام"),
        "in_process": ("In process", "أثناء التنفيذ"),
        "final_inspection": ("Final inspection", "الفحص النهائي"),
        "internal_audit": ("Internal audit", "تدقيق داخلي"),
        "storage": ("Storage", "التخزين"),
        "at_customer": ("At customer", "لدى العميل"),
        "after_handover": ("After handover", "بعد التسليم"),
        "regulator": ("Regulator", "جهة رقابية"),
    },
    "cause_category": {
        "people": ("People", "الأفراد"),
        "machine": ("Machine", "المعدات"),
        "method": ("Method", "الطريقة"),
        "material": ("Material", "المواد"),
        "measurement": ("Measurement", "القياس"),
        "environment": ("Environment", "البيئة"),
    },
    "disposition": {
        "use_as_is": ("Use as is", "استخدام كما هو"),
        "repair": ("Repair", "إصلاح"),
        "rework": ("Rework", "إعادة العمل"),
        "reject_return": ("Reject and return to supplier", "رفض وإرجاع للمورد"),
        "reject_scrap": ("Reject and scrap", "رفض وإتلاف"),
    },
    "disposition_logistics": {"use_as_is": ("Release, no impact", "إفراج بدون أثر")},
    "rca_method": {
        "simple": ("Cause statement", "بيان السبب"),
        "five_why": ("5-Why", "لماذا الخمسة"),
        "ishikawa": ("Ishikawa (fishbone)", "مخطط عظم السمكة"),
        "eight_d": ("8D", "منهجية 8D"),
    },
    "cost_type": {
        "rework_labour": ("Rework labour", "إعادة العمل"),
        "repair_labour": ("Repair labour", "الإصلاح"),
        "material": ("Replacement material", "مواد بديلة"),
        "plant": ("Plant", "معدات"),
        "retest_reinspection": ("Re-test and re-inspection", "إعادة الاختبار والفحص"),
        "scrap_writeoff": ("Scrap / write-off", "إتلاف / شطب"),
        "delay": ("Delay", "تأخير"),
        "transport_return": ("Transport and return", "نقل وإرجاع"),
        "disposal": ("Disposal", "تخلص"),
        "customer_credit": ("Customer credit", "تعويض للعميل"),
        "claim_penalty": ("Claim or penalty", "غرامة أو مطالبة"),
        "other": ("Other", "أخرى"),
    },
    "control_level_quality": {
        "elimination": ("Remove the cause (design or process change)", "إزالة السبب"),
        "substitution": (
            "Change material, method or supplier",
            "تغيير المادة أو الطريقة أو المورد",
        ),
        "engineering": ("Error-proof (fixture, poka-yoke, automation)", "منع الخطأ"),
        "administrative": ("Procedure, instruction or training", "إجراء أو تعليمات أو تدريب"),
        "ppe": ("Extra inspection only (detection)", "فحص إضافي فقط"),
    },
    "supplier_status": {
        "draft": ("Draft", "مسودة"),
        "pending_approval": ("Pending approval", "بانتظار الاعتماد"),
        "approved": ("Approved", "معتمد"),
        "conditional": ("Conditional", "معتمد بشروط"),
        "suspended": ("Suspended", "موقوف"),
        "disqualified": ("Disqualified", "مستبعد"),
    },
    "supplier_category": {
        "material_supplier": ("Material supplier", "مورد مواد"),
        "manufacturer": ("Manufacturer", "مصنّع"),
        "subcontractor": ("Subcontractor", "مقاول باطن"),
        "testing_lab": ("Testing laboratory", "مختبر اختبارات"),
        "calibration_lab": ("Calibration laboratory", "مختبر معايرة"),
        "ndt_provider": ("NDT provider", "مزود فحص غير إتلافي"),
        "carrier": ("Carrier", "ناقل"),
        "pest_control": ("Pest control", "مكافحة آفات"),
        "cleaning": ("Cleaning", "تنظيف"),
        "packaging": ("Packaging", "تغليف"),
        "shipper": ("Shipper / goods supplier", "شاحن / مورد البضاعة"),
        "service": ("Service", "خدمات"),
        "other": ("Other", "أخرى"),
    },
    "customer_kind": {
        "client": ("Client", "العميل"),
        "depositor": ("Depositor (goods owner)", "مالك البضاعة"),
        "consignee": ("Consignee", "المستلم"),
        "end_user": ("End user", "المستخدم النهائي"),
    },
    "cal_status": {
        "calibrated": ("Calibrated", "معاير"),
        "due_soon": ("Due soon", "قريب الاستحقاق"),
        "overdue": ("Overdue", "متأخر"),
        "out_of_service": ("Out of service", "خارج الخدمة"),
        "limited_use": ("Limited use", "استخدام محدود"),
        "not_required": ("Not required", "لا يتطلب معايرة"),
        "unknown": ("Unknown", "غير معروف"),
    },
    "observation_status": {
        "open": ("Open", "مفتوحة"),
        "actioned": ("Actioned", "تم اتخاذ إجراء"),
        "closed": ("Closed", "مغلقة"),
    },
    "alert_severity": {
        "info": ("Information", "معلومة"),
        "warning": ("Warning", "تحذير"),
        "stop_use": ("Stop use", "إيقاف الاستخدام"),
    },
    "alert_status": {
        "draft": ("Draft", "مسودة"),
        "issued": ("Issued", "صادر"),
        "expired": ("Expired", "منتهي"),
        "withdrawn": ("Withdrawn", "مسحوب"),
    },
    "complaint_status": {
        "received": ("Received", "مستلمة"),
        "acknowledged": ("Acknowledged", "تم الإقرار"),
        "under_investigation": ("Under investigation", "قيد التحقيق"),
        "responded": ("Responded", "تم الرد"),
        "closed": ("Closed", "مغلقة"),
        "withdrawn": ("Withdrawn", "مسحوبة"),
    },
    "criterion_kind": {
        "range": ("Range", "نطاق"),
        "min": ("Minimum", "حد أدنى"),
        "max": ("Maximum", "حد أقصى"),
        "target_tolerance": ("Target ± tolerance", "قيمة مستهدفة مع تفاوت"),
        "pass_fail": ("Pass / fail", "ناجح / راسب"),
        "text": ("Described", "وصفي"),
        "rule": ("Coded rule", "قاعدة مبرمجة"),
    },
    "verdict": {
        "pass": ("Pass", "ناجح"),
        "fail": ("Fail", "راسب"),
        "indicative": ("Indicative", "إرشادي"),
        "not_evaluable": ("Not evaluable", "غير قابل للتقييم"),
    },
}


_MTE_AR = {
    "tape_rule": "شريط قياس",
    "caliper_micrometer": "قدمة / ميكرومتر",
    "level_theodolite": "ميزان / ثيودوليت",
    "total_station": "محطة رصد",
    "gnss_survey": "جهاز مساحة GNSS",
    "thermometer": "ميزان حرارة",
    "temp_probe": "مجس حرارة",
    "temp_logger": "مسجل حرارة",
    "humidity_logger": "مسجل رطوبة",
    "infrared_thermometer": "ميزان حرارة بالأشعة تحت الحمراء",
    "pressure_gauge": "مقياس ضغط",
    "torque_wrench": "مفتاح عزم",
    "dft_gauge": "مقياس سماكة الطلاء",
    "holiday_detector": "كاشف ثقوب الطلاء",
    "hardness_tester": "جهاز قياس الصلادة",
    "compression_machine": "ماكينة الضغط",
    "slump_cone": "مخروط الهبوط",
    "cube_mould": "قالب المكعبات",
    "nuclear_density_gauge": "جهاز الكثافة النووي",
    "scale_balance": "ميزان",
    "multimeter_insulation_tester": "جهاز متعدد / فاحص عزل",
    "ultrasonic_thickness": "مقياس سماكة بالموجات فوق الصوتية",
    "other": "أخرى",
}
LABELS.update(
    {
        "mte_type": {k: (k.replace("_", " ").capitalize(), v) for k, v in _MTE_AR.items()},
        "check_kind": {
            "calibration": ("Calibration", "معايرة"),
            "verification": ("Verification", "تحقق"),
            "none": ("None", "لا يوجد"),
        },
        "mte_status": {
            "active": ("Active", "نشط"),
            "retired": ("Retired", "مستبعد"),
            "lost": ("Lost", "مفقود"),
        },
        "complaint_channel": {
            "email": ("Email", "بريد إلكتروني"),
            "phone": ("Phone", "هاتف"),
            "letter": ("Letter", "خطاب"),
            "meeting": ("Meeting", "اجتماع"),
            "portal": ("Portal", "بوابة"),
            "other": ("Other", "أخرى"),
        },
        "complaint_severity": {
            "low": ("Low", "منخفضة"),
            "medium": ("Medium", "متوسطة"),
            "high": ("High", "عالية"),
        },
        "justified": {
            "yes": ("Justified", "مبررة"),
            "no": ("Not justified", "غير مبررة"),
            "partly": ("Partly justified", "مبررة جزئياً"),
        },
        "satisfaction": {
            "yes": ("Satisfied", "راضٍ"),
            "no": ("Not satisfied", "غير راضٍ"),
            "no_reply": ("No reply", "لا رد"),
        },
        "criterion_status": {
            "draft": ("Draft", "مسودة"),
            "published": ("Published", "منشور"),
            "superseded": ("Superseded", "مستبدل"),
            "retired": ("Retired", "موقوف"),
        },
        "link_kind": {
            "raised_from": ("Raised from", "صادر عن"),
            "relates": ("Related", "مرتبط"),
            "evidence": ("Evidence", "دليل"),
            "requires": ("Requires", "يتطلب"),
            "supersedes": ("Supersedes", "يحل محل"),
        },
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
        "assignee_kind": {
            "user": ("Named user", "مستخدم محدد"),
            "role": ("Platform role", "دور"),
            "position": ("Project position", "منصب في المشروع"),
        },
        "role": {
            "qa_qc_manager": ("QA/QC Manager", "مدير ضبط وتوكيد الجودة"),
            "quality_engineer": ("Quality Engineer", "مهندس الجودة"),
            "qc_inspector": ("QC Inspector", "مفتش ضبط الجودة"),
            "warehouse_qc": ("Warehouse QC", "مراقب جودة المستودع"),
            "responsible_person": ("Responsible Person", "الشخص المسؤول"),
            "hse_manager": ("HSE Manager", "مدير الصحة والسلامة"),
            "hse_officer": ("HSE Officer", "مسؤول الصحة والسلامة"),
            "site_engineer": ("Site Engineer", "مهندس الموقع"),
        },
        "channel": {"in_app": ("In the app", "داخل التطبيق"), "paper": ("On paper", "ورقياً")},
        "accreditation_body": {
            "sac": ("SAC (Saudi Accreditation Center)", "المركز السعودي للاعتماد"),
            "ilac_mra_other": ("Other ILAC MRA body", "جهة أخرى ضمن ILAC MRA"),
            "other": ("Other", "أخرى"),
        },
        "accreditation_standard": {
            "iso_iec_17025": ("ISO/IEC 17025", "ISO/IEC 17025"),
            "iso_iec_17020": ("ISO/IEC 17020", "ISO/IEC 17020"),
            "iso_9001": ("ISO 9001", "ISO 9001"),
            "iso_22000": ("ISO 22000", "ISO 22000"),
            "other": ("Other", "أخرى"),
        },
        "customer_status": {"active": ("Active", "نشط"), "inactive": ("Inactive", "غير نشط")},
        "active_status": {"active": ("Active", "نشط"), "archived": ("Archived", "مؤرشف")},
        "mte_owner_kind": {
            "own": ("Own", "ملك المشروع"),
            "engagement": ("Contractor", "المقاول"),
            "supplier": ("Supplier", "المورد"),
        },
        "number_reset": {"yearly": ("Every year", "كل سنة"), "never": ("Never", "أبداً")},
        "mte_use_verdict": {
            "ok": ("OK", "سليم"),
            "warned": ("Warned", "مع تحذير"),
            "blocked_overridden": ("Blocked, overridden", "محظور مع تجاوز"),
        },
    }
)


def label(kind: str, value: Any, ar: bool = False) -> str:
    v = value.value if isinstance(value, StrEnum) else str(value)
    pair = LABELS.get(kind, {}).get(v)
    if pair is None:
        return v
    return pair[1] if ar else pair[0]


@dataclass
class PartInfo:
    code: str
    title_en: str
    title_ar: str
    record_types: list[QRecordType] = field(default_factory=list)


PARTS = ("Q0", "Q1", "Q2", "Q3", "Q4")
