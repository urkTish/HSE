"""Phase 6a seed (spec 6a-occupational-health Appendix A; every row `seed_fake`).

Runs on top of the Phase 0-5 world, idempotently (skipped when a medical provider exists). Rows
are written directly with the values the services would compute (§6.1 validity, line states).
The bulk is generated from the built population so that the requirement engine reproduces
A.9 / MF4 at as_of 2026-09-30; `check` verifies the result and raises when a figure is off.

Deviations (DECISIONS #121):
- The requirement population is the one the Phase 0-5 seeds build: on ANIA-EXP DRIVER-FIT
  applies to 103 ADP holders who are not drivers (A.9: 86), and 47 noise / 14 silica workers
  were mobilised on or after 2026-09-01 (A.9: 22 / 12), so ANIA-EXP counts 5,105 requirements
  and 5,009 met (K-89 98.1195…, displayed 98.1 %, no E14). Every gap figure, K-90…K-96 and every
  displayed value of MF4 is unchanged; RBT-52 matches A.9 exactly.
- The hook-derived lines (H01…H03) are effective 2026-08-01 like the manual lines (A.5), although
  the attach points are seeded on enable (2026-10-01).
- QUICKMED's rejected certificate needs an examiner: EXR-0006 (physician, QUICKMED) is added.
"""

from __future__ import annotations

import functools
import itertools
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.access_enums import (
    DeploymentStatus,
    WorkerIdType,
    WorkerLanguage,
    WorkerPersonType,
)
from app.core.cert_enums import VerificationStatus
from app.core.clock import set_now
from app.core.enums import EmployerType, Language, Role, UserStatus
from app.core.med_enums import (
    AssessmentSource,
    AssessmentStatus,
    AssessmentType,
    ExaminerClass,
    ExaminerStatus,
    FitnessLineState,
    FitnessOutcome,
    FitnessRequirementState,
    FitnessVerificationMethod,
    FitnessVerificationOutcome,
    HoldReason,
    HoldSourceType,
    HoldStatus,
    MedicalAppliesTo,
    MedicalLineSource,
    MedicalProviderKind,
    MedicalProviderStatus,
    ReferralReason,
    ReferralStatus,
)
from app.core.security import hash_password
from app.core.text import normalize, search_blob
from app.models import (
    Contractor,
    Deployment,
    FitnessAssessment,
    FitnessHold,
    FitnessLine,
    FitnessReferral,
    FitnessVerification,
    GateCheck,
    HealthProfile,
    Incident,
    InjuryCase,
    MedicalExaminer,
    MedicalPlanLine,
    MedicalProvider,
    PermitCrew,
    Project,
    ProjectEngagement,
    RoleAssignment,
    Site,
    User,
    Worker,
)
from app.services.access import common as acommon
from app.services.med import common as mcommon
from app.services.med import engine

RIYADH = ZoneInfo("Asia/Riyadh")
KPI_DAY = date(2026, 9, 30)
REG_FROM = date(2026, 8, 1)
ENABLE_DAY = date(2026, 10, 1)
CLOCK_DAY = date(2026, 10, 6)
PROJECTS = ("ANIA-EXP", "RBT-52")
GEN, WAH, CRANE, PLANT, DRIVER = (
    "GEN-FIT",
    "WAH-FIT",
    "CRANE-OPERATOR-FIT",
    "PLANT-OPERATOR-FIT",
    ("DRIVER-FIT"),
)
NOISE, SILICA, RAD, CSE, RESP = (
    "NOISE-SURV",
    "SILICA-SURV",
    "RAD-WORKER-FIT",
    "CSE-ENTRY-FIT",
    ("RESPIRATOR-FIT"),
)
CREW_CODES = (CSE, RESP, WAH, CRANE, PLANT, DRIVER, RAD)
F, FWR, TU = (
    FitnessOutcome.fit,
    FitnessOutcome.fit_with_restrictions,
    (FitnessOutcome.temporarily_unfit),
)
RS = FitnessRequirementState
K89 = {"ANIA-EXP": Decimal("98.1"), "RBT-52": Decimal("97.7")}


def at(y: int, m: int, d: int, h: int = 9, mi: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=RIYADH).astimezone(UTC)


def at_d(d: date, h: int = 9, mi: int = 0) -> datetime:
    return at(d.year, d.month, d.day, h, mi)


SEED_CLOCK = at(2026, 10, 6, 10)

# ---- expected values (MF4 / A.9; DECISIONS #121 for the K-89 population) ----------------------

EXPECTED: dict[str, dict[str, Any]] = {
    "ANIA-EXP": {
        "deps": 3412,
        "gaps": {GEN: 52, WAH: 15, PLANT: 3, DRIVER: 6, NOISE: 14, SILICA: 6},
        "applicable": {GEN: 3412, WAH: 519, CRANE: 14, PLANT: 158, DRIVER: 317, NOISE: 431,
                       SILICA: 253, RAD: 1},
        "workers_gap": 87,
        "hook_gaps": 76,
        "k92": 71,
        "k93": (3, 1),
        "k94": (8, 9),
        "k95": (10, 12),
        "k96": 41,
    },
    "RBT-52": {
        "deps": 654,
        "gaps": {GEN: 14, WAH: 2},
        "applicable": {GEN: 654, WAH: 42, CRANE: 6, NOISE: 1},
        "workers_gap": 15,
        "hook_gaps": 16,
        "k92": 12,
        "k93": (1, 0),
        "k94": (2, 2),
        "k95": (3, 3),
        "k96": 6,
    },
}  # fmt: skip

# gap picks: (project, code, kind, n, pool) — pool "only" = workers whose only counted code is
# the gap code (plus GEN-FIT for task codes); two-gap pairs are listed separately.
TWO_GAPS = {"ANIA-EXP": [(WAH, 4), (NOISE, 3), (DRIVER, 2)], "RBT-52": [(WAH, 1)]}
SINGLE_GAPS: dict[str, list[tuple[str, str, int]]] = {
    "ANIA-EXP": [
        (GEN, "missing", 33 - 9), (GEN, "expired", 10), (GEN, "unfit", 5),
        (WAH, "missing", 4), (WAH, "expired", 4), (WAH, "conflict", 1), (WAH, "unfit", 1),
        (PLANT, "expired", 3), (DRIVER, "missing", 2), (DRIVER, "expired", 2),
        (NOISE, "missing", 6), (NOISE, "expired", 5), (SILICA, "missing", 6),
    ],
    "RBT-52": [(GEN, "missing", 9 - 1), (GEN, "expired", 4), (WAH, "expired", 1)],
}  # fmt: skip
K92_BULK = {"ANIA-EXP": 69, "RBT-52": 12}
K96_BULK = {"ANIA-EXP": 38, "RBT-52": 6}

USERS = [
    ("huda.mansour", ("Dr. Huda Al-Mansour", "د. هدى المنصور"), "+966500000017",
     "Occupational Health Physician"),
    ("grace.villanueva", ("Grace Villanueva", "غريس فيلانويفا"), "+966500000018",
     "Occupational Health Nurse"),
]  # fmt: skip

PROVIDERS: list[dict[str, Any]] = [
    {"code": "SHIFA-ANIA", "en": "Shifa Occupational Health Services — ANIA-EXP site clinic (test)",
     "ar": "شفاء لخدمات الصحة المهنية — عيادة موقع مطار النور (تجريبي)",
     "kind": MedicalProviderKind.site_clinic, "projects": ["ANIA-EXP"],
     "licence": "MOH-TEST-FAC-0457", "valid": date(2027, 12, 31), "approved": date(2026, 7, 20)},
    {"code": "SHIFA-RBT", "en": "Shifa Occupational Health Services — RBT-52 site clinic (test)",
     "ar": "شفاء — عيادة موقع برج الرياض (تجريبي)",
     "kind": MedicalProviderKind.site_clinic, "projects": ["RBT-52"],
     "licence": "MOH-TEST-FAC-0458", "valid": date(2027, 12, 31), "approved": date(2026, 7, 20)},
    {"code": "SALAMA", "en": "Al-Salama Medical Polyclinic (test)",
     "ar": "مجمع السلامة الطبي (تجريبي)", "kind": MedicalProviderKind.external_clinic,
     "licence": "MOH-TEST-FAC-1188", "valid": date(2027, 3, 31), "approved": date(2026, 7, 25),
     "domains": ["salama-test.example"], "email": "fitness@salama-test.example",
     "portal": "https://verify.salama-test.example"},
    {"code": "RAWABI-CC", "en": "Rawabi Camp Clinic (test)", "ar": "عيادة سكن الروابي (تجريبي)",
     "kind": MedicalProviderKind.contractor_clinic, "contractor": "RAWABI",
     "licence": "MOH-TEST-FAC-2203", "valid": date(2027, 5, 31), "approved": date(2026, 7, 25),
     "domains": ["rawabi-cc-test.example"], "email": "clinic@rawabi-cc-test.example"},
    {"code": "QUICKMED", "en": "QuickMed Clinic (test)", "ar": "عيادة كويك ميد (تجريبي)",
     "kind": MedicalProviderKind.external_clinic, "licence": "MOH-TEST-FAC-3310",
     "valid": date(2027, 1, 31), "approved": date(2026, 7, 25),
     "domains": ["quickmed-test.example"], "email": "info@quickmed-test.example",
     "suspended": date(2026, 9, 25),
     "reason": "certificate QM-TEST-26-0917 not found in clinic records"},
]  # fmt: skip

EXAMINERS = [
    (1, "Dr. Huda Al-Mansour", "د. هدى المنصور", ExaminerClass.occupational_physician,
     "SCFHS-TEST-14-0457", date(2027, 6, 30), ["SHIFA-ANIA", "SHIFA-RBT"], "huda.mansour"),
    (2, "Dr. Arun Menon", "د. أرون مينون", ExaminerClass.physician, "SCFHS-TEST-11-2210",
     date(2026, 10, 20), ["SHIFA-ANIA"], None),
    (3, "Dr. Samir Khoury", "د. سمير خوري", ExaminerClass.physician, "SCFHS-TEST-09-7781",
     date(2028, 1, 31), ["SALAMA"], None),
    (4, "Dr. Faheem Qureshi", "د. فهيم قريشي", ExaminerClass.physician, "SCFHS-TEST-16-0315",
     date(2027, 4, 30), ["RAWABI-CC"], None),
    (5, "Dr. Nadia Rahman", "د. نادية رحمن", ExaminerClass.occupational_physician,
     "SCFHS-TEST-12-0921", date(2027, 11, 30), ["SHIFA-RBT", "SHIFA-ANIA"], None),
    (6, "Dr. Karim Haddad", "د. كريم حداد", ExaminerClass.physician, "SCFHS-TEST-13-4410",
     date(2027, 9, 30), ["QUICKMED"], None),
]  # fmt: skip

A = MedicalAppliesTo
PLAN = [  # line, applies-to kind, values, code, due days
    ("001", A.all_workers, [], GEN, 0),
    ("002", A.trade, ["scaffolder", "steel_erector", "rigger"], WAH, 0),
    ("003", A.trade, ["crane_operator"], CRANE, 0),
    ("004", A.trade, ["plant_operator"], PLANT, 0),
    ("005", A.trade, ["driver"], DRIVER, 0),
    ("006", A.exposure_group, ["noise_85"], NOISE, 30),
    ("007", A.exposure_group, ["silica_rcs"], SILICA, 30),
    ("008", A.exposure_group, ["ionising_radiation"], RAD, 0),
]

Line = tuple[str, FitnessOutcome, list[str], date | None]  # code, outcome, restrictions, review


@dataclass
class Named:
    worker: str
    pcode: str
    year: int
    seq: int
    typ: AssessmentType
    examined: date
    lines: list[Line]
    accepted: datetime | None = None
    hold: str | None = None


NAMED: list[Named] = [
    Named("WKR-000001", "ANIA-EXP", 2026, 287, AssessmentType.pre_placement, date(2026, 8, 20),
          [(GEN, F, [], None), (WAH, F, [], None)]),
    Named("WKR-000001", "ANIA-EXP", 2026, 412, AssessmentType.return_to_work, date(2026, 9, 28),
          [(GEN, F, [], None), (WAH, F, [], None)], at(2026, 9, 28, 10, 42), "MFH-15"),
    Named("WKR-000002", "ANIA-EXP", 2026, 21, AssessmentType.periodic, date(2026, 1, 12),
          [(GEN, F, [], None), (PLANT, F, [], None), (DRIVER, F, [], None),
           (NOISE, F, [], None)]),
    Named("WKR-000005", "ANIA-EXP", 2026, 31, AssessmentType.periodic, date(2026, 1, 20),
          [(GEN, F, [], None), (DRIVER, F, [], None)]),
    Named("WKR-000007", "ANIA-EXP", 2026, 32, AssessmentType.periodic, date(2026, 1, 20),
          [(GEN, F, [], None), (DRIVER, F, [], None)]),
    Named("WKR-000013", "ANIA-EXP", 2026, 33, AssessmentType.periodic, date(2026, 1, 20),
          [(GEN, F, [], None), (DRIVER, F, [], None)]),
    Named("WKR-000009", "ANIA-EXP", 2026, 55, AssessmentType.periodic, date(2026, 3, 1),
          [(WAH, F, [], None), (GEN, F, [], None)]),
    Named("WKR-000009", "ANIA-EXP", 2026, 398, AssessmentType.periodic, date(2026, 9, 15),
          [(GEN, FWR, ["no_work_at_height"], date(2026, 12, 15))]),
    Named("WKR-000014", "ANIA-EXP", 2026, 220, AssessmentType.periodic, date(2026, 5, 4),
          [(GEN, F, [], None), (NOISE, F, [], None)]),
    Named("WKR-000015", "ANIA-EXP", 2026, 60, AssessmentType.periodic, date(2026, 2, 10),
          [(GEN, F, [], None)]),
    Named("WKR-000017", "ANIA-EXP", 2026, 61, AssessmentType.periodic, date(2026, 2, 10),
          [(GEN, F, [], None)]),
    Named("WKR-000018", "ANIA-EXP", 2026, 62, AssessmentType.periodic, date(2026, 2, 10),
          [(GEN, F, [], None)]),
    Named("WKR-000004", "ANIA-EXP", 2026, 63, AssessmentType.periodic, date(2026, 2, 10),
          [(GEN, F, [], None)]),
    Named("WKR-000016", "ANIA-EXP", 2026, 118, AssessmentType.change_of_task, date(2026, 3, 2),
          [(GEN, F, [], None), (CSE, F, [], None)]),
    Named("WKR-000019", "ANIA-EXP", 2025, 391, AssessmentType.periodic, date(2025, 10, 10),
          [(GEN, F, [], None), (CRANE, F, [], None)]),
    Named("WKR-000020", "ANIA-EXP", 2026, 150, AssessmentType.periodic, date(2026, 4, 1),
          [(GEN, F, [], None), (RAD, F, [], None)]),
    Named("WKR-000021", "ANIA-EXP", 2025, 402, AssessmentType.periodic, date(2025, 11, 1),
          [(GEN, F, [], None), (CSE, F, [], None), (RESP, F, [], None)]),
    Named("WKR-000033", "ANIA-EXP", 2026, 170, AssessmentType.pre_placement, date(2026, 4, 20),
          [(GEN, F, [], None)]),
    Named("WKR-000033", "ANIA-EXP", 2026, 405, AssessmentType.return_to_work, date(2026, 9, 23),
          [(GEN, FWR, ["no_heat_exposure"], date(2026, 10, 7))], at(2026, 9, 23, 6, 31),
          "MFH-19"),
    Named("WKR-000034", "ANIA-EXP", 2026, 92, AssessmentType.periodic, date(2026, 2, 14),
          [(GEN, F, [], None)]),
    Named("WKR-000101", "RBT-52", 2026, 41, AssessmentType.periodic, date(2026, 5, 5),
          [(GEN, F, [], None), (WAH, F, [], None)]),
    Named("WKR-000108", "RBT-52", 2026, 42, AssessmentType.periodic, date(2026, 5, 5),
          [(GEN, F, [], None), (WAH, F, [], None)]),
    Named("WKR-000105", "RBT-52", 2026, 43, AssessmentType.periodic, date(2026, 5, 5),
          [(GEN, F, [], None), (WAH, F, [], None)]),
    Named("WKR-000102", "RBT-52", 2026, 61, AssessmentType.periodic, date(2026, 6, 14),
          [(GEN, F, [], None), (CRANE, F, [], None)]),
    Named("WKR-000106", "RBT-52", 2026, 70, AssessmentType.periodic, date(2026, 6, 20),
          [(GEN, F, [], None), (NOISE, F, [], None)]),
    Named("WKR-000107", "RBT-52", 2026, 71, AssessmentType.periodic, date(2026, 6, 20),
          [(GEN, F, [], None)]),
    Named("WKR-000103", "RBT-52", 2026, 72, AssessmentType.periodic, date(2026, 6, 20),
          [(GEN, F, [], None)]),
]  # fmt: skip
NAMED_WORKERS = {n.worker for n in NAMED} | {"WKR-000003"}
CONVERT = [  # seq, contractor, project, trade, site, (en, ar), primary language
    (33, "GULFPAVE", "ANIA-EXP", "labourer", "S-AIR", ("Ganesh Shrestha", "غانيش شريستا")),
    (34, "RAWABI", "ANIA-EXP", "labourer", "S-LAND", ("Sunil Gurung", "سونيل غورونغ")),
]
RESERVED_HOLDS = {"ANIA-EXP": {15, 16, 19, 27}, "RBT-52": set()}
RESERVED_REFS = {"ANIA-EXP": {12, 31}, "RBT-52": set()}


@dataclass
class Plan:
    """Per project: the generator's view of the counted requirements at KPI_DAY."""

    pcode: str
    need: dict[uuid.UUID, set[str]] = field(default_factory=dict)  # dep → gap codes at 09-30
    later: dict[uuid.UUID, set[str]] = field(default_factory=dict)  # deps mobilised after 09-30
    deps: dict[uuid.UUID, Deployment] = field(default_factory=dict)
    contractor: set[uuid.UUID] = field(default_factory=set)  # dep ids (contractor_worker)
    gaps: dict[uuid.UUID, dict[str, str]] = field(default_factory=dict)  # dep → code → kind
    k92: set[uuid.UUID] = field(default_factory=set)
    k96: set[uuid.UUID] = field(default_factory=set)
    referral: list[uuid.UUID] = field(default_factory=list)
    holds: list[uuid.UUID] = field(default_factory=list)  # active at 09-30


class Ctx:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.rng = random.Random(20261009)  # noqa: S311
        self.projects = {p.code: p for p in db.scalars(select(Project))}
        self.users = {u.email.split("@")[0]: u for u in db.scalars(select(User))}
        self.workers = {w.worker_no: w for w in db.scalars(select(Worker).where(Worker.seq < 1000))}
        self.seq = dict(db.execute(select(Worker.id, Worker.seq)).all())
        self.engs: dict[tuple[str, str], ProjectEngagement] = {}
        code_of = {p.id: p.code for p in self.projects.values()}
        for e, c in db.execute(
            select(ProjectEngagement, Contractor).join(
                Contractor, Contractor.id == ProjectEngagement.contractor_id
            )
        ):
            self.engs[(code_of[e.project_id], c.short_code)] = e
        self.contractor_of = {e.id: c for (_p, c), e in self.engs.items()}
        self.providers: dict[str, MedicalProvider] = {}
        self.examiners: dict[int, MedicalExaminer] = {}
        self.counters: dict[tuple[str, int], itertools.count[int]] = {}
        self.reserved: dict[tuple[str, int], set[int]] = defaultdict(set)
        for n in NAMED:
            self.reserved[(n.pcode, n.year)].add(n.seq)
        self.hold_n = {pc: itertools.count(1) for pc in PROJECTS}
        self.ref_n = {pc: itertools.count(1) for pc in PROJECTS}
        self.assessments: list[FitnessAssessment] = []
        self.named_holds: dict[str, FitnessHold] = {}

    def uid(self, key: str) -> uuid.UUID | None:
        u = self.users.get(key)
        return u.id if u else None

    def pid(self, pcode: str) -> uuid.UUID:
        return self.projects[pcode].id

    def next_seq(self, pcode: str, year: int) -> int:
        c = self.counters.setdefault((pcode, year), itertools.count(1))
        while True:
            n = next(c)
            if n not in self.reserved[(pcode, year)]:
                self.reserved[(pcode, year)].add(n)
                return n

    def wk(self, x: uuid.UUID) -> tuple[int, str]:
        return (self.seq.get(x, 1 << 60), str(x))


def already_seeded(db: Session) -> bool:
    return db.scalar(select(MedicalProvider.id).limit(1)) is not None


# ---- users, workers, settings, providers, examiners, plan --------------------------------------


def _users(ctx: Ctx, password: str) -> None:
    db = ctx.db
    pw = hash_password(password)
    for key, (en, ar), mobile, job in USERS:
        if key in ctx.users:
            continue
        u = User(
            id=uuid.uuid4(),
            email=f"{key}@example.com",
            full_name_en=en,
            full_name_ar=ar,
            mobile=mobile,
            employer_type=EmployerType.client,
            job_title=job,
            preferred_language=Language.en,
            status=UserStatus.active,
            password_hash=pw,
            activated_at=at(2026, 7, 15),
            privacy_notice_ack_at=at(2026, 7, 15),
            search_text=search_blob(en, ar, f"{key}@example.com"),
        )
        from app.core.config import get_settings  # noqa: PLC0415

        u.privacy_notice_version = get_settings().privacy_notice_version
        db.add(u)
        db.flush()
        for pc in PROJECTS:
            db.add(
                RoleAssignment(
                    id=uuid.uuid4(),
                    user_id=u.id,
                    role=Role.oh_practitioner,
                    project_id=ctx.pid(pc),
                    site_ids=[],
                    contractor_engagement_id=None,
                    valid_from=date(2026, 7, 15),
                    created_at=at(2026, 7, 15),
                )
            )
        ctx.users[key] = u
    db.flush()


def _protected(db: Session) -> set[uuid.UUID]:
    ids: set[uuid.UUID] = set(db.scalars(select(Worker.id).where(Worker.seq < 1000)))
    return ids | set(db.scalars(select(PermitCrew.worker_id)))


def _live(d: Deployment, day: date) -> bool:
    return mcommon.mobilised_on(d, day)


def _workers(ctx: Ctx) -> None:
    """§11.3 item 7: two bulk labourers become named workers (trade, sites, dates kept); §11.2
    item 7: the September heat-exhaustion case is linked to Ganesh."""
    db = ctx.db
    protected = _protected(db)
    sites = {(s.project_id, s.code): s.id for s in db.scalars(select(Site))}
    for seq, contractor, pcode, trade, site, (en, ar) in CONVERT:
        no = f"WKR-{seq:06d}"
        if no in ctx.workers:
            continue
        eng = ctx.engs[(pcode, contractor)]
        site_id = sites[(ctx.pid(pcode), site)]
        cand = db.execute(
            select(Worker, Deployment)
            .join(Deployment, Deployment.worker_id == Worker.id)
            .where(Worker.seq >= 1000, Deployment.engagement_id == eng.id)
            .order_by(Worker.seq)
        ).all()
        for w, d in cand:
            if (
                w.id in protected
                or d.trade.value != trade
                or site_id not in (d.site_ids or [])
                or not _live(d, date(2026, 4, 1))
                or w.person_type != WorkerPersonType.contractor_worker
            ):
                continue
            w.seq = seq
            w.worker_no = no
            w.full_name_en = en
            w.full_name_ar = ar
            n = acommon.check_id(WorkerIdType.iqama, f"20000010{seq:02d}", None)
            w.id_type = WorkerIdType.iqama
            w.id_number_enc = crypto.encrypt(n)
            w.id_number_bidx = acommon.blind_index(WorkerIdType.iqama, n, None)
            w.id_number_masked = acommon.mask_worker_id(WorkerIdType.iqama, n)
            w.nationality = "NP"
            w.primary_language = WorkerLanguage.ne
            w.search_text = search_blob(no, en, ar)
            ctx.workers[no] = w
            ctx.seq[w.id] = seq
            protected.add(w.id)
            break
        else:
            raise RuntimeError(f"no bulk worker to convert into {no}")
    db.flush()
    ganesh = ctx.workers["WKR-000033"]
    for c, inc in db.execute(
        select(InjuryCase, Incident)
        .join(Incident, Incident.id == InjuryCase.incident_id)
        .where(
            Incident.project_id == ctx.pid("ANIA-EXP"),
            Incident.occurred_date == date(2026, 9, 22),
            InjuryCase.nature == "heat_exhaustion",
        )
    ):
        c.worker_id = ganesh.id
        ctx.heat_case = (c, inc)  # type: ignore[attr-defined]
    db.flush()


def _settings(ctx: Ctx) -> None:
    db = ctx.db
    mcommon.codes(db)
    for pc in PROJECTS:
        s = mcommon.settings(db, ctx.pid(pc))
        s.medical_register_from = REG_FROM
        s.worker_purpose_notice_version = "WPN-MED-0.1 (draft)"
    db.flush()


def _providers(ctx: Ctx) -> None:
    db = ctx.db
    faisal = ctx.uid("faisal.harbi")
    for spec in PROVIDERS:
        pv = MedicalProvider(
            id=uuid.uuid4(),
            provider_code=spec["code"],
            legal_name_en=spec["en"],
            legal_name_ar=spec["ar"],
            name_norm_en=normalize(spec["en"]),
            name_norm_ar=normalize(spec["ar"]),
            kind=spec["kind"],
            project_ids=[ctx.pid(p) for p in spec.get("projects", [])],
            contractor_id=ctx.engs[("ANIA-EXP", spec["contractor"])].contractor_id
            if spec.get("contractor")
            else None,
            moh_licence_no=spec["licence"],
            licence_valid_until=spec["valid"],
            licence_checked_at=at_d(spec["approved"] - timedelta(days=1), 11),
            licence_checked_by_user_id=faisal,
            verification_domains=spec.get("domains", []),
            verification_email=spec.get("email"),
            verification_portal_url=spec.get("portal"),
            status=MedicalProviderStatus.approved,
            approved_on=spec["approved"],
            suspension_periods=[],
            alerts_sent=[],
            created_by_user_id=faisal,
            seed_fake=True,
            created_at=at_d(spec["approved"] - timedelta(days=3)),
            updated_at=at_d(spec["approved"]),
        )
        if spec.get("suspended"):
            pv.status = MedicalProviderStatus.suspended
            pv.status_reason = spec["reason"]
            pv.suspension_periods = [{"from": spec["suspended"].isoformat(), "to": None}]
            pv.updated_at = at_d(spec["suspended"], 15)
        db.add(pv)
        ctx.providers[spec["code"]] = pv
    db.flush()
    for seq, en, ar, cls, lic, valid, provs, user in EXAMINERS:
        x = MedicalExaminer(
            id=uuid.uuid4(),
            seq=seq,
            examiner_no=f"EXR-{seq:04d}",
            full_name_en=en,
            full_name_ar=ar,
            scfhs_licence_no=lic,
            classification=cls,
            licence_valid_until=valid,
            licence_checked_at=at(2026, 7, 20, 11),
            licence_checked_by_user_id=faisal,
            provider_ids=[ctx.providers[p].id for p in provs],
            user_id=ctx.uid(user) if user else None,
            status=ExaminerStatus.active,
            alerts_sent=[],
            created_by_user_id=faisal,
            seed_fake=True,
            created_at=at(2026, 7, 20, 11),
            updated_at=at(2026, 7, 20, 11),
        )
        db.add(x)
        ctx.examiners[seq] = x
    db.flush()


def _plan(ctx: Ctx) -> None:
    db = ctx.db
    noura = ctx.uid("noura.qahtani")
    for pc in PROJECTS:
        for no, kind, vals, code, due in PLAN:
            db.add(
                MedicalPlanLine(
                    id=uuid.uuid4(),
                    line_id=uuid.uuid4(),
                    project_id=ctx.pid(pc),
                    line_no=f"MRL-{pc}-{no}",
                    applies_to_kind=kind,
                    applies_to_values=vals,
                    trades=[],
                    code=code,
                    due_within_days=due,
                    source=MedicalLineSource.manual,
                    kpi_counted=True,
                    effective_from=REG_FROM,
                    created_by_user_id=ctx.uid("faisal.harbi"),
                    seed_fake=True,
                    created_at=at(2026, 7, 28),
                    updated_at=at(2026, 7, 28),
                )
            )
    vinod = ctx.workers["WKR-000020"]
    dep = db.scalar(
        select(Deployment).where(
            Deployment.worker_id == vinod.id, Deployment.project_id == ctx.pid("ANIA-EXP")
        )
    )
    if dep is not None:
        db.add(
            HealthProfile(
                id=uuid.uuid4(),
                deployment_id=dep.id,
                project_id=dep.project_id,
                exposure_groups=["ionising_radiation"],
                history=[
                    {
                        "value": [],
                        "from_date": dep.mobilised_on.isoformat(),
                        "to_date": (REG_FROM - timedelta(days=1)).isoformat(),
                        "by": None,
                    },
                    {
                        "value": ["ionising_radiation"],
                        "from_date": REG_FROM.isoformat(),
                        "to_date": None,
                        "by": str(noura) if noura else None,
                    },
                ],
                created_by_user_id=noura,
                seed_fake=True,
                created_at=at(2026, 8, 1),
                updated_at=at(2026, 8, 1),
            )
        )
    db.flush()


def _enable(ctx: Ctx) -> None:
    from app.services.cert import policy  # noqa: PLC0415
    from app.services.med import config  # noqa: PLC0415

    db = ctx.db
    set_now(at(2026, 10, 1, 9))
    for pc in PROJECTS:
        config.enable(db, None, ctx.pid(pc), ENABLE_DAY)
    for ln in db.scalars(
        select(MedicalPlanLine).where(MedicalPlanLine.source != MedicalLineSource.manual)
    ):
        if ln.line_no.split("-")[-1].startswith("H"):
            ln.effective_from = REG_FROM  # DECISIONS #121
    db.flush()
    policy.clear_cache(db)
    mcommon.clear_cache(db)


# ---- assessments ---------------------------------------------------------------------------------


def assess(
    ctx: Ctx,
    w: Worker,
    pcode: str,
    examined: date,
    lines: list[Line],
    *,
    typ: AssessmentType = AssessmentType.periodic,
    seq: int | None = None,
    year: int | None = None,
    source: AssessmentSource = AssessmentSource.site_clinic,
    provider: str | None = None,
    examiner: int = 1,
    accepted: datetime | None = None,
    status: AssessmentStatus = AssessmentStatus.accepted,
    verification: VerificationStatus = VerificationStatus.verified,
    cert_no: str | None = None,
    hold: FitnessHold | None = None,
    referral: FitnessReferral | None = None,
    dep: Deployment | None = None,
) -> FitnessAssessment:
    db = ctx.db
    pid = ctx.pid(pcode)
    pr = ctx.projects[pcode]
    year = year or examined.year
    seq = seq or ctx.next_seq(pcode, year)
    provider = provider or ("SHIFA-ANIA" if pcode == "ANIA-EXP" else "SHIFA-RBT")
    pv = ctx.providers[provider]
    huda = ctx.uid("huda.mansour")
    when = accepted or at_d(examined, 10)
    if source == AssessmentSource.import_:
        when = accepted or at_d(max(examined + timedelta(days=1), REG_FROM), 9)
    a = FitnessAssessment(
        id=uuid.uuid4(),
        year=year,
        seq=seq,
        assessment_no=f"MFA-{pr.code}-{year}-{seq:05d}",
        worker_id=w.id,
        project_id=pid,
        engagement_id=dep.engagement_id if dep is not None else _eng(ctx, w, pid),
        assessment_type=typ,
        source=source,
        provider_id=pv.id,
        examiner_id=ctx.examiners[examiner].id,
        examined_on=examined,
        certificate_no=cert_no or f"MFC-{pr.code}-{year}-{seq:05d}",
        related_hold_id=hold.id if hold else None,
        related_referral_id=referral.id if referral else None,
        purpose_notice_given=True,
        purpose_notice_version="WPN-MED-0.1 (draft)",
        historic=False,
        status=status,
        status_changed_at=when,
        verification_status=verification,
        verified_at=when if verification == VerificationStatus.verified else None,
        recorded_by_user_id=huda,
        signed_by_user_id=huda if source == AssessmentSource.site_clinic else None,
        signed_at=when if source == AssessmentSource.site_clinic else None,
        reviewed_by_user_id=huda if status == AssessmentStatus.accepted else None,
        reviewed_at=when if status == AssessmentStatus.accepted else None,
        accepted_at=when if status == AssessmentStatus.accepted else None,
        alerts_sent=[],
        created_by_user_id=huda,
        seed_fake=True,
        created_at=when,
        updated_at=when,
    )
    db.add(a)
    codes = mcommon.codes(db)
    for code, outcome, restr, review in lines:
        rs = [{"code": r} for r in restr]
        unfit = review if outcome == TU else None
        vu, lf = engine.stored_validity(
            codes[code], examined, outcome, rs, review if outcome == FWR else None, None
        )
        db.add(
            FitnessLine(
                id=uuid.uuid4(),
                assessment_id=a.id,
                worker_id=w.id,
                code=code,
                outcome=outcome,
                restrictions=rs,
                restriction_codes=list(restr),
                restriction_review_date=review if outcome == FWR else None,
                unfit_review_date=unfit,
                valid_until=vu,
                limiting_factor=lf,
                line_state=FitnessLineState.pending,
                alerts_sent=[],
            )
        )
    ctx.assessments.append(a)
    return a


_ENG_CACHE: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID | None] = {}


def _eng(ctx: Ctx, w: Worker, pid: uuid.UUID) -> uuid.UUID | None:
    key = (w.id, pid)
    if key not in _ENG_CACHE:
        dep = mcommon.deployment(ctx.db, w.id, pid)
        _ENG_CACHE[key] = dep.engagement_id if dep else None
    return _ENG_CACHE[key]


def _hold(
    ctx: Ctx,
    w: Worker,
    pcode: str,
    reason: HoldReason,
    started: datetime,
    released: datetime | None,
    *,
    seq: int | None = None,
    source: HoldSourceType = HoldSourceType.referral,
    source_id: uuid.UUID | None = None,
    source_ref: str | None = None,
    wdh: list[dict[str, Any]] | None = None,
) -> FitnessHold:
    pr = ctx.projects[pcode]
    if seq is None:
        seq = next(ctx.hold_n[pcode])
        while seq in RESERVED_HOLDS[pcode]:
            seq = next(ctx.hold_n[pcode])
    y = started.astimezone(RIYADH).year
    h = FitnessHold(
        id=uuid.uuid4(),
        year=y,
        seq=seq,
        hold_no=f"MFH-{pr.code}-{y}-{seq:05d}",
        worker_id=w.id,
        project_id=pr.id,
        engagement_id=_eng(ctx, w, pr.id),
        reason=reason,
        source_type=source,
        source_id=source_id,
        source_ref=source_ref,
        started_at=started,
        status=HoldStatus.released if released else HoldStatus.active,
        released_at=released,
        work_during_hold=wdh or [],
        alerts_sent=[],
        seed_fake=True,
        created_at=started,
        updated_at=released or started,
    )
    ctx.db.add(h)
    return h


def _referral(
    ctx: Ctx,
    w: Worker,
    pcode: str,
    raised: datetime,
    by: str,
    remove: bool,
    assessed: datetime | None,
    *,
    seq: int | None = None,
    note: str | None = None,
    reason: ReferralReason = ReferralReason.observed_unwell,
) -> FitnessReferral:
    pr = ctx.projects[pcode]
    if seq is None:
        seq = next(ctx.ref_n[pcode])
        while seq in RESERVED_REFS[pcode]:
            seq = next(ctx.ref_n[pcode])
    y = raised.astimezone(RIYADH).year
    r = FitnessReferral(
        id=uuid.uuid4(),
        year=y,
        seq=seq,
        referral_no=f"MFR-{pr.code}-{y}-{seq:05d}",
        worker_id=w.id,
        project_id=pr.id,
        engagement_id=_eng(ctx, w, pr.id),
        reason=reason,
        note_enc=crypto.encrypt(note) if note else None,
        remove_from_work=remove,
        raised_by_user_id=ctx.uid(by),
        raised_at=raised,
        due_at=raised + timedelta(hours=24),
        status=ReferralStatus.assessed if assessed else ReferralStatus.open,
        assessed_at=assessed,
        alerts_sent=[],
        seed_fake=True,
        created_at=raised,
        updated_at=assessed or raised,
    )
    ctx.db.add(r)
    ctx.db.flush()
    if remove:
        h = _hold(ctx, w, pcode, HoldReason.referral, raised, assessed, source_id=r.id,
                  source_ref=r.referral_no)  # fmt: skip
        r.hold_id = h.id
    if assessed is not None:
        a = assess(ctx, w, pcode, assessed.astimezone(RIYADH).date(), [(GEN, F, [], None)],
                   typ=AssessmentType.referral, accepted=assessed, referral=r)  # fmt: skip
        r.assessment_id = a.id
        if remove:
            h.release_assessment_id = a.id
            a.related_hold_id = h.id
    return r


def _named(ctx: Ctx) -> None:
    db = ctx.db
    wn = ctx.workers
    imran_case = db.execute(
        select(InjuryCase, Incident)
        .join(Incident, Incident.id == InjuryCase.incident_id)
        .where(Incident.ref == "INC-ANIA-EXP-2026-0147", InjuryCase.person_no == 1)
    ).first()
    c, inc = imran_case if imran_case else (None, None)
    ctx.named_holds["MFH-15"] = _hold(
        ctx, wn["WKR-000001"], "ANIA-EXP", HoldReason.rtw_after_injury, at(2026, 9, 9, 8),
        at(2026, 9, 28, 10, 42), seq=15, source=HoldSourceType.injury_case,
        source_id=c.id if c else None, source_ref=f"{inc.ref}-P1" if inc else None,
    )  # fmt: skip
    hc, hinc = getattr(ctx, "heat_case", (None, None))
    ctx.named_holds["MFH-19"] = _hold(
        ctx, wn["WKR-000033"], "ANIA-EXP", HoldReason.heat_illness, at(2026, 9, 22, 14, 35),
        at(2026, 9, 23, 6, 31), seq=19, source=HoldSourceType.injury_case,
        source_id=hc.id if hc else None, source_ref=f"{hinc.ref}-P1" if hinc else None,
    )  # fmt: skip
    db.flush()
    for n in NAMED:
        hold = ctx.named_holds.get(n.hold) if n.hold else None
        a = assess(ctx, wn[n.worker], n.pcode, n.examined, n.lines, typ=n.typ, seq=n.seq,
                   year=n.year, accepted=n.accepted, hold=hold)  # fmt: skip
        if hold is not None:
            hold.release_assessment_id = a.id
    # Jomar: SALAMA external certificate, submitted by Ahmed, accepted and verified by Dr. Huda
    huda = ctx.uid("huda.mansour")
    j = assess(ctx, wn["WKR-000003"], "ANIA-EXP", date(2026, 2, 20),
               [(DRIVER, FWR, ["requires_corrective_lenses"], None), (GEN, F, [], None)],
               source=AssessmentSource.external_certificate, provider="SALAMA", examiner=3,
               accepted=at(2026, 2, 23, 11), cert_no="SAL-TEST-26-0220")  # fmt: skip
    j.recorded_by_user_id = j.submitted_by_user_id = ctx.uid("ahmed.zahrani")
    j.submitted_at = at(2026, 2, 22, 15)
    j.created_by_user_id = j.recorded_by_user_id
    db.flush()
    db.add(_verif(j, "https://verify.salama-test.example", FitnessVerificationMethod.clinic_portal,
                  FitnessVerificationOutcome.confirmed, at(2026, 2, 23, 11), huda))  # fmt: skip
    # Sunil: referral 00031 with removal (hold 00027) at 08:40 today, still Open
    r = _referral(ctx, wn["WKR-000034"], "ANIA-EXP", at(2026, 10, 6, 8, 40), "fahad.mutairi",
                  True, None, seq=31, note="Dizzy and sweating on level 2 at 08:30")  # fmt: skip
    h = db.get(FitnessHold, r.hold_id)
    if h is not None:
        h.seq = 27
        h.hold_no = "MFH-ANIA-EXP-2026-00027"
    db.flush()


def _verif(
    a: FitnessAssessment,
    channel: str,
    method: FitnessVerificationMethod,
    outcome: FitnessVerificationOutcome,
    when: datetime,
    by: uuid.UUID | None,
) -> FitnessVerification:
    ok = outcome == FitnessVerificationOutcome.confirmed
    return FitnessVerification(
        id=uuid.uuid4(),
        assessment_id=a.id,
        project_id=a.project_id,
        provider_id=a.provider_id,
        method=method,
        channel_used=channel,
        outcome=outcome,
        reference=f"{a.certificate_no} {when.astimezone(RIYADH):%Y-%m-%d}",
        performed_by_user_id=by,
        performed_at=when,
        counts_as_verification=True,
        verification_status_after=VerificationStatus.verified if ok else VerificationStatus.failed,
    )


# ---- bulk ----------------------------------------------------------------------------------------


def _plan_of(ctx: Ctx, pcode: str) -> Plan:
    from app.services.med import requirements as rq  # noqa: PLC0415

    db = ctx.db
    pid = ctx.pid(pcode)
    pl = Plan(pcode)
    f = rq.load(db, pid, KPI_DAY)
    for dep in f.deps:
        w = f.workers.get(dep.worker_id)
        pl.deps[dep.id] = dep
        if w is not None and w.person_type == WorkerPersonType.contractor_worker:
            pl.contractor.add(dep.id)
        pl.need[dep.id] = {r.code for r in rq.evaluate_dep(f, dep) if r.state == RS.gap}
    f2 = rq.load(db, pid, CLOCK_DAY)
    for dep in f2.deps:
        if dep.id not in pl.deps:
            pl.deps[dep.id] = dep
            pl.later[dep.id] = {r.code for r in rq.evaluate_dep(f2, dep)}
    return pl


def _pick(ctx: Ctx, pool: list[uuid.UUID], n: int, what: str) -> list[uuid.UUID]:
    pool = sorted(set(pool), key=lambda d: ctx.wk(_dep_worker[d]))
    if len(pool) < n:
        raise RuntimeError(f"seed_med: {what}: {len(pool)} candidates < {n}")
    return sorted(ctx.rng.sample(pool, n), key=lambda d: ctx.wk(_dep_worker[d]))


_dep_worker: dict[uuid.UUID, uuid.UUID] = {}


def _choose(ctx: Ctx, pl: Plan, protected: set[uuid.UUID], trades_of: dict[uuid.UUID, str]) -> None:
    used: set[uuid.UUID] = set()
    base = [
        d
        for d in pl.contractor
        if pl.deps[d].worker_id not in protected and pl.deps[d].id in pl.need
    ]
    for d in base:
        _dep_worker[d] = pl.deps[d].worker_id
    eng_code = {e.id: c for c, e in ((c, e) for (p, c), e in ctx.engs.items() if p == pl.pcode)}

    def pool(pred: Any) -> list[uuid.UUID]:
        return [d for d in base if d not in used and pred(d)]

    def only(*codes: str) -> Any:
        return lambda d: pl.need[d] == set(codes)

    def take(ds: list[uuid.UUID], gaps: dict[str, str]) -> None:
        for d in ds:
            used.add(d)
            pl.gaps.setdefault(d, {}).update(gaps)

    for code, n in TWO_GAPS[pl.pcode]:
        rigger = pl.pcode == "RBT-52"
        ds = _pick(
            ctx,
            pool(
                lambda d, c=code, r=rigger: only(GEN, c)(d) and (not r or trades_of[d] == "rigger")
            ),
            n,
            f"{pl.pcode} two-gap {code}",
        )
        take(ds, {GEN: "missing", code: "missing"})
    sahara = ctx.engs[("ANIA-EXP", "SAHARA")].id if pl.pcode == "ANIA-EXP" else None
    for code, kind, n in SINGLE_GAPS[pl.pcode]:
        pred: Any
        if code == GEN and kind == "unfit":
            pred = lambda d: only(GEN)(d) and trades_of[d] in ("labourer", "carpenter")  # noqa: E731
        elif code == GEN:
            pred = only(GEN)
        elif code == WAH and kind == "conflict":
            pred = lambda d: (  # noqa: E731
                only(GEN, WAH)(d) and trades_of[d] == "scaffolder"
                and pl.deps[d].engagement_id == sahara
            )  # fmt: skip
        elif code == WAH and kind == "unfit":
            pred = lambda d: only(GEN, WAH)(d) and trades_of[d] == "steel_erector"  # noqa: E731
        else:
            pred = functools.partial(lambda c, d: c in pl.need[d], code)
        take(_pick(ctx, pool(pred), n, f"{pl.pcode} {code} {kind}"), {code: kind})
    _ = eng_code
    # 3 / 1 referral holds still Active at 09-30 (labourers): GEN-FIT gap "hold"
    n_active = 3 if pl.pcode == "ANIA-EXP" else 1
    ds = _pick(ctx, pool(lambda d: only(GEN)(d) and trades_of[d] == "labourer"), n_active,
               "active holds")  # fmt: skip
    take(ds, {GEN: "hold"})
    pl.holds = ds
    # September referrals (excluding the active holds): ANIA 11 (FX-BREACH + 6 + 4), RBT 3
    n_ref = 11 if pl.pcode == "ANIA-EXP" else 3
    rawabi = ctx.engs[("ANIA-EXP", "RAWABI")].id if pl.pcode == "ANIA-EXP" else None
    if rawabi is not None:
        breach = _pick(
            ctx,
            pool(
                lambda d: (
                    only(GEN)(d)
                    and trades_of[d] == "labourer"
                    and pl.deps[d].engagement_id == rawabi
                )
            ),
            1,
            "FX-BREACH",
        )
        used.update(breach)
        n_ref -= 1
    else:
        breach = []
    rest = _pick(ctx, pool(lambda d: only(GEN)(d) and trades_of[d] == "labourer"), n_ref,
                 "referrals")  # fmt: skip
    used.update(rest)
    pl.referral = breach + rest
    if pl.pcode == "ANIA-EXP":
        najd = ctx.engs[("ANIA-EXP", "NAJD")].id
        qm = _pick(ctx, pool(lambda d: only(GEN)(d) and pl.deps[d].engagement_id == najd), 1,
                   "FX-QM")  # fmt: skip
        take(qm, {GEN: "verification_failed"})
    k92 = _pick(ctx, pool(only(GEN)), K92_BULK[pl.pcode], "K-92")
    used.update(k92)
    pl.k92 = set(k92)
    k96 = _pick(ctx, pool(only(GEN)), K96_BULK[pl.pcode], "K-96")
    used.update(k96)
    pl.k96 = set(k96)


def _expired_date(code: str, ctx: Ctx, months: int) -> date:
    """An examination whose line ended between 2026-08-02 and 2026-09-28."""
    from app.kpi.periods import add_months  # noqa: PLC0415

    end = date(2026, 8, 2) + timedelta(days=ctx.rng.randint(0, 57))
    return add_months(end, -months) + timedelta(days=1)


def _bulk(ctx: Ctx, pl: Plan, crew: dict[uuid.UUID, set[str]]) -> None:
    from app.kpi.periods import add_months  # noqa: PLC0415

    db = ctx.db
    codes = mcommon.codes(db)
    pcode = pl.pcode
    workers = {w.id: w for w in db.scalars(select(Worker).where(
        Worker.id.in_([d.worker_id for d in pl.deps.values()])))}  # fmt: skip
    named = {ctx.workers[n].id for n in NAMED_WORKERS if n in ctx.workers}
    for dep_id in sorted(pl.deps, key=lambda d: ctx.wk(pl.deps[d].worker_id)):
        dep = pl.deps[dep_id]
        w = workers[dep.worker_id]
        if w.id in named:
            continue
        need = set(pl.need.get(dep_id, set()) | pl.later.get(dep_id, set()))
        need |= crew.get(w.id, set())
        gaps = pl.gaps.get(dep_id, {})
        base = sorted(c for c in need if c not in gaps)
        examined = date(2025, 12, 1) + timedelta(days=ctx.rng.randint(0, 242))
        if dep.mobilised_on > examined:
            examined = min(dep.mobilised_on, date(2026, 7, 31))
        if dep_id in pl.later:
            examined = min(max(dep.mobilised_on - timedelta(days=3), date(2026, 8, 2)),
                           CLOCK_DAY - timedelta(days=1))  # fmt: skip
        if dep_id in pl.k92:
            vu = KPI_DAY + timedelta(days=ctx.rng.randint(0, 30))
            examined = add_months(vu + timedelta(days=1), -24)
        if base and dep_id not in pl.k96:
            src = AssessmentSource.import_ if examined < REG_FROM else AssessmentSource.site_clinic
            assess(ctx, w, pcode, examined, [(c, F, [], None) for c in base], source=src, dep=dep)
        if dep_id in pl.k96:
            ex = date(2026, 9, 1) + timedelta(days=ctx.rng.randint(0, 19))
            restr = ctx.rng.choice(["light_duties_only", "no_night_work", "no_lone_work"])
            assess(ctx, w, pcode, ex, [(GEN, FWR, [restr], ex + timedelta(days=80))], dep=dep)
        for code, kind in gaps.items():
            months = codes[code].validity_months
            if kind == "expired":
                ex = _expired_date(code, ctx, months)
                assess(ctx, w, pcode, ex, [(code, F, [], None)],
                       source=AssessmentSource.import_, dep=dep)  # fmt: skip
            elif kind == "unfit":
                if code == GEN:
                    ex = date(2026, 9, 2) + timedelta(days=ctx.rng.randint(0, 20))
                    assess(ctx, w, pcode, ex, [(GEN, TU, [], ex + timedelta(days=45))], dep=dep)
                else:
                    ex = date(2026, 9, 2) + timedelta(days=ctx.rng.randint(0, 20))
                    assess(ctx, w, pcode, examined, [(code, F, [], None)], dep=dep)
                    assess(ctx, w, pcode, ex, [(code, TU, [], ex + timedelta(days=45))], dep=dep)
            elif kind == "conflict":
                ex = date(2026, 9, 3) + timedelta(days=ctx.rng.randint(0, 15))
                assess(ctx, w, pcode, examined, [(code, F, [], None)], dep=dep)
                assess(ctx, w, pcode, ex, [(GEN, FWR, ["no_work_at_height"],
                                            ex + timedelta(days=85))], dep=dep)  # fmt: skip
            elif kind == "hold":
                assess(ctx, w, pcode, examined, [(GEN, F, [], None)], dep=dep)
            elif kind == "verification_failed":
                _fx_qm(ctx, w, dep)
    db.flush()


def _fx_qm(ctx: Ctx, w: Worker, dep: Deployment) -> None:
    a = assess(ctx, w, "ANIA-EXP", date(2026, 9, 8), [(GEN, F, [], None)],
               source=AssessmentSource.external_certificate, provider="QUICKMED", examiner=6,
               status=AssessmentStatus.rejected, verification=VerificationStatus.failed,
               cert_no="QM-TEST-26-0917", dep=dep)  # fmt: skip
    a.recorded_by_user_id = a.submitted_by_user_id = ctx.uid("ahmed.zahrani")
    a.submitted_at = at(2026, 9, 22, 11)
    a.status_changed_at = a.reviewed_at = at(2026, 9, 24, 12)
    a.reviewed_by_user_id = ctx.uid("huda.mansour")
    a.status_reason_enc = crypto.encrypt("verification_failed")
    ctx.db.flush()
    ctx.db.add(_verif(a, "info@quickmed-test.example", FitnessVerificationMethod.clinic_email,
                      FitnessVerificationOutcome.not_found, at(2026, 9, 24, 12),
                      ctx.uid("huda.mansour")))  # fmt: skip


def _referrals(ctx: Ctx, pl: Plan) -> None:
    """September referrals (§6.9 MF3c, MF4) and the holds still Active at 09-30."""
    db = ctx.db
    workers = {w.id: w for w in db.scalars(select(Worker).where(Worker.id.in_(
        [pl.deps[d].worker_id for d in pl.referral + pl.holds])))}  # fmt: skip

    def w_of(d: uuid.UUID) -> Worker:
        return workers[pl.deps[d].worker_id]

    if pl.pcode == "ANIA-EXP":
        breach, rest = pl.referral[0], pl.referral[1:]
        bw = w_of(breach)
        gate = _gate_row(ctx, bw)
        r = _referral(ctx, bw, "ANIA-EXP", at(2026, 9, 11, 16, 20), "omar.siddiqui", True,
                      at(2026, 9, 13, 9), seq=12)  # fmt: skip
        h = db.get(FitnessHold, r.hold_id)
        if h is not None:
            h.seq = 16
            h.hold_no = "MFH-ANIA-EXP-2026-00016"
            h.work_during_hold = [{"event_type": "gate_entry", "ref": gate[0],
                                   "at": gate[1].isoformat()}]  # fmt: skip
        days = [2, 4, 7, 9, 14, 16, 18, 21, 23, 25]
        for i, d in enumerate(rest):
            raised = at(2026, 9, days[i], 9 + i % 5, 15)
            remove = i < 6
            _referral(ctx, w_of(d), "ANIA-EXP", raised, ("noura.qahtani", "fahad.mutairi",
                      "omar.siddiqui")[i % 3], remove, raised + timedelta(hours=6 + i))  # fmt: skip
        times = [at(2026, 9, 29, 15), at(2026, 9, 30, 10), at(2026, 9, 30, 13, 30)]
        released = [at(2026, 10, 1, 11), at(2026, 10, 1, 9, 30), at(2026, 10, 2, 10)]
    else:
        days = [8, 17, 24]
        for i, d in enumerate(pl.referral):
            raised = at(2026, 9, days[i], 10)
            _referral(ctx, w_of(d), "RBT-52", raised, "lina.haddad", i < 2,
                      raised + timedelta(hours=5))  # fmt: skip
        times = [at(2026, 9, 30, 11)]
        released = [at(2026, 10, 1, 10)]
    for d, raised, rel in zip(pl.holds, times, released, strict=True):
        by = "noura.qahtani" if pl.pcode == "ANIA-EXP" else "lina.haddad"
        _referral(ctx, w_of(d), pl.pcode, raised, by, True, rel)
    db.flush()


def _gate_row(ctx: Ctx, w: Worker) -> tuple[str, datetime]:
    """FX-BREACH: the worker's existing gate entry on 2026-09-12 (else 06:52 at G-ANIA-01)."""
    from app.core.access_enums import GateDirection  # noqa: PLC0415
    from app.models import Gate  # noqa: PLC0415

    db = ctx.db
    row = db.execute(
        select(GateCheck, Gate)
        .join(Gate, Gate.id == GateCheck.gate_id)
        .where(
            GateCheck.worker_id == w.id,
            GateCheck.local_date == date(2026, 9, 12),
            GateCheck.direction == GateDirection.in_,
        )
        .order_by(GateCheck.occurred_at)
    ).first()
    if row is not None:
        return row[1].gate_code, row[0].occurred_at
    return "G-ANIA-01", at(2026, 9, 12, 6, 52)


def _crew_codes(ctx: Ctx) -> dict[uuid.UUID, set[str]]:
    """Bulk crew members of non-terminal permits hold every crew-role code (A.6, A.1)."""
    from app.core.ptw_enums import PERMIT_TERMINAL  # noqa: PLC0415
    from app.models import Permit  # noqa: PLC0415

    out: dict[uuid.UUID, set[str]] = {}
    for c in ctx.db.scalars(
        select(PermitCrew)
        .join(Permit, Permit.id == PermitCrew.permit_id)
        .where(Permit.status.notin_(list(PERMIT_TERMINAL)))
    ):
        out.setdefault(c.worker_id, set()).update(CREW_CODES)
    return out


def _line_states(ctx: Ctx) -> None:
    """§3.6a line_state at the seed clock (governing / superseded / rejected / pending)."""
    db = ctx.db
    rows = db.execute(
        select(FitnessLine, FitnessAssessment).join(
            FitnessAssessment, FitnessAssessment.id == FitnessLine.assessment_id
        )
    ).all()
    by: dict[tuple[uuid.UUID, str], list[engine.Row]] = defaultdict(list)
    for ln, a in rows:
        by[(ln.worker_id, ln.code)].append(engine.Row(ln, a))
    for rs in by.values():
        gov = engine.governing(rs, SEED_CLOCK)
        for r in rs:
            if r.a.status == AssessmentStatus.rejected:
                r.line.line_state = FitnessLineState.rejected
            elif r.a.status != AssessmentStatus.accepted:
                r.line.line_state = FitnessLineState.pending
            elif gov is not None and gov.line.id == r.line.id:
                r.line.line_state = FitnessLineState.governing
            else:
                r.line.line_state = FitnessLineState.superseded
    db.flush()


def _fill_named(ctx: Ctx) -> None:
    """Named workers (seq < 1000) not in A.6, or with a counted code A.6 does not list, get a
    periodic site-clinic line so that only the A.9 gaps exist (Osman's WAH-FIT conflict stays)."""
    from app.services.med import requirements as rq  # noqa: PLC0415

    db = ctx.db
    allowed = {("WKR-000009", WAH)}
    for pc in PROJECTS:
        for day in (KPI_DAY, CLOCK_DAY):
            f = rq.load(db, ctx.pid(pc), day)
            for dep in f.deps:
                w = f.workers.get(dep.worker_id)
                if w is None or w.seq >= 1000:
                    continue
                missing = sorted(
                    r.code
                    for r in rq.evaluate_dep(f, dep)
                    if r.state == RS.gap and (w.worker_no, r.code) not in allowed
                    and not (r.check is not None and r.check.reason is not None
                             and r.check.reason.value == "MEDICAL_HOLD")
                )  # fmt: skip
                if missing:
                    ex = (
                        min(max(dep.mobilised_on, date(2026, 3, 10)), KPI_DAY - timedelta(days=1))
                        if day == KPI_DAY
                        else CLOCK_DAY - timedelta(days=2)
                    )
                    assess(ctx, w, pc, ex, [(c, F, [], None) for c in missing], dep=dep)
            db.flush()
            mcommon.clear_cache(db)


# ---- verification --------------------------------------------------------------------------------


def verify(db: Session) -> dict[str, dict[str, Any]]:
    from app.kpi import medical as km  # noqa: PLC0415
    from app.services.med import requirements as rq  # noqa: PLC0415

    out: dict[str, dict[str, Any]] = {}
    for p in db.scalars(select(Project).where(Project.code.in_(PROJECTS))):
        pe = rq.evaluate_project(db, p.id, KPI_DAY)
        counted = pe.counted
        gaps: dict[str, int] = defaultdict(int)
        appl: dict[str, int] = defaultdict(int)
        per: dict[uuid.UUID, bool] = {}
        for r in counted:
            appl[r.code] += 1
            per[r.dep.id] = per.get(r.dep.id, False) or r.state == RS.gap
            if r.state == RS.gap:
                gaps[r.code] += 1
        mf = km.load_med(db, [p.id])

        class _E:  # minimal engine stand-in for the hold / referral helpers
            pass

        e: Any = _E()
        e.facts = type("Fx", (), {"med": mf})()
        e.flt = type("Flt", (), {"zone_filtered": False, "sites": None,
                                 "eng_ok": staticmethod(lambda _x: True)})()  # fmt: skip
        e.as_of = KPI_DAY
        w = type("W", (), {"start": date(2026, 9, 1), "end": KPI_DAY})()
        a = type("Ag", (), {"window": w})()
        act, late = km.active_holds(e, KPI_DAY)
        rel = km.released_holds(e, a)
        refs = km.counted_referrals(e, a)
        stats = km.req_stats(e, KPI_DAY)
        out[p.code] = {
            "deps": len(per),
            "gaps": {k: v for k, v in gaps.items() if v},
            "applicable": dict(appl),
            "workers_gap": sum(per.values()),
            "hook_gaps": sum(1 for r in counted if r.state == RS.gap and r.hook_code),
            "k92": stats.k92,
            "k93": (len(act), len(late)),
            "k94": (sum(1 for h in rel if not h.work_during_hold), len(rel)),
            "k95": (sum(1 for r in refs if km.on_time(r)), len(refs)),
            "k96": stats.k96,
        }
    return out


def check(db: Session) -> None:
    got = verify(db)
    errors = []
    for pc, exp in EXPECTED.items():
        g = got.get(pc, {})
        for k, v in exp.items():
            if k == "applicable":
                # the population comes from the Phase 0-5 seeds (DECISIONS #121): check the
                # displayed K-89 and the E14 side of the threshold, not the exact counts
                n = sum(g.get(k, {}).values())
                met = n - sum(g.get("gaps", {}).values())
                pct = Decimal(met * 100) / Decimal(n) if n else Decimal(0)
                shown = pct.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                if shown != K89[pc] or (pct < Decimal("98.0")) != (pc == "RBT-52"):
                    errors.append(f"{pc} K-89 {met}/{n} = {pct:.4f}")
                continue
            if g.get(k) != v:
                errors.append(f"{pc} {k}: {g.get(k)} != {v}")
    if errors:
        raise RuntimeError("seed_med verification failed: " + "; ".join(errors))


# ---- entry point ---------------------------------------------------------------------------------


def seed_med_data(db: Session, password: str | None = None, verify_kpis: bool = True) -> None:
    if already_seeded(db):
        return
    if db.scalar(select(Project.id).where(Project.code == "ANIA-EXP")) is None:
        return
    if password is None:
        from app.core.config import get_settings  # noqa: PLC0415

        password = get_settings().seed_password or "Seed-Passw0rd!2026"
    ctx = Ctx(db)
    _ENG_CACHE.clear()
    _dep_worker.clear()
    try:
        set_now(at(2026, 7, 15, 9))
        _users(ctx, password)
        _workers(ctx)
        _settings(ctx)
        _providers(ctx)
        _plan(ctx)
        _enable(ctx)
        set_now(SEED_CLOCK)
        _named(ctx)
        db.flush()
        protected = _protected(db)
        crew = _crew_codes(ctx)
        for pc in PROJECTS:
            pl = _plan_of(ctx, pc)
            trades = {d: pl.deps[d].trade.value for d in pl.deps}
            _choose(ctx, pl, protected, trades)
            _bulk(ctx, pl, crew)
            _referrals(ctx, pl)
        db.flush()
        mcommon.clear_cache(db)
        _fill_named(ctx)
        _line_states(ctx)
        mcommon.clear_cache(db)
        _refresh_permits(db)
        if verify_kpis:
            check(db)
    finally:
        set_now(None)


def _refresh_permits(db: Session) -> None:
    from app.core.ptw_enums import PERMIT_LIVE, PermitStatus  # noqa: PLC0415
    from app.models import Permit  # noqa: PLC0415
    from app.services.ptw import evaluation  # noqa: PLC0415

    set_now(SEED_CLOCK)
    for p in db.scalars(
        select(Permit)
        .where(Permit.status.in_([*PERMIT_LIVE, PermitStatus.approved]))
        .order_by(Permit.permit_no)
    ):
        evaluation.refresh(db, p, run_simops=False)
    db.flush()


def main() -> int:  # pragma: no cover - CLI
    from app.db.session import get_sessionmaker  # noqa: PLC0415

    with get_sessionmaker()() as db:
        seed_med_data(db)
        db.commit()
    print("Phase 6a seed loaded.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

_ = DeploymentStatus
