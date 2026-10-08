"""Idempotent demo/test seed from spec 0-foundation Appendix A (all data fictional).

Usage: ``SEED_PASSWORD=... uv run python -m app.seed``. Existing records (matched by code /
email) are left as they are; passwords are only set when a user is created.
"""

import sys
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.config import get_settings
from app.core.enums import (
    AirsideArea,
    ContractorCategory,
    ContractorStatus,
    EmployerType,
    Language,
    ProjectStatus,
    ProjectType,
    Role,
    SiteSide,
    SiteStatus,
    UserStatus,
    ZoneStatus,
    ZoneType,
)
from app.core.security import hash_password, password_problems
from app.core.text import normalize, search_blob
from app.db.session import get_sessionmaker
from app.models import (
    Contractor,
    Project,
    ProjectEngagement,
    ProjectSettings,
    RoleAssignment,
    Site,
    User,
    Zone,
)
from app.models.org import AIRSIDE_FIELDS
from app.seed_access import seed_access_data
from app.seed_hse import seed_data, seed_settings

VALID_FROM = date(2025, 1, 1)

PROJECTS: list[dict[str, Any]] = [
    {
        "code": "ANIA-EXP",
        "name_en": "Al-Noor International Airport — Terminal & Apron Expansion",
        "name_ar": "مشروع توسعة صالة وساحات مطار النور الدولي",
        "project_type": ProjectType.airport,
        "airport_icao": "OEXX",
        "client_name_en": "Al-Noor Airport Company (fictional)",
        "client_name_ar": "شركة مطار النور (وهمية)",
        "city": "Riyadh",
        "start_date": date(2025, 3, 1),
        "planned_end_date": date(2028, 12, 31),
        "settings": {
            "ltifr_base_hours": 1_000_000,
            "rate_base_hours": 200_000,
            "show_hijri": True,
            "default_language": Language.ar,
        },
    },
    {
        "code": "RBT-52",
        "name_en": "Riyadh Business Tower — 52-Storey Mixed-Use",
        "name_ar": "برج الرياض للأعمال — 52 طابقاً",
        "project_type": ProjectType.building_highrise,
        "airport_icao": None,
        "client_name_en": "Riyadh Business Tower Development Co. (fictional)",
        "client_name_ar": "شركة تطوير برج الرياض للأعمال (وهمية)",
        "city": "Riyadh",
        "start_date": date(2025, 1, 15),
        "planned_end_date": date(2029, 6, 30),
        "settings": {
            "ltifr_base_hours": 200_000,
            "rate_base_hours": 200_000,
            "show_hijri": False,
            "default_language": Language.en,
        },
    },
]

SITES: list[dict[str, Any]] = [
    {
        "project": "ANIA-EXP",
        "code": "S-AIR",
        "name_en": "Airside Works",
        "name_ar": "أعمال الجانب الجوي",
        "site_side": SiteSide.airside,
        "gps_lat": 24.957,
        "gps_lng": 46.698,
    },
    {
        "project": "ANIA-EXP",
        "code": "S-LAND",
        "name_en": "Terminal 3 Building",
        "name_ar": "مبنى الصالة 3",
        "site_side": SiteSide.landside,
        "gps_lat": 24.962,
        "gps_lng": 46.705,
    },
    {
        "project": "RBT-52",
        "code": "S-TWR",
        "name_en": "Main Tower",
        "name_ar": "البرج الرئيسي",
        "site_side": SiteSide.other,
        "gps_lat": 24.712,
        "gps_lng": 46.674,
    },
    {
        "project": "RBT-52",
        "code": "S-POD",
        "name_en": "Podium & Basement",
        "name_ar": "المنصة والقبو",
        "site_side": SiteSide.other,
        "gps_lat": 24.711,
        "gps_lng": 46.675,
    },
]


def _airside(area: AirsideArea, movement: bool, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict.fromkeys(AIRSIDE_FIELDS)
    base.update(
        airside_area=area,
        in_movement_area=movement,
        security_restricted_area=True,
        notam_required_for_works=True,
        escort_required=True,
        adp_required=True,
        fod_control_required=True,
    )
    base.update(kw)
    return base


ZONES: list[dict[str, Any]] = [
    {
        "site": ("ANIA-EXP", "S-AIR"),
        "code": "Z-APR-21",
        "name_en": "Apron Stands 21–28",
        "name_ar": "ساحة الوقوف 21–28",
        "zone_type": ZoneType.airside,
        "attrs": _airside(
            AirsideArea.apron,
            True,
            max_equipment_height_m_agl=12.0,
            works_safety_plan_ref="WSP-APR-004",
        ),
    },
    {
        "site": ("ANIA-EXP", "S-AIR"),
        "code": "Z-TWB",
        "name_en": "Taxiway B Strip",
        "name_ar": "شريط الممر B",
        "zone_type": ZoneType.airside,
        "attrs": _airside(
            AirsideArea.taxiway_strip,
            True,
            ols_height_limit_m_amsl=642.5,
            max_equipment_height_m_agl=6.0,
        ),
    },
    {
        "site": ("ANIA-EXP", "S-AIR"),
        "code": "Z-ILS33R",
        "name_en": "RWY 33R Glide Path Critical Area",
        "name_ar": "المنطقة الحرجة لمسار الانزلاق 33R",
        "zone_type": ZoneType.airside,
        "attrs": _airside(
            AirsideArea.ils_critical, False, runway_ref="15L/33R", max_equipment_height_m_agl=3.0
        ),
    },
    {
        "site": ("ANIA-EXP", "S-LAND"),
        "code": "Z-PIERB",
        "name_en": "Pier B Structure",
        "name_ar": "هيكل الرصيف B",
        "zone_type": ZoneType.landside,
    },
    {
        "site": ("ANIA-EXP", "S-LAND"),
        "code": "Z-MSCP",
        "name_en": "Multi-Storey Car Park",
        "name_ar": "مواقف السيارات متعددة الطوابق",
        "zone_type": ZoneType.landside,
    },
    {
        "site": ("ANIA-EXP", "S-LAND"),
        "code": "Z-LAY1",
        "name_en": "Contractor Laydown Yard 1",
        "name_ar": "ساحة تخزين المقاولين 1",
        "zone_type": ZoneType.other,
    },
    {
        "site": ("RBT-52", "S-TWR"),
        "code": "Z-CORE",
        "name_en": "Tower Core L1–L52",
        "name_ar": "قلب البرج ط1–ط52",
        "zone_type": ZoneType.other,
    },
    {
        "site": ("RBT-52", "S-TWR"),
        "code": "Z-TC01",
        "name_en": "Tower Crane TC-01 Exclusion Zone",
        "name_ar": "منطقة حظر الرافعة البرجية TC-01",
        "zone_type": ZoneType.other,
    },
    {
        "site": ("RBT-52", "S-POD"),
        "code": "Z-B4",
        "name_en": "Basement Excavation B1–B4",
        "name_ar": "حفريات القبو ق1–ق4",
        "zone_type": ZoneType.other,
    },
    {
        "site": ("RBT-52", "S-POD"),
        "code": "Z-FAC",
        "name_en": "Facade Hoist Zone",
        "name_ar": "منطقة رافعة الواجهات",
        "zone_type": ZoneType.other,
    },
]

CONTRACTORS: list[dict[str, Any]] = [
    {
        "short_code": "RAWABI",
        "legal_name_en": "Al-Rawabi Construction Co.",
        "legal_name_ar": "شركة الروابي للمقاولات",
        "cr_number": "1010000001",
        "contractor_category": ContractorCategory.civil,
        "status": ContractorStatus.approved,
        "contact": ("Ahmed Al-Zahrani", "+966500000101", "rawabi.hse@example.com"),
        "cr_expiry_date": date(2027, 6, 30),
        "engagement": (
            "ANIA-EXP",
            1,
            None,
            ["S-AIR", "S-LAND"],
            "Main civil works contractor",
            "المقاول الرئيسي للأعمال المدنية",
            date(2025, 3, 1),
        ),
    },
    {
        "short_code": "NAJD",
        "legal_name_en": "Najd Steel Erection Est.",
        "legal_name_ar": "مؤسسة نجد لتركيب الحديد",
        "cr_number": "1010000002",
        "contractor_category": ContractorCategory.steel,
        "status": ContractorStatus.approved,
        "contact": ("Ramesh Kumar", "+966500000102", "najd.hse@example.com"),
        "cr_expiry_date": date(2027, 1, 31),
        "engagement": (
            "ANIA-EXP",
            2,
            "RAWABI",
            ["S-LAND"],
            "Structural steel erection, Pier B",
            "تركيب الهياكل الحديدية، الرصيف B",
            date(2025, 5, 1),
        ),
    },
    {
        "short_code": "GULFPAVE",
        "legal_name_en": "Gulf Airfield Paving Co.",
        "legal_name_ar": "شركة الخليج لرصف المطارات",
        "cr_number": "1010000003",
        "contractor_category": ContractorCategory.airfield,
        "status": ContractorStatus.approved,
        "contact": ("Majed Al-Shehri", "+966500000103", "gulfpave.hse@example.com"),
        "cr_expiry_date": date(2026, 10, 30),
        "engagement": (
            "ANIA-EXP",
            2,
            "RAWABI",
            ["S-AIR"],
            "Apron and taxiway pavement works",
            "أعمال رصف الساحات والممرات",
            date(2025, 4, 15),
        ),
    },
    {
        "short_code": "SAHARA",
        "legal_name_en": "Sahara Scaffolding Services",
        "legal_name_ar": "شركة الصحراء لخدمات السقالات",
        "cr_number": "1010000004",
        "contractor_category": ContractorCategory.scaffolding,
        "status": ContractorStatus.approved,
        "contact": ("Bilal Hussain", "+966500000104", "sahara.hse@example.com"),
        "cr_expiry_date": None,
        "engagement": (
            "ANIA-EXP",
            3,
            "NAJD",
            ["S-LAND"],
            "Scaffolding for steel erection",
            "السقالات لأعمال تركيب الحديد",
            date(2025, 6, 1),
        ),
    },
    {
        "short_code": "QIMMA",
        "legal_name_en": "Al-Qimma Towers Contracting",
        "legal_name_ar": "شركة القمة لمقاولات الأبراج",
        "cr_number": "1010000005",
        "contractor_category": ContractorCategory.civil,
        "status": ContractorStatus.approved,
        "contact": ("Yousef Al-Ghamdi", "+966500000105", "qimma.hse@example.com"),
        "cr_expiry_date": date(2027, 3, 31),
        "engagement": (
            "RBT-52",
            1,
            None,
            ["S-TWR", "S-POD"],
            "Main contractor, tower and podium",
            "المقاول الرئيسي للبرج والمنصة",
            date(2025, 1, 15),
        ),
    },
    {
        "short_code": "DLIFT",
        "legal_name_en": "Desert Lift Crane Services",
        "legal_name_ar": "مؤسسة رافعات الصحراء",
        "cr_number": "1010000006",
        "contractor_category": ContractorCategory.lifting,
        "status": ContractorStatus.suspended,
        "status_reason": "TPI certificate lapsed — test data",
        "contact": ("Saeed Al-Dosari", "+966500000106", "dlift.hse@example.com"),
        "cr_expiry_date": date(2026, 12, 31),
        "engagement": (
            "RBT-52",
            2,
            "QIMMA",
            ["S-TWR"],
            "Tower crane supply and operation",
            "توريد وتشغيل الرافعات البرجية",
            date(2025, 3, 1),
        ),
    },
]

# (email, name_en, name_ar, mobile, employer contractor code | employer type, job, roles)
# roles: (role, project code | None, site codes, engagement contractor code | None)
USERS: list[dict[str, Any]] = [
    {
        "email": "faisal.harbi@example.com",
        "name": ("Faisal Al-Harbi", "فيصل الحربي"),
        "mobile": "+966500000001",
        "employer": EmployerType.client,
        "job": "HSE Manager",
        "roles": [(Role.hse_manager, None, [], None)],
    },
    {
        "email": "noura.qahtani@example.com",
        "name": ("Noura Al-Qahtani", "نورة القحطاني"),
        "mobile": "+966500000002",
        "employer": EmployerType.pmc_consultant,
        "job": "HSE Officer",
        "roles": [(Role.hse_officer, "ANIA-EXP", [], None)],
    },
    {
        "email": "omar.siddiqui@example.com",
        "name": ("Omar Siddiqui", "عمر صديقي"),
        "mobile": "+966500000003",
        "employer": "RAWABI",
        "job": "Site Engineer",
        "roles": [(Role.site_engineer, "ANIA-EXP", ["S-AIR"], None)],
    },
    {
        "email": "khalid.otaibi@example.com",
        "name": ("Khalid Al-Otaibi", "خالد العتيبي"),
        "mobile": "+966500000004",
        "employer": EmployerType.client,
        "job": "Permit Issuer",
        "roles": [(Role.permit_issuer, "ANIA-EXP", [], None)],
    },
    {
        "email": "ramesh.kumar@example.com",
        "name": ("Ramesh Kumar", "راميش كومار"),
        "mobile": "+966500000005",
        "employer": "NAJD",
        "job": "Supervisor",
        "roles": [(Role.permit_receiver, "ANIA-EXP", [], "NAJD")],
    },
    {
        "email": "ahmed.zahrani@example.com",
        "name": ("Ahmed Al-Zahrani", "أحمد الزهراني"),
        "mobile": "+966500000006",
        "employer": "RAWABI",
        "job": "Contractor HSE Rep",
        "roles": [(Role.contractor_hse_rep, "ANIA-EXP", [], "RAWABI")],
    },
    {
        "email": "sarah.mitchell@example.com",
        "name": ("Sarah Mitchell", "سارة ميتشل"),
        "mobile": "+966500000007",
        "employer": EmployerType.client,
        "job": "Client Representative",
        "roles": [
            (Role.viewer_client, "ANIA-EXP", [], None),
            (Role.viewer_client, "RBT-52", [], None),
        ],
    },
    {
        "email": "yousef.ghamdi@example.com",
        "name": ("Yousef Al-Ghamdi", "يوسف الغامدي"),
        "mobile": "+966500000008",
        "employer": "QIMMA",
        "job": "Contractor HSE Rep",
        "roles": [(Role.contractor_hse_rep, "RBT-52", [], "QIMMA")],
    },
]


def _vat(i: int) -> str:
    return f"3{i:013d}3"


def seed(db: Session, password: str) -> None:
    current = now()
    projects: dict[str, Project] = {}
    for spec in PROJECTS:
        data = {k: v for k, v in spec.items() if k != "settings"}
        proj = db.scalar(select(Project).where(Project.code == spec["code"]))
        if proj is None:
            proj = Project(id=uuid.uuid4(), status=ProjectStatus.active, **data)
            proj.search_text = search_blob(
                proj.code,
                proj.name_en,
                proj.name_ar,
                proj.client_name_en,
                proj.client_name_ar,
                proj.city,
            )
            db.add(proj)
            db.flush()
            db.add(
                ProjectSettings(
                    project_id=proj.id, saved_at=current, updated_at=current, **spec["settings"]
                )
            )
        projects[proj.code] = proj
    db.flush()

    sites: dict[tuple[str, str], Site] = {}
    for spec in SITES:
        proj = projects[spec["project"]]
        site = db.scalar(select(Site).where(Site.project_id == proj.id, Site.code == spec["code"]))
        if site is None:
            data = {k: v for k, v in spec.items() if k != "project"}
            site = Site(id=uuid.uuid4(), project_id=proj.id, status=SiteStatus.active, **data)
            site.search_text = search_blob(site.code, site.name_en, site.name_ar)
            db.add(site)
            db.flush()
        sites[(spec["project"], spec["code"])] = site

    for spec in ZONES:
        site = sites[spec["site"]]
        if db.scalar(select(Zone.id).where(Zone.site_id == site.id, Zone.code == spec["code"])):
            continue
        zone = Zone(
            id=uuid.uuid4(),
            project_id=site.project_id,
            site_id=site.id,
            code=spec["code"],
            name_en=spec["name_en"],
            name_ar=spec["name_ar"],
            zone_type=spec["zone_type"],
            status=ZoneStatus.active,
            **spec.get("attrs", dict.fromkeys(AIRSIDE_FIELDS)),
        )
        zone.search_text = search_blob(zone.code, zone.name_en, zone.name_ar)
        db.add(zone)
    db.flush()

    contractors: dict[str, Contractor] = {}
    for i, spec in enumerate(CONTRACTORS, start=1):
        c = db.scalar(select(Contractor).where(Contractor.short_code == spec["short_code"]))
        if c is None:
            name, mobile, email = spec["contact"]
            c = Contractor(
                id=uuid.uuid4(),
                short_code=spec["short_code"],
                legal_name_en=spec["legal_name_en"],
                legal_name_ar=spec["legal_name_ar"],
                legal_name_en_norm=normalize(spec["legal_name_en"]),
                legal_name_ar_norm=normalize(spec["legal_name_ar"]),
                cr_number=spec["cr_number"],
                cr_expiry_date=spec["cr_expiry_date"],
                vat_number=_vat(i),
                contractor_category=spec["contractor_category"],
                primary_contact_name=name,
                primary_contact_mobile=mobile,
                primary_contact_email=email,
                status=spec["status"],
                status_reason=spec.get("status_reason"),
                cr_alerts={},
            )
            c.search_text = search_blob(c.short_code, c.cr_number, c.legal_name_en, c.legal_name_ar)
            db.add(c)
            db.flush()
        contractors[c.short_code] = c

    engagements: dict[str, ProjectEngagement] = {}
    for spec in CONTRACTORS:  # parents are listed before children
        c = contractors[spec["short_code"]]
        pcode, tier, parent_code, site_codes, scope_en, scope_ar, mob = spec["engagement"]
        proj = projects[pcode]
        e = db.scalar(
            select(ProjectEngagement).where(
                ProjectEngagement.project_id == proj.id, ProjectEngagement.contractor_id == c.id
            )
        )
        if e is None:
            parent = engagements[parent_code] if parent_code else None
            e = ProjectEngagement(
                id=uuid.uuid4(),
                project_id=proj.id,
                contractor_id=c.id,
                tier=tier,
                parent_engagement_id=parent.id if parent else None,
                scope_of_work_en=scope_en,
                scope_of_work_ar=scope_ar,
                site_ids=[sites[(pcode, s)].id for s in site_codes],
                mobilisation_date=mob,
                parent_blacklisted=False,
            )
            e.root_engagement_id = (parent.root_engagement_id if parent else None) or (
                parent.id if parent else e.id
            )
            db.add(e)
            db.flush()
        engagements[c.short_code] = e

    pw_hash = hash_password(password)
    version = get_settings().privacy_notice_version
    for spec in USERS:
        user = db.scalar(select(User).where(User.email == spec["email"]))
        if user is None:
            employer = spec["employer"]
            is_contractor = isinstance(employer, str) and employer in contractors
            name_en, name_ar = spec["name"]
            user = User(
                id=uuid.uuid4(),
                email=spec["email"],
                full_name_en=name_en,
                full_name_ar=name_ar,
                mobile=spec["mobile"],
                employer_type=EmployerType.contractor if is_contractor else employer,
                employer_contractor_id=contractors[employer].id if is_contractor else None,
                job_title=spec["job"],
                preferred_language=Language.en,
                status=UserStatus.active,
                password_hash=pw_hash,
                activated_at=current,
                privacy_notice_version=version,
                privacy_notice_ack_at=current,
                search_text=search_blob(name_en, name_ar, spec["email"]),
            )
            db.add(user)
            db.flush()
        for role, pcode, site_codes, eng_code in spec["roles"]:
            pid = projects[pcode].id if pcode else None
            exists = db.scalar(
                select(RoleAssignment.id).where(
                    RoleAssignment.user_id == user.id,
                    RoleAssignment.role == role,
                    RoleAssignment.project_id == pid
                    if pid
                    else RoleAssignment.project_id.is_(None),
                )
            )
            if exists:
                continue
            db.add(
                RoleAssignment(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    role=role,
                    project_id=pid,
                    site_ids=[sites[(pcode, s)].id for s in site_codes],
                    contractor_engagement_id=engagements[eng_code].id if eng_code else None,
                    valid_from=VALID_FROM,
                    created_at=current,
                )
            )
    db.flush()
    seed_settings(db)


def main() -> int:
    password = get_settings().seed_password
    if not password:
        print("Set SEED_PASSWORD (see .env.example).", file=sys.stderr)
        return 2
    problems = password_problems(password, "seed@example.com")
    if problems:
        print("SEED_PASSWORD " + "; ".join(problems), file=sys.stderr)
        return 2
    with get_sessionmaker()() as db:
        seed(db, password)
        db.commit()
        seed_data(db)
        db.commit()
        seed_access_data(db)
        db.commit()
        from app.seed_ptw import seed_ptw_data  # noqa: PLC0415

        seed_ptw_data(db, password)
        db.commit()
    print("Seed data loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
