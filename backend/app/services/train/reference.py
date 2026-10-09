"""Phase 5 reference data (spec 5-training §3.15): the seeded course catalogue (32 courses, v1.2
adds WAH-RESCUE), list labels, hook codes (HK5-2) and the settings defaults (§3.16)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.core.access_enums import WorkerLanguage
from app.core.cert_enums import HookReasonCode
from app.core.train_enums import (
    AccreditationBodyCode,
    CourseCategory,
    DeliveryMode,
    MatrixRole,
    SessionVoidReason,
)

CAT = CourseCategory
ACB = AccreditationBodyCode
D = DeliveryMode
L = WorkerLanguage

ALL_LANGS = (L.ar, L.en, L.ur, L.hi, L.bn, L.ne, L.tl, L.ml)
PRACTICAL_MODES = (D.classroom, D.practical, D.blended)
THEORY_MODES = (D.classroom, D.blended, D.e_learning)
CLASS_SIZE: dict[CourseCategory, int] = {
    CAT.awareness: 30,
    CAT.aviation_security: 25,
    CAT.airside_operations: 12,
    CAT.high_risk_task: 12,
    CAT.ptw_role: 12,
    CAT.emergency_response: 12,
    CAT.electrical: 12,
    CAT.professional_qualification: 30,
}


@dataclass(frozen=True)
class Course:
    code: str
    name_en: str
    name_ar: str
    category: CourseCategory
    validity: int | None = None
    hours: str | None = None
    theory: bool = True
    practical: bool = False
    internal: bool = True
    contractor: bool = False
    bodies: tuple[AccreditationBodyCode, ...] = ()
    prereq: tuple[str, ...] = ()
    satisfies: tuple[str, ...] = ()
    renewal: str | None = None
    renews_only: bool = False
    induction_type: str | None = None
    induction_codes: dict[str, str] = field(default_factory=dict)

    @property
    def max_class_size(self) -> int | None:
        return None if self.category == CAT.induction_link else CLASS_SIZE[self.category]

    @property
    def delivery_modes(self) -> tuple[DeliveryMode, ...]:
        if self.category == CAT.induction_link:
            return ()
        return PRACTICAL_MODES if self.practical else THEORY_MODES

    @property
    def languages(self) -> tuple[WorkerLanguage, ...]:
        if self.category == CAT.induction_link:
            return ()
        if self.category == CAT.professional_qualification:
            return (L.en, L.ar)
        return ALL_LANGS


def _ext(
    code: str, en: str, ar: str, validity: int | None, hours: str, body: ACB, **kw: object
) -> Course:
    return Course(
        code, en, ar, CAT.professional_qualification, validity, hours, theory=False,
        internal=False, bodies=(body,), **kw,  # type: ignore[arg-type]
    )  # fmt: skip


CATALOGUE: tuple[Course, ...] = (
    Course("IND-GENERAL", "General site induction (link)", "التعريف العام بالموقع (ربط)",
           CAT.induction_link, theory=False, internal=False, induction_type="general_site"),
    Course("IND-AIRSIDE", "Airside induction (link)", "التعريف بالجانب الجوي (ربط)",
           CAT.induction_link, theory=False, internal=False, induction_type="airside"),
    Course("IND-ZONE-ILS", "ILS critical-area briefing (link)",
           "إحاطة المنطقة الحرجة لنظام ILS (ربط)", CAT.induction_link, theory=False,
           internal=False, induction_type="zone_specific", induction_codes={"ANIA-EXP": "ILS"}),
    Course("IND-ZONE-TC", "Tower-crane zone briefing (link)",
           "إحاطة منطقة الرافعة البرجية (ربط)", CAT.induction_link, theory=False,
           internal=False, induction_type="zone_specific", induction_codes={"RBT-52": "TC"}),
    Course("AVSEC-AWR", "Aviation security awareness", "التوعية بأمن الطيران",
           CAT.aviation_security, 12, "3.00", internal=False, bodies=(ACB.gaca_avsec,)),
    Course("AIRSIDE-DRV", "Airside driver training", "تدريب القيادة في الجانب الجوي",
           CAT.airside_operations, 24, "4.00", practical=True, internal=False,
           bodies=(ACB.airport_operator,), prereq=("IND-AIRSIDE",)),
    Course("AIRSIDE-RTF", "Radiotelephony for manoeuvring-area drivers",
           "الاتصال اللاسلكي لسائقي منطقة المناورة", CAT.airside_operations, 24, "4.00",
           practical=True, internal=False, bodies=(ACB.airport_operator,),
           prereq=("AIRSIDE-DRV",)),
    Course("WAH", "Working at height — user, fall arrest and rescue awareness",
           "العمل على ارتفاعات", CAT.high_risk_task, 24, "8.00", practical=True),
    Course("CSE-ENTRANT", "Confined space entrant", "الداخل إلى الأماكن المحصورة",
           CAT.high_risk_task, 24, "8.00", practical=True),
    Course("CSE-ATTENDANT", "Confined space attendant (standby)",
           "المناوب عند الأماكن المحصورة", CAT.high_risk_task, 24, "8.00", practical=True),
    Course("CSE-RESCUE", "Confined space rescue team", "فريق إنقاذ الأماكن المحصورة",
           CAT.high_risk_task, 12, "16.00", practical=True,
           prereq=("CSE-ENTRANT", "FIRST-AID"), satisfies=("CSE-ENTRANT", "CSE-ATTENDANT")),
    # 5-training v1.2 §11.6 (6c): height rescue teams (RT-2)
    Course("WAH-RESCUE", "Rescue from height", "الإنقاذ من المرتفعات", CAT.high_risk_task, 24,
           "8.00", practical=True, prereq=("WAH",)),
    Course("GAS-TEST", "Gas testing (atmospheric monitoring)", "فحص الغازات", CAT.ptw_role, 24,
           "8.00", practical=True),
    Course("H2S-AWR", "H₂S awareness and escape", "التوعية بغاز كبريتيد الهيدروجين والهروب",
           CAT.awareness, 12, "4.00", practical=True),
    Course("FIRE-WATCH", "Fire watch", "مراقب الحريق", CAT.ptw_role, 24, "4.00", practical=True),
    Course("FIRE-WARDEN", "Fire warden", "مسؤول الإخلاء والحريق", CAT.emergency_response, 24,
           "4.00", practical=True),
    Course("FIRST-AID", "First aid, CPR and AED", "الإسعافات الأولية والإنعاش القلبي الرئوي",
           CAT.emergency_response, 24, "16.00", practical=True, internal=False,
           bodies=(ACB.srca, ACB.aha, ACB.erc), renewal="FIRST-AID-R"),
    Course("FIRST-AID-R", "First aid refresher", "تجديد الإسعافات الأولية",
           CAT.emergency_response, 24, "8.00", practical=True, internal=False,
           bodies=(ACB.srca, ACB.aha, ACB.erc), satisfies=("FIRST-AID",), renews_only=True),
    Course("SCAFF-AWR", "Scaffold user awareness", "التوعية باستخدام السقالات", CAT.awareness,
           24, "2.00", contractor=True),
    Course("LOTO", "Lockout/tagout awareness (affected and authorised worker)",
           "التوعية بالعزل والقفل والوسم", CAT.electrical, 36, "4.00", practical=True),
    Course("LOTO-AUTHORITY", "Isolation authority", "مسؤول العزل", CAT.ptw_role, 24, "16.00",
           practical=True, prereq=("LOTO",), satisfies=("LOTO",)),
    Course("ELEC-QUALIFIED", "Electrical safety — qualified person (NFPA 70E)",
           "السلامة الكهربائية — الشخص المؤهل", CAT.electrical, 36, "16.00", practical=True,
           prereq=("LOTO",)),
    Course("BANKSMAN-AWR", "Banksman / traffic-marshal awareness",
           "التوعية بتنظيم حركة المعدات", CAT.awareness, 24, "4.00", practical=True,
           contractor=True),
    Course("HEAT-AWR", "Heat stress awareness", "التوعية بالإجهاد الحراري", CAT.awareness, 12,
           "1.50", contractor=True),
    Course("PTW-RECEIVER", "PTW receiver", "مستلم تصريح العمل", CAT.ptw_role, 24, "8.00"),
    Course("PTW-ISSUER", "PTW issuer", "مُصدِر تصريح العمل", CAT.ptw_role, 24, "16.00",
           practical=True, satisfies=("PTW-RECEIVER",)),
    _ext("NEBOSH-IGC", "NEBOSH International General Certificate",
         "الشهادة العامة الدولية من NEBOSH", None, "80.00", ACB.nebosh),
    _ext("NEBOSH-ICC", "NEBOSH International Construction Certificate",
         "شهادة البناء الدولية من NEBOSH", None, "80.00", ACB.nebosh),
    _ext("NEBOSH-DIP", "NEBOSH International Diploma", "الدبلوم الدولي من NEBOSH", None,
         "400.00", ACB.nebosh, satisfies=("NEBOSH-IGC",)),
    _ext("IOSH-MS", "IOSH Managing Safely", "إدارة السلامة من IOSH", 36, "24.00", ACB.iosh,
         renewal="IOSH-MS-R"),
    _ext("IOSH-MS-R", "IOSH Managing Safely refresher", "تجديد إدارة السلامة من IOSH", 36,
         "7.00", ACB.iosh, satisfies=("IOSH-MS",), renews_only=True),
    _ext("OSHA-30", "OSHA 30-hour Construction (Outreach)", "دورة OSHA الإنشائية 30 ساعة", None,
         "30.00", ACB.osha_otc),
)  # fmt: skip
BY_CODE = {c.code: c for c in CATALOGUE}
assert len(CATALOGUE) == 32  # noqa: S101

# HK5-2: codes called by Phases 2–3 today (the first list).
HOOK_CODES_TODAY = (
    "AVSEC-AWR",
    "AIRSIDE-DRV",
    "FIRE-WATCH",
    "CSE-ENTRANT",
    "CSE-ATTENDANT",
    "CSE-RESCUE",
    "WAH",
    "LOTO",
    "ELEC-QUALIFIED",
    "GAS-TEST",
    "PTW-ISSUER",
    "PTW-RECEIVER",
    "LOTO-AUTHORITY",
)
DEFAULT_CRITICAL = (
    "CSE-ENTRANT",
    "CSE-ATTENDANT",
    "CSE-RESCUE",
    "GAS-TEST",
    "FIRE-WATCH",
    "WAH",
    "LOTO",
    "LOTO-AUTHORITY",
)
DEFAULT_LANGUAGE_BLOCK = (
    CAT.high_risk_task,
    CAT.ptw_role,
    CAT.emergency_response,
    CAT.aviation_security,
    CAT.airside_operations,
)
ALERT_SCHEDULE_LONG = [30, 14, 7, 0]
EVIDENCE_CATEGORIES = frozenset({CAT.high_risk_task, CAT.ptw_role, CAT.emergency_response})
ANY_OF_CATEGORIES = frozenset({CAT.professional_qualification, CAT.awareness})
ADP_CATEGORIES = ("apron", "manoeuvring", "airside_roads")
EXEMPTION_MAX_MONTHS = 6
SESSION_MAX_DAYS = 15
ATTEMPTS_WINDOW_DAYS = 30
HOURS_PER_DAY_CAP = Decimal("16")

# ---- labels -------------------------------------------------------------------------------------

CATEGORY_LABELS: dict[CourseCategory, tuple[str, str]] = {
    CAT.induction_link: ("Phase 2 induction link", "ربط بتعريف المرحلة 2"),
    CAT.awareness: ("Awareness", "توعية"),
    CAT.high_risk_task: ("High-risk task", "مهام عالية الخطورة"),
    CAT.ptw_role: ("PTW role", "أدوار تصاريح العمل"),
    CAT.emergency_response: ("Emergency response", "الاستجابة للطوارئ"),
    CAT.aviation_security: ("Aviation security", "أمن الطيران"),
    CAT.airside_operations: ("Airside operations", "عمليات الجانب الجوي"),
    CAT.electrical: ("Electrical safety", "السلامة الكهربائية"),
    CAT.professional_qualification: ("Professional qualification", "مؤهل مهني في السلامة"),
}
BODY_LABELS: dict[AccreditationBodyCode, tuple[str, str]] = {
    ACB.srca: ("Saudi Red Crescent Authority", "هيئة الهلال الأحمر السعودي"),
    ACB.aha: ("American Heart Association", "جمعية القلب الأمريكية"),
    ACB.erc: ("European Resuscitation Council", "المجلس الأوروبي للإنعاش"),
    ACB.gaca_avsec: (
        "GACA-approved aviation security training centre",
        "مركز تدريب أمن طيران معتمد من الهيئة العامة للطيران المدني",
    ),
    ACB.airport_operator: ("Approved by the airport operator", "معتمد من مشغل المطار"),
    ACB.nebosh: ("NEBOSH accredited learning partner", "شريك تعليمي معتمد من NEBOSH"),
    ACB.iosh: ("IOSH approved training provider", "مقدم تدريب معتمد من IOSH"),
    ACB.osha_otc: ("OSHA Training Institute Education Center", "مركز تعليم معهد تدريب OSHA"),
    ACB.tvtc: ("Licensed by TVTC", "مرخص من المؤسسة العامة للتدريب التقني والمهني"),
    ACB.client_approved: ("Client approved", "معتمد من العميل"),
    ACB.other: ("Other", "أخرى"),
}
# VR-3: awarding-body channels (registered domains on list ACB; fictional for the seed)
BODY_DOMAINS: dict[AccreditationBodyCode, tuple[str, ...]] = {
    ACB.srca: ("srca.org.sa",),
    ACB.aha: ("heart.org",),
    ACB.erc: ("erc.edu",),
    ACB.nebosh: ("nebosh.org.uk",),
    ACB.iosh: ("iosh.com",),
    ACB.osha_otc: ("osha.gov",),
}
MATRIX_ROLE_LABELS: dict[MatrixRole, tuple[str, str]] = {
    MatrixRole.fire_warden: ("Fire warden", "مسؤول إخلاء/حريق"),
    MatrixRole.first_aider: ("First aider", "مسعف أولي"),
    MatrixRole.fire_watch: ("Designated fire watch", "مراقب حريق معيّن"),
}
VOID_REASON_LABELS: dict[SessionVoidReason, tuple[str, str]] = {
    SessionVoidReason.trainer_not_competent: ("Trainer not competent", "المدرب غير مؤهل"),
    SessionVoidReason.attendance_falsified: ("Attendance falsified", "تزوير الحضور"),
    SessionVoidReason.assessment_compromised: ("Assessment compromised", "الإخلال بالتقييم"),
    SessionVoidReason.provider_misconduct: ("Provider misconduct", "مخالفة من الجهة"),
    SessionVoidReason.other: ("Other", "أخرى"),
}
R = HookReasonCode
REASON_TEXT: dict[HookReasonCode, tuple[str, str]] = {
    R.TRAINING_MISSING: ("No training record", "لا يوجد سجل تدريب"),
    R.TRAINING_EXPIRED: ("Training expired", "انتهت صلاحية التدريب"),
    R.TRAINING_PENDING_REVIEW: ("Training record awaiting review", "السجل التدريبي قيد المراجعة"),
    R.TRAINING_UNVERIFIED: ("Training not verified with the issuer", "لم يتم التحقق من التدريب"),
    R.TRAINING_SUSPENDED: ("Training record not accepted", "السجل التدريبي غير مقبول"),
    R.TRAINING_REVOKED: ("Training record not accepted", "السجل التدريبي غير مقبول"),
    R.TRAINING_VERIFICATION_FAILED: (
        "Training record not accepted",
        "السجل التدريبي غير مقبول",
    ),
    R.INDUCTION_NOT_VALID: ("Induction not valid", "التعريف غير ساري"),
    R.HOLDER_NOT_LINKED: (
        "Appointment holder has no linked worker record",
        "صاحب التعيين غير مرتبط بسجل عامل",
    ),
}
