"""Phase 2 demo seed (spec 2-access-permits Appendix A; fictional, `seed_fake = true`).

`seed_access_reference` (courses, pass categories/areas, zone profiles, hooks, settings, gates and
devices) is cheap and idempotent. `seed_access_data` loads the volume data (workers,
deployments, induction history, passes, ADPs, vehicles, NOTAMs, obstacle clearances, WAPs, ops
events, gate log) and runs once (skipped when seeded workers exist). Both run from
``python -m app.seed`` after the Phase 1 seed; tests load them through the ``access_seed``
fixture.

Fixture state is "as of 2026-10-06" (KPI month Sep 2026 ends 2026-09-30, §6.10). The A.1.4 rule
"passed GEN records = daily-return Σ inductions" is met by rewriting the Phase 1 daily-return
`inductions` field from the GEN register (DECISIONS: the A.1.3 GEN volume cannot be reached from
the Phase 1 daily-return numbers).
"""

import random
import secrets
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import Table, bindparam, insert, select, update
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.access_enums import (
    AreaCategory,
    BackgroundCheckStatus,
    CardColour,
    ClearanceReason,
    CredentialAction,
    CredentialKind,
    CredentialReason,
    CrewMemberStatus,
    CrewRole,
    CustodyStatus,
    DeploymentStatus,
    GateDirection,
    GateResult,
    GateSubjectKind,
    GateType,
    HookKind,
    InductionResult,
    InductionStatus,
    InductionType,
    InspectionResult,
    LicenceClass,
    LicenceIssuer,
    NotamStatus,
    NotamType,
    ObstacleCondition,
    ObstacleDecision,
    ObstacleEquipmentType,
    ObstacleStatus,
    OffenceStatus,
    OlsSurface,
    OpsEventSource,
    OpsEventType,
    PassApplicationStatus,
    PassApplicationType,
    PassAreaKind,
    PlateType,
    PracticalTestResult,
    QrKind,
    QrTokenStatus,
    SuspensionState,
    ValidityStatus,
    VehicleCategory,
    VehicleClass,
    VehicleOwnerType,
    VehicleStatus,
    WapStatus,
    WorkerIdType,
    WorkerLanguage,
    WorkerPersonType,
    WorkerStatus,
    WorksImpact,
)
from app.core.clock import frozen
from app.core.enums import Role
from app.core.hse_enums import Trade
from app.core.security import token_digest
from app.core.text import search_blob
from app.kpi.periods import add_months, month_end
from app.models import (
    Adp,
    AirportPass,
    Avp,
    Contractor,
    CredentialEvent,
    Deployment,
    Gate,
    GateDevice,
    Incident,
    InductionCourse,
    InductionRecord,
    InjuryCase,
    NotamRequest,
    ObstacleClearance,
    Offence,
    OpsEvent,
    PassApplication,
    PassArea,
    PassCategory,
    Project,
    ProjectEngagement,
    QrToken,
    Site,
    User,
    Vehicle,
    Wap,
    WapCrew,
    WapVehicle,
    Worker,
    WorkforceReturn,
    Zone,
)
from app.services import hse_settings
from app.services.access import common, lifecycle, profiles
from app.services.hse_common import make_ref

RIYADH = ZoneInfo("Asia/Riyadh")
AS_OF = date(2026, 9, 30)  # KPI fixture month end (X6-X10)
TODAY = date(2026, 10, 6)  # acceptance-criteria "today" (§9)
AT_TODAY = datetime(2026, 10, 6, 7, 0, tzinfo=UTC)  # 10:00 local
PN = "WPN-1.0"
L = WorkerLanguage
T = Trade
IT = WorkerIdType
C = InductionType

# ---- reference lists (A.2) -----------------------------------------------------------------------

ALL_LANGS = [x.value for x in (L.ar, L.en, L.ur, L.hi, L.bn, L.ne, L.tl, L.ml, L.ta)]
OFFICER_REP = [Role.hse_officer.value, Role.contractor_hse_rep.value]
OFFICER = [Role.hse_officer.value]

# project, code, type, en, ar, version, months, days, pass mark, prereq, delivered by, minutes
COURSES: list[tuple[Any, ...]] = [
    (
        "ANIA-EXP",
        "GEN",
        C.general_site,
        "General Site HSE Induction",
        "التعريف العام بالسلامة في الموقع",
        "3.1",
        12,
        None,
        80,
        [],
        OFFICER_REP,
        90,
    ),
    (
        "ANIA-EXP",
        "AIR",
        C.airside,
        "Airside Safety & FOD Awareness",
        "السلامة في الجانب الجوي والتوعية بالأجسام الغريبة",
        "2.0",
        12,
        None,
        80,
        ["GEN"],
        OFFICER,
        60,
    ),
    (
        "ANIA-EXP",
        "ILS",
        C.zone_specific,
        "ILS Critical/Sensitive Area Briefing",
        "إحاطة المناطق الحرجة والحساسة لنظام ILS",
        "1.0",
        6,
        None,
        90,
        ["AIR"],
        OFFICER,
        30,
    ),
    (
        "ANIA-EXP",
        "VIS",
        C.visitor,
        "Visitor Safety Briefing",
        "إحاطة السلامة للزوار",
        "1.0",
        None,
        1,
        None,
        [],
        OFFICER,
        15,
    ),
    (
        "RBT-52",
        "GEN",
        C.general_site,
        "General Site HSE Induction",
        "التعريف العام بالسلامة في الموقع",
        "2.4",
        12,
        None,
        80,
        [],
        OFFICER_REP,
        90,
    ),
    (
        "RBT-52",
        "TC",
        C.zone_specific,
        "Tower Crane Exclusion Zone Briefing",
        "إحاطة منطقة حظر الرافعة البرجية",
        "1.2",
        12,
        None,
        80,
        ["GEN"],
        OFFICER_REP,
        30,
    ),
]

AVSEC = [{"kind": HookKind.training_course.value, "code": "AVSEC-AWR", "trades": []}]
# code, en, ar, escorted, bg, days, colour, adp, hooks
PASS_CATEGORIES: list[tuple[Any, ...]] = [
    (
        "PERM",
        "Permanent Airport ID",
        "تصريح مطار دائم",
        False,
        True,
        730,
        CardColour.red,
        True,
        AVSEC,
    ),
    (
        "TEMP-U",
        "Temporary Unescorted",
        "تصريح مؤقت دون مرافقة",
        False,
        True,
        90,
        CardColour.blue,
        True,
        AVSEC,
    ),
    (
        "TEMP-E",
        "Temporary Escorted",
        "تصريح مؤقت بمرافقة",
        True,
        False,
        30,
        CardColour.yellow,
        False,
        [],
    ),
    ("VIS", "Visitor Escorted", "تصريح زائر بمرافقة", True, False, 1, CardColour.white, False, []),
]
PASS_AREAS: list[tuple[Any, ...]] = [
    (
        "A",
        "Apron & Stands",
        "الساحات ومواقف الطائرات",
        CardColour.red,
        PassAreaKind.apron,
        ["Z-APR-21"],
    ),
    (
        "M",
        "Manoeuvring Area",
        "منطقة المناورة",
        CardColour.yellow,
        PassAreaKind.manoeuvring,
        ["Z-TWB", "Z-ILS33R"],
    ),
    (
        "T",
        "Terminal Airside",
        "الجانب الجوي للمبنى",
        CardColour.blue,
        PassAreaKind.terminal_airside,
        [],
    ),
    (
        "R",
        "Airside Service Roads",
        "طرق الخدمة الجوية",
        CardColour.orange,
        PassAreaKind.airside_roads,
        [],
    ),
]
# zone → (inductions, pass area, WAP, ADP, AVP, escort ratio, LVP, ILS NOTAM, hooks)
PROFILES: dict[str, tuple[Any, ...]] = {
    "Z-APR-21": (
        ["GEN", "AIR"],
        "A",
        True,
        AreaCategory.apron,
        AreaCategory.apron,
        5,
        False,
        False,
        AVSEC,
    ),
    "Z-TWB": (
        ["GEN", "AIR"],
        "M",
        True,
        AreaCategory.manoeuvring,
        AreaCategory.manoeuvring,
        2,
        True,
        False,
        AVSEC,
    ),
    "Z-ILS33R": (
        ["GEN", "AIR", "ILS"],
        "M",
        True,
        AreaCategory.manoeuvring,
        AreaCategory.manoeuvring,
        2,
        True,
        True,
        AVSEC,
    ),
    "Z-PIERB": (["GEN"], None, False, None, None, None, False, False, []),
    "Z-MSCP": (["GEN"], None, False, None, None, None, False, False, []),
    "Z-LAY1": (["GEN"], None, False, None, None, None, False, False, []),
    "Z-CORE": (["GEN"], None, False, None, None, None, False, False, []),
    "Z-B4": (["GEN"], None, False, None, None, None, False, False, []),
    "Z-FAC": (["GEN"], None, False, None, None, None, False, False, []),
    "Z-TC01": (
        ["GEN", "TC"],
        None,
        False,
        None,
        None,
        None,
        False,
        False,
        [
            {
                "kind": HookKind.personnel_certificate.value,
                "code": "CRANE-OPERATOR",
                "trades": [T.crane_operator.value],
            },
            {
                "kind": HookKind.personnel_certificate.value,
                "code": "RIGGER",
                "trades": [T.rigger.value],
            },
        ],
    ),
}
VEHICLE_HOOKS = {
    "mobile_crane": "CRANE-TPI",
    "crawler_crane": "CRANE-TPI",
    "mewp": "MEWP-TPI",
    "forklift": "FORKLIFT-TPI",
    "telehandler": "TELEHANDLER-TPI",
}
ADP_HOOKS = {
    c: [{"kind": HookKind.training_course.value, "code": "AIRSIDE-DRV", "trades": []}]
    for c in ("manoeuvring", "apron")
}
REGISTER_FROM = {"ANIA-EXP": date(2025, 3, 1), "RBT-52": date(2025, 1, 15)}
# code, en, ar, type, site, zones
GATES: list[tuple[Any, ...]] = [
    (
        "ANIA-EXP",
        "G-ANIA-01",
        "Main Construction Gate",
        "البوابة الرئيسية للإنشاءات",
        GateType.site_gate,
        "S-LAND",
        [],
    ),
    (
        "ANIA-EXP",
        "G-AAP3",
        "Contractor Airside Access Point 3",
        "نقطة دخول المقاولين للجانب الجوي 3",
        GateType.airside_precheck,
        "S-AIR",
        ["Z-APR-21", "Z-TWB", "Z-ILS33R"],
    ),
    ("RBT-52", "G-RBT-01", "Tower Site Gate", "بوابة موقع البرج", GateType.site_gate, "S-TWR", []),
    (
        "RBT-52",
        "G-RBT-TC",
        "Tower Crane Zone Entry",
        "مدخل منطقة الرافعة البرجية",
        GateType.zone_entry,
        "S-TWR",
        ["Z-TC01"],
    ),
]


def _users(db: Session) -> dict[str, User]:
    return {u.email.split("@")[0]: u for u in db.scalars(select(User))}


def _projects(db: Session) -> dict[str, Project]:
    return {p.code: p for p in db.scalars(select(Project))}


def _zones(db: Session, pid: uuid.UUID) -> dict[str, Zone]:
    return {z.code: z for z in db.scalars(select(Zone).where(Zone.project_id == pid))}


def _sites(db: Session, pid: uuid.UUID) -> dict[str, Site]:
    return {s.code: s for s in db.scalars(select(Site).where(Site.project_id == pid))}


def _engs(db: Session, pid: uuid.UUID) -> dict[str, ProjectEngagement]:
    return {
        c.short_code: e
        for e, c in db.execute(
            select(ProjectEngagement, Contractor)
            .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
            .where(ProjectEngagement.project_id == pid)
        )
    }


def seed_access_reference(db: Session) -> None:
    """A.2 lists, zone profiles, hook settings, gates and devices (idempotent)."""
    projects = _projects(db)
    users = _users(db)
    manager = users.get("faisal.harbi")
    for code, proj in projects.items():
        s = common.settings(db, proj.id)
        hs = hse_settings.get(db, proj.id)
        if hs.induction_register_from is None and code in REGISTER_FROM:
            hs.induction_register_from = REGISTER_FROM[code]
        if code == "ANIA-EXP" and not s.hook_requirements_by_adp_category:
            s.hook_requirements_by_adp_category = ADP_HOOKS
            s.hook_requirements_by_vehicle_category = {
                k: [{"kind": HookKind.equipment_certificate.value, "code": v, "trades": []}]
                for k, v in VEHICLE_HOOKS.items()
            }
        zones = _zones(db, proj.id)
        for z in zones.values():
            prof = profiles.ensure(db, z)
            spec = PROFILES.get(z.code)
            if spec is None or prof.updated_by_user_id is not None:
                continue
            ind, area, wap, adp, avp, ratio, lvp, ils, hooks = spec
            prof.required_inductions = ind
            prof.airport_pass_area_code = area
            prof.access_permit_required = wap
            prof.adp_category_required = adp
            prof.avp_area_required = avp
            prof.escort_ratio_max = ratio
            prof.lvp_withdrawal_required = lvp
            prof.ils_outage_notam_required = ils
            prof.hook_requirements = hooks
            prof.updated_by_user_id = manager.id if manager else None
    have = {
        (pid, c) for pid, c in db.execute(select(InductionCourse.project_id, InductionCourse.code))
    }
    for pcode, code, ctype, en, ar, ver, months, days, mark, prereq, by, mins in COURSES:
        cproj = projects.get(pcode)
        if cproj is None or (cproj.id, code) in have:
            continue
        db.add(
            InductionCourse(
                id=uuid.uuid4(),
                project_id=cproj.id,
                code=code,
                induction_type=ctype,
                name_en=en,
                name_ar=ar,
                version=ver,
                version_published_on=date(2025, 1, 1),
                requires_reinduction=False,
                validity_months=months,
                validity_days=days,
                min_duration_minutes=mins,
                test_required=mark is not None,
                pass_mark_pct=mark,
                languages_offered=ALL_LANGS,
                prerequisite_codes=prereq,
                delivered_by_roles=by,
                active=True,
                seed_fake=True,
            )
        )
    ania = projects.get("ANIA-EXP")
    if ania is not None:
        zones = _zones(db, ania.id)
        cats = set(db.scalars(select(PassCategory.code).where(PassCategory.project_id == ania.id)))
        for code, en, ar, esc, bg, days, colour, adp, hooks in PASS_CATEGORIES:
            if code not in cats:
                db.add(
                    PassCategory(
                        id=uuid.uuid4(),
                        project_id=ania.id,
                        code=code,
                        name_en=en,
                        name_ar=ar,
                        escorted=esc,
                        background_check_required=bg,
                        max_validity_days=days,
                        card_colour=colour,
                        allows_adp=adp,
                        hook_requirements=hooks,
                        active=True,
                        seed_fake=True,
                    )
                )
        areas = set(db.scalars(select(PassArea.code).where(PassArea.project_id == ania.id)))
        for code, en, ar, colour, kind, zcodes in PASS_AREAS:
            if code not in areas:
                db.add(
                    PassArea(
                        id=uuid.uuid4(),
                        project_id=ania.id,
                        code=code,
                        name_en=en,
                        name_ar=ar,
                        colour=colour,
                        area_kind=kind,
                        zone_ids=[zones[z].id for z in zcodes if z in zones],
                        active=True,
                        seed_fake=True,
                    )
                )
    gates = {g.gate_code for g in db.scalars(select(Gate))}
    n = 0
    for pcode, code, en, ar, gtype, site_code, zcodes in GATES:
        gproj = projects.get(pcode)
        if gproj is None:
            continue
        n += 2
        if code in gates:
            continue
        sites, zones = _sites(db, gproj.id), _zones(db, gproj.id)
        g = Gate(
            id=uuid.uuid4(),
            project_id=gproj.id,
            gate_code=code,
            name_en=en,
            name_ar=ar,
            site_id=sites[site_code].id,
            protected_zone_ids=[zones[z].id for z in zcodes],
            gate_type=gtype,
            created_by_user_id=manager.id if manager else None,
            seed_fake=True,
        )
        db.add(g)
        db.flush()
        for k in (n - 1, n):
            db.add(
                GateDevice(
                    id=uuid.uuid4(),
                    gate_id=g.id,
                    device_id=f"GATE-TAB-{k:02d}",
                    label=f"Gate tablet {k:02d} (seed)",
                    token_hash=token_digest(secrets.token_urlsafe(32)),
                    registered_by_user_id=manager.id if manager else None,
                    seed_fake=True,
                )
            )
    db.flush()


# ---- worker plans (A.1, A.3) ---------------------------------------------------------------------


@dataclass
class Plan:
    seq: int
    en: str
    ar: str
    nat: str
    id_type: WorkerIdType
    id_no: str
    id_exp: date
    lang: WorkerLanguage
    project: str
    eng: str | None
    trade: Trade
    sites: list[str]
    mob: date
    demob: date | None = None
    person_type: WorkerPersonType = WorkerPersonType.contractor_worker
    user: str | None = None
    airside: bool = False
    named: bool = False
    # (course, delivered, valid_until, status, attempt, result, score)
    inductions: list[tuple[str, date, date | None, InductionStatus, int, bool, int | None]] = field(
        default_factory=list
    )
    wid: uuid.UUID = field(default_factory=uuid.uuid4)
    did: uuid.UUID = field(default_factory=uuid.uuid4)
    areas: list[str] = field(default_factory=list)

    @property
    def no(self) -> str:
        return f"WKR-{self.seq:06d}"


V = InductionStatus.valid
X = InductionStatus.expired
S = InductionStatus.superseded


def _vu(d: date, months: int) -> date:
    return add_months(d, months) - timedelta(days=1)


def _gen(
    *dates: date, last: InductionStatus = V, months: int = 12, code: str = "GEN"
) -> list[tuple[str, date, date | None, InductionStatus, int, bool, int | None]]:
    """A chain of passed records; all but the last superseded."""
    out: list[tuple[str, date, date | None, InductionStatus, int, bool, int | None]] = []
    for i, d in enumerate(dates):
        out.append((code, d, _vu(d, months), S if i < len(dates) - 1 else last, 1, True, 88))
    return out


def _named() -> list[Plan]:
    d = date
    P = Plan  # noqa: N806
    out = [
        P(
            1,
            "Imran Hussain",
            "عمران حسين",
            "PK",
            IT.iqama,
            "2000000017",
            d(2027, 8, 31),
            L.ur,
            "ANIA-EXP",
            "NAJD",
            T.scaffolder,
            ["S-LAND"],
            d(2026, 8, 25),
            inductions=_gen(d(2026, 8, 25)),
        ),
        P(
            2,
            "Rajesh Nair",
            "راجيش ناير",
            "IN",
            IT.iqama,
            "2000001002",
            d(2027, 3, 14),
            L.hi,
            "ANIA-EXP",
            "GULFPAVE",
            T.plant_operator,
            ["S-AIR"],
            d(2025, 5, 25),
            airside=True,
            inductions=_gen(d(2025, 5, 25), d(2026, 1, 12)) + _gen(d(2026, 1, 13), code="AIR"),
            areas=["A", "M"],
        ),
        P(
            3,
            "Jomar Santos",
            "جومار سانتوس",
            "PH",
            IT.iqama,
            "2000001003",
            d(2027, 7, 10),
            L.tl,
            "ANIA-EXP",
            "GULFPAVE",
            T.driver,
            ["S-AIR"],
            d(2025, 5, 4),
            airside=True,
            inductions=_gen(d(2025, 5, 4), d(2026, 2, 20)) + _gen(d(2026, 2, 21), code="AIR"),
            areas=["A"],
        ),
        P(
            4,
            "Abdul Karim Mia",
            "عبد الكريم ميا",
            "BD",
            IT.iqama,
            "2000001004",
            d(2027, 11, 30),
            L.bn,
            "ANIA-EXP",
            "GULFPAVE",
            T.labourer,
            ["S-AIR"],
            d(2025, 10, 12),
            airside=True,
            inductions=_gen(d(2025, 10, 12), d(2026, 2, 1)) + _gen(d(2025, 10, 14), code="AIR"),
            areas=["A", "M"],
        ),
        P(
            5,
            "Mahmoud Fathy",
            "محمود فتحي",
            "EG",
            IT.iqama,
            "2000001005",
            d(2028, 1, 20),
            L.ar,
            "ANIA-EXP",
            "RAWABI",
            T.supervisor,
            ["S-AIR"],
            d(2025, 4, 1),
            airside=True,
            inductions=_gen(d(2025, 4, 1), d(2026, 3, 10))
            + _gen(d(2026, 3, 11), code="AIR")
            + _gen(d(2026, 6, 16), code="ILS", months=6),
            areas=["A", "M"],
        ),
        P(
            6,
            "Suman Tamang",
            "سومان تامانغ",
            "NP",
            IT.iqama,
            "2000001006",
            d(2027, 5, 5),
            L.ne,
            "ANIA-EXP",
            "RAWABI",
            T.electrician,
            ["S-AIR"],
            d(2025, 10, 1),
            airside=True,
            inductions=_gen(d(2025, 10, 1), last=X) + _gen(d(2026, 2, 15), code="AIR"),
            areas=["A"],
        ),
        P(
            7,
            "Saad Al-Dosari",
            "سعد الدوسري",
            "SA",
            IT.national_id,
            "1000001007",
            d(2030, 2, 11),
            L.ar,
            "ANIA-EXP",
            "RAWABI",
            T.engineer,
            ["S-AIR", "S-LAND"],
            d(2025, 3, 2),
            airside=True,
            inductions=_gen(d(2025, 3, 2), d(2026, 2, 1))
            + _gen(d(2026, 2, 2), code="AIR")
            + _gen(d(2026, 7, 1), code="ILS", months=6),
            areas=["A", "M"],
        ),
        P(
            8,
            "Waleed Saleh",
            "وليد صالح",
            "YE",
            IT.iqama,
            "2000001008",
            d(2027, 1, 25),
            L.ar,
            "ANIA-EXP",
            "SAHARA",
            T.scaffolder,
            ["S-LAND"],
            d(2025, 6, 15),
            inductions=_gen(d(2025, 6, 15), d(2026, 3, 1)),
        ),
        P(
            9,
            "Osman Idris",
            "عثمان إدريس",
            "SD",
            IT.iqama,
            "2000001009",
            d(2026, 10, 20),
            L.ar,
            "ANIA-EXP",
            "NAJD",
            T.rigger,
            ["S-LAND"],
            d(2026, 4, 1),
            inductions=_gen(d(2026, 4, 1)),
        ),
        P(
            10,
            "Arjun Pillai",
            "أرجون بيلاي",
            "IN",
            IT.iqama,
            "2000001010",
            d(2027, 6, 1),
            L.ml,
            "ANIA-EXP",
            "GULFPAVE",
            T.driver,
            ["S-AIR"],
            d(2025, 6, 10),
            d(2026, 9, 20),
            airside=True,
            inductions=_gen(d(2025, 6, 10), d(2026, 1, 5)) + _gen(d(2026, 1, 6), code="AIR"),
            areas=["A", "M"],
        ),
        P(
            11,
            "Noura Al-Qahtani",
            "نورة القحطاني",
            "SA",
            IT.national_id,
            "1000001011",
            d(2031, 4, 2),
            L.ar,
            "ANIA-EXP",
            None,
            T.hse_staff,
            ["S-AIR", "S-LAND"],
            d(2025, 3, 3),
            person_type=WorkerPersonType.client_pmc_staff,
            user="noura.qahtani",
            airside=True,
            inductions=_gen(d(2025, 3, 3), d(2026, 1, 20))
            + _gen(d(2026, 1, 21), code="AIR")
            + _gen(d(2026, 7, 15), code="ILS", months=6),
            areas=["A", "M"],
        ),
        P(
            12,
            "David Brown",
            "ديفيد براون",
            "GB",
            IT.passport,
            "TEST00012",
            d(2033, 8, 14),
            L.en,
            "ANIA-EXP",
            None,
            T.other,
            ["S-AIR"],
            d(2026, 10, 6),
            person_type=WorkerPersonType.visitor,
            airside=True,
            inductions=[("VIS", d(2026, 10, 6), d(2026, 10, 6), V, 1, True, None)],
            areas=["A"],
        ),
        P(
            13,
            "Tariq Mahmood",
            "طارق محمود",
            "PK",
            IT.iqama,
            "2000001013",
            d(2027, 12, 12),
            L.ur,
            "ANIA-EXP",
            "GULFPAVE",
            T.supervisor,
            ["S-AIR"],
            d(2025, 5, 1),
            airside=True,
            inductions=_gen(d(2025, 5, 1), d(2026, 3, 1))
            + _gen(d(2026, 3, 2), code="AIR")
            + _gen(d(2026, 8, 1), code="ILS", months=6),
            areas=["A", "M"],
        ),
        P(
            101,
            "Imtiaz Ahmed",
            "امتياز أحمد",
            "PK",
            IT.iqama,
            "2000001101",
            d(2027, 9, 30),
            L.ur,
            "RBT-52",
            "QIMMA",
            T.steel_fixer,
            ["S-TWR"],
            d(2026, 4, 20),
            inductions=_gen(d(2026, 4, 20)),
        ),
        P(
            102,
            "Ali Hassan",
            "علي حسن",
            "EG",
            IT.iqama,
            "2000001102",
            d(2027, 2, 28),
            L.ar,
            "RBT-52",
            "QIMMA",
            T.crane_operator,
            ["S-TWR"],
            d(2025, 7, 1),
            inductions=_gen(d(2025, 7, 1), d(2026, 5, 10)) + _gen(d(2026, 5, 11), code="TC"),
        ),
        P(
            103,
            "Ramon Cruz",
            "رامون كروز",
            "PH",
            IT.iqama,
            "2000001103",
            d(2027, 8, 8),
            L.tl,
            "RBT-52",
            "QIMMA",
            T.electrician,
            ["S-POD"],
            d(2025, 11, 6),
            inductions=_gen(d(2025, 11, 6)),
        ),
        P(
            104,
            "Bikash Rai",
            "بيكاش راي",
            "NP",
            IT.iqama,
            "2000001104",
            d(2027, 3, 3),
            L.ne,
            "RBT-52",
            "DLIFT",
            T.rigger,
            ["S-TWR"],
            d(2025, 3, 15),
            inductions=_gen(d(2025, 3, 15), d(2026, 1, 10)),
        ),
        P(
            105,
            "Hamza Al-Shehri",
            "حمزة الشهري",
            "SA",
            IT.national_id,
            "1000001105",
            d(2032, 1, 19),
            L.ar,
            "RBT-52",
            "QIMMA",
            T.supervisor,
            ["S-TWR"],
            d(2026, 9, 3),
            inductions=[
                ("GEN", d(2026, 9, 2), None, InductionStatus.failed, 1, False, 65),
                ("GEN", d(2026, 9, 3), d(2027, 9, 2), V, 2, True, 85),
            ],
        ),
    ]
    for p in out:
        p.named = True
    return out


# bulk volumes at 2026-09-30 (A.1.3, named workers included in these counts)
VOLUMES = {
    "ANIA-EXP": {"RAWABI": 1380, "NAJD": 960, "GULFPAVE": 720, "SAHARA": 352},
    "RBT-52": {"QIMMA": 590, "DLIFT": 64},
}
GEN_INVALID = {"RAWABI": 15, "NAJD": 12, "GULFPAVE": 6, "SAHARA": 8, "QIMMA": 10, "DLIFT": 4}
RAWABI_AIRSIDE = 180  # RAWABI S-AIR share of the ≈ 900 airside crew
BULK_TRADES = {
    "RAWABI": [T.labourer, T.carpenter, T.steel_fixer, T.mason, T.electrician],
    "NAJD": [T.steel_erector, T.rigger, T.welder],
    "GULFPAVE": [T.plant_operator, T.labourer, T.flagman, T.driver],
    "SAHARA": [T.scaffolder, T.labourer],
    "QIMMA": [T.labourer, T.carpenter, T.steel_fixer, T.electrician],
    "DLIFT": [T.crane_operator, T.rigger],
}
BULK_SITES = {
    "NAJD": ["S-LAND"],
    "GULFPAVE": ["S-AIR"],
    "SAHARA": ["S-LAND"],
    "QIMMA": ["S-TWR", "S-POD"],
    "DLIFT": ["S-TWR"],
}
# delivery-language mix (A.1.4) → nationalities
LANG_MIX = [(L.ur, 25), (L.hi, 20), (L.bn, 15), (L.ar, 12), (L.ne, 10), (L.tl, 8), (L.en, 10)]
LANG_NAT = {
    L.ur: ["PK"],
    L.hi: ["IN"],
    L.bn: ["BD"],
    L.ar: ["EG", "SA", "YE", "SD", "JO"],
    L.ne: ["NP"],
    L.tl: ["PH"],
    L.en: ["IN", "LK", "KE"],
}
FIRST = {
    "PK": [
        ("Asif", "آصف"),
        ("Bilal", "بلال"),
        ("Naveed", "نويد"),
        ("Shahid", "شاهد"),
        ("Usman", "عثمان"),
        ("Zubair", "زبير"),
    ],
    "IN": [
        ("Anil", "أنيل"),
        ("Vijay", "فيجاي"),
        ("Suresh", "سوريش"),
        ("Manoj", "مانوج"),
        ("Ravi", "رافي"),
        ("Deepak", "ديباك"),
    ],
    "BD": [
        ("Rahim", "رحيم"),
        ("Kamal", "كمال"),
        ("Jamal", "جمال"),
        ("Habib", "حبيب"),
        ("Sohel", "سهيل"),
        ("Rafiq", "رفيق"),
    ],
    "EG": [("Ahmed", "أحمد"), ("Mostafa", "مصطفى"), ("Hany", "هاني"), ("Tamer", "تامر")],
    "SA": [("Fahad", "فهد"), ("Nawaf", "نواف"), ("Turki", "تركي"), ("Majed", "ماجد")],
    "YE": [("Fuad", "فؤاد"), ("Nabil", "نبيل"), ("Adel", "عادل")],
    "SD": [("Mohamed", "محمد"), ("Hassan", "حسن"), ("Babiker", "بابكر")],
    "JO": [("Rami", "رامي"), ("Khaled", "خالد")],
    "NP": [("Ram", "رام"), ("Hari", "هاري"), ("Krishna", "كريشنا"), ("Bishnu", "بيشنو")],
    "PH": [("Mark", "مارك"), ("Jun", "جون"), ("Rodel", "روديل"), ("Arnel", "أرنيل")],
    "LK": [("Nimal", "نيمال"), ("Sunil", "سونيل")],
    "KE": [("Peter", "بيتر"), ("Joseph", "جوزيف")],
}
LAST = {
    "PK": [("Khan", "خان"), ("Iqbal", "إقبال"), ("Butt", "بت"), ("Malik", "مالك")],
    "IN": [("Kumar", "كومار"), ("Singh", "سينغ"), ("Nair", "ناير"), ("Das", "داس")],
    "BD": [("Uddin", "الدين"), ("Hossain", "حسين"), ("Miah", "ميا"), ("Islam", "إسلام")],
    "EG": [("Abdelaziz", "عبدالعزيز"), ("Fawzy", "فوزي"), ("Saleh", "صالح")],
    "SA": [("Al-Otaibi", "العتيبي"), ("Al-Harbi", "الحربي"), ("Al-Mutairi", "المطيري")],
    "YE": [("Al-Saidi", "السعيدي"), ("Qasim", "قاسم")],
    "SD": [("Osman", "عثمان"), ("Abdalla", "عبدالله")],
    "JO": [("Haddad", "حداد"), ("Nasser", "ناصر")],
    "NP": [("Thapa", "ثابا"), ("Gurung", "غورونغ"), ("Shrestha", "شريستا"), ("Magar", "ماغار")],
    "PH": [("Reyes", "رييس"), ("Garcia", "غارسيا"), ("Bautista", "باوتيستا")],
    "LK": [("Perera", "بيريرا"), ("Silva", "سيلفا")],
    "KE": [("Otieno", "أوتينو"), ("Mwangi", "موانغي")],
}


# ---- context and helpers -------------------------------------------------------------------------


@dataclass
class Ctx:
    db: Session
    rng: random.Random
    project: Project
    sites: dict[str, Site]
    zones: dict[str, Zone]
    engs: dict[str, ProjectEngagement]
    users: dict[str, User]
    days: dict[str, list[date]] = field(default_factory=dict)  # eng → working days with returns
    plans: list[Plan] = field(default_factory=list)
    courses: dict[str, InductionCourse] = field(default_factory=dict)
    has_returns: bool = False

    def plan(self, seq: int) -> Plan:
        return next(p for p in self.plans if p.seq == seq)

    def user_id(self, key: str) -> uuid.UUID | None:
        u = self.users.get(key)
        return u.id if u else None


def _at(d: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(d, time(hour % 24, minute), RIYADH).astimezone(UTC)


def _days(start: date, end: date) -> list[date]:
    return (
        [start + timedelta(days=i) for i in range((end - start).days + 1)] if end >= start else []
    )


def _candidate_days(ctx: Ctx) -> None:
    by_id = {e.id: c for c, e in ctx.engs.items()}
    rows: dict[str, set[date]] = defaultdict(set)
    for eid, d in ctx.db.execute(
        select(WorkforceReturn.engagement_id, WorkforceReturn.work_date)
        .where(WorkforceReturn.project_id == ctx.project.id, WorkforceReturn.man_hours > 0)
        .group_by(WorkforceReturn.engagement_id, WorkforceReturn.work_date)
    ):
        if eid in by_id:
            rows[by_id[eid]].add(d)
    ctx.has_returns = bool(rows)
    for code, e in ctx.engs.items():
        days = sorted(rows.get(code, set()))
        if not days:  # no Phase 1 returns: every non-Friday day from mobilisation
            days = [d for d in _days(e.mobilisation_date, AS_OF) if d.weekday() != 4]
        ctx.days[code] = [d for d in days if d <= AS_OF]


def _pick_day(ctx: Ctx, eng: str, lo: date, hi: date) -> date | None:
    days = [d for d in ctx.days.get(eng, []) if lo <= d <= hi]
    if days:
        return ctx.rng.choice(days)
    span = [d for d in _days(lo, hi) if d.weekday() != 4]
    return ctx.rng.choice(span) if span else None


def _rand_date(rng: random.Random, lo: date, hi: date) -> date:
    return lo + timedelta(days=rng.randint(0, max(0, (hi - lo).days)))


def _person(ctx: Ctx, counters: dict[str, int]) -> tuple[str, str, str, WorkerLanguage, Any, str]:
    langs, weights = zip(*LANG_MIX, strict=True)
    lang = ctx.rng.choices(langs, weights=weights)[0]
    nat = ctx.rng.choice(LANG_NAT[lang])
    f_en, f_ar = ctx.rng.choice(FIRST[nat])
    l_en, l_ar = ctx.rng.choice(LAST[nat])
    if nat == "SA":
        counters["nid"] += 1
        return f"{f_en} {l_en}", f"{f_ar} {l_ar}", nat, lang, IT.national_id, str(counters["nid"])
    counters["iqama"] += 1
    return f"{f_en} {l_en}", f"{f_ar} {l_ar}", nat, lang, IT.iqama, str(counters["iqama"])


def _bulk_plans(ctx: Ctx, counters: dict[str, int]) -> None:
    rng = ctx.rng
    code = ctx.project.code
    named = [p for p in ctx.plans if p.project == code]
    for eng, total in VOLUMES[code].items():
        have = sum(
            1
            for p in named
            if p.eng == eng
            and p.demob is None
            and p.person_type == WorkerPersonType.contractor_worker
        )
        n = total - have
        days = ctx.days[eng]
        weights = [1 + 2 * i / max(1, len(days)) for i in range(len(days))]
        mobs = sorted(rng.choices(days, weights=weights, k=n))
        early = [i for i, d in enumerate(mobs) if date(2025, 8, 1) <= d <= date(2025, 9, 25)]
        if len(early) < GEN_INVALID[eng]:
            early = [i for i, d in enumerate(mobs) if d <= date(2025, 9, 25)]
        invalid = set(rng.sample(early, GEN_INVALID[eng]))
        for i, mob in enumerate(mobs):
            en, ar, nat, lang, id_type, id_no = _person(ctx, counters)
            counters["seq"] += 1
            if eng == "RAWABI":
                sites = ["S-AIR"] if counters["rawabi_air"] < RAWABI_AIRSIDE else ["S-LAND"]
                counters["rawabi_air"] += 1 if sites == ["S-AIR"] else 0
            else:
                sites = list(BULK_SITES[eng])
                if eng == "QIMMA":
                    sites = [rng.choice(sites)]
            exp = (
                _rand_date(rng, date(2026, 10, 8), date(2026, 10, 30))
                if rng.random() < 0.015
                else _rand_date(rng, date(2026, 11, 1), date(2029, 12, 31))
            )
            p = Plan(
                counters["seq"],
                en,
                ar,
                nat,
                id_type,
                id_no,
                exp,
                lang,
                code,
                eng,
                rng.choice(BULK_TRADES[eng]),
                sites,
                mob,
                airside="S-AIR" in sites,
            )
            p.inductions = _bulk_gen(ctx, p, invalid=i in invalid)
            ctx.plans.append(p)


def _bulk_gen(
    ctx: Ctx, p: Plan, invalid: bool
) -> list[tuple[str, date, date | None, InductionStatus, int, bool, int | None]]:
    rng = ctx.rng
    out: list[tuple[str, date, date | None, InductionStatus, int, bool, int | None]] = []
    first_attempt = 1
    if rng.random() < 0.08:  # ≈ 8 % failed first attempts (A.1.4)
        out.append(("GEN", p.mob, None, InductionStatus.failed, 1, False, rng.randint(55, 78)))
        first_attempt = 2
    d = p.mob
    chain = [d]
    while not invalid and _vu(d, 12) < AS_OF + timedelta(days=30):
        vu = _vu(d, 12)
        r = _pick_day(ctx, p.eng or "", vu - timedelta(days=30), min(vu - timedelta(days=1), AS_OF))
        if r is None:
            break
        chain.append(r)
        d = r
    for i, day in enumerate(chain):
        vu = _vu(day, 12)
        last = i == len(chain) - 1
        st = (V if vu >= TODAY else X) if last else S
        out.append(("GEN", day, vu, st, first_attempt if i == 0 else 1, True, rng.randint(80, 100)))
    return out


def _extra_courses(ctx: Ctx) -> None:
    """AIR for the airside crew, ILS for some RAWABI/GULFPAVE crew, TC on RBT-52."""
    bulk = [p for p in ctx.plans if p.project == ctx.project.code and not p.named]
    for p in bulk:
        gen_ok = any(x[0] == "GEN" and x[3] == V for x in p.inductions)
        if not gen_ok:
            continue
        if p.airside:
            lo = max(p.mob + timedelta(days=1), date(2025, 10, 22))
            d = _pick_day(ctx, p.eng or "", lo, AS_OF) if lo <= AS_OF else None
            if d is not None:
                p.inductions += _gen(d, code="AIR")
    if ctx.project.code == "ANIA-EXP":
        ils = [p for p in bulk if p.eng == "RAWABI" and p.airside and _has(p, "AIR")][:20]
        for p in ils:
            d = _pick_day(ctx, "RAWABI", date(2026, 6, 1), date(2026, 9, 25))
            if d is not None and max(x[1] for x in p.inductions if x[0] == "AIR") < d:
                p.inductions += _gen(d, code="ILS", months=6)
    else:
        tc = [p for p in bulk if p.eng == "DLIFT"] + [
            p for p in bulk if p.eng == "QIMMA" and p.trade in (T.carpenter, T.steel_fixer)
        ][:20]
        for p in tc:
            lo = max(p.mob + timedelta(days=1), date(2025, 10, 15))
            d = _pick_day(ctx, p.eng or "", lo, AS_OF) if lo <= AS_OF else None
            if d is not None:
                p.inductions += _gen(d, code="TC")


def _has(p: Plan, course: str, on: date = TODAY) -> bool:
    return any(
        x[0] == course and x[3] == V and x[2] is not None and x[1] <= on <= x[2]
        for x in p.inductions
    )


X8_DEMOB = [  # (demob date, returned offset days after due or None, has ADP)
    (date(2026, 9, 1), 0, True),
    (date(2026, 9, 3), -1, False),
    (date(2026, 9, 7), 0, False),
    (date(2026, 9, 10), -2, True),
    (date(2026, 9, 14), 0, False),
    (date(2026, 9, 17), -1, True),
    (date(2026, 9, 20), 3, False),  # due 09-23, returned 09-26 (late)
]


def _x8_plans(ctx: Ctx, counters: dict[str, int]) -> list[Plan]:
    """Seven demobilised GULFPAVE drivers with passes (3 with ADPs) for X8."""
    out = []
    for demob, _, _ in X8_DEMOB:
        en, ar, nat, lang, id_type, id_no = _person(ctx, counters)
        counters["seq"] += 1
        mob = _pick_day(ctx, "GULFPAVE", date(2025, 11, 1), date(2025, 12, 31)) or date(2025, 11, 2)
        exp = _rand_date(ctx.rng, date(2027, 1, 1), date(2029, 6, 30))
        p = Plan(
            counters["seq"],
            en,
            ar,
            nat,
            id_type,
            id_no,
            exp,
            lang,
            "ANIA-EXP",
            "GULFPAVE",
            T.driver,
            ["S-AIR"],
            mob,
            demob,
            airside=True,
        )
        p.inductions = _gen(mob, last=V)
        p.inductions += _gen(mob + timedelta(days=1), code="AIR")
        ctx.plans.append(p)
        out.append(p)
    return out


# ---- inserts -------------------------------------------------------------------------------------


def _chunks(rows: list[dict[str, Any]], n: int = 2000) -> Iterable[list[dict[str, Any]]]:
    for i in range(0, len(rows), n):
        yield rows[i : i + n]


def _insert(db: Session, model: Any, rows: list[dict[str, Any]]) -> None:
    for part in _chunks(rows):
        db.execute(insert(model), part)


def _insert_people(ctx: Ctx) -> None:
    db = ctx.db
    code = ctx.project.code
    plans = [p for p in ctx.plans if p.project == code]
    creator = ctx.user_id("noura.qahtani" if code == "ANIA-EXP" else "yousef.ghamdi")
    created = _at(date(2025, 1, 1), 8)
    workers, deps = [], []
    for p in plans:
        n = common.check_id(p.id_type, p.id_no, p.nat if p.id_type == IT.passport else None)
        workers.append(
            {
                "id": p.wid,
                "seq": p.seq,
                "worker_no": p.no,
                "person_type": p.person_type,
                "full_name_en": p.en,
                "full_name_ar": p.ar,
                "id_type": p.id_type,
                "id_number_enc": crypto.encrypt(n),
                "id_number_bidx": common.blind_index(p.id_type, n, p.nat),
                "id_number_masked": common.mask_worker_id(p.id_type, n),
                "passport_country": p.nat if p.id_type == IT.passport else None,
                "id_expiry_date": p.id_exp,
                "nationality": p.nat,
                "adult_attestation": True,
                "primary_language": p.lang,
                "user_id": ctx.user_id(p.user) if p.user else None,
                "status": WorkerStatus.active,
                "search_text": search_blob(p.no, p.en, p.ar),
                "created_by_user_id": creator,
                "seed_fake": True,
                "created_at": created,
                "updated_at": created,
            }
        )
        eng = ctx.engs[p.eng] if p.eng else None
        deps.append(
            {
                "id": p.did,
                "worker_id": p.wid,
                "project_id": ctx.project.id,
                "engagement_id": eng.id if eng else None,
                "employee_no": None,
                "trade": p.trade,
                "site_ids": [ctx.sites[s].id for s in p.sites],
                "mobilised_on": p.mob,
                "planned_demob_on": None,
                "demobilised_on": p.demob,
                "status": DeploymentStatus.demobilised if p.demob else DeploymentStatus.mobilised,
                "inducted_on": p.mob,
                "access_card_issued_on": p.mob,
                "reissue_count": 0,
                "passport_alerts_sent": [],
                "created_by_user_id": creator,
                "seed_fake": True,
                "created_at": _at(p.mob, 7),
                "updated_at": _at(p.demob or p.mob, 7),
            }
        )
    _insert(db, Worker, workers)
    _insert(db, Deployment, deps)
    # access-card tokens (§3.20): active for mobilised deployments, revoked at demobilisation
    tokens = []
    for p in plans:
        tokens.append(
            {
                "id": uuid.uuid4(),
                "token": common.new_qr_token(),
                "kind": QrKind.AC,
                "project_id": ctx.project.id,
                "subject_id": p.did,
                "printed_ref": f"{p.no} / {code}",
                "status": QrTokenStatus.revoked if p.demob else QrTokenStatus.active,
                "lost": False,
                "created_at": _at(p.mob, 7),
                "ended_at": _at(p.demob, 9) if p.demob else None,
            }
        )
    _insert(db, QrToken, tokens)


def _insert_inductions(ctx: Ctx) -> dict[tuple[uuid.UUID | None, date], int]:
    """Induction records; returns passed GEN counts per (engagement, local day)."""
    db = ctx.db
    code = ctx.project.code
    officer = ctx.user_id("noura.qahtani" if code == "ANIA-EXP" else "yousef.ghamdi")
    rep = ctx.user_id("ahmed.zahrani" if code == "ANIA-EXP" else "yousef.ghamdi")
    seqs: dict[int, int] = defaultdict(int)
    rows = []
    gen_counts: dict[tuple[uuid.UUID | None, date], int] = defaultdict(int)
    items = [
        (d, p, course, vu, st, attempt, passed, score)
        for p in ctx.plans
        if p.project == code
        for course, d, vu, st, attempt, passed, score in p.inductions
    ]
    items.sort(key=lambda x: (x[0], x[1].seq, x[5]))
    mismatch_left = 3 if code == "ANIA-EXP" else 0
    for d, p, course_code, vu, st, attempt, passed, score in items:
        course = ctx.courses[course_code]
        seqs[d.year] += 1
        eng = ctx.engs[p.eng] if p.eng else None
        lang, mismatch = p.lang, False
        if (
            mismatch_left
            and not p.named
            and course_code == "GEN"
            and d >= date(2026, 9, 10)
            and p.lang == L.ur
        ):
            lang, mismatch = L.en, True
            mismatch_left -= 1
        hour = 7 if attempt == 1 else 11
        by = rep if (course_code in ("GEN", "TC") and p.eng and p.seq % 3 == 0) else officer
        rows.append(
            {
                "id": uuid.uuid4(),
                "year": d.year,
                "seq": seqs[d.year],
                "induction_no": make_ref("IND", code, d.year, seqs[d.year], 5),
                "project_id": ctx.project.id,
                "worker_id": p.wid,
                "deployment_id": p.did,
                "engagement_id": eng.id if eng else None,
                "course_id": course.id,
                "induction_type": course.induction_type,
                "course_version": course.version,
                "session_ref": f"SES-{d:%y%m%d}-{course_code}",
                "delivered_at": _at(d, hour),
                "delivered_on": d,
                "delivered_by_user_id": by,
                "delivery_language": lang,
                "interpreter_used": False,
                "language_mismatch": mismatch,
                "duration_minutes": course.min_duration_minutes + 5,
                "test_score_pct": Decimal(score) if score is not None else None,
                "attempt_no": attempt,
                "result": InductionResult.passed if passed else InductionResult.failed,
                "privacy_notice_version": PN,
                "signature_attachment_id": None,
                "valid_from": d if passed else None,
                "valid_until": vu,
                "reinduction_due_on": None,
                "helmet_sticker_no": None,
                "status": st,
                "status_changed_at": _at(vu + timedelta(days=1), 0)
                if st == X and vu
                else _at(d, hour),
                "created_by_user_id": by,
                "seed_fake": True,
                "created_at": _at(d, hour),
                "updated_at": _at(d, hour),
            }
        )
        if course_code == "GEN" and passed and d <= AS_OF:
            gen_counts[(eng.id if eng else None, d)] += 1
    _insert(db, InductionRecord, rows)
    return gen_counts


def _rewrite_returns(ctx: Ctx, counts: dict[tuple[uuid.UUID | None, date], int]) -> None:
    """KA-2 / A.1.4: daily-return `inductions` = passed GEN records of that engagement-day."""
    if not ctx.has_returns:
        return
    db = ctx.db
    t = cast(Table, WorkforceReturn.__table__)
    db.execute(update(t).where(t.c.project_id == ctx.project.id).values(inductions=0))
    rows = db.execute(
        select(t.c.id, t.c.engagement_id, t.c.work_date, t.c.man_hours)
        .where(t.c.project_id == ctx.project.id)
        .order_by(t.c.engagement_id, t.c.work_date, t.c.man_hours.desc())
    ).all()
    first: dict[tuple[uuid.UUID, date], uuid.UUID] = {}
    by_eng: dict[uuid.UUID, list[date]] = defaultdict(list)
    for rid, eid, d, _mh in rows:
        if (eid, d) not in first:
            first[(eid, d)] = rid
            by_eng[eid].append(d)
    add: dict[uuid.UUID, int] = defaultdict(int)
    for (eid, d), n in counts.items():
        if eid is None:
            continue
        rid = first.get((eid, d))
        if rid is None:  # no return that day: the next day with a return
            later = [x for x in by_eng.get(eid, []) if x > d]
            if not later:
                continue
            rid = first[(eid, later[0])]
        add[rid] += n
    stmt = update(t).where(t.c.id == bindparam("rid")).values(inductions=bindparam("n"))
    db.execute(stmt, [{"rid": k, "n": v} for k, v in add.items()])


# ---- passes, applications, ADPs (A.3; ≈ 900 airside crew, 236 Active ADPs at 2026-09-30) -------

PROJECT_END = date(2028, 12, 31)


class Numbers:
    """Per-year sequences that skip the numbers reserved by the A.3/A.5 named records."""

    def __init__(self, reserved: dict[int, set[int]] | None = None) -> None:
        self.seq: dict[int, int] = defaultdict(int)
        self.reserved = reserved or {}

    def next(self, year: int) -> int:
        n = self.seq[year] + 1
        while n in self.reserved.get(year, set()):
            n += 1
        self.seq[year] = n
        return n


def _pass_eff(p: Plan, card: date, recheck: date | None) -> lifecycle.Eff:
    from app.core.access_enums import LimitingFactor as F  # noqa: PLC0415

    return lifecycle.strictest(
        {
            F.card_expiry_date: card,
            F.worker_id_expiry_date: p.id_exp,
            F.deployment_planned_demob_on: None,
            F.engagement_demobilisation_date: None,
            F.project_planned_end_date: PROJECT_END,
            F.background_recheck_due: recheck,
        }
    )


def _adp_eff(own: date, pass_eff: date | None, licence: date) -> lifecycle.Eff:
    from app.core.access_enums import LimitingFactor as F  # noqa: PLC0415

    return lifecycle.strictest(
        {
            F.own_valid_until: own,
            F.pass_effective_valid_until: pass_eff,
            F.licence_expiry_date: licence,
        }
    )


@dataclass
class PassSpec:
    plan: Plan
    category: str
    pass_no: str | None
    areas: list[str]
    issued: date | None
    card: date | None
    check: date | None  # background cleared on
    app_no: tuple[int, int] | None = None  # (year, seq) for named applications
    status: PassApplicationStatus = PassApplicationStatus.issued
    bg_status: BackgroundCheckStatus = BackgroundCheckStatus.cleared
    submitted: date | None = None
    decided: date | None = None
    pass_id: uuid.UUID = field(default_factory=uuid.uuid4)
    app_id: uuid.UUID = field(default_factory=uuid.uuid4)
    eff: date | None = None


def _app_and_pass(
    ctx: Ctx, sp: PassSpec, nums: Numbers
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    p = sp.plan
    eng = ctx.engs[p.eng] if p.eng else None
    rep = ctx.user_id("ahmed.zahrani")
    officer = ctx.user_id("noura.qahtani")
    submitted = sp.submitted or ((sp.issued or AS_OF) - timedelta(days=ctx.rng.randint(9, 30)))
    year, seq = sp.app_no or (submitted.year, nums.next(submitted.year))
    lodged = submitted + timedelta(days=2)
    cat = sp.category
    bg: dict[str, Any] = {"status": BackgroundCheckStatus.not_required.value}
    recheck = None
    if cat in ("PERM", "TEMP-U"):
        bg = {"status": sp.bg_status.value}
        if sp.bg_status == BackgroundCheckStatus.cleared:
            check = sp.check or (submitted + timedelta(days=5))
            recheck = add_months(check, 24)
            bg.update(check_date=check.isoformat(), recheck_due=recheck.isoformat())
        elif sp.bg_status != BackgroundCheckStatus.submitted:
            bg["check_date"] = (submitted + timedelta(days=5)).isoformat()
    issued = sp.status == PassApplicationStatus.issued
    decided = sp.decided or ((sp.issued - timedelta(days=1)) if sp.issued else None)
    app = {
        "id": sp.app_id,
        "year": year,
        "seq": seq,
        "application_no": make_ref("APA", ctx.project.code, year, seq, 4),
        "project_id": ctx.project.id,
        "application_type": PassApplicationType.new,
        "worker_id": p.wid,
        "deployment_id": p.did,
        "sponsor_engagement_id": eng.id if eng else None,
        "sponsor_letter_ref": f"SPL-TEST-{year % 100:02d}{seq:04d}",
        "client_sponsor_user_id": None,
        "pass_category": cat,
        "requested_area_codes": sp.areas,
        "requested_valid_until": sp.card or add_months(submitted, 24),
        "justification": "Airside works crew (seed data)",
        "prerequisite_snapshot": None,
        "submitted_at": _at(submitted, 9),
        "submitted_by_user_id": rep,
        "lodged_at": _at(lodged, 10)
        if sp.status not in (PassApplicationStatus.submitted, PassApplicationStatus.endorsed)
        else None,
        "authority_ref": f"AUTH-TEST-{year % 100:02d}{seq:04d}",
        "background_enc": crypto.encrypt(json_dumps(bg)),
        "outcome_note": None,
        "decided_at": _at(decided, 12)
        if decided and sp.status in (PassApplicationStatus.issued, PassApplicationStatus.refused)
        else None,
        "closed_at": _at(sp.issued, 13)
        if issued and sp.issued
        else (_at(decided, 12) if decided and sp.status == PassApplicationStatus.refused else None),
        "issued_pass_id": sp.pass_id if issued else None,
        "id_copy_deleted_at": _at(sp.issued + timedelta(days=30), 1)
        if issued and sp.issued and sp.issued + timedelta(days=30) < TODAY
        else None,
        "stale_alerted_on": None,
        "status": sp.status,
        "created_by_user_id": rep,
        "updated_by_user_id": officer,
        "seed_fake": True,
        "created_at": _at(submitted, 9),
        "updated_at": _at(decided or submitted, 12),
    }
    if not issued or sp.issued is None or sp.card is None:
        return app, None
    pcat = {c[0]: c for c in PASS_CATEGORIES}[cat]
    escorted = pcat[3]
    eff = _pass_eff(p, sp.card, recheck if not escorted else None)
    sp.eff = eff.eff
    ps = {
        "id": sp.pass_id,
        "pass_no": sp.pass_no,
        "project_id": ctx.project.id,
        "application_id": sp.app_id,
        "worker_id": p.wid,
        "deployment_id": p.did,
        "engagement_id": eng.id if eng else None,
        "pass_category": cat,
        "area_codes": sp.areas,
        "card_colour": pcat[6],
        "escorted": escorted,
        "issued_on": sp.issued,
        "card_expiry_date": sp.card,
        "validity_status": ValidityStatus.active,
        "effective_valid_until": eff.eff,
        "limiting_factor": eff.limiting,
        "custody_status": CustodyStatus.held,
        "return_due_on": None,
        "returned_at": None,
        "received_by_user_id": None,
        "lost_reported_at": None,
        "authority_notified_at": None,
        "revoked_at": None,
        "revoked_reason": None,
        "expired_on": None,
        "created_by_user_id": officer,
        "updated_by_user_id": officer,
        "seed_fake": True,
        "created_at": _at(sp.issued, 13),
        "updated_at": _at(sp.issued, 13),
    }
    return app, ps


def json_dumps(data: dict[str, Any]) -> str:
    import json  # noqa: PLC0415

    return json.dumps(data, default=str)


@dataclass
class AdpSpec:
    plan: Plan
    adp_no: str
    category: AreaCategory
    issued: date
    own: date
    licence: date
    pass_spec: PassSpec
    adp_id: uuid.UUID = field(default_factory=uuid.uuid4)
    licence_class: LicenceClass = LicenceClass.heavy_equipment


def _adp_row(ctx: Ctx, a: AdpSpec) -> dict[str, Any]:
    p = a.plan
    eng = ctx.engs[p.eng] if p.eng else None
    officer = ctx.user_id("noura.qahtani")
    eff = _adp_eff(a.own, a.pass_spec.eff, a.licence)
    return {
        "id": a.adp_id,
        "adp_no": a.adp_no,
        "project_id": ctx.project.id,
        "worker_id": p.wid,
        "deployment_id": p.did,
        "engagement_id": eng.id if eng else None,
        "category": a.category,
        "vehicle_classes": [VehicleClass.light]
        if p.trade == T.driver
        else [VehicleClass.heavy, VehicleClass.special_plant],
        "licence_issuer": LicenceIssuer.ksa,
        "licence_class": a.licence_class,
        "licence_expiry_date": a.licence,
        "theory_test_date": a.issued - timedelta(days=6),
        "theory_score_pct": Decimal(ctx.rng.randint(80, 98)),
        "practical_test_date": a.issued - timedelta(days=2),
        "practical_result": PracticalTestResult.passed,
        "practical_examiner": "Examiner TEST-01",
        "practical_included_manoeuvring": a.category == AreaCategory.manoeuvring,
        "rtf_competence": a.category == AreaCategory.manoeuvring,
        "issued_on": a.issued,
        "own_valid_until": a.own,
        "pass_id": a.pass_spec.pass_id,
        "validity_status": ValidityStatus.active,
        "effective_valid_until": eff.eff,
        "limiting_factor": eff.limiting,
        "custody_status": CustodyStatus.held,
        "return_due_on": None,
        "returned_at": None,
        "received_by_user_id": None,
        "lost_reported_at": None,
        "authority_notified_at": None,
        "revoked_at": None,
        "revoked_reason": None,
        "expired_on": None,
        "created_by_user_id": officer,
        "updated_by_user_id": officer,
        "seed_fake": True,
        "created_at": _at(a.issued, 12),
        "updated_at": _at(a.issued, 12),
    }


def _passes(ctx: Ctx, x8: list[Plan]) -> tuple[list[PassSpec], list[AdpSpec]]:
    rng = ctx.rng
    d = date
    P = ctx.plan  # noqa: N806
    PS = PassApplicationStatus  # noqa: N806
    BG = BackgroundCheckStatus  # noqa: N806
    specs = [
        PassSpec(
            P(2),
            "PERM",
            "ANIA-AP-26-01877",
            ["A", "M"],
            d(2025, 6, 1),
            d(2027, 5, 31),
            d(2025, 5, 20),
        ),
        PassSpec(
            P(3), "PERM", "ANIA-AP-25-01422", ["A"], d(2025, 5, 1), d(2027, 4, 30), d(2025, 4, 20)
        ),
        PassSpec(
            P(4),
            "TEMP-E",
            "ANIA-AP-26-02210",
            ["A", "M"],
            d(2026, 9, 29),
            d(2026, 10, 28),
            None,
            app_no=(2026, 139),
            submitted=d(2026, 9, 22),
        ),
        PassSpec(
            P(4),
            "PERM",
            None,
            ["A", "M"],
            None,
            None,
            None,
            app_no=(2026, 142),
            status=PS.lodged,
            bg_status=BG.in_progress,
            submitted=d(2026, 9, 24),
        ),
        PassSpec(
            P(5),
            "PERM",
            "ANIA-AP-25-00710",
            ["A", "M"],
            d(2025, 10, 1),
            d(2027, 9, 30),
            d(2025, 9, 15),
        ),
        PassSpec(
            P(6),
            "PERM",
            "ANIA-AP-25-01105",
            ["A"],
            d(2025, 10, 20),
            d(2027, 10, 19),
            d(2025, 10, 5),
        ),
        PassSpec(
            P(7),
            "PERM",
            "ANIA-AP-25-00402",
            ["A", "M"],
            d(2025, 3, 20),
            d(2027, 3, 19),
            d(2025, 3, 10),
        ),
        PassSpec(
            P(8),
            "PERM",
            None,
            ["A"],
            None,
            None,
            None,
            app_no=(2026, 118),
            status=PS.refused,
            bg_status=BG.not_cleared,
            submitted=d(2026, 8, 10),
            decided=d(2026, 9, 10),
        ),
        PassSpec(
            P(10),
            "PERM",
            "ANIA-AP-25-00933",
            ["A", "M"],
            d(2025, 6, 25),
            d(2027, 6, 24),
            d(2025, 6, 15),
        ),
        PassSpec(
            P(11),
            "PERM",
            "ANIA-AP-25-00011",
            ["A", "M"],
            d(2025, 3, 10),
            d(2027, 3, 9),
            d(2025, 3, 5),
        ),
        PassSpec(
            P(12),
            "VIS",
            "ANIA-AP-26-V0412",
            ["A"],
            d(2026, 10, 6),
            d(2026, 10, 6),
            None,
            submitted=d(2026, 10, 5),
            decided=d(2026, 10, 5),
        ),
        PassSpec(
            P(13),
            "PERM",
            "ANIA-AP-25-00988",
            ["A", "M"],
            d(2025, 5, 15),
            d(2027, 5, 14),
            d(2025, 5, 5),
        ),
    ]
    for p in [P(2), P(3), P(4), P(5), P(6), P(7), P(10), P(11), P(12), P(13)]:
        p.areas = next(s.areas for s in specs if s.plan is p and s.pass_no)
    n = 0
    stale_left = 4
    bulk = [
        p
        for p in ctx.plans
        if p.project == "ANIA-EXP" and not p.named and p.airside and _has(p, "AIR")
    ]
    for p in bulk:
        n += 1
        if p.eng == "GULFPAVE":
            areas = ["A", "M"] if rng.random() < 0.65 or p in x8 else ["A"]
        else:
            areas = ["A"] if rng.random() < 0.8 else ["A", "M"]
        if stale_left and p.eng == "RAWABI" and date(2026, 7, 15) <= p.mob <= date(2026, 8, 20):
            stale_left -= 1
            specs.append(
                PassSpec(
                    p,
                    "PERM",
                    None,
                    areas,
                    None,
                    None,
                    None,
                    status=PS.lodged,
                    bg_status=BG.in_progress,
                    submitted=d(2026, 8, 10),
                )
            )
            continue
        if p.mob + timedelta(days=20) > d(2026, 9, 20):
            specs.append(
                PassSpec(
                    p,
                    "PERM",
                    None,
                    areas,
                    None,
                    None,
                    None,
                    status=rng.choice([PS.submitted, PS.lodged]),
                    bg_status=BG.submitted,
                    submitted=min(p.mob + timedelta(days=3), AS_OF),
                )
            )
            continue
        issued = min(p.mob + timedelta(days=rng.randint(15, 35)), d(2026, 9, 20))
        if issued >= d(2026, 7, 15) and p not in x8:
            card, cat = issued + timedelta(days=89), "TEMP-U"
        else:
            card, cat = issued + timedelta(days=729), "PERM"
        check = issued - timedelta(days=rng.randint(5, 15))
        p.areas = areas
        specs.append(PassSpec(p, cat, f"ANIA-AP-TEST-{n:05d}", areas, issued, card, check))
    # ADPs
    adps = []
    by_plan = {s.plan.seq: s for s in specs if s.pass_no}
    named_adps = [
        (
            2,
            "ADP-OEXX-26-0042",
            AreaCategory.manoeuvring,
            d(2026, 2, 2),
            d(2028, 2, 1),
            d(2029, 6, 30),
            LicenceClass.heavy_equipment,
        ),
        (
            3,
            "ADP-OEXX-25-0057",
            AreaCategory.apron,
            d(2025, 8, 1),
            d(2027, 7, 31),
            d(2028, 5, 31),
            LicenceClass.heavy_transport,
        ),
        (
            5,
            "ADP-OEXX-25-0019",
            AreaCategory.manoeuvring,
            d(2025, 10, 15),
            d(2027, 10, 14),
            d(2029, 1, 31),
            LicenceClass.private,
        ),
        (
            7,
            "ADP-OEXX-25-0008",
            AreaCategory.manoeuvring,
            d(2025, 4, 10),
            d(2027, 4, 9),
            d(2030, 1, 31),
            LicenceClass.private,
        ),
        (
            10,
            "ADP-OEXX-25-0031",
            AreaCategory.manoeuvring,
            d(2025, 7, 1),
            d(2027, 6, 30),
            d(2028, 2, 29),
            LicenceClass.heavy_transport,
        ),
        (
            13,
            "ADP-OEXX-25-0044",
            AreaCategory.manoeuvring,
            d(2025, 6, 1),
            d(2027, 5, 31),
            d(2028, 11, 30),
            LicenceClass.heavy_transport,
        ),
    ]
    for seq, no, cat_, issued, own, lic, lclass in named_adps:
        adps.append(AdpSpec(P(seq), no, cat_, issued, own, lic, by_plan[seq], licence_class=lclass))
    for i, (p, (_, _, has_adp)) in enumerate(zip(x8, X8_DEMOB, strict=True)):
        if has_adp:
            sp = by_plan[p.seq]
            assert sp.issued is not None  # noqa: S101
            issued = sp.issued + timedelta(days=10)
            adps.append(
                AdpSpec(
                    p,
                    f"ADP-OEXX-TEST-X8{i:02d}",
                    AreaCategory.manoeuvring,
                    issued,
                    _vu(issued, 24),
                    d(2029, 3, 31),
                    sp,
                )
            )
    cands = [
        by_plan[p.seq]
        for p in bulk
        if p.seq in by_plan
        and p not in x8
        and p.trade in (T.driver, T.plant_operator)
        and by_plan[p.seq].category in ("PERM", "TEMP-U")
        and (by_plan[p.seq].issued or AS_OF) <= d(2026, 9, 10)
        and p.id_exp >= d(2026, 11, 1)
    ]
    for sp in specs:  # eff is needed for the ADP terms
        if sp.pass_no and sp.eff is None and sp.card is not None:
            recheck = add_months(sp.check, 24) if sp.check else None
            sp.eff = _pass_eff(sp.plan, sp.card, recheck).eff
    cands = [c for c in cands if c.eff is not None and c.eff >= d(2026, 11, 1)]
    for k, sp in enumerate(cands[:232]):
        assert sp.issued is not None  # noqa: S101
        issued = min(sp.issued + timedelta(days=rng.randint(7, 30)), d(2026, 9, 25))
        cat_ = AreaCategory.manoeuvring if "M" in sp.areas else AreaCategory.apron
        adps.append(
            AdpSpec(
                sp.plan,
                f"ADP-OEXX-TEST-{k + 1:04d}",
                cat_,
                issued,
                _vu(issued, 24),
                _rand_date(rng, d(2027, 6, 1), d(2030, 12, 31)),
                sp,
            )
        )
    if len(cands) < 232:
        raise RuntimeError(f"Seed: only {len(cands)} ADP candidates (need 232)")
    return specs, adps


def _insert_passes(ctx: Ctx, specs: list[PassSpec], adps: list[AdpSpec]) -> None:
    nums = Numbers({2026: {118, 139, 142}})
    apps, passes = [], []
    for sp in sorted(specs, key=lambda s: (s.submitted or s.issued or AS_OF, s.plan.seq)):
        a, ps = _app_and_pass(ctx, sp, nums)
        apps.append(a)
        if ps is not None:
            passes.append(ps)
    _insert(ctx.db, PassApplication, apps)
    _insert(ctx.db, AirportPass, passes)
    _insert(ctx.db, Adp, [_adp_row(ctx, a) for a in adps])


# ---- lifecycle scenarios (ORM, frozen clock) -----------------------------------------------------


def _custody(ctx: Ctx, x8: list[Plan]) -> None:
    """X8: Arjun's pass + ADP revoked at demobilisation and not returned; ten more items due in
    Sep 2026 (9 returned on time, 1 late)."""
    db = ctx.db
    s = common.settings(db, ctx.project.id)
    officer = ctx.user_id("noura.qahtani")
    arjun = ctx.plan(10)
    jobs: list[tuple[Plan, date, int | None]] = [(arjun, date(2026, 9, 20), None)]
    jobs += [(p, dm, off) for p, (dm, off, _) in zip(x8, X8_DEMOB, strict=True)]
    for p, demob, offset in jobs:
        at = _at(demob, 10)
        with frozen(at):
            cmodels: tuple[Any, ...] = (AirportPass, Adp)
            for model in cmodels:
                for obj in db.scalars(select(model).where(model.deployment_id == p.did)):
                    lifecycle.revoke(db, obj, CredentialReason.demobilised, None, officer, s, at)
                    if offset is not None and obj.return_due_on is not None:
                        back = _at(obj.return_due_on + timedelta(days=offset), 10)
                        obj.custody_status = CustodyStatus.returned
                        obj.returned_at = back
                        obj.received_by_user_id = officer
                        lifecycle.event(
                            db,
                            obj,
                            CredentialAction.returned,
                            CredentialReason.demobilised,
                            None,
                            officer,
                            back,
                        )
            db.add(
                CredentialEvent(
                    id=uuid.uuid4(),
                    project_id=ctx.project.id,
                    credential_kind=CredentialKind.access_card,
                    credential_id=p.did,
                    action=CredentialAction.revoked,
                    reason_code=CredentialReason.demobilised,
                    actor_user_id=officer,
                    occurred_at=at,
                    seed_fake=True,
                )
            )
    db.flush()


def _offences(ctx: Ctx, adps: list[AdpSpec]) -> None:
    """X5 (Jomar Santos, points suspension 2026-09-14…10-13) and X10 (4 offences in Sep)."""
    db = ctx.db
    zones = ctx.zones
    omar = ctx.user_id("omar.siddiqui")
    jomar = next(a for a in adps if a.plan.seq == 3)
    bulk = [
        a
        for a in adps
        if not a.plan.named and "TEST-X8" not in a.adp_no and a.issued <= date(2026, 8, 31)
    ][:3]
    rows: list[tuple[AdpSpec, int, int, str, date, int, str, list[str]]] = [
        (jomar, 2025, 44, "OFF-01", date(2025, 11, 20), 3, "Z-APR-21", []),
        (jomar, 2026, 12, "OFF-04", date(2026, 3, 5), 6, "Z-APR-21", []),
        (bulk[0], 2026, 30, "OFF-07", date(2026, 9, 5), 3, "Z-APR-21", []),
        (jomar, 2026, 31, "OFF-01", date(2026, 9, 14), 3, "Z-APR-21", ["adp_suspended_points"]),
        (bulk[1], 2026, 32, "OFF-08", date(2026, 9, 16), 2, "Z-TWB", []),
        (bulk[2], 2026, 33, "OFF-09", date(2026, 9, 24), 2, "Z-APR-21", []),
    ]
    for a, year, seq, code, day, pts, zone, actions in rows:
        eng = ctx.engs[a.plan.eng] if a.plan.eng else None
        db.add(
            Offence(
                id=uuid.uuid4(),
                year=year,
                seq=seq,
                offence_no=make_ref("OFF", ctx.project.code, year, seq, 4),
                project_id=ctx.project.id,
                worker_id=a.plan.wid,
                engagement_id=eng.id if eng else None,
                adp_id=a.adp_id,
                offence_code=code,
                points=pts,
                immediate_suspension=False,
                offence_at=_at(day, 14),
                offence_date=day,
                zone_id=zones[zone].id,
                vehicle_id=None,
                reported_by_user_id=omar,
                notes="Seed offence (fictional)",
                status=OffenceStatus.recorded,
                resulting_actions=actions,
                created_by_user_id=omar,
                seed_fake=True,
                created_at=_at(day, 15),
                updated_at=_at(day, 15),
            )
        )
    db.flush()
    adp = db.get(Adp, jomar.adp_id)
    assert adp is not None  # noqa: S101
    at = _at(date(2026, 9, 14), 15)
    with frozen(at):
        lifecycle.suspend(
            db,
            adp,
            SuspensionState.system,
            CredentialReason.points_threshold,
            "12 points in 365 days",
            None,
            at=at,
            suspension_end=date(2026, 10, 13),
        )
    db.flush()


VEHICLES: list[tuple[Any, ...]] = [
    # seq, eng, category, plate type, AR, EN, digits, fleet, serial, travel, max, istimara,
    # insurance, mvpi, AVP no, areas, AVP issued, own until, make
    (
        1,
        "GULFPAVE",
        VehicleCategory.paver,
        PlateType.none,
        None,
        None,
        None,
        "GP-PV-02",
        "TESTSN-PV-0001",
        "3.90",
        "3.90",
        None,
        date(2027, 3, 31),
        None,
        "AVP-OEXX-26-0117",
        ["apron", "manoeuvring"],
        date(2026, 3, 1),
        date(2027, 2, 28),
        "Paver TEST-PV 2021",
    ),
    (
        2,
        "GULFPAVE",
        VehicleCategory.pickup,
        PlateType.private,
        "ح ط ر",
        "JTR",
        "9012",
        "GP-LV-07",
        "TESTVIN0000000002",
        "1.90",
        "1.90",
        date(2027, 4, 30),
        date(2026, 10, 20),
        date(2027, 1, 15),
        "AVP-OEXX-26-0118",
        ["apron", "manoeuvring"],
        date(2026, 3, 1),
        date(2027, 2, 28),
        "Pickup TEST-LV 2023",
    ),
    (
        3,
        "RAWABI",
        VehicleCategory.mobile_crane,
        PlateType.heavy_equipment,
        "ر ع ق",
        "REG",
        "9003",
        "RW-MC-03",
        "TESTVIN0000000003",
        "3.95",
        "32.00",
        date(2027, 5, 31),
        date(2027, 5, 31),
        date(2027, 2, 28),
        "AVP-OEXX-26-0120",
        ["apron"],
        date(2026, 4, 1),
        date(2027, 3, 31),
        "Mobile crane 50 t TEST-MC",
    ),
    (
        4,
        "RAWABI",
        VehicleCategory.tipper,
        PlateType.transport,
        "د ل ك",
        "DLK",
        "9004",
        "RW-TP-11",
        "TESTVIN0000000004",
        "3.40",
        "3.40",
        date(2027, 6, 30),
        date(2027, 6, 30),
        date(2027, 3, 31),
        None,
        [],
        None,
        None,
        "Tipper TEST-TP 2020",
    ),
    (
        5,
        "GULFPAVE",
        VehicleCategory.excavator,
        PlateType.none,
        None,
        None,
        None,
        "GP-EX-05",
        "TESTSN-EX-0005",
        "3.10",
        "9.50",
        None,
        date(2027, 1, 31),
        None,
        "AVP-OEXX-26-0131",
        ["apron", "manoeuvring"],
        date(2026, 4, 1),
        date(2027, 3, 31),
        "Excavator 20 t TEST-EX",
    ),
    (
        6,
        "RAWABI",
        VehicleCategory.pickup,
        PlateType.private,
        "س ص ن",
        "SXN",
        "9006",
        "RW-LV-02",
        "TESTVIN0000000006",
        "1.95",
        "1.95",
        date(2027, 7, 31),
        date(2027, 7, 31),
        date(2027, 4, 30),
        "AVP-OEXX-26-0125",
        ["apron"],
        date(2026, 4, 1),
        date(2027, 3, 31),
        "Pickup TEST-LV 2024",
    ),
]


def _vehicles(ctx: Ctx) -> dict[int, Vehicle]:
    db = ctx.db
    officer = ctx.user_id("noura.qahtani")
    out: dict[int, Vehicle] = {}
    for (
        seq,
        eng,
        cat,
        ptype,
        ar,
        en,
        digits,
        fleet,
        serial,
        travel,
        mx,
        ist,
        ins,
        mvpi,
        avp_no,
        areas,
        avp_issued,
        own,
        make,
    ) in VEHICLES:
        v = Vehicle(
            id=uuid.uuid4(),
            seq=seq,
            vehicle_no=f"VEH-{seq:04d}",
            project_id=ctx.project.id,
            engagement_id=ctx.engs[eng].id,
            owner_type=VehicleOwnerType.company,
            category=cat,
            plate_type=ptype,
            plate_letters_ar=ar,
            plate_letters_en=en,
            plate_digits=digits,
            fleet_no=fleet,
            serial_or_vin=serial,
            make_model=make,
            year_built=2022,
            colour="Yellow" if ptype == PlateType.none else "White",
            travel_height_m=Decimal(travel),
            max_working_height_m_agl=Decimal(mx),
            istimara_expiry=ist,
            insurance_policy_no=f"TEST-INS-{seq:04d}",
            insurance_expiry=ins,
            mvpi_expiry=mvpi,
            status=VehicleStatus.active,
            created_by_user_id=officer,
            seed_fake=True,
            created_at=_at(date(2026, 2, 15), 9),
            updated_at=_at(date(2026, 2, 15), 9),
        )
        db.add(v)
        db.flush()
        out[seq] = v
        if avp_no is None:
            continue
        a = Avp(
            id=uuid.uuid4(),
            avp_no=avp_no,
            project_id=ctx.project.id,
            vehicle_id=v.id,
            engagement_id=v.engagement_id,
            areas=areas,
            inspection_date=avp_issued - timedelta(days=3),
            inspector="Inspector TEST-02",
            inspection_result=InspectionResult.passed,
            checklist={},
            sticker_no=f"STK-TEST-{avp_no[-4:]}",
            issued_on=avp_issued,
            own_valid_until=own,
            validity_status=ValidityStatus.active,
            custody_status=CustodyStatus.held,
            created_by_user_id=officer,
            seed_fake=True,
            created_at=_at(avp_issued, 12),
            updated_at=_at(avp_issued, 12),
        )
        db.add(a)
        db.flush()
        e = lifecycle.avp_eff(db, a)
        a.effective_valid_until, a.limiting_factor = e.eff, e.limiting
        with frozen(_at(avp_issued, 12)):
            common.issue_qr(db, QrKind.VS, ctx.project.id, a.id, a.sticker_no or avp_no)
    db.flush()
    return out


# ---- NOTAM requests, obstacle clearances, ops events, WAPs (A.5) ---------------------------------


def _utc(y: int, m: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=UTC)


# seq, zone, impact, start, end, schedule, submitted, number, status, eng, description
NOTAMS: list[tuple[Any, ...]] = [
    (
        1,
        "Z-TWB",
        WorksImpact.taxiway_closure,
        _utc(2026, 6, 14, 20),
        _utc(2026, 6, 20, 2),
        "DAILY 2000-0200",
        _utc(2026, 6, 5, 7),
        "A0990/26",
        NotamStatus.expired,
        "GULFPAVE",
        "TWY B section closure for joint sealing",
    ),
    (
        2,
        "Z-APR-21",
        WorksImpact.stand_closure,
        _utc(2026, 6, 28, 3),
        _utc(2026, 7, 5, 15),
        "DAILY 0300-1500",
        _utc(2026, 6, 20, 7),
        "A0991/26",
        NotamStatus.expired,
        "RAWABI",
        "Stands 23-24 closed for pavement repair",
    ),
    (
        3,
        "Z-TWB",
        WorksImpact.taxiway_closure,
        _utc(2026, 7, 16, 20),
        _utc(2026, 7, 25, 2),
        "DAILY 2000-0200",
        _utc(2026, 7, 8, 7),
        "A0992/26",
        NotamStatus.expired,
        "GULFPAVE",
        "TWY B B4-B6 closed for resurfacing",
    ),
    (
        4,
        "Z-ILS33R",
        WorksImpact.ils_outage,
        _utc(2026, 8, 3, 4),
        _utc(2026, 8, 6, 13),
        "DAILY 0400-1300",
        _utc(2026, 7, 25, 7),
        "A0993/26",
        NotamStatus.expired,
        "GULFPAVE",
        "RWY 33R GP U/S for cable works",
    ),
    (
        5,
        "Z-APR-21",
        WorksImpact.stand_closure,
        _utc(2026, 8, 18, 3),
        _utc(2026, 8, 25, 15),
        "DAILY 0300-1500",
        _utc(2026, 8, 10, 7),
        "A0994/26",
        NotamStatus.expired,
        "RAWABI",
        "Stand 26 closed for drainage works",
    ),
    (
        6,
        "Z-TWB",
        WorksImpact.taxiway_closure,
        _utc(2026, 9, 2, 20),
        _utc(2026, 9, 9, 2),
        "DAILY 2000-0200",
        _utc(2026, 8, 24, 7),
        "A0995/26",
        NotamStatus.expired,
        "GULFPAVE",
        "TWY B B1-B2 closed for joint sealing",
    ),
    (
        7,
        "Z-APR-21",
        WorksImpact.stand_closure,
        _utc(2026, 9, 10, 3),
        _utc(2026, 9, 14, 15),
        "DAILY 0300-1500",
        _utc(2026, 9, 2, 7),
        "A0996/26",
        NotamStatus.expired,
        "RAWABI",
        "Stand 21 closed for marking works",
    ),
    (
        8,
        "Z-TWB",
        WorksImpact.taxiway_closure,
        _utc(2026, 9, 17, 20),
        _utc(2026, 10, 1, 2),
        "DAILY 2000-0200",
        _utc(2026, 9, 8, 7),
        "A0997/26",
        NotamStatus.expired,
        "GULFPAVE",
        "TWY B B2-B3 closed for pavement works",
    ),
    (
        9,
        "Z-APR-21",
        WorksImpact.stand_closure,
        _utc(2026, 9, 15, 3),
        _utc(2026, 9, 18, 15),
        "DAILY 0300-1500",
        _utc(2026, 9, 12, 7),
        "A0998/26",
        NotamStatus.expired,
        "RAWABI",
        "Stand 25 closed for urgent slab repair",
    ),
    (
        10,
        "Z-APR-21",
        WorksImpact.stand_closure,
        _utc(2026, 9, 24, 3),
        _utc(2026, 9, 29, 15),
        "DAILY 0300-1500",
        _utc(2026, 9, 16, 7),
        "A1000/26",
        NotamStatus.expired,
        "RAWABI",
        "Stand 27 closed for lighting works",
    ),
    (
        11,
        "Z-APR-21",
        WorksImpact.stand_closure,
        _utc(2026, 9, 28, 3),
        _utc(2026, 10, 15, 15),
        "DAILY 0300-1500",
        _utc(2026, 9, 19, 7),
        "A1001/26",
        NotamStatus.issued,
        "RAWABI",
        "Stands 21-22 closed for crane works",
    ),
    (
        12,
        "Z-TWB",
        WorksImpact.taxiway_closure,
        _utc(2026, 10, 1, 20),
        _utc(2026, 10, 22, 2),
        "DAILY 2000-0200",
        _utc(2026, 9, 22, 7),
        "A0999/26",
        NotamStatus.issued,
        "GULFPAVE",
        "TWY B between B2 and B4 closed due to works in progress",
    ),
    (
        14,
        "Z-ILS33R",
        WorksImpact.ils_outage,
        _utc(2026, 10, 8, 4),
        _utc(2026, 10, 12, 13),
        "DAILY 0400-1300",
        _utc(2026, 10, 3, 8),
        None,
        NotamStatus.requested_from_ais,
        "GULFPAVE",
        "RWY 33R glide path U/S for excavation in the GP critical area",
    ),
]


def _notams(ctx: Ctx) -> dict[int, NotamRequest]:
    db = ctx.db
    s = common.settings(db, ctx.project.id)
    rep = ctx.user_id("ahmed.zahrani")
    out = {}
    for seq, zone, impact, start, end, sched, sub, number, st, eng, desc in NOTAMS:
        lead = (common.local_day(start) - common.local_day(sub)).days
        late = lead < s.notam_request_lead_days
        issued = number is not None
        n = NotamRequest(
            id=uuid.uuid4(),
            year=2026,
            seq=seq,
            ntm_no=make_ref("NTM", ctx.project.code, 2026, seq, 4),
            project_id=ctx.project.id,
            zone_ids=[ctx.zones[zone].id],
            engagement_id=ctx.engs[eng].id,
            works_impact=[impact.value],
            description_en=desc,
            description_ar="أعمال في الجانب الجوي (بيانات تجريبية)",
            requested_start_utc=start,
            requested_end_utc=end,
            schedule_text=sched,
            submitted_to_ops_at=sub,
            late_request=late,
            late_justification="Programme change by the client (seed)" if late else None,
            notam_number=number,
            notam_type=NotamType.N if issued else None,
            effective_from_utc=start if issued else None,
            effective_to_utc=end if issued else None,
            item_e_text=("TWY B BTN B2 AND B4 CLSD DUE WIP" if seq == 12 else desc.upper())
            if issued
            else None,
            requested_by_user_id=rep or uuid.uuid4(),
            alerts_sent=[],
            status=st,
            created_by_user_id=rep,
            seed_fake=True,
            created_at=sub - timedelta(hours=2),
            updated_at=sub,
        )
        db.add(n)
        out[seq] = n
    db.flush()
    return out


def _obstacles(
    ctx: Ctx, veh: dict[int, Vehicle], ntm: dict[int, NotamRequest]
) -> dict[int, ObstacleClearance]:
    db = ctx.db
    rep = ctx.user_id("ahmed.zahrani")
    R = ClearanceReason  # noqa: N806
    OC = ObstacleCondition  # noqa: N806
    specs: list[dict[str, Any]] = [
        dict(
            seq=4,
            zone="Z-APR-21",
            eng="RAWABI",
            vehicle=veh[3].id,
            equipment_desc="50 t mobile crane VEH-0003",
            etype=ObstacleEquipmentType.mobile_crane,
            loc="Stand 22 (LM-22)",
            ground="612.40",
            height="32.00",
            surface=OlsSurface.inner_horizontal,
            ols="655.00",
            ols_ref="OEXX-OLS-DWG-TEST-03",
            reasons=[R.zone_height_exceeded, R.operator_requires],
            frm=date(2026, 10, 4),
            to=date(2026, 10, 10),
            submitted=date(2026, 9, 2),
            authority="GACA-OBS-TEST-0004",
            decision=ObstacleDecision.approved_with_conditions,
            decided=date(2026, 9, 24),
            conditions=[OC.obstruction_light, OC.lower_at_night, OC.lower_when_idle],
            ntm=[],
            status=ObstacleStatus.approved_with_conditions,
        ),
        dict(
            seq=7,
            zone="Z-ILS33R",
            eng="GULFPAVE",
            vehicle=veh[5].id,
            equipment_desc="20 t excavator VEH-0005 (height limiter 4.50 m)",
            etype=ObstacleEquipmentType.excavator,
            loc="RWY 33R GP critical area, grid G-7",
            ground="612.40",
            height="4.50",
            surface=OlsSurface.none_applicable,
            ols=None,
            ols_ref=None,
            reasons=[R.zone_height_exceeded, R.operator_requires],
            frm=date(2026, 10, 8),
            to=date(2026, 10, 12),
            submitted=date(2026, 9, 5),
            authority="GACA-OBS-TEST-0007",
            decision=ObstacleDecision.approved_with_conditions,
            decided=date(2026, 10, 2),
            conditions=[OC.notam_required, OC.daylight_only, OC.day_marking],
            ntm=[ntm[14].id],
            status=ObstacleStatus.approved_with_conditions,
        ),
        dict(
            seq=9,
            zone="Z-TWB",
            eng="RAWABI",
            vehicle=None,
            equipment_desc="35 m mobile crane (proposal)",
            etype=ObstacleEquipmentType.mobile_crane,
            loc="TWY B strip, grid B-3",
            ground="612.40",
            height="35.00",
            surface=OlsSurface.transitional,
            ols="642.50",
            ols_ref="OEXX-OLS-DWG-TEST-03",
            reasons=[R.zone_height_exceeded, R.ols_penetration, R.operator_requires],
            frm=date(2026, 10, 15),
            to=date(2026, 10, 20),
            submitted=date(2026, 9, 10),
            authority="GACA-OBS-TEST-0009",
            decision=ObstacleDecision.rejected,
            decided=date(2026, 9, 25),
            conditions=[],
            ntm=[],
            status=ObstacleStatus.rejected,
        ),
    ]
    out = {}
    for sp in specs:
        ground, height = Decimal(sp["ground"]), Decimal(sp["height"])
        top = ground + height
        ols = Decimal(sp["ols"]) if sp["ols"] else None
        pen = max(Decimal(0), top - ols) if ols is not None else Decimal(0)
        approved = sp["decision"] != ObstacleDecision.rejected
        o = ObstacleClearance(
            id=uuid.uuid4(),
            year=2026,
            seq=sp["seq"],
            obs_no=make_ref("OBS", ctx.project.code, 2026, sp["seq"], 4),
            project_id=ctx.project.id,
            zone_id=ctx.zones[sp["zone"]].id,
            engagement_id=ctx.engs[sp["eng"]].id,
            vehicle_id=sp["vehicle"],
            equipment_desc=sp["equipment_desc"],
            equipment_type=sp["etype"],
            location_lat=Decimal("24.955100"),
            location_lng=Decimal("46.699200"),
            location_desc=sp["loc"],
            ground_elevation_m_amsl=ground,
            max_height_m_agl=height,
            ols_surface=sp["surface"],
            ols_limit_m_amsl=ols,
            ols_source_ref=sp["ols_ref"],
            clearance_reasons=[r.value for r in sp["reasons"]],
            top_elevation_m_amsl=top,
            penetration_m=pen,
            requested_from=sp["frm"],
            requested_to=sp["to"],
            submitted_at=_at(sp["submitted"], 10),
            late_request=False,
            authority_ref=sp["authority"],
            decision=sp["decision"],
            decided_at=_at(sp["decided"], 12),
            approved_max_height_m_agl=height if approved else None,
            approved_top_m_amsl=top if approved else None,
            conditions=[c.value for c in sp["conditions"]],
            conditions_text=None,
            valid_from=sp["frm"] if approved else None,
            valid_to=sp["to"] if approved else None,
            linked_ntm_ids=sp["ntm"],
            system_suspended=False,
            requested_by_user_id=rep or uuid.uuid4(),
            alerts_sent=[],
            status=sp["status"],
            created_by_user_id=rep,
            seed_fake=True,
            created_at=_at(sp["submitted"], 9),
            updated_at=_at(sp["decided"], 12),
        )
        db.add(o)
        out[sp["seq"]] = o
    db.flush()
    return out


OPS: list[tuple[Any, ...]] = [
    (4, OpsEventType.dust_sandstorm, _utc(2026, 6, 12, 10), _utc(2026, 6, 12, 14, 30), "140"),
    (5, OpsEventType.dust_sandstorm, _utc(2026, 7, 3, 9), _utc(2026, 7, 3, 12), "163"),
    (6, OpsEventType.thunderstorm_lightning, _utc(2026, 7, 28, 13), _utc(2026, 7, 28, 14), "178"),
    (7, OpsEventType.dust_sandstorm, _utc(2026, 8, 14, 11), _utc(2026, 8, 14, 15), "196"),
    (8, OpsEventType.dust_sandstorm, _utc(2026, 9, 6, 10), _utc(2026, 9, 6, 12, 30), "209"),
    (9, OpsEventType.lvp, _utc(2026, 9, 28, 1, 10), _utc(2026, 9, 28, 4, 40), "221"),
]


def _ops(ctx: Ctx) -> dict[int, OpsEvent]:
    db = ctx.db
    khalid = ctx.user_id("khalid.otaibi")
    lvp = [ctx.zones["Z-TWB"].id, ctx.zones["Z-ILS33R"].id]
    out = {}
    for seq, typ, start, end, log in OPS:
        zones = (
            lvp
            if typ != OpsEventType.thunderstorm_lightning
            else [ctx.zones[z].id for z in ("Z-APR-21", "Z-TWB", "Z-ILS33R")]
        )
        o = OpsEvent(
            id=uuid.uuid4(),
            year=2026,
            seq=seq,
            ops_no=make_ref("OPS", ctx.project.code, 2026, seq, 4),
            project_id=ctx.project.id,
            site_id=ctx.sites["S-AIR"].id,
            type=typ,
            zone_ids=zones,
            default_zone_ids=lvp,
            source=OpsEventSource.aocc,
            source_ref=f"AOCC-LOG-TEST-{log}",
            started_at=start,
            ended_at=end,
            declared_by_user_id=khalid or uuid.uuid4(),
            notes="Dust reducing visibility (LVP)" if seq == 9 else None,
            suspended_wap_ids=[],
            created_by_user_id=khalid,
            seed_fake=True,
            created_at=start,
            updated_at=end,
        )
        db.add(o)
        out[seq] = o
    db.flush()
    return out


def _window(start: str, end: str) -> list[dict[str, Any]]:
    from app.services.access.windows import ALL_DAYS  # noqa: PLC0415

    return [{"start_local": start, "end_local": end, "weekdays": list(ALL_DAYS)}]


def _crew_pool(ctx: Ctx, eng: str, area: str, until: date, extra: str | None = None) -> list[Plan]:
    out = []
    for p in ctx.plans:
        if p.named or p.project != "ANIA-EXP" or p.eng != eng or p.demob is not None:
            continue
        if area not in p.areas or p.id_exp < until + timedelta(days=30):
            continue
        if not (_has(p, "GEN", until) and _has(p, "AIR", until) and _has(p, "GEN", TODAY)):
            continue
        if extra and not _has(p, extra, until):
            continue
        out.append(p)
    return out


@dataclass
class WapSpec:
    seq: int
    eng: str
    zone: str
    valid_from: date
    valid_to: date
    window: tuple[str, str]
    supervisor: Plan
    crew: list[Any]  # (plan, role, escort plan | None)
    vehicles: list[tuple[int, int | None, Decimal | None]]
    status: WapStatus
    approved: datetime | None
    activated: datetime | None = None
    closed: datetime | None = None
    ntm: list[uuid.UUID] = field(default_factory=list)
    obs: list[uuid.UUID] = field(default_factory=list)
    scope: tuple[str, str] = ("Airside works (seed)", "أعمال في الجانب الجوي (تجريبية)")
    wsp: str | None = None
    fod: bool = False


def _plan_waps(
    ctx: Ctx, ntm: dict[int, NotamRequest], obs: dict[int, ObstacleClearance]
) -> list[WapSpec]:
    rng = ctx.rng
    P = ctx.plan  # noqa: N806
    W = CrewRole.worker  # noqa: N806
    gp_m = _crew_pool(ctx, "GULFPAVE", "M", date(2026, 10, 21))
    rng.shuffle(gp_m)
    rw_a = _crew_pool(ctx, "RAWABI", "A", date(2026, 10, 10))
    rng.shuffle(rw_a)
    crew31, rest = gp_m[:6], gp_m[6:]
    ils = [p for p in rest if p.id_exp > date(2026, 12, 31)][:3]
    for p in ils:  # ILS briefing for the WAP-0035 crew
        d = _pick_day(ctx, "GULFPAVE", date(2026, 8, 1), date(2026, 9, 28)) or date(2026, 9, 1)
        p.inductions += _gen(d, code="ILS", months=6)
    crew29 = rest[3:7]
    tariq, rajesh, abdul = P(13), P(2), P(4)
    specs = [
        WapSpec(
            29,
            "GULFPAVE",
            "Z-TWB",
            date(2026, 9, 20),
            date(2026, 9, 30),
            ("23:00", "05:00"),
            tariq,
            [(p, W, None) for p in crew29],
            [(1, None, None)],
            WapStatus.closed,
            _at(date(2026, 9, 18), 11),
            _at(date(2026, 9, 20), 23),
            _at(date(2026, 10, 1), 5, 30),
            ntm=[ntm[8].id],
            scope=("TWY B B2-B3 pavement works (night)", "أعمال رصف الممر B (ليلاً)"),
            wsp="WSP-TWB-006",
            fod=True,
        ),
        WapSpec(
            31,
            "GULFPAVE",
            "Z-TWB",
            date(2026, 10, 1),
            date(2026, 10, 21),
            ("23:00", "05:00"),
            tariq,
            [(rajesh, CrewRole.driver, None), (abdul, W, tariq)] + [(p, W, None) for p in crew31],
            [(1, None, None), (2, None, None)],
            WapStatus.active,
            _at(date(2026, 9, 29), 10),
            _at(date(2026, 10, 1), 23),
            ntm=[ntm[12].id],
            scope=(
                "Taxiway B rehabilitation between B2 and B4 (night works)",
                "إعادة تأهيل الممر B بين B2 وB4 (أعمال ليلية)",
            ),
            wsp="WSP-TWB-007",
            fod=True,
        ),
        WapSpec(
            33,
            "RAWABI",
            "Z-APR-21",
            date(2026, 10, 4),
            date(2026, 10, 10),
            ("06:00", "18:00"),
            P(5),
            [(p, W, None) for p in rw_a[:5]],
            [(3, None, None), (4, 6, None), (6, None, None)],
            WapStatus.active,
            _at(date(2026, 10, 2), 10),
            _at(date(2026, 10, 4), 6),
            ntm=[ntm[11].id],
            obs=[obs[4].id],
            scope=(
                "Crane lift of apron lighting masts, stands 21-22",
                "رفع أعمدة إنارة الساحة بالرافعة، المواقف 21-22",
            ),
            wsp="WSP-APR-004",
        ),
        WapSpec(
            35,
            "GULFPAVE",
            "Z-ILS33R",
            date(2026, 10, 8),
            date(2026, 10, 12),
            ("07:00", "16:00"),
            tariq,
            [(P(7), W, None)] + [(p, W, None) for p in ils],
            [(5, None, Decimal("4.50"))],
            WapStatus.approved,
            _at(date(2026, 10, 5), 11),
            ntm=[ntm[14].id],
            obs=[obs[7].id],
            scope=(
                "Cable duct excavation in the RWY 33R GP critical area",
                "حفر مجرى كابلات في المنطقة الحرجة لمسار الانزلاق 33R",
            ),
            wsp="WSP-ILS-002",
            fod=True,
        ),
    ]
    # background history (Jun-Sep, closed) for K-58 trends
    hist = [
        (21, "GULFPAVE", "Z-TWB", date(2026, 6, 14), date(2026, 6, 20), ("23:00", "05:00")),
        (22, "RAWABI", "Z-APR-21", date(2026, 6, 28), date(2026, 7, 5), ("06:00", "18:00")),
        (23, "GULFPAVE", "Z-TWB", date(2026, 7, 16), date(2026, 7, 24), ("23:00", "05:00")),
        (24, "GULFPAVE", "Z-ILS33R", date(2026, 8, 3), date(2026, 8, 6), ("07:00", "16:00")),
        (25, "RAWABI", "Z-APR-21", date(2026, 8, 18), date(2026, 8, 25), ("06:00", "18:00")),
        (26, "GULFPAVE", "Z-TWB", date(2026, 9, 2), date(2026, 9, 8), ("23:00", "05:00")),
        (27, "RAWABI", "Z-APR-21", date(2026, 9, 10), date(2026, 9, 14), ("06:00", "18:00")),
        (28, "RAWABI", "Z-APR-21", date(2026, 9, 24), date(2026, 9, 29), ("06:00", "18:00")),
    ]
    for seq, eng, zone, vf, vt, win in hist:
        sup = tariq if eng == "GULFPAVE" else P(5)
        pool = rest[8:20] if eng == "GULFPAVE" else rw_a[5:15]
        specs.append(
            WapSpec(
                seq,
                eng,
                zone,
                vf,
                vt,
                win,
                sup,
                [(p, W, None) for p in pool[:3]],
                [],
                WapStatus.closed,
                _at(vf - timedelta(days=2), 10),
                _at(vf, int(win[0][:2])),
                _at(vt + timedelta(days=1), 6),
            )
        )
    return specs


def _waps(ctx: Ctx, specs: list[WapSpec], veh: dict[int, Vehicle]) -> dict[int, Wap]:
    db = ctx.db
    rep = ctx.user_id("ahmed.zahrani")
    khalid = ctx.user_id("khalid.otaibi")
    out = {}
    for sp in specs:
        w = Wap(
            id=uuid.uuid4(),
            year=2026,
            seq=sp.seq,
            wap_no=make_ref("WAP", ctx.project.code, 2026, sp.seq, 4),
            revision_no=0,
            project_id=ctx.project.id,
            site_id=ctx.sites["S-AIR"].id,
            zone_ids=[ctx.zones[sp.zone].id],
            engagement_id=ctx.engs[sp.eng].id,
            requested_by_user_id=rep or uuid.uuid4(),
            supervisor_worker_id=sp.supervisor.wid,
            scope_en=sp.scope[0],
            scope_ar=sp.scope[1],
            works_safety_plan_ref=sp.wsp,
            valid_from=sp.valid_from,
            valid_to=sp.valid_to,
            windows=_window(*sp.window),
            operator_permit_ref=f"OP-PERMIT-TEST-{sp.seq:04d}",
            linked_ntm_ids=sp.ntm,
            linked_obs_ids=sp.obs,
            fod_handback_required=sp.fod,
            fod_check=None,
            submitted_at=(sp.approved - timedelta(days=3)) if sp.approved else None,
            approved_by_user_id=khalid if sp.approved else None,
            approved_at=sp.approved,
            activated_at=sp.activated,
            closed_at=sp.closed,
            blockers=[],
            alerts_sent=[],
            status=sp.status,
            created_by_user_id=rep,
            seed_fake=True,
            created_at=(sp.approved or AT_TODAY) - timedelta(days=4),
            updated_at=sp.closed or sp.activated or sp.approved or AT_TODAY,
        )
        db.add(w)
        db.flush()
        out[sp.seq] = w
        members = [(sp.supervisor, CrewRole.supervisor, None), *sp.crew]
        for p, role, escort in members:
            db.add(
                WapCrew(
                    id=uuid.uuid4(),
                    wap_id=w.id,
                    worker_id=p.wid,
                    crew_role=role,
                    escort_worker_id=escort.wid if escort else None,
                    status=CrewMemberStatus.included,
                    exclusion_reasons=[],
                    escorted=escort is not None,
                    eligible_now=None,
                    evaluated_at=None,
                )
            )
        for vseq, escort_seq, limit in sp.vehicles:
            db.add(
                WapVehicle(
                    id=uuid.uuid4(),
                    wap_id=w.id,
                    vehicle_id=veh[vseq].id,
                    escort_vehicle_id=veh[escort_seq].id if escort_seq else None,
                    height_limited_to_m=limit,
                    status=CrewMemberStatus.included,
                    exclusion_reasons=[],
                )
            )
    db.flush()
    return out


def _wap_history(ctx: Ctx, waps: dict[int, Wap], ops: dict[int, OpsEvent]) -> None:
    """WAP-0029 suspended by OPS-0009 (2026-09-28 01:10Z) and resumed after a FOD check at
    23:00 local; QR tokens for the Active WAPs."""
    db = ctx.db
    khalid = ctx.user_id("khalid.otaibi")
    w29 = waps[29]
    ops[9].suspended_wap_ids = [w29.id]
    for action, reason, at, actor in (
        (CredentialAction.auto_suspended, CredentialReason.ops_suspension, ops[9].started_at, None),
        (
            CredentialAction.reinstated,
            CredentialReason.ops_suspension,
            _utc(2026, 9, 28, 20),
            khalid,
        ),
    ):
        db.add(
            CredentialEvent(
                id=uuid.uuid4(),
                project_id=ctx.project.id,
                credential_kind=lifecycle.kind_of(w29),
                credential_id=w29.id,
                action=action,
                reason_code=reason,
                reason_text=ops[9].ops_no,
                actor_user_id=actor,
                occurred_at=at,
                seed_fake=True,
            )
        )
    w29.fod_check = {
        "checked_by_worker_id": str(ctx.plan(13).wid),
        "checked_by_user_id": str(khalid) if khalid else None,
        "checked_at": _utc(2026, 9, 28, 19, 40).isoformat(),
        "result": "clear",
        "notes": "FOD walk completed after LVP (seed)",
    }
    for seq in (31, 33):
        with frozen(waps[seq].activated_at or AT_TODAY):
            common.issue_qr(db, QrKind.WP, ctx.project.id, waps[seq].id, waps[seq].wap_no)
    db.flush()


# ---- gate log (A.1.5) ----------------------------------------------------------------------------

ANIA_GATE_MONTHS = {  # month → (in-direction checks, denied)
    date(2026, 6, 1): (74_909, 412),
    date(2026, 7, 1): (75_806, 470),
    date(2026, 8, 1): (74_655, 433),
    date(2026, 9, 1): (74_880, 449),
}
ANIA_SEP_REASONS = {
    "INDUCTION_EXPIRED": 151,
    "PASS_AREA_NOT_COVERED": 88,
    "WAP_MISSING": 71,
    "ESCORT_REQUIRED": 54,
    "ADP_MISSING": 33,
    "ID_EXPIRED": 29,
    "INDUCTION_MISSING": 6,
    "PASS_EXPIRED": 5,
    "WORKER_NOT_DEPLOYED": 5,
    "CREDENTIAL_REVOKED": 4,
    "AVP_MISSING": 3,
}
AIRSIDE_REASONS = {
    "PASS_AREA_NOT_COVERED",
    "WAP_MISSING",
    "ESCORT_REQUIRED",
    "ADP_MISSING",
    "PASS_EXPIRED",
    "AVP_MISSING",
}
RBT_GATE_MONTHS = {date(2026, 9, 1): (13_520, 62)}
RBT_SEP_REASONS = {"INDUCTION_EXPIRED": 30, "CONTRACTOR_SUSPENDED": 18, "INDUCTION_MISSING": 14}
GATE_COLUMNS = (
    "id",
    "occurred_at",
    "local_date",
    "project_id",
    "site_id",
    "gate_id",
    "device_pk",
    "user_id",
    "direction",
    "qr_kind",
    "subject_kind",
    "worker_id",
    "deployment_id",
    "vehicle_id",
    "wap_id",
    "engagement_id",
    "subject_ref",
    "zone_id",
    "result",
    "reason_codes",
    "first_deny_reason",
    "final",
    "pairing_id",
    "late_exit",
    "admitted_despite_denial",
    "admitted_reason",
    "admitted_by_user_id",
    "admitted_at",
    "incident_id",
    "seed_fake",
)


def _scale(reasons: dict[str, int], total: int) -> dict[str, int]:
    """Largest-remainder scaling of the Sep reason mix to another month's denied total."""
    base = sum(reasons.values())
    raw = {k: Decimal(v) * total / base for k, v in reasons.items()}
    out = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda x: raw[x] - out[x], reverse=True)[: total - sum(out.values())]:
        out[k] += 1
    return out


def _weight(d: date) -> float:
    return 0.15 if d.weekday() == 4 else 1.0


def _gate_log(ctx: Ctx) -> int:
    db = ctx.db
    rng = ctx.rng
    code = ctx.project.code
    gates = {
        g.gate_code: g for g in db.scalars(select(Gate).where(Gate.project_id == ctx.project.id))
    }
    devices: dict[uuid.UUID, uuid.UUID] = {}
    for dev in db.scalars(select(GateDevice).order_by(GateDevice.device_id)):
        devices.setdefault(dev.gate_id, dev.id)
    if code == "ANIA-EXP":
        months, sep = ANIA_GATE_MONTHS, ANIA_SEP_REASONS
        main, zone_gate = gates["G-ANIA-01"], gates["G-AAP3"]
        main_site, zone_site = "S-LAND", "S-AIR"
        zone_codes, zone_w, zone_share = ["Z-APR-21", "Z-TWB", "Z-ILS33R"], [5, 4, 1], 0.28
    else:
        months, sep = RBT_GATE_MONTHS, RBT_SEP_REASONS
        main, zone_gate = gates["G-RBT-01"], gates["G-RBT-TC"]
        main_site, zone_site = "S-TWR", "S-TWR"
        zone_codes, zone_w, zone_share = ["Z-TC01"], [1], 0.10
    plans = [p for p in ctx.plans if p.project == code and p.eng is not None]

    def pool(site: str, engs: set[str] | None = None) -> list[Plan]:
        return sorted(
            (p for p in plans if site in p.sites and (engs is None or p.eng in engs)),
            key=lambda p: p.mob,
        )

    import bisect  # noqa: PLC0415

    pools: dict[tuple[str, str], tuple[list[Plan], list[date]]] = {}

    def pick(site: str, day: date, kind: str = "all") -> Plan:
        key = (site, kind)
        if key not in pools:
            engs = {"DLIFT"} if kind == "dlift" else ({"QIMMA"} if kind == "no_dlift" else None)
            if kind == "no_dlift" and code != "RBT-52":
                engs = None
            ps = pool(site, engs)
            pools[key] = (ps, [p.mob for p in ps])
        ps, mobs = pools[key]
        n = bisect.bisect_right(mobs, day)
        while True:
            p = ps[rng.randrange(max(1, n))]
            if p.demob is None or p.demob > day:
                return p

    rows: list[tuple[Any, ...]] = []
    admitted_left = 2 if code == "ANIA-EXP" else 0
    noura = ctx.user_id("noura.qahtani")
    for m, (total, denied) in months.items():
        days = _days(m, month_end(m))
        weights = [_weight(d) for d in days]
        reasons = sep if m == date(2026, 9, 1) else _scale(sep, denied)
        assert sum(reasons.values()) == denied  # noqa: S101
        n_zone = round(total * zone_share)
        items: list[tuple[Gate, str | None]] = []
        z_denied = 0
        for r, c in reasons.items():
            frac = 1.0 if r in AIRSIDE_REASONS else 0.3
            if code == "RBT-52":
                frac = 0.1
            cz = round(c * frac)
            z_denied += cz
            items += [(zone_gate, r)] * cz + [(main, r)] * (c - cz)
        items += [(zone_gate, None)] * (n_zone - z_denied)
        items += [(main, None)] * (total - n_zone - (denied - z_denied))
        assert len(items) == total  # noqa: S101
        picked_days = rng.choices(days, weights=weights, k=total)
        for (gate, reason), day in zip(items, picked_days, strict=True):
            on_zone = gate is zone_gate
            site = zone_site if on_zone else main_site
            kind = (
                "dlift"
                if reason == "CONTRACTOR_SUSPENDED"
                else ("no_dlift" if code == "RBT-52" and day >= date(2026, 8, 15) else "all")
            )
            p = pick(site, day, kind)
            if on_zone and code == "ANIA-EXP" and p.eng not in ("GULFPAVE", "RAWABI"):
                p = pick(site, day)
            night = p.eng == "GULFPAVE" and rng.random() < 0.6
            hour = rng.choice([21, 22]) if night else rng.choice([5, 6, 6, 7, 7, 8])
            at = _at(day, hour, rng.randrange(60))
            if reason:
                result, codes, first = GateResult.DENIED.value, [reason], reason
            elif on_zone and code == "ANIA-EXP":
                result, codes, first = (
                    GateResult.GRANTED_WITH_WARNING.value,
                    ["HOOK_NOT_AVAILABLE"],
                    None,
                )
            else:
                result, codes, first = GateResult.GRANTED.value, [], None
            admitted = bool(
                reason
                and admitted_left
                and m == date(2026, 9, 1)
                and day >= date(2026, 9, 15)
                and reason == "ESCORT_REQUIRED"
            )
            if admitted:
                admitted_left -= 1
            eng = ctx.engs[p.eng].id if p.eng else None
            zone_id = ctx.zones[rng.choices(zone_codes, weights=zone_w)[0]].id if on_zone else None
            rows.append(
                (
                    uuid.uuid4(),
                    at,
                    day,
                    ctx.project.id,
                    ctx.sites[site].id,
                    gate.id,
                    devices.get(gate.id),
                    None,
                    GateDirection.in_.value,
                    QrKind.AC.value,
                    GateSubjectKind.person.value,
                    p.wid,
                    p.did,
                    None,
                    None,
                    eng,
                    p.no,
                    zone_id,
                    result,
                    codes,
                    first,
                    True,
                    None,
                    False,
                    admitted,
                    "Escort arrived late; admitted by the gate supervisor (seed)"
                    if admitted
                    else None,
                    noura if admitted else None,
                    at + timedelta(minutes=4) if admitted else None,
                    None,
                    True,
                )
            )
    cols = ", ".join(GATE_COLUMNS)
    raw: Any = db.connection().connection.driver_connection
    with raw.cursor() as cur, cur.copy(f"COPY gate_checks ({cols}) FROM STDIN") as cp:
        for row in rows:
            cp.write_row(row)
    return len(rows)


# ---- orchestration -------------------------------------------------------------------------------


def _link_injury_case(db: Session, ctx: Ctx) -> None:
    """A.3: WKR-000001 linked to INC-ANIA-EXP-2026-0147 person 1 (v1.1 worker_id)."""
    inc = db.scalar(select(Incident).where(Incident.ref == "INC-ANIA-EXP-2026-0147"))
    if inc is None:
        return
    case = db.scalar(
        select(InjuryCase).where(InjuryCase.incident_id == inc.id, InjuryCase.person_no == 1)
    )
    if case is not None and case.worker_id is None:
        case.worker_id = ctx.plan(1).wid


def already_seeded(db: Session) -> bool:
    return db.scalar(select(Worker.id).where(Worker.seed_fake.is_(True)).limit(1)) is not None


def seed_access_data(db: Session) -> None:
    """Appendix A volume data for both projects (skipped when seeded workers exist)."""
    seed_access_reference(db)
    if already_seeded(db):
        return
    rng = random.Random(20261006)
    users = _users(db)
    projects = _projects(db)
    named = _named()
    counters = {"seq": 1000, "iqama": 2000001999, "nid": 1000001999, "rawabi_air": 0}
    for code in ("ANIA-EXP", "RBT-52"):
        project = projects.get(code)
        if project is None:
            continue
        ctx = Ctx(
            db,
            rng,
            project,
            _sites(db, project.id),
            _zones(db, project.id),
            _engs(db, project.id),
            users,
        )
        ctx.courses = {
            c.code: c
            for c in db.scalars(
                select(InductionCourse).where(InductionCourse.project_id == project.id)
            )
        }
        ctx.plans = [p for p in named if p.project == code]
        _candidate_days(ctx)
        _bulk_plans(ctx, counters)
        x8 = _x8_plans(ctx, counters) if code == "ANIA-EXP" else []
        _extra_courses(ctx)
        if code == "ANIA-EXP":
            specs, adps = _passes(ctx, x8)
            veh = _vehicles(ctx)
            ntm = _notams(ctx)
            obs = _obstacles(ctx, veh, ntm)
            ops = _ops(ctx)
            wap_specs = _plan_waps(ctx, ntm, obs)
        _insert_people(ctx)
        counts = _insert_inductions(ctx)
        _rewrite_returns(ctx, counts)
        db.flush()
        if code == "ANIA-EXP":
            _insert_passes(ctx, specs, adps)
            db.flush()
            _custody(ctx, x8)
            _offences(ctx, adps)
            waps = _waps(ctx, wap_specs, veh)
            _wap_history(ctx, waps, ops)
            _link_injury_case(db, ctx)
            db.flush()
            _refresh_waps(db, waps)
        _gate_log(ctx)
        db.flush()
    _assert_ids(db)


def _refresh_waps(db: Session, waps: dict[int, Wap]) -> None:
    """Crew evaluation and blockers as of 2026-10-06 10:00 local (WA-10, WA-13)."""
    from app.services.access import waps as wap_svc  # noqa: PLC0415

    with frozen(AT_TODAY):
        for seq in (31, 33, 35):
            w = waps[seq]
            before = w.status
            wap_svc.refresh(db, w, at=AT_TODAY, evaluate=True)
            if w.status != before:
                raise RuntimeError(f"Seed: {w.wap_no} moved {before} → {w.status} ({w.blockers})")
    db.flush()


ID_SEED_RE = r"^(2000000017|20000010\d\d|20000011\d\d|200000[2-9]\d{3}|100000[12]\d{3}|TEST\d{5})$"


def _assert_ids(db: Session) -> None:
    """A.1.1 CI rule: seeded worker IDs only from the fictional ranges."""
    import re  # noqa: PLC0415

    pat = re.compile(ID_SEED_RE)
    for enc in db.scalars(select(Worker.id_number_enc).where(Worker.seed_fake.is_(True))):
        if enc is not None and not pat.match(crypto.decrypt(enc)):
            raise RuntimeError("Seed: worker ID outside the fictional ranges (A.1.1)")
