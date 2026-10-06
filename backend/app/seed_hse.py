"""Phase 1 demo seed (spec 1-dashboard Appendix A; all data fictional, `seed_fake = true`).

13 months 2025-09 … 2026-09 plus a lighter ramp-up from project start. ANIA-EXP monthly
man-hours and case counts equal the W3 table, other monthly counts equal A.3; the daily
distribution follows A.4 and the incident patterns A.5. Deterministic (fixed random seed).

`seed_settings` (Phase 1 settings, reference lists, a clearly fake AI transfer approval) is
cheap and runs with every seed; `seed_data` loads the volume data and runs from
``python -m app.seed`` (tests load it only where needed).
"""

import math
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.clock import now
from app.core.hse_enums import (
    Activity,
    AgeBand,
    Agency,
    AirsideFlag,
    BodyPart,
    BodySide,
    CaPriority,
    CaseCategory,
    CaSourceType,
    CaStatus,
    ClassificationStatus,
    ControlLevel,
    DangerousOccurrenceCategory,
    EnvCategory,
    EnvReached,
    IdType,
    IncidentShift,
    IncidentStatus,
    IncidentType,
    InjuryNature,
    InspectionAssigneeRole,
    InspectionFrequency,
    InspectionStatus,
    InspectionType,
    InvestigationLevel,
    InvestigationMethod,
    Mechanism,
    MeetingType,
    NotWorkRelatedReason,
    ObservationCategory,
    ObservationStatus,
    ObservationType,
    PersonType,
    RiskRating,
    Shift,
    Trade,
    TreatedAt,
    Weekday,
    WorkforceSource,
    WorkforceStatus,
)
from app.kpi import calendar
from app.kpi.periods import add_months, month_end, month_start
from app.models import (
    Contractor,
    CorrectiveAction,
    ExternalNotification,
    HseMeeting,
    Incident,
    InjuryCase,
    Inspection,
    InspectionPlan,
    Investigation,
    Observation,
    PeriodLock,
    Project,
    ProjectEngagement,
    Site,
    User,
    WorkforceReturn,
    Zone,
)
from app.services import hse_settings
from app.services import incidents as inc_svc

RIYADH = ZoneInfo("Asia/Riyadh")
SEED_END = date(2026, 9, 30)
LAST_ACTIVITY = date(2026, 10, 3)  # no completion/verification later than this in the seed
LOCKED_UNTIL = date(2026, 8, 1)  # months up to Aug 2026 are locked

FAKE_APPROVAL = {
    "ai_approver_name": "Test Approver (seed-fake, not a real approval)",
    "ai_approver_organisation": "Fictional client — demo data",
    "ai_approval_reference": "SEED-FAKE-AI-APPROVAL",
    "ai_approval_notes": "Fake approval recorded by the dev seed so the demo can use the "
    "assistant once an API key is set. Not valid for production.",
}

# W3: month → (MH, LTI, RWC, JTC, MTC, FAC, NM)
W3: dict[date, tuple[int, int, int, int, int, int, int]] = {
    date(2025, 9, 1): (610_000, 1, 0, 0, 1, 5, 14),
    date(2025, 10, 1): (640_000, 0, 1, 0, 1, 4, 16),
    date(2025, 11, 1): (660_000, 0, 0, 0, 2, 6, 18),
    date(2025, 12, 1): (700_000, 1, 0, 0, 1, 5, 20),
    date(2026, 1, 1): (720_000, 0, 0, 1, 1, 7, 21),
    date(2026, 2, 1): (690_000, 0, 1, 0, 0, 4, 19),
    date(2026, 3, 1): (650_000, 0, 0, 0, 1, 5, 17),
    date(2026, 4, 1): (760_000, 0, 1, 0, 2, 6, 22),
    date(2026, 5, 1): (800_000, 1, 0, 0, 1, 7, 23),
    date(2026, 6, 1): (830_000, 0, 1, 0, 3, 8, 20),
    date(2026, 7, 1): (850_000, 0, 0, 1, 2, 9, 18),
    date(2026, 8, 1): (860_000, 0, 1, 0, 3, 7, 21),
    date(2026, 9, 1): (870_000, 1, 1, 0, 2, 6, 24),
}
# A.3: month → (safe, unsafe, planned, on_time, late, missed, CAs raised, CA overdue at month
# end, DO, PD, ENV, toolbox talks)
A3: dict[date, tuple[int, ...]] = {
    date(2025, 9, 1): (300, 150, 32, 26, 3, 3, 38, 4, 0, 1, 0, 380),
    date(2025, 10, 1): (320, 150, 34, 29, 2, 3, 40, 3, 1, 1, 1, 400),
    date(2025, 11, 1): (330, 150, 34, 30, 2, 2, 41, 3, 0, 2, 0, 410),
    date(2025, 12, 1): (350, 160, 36, 31, 3, 2, 44, 4, 0, 1, 1, 430),
    date(2026, 1, 1): (360, 160, 36, 32, 2, 2, 45, 3, 1, 1, 0, 440),
    date(2026, 2, 1): (340, 150, 36, 30, 3, 3, 42, 3, 0, 2, 0, 420),
    date(2026, 3, 1): (320, 140, 36, 29, 3, 4, 40, 3, 0, 1, 1, 400),
    date(2026, 4, 1): (380, 170, 38, 33, 2, 3, 47, 3, 1, 2, 0, 470),
    date(2026, 5, 1): (390, 170, 38, 33, 3, 2, 48, 4, 0, 1, 1, 480),
    date(2026, 6, 1): (380, 180, 40, 32, 4, 4, 50, 6, 0, 2, 1, 490),
    date(2026, 7, 1): (350, 190, 40, 30, 4, 6, 49, 9, 1, 1, 0, 480),
    date(2026, 8, 1): (370, 190, 40, 31, 4, 5, 52, 11, 0, 2, 1, 500),
    date(2026, 9, 1): (420, 180, 40, 34, 3, 3, 55, 7, 1, 2, 1, 520),
}
ANIA_RAMP = {  # lighter ramp-up from project start (no LTI)
    date(2025, 3, 1): 150_000,
    date(2025, 4, 1): 230_000,
    date(2025, 5, 1): 320_000,
    date(2025, 6, 1): 410_000,
    date(2025, 7, 1): 480_000,
    date(2025, 8, 1): 560_000,
}
RBT_MONTHLY = {  # A.5.7 (Oct 2025 … Sep 2026) and ramp-up from 2025-01-15
    date(2025, 1, 1): 30_000,
    date(2025, 2, 1): 60_000,
    date(2025, 3, 1): 70_000,
    date(2025, 4, 1): 80_000,
    date(2025, 5, 1): 90_000,
    date(2025, 6, 1): 100_000,
    date(2025, 7, 1): 105_000,
    date(2025, 8, 1): 110_000,
    date(2025, 9, 1): 120_000,
    date(2025, 10, 1): 120_000,
    date(2025, 11, 1): 125_000,
    date(2025, 12, 1): 130_000,
    date(2026, 1, 1): 130_000,
    date(2026, 2, 1): 135_000,
    date(2026, 3, 1): 135_000,
    date(2026, 4, 1): 135_000,
    date(2026, 5, 1): 140_000,
    date(2026, 6, 1): 140_000,
    date(2026, 7, 1): 140_000,
    date(2026, 8, 1): 135_000,
    date(2026, 9, 1): 135_000,
}
SHARES = {"NAJD": Decimal("0.28"), "GULFPAVE": Decimal("0.21"), "SAHARA": Decimal("0.10")}
SEP_2026 = {"RAWABI": 360_000, "NAJD": 240_000, "GULFPAVE": 180_000, "SAHARA": 90_000}
DLIFT_LAST_HOURS = date(2026, 8, 14)  # suspended 2026-08-15
GULFPAVE_MISSING = {date(2026, 7, 7), date(2026, 7, 14), date(2026, 7, 21)}  # A.4.5
EID = {
    *(date(2025, 3, 30) + timedelta(days=i) for i in range(4)),
    *(date(2025, 6, 6) + timedelta(days=i) for i in range(4)),
    *(date(2026, 3, 20) + timedelta(days=i) for i in range(4)),
    *(date(2026, 5, 26) + timedelta(days=i) for i in range(4)),
}
# Engagement cells: contractor → [(site, shift, share)]
CELLS = {
    "RAWABI": [("S-AIR", Shift.day, Decimal("0.5")), ("S-LAND", Shift.day, Decimal("0.5"))],
    "NAJD": [("S-LAND", Shift.day, Decimal(1))],
    "GULFPAVE": [("S-AIR", Shift.day, Decimal("0.4")), ("S-AIR", Shift.night, Decimal("0.6"))],
    "SAHARA": [("S-LAND", Shift.day, Decimal(1))],
    "QIMMA": [("S-TWR", Shift.day, Decimal("0.6")), ("S-POD", Shift.day, Decimal("0.4"))],
    "DLIFT": [("S-TWR", Shift.day, Decimal(1))],
}
PEOPLE = [  # A.1.4 fake bilingual names (nationality ISO 3166 alpha-2)
    ("Imran Hussain", "عمران حسين", "PK"),
    ("Rajesh Nair", "راجيش ناير", "IN"),
    ("Abdul Karim Mia", "عبد الكريم ميا", "BD"),
    ("Mahmoud Fathy", "محمود فتحي", "EG"),
    ("Jomar Santos", "جومار سانتوس", "PH"),
    ("Suman Tamang", "سومان تامانغ", "NP"),
    ("Saad Al-Dosari", "سعد الدوسري", "SA"),
    ("Waleed Saleh", "وليد صالح", "YE"),
    ("Osman Idris", "عثمان إدريس", "SD"),
]
MECHANISMS = [  # A.5.4 (heat handled separately)
    (Mechanism.slip_trip_same_level, 22),
    (Mechanism.struck_by_falling_object, 15),
    (Mechanism.overexertion_manual_handling, 14),
    (Mechanism.caught_in_between, 10),
    (Mechanism.fall_from_height, 9),
    (Mechanism.struck_against, 9),
    (Mechanism.other, 9),
]
MECH_DETAIL = {  # mechanism → (agency, body parts, nature for minor, nature for serious)
    Mechanism.slip_trip_same_level: (
        Agency.ground_surface,
        [BodyPart.ankle, BodyPart.knee, BodyPart.hand],
        InjuryNature.abrasion,
        InjuryNature.sprain_strain,
    ),
    Mechanism.struck_by_falling_object: (
        Agency.materials,
        [BodyPart.head, BodyPart.shoulder, BodyPart.foot],
        InjuryNature.contusion,
        InjuryNature.laceration,
    ),
    Mechanism.overexertion_manual_handling: (
        Agency.materials,
        [BodyPart.lower_back, BodyPart.shoulder],
        InjuryNature.sprain_strain,
        InjuryNature.sprain_strain,
    ),
    Mechanism.caught_in_between: (
        Agency.formwork,
        [BodyPart.finger, BodyPart.hand],
        InjuryNature.contusion,
        InjuryNature.crush,
    ),
    Mechanism.fall_from_height: (
        Agency.ladder,
        [BodyPart.wrist, BodyPart.ankle],
        InjuryNature.contusion,
        InjuryNature.fracture,
    ),
    Mechanism.struck_against: (
        Agency.rebar_steel,
        [BodyPart.forearm, BodyPart.head],
        InjuryNature.abrasion,
        InjuryNature.laceration,
    ),
    Mechanism.other: (
        Agency.hand_tool,
        [BodyPart.hand, BodyPart.eye],
        InjuryNature.foreign_body_eye,
        InjuryNature.laceration,
    ),
    Mechanism.exposure_heat: (
        Agency.weather_sun,
        [BodyPart.internal_systemic],
        InjuryNature.heat_exhaustion,
        InjuryNature.heat_exhaustion,
    ),
}
TRADES = {
    "RAWABI": [Trade.labourer, Trade.carpenter, Trade.steel_fixer, Trade.mason],
    "NAJD": [Trade.steel_erector, Trade.rigger, Trade.welder],
    "GULFPAVE": [Trade.plant_operator, Trade.labourer, Trade.flagman, Trade.driver],
    "SAHARA": [Trade.scaffolder, Trade.labourer],
    "QIMMA": [Trade.labourer, Trade.carpenter, Trade.steel_fixer, Trade.electrician],
    "DLIFT": [Trade.crane_operator, Trade.rigger],
}
ACTIVITY = {
    "RAWABI": [Activity.concrete, Activity.formwork, Activity.rebar, Activity.excavation],
    "NAJD": [Activity.steel_erection, Activity.lifting, Activity.work_at_height],
    "GULFPAVE": [Activity.paving_asphalt, Activity.airfield_lighting, Activity.driving_transport],
    "SAHARA": [Activity.scaffolding, Activity.work_at_height],
    "QIMMA": [Activity.concrete, Activity.formwork, Activity.mep_installation],
    "DLIFT": [Activity.lifting],
}
OBS_CATS = {
    "RAWABI": [
        ObservationCategory.housekeeping,
        ObservationCategory.ppe,
        ObservationCategory.excavation,
        ObservationCategory.electrical,
        ObservationCategory.manual_handling,
    ],
    "NAJD": [
        ObservationCategory.lifting,
        ObservationCategory.work_at_height,
        ObservationCategory.hot_work,
    ],
    "GULFPAVE": [
        ObservationCategory.airside_fod_control,
        ObservationCategory.airside_driving,
        ObservationCategory.traffic_plant,
        ObservationCategory.heat_stress,
    ],
    "SAHARA": [ObservationCategory.scaffolding, ObservationCategory.work_at_height],
    "QIMMA": [
        ObservationCategory.housekeeping,
        ObservationCategory.work_at_height,
        ObservationCategory.ppe,
        ObservationCategory.electrical,
    ],
    "DLIFT": [ObservationCategory.lifting],
}
ROOT_CAUSES = ["OF-04", "TE-08", "OF-03", "TE-03", "IT-03", "OF-01", "TE-06", "AD-06", "OF-05"]
ROOT_WEIGHTS = [30, 25, 10, 8, 7, 7, 5, 4, 4]
SAFE_TEXT = [
    (
        "Barricades and signage in place around the work area",
        "الحواجز واللافتات في مكانها حول منطقة العمل",
    ),
    (
        "Workers using full-body harness with 100 % tie-off",
        "العمال يستخدمون أحزمة كاملة مع ربط دائم",
    ),
    ("Good housekeeping, access routes clear", "نظافة جيدة وممرات الوصول خالية"),
    ("Spotter in place for reversing plant", "مراقب موجود لتوجيه المعدات أثناء الرجوع"),
    (
        "Hydration station stocked and shaded rest area used",
        "محطة مياه مجهزة واستخدام منطقة الاستراحة المظللة",
    ),
]
UNSAFE_TEXT = [
    ("Missing toe-board on working platform", "لوح القدم مفقود على منصة العمل"),
    ("Worker not tied off at open edge", "عامل غير مربوط عند حافة مفتوحة"),
    (
        "Loose material near the apron edge (FOD risk)",
        "مواد سائبة قرب حافة الساحة (خطر أجسام غريبة)",
    ),
    ("Unguarded rebar ends", "أطراف حديد تسليح دون حماية"),
    ("Lifting without tag line", "رفع دون حبل توجيه"),
    ("Vehicle driving above airside speed limit", "مركبة تتجاوز السرعة المسموحة في الجانب الجوي"),
]


def seed_settings(db: Session) -> None:
    """Phase 1 settings per project, reference lists, and the fake AI transfer approval."""
    hse_settings.seed_reference(db)
    manager = db.scalar(select(User).where(User.email == "faisal.harbi@example.com"))
    for project in db.scalars(select(Project)):
        s = hse_settings.get(db, project.id)
        if s.ai_approved_on is None:
            s.ai_requested = True
            s.ai_approved_on = date(2026, 9, 1)
            for k, v in FAKE_APPROVAL.items():
                setattr(s, k, v)
            s.ai_approval_recorded_by = manager.id if manager else None
            s.ai_approval_recorded_at = now()
    db.flush()


# ---- helpers -------------------------------------------------------------------------------------


@dataclass
class Ctx:
    db: Session
    rng: random.Random
    project: Project
    sites: dict[str, Site]
    zones: dict[str, Zone]
    engs: dict[str, ProjectEngagement]
    users: dict[str, User]
    mh: dict[tuple[str, date], int] = field(default_factory=dict)  # (eng, month) → MH
    seq: dict[tuple[str, int], int] = field(default_factory=lambda: defaultdict(int))
    reserved: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    person_seq: int = 0
    incidents: list[Incident] = field(default_factory=list)
    cases: list[InjuryCase] = field(default_factory=list)
    unsafe_obs: dict[date, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    inspections_with_findings: dict[date, list[Inspection]] = field(
        default_factory=lambda: defaultdict(list)
    )
    sites_by_id: dict[uuid.UUID, Site] = field(default_factory=dict)
    inc_cases: dict[uuid.UUID, list[InjuryCase]] = field(default_factory=dict)
    inc_roots: dict[uuid.UUID, list[str]] = field(default_factory=dict)

    def next(self, kind: str, year: int) -> int:
        n = self.seq[(kind, year)] + 1
        while kind == "INC" and n in self.reserved[year]:
            n += 1
        self.seq[(kind, year)] = n
        return n


def _months(first: date, last: date) -> list[date]:
    out, m = [], month_start(first)
    while m <= last:
        out.append(m)
        m = add_months(m, 1)
    return out


def _days(m: date, start: date, end: date) -> list[date]:
    d0, d1 = max(m, start), min(month_end(m), end)
    return [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)] if d1 >= d0 else []


def _weight(d: date) -> Decimal:
    if d in EID:
        return Decimal(0)
    if d.weekday() == 4:  # Friday
        return Decimal("0.15")
    if calendar.in_ramadan(d):
        return Decimal("0.85")
    return Decimal(1)


def _split(total: int, weights: list[Decimal]) -> list[int]:
    """Integer split; the remainder goes to the last day with the full weight (A.4.4)."""
    w = sum(weights)
    if w == 0:
        return [0] * len(weights)
    parts = [int(Decimal(total) * x / w) for x in weights]
    rest = total - sum(parts)
    idx = max((i for i, x in enumerate(weights) if x == max(weights)), default=len(weights) - 1)
    parts[idx] += rest
    return parts


def _at(d: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(d, time(hour % 24, minute), RIYADH).astimezone(UTC)


def _working_day(ctx: Ctx, m: date, start: date | None = None) -> date:
    days = [d for d in _days(m, start or m, SEED_END) if _weight(d) == 1]
    return ctx.rng.choice(days or _days(m, start or m, SEED_END))


def _pick_eng(ctx: Ctx, m: date, codes: list[str]) -> str:
    weights = [ctx.mh.get((c, m), 0) for c in codes]
    if not any(weights):
        return codes[0]
    return ctx.rng.choices(codes, weights=weights)[0]


# ---- workforce -----------------------------------------------------------------------------------


def _eng_month_mh(project_code: str, m: date, active: dict[str, list[date]]) -> dict[str, int]:
    if project_code == "ANIA-EXP":
        if m == date(2026, 9, 1):
            return dict(SEP_2026)
        if m in W3:
            total = W3[m][0]
            out = {k: int((Decimal(total) * v).quantize(Decimal(1))) for k, v in SHARES.items()}
            out["RAWABI"] = total - sum(out.values())
            return out
        total = ANIA_RAMP.get(m, 0)
        base = {"RAWABI": Decimal("0.41"), **SHARES}
    else:
        total = RBT_MONTHLY.get(m, 0)
        base = {"QIMMA": Decimal("0.85"), "DLIFT": Decimal("0.15")}
    days_in = Decimal((month_end(m) - m).days + 1)
    w = {k: v * Decimal(len(active.get(k, []))) / days_in for k, v in base.items()}
    w = {k: v for k, v in w.items() if v > 0}
    s = sum(w.values())
    out = {k: int((Decimal(total) * v / s).quantize(Decimal(1))) for k, v in w.items()}
    first = next(iter(out))
    out[first] += total - sum(out.values())
    return out


def seed_workforce(ctx: Ctx, months: list[date], tbt: dict[date, int]) -> None:
    rows: list[dict[str, Any]] = []
    code = ctx.project.code
    creator = ctx.users["noura.qahtani" if code == "ANIA-EXP" else "yousef.ghamdi"].id
    for m in months:
        active = {}
        for c, e in ctx.engs.items():
            end = DLIFT_LAST_HOURS if c == "DLIFT" else SEED_END
            active[c] = list(_days(m, e.mobilisation_date, end))
        per_eng = _eng_month_mh(code, m, active)
        cell_rows: list[dict[str, Any]] = []
        for c, e in ctx.engs.items():
            ctx.mh[(c, m)] = per_eng.get(c, 0)
            all_days = _days(m, e.mobilisation_date, SEED_END)
            if not all_days:
                continue
            cells = CELLS[c]
            alloc = _split(per_eng.get(c, 0), [s for _, _, s in cells])
            for (site, shift, _), cell_total in zip(cells, alloc, strict=True):
                days = [d for d in all_days if not (c == "GULFPAVE" and d in GULFPAVE_MISSING)]
                weights = [
                    Decimal(0) if (c == "DLIFT" and d > DLIFT_LAST_HOURS) else _weight(d)
                    for d in days
                ]
                parts = _split(cell_total, weights)
                for d, mh, wt in zip(days, parts, weights, strict=True):
                    hpp = Decimal("8.5") if calendar.in_ramadan(d) else Decimal(10)
                    hc = math.ceil(Decimal(mh) / hpp) if mh else 0
                    status = (
                        WorkforceStatus.locked
                        if m <= LOCKED_UNTIL
                        else (
                            WorkforceStatus.verified
                            if d <= date(2026, 9, 25)
                            else WorkforceStatus.submitted
                        )
                    )
                    cell_rows.append(
                        {
                            "id": uuid.uuid4(),
                            "project_id": ctx.project.id,
                            "site_id": ctx.sites[site].id,
                            "zone_id": None,
                            "engagement_id": e.id,
                            "work_date": d,
                            "shift": shift,
                            "no_work": mh == 0,
                            "headcount": hc,
                            "man_hours": Decimal(mh),
                            "toolbox_talks": 0,
                            "toolbox_attendees": 0,
                            "inductions": 0,
                            "training_hours": Decimal(0),
                            "remarks": "Eid holiday"
                            if d in EID
                            else ("Suspended — no work" if wt == 0 and c == "DLIFT" else None),
                            "source": WorkforceSource.manual,
                            "status": status,
                            "warnings": [],
                            "created_by_user_id": creator,
                            "verified_by_user_id": creator
                            if status != WorkforceStatus.submitted
                            else None,
                            "verified_at": _at(d + timedelta(days=2), 9)
                            if status != WorkforceStatus.submitted
                            else None,
                            "seed_fake": True,
                        }
                    )
        # toolbox talks, attendees, training, inductions (proportional to man-hours)
        working = [r for r in cell_rows if r["man_hours"] > 0]
        talks = tbt.get(m) or max(1, int(sum(r["man_hours"] for r in working) / 2000))
        mh_w = [Decimal(r["man_hours"]) for r in working]
        for r, n in zip(working, _split(talks, mh_w), strict=True):
            r["toolbox_talks"] = n
            r["toolbox_attendees"] = min(n * 25, r["headcount"] * max(n, 1))
            r["training_hours"] = Decimal(r["headcount"]) * Decimal("0.06")
            r["inductions"] = ctx.rng.choice([0, 0, 0, 1, 2])
        rows += cell_rows
    for i in range(0, len(rows), 2000):
        ctx.db.execute(insert(WorkforceReturn), rows[i : i + 2000])
    for m in months:
        if m <= LOCKED_UNTIL:
            ctx.db.add(
                PeriodLock(
                    project_id=ctx.project.id,
                    month=m,
                    locked=True,
                    locked_at=_at(add_months(m, 1) + timedelta(days=9), 1),
                )
            )
    ctx.db.flush()


# ---- incidents and injury cases ------------------------------------------------------------------


@dataclass
class Spec:
    """One incident to create."""

    d: date
    eng: str
    types: list[IncidentType]
    category: CaseCategory | None = None
    days_away: int = 0
    hour: int | None = None
    seq: int | None = None
    title: str | None = None
    title_ar: str | None = None
    mechanism: Mechanism | None = None
    nature: InjuryNature | None = None
    body: BodyPart | None = None
    agency: Agency | None = None
    trade: Trade | None = None
    person: int | None = None
    id_number: str | None = None
    days_on_site: int | None = None
    zone: str | None = None
    site: str | None = None
    flags: list[AirsideFlag] = field(default_factory=list)
    potential: int | None = None
    activity: Activity | None = None
    do_category: DangerousOccurrenceCategory | None = None
    work_related: bool = True
    voided: bool = False
    root_causes: list[str] | None = None
    heat: bool = False
    restricted: tuple[int, int] | None = None
    shift: IncidentShift | None = None


def _named_ania() -> list[Spec]:
    return [
        Spec(
            date(2025, 9, 17),
            "RAWABI",
            [IncidentType.injury_illness],
            CaseCategory.LTI,
            12,
            hour=10,
            mechanism=Mechanism.struck_against,
            nature=InjuryNature.fracture,
            body=BodyPart.foot,
            agency=Agency.rebar_steel,
            trade=Trade.steel_fixer,
            title="Foot fracture — struck against rebar cage",
            site="S-LAND",
        ),
        Spec(
            date(2025, 12, 14),
            "RAWABI",
            [IncidentType.injury_illness],
            CaseCategory.LTI,
            9,
            hour=11,
            seq=201,
            mechanism=Mechanism.struck_by_falling_object,
            nature=InjuryNature.fracture,
            body=BodyPart.shoulder,
            agency=Agency.formwork,
            trade=Trade.labourer,
            site="S-LAND",
            zone="Z-PIERB",
            title="Labourer struck by falling formwork panel",
            title_ar="سقوط لوح قوالب على عامل",
        ),
        Spec(
            date(2026, 5, 19),
            "GULFPAVE",
            [IncidentType.injury_illness],
            CaseCategory.LTI,
            15,
            hour=23,
            seq=93,
            mechanism=Mechanism.caught_in_between,
            nature=InjuryNature.crush,
            body=BodyPart.lower_leg,
            agency=Agency.earthmoving,
            trade=Trade.plant_operator,
            site="S-AIR",
            zone="Z-TWB",
            flags=[AirsideFlag.airside_vehicle_incident],
            shift=IncidentShift.night,
            title="Plant operator caught between paver and kerb on Taxiway B strip",
        ),
        Spec(
            date(2026, 9, 8),
            "NAJD",
            [IncidentType.injury_illness],
            CaseCategory.LTI,
            20,
            hour=9,
            seq=147,
            mechanism=Mechanism.fall_from_height,
            nature=InjuryNature.fracture,
            body=BodyPart.wrist,
            agency=Agency.scaffold,
            trade=Trade.scaffolder,
            person=0,
            id_number="2000000017",
            days_on_site=14,
            site="S-LAND",
            zone="Z-PIERB",
            root_causes=["AD-01", "OF-04", "TE-08"],
            title="Fall from scaffold working platform at Pier B grid C-14",
            title_ar="سقوط من منصة عمل السقالة عند الرصيف B المحور C-14",
        ),
        Spec(
            date(2026, 7, 22),
            "GULFPAVE",
            [IncidentType.near_miss],
            hour=14,
            seq=121,
            site="S-AIR",
            zone="Z-APR-21",
            flags=[AirsideFlag.fod_event],
            potential=4,
            title="FOD (loose bolts) found on Apron stand 23 during live operations",
            title_ar="أجسام غريبة (براغي سائبة) على موقف الساحة 23 أثناء التشغيل",
        ),
        Spec(
            date(2026, 9, 11),
            "NAJD",
            [IncidentType.dangerous_occurrence],
            hour=13,
            seq=150,
            site="S-LAND",
            zone="Z-PIERB",
            potential=4,
            do_category=DangerousOccurrenceCategory.crane_lifting_failure,
            title="Sling failure — 1.2 t steel beam dropped in exclusion zone, no injury",
            title_ar="انقطاع حبل رفع — سقوط عارضة حديد 1.2 طن في منطقة الحظر دون إصابات",
        ),
    ]


def _sep_2026_ania() -> list[Spec]:
    """Sep 2026 mirrors the W1 incident list (contractors and categories)."""
    inj = IncidentType.injury_illness
    out = [
        Spec(
            date(2026, 9, 15),
            "SAHARA",
            [inj],
            CaseCategory.RWC,
            restricted=(1, 5),
            hour=8,
            mechanism=Mechanism.struck_by_falling_object,
            nature=InjuryNature.contusion,
            body=BodyPart.shoulder,
            title="Struck by falling clamp, restricted duties 5 days",
        ),
        Spec(
            date(2026, 9, 20),
            "RAWABI",
            [inj],
            CaseCategory.MTC,
            hour=10,
            mechanism=Mechanism.other,
            nature=InjuryNature.laceration,
            body=BodyPart.hand,
            title="Hand laceration from cutting tool, sutures",
        ),
        Spec(
            date(2026, 9, 22),
            "GULFPAVE",
            [inj],
            CaseCategory.MTC,
            hour=11,
            heat=True,
            site="S-AIR",
            title="Heat exhaustion during paving, IV fluids",
        ),
    ]
    for eng, n in (("RAWABI", 3), ("NAJD", 1), ("GULFPAVE", 1), ("SAHARA", 1)):
        out += [
            Spec(date(2026, 9, 2 + 4 * i + len(out) % 3), eng, [inj], CaseCategory.FAC)
            for i in range(n)
        ]
    for eng, n in (("RAWABI", 10), ("NAJD", 6), ("GULFPAVE", 5), ("SAHARA", 3)):
        out += [
            Spec(date(2026, 9, 1 + (i * 3 + len(out)) % 29), eng, [IncidentType.near_miss])
            for i in range(n)
        ]
    out += [
        Spec(date(2026, 9, 6), "RAWABI", [IncidentType.property_damage], hour=15),
        Spec(
            date(2026, 9, 19),
            "GULFPAVE",
            [IncidentType.property_damage],
            hour=2,
            flags=[AirsideFlag.gse_damage],
            shift=IncidentShift.night,
        ),
        Spec(
            date(2026, 9, 25),
            "GULFPAVE",
            [IncidentType.environmental],
            hour=9,
            title="Diesel spill 40 L from paver, contained",
        ),
        Spec(
            date(2026, 9, 17),
            "RAWABI",
            [inj],
            CaseCategory.FAC,
            hour=21,
            work_related=False,
            title="Off-duty illness at camp",
        ),
        Spec(
            date(2026, 9, 18),
            "RAWABI",
            [IncidentType.near_miss],
            voided=True,
            title="Duplicate report of a near miss",
        ),
    ]
    return out


def _month_specs(ctx: Ctx, m: date, named: list[Spec]) -> list[Spec]:
    code = ctx.project.code
    specs = [s for s in named if month_start(s.d) == m]
    if code == "ANIA-EXP" and m == date(2026, 9, 1):
        return specs + _sep_2026_ania()
    engs = [c for c in ctx.engs if ctx.mh.get((c, m), 0) > 0]
    if not engs:
        return specs
    inj = IncidentType.injury_illness
    if code == "ANIA-EXP" and m in W3:
        _, lti, rwc, jtc, mtc, fac, nm = W3[m]
        do, pd, env = A3[m][8], A3[m][9], A3[m][10]
        lti -= sum(1 for s in specs if s.category == CaseCategory.LTI)
        nm -= sum(1 for s in specs if IncidentType.near_miss in s.types)
        do -= sum(1 for s in specs if IncidentType.dangerous_occurrence in s.types)
    elif code == "ANIA-EXP":
        lti = rwc = jtc = do = 0
        mtc, fac, nm = ctx.rng.randint(0, 1), ctx.rng.randint(2, 4), ctx.rng.randint(6, 12)
        pd, env = ctx.rng.randint(0, 1), 0
    else:
        lti = rwc = jtc = do = env = 0
        mtc = 1 if m == date(2026, 3, 1) else 0
        fac, nm, pd = ctx.rng.randint(1, 3), ctx.rng.randint(4, 8), ctx.rng.randint(0, 1)
    summer = m.month in (6, 7, 8, 9)
    for _ in range(mtc):
        heat = summer and code == "ANIA-EXP" and ctx.rng.random() < 0.6
        eng = _pick_eng(ctx, m, ["GULFPAVE", "RAWABI"] if heat else engs)
        d = date(2026, 3, 10) if code == "RBT-52" else _working_day(ctx, m)
        specs.append(
            Spec(
                d,
                "QIMMA" if code == "RBT-52" else eng,
                [inj],
                CaseCategory.MTC,
                heat=heat,
                site="S-AIR" if heat else None,
                hour=ctx.rng.choice([10, 11, 15, 16]) if heat else None,
                mechanism=Mechanism.other if code == "RBT-52" else None,
                nature=InjuryNature.laceration if code == "RBT-52" else None,
                body=BodyPart.hand if code == "RBT-52" else None,
                title="Hand laceration, sutures" if code == "RBT-52" else None,
            )
        )
    for cat, n in (
        (CaseCategory.LTI, lti),
        (CaseCategory.RWC, rwc),
        (CaseCategory.JTC, jtc),
        (CaseCategory.FAC, fac),
    ):
        for _ in range(n):
            specs.append(
                Spec(
                    _working_day(ctx, m),
                    _pick_eng(ctx, m, engs),
                    [inj],
                    cat,
                    days_away=ctx.rng.randint(3, 10) if cat == CaseCategory.LTI else 0,
                    restricted=(1, ctx.rng.randint(3, 8)) if cat == CaseCategory.RWC else None,
                )
            )
    for t, n in (
        (IncidentType.near_miss, nm),
        (IncidentType.property_damage, pd),
        (IncidentType.environmental, env),
        (IncidentType.dangerous_occurrence, do),
    ):
        for _ in range(max(n, 0)):
            eng = _pick_eng(ctx, m, engs)
            night = eng == "GULFPAVE" and ctx.rng.random() < 0.6
            flags = []
            if eng == "GULFPAVE" and t in (IncidentType.near_miss, IncidentType.property_damage):
                flags = [
                    AirsideFlag.fod_event
                    if t == IncidentType.near_miss
                    else AirsideFlag.airside_vehicle_incident
                ]
            specs.append(
                Spec(
                    _working_day(ctx, m),
                    eng,
                    [t],
                    hour=ctx.rng.choice([22, 1, 3]) if night else None,
                    flags=flags,
                    shift=IncidentShift.night if night else None,
                    do_category=DangerousOccurrenceCategory.crane_lifting_failure
                    if t == IncidentType.dangerous_occurrence
                    else None,
                )
            )
    return specs


def _treatments(cat: CaseCategory, heat: bool) -> tuple[list[str], TreatedAt]:
    if cat == CaseCategory.FAC:
        return (
            ["fluids_oral_heat"] if heat else ["wound_cleaning", "wound_covering_steristrips"],
            TreatedAt.site_clinic,
        )
    if cat == CaseCategory.MTC:
        return (["iv_fluids"] if heat else ["sutures_staples_glue"]), TreatedAt.hospital_outpatient
    if cat == CaseCategory.LTI:
        return [
            "rigid_splint",
            "prescription_medication",
            "x_ray_diagnosis",
        ], TreatedAt.hospital_outpatient
    return ["prescription_medication"], TreatedAt.hospital_outpatient


def _person(ctx: Ctx, idx: int | None) -> tuple[str, str, IdType, str]:
    ctx.person_seq += 1
    name_en, _name_ar, nat = PEOPLE[idx if idx is not None else ctx.rng.randrange(len(PEOPLE))]
    n = ctx.person_seq
    if n == 17:  # 2000000017 is reserved for INC-ANIA-EXP-2026-0147
        ctx.person_seq += 1
        n = ctx.person_seq
    if nat == "SA":
        return name_en, nat, IdType.national_id, f"10000{n:05d}"[-10:]
    return name_en, nat, IdType.iqama, f"20000{n:05d}"[-10:]


def _incident(ctx: Ctx, s: Spec) -> Incident:
    rng = ctx.rng
    code = ctx.project.code
    e = ctx.engs[s.eng]
    sites = [x for x in ctx.sites.values() if x.id in set(e.site_ids)]
    site = ctx.sites[s.site] if s.site else rng.choice(sites)
    zone = ctx.zones.get(s.zone) if s.zone else None
    if zone is None and rng.random() < 0.5:
        zs = [z for z in ctx.zones.values() if z.site_id == site.id]
        zone = rng.choice(zs) if zs else None
    hour = s.hour if s.hour is not None else rng.choice([7, 8, 9, 10, 11, 13, 14, 15, 16])
    occurred = _at(s.d, hour, rng.choice([0, 10, 20, 40, 50]))
    late = rng.random() < 0.03
    reported = occurred + timedelta(hours=rng.randint(26, 40) if late else rng.randint(1, 6))
    year = s.d.year
    seq = s.seq if s.seq is not None else ctx.next("INC", year)
    primary = s.types[0]
    heat = s.heat
    cat = s.category
    title = s.title or {
        IncidentType.near_miss: "Near miss — "
        + rng.choice(
            [
                "unsecured load",
                "plant reversing without banksman",
                "dropped hand tool",
                "open edge without barrier",
            ]
        ),
        IncidentType.property_damage: "Property damage — "
        + rng.choice(["vehicle struck barrier", "GSE damaged by paver", "damaged cable tray"]),
        IncidentType.environmental: "Minor oil spill, contained",
        IncidentType.dangerous_occurrence: "Lifting equipment failure, no injury",
    }.get(primary, "Injury — " + (cat.value if cat else "case"))
    arabic = rng.random() < 0.3
    status = IncidentStatus.closed
    if s.voided:
        status = IncidentStatus.voided
    elif s.d >= date(2026, 9, 26):
        status = IncidentStatus.reported
    elif s.d >= date(2026, 9, 1):
        status = (
            IncidentStatus.under_investigation
            if cat in (CaseCategory.LTI, CaseCategory.RWC) or s.do_category
            else IncidentStatus.actions_pending
        )
    elif s.d >= date(2026, 8, 15):
        status = IncidentStatus.actions_pending
    if s.seq == 147:
        status = IncidentStatus.actions_pending
    inc = Incident(
        id=uuid.uuid4(),
        project_id=ctx.project.id,
        ref=f"INC-{code}-{year}-{seq:04d}",
        year=year,
        seq=seq,
        site_id=site.id,
        zone_id=zone.id if zone else None,
        location_detail="Pier B grid C-14" if s.seq == 147 else None,
        responsible_engagement_id=e.id,
        occurred_at=occurred,
        occurred_date=s.d,
        reported_at=reported,
        reported_by_user_id=ctx.users[
            "noura.qahtani" if code == "ANIA-EXP" else "yousef.ghamdi"
        ].id,
        shift=s.shift or (IncidentShift.night if hour >= 20 or hour < 5 else IncidentShift.day),
        incident_types=[t.value for t in s.types],
        primary_type=primary,
        title=(s.title_ar if arabic and s.title_ar else title)[:150],
        description=(s.title_ar or title)
        if arabic
        else f"{title}. Area made safe; supervisor informed.",
        immediate_actions="تم تأمين المنطقة وإبلاغ المشرف"
        if arabic
        else "Area barricaded, work stopped, first aid given where needed",
        activity=s.activity or rng.choice(ACTIVITY[s.eng]),
        work_related=s.work_related,
        not_work_related_reason=None if s.work_related else NotWorkRelatedReason.off_duty_camp,
        work_related_rationale=None if s.work_related else "Illness at camp outside working hours",
        actual_severity=3
        if cat == CaseCategory.LTI
        else (2 if cat in (CaseCategory.MTC, CaseCategory.RWC, CaseCategory.JTC) else 1),
        potential_severity=s.potential
        or (4 if cat == CaseCategory.LTI else rng.choice([1, 2, 2, 3])),
        ambient_temp_c=Decimal(rng.randint(42, 47)) if heat else None,
        airside_flags=[f.value for f in s.flags],
        pd_estimated_cost_sar=Decimal(rng.choice([4500, 12000, 28000]))
        if primary == IncidentType.property_damage
        else None,
        env_category=EnvCategory.spill if primary == IncidentType.environmental else None,
        env_substance="diesel" if primary == IncidentType.environmental else None,
        env_quantity_l=Decimal(40) if primary == IncidentType.environmental else None,
        env_contained=True if primary == IncidentType.environmental else None,
        env_reached=EnvReached.soil if primary == IncidentType.environmental else None,
        do_category=s.do_category,
        status=status,
        void_reason="Duplicate of an earlier near-miss report" if s.voided else None,
        closed_at=_at(s.d + timedelta(days=30), 12) if status == IncidentStatus.closed else None,
        created_by_user_id=ctx.users["noura.qahtani" if code == "ANIA-EXP" else "yousef.ghamdi"].id,
        alerts_sent=[],
        seed_fake=True,
    )
    ctx.incidents.append(inc)
    if cat is not None:
        if heat:
            mech, (agency, bodies, nature, _) = (
                Mechanism.exposure_heat,
                MECH_DETAIL[Mechanism.exposure_heat],
            )
        else:
            mech = (
                s.mechanism
                or rng.choices([m for m, _ in MECHANISMS], [w for _, w in MECHANISMS])[0]
            )
            agency, bodies, minor, serious = MECH_DETAIL[mech]
            nature = minor if cat == CaseCategory.FAC else serious
        name, nat, id_type, number = _person(ctx, s.person)
        if s.id_number:
            number = s.id_number
        treat, where = _treatments(cat, heat)
        dos = (
            s.days_on_site
            if s.days_on_site is not None
            else (rng.randint(1, 30) if rng.random() < 0.35 else rng.randint(31, 700))
        )
        trade = s.trade or rng.choice(TRADES[s.eng])
        c = InjuryCase(
            id=uuid.uuid4(),
            incident_id=inc.id,
            project_id=ctx.project.id,
            person_no=1,
            person_type=PersonType.contractor_worker,
            employer_engagement_id=e.id,
            person_name=name,
            id_type=id_type,
            id_number_enc=crypto.encrypt(number),
            id_number_masked=crypto.mask_id(number),
            employee_no=f"{s.eng}-{ctx.person_seq:04d}",
            nationality=nat,
            trade=trade,
            age_band=rng.choice([AgeBand.a20_29, AgeBand.a30_39, AgeBand.a40_49]),
            site_start_date=s.d - timedelta(days=dos),
            hours_into_shift=Decimal(rng.randint(1, 9)),
            illness=heat,
            body_part=s.body or rng.choice(bodies),
            body_side=BodySide.right if s.seq == 147 else None,
            nature=s.nature or nature,
            mechanism=mech,
            agency=s.agency or agency,
            treatments=treat,
            treated_at=where,
            away_start_date=s.d + timedelta(days=1) if cat == CaseCategory.LTI else None,
            rtw_date=s.d + timedelta(days=1 + s.days_away) if cat == CaseCategory.LTI else None,
            restricted_start=s.d + timedelta(days=s.restricted[0]) if s.restricted else None,
            restricted_end=s.d + timedelta(days=s.restricted[0] + s.restricted[1] - 1)
            if s.restricted
            else None,
            transfer_start=s.d + timedelta(days=1) if cat == CaseCategory.JTC else None,
            transfer_end=s.d + timedelta(days=7) if cat == CaseCategory.JTC else None,
            gosi_case_ref=f"GOSI-TEST-{len(ctx.cases) + 1:04d}"
            if cat != CaseCategory.FAC
            else None,
            derived_category=cat,
            confirmed_category=cat,
            classification_status=ClassificationStatus.confirmed,
            seed_fake=True,
        )
        if cat == CaseCategory.FAC and s.d == date(2026, 9, 28):
            c.confirmed_category = None
            c.classification_status = ClassificationStatus.provisional
        ctx.cases.append(c)
        ctx.inc_cases[inc.id] = [c]
    else:
        ctx.inc_cases[inc.id] = []
    ctx.inc_roots[inc.id] = list(s.root_causes or [])
    return inc


def _investigation(ctx: Ctx, inc: Incident) -> Investigation | None:
    if inc.status in (IncidentStatus.voided, IncidentStatus.reported, IncidentStatus.draft):
        return None
    cases = ctx.inc_cases[inc.id]
    level = inc_svc.minimum_level(inc, cases)
    lead = ctx.users["noura.qahtani" if ctx.project.code == "ANIA-EXP" else "faisal.harbi"]
    team = (
        [ctx.users["ahmed.zahrani"].id, ctx.users["omar.siddiqui"].id]
        if ctx.project.code == "ANIA-EXP"
        else [ctx.users["yousef.ghamdi"].id, ctx.users["faisal.harbi"].id]
    )
    roots: list[dict[str, Any]] = []
    if level != InvestigationLevel.L1:
        codes = ctx.inc_roots[inc.id] or sorted(
            set(ctx.rng.choices(ROOT_CAUSES, ROOT_WEIGHTS, k=2))
        )
        roots = [
            {"code": c, "text": "Identified during the investigation", "linked_ca_ids": []}
            for c in codes
        ]
    done = inc.status in (IncidentStatus.actions_pending, IncidentStatus.closed)
    d0 = inc.occurred_date
    return Investigation(
        incident_id=inc.id,
        level=level,
        lead_investigator_id=lead.id,
        team_member_ids=team if level == InvestigationLevel.L3 else [],
        method={
            InvestigationLevel.L3: InvestigationMethod.icam,
            InvestigationLevel.L2: InvestigationMethod.five_why,
        }.get(level, InvestigationMethod.simple),
        due_date=d0 + timedelta(days=inc_svc.DUE_DAYS[level]),
        extensions=[],
        preliminary_report="Preliminary findings shared with the client."
        if level == InvestigationLevel.L3
        else None,
        preliminary_report_at=inc.occurred_at + timedelta(hours=30)
        if level == InvestigationLevel.L3
        else None,
        sequence_of_events="Sequence reconstructed from witness statements.",
        immediate_causes="Unsafe condition not identified before work started.",
        root_causes=roots,
        lessons_learned="Shared at the weekly HSE meeting."
        if level == InvestigationLevel.L3
        else None,
        ptw_involved=ctx.rng.random() < 0.3,
        submitted_at=_at(d0 + timedelta(days=inc_svc.DUE_DAYS[level] - 1), 15) if done else None,
        approved_by_user_id=ctx.users["faisal.harbi"].id if done else None,
        approved_at=_at(d0 + timedelta(days=inc_svc.DUE_DAYS[level]), 10) if done else None,
        alerts_sent=[],
        created_at=inc.reported_at or inc.occurred_at,
    )


def seed_incidents(ctx: Ctx, months: list[date]) -> list[Investigation]:
    named = _named_ania() if ctx.project.code == "ANIA-EXP" else []
    for s in named:
        if s.seq:
            ctx.reserved[s.d.year].add(s.seq)
    specs: list[Spec] = []
    for m in months:
        specs += _month_specs(ctx, m, named)
    for s in sorted(specs, key=lambda x: (x.d, x.hour or 0)):
        _incident(ctx, s)
    ctx.db.add_all(ctx.incidents)
    ctx.db.flush()
    ctx.db.add_all(ctx.cases)
    invs = [v for v in (_investigation(ctx, i) for i in ctx.incidents) if v is not None]
    ctx.db.add_all(invs)
    for inc in ctx.incidents:
        for r in inc_svc.required_notifications(inc, ctx.inc_cases[inc.id]):
            ctx.db.add(
                ExternalNotification(
                    incident_id=inc.id,
                    body=r.body,
                    notified_at=inc.occurred_at + timedelta(hours=ctx.rng.randint(2, 20)),
                    reference_no=f"SEED-{r.body.value.upper()}-{inc.seq:04d}",
                    notified_by_user_id=inc.created_by_user_id,
                    alerts_sent=[],
                )
            )
    ctx.db.flush()
    return invs


# ---- observations --------------------------------------------------------------------------------


def seed_observations(ctx: Ctx, months: list[date]) -> None:
    rng = ctx.rng
    code = ctx.project.code
    observers = (
        [
            ctx.users[u].id
            for u in ("noura.qahtani", "omar.siddiqui", "ahmed.zahrani", "khalid.otaibi")
        ]
        if code == "ANIA-EXP"
        else [ctx.users[u].id for u in ("yousef.ghamdi", "faisal.harbi")]
    )
    rows: list[dict[str, Any]] = []
    for m in months:
        engs = [c for c in ctx.engs if ctx.mh.get((c, m), 0) > 0]
        if not engs:
            continue
        if code == "ANIA-EXP" and m in A3:
            safe, unsafe = A3[m][0], A3[m][1]
        elif code == "ANIA-EXP":
            safe, unsafe = rng.randint(120, 220), rng.randint(60, 110)
        else:
            safe, unsafe = rng.randint(60, 90), rng.randint(25, 40)
        kinds = [(True, safe), (False, unsafe)]
        for is_safe, n in kinds:
            for _ in range(n):
                eng = _pick_eng(ctx, m, engs)
                e = ctx.engs[eng]
                site = ctx.sites_by_id[rng.choice(list(e.site_ids))]
                zs = [z for z in ctx.zones.values() if z.site_id == site.id]
                zone = rng.choice(zs) if zs and rng.random() < 0.6 else None
                d = _working_day(ctx, m, e.mobilisation_date)
                hour = (
                    rng.choice([22, 1, 3])
                    if eng == "GULFPAVE" and rng.random() < 0.5
                    else rng.randint(7, 16)
                )
                at = _at(d, hour, rng.randint(0, 59))
                t = (
                    rng.choice(
                        [ObservationType.safe_behaviour] * 3 + [ObservationType.safe_condition] * 2
                    )
                    if is_safe
                    else rng.choice(
                        [ObservationType.unsafe_act] * 2 + [ObservationType.unsafe_condition] * 3
                    )
                )
                txt = rng.choice(SAFE_TEXT if is_safe else UNSAFE_TEXT)
                arabic = rng.random() < 0.3
                risk = (
                    None
                    if is_safe
                    else rng.choices(
                        [RiskRating.low, RiskRating.medium, RiskRating.high], [50, 40, 10]
                    )[0]
                )
                on_spot = None if is_safe else rng.random() < 0.55
                anonymous = rng.random() < 0.02
                closed_d = (
                    d
                    if is_safe or on_spot
                    else min(d + timedelta(days=rng.randint(1, 5)), LAST_ACTIVITY)
                )
                row = {
                    "id": uuid.uuid4(),
                    "project_id": ctx.project.id,
                    "year": d.year,
                    "site_id": site.id,
                    "zone_id": zone.id if zone else None,
                    "observed_at": at,
                    "observed_date": d,
                    "observer_id": None if anonymous else rng.choice(observers),
                    "anonymous": anonymous,
                    "observed_engagement_id": e.id,
                    "obs_type": t,
                    "category": rng.choice(OBS_CATS[eng]),
                    "risk_rating": risk,
                    "description": txt[1] if arabic else txt[0],
                    "stop_work_applied": risk == RiskRating.high,
                    "immediate_action": None
                    if is_safe
                    else (
                        "تم إيقاف العمل وتصحيح الوضع"
                        if arabic
                        else "Work stopped and condition corrected"
                    ),
                    "closed_on_spot": on_spot,
                    "status": ObservationStatus.closed,
                    "closure_comment": None if is_safe else "Corrected",
                    "closed_at": _at(closed_d, 17),
                    "closed_date": closed_d,
                    "closed_by_user_id": observers[0],
                    "no_ca_alert_sent": False,
                    "seed_fake": True,
                }
                rows.append(row)
                if not is_safe and not on_spot and risk in (RiskRating.medium, RiskRating.high):
                    ctx.unsafe_obs[m].append(row)
    rows.sort(key=lambda r: r["observed_at"])
    for r in rows:
        seq = ctx.next("OBS", r["year"])
        r["seq"] = seq
        r["ref"] = f"OBS-{code}-{r['year']}-{seq:05d}"
    for i in range(0, len(rows), 2000):
        ctx.db.execute(insert(Observation), rows[i : i + 2000])
    ctx.db.flush()


# ---- inspections ---------------------------------------------------------------------------------

PLANS: dict[
    str,
    list[tuple[str, str, InspectionType, str, str | None, str | None, Weekday]],
] = {
    "ANIA-EXP": [
        (
            "General site inspection — airside",
            "تفتيش عام — الجانب الجوي",
            InspectionType.general_site,
            "S-AIR",
            None,
            "RAWABI",
            Weekday.sunday,
        ),
        (
            "General site inspection — Terminal 3",
            "تفتيش عام — الصالة 3",
            InspectionType.general_site,
            "S-LAND",
            None,
            "RAWABI",
            Weekday.monday,
        ),
        (
            "Scaffold inspection — Pier B",
            "تفتيش السقالات — الرصيف B",
            InspectionType.scaffold,
            "S-LAND",
            "Z-PIERB",
            "SAHARA",
            Weekday.tuesday,
        ),
        (
            "Lifting equipment — steel erection",
            "معدات الرفع — تركيب الحديد",
            InspectionType.lifting_equipment,
            "S-LAND",
            None,
            "NAJD",
            Weekday.wednesday,
        ),
        (
            "FOD walk — apron",
            "جولة الأجسام الغريبة — الساحة",
            InspectionType.airside_fod_walk,
            "S-AIR",
            "Z-APR-21",
            "GULFPAVE",
            Weekday.saturday,
        ),
        (
            "Plant & vehicles — airside",
            "المعدات والمركبات — الجانب الجوي",
            InspectionType.plant_vehicle,
            "S-AIR",
            None,
            "GULFPAVE",
            Weekday.thursday,
        ),
        (
            "Housekeeping — steel yard",
            "النظافة — ساحة الحديد",
            InspectionType.housekeeping,
            "S-LAND",
            "Z-LAY1",
            "NAJD",
            Weekday.sunday,
        ),
        (
            "Electrical — temporary supply",
            "الكهرباء — التغذية المؤقتة",
            InspectionType.electrical,
            "S-LAND",
            None,
            "RAWABI",
            Weekday.wednesday,
        ),
        (
            "Fire safety — Terminal 3",
            "السلامة من الحريق — الصالة 3",
            InspectionType.fire_safety,
            "S-LAND",
            None,
            "RAWABI",
            Weekday.thursday,
        ),
        (
            "Leadership walk — airside",
            "جولة القيادة — الجانب الجوي",
            InspectionType.leadership_walk,
            "S-AIR",
            None,
            None,
            Weekday.saturday,
        ),
    ],
    "RBT-52": [
        (
            "General site inspection — tower",
            "تفتيش عام — البرج",
            InspectionType.general_site,
            "S-TWR",
            None,
            "QIMMA",
            Weekday.sunday,
        ),
        (
            "Lifting equipment — tower crane",
            "معدات الرفع — الرافعة البرجية",
            InspectionType.lifting_equipment,
            "S-TWR",
            "Z-TC01",
            "DLIFT",
            Weekday.tuesday,
        ),
        (
            "Excavation — basement",
            "الحفريات — القبو",
            InspectionType.excavation,
            "S-POD",
            "Z-B4",
            "QIMMA",
            Weekday.wednesday,
        ),
    ],
}
PY_WEEKDAY = {
    Weekday.monday: 0,
    Weekday.tuesday: 1,
    Weekday.wednesday: 2,
    Weekday.thursday: 3,
    Weekday.friday: 4,
    Weekday.saturday: 5,
    Weekday.sunday: 6,
}


def seed_inspections(ctx: Ctx, months: list[date]) -> None:
    rng = ctx.rng
    code = ctx.project.code
    officer = ctx.users["noura.qahtani" if code == "ANIA-EXP" else "yousef.ghamdi"].id
    plans = []
    for name_en, name_ar, t, site, zone, eng, wd in PLANS[code]:
        plans.append(
            InspectionPlan(
                id=uuid.uuid4(),
                project_id=ctx.project.id,
                name_en=name_en,
                name_ar=name_ar,
                inspection_type=t,
                site_id=ctx.sites[site].id,
                zone_id=ctx.zones[zone].id if zone else None,
                engagement_id=ctx.engs[eng].id if eng else None,
                frequency=InspectionFrequency.weekly,
                weekday=wd,
                start_date=months[0],
                assignee_role=InspectionAssigneeRole.hse_officer,
                assignee_user_id=officer,
                active=True,
                generated_until=SEED_END,
            )
        )
    ctx.db.add_all(plans)
    ctx.db.flush()
    rows: list[Inspection] = []
    for m in months:
        cands = []
        for p in plans:
            for d in _days(m, m, SEED_END):
                if p.weekday is not None and d.weekday() == PY_WEEKDAY[p.weekday]:
                    cands.append((p, d))
        if code == "ANIA-EXP" and m in A3:
            planned, _on_time, late, missed = A3[m][2:6]
        else:
            planned = min(
                len(cands), rng.randint(10, 14) if code == "RBT-52" else rng.randint(18, 26)
            )
            missed = rng.randint(0, 2)
            late = rng.randint(0, 2)
        rng.shuffle(cands)
        chosen, spare = cands[:planned], cands[planned:]
        me = month_end(m)
        early = [c for c in chosen if c[1] <= me - timedelta(days=6)]
        rng.shuffle(early)
        bad = early[: late + missed]
        late_set = {id(c) for c in bad[:late]}
        missed_set = {id(c) for c in bad[late:]}
        for c in chosen:
            p, d = c
            if id(c) in missed_set:
                status, done = InspectionStatus.missed, None
            elif id(c) in late_set:
                status, done = InspectionStatus.completed, d + timedelta(days=rng.randint(3, 5))
            else:
                status, done = (
                    InspectionStatus.completed,
                    min(d + timedelta(days=rng.randint(0, 2)), me),
                )
            rows.append(_ins(ctx, p, d, status, done, officer))
        for p, d in spare[:1]:
            r = _ins(ctx, p, d, InspectionStatus.cancelled, None, officer)
            r.cancel_reason = "Area handed over / no work that week"
            rows.append(r)
        for _ in range(3):
            p = rng.choice(plans)
            d = _working_day(ctx, m)
            r = _ins(ctx, p, None, InspectionStatus.completed, d, officer)
            r.plan_id = None
            rows.append(r)
    rows.sort(key=lambda r: r.planned_date or r.completed_date or SEED_END)
    for r in rows:
        y = (r.planned_date or r.completed_date or SEED_END).year
        r.year = y
        r.seq = ctx.next("INS", y)
        r.ref = f"INS-{code}-{y}-{r.seq:05d}"
        if r.findings:
            ctx.inspections_with_findings[month_start(r.completed_date or SEED_END)].append(r)
    ctx.db.add_all(rows)
    ctx.db.flush()


def _ins(
    ctx: Ctx,
    p: InspectionPlan,
    planned: date | None,
    status: InspectionStatus,
    done: date | None,
    officer: uuid.UUID,
) -> Inspection:
    rng = ctx.rng
    checked = 20 if done else None
    ok = rng.randint(15, 20) if done else None
    findings = []
    if done and ok is not None and ok < 18:
        findings = [{"item": "Deficiency noted", "severity": "medium", "ca_id": None}]
    return Inspection(
        id=uuid.uuid4(),
        project_id=ctx.project.id,
        ref="",
        year=0,
        seq=0,
        plan_id=p.id,
        inspection_type=p.inspection_type,
        site_id=p.site_id,
        zone_id=p.zone_id,
        engagement_id=p.engagement_id,
        assignee_role=p.assignee_role,
        assignee_user_id=p.assignee_user_id,
        planned_date=planned,
        completed_at=_at(done, 11) if done else None,
        completed_date=done,
        inspector_id=officer if done else None,
        items_checked=checked,
        items_compliant=ok,
        findings=findings,
        status=status,
        missed_at=_at(planned + timedelta(days=3), 0)
        if status == InspectionStatus.missed and planned
        else None,
        seed_fake=True,
    )


# ---- corrective actions --------------------------------------------------------------------------

CA_TEXT = {
    ControlLevel.elimination: (
        "Eliminate manual lifting by pre-assembly at ground level",
        "إلغاء الرفع اليدوي بالتجميع المسبق على الأرض",
    ),
    ControlLevel.substitution: (
        "Substitute solvent-based product with water-based",
        "استبدال المنتج المذيب بآخر مائي",
    ),
    ControlLevel.engineering: (
        "Install double guardrails and toe-boards",
        "تركيب حواجز مزدوجة وألواح قدم",
    ),
    ControlLevel.administrative: (
        "Re-brief permit and inspection tagging procedure",
        "إعادة شرح إجراءات التصاريح ووسم التفتيش",
    ),
    ControlLevel.ppe: ("Issue cut-resistant gloves", "توزيع قفازات مقاومة للقطع"),
}
OWNERS = {
    "RAWABI": "ahmed.zahrani",
    "NAJD": "ramesh.kumar",
    "GULFPAVE": "omar.siddiqui",
    "SAHARA": "ramesh.kumar",
    "QIMMA": "yousef.ghamdi",
    "DLIFT": "yousef.ghamdi",
}
DUE = {CaPriority.critical: 1, CaPriority.high: 7, CaPriority.medium: 14, CaPriority.low: 30}


def seed_cas(ctx: Ctx, months: list[date], invs: dict[uuid.UUID, Investigation]) -> None:
    rng = ctx.rng
    code = ctx.project.code
    rows: list[CorrectiveAction] = []
    obs_close: list[tuple[uuid.UUID, date | None]] = []
    for m in months:
        engs = [c for c in ctx.engs if ctx.mh.get((c, m), 0) > 0]
        if not engs:
            continue
        if code == "ANIA-EXP" and m in A3:
            raised, overdue = A3[m][6], A3[m][7]
        else:
            raised, overdue = rng.randint(8, 16), rng.randint(0, 2)
        me = month_end(m)
        incs = [
            i
            for i in ctx.incidents
            if month_start(i.occurred_date) == m
            and i.id in invs
            and invs[i.id].level != InvestigationLevel.L1
        ]
        obs = list(ctx.unsafe_obs.get(m, []))
        insp = list(ctx.inspections_with_findings.get(m, []))
        sources: list[tuple[CaSourceType, Any]] = []
        named = [i for i in incs if i.seq == 147 and code == "ANIA-EXP"]
        for i in named:
            sources += [(CaSourceType.incident, i), (CaSourceType.incident, i)]
        for i in incs:
            if i not in named and len(sources) < raised * 0.4:
                sources.append((CaSourceType.incident, i))
        for o in obs:
            if len(sources) < raised * 0.8:
                sources.append((CaSourceType.observation, o))
        for x in insp:
            if len(sources) < raised:
                sources.append((CaSourceType.inspection, x))
        while len(sources) < raised:
            sources.append((CaSourceType.other, None))
        sources = sources[:raised]
        n_named = 2 if named else 0
        idx_over = set(rng.sample(range(n_named, raised), min(overdue, raised - n_named)))
        for k, (st, src) in enumerate(sources):
            if st == CaSourceType.incident:
                eng_id, site_id, zone_id = src.responsible_engagement_id, src.site_id, src.zone_id
                created = min(src.occurred_date + timedelta(days=rng.randint(1, 4)), me)
            elif st == CaSourceType.observation:
                eng_id, site_id, zone_id = (
                    src["observed_engagement_id"],
                    src["site_id"],
                    src["zone_id"],
                )
                created = src["observed_date"]
            elif st == CaSourceType.inspection:
                eng_id, site_id, zone_id = (
                    src.engagement_id or ctx.engs[engs[0]].id,
                    src.site_id,
                    src.zone_id,
                )
                created = src.completed_date
            else:
                ec = _pick_eng(ctx, m, engs)
                e = ctx.engs[ec]
                eng_id, site_id, zone_id = e.id, e.site_ids[0], None
                created = _working_day(ctx, m)
            eng_code = next(c for c, e in ctx.engs.items() if e.id == eng_id)
            if k in idx_over:
                created = min(created, m + timedelta(days=rng.randint(0, 9)))
                pr = rng.choice([CaPriority.high, CaPriority.medium])
                due = min(created + timedelta(days=DUE[pr]), me - timedelta(days=1))
            else:
                pr = rng.choices(list(DUE), [5, 25, 50, 20])[0]
                due = created + timedelta(days=DUE[pr])
            level = rng.choices(list(ControlLevel), [5, 10, 30, 45, 10])[0]
            if named and st == CaSourceType.incident and src.seq == 147:
                level = ControlLevel.engineering if k == 0 else ControlLevel.administrative
                pr = CaPriority.high if k == 0 else CaPriority.medium
                due = created + timedelta(days=DUE[pr])
            title_en, title_ar = CA_TEXT[level]
            if named and st == CaSourceType.incident and src.seq == 147 and k == 1:
                title_en, title_ar = (
                    "Scaffold inspection tagging re-briefing",
                    "إعادة شرح وسم فحص السقالات",
                )
            owner = ctx.users[OWNERS[eng_code]]
            verifier = ctx.users["noura.qahtani" if code == "ANIA-EXP" else "faisal.harbi"]
            if (
                pr in (CaPriority.medium, CaPriority.low)
                and code == "ANIA-EXP"
                and owner.email != "ahmed.zahrani@example.com"
            ):
                verifier = ctx.users["ahmed.zahrani"]
            completed: date | None
            if k in idx_over:
                completed = (
                    None if m == date(2026, 9, 1) else me + timedelta(days=rng.randint(3, 15))
                )
            elif rng.random() < 0.08 and due < me - timedelta(days=5):
                completed = due + timedelta(days=rng.randint(1, 4))  # late, before month end
            else:
                completed = created + timedelta(days=rng.randint(0, max((due - created).days, 0)))
            if completed and completed > LAST_ACTIVITY:
                completed = None
            verified = completed + timedelta(days=rng.randint(1, 3)) if completed else None
            if verified and verified > LAST_ACTIVITY:
                verified = None
            status = (
                CaStatus.closed
                if verified
                else CaStatus.pending_verification
                if completed
                else CaStatus.in_progress
                if rng.random() < 0.6
                else CaStatus.open
            )
            y = created.year
            ca = CorrectiveAction(
                id=uuid.uuid4(),
                project_id=ctx.project.id,
                year=y,
                seq=0,
                ref="",
                source_type=st,
                source_id=(
                    src.id
                    if st in (CaSourceType.incident, CaSourceType.inspection)
                    else src["id"]
                    if st == CaSourceType.observation
                    else None
                ),
                site_id=site_id,
                zone_id=zone_id,
                responsible_engagement_id=eng_id,
                title=title_en if rng.random() < 0.7 else title_ar,
                description=f"{title_en}. Responsible contractor to implement and "
                "provide evidence.",
                control_level=level,
                priority=pr,
                owner_id=owner.id,
                verifier_id=verifier.id,
                created_date=created,
                due_date=due,
                original_due_date=due,
                status=status,
                completed_at=_at(completed, 15) if completed else None,
                completed_date=completed,
                evidence_text="Completed; photos and inspection record attached."
                if completed
                else None,
                verified_at=_at(verified, 10) if verified else None,
                verified_date=verified,
                created_by_user_id=ctx.users[
                    "noura.qahtani" if code == "ANIA-EXP" else "yousef.ghamdi"
                ].id,
                alerts_sent=[],
                seed_fake=True,
            )
            rows.append(ca)
            if st == CaSourceType.observation:
                obs_close.append((src["id"], verified))
            if st == CaSourceType.incident and src.id in invs:
                for rc in invs[src.id].root_causes:
                    if not rc["linked_ca_ids"]:
                        rc["linked_ca_ids"] = [str(ca.id)]
                        break
            if st == CaSourceType.inspection:
                src.findings = [{**f, "ca_id": str(ca.id)} for f in src.findings]
    rows.sort(key=lambda r: r.created_date)
    for r in rows:
        r.seq = ctx.next("CA", r.year)
        r.ref = f"CA-{code}-{r.year}-{r.seq:05d}"
    ctx.db.add_all(rows)
    ctx.db.flush()
    for inv in invs.values():
        inv.root_causes = [dict(rc) for rc in inv.root_causes]
    # observation status follows its CA (O-4)
    for oid, verified in obs_close:
        obs_row = ctx.db.get(Observation, oid)
        if obs_row is None:
            continue
        if verified is None:
            obs_row.status, obs_row.closed_at, obs_row.closed_date, obs_row.closure_comment = (
                ObservationStatus.action_raised,
                None,
                None,
                None,
            )
        else:
            obs_row.status, obs_row.closed_at, obs_row.closed_date = (
                ObservationStatus.closed,
                _at(verified, 16),
                verified,
            )
    # incidents with an open CA are still pending actions
    open_by_inc = {
        r.source_id
        for r in rows
        if r.source_type == CaSourceType.incident and r.status != CaStatus.closed
    }
    for inc in ctx.incidents:
        if inc.id in open_by_inc and inc.status == IncidentStatus.closed:
            inc.status, inc.closed_at = IncidentStatus.actions_pending, None
    ctx.db.flush()


def seed_meetings(ctx: Ctx, months: list[date]) -> None:
    rng = ctx.rng
    rows = []
    for m in months:
        engs = [c for c in ctx.engs if ctx.mh.get((c, m), 0) > 0]
        if not engs:
            continue
        d = _working_day(ctx, m)
        invited = rng.randint(10, 14)
        rows.append(
            HseMeeting(
                id=uuid.uuid4(),
                project_id=ctx.project.id,
                engagement_id=None,
                meeting_type=MeetingType.hse_committee,
                title="Monthly HSE committee",
                planned_date=d,
                held_date=d,
                invited_count=invited,
                attended_count=invited - rng.randint(0, 2),
                seed_fake=True,
            )
        )
        for c in engs:
            for wk in (0, 14):
                pd = min(m + timedelta(days=3 + wk), month_end(m))
                held = pd if rng.random() < 0.9 else None
                inv = rng.randint(6, 10)
                rows.append(
                    HseMeeting(
                        id=uuid.uuid4(),
                        project_id=ctx.project.id,
                        engagement_id=ctx.engs[c].id,
                        meeting_type=MeetingType.contractor_hse,
                        title=f"{c} weekly HSE meeting",
                        planned_date=pd,
                        held_date=held,
                        invited_count=inv,
                        attended_count=inv - rng.randint(0, 3) if held else None,
                        seed_fake=True,
                    )
                )
    ctx.db.add_all(rows)
    ctx.db.flush()


# ---- entry point ---------------------------------------------------------------------------------


def _ctx(db: Session, project: Project, rng: random.Random) -> Ctx:
    sites = {s.code: s for s in db.scalars(select(Site).where(Site.project_id == project.id))}
    zones = {z.code: z for z in db.scalars(select(Zone).where(Zone.project_id == project.id))}
    engs = {
        c.short_code: e
        for e, c in db.execute(
            select(ProjectEngagement, Contractor)
            .join(Contractor, Contractor.id == ProjectEngagement.contractor_id)
            .where(ProjectEngagement.project_id == project.id)
            .order_by(ProjectEngagement.tier)
        ).all()
    }
    users = {u.email.split("@")[0]: u for u in db.scalars(select(User))}
    ctx = Ctx(db, rng, project, sites, zones, engs, users)
    ctx.sites_by_id = {s.id: s for s in sites.values()}
    return ctx


def already_seeded(db: Session) -> bool:
    return (
        db.scalar(select(WorkforceReturn.id).where(WorkforceReturn.seed_fake.is_(True)).limit(1))
        is not None
    )


def seed_data(db: Session) -> None:
    """Volume data for both projects (skipped when seed rows already exist)."""
    if already_seeded(db):
        return
    rng = random.Random(20260930)
    person_seq = 0  # person IDs are unique across projects
    for code in ("ANIA-EXP", "RBT-52"):
        project = db.scalar(select(Project).where(Project.code == code))
        if project is None:
            continue
        ctx = _ctx(db, project, rng)
        ctx.person_seq = person_seq
        months = _months(project.start_date, SEED_END)
        tbt = {m: v[11] for m, v in A3.items()} if code == "ANIA-EXP" else {}
        seed_workforce(ctx, months, tbt)
        invs = seed_incidents(ctx, months)
        seed_observations(ctx, months)
        seed_inspections(ctx, months)
        seed_cas(ctx, months, {v.incident_id: v for v in invs})
        seed_meetings(ctx, months)
        person_seq = ctx.person_seq
    db.flush()
