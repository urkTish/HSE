"""Demo seed of package Q2 materials, testing and lab, welding, calibration, competence (spec
8-quality Part C, Appendix A; `seed_fake = true`).

* `seed_libraries` — org-wide data: the 22 test types of §C.2.1 (Published v1), two extra criteria
  the test types use, the competence requirements of A.2, the cert types `ndt_rt` … `cwi` and the
  training courses `CONC-FIELD-TECH`, `MAPPING-LEAD`, `ISO9001-IA`, `GDP-BASIC` when absent (§5).
  The Q2 test fixture loads it on top of the Q0 set-up.
* `seed_people` — Phase 2 worker records for the quality users (competence reads them), with
  training records and personnel certificates for the competence matrix.
* `seed` — the ANIA-EXP (construction) and RUH-CCH (logistics) records of A.3–A.6: MAR-0021 /
  0022 / 0027, MIR-0112 → QTN-0009 → NCR-0041, POUR-0077 with TST-00385 … 00388 (00388 fails (b)
  → NCR-0044) and the cores TST-00431, the September generator volumes (38 MIRs, 212 test
  requests, 120 first NDT examinations), WPS / PQR / welders W-017 and W-021 with the QX8 lot and
  QX9 continuity, calibrations of MTE-0012, MTE-0015 and the RUH-CCH loggers MTE-0101 … 0122
  (CAL-NMS, March 2026, points −25 / 0 / +5 / +25 °C) and an ATP swab test.
* `seed_after_parts` (registry `SEEDS`, after every part) — the QX11 calibration of probe MTE-0042
  and its out-of-tolerance review OOT-RUH-CCH-2026-0003 over the receiving usages of the probe."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.quality.common import (
    QCalStatus,
    QCriterionKind,
    QCriterionStatus,
    QNcrSourceType,
    QProfileScope,
    QRecordType,
)
from app.core.quality.q2 import (
    QAcceptReject,
    QCalKind,
    QCalRecordStatus,
    QCompetencePolicy,
    QEvaluationMode,
    QJointType,
    QMarStatus,
    QMaterialCategory,
    QMirResult,
    QMirStatus,
    QNdtMethod,
    QNdtSelection,
    QOotDecision,
    QOotStatus,
    QPourStatus,
    QPqrStatus,
    QQuarantineStatus,
    QTestStatus,
    QTestTypeStatus,
    QTestVerdict,
    QWeldProcess,
    QWelderStatus,
    QWeldStandard,
    QWeldStatus,
    QWpqMethod,
    QWpqStatus,
    QWpsStatus,
)
from app.models import Project, ProjectEngagement, User, Worker
from app.models.quality import QCriterion, QLink, QMteItem, QMteUsage, QNcr, QSupplier
from app.models.quality.q2 import (
    QCalibration,
    QCompetenceReq,
    QMar,
    QMir,
    QOotItem,
    QOotReview,
    QPour,
    QPqr,
    QQuarantineItem,
    QTestRequest,
    QTestSpecimen,
    QTestType,
    QWeld,
    QWelder,
    QWpq,
    QWps,
)

TZ = ZoneInfo("Asia/Riyadh")
D = Decimal
RT = QRecordType


def at(d: date, hh: int = 9, mm: int = 0) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=TZ).astimezone(UTC)


# ==== libraries ===================================================================================

STRENGTH = [
    {
        "key": "strength",
        "label_en": "Strength",
        "label_ar": "المقاومة",
        "unit": "MPa",
        "kind": "numeric",
    }
]


def _f(
    key: str, en: str, ar: str, unit: str | None = None, kind: str = "numeric"
) -> dict[str, Any]:
    return {"key": key, "label_en": en, "label_ar": ar, "unit": unit, "kind": kind}


# code, EN, AR, discipline, profile, standard, plan, fields, evaluation, criterion, field criteria,
# acceptance age, NCR class on fail, competence
TEST_TYPES: list[tuple[Any, ...]] = [
    ("CONC-CYL", "Concrete cylinders", "أسطوانات خرسانية", "STC", "construction", "ASTM C31 / C39; SBC 304 [VERIFY]",
     [{"age_days": 7, "count": 2}, {"age_days": 28, "count": 2}, {"age_days": None, "count": 1, "spare": True}],
     STRENGTH, "rule", "CONC-ACI-40", {}, 28, {"default": "major", "a": "major", "b": "critical"}, "CONC-FIELD-TECH"),
    ("CONC-CUBE", "Concrete cubes", "مكعبات خرسانية", "STC", "construction", "BS EN 12390-3",
     [{"age_days": 7, "count": 3}, {"age_days": 28, "count": 3}],
     STRENGTH, "rule", "CONC-EN206-50", {}, 28, {"default": "major", "each": "critical", "mean": "major"}, "CONC-FIELD-TECH"),
    ("CONC-CORE", "Concrete cores", "قلوب خرسانية", "STC", "construction", "ASTM C42", [{"age_days": None, "count": 3}],
     STRENGTH, "rule", "CORE-ACI-40", {}, None, {"default": "critical"}, None),
    ("SLUMP", "Slump", "الهبوط", "STC", "construction", "ASTM C143", [],
     [_f("slump", "Slump", "الهبوط", "mm")], "rule", "SLUMP-100", {}, None, {"default": "minor"}, "CONC-FIELD-TECH"),
    ("CONC-TEMP", "Fresh concrete temperature", "حرارة الخرسانة الطازجة", "STC", "construction", "ASTM C1064", [],
     [_f("temperature", "Temperature", "الحرارة", "°C")], "fields", None, {"temperature": "CONC-TEMP-32"}, None, {"default": "minor"}, None),
    ("PROCTOR", "Modified Proctor", "اختبار بروكتور المعدل", "GEO", "construction", "ASTM D1557", [],
     [_f("mdd", "Maximum dry density", "الكثافة الجافة القصوى", "g/cm³"), _f("omc", "Optimum moisture", "المحتوى الرطوبي الأمثل", "%")],
     "fields", None, {}, None, {"default": "minor"}, None),
    ("FDT-SC", "Field density, sand cone", "الكثافة الحقلية بالمخروط الرملي", "GEO", "construction", "ASTM D1556", [],
     [_f("dry_density", "Field dry density", "الكثافة الجافة الحقلية", "g/cm³"), _f("mdd", "Maximum dry density", "الكثافة الجافة القصوى", "g/cm³")],
     "rule", "COMP-RATIO-95", {}, None, {"default": "major"}, None),
    ("FDT-NDG", "Field density, nuclear gauge", "الكثافة الحقلية بالجهاز النووي", "GEO", "construction", "ASTM D6938", [],
     [_f("dry_density", "Field dry density", "الكثافة الجافة الحقلية", "g/cm³"), _f("mdd", "Maximum dry density", "الكثافة الجافة القصوى", "g/cm³")],
     "rule", "COMP-RATIO-95", {}, None, {"default": "major"}, None),
    ("CBR", "California bearing ratio", "نسبة تحمل كاليفورنيا", "GEO", "construction", "ASTM D1883", [],
     [_f("cbr", "CBR", "نسبة التحمل", "%")], "fields", None, {}, None, {"default": "minor"}, None),
    ("PSD", "Particle size distribution", "التدرج الحبيبي", "GEO", "construction", "ASTM D6913", [],
     [_f("grading", "Grading within envelope", "التدرج ضمن الحدود", None, "pass_fail")], "fields", None, {}, None, {"default": "minor"}, None),
    ("ASPH-CORE", "Asphalt core density and thickness", "كثافة وسماكة قلب الأسفلت", "AFP", "construction", "ASTM D2726", [],
     [_f("density_pct", "Density", "الكثافة", "%"), _f("thickness", "Thickness", "السماكة", "mm")], "fields", None, {}, None, {"default": "major"}, None),
    ("ASPH-MARSHALL", "Marshall stability and flow", "ثبات وانسياب مارشال", "AFP", "construction", "ASTM D6927", [],
     [_f("stability", "Stability", "الثبات", "kN"), _f("flow", "Flow", "الانسياب", "mm")], "fields", None, {}, None, {"default": "major"}, None),
    ("REBAR-TENSILE", "Rebar tensile test", "اختبار شد حديد التسليح", "STC", "construction", "ASTM A615 / A370 [VERIFY] SASO", [],
     [_f("yield_strength", "Yield strength", "مقاومة الخضوع", "MPa"), _f("tensile_strength", "Tensile strength", "مقاومة الشد", "MPa"), _f("elongation", "Elongation", "الاستطالة", "%")],
     "fields", None, {}, None, {"default": "major"}, None),
    ("HYDRO", "Hydrostatic pressure test", "اختبار الضغط الهيدروستاتيكي", "PLB", "construction", "ASME B31.3 §345.4 [VERIFY]", [],
     [_f("test_pressure", "Test pressure", "ضغط الاختبار", "bar"), _f("design_pressure", "Design pressure", "ضغط التصميم", "bar"),
      _f("hold_minutes", "Hold time", "زمن الثبات", "min"), _f("pressure_drop", "Pressure drop", "انخفاض الضغط", "bar"),
      _f("leak", "Visible leak", "تسرب مرئي", None, "text")],
     "rule", "HYDRO-1.5", {}, None, {"default": "major"}, None),
    ("PNEU", "Pneumatic test", "اختبار الضغط بالهواء", "PLB", "construction", "ASME B31.3 §345.5 [VERIFY]", [],
     [_f("test_pressure", "Test pressure", "ضغط الاختبار", "bar"), _f("hold_minutes", "Hold time", "زمن الثبات", "min")], "fields", None, {}, None, {"default": "major"}, None),
    ("DUCT-LEAK", "Duct leakage test", "اختبار تسرب مجاري الهواء", "HVC", "construction", "SMACNA [VERIFY]", [],
     [_f("leakage", "Leakage", "التسرب", "l/s per m²")], "fields", None, {}, None, {"default": "minor"}, None),
    ("TORQUE", "Bolt torque", "عزم ربط البراغي", "STL", "construction", "Project spec", [],
     [_f("torque", "Torque", "العزم", "N·m")], "fields", None, {"torque": "TORQUE-M20"}, None, {"default": "minor"}, None),
    ("DFT", "Coating dry-film thickness", "سماكة الطلاء الجاف", "STL", "construction", "SSPC-PA 2", [{"age_days": None, "count": 5}],
     [_f("dft", "Spot mean", "متوسط النقطة", "µm")], "rule", "DFT-125-200", {}, None, {"default": "minor"}, None),
    ("PULL-OFF", "Coating pull-off adhesion", "التصاق الطلاء", "STL", "construction", "ASTM D4541", [],
     [_f("adhesion", "Adhesion", "الالتصاق", "MPa")], "fields", None, {}, None, {"default": "minor"}, None),
    ("PILE-PIT", "Pile integrity test", "اختبار سلامة الخوازيق", "GEO", "construction", "ASTM D5882", [],
     [_f("result", "Integrity", "السلامة", None, "pass_fail")], "fields", None, {"result": "PASS-FAIL"}, None, {"default": "major"}, None),
    ("ATP-SWAB", "Hygiene swab (ATP)", "مسحة النظافة (ATP)", "logistics", "logistics", "Supplier method; RLU", [],
     [_f("rlu", "Reading", "القراءة", "RLU")], "fields", None, {"rlu": "ATP-RLU-150"}, None, {"default": "minor"}, None),
    ("WATER-MICRO", "Water microbiology", "الفحص الميكروبي للمياه", "logistics", "logistics", "SASO GSO 149 [VERIFY]", [],
     [_f("tvc", "Total viable count", "العدد الكلي", "cfu/ml"), _f("ecoli", "E. coli absent", "خلوها من الإشريكية القولونية", None, "pass_fail")],
     "fields", None, {"ecoli": "PASS-FAIL"}, None, {"default": "major"}, None),
]  # fmt: skip

EXTRA_CRITERIA: list[dict[str, Any]] = [
    {"code": "COMP-RATIO-95", "title_en": "Compaction ≥ 95 % of MDD", "title_ar": "الدمك ≥ 95 % من الكثافة القصوى",
     "profile": QProfileScope.construction, "kind": QCriterionKind.rule, "unit": "%", "rule_code": "ratio_min",
     "params": {"min_pct": 95, "num": "dry_density", "den": "mdd"}, "reference": "ASTM D1557 / project spec"},
    {"code": "ATP-RLU-150", "title_en": "ATP hygiene ≤ 150 RLU", "title_ar": "نظافة ATP ≤ 150",
     "profile": QProfileScope.logistics, "kind": QCriterionKind.max, "unit": "RLU", "max_value": D("150"),
     "reference": "Hygiene SOP [VERIFY]"},
    {"code": "PASS-FAIL", "title_en": "Pass / fail entered", "title_ar": "ناجح / راسب",
     "profile": QProfileScope.both, "kind": QCriterionKind.pass_fail, "reference": "Test method"},
]  # fmt: skip

COMPETENCE: list[dict[str, Any]] = [
    {"code": "CONC-FIELD-TECH", "title_en": "Concrete field testing technician", "title_ar": "فني اختبارات الخرسانة الحقلية",
     "applies_to": ["test_technician", "ir_inspector"], "any_of": [{"kind": "training_course", "code": "CONC-FIELD-TECH"}],
     "profile": "construction"},
    {"code": "NDT-RT-L2", "title_en": "Radiographic testing level 2 (ISO 9712)", "title_ar": "التصوير الإشعاعي المستوى 2",
     "applies_to": ["ndt_technician"], "filters": {"ndt_method": "RT"},
     "any_of": [{"kind": "personnel_certificate", "code": "ndt_rt", "min_level": "2"}], "profile": "construction"},
    {"code": "NDT-UT-L2", "title_en": "Ultrasonic testing level 2 (ISO 9712)", "title_ar": "الفحص بالموجات فوق الصوتية المستوى 2",
     "applies_to": ["ndt_technician"], "filters": {"ndt_method": "UT"},
     "any_of": [{"kind": "personnel_certificate", "code": "ndt_ut", "min_level": "2"}], "profile": "construction"},
    {"code": "CWI", "title_en": "Certified welding inspector", "title_ar": "مفتش لحام معتمد",
     "applies_to": ["welding_inspector"], "any_of": [{"kind": "personnel_certificate", "code": "cwi"}], "profile": "construction"},
    {"code": "MAPPING-LEAD", "title_en": "Temperature mapping lead", "title_ar": "قائد دراسة التوزيع الحراري",
     "applies_to": ["mapping_lead"], "any_of": [{"kind": "training_course", "code": "MAPPING-LEAD"}], "profile": "logistics"},
    {"code": "QMS-AUDITOR", "title_en": "QMS internal auditor (ISO 9001)", "title_ar": "مدقق داخلي لنظام إدارة الجودة",
     "applies_to": ["auditor"], "any_of": [{"kind": "training_course", "code": "ISO9001-IA"}], "profile": "both"},
    {"code": "GDP-BASIC", "title_en": "Good distribution practice (basic)", "title_ar": "ممارسات التوزيع الجيدة (أساسي)",
     "applies_to": ["warehouse_qc", "receiving_inspector"], "any_of": [{"kind": "training_course", "code": "GDP-BASIC"}],
     "profile": "logistics"},
]  # fmt: skip

CERT_TYPES = [
    ("ndt_rt", "NDT radiographic testing (ISO 9712)", "فحص إشعاعي غير إتلافي"),
    ("ndt_ut", "NDT ultrasonic testing (ISO 9712)", "فحص بالموجات فوق الصوتية"),
    ("ndt_mt", "NDT magnetic particle testing (ISO 9712)", "فحص بالجسيمات المغناطيسية"),
    ("ndt_pt", "NDT penetrant testing (ISO 9712)", "فحص بالسائل النافذ"),
    ("cwi", "Certified welding inspector (AWS CWI)", "مفتش لحام معتمد"),
]
COURSES = [
    ("CONC-FIELD-TECH", "Concrete field testing technician", "فني اختبارات الخرسانة الحقلية", 60),
    ("MAPPING-LEAD", "Temperature mapping lead", "قائد دراسة التوزيع الحراري", 36),
    ("ISO9001-IA", "ISO 9001 internal auditor", "مدقق داخلي ISO 9001", 36),
    ("GDP-BASIC", "Good distribution practice (basic)", "ممارسات التوزيع الجيدة", 24),
]


def _faisal(db: Session) -> uuid.UUID | None:
    return db.scalar(select(User.id).where(User.email == "faisal.harbi@example.com"))


def seed_libraries(db: Session) -> None:
    """Org-wide Q2 data (idempotent)."""
    from app.core.train_enums import CourseCategory  # noqa: PLC0415
    from app.models import TrainingCourse  # noqa: PLC0415
    from app.models.cert import CertType  # noqa: PLC0415

    fa = _faisal(db)
    pub = at(date(2026, 4, 1))
    for c in EXTRA_CRITERIA:
        if db.scalar(select(QCriterion.id).where(QCriterion.code == c["code"])) is None:
            db.add(
                QCriterion(
                    version=1,
                    status=QCriterionStatus.published,
                    published_at=pub,
                    published_by_user_id=fa,
                    created_by_user_id=fa,
                    params=c.get("params", {}),
                    project_ids=[],
                    seed_fake=True,
                    **{k: v for k, v in c.items() if k != "params"},
                )
            )
    for code, en, ar, disc, prof, ref, plan, fields, ev, crit, fcrit, age, ncls, cpt in TEST_TYPES:
        if db.scalar(select(QTestType.id).where(QTestType.code == code)) is not None:
            continue
        db.add(
            QTestType(
                code=code, version=1, name_en=en, name_ar=ar, discipline=disc, profile=QProfileScope(prof),
                standard_ref=ref, specimen_plan=plan, result_fields=fields, evaluation=QEvaluationMode(ev),
                criterion_code=crit, field_criteria=fcrit, acceptance_age_days=age, ncr_class_on_fail=ncls,
                competence_code=cpt, project_ids=[], status=QTestTypeStatus.published, published_at=pub,
                created_by_user_id=fa, seed_fake=True,
            )
        )  # fmt: skip
    for r in COMPETENCE:
        if db.scalar(select(QCompetenceReq.id).where(QCompetenceReq.code == r["code"])) is None:
            db.add(
                QCompetenceReq(
                    code=r["code"], title_en=r["title_en"], title_ar=r["title_ar"], applies_to=r["applies_to"],
                    filters=r.get("filters", {}), any_of=r["any_of"], all_of=[], policy=QCompetencePolicy.inherit,
                    profile=QProfileScope(r["profile"]), created_by_user_id=fa, seed_fake=True,
                )
            )  # fmt: skip
    for code, en, ar in CERT_TYPES:
        if db.get(CertType, code) is None:
            db.add(
                CertType(
                    code=code,
                    label_en=en,
                    label_ar=ar,
                    cap_months=60,
                    levels_allowed=["1", "2", "3"],
                    seeded=True,
                )
            )
    for code, en, ar, months in COURSES:
        if db.scalar(select(TrainingCourse.id).where(TrainingCourse.code == code)) is None:
            db.add(
                TrainingCourse(
                    code=code, name_en=en, name_ar=ar, category=CourseCategory.professional_qualification,
                    validity_months=months, delivery_modes=[], prerequisite_codes=[], satisfies=[],
                    accreditation_bodies_required=[], languages_offered=["en", "ar"], active=True, seeded=True,
                )
            )  # fmt: skip
    db.flush()


# ==== people (competence) ======================================================================

Q_PEOPLE = [
    "hatem.shehri", "bilal.qureshi", "joseph.mathew.qc", "rania.zahrani", "mazen.harbi", "arun.pillai",
    "reem.mutairi", "imran.siddiq", "naveen.kumar", "saad.anazi", "lama.qarni", "abdullah.dossary", "sultan.mutlaq",
]  # fmt: skip


def _uid(db: Session, key: str) -> uuid.UUID:
    uid = db.scalar(select(User.id).where(User.email == f"{key}@example.com"))
    assert uid is not None, key  # noqa: S101
    return uid


def ensure_worker(db: Session, user_id: uuid.UUID, person_type: str = "client_pmc_staff") -> Worker:
    from app.core.access_enums import WorkerLanguage, WorkerPersonType, WorkerStatus  # noqa: PLC0415

    w = db.scalar(select(Worker).where(Worker.user_id == user_id))
    if w is not None:
        return w
    u = db.get(User, user_id)
    assert u is not None  # noqa: S101
    seq = int(db.scalar(select(func.max(Worker.seq))) or 0) + 1
    w = Worker(
        id=uuid.uuid4(), seq=seq, worker_no=f"WKR-{seq:06d}", person_type=WorkerPersonType(person_type),
        full_name_en=u.full_name_en, full_name_ar=u.full_name_ar or u.full_name_en, adult_attestation=True,
        primary_language=WorkerLanguage.en, user_id=user_id, status=WorkerStatus.active,
        search_text=f"{u.full_name_en} {seq}".lower(), seed_fake=True,
    )  # fmt: skip
    db.add(w)
    db.flush()
    return w


def _provider(db: Session) -> Any:
    from app.core.train_enums import TrainingProviderKind, TrainingProviderStatus  # noqa: PLC0415
    from app.models import TrainingProvider  # noqa: PLC0415

    pv = db.scalar(select(TrainingProvider).where(TrainingProvider.provider_code == "QTRN"))
    if pv is None:
        pv = TrainingProvider(
            id=uuid.uuid4(), provider_code="QTRN", legal_name_en="Quality Training Academy (fictional)",
            legal_name_ar="أكاديمية تدريب الجودة", name_norm_en="quality training academy fictional",
            name_norm_ar="اكاديمية تدريب الجودة", kind=TrainingProviderKind.external, country="SA",
            status=TrainingProviderStatus.approved, verification_domains=[], suspension_periods=[],
        )  # fmt: skip
        db.add(pv)
        db.flush()
    return pv


def training_record(
    db: Session, w: Worker, code: str, completed: date, valid_until: date | None
) -> Any:
    from app.core.cert_enums import VerificationStatus  # noqa: PLC0415
    from app.core.train_enums import (  # noqa: PLC0415
        TrainingLimitingFactor,
        TrainingRecordSource,
        TrainingRecordStatus,
    )
    from app.models import TrainingRecord  # noqa: PLC0415

    pv = _provider(db)
    seq = int(db.scalar(select(func.max(TrainingRecord.seq))) or 0) + 1
    rev = at(completed, 10)
    r = TrainingRecord(
        id=uuid.uuid4(), seq=seq, record_no=f"TR-{seq:06d}"[:12], worker_id=w.id, course_code=code,
        source=TrainingRecordSource.external_certificate, provider_id=pv.id, certificate_no=f"QTRN-{seq:06d}",
        completed_on=completed, printed_expiry=valid_until, valid_until=valid_until,
        limiting_factor=TrainingLimitingFactor.printed_expiry if valid_until else TrainingLimitingFactor.none,
        name_as_printed=w.full_name_en, status=TrainingRecordStatus.accepted,
        verification_status=VerificationStatus.verified, reviewed_at=rev, verified_at=rev, in_force_from=rev,
        alerts_sent=[], seed_fake=True,
    )  # fmt: skip
    db.add(r)
    db.flush()
    return r


def personnel_cert(
    db: Session,
    w: Worker,
    project_id: uuid.UUID,
    code: str,
    issued: date,
    valid_until: date,
    level: str | None,
) -> Any:
    from app.core.cert_enums import (  # noqa: PLC0415
        CertificateStatus,
        CertLevel,
        CertLimitingFactor,
        IdMatchResult,
        NameMatch,
        TpiKind,
        TpiStatus,
        VerificationStatus,
    )
    from app.models import PersonnelCertificate  # noqa: PLC0415
    from app.models.cert import Tpi  # noqa: PLC0415

    tpi = db.scalar(select(Tpi).where(Tpi.tpi_code == "QNDT"))
    if tpi is None:
        tpi = Tpi(
            id=uuid.uuid4(), tpi_code="QNDT", legal_name_en="Desert NDT Certification (fictional)",
            legal_name_ar="الصحراء لشهادات الفحص غير الإتلافي", name_norm_en="desert ndt certification fictional",
            name_norm_ar="الصحراء لشهادات الفحص غير الاتلافي", kinds=[TpiKind.ndt_body.value, TpiKind.personnel_certification_body.value],
            country="SA", status=TpiStatus.approved, verification_domains=[], affiliated_contractor_ids=[], suspension_periods=[],
        )  # fmt: skip
        db.add(tpi)
        db.flush()
    seq = int(db.scalar(select(func.max(PersonnelCertificate.seq))) or 0) + 1
    ok = at(issued, 12)
    pc = PersonnelCertificate(
        id=uuid.uuid4(), seq=seq, record_no=f"PCR-{seq:06d}", project_id=project_id, worker_id=w.id, cert_type=code,
        tpi_id=tpi.id, cert_no=f"QNDT-{code.upper()}-{seq:05d}", issued_on=issued, printed_expiry=valid_until,
        cap_end=valid_until, valid_until=valid_until, limiting_factor=CertLimitingFactor.printed_expiry,
        scope_categories=[], level=CertLevel(level) if level else None, name_as_printed=w.full_name_en,
        id_match_result=IdMatchResult.matched, name_match=NameMatch.exact, status=CertificateStatus.accepted,
        verification_status=VerificationStatus.verified, verification_due_on=issued + timedelta(days=14),
        submitted_at=ok, reviewed_at=ok, accepted_at=ok, verified_at=ok, in_force_from=ok, seed_fake=True,
    )  # fmt: skip
    db.add(pc)
    db.flush()
    return pc


def seed_people(db: Session) -> None:
    """Worker records for the quality users (D-345) and their competence evidence."""
    for key in Q_PEOPLE:
        uid = db.scalar(select(User.id).where(User.email == f"{key}@example.com"))
        if uid is not None:
            ensure_worker(db, uid)
    if db.scalar(select(func.count()).select_from(QWelder)):
        return
    ania = db.scalar(select(Project).where(Project.code == "ANIA-EXP"))
    if ania is None:
        return
    w = {k: ensure_worker(db, _uid(db, k)) for k in Q_PEOPLE}
    training_record(
        db, w["joseph.mathew.qc"], "CONC-FIELD-TECH", date(2021, 10, 21), date(2026, 10, 20)
    )
    training_record(db, w["mazen.harbi"], "CONC-FIELD-TECH", date(2025, 1, 10), date(2030, 1, 9))
    training_record(db, w["hatem.shehri"], "ISO9001-IA", date(2025, 3, 1), date(2028, 2, 29))
    training_record(db, w["rania.zahrani"], "ISO9001-IA", date(2025, 6, 1), date(2028, 5, 31))
    training_record(db, w["reem.mutairi"], "ISO9001-IA", date(2024, 11, 1), date(2027, 10, 31))
    training_record(db, w["reem.mutairi"], "MAPPING-LEAD", date(2025, 2, 1), date(2028, 1, 31))
    training_record(db, w["imran.siddiq"], "GDP-BASIC", date(2025, 4, 1), date(2027, 3, 31))
    training_record(db, w["naveen.kumar"], "GDP-BASIC", date(2025, 5, 1), date(2027, 4, 30))
    personnel_cert(db, w["arun.pillai"], ania.id, "cwi", date(2024, 1, 15), date(2027, 1, 14), None)
    # an NDT technician whose RT level 2 certificate ended 2026-09-30 (AC-Q2-25)
    personnel_cert(
        db, w["mazen.harbi"], ania.id, "ndt_rt", date(2021, 10, 1), date(2026, 9, 30), "2"
    )
    db.flush()


# ==== ANIA-EXP records ===========================================================================


class _Ctx:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.p = {
            p.code: p
            for p in db.scalars(select(Project).where(Project.code.in_(["ANIA-EXP", "RUH-CCH"])))
        }
        self.sup = {s.supplier_code: s for s in db.scalars(select(QSupplier))}

    def u(self, key: str) -> uuid.UUID:
        return _uid(self.db, key)

    def eng(self, project: Project, short: str) -> uuid.UUID:
        from app.models import Contractor  # noqa: PLC0415

        eid = self.db.scalar(
            select(ProjectEngagement.id)
            .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
            .where(ProjectEngagement.project_id == project.id, Contractor.short_code == short)
        )
        assert eid is not None, short  # noqa: S101
        return eid

    def site(self, project: Project, code: str) -> uuid.UUID:
        from app.models import Site  # noqa: PLC0415

        sid = self.db.scalar(
            select(Site.id).where(Site.project_id == project.id, Site.code == code)
        )
        assert sid is not None, code  # noqa: S101
        return sid

    def zone(self, project: Project, code: str) -> uuid.UUID | None:
        from app.models import Zone  # noqa: PLC0415

        return self.db.scalar(
            select(Zone.id).where(Zone.project_id == project.id, Zone.code == code)
        )

    def mte(self, project: Project, no: int) -> QMteItem | None:
        return self.db.scalar(
            select(QMteItem).where(
                QMteItem.project_id == project.id, QMteItem.mte_no == f"MTE-{no:04d}"
            )
        )

    def crit(self, code: str) -> uuid.UUID | None:
        return self.db.scalar(
            select(QCriterion.id).where(
                QCriterion.code == code, QCriterion.status == QCriterionStatus.published
            )
        )

    def tt(self, code: str) -> QTestType:
        t = self.db.scalar(
            select(QTestType).where(
                QTestType.code == code, QTestType.status == QTestTypeStatus.published
            )
        )
        assert t is not None, code  # noqa: S101
        return t

    def ncr(self, project: Project, no: str) -> QNcr | None:
        return self.db.scalar(select(QNcr).where(QNcr.project_id == project.id, QNcr.ncr_no == no))


def _link(
    db: Session,
    project: Project,
    ft: RT,
    fid: uuid.UUID,
    tt: RT,
    tid: uuid.UUID,
    kind: str,
    on: datetime,
) -> None:
    from app.core.quality.common import QLinkKind  # noqa: PLC0415

    db.add(
        QLink(
            project_id=project.id,
            from_type=ft.value,
            from_id=fid,
            to_type=tt.value,
            to_id=tid,
            kind=QLinkKind(kind),
            created_at=on,
            seed_fake=True,
        )
    )


def _bump(db: Session, project: Project, rt: RT, seq: int, year: int = 2026) -> None:
    from app.services.quality import numbering  # noqa: PLC0415

    numbering.bump_to(db, project, rt, year, seq)


def _mars(c: _Ctx, p: Project) -> dict[int, QMar]:
    db = c.db
    bilal, abdullah = c.u("bilal.qureshi"), c.u("abdullah.dossary")
    out = {}
    rows = [
        (21, "Ready-mix concrete C40/50 (mix C40-B12)", "خرسانة جاهزة C40", QMaterialCategory.concrete_mix, "RMX", "A", QMarStatus.approved, "RAWABI"),
        (22, "Reinforcing steel B500B", "حديد تسليح B500B", QMaterialCategory.rebar, "ARS", "B", QMarStatus.approved_as_noted, "RAWABI"),
        (27, "Waterproofing membrane, podium", "غشاء عزل مائي", QMaterialCategory.waterproofing, "SAHEL", "C", QMarStatus.revise_resubmit, "RAWABI"),
        (30, "HDPE pressure pipes PE100 SDR11", "أنابيب HDPE", QMaterialCategory.pipes_fittings, "GULFPIPE", "A", QMarStatus.approved, "RAWABI"),
    ]  # fmt: skip
    for no, en, ar, cat, sup, code, st, eng in rows:
        sub = at(date(2026, 3, 1) + timedelta(days=no))
        m = QMar(
            id=uuid.uuid4(), project_id=p.id, mar_no=f"MAR-ANIA-EXP-2026-{no:04d}", revision=0, engagement_id=c.eng(p, eng),
            title_en=en, title_ar=ar, category=cat, spec_section="03 30 00" if cat == QMaterialCategory.concrete_mix else None,
            manufacturer=c.sup[sup].legal_name_en, supplier_id=c.sup[sup].id, country_of_origin="SA",
            compliance=[{"requirement": "Grade / class per specification", "offered": en, "result": "complies", "note": ""},
                        {"requirement": "Test certificates", "offered": "Mill / plant certificates", "result": "complies", "note": ""}],
            approval_code=code, decision_comment=None if code == "A" else "Submit the missing durability data and resubmit the "
            "sample board." if code == "C" else "Approved; follow the noted lap-length table.",
            submitted_at=sub, submitted_by_user_id=bilal, decided_at=sub + timedelta(days=6), decided_by_user_id=abdullah,
            status=st, alerts_sent=[], created_by_user_id=bilal, seed_fake=True,
        )  # fmt: skip
        db.add(m)
        out[no] = m
    db.flush()
    _bump(db, p, RT.mar, 30)
    return out


def _mir_named(c: _Ctx, p: Project, mars: dict[int, QMar]) -> None:
    """MIR-0112 HDPE (GULFPIPE, 240 m, 180 accepted, 60 rejected) → QTN-0009 → NCR-0041."""
    db = c.db
    joseph, abdullah = c.u("joseph.mathew.qc"), c.u("abdullah.dossary")
    when = at(date(2026, 9, 20), 10)
    x = QMir(
        id=uuid.uuid4(), project_id=p.id, mir_no="MIR-ANIA-EXP-2026-0112", mar_id=mars[30].id, mar_revision=0,
        engagement_id=mars[30].engagement_id, category=QMaterialCategory.pipes_fittings,
        material_description="HDPE pipes PE100 DN200 SDR11", site_id=c.site(p, "S-LAND"), delivery_note_no="GP-DN-55120",
        po_no="PO-RAW-8841", supplier_id=c.sup["GULFPIPE"].id, delivered_at=when, quantity=D("240"), unit="m",
        lot_numbers=["GP-2609-L4"], cert_heat_numbers=["GP-2609-L4"], heat_mismatch=[], accepted_qty=D("180"),
        rejected_qty=D("60"), result=QMirResult.accepted_with_comments,
        decision_comment="60 m rejected for ovality beyond tolerance and damaged ends; 180 m accepted.",
        submitted_at=when, submitted_by_user_id=joseph, decided_at=when + timedelta(hours=5), decided_by_user_id=abdullah,
        status=QMirStatus.decided, created_by_user_id=joseph, seed_fake=True,
    )  # fmt: skip
    db.add(x)
    db.flush()
    n41 = c.ncr(p, "NCR-ANIA-EXP-2026-0041")
    q = QQuarantineItem(
        id=uuid.uuid4(), project_id=p.id, tag_no="QTN-ANIA-EXP-2026-0009", material_description=x.material_description,
        mir_id=x.id, engagement_id=x.engagement_id, quantity=D("60"), unit="m", site_id=x.site_id,
        location_ref="Laydown yard L2, red-tag bay", ncr_id=n41.id if n41 else None, quarantined_on=date(2026, 9, 20),
        status=QQuarantineStatus.quarantined, created_by_user_id=abdullah, seed_fake=True,
    )  # fmt: skip
    db.add(q)
    db.flush()
    _link(db, p, RT.quarantine, q.id, RT.mir, x.id, "raised_from", when)
    _link(db, p, RT.mir, x.id, RT.mar, mars[30].id, "requires", when)
    if n41 is not None:
        n41.source_id = x.id
        _link(db, p, RT.ncr, n41.id, RT.mir, x.id, "raised_from", when)
        _link(db, p, RT.quarantine, q.id, RT.ncr, n41.id, "relates", when)
    _bump(db, p, RT.quarantine, 9)


def _mir_volume(c: _Ctx, p: Project, mars: dict[int, QMar]) -> None:
    """38 MIRs decided in September 2026, 2 with rejections (MIR-0112 and one rebar MIR)."""
    db = c.db
    joseph, abdullah = c.u("joseph.mathew.qc"), c.u("abdullah.dossary")
    site = c.site(p, "S-LAND")
    n = 0
    for i in range(37):
        no = 75 + i if 75 + i < 112 else 75 + i + 1
        day = date(2026, 9, 1) + timedelta(days=i % 29)
        mar = mars[21] if i % 3 == 0 else mars[22]
        rej = i == 10
        qty = D("40") if mar is mars[22] else D("60")
        db.add(
            QMir(
                id=uuid.uuid4(), project_id=p.id, mir_no=f"MIR-ANIA-EXP-2026-{no:04d}", mar_id=mar.id, mar_revision=0,
                engagement_id=mar.engagement_id, category=mar.category, material_description=mar.title_en, site_id=site,
                delivery_note_no=f"DN-{no:05d}", supplier_id=mar.supplier_id, delivered_at=at(day, 8), quantity=qty,
                unit="t" if mar is mars[22] else "m3", lot_numbers=[f"H7{no:04d}"] if mar is mars[22] else [],
                cert_heat_numbers=[f"H7{no:04d}"] if mar is mars[22] else [], heat_mismatch=[],
                accepted_qty=qty - (D("8") if rej else D(0)), rejected_qty=D("8") if rej else D(0),
                result=QMirResult.accepted_with_comments if rej else QMirResult.accepted,
                decision_comment="8 t rejected: bars bent beyond repair during unloading." if rej else None,
                submitted_at=at(day, 8), submitted_by_user_id=joseph, decided_at=at(day, 11), decided_by_user_id=abdullah,
                status=QMirStatus.decided, created_by_user_id=joseph, seed_fake=True,
            )
        )  # fmt: skip
        n += 1
    db.flush()
    _bump(db, p, RT.mir, 112)
    _ = n


def _spec_rows(
    t: QTestRequest, tt: QTestType, cast: date, values: list[str | None]
) -> list[QTestSpecimen]:
    out = []
    plan: list[tuple[int | None, bool]] = []
    for row in tt.specimen_plan or []:
        plan += [(row.get("age_days"), bool(row.get("spare")))] * int(row["count"])
    vals = iter(values)
    for i, (age, spare) in enumerate(plan):
        v = None if spare else next(vals, None)
        out.append(
            QTestSpecimen(
                test_request_id=t.id, specimen_ref=f"{t.sample_ref}-{i + 1}", age_days=age,
                due_on=cast + timedelta(days=age) if age is not None else None,
                tested_on=(cast + timedelta(days=age or 0)) if v is not None else None,
                values={"strength": v} if v is not None and tt.result_fields[0]["key"] == "strength" else ({tt.result_fields[0]["key"]: v} if v is not None else {}),
                spare=spare, position=i, seed_fake=True,
            )
        )  # fmt: skip
    return out


def _test(
    c: _Ctx, p: Project, no: int, tt: QTestType, crit_code: str | None, cast: date, *, site: str, loc: str,
    eng: uuid.UUID | None, values: list[str | None] | None = None, results: dict[str, Any] | None = None,
    verdict: QTestVerdict = QTestVerdict.pass_, detail: dict[str, Any] | None = None, pour: QPour | None = None,
    status: QTestStatus = QTestStatus.verified, retest_of: QTestRequest | None = None, lab: str = "LAB-RGM",
    mix_key: str = "", year: int = 2026,
) -> QTestRequest:  # fmt: skip
    db = c.db
    joseph, rania = c.u("joseph.mathew.qc"), c.u("rania.zahrani")
    done = cast + timedelta(
        days=max([int(r.get("age_days") or 0) for r in tt.specimen_plan or []] or [0]) + 1
    )
    t = QTestRequest(
        id=uuid.uuid4(), project_id=p.id, test_no=f"TST-{p.code}-{year}-{no:05d}", test_type_id=tt.id, test_type_code=tt.code,
        criterion_id=c.crit(crit_code) if crit_code else None, field_criterion_ids={k: str(c.crit(v)) for k, v in (tt.field_criteria or {}).items() if c.crit(v)},
        site_id=c.site(p, site), location_ref=loc, engagement_id=eng, lab_supplier_id=c.sup[lab].id,
        pour_id=pour.id if pour else None, retest_of_id=retest_of.id if retest_of else None,
        mix_key=mix_key or (pour.mix_key if pour else ""), requested_by_user_id=joseph, sampled_at=at(cast, 10, 40),
        cast_date=cast, sampled_by_user_id=joseph, sample_ref=f"S-{no:05d}", mte_ids=[], delivered_to_lab_on=cast + timedelta(days=1),
        results=results or {}, report_no=f"RGM-26-{11000 + no}", tested_by_name="Lab technician (fictional)",
        verdict=verdict, verdict_detail=detail or {"reason_en": "Within the criterion.", "reason_ar": "مطابق."},
        result_version=1, history=[], results_entered_at=at(done, 14), results_entered_by_user_id=joseph,
        verified_at=at(done + timedelta(days=1), 9) if status == QTestStatus.verified else None,
        verified_by_user_id=rania if status == QTestStatus.verified else None, ncr_decision={}, status=status,
        alerts_sent=[], created_by_user_id=joseph, seed_fake=True,
    )  # fmt: skip
    db.add(t)
    db.flush()
    for s in _spec_rows(t, tt, cast, values or []):
        db.add(s)
    return t


def _pour_and_tests(c: _Ctx, p: Project, mars: dict[int, QMar]) -> None:
    """POUR-0077 (186 m³, C40, 4 sets TST-00385 … 00388; set 3 fails (b) → NCR-0044) and the cores
    TST-00431 (QX6, acceptable)."""
    from app.services.quality.q2.pours import mix_key  # noqa: PLC0415

    db = c.db
    rawabi = c.eng(p, "RAWABI")
    bilal = c.u("bilal.qureshi")
    pour = QPour(
        id=uuid.uuid4(), project_id=p.id, pour_no="POUR-ANIA-EXP-2026-0077", engagement_id=rawabi,
        element="Pier B level 3 slab", site_id=c.site(p, "S-LAND"), zone_id=c.zone(p, "Z-PIERB"),
        location_ref="Level 3 slab, grid C14–C20", mar_id=mars[21].id, grade="C40", fc_mpa=D("40"), volume_m3=D("186"),
        supplier_id=c.sup["RMX"].id, planned_on=date(2026, 9, 1), started_at=at(date(2026, 9, 1), 6),
        finished_at=at(date(2026, 9, 1), 17), ambient_temp_c=D("38.5"), quality_engineer_id=bilal,
        mix_key=mix_key(mars[21].id, "C40"), sets_required=4, warnings=[], status=QPourStatus.closed,
        created_by_user_id=bilal, seed_fake=True,
    )  # fmt: skip
    db.add(pour)
    db.flush()
    _link(db, p, RT.pour, pour.id, RT.mar, mars[21].id, "relates", at(date(2026, 9, 1)))
    cyl = c.tt("CONC-CYL")
    sets = [("41.5", "42.3"), ("40.8", "41.6"), ("33.0", "33.4"), ("42.0", "43.1")]
    tests: list[QTestRequest] = []
    for i, (a, b) in enumerate(sets):
        m = (D(a) + D(b)) / 2
        hist = [((D(x) + D(y)) / 2) for x, y in sets[: i + 1]]
        mean3 = sum(hist[-3:], D(0)) / len(hist[-3:]) if len(hist) >= 3 else None
        fail = m < D("36.0")
        det = {
            "test": str(m), "fc": "40", "limit_b": "36.00", "b": "fail" if fail else "pass",
            "a": "pending" if mean3 is None else ("pass" if mean3 >= 40 else "fail"),
            "mean3": f"{mean3:.2f}" if mean3 is not None else None, "clause": "b" if fail else None,
            "criterion": "CONC-ACI-40 v1",
            "reason_en": f"Test {m:.2f} MPa < 36.00 MPa (ACI 318 (b))." if fail else f"Test {m:.2f} MPa meets ACI 318.",
            "reason_ar": "النتيجة أقل من الحد (البند ب)." if fail else "النتيجة مطابقة.",
        }  # fmt: skip
        t = _test(
            c, p, 385 + i, cyl, "CONC-ACI-40", date(2026, 9, 1), site="S-LAND", loc="Level 3 slab, grid C14–C20",
            eng=rawabi, values=["27.1", "28.0", a, b], verdict=QTestVerdict.fail if fail else QTestVerdict.pass_,
            detail=det, pour=pour,
        )  # fmt: skip
        tests.append(t)
        _link(db, p, RT.test_request, t.id, RT.pour, pour.id, "relates", at(date(2026, 9, 1)))
    t388 = tests[2]
    n44 = c.ncr(p, "NCR-ANIA-EXP-2026-0044")
    if n44 is not None:
        n44.source_id = t388.id
        t388.ncr_decision = {"mode": "raised", "ncr_id": str(n44.id), "ncr_no": n44.ncr_no}
        _link(
            db,
            p,
            RT.ncr,
            n44.id,
            RT.test_request,
            t388.id,
            "raised_from",
            at(date(2026, 9, 29), 11, 20),
        )
    cores = _test(
        c, p, 431, c.tt("CONC-CORE"), "CORE-ACI-40", date(2026, 10, 2), site="S-LAND", loc="Level 3 slab, grid C16",
        eng=rawabi, values=["36.1", "34.9", "33.6"], retest_of=t388, mix_key=pour.mix_key,
        detail={"mean": "34.87", "min": "33.6", "limit_mean": "34.00", "limit_each": "30.00", "reason_en": "Cores acceptable: mean 34.87 ≥ 34.00 and min 33.60 ≥ 30.00 MPa.", "reason_ar": "القلوب مقبولة."},
    )  # fmt: skip
    _link(
        db, p, RT.test_request, cores.id, RT.test_request, t388.id, "relates", at(date(2026, 10, 2))
    )


def _test_volume(c: _Ctx, p: Project) -> None:
    """September 2026 test requests with a verdict: 212 in total, 6 failed (incl. TST-00388)."""
    db = c.db
    rawabi, gulfpave = c.eng(p, "RAWABI"), c.eng(p, "GULFPAVE")
    kinds = [
        ("SLUMP", "SLUMP-100", {"slump": "95"}, {"slump": "135"}),
        ("CONC-TEMP", None, {"temperature": "29.5"}, {"temperature": "33.6"}),
        (
            "FDT-SC",
            "COMP-RATIO-95",
            {"dry_density": "2.068", "mdd": "2.150"},
            {"dry_density": "2.030", "mdd": "2.150"},
        ),
        ("TORQUE", None, {"torque": "405"}, {"torque": "372"}),
    ]
    made, failed = 5, 1  # the four pour sets and the cores; set 3 failed
    no = 100
    while made < 212:
        no += 1
        if 385 <= no <= 388:
            continue
        code, crit, ok, bad = kinds[no % len(kinds)]
        fail = failed < 6 and no % 37 == 0
        day = date(2026, 9, 1) + timedelta(days=no % 29)
        _test(
            c, p, no, c.tt(code), crit, day, site="S-LAND" if no % 2 else "S-AIR", loc=f"Grid {no % 40}",
            eng=gulfpave if code == "FDT-SC" else rawabi, results=bad if fail else ok,
            verdict=QTestVerdict.fail if fail else QTestVerdict.pass_,
            detail={"reason_en": "Outside the criterion." if fail else "Within the criterion.", "reason_ar": "غير مطابق." if fail else "مطابق."},
        )  # fmt: skip
        made += 1
        failed += 1 if fail else 0
    db.flush()
    _bump(db, p, RT.test_request, 431)


def _welding(c: _Ctx, p: Project) -> None:
    """WPS-NAJD-SMAW-01 (5–25 mm), PQR-NAJD-001, welders W-017 / W-021, the QX8 lot "PB-ROOF RT 10 %"
    (40 welds, 4 random + 2 progressive examined, J07 rejected then repaired R1 and accepted),
    QX9 (W-021's last SMAW weld 2026-03-28) and September first NDT examinations 120, rejected 5."""
    db = c.db
    najd = c.eng(p, "NAJD")
    arun, rania = c.u("arun.pillai"), c.u("rania.zahrani")
    pqr = QPqr(
        id=uuid.uuid4(), project_id=p.id, pqr_no="PQR-NAJD-001", standard=QWeldStandard.aws_d1_1, process=QWeldProcess.smaw,
        test_date=date(2025, 12, 10), results=[{"test": "tensile", "value": "512 MPa", "result": "pass"}, {"test": "bend", "value": "4 × side bend", "result": "pass"}],
        lab_supplier_id=c.sup["LAB-RGM"].id, certificate_no="RGM-PQR-2512", approved_at=at(date(2025, 12, 20)),
        status=QPqrStatus.approved, created_by_user_id=arun, seed_fake=True,
    )  # fmt: skip
    wps = QWps(
        id=uuid.uuid4(), project_id=p.id, wps_no="WPS-NAJD-SMAW-01", revision=0, standard=QWeldStandard.aws_d1_1,
        processes=["SMAW"], joint_types=["butt", "fillet"], base_material_group="AWS D1.1 Group II",
        thickness_min_mm=D("5"), thickness_max_mm=D("25"), positions=["1G", "2G", "3G", "4G", "1F", "2F", "3F", "4F"],
        filler_class="E7018", f_no="4", a_no="1", preheat_min_c=D("10"), interpass_max_c=D("250"), pwht="None",
        prequalified=False, pqr_ids=[pqr.id], approved_at=at(date(2026, 1, 5)), status=QWpsStatus.approved,
        created_by_user_id=arun, submitted_by_user_id=arun, seed_fake=True,
    )  # fmt: skip
    db.add_all([pqr, wps])
    db.flush()
    welders = {}
    for stamp, name in (
        ("W-017", "Ramesh Nair"),
        ("W-021", "Sajid Khan"),
        ("W-030", "Mohan Das"),
        ("W-031", "Ali Raza"),
    ):
        from app.core.access_enums import WorkerLanguage, WorkerPersonType, WorkerStatus  # noqa: PLC0415

        seq = int(db.scalar(select(func.max(Worker.seq))) or 0) + 1
        wk = Worker(
            id=uuid.uuid4(), seq=seq, worker_no=f"WKR-{seq:06d}", person_type=WorkerPersonType.contractor_worker,
            full_name_en=f"{name} (welder, fictional)", full_name_ar=name, adult_attestation=True,
            primary_language=WorkerLanguage.en, status=WorkerStatus.active, search_text=name.lower(), seed_fake=True,
        )  # fmt: skip
        db.add(wk)
        db.flush()
        w = QWelder(
            id=uuid.uuid4(),
            project_id=p.id,
            worker_id=wk.id,
            stamp=stamp,
            engagement_id=najd,
            status=QWelderStatus.active,
            created_by_user_id=arun,
            seed_fake=True,
        )
        db.add(w)
        welders[stamp] = w
    db.flush()
    wpq_no = 0
    wpqs = {}
    for stamp, w in welders.items():
        wpq_no += 1
        wpqs[stamp] = QWpq(
            id=uuid.uuid4(), project_id=p.id, wpq_no=f"WPQ-ANIA-EXP-2026-{wpq_no:04d}", welder_id=w.id,
            standard=QWeldStandard.aws_d1_1, process=QWeldProcess.smaw, test_wps_id=wps.id, test_date=date(2026, 1, 20),
            coupon_thickness_mm=D("25"), coupon_position="3G", positions=["1G", "2G", "3G", "1F", "2F", "3F"],
            thickness_min_mm=D("3"), thickness_max_mm=D("50"), f_no="4", test_method=QWpqMethod.rt, result=QAcceptReject.accept,
            examiner_supplier_id=c.sup["DNDT"].id, revalidation_due=date(2028, 1, 19), confirmations=[], alerts_sent=[],
            approved_at=at(date(2026, 1, 25)), status=QWpqStatus.active, created_by_user_id=arun, seed_fake=True,
        )  # fmt: skip
        db.add(wpqs[stamp])
    db.flush()

    def weld(joint: str, stamp: str, on: date, lot: str | None, status: QWeldStatus, results: list[dict[str, Any]] | None = None,
             sel: QNdtSelection | None = None, repairs: int = 0, parent: QWeld | None = None) -> QWeld:  # fmt: skip
        x = QWeld(
            id=uuid.uuid4(), project_id=p.id, joint_id=joint, engagement_id=najd, drawing_ref="S-PB-ROOF-201",
            site_id=c.site(p, "S-LAND"), zone_id=c.zone(p, "Z-PIERB"), wps_id=wps.id, process=QWeldProcess.smaw,
            position="2G", joint_type=QJointType.butt, thickness_mm=D("16"), length_mm=D("300"),
            welders=[{"welder_id": str(welders[stamp].id), "root": True, "fill": True, "cap": True}],
            welder_ids=[welders[stamp].id], welded_on=on, visual_result=QAcceptReject.accept, lot_code=lot,
            ndt_method=QNdtMethod.rt if lot else None, ndt_required_pct=D("10") if lot else None,
            selected_for_ndt=sel is not None, selection_reason=sel, selected_from_id=parent.id if parent else None,
            ndt_results=results or [], repair_count=repairs, status=status, created_by_user_id=arun, seed_fake=True,
        )  # fmt: skip
        db.add(x)
        return x

    def ndt(res: str, on: date, rnd: int = 0, defect: str | None = None) -> dict[str, Any]:
        return {"method": "RT", "report_no": f"DNDT-RT-{on.isoformat()}", "attachment_id": None, "result": res,
                "defect_type": defect, "defect_length_mm": "12" if defect else None, "examined_length_mm": "300",
                "technician_name": "Desert NDT technician (fictional)", "technician_user_id": None,
                "examined_on": on.isoformat(), "repair_round": rnd, "at": at(on, 12).isoformat()}  # fmt: skip

    lot = "PB-ROOF-RT10"
    d0 = date(2026, 9, 2)
    j07 = None
    for i in range(1, 41):
        jid = f"PB-RT-T12-J{i:02d}"
        on = d0 + timedelta(days=i // 4)
        exam = on + timedelta(days=2)
        if i == 7:
            j07 = weld(
                jid,
                "W-017",
                on,
                lot,
                QWeldStatus.accepted,
                [
                    ndt("reject", exam, 0, "slag inclusion"),
                    ndt("accept", exam + timedelta(days=2), 1),
                ],
                QNdtSelection.random,
                1,
            )
        elif i in (1, 15, 30):
            weld(
                jid,
                "W-017" if i == 15 else "W-030",
                on,
                lot,
                QWeldStatus.accepted,
                [ndt("accept", exam)],
                QNdtSelection.random,
            )
        elif i in (8, 9):
            db.flush()
            weld(
                jid,
                "W-017",
                on,
                lot,
                QWeldStatus.accepted,
                [ndt("accept", exam + timedelta(days=1))],
                QNdtSelection.progressive,
                parent=j07,
            )
        else:
            weld(jid, ("W-017", "W-030", "W-031")[i % 3], on, lot, QWeldStatus.visual_accepted)
    # QX9: W-021's last SMAW weld 2026-03-28 (no later weld; the WPQ lapses on 2026-09-28)
    weld("PB-RT-T02-J01", "W-021", date(2026, 3, 28), None, QWeldStatus.visual_accepted)
    # September first NDT examinations: 120 with 5 rejected (6 above incl. J07, plus 114 here, 4 rejected)
    for i in range(114):
        on = date(2026, 9, 1) + timedelta(days=i % 28)
        rej = i in (13, 41, 77, 101)
        st = QWeldStatus.rejected if rej else QWeldStatus.accepted
        weld(f"T3-HVC-SUP-J{i + 1:03d}", ("W-030", "W-031")[i % 2], on, "T3-SUPPORTS-RT100", st,
             [ndt("reject" if rej else "accept", on + timedelta(days=1), 0, "porosity" if rej else None)], QNdtSelection.pct100)  # fmt: skip
    db.flush()
    from app.services.quality.q2 import welding as wsvc  # noqa: PLC0415

    for x in wpqs.values():
        x.last_use, x.continuity_until = wsvc.continuity(db, x)
    _bump(db, p, RT.wpq, wpq_no)
    _ = rania


def _calibrations(c: _Ctx, p: Project, r: Project) -> None:
    """CAL-ANIA-EXP-2026-0018 for MTE-0012 (CAL-NMS, accepted); MTE-0015 last calibrated 2025-10-01
    (due 2026-09-30, overdue at the clock); RUH-CCH loggers MTE-0101 … 0122 by CAL-NMS in March 2026
    (points −25 / 0 / +5 / +25 °C) and MTE-0042's in-tolerance calibration of 2026-03-08 (QX11)."""
    db = c.db
    rania, reem = c.u("rania.zahrani"), c.u("reem.mutairi")
    nms = c.sup["CAL-NMS"].id

    def cal(project: Project, m: QMteItem | None, no: int | None, d: date, points: list[tuple[str, str]], tol: str,
            by: uuid.UUID, interval: int | None = None, set_last: bool = True) -> QCalibration | None:  # fmt: skip
        if m is None:
            return None
        pts = [{"nominal": n, "as_found": f, "as_left": None, "tolerance": tol, "error": str(D(f) - D(n)),
                "in_tolerance": abs(D(f) - D(n)) <= D(tol), "as_left_in_tolerance": abs(D(f) - D(n)) <= D(tol)} for n, f in points]  # fmt: skip
        from app.services.quality.q2.calibration import due_on  # noqa: PLC0415

        months = interval or m.interval_months or 12
        x = QCalibration(
            id=uuid.uuid4(), project_id=project.id, cal_no=f"CAL-{project.code}-{d.year}-{no:04d}" if no else None,
            mte_id=m.id, kind=QCalKind.calibration, cal_date=d, provider_supplier_id=nms,
            certificate_no=f"NMS-{d.isoformat()}-{m.mte_no}", points=pts, as_found_ok=all(x["in_tolerance"] for x in pts),
            as_left_ok=True, traceability="Traceable to SI through a national metrology institute [VERIFY] SASO NMCC",
            next_due=due_on(d, months), decided_at=at(d + timedelta(days=2)), decided_by_user_id=by,
            status=QCalRecordStatus.accepted, created_by_user_id=by, seed_fake=True,
        )  # fmt: skip
        db.add(x)
        db.flush()
        if set_last:
            m.last_calibration_id = x.id
        return x

    cal(p, c.mte(p, 12), 18, date(2026, 2, 15), [("20", "20.2"), ("40", "40.1")], "0.5", rania)
    cal(p, c.mte(p, 15), None, date(2025, 10, 1), [("125", "126"), ("250", "251")], "5", rania)
    n = 0
    for no in range(101, 123):
        n += 1
        cal(
            r,
            c.mte(r, no),
            n,
            date(2026, 3, 1),
            [("-25", "-25.1"), ("0", "0.1"), ("5", "5.0"), ("25", "24.9")],
            "0.5",
            reem,
        )
    m42 = c.mte(r, 42)
    if m42 is not None:
        m42.tolerance_value, m42.tolerance_unit = D("0.5"), "°C"
        n += 1
        cal(
            r,
            m42,
            n,
            date(2026, 3, 8),
            [("-18", "-18.2"), ("0", "0.1"), ("5", "5.1")],
            "0.5",
            reem,
            set_last=True,
        )
    _bump(db, p, RT.calibration, 18)
    _bump(db, r, RT.calibration, n)
    db.flush()


def _ruh_tests(c: _Ctx, r: Project) -> None:
    """One ATP hygiene swab test on the dock (logistics test types)."""
    _test(
        c,
        r,
        12,
        c.tt("ATP-SWAB"),
        None,
        date(2026, 9, 18),
        site="S-DC1",
        loc="Z-DOCK dock door 3 bumper",
        eng=c.eng(r, "WAHAT"),
        results={"rlu": "88"},
        lab="LAB-RGM",
        detail={"reason_en": "88 RLU ≤ 150 RLU.", "reason_ar": "88 ≤ 150."},
    )
    _bump(c.db, r, RT.test_request, 12)


def seed(db: Session) -> None:
    """Seed Q2's Appendix A records (after the Q0 seed; idempotent)."""
    seed_libraries(db)
    seed_people(db)
    if db.scalar(select(QMar.id).where(QMar.seed_fake.is_(True)).limit(1)) is not None:
        return
    c = _Ctx(db)
    p, r = c.p.get("ANIA-EXP"), c.p.get("RUH-CCH")
    if p is None or r is None or "RMX" not in c.sup:
        return
    mars = _mars(c, p)
    _mir_named(c, p, mars)
    _mir_volume(c, p, mars)
    _pour_and_tests(c, p, mars)
    _test_volume(c, p)
    _bump(db, p, RT.pour, 77)
    _welding(c, p)
    _calibrations(c, p, r)
    _ruh_tests(c, r)
    db.flush()
    from app.services.quality.q2 import calibration  # noqa: PLC0415

    for m in db.scalars(select(QMteItem).where(QMteItem.project_id.in_([p.id, r.id]))):
        calibration.recompute(db, m, date(2026, 10, 6))
    db.flush()


# ==== after every part (registry SEEDS) =========================================================


def seed_after_parts(db: Session) -> None:
    """QX11: probe MTE-0042 (± 0.5 °C) as-found +1.2 °C at the 0 °C point on 2026-09-10; the last
    in-tolerance calibration 2026-03-08 → OOT-RUH-CCH-2026-0003 over 37 receiving checks (35
    proposed no_impact, 2 recheck, 1 decided ncr). Uses Q3's receiving usages of the probe when Q3
    recorded them (with `value=` / `lo=` / `hi=` notes); otherwise it records 37 receiving usages."""
    c = _Ctx(db)
    r = c.p.get("RUH-CCH")
    if r is None:
        return
    m = c.mte(r, 42)
    if m is None or db.scalar(select(QOotReview.id).where(QOotReview.mte_id == m.id)) is not None:
        return
    reem, imran = c.u("reem.mutairi"), c.u("imran.siddiq")
    start, end = at(date(2026, 3, 8), 12), at(date(2026, 9, 10), 8)
    used = list(
        db.scalars(
            select(QMteUsage).where(
                QMteUsage.mte_id == m.id, QMteUsage.used_at >= start, QMteUsage.used_at < end
            )
        )
    )
    if not used:
        for i in range(37):
            day = date(2026, 3, 9) + timedelta(days=i * 5)
            if i in (11, 29):
                note = "value=-18.4;lo=-30;hi=-18"  # frozen line: within 1.2 °C of the limit
            else:
                note = (
                    f"value={2.0 + (i % 5) * 0.4:.1f};lo=0;hi=8"
                    if i % 2
                    else f"value=-{21 + i % 3}.0;lo=-30;hi=-18"
                )
            u = QMteUsage(mte_id=m.id, project_id=r.id, record_type=RT.receipt.value, record_id=uuid.uuid4(),
                          used_at=at(day, 7, 30), verdict="ok", cal_status_at_use=QCalStatus.calibrated,
                          value_note=note, recorded_by_user_id=imran, seed_fake=True)  # fmt: skip
            db.add(u)
            used.append(u)
        db.flush()
    from app.services.quality.q2.calibration import due_on, margin_of, parse_note  # noqa: PLC0415

    nxt = (
        int(
            db.scalar(
                select(func.count())
                .select_from(QCalibration)
                .where(QCalibration.project_id == r.id)
            )
            or 0
        )
        + 1
    )
    cal = QCalibration(
        id=uuid.uuid4(), project_id=r.id, cal_no=f"CAL-RUH-CCH-2026-{nxt:04d}", mte_id=m.id, kind=QCalKind.calibration,
        cal_date=date(2026, 9, 10), provider_supplier_id=c.sup["CAL-NMS"].id, certificate_no="NMS-2026-09-10-MTE-0042",
        points=[{"nominal": "-18", "as_found": "-17.9", "as_left": None, "tolerance": "0.5", "error": "0.1", "in_tolerance": True, "as_left_in_tolerance": True},
                {"nominal": "0", "as_found": "1.2", "as_left": "0.1", "tolerance": "0.5", "error": "1.2", "in_tolerance": False, "as_left_in_tolerance": True}],
        as_found_ok=False, as_left_ok=True, max_found_error=D("1.2"), traceability="Traceable to SI [VERIFY] SASO NMCC",
        next_due=due_on(date(2026, 9, 10), m.interval_months or 6), decided_at=at(date(2026, 9, 11)), decided_by_user_id=reem,
        status=QCalRecordStatus.accepted, created_by_user_id=imran, seed_fake=True,
    )  # fmt: skip
    db.add(cal)
    db.flush()
    m.last_calibration_id, m.cal_due_on = cal.id, cal.next_due
    rv = QOotReview(
        id=uuid.uuid4(), project_id=r.id, oot_no="OOT-RUH-CCH-2026-0003", mte_id=m.id, calibration_id=cal.id,
        period_from=date(2026, 3, 8), period_to=date(2026, 9, 10), error_abs=D("1.2"), due_on=date(2026, 9, 25),
        status=QOotStatus.open, created_by_user_id=reem, seed_fake=True,
    )  # fmt: skip
    db.add(rv)
    db.flush()
    n_ncr = 0
    for u in sorted(used, key=lambda x: x.used_at)[:37]:
        v, lo, hi = parse_note(u.value_note)
        mg = margin_of(v, lo, hi)
        prop = (
            QOotDecision.no_impact.value
            if mg is not None and mg > D("1.2")
            else QOotDecision.recheck.value
        )
        item = QOotItem(review_id=rv.id, usage_id=u.id, record_type=u.record_type, record_id=u.record_id, ref=None,
                        used_at=u.used_at, value=v, limit_low=lo, limit_high=hi, margin=mg, proposed=prop, seed_fake=True)  # fmt: skip
        if prop == QOotDecision.no_impact.value:
            item.decision, item.justification = (
                prop,
                "Margin to the nearest limit is larger than the as-found error.",
            )
            item.decided_at, item.decided_by_user_id = at(date(2026, 9, 15)), reem
        elif n_ncr == 0:
            n31 = c.ncr(r, "NCR-RUH-CCH-2026-0031")
            item.decision = QOotDecision.ncr.value
            item.justification = (
                "Frozen line at −18.4 °C recorded; the true value may have been −17.2 °C."
            )
            item.ncr_id = n31.id if n31 else None
            item.decided_at, item.decided_by_user_id = at(date(2026, 9, 16)), reem
            n_ncr += 1
        db.add(item)
    _link(db, r, RT.oot_review, rv.id, RT.calibration, cal.id, "raised_from", at(date(2026, 9, 11)))
    from app.services.quality import numbering  # noqa: PLC0415

    numbering.bump_to(db, r, RT.oot_review, 2026, 3)
    numbering.bump_to(db, r, RT.calibration, 2026, nxt)
    from app.services.quality.q2 import calibration  # noqa: PLC0415

    calibration.recompute(db, m, date(2026, 10, 6))
    db.flush()
    _ = QNcrSourceType
