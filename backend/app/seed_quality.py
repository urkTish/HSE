"""Phase 8 Quality demo seed (spec 8-quality Appendix A; `seed_fake = true`; fictional people
with `@example.com` emails and `+96650000xxxx` mobiles).

Two layers:

* **Base** (`Q_PROJECTS`, `Q_SITES`, `Q_ZONES`, `Q_CONTRACTORS`, `Q_USERS`, `Q_EXTRA_ROLES`): the
  logistics project RUH-CCH, its site and zones, the 3PL contractor WAHAT and the quality users of
  Appendix A.1. `app.seed.seed` appends them to its own lists, so every test database has them
  (`tests/test_auth.py` counts Sarah's three projects). WAHAT is engaged on RUH-CCH without HSE
  work sites, so no daily workforce returns are expected there and RUH-CCH adds nothing to the HSE
  data completeness K-45 or the daily-return alerts (D-321).
* **Data** (`seed_quality_data`): the Part A records for ANIA-EXP (construction) and RUH-CCH
  (logistics) — settings and profiles, positions and holders, the default matrix, suppliers,
  customers, systems, criteria, M&TE, NCRs with RCA, dispositions, costs, CAs and sign-offs, the
  quality alert, observations and complaints — then each wave-2 part's `seed(db)`
  (`app/seed_quality_q1.py` … `q4.py` and registry `SEEDS`). Runs after the Option 7b seed."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.core.enums import (
    ContractorCategory,
    ContractorStatus,
    EmployerType,
    Language,
    ProjectType,
    Role,
    SiteSide,
    ZoneType,
)
from app.core.hse_enums import CaPriority, CaSourceType, CaStatus, ControlLevel
from app.core.quality.common import (
    DEFAULT_POSITIONS,
    QAccreditationBody,
    QAccreditationStandard,
    QAlertSeverity,
    QAlertStatus,
    QAssigneeKind,
    QCalStatus,
    QCauseCategory,
    QComplaintChannel,
    QComplaintSeverity,
    QComplaintStatus,
    QCostType,
    QCriterionKind,
    QCriterionStatus,
    QCustomerKind,
    QDetectionStage,
    QDiscipline,
    QDisposition,
    QJustified,
    QLinkKind,
    QMteCheckKind,
    QMteType,
    QNcrCategory,
    QNcrClass,
    QNcrSourceType,
    QNcrStatus,
    QObservationStatus,
    QProfileScope,
    QRcaMethod,
    QRecordType,
    QSectorProfile,
    QSignoffChannel,
    QSupplierStatus,
)
from app.core.text import normalize, search_blob
from app.models import CorrectiveAction, Project, ProjectEngagement, Site, User, Zone
from app.models.quality import (
    QAlert,
    QAlertAck,
    QComplaint,
    QCriterion,
    QCustomer,
    QLink,
    QMteItem,
    QNcr,
    QNcrCost,
    QNcrLine,
    QNcrRca,
    QObservation,
    QPosition,
    QPositionHolder,
    QRpRule,
    QSettings,
    QSignoff,
    QSupplier,
    QSupplierAccreditation,
    QSystem,
)

RIYADH = ZoneInfo("Asia/Riyadh")
D = Decimal

# ---- base layer (appended to app.seed lists) -----------------------------------------------------

Q_PROJECTS: list[dict[str, Any]] = [
    {
        "code": "RUH-CCH",
        "name_en": "Riyadh Cold Chain Hub — Al-Sulay",
        "name_ar": "مركز الرياض لسلسلة التبريد — السلي",
        "project_type": ProjectType.logistics,
        "airport_iata": None,
        "client_name_en": "Al-Wahat Logistics Co. (fictional)",
        "client_name_ar": "شركة الواحة للخدمات اللوجستية (وهمية)",
        "city": "Riyadh",
        "start_date": date(2025, 11, 1),
        "planned_end_date": date(2030, 12, 31),
        "settings": {
            "ltifr_base_hours": 200_000,
            "rate_base_hours": 200_000,
            "show_hijri": True,
            "default_language": Language.ar,
        },
    }
]
Q_SITES: list[dict[str, Any]] = [
    {
        "project": "RUH-CCH",
        "code": "S-DC1",
        "name_en": "Distribution Centre 1",
        "name_ar": "مركز التوزيع 1",
        "site_side": SiteSide.other,
        "gps_lat": 24.585,
        "gps_lng": 46.812,
    }
]
_RUH_ZONES = (
    ("Z-DOCK", "Controlled dock", "الرصيف المبرد"),
    ("Z-FRZ1", "Frozen chamber 1", "غرفة التجميد 1"),
    ("Z-CHL1", "Chilled chamber 1", "غرفة التبريد 1"),
    ("Z-PHR1", "Medicines 2–8 °C", "الأدوية 2–8 °م"),
    ("Z-AMB1", "Controlled ambient", "المحيط المضبوط"),
    ("Z-DRY1", "Dry store", "المخزن الجاف"),
    ("Z-QRT", "Quarantine cage", "قفص العزل"),
    ("Z-RET", "Returns area", "منطقة المرتجعات"),
)
Q_ZONES: list[dict[str, Any]] = [
    {
        "site": ("RUH-CCH", "S-DC1"),
        "code": c,
        "name_en": en,
        "name_ar": ar,
        "zone_type": ZoneType.other,
    }
    for c, en, ar in _RUH_ZONES
]
Q_CONTRACTORS: list[dict[str, Any]] = [
    {
        "short_code": "WAHAT",
        "legal_name_en": "Al-Wahat Logistics Co.",
        "legal_name_ar": "شركة الواحة للخدمات اللوجستية",
        "cr_number": "1010000007",
        "contractor_category": ContractorCategory.other,
        "status": ContractorStatus.approved,
        "contact": ("Reem Al-Mutairi", "+966500000111", "wahat.qa@example.com"),
        "cr_expiry_date": date(2027, 12, 31),
        # D-321: no HSE work sites — no daily workforce returns are expected (K-45 unaffected)
        "engagement": (
            "RUH-CCH",
            1,
            None,
            [],
            "3PL operator: cold chain storage and distribution",
            "مشغل لوجستي: التخزين المبرد والتوزيع",
            date(2025, 11, 1),
        ),
    }
]


def _u(
    email: str,
    en: str,
    ar: str,
    mobile: str,
    employer: Any,
    job: str,
    roles: list[tuple[Role, str, list[str], str | None]],
) -> dict[str, Any]:
    return {
        "email": email,
        "name": (en, ar),
        "mobile": mobile,
        "employer": employer,
        "job": job,
        "roles": roles,
    }


A, R = "ANIA-EXP", "RUH-CCH"
PMC, CLIENT = EmployerType.pmc_consultant, EmployerType.client
Q_USERS: list[dict[str, Any]] = [
    _u(
        "hatem.shehri@example.com",
        "Hatem Al-Shehri",
        "حاتم الشهري",
        "+966500000301",
        PMC,
        "QA/QC Manager",
        [(Role.qa_qc_manager, A, [], None)],
    ),
    _u(
        "bilal.qureshi@example.com",
        "Bilal Qureshi",
        "بلال قريشي",
        "+966500000302",
        "RAWABI",
        "Quality Engineer",
        [(Role.quality_engineer, A, [], "RAWABI")],
    ),
    # Appendix A.1 names joseph.mathew@example.com, which the PTW seed already uses for a QIMMA
    # supervisor on RBT-52; the QC inspector gets his own address (D-322)
    _u(
        "joseph.mathew.qc@example.com",
        "Joseph Mathew",
        "جوزيف ماثيو",
        "+966500000303",
        "RAWABI",
        "QC Inspector",
        [(Role.qc_inspector, A, [], "RAWABI")],
    ),
    _u(
        "abdullah.dossary@example.com",
        "Abdullah Al-Dossary",
        "عبدالله الدوسري",
        "+966500000304",
        PMC,
        "Consultant Resident Engineer",
        [(Role.responsible_person, A, [], None)],
    ),
    _u(
        "sultan.mutlaq@example.com",
        "Sultan Al-Mutlaq",
        "سلطان المطلق",
        "+966500000305",
        CLIENT,
        "Client Representative",
        [(Role.responsible_person, A, [], None)],
    ),
    _u(
        "arun.pillai@example.com",
        "Arun Pillai",
        "آرون بيلاي",
        "+966500000306",
        "NAJD",
        "Welding Inspector (CWI)",
        [(Role.qc_inspector, A, [], "NAJD")],
    ),
    _u(
        "mazen.harbi@example.com",
        "Mazen Al-Harbi",
        "مازن الحربي",
        "+966500000307",
        PMC,
        "QC Inspector",
        [(Role.qc_inspector, A, [], None)],
    ),
    _u(
        "rania.zahrani@example.com",
        "Rania Al-Zahrani",
        "رانيا الزهراني",
        "+966500000308",
        PMC,
        "Quality Engineer",
        [(Role.quality_engineer, A, [], None)],
    ),
    _u(
        "reem.mutairi@example.com",
        "Reem Al-Mutairi",
        "ريم المطيري",
        "+966500000311",
        CLIENT,
        "QA/QC Manager",
        [(Role.qa_qc_manager, R, [], None)],
    ),
    _u(
        "imran.siddiq@example.com",
        "Imran Siddiq",
        "عمران صديق",
        "+966500000312",
        CLIENT,
        "Warehouse QC",
        [(Role.warehouse_qc, R, [], None)],
    ),
    _u(
        "saad.anazi@example.com",
        "Saad Al-Anazi",
        "سعد العنزي",
        "+966500000313",
        CLIENT,
        "Warehouse Manager",
        [(Role.responsible_person, R, [], None)],
    ),
    _u(
        "lama.qarni@example.com",
        "Lama Al-Qarni",
        "لمى القرني",
        "+966500000314",
        CLIENT,
        "Responsible Pharmacist",
        [(Role.responsible_person, R, [], None)],
    ),
    _u(
        "naveen.kumar@example.com",
        "Naveen Kumar",
        "نافين كومار",
        "+966500000315",
        CLIENT,
        "Transport Supervisor",
        [(Role.warehouse_qc, R, [], None)],
    ),
]
# Existing Phase 0 users with an extra assignment (A.1: Sarah is also Viewer on RUH-CCH)
Q_EXTRA_ROLES: dict[str, list[tuple[Role, str, list[str], str | None]]] = {
    "sarah.mitchell@example.com": [(Role.viewer_client, R, [], None)],
}


# ---- data layer ----------------------------------------------------------------------------------


class _W:
    """Lookup helpers for the data layer."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.users = {u.email.split("@")[0]: u for u in db.scalars(select(User))}
        self.projects = {p.code: p for p in db.scalars(select(Project))}
        self.sites = {(s.project_id, s.code): s for s in db.scalars(select(Site))}
        self.zones = {(z.project_id, z.code): z for z in db.scalars(select(Zone))}
        self.engs = {
            (e.project_id, e.contractor.short_code): e
            for e in db.scalars(select(ProjectEngagement))
        }

    def u(self, who: str) -> uuid.UUID:
        return self.users[who].id

    def site(self, p: Project, code: str) -> uuid.UUID:
        return self.sites[(p.id, code)].id

    def zone(self, p: Project, code: str) -> uuid.UUID:
        return self.zones[(p.id, code)].id

    def eng(self, p: Project, code: str) -> uuid.UUID:
        return self.engs[(p.id, code)].id


def at(d: date, hh: int = 9, mm: int = 0) -> datetime:
    return datetime.combine(d, time(hh, mm), RIYADH).astimezone(UTC)


def _settings(db: Session, w: _W, p: Project, prof: QSectorProfile, values: dict[str, Any]) -> None:
    from app.services.quality import rpm  # noqa: PLC0415

    row = db.get(QSettings, p.id)
    if row is None:
        row = QSettings(project_id=p.id, values={})
        db.add(row)
    row.sector_profile = prof
    row.quality_start_date = date(2026, 1, 1)
    row.values = values
    row.updated_at = at(date(2026, 1, 1))
    db.flush()
    rpm.seed_defaults(db, p, prof, w.u("faisal.harbi"))
    db.execute(sa_update(QPosition).where(QPosition.project_id == p.id).values(seed_fake=True))
    db.execute(sa_update(QRpRule).where(QRpRule.project_id == p.id).values(seed_fake=True))


def _hold(db: Session, w: _W, p: Project, code: str, who: str) -> None:
    pos = db.scalar(select(QPosition).where(QPosition.project_id == p.id, QPosition.code == code))
    assert pos is not None  # noqa: S101
    db.add(
        QPositionHolder(
            position_id=pos.id, user_id=w.u(who), valid_from=date(2026, 1, 1), seed_fake=True
        )
    )


SUPPLIERS = [
    (
        "RMX",
        "Riyadh Readymix Concrete Co.",
        "شركة الرياض للخرسانة الجاهزة",
        ["material_supplier"],
        QSupplierStatus.approved,
        None,
    ),
    (
        "ARS",
        "Arabian Rebar & Steel Co.",
        "الشركة العربية لحديد التسليح",
        ["material_supplier"],
        QSupplierStatus.approved,
        None,
    ),
    (
        "GULFPIPE",
        "Gulf Pipes Industries",
        "مصانع الخليج للأنابيب",
        ["manufacturer"],
        QSupplierStatus.suspended,
        "2 HDPE rejections Q3 — test data",
    ),
    (
        "SAHEL",
        "Al-Sahel Waterproofing Est.",
        "مؤسسة الساحل للعزل المائي",
        ["material_supplier"],
        QSupplierStatus.approved,
        None,
    ),
    (
        "LAB-RGM",
        "Riyadh Geo-Materials Laboratory",
        "مختبر الرياض للمواد الجيوتقنية",
        ["testing_lab"],
        QSupplierStatus.approved,
        None,
    ),
    (
        "CAL-NMS",
        "Najd Metrology Services",
        "نجد لخدمات المعايرة",
        ["calibration_lab"],
        QSupplierStatus.approved,
        None,
    ),
    (
        "DNDT",
        "Desert NDT Services",
        "الصحراء لخدمات الفحص غير الإتلافي",
        ["ndt_provider"],
        QSupplierStatus.approved,
        None,
    ),
    (
        "COOLRD",
        "CoolRoad Transport Est.",
        "مؤسسة الطريق البارد للنقل",
        ["carrier"],
        QSupplierStatus.conditional,
        None,
    ),
    (
        "SHIELD",
        "Shield Pest Control",
        "شيلد لمكافحة الآفات",
        ["pest_control"],
        QSupplierStatus.approved,
        None,
    ),
    (
        "BRIGHT",
        "Bright Hygiene Services",
        "برايت لخدمات النظافة",
        ["cleaning"],
        QSupplierStatus.approved,
        None,
    ),
    ("NDCF", "Najd Dairy Factory", "مصنع نجد للألبان", ["shipper"], QSupplierStatus.approved, None),
]


def _suppliers(db: Session) -> dict[str, QSupplier]:
    out: dict[str, QSupplier] = {}
    for i, (code, en, ar, cats, status, why) in enumerate(SUPPLIERS, start=1):
        s = db.scalar(select(QSupplier).where(QSupplier.supplier_code == code))
        if s is None:
            s = QSupplier(
                supplier_code=code,
                legal_name_en=en,
                legal_name_ar=ar,
                legal_name_en_norm=normalize(en),
                legal_name_ar_norm=normalize(ar),
                country="SA",
                categories=cats,
                status=status,
                status_reason=why,
                status_changed_at=at(date(2026, 1, 15)),
                approved_scope="Logger data to be sent within 24 h" if code == "COOLRD" else None,
                contact_name=f"{code.title()} QA",
                contact_mobile=f"+9665000004{i:02d}",
                contact_email=f"{code.lower()}.qa@example.com",
                search_text=search_blob(code, en, ar),
                seed_fake=True,
            )
            db.add(s)
            db.flush()
        out[code] = s
    accs = [
        (
            "LAB-RGM",
            "TL-0451-TEST",
            ["CONC-CYL", "CONC-CUBE", "SLUMP", "PROCTOR", "FDT-SC", "CBR"],
            date(2027, 5, 31),
        ),
        (
            "CAL-NMS",
            "CL-0219-TEST",
            ["TEMP", "PRESSURE", "TORQUE", "DIMENSIONAL", "DFT"],
            date(2027, 8, 31),
        ),
    ]
    for code, number, scope, until in accs:
        if not db.scalar(
            select(QSupplierAccreditation.id).where(QSupplierAccreditation.number == number)
        ):
            db.add(
                QSupplierAccreditation(
                    supplier_id=out[code].id,
                    body=QAccreditationBody.sac,
                    standard=QAccreditationStandard.iso_iec_17025,
                    number=number,
                    scope_text=", ".join(scope),
                    scope_codes=scope,
                    valid_from=date(2024, 6, 1),
                    valid_until=until,
                    seed_fake=True,
                )
            )
    db.flush()
    return out


CRITERIA = [
    # code, title en, title ar, profile, kind, unit, min, max, target, -, +, rule, params, ref
    (
        "COVER-40",
        "Concrete cover 40 mm",
        "الغطاء الخرساني 40 مم",
        "construction",
        "target_tolerance",
        "mm",
        None,
        None,
        "40",
        "5",
        "5",
        None,
        {},
        "Project spec 03 30 00",
    ),
    (
        "FORM-TOL",
        "Formwork tolerance in 3 m",
        "تفاوت القوالب في 3 م",
        "construction",
        "max",
        "mm",
        None,
        "5",
        None,
        None,
        None,
        None,
        {},
        "Project spec 03 10 00",
    ),
    (
        "SLUMP-100",
        "Slump 100 mm (ASTM C94)",
        "الهبوط 100 مم",
        "construction",
        "rule",
        "mm",
        None,
        None,
        None,
        None,
        None,
        "slump_astm_c94",
        {"target": 100},
        "ASTM C94",
    ),
    (
        "CONC-TEMP-32",
        "Fresh concrete temperature",
        "حرارة الخرسانة الطازجة",
        "construction",
        "max",
        "°C",
        None,
        "32",
        None,
        None,
        None,
        None,
        {},
        "Project spec [VERIFY]",
    ),
    (
        "CURE-7D",
        "Curing 7 days",
        "المعالجة 7 أيام",
        "construction",
        "text",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        {},
        "ACI 308",
    ),
    (
        "STRIKE-70",
        "Strike at 70 % f'c",
        "فك القوالب عند 70 %",
        "construction",
        "min",
        "%",
        "70",
        None,
        None,
        None,
        None,
        None,
        {},
        "ACI 347",
    ),
    (
        "CONC-ACI-40",
        "Cylinder strength f'c 40 (ACI 318)",
        "مقاومة الأسطوانات 40",
        "construction",
        "rule",
        "MPa",
        None,
        None,
        None,
        None,
        None,
        "aci318_strength",
        {"fc": 40},
        "ACI 318 §26.12 [VERIFY]",
    ),
    (
        "CONC-ACI-32",
        "Cylinder strength f'c 32 (ACI 318)",
        "مقاومة الأسطوانات 32",
        "construction",
        "rule",
        "MPa",
        None,
        None,
        None,
        None,
        None,
        "aci318_strength",
        {"fc": 32},
        "ACI 318 §26.12 [VERIFY]",
    ),
    (
        "CONC-EN206-50",
        "Cube strength fck 50 (EN 206)",
        "مقاومة المكعبات 50",
        "construction",
        "rule",
        "MPa",
        None,
        None,
        None,
        None,
        None,
        "en206_strength",
        {"fck": 50},
        "BS EN 206",
    ),
    (
        "CORE-ACI-40",
        "Core strength (ACI 318)",
        "مقاومة القلب الخرساني",
        "construction",
        "rule",
        "MPa",
        None,
        None,
        None,
        None,
        None,
        "aci318_cores",
        {"fc": 40},
        "ACI 318 §26.12.6",
    ),
    (
        "COMP-95",
        "Compaction ≥ 95 %",
        "الدمك ≥ 95 %",
        "construction",
        "min",
        "%",
        "95.0",
        None,
        None,
        None,
        None,
        None,
        {},
        "ASTM D1557",
    ),
    (
        "COMP-98",
        "Compaction ≥ 98 %",
        "الدمك ≥ 98 %",
        "construction",
        "min",
        "%",
        "98.0",
        None,
        None,
        None,
        None,
        None,
        {},
        "ASTM D1557",
    ),
    (
        "DFT-125-200",
        "Coating DFT 125–200 µm (SSPC-PA 2)",
        "سماكة الطلاء",
        "construction",
        "rule",
        "µm",
        "125",
        "200",
        None,
        None,
        None,
        "sspc_pa2",
        {"min": 125, "max": 200},
        "SSPC-PA 2",
    ),
    (
        "HYDRO-1.5",
        "Hydrotest 1.5 × design, 10 min",
        "اختبار الضغط",
        "construction",
        "rule",
        "bar",
        None,
        None,
        None,
        None,
        None,
        "pressure_hold",
        {"factor": 1.5, "hold_min": 10},
        "ASME B31.3 [VERIFY]",
    ),
    (
        "TORQUE-M20",
        "Bolt torque M20",
        "عزم ربط البراغي M20",
        "construction",
        "target_tolerance",
        "N·m",
        None,
        None,
        "400",
        "20",
        "20",
        None,
        {},
        "Illustrative",
    ),
    (
        "ARR-FROZEN",
        "Arrival temperature, frozen",
        "حرارة الوصول — مجمد",
        "logistics",
        "rule",
        "°C",
        None,
        None,
        None,
        None,
        None,
        "arrival_temperature",
        {"class": "frozen"},
        "Q-RCV-01",
    ),
    (
        "ARR-CHILLED",
        "Arrival temperature, chilled",
        "حرارة الوصول — مبرد",
        "logistics",
        "rule",
        "°C",
        None,
        None,
        None,
        None,
        None,
        "arrival_temperature",
        {"class": "chilled"},
        "Q-RCV-01",
    ),
    (
        "ARR-PHARMA",
        "Arrival temperature, 2–8 °C",
        "حرارة الوصول — أدوية",
        "logistics",
        "rule",
        "°C",
        None,
        None,
        None,
        None,
        None,
        "arrival_temperature",
        {"class": "pharma_2_8"},
        "Q-RCV-01",
    ),
    (
        "RSL-60",
        "Remaining shelf life ≥ 60 %",
        "الصلاحية المتبقية ≥ 60 %",
        "logistics",
        "rule",
        "%",
        None,
        None,
        None,
        None,
        None,
        "remaining_shelf_life",
        {"min_pct": 60},
        "Customer SLA",
    ),
    (
        "PRECOOL-FRZ",
        "Pre-cooling ≤ setpoint + 2 °C",
        "التبريد المسبق",
        "logistics",
        "rule",
        "°C",
        None,
        None,
        None,
        None,
        None,
        "precool_setpoint",
        {"margin": 2.0},
        "Q-TRN-02",
    ),
]


def _criteria(db: Session, w: _W) -> None:
    for code, en, ar, prof, kind, unit, lo, hi, tgt, tm, tp, rule, params, ref in CRITERIA:
        if db.scalar(select(QCriterion.id).where(QCriterion.code == code)):
            continue
        db.add(
            QCriterion(
                code=code,
                version=1,
                title_en=en,
                title_ar=ar,
                profile=QProfileScope(prof),
                kind=QCriterionKind(kind),
                unit=unit,
                min_value=D(lo) if lo else None,
                max_value=D(hi) if hi else None,
                target=D(tgt) if tgt else None,
                tol_minus=D(tm) if tm else None,
                tol_plus=D(tp) if tp else None,
                rule_code=rule,
                params=params,
                reference=ref,
                status=QCriterionStatus.published,
                published_at=at(date(2026, 4, 1)),
                published_by_user_id=w.u("faisal.harbi"),
                created_by_user_id=w.u("faisal.harbi"),
                seed_fake=True,
            )
        )
    db.flush()


def _mte(db: Session, p: Project, w: _W, rows: list[tuple[int, QMteType, str, str, Any]]) -> None:
    from app.services.quality import numbering  # noqa: PLC0415

    top = 0
    for no, typ, desc, site, (kind, interval, status, due, last) in rows:
        db.add(
            QMteItem(
                project_id=p.id,
                mte_no=f"MTE-{no:04d}",
                mte_type=typ,
                description=desc,
                manufacturer="Generic",
                model=typ.value,
                serial_no=f"{p.code}-SN-{no:05d}",
                site_id=w.site(p, site),
                check_kind=kind,
                interval_months=interval,
                cal_status=status,
                cal_due_on=due,
                cal_status_reason=f"Last calibrated {last.isoformat()}" if last else None,
                created_by_user_id=w.u("faisal.harbi"),
                seed_fake=True,
            )
        )
        top = max(top, int(no))
    db.flush()
    numbering.bump_to(db, p, QRecordType.mte, 2026, top)


def _ania_mte(db: Session, p: Project, w: _W) -> None:
    cal = QMteCheckKind.calibration
    ok = QCalStatus.calibrated
    named: dict[int, tuple[QMteType, str, Any]] = {
        7: (
            QMteType.slump_cone,
            "Slump cone",
            (QMteCheckKind.verification, 1, ok, date(2026, 10, 31), date(2026, 10, 1)),
        ),
        12: (
            QMteType.thermometer,
            "Concrete thermometer",
            (cal, 12, ok, date(2027, 2, 14), date(2026, 2, 15)),
        ),
        15: (
            QMteType.dft_gauge,
            "DFT gauge",
            (cal, 12, QCalStatus.overdue, date(2026, 9, 30), date(2025, 10, 1)),
        ),
        21: (
            QMteType.torque_wrench,
            "Torque wrench 100–600 N·m",
            (cal, 12, ok, date(2027, 3, 31), date(2026, 4, 1)),
        ),
        30: (
            QMteType.total_station,
            "Total station",
            (cal, 12, ok, date(2027, 1, 31), date(2026, 2, 1)),
        ),
        31: (
            QMteType.nuclear_density_gauge,
            "Nuclear density gauge (NRRC licence [VERIFY])",
            (cal, 12, ok, date(2027, 5, 31), date(2026, 6, 1)),
        ),
        40: (
            QMteType.pressure_gauge,
            "Pressure gauge 0–40 bar",
            (cal, 6, QCalStatus.overdue, date(2026, 9, 15), date(2026, 3, 16)),
        ),
        44: (
            QMteType.caliper_micrometer,
            "Digital caliper",
            (cal, 12, QCalStatus.overdue, date(2026, 9, 20), date(2025, 9, 21)),
        ),
    }
    rows = []
    for no in range(1, 49):
        if no in named:
            typ, desc, spec = named[no]
        else:
            typ, desc = QMteType.tape_rule, f"Measuring tape {no}"
            spec = (cal, 12, ok, date(2027, 1, 1) + timedelta(days=no * 3), date(2026, 1, 2))
        rows.append((no, typ, desc, "S-LAND" if no % 2 else "S-AIR", spec))
    _mte(db, p, w, rows)


def _ruh_mte(db: Session, p: Project, w: _W) -> None:
    cal = QMteCheckKind.calibration
    ok = QCalStatus.calibrated
    rows: list[tuple[int, QMteType, str, str, Any]] = [
        (
            42,
            QMteType.temp_probe,
            "Receiving probe thermometer",
            "S-DC1",
            (cal, 6, ok, date(2027, 3, 9), date(2026, 9, 10)),
        ),
        (
            51,
            QMteType.temp_probe,
            "Dispatch probe thermometer",
            "S-DC1",
            (cal, 6, ok, date(2027, 2, 28), date(2026, 9, 1)),
        ),
    ]
    for no in range(101, 123):
        rows.append(
            (
                no,
                QMteType.temp_logger,
                f"Temperature logger {no}",
                "S-DC1",
                (cal, 12, ok, date(2027, 2, 28), date(2026, 3, 1)),
            )
        )
    _mte(db, p, w, rows)


# ---- NCRs ---------------------------------------------------------------------------------------

M, CR, MI = QNcrClass.major, QNcrClass.critical, QNcrClass.minor
WK, MAT, DOC, DIM = (
    QNcrCategory.workmanship,
    QNcrCategory.material,
    QNcrCategory.design_documentation,
    QNcrCategory.dimensional,
)
TST, OTH = QNcrCategory.testing_failure, QNcrCategory.other
ST = QNcrStatus


def _ncr_rows_ania() -> list[dict[str, Any]]:
    """Appendix A.4: 44 NCRs in 2026; September 14 opened (9 / 4 / 1; QX25), 10 closed (median 12
    days), 10 with target in September (8 on time), 11 open at 09-30 (8 / 2 / 1 / 0), costs QX26
    (gross 186,450.00, internal 171,200.00, external 15,250.00, recovered 22,600.00)."""
    rows: list[dict[str, Any]] = []
    cats = [WK, MAT, DIM, DOC, WK, TST, WK, MAT, OTH]
    for i in range(1, 19):  # January – June, closed within the month
        o = date(2026, 1, 8) + timedelta(days=(i - 1) * 9)
        rows.append(
            {
                "o": o,
                "cls": MI if i % 3 else M,
                "cat": cats[i % len(cats)],
                "closed": o + timedelta(days=9 + i % 7),
                "costs": [("rework_labour", "10", None)],
            }
        )
    rows.append(
        {
            "o": date(2026, 7, 2),
            "cls": M,
            "cat": MAT,
            "supplier": "RMX",
            "item_key": "TT:CONC-CYL",
            "status": ST.disposition_approved,
            "title": "7-day cylinders of pour POUR-ANIA-EXP-2026-0041 below the trend",
            "costs": [("retest_reinspection", "2", "350.00")],
        }
    )
    rows.append(
        {
            "o": date(2026, 7, 15),
            "cls": MI,
            "cat": WK,
            "closed": date(2026, 7, 30),
            "costs": [("rework_labour", "6", None)],
        }
    )
    aug = [
        (date(2026, 8, 3), MI, WK, date(2026, 8, 12)),
        (date(2026, 8, 5), MI, DIM, date(2026, 8, 20)),
        (date(2026, 8, 10), M, WK, None),  # QX3: still open (age 57 at 10-06)
        (date(2026, 8, 11), MI, DOC, date(2026, 8, 25)),
        (date(2026, 8, 12), MI, WK, date(2026, 9, 11)),  # 30 days, on its target
        (date(2026, 8, 14), MI, MAT, date(2026, 8, 28)),
        (date(2026, 8, 20), MI, WK, None),
        (date(2026, 8, 22), MI, DIM, date(2026, 9, 1)),
        (date(2026, 8, 24), M, WK, date(2026, 9, 5)),
        (date(2026, 8, 26), MI, DOC, date(2026, 9, 9)),
    ]
    for o, cls, cat, closed in aug:
        r: dict[str, Any] = {
            "o": o,
            "cls": cls,
            "cat": cat,
            "closed": closed,
            "costs": [("rework_labour", "8", None)],
        }
        if closed is None:
            r["status"] = ST.disposition_proposed if o.day == 10 else ST.open
        rows.append(r)
    lab = "rework_labour"
    sept = [
        (1, MI, WK, date(2026, 9, 10), [(lab, "30", None)]),
        (2, MI, WK, date(2026, 9, 14), [(lab, "50", None)]),
        (3, MI, DOC, date(2026, 9, 16), [(lab, "40", None)]),
        (4, MI, DIM, date(2026, 9, 15), [(lab, "60", None)]),
        (
            7,
            M,
            WK,
            date(2026, 9, 25),
            [(lab, "80", None), ("plant", "24", None), ("material", "1", "9200.00")],
        ),
        (8, MI, OTH, date(2026, 9, 20), [(lab, "34", None)]),
        (10, MI, WK, None, [(lab, "80", None)]),
        (14, MI, MAT, None, [("material", "1", "3525.00")]),
        (16, M, DOC, None, [("delay", "5", None), (lab, "120", None)]),
        (18, MI, WK, None, [(lab, "50", None)]),
        (20, M, MAT, None, None),  # NCR-0041 (QTN-0009, GULFPIPE)
        (22, MI, TST, None, [("retest_reinspection", "2", "350.00"), (lab, "25", None)]),
        (24, M, WK, None, None),  # NCR-0043 (complaint CCM-0002, external)
        (29, CR, MAT, None, None),  # NCR-0044 (TST-00388, QX1)
    ]
    status = {
        10: ST.open,
        14: ST.open,
        16: ST.disposition_proposed,
        18: ST.open,
        20: ST.disposition_approved,
        22: ST.pending_verification,
        24: ST.open,
        29: ST.disposition_approved,
    }
    for day, cls, cat, closed, costs in sept:
        rows.append(
            {
                "o": date(2026, 9, day),
                "cls": cls,
                "cat": cat,
                "closed": closed,
                "costs": costs,
                "status": status.get(day),
            }
        )
    return rows


def _ncr_rows_ruh() -> list[dict[str, Any]]:
    """Appendix A.6: 36 NCRs in 2026, 9 opened in September (6 minor, 3 major; the three majors
    are the receiving rejection NCR-0031, the Z-FRZ1 excursion NCR-0034 and the transit excursion
    NCR-0036)."""
    rows: list[dict[str, Any]] = []
    cats = [
        QNcrCategory.temperature,
        QNcrCategory.labelling,
        QNcrCategory.damage,
        QNcrCategory.expiry_shelf_life,
        QNcrCategory.contamination_hygiene,
        QNcrCategory.quantity,
        QNcrCategory.packaging,
    ]
    for i in range(1, 28):
        o = date(2026, 1, 10) + timedelta(days=(i - 1) * 8)
        closed = o + timedelta(days=8 + i % 9) if o < date(2026, 8, 10) else None
        rows.append(
            {
                "o": o,
                "cls": MI if i % 4 else M,
                "cat": cats[i % len(cats)],
                "closed": closed,
                "status": None if closed else ST.open,
                "costs": [("rework_labour", "4", None)],
            }
        )
    sept = [
        (3, MI, QNcrCategory.labelling, None),
        (8, MI, QNcrCategory.damage, None),
        (15, MI, QNcrCategory.packaging, None),
        (21, M, QNcrCategory.temperature, ("receipt", "RCV-RUH-CCH-2026-01902")),
        (22, MI, QNcrCategory.expiry_shelf_life, None),
        (24, MI, QNcrCategory.damage, None),
        (22, M, QNcrCategory.temperature, ("excursion", "EXC-RUH-CCH-2026-0041")),
        (25, MI, QNcrCategory.contamination_hygiene, None),
        (26, M, QNcrCategory.temperature, ("trip", "TRP-RUH-CCH-2026-00921")),
    ]
    for day, cls, cat, src in sept:
        rows.append(
            {
                "o": date(2026, 9, day),
                "cls": cls,
                "cat": cat,
                "closed": None,
                "status": ST.open,
                "src": src,
                "costs": None,
            }
        )
    return rows


def _cost(
    db: Session,
    n: QNcr,
    ct: str,
    qty: str,
    rate: str | None,
    user: uuid.UUID,
    rates: dict[str, str],
    recovered: str = "0",
    ext: bool = False,
) -> None:
    cost_type = QCostType(ct)
    key = {
        "rework_labour": "labour",
        "repair_labour": "labour",
        "plant": "plant",
        "delay": "delay",
    }.get(ct)
    r = D(rate) if rate else D(rates[key]) if key else D("0")
    amount = (D(qty) * r).quantize(D("0.01"))
    db.add(
        QNcrCost(
            ncr_id=n.id,
            cost_type=cost_type,
            quantity=D(qty),
            rate_sar=r,
            amount_sar=amount,
            recoverable=D(recovered) > 0,
            recovered_sar=D(recovered),
            entered_by_user_id=user,
            entered_at=(n.opened_at or at(n.opened_date or date(2026, 1, 1))) + timedelta(days=2),
            unit={"rework_labour": "h", "plant": "h", "delay": "day"}.get(ct, "lot"),
            created_by_user_id=user,
            seed_fake=True,
        )
    )
    _ = ext


def _signoff(
    db: Session,
    n: QNcr,
    step: str,
    who: uuid.UUID,
    capacity: str,
    when: datetime,
    decision: str = "approved",
) -> None:
    db.add(
        QSignoff(
            project_id=n.project_id,
            record_type="ncr",
            record_id=n.id,
            step=step,
            decision=decision,
            signed_by_user_id=who,
            signed_at=when,
            signer_capacity=capacity,
            channel=QSignoffChannel.in_app,
            seed_fake=True,
        )
    )


def _ca(
    db: Session,
    p: Project,
    n: QNcr,
    title: str,
    owner: uuid.UUID,
    verifier: uuid.UUID,
    created: date,
    status: CaStatus,
) -> CorrectiveAction:
    from app.services.hse_common import make_ref, next_seq  # noqa: PLC0415

    seq = next_seq(db, CorrectiveAction, p.id, created.year)
    prio = {CR: CaPriority.critical, M: CaPriority.high}.get(
        n.classification or MI, CaPriority.medium
    )
    days = {CaPriority.critical: 14, CaPriority.high: 30}.get(prio, 45)
    assert n.responsible_engagement_id is not None  # noqa: S101
    ca = CorrectiveAction(
        project_id=p.id,
        ref=make_ref("CA", p.code, created.year, seq, 5),
        year=created.year,
        seq=seq,
        source_type=CaSourceType.quality_ncr,
        source_id=n.id,
        site_id=n.site_id,
        zone_id=n.zone_id,
        responsible_engagement_id=n.responsible_engagement_id,
        title=title,
        description=title,
        control_level=ControlLevel.administrative,
        priority=prio,
        owner_id=owner,
        verifier_id=verifier,
        created_date=created,
        due_date=created + timedelta(days=days),
        original_due_date=created + timedelta(days=days),
        status=status,
        created_by_user_id=verifier,
        alerts_sent=[],
    )
    if status == CaStatus.closed:
        ca.completed_date = created + timedelta(days=5)
        ca.verified_date = created + timedelta(days=7)
        ca.evidence_text = "Procedure revised and toolbox briefing held; records attached."
    db.add(ca)
    db.flush()
    return ca


def _ncrs(
    db: Session,
    w: _W,
    p: Project,
    rows: list[dict[str, Any]],
    prof: QSectorProfile,
    cfg: dict[str, Any],
) -> dict[int, QNcr]:
    from app.services.quality import numbering  # noqa: PLC0415

    out: dict[int, QNcr] = {}
    rates = {"labour": "85.00", "plant": "250.00", "delay": "12000.00"}
    for i, r in enumerate(rows, start=1):
        o: date = r["o"]
        opened = at(o, 9 + i % 6, (i * 7) % 60)
        cls: QNcrClass = r["cls"]
        days = {CR: 21, M: 30, MI: 30}[cls]
        hours = {CR: 24, M: 72, MI: 168}[cls]
        closed: date | None = r.get("closed")
        status = r.get("status") or (ST.closed if closed else ST.open)
        owner = cfg["owners"][i % len(cfg["owners"])]
        raiser = cfg["raisers"][i % len(cfg["raisers"])]
        eng = cfg["engs"][i % len(cfg["engs"])]
        sup = r.get("supplier")
        stage = (
            QDetectionStage.in_process
            if prof == QSectorProfile.construction
            else (QDetectionStage.receiving if i % 2 else QDetectionStage.storage)
        )
        n = QNcr(
            project_id=p.id,
            ncr_no=f"NCR-{p.code}-2026-{i:04d}",
            profile=prof,
            source_type=QNcrSourceType.manual,
            site_id=w.site(p, cfg["sites"][i % len(cfg["sites"])]),
            title=r.get("title")
            or f"{r['cat'].value.replace('_', ' ').capitalize()} nonconformity {i:02d}",
            requirement_en="Requirement of the approved drawing / specification / procedure.",
            finding_en="Condition found during inspection does not meet the requirement.",
            category=r["cat"],
            detection_stage=stage,
            classification=cls,
            responsible_engagement_id=eng,
            supplier_id=cfg["suppliers"].get(sup) if sup else None,
            item_key=r.get("item_key"),
            raised_by_user_id=raiser,
            opened_at=opened,
            opened_date=o,
            owner_id=owner,
            target_close_date=o + timedelta(days=days),
            containment_due_at=opened + timedelta(hours=hours),
            status=status,
            status_changed_at=opened,
            alerts_sent=[],
            lot_refs=[],
            created_by_user_id=raiser,
            seed_fake=True,
        )
        if r.get("src"):
            n.source_type = QNcrSourceType(r["src"][0])
            n.source_ref = r["src"][1]
        if cls != MI or status != ST.open:
            n.containment_en = "Affected work / product segregated, tagged and held."
            n.containment_done_at = opened + timedelta(hours=min(hours, 12))
            n.containment_by_user_id = owner
        if status not in (ST.open,):
            n.cause_category = QCauseCategory.method
            n.disposition_proposed_at = opened + timedelta(days=2)
            n.disposition_proposed_by_user_id = owner
        if status in (ST.disposition_approved, ST.pending_verification, ST.closed):
            n.disposition_approved_at = opened + timedelta(days=3)
        if status in (ST.pending_verification, ST.closed):
            n.implementation_note = "Disposition carried out and recorded with photos."
            n.implemented_at = opened + timedelta(days=4)
            n.implemented_by_user_id = owner
        if closed is not None:
            n.closed_at = at(closed, 15)
            n.closed_date = closed
            n.effectiveness = {"due_on": (closed + timedelta(days=90)).isoformat()}
        db.add(n)
        db.flush()
        if status != ST.open:
            db.add(
                QNcrRca(
                    ncr_id=n.id,
                    method=QRcaMethod.five_why if cls != MI else QRcaMethod.simple,
                    data={
                        "cause": "Method statement step not briefed to the crew before "
                        "the work started."
                    }
                    if cls == MI
                    else {
                        "whys": [
                            "The crew did not follow the step.",
                            "The step was not in the briefing pack.",
                            "The method statement revision was not issued to site.",
                        ],
                        "root_cause": "Document control did not reach the work front.",
                    },
                    root_cause="Document control did not reach the work front.",
                    cause_category=QCauseCategory.method,
                    complete=True,
                    seed_fake=True,
                )
            )
            db.add(
                QNcrLine(
                    ncr_id=n.id,
                    disposition=QDisposition.rework,
                    position=0,
                    note="Rework to the drawing.",
                    seed_fake=True,
                )
            )
        mgr = cfg["manager"]
        if n.disposition_approved_at is not None:
            _signoff(db, n, "disposition", mgr, "role:qa_qc_manager", n.disposition_approved_at)
        if closed is not None:
            _signoff(db, n, "close", mgr, "role:qa_qc_manager", at(closed, 15))
        for ct, qty, rate in r.get("costs") or []:
            _cost(db, n, ct, qty, rate, owner, rates)
        if cls != MI:
            _ca(
                db,
                p,
                n,
                f"Remove the cause of {n.ncr_no}",
                owner,
                mgr,
                o + timedelta(days=2),
                CaStatus.closed if closed else CaStatus.in_progress,
            )
        out[i] = n
    db.flush()
    numbering.bump_to(db, p, QRecordType.ncr, 2026, len(rows))
    return out


def _recost(db: Session, n: QNcr) -> None:
    from app.services.quality.ncr import costs  # noqa: PLC0415

    costs.recompute(db, n)


def _ania_named(
    db: Session, w: _W, p: Project, ncrs: dict[int, QNcr], sup: dict[str, QSupplier]
) -> None:
    hatem, bilal, joseph, abdullah = (
        w.u("hatem.shehri"),
        w.u("bilal.qureshi"),
        w.u("joseph.mathew.qc"),
        w.u("abdullah.dossary"),
    )
    rates = {"labour": "85.00", "plant": "250.00", "delay": "12000.00"}
    rawabi = w.eng(p, "RAWABI")
    # NCR-0041: MIR-ANIA-EXP-2026-0112 HDPE pipes (GULFPIPE), 60 m rejected → QTN-0009
    n41 = ncrs[41]
    n41.title = "HDPE pipes rejected on delivery (ovality, damaged ends) — MIR-ANIA-EXP-2026-0112"
    n41.source_type = QNcrSourceType.mir
    n41.source_ref = "MIR-ANIA-EXP-2026-0112"
    n41.detection_stage = QDetectionStage.receiving
    n41.supplier_id = sup["GULFPIPE"].id
    n41.item_key = "MAT:HDPE-PIPE"
    n41.quantity, n41.unit = D("60"), "m"
    n41.responsible_engagement_id = rawabi
    n41.finding_en = "60 m of 240 m delivered show ovality beyond tolerance and damaged ends."
    db.execute(sa_delete(QNcrLine).where(QNcrLine.ncr_id == n41.id))
    db.add(
        QNcrLine(
            ncr_id=n41.id,
            disposition=QDisposition.reject_return,
            quantity=D("60"),
            note="Return to GULFPIPE; return note pending.",
            position=0,
            seed_fake=True,
        )
    )
    for ct, qty, rate, rec in (
        ("material", "1", "18350.00", "18350.00"),
        ("transport_return", "1", "1650.00", "0"),
        ("rework_labour", "40", None, "0"),
    ):
        _cost(db, n41, ct, qty, rate, bilal, rates, rec)
    n41.supplier_response = {
        "requested_at": at(date(2026, 9, 21)).isoformat(),
        "due_on": "2026-10-05",
        "received_at": None,
        "accepted": None,
        "note": "8D requested for HDPE ovality",
    }
    # NCR-0043: complaint CCM-ANIA-EXP-2026-0002 water ponding at stand 23 (external failure)
    n43 = ncrs[43]
    n43.title = "Water ponding at stand 23 after rain — apron falls not to drawing"
    n43.source_type = QNcrSourceType.complaint
    n43.detection_stage = QDetectionStage.at_customer
    n43.responsible_engagement_id = w.eng(p, "GULFPAVE")
    n43.zone_id = w.zone(p, "Z-APR-21")
    n43.site_id = w.site(p, "S-AIR")
    for ct, qty, rate in (
        ("rework_labour", "50", None),
        ("material", "1", "6000.00"),
        ("plant", "20", None),
    ):
        _cost(db, n43, ct, qty, rate, n43.owner_id or bilal, rates)
    # NCR-0044 (critical, Bilal, 8D, use_as_is approved with concession by Abdullah, QX1 costs)
    n = ncrs[44]
    opened = at(date(2026, 9, 29), 11, 20)
    n.title = "28-day cylinder strength below acceptance, pour POUR-ANIA-EXP-2026-0077"
    n.source_type = QNcrSourceType.test_result
    n.source_ref = "TST-ANIA-EXP-2026-00388"
    n.requirement_en = "f'c 40 MPa; ACI 318 §26.12.3.1 [VERIFY]"
    n.finding_en = "Set 3 average 33.2 MPa < 36.0 MPa (f'c − 4.0)."
    n.site_id = w.site(p, "S-LAND")
    n.location_ref = "Level 3 slab, grid C14–C20"
    n.responsible_engagement_id = rawabi
    n.supplier_id = sup["RMX"].id
    n.item_key = "TT:CONC-CYL"
    n.quantity, n.unit, n.lot_refs = D("186"), "m3", ["mix C40-B12"]
    n.raised_by_user_id = bilal
    n.owner_id = bilal
    n.opened_at = opened
    n.opened_date = date(2026, 9, 29)
    n.target_close_date = date(2026, 10, 20)
    n.containment_due_at = opened + timedelta(hours=24)
    n.containment_en = "Slab load restricted, props kept, cores ordered."
    n.containment_done_at = opened + timedelta(hours=3)
    n.containment_by_user_id = bilal
    n.cause_category = QCauseCategory.material
    n.repeat_of_id = ncrs[19].id
    n.disposition_justification_en = (
        "Cores avg 34.9 MPa ≥ 0.85 f'c (34.0), min 33.6 ≥ 0.75 f'c (30.0); structural engineer "
        "confirms capacity (TST-ANIA-EXP-2026-00431, QX6)."
    )
    n.disposition_proposed_at = opened + timedelta(days=4)
    n.disposition_proposed_by_user_id = bilal
    n.disposition_approved_at = opened + timedelta(days=5)
    n.status = ST.disposition_approved
    n.status_changed_at = n.disposition_approved_at
    db.execute(sa_delete(QNcrRca).where(QNcrRca.ncr_id == n.id))
    db.execute(sa_delete(QNcrLine).where(QNcrLine.ncr_id == n.id))
    db.execute(sa_delete(QSignoff).where(QSignoff.record_id == n.id))
    db.add(
        QNcrRca(
            ncr_id=n.id,
            method=QRcaMethod.eight_d,
            cause_category=QCauseCategory.material,
            root_cause="Uncontrolled water addition at the batching plant for mix C40-B12.",
            complete=True,
            seed_fake=True,
            data={
                "d1_team": [str(bilal), str(joseph), str(hatem)],
                "d2_problem": {
                    "what": "Low 28-day cylinder strength",
                    "where": "Pier B L3",
                    "when": "Pour 2026-09-01",
                    "how_many": "Set 3 of 4",
                    "is_not": "Sets 1, 2 and 4 conform",
                },
                "d3_containment": "Load restriction, props kept, cores taken.",
                "d4_root_cause": "Water added at the plant beyond the mix design.",
                "d4_escape_point": "Plant slump control not checked against the ticket.",
                "d6_implemented_on": "2026-10-10",
                "d6_validated_on": "2026-11-15",
                "d7_prevention": "Plant water meter interlock and ticket check in ITP.",
                "d8_closure": "Team recognised; lessons shared with RMX.",
            },
        )
    )
    db.add(
        QNcrLine(
            ncr_id=n.id,
            disposition=QDisposition.use_as_is,
            quantity=D("186"),
            note="Accepted on cores (QX6).",
            position=0,
            seed_fake=True,
        )
    )
    _signoff(db, n, "disposition", hatem, "role:qa_qc_manager", n.disposition_approved_at)
    _signoff(db, n, "concession", abdullah, "position:CONSULTANT_RE", n.disposition_approved_at)
    for ct, qty, rate, rec in (
        ("rework_labour", "36", None, "0"),
        ("material", "1", "4250.00", "4250.00"),
        ("retest_reinspection", "2", "350.00", "0"),
        ("delay", "1", None, "0"),
    ):
        _cost(db, n, ct, qty, rate, bilal, rates, rec)
    db.flush()
    db.execute(
        sa_update(CorrectiveAction)
        .where(CorrectiveAction.source_id == n.id)
        .values(
            title="Tighten water addition control at the batching plant",
            owner_id=joseph,
            verifier_id=hatem,
        )
    )
    for x in ncrs.values():
        _recost(db, x)
    db.add(
        QLink(
            project_id=p.id,
            from_type="ncr",
            from_id=n.id,
            to_type="ncr",
            to_id=ncrs[19].id,
            kind=QLinkKind.relates,
            created_at=opened,
            seed_fake=True,
        )
    )
    db.flush()


def _registers_ania(db: Session, w: _W, p: Project) -> None:
    db.add(
        QCustomer(
            project_id=p.id,
            code="ANC",
            name_en="Al-Noor Airport Company",
            name_ar="شركة مطار النور",
            kind=QCustomerKind.client,
            contact_name="ANC Quality",
            contact_mobile="+966500000420",
            contact_email="anc.qa@example.com",
            seed_fake=True,
        )
    )
    for code, en, ar, disc, zone in (
        ("SYS-T3-HVAC", "Terminal 3 HVAC", "تكييف الصالة 3", QDiscipline.HVC, None),
        (
            "SYS-T3-FPS",
            "Terminal 3 fire protection",
            "الحماية من الحريق للصالة 3",
            QDiscipline.FPS,
            None,
        ),
        ("SYS-APR-DRN", "Apron drainage", "تصريف الساحات", QDiscipline.PLB, "Z-APR-21"),
    ):
        db.add(
            QSystem(
                project_id=p.id,
                code=code,
                name_en=en,
                name_ar=ar,
                discipline=disc,
                zone_ids=[w.zone(p, zone)] if zone else [],
                seed_fake=True,
            )
        )
    db.flush()


def _registers_ruh(db: Session, w: _W, p: Project) -> dict[str, QCustomer]:
    out = {}
    for code, en, ar, flag in (
        ("NDC", "Najd Dairy Co.", "شركة نجد للألبان", False),
        ("GFF", "Gulf Frozen Foods Co.", "شركة الخليج للأغذية المجمدة", True),
        ("SAHM", "Sahm Pharma Distribution", "سهم لتوزيع الأدوية", True),
    ):
        c = QCustomer(
            project_id=p.id,
            code=code,
            name_en=en,
            name_ar=ar,
            kind=QCustomerKind.depositor,
            owner_release_approval=flag,
            contact_name=f"{code} Quality",
            contact_email=f"{code.lower()}.qa@example.com",
            contact_mobile="+966500000430",
            seed_fake=True,
        )
        db.add(c)
        out[code] = c
    db.flush()
    return out


def _alert_obs_complaints_ania(db: Session, w: _W, p: Project, ncrs: dict[int, QNcr]) -> None:
    from app.services.quality import numbering  # noqa: PLC0415

    hatem = w.u("hatem.shehri")
    joseph, mazen, arun = w.u("joseph.mathew.qc"), w.u("mazen.harbi"), w.u("arun.pillai")
    s_land = w.site(p, "S-LAND")
    for i in (1, 2):
        db.add(
            QAlert(
                project_id=p.id,
                alert_no=f"QAL-{p.code}-2026-{i:04d}",
                title_en=f"Quality alert {i}",
                title_ar=f"تنبيه جودة {i}",
                message_en="Check delivery tickets against the approved mix.",
                message_ar="تحقق من تذاكر التوريد مقابل الخلطة المعتمدة.",
                severity=QAlertSeverity.warning,
                valid_until=date(2026, 6, 30),
                status=QAlertStatus.expired,
                issued_at=at(date(2026, 3 * i, 1)),
                issued_by_user_id=hatem,
                created_by_user_id=hatem,
                recipients=[],
                alerts_sent=[],
                seed_fake=True,
            )
        )
    a = QAlert(
        project_id=p.id,
        alert_no=f"QAL-{p.code}-2026-0003",
        title_en="Rebar heat H71203 — do not use pending certificate",
        title_ar="حديد التسليح بالصبّة H71203 — لا يُستخدم حتى ورود الشهادة",
        message_en="Rebar of heat H71203 is held until the mill certificate matches. Do not fix.",
        message_ar="حديد الصبّة H71203 محجوز حتى مطابقة شهادة المصنع. لا يُركّب.",
        severity=QAlertSeverity.stop_use,
        applies_to="Heat H71203 (ARS)",
        site_ids=[s_land],
        lot_refs=["H71203"],
        valid_until=date(2026, 10, 31),
        dist_roles=["qc_inspector"],
        ack_required=True,
        status=QAlertStatus.issued,
        issued_at=at(date(2026, 9, 10), 8),
        issued_by_user_id=hatem,
        recipients=[joseph, mazen, arun],
        created_by_user_id=hatem,
        alerts_sent=[],
        seed_fake=True,
    )
    db.add(a)
    db.flush()
    db.add(
        QAlertAck(alert_id=a.id, user_id=mazen, acked_at=at(date(2026, 9, 10), 10), seed_fake=True)
    )
    numbering.bump_to(db, p, QRecordType.quality_alert, 2026, 3)
    for i, (day, cat, site) in enumerate(
        (
            (2, WK, "S-LAND"),
            (6, MAT, "S-LAND"),
            (11, DIM, "S-AIR"),
            (17, WK, "S-AIR"),
            (23, DOC, "S-LAND"),
            (28, WK, "S-LAND"),
        ),
        start=1,
    ):
        db.add(
            QObservation(
                project_id=p.id,
                obs_no=f"QOB-{p.code}-2026-{i:04d}",
                site_id=w.site(p, site),
                engagement_id=w.eng(p, "RAWABI"),
                category=cat,
                description="Housekeeping of stored material may damage it before installation.",
                raised_by_user_id=joseph if i % 2 else mazen,
                raised_at=at(date(2026, 9, day)),
                raised_date=date(2026, 9, day),
                status=QObservationStatus.closed if i < 4 else QObservationStatus.open,
                closed_at=at(date(2026, 9, day + 2)) if i < 4 else None,
                created_by_user_id=joseph,
                seed_fake=True,
            )
        )
    numbering.bump_to(db, p, QRecordType.observation, 2026, 6)
    anc = db.scalar(select(QCustomer).where(QCustomer.project_id == p.id, QCustomer.code == "ANC"))
    assert anc is not None  # noqa: S101
    db.add(
        QComplaint(
            project_id=p.id,
            complaint_no=f"CCM-{p.code}-2026-0001",
            customer_id=anc.id,
            received_at=at(date(2026, 5, 12)),
            channel=QComplaintChannel.email,
            category=QNcrCategory.workmanship,
            description="Joint sealant gaps at gate 4.",
            severity=QComplaintSeverity.low,
            acknowledged_at=at(date(2026, 5, 12), 14),
            justified=QJustified.no,
            response_en="Inspected: within tolerance.",
            responded_at=at(date(2026, 5, 18)),
            status=QComplaintStatus.closed,
            closed_at=at(date(2026, 6, 2)),
            alerts_sent=[],
            created_by_user_id=hatem,
            seed_fake=True,
        )
    )
    c = QComplaint(
        project_id=p.id,
        complaint_no=f"CCM-{p.code}-2026-0002",
        customer_id=anc.id,
        site_id=w.site(p, "S-AIR"),
        received_at=at(date(2026, 9, 24), 8),
        channel=QComplaintChannel.letter,
        category=QNcrCategory.workmanship,
        description="Water ponding at stand 23 after rain.",
        severity=QComplaintSeverity.medium,
        acknowledged_at=at(date(2026, 9, 24), 12),
        ack_method="email",
        justified=QJustified.yes,
        ncr_id=ncrs[43].id,
        response_en="Falls corrected under NCR-ANIA-EXP-2026-0043.",
        responded_at=at(date(2026, 9, 30)),
        status=QComplaintStatus.responded,
        alerts_sent=[],
        created_by_user_id=hatem,
        seed_fake=True,
    )
    db.add(c)
    db.flush()
    ncrs[43].source_id = c.id
    ncrs[43].customer_id = anc.id
    db.add(
        QLink(
            project_id=p.id,
            from_type="ncr",
            from_id=ncrs[43].id,
            to_type="complaint",
            to_id=c.id,
            kind=QLinkKind.raised_from,
            created_at=at(date(2026, 9, 24), 13),
            seed_fake=True,
        )
    )
    numbering.bump_to(db, p, QRecordType.complaint, 2026, 2)


def _complaints_ruh(
    db: Session, w: _W, p: Project, cust: dict[str, QCustomer], ncrs: dict[int, QNcr]
) -> None:
    from app.services.quality import numbering  # noqa: PLC0415

    reem = w.u("reem.mutairi")
    rows = [
        (1, "NDC", date(2026, 4, 9), QComplaintStatus.closed, "Short-dated yoghurt delivered."),
        (2, "SAHM", date(2026, 7, 2), QComplaintStatus.closed, "Outer cartons crushed."),
        (3, "NDC", date(2026, 9, 6), QComplaintStatus.acknowledged, "Labels in English only."),
        (
            4,
            "GFF",
            date(2026, 9, 15),
            QComplaintStatus.under_investigation,
            "Pallet height above agreed limit.",
        ),
        (
            5,
            "GFF",
            date(2026, 9, 27),
            QComplaintStatus.responded,
            "Cartons partly thawed at delivery.",
        ),
    ]
    for no, code, d, status, text in rows:
        c = QComplaint(
            project_id=p.id,
            complaint_no=f"CCM-{p.code}-2026-{no:04d}",
            customer_id=cust[code].id,
            site_id=w.site(p, "S-DC1"),
            received_at=at(d, 10),
            channel=QComplaintChannel.email,
            category=QNcrCategory.temperature if no == 5 else QNcrCategory.packaging,
            description=text,
            severity=QComplaintSeverity.high if no == 5 else QComplaintSeverity.medium,
            acknowledged_at=at(d, 14),
            ack_method="email",
            status=status,
            alerts_sent=[],
            created_by_user_id=reem,
            seed_fake=True,
        )
        if status in (QComplaintStatus.responded, QComplaintStatus.closed):
            c.justified = QJustified.yes if no == 5 else QJustified.partly
            c.response_en = "Investigated with the carrier; corrective actions agreed."
            c.responded_at = at(d + timedelta(days=4))
        if no == 5:
            c.ncr_id = ncrs[36].id
        if status == QComplaintStatus.closed:
            c.satisfied = QSatisfaction_yes()
            c.closed_at = at(d + timedelta(days=20))
        db.add(c)
    db.flush()
    numbering.bump_to(db, p, QRecordType.complaint, 2026, 5)


def QSatisfaction_yes() -> Any:  # noqa: N802
    from app.core.quality.common import QSatisfaction  # noqa: PLC0415

    return QSatisfaction.yes


def seed_quality_setup(db: Session) -> None:
    """Quality configured on both projects (profiles, positions and holders, default matrix,
    suppliers, criteria, customers, systems) without any record — the fixture of the Q0 tests."""
    w = _W(db)
    ania, ruh = w.projects["ANIA-EXP"], w.projects["RUH-CCH"]
    if db.get(QSettings, ania.id) is not None:
        return
    _settings(db, w, ania, QSectorProfile.construction, {"delay_rate_sar_day": "12000.00"})
    _settings(db, w, ruh, QSectorProfile.logistics, {})
    _hold(db, w, ania, "CONSULTANT_RE", "abdullah.dossary")
    _hold(db, w, ania, "CLIENT_REP", "sultan.mutlaq")
    _hold(db, w, ruh, "WAREHOUSE_MGR", "saad.anazi")
    _hold(db, w, ruh, "RESP_PHARMACIST", "lama.qarni")
    _hold(db, w, ruh, "TRANSPORT_SUP", "naveen.kumar")
    # RUH-CCH matrix: q_audit.issue → user Faisal (the only QA/QC Manager, Reem, leads audits)
    for r in db.scalars(
        select(QRpRule).where(QRpRule.project_id == ruh.id, QRpRule.record_type == "q_audit")
    ):
        r.assignee_kind = QAssigneeKind.user
        r.assignee = str(w.u("faisal.harbi"))
    _suppliers(db)
    _criteria(db, w)
    _registers_ania(db, w, ania)
    _registers_ruh(db, w, ruh)
    db.flush()


def seed_quality_data(db: Session) -> None:
    """Part A records for both profiles, then each wave-2 part's seed."""
    if db.scalar(select(QNcr.id).where(QNcr.seed_fake.is_(True)).limit(1)) is not None:
        return
    seed_quality_setup(db)
    w = _W(db)
    ania, ruh = w.projects["ANIA-EXP"], w.projects["RUH-CCH"]
    sup = {s.supplier_code: s for s in db.scalars(select(QSupplier))}
    cust = {c.code: c for c in db.scalars(select(QCustomer).where(QCustomer.project_id == ruh.id))}
    _ania_mte(db, ania, w)
    _ruh_mte(db, ruh, w)
    ania_cfg = {
        "owners": [w.u("bilal.qureshi"), w.u("rania.zahrani")],
        "raisers": [w.u("joseph.mathew.qc"), w.u("mazen.harbi"), w.u("rania.zahrani")],
        "engs": [w.eng(ania, c) for c in ("RAWABI", "NAJD", "GULFPAVE", "SAHARA")],
        "sites": ["S-LAND", "S-AIR"],
        "manager": w.u("hatem.shehri"),
        "suppliers": {k: v.id for k, v in sup.items()},
    }
    ncrs = _ncrs(db, w, ania, _ncr_rows_ania(), QSectorProfile.construction, ania_cfg)
    _ania_named(db, w, ania, ncrs, sup)
    _alert_obs_complaints_ania(db, w, ania, ncrs)
    ruh_cfg = {
        "owners": [w.u("imran.siddiq"), w.u("naveen.kumar")],
        "raisers": [w.u("imran.siddiq"), w.u("naveen.kumar")],
        "engs": [w.eng(ruh, "WAHAT")],
        "sites": ["S-DC1"],
        "manager": w.u("reem.mutairi"),
        "suppliers": {k: v.id for k, v in sup.items()},
    }
    rncrs = _ncrs(db, w, ruh, _ncr_rows_ruh(), QSectorProfile.logistics, ruh_cfg)
    n31 = rncrs[31]
    n31.title = "Yoghurt received at +11.0 °C rejected — RCV-RUH-CCH-2026-01902"
    n31.supplier_id = sup["NDCF"].id
    n31.customer_id = cust["NDC"].id
    n31.zone_id = w.zone(ruh, "Z-DOCK")
    rncrs[34].title = "Z-FRZ1 excursion 02:00–05:30 (major) — product impact assessment"
    rncrs[34].zone_id = w.zone(ruh, "Z-FRZ1")
    rncrs[36].title = "Transit excursion on TRP-RUH-CCH-2026-00921 — cartons partly thawed"
    rncrs[36].customer_id = cust["GFF"].id
    rncrs[36].supplier_id = sup["COOLRD"].id
    rncrs[36].detection_stage = QDetectionStage.at_customer
    db.flush()
    _complaints_ruh(db, w, ruh, cust, rncrs)
    for model in (QSettings,):
        _ = model
    db.flush()
    from app import (  # noqa: PLC0415
        seed_quality_q1,
        seed_quality_q2,
        seed_quality_q3,
        seed_quality_q4,
    )
    from app.services.quality import ensure_registered  # noqa: PLC0415
    from app.services.quality import registry as reg  # noqa: PLC0415

    for part in (seed_quality_q1, seed_quality_q2, seed_quality_q3, seed_quality_q4):
        part.seed(db)
    ensure_registered()
    for fn in reg.SEEDS.values():
        fn(db)
    db.flush()


_ = (DEFAULT_POSITIONS, Role)
