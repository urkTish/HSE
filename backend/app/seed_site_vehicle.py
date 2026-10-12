"""Option 7b seed (spec 7b-fleet-driver v2.0 Appendix A; prototype; fictional, seed_fake = true,
refs contain TEST). Additive: new site vehicles (VEH-0101…VEH-0124), the user Tariq (rep NAJD),
the Phase 5 courses DEF-DRV / BUS-DRV with 27 DEF-DRV records, 30 authorisations, the templates
VPU-L / VPU-H / VPU-B, pre-use checks for September and 2026-10-11/12 and 15 journey plans. The
only earlier row touched is the Phase 4 item FX-EX-11 (EQP-000206), which gains the link to the
NAJD excavator VEH-0119 (DECISIONS D-251).

Worked examples (exact):
- SW1 at 2026-10-12: 24 site vehicles, 1 idle (VEH-0121), 2 docs_expired (VEH-0116 MVPI,
  VEH-0123 operating card), 1 defect_hold (RAWABI tipper VEH-0109, brakes, CA open), 1
  not_certified (VEH-0119 → FX-EX-11 out of service) → K-138 = 19 ÷ 23 = 82.6 %.
- SW2 2026-10-11: 23 required, 20 Completed (2 paper by Ahmed) → K-140 = 87.0 %; Friday
  2026-10-09 → "—".
- SW3 September 2026: 398 checks (8 days × 16 + 18 days × 15) + 14 Arrived journey plans = 412
  records; 12 checks by the two drivers without an authorisation → K-139 = 400 ÷ 412 = 97.1 %."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    DeploymentStatus,
    LicenceClass,
    LicenceIssuer,
    PlateType,
    VehicleCategory,
    VehicleOwnerType,
    VehicleStatus,
)
from app.core.clock import set_now
from app.core.enums import EmployerType, Language, Role, UserStatus
from app.core.field_enums import (
    ItemType,
    ResponseOwnerType,
    ResponseResult,
    StopRule,
    TemplateKind,
    VersionStatus,
)
from app.core.hse_enums import AttachmentOwner, InspectionType
from app.core.site_vehicle_enums import (
    USE_CLASS_GROUP,
    SiteVehAuthStatus,
    SiteVehCheckSource,
    SiteVehDriverGroup,
    SiteVehJourneyStatus,
    SiteVehScope,
    SiteVehUseClass,
)
from app.core.text import search_blob
from app.models import (
    ChecklistResponse,
    ChecklistTemplate,
    Contractor,
    Deployment,
    DriverAuthorisation,
    EmailMessage,
    EquipmentItem,
    JourneyPlan,
    Notification,
    Project,
    ProjectEngagement,
    RoleAssignment,
    SiteVehicleSettings,
    TrainingProvider,
    TrainingRecord,
    User,
    Vehicle,
    VehicleCheck,
    Worker,
)
from app.schemas.field import AnswerInput

SEED_CLOCK = datetime(2026, 10, 12, 7, 0, tzinfo=UTC)  # 10:00 Riyadh (7b §9 clock)
LIVE_FROM = date(2026, 7, 1)
CREATED = datetime(2026, 6, 30, 6, 0, tzinfo=UTC)
VERIFIED = datetime(2026, 7, 2, 7, 0, tzinfo=UTC)
PUBLISHED = datetime(2026, 6, 15, 6, 0, tzinfo=UTC)
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa75\x81\x84"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
U = SiteVehUseClass
G = SiteVehDriverGroup
VC = VehicleCategory
FAR = date(2027, 3, 31)


@dataclass(frozen=True)
class V:
    seq: int
    eng: str
    use: SiteVehUseClass
    cat: VehicleCategory
    plated: bool
    make: str
    fleet: str
    seats: int | None = None


VEHICLES = [
    # GULFPAVE (8)
    V(101, "GULFPAVE", U.pool_car, VC.light_vehicle, True, "Toyota Corolla", "GP-PC-01"),
    V(102, "GULFPAVE", U.crew_pickup, VC.pickup, True, "Toyota Hilux", "GP-CP-02", 5),
    V(103, "GULFPAVE", U.crew_pickup, VC.pickup, True, "Nissan Navara", "GP-CP-03", 5),
    V(104, "GULFPAVE", U.pool_car, VC.light_vehicle, True, "Hyundai Accent", "GP-PC-04"),
    V(105, "GULFPAVE", U.crew_bus, VC.bus, True, "Toyota Hiace", "GP-CB-05", 14),
    V(106, "GULFPAVE", U.water_tanker, VC.water_tanker, True, "Isuzu FVR tanker", "GP-WT-06"),
    V(107, "GULFPAVE", U.crew_bus, VC.bus, True, "Toyota Coaster", "GP-CB-07", 30),
    V(108, "GULFPAVE", U.other_plant, VC.roller, False, "Bomag BW 211", "GP-RL-08"),
    # RAWABI (10, 4 tippers)
    V(109, "RAWABI", U.tipper, VC.tipper, True, "Mercedes Actros tipper", "RW-TP-09"),
    V(110, "RAWABI", U.tipper, VC.tipper, True, "Volvo FMX tipper", "RW-TP-10"),
    V(111, "RAWABI", U.tipper, VC.tipper, True, "MAN TGS tipper", "RW-TP-11B"),
    V(112, "RAWABI", U.tipper, VC.tipper, True, "Scania P410 tipper", "RW-TP-12"),
    V(113, "RAWABI", U.goods_heavy, VC.truck, True, "Hino 700 flatbed", "RW-GH-13"),
    V(114, "RAWABI", U.water_tanker, VC.water_tanker, True, "Isuzu FTR tanker", "RW-WT-14"),
    V(115, "RAWABI", U.crew_pickup, VC.pickup, True, "Toyota Hilux", "RW-CP-15", 5),
    V(116, "RAWABI", U.pool_car, VC.light_vehicle, True, "Kia Cerato", "RW-PC-16"),
    V(117, "RAWABI", U.earthmoving_plant, VC.wheel_loader, False, "CAT 950 loader", "RW-WL-17"),
    V(118, "RAWABI", U.crew_bus, VC.bus, True, "Ashok Leyland Falcon", "RW-CB-18", 26),
    # NAJD (6, incl. the excavator linked to Phase 4 item FX-EX-11)
    V(119, "NAJD", U.earthmoving_plant, VC.excavator, False, "TestLift Excavator T36", "NJ-EX-19"),
    V(120, "NAJD", U.crew_pickup, VC.pickup, True, "Isuzu D-Max", "NJ-CP-20", 5),
    V(121, "NAJD", U.pool_car, VC.light_vehicle, True, "Toyota Yaris", "NJ-PC-21"),
    V(122, "NAJD", U.tipper, VC.tipper, True, "Mercedes Arocs tipper", "NJ-TP-22"),
    V(123, "NAJD", U.goods_heavy, VC.truck, True, "Mitsubishi Fuso", "NJ-GH-23"),
    V(124, "NAJD", U.crew_pickup, VC.pickup, True, "Toyota Hilux", "NJ-CP-24", 5),
]  # fmt: skip
IDLE = 121
HOLD = 109
PHASE4 = 119
UNVERIFIED = {115, 124}
MISSING_1011 = {113, 122, 124}
PAPER_1011 = {110, 114}
AR_LETTERS = ["ا ب ح", "د ر س", "ص ط ع", "ق ك ل", "م ن و", "و ى ب"]

# ---- 6d templates (§3.3, PU-2) ----

TPL: dict[str, tuple[str, str, str, list[tuple[str, str, bool]]]] = {
    "VPU-L": ("VPL", "Pre-use check — light vehicle", "الفحص اليومي — مركبة خفيفة", [
        ("Brakes (service and parking)", "المكابح (الرئيسية واليدوية)", True),
        ("Steering", "التوجيه", True),
        ("Tyres and wheel nuts", "الإطارات وصواميل العجلات", True),
        ("Seat belts", "أحزمة الأمان", True),
        ("Lights and indicators", "الأضواء والإشارات", True),
        ("Windscreen, mirrors and wipers", "الزجاج الأمامي والمرايا والمساحات", True),
        ("Fluid levels (oil, coolant)", "مستويات السوائل (الزيت، التبريد)", False),
        ("No leaks under the vehicle", "لا تسربات أسفل المركبة", False),
        ("Fire extinguisher in date", "طفاية الحريق صالحة", False),
        ("First-aid kit present", "حقيبة الإسعافات موجودة", False),
        ("Body damage reported", "الإبلاغ عن أضرار الهيكل", False),
        ("Cab clean, no loose items", "المقصورة نظيفة دون أغراض سائبة", False),
    ]),
    "VPU-H": ("VPH", "Pre-use check — heavy vehicle / plant", "الفحص اليومي — مركبة ثقيلة / معدة", [
        ("Brakes (service and parking)", "المكابح (الرئيسية واليدوية)", True),
        ("Steering", "التوجيه", True),
        ("Tyres / tracks", "الإطارات / الجنازير", True),
        ("Seat belt", "حزام الأمان", True),
        ("Lights and indicators", "الأضواء والإشارات", True),
        ("Reverse alarm", "إنذار الرجوع للخلف", True),
        ("Amber beacon", "الضوء الدوار", True),
        ("Mirrors / camera visibility", "المرايا / الكاميرا", True),
        ("Hydraulic hoses and rams", "الخراطيم والأسطوانات الهيدروليكية", False),
        ("Fluid levels", "مستويات السوائل", False),
        ("No leaks", "لا تسربات", False),
        ("Fire extinguisher", "طفاية الحريق", False),
        ("Tipping body / attachment pins", "صندوق القلاب / مسامير الملحقات", False),
        ("Guards in place", "الحواجز الواقية في مكانها", False),
        ("Steps and handrails", "الدرجات والمقابض", False),
        ("Cab clean, windows clear", "المقصورة نظيفة والنوافذ واضحة", False),
    ]),
    "VPU-B": ("VPB", "Pre-use check — crew bus", "الفحص اليومي — حافلة العمال", [
        ("Brakes (service and parking)", "المكابح (الرئيسية واليدوية)", True),
        ("Steering", "التوجيه", True),
        ("Tyres and wheel nuts", "الإطارات وصواميل العجلات", True),
        ("Seat belts (all seats)", "أحزمة الأمان (جميع المقاعد)", True),
        ("Lights and indicators", "الأضواء والإشارات", True),
        ("Emergency exits and hammer", "مخارج الطوارئ والمطرقة", True),
        ("First-aid kit", "حقيبة الإسعافات", True),
        ("Fire extinguisher", "طفاية الحريق", True),
        ("Doors and door interlock", "الأبواب وقفلها", True),
        ("Mirrors", "المرايا", False),
        ("Wipers and washers", "المساحات والغسالات", False),
        ("Air conditioning", "التكييف", False),
        ("Seats secure", "المقاعد مثبتة", False),
        ("Floor and steps", "الأرضية والدرجات", False),
        ("Fluid levels", "مستويات السوائل", False),
        ("No leaks", "لا تسربات", False),
        ("Body damage reported", "الإبلاغ عن أضرار الهيكل", False),
        ("Clean inside", "النظافة الداخلية", False),
    ]),
}  # fmt: skip


def template_items(code: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    prefix, _, _, rows = TPL[code]
    secs = [
        {"code": "A", "title_en": "Critical items", "title_ar": "البنود الحرجة", "order": 1},
        {"code": "B", "title_en": "General", "title_ar": "عام", "order": 2},
    ]
    items = []
    for n, (en, ar, crit) in enumerate(rows, start=1):
        items.append(
            {
                "item_code": f"{prefix}-{n:02d}", "section_code": "A" if crit else "B",
                "order": n, "text_en": en, "text_ar": ar, "item_type": ItemType.yes_no.value,
                "weight": 3 if crit else 1, "critical": crit, "stop_rule": StopRule.none.value,
                "na_allowed": False, "photo_required_on_fail": False,
                "default_severity": "minor", "airside_only": False, "numeric_rule": None,
                "options": None,
                "suggested_ca_en": f"Repair before use: {en}" if crit else None,
                "suggested_ca_ar": f"الإصلاح قبل الاستخدام: {ar}" if crit else None,
                "suggested_control_level": None, "reference": "OSHA 1926.600-602 (7b PU-2)",
                "guidance_en": None, "guidance_ar": None,
            }
        )  # fmt: skip
    return secs, items


def ensure_templates(db: Session, author: uuid.UUID | None) -> dict[str, ChecklistTemplate]:
    from app.services.field.library import review_due  # noqa: PLC0415

    out = {}
    for code, (_, en, ar, _) in TPL.items():
        t = db.scalar(select(ChecklistTemplate).where(ChecklistTemplate.template_code == code))
        if t is None:
            secs, items = template_items(code)
            t = ChecklistTemplate(
                id=uuid.uuid4(), template_code=code, version=1, kind=TemplateKind.inspection,
                inspection_type=InspectionType.plant_vehicle, title_en=en, title_ar=ar,
                sections=secs, items=items, zone_types=[], project_ids=[],
                review_due_on=review_due(PUBLISHED), authored_by_user_id=author,
                published_by_user_id=author, published_at=PUBLISHED,
                status=VersionStatus.published, created_by_user_id=author,
            )  # fmt: skip
            db.add(t)
            db.flush()
        out[code] = t
    return out


# ---- helpers -------------------------------------------------------------------------------------


def already_seeded(db: Session) -> bool:
    return db.scalar(select(Vehicle.id).where(Vehicle.vehicle_no == "VEH-0101")) is not None


def _local(d: date, h: int, mi: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, mi, tzinfo=UTC) - timedelta(hours=3)


def _uid(db: Session, login: str) -> uuid.UUID:
    u = db.scalar(select(User.id).where(User.email == f"{login}@example.com"))
    assert u is not None, login  # noqa: S101
    return u


def _engs(db: Session, project: Project) -> dict[str, ProjectEngagement]:
    rows = db.execute(
        select(Contractor.short_code, ProjectEngagement)
        .join(ProjectEngagement, ProjectEngagement.contractor_id == Contractor.id)
        .where(ProjectEngagement.project_id == project.id)
    ).all()
    return {str(code): e for code, e in rows}


def _tariq(db: Session, project: Project, najd: ProjectEngagement) -> None:
    """§9: the rep of NAJD on ANIA-EXP (same password as the other seeded users)."""
    if db.scalar(select(User.id).where(User.email == "tariq.mutairi@example.com")):
        return
    ref = db.scalar(select(User).where(User.email == "ahmed.zahrani@example.com"))
    assert ref is not None  # noqa: S101
    u = User(
        id=uuid.uuid4(), email="tariq.mutairi@example.com", full_name_en="Tariq Al-Mutairi",
        full_name_ar="طارق المطيري", mobile="+966500000017",
        employer_type=EmployerType.contractor, employer_contractor_id=najd.contractor_id,
        job_title="Contractor HSE Rep", preferred_language=Language.en,
        status=UserStatus.active, password_hash=ref.password_hash, activated_at=ref.activated_at,
        privacy_notice_version=ref.privacy_notice_version,
        privacy_notice_ack_at=ref.privacy_notice_ack_at,
        search_text=search_blob("Tariq Al-Mutairi", "طارق المطيري", "tariq.mutairi@example.com"),
    )  # fmt: skip
    db.add(u)
    db.flush()
    db.add(
        RoleAssignment(
            id=uuid.uuid4(), user_id=u.id, role=Role.contractor_hse_rep, project_id=project.id,
            site_ids=[], contractor_engagement_id=najd.id, valid_from=date(2026, 1, 1),
            created_at=CREATED,
        )
    )  # fmt: skip
    db.flush()


def _pool(db: Session, project: Project, eng: ProjectEngagement) -> list[Worker]:
    """Mobilised workers of the engagement for the driver pool (drivers / operators first; named
    fixture workers below WKR-001000 left alone)."""
    rows = db.execute(
        select(Worker, Deployment.trade)
        .join(Deployment, Deployment.worker_id == Worker.id)
        .where(
            Deployment.project_id == project.id,
            Deployment.engagement_id == eng.id,
            Deployment.status == DeploymentStatus.mobilised,
            Worker.worker_no >= "WKR-001000",
            Worker.id_expiry_date >= date(2027, 6, 1),
        )
        .order_by(Worker.worker_no)
    ).all()
    pref = [w for w, t in rows if t.value in ("driver", "plant_operator")]
    rest = [w for w, t in rows if t.value not in ("driver", "plant_operator")]
    return pref + rest


def _vin(seq: int) -> str:
    return f"JT7BTESTVN{seq:07d}"


def _add_vehicles(
    db: Session, project: Project, engs: dict[str, ProjectEngagement], noura: uuid.UUID
) -> dict[int, Vehicle]:
    out: dict[int, Vehicle] = {}
    for i, s in enumerate(VEHICLES):
        plated = s.plated
        oc = s.use in (U.crew_bus, U.tipper, U.goods_heavy) and plated
        heavy = USE_CLASS_GROUP[s.use] in (G.heavy, G.bus)
        v = Vehicle(
            id=uuid.uuid4(), seq=s.seq, vehicle_no=f"VEH-{s.seq:04d}", project_id=project.id,
            engagement_id=engs[s.eng].id, owner_type=VehicleOwnerType.company, category=s.cat,
            plate_type=(PlateType.transport if heavy else PlateType.private) if plated
            else PlateType.none,
            plate_letters_ar=AR_LETTERS[i % len(AR_LETTERS)] if plated else None,
            plate_letters_en=None, plate_digits=f"{7000 + s.seq}" if plated else None,
            fleet_no=s.fleet, serial_or_vin=_vin(s.seq) if plated else f"TESTSN-7B-{s.seq:04d}",
            make_model=s.make, year_built=2022, colour="White",
            travel_height_m=Decimal("3.20") if heavy or not plated else Decimal("1.90"),
            max_working_height_m_agl=Decimal("3.20") if heavy or not plated else Decimal("1.90"),
            istimara_expiry=FAR if plated else None, insurance_policy_no=f"TEST-POL-{s.seq:04d}",
            insurance_expiry=FAR, mvpi_expiry=date(2027, 1, 31) if plated else None,
            status=VehicleStatus.active, site_scope=SiteVehScope.site, use_class=s.use,
            driver_group=USE_CLASS_GROUP[s.use], seats=s.seats,
            operating_card_no=f"TEST-OC-{5400 + s.seq}" if oc else None,
            operating_card_expiry=date(2027, 1, 31) if oc else None,
            docs_verified_by_user_id=None if s.seq in UNVERIFIED or not plated else noura,
            docs_verified_at=None if s.seq in UNVERIFIED or not plated else VERIFIED,
            created_at=CREATED, updated_at=CREATED, seed_fake=True,
        )  # fmt: skip
        if s.seq == 107:
            v.insurance_expiry = date(2026, 10, 19)  # AC 3
        if s.seq == 116:
            v.mvpi_expiry = date(2026, 10, 5)  # docs_expired (SW1)
        if s.seq == 123:
            v.operating_card_expiry = date(2026, 10, 1)  # docs_expired (SW1)
        if s.seq == IDLE:
            v.idle_from, v.idle_to = date(2026, 10, 1), date(2026, 10, 31)
        db.add(v)
        out[s.seq] = v
    db.flush()
    return out


# ---- authorisations ------------------------------------------------------------------------------


@dataclass
class Driver:
    worker: Worker
    eng: ProjectEngagement
    groups: list[SiteVehDriverGroup]
    plant: list[uuid.UUID]


def _groups_for(v: V) -> list[SiteVehDriverGroup]:
    g = USE_CLASS_GROUP[v.use]
    return [G.plant] if g == G.plant else ([G.light] if g == G.light else [G.light, g])


LICENCE = {
    G.light: LicenceClass.private,
    G.bus: LicenceClass.public_transport,
    G.heavy: LicenceClass.heavy_transport,
}


def _auth(
    db: Session,
    project: Project,
    n: int,
    d: Driver,
    status: SiteVehAuthStatus,
    issued: date,
    officer: uuid.UUID,
    reason: str | None = None,
) -> DriverAuthorisation:
    from app.services.site_vehicle import authorisations as auths  # noqa: PLC0415
    from app.services.site_vehicle import common as c  # noqa: PLC0415

    dep = c.mobilised_deployment(db, project.id, d.worker.id)
    road = [g for g in d.groups if g != G.plant]
    cls = None
    if road:
        cls = max((LICENCE[g] for g in road), key=lambda x: list(LICENCE.values()).index(x))
    a = DriverAuthorisation(
        id=uuid.uuid4(), project_id=project.id, seq=n, auth_no=f"DA-{project.code}-{n:04d}",
        worker_id=d.worker.id, deployment_id=dep.id, engagement_id=dep.engagement_id,
        groups=[g.value for g in d.groups], plant_vehicle_ids=d.plant,
        licence_issuer=LicenceIssuer.ksa if road else None, licence_class=cls,
        licence_expiry=date(2028, 5, 10) if road else None, licence_prefilled_from_adp=False,
        assessment_date=issued - timedelta(days=5), assessor="Test Driving Academy",
        issued_on=issued, own_valid_until=issued + timedelta(days=730), status=status,
        status_reason=reason, status_changed_at=_local(issued, 9),
        activated_at=_local(issued, 9) if status != SiteVehAuthStatus.draft else None,
        activated_by_user_id=officer if status != SiteVehAuthStatus.draft else None,
        proposed_by_user_id=officer, hook_results=[], created_by_user_id=officer,
        created_at=_local(issued, 8), updated_at=_local(issued, 9), seed_fake=True,
    )  # fmt: skip
    db.add(a)
    db.flush()
    auths.evaluate(db, a, SEED_CLOCK)
    return a


def _def_drv(db: Session, workers: list[Worker], officer: uuid.UUID) -> None:
    """27 DEF-DRV records (Phase 5, org-wide; completed 2026-08-10, valid 36 months)."""
    from sqlalchemy import func  # noqa: PLC0415

    from app.core.cert_enums import VerificationStatus  # noqa: PLC0415
    from app.core.train_enums import (  # noqa: PLC0415
        TrainingLimitingFactor,
        TrainingRecordSource,
        TrainingRecordStatus,
    )
    from app.services.train import common as tcommon  # noqa: PLC0415
    from app.services.train import validity as tval  # noqa: PLC0415

    course = tcommon.course(db, "DEF-DRV")
    assert course is not None  # noqa: S101
    provider = db.scalar(
        select(TrainingProvider).where(TrainingProvider.provider_code == "INT-HSE")
    ) or db.scalar(select(TrainingProvider).limit(1))
    assert provider is not None  # noqa: S101
    seq = int(db.scalar(select(func.max(TrainingRecord.seq))) or 0)
    done = date(2026, 8, 10)
    vu, lf = tval.stored_validity(course, done, None)
    rev = datetime(2026, 8, 11, 7, 0, tzinfo=UTC)
    for w in workers:
        seq += 1
        db.add(
            TrainingRecord(
                id=uuid.uuid4(), seq=seq, record_no=f"TRR-{seq:06d}", worker_id=w.id,
                course_code="DEF-DRV", source=TrainingRecordSource.import_,
                provider_id=provider.id, certificate_no=f"TEST-DEFDRV-{seq:06d}",
                completed_on=done, valid_until=vu,
                limiting_factor=lf or TrainingLimitingFactor.course_validity,
                status=TrainingRecordStatus.accepted,
                verification_status=VerificationStatus.verified, submitted_by_user_id=officer,
                submitted_at=rev - timedelta(hours=2), reviewed_by_user_id=officer,
                reviewed_at=rev, verified_at=rev, in_force_from=rev, alerts_sent=[],
                name_as_printed=w.full_name_en, seed_fake=True, created_at=rev, updated_at=rev,
            )
        )  # fmt: skip
    db.flush()
    tcommon.clear_cache(db)


# ---- checks and journeys -------------------------------------------------------------------------


def _answers(t: ChecklistTemplate, fail: set[str] | None = None) -> list[AnswerInput]:
    out = []
    for it in t.items:
        code = it["item_code"]
        bad = code in (fail or set())
        out.append(
            AnswerInput(
                item_code=code,
                answer="non_compliant" if bad else "compliant",
                note="Brake pedal soft, stopping distance long" if bad else None,
            )
        )
    return out


def _check(
    db: Session,
    project: Project,
    v: Vehicle,
    driver: Worker,
    driver_eng: uuid.UUID | None,
    auth: DriverAuthorisation | None,
    d: date,
    seq: int,
    t: ChecklistTemplate,
    site_id: uuid.UUID,
    by: uuid.UUID,
    hour: int = 6,
    paper: bool = False,
    fail: set[str] | None = None,
) -> tuple[VehicleCheck, ChecklistResponse, Any, dict[str, tuple[int, Any]]]:
    from app.services.field import execution, scoring  # noqa: PLC0415

    answers = _answers(t, fail)
    sc = scoring.evaluate(t.items, [a.model_dump(mode="json") for a in answers], airside=True)
    by_code = {a.item_code: (i, a) for i, a in enumerate(answers)}
    at = _local(d, hour, (seq * 7) % 50)
    passed = sc.critical_fails == 0
    r = ChecklistResponse(
        id=uuid.uuid4(), project_id=project.id, client_uuid=uuid.uuid4(),
        owner_type=ResponseOwnerType.vehicle_check, template_id=t.id,
        template_code=t.template_code, template_version=t.version,
        inspection_type=InspectionType.plant_vehicle, site_id=site_id,
        engagement_id=v.engagement_id, airside=False, started_at=at - timedelta(minutes=6),
        completed_at=at, completed_date=d, received_at=at, inspector_id=by, answers=[],
        applicable_count=sc.applicable_count, compliant_count=sc.compliant_count,
        applicable_weight=sc.applicable_weight, earned_weight=sc.earned_weight,
        score_pct=scoring.q(sc.pct) if sc.pct is not None else None,
        critical_fail_count=sc.critical_fails,
        result=ResponseResult.pass_ if passed else ResponseResult.fail, submitted=True,
        created_by_user_id=by, created_at=at, updated_at=at, seed_fake=True,
    )  # fmt: skip
    db.add(r)
    db.flush()
    r.answers = execution.store_answers(db, by, r, sc, by_code, [])
    photo = None
    if paper:
        from app.services.attachments import store  # noqa: PLC0415

        photo = store(db, AttachmentOwner.field_photo, r.id, project.id,
                      f"paper-card-{v.vehicle_no}-{d:%Y%m%d}.png", PNG, "image/png", by).id  # fmt: skip
    ch = VehicleCheck(
        id=uuid.uuid4(), project_id=project.id,
        check_no=f"VPC-{project.code}-{d:%Y%m%d}-{seq:04d}", seq=seq, vehicle_id=v.id,
        engagement_id=v.engagement_id, driver_worker_id=driver.id,
        driver_engagement_id=driver_eng, driver_group=v.driver_group,
        driver_authorised=auth is not None, authorisation_id=auth.id if auth else None,
        check_date=d, response_id=r.id, template_code=t.template_code, passed=passed,
        critical_fail_count=sc.critical_fails,
        failed_items=[e.code for e in sc.evals if e.non_compliant],
        source=SiteVehCheckSource.paper if paper else SiteVehCheckSource.app,
        paper_photo_id=photo, recorded_by_user_id=by, completed_at=at, warnings=[],
        created_by_user_id=by, created_at=at, updated_at=at, seed_fake=True,
    )  # fmt: skip
    db.add(ch)
    db.flush()
    return ch, r, sc, by_code


def seed_site_vehicle_data(db: Session) -> None:
    """Appendix A (additive)."""
    if already_seeded(db):
        return
    project = db.scalar(select(Project).where(Project.code == "ANIA-EXP"))
    if project is None:
        return
    item = db.scalar(select(EquipmentItem).where(EquipmentItem.equipment_no == "EQP-000206"))
    if item is None or item.vehicle_id is not None:
        return
    from app.services.site_vehicle import checks as svc_checks  # noqa: PLC0415
    from app.services.site_vehicle import common as c  # noqa: PLC0415

    n0 = set(db.scalars(select(Notification.id)))
    e0 = set(db.scalars(select(EmailMessage.id)))
    try:
        set_now(SEED_CLOCK)
        faisal, noura = _uid(db, "faisal.harbi"), _uid(db, "noura.qahtani")
        ahmed, omar = _uid(db, "ahmed.zahrani"), _uid(db, "omar.siddiqui")
        engs = _engs(db, project)
        _tariq(db, project, engs["NAJD"])
        db.add(
            SiteVehicleSettings(
                project_id=project.id, site_vehicles_from=LIVE_FROM, values={},
                updated_at=CREATED, updated_by_user_id=faisal,
            )
        )  # fmt: skip
        db.flush()
        c.clear_cache(db)
        c.ensure_courses(db)
        tpls = ensure_templates(db, faisal)
        vs = _add_vehicles(db, project, engs, noura)
        item.vehicle_id = vs[PHASE4].id  # SV-3 link (D-251)
        db.flush()
        # drivers: one regular driver per vehicle + 6 more; Jomar drives VEH-0107
        jomar = db.scalar(select(Worker).where(Worker.worker_no == "WKR-000003"))
        assert jomar is not None  # noqa: S101
        pools = {k: [w for w in _pool(db, project, engs[k]) if w.id != jomar.id]
                 for k in ("GULFPAVE", "RAWABI", "NAJD")}  # fmt: skip
        taken: dict[str, int] = dict.fromkeys(pools, 0)

        def nxt(eng: str) -> Worker:
            w = pools[eng][taken[eng]]
            taken[eng] += 1
            return w

        regular: dict[int, Driver] = {}
        for s in VEHICLES:
            w = jomar if s.seq == 107 else nxt(s.eng)
            g = [G.light, G.bus] if s.seq == 107 else _groups_for(s)
            plant = [vs[s.seq].id] if G.plant in g else []
            regular[s.seq] = Driver(w, engs[s.eng], g, plant)
        spares = [Driver(nxt("GULFPAVE"), engs["GULFPAVE"], [G.light], []),
                  Driver(nxt("RAWABI"), engs["RAWABI"], [G.light, G.heavy], [])]  # fmt: skip
        others = [
            (Driver(nxt("GULFPAVE"), engs["GULFPAVE"], [G.light], []), SiteVehAuthStatus.draft,
             date(2026, 10, 10), None),
            (Driver(nxt("RAWABI"), engs["RAWABI"], [G.light], []), SiteVehAuthStatus.suspended,
             date(2026, 8, 25), "Suspended pending a refresher after a near miss on the haul road"),
            (Driver(nxt("NAJD"), engs["NAJD"], [G.light], []), SiteVehAuthStatus.revoked,
             date(2026, 8, 25), "Left the project; authorisation withdrawn"),
            (Driver(nxt("NAJD"), engs["NAJD"], [G.light], []), SiteVehAuthStatus.expired,
             date(2024, 9, 1), "Effective validity ended (own_validity)."),
        ]  # fmt: skip
        unauth = [nxt("GULFPAVE"), nxt("RAWABI")]  # SW3: 2 drivers without an authorisation
        road_workers = [x.worker for x in [*regular.values(), *spares] if G.plant not in x.groups]
        road_workers += [x.worker for x, *_ in others]
        assert len(road_workers) == 27  # noqa: S101
        _def_drv(db, road_workers, noura)
        auth_of: dict[uuid.UUID, DriverAuthorisation] = {}
        n = 0
        for dr in [*regular.values(), *spares]:
            n += 1
            auth_of[dr.worker.id] = _auth(db, project, n, dr, SiteVehAuthStatus.active,
                                          date(2026, 8, 25), noura)  # fmt: skip
        for dr, st, issued, reason in others:
            n += 1
            a = _auth(db, project, n, dr, st, issued, noura, reason)
            if st == SiteVehAuthStatus.expired:
                a.effective_valid_until = a.own_valid_until = date(2026, 8, 31)
        assert n == 30  # noqa: S101
        db.flush()
        sites = {k: svc_checks.site_for(db, project.id, e.id) for k, e in engs.items()}
        tpl_of = {G.light: tpls["VPU-L"], G.bus: tpls["VPU-B"], G.heavy: tpls["VPU-H"],
                  G.plant: tpls["VPU-H"]}  # fmt: skip
        recorder = {"GULFPAVE": noura, "RAWABI": ahmed, "NAJD": omar}
        # September: 26 working days; 8 days × 16 + 18 days × 15 = 398 checks
        days = [date(2026, 9, 1) + timedelta(days=i) for i in range(30)]
        days = [d for d in days if d.weekday() != 4]
        assert len(days) == 26  # noqa: S101
        order = [s.seq for s in VEHICLES if s.seq != PHASE4]  # 23 vehicles
        picks = [
            (d, sorted(order[(i * 5 + j) % len(order)] for j in range(16 if i < 8 else 15)))
            for i, d in enumerate(days)
        ]
        assert sum(len(p) for _, p in picks) == 398  # noqa: S101
        # 6 checks each on VEH-0101 and VEH-0110 by the two drivers without an authorisation
        unauth_days: set[tuple[int, date]] = set()
        for vno in (101, 110):
            hits = [(vno, d) for d, p in picks if vno in p][2:8]
            assert len(hits) == 6  # noqa: S101
            unauth_days |= set(hits)
        for d, pick in picks:
            for seq_n, vno in enumerate(pick, start=1):
                s = next(x for x in VEHICLES if x.seq == vno)
                v = vs[vno]
                auth: DriverAuthorisation | None
                if (vno, d) in unauth_days:
                    drv = unauth[0] if vno == 101 else unauth[1]
                    auth = None
                else:
                    drv = regular[vno].worker
                    auth = auth_of[drv.id]
                _check(db, project, v, drv, engs[s.eng].id, auth, d, seq_n,
                       tpl_of[v.driver_group or G.light], sites[s.eng], recorder[s.eng])  # fmt: skip
        # 2026-10-11 (Sunday): 20 of 23 required, 2 on paper (Ahmed)
        d = date(2026, 10, 11)
        seq_n = 0
        for s in VEHICLES:
            if s.seq in MISSING_1011 or s.seq == IDLE:
                continue
            seq_n += 1
            drv = regular[s.seq].worker
            paper = s.seq in PAPER_1011
            _check(db, project, vs[s.seq], drv, engs[s.eng].id, auth_of[drv.id], d, seq_n,
                   tpl_of[vs[s.seq].driver_group or G.light], sites[s.eng],
                   ahmed if paper else recorder[s.eng], paper=paper)  # fmt: skip
        assert seq_n == 20  # noqa: S101
        # 2026-10-12 06:40: RAWABI tipper VEH-0109, brakes failed → defect hold + CA (PU-3)
        d = date(2026, 10, 12)
        drv = regular[HOLD].worker
        set_now(_local(d, 6, 45))
        ch, r, sc, by_code = _check(db, project, vs[HOLD], drv, engs["RAWABI"].id,
                                    auth_of[drv.id], d, 1, tpls["VPU-H"], sites["RAWABI"],
                                    ahmed, hour=6, fail={"VPH-01"})  # fmt: skip
        svc_checks.outcomes(db, None, project, vs[HOLD], ch, r, sc, by_code, seed_fake=True)
        set_now(SEED_CLOCK)
        # journey plans: 14 Arrived in September (authorised drivers) + JP-0118 Planned
        trips = [(105, "Quarry Q3"), (107, "Batching plant B2"), (118, "Labour camp C1"),
                 (109, "Quarry Q3"), (113, "Laydown yard L4")]  # fmt: skip
        for i in range(14):
            vno, dest = trips[i % len(trips)]
            dday = days[2 + i]
            _plan(db, project, vs[vno], regular[vno], auth_of[regular[vno].worker.id], 104 + i,
                  dday, dest, noura, SiteVehJourneyStatus.arrived)  # fmt: skip
        _plan(db, project, vs[107], regular[107], auth_of[jomar.id], 118, date(2026, 10, 12),
              "Quarry Q3", noura, SiteVehJourneyStatus.planned, km=160, pax=22)  # fmt: skip
        for v in vs.values():
            c.refresh(db, v)
        db.flush()
        from app.seed_field import _cleanup  # noqa: PLC0415

        _cleanup(db, n0, e0)
        c.clear_cache(db)
        db.flush()
    finally:
        set_now(None)


def _plan(
    db: Session,
    project: Project,
    v: Vehicle,
    d: Driver,
    auth: DriverAuthorisation,
    seq: int,
    day: date,
    dest: str,
    contact: uuid.UUID,
    status: SiteVehJourneyStatus,
    km: int = 95,
    pax: int = 0,
) -> JourneyPlan:
    dep = _local(day, 5, 30)
    arr = _local(day, 8, 0)
    j = JourneyPlan(
        id=uuid.uuid4(), project_id=project.id, year=day.year, seq=seq,
        plan_no=f"JP-{project.code}-{day.year}-{seq:04d}", vehicle_id=v.id,
        engagement_id=v.engagement_id, driver_worker_id=d.worker.id,
        driver_engagement_id=d.eng.id, driver_group=v.driver_group, driver_authorised=True,
        authorisation_id=auth.id, passengers=pax,
        origin="ANIA-EXP site", destination=dest, distance_km=km, planned_depart=dep,
        planned_arrive=arr, depart_date=day, contact_user_id=contact,
        notes="Hwy 65, fuel stop Tamir" if km >= 150 else None, hint_recommended=km >= 150,
        arrived_at=arr - timedelta(minutes=10) if status == SiteVehJourneyStatus.arrived
        else None,
        status=status, warnings=[], created_by_user_id=contact, created_at=dep - timedelta(hours=10),
        updated_at=dep - timedelta(hours=10), seed_fake=True,
    )  # fmt: skip
    db.add(j)
    db.flush()
    return j


__all__ = ["seed_site_vehicle_data"]
