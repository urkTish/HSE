"""Enumerations of package Q2 materials, testing and lab, welding, calibration, competence
(spec 8-quality Part C). Every class carries the `Q` prefix (D-202 pattern). The EN / AR labels of
these lists live in `Q2_LABELS`; `app.services.quality.q2.register()` merges them into the shared
`LABELS` served by `GET /quality/reference` (D-327), so the UI shows them without message keys."""

from __future__ import annotations

from enum import StrEnum

# ---- materials (§C.1, §C.3) -----------------------------------------------------------------


class QMaterialCategory(StrEnum):
    """List MC."""

    concrete_mix = "concrete_mix"
    cement = "cement"
    aggregates = "aggregates"
    rebar = "rebar"
    structural_steel = "structural_steel"
    blockwork = "blockwork"
    waterproofing = "waterproofing"
    insulation = "insulation"
    pipes_fittings = "pipes_fittings"
    valves = "valves"
    ductwork = "ductwork"
    cables = "cables"
    electrical_equipment = "electrical_equipment"
    mechanical_equipment = "mechanical_equipment"
    coatings = "coatings"
    finishes = "finishes"
    asphalt = "asphalt"
    consumables = "consumables"
    other = "other"


class QMarStatus(StrEnum):
    """§C.3.1 MAR states."""

    draft = "draft"
    submitted = "submitted"
    approved = "approved"  # code A
    approved_as_noted = "approved_as_noted"  # code B
    revise_resubmit = "revise_resubmit"  # code C
    rejected = "rejected"  # code D
    superseded = "superseded"
    withdrawn = "withdrawn"


MAR_APPROVED = frozenset({QMarStatus.approved, QMarStatus.approved_as_noted})
MAR_CODE_STATUS = {
    "A": QMarStatus.approved,
    "B": QMarStatus.approved_as_noted,
    "C": QMarStatus.revise_resubmit,
    "D": QMarStatus.rejected,
}


class QCompliance(StrEnum):
    complies = "complies"
    deviation = "deviation"
    not_applicable = "not_applicable"


class QMirStatus(StrEnum):
    draft = "draft"
    submitted = "submitted"
    decided = "decided"
    cancelled = "cancelled"


class QMirResult(StrEnum):
    accepted = "accepted"
    accepted_with_comments = "accepted_with_comments"
    rejected = "rejected"


class QQuarantineStatus(StrEnum):
    quarantined = "quarantined"
    released = "released"
    returned = "returned"
    scrapped = "scrapped"


# ---- testing (§C.2) ---------------------------------------------------------------------------


class QTestTypeStatus(StrEnum):
    """6d-style versions (Q-TST-01)."""

    draft = "draft"
    published = "published"
    superseded = "superseded"
    retired = "retired"


class QResultFieldKind(StrEnum):
    numeric = "numeric"
    text = "text"
    pass_fail = "pass_fail"


class QEvaluationMode(StrEnum):
    """`fields` = one criterion per result field; `rule` = one criterion of kind rule."""

    fields = "fields"
    rule = "rule"


class QTestStatus(StrEnum):
    """§C.2.3."""

    requested = "requested"
    sampled = "sampled"
    at_lab = "at_lab"
    results_entered = "results_entered"
    verified = "verified"
    amended = "amended"
    cancelled = "cancelled"
    voided = "voided"


TEST_WITH_RESULT = frozenset(
    {QTestStatus.results_entered, QTestStatus.verified, QTestStatus.amended}
)


class QTestVerdict(StrEnum):
    """Q-CRT-01 verdict of a test request (`pending` until results are entered)."""

    pass_ = "pass"
    fail = "fail"
    indicative = "indicative"
    pending = "pending"


class QNcrDecline(StrEnum):
    """Q-TST-06 prompt mode: what the user did with a failed result."""

    raised = "raised"
    declined = "declined"


class QPourStatus(StrEnum):
    """Q-TST-11 pour log."""

    planned = "planned"
    started = "started"
    closed = "closed"
    cancelled = "cancelled"


# ---- welding (§C.6) ---------------------------------------------------------------------------


class QWeldStandard(StrEnum):
    aws_d1_1 = "AWS_D1_1"
    asme_ix = "ASME_IX"
    iso_15614_1 = "ISO_15614_1"
    iso_9606_1 = "ISO_9606_1"
    other = "other"


class QWeldProcess(StrEnum):
    """List WP."""

    smaw = "SMAW"
    gtaw = "GTAW"
    gmaw = "GMAW"
    fcaw = "FCAW"
    saw = "SAW"
    other = "other"


WELD_POSITIONS = (
    "1G",
    "2G",
    "3G",
    "4G",
    "5G",
    "6G",
    "6GR",
    "1F",
    "2F",
    "3F",
    "4F",
)


class QWpsStatus(StrEnum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    superseded = "superseded"
    withdrawn = "withdrawn"


class QPqrStatus(StrEnum):
    draft = "draft"
    approved = "approved"


class QWelderStatus(StrEnum):
    active = "active"
    inactive = "inactive"


class QWpqStatus(StrEnum):
    draft = "draft"
    active = "active"
    lapsed = "lapsed"
    expired = "expired"
    revoked = "revoked"


class QWpqMethod(StrEnum):
    rt = "RT"
    bend = "bend"
    fracture = "fracture"
    macro = "macro"


class QJointType(StrEnum):
    butt = "butt"
    fillet = "fillet"
    branch = "branch"
    socket = "socket"


class QNdtMethod(StrEnum):
    rt = "RT"
    ut = "UT"
    mt = "MT"
    pt = "PT"


class QNdtSelection(StrEnum):
    random = "random"
    progressive = "progressive"
    pct100 = "100pct"


class QAcceptReject(StrEnum):
    accept = "accept"
    reject = "reject"


class QWeldStatus(StrEnum):
    """§C.6 weld transitions."""

    welded = "welded"
    visual_accepted = "visual_accepted"
    visual_rejected = "visual_rejected"
    ndt_pending = "ndt_pending"
    accepted = "accepted"
    rejected = "rejected"
    repaired_r1 = "repaired_r1"
    repaired_r2 = "repaired_r2"
    cut_out = "cut_out"
    voided = "voided"


# ---- calibration (§C.4) -----------------------------------------------------------------------


class QCalKind(StrEnum):
    calibration = "calibration"
    verification = "verification"


class QCalRecordStatus(StrEnum):
    draft = "draft"
    accepted = "accepted"
    rejected = "rejected"


class QMteOverride(StrEnum):
    """Manual M&TE status (Q-CAL-02: manual statuses win)."""

    out_of_service = "out_of_service"
    limited_use = "limited_use"


class QOotStatus(StrEnum):
    open = "open"
    closed = "closed"


class QOotDecision(StrEnum):
    no_impact = "no_impact"
    recheck = "recheck"
    ncr = "ncr"


# ---- competence (§C.5) ------------------------------------------------------------------------


class QCompetenceAppliesTo(StrEnum):
    """List CA."""

    ir_inspector = "ir_inspector"
    test_technician = "test_technician"
    ndt_technician = "ndt_technician"
    welding_inspector = "welding_inspector"
    receiving_inspector = "receiving_inspector"
    mapping_lead = "mapping_lead"
    auditor = "auditor"
    calibration_acceptor = "calibration_acceptor"
    warehouse_qc = "warehouse_qc"
    pharmacist = "pharmacist"
    equipment_operator = "equipment_operator"
    other = "other"


class QCompetencePolicy(StrEnum):
    inherit = "inherit"
    warn = "warn"
    block = "block"


class QEvidenceKind(StrEnum):
    training_course = "training_course"
    personnel_certificate = "personnel_certificate"


class QCompetenceState(StrEnum):
    """Q-CPT-03 matrix cell."""

    met = "met"
    expiring = "expiring"
    not_met = "not_met"
    not_applicable = "not_applicable"


# ---- labels (D-327) -------------------------------------------------------------------------

Q2_LABELS: dict[str, dict[str, tuple[str, str]]] = {
    "material_category": {
        "concrete_mix": ("Concrete mix", "خلطة خرسانية"),
        "cement": ("Cement", "إسمنت"),
        "aggregates": ("Aggregates", "ركام"),
        "rebar": ("Rebar", "حديد تسليح"),
        "structural_steel": ("Structural steel", "حديد إنشائي"),
        "blockwork": ("Blockwork", "بلوك"),
        "waterproofing": ("Waterproofing", "عزل مائي"),
        "insulation": ("Insulation", "عزل حراري"),
        "pipes_fittings": ("Pipes and fittings", "أنابيب وتجهيزات"),
        "valves": ("Valves", "صمامات"),
        "ductwork": ("Ductwork", "مجاري هواء"),
        "cables": ("Cables", "كابلات"),
        "electrical_equipment": ("Electrical equipment", "معدات كهربائية"),
        "mechanical_equipment": ("Mechanical equipment", "معدات ميكانيكية"),
        "coatings": ("Coatings", "دهانات وطلاءات"),
        "finishes": ("Finishes", "تشطيبات"),
        "asphalt": ("Asphalt", "إسفلت"),
        "consumables": ("Consumables", "مستهلكات"),
        "other": ("Other", "أخرى"),
    },
    "mar_status": {
        "draft": ("Draft", "مسودة"),
        "submitted": ("Submitted", "مُقدَّم"),
        "approved": ("Approved (A)", "معتمد (A)"),
        "approved_as_noted": ("Approved as noted (B)", "معتمد مع ملاحظات (B)"),
        "revise_resubmit": ("Revise and resubmit (C)", "يعاد للتعديل (C)"),
        "rejected": ("Rejected (D)", "مرفوض (D)"),
        "superseded": ("Superseded", "مستبدل"),
        "withdrawn": ("Withdrawn", "مسحوب"),
    },
    "mar_code": {
        "A": ("A — Approved", "A — معتمد"),
        "B": ("B — Approved as noted", "B — معتمد مع ملاحظات"),
        "C": ("C — Revise and resubmit", "C — يعاد للتعديل"),
        "D": ("D — Rejected", "D — مرفوض"),
    },
    "compliance": {
        "complies": ("Complies", "مطابق"),
        "deviation": ("Deviation", "انحراف"),
        "not_applicable": ("Not applicable", "لا ينطبق"),
    },
    "mir_status": {
        "draft": ("Draft", "مسودة"),
        "submitted": ("Submitted", "مُقدَّم"),
        "decided": ("Decided", "تم القرار"),
        "cancelled": ("Cancelled", "ملغى"),
    },
    "mir_result": {
        "accepted": ("Accepted", "مقبول"),
        "accepted_with_comments": ("Accepted with comments", "مقبول مع ملاحظات"),
        "rejected": ("Rejected", "مرفوض"),
    },
    "quarantine_status": {
        "quarantined": ("Quarantined", "محجوز"),
        "released": ("Released", "مُفرج عنه"),
        "returned": ("Returned to supplier", "مُعاد للمورد"),
        "scrapped": ("Scrapped", "متلف"),
    },
    "test_type_status": {
        "draft": ("Draft", "مسودة"),
        "published": ("Published", "منشور"),
        "superseded": ("Superseded", "مستبدل"),
        "retired": ("Retired", "موقوف"),
    },
    "result_field_kind": {
        "numeric": ("Number", "رقم"),
        "text": ("Text", "نص"),
        "pass_fail": ("Pass / fail", "ناجح / راسب"),
    },
    "evaluation_mode": {
        "fields": ("One criterion per field", "معيار لكل حقل"),
        "rule": ("Coded rule", "قاعدة مبرمجة"),
    },
    "test_status": {
        "requested": ("Requested", "مطلوب"),
        "sampled": ("Sampled", "أُخذت العينة"),
        "at_lab": ("At lab", "في المختبر"),
        "results_entered": ("Results entered", "أُدخلت النتائج"),
        "verified": ("Verified", "معتمدة"),
        "amended": ("Amended", "معدّلة"),
        "cancelled": ("Cancelled", "ملغى"),
        "voided": ("Voided", "باطل"),
    },
    "test_verdict": {
        "pass": ("Pass", "ناجح"),
        "fail": ("Fail", "راسب"),
        "indicative": ("Indicative", "إرشادي"),
        "pending": ("Pending", "قيد الانتظار"),
    },
    "pour_status": {
        "planned": ("Planned", "مخطط"),
        "started": ("Started", "بدأت"),
        "closed": ("Closed", "مغلقة"),
        "cancelled": ("Cancelled", "ملغاة"),
    },
    "weld_standard": {
        "AWS_D1_1": ("AWS D1.1", "AWS D1.1"),
        "ASME_IX": ("ASME IX", "ASME IX"),
        "ISO_15614_1": ("ISO 15614-1", "ISO 15614-1"),
        "ISO_9606_1": ("ISO 9606-1", "ISO 9606-1"),
        "other": ("Other", "أخرى"),
    },
    "weld_process": {
        "SMAW": ("SMAW (stick)", "SMAW (لحام القوس بالقطب)"),
        "GTAW": ("GTAW (TIG)", "GTAW (تيغ)"),
        "GMAW": ("GMAW (MIG / MAG)", "GMAW (ميغ / ماغ)"),
        "FCAW": ("FCAW (flux-cored)", "FCAW (سلك بقلب مساعد)"),
        "SAW": ("SAW (submerged arc)", "SAW (القوس المغمور)"),
        "other": ("Other", "أخرى"),
    },
    "wps_status": {
        "draft": ("Draft", "مسودة"),
        "submitted": ("Submitted", "مُقدَّمة"),
        "approved": ("Approved", "معتمدة"),
        "superseded": ("Superseded", "مستبدلة"),
        "withdrawn": ("Withdrawn", "مسحوبة"),
    },
    "pqr_status": {"draft": ("Draft", "مسودة"), "approved": ("Approved", "معتمد")},
    "welder_status": {"active": ("Active", "نشط"), "inactive": ("Inactive", "غير نشط")},
    "wpq_status": {
        "draft": ("Draft", "مسودة"),
        "active": ("Active", "ساري"),
        "lapsed": ("Lapsed (continuity)", "منقطع (الاستمرارية)"),
        "expired": ("Expired (revalidation)", "منتهي (إعادة التأهيل)"),
        "revoked": ("Revoked", "ملغى"),
    },
    "wpq_method": {
        "RT": ("Radiography", "تصوير إشعاعي"),
        "bend": ("Bend test", "اختبار الثني"),
        "fracture": ("Fracture test", "اختبار الكسر"),
        "macro": ("Macro examination", "فحص مجهري كلي"),
    },
    "joint_type": {
        "butt": ("Butt", "تناكبي"),
        "fillet": ("Fillet", "زاوي"),
        "branch": ("Branch", "تفرع"),
        "socket": ("Socket", "مقبس"),
    },
    "ndt_method": {
        "RT": ("RT (radiography)", "RT (تصوير إشعاعي)"),
        "UT": ("UT (ultrasonic)", "UT (موجات فوق صوتية)"),
        "MT": ("MT (magnetic particle)", "MT (جسيمات مغناطيسية)"),
        "PT": ("PT (penetrant)", "PT (سائل نافذ)"),
    },
    "ndt_selection": {
        "random": ("Random", "عشوائي"),
        "progressive": ("Progressive", "تصاعدي"),
        "100pct": ("100 %", "100 %"),
    },
    "accept_reject": {"accept": ("Accept", "مقبول"), "reject": ("Reject", "مرفوض")},
    "weld_status": {
        "welded": ("Welded", "منفّذ"),
        "visual_accepted": ("Visual accepted", "مقبول بصرياً"),
        "visual_rejected": ("Visual rejected", "مرفوض بصرياً"),
        "ndt_pending": ("NDT pending", "بانتظار الفحص غير الإتلافي"),
        "accepted": ("Accepted", "مقبول"),
        "rejected": ("Rejected", "مرفوض"),
        "repaired_r1": ("Repaired R1", "إصلاح أول"),
        "repaired_r2": ("Repaired R2", "إصلاح ثانٍ"),
        "cut_out": ("Cut out", "مقطوع"),
        "voided": ("Voided", "باطل"),
    },
    "cal_kind": {
        "calibration": ("Calibration", "معايرة"),
        "verification": ("Verification", "تحقق"),
    },
    "cal_record_status": {
        "draft": ("Draft", "مسودة"),
        "accepted": ("Accepted", "مقبول"),
        "rejected": ("Rejected", "مرفوض"),
    },
    "mte_override": {
        "out_of_service": ("Out of service", "خارج الخدمة"),
        "limited_use": ("Limited use", "استخدام محدود"),
    },
    "oot_status": {"open": ("Open", "مفتوحة"), "closed": ("Closed", "مغلقة")},
    "oot_decision": {
        "no_impact": ("No impact", "لا أثر"),
        "recheck": ("Re-check", "إعادة فحص"),
        "ncr": ("Raise NCR", "تقرير عدم مطابقة"),
    },
    "competence_applies_to": {
        "ir_inspector": ("IR inspector", "مفتش طلبات الفحص"),
        "test_technician": ("Test technician", "فني اختبارات"),
        "ndt_technician": ("NDT technician", "فني فحص غير إتلافي"),
        "welding_inspector": ("Welding inspector", "مفتش لحام"),
        "receiving_inspector": ("Receiving inspector", "مفتش استلام"),
        "mapping_lead": ("Mapping lead", "قائد دراسة التوزيع الحراري"),
        "auditor": ("Auditor", "مدقق"),
        "calibration_acceptor": ("Calibration acceptor", "معتمد المعايرة"),
        "warehouse_qc": ("Warehouse QC", "مراقب جودة المستودع"),
        "pharmacist": ("Pharmacist", "صيدلي"),
        "equipment_operator": ("Equipment operator", "مشغل معدات"),
        "other": ("Other", "أخرى"),
    },
    "competence_policy": {
        "inherit": ("Project setting", "حسب إعداد المشروع"),
        "warn": ("Warn", "تحذير"),
        "block": ("Block", "منع"),
    },
    "evidence_kind": {
        "training_course": ("Training course", "دورة تدريبية"),
        "personnel_certificate": ("Personnel certificate", "شهادة أفراد"),
    },
    "competence_state": {
        "met": ("Met", "مستوفى"),
        "expiring": ("Expiring", "قارب على الانتهاء"),
        "not_met": ("Not met", "غير مستوفى"),
        "not_applicable": ("Not applicable", "لا ينطبق"),
    },
}
