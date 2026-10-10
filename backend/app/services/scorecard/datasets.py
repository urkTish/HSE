"""The export dataset registry (spec 6g §3.8, EX-1…EX-4, §11.3 item 1). One entry per register:
its view and export capabilities, column classes (none / personal / sensitive / never), the right
each personal column needs, its mask mode and the purpose rule.

Two kinds of entries (DECISIONS D-225):
- **legacy** registers of Phases 0–5 (and the Phase 1 registers) keep their own export code and
  rules; the registry declares only their personal, sensitive and never columns, and the 6g
  mechanism selects, masks and re-encodes what that code returns;
- **native** registers parked by Phases 6a–6f are read here from their tables with the row scope
  of the caller's grant (project, contractor tree, sites); columns are classified from the table
  (photos, scans, encrypted texts and JSON blobs are never exported; user / worker columns are
  personal and need the dataset's names right)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.sqltypes import ARRAY, JSON, Boolean, Date, DateTime, Integer, Numeric, String

from app.core.enums import Capability, ExportDataset
from app.core.scorecard_enums import XpMaskMode, XpPdpl, XpPurposeRule
from app.models import (
    BanPatrol,
    ChecklistResponse,
    Drill,
    EmergencyAsset,
    EmergencyEvent,
    EnvComplaint,
    EnvReading,
    FieldAudit,
    FitnessAssessment,
    FitnessCode,
    FitnessHold,
    FitnessReferral,
    FitnessVerification,
    FuLesson,
    FuRequirement,
    HeatIllnessEntry,
    HeatWelfareCheck,
    MedicalExaminer,
    MedicalImportBatch,
    MedicalPlanLine,
    MedicalProvider,
    ProjectEngagement,
    Site,
    Spill,
    ToolboxTalk,
    User,
    WasteConsignment,
    Worker,
    Zone,
)
from app.services.permissions import Grant, Principal

C = Capability
P = XpPdpl
MM = XpMaskMode


@dataclass(frozen=True)
class Col:
    code: str
    en: str
    ar: str
    pdpl: XpPdpl = P.none
    needs: Capability | None = None
    mask: XpMaskMode | None = None
    default: bool = True


@dataclass
class Dataset:
    code: str
    module: str
    view_cap: Capability
    export_cap: Capability
    en: str
    ar: str
    purpose_rule: XpPurposeRule = XpPurposeRule.sensitive_column
    aggregate: bool = False  # Viewer / Client: aggregates only (EX-9)
    pdf_allowed: bool = True
    project_required: bool = True
    legacy: bool = False
    model: Any = None
    date_attr: str | None = None
    names_cap: Capability | None = None
    special: list[Col] = field(default_factory=list)  # declared columns (legacy and overrides)


# ---- labels ------------------------------------------------------------------------------------

AR_WORDS = {
    "ref": "المرجع", "no": "الرقم", "date": "التاريخ", "at": "الوقت", "status": "الحالة",
    "site": "الموقع", "zone": "المنطقة", "contractor": "المقاول", "engagement": "المقاول",
    "type": "النوع", "reason": "السبب", "name": "الاسم", "en": "(إنجليزي)", "ar": "(عربي)",
    "result": "النتيجة", "score": "الدرجة", "pct": "%", "count": "العدد", "outcome": "النتيجة",
    "headcount": "عدد العاملين", "checked": "فحص", "by": "بواسطة", "planned": "مخطط",
    "conducted": "منفذ", "drill": "التمرين", "event": "الحدث", "asset": "الأصل", "audit": "التدقيق",
    "talk": "الاجتماع", "consignment": "الشحنة", "reading": "القراءة", "spill": "الانسكاب",
    "complaint": "الشكوى", "lesson": "الدرس", "title": "العنوان", "code": "الرمز",
    "category": "الفئة", "value": "القيمة", "quantity": "الكمية", "unit": "الوحدة",
    "due": "الاستحقاق", "on": "", "received": "الاستلام", "closed": "الإغلاق", "source": "المصدر",
    "stage": "المرحلة", "body": "الجهة", "person": "الشخص", "worker": "العامل", "user": "المستخدم",
    "id": "المعرف", "number": "الرقم", "trade": "المهنة", "employer": "صاحب العمل",
    "description": "الوصف", "location": "الموقع", "duration": "المدة", "minutes": "دقائق",
    "shift": "الوردية", "parameter": "المعامل", "limit": "الحد", "period": "الفترة",
    "provider": "مقدم الخدمة", "licence": "الترخيص", "valid": "سارٍ", "until": "حتى",
    "kind": "النوع", "level": "المستوى", "severity": "الخطورة", "potential": "المحتملة",
    "activity": "النشاط", "issued": "الإصدار", "started": "البدء", "released": "الإفراج",
    "examined": "الفحص", "assessment": "التقييم", "verification": "التحقق", "method": "الطريقة",
    "channel": "القناة", "required": "مطلوب", "form": "النموذج", "filer": "المقدِّم",
    "deadline": "المهلة", "hours": "الساعات", "presenter": "المقدّم", "inspector": "المفتش",
    "lead": "الرئيسي", "auditor": "المدقق", "driver": "السائق", "mobile": "الجوال",
    "complainant": "المشتكي", "contact": "التواصل", "persons": "الأشخاص", "present": "الحاضرون",
    "water": "الماء", "temp": "الحرارة", "c": "°م", "late": "متأخر", "entry": "إدخال",
}  # fmt: skip


def label_ar(code: str) -> str:
    words = [AR_WORDS.get(w, w) for w in code.split("_")]
    return " ".join(w for w in words if w)


def label_en(code: str) -> str:
    return code.replace("_", " ").capitalize()


# ---- legacy registers (Phases 0–5, Phase 1) ------------------------------------------------------

_LEGACY_CAP: dict[str, Capability] = {}


def _legacy_cap(ds: ExportDataset) -> tuple[Capability, str]:
    from app.services.access import exports as a  # noqa: PLC0415
    from app.services.cert import exports as ce  # noqa: PLC0415
    from app.services.ptw import exports as pt  # noqa: PLC0415
    from app.services.train import exports as tr  # noqa: PLC0415

    if ds in tr.DATASETS:
        return C.export_training, "training"
    if ds in ce.DATASETS:
        return C.export_cert, "cert"
    if ds in a.DATASETS:
        return C.export_access, "access"
    if ds in pt.DATASETS:
        return C.export_ptw, "ptw"
    if ds.value in (
        "workforce_returns",
        "incidents",
        "observations",
        "inspections",
        "corrective_actions",
        "hse_meetings",
    ):
        return C.export_kpis, "phase1"
    return C.export_lists, "foundation"


SPECIAL: dict[str, list[Col]] = {
    "incidents": [
        Col("person", "Person", "الشخص", P.none, None, MM.person_n),
        Col("person_name", "Person name", "اسم الشخص", P.sensitive, C.export_identity,
            MM.privacy_case, False),
        Col("id_type", "ID type", "نوع الهوية", P.sensitive, C.export_identity, MM.omit, False),
        Col("id_number", "ID number", "رقم الهوية", P.sensitive, C.export_identity, MM.mask_id,
            False),
        Col("employee_no", "Employee no.", "الرقم الوظيفي", P.sensitive, C.export_identity,
            MM.omit, False),
        Col("gosi_case_ref", "GOSI case ref", "مرجع التأمينات", P.sensitive, C.export_identity,
            MM.omit, False),
        Col("medical_attachments", "Medical attachments", "المرفقات الطبية", P.never),
        Col("nationality", "Nationality", "الجنسية", P.never),
    ],
    "workers": [
        Col("full_name_en", "Name (EN)", "الاسم (إنجليزي)", P.personal, C.worker_view, MM.omit),
        Col("full_name_ar", "Name (AR)", "الاسم (عربي)", P.personal, C.worker_view, MM.omit),
        Col("id_number", "ID number", "رقم الهوية", P.sensitive, C.export_access_identity,
            MM.mask_id, False),
        Col("photo", "Photo", "الصورة", P.never),
        Col("id_copy", "ID copy", "صورة الهوية", P.never),
    ],
    "permits": [
        Col("issuer_name", "Issuer", "المُصدر", P.personal, C.worker_view, MM.role_only),
        Col("receiver_name", "Receiver", "المستلم", P.personal, C.worker_view, MM.role_only),
        Col("signatures", "Signatures", "التواقيع", P.never),
    ],
    "gas_tests": [
        Col("readings", "Gas readings", "قراءات الغاز", P.never),
        Col("signature", "Signature", "التوقيع", P.never),
    ],
    "locks": [Col("holder_name", "Holder", "الحامل", P.personal, C.worker_view, MM.person_n)],
    "ptw_appointments": [
        Col("holder_name", "Holder", "الحامل", P.personal, C.worker_view, MM.person_n)],
    "observations": [Col("observer_name", "Observer", "المراقِب", P.personal,
                         C.observer_identity_view, MM.role_only)],
}  # fmt: skip


# ---- native registers (6a–6f) -------------------------------------------------------------------

NATIVE: list[Dataset] = [
    # 6a (163; tier columns: reasons and scans never; names need 46)
    Dataset("fitness_codes", "6a", C.fitness_catalogue_view, C.export_medical, "Fitness codes",
            "رموز اللياقة", model=FitnessCode, project_required=False),
    Dataset("medical_providers", "6a", C.fitness_catalogue_view, C.export_medical,
            "Medical providers", "مقدمو الخدمات الطبية", model=MedicalProvider,
            project_required=False),
    Dataset("medical_examiners", "6a", C.fitness_catalogue_view, C.export_medical,
            "Medical examiners", "الأطباء الفاحصون", model=MedicalExaminer,
            project_required=False, names_cap=C.fitness_catalogue_view),
    Dataset("medical_plan", "6a", C.fitness_catalogue_view, C.export_medical, "Medical plan",
            "الخطة الطبية", model=MedicalPlanLine),
    Dataset("fitness_status", "6a", C.fitness_status_view, C.export_medical,
            "Fitness assessments", "تقييمات اللياقة", model=FitnessAssessment,
            date_attr="examined_on", names_cap=C.worker_view, aggregate=True),
    Dataset("fitness_gaps", "6a", C.fitness_status_view, C.export_medical, "Fitness gaps",
            "فجوات اللياقة", model=FitnessHold, date_attr="started_at", names_cap=C.worker_view,
            aggregate=True),
    Dataset("fitness_holds", "6a", C.fitness_status_view, C.export_medical, "Fitness holds",
            "إيقافات اللياقة", model=FitnessHold, date_attr="started_at",
            names_cap=C.worker_view, aggregate=True),
    Dataset("fitness_referrals", "6a", C.fitness_status_view, C.export_medical,
            "Fitness referrals", "إحالات اللياقة", model=FitnessReferral, date_attr="raised_at",
            names_cap=C.worker_view, aggregate=True),
    Dataset("fitness_verifications", "6a", C.fitness_review, C.export_medical,
            "Fitness verifications", "التحقق من اللياقة", model=FitnessVerification,
            date_attr="performed_at"),
    Dataset("medical_imports", "6a", C.fitness_import, C.export_medical, "Medical imports",
            "استيراد البيانات الطبية", model=MedicalImportBatch, date_attr="created_at"),
    # 6b (176)
    Dataset("heat_patrols", "6b", C.heat_view, C.export_heat, "Midday-ban patrols",
            "جولات حظر الظهيرة", model=BanPatrol, date_attr="checked_at", aggregate=True),
    Dataset("heat_welfare_checks", "6b", C.heat_view, C.export_heat, "Welfare checks",
            "فحوص الرعاية", model=HeatWelfareCheck, date_attr="checked_at", aggregate=True),
    Dataset("heat_illness_log", "6b", C.heat_log_view, C.export_heat, "Heat-illness log",
            "سجل أمراض الحرارة", model=HeatIllnessEntry, date_attr="event_at",
            names_cap=C.worker_view, aggregate=True,
            special=[Col("review", "Review", "المراجعة", P.never),
                     Col("context", "Context", "السياق", P.never)]),
    # 6c (189)
    Dataset("emergency_drills", "6c", C.emergency_view, C.emergency_kpi_view, "Drills",
            "التمارين", model=Drill, date_attr="planned_at"),
    Dataset("emergency_assets", "6c", C.emergency_view, C.emergency_kpi_view,
            "Emergency assets", "أصول الطوارئ", model=EmergencyAsset),
    Dataset("emergency_events", "6c", C.emergency_view, C.emergency_kpi_view,
            "Emergency events", "أحداث الطوارئ", model=EmergencyEvent, date_attr="raised_at"),
    # 6d (200)
    Dataset("field_inspections", "6d", C.field_view, C.field_view, "Inspections (6d)",
            "التفتيش الميداني", model=ChecklistResponse, date_attr="completed_date",
            names_cap=C.field_view),
    Dataset("field_audits", "6d", C.field_view, C.field_view, "HSE audits", "تدقيقات السلامة",
            model=FieldAudit, date_attr="planned_start", names_cap=C.field_view),
    Dataset("toolbox_talks", "6d", C.field_view, C.field_view, "Toolbox talks",
            "اجتماعات التوعية", model=ToolboxTalk, date_attr="delivered_date",
            names_cap=C.toolbox_names_view),
    # 6e (202; complainant data needs 212)
    Dataset("waste_consignments", "6e", C.env_view, C.env_view, "Waste consignments",
            "شحنات النفايات", model=WasteConsignment, date_attr="dispatched_date",
            names_cap=C.env_permit_manage,
            special=[Col("driver_name", "Driver", "السائق", P.personal, C.env_permit_manage,
                         MM.role_only, False),
                     Col("driver_mobile", "Driver mobile", "جوال السائق", P.personal,
                         C.env_permit_manage, MM.omit, False)]),
    Dataset("env_readings", "6e", C.env_view, C.env_view, "Environmental readings",
            "القراءات البيئية", model=EnvReading, date_attr="day"),
    Dataset("env_spills", "6e", C.env_view, C.env_view, "Spills", "الانسكابات", model=Spill,
            date_attr="occurred_date"),
    Dataset("env_complaints", "6e", C.env_view, C.env_view, "Complaints", "الشكاوى",
            model=EnvComplaint, date_attr="received_date", names_cap=C.env_complaint,
            special=[Col("complainant_name", "Complainant", "المشتكي", P.personal,
                         C.env_complaint, MM.omit, False),
                     Col("complainant_contact", "Complainant contact", "تواصل المشتكي",
                         P.personal, C.env_complaint, MM.omit, False),
                     Col("description", "Description", "الوصف", P.personal, C.env_complaint,
                         MM.omit, False)]),
    # 6f (215, 222)
    Dataset("notification_requirements", "6f", C.followup_view, C.followup_view,
            "Notification requirements", "متطلبات الإخطار", model=FuRequirement,
            date_attr="due_at",
            special=[Col("waiver_text", "Waiver text", "نص الإعفاء", P.never)]),
    Dataset("lessons", "6f", C.lesson_library_view, C.lesson_library_view, "Lessons learned",
            "الدروس المستفادة", model=FuLesson, date_attr="published_at",
            project_required=False),
]  # fmt: skip
NATIVE_BY_CODE = {d.code: d for d in NATIVE}

SKIP = {"id", "seed_fake", "year", "seq", "client_uuid", "alerts_sent", "search_text",
        "created_by_user_id", "updated_by_user_id", "updated_at", "warnings", "project_id",
        "name_norm_en", "name_norm_ar", "legal_name_en_norm", "legal_name_ar_norm"}  # fmt: skip
NEVER_PARTS = ("photo", "scan", "_enc", "signature", "file_id", "file_ids", "report_en_id",
               "report_ar_id", "answers", "evidence")  # fmt: skip
USER_SUFFIX = ("_user_id", "_user_ids", "inspector_id", "author_id", "lead_auditor_id",
               "team_ids", "examiner_id")  # fmt: skip
CODE_FK = {"site_id": "site", "zone_id": "zone"}


def _is_eng(name: str) -> bool:
    return name.endswith("engagement_id")


def native_columns(ds: Dataset) -> list[Col]:
    special = {c.code: c for c in ds.special}
    out: list[Col] = []
    for col in ds.model.__table__.columns:
        k = col.key
        if k in special:
            out.append(special[k])
            continue
        if k in SKIP:
            continue
        if any(x in k for x in NEVER_PARTS) or (isinstance(col.type, (JSON, ARRAY)) and k not in (
            "zone_ids", "site_ids")):  # fmt: skip
            if any(x in k for x in NEVER_PARTS):
                out.append(Col(k, label_en(k), label_ar(k), P.never))
            continue
        if k == "worker_id":
            out.append(Col("worker", "Worker", "العامل", P.personal, ds.names_cap or C.worker_view,
                           MM.person_n))  # fmt: skip
            continue
        if k.endswith(USER_SUFFIX):
            out.append(Col(k.removesuffix("_id").removesuffix("_user"), label_en(k[:-3]),
                           label_ar(k[:-3]), P.personal, ds.names_cap or C.worker_view,
                           MM.role_only))  # fmt: skip
            continue
        if _is_eng(k):
            name = k.removesuffix("_id")
            out.append(Col(name, label_en(name), label_ar(name)))
            continue
        if k in CODE_FK:
            out.append(Col(CODE_FK[k], label_en(CODE_FK[k]), label_ar(CODE_FK[k])))
            continue
        if k.endswith("_id") or k.endswith("_ids"):
            continue
        if not isinstance(col.type, (String, Integer, Numeric, Date, DateTime, Boolean)) and not (
            hasattr(col.type, "enums") or k in ("zone_ids", "site_ids")):  # fmt: skip
            continue
        out.append(Col(k, label_en(k), label_ar(k)))
    for k, c in special.items():
        if k not in {x.code for x in out}:
            out.append(c)
    return out


def get(code: str) -> Dataset | None:
    if code in NATIVE_BY_CODE:
        return NATIVE_BY_CODE[code]
    try:
        ds = ExportDataset(code)
    except ValueError:
        return None
    cap, module = _legacy_cap(ds)
    rule = XpPurposeRule.injured_identity if code == "incidents" else XpPurposeRule.sensitive_column
    en, ar = LEGACY_LABELS.get(code, (label_en(code), label_ar(code)))
    return Dataset(code, module, cap, cap, en, ar, rule, legacy=True,
                   pdf_allowed=True, project_required=module not in ("foundation",),
                   special=SPECIAL.get(code, []))  # fmt: skip


# Names of the Phase 0–5 datasets wrapped in the registry (EN / AR).
LEGACY_LABELS: dict[str, tuple[str, str]] = {
    "projects": ("Projects", "المشاريع"),
    "sites": ("Sites", "المواقع"),
    "zones": ("Zones", "المناطق"),
    "contractors": ("Contractors", "المقاولون"),
    "engagements": ("Contractor engagements", "ارتباطات المقاولين"),
    "users": ("Users", "المستخدمون"),
    "audit_log": ("Audit log", "سجل التدقيق"),
    "workforce_returns": ("Workforce returns", "تقارير القوى العاملة"),
    "incidents": ("Incidents", "الحوادث"),
    "observations": ("Observations", "الملاحظات"),
    "inspections": ("Inspections", "عمليات التفتيش"),
    "corrective_actions": ("Corrective actions", "الإجراءات التصحيحية"),
    "hse_meetings": ("HSE meetings", "اجتماعات السلامة"),
    "workers": ("Workers", "العمال"),
    "deployments": ("Deployments", "التكليفات"),
    "inductions": ("Inductions", "التعريفات"),
    "pass_applications": ("Pass applications", "طلبات التصاريح"),
    "airport_passes": ("Airport passes", "تصاريح المطار"),
    "adps": ("Airside driving permits (ADP)", "تصاريح القيادة في الساحة (ADP)"),
    "airside_offences": ("Airside offences", "مخالفات الساحة"),
    "vehicles": ("Vehicles", "المركبات"),
    "avps": ("Airside vehicle permits (AVP)", "تصاريح مركبات الساحة (AVP)"),
    "waps": ("Work area permits (WAP)", "تصاريح مناطق العمل (WAP)"),
    "notam_requests": ("NOTAM requests", "طلبات NOTAM"),
    "obstacle_clearances": ("Obstacle clearances", "تصاريح العوائق"),
    "ops_events": ("Airport operations events", "أحداث عمليات المطار"),
    "gate_log": ("Gate log", "سجل البوابات"),
    "permits": ("Permits to work", "تصاريح العمل"),
    "permit_suspensions": ("Permit suspensions", "إيقافات التصاريح"),
    "gas_tests": ("Gas tests", "اختبارات الغاز"),
    "gas_detectors": ("Gas detectors", "أجهزة كشف الغاز"),
    "isolations": ("Isolations", "العزل"),
    "locks": ("Locks", "الأقفال"),
    "ptw_appointments": ("PTW appointments", "تعيينات تصاريح العمل"),
    "jsa_templates": ("JSA templates", "نماذج تحليل السلامة الوظيفية"),
    "simops_conflicts": ("SIMOPS conflicts", "تعارضات الأعمال المتزامنة"),
    "ptw_audits": ("PTW audits", "تدقيقات تصاريح العمل"),
    "tpis": ("Third-party inspectors", "جهات الفحص الخارجية"),
    "equipment": ("Equipment", "المعدات"),
    "equipment_deployments": ("Equipment deployments", "تكليفات المعدات"),
    "equipment_certificates": ("Equipment certificates", "شهادات المعدات"),
    "scaffolds": ("Scaffolds", "السقالات"),
    "personnel_certificates": ("Personnel certificates", "شهادات الأفراد"),
    "cert_verifications": ("Certificate verifications", "التحقق من الشهادات"),
    "equipment_defects": ("Equipment defects", "عيوب المعدات"),
    "blacklist_register": ("Ban register", "سجل الحظر"),
    "cert_imports": ("Certificate imports", "استيراد الشهادات"),
    "training_courses": ("Training courses", "الدورات التدريبية"),
    "training_providers": ("Training providers", "مقدمو التدريب"),
    "trainer_authorisations": ("Trainer authorisations", "اعتمادات المدربين"),
    "training_matrix": ("Training matrix", "مصفوفة التدريب"),
    "training_sessions": ("Training sessions", "الجلسات التدريبية"),
    "training_attendance": ("Training attendance", "حضور التدريب"),
    "training_records": ("Training records", "سجلات التدريب"),
    "training_verifications": ("Training verifications", "التحقق من التدريب"),
    "training_gaps": ("Training gaps", "فجوات التدريب"),
    "refresher_plan": ("Refresher plan", "خطة التدريب التنشيطي"),
    "training_hours": ("Training hours", "ساعات التدريب"),
    "training_imports": ("Training imports", "استيراد التدريب"),
}


def all_codes() -> list[str]:
    return [*[d.value for d in ExportDataset if d.value not in NATIVE_BY_CODE], *NATIVE_BY_CODE]


def columns(ds: Dataset) -> list[Col]:
    return native_columns(ds) if not ds.legacy else list(ds.special)


# ---- native rows ---------------------------------------------------------------------------------


def _eng_attr(model: Any) -> str | None:
    for k in (
        "engagement_id",
        "responsible_engagement_id",
        "owner_engagement_id",
        "host_engagement_id",
        "generator_engagement_id",
        "auditee_engagement_id",
        "filer_engagement_id",
    ):
        if hasattr(model, k):
            return k
    return None


def native_rows(
    db: Session,
    ds: Dataset,
    g: Grant | None,
    project_id: uuid.UUID | None,
    filters: dict[str, Any],
) -> list[Any]:
    m = ds.model
    stmt = select(m)
    if project_id is not None:
        if hasattr(m, "project_id"):
            stmt = stmt.where(m.project_id == project_id)
        elif hasattr(m, "source_project_id"):
            stmt = stmt.where(m.source_project_id == project_id)
    ea = _eng_attr(m)
    if g is not None and g.engagement_ids is not None and ea is not None:
        stmt = stmt.where(getattr(m, ea).in_(list(g.engagement_ids)))
    if g is not None and getattr(g, "site_ids", None) is not None and hasattr(m, "site_id"):
        stmt = stmt.where(m.site_id.in_(list(g.site_ids or [])))
    if ds.date_attr:
        col = getattr(m, ds.date_attr)
        if filters.get("from"):
            stmt = stmt.where(col >= filters["from"])
        if filters.get("to"):
            stmt = stmt.where(col <= filters["to"])
        stmt = stmt.order_by(col)
    if filters.get("status") and hasattr(m, "status"):
        stmt = stmt.where(m.status == filters["status"])
    return list(db.scalars(stmt))


class Resolver:
    """Codes and names for ids (cached per export)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.cache: dict[tuple[str, Any], str] = {}

    def _get(self, kind: str, key: Any, fn: Any) -> str:
        if (kind, key) not in self.cache:
            self.cache[(kind, key)] = fn()
        return self.cache[(kind, key)]

    def eng(self, eid: uuid.UUID | None) -> str:
        if eid is None:
            return ""

        def f() -> str:
            e = self.db.get(ProjectEngagement, eid)
            return e.contractor.short_code if e and e.contractor else ""

        return self._get("eng", eid, f)

    def site(self, sid: uuid.UUID | None) -> str:
        def f() -> str:
            s = self.db.get(Site, sid) if sid else None
            return s.code if s else ""

        return self._get("site", sid, f)

    def zone(self, zid: uuid.UUID | None) -> str:
        def f() -> str:
            z = self.db.get(Zone, zid) if zid else None
            return z.code if z else ""

        return self._get("zone", zid, f)

    def user(self, uid: Any) -> str:
        if isinstance(uid, list):
            return ", ".join(self.user(u) for u in uid)

        def f() -> str:
            u = self.db.get(User, uid) if uid else None
            return u.full_name_en if u else ""

        return self._get("user", uid, f)

    def worker(self, wid: uuid.UUID | None) -> str:
        def f() -> str:
            w = self.db.get(Worker, wid) if wid else None
            return w.full_name_en if w else ""

        return self._get("worker", wid, f)


def cell(v: Any) -> Any:
    if v is None:
        return ""
    if hasattr(v, "value") and not isinstance(v, (Decimal, int, float)):
        return v.value
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, list):
        return ", ".join(str(cell(x)) for x in v)
    return v


def native_value(r: Resolver, obj: Any, col: Col) -> tuple[Any, Any]:
    """(display value, raw key for masking) of one native column."""
    k = col.code
    if k == "worker":
        wid = getattr(obj, "worker_id", None)
        return r.worker(wid), wid
    if hasattr(obj, k + "_user_id"):
        uid = getattr(obj, k + "_user_id")
        return r.user(uid), uid
    if hasattr(obj, k + "_user_ids"):
        uid = getattr(obj, k + "_user_ids")
        return r.user(uid), None
    if hasattr(obj, k + "_id") and _is_eng(k + "_id"):
        return r.eng(getattr(obj, k + "_id")), None
    if k in ("site", "zone"):
        v = getattr(obj, k + "_id", None)
        return (r.site(v) if k == "site" else r.zone(v)), None
    if k in ("inspector", "author", "lead_auditor", "examiner"):
        uid = getattr(obj, k + "_id", None)
        return r.user(uid), uid
    if k == "team":
        return r.user(getattr(obj, "team_ids", []) or []), None
    if k == "zone_ids":
        return ", ".join(r.zone(z) for z in getattr(obj, k) or []), None
    if k == "site_ids":
        return ", ".join(r.site(s) for s in getattr(obj, k) or []), None
    return cell(getattr(obj, k, None)), None


def month_key(obj: Any, ds: Dataset) -> str:
    v = getattr(obj, ds.date_attr, None) if ds.date_attr else None
    if isinstance(v, (datetime, date)):
        return f"{v.year:04d}-{v.month:02d}"
    return "—"


__all__ = ["Principal"]
