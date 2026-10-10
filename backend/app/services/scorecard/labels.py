"""EN/AR labels of the 6g reference lists (spec 6g §3.10) served by GET /scorecard-reference and
used by the packs."""

from __future__ import annotations

from app.services.scorecard import common as cm

L = list[tuple[str, str, str, str | None]]

PILLARS: L = [
    ("LAG", "Lagging indicators", "المؤشرات المتأخرة", "30"),
    ("OBS", "Observations and reporting", "الملاحظات والإبلاغ", "7"),
    ("CA", "Corrective actions", "الإجراءات التصحيحية", "10"),
    ("PTW", "Permits to work", "تصاريح العمل", "10"),
    ("CERT", "Certificates and equipment", "الشهادات والمعدات", "8"),
    ("TRN", "Training and induction", "التدريب والتعريف", "7"),
    ("FIT", "Medical fitness", "اللياقة الطبية", "4"),
    ("HEAT", "Heat stress", "الإجهاد الحراري", "4"),
    ("EMG", "Emergency", "الطوارئ", "4"),
    ("INS", "Inspections and audits", "التفتيش والتدقيق", "7"),
    ("TBT", "Toolbox talks", "اجتماعات التوعية", "3"),
    ("ENV", "Environment", "البيئة", "3"),
    ("NOT", "Notifications and lessons", "الإخطار والدروس", "3"),
]
METRIC_LABELS: dict[str, tuple[str, str]] = {
    "SM-TRIR": ("TRIR (12 months)", "معدل الإصابات المسجلة (12 شهراً)"),
    "SM-LTIFR": ("LTIFR (12 months)", "معدل تكرار الإصابات المضيعة للوقت"),
    "SM-LTISR": ("LTISR (12 months)", "معدل شدة الإصابات"),
    "SM-HIPO": ("HiPo event rate", "معدل الأحداث عالية الخطورة"),
    "SM-OBS": ("Observation rate", "معدل الملاحظات"),
    "SM-UNSAFE-CLOSE": ("Unsafe observation close-out", "إغلاق الملاحظات غير الآمنة"),
    "SM-CA-ONTIME": ("CA on-time closure", "إغلاق الإجراءات في الموعد"),
    "SM-CA-OVERDUE": ("Overdue CAs per 100 workers", "الإجراءات المتأخرة لكل 100 عامل"),
    "SM-PTW-AUDIT": ("PTW audit compliance", "الالتزام في تدقيق التصاريح"),
    "SM-PTW-CRIT": ("Critical PTW findings per 100 audits", "الملاحظات الحرجة لكل 100 تدقيق"),
    "SM-PTW-CLOSE": ("Permit closure compliance", "الالتزام بإغلاق التصاريح"),
    "SM-EQ-CERT": ("Equipment certificate compliance", "الالتزام بشهادات المعدات"),
    "SM-PERS-CERT": ("Personnel certification compliance", "الالتزام بشهادات الأفراد"),
    "SM-SCAF-TAG": ("Scaffold tag compliance", "الالتزام ببطاقات السقالات"),
    "SM-TRAIN": ("Training matrix compliance", "الالتزام بمصفوفة التدريب"),
    "SM-INDUCT": ("Induction coverage", "تغطية التعريف"),
    "SM-FIT": ("Medical fitness compliance", "الالتزام باللياقة الطبية"),
    "SM-HEAT-WELF": ("Heat welfare compliance", "الالتزام بالرعاية الحرارية"),
    "SM-HEAT-BAN": ("Midday-ban violations per 100 patrols", "مخالفات حظر الظهيرة لكل 100 جولة"),
    "SM-EMG-COVER": ("Emergency team coverage", "تغطية فرق الطوارئ"),
    "SM-EMG-EQUIP": ("Emergency equipment readiness", "جاهزية معدات الطوارئ"),
    "SM-CHECKLIST": ("Checklist compliance score", "نسبة المطابقة في قوائم التفتيش"),
    "SM-INSP-COVER": ("Contractor inspection coverage", "تغطية تفتيش المقاول"),
    "SM-AUDIT": ("HSE audit score", "نتيجة تدقيق السلامة"),
    "SM-TBT": ("Toolbox weekly reach", "الوصول الأسبوعي لاجتماعات التوعية"),
    "SM-WASTE-COC": ("Waste chain of custody on time", "سلسلة حيازة النفايات في الموعد"),
    "SM-SPILL": ("Spill rate", "معدل الانسكابات"),
    "SM-NOTIF": ("Notifications on time", "الإخطارات في الموعد"),
    "SM-LESSON-ACK": ("Lesson acknowledgement on time", "الإقرار بالدروس في الموعد"),
}
GRADES = {
    "A": ("Good", "جيد"),
    "B": ("Satisfactory", "مُرضٍ"),
    "C": ("Needs improvement", "يحتاج إلى تحسين"),
    "D": ("Poor", "ضعيف"),
    "—": ("Insufficient data", "بيانات غير كافية"),
}
RT = {
    "MCR": ("Monthly client HSE report", "تقرير الصحة والسلامة الشهري للعميل"),
    "SCP": ("Contractor scorecard pack", "حزمة بطاقة أداء المقاول"),
    "CPS": ("Contractor performance summary", "ملخص أداء المقاول"),
    "OSHA300": ("OSHA 300-style log (benchmark; not a KSA statutory form)",
                "سجل الإصابات السنوي (مرجعي؛ ليس نموذجاً نظامياً سعودياً)"),
    "HEAT": ("Heat season report", "تقرير موسم الحرارة"),
}  # fmt: skip

LISTS: dict[str, L] = {
    "pillars": PILLARS,
    "metrics": [
        (
            m.code.value,
            *METRIC_LABELS[m.code.value],
            f"{m.pillar.value} · {m.kpi} · {m.window.value}",
        )
        for m in cm.METRICS
    ],
    "caps": [
        ("CP-1", "Fatality or permanent disability → max D", "وفاة أو عجز دائم ← بحد أقصى D", "D"),
        ("CP-2", "Lost-time injury → max C", "إصابة مضيعة للوقت ← بحد أقصى C", "C"),
        (
            "CP-3",
            "Statutory or reporting breach → max B",
            "مخالفة نظامية أو تأخر إبلاغ ← بحد أقصى B",
            "B",
        ),
    ],
    "grades": [(g, en, ar, None) for g, (en, ar) in GRADES.items()],
    "dispute_reasons": [
        ("data_error", "Data error", "خطأ في البيانات", None),
        ("wrong_attribution", "Wrong attribution", "نُسب لمقاول آخر", None),
        ("not_applicable", "Not applicable to our work", "لا ينطبق على نشاطنا", None),
        ("other", "Other", "أخرى", None),
    ],
    "watch_levels": [
        ("watch", "Watch", "تحت المراقبة", None),
        ("improvement_plan", "Improvement plan", "خطة تحسين الأداء", None),
        ("suspension_review", "Suspension review", "مراجعة الإيقاف", None),
    ],
    "report_types": [(k, en, ar, None) for k, (en, ar) in RT.items()],
    "export_purposes": [
        ("gosi", "GOSI", "التأمينات الاجتماعية", None),
        ("mhrsd", "MHRSD", "وزارة الموارد البشرية", None),
        ("client_report", "Client report", "تقرير العميل", None),
        ("legal", "Legal", "قانوني", None),
        ("insurance", "Insurance", "التأمين", None),
        ("audit", "Audit", "التدقيق", None),
        ("data_subject_request", "Data subject request", "طلب صاحب البيانات", None),
        ("internal_analysis", "Internal analysis", "تحليل داخلي", None),
        ("other", "Other (text ≥ 20 chars)", "أخرى", None),
    ],
    "mask_modes": [
        ("omit", "Column dropped", "حذف العمود", None),
        ("mask_id", "Masked ID (2*******89)", "رقم مقنّع", None),
        ("person_n", "Person n · trade · employer", "شخص n · المهنة · صاحب العمل", None),
        ("role_only", "Role only", "الدور فقط", None),
        ("privacy_case", "Privacy case", "حالة خصوصية", None),
    ],
    "card_statuses": [
        ("provisional", "Provisional", "مبدئية", None),
        ("issued", "Issued for comment", "صادرة للملاحظات", None),
        ("final", "Final", "معتمدة", None),
        ("superseded", "Superseded", "مستبدلة", None),
    ],
    "line_statuses": [
        ("scored", "Scored", "محتسب", None),
        ("not_applicable", "Not applicable", "غير منطبق", None),
        ("insufficient_volume", "Insufficient volume", "حجم غير كافٍ", None),
        ("source_not_live", "Module not live", "الوحدة غير مفعلة", None),
        ("excluded_by_manager", "Excluded by decision", "مستبعد بقرار", None),
    ],
    "remark_statuses": [
        ("open", "Open", "مفتوح", None),
        ("resolved", "Resolved", "تم البت", None),
        ("withdrawn", "Withdrawn", "مسحوب", None),
    ],
    "resolutions": [
        ("upheld_data_corrected", "Upheld, data corrected", "قُبل وصُحّحت البيانات", None),
        ("upheld_metric_excluded", "Upheld, metric excluded", "قُبل واستُبعد المقياس", None),
        ("rejected", "Rejected", "رُفض", None),
    ],
    "decisions": [
        ("suspend", "Suspend (Phase 0 form)", "إيقاف (نموذج المرحلة 0)", None),
        ("continue_with_conditions", "Continue with conditions", "الاستمرار بشروط", None),
        ("remove_from_project", "Remove from project", "الإخراج من المشروع", None),
    ],
    "pack_statuses": [
        ("draft", "Draft", "مسودة", None),
        ("in_review", "In review", "قيد المراجعة", None),
        ("issued", "Issued", "صادرة", None),
        ("superseded", "Superseded", "مستبدلة", None),
    ],
    "export_statuses": [
        ("queued", "Queued", "في الانتظار", None),
        ("ready", "Ready", "جاهز", None),
        ("expired", "Expired", "منتهي الصلاحية", None),
        ("failed", "Failed", "فشل", None),
    ],
    "delivery_statuses": [
        ("queued", "Queued", "في الانتظار", None),
        ("sent", "Sent", "أُرسل", None),
        ("bounced", "Bounced", "مرتد", None),
        ("failed", "Failed", "فشل", None),
    ],
    "modules": [
        ("access", "Access (Phase 2)", "التصاريح والدخول", None),
        ("ptw", "Permit to work (Phase 3)", "تصاريح العمل", None),
        ("cert", "Certification (Phase 4)", "الشهادات", None),
        ("training", "Training (Phase 5)", "التدريب", None),
        ("medical", "Occupational health (6a)", "الصحة المهنية", None),
        ("heat", "Heat stress (6b)", "الإجهاد الحراري", None),
        ("emergency", "Emergency (6c)", "الطوارئ", None),
        ("field", "Field assurance (6d)", "ضمان الميدان", None),
        ("toolbox", "Toolbox talks (6d)", "اجتماعات التوعية", None),
        ("env", "Environment (6e)", "البيئة", None),
        ("followup", "Incident follow-up (6f)", "متابعة الحوادث", None),
    ],
}
