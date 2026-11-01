"""Enumerations of package Q4: document control, quality audits and management review, supplier
evaluation and scorecards, KPIs K-141…K-169, SPC, COPQ / DPMO / sigma, report packs and AI tools
(spec 8-quality Part E). Arabic names follow the spec tables."""

from __future__ import annotations

from enum import StrEnum

# ---- documents (§E.1.2) -------------------------------------------------------------------------


class QDocType(StrEnum):
    """List DT (prefix in `DOC_PREFIX`)."""

    pqp = "pqp"
    quality_manual = "quality_manual"
    procedure = "procedure"
    work_instruction = "work_instruction"
    sop = "sop"
    method_statement = "method_statement"
    specification = "specification"
    form = "form"
    other = "other"


DOC_PREFIX: dict[QDocType, str] = {
    QDocType.pqp: "PQP",
    QDocType.quality_manual: "QM",
    QDocType.procedure: "PRC",
    QDocType.work_instruction: "WI",
    QDocType.sop: "SOP",
    QDocType.method_statement: "MS",
    QDocType.specification: "SPC",
    QDocType.form: "FRM",
    QDocType.other: "DOC",
}
DOC_TYPE_LABELS: dict[QDocType, tuple[str, str]] = {
    QDocType.pqp: ("Project Quality Plan", "خطة الجودة للمشروع"),
    QDocType.quality_manual: ("Quality manual", "دليل الجودة"),
    QDocType.procedure: ("Procedure", "إجراء"),
    QDocType.work_instruction: ("Work instruction", "تعليمات عمل"),
    QDocType.sop: ("Standard operating procedure", "إجراء تشغيل قياسي"),
    QDocType.method_statement: ("Method statement", "بيان طريقة العمل"),
    QDocType.specification: ("Specification", "مواصفة"),
    QDocType.form: ("Form", "نموذج"),
    QDocType.other: ("Other", "أخرى"),
}


class QRevStatus(StrEnum):
    """§E.1.2 revision states (the document's status is its current revision's)."""

    draft = "draft"  # مسودة
    for_review = "for_review"  # قيد المراجعة
    approved = "approved"  # معتمدة
    superseded = "superseded"  # مستبدلة
    obsolete = "obsolete"  # ملغاة


class QRevisionScheme(StrEnum):
    letters_then_numbers = "letters_then_numbers"
    numbers = "numbers"


class QTransmittalPurpose(StrEnum):
    for_approval = "for_approval"
    for_review = "for_review"
    for_information = "for_information"
    for_construction = "for_construction"
    as_built = "as_built"


class QTransmittalMethod(StrEnum):
    email = "email"
    portal = "portal"
    hand = "hand"


class QTransmittalTo(StrEnum):
    engagement = "engagement"
    supplier = "supplier"
    customer = "customer"
    external = "external"


class QTransmittalStatus(StrEnum):
    draft = "draft"  # مسودة
    sent = "sent"  # مرسلة
    responded = "responded"  # تم الرد
    cancelled = "cancelled"  # ملغاة


class QResponseCode(StrEnum):
    """Per-item response A / B / C / D (approved · approved as noted · revise and resubmit ·
    rejected)."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"


class QTransmittalItemKind(StrEnum):
    document_revision = "document_revision"
    record = "record"


# ---- audits, processes, programme, management review (§E.2) -------------------------------------


class QRisk(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class QProgrammeSubject(StrEnum):
    process = "process"
    supplier = "supplier"
    engagement = "engagement"
    clause_set = "clause_set"


class QProgrammeStatus(StrEnum):
    planned = "planned"  # مخطط
    scheduled = "scheduled"  # مجدول
    done = "done"  # منجز
    postponed = "postponed"  # مؤجل
    cancelled = "cancelled"  # ملغى


class QMrvStatus(StrEnum):
    draft = "draft"  # مسودة
    held = "held"  # عُقدت
    minutes_issued = "minutes_issued"  # صدر المحضر


# ISO 9001:2015 9.3.2 inputs (Q-MRV-01): key, EN, AR
MRV_INPUTS: tuple[tuple[str, str, str], ...] = (
    ("previous_actions", "Status of actions from previous reviews",
     "حالة الإجراءات من المراجعات السابقة"),
    ("issues", "Changes in external and internal issues", "التغيرات في القضايا الخارجية والداخلية"),
    ("customer", "Customer satisfaction and feedback", "رضا العملاء والتغذية الراجعة"),
    ("objectives", "Extent to which quality objectives were met", "مدى تحقيق أهداف الجودة"),
    ("process_performance", "Process performance and conformity of products and services",
     "أداء العمليات ومطابقة المنتجات والخدمات"),
    ("nonconformities", "Nonconformities and corrective actions",
     "حالات عدم المطابقة والإجراءات التصحيحية"),
    ("monitoring", "Monitoring and measurement results", "نتائج الرصد والقياس"),
    ("audits", "Audit results", "نتائج التدقيق"),
    ("external_providers", "Performance of external providers", "أداء المزودين الخارجيين"),
    ("resources", "Adequacy of resources", "كفاية الموارد"),
    ("risks", "Effectiveness of actions on risks and opportunities",
     "فعالية الإجراءات المتخذة للمخاطر والفرص"),
    ("improvement", "Opportunities for improvement", "فرص التحسين"),
)  # fmt: skip
MRV_INPUT_KEYS: tuple[str, ...] = tuple(k for k, _, _ in MRV_INPUTS)


class QMrvOutputKind(StrEnum):
    improvement = "improvement"
    qms_change = "qms_change"
    resource = "resource"


# ---- suppliers (§E.3) -----------------------------------------------------------------------------


class QSevKind(StrEnum):
    initial = "initial"
    periodic = "periodic"
    for_cause = "for_cause"


class QSevMethod(StrEnum):
    questionnaire = "questionnaire"
    audit = "audit"
    document_review = "document_review"
    trial_order = "trial_order"


class QSevRecommendation(StrEnum):
    approve = "approve"
    conditional = "conditional"
    reject = "reject"
    suspend = "suspend"


class QSevStatus(StrEnum):
    draft = "draft"  # مسودة
    submitted = "submitted"  # مُقدَّم
    approved = "approved"  # معتمد
    cancelled = "cancelled"  # ملغى


class QScoreStatus(StrEnum):
    provisional = "provisional"
    final = "final"


class QScorePeriod(StrEnum):
    month = "month"
    quarter = "quarter"


SCORE_METRICS: tuple[tuple[str, str, str], ...] = (
    ("M1", "Acceptance", "القبول"),
    ("M2", "NCR rate", "معدل تقارير عدم المطابقة"),
    ("M3", "On-time delivery", "التسليم في الموعد"),
    ("M4", "Test conformity", "مطابقة الاختبارات"),
    ("M5", "Responsiveness", "الاستجابة"),
    ("M6", "Documents", "المستندات"),
)


# ---- SPC (§E.5) -----------------------------------------------------------------------------------


class QSpcType(StrEnum):
    xbar_r = "xbar_r"
    imr = "imr"
    p = "p"


class QSpcSource(StrEnum):
    """Registry list SPCS with the chart type each source supports."""

    conc_strength_28d = "conc_strength_28d"
    slump = "slump"
    dft_spot = "dft_spot"
    compaction_pct = "compaction_pct"
    zone_daily_mean_temp = "zone_daily_mean_temp"
    ir_rejection_weekly = "ir_rejection_weekly"
    receiving_rejection_weekly = "receiving_rejection_weekly"


SPC_SOURCE_TYPES: dict[QSpcSource, QSpcType] = {
    QSpcSource.conc_strength_28d: QSpcType.xbar_r,
    QSpcSource.slump: QSpcType.imr,
    QSpcSource.dft_spot: QSpcType.xbar_r,
    QSpcSource.compaction_pct: QSpcType.imr,
    QSpcSource.zone_daily_mean_temp: QSpcType.imr,
    QSpcSource.ir_rejection_weekly: QSpcType.p,
    QSpcSource.receiving_rejection_weekly: QSpcType.p,
}


class QSpcBaseline(StrEnum):
    frozen = "frozen"
    rolling = "rolling"


# ---- KPIs (§E.4) ----------------------------------------------------------------------------------


class QKpi(StrEnum):
    K141 = "K-141"
    K142 = "K-142"
    K143 = "K-143"
    K144 = "K-144"
    K145 = "K-145"
    K146 = "K-146"
    K147 = "K-147"
    K148 = "K-148"
    K149 = "K-149"
    K150 = "K-150"
    K151 = "K-151"
    K152 = "K-152"
    K153 = "K-153"
    K154 = "K-154"
    K155 = "K-155"
    K156 = "K-156"
    K157 = "K-157"
    K158 = "K-158"
    K159 = "K-159"
    K160 = "K-160"
    K161 = "K-161"
    K162 = "K-162"
    K163 = "K-163"
    K164 = "K-164"
    K165 = "K-165"
    K166 = "K-166"
    K167 = "K-167"
    K168 = "K-168"
    K169 = "K-169"


class QWarning(StrEnum):
    E26 = "E26"
    E27 = "E27"
    E28 = "E28"


class QPackType(StrEnum):
    QMR = "QMR"
    QNCR = "QNCR"
    QSUP = "QSUP"
    QMRV = "QMRV"
