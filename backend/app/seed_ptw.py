"""Phase 3 seed (spec 3-ptw Appendix A; every row `seed_fake`).

Runs on top of the Phase 0/1/2 Appendix A world. Order:
1. reference — A.2 users, A.4 named workers (converted from Phase 2 bulk workers of the same
   engagement so every Phase 2 count is unchanged), A.10 obstacle clearance, A.5 zone profiles
   and adjacency, A.3 appointments, A.6 detectors / bump tests / locks, A.9 JSA templates;
2. bulk — June–September 2026 history written as rows (terminal permits, shifts, suspensions,
   audits, conflicts, isolations) so every Y12 figure and its history is reproduced exactly;
3. named — the A.7 permits driven through the real services with a pinned clock (signatures,
   hashes, blockers, shifts and gas tests exactly as the API would make them), then the A.8
   audits; the clock ends at the seed time 2026-10-06 10:00 (Asia/Riyadh).
"""

from __future__ import annotations

import random
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.access_enums import ObstacleStatus
from app.core.clock import now, set_now
from app.core.enums import EmployerType, Language, Role, UserStatus
from app.core.hse_enums import Trade
from app.core.ptw_enums import (
    AppointmentDiscipline,
    AppointmentFunction,
    AppointmentStatus,
    BumpTestResult,
    DetectorStatus,
    Exposure,
    HazardousAreaClass,
    JsaStatus,
    LelReferenceGas,
    LockStatus,
    LockType,
    PermitType,
    QuarantineReason,
    VerticalRelation,
)
from app.core.security import hash_password
from app.core.text import search_blob
from app.models import (
    BumpTest,
    Contractor,
    Deployment,
    GasDetector,
    InductionRecord,
    Jsa,
    Lock,
    ObstacleClearance,
    Project,
    ProjectEngagement,
    PtwAppointment,
    RoleAssignment,
    Site,
    User,
    UserSession,
    Worker,
    Zone,
    ZoneAdjacency,
)
from app.services.access import common as acommon

RIYADH = ZoneInfo("Asia/Riyadh")
SEED_AT = datetime(2026, 10, 6, 7, 0, tzinfo=UTC)  # 10:00 local (A.1)
T = PermitType
ALL_TYPES = [t.value for t in PermitType]
F = AppointmentFunction
D = AppointmentDiscipline


def at(y: int, m: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    """Local Riyadh wall time → UTC."""
    return datetime(y, m, d, h, mi, tzinfo=RIYADH).astimezone(UTC)


@contextmanager
def clock(t: datetime) -> Iterator[None]:
    set_now(t)
    try:
        yield
    finally:
        pass


# ---- context -------------------------------------------------------------------------------------


@dataclass
class Ctx:
    db: Session
    rng: random.Random
    projects: dict[str, Project] = field(default_factory=dict)
    sites: dict[tuple[str, str], Site] = field(default_factory=dict)
    zones: dict[str, Zone] = field(default_factory=dict)
    engs: dict[tuple[str, str], ProjectEngagement] = field(default_factory=dict)
    users: dict[str, User] = field(default_factory=dict)
    workers: dict[str, Worker] = field(default_factory=dict)  # worker_no → worker
    apts: dict[str, PtwAppointment] = field(default_factory=dict)
    detectors: dict[str, GasDetector] = field(default_factory=dict)
    locks: dict[str, Lock] = field(default_factory=dict)
    templates: dict[str, Jsa] = field(default_factory=dict)
    permits: dict[str, Any] = field(default_factory=dict)
    bulk_used: set[uuid.UUID] = field(default_factory=set)
    password: str = "Seed-Passw0rd!2026"

    def pid(self, code: str) -> uuid.UUID:
        return self.projects[code].id

    def eng(self, project: str, contractor: str) -> ProjectEngagement:
        return self.engs[(project, contractor)]

    def site(self, project: str, code: str) -> Site:
        return self.sites[(project, code)]

    def user(self, key: str) -> User:
        return self.users[key]

    def uid(self, key: str) -> uuid.UUID:
        return self.users[key].id


def _load(db: Session) -> Ctx:
    ctx = Ctx(db, random.Random(20261006))
    ctx.projects = {p.code: p for p in db.scalars(select(Project))}
    code_of = {p.id: p.code for p in ctx.projects.values()}
    for s in db.scalars(select(Site)):
        ctx.sites[(code_of[s.project_id], s.code)] = s
    for z in db.scalars(select(Zone)):
        ctx.zones[z.code] = z
    for e, c in db.execute(
        select(ProjectEngagement, Contractor).join(
            Contractor, Contractor.id == ProjectEngagement.contractor_id
        )
    ):
        ctx.engs[(code_of[e.project_id], c.short_code)] = e
    ctx.users = {u.email.split("@")[0]: u for u in db.scalars(select(User))}
    ctx.workers = {w.worker_no: w for w in db.scalars(select(Worker).where(Worker.seq < 1000))}
    return ctx


# ---- A.2 users -----------------------------------------------------------------------------------

# (key, name_en, name_ar, mobile, employer, job, [(role, project, sites, engagement contractor)])
NEW_USERS: list[
    tuple[str, str, str, str, Any, str, list[tuple[Role, str, list[str], str | None]]]
] = [
    (
        "majed.shammari",
        "Majed Al-Shammari",
        "ماجد الشمري",
        "+966500000009",
        EmployerType.pmc_consultant,
        "Permit Issuer",
        [(Role.permit_issuer, "RBT-52", [], None)],
    ),
    (
        "joseph.mathew",
        "Joseph Mathew",
        "جوزيف ماثيو",
        "+966500000010",
        "QIMMA",
        "Supervisor",
        [(Role.permit_receiver, "RBT-52", [], "QIMMA")],
    ),
    (
        "fahad.mutairi",
        "Fahad Al-Mutairi",
        "فهد المطيري",
        "+966500000011",
        "RAWABI",
        "Site Engineer",
        [(Role.site_engineer, "ANIA-EXP", ["S-LAND"], None)],
    ),
    (
        "ibrahim.saleh",
        "Ibrahim Al-Saleh",
        "إبراهيم الصالح",
        "+966500000012",
        "QIMMA",
        "Site Engineer",
        [(Role.site_engineer, "RBT-52", ["S-TWR", "S-POD"], None)],
    ),
    (
        "lina.haddad",
        "Lina Haddad",
        "لينا حداد",
        "+966500000013",
        EmployerType.pmc_consultant,
        "HSE Officer",
        [(Role.hse_officer, "RBT-52", [], None)],
    ),
    (
        "sanjay.verma",
        "Sanjay Verma",
        "سانجاي فيرما",
        "+966500000014",
        "GULFPAVE",
        "Supervisor",
        [(Role.permit_receiver, "ANIA-EXP", [], "GULFPAVE")],
    ),
    (
        "faris.anazi",
        "Faris Al-Anazi",
        "فارس العنزي",
        "+966500000015",
        "RAWABI",
        "Supervisor",
        [(Role.permit_receiver, "ANIA-EXP", [], "RAWABI")],
    ),
    (
        "nasser.shahrani",
        "Nasser Al-Shahrani",
        "ناصر الشهراني",
        "+966500000016",
        "RAWABI",
        "Electrical Engineer",
        [(Role.site_engineer, "ANIA-EXP", ["S-LAND"], None)],
    ),
]


def _seed_users(ctx: Ctx, password: str | None) -> None:
    db = ctx.db
    from app.core.config import get_settings

    pw = hash_password(password) if password else None
    if pw is None:
        ref = ctx.users.get("noura.qahtani")
        pw = ref.password_hash if ref else hash_password("Seed-Passw0rd!2026")
    version = get_settings().privacy_notice_version
    contractors = {c.short_code: c for c in db.scalars(select(Contractor))}
    created = at(2026, 1, 1, 8)
    for key, en, ar, mobile, employer, job, roles in NEW_USERS:
        if key in ctx.users:
            continue
        is_con = not isinstance(employer, EmployerType)
        u = User(
            id=uuid.uuid4(),
            email=f"{key}@example.com",
            full_name_en=en,
            full_name_ar=ar,
            mobile=mobile,
            employer_type=EmployerType.contractor if is_con else employer,
            employer_contractor_id=contractors[employer].id if is_con else None,
            job_title=job,
            preferred_language=Language.en,
            status=UserStatus.active,
            password_hash=pw,
            activated_at=created,
            privacy_notice_version=version,
            privacy_notice_ack_at=created,
            search_text=search_blob(en, ar, f"{key}@example.com"),
        )
        db.add(u)
        db.flush()
        for role, pcode, site_codes, eng_code in roles:
            db.add(
                RoleAssignment(
                    id=uuid.uuid4(),
                    user_id=u.id,
                    role=role,
                    project_id=ctx.pid(pcode),
                    site_ids=[ctx.site(pcode, s).id for s in site_codes],
                    contractor_engagement_id=ctx.eng(pcode, eng_code).id if eng_code else None,
                    valid_from=date(2026, 1, 1),
                    created_at=created,
                )
            )
        ctx.users[key] = u
    db.flush()


# ---- A.4 named workers (converted from bulk workers) --------------------------------------------

# (seq, en, ar, nat, id_type, id_no, id_expiry, project, contractor, trade, sites, needs)
NAMED_WORKERS: list[tuple[int, str, str, str, str, str, date, str, str, Trade, list[str], str]] = [
    (
        14,
        "Prakash Thapa",
        "براكاش ثابا",
        "NP",
        "iqama",
        "2000001014",
        date(2027, 6, 30),
        "ANIA-EXP",
        "NAJD",
        Trade.welder,
        ["S-LAND"],
        "GEN",
    ),
    (
        15,
        "Ahmed Raza",
        "أحمد رضا",
        "PK",
        "iqama",
        "2000001015",
        date(2027, 4, 15),
        "ANIA-EXP",
        "NAJD",
        Trade.other,
        ["S-LAND"],
        "GEN",
    ),
    (
        16,
        "Kamal Hossain",
        "كمال حسين",
        "BD",
        "iqama",
        "2000001016",
        date(2027, 9, 9),
        "ANIA-EXP",
        "RAWABI",
        Trade.labourer,
        ["S-LAND"],
        "GEN",
    ),
    (
        17,
        "Biju Thomas",
        "بيجو توماس",
        "IN",
        "iqama",
        "2000001017",
        date(2027, 11, 2),
        "ANIA-EXP",
        "RAWABI",
        Trade.labourer,
        ["S-LAND"],
        "GEN",
    ),
    (
        18,
        "Salem Al-Harthi",
        "سالم الحارثي",
        "SA",
        "national_id",
        "1000001018",
        date(2031, 5, 12),
        "ANIA-EXP",
        "RAWABI",
        Trade.hse_staff,
        ["S-AIR", "S-LAND"],
        "AIR",
    ),
    (
        19,
        "Zaheer Abbas",
        "ظهير عباس",
        "PK",
        "iqama",
        "2000001019",
        date(2027, 8, 20),
        "ANIA-EXP",
        "RAWABI",
        Trade.crane_operator,
        ["S-AIR"],
        "WAP33",
    ),
    (
        20,
        "Vinod Menon",
        "فينود مينون",
        "IN",
        "iqama",
        "2000001020",
        date(2027, 12, 1),
        "ANIA-EXP",
        "NAJD",
        Trade.other,
        ["S-LAND"],
        "GEN",
    ),
    (
        21,
        "Rafiq Islam",
        "رفيق إسلام",
        "BD",
        "iqama",
        "2000001021",
        date(2027, 10, 18),
        "ANIA-EXP",
        "RAWABI",
        Trade.supervisor,
        ["S-LAND"],
        "GEN",
    ),
    (
        106,
        "Dinesh Kumar",
        "دينيش كومار",
        "IN",
        "iqama",
        "2000001106",
        date(2027, 7, 7),
        "RBT-52",
        "QIMMA",
        Trade.welder,
        ["S-TWR"],
        "GEN",
    ),
    (
        107,
        "Rohan Fernando",
        "روهان فرناندو",
        "LK",
        "iqama",
        "2000001107",
        date(2027, 5, 25),
        "RBT-52",
        "QIMMA",
        Trade.other,
        ["S-TWR"],
        "GEN",
    ),
    (
        108,
        "Joel Bautista",
        "جويل باوتيستا",
        "PH",
        "iqama",
        "2000001108",
        date(2028, 2, 14),
        "RBT-52",
        "QIMMA",
        Trade.rigger,
        ["S-TWR"],
        "TC",
    ),
]


def _valid_courses(db: Session, worker_id: uuid.UUID) -> set[str]:
    from app.core.access_enums import InductionStatus
    from app.models import InductionCourse

    rows = db.execute(
        select(InductionCourse.code, InductionRecord.valid_until)
        .join(InductionCourse, InductionCourse.id == InductionRecord.course_id)
        .where(
            InductionRecord.worker_id == worker_id,
            InductionRecord.status == InductionStatus.valid,
        )
    )
    return {c for c, vu in rows if vu is None or vu >= date(2026, 11, 30)}


def _wap33_worker(db: Session) -> uuid.UUID | None:
    from app.models import Wap, WapCrew

    w = db.scalar(select(Wap).where(Wap.wap_no == "WAP-ANIA-EXP-2026-0033"))
    if w is None:
        return None
    for _wc, wk in db.execute(
        select(WapCrew, Worker)
        .join(Worker, Worker.id == WapCrew.worker_id)
        .where(WapCrew.wap_id == w.id)
        .order_by(Worker.seq)  # without it, which bulk worker becomes WKR-000019 varied by build
    ):
        if wk.seq >= 1000:
            return wk.id
    return None


def _wap_crew_ids(db: Session) -> set[uuid.UUID]:
    from app.models import WapCrew

    return set(db.scalars(select(WapCrew.worker_id)))


def _seed_workers(ctx: Ctx) -> None:
    db = ctx.db
    on_waps = _wap_crew_ids(db)
    used: set[uuid.UUID] = set()
    for seq, en, ar, nat, id_type, id_no, exp, pcode, con, trade, sites, needs in NAMED_WORKERS:
        no = f"WKR-{seq:06d}"
        if no in ctx.workers:
            continue
        eng = ctx.eng(pcode, con)
        site_ids = [ctx.site(pcode, s).id for s in sites]
        wid: uuid.UUID | None = None
        if needs == "WAP33":
            wid = _wap33_worker(db)
        else:
            cands = db.execute(
                select(Worker, Deployment)
                .join(Deployment, Deployment.worker_id == Worker.id)
                .where(
                    Worker.seq >= 1000,
                    Deployment.engagement_id == eng.id,
                    Deployment.demobilised_on.is_(None),
                )
                .order_by(Worker.seq)
            ).all()
            for w, d in cands:
                if (
                    w.id in used
                    or w.id in on_waps
                    or w.id_expiry_date is None
                    or w.id_expiry_date < date(2026, 12, 31)
                ):
                    continue
                if not set(site_ids[:1]) & set(d.site_ids or []):
                    continue
                have = _valid_courses(db, w.id)
                need = (
                    {"GEN"}
                    | ({"AIR"} if needs == "AIR" else set())
                    | ({"TC"} if needs == "TC" else set())
                )
                if need <= have:
                    wid = w.id
                    break
        if wid is None:
            raise RuntimeError(f"no bulk worker to convert into {no}")
        used.add(wid)
        w2 = db.get(Worker, wid)
        assert w2 is not None
        w = w2
        from app.core.access_enums import WorkerIdType

        it = WorkerIdType(id_type)
        n = acommon.check_id(it, id_no, None)
        w.seq = seq
        w.worker_no = no
        w.full_name_en = en
        w.full_name_ar = ar
        w.nationality = nat
        w.id_type = it
        w.id_number_enc = crypto.encrypt(n)
        w.id_number_bidx = acommon.blind_index(it, n, nat)
        w.id_number_masked = acommon.mask_worker_id(it, n)
        w.id_expiry_date = exp
        w.search_text = search_blob(no, en, ar)
        dep = db.scalar(
            select(Deployment).where(
                Deployment.worker_id == wid, Deployment.engagement_id == eng.id
            )
        )
        if dep is not None:
            dep.trade = trade
            dep.site_ids = list(dict.fromkeys([*site_ids, *(dep.site_ids or [])]))
        ctx.workers[no] = w
    _hamza_tc(ctx)
    # A.7 0279 puts Ramon Cruz (Phase 2: S-POD) on Z-CORE L30 → his deployment also covers S-TWR
    ramon = ctx.workers.get("WKR-000103")
    if ramon is not None:
        dep = db.scalar(select(Deployment).where(Deployment.worker_id == ramon.id))
        twr = ctx.site("RBT-52", "S-TWR").id
        if dep is not None and twr not in (dep.site_ids or []):
            dep.site_ids = [*(dep.site_ids or []), twr]
    db.flush()


def _hamza_tc(ctx: Ctx) -> None:
    """A.7 0290 needs Hamza (lift supervisor) inducted for Z-TC01: TC course on 2026-10-05
    (after the KPI month, so no Phase 2 September figure moves)."""
    from sqlalchemy import func

    from app.core.access_enums import InductionStatus
    from app.models import InductionCourse

    db = ctx.db
    hamza = ctx.workers.get("WKR-000105")
    if hamza is None:
        return
    pid = ctx.pid("RBT-52")
    tc = db.scalar(
        select(InductionCourse).where(
            InductionCourse.project_id == pid, InductionCourse.code == "TC"
        )
    )
    gen = db.scalar(
        select(InductionRecord)
        .where(
            InductionRecord.worker_id == hamza.id, InductionRecord.status == InductionStatus.valid
        )
        .order_by(InductionRecord.delivered_on.desc())
    )
    if tc is None or gen is None or "TC" in _valid_courses(db, hamza.id):
        return
    seq = (
        db.scalar(
            select(func.max(InductionRecord.seq)).where(
                InductionRecord.project_id == pid, InductionRecord.year == 2026
            )
        )
        or 0
    ) + 1
    cols = {c.key: getattr(gen, c.key) for c in InductionRecord.__table__.columns}
    d = date(2026, 10, 5)
    cols.update(
        id=uuid.uuid4(),
        induction_no=f"IND-RBT-52-2026-{seq:05d}",
        seq=seq,
        year=2026,
        course_id=tc.id,
        induction_type=tc.induction_type,
        course_version=tc.version if hasattr(tc, "version") else cols.get("course_version"),
        delivered_on=d,
        delivered_at=at(2026, 10, 5, 9),
        valid_from=d,
        valid_until=date(2027, 10, 4),
        reinduction_due_on=None,
        helmet_sticker_no=None,
        status_changed_at=at(2026, 10, 5, 10),
        created_at=at(2026, 10, 5, 10),
        updated_at=at(2026, 10, 5, 10),
        seed_fake=True,
    )
    db.execute(insert(InductionRecord), [cols])
    db.flush()


# ---- A.10 obstacle clearance for TC-01 -----------------------------------------------------------


def _seed_obstacle(ctx: Ctx) -> None:
    db = ctx.db
    if db.scalar(
        select(ObstacleClearance.id).where(ObstacleClearance.obs_no == "OBS-RBT-52-2026-0001")
    ):
        return
    ref = db.scalar(
        select(ObstacleClearance).where(ObstacleClearance.obs_no == "OBS-ANIA-EXP-2026-0004")
    )
    assert ref is not None
    cols = {c.key: getattr(ref, c.key) for c in ObstacleClearance.__table__.columns}
    cols.update(
        id=uuid.uuid4(),
        obs_no="OBS-RBT-52-2026-0001",
        project_id=ctx.pid("RBT-52"),
        zone_id=ctx.zones["Z-TC01"].id,
        engagement_id=ctx.eng("RBT-52", "QIMMA").id,
        vehicle_id=None,
        equipment_desc="Tower crane TC-01",
        equipment_type="tower_crane",
        location_desc="Tower crane TC-01 base, core south face",
        ground_elevation_m_amsl=Decimal("618.00"),
        max_height_m_agl=Decimal("236.00"),
        top_elevation_m_amsl=Decimal("854.00"),
        clearance_reasons=["height_threshold"],
        ols_surface=None,
        ols_limit_m_amsl=None,
        ols_source_ref=None,
        penetration_m=Decimal("0.00"),
        requested_from=date(2026, 1, 20),
        requested_to=date(2027, 6, 30),
        authority_ref="GACA-OBS-TEST-0101",
        conditions=["obstruction_light", "day_marking"],
        approved_max_height_m_agl=Decimal("236.00"),
        approved_top_m_amsl=Decimal("854.00"),
        seed_fake=True,
    )
    for k in ("year", "seq"):
        if k in cols:
            cols[k] = 2026 if k == "year" else 1
    if "status" in cols:
        cols["status"] = ObstacleStatus.approved_with_conditions
    if "valid_from" in cols:
        cols["valid_from"] = date(2026, 1, 20)
    if "valid_to" in cols:
        cols["valid_to"] = date(2027, 6, 30)
    db.execute(insert(ObstacleClearance), [cols])
    db.flush()


# ---- A.5 zone profiles and adjacency -------------------------------------------------------------

PROFILES = {
    # zone: (all_work, gas_zone, hazardous class, note, exposure, fire protection, authority, datum)
    "Z-APR-21": (
        True,
        True,
        HazardousAreaClass.zone_2,
        "within 3 m of hydrant pit valve chambers",
        Exposure.outdoor_direct_sun,
        False,
        "omar.siddiqui",
        None,
    ),
    "Z-TWB": (
        True,
        False,
        HazardousAreaClass.none,
        None,
        Exposure.outdoor_direct_sun,
        False,
        "omar.siddiqui",
        None,
    ),
    "Z-ILS33R": (
        True,
        False,
        HazardousAreaClass.none,
        None,
        Exposure.outdoor_direct_sun,
        False,
        "omar.siddiqui",
        None,
    ),
    "Z-PIERB": (
        False,
        False,
        HazardousAreaClass.none,
        None,
        Exposure.outdoor_shaded,
        False,
        "fahad.mutairi",
        None,
    ),
    "Z-MSCP": (
        False,
        True,
        HazardousAreaClass.none,
        "manholes, sewer",
        Exposure.outdoor_shaded,
        False,
        "fahad.mutairi",
        None,
    ),
    "Z-LAY1": (
        False,
        False,
        HazardousAreaClass.none,
        None,
        Exposure.outdoor_direct_sun,
        False,
        "fahad.mutairi",
        None,
    ),
    "Z-CORE": (
        False,
        False,
        HazardousAreaClass.none,
        None,
        Exposure.indoor,
        False,
        "ibrahim.saleh",
        "site ±0.00 = FFL ground",
    ),
    "Z-TC01": (
        True,
        False,
        HazardousAreaClass.none,
        None,
        Exposure.outdoor_direct_sun,
        False,
        "ibrahim.saleh",
        None,
    ),
    "Z-B4": (
        False,
        True,
        HazardousAreaClass.none,
        "dewatering sumps",
        Exposure.indoor,
        False,
        "ibrahim.saleh",
        None,
    ),
    "Z-FAC": (
        True,
        False,
        HazardousAreaClass.none,
        None,
        Exposure.outdoor_direct_sun,
        False,
        "ibrahim.saleh",
        None,
    ),
}
ADJACENCY = [
    ("Z-PIERB", "Z-MSCP", "40.0", VerticalRelation.none),
    ("Z-PIERB", "Z-LAY1", "120.0", VerticalRelation.none),
    ("Z-APR-21", "Z-TWB", "60.0", VerticalRelation.none),
    ("Z-TWB", "Z-ILS33R", "150.0", VerticalRelation.none),
    ("Z-CORE", "Z-TC01", "0.0", VerticalRelation.overlapping),
    ("Z-CORE", "Z-FAC", "0.0", VerticalRelation.none),
    ("Z-CORE", "Z-B4", "0.0", VerticalRelation.a_above_b),
]


def _seed_config(ctx: Ctx) -> None:
    from app.services.ptw import common as ptw_common
    from app.services.ptw import config as ptw_config

    db = ctx.db
    for code in ("ANIA-EXP", "RBT-52"):
        ptw_common.settings(db, ctx.pid(code))
        ptw_config.ensure_rules(db, ctx.pid(code))
    for z in ctx.zones.values():
        prof = ptw_common.profile(db, z)
        spec = PROFILES.get(z.code)
        if spec is None:
            continue
        all_work, gas_zone, haz, note, exp, fire, auth, datum = spec
        prof.permit_required_all_work = all_work
        prof.gas_test_zone = gas_zone
        prof.hazardous_area_class = haz
        prof.hazardous_area_note = note
        prof.default_exposure = exp
        prof.fire_protection_present = fire
        prof.default_area_authority_ids = [ctx.uid(auth)]
        prof.level_datum_note = datum
        prof.seed_fake = True
    for a, b, dist, vr0 in ADJACENCY:
        za, zb = ctx.zones[a], ctx.zones[b]
        lo, hi = (za, zb) if str(za.id) < str(zb.id) else (zb, za)
        vr = vr0
        if vr == VerticalRelation.a_above_b and lo is not za:
            vr = VerticalRelation.b_above_a
        if db.scalar(
            select(ZoneAdjacency.id).where(
                ZoneAdjacency.zone_a_id == lo.id, ZoneAdjacency.zone_b_id == hi.id
            )
        ):
            continue
        db.add(
            ZoneAdjacency(
                id=uuid.uuid4(),
                project_id=za.project_id,
                zone_a_id=lo.id,
                zone_b_id=hi.id,
                distance_m=Decimal(dist),
                vertical_relation=vr,
                seed_fake=True,
            )
        )
    db.flush()


# ---- A.3 appointments ----------------------------------------------------------------------------

# (no, holder (user key | worker no), function, discipline, types, sites, from, to, appointed by)
APPOINTMENTS: list[tuple[str, str, F, D | None, list[str], list[str], date, date]] = [
    (
        "APT-ANIA-EXP-0001",
        "khalid.otaibi",
        F.issuer,
        None,
        ALL_TYPES,
        ["S-AIR", "S-LAND"],
        date(2026, 1, 1),
        date(2026, 12, 31),
    ),
    (
        "APT-ANIA-EXP-0002",
        "omar.siddiqui",
        F.area_authority,
        None,
        ALL_TYPES,
        ["S-AIR"],
        date(2026, 1, 1),
        date(2026, 12, 31),
    ),
    (
        "APT-ANIA-EXP-0003",
        "fahad.mutairi",
        F.area_authority,
        None,
        ALL_TYPES,
        ["S-LAND"],
        date(2026, 2, 1),
        date(2027, 1, 31),
    ),
    (
        "APT-ANIA-EXP-0004",
        "noura.qahtani",
        F.area_authority,
        None,
        ALL_TYPES,
        ["S-AIR", "S-LAND"],
        date(2026, 1, 1),
        date(2026, 12, 31),
    ),
    (
        "APT-ANIA-EXP-0005",
        "nasser.shahrani",
        F.isolation_authority,
        D.electrical_hv,
        [T.electrical_isolation.value, T.general.value],
        ["S-LAND"],
        date(2026, 3, 1),
        date(2027, 2, 28),
    ),
    (
        "APT-ANIA-EXP-0006",
        "nasser.shahrani",
        F.authorised_person,
        D.electrical_lv,
        [T.electrical_isolation.value],
        ["S-LAND"],
        date(2026, 3, 1),
        date(2027, 2, 28),
    ),
    (
        "APT-ANIA-EXP-0007",
        "WKR-000007",
        F.authorised_person,
        D.lifting_appointed_person,
        [T.lifting.value],
        ["S-AIR", "S-LAND"],
        date(2026, 1, 15),
        date(2027, 1, 14),
    ),
    (
        "APT-ANIA-EXP-0008",
        "WKR-000005",
        F.authorised_person,
        D.lift_supervisor,
        [T.lifting.value],
        ["S-AIR"],
        date(2026, 1, 15),
        date(2027, 1, 14),
    ),
    (
        "APT-ANIA-EXP-0009",
        "WKR-000013",
        F.authorised_person,
        D.excavation_competent_person,
        [T.excavation.value],
        ["S-AIR"],
        date(2026, 2, 10),
        date(2027, 2, 9),
    ),
    (
        "APT-ANIA-EXP-0010",
        "WKR-000020",
        F.authorised_person,
        D.radiation_protection_officer,
        [T.radiography.value],
        ["S-LAND"],
        date(2026, 4, 1),
        date(2027, 3, 31),
    ),
    (
        "APT-ANIA-EXP-0011",
        "WKR-000018",
        F.gas_tester,
        None,
        [T.confined_space.value, T.hot_work.value, T.excavation.value, T.general.value],
        ["S-AIR", "S-LAND"],
        date(2026, 4, 21),
        date(2026, 10, 20),
    ),
    (
        "APT-ANIA-EXP-0012",
        "WKR-000021",
        F.authorised_person,
        D.cse_rescue_lead,
        [T.confined_space.value],
        ["S-LAND"],
        date(2026, 5, 1),
        date(2027, 4, 30),
    ),
    (
        "APT-RBT-52-0001",
        "majed.shammari",
        F.issuer,
        None,
        [t for t in ALL_TYPES if t not in (T.confined_space.value, T.radiography.value)],
        ["S-TWR", "S-POD"],
        date(2026, 1, 1),
        date(2026, 12, 31),
    ),
    (
        "APT-RBT-52-0002",
        "ibrahim.saleh",
        F.area_authority,
        None,
        ALL_TYPES,
        ["S-TWR", "S-POD"],
        date(2026, 1, 1),
        date(2026, 12, 31),
    ),
    (
        "APT-RBT-52-0003",
        "ibrahim.saleh",
        F.authorised_person,
        D.lifting_appointed_person,
        [T.lifting.value],
        ["S-TWR", "S-POD"],
        date(2026, 1, 1),
        date(2026, 12, 31),
    ),
    (
        "APT-RBT-52-0004",
        "WKR-000105",
        F.authorised_person,
        D.lift_supervisor,
        [T.lifting.value],
        ["S-TWR"],
        date(2026, 3, 1),
        date(2027, 2, 28),
    ),
    (
        "APT-RBT-52-0005",
        "WKR-000105",
        F.authorised_person,
        D.fall_protection_competent_person,
        [T.work_at_height.value],
        ["S-TWR"],
        date(2026, 3, 1),
        date(2027, 2, 28),
    ),
    (
        "APT-RBT-52-0006",
        "ibrahim.saleh",
        F.isolation_authority,
        D.electrical_lv,
        [T.electrical_isolation.value],
        ["S-TWR", "S-POD"],
        date(2026, 1, 1),
        date(2026, 12, 31),
    ),
    (
        "APT-RBT-52-0007",
        "ibrahim.saleh",
        F.authorised_person,
        D.electrical_lv,
        [T.electrical_isolation.value],
        ["S-TWR", "S-POD"],
        date(2026, 1, 1),
        date(2026, 12, 31),
    ),
]


def _seed_appointments(ctx: Ctx) -> None:
    db = ctx.db
    for no, holder, fn, disc, types, sites, vf, vt in APPOINTMENTS:
        existing = db.scalar(select(PtwAppointment).where(PtwAppointment.appointment_no == no))
        if existing is not None:
            ctx.apts[no] = existing
            continue
        pcode = "ANIA-EXP" if no.startswith("APT-ANIA") else "RBT-52"
        by = (
            "faisal.harbi"
            if fn == F.issuer
            else ("noura.qahtani" if pcode == "ANIA-EXP" else "lina.haddad")
        )
        is_worker = holder.startswith("WKR-")
        a = PtwAppointment(
            id=uuid.uuid4(),
            project_id=ctx.pid(pcode),
            seq=int(no.rsplit("-", 1)[1]),
            appointment_no=no,
            function=fn,
            discipline=disc,
            holder_user_id=None if is_worker else ctx.uid(holder),
            holder_worker_id=ctx.workers[holder].id if is_worker else None,
            permit_types=list(types),
            site_ids=[ctx.site(pcode, s).id for s in sites],
            zone_ids=[],
            basis=f"TEST-BASIS-{no[-4:]} competence assessment (fake)",
            valid_from=vf,
            valid_to=vt,
            appointed_by_user_id=ctx.uid(by),
            status=AppointmentStatus.active,
            alerts_sent=[],
            created_by_user_id=ctx.uid(by),
            seed_fake=True,
            created_at=at(vf.year, vf.month, vf.day, 8),
        )
        db.add(a)
        ctx.apts[no] = a
    db.flush()


# ---- A.6 detectors, bump tests, locks ------------------------------------------------------------

DETECTORS = [
    (
        "GD-ANIA-003",
        3,
        "ANIA-EXP",
        "RAWABI",
        "TEST-GD-SN-0003",
        date(2026, 7, 2),
        date(2026, 12, 29),
        DetectorStatus.in_service,
    ),
    (
        "GD-ANIA-005",
        5,
        "ANIA-EXP",
        "GULFPAVE",
        "TEST-GD-SN-0005",
        date(2026, 3, 30),
        date(2026, 9, 26),
        DetectorStatus.quarantined,
    ),
    (
        "GD-RBT-001",
        1,
        "RBT-52",
        "QIMMA",
        "TEST-GD-SN-0101",
        date(2026, 5, 10),
        date(2026, 11, 6),
        DetectorStatus.in_service,
    ),
]


def _seed_detectors(ctx: Ctx) -> None:
    db = ctx.db
    for no, seq, pcode, con, serial, cal, due, st in DETECTORS:
        d = db.scalar(select(GasDetector).where(GasDetector.detector_no == no))
        if d is None:
            d = GasDetector(
                id=uuid.uuid4(),
                project_id=ctx.pid(pcode),
                seq=seq,
                detector_no=no,
                engagement_id=ctx.eng(pcode, con).id,
                make_model="TEST-Multigas 4 (fake)",
                serial=serial,
                sensors=["o2", "lel", "h2s", "co"],
                lel_reference_gas=LelReferenceGas.methane,
                calibrated_on=cal,
                calibration_cert_ref=f"CAL-TEST-{serial[-4:]}",
                calibration_due_on=due,
                status=st,
                quarantine_reason=QuarantineReason.calibration_overdue
                if st == DetectorStatus.quarantined
                else None,
                quarantined_at=at(2026, 9, 27, 0, 5) if st == DetectorStatus.quarantined else None,
                alerts_sent=[],
                seed_fake=True,
                created_at=at(cal.year, cal.month, cal.day, 9),
            )
            db.add(d)
        ctx.detectors[no] = d
    db.flush()
    gd3 = ctx.detectors["GD-ANIA-003"]
    if not db.scalar(select(BumpTest.id).where(BumpTest.detector_id == gd3.id)):
        db.add(
            BumpTest(
                id=uuid.uuid4(),
                detector_id=gd3.id,
                tested_at=at(2026, 10, 6, 7, 30),
                result=BumpTestResult.pass_,
                sensors_responded=["o2", "lel", "h2s", "co"],
                tested_by_user_id=ctx.uid("faris.anazi"),
                tested_by_worker_id=ctx.workers["WKR-000018"].id,
                gas_cylinder_lot="TEST-LOT-2611",
                gas_cylinder_expiry=date(2027, 5, 31),
                seed_fake=True,
            )
        )
    # GD-RBT-001: 30-day alert is sent by the daily job on 2026-10-07 (Y11)
    db.flush()


LOCKS = {
    "ANIA-EXP": [
        *[(f"L-ANIA-{n:04d}", LockType.isolation_lock) for n in range(231, 241)],
        ("LB-ANIA-012", LockType.lockbox),
        *[(f"P-ANIA-{n:04d}", LockType.personal_lock) for n in range(1101, 1121)],
    ],
    "RBT-52": [
        *[(f"L-RBT-{n:04d}", LockType.isolation_lock) for n in range(101, 111)],
        ("LB-RBT-003", LockType.lockbox),
        *[(f"P-RBT-{n:04d}", LockType.personal_lock) for n in range(201, 216)],
    ],
}


def _seed_locks(ctx: Ctx) -> None:
    db = ctx.db
    for pcode, rows in LOCKS.items():
        for no, lt in rows:
            lk = db.scalar(
                select(Lock).where(Lock.project_id == ctx.pid(pcode), Lock.lock_no == no)
            )
            if lk is None:
                lk = Lock(
                    id=uuid.uuid4(),
                    project_id=ctx.pid(pcode),
                    lock_no=no,
                    lock_type=lt,
                    status=LockStatus.available,
                    seed_fake=True,
                    created_at=at(2026, 1, 10, 9),
                )
                db.add(lk)
            ctx.locks[no] = lk
    db.flush()


# ---- A.9 JSA templates ---------------------------------------------------------------------------


def _line(
    code: str, desc: str, il: int, is_: int, controls: list[tuple[str, str]], rl: int, rs: int
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "hazard_code": code,
        "description": desc,
        "initial_l": il,
        "initial_s": is_,
        "controls": [{"text": t, "level": lv} for t, lv in controls],
        "residual_l": rl,
        "residual_s": rs,
    }


ENG = "engineering"
ADM = "administrative"
PPE = "ppe"

TEMPLATE_LINES: dict[str, list[dict[str, Any]]] = {
    T.general.value: [
        _line(
            "slips_trips",
            "Uneven ground and trailing materials",
            3,
            2,
            [("Housekeeping and marked walkways", ADM), ("Safety boots", PPE)],
            2,
            2,
        )
    ],
    T.hot_work.value: [
        _line(
            "fire_explosion",
            "Sparks igniting combustibles",
            3,
            4,
            [
                ("Combustibles cleared 11 m or covered with fire blankets", ENG),
                ("Fire watch with extinguisher", ADM),
            ],
            2,
            4,
        ),
        _line(
            "hot_surfaces_burns",
            "Contact with hot metal",
            3,
            3,
            [("Hot-work screens", ENG), ("Welding gloves and leathers", PPE)],
            2,
            3,
        ),
    ],
    T.confined_space.value: [
        _line(
            "toxic_atmosphere",
            "H2S / CO from sewer",
            3,
            5,
            [("Forced ventilation", ENG), ("Continuous gas monitor and entry log", ADM)],
            1,
            5,
        ),
        _line(
            "oxygen_deficiency",
            "Low O2 at the bottom",
            2,
            5,
            [("Forced ventilation", ENG), ("Pre-entry gas test at 3 levels", ADM)],
            1,
            5,
        ),
    ],
    T.work_at_height.value: [
        _line(
            "fall_from_height",
            "Fall from slab edge",
            4,
            5,
            [
                ("Perimeter edge-protection system", ENG),
                ("Exclusion of non-essential persons", ADM),
                ("SRL on cast-in anchor", PPE),
            ],
            2,
            5,
        ),
        _line(
            "falling_objects",
            "Tools and debris falling",
            3,
            4,
            [
                ("Toe-boards and debris netting", ENG),
                ("Drop-zone barricade at L37 and ground", ADM),
            ],
            1,
            4,
        ),
    ],
    T.excavation.value: [
        _line(
            "excavation_collapse",
            "Trench wall collapse",
            3,
            5,
            [("Sloping 1.5:1 (type C)", ENG), ("Daily competent-person inspection", ADM)],
            1,
            5,
        ),
        _line(
            "buried_services",
            "Strike on buried AGL cable",
            3,
            4,
            [
                ("Hand dig within 1.0 m of marked services", ENG),
                ("Utility clearance and cable locator", ADM),
            ],
            1,
            4,
        ),
    ],
    T.electrical_isolation.value: [
        _line(
            "electric_shock",
            "Contact with live conductors",
            3,
            5,
            [("Isolation, lock-out and test for dead", ENG), ("Permit and authorised person", ADM)],
            1,
            5,
        ),
        _line(
            "arc_flash",
            "Arc flash on switching",
            2,
            5,
            [("Remote racking", ENG), ("Arc-rated PPE", PPE)],
            1,
            5,
        ),
    ],
    T.lifting.value: [
        _line(
            "struck_by_load",
            "Load swinging or falling",
            3,
            5,
            [("Exclusion zone under the load", ENG), ("Lift plan and appointed signaller", ADM)],
            1,
            5,
        ),
        _line(
            "crane_overturn",
            "Crane overturn",
            2,
            5,
            [
                ("Outriggers on mats, ground bearing checked", ENG),
                ("Wind limit and load chart check", ADM),
            ],
            1,
            5,
        ),
    ],
    T.radiography.value: [
        _line(
            "ionising_radiation",
            "Exposure to gamma radiation",
            3,
            5,
            [
                ("Collimator and barrier at the computed distance", ENG),
                ("Dosimetry and survey meter", ADM),
            ],
            1,
            5,
        ),
    ],
    T.airside_works.value: [
        _line(
            "fod",
            "FOD on the movement area",
            3,
            4,
            [("FOD control plan and sweep", ADM), ("Covered skips", ENG)],
            1,
            4,
        ),
        _line(
            "aircraft_jet_blast",
            "Jet blast near active stands",
            2,
            5,
            [("Barriers and ops coordination", ENG), ("Escort and radio watch", ADM)],
            1,
            5,
        ),
    ],
}

TEMPLATE_PLAN = {
    "ANIA-EXP": [
        [T.general.value],
        [T.hot_work.value],
        [T.confined_space.value],
        [T.work_at_height.value],
        [T.excavation.value],
        [T.electrical_isolation.value],
        [T.lifting.value],
        [T.radiography.value],
        [T.airside_works.value],
        [T.excavation.value, T.airside_works.value],
        [T.lifting.value, T.airside_works.value],
        [T.hot_work.value, T.airside_works.value],
        [T.general.value, T.airside_works.value],
        [T.work_at_height.value, T.airside_works.value],
    ],
    "RBT-52": [
        [T.general.value],
        [T.hot_work.value],
        [T.work_at_height.value],
        [T.excavation.value],
        [T.electrical_isolation.value],
        [T.lifting.value],
        [T.work_at_height.value, T.hot_work.value],
        [T.lifting.value, T.work_at_height.value],
        [T.general.value],
    ],
}


def template_steps(types: list[str]) -> list[dict[str, Any]]:
    steps = []
    for i, t in enumerate(types, start=1):
        steps.append(
            {
                "step_no": i,
                "description_en": f"{t.replace('_', ' ').capitalize()} activities",
                "description_ar": None,
                "hazards": [dict(h, id=str(uuid.uuid4())) for h in TEMPLATE_LINES[t]],
            }
        )
    return steps


def _seed_templates(ctx: Ctx) -> None:
    db = ctx.db
    for pcode, plan in TEMPLATE_PLAN.items():
        officer = ctx.uid("noura.qahtani" if pcode == "ANIA-EXP" else "lina.haddad")
        for i, types in enumerate(plan, start=1):
            no = f"JSA-T-{pcode}-{i:04d}"
            j = db.scalar(select(Jsa).where(Jsa.jsa_no == no))
            if j is None:
                review_due = date(2027, 1, 15) + timedelta(days=7 * i)
                st = JsaStatus.approved
                if pcode == "RBT-52" and i == 9:
                    st = JsaStatus.review_due
                    review_due = date(2026, 9, 30)
                j = Jsa(
                    id=uuid.uuid4(),
                    project_id=ctx.pid(pcode),
                    jsa_no=no,
                    seq=i,
                    revision=0,
                    is_template=True,
                    engagement_id=None,
                    work_types=list(types),
                    title_en=" + ".join(t.replace("_", " ") for t in types).capitalize()
                    + " — standard JSA",
                    title_ar=None,
                    steps=template_steps(types),
                    residual_acceptances=[],
                    crew_briefings=[],
                    review_due_on=review_due,
                    approved_by_user_id=officer,
                    approved_at=at(2026, 1, 12, 10),
                    status=st,
                    alerts_sent=[],
                    created_by_user_id=officer,
                    seed_fake=True,
                    created_at=at(2026, 1, 10, 10),
                )
                db.add(j)
            ctx.templates[no] = j
    db.flush()


# ---- principals ----------------------------------------------------------------------------------


def principal(ctx: Ctx, key: str) -> Any:
    """A Principal for `key` with a fresh password authentication (signatures, §3.2.3)."""
    from app.services.permissions import build_principal

    u = ctx.user(key)
    sess = UserSession(
        id=uuid.uuid4(),
        user_id=u.id,
        created_at=now(),
        last_seen_at=now(),
        expires_at=now() + timedelta(hours=8),
        last_authenticated_at=now(),
    )
    return build_principal(ctx.db, u, sess)


# ---- entry point ---------------------------------------------------------------------------------


def already_seeded(db: Session) -> bool:
    return db.scalar(select(PtwAppointment.id).limit(1)) is not None


def seed_ptw_data(db: Session, password: str | None = None) -> None:
    if already_seeded(db):
        return
    ctx = _load(db)
    if password:
        ctx.password = password
    try:
        set_now(at(2026, 6, 1, 6))
        _seed_users(ctx, password)
        _seed_workers(ctx)
        _seed_obstacle(ctx)
        _seed_config(ctx)
        _seed_appointments(ctx)
        _seed_detectors(ctx)
        _seed_locks(ctx)
        _seed_templates(ctx)
        from app import seed_ptw_bulk, seed_ptw_named

        seed_ptw_bulk.run(ctx)
        seed_ptw_named.run(ctx, ctx.password)
        db.flush()
    finally:
        set_now(None)


def main() -> int:  # pragma: no cover - CLI
    import sys

    from app.core.config import get_settings
    from app.db.session import get_sessionmaker

    password = get_settings().seed_password
    if not password:
        print("Set SEED_PASSWORD (the same as for app.seed).", file=sys.stderr)
        return 2
    with get_sessionmaker()() as db:
        seed_ptw_data(db, password)
        db.commit()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
