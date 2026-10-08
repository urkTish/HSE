"""Phase 5 seed (spec 5-training Appendix A; every row `seed_fake`).

Runs on top of the Phase 0-4 world, idempotently (skipped when a training provider exists).
Rows are written directly with the values the services would compute (§6.1 validity, §6.3
minutes, TR-14 certificates). The bulk is generated from the built population so that the
requirement engine reproduces A.9 / TR7 at as_of 2026-09-30; the generator verifies the result
and raises when a count is off.

Deviations (DECISIONS #105-#110):
- TRS-ANIA-EXP-2026-00031 is held on 2026-09-29 (Imran Hussain was on LTI 09-09…09-28) and
  closed the same day 16:30 by Faisal: Imran's WAH runs 2026-09-29 → 2028-09-28 and his WAH
  gap is 09-01…09-28 (TR1a/TR2a dates move; TR9 unchanged).
- §6.2 is applied literally (exempt, met, due, gap): supervisors and the HSE staff member who
  already hold a qualifying record are `met` (counted) although A.9 shows them `due`. K-82
  numerators/denominators therefore read ANIA-EXP 10,830 / 11,023 and RBT-52 2,104 / 2,164;
  every displayed value of TR7 is unchanged.
- Extra trainer authorisations (TA-ANIA-EXP-0002/0004, TA-RBT-52-0003/0004) authorise the
  trainers of the generated September sessions.
"""

from __future__ import annotations

import itertools
import math
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.access_enums import (
    DeploymentStatus,
    HookKind,
    QrKind,
    QrTokenStatus,
    WorkerIdType,
    WorkerLanguage,
    WorkerPersonType,
    WorkerStatus,
)
from app.core.cert_enums import VerificationStatus
from app.core.clock import set_now
from app.core.enums import Role
from app.core.hse_enums import Trade
from app.core.text import search_blob
from app.core.train_enums import (
    AttendanceResult,
    CourseCategory,
    DeliveryMode,
    MatrixAppliesTo,
    MatrixLevel,
    NominationStatus,
    PracticalResult,
    RequirementState,
    SessionStatus,
    TrainerAuthorisationStatus,
    TrainingProviderKind,
    TrainingProviderStatus,
    TrainingRecordSource,
    TrainingRecordStatus,
    TrainingStatusReason,
    TrainingVerificationMethod,
    TrainingVerificationOutcome,
    UnderstoodLanguage,
)
from app.kpi.periods import add_months
from app.models import (
    Contractor,
    Deployment,
    HseSettings,
    PermitCrew,
    Project,
    ProjectEngagement,
    PtwAppointment,
    QrToken,
    Site,
    TrainerAuthorisation,
    TrainingCourse,
    TrainingNomination,
    TrainingProvider,
    TrainingProviderAccreditation,
    TrainingRecord,
    TrainingSession,
    TrainingVerification,
    User,
    WapCrew,
    Worker,
    WorkforceReturn,
    Zone,
)
from app.schemas.training_matrix import MatrixLineCreate, MatrixRequirement
from app.services.access import common as acommon
from app.services.cert import policy as cpolicy
from app.services.train import common as tcommon
from app.services.train import hook as thook
from app.services.train import matrix as tmatrix
from app.services.train import requirements as treq
from app.services.train import validity as tval

RIYADH = ZoneInfo("Asia/Riyadh")
KPI_DAY = date(2026, 9, 30)
SEP1 = date(2026, 9, 1)
REG_DAY = date(2026, 10, 1)
CLOCK_DAY = date(2026, 10, 6)
A = MatrixAppliesTo
RS = RequirementState
TRS = TrainingRecordStatus
D = DeliveryMode


def at(y: int, m: int, d: int, h: int = 9, mi: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=RIYADH).astimezone(UTC)


def at_d(d: date, h: int = 9, mi: int = 0) -> datetime:
    return at(d.year, d.month, d.day, h, mi)


SEED_CLOCK = at(2026, 10, 6, 10)

# ---- expected values (TR7 / A.9 with the §6.2 literal deviation) -------------------------------

EXPECTED: dict[str, dict[str, Any]] = {
    "ANIA-EXP": {
        "counted": 11_023,
        "met": 10_830,
        "gap": 193,
        "workers": 3_412,
        "workers_gap": 171,
        "hook_gaps": 34,
        "k85": 64,
        "k88": 41,
        "gaps": {
            "IND-GENERAL": 41,
            "HEAT-AWR": 54,
            "WAH": 12,
            "LOTO": 4,
            "ELEC-QUALIFIED": 9,
            "SCAFF-AWR": 54,
            "BANKSMAN-AWR": 1,
            "FIRE-WARDEN": 2,
            "FIRST-AID": 3,
            "AVSEC-AWR": 9,
            "H2S-AWR": 4,
        },
    },
    "RBT-52": {
        "counted": 2_164,
        "met": 2_104,
        "gap": 60,
        "workers": 654,
        "workers_gap": 54,
        "hook_gaps": 10,
        "k85": 15,
        "k88": 12,
        "gaps": {
            "IND-GENERAL": 14,
            "HEAT-AWR": 18,
            "WAH": 5,
            "LOTO": 2,
            "ELEC-QUALIFIED": 3,
            "SCAFF-AWR": 14,
            "FIRE-WARDEN": 1,
            "FIRST-AID": 1,
            "H2S-AWR": 2,
        },
    },
}
# K-85 expiring (unbooked unless listed in BOOKED_K85)
K85 = {
    "ANIA-EXP": {"FIRE-WATCH": 7, "HEAT-AWR": 20, "SCAFF-AWR": 13, "AVSEC-AWR": 5, "WAH": 5,
                 "FIRST-AID": 3, "FIRE-WARDEN": 3, "H2S-AWR": 2, "LOTO": 2, "BANKSMAN-AWR": 2},
    "RBT-52": {"WAH": 8, "HEAT-AWR": 4, "SCAFF-AWR": 2, "FIRE-WARDEN": 1},
}  # fmt: skip
# September sessions per project: course → (contractor attendances, failures)
SEP_SESSIONS = {
    "ANIA-EXP": {
        "AVSEC-AWR": (52, 1), "AIRSIDE-DRV": (14, 0), "LOTO": (32, 2), "ELEC-QUALIFIED": (16, 1),
        "FIRE-WATCH": (24, 1), "GAS-TEST": (20, 2), "PTW-RECEIVER": (30, 1),
        "FIRE-WARDEN": (40, 1), "FIRST-AID": (15, 1), "WAH": (120, 5), "CSE-ENTRANT": (48, 3),
        "CSE-ATTENDANT": (49, 3), "HEAT-AWR": (272, 10), "SCAFF-AWR": (640, 25),
        "BANKSMAN-AWR": (20, 0), "H2S-AWR": (20, 0),
    },
    "RBT-52": {
        "HEAT-AWR": (48, 2), "SCAFF-AWR": (127, 6), "H2S-AWR": (10, 1), "WAH": (48, 2),
        "GAS-TEST": (12, 1), "ELEC-QUALIFIED": (4, 0), "FIRST-AID": (5, 0),
        "FIRE-WARDEN": (3, 0),
    },
}  # fmt: skip
STAFF_ATTEND = {
    "WKR-000011": ["CSE-ENTRANT", "CSE-ATTENDANT", "FIRST-AID", "LOTO", "H2S-AWR", "FIRE-WARDEN",
                   "BANKSMAN-AWR"],
    "WKR-000024": ["WAH", "CSE-ENTRANT", "CSE-ATTENDANT", "GAS-TEST", "FIRE-WATCH", "LOTO",
                   "H2S-AWR", "FIRE-WARDEN"],
    "WKR-000025": ["FIRST-AID", "GAS-TEST"],
}  # fmt: skip
BULK_ROLES = {  # matrix roles / zones (total holders incl. named)
    "ANIA-EXP": {"fire_watch": 30, "fire_warden": 64, "first_aider": 96, "zone:Z-MSCP": 85},
    "RBT-52": {"fire_watch": 12, "fire_warden": 16, "first_aider": 20, "zone:Z-B4": 40},
}


# ---- providers (A.2) ---------------------------------------------------------------------------

PROVIDERS: list[dict[str, Any]] = [
    {"code": "INT-HSE", "en": "Project HSE Training (client/PMC)", "ar": "تدريب السلامة بالمشروع",
     "kind": TrainingProviderKind.internal},
    {"code": "RAWABI-TU", "en": "Rawabi Training Unit", "ar": "وحدة التدريب – روابي",
     "kind": TrainingProviderKind.contractor_internal, "contractor": "RAWABI"},
    {"code": "QIMMA-TU", "en": "Qimma Training Unit", "ar": "وحدة التدريب – قمة",
     "kind": TrainingProviderKind.contractor_internal, "contractor": "QIMMA"},
    {"code": "ASTA", "en": "Airport Security Training Academy (test)",
     "ar": "أكاديمية أمن المطارات للتدريب (تجريبي)", "kind": TrainingProviderKind.external,
     "portal": "https://verify.asta-test.example", "domains": ["verify.asta-test.example",
     "asta-test.example"], "cr": "1010000301",
     "acc": [("gaca_avsec", "GACA-AVSEC-TEST-031", ["AVSEC-AWR"], date(2027, 12, 31), True),
             ("airport_operator", "AOP-TEST-0007", ["AIRSIDE-DRV", "AIRSIDE-RTF"],
              date(2027, 12, 31), True)]},
    {"code": "HAYAT", "en": "Al-Hayat Lifesaving Training Centre (test)",
     "ar": "مركز الحياة للتدريب على الإسعاف (تجريبي)", "kind": TrainingProviderKind.external,
     "portal": "https://verify.hayat-test.example", "email": "cards@hayat-test.example",
     "domains": ["verify.hayat-test.example", "hayat-test.example"], "cr": "1010000302",
     "contact": "Mona Al-Saeed (fake)",
     "acc": [("srca", "SRCA-TC-TEST-114", ["FIRST-AID", "FIRST-AID-R"], date(2027, 6, 30), True),
             ("aha", "AHA-TC-TEST-2281", ["FIRST-AID", "FIRST-AID-R"], date(2027, 6, 30),
              True)]},
    {"code": "GSA", "en": "Gulf Safety Academy (test)", "ar": "أكاديمية الخليج للسلامة (تجريبي)",
     "kind": TrainingProviderKind.external, "domains": ["gsa-test.example"], "cr": "1010000303",
     "acc": [("nebosh", "NEB-LP-TEST-5521", ["NEBOSH-IGC", "NEBOSH-ICC", "NEBOSH-DIP"],
              date(2027, 9, 30), True),
             ("iosh", "IOSH-TP-TEST-0904", ["IOSH-MS", "IOSH-MS-R"], date(2027, 9, 30), True)]},
    {"code": "OTCME", "en": "OSHA Training Center Middle East (test)",
     "ar": "مركز تدريب OSHA الشرق الأوسط (تجريبي)", "kind": TrainingProviderKind.external,
     "email": "cards@otcme-test.example", "domains": ["otcme-test.example"], "cr": "1010000304",
     "acc": [("osha_otc", "OTC-TEST-77", ["OSHA-30"], date(2027, 3, 31), True)]},
    {"code": "QUICKTRAIN", "en": "QuickTrain Safety Courses (test)",
     "ar": "كويك ترين لدورات السلامة (تجريبي)", "kind": TrainingProviderKind.external,
     "email": "info@quicktrain-test.example", "domains": ["quicktrain-test.example"],
     "cr": "1010000305", "status": TrainingProviderStatus.suspended,
     "reason": "First-aid cards not traceable with SRCA",
     "acc": [("srca", "SRCA-TC-TEST-990", ["FIRST-AID"], date(2027, 1, 31), False)]},
]  # fmt: skip

# ---- A.8 conversions ---------------------------------------------------------------------------

CONVERT = [
    (26, "ramesh.kumar", "NAJD", "ANIA-EXP", "Ramesh Kumar", "راميش كومار"),
    (27, "joseph.mathew", "QIMMA", "RBT-52", "Joseph Mathew", "جوزيف ماثيو"),
    (28, "sanjay.verma", "GULFPAVE", "ANIA-EXP", "Sanjay Verma", "سانجاي فيرما"),
    (29, "faris.anazi", "RAWABI", "ANIA-EXP", "Faris Al-Anazi", "فارس العنزي"),
    (30, "nasser.shahrani", "RAWABI", "ANIA-EXP", "Nasser Al-Shahrani", "ناصر الشهراني"),
    (31, "ibrahim.saleh", "QIMMA", "RBT-52", "Ibrahim Al-Saleh", "إبراهيم الصالح"),
    (32, "yousef.ghamdi", "QIMMA", "RBT-52", "Yousef Al-Ghamdi", "يوسف الغامدي"),
]
STAFF = [
    (24, "khalid.otaibi", "ANIA-EXP", "Khalid Al-Otaibi", "خالد العتيبي", "1000001024"),
    (25, "majed.shammari", "RBT-52", "Majed Al-Shammari", "ماجد الشمري", "1000001025"),
]

# ---- A.5 named records: (worker, course, provider, completed, source, cert_no, printed) ---------

IMP = TrainingRecordSource.import_
EXT = TrainingRecordSource.external_certificate
NAMED: list[tuple[str, str, str, date, TrainingRecordSource, str | None, date | None]] = [
    ("WKR-000002", "AVSEC-AWR", "ASTA", date(2025, 10, 13), EXT, "AVS-TEST-25-1013", None),
    ("WKR-000002", "AIRSIDE-DRV", "ASTA", date(2026, 1, 25), EXT, "ADT-TEST-26-0125", None),
    ("WKR-000002", "AIRSIDE-RTF", "ASTA", date(2026, 1, 26), EXT, "RTF-TEST-26-0126", None),
    ("WKR-000002", "HEAT-AWR", "INT-HSE", date(2026, 5, 20), IMP, None, None),
    ("WKR-000005", "IOSH-MS", "GSA", date(2025, 2, 10), EXT, "IOSH-TEST-25-0210", None),
    ("WKR-000005", "FIRE-WARDEN", "INT-HSE", date(2025, 6, 1), IMP, None, None),
    ("WKR-000007", "AVSEC-AWR", "ASTA", date(2026, 3, 2), EXT, "AVS-TEST-26-0302", None),
    ("WKR-000009", "WAH", "INT-HSE", date(2025, 7, 14), IMP, None, None),
    ("WKR-000011", "NEBOSH-IGC", "GSA", date(2019, 5, 15), EXT, "NEB-TEST-19-0515", None),
    ("WKR-000011", "WAH", "INT-HSE", date(2026, 2, 1), IMP, None, None),
    ("WKR-000011", "FIRE-WATCH", "INT-HSE", date(2026, 2, 3), IMP, None, None),
    ("WKR-000011", "PTW-ISSUER", "INT-HSE", date(2025, 9, 1), IMP, None, None),
    ("WKR-000011", "AVSEC-AWR", "ASTA", date(2026, 1, 20), EXT, "AVS-TEST-26-0120", None),
    ("WKR-000013", "OSHA-30", "OTCME", date(2024, 6, 20), EXT, "OSHA-TEST-24-0620", None),
    ("WKR-000013", "AVSEC-AWR", "ASTA", date(2026, 5, 12), EXT, "AVS-TEST-26-0512", None),
    ("WKR-000015", "FIRE-WATCH", "INT-HSE", date(2024, 10, 11), IMP, None, None),
    ("WKR-000016", "CSE-ENTRANT", "INT-HSE", date(2025, 12, 8), IMP, None, None),
    ("WKR-000016", "H2S-AWR", "INT-HSE", date(2026, 2, 15), IMP, None, None),
    ("WKR-000018", "GAS-TEST", "INT-HSE", date(2026, 4, 15), IMP, None, None),
    ("WKR-000018", "CSE-ENTRANT", "INT-HSE", date(2025, 3, 10), IMP, None, None),
    ("WKR-000018", "CSE-ATTENDANT", "INT-HSE", date(2025, 3, 11), IMP, None, None),
    ("WKR-000018", "H2S-AWR", "INT-HSE", date(2026, 2, 15), IMP, None, None),
    ("WKR-000018", "HEAT-AWR", "INT-HSE", date(2026, 4, 1), IMP, None, None),
    ("WKR-000018", "NEBOSH-ICC", "GSA", date(2022, 11, 30), EXT, "NEB-TEST-22-1130", None),
    (
        "WKR-000018",
        "FIRST-AID",
        "HAYAT",
        date(2025, 7, 1),
        EXT,
        "HY-FA-TEST-25-0701",
        date(2027, 6, 30),
    ),
    ("WKR-000019", "AVSEC-AWR", "ASTA", date(2026, 2, 20), EXT, "AVS-TEST-26-0220", None),
    ("WKR-000021", "CSE-RESCUE", "INT-HSE", date(2025, 11, 3), IMP, None, None),
    ("WKR-000021", "FIRST-AID", "HAYAT", date(2024, 11, 16), EXT, "HY-FA-TEST-24-1116", None),
    ("WKR-000021", "NEBOSH-IGC", "GSA", date(2023, 4, 10), EXT, "NEB-TEST-23-0410", None),
    ("WKR-000024", "PTW-ISSUER", "INT-HSE", date(2025, 12, 1), IMP, None, None),
    ("WKR-000025", "PTW-ISSUER", "INT-HSE", date(2024, 10, 26), IMP, None, None),
    ("WKR-000026", "PTW-RECEIVER", "INT-HSE", date(2025, 11, 20), IMP, None, None),
    ("WKR-000027", "PTW-RECEIVER", "INT-HSE", date(2026, 2, 8), IMP, None, None),
    ("WKR-000029", "PTW-RECEIVER", "INT-HSE", date(2026, 1, 12), IMP, None, None),
    ("WKR-000030", "LOTO-AUTHORITY", "INT-HSE", date(2025, 8, 18), IMP, None, None),
    ("WKR-000031", "LOTO-AUTHORITY", "INT-HSE", date(2026, 1, 5), IMP, None, None),
    ("WKR-000032", "HEAT-AWR", "INT-HSE", date(2026, 4, 10), IMP, None, None),
    ("WKR-000032", "NEBOSH-IGC", "GSA", date(2021, 3, 1), EXT, "NEB-TEST-21-0301", None),
    ("WKR-000032", "FIRST-AID", "HAYAT", date(2025, 10, 20), EXT, "HY-FA-TEST-25-1020", None),
    ("WKR-000101", "WAH", "INT-HSE", date(2026, 4, 22), IMP, None, None),
    ("WKR-000101", "SCAFF-AWR", "QIMMA-TU", date(2026, 4, 23), IMP, None, None),
    ("WKR-000103", "LOTO", "INT-HSE", date(2024, 9, 30), IMP, None, None),
    ("WKR-000105", "WAH", "INT-HSE", date(2025, 3, 2), IMP, None, None),
    ("WKR-000105", "IOSH-MS", "GSA", date(2024, 5, 5), EXT, "IOSH-TEST-24-0505", None),
    ("WKR-000107", "FIRE-WATCH", "INT-HSE", date(2026, 3, 15), IMP, None, None),
    ("WKR-000108", "WAH", "INT-HSE", date(2025, 6, 2), IMP, None, None),
    # trainers' own records (TA-3) for the extra authorisations
    ("WKR-000007", "LOTO", "INT-HSE", date(2025, 5, 6), IMP, None, None),
    ("WKR-000007", "ELEC-QUALIFIED", "INT-HSE", date(2025, 5, 8), IMP, None, None),
    ("WKR-000007", "FIRE-WARDEN", "INT-HSE", date(2025, 6, 2), IMP, None, None),
    ("WKR-000007", "SCAFF-AWR", "INT-HSE", date(2025, 6, 3), IMP, None, None),
    ("WKR-000007", "BANKSMAN-AWR", "INT-HSE", date(2025, 6, 4), IMP, None, None),
    ("WKR-000005", "HEAT-AWR", "INT-HSE", date(2026, 3, 22), IMP, None, None),
    ("WKR-000005", "SCAFF-AWR", "INT-HSE", date(2025, 6, 3), IMP, None, None),
    ("WKR-000005", "BANKSMAN-AWR", "INT-HSE", date(2025, 6, 4), IMP, None, None),
]

# trainer authorisations: (project, seq, trainer, provider, courses, roles, from, to, by)
TAS = [
    ("ANIA-EXP", 1, "user:noura.qahtani", "INT-HSE", ["WAH", "PTW-RECEIVER", "FIRE-WATCH"],
     date(2026, 3, 1), date(2028, 2, 29), "faisal.harbi",
     "Train-the-trainer course TTT-TEST-0011; NEBOSH IGC; 8 years HSE supervision"),
    ("ANIA-EXP", 2, "WKR-000005", "RAWABI-TU", ["HEAT-AWR", "SCAFF-AWR", "BANKSMAN-AWR"],
     date(2026, 4, 1), date(2027, 3, 31), "noura.qahtani",
     "IOSH Managing Safely; 10 years site supervision; trainer course TTT-TEST-0031"),
    ("ANIA-EXP", 3, "WKR-000018", "INT-HSE",
     ["HEAT-AWR", "H2S-AWR", "CSE-ENTRANT", "CSE-ATTENDANT", "GAS-TEST"],
     date(2026, 4, 1), date(2027, 3, 31), "noura.qahtani",
     "Train-the-trainer course TTT-TEST-0042; NEBOSH ICC; 6 years CSE supervision"),
    ("ANIA-EXP", 4, "WKR-000007", "INT-HSE",
     ["LOTO", "ELEC-QUALIFIED", "FIRE-WARDEN", "SCAFF-AWR", "BANKSMAN-AWR"],
     date(2026, 4, 1), date(2027, 3, 31), "noura.qahtani",
     "Electrical engineer; NFPA 70E instructor course TTT-TEST-0057; 7 years site work"),
    ("RBT-52", 1, "WKR-000105", "INT-HSE", ["WAH"], date(2026, 3, 15), date(2027, 3, 14),
     "lina.haddad", "Fall protection competent person; trainer course TTT-TEST-0063"),
    ("RBT-52", 2, "user:yousef.ghamdi", "QIMMA-TU", ["HEAT-AWR"], date(2026, 6, 1),
     date(2027, 5, 31), "lina.haddad", "NEBOSH IGC; Qimma HSE representative for 5 years"),
    ("RBT-52", 3, "WKR-000018", "INT-HSE", ["GAS-TEST", "H2S-AWR", "HEAT-AWR"],
     date(2026, 4, 1), date(2027, 3, 31), "lina.haddad",
     "Train-the-trainer course TTT-TEST-0042; NEBOSH ICC; 6 years CSE supervision"),
    ("RBT-52", 4, "WKR-000007", "INT-HSE",
     ["LOTO", "ELEC-QUALIFIED", "FIRE-WARDEN", "SCAFF-AWR"], date(2026, 4, 1),
     date(2027, 3, 31), "lina.haddad",
     "Electrical engineer; NFPA 70E instructor course TTT-TEST-0057; 7 years site work"),
]  # fmt: skip

# trainer of the generated sessions: course → (provider, trainer key, closer)
TRAINER = {
    "ANIA-EXP": {
        "AVSEC-AWR": ("ASTA", "ext:M. Al-Ghamdi"), "AIRSIDE-DRV": ("ASTA", "ext:K. Al-Harbi"),
        "FIRST-AID": ("HAYAT", "ext:S. Al-Qahtani"), "WAH": ("INT-HSE", "user:noura.qahtani"),
        "FIRE-WATCH": ("INT-HSE", "user:noura.qahtani"),
        "PTW-RECEIVER": ("INT-HSE", "user:noura.qahtani"),
        "HEAT-AWR": ("RAWABI-TU", "WKR-000005"), "SCAFF-AWR": ("RAWABI-TU", "WKR-000005"),
        "BANKSMAN-AWR": ("RAWABI-TU", "WKR-000005"), "H2S-AWR": ("INT-HSE", "WKR-000018"),
        "CSE-ENTRANT": ("INT-HSE", "WKR-000018"), "CSE-ATTENDANT": ("INT-HSE", "WKR-000018"),
        "GAS-TEST": ("INT-HSE", "WKR-000018"), "LOTO": ("INT-HSE", "WKR-000007"),
        "ELEC-QUALIFIED": ("INT-HSE", "WKR-000007"), "FIRE-WARDEN": ("INT-HSE", "WKR-000007"),
    },
    "RBT-52": {
        "HEAT-AWR": ("QIMMA-TU", "user:yousef.ghamdi"), "SCAFF-AWR": ("INT-HSE", "WKR-000007"),
        "H2S-AWR": ("INT-HSE", "WKR-000018"), "WAH": ("INT-HSE", "WKR-000105"),
        "GAS-TEST": ("INT-HSE", "WKR-000018"), "ELEC-QUALIFIED": ("INT-HSE", "WKR-000007"),
        "FIRST-AID": ("HAYAT", "ext:S. Al-Qahtani"), "FIRE-WARDEN": ("INT-HSE", "WKR-000007"),
    },
}  # fmt: skip

# day shapes by hours per day: (start, end, break)
SHAPES = {
    90: (time(6, 0), time(7, 45), 15),
    120: (time(7, 0), time(9, 15), 15),
    180: (time(8, 0), time(11, 15), 15),
    240: (time(8, 0), time(12, 15), 15),
    480: (time(7, 0), time(16, 0), 60),
}


def net(day: dict[str, Any]) -> int:
    s = time.fromisoformat(day["start_time"])
    e = time.fromisoformat(day["end_time"])
    return (e.hour * 60 + e.minute) - (s.hour * 60 + s.minute) - int(day["break_minutes"])


def mkday(d: date, minutes: int) -> dict[str, Any]:
    s, e, b = SHAPES[minutes]
    return {"date": d.isoformat(), "start_time": s.strftime("%H:%M"),
            "end_time": e.strftime("%H:%M"), "break_minutes": b}  # fmt: skip


def session_days(course: TrainingCourse, first: date) -> list[dict[str, Any]]:
    total = int((course.min_duration_hours or Decimal(1)) * 60)
    out = []
    d = first
    while total > 0:
        m = min(total, 480)
        out.append(mkday(d, m))
        total -= m
        d += timedelta(days=1)
        while d.weekday() in (4, 5):
            d += timedelta(days=1)
    return out


# ---- context -----------------------------------------------------------------------------------


@dataclass
class PlanP:
    """Per-project generation state."""

    pcode: str
    pid: uuid.UUID
    deps: dict[uuid.UUID, Deployment] = field(default_factory=dict)  # worker → live deployment
    need: dict[str, set[uuid.UUID]] = field(default_factory=lambda: defaultdict(set))
    due: dict[str, set[uuid.UUID]] = field(default_factory=lambda: defaultdict(set))
    gaps: dict[str, set[uuid.UUID]] = field(default_factory=lambda: defaultdict(set))
    k85: dict[str, set[uuid.UUID]] = field(default_factory=lambda: defaultdict(set))
    used_gap: set[uuid.UUID] = field(default_factory=set)
    idle: set[uuid.UUID] = field(default_factory=set)  # workers of engagements with no Sep work


_SEQ: dict[uuid.UUID, int] = {}


def wk(x: uuid.UUID) -> tuple[int, str]:
    """Deterministic worker order (seq, not the random uuid) so the generated world does not
    depend on the ids of the underlying template."""
    return (_SEQ.get(x, 1 << 60), str(x))


class Ctx:
    def __init__(self, db: Session) -> None:
        self.db = db
        _SEQ.clear()
        _SEQ.update(dict(db.execute(select(Worker.id, Worker.seq)).all()))
        self.rng = random.Random(20261008)  # noqa: S311
        self.tmp_seq = itertools.count(1)
        self.projects = {p.code: p for p in db.scalars(select(Project))}
        code_of = {p.id: p.code for p in self.projects.values()}
        self.sites = {(code_of[s.project_id], s.code): s for s in db.scalars(select(Site))}
        self.zones = {z.code: z for z in db.scalars(select(Zone))}
        self.engs: dict[tuple[str, str], ProjectEngagement] = {}
        self.eng_contractor: dict[uuid.UUID, str] = {}
        for e, c in db.execute(
            select(ProjectEngagement, Contractor).join(
                Contractor, Contractor.id == ProjectEngagement.contractor_id
            )
        ):
            self.engs[(code_of[e.project_id], c.short_code)] = e
            self.eng_contractor[e.id] = c.short_code
        self.contractors = {c.short_code: c for c in db.scalars(select(Contractor))}
        self.users = {u.email.split("@")[0]: u for u in db.scalars(select(User))}
        self.workers = {w.worker_no: w for w in db.scalars(select(Worker).where(Worker.seq < 1000))}
        self.providers: dict[str, TrainingProvider] = {}
        self.records: list[TrainingRecord] = []
        self.verifs: list[TrainingVerification] = []
        self.has: dict[tuple[uuid.UUID, str], TrainingRecord] = {}
        self.cert_n: dict[str, int] = defaultdict(int)
        self.imp_n: dict[str, int] = defaultdict(int)
        self.sessions: list[TrainingSession] = []
        self.session_n: dict[str, set[int]] = defaultdict(set)
        self.reserved_cert: dict[str, set[int]] = {"ANIA-EXP": {402}}

    def pid(self, code: str) -> uuid.UUID:
        return self.projects[code].id

    def uid(self, key: str) -> uuid.UUID | None:
        u = self.users.get(key)
        return u.id if u else None

    @property
    def faisal(self) -> uuid.UUID | None:
        return self.uid("faisal.harbi")

    def officer(self, pcode: str) -> uuid.UUID | None:
        return self.uid("noura.qahtani" if pcode == "ANIA-EXP" else "lina.haddad")

    def rep(self, pcode: str) -> uuid.UUID | None:
        return self.uid("ahmed.zahrani" if pcode == "ANIA-EXP" else "yousef.ghamdi")

    def worker(self, no: str) -> Worker:
        return self.workers[no]


def already_seeded(db: Session) -> bool:
    return db.scalar(select(TrainingProvider.id).limit(1)) is not None


# ---- setup -------------------------------------------------------------------------------------


def _seed_setup(ctx: Ctx) -> None:
    db = ctx.db
    tcommon.ensure_catalogue(db)
    for p in ctx.projects.values():
        tcommon.settings(db, p.id).updated_by_user_id = None
        hs = db.get(HseSettings, p.id)
        if hs is not None:
            hs.training_register_from = SEP1
    for spec in PROVIDERS:
        status = spec.get("status", TrainingProviderStatus.approved)
        pv = TrainingProvider(
            id=uuid.uuid4(),
            provider_code=spec["code"],
            legal_name_en=spec["en"],
            legal_name_ar=spec["ar"],
            name_norm_en=acommon_norm(spec["en"]),
            name_norm_ar=acommon_norm(spec["ar"]),
            kind=spec["kind"],
            contractor_id=ctx.contractors[spec["contractor"]].id if "contractor" in spec else None,
            country="SA" if spec["kind"] == TrainingProviderKind.external else None,
            cr_number=spec.get("cr"),
            verification_portal_url=spec.get("portal"),
            verification_domains=list(spec.get("domains", [])),
            verification_email=spec.get("email"),
            contact_name=spec.get("contact"),
            status=status,
            status_reason=spec.get("reason"),
            suspension_periods=[{"from": "2026-09-22", "to": None}]
            if status == TrainingProviderStatus.suspended
            else [],
            submitted_by_user_id=ctx.uid("noura.qahtani"),
            approved_by_user_id=ctx.faisal,
            approved_at=at(2026, 8, 20, 11),
            created_by_user_id=ctx.uid("noura.qahtani"),
            seed_fake=True,
            created_at=at(2026, 8, 18, 10),
            updated_at=at(2026, 9, 22, 12) if status != TrainingProviderStatus.approved
            else at(2026, 8, 20, 11),
        )  # fmt: skip
        db.add(pv)
        ctx.providers[pv.provider_code] = pv
        for body, no, scope, until, checked in spec.get("acc", []):
            db.add(
                TrainingProviderAccreditation(
                    id=uuid.uuid4(),
                    provider_id=pv.id,
                    accreditation_body=body,
                    accreditation_no=no,
                    scope_course_codes=scope,
                    valid_from=date(2024, 1, 1),
                    valid_until=until,
                    register_checked_at=at(2026, 8, 20, 10) if checked else None,
                    register_checked_by_user_id=ctx.uid("noura.qahtani") if checked else None,
                    register_check_note=None if checked else "Not found on the SRCA register",
                    alerts_sent=[],
                    seed_fake=True,
                    created_at=at(2026, 8, 18, 10),
                    updated_at=at(2026, 8, 20, 10),
                )
            )
    db.flush()
    thook.clear_cache(db)


def acommon_norm(s: str) -> str:
    from app.core.text import normalize  # noqa: PLC0415

    return normalize(s)


def _seed_policy(ctx: Ctx) -> None:
    from app.services import audit  # noqa: PLC0415

    db = ctx.db
    u = db.get(User, ctx.faisal) if ctx.faisal else None
    actor = audit.AuditActor(user_id=u.id, role=Role.hse_manager) if u else audit.SYSTEM
    for p in ctx.projects.values():
        sts = cpolicy.enable_project(
            db, p.id, REG_DAY, actor, seed=True, kinds=(HookKind.training_course,)
        )
        for st in sts:
            st.created_by_user_id = ctx.faisal
            st.created_at = at(2026, 10, 1, 9)
            st.updated_at = at(2026, 10, 1, 9)
    db.flush()
    cpolicy.clear_cache(db)


# ---- A.8 workers -------------------------------------------------------------------------------


def _protected(db: Session) -> set[uuid.UUID]:
    ids: set[uuid.UUID] = set(db.scalars(select(Worker.id).where(Worker.seq < 1000)))
    ids |= set(db.scalars(select(PermitCrew.worker_id)))
    ids |= set(db.scalars(select(WapCrew.worker_id)))
    ids |= {x for x in db.scalars(select(PtwAppointment.holder_worker_id)) if x is not None}
    return ids


def _live(d: Deployment, day: date = KPI_DAY) -> bool:
    return (
        d.status == DeploymentStatus.mobilised
        and d.mobilised_on <= day
        and (d.demobilised_on is None or d.demobilised_on > day)
    )


def _set_id(w: Worker, it: WorkerIdType, number: str, nat: str | None) -> None:
    n = acommon.check_id(it, number, None)
    w.id_type = it
    w.id_number_enc = crypto.encrypt(n)
    w.id_number_bidx = acommon.blind_index(it, n, None)
    w.id_number_masked = acommon.mask_worker_id(it, n)
    w.nationality = nat


def _seed_workers(ctx: Ctx) -> None:
    db = ctx.db
    protected = _protected(db)
    for seq, ukey, contractor, pcode, en, ar in CONVERT:
        no = f"WKR-{seq:06d}"
        if no in ctx.workers:
            continue
        eng = ctx.engs[(pcode, contractor)]
        cand = db.execute(
            select(Worker, Deployment)
            .join(Deployment, Deployment.worker_id == Worker.id)
            .where(Worker.seq >= 1000, Deployment.engagement_id == eng.id)
            .order_by(Worker.seq)
        ).all()
        for w, d in cand:
            if w.id in protected or not _live(d, date(2026, 8, 31)):
                continue
            w.seq = seq
            w.worker_no = no
            w.full_name_en = en
            w.full_name_ar = ar
            _set_id(w, WorkerIdType.iqama, f"20000010{seq:02d}", w.nationality or "IN")
            w.user_id = ctx.uid(ukey)
            w.search_text = search_blob(no, en, ar)
            ctx.workers[no] = w
            protected.add(w.id)
            break
        else:
            raise RuntimeError(f"no bulk worker to convert into {no}")
    noura = ctx.workers["WKR-000011"]
    for seq, ukey, pcode, en, ar, nid in STAFF:
        no = f"WKR-{seq:06d}"
        if no in ctx.workers:
            continue
        w = Worker(
            id=uuid.uuid4(),
            seq=seq,
            worker_no=no,
            person_type=WorkerPersonType.client_pmc_staff,
            full_name_en=en,
            full_name_ar=ar,
            adult_attestation=True,
            primary_language=WorkerLanguage.ar,
            user_id=ctx.uid(ukey),
            status=WorkerStatus.active,
            search_text=search_blob(no, en, ar),
            created_by_user_id=ctx.officer(pcode),
            seed_fake=True,
            created_at=at(2025, 3, 1, 9),
            updated_at=at(2025, 3, 1, 9),
        )
        _set_id(w, WorkerIdType.national_id, nid, "SA")
        db.add(w)
        db.flush()
        sites = [s.id for (pc, _c), s in ctx.sites.items() if pc == pcode]
        db.add(
            Deployment(
                id=uuid.uuid4(),
                worker_id=w.id,
                project_id=ctx.pid(pcode),
                engagement_id=None,
                trade=Trade.engineer,
                site_ids=sites,
                mobilised_on=date(2025, 3, 3),
                status=DeploymentStatus.mobilised,
                inducted_on=date(2025, 3, 3),
                created_by_user_id=ctx.officer(pcode),
                seed_fake=True,
                created_at=at(2025, 3, 1, 9),
                updated_at=at(2025, 3, 3, 9),
            )
        )
        ctx.workers[no] = w
    _ = noura
    db.flush()


# ---- authorisations ----------------------------------------------------------------------------


def _trainer_ids(ctx: Ctx, key: str) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    if key.startswith("user:"):
        return ctx.uid(key[5:]), None
    return None, ctx.workers[key].id


def _seed_tas(ctx: Ctx) -> None:
    db = ctx.db
    for pcode, seq, trainer, prov, courses, vf, vt, by, basis in TAS:
        uid, wid = _trainer_ids(ctx, trainer)
        db.add(
            TrainerAuthorisation(
                id=uuid.uuid4(),
                project_id=ctx.pid(pcode),
                seq=seq,
                authorisation_no=f"TA-{pcode}-{seq:04d}",
                trainer_user_id=uid,
                trainer_worker_id=wid,
                provider_id=ctx.providers[prov].id,
                course_codes=courses,
                roles=["trainer"] if prov == "QIMMA-TU" else ["trainer", "assessor"],
                basis=basis,
                evidence_attachment_ids=[],
                valid_from=vf,
                valid_to=vt,
                status=TrainerAuthorisationStatus.active,
                suspension_periods=[],
                authorised_by_user_id=ctx.uid(by),
                authorised_at=at_d(vf, 9),
                created_by_user_id=ctx.uid(by),
                seed_fake=True,
                created_at=at_d(vf, 9),
                updated_at=at_d(vf, 9),
            )
        )
    db.flush()


# ---- matrix (A.4) and profiles -----------------------------------------------------------------

MANUAL_LINES: list[tuple[A, list[str], str | None, list[str] | None, int]] = [
    (A.all_workers, [], "IND-GENERAL", None, 0),
    (A.all_workers, [], "HEAT-AWR", None, 7),
    (A.trade, ["scaffolder", "steel_erector", "rigger"], "WAH", None, 0),
    (A.trade, ["electrician"], "LOTO", None, 0),
    (A.trade, ["electrician"], "ELEC-QUALIFIED", None, 0),
    (A.trade, ["labourer", "carpenter", "mason", "painter", "steel_fixer"], "SCAFF-AWR", None, 14),
    (A.trade, ["flagman"], "BANKSMAN-AWR", None, 7),
    (A.matrix_role, ["fire_watch"], "FIRE-WATCH", None, 0),
    (A.trade, ["supervisor"], None, ["NEBOSH-IGC", "NEBOSH-ICC", "IOSH-MS", "OSHA-30"], 90),
    (A.trade, ["hse_staff"], None, ["NEBOSH-IGC", "NEBOSH-ICC", "NEBOSH-DIP"], 0),
    (A.trade, ["hse_staff"], "FIRST-AID", None, 30),
    (A.matrix_role, ["fire_warden"], "FIRE-WARDEN", None, 14),
    (A.matrix_role, ["first_aider"], "FIRST-AID", None, 0),
]
H2S_ZONE = {"ANIA-EXP": "Z-MSCP", "RBT-52": "Z-B4"}


def _seed_matrix(ctx: Ctx) -> None:
    db = ctx.db
    for pcode, p in ctx.projects.items():
        if pcode not in H2S_ZONE:
            continue
        set_now(at(2026, 9, 1, 8))
        lines = [*MANUAL_LINES, (A.zone, [str(ctx.zones[H2S_ZONE[pcode]].id)], "H2S-AWR", None, 0)]
        for kind, vals, code, any_of, due in lines:
            body = MatrixLineCreate(
                applies_to_kind=kind,
                applies_to_values=vals,
                requirement=MatrixRequirement(course_code=code, any_of=any_of),
                level=MatrixLevel.mandatory,
                due_within_days=due,
            )
            tmatrix.create_line(db, None, p.id, body, effective_from=SEP1, seed=True)
        tmatrix.sync_hook_lines(db, p.id, on=SEP1, seed=True)
    from app.models import TrainingMatrixLine  # noqa: PLC0415

    for r in db.scalars(select(TrainingMatrixLine)):
        r.created_by_user_id = ctx.faisal
        r.created_at = at(2026, 9, 1, 8)
    db.flush()


NAMED_PROFILES = [
    ("WKR-000005", "ANIA-EXP", ["fire_warden"], []),
    ("WKR-000021", "ANIA-EXP", ["first_aider"], ["Z-MSCP"]),
    ("WKR-000008", "ANIA-EXP", ["first_aider"], []),
    ("WKR-000015", "ANIA-EXP", ["fire_watch"], []),
    ("WKR-000107", "RBT-52", ["fire_watch"], []),
    ("WKR-000016", "ANIA-EXP", [], ["Z-MSCP"]),
    ("WKR-000017", "ANIA-EXP", [], ["Z-MSCP"]),
]


def _profile(ctx: Ctx, dep: Deployment, roles: list[str], zones: list[uuid.UUID]) -> None:
    pr = tmatrix.set_profile(ctx.db, None, dep, roles or None, zones or None, on=date(2026, 8, 20),
                             seed=True)  # fmt: skip
    by = str(ctx.officer("ANIA-EXP" if dep.project_id == ctx.pid("ANIA-EXP") else "RBT-52"))
    pr.history = [{**h, "by": by} for h in pr.history]
    pr.created_by_user_id = uuid.UUID(by)
    pr.created_at = at(2026, 8, 20, 9)


def _dep_of(ctx: Ctx, no: str, pcode: str) -> Deployment:
    dep = tcommon.deployment(ctx.db, ctx.workers[no].id, ctx.pid(pcode))
    assert dep is not None, no  # noqa: S101
    return dep


# ---- records -----------------------------------------------------------------------------------


def _course(ctx: Ctx, code: str) -> TrainingCourse:
    c = tcommon.course(ctx.db, code)
    assert c is not None, code  # noqa: S101
    return c


def record(
    ctx: Ctx,
    w: Worker,
    code: str,
    provider: str,
    completed: date,
    source: TrainingRecordSource,
    cert_no: str | None = None,
    printed: date | None = None,
    pcode: str | None = None,
    session: TrainingSession | None = None,
    reviewed: datetime | None = None,
    hours: Decimal | None = None,
    sponsored: bool = False,
    theory: Decimal | None = None,
) -> TrainingRecord:
    c = _course(ctx, code)
    pv = ctx.providers[provider]
    vu, lf = tval.stored_validity(c, completed, printed)
    if cert_no is None:
        ctx.imp_n[provider] += 1
        cert_no = f"{provider}-REG-{ctx.imp_n[provider]:06d}"
    rev = reviewed or at_d(min(completed + timedelta(days=3), date(2026, 8, 31)), 10)
    if completed > date(2026, 8, 31) and reviewed is None:
        rev = at_d(completed + timedelta(days=1), 10)
    pid = ctx.pid(pcode) if pcode else None
    dep = tcommon.deployment(ctx.db, w.id, pid) if pid else None
    r = TrainingRecord(
        id=uuid.uuid4(),
        seq=0,
        record_no="",
        worker_id=w.id,
        course_code=code,
        source=source,
        provider_id=pv.id,
        session_id=session.id if session else None,
        project_id=pid,
        engagement_id=dep.engagement_id if dep else None,
        certificate_no=cert_no,
        completed_on=completed,
        printed_expiry=printed,
        valid_until=vu,
        limiting_factor=lf,
        theory_score_pct=theory,
        practical_result=PracticalResult.pass_ if c.practical_required else None,
        hours=hours,
        project_sponsored=sponsored,
        sponsoring_project_id=pid if sponsored else None,
        name_as_printed=w.full_name_en if source != TrainingRecordSource.session else None,
        status=TRS.accepted,
        verification_status=VerificationStatus.verified,
        submitted_by_user_id=ctx.officer(pcode or "ANIA-EXP"),
        submitted_at=rev - timedelta(hours=2),
        reviewed_by_user_id=ctx.faisal if source == TrainingRecordSource.session
        else ctx.officer(pcode or "ANIA-EXP"),
        reviewed_at=rev,
        verified_at=rev,
        in_force_from=rev,
        alerts_sent=[],
        seed_fake=True,
        created_at=rev - timedelta(hours=2),
        updated_at=rev,
    )  # fmt: skip
    if source == TrainingRecordSource.external_certificate and code not in ("NEBOSH-IGC",):
        r.provider_verification_url = None
    ctx.records.append(r)
    method = {
        TrainingRecordSource.session: TrainingVerificationMethod.session_record,
        TrainingRecordSource.import_: TrainingVerificationMethod.provider_register_file,
        TrainingRecordSource.external_certificate: TrainingVerificationMethod.awarding_body_portal
        if c.category == CourseCategory.professional_qualification
        else TrainingVerificationMethod.provider_portal,
    }[source]
    ctx.verifs.append(
        TrainingVerification(
            id=uuid.uuid4(),
            record_id=r.id,
            project_id=pid,
            provider_id=pv.id,
            method=method,
            channel_used=pv.verification_portal_url or (pv.verification_domains or ["internal"])[0],
            outcome=TrainingVerificationOutcome.confirmed,
            differences=[],
            reference=f"REG-{cert_no}"[:100],
            performed_by_user_id=None if source == TrainingRecordSource.session
            else ctx.officer(pcode or "ANIA-EXP"),
            performed_at=rev,
            counts_as_verification=True,
            verification_status_after=VerificationStatus.verified,
            created_at=rev,
            seed_fake=True,
        )
    )  # fmt: skip
    r.seq = 900_000 + next(ctx.tmp_seq)
    r.record_no = f"TMP-{r.seq:07d}"
    ctx.db.add(r)
    ctx.db.add(ctx.verifs[-1])
    ctx.has[(w.id, code)] = r
    for t in c.satisfies or []:
        ctx.has.setdefault((w.id, t), r)
    return r


def _seed_named_records(ctx: Ctx) -> None:
    for no, code, prov, done, src, cert, printed in NAMED:
        w = ctx.workers[no]
        pcode = "RBT-52" if no in ("WKR-000025", "WKR-000027", "WKR-000031", "WKR-000032") or (
            w.seq >= 101 and w.seq < 200) else "ANIA-EXP"  # fmt: skip
        record(ctx, w, code, prov, done, src, cert, printed, pcode)
    # Waleed Saleh's QUICKTRAIN card: Rejected verification_failed (A.5, A.7)
    w = ctx.workers["WKR-000008"]
    pv = ctx.providers["QUICKTRAIN"]
    c = _course(ctx, "FIRST-AID")
    vu, lf = tval.stored_validity(c, date(2026, 9, 12), None)
    r = TrainingRecord(
        id=uuid.uuid4(),
        seq=0,
        record_no="",
        worker_id=w.id,
        course_code="FIRST-AID",
        source=EXT,
        provider_id=pv.id,
        project_id=ctx.pid("ANIA-EXP"),
        engagement_id=_dep_of(ctx, "WKR-000008", "ANIA-EXP").engagement_id,
        certificate_no="QT-FA-TEST-26-0912",
        completed_on=date(2026, 9, 12),
        valid_until=vu,
        limiting_factor=lf,
        practical_result=PracticalResult.pass_,
        name_as_printed="Waleed Saleh",
        status=TRS.rejected,
        status_reason=TrainingStatusReason.verification_failed,
        status_changed_at=at(2026, 9, 21, 11),
        verification_status=VerificationStatus.failed,
        verification_due_on=date(2026, 9, 22),
        submitted_by_user_id=ctx.uid("ahmed.zahrani"),
        submitted_at=at(2026, 9, 19, 10),
        alerts_sent=[],
        seed_fake=True,
        created_at=at(2026, 9, 19, 9),
        updated_at=at(2026, 9, 21, 11),
    )
    r.seq = 900_000 + next(ctx.tmp_seq)
    r.record_no = f"TMP-{r.seq:07d}"
    ctx.records.append(r)
    ctx.db.add(r)
    ctx.verifs.append(
        TrainingVerification(
            id=uuid.uuid4(),
            record_id=r.id,
            project_id=ctx.pid("ANIA-EXP"),
            provider_id=pv.id,
            method=TrainingVerificationMethod.awarding_body_portal,
            channel_used="srca.gov.sa (SRCA register)",
            outcome=TrainingVerificationOutcome.not_found,
            differences=[],
            reference="SRCA-LOOKUP-TEST-0921",
            performed_by_user_id=ctx.uid("noura.qahtani"),
            performed_at=at(2026, 9, 21, 11),
            counts_as_verification=True,
            verification_status_after=VerificationStatus.failed,
            created_at=at(2026, 9, 21, 11),
            seed_fake=True,
        )
    )
    ctx.db.add(ctx.verifs[-1])


# ---- sessions ----------------------------------------------------------------------------------


def _free_no(ctx: Ctx, pcode: str, reserved: set[int]) -> int:
    n = 1
    while n in ctx.session_n[pcode] or n in reserved:
        n += 1
    ctx.session_n[pcode].add(n)
    return n


RESERVED = {"ANIA-EXP": {31, 57, 58, 59, 60, 61}, "RBT-52": {19, 22, 23}}


def _understood(w: Worker, lang: str, interp: list[str]) -> UnderstoodLanguage:
    pl = w.primary_language.value
    if pl == lang:
        return UnderstoodLanguage.session_language
    if pl in interp:
        return UnderstoodLanguage.interpreter
    return UnderstoodLanguage.none


@dataclass
class Att:
    w: Worker
    passed: bool
    theory: Decimal | None = None
    nominated_at: datetime | None = None


def session(
    ctx: Ctx,
    pcode: str,
    no: int | None,
    code: str,
    provider: str,
    trainer: str,
    days: list[dict[str, Any]],
    attendees: list[Att],
    status: SessionStatus,
    lang: str = "en",
    interp: list[str] | None = None,
    closed_at: datetime | None = None,
    closer: str | None = None,
    scheduled_at: datetime | None = None,
    capacity: int | None = None,
    cert_no: int | None = None,
) -> TrainingSession:
    db = ctx.db
    c = _course(ctx, code)
    pid = ctx.pid(pcode)
    if no is None:
        no = _free_no(ctx, pcode, RESERVED[pcode])
    else:
        ctx.session_n[pcode].add(no)
    first = date.fromisoformat(days[0]["date"])
    last = date.fromisoformat(days[-1]["date"])
    uid, wid = (None, None) if trainer.startswith("ext:") else _trainer_ids(ctx, trainer)
    tr = {
        "user_id": str(uid) if uid else None,
        "worker_id": str(wid) if wid else None,
        "external_name": trainer[4:] if trainer.startswith("ext:") else None,
        "roles": ["trainer"] if provider == "QIMMA-TU" else ["trainer", "assessor"],
        "authorisation_id": None,
    }
    if interp is None:
        langs = sorted({a.w.primary_language.value for a in attendees} - {lang})
        interp = langs
    s0 = time.fromisoformat(days[0]["start_time"])
    e1 = time.fromisoformat(days[-1]["end_time"])
    sched = scheduled_at or at_d(first - timedelta(days=7), 10)
    site = next(s for (pc, _c), s in ctx.sites.items() if pc == pcode)
    s = TrainingSession(
        id=uuid.uuid4(),
        project_id=pid,
        year=first.year,
        seq=no,
        session_no=f"TRS-{pcode}-{first.year}-{no:05d}",
        course_code=code,
        provider_id=ctx.providers[provider].id,
        delivery_mode=D.classroom if not c.practical_required else D.blended,
        trainers=[tr],
        trainer_user_ids=[uid] if uid else [],
        trainer_worker_ids=[wid] if wid else [],
        site_id=site.id,
        offsite_text="Training room T3",
        language=WorkerLanguage(lang),
        interpreter_languages=interp,
        days=days,
        first_day=first,
        last_day=last,
        starts_at=at_d(first, s0.hour, s0.minute),
        ends_at=at_d(last, e1.hour, e1.minute),
        net_minutes_total=sum(net(d) for d in days),
        capacity=capacity or max(len(attendees), 1),
        status=status,
        scheduled_at=sched,
        delivered_at=at_d(last, e1.hour, e1.minute)
        if status in (SessionStatus.delivered, SessionStatus.closed) else None,
        closed_by_user_id=ctx.uid(closer) if closer else None,
        closed_at=closed_at,
        alerts_sent=[],
        created_by_user_id=ctx.officer(pcode),
        seed_fake=True,
        created_at=sched - timedelta(hours=1),
        updated_at=closed_at or sched,
    )  # fmt: skip
    db.add(s)
    ctx.sessions.append(s)
    closed = status == SessionStatus.closed
    started = status in (SessionStatus.in_progress, SessionStatus.delivered, SessionStatus.closed)
    for a in attendees:
        dep = tcommon.deployment(db, a.w.id, pid)
        minutes = {str(i + 1): net(d) for i, d in enumerate(days)} if closed else {}
        if started and not closed:
            minutes = {"1": net(days[0])} if status != SessionStatus.in_progress else {}
        theory = a.theory
        if closed and c.theory_required and theory is None:
            theory = Decimal(ctx.rng.randint(81, 97)) if a.passed else Decimal(72)
        n = TrainingNomination(
            id=uuid.uuid4(),
            session_id=s.id,
            worker_id=a.w.id,
            deployment_id=dep.id if dep else None,
            engagement_id=dep.engagement_id if dep else None,
            contractor_worker=a.w.person_type == WorkerPersonType.contractor_worker,
            nominated_by_user_id=ctx.officer(pcode),
            nominated_at=a.nominated_at or sched + timedelta(hours=1),
            status=NominationStatus.attended if closed else NominationStatus.nominated,
            minutes_by_day=minutes,
            understood_language=_understood(a.w, lang, interp),
            theory_score_pct=theory if closed else None,
            practical_result=(PracticalResult.pass_ if a.passed or c.theory_required
                              else PracticalResult.fail)
            if closed and c.practical_required else None,
            attempt_no=1,
            result=(AttendanceResult.passed if a.passed else AttendanceResult.failed)
            if closed else AttendanceResult.pending,
            seed_fake=True,
            created_at=a.nominated_at or sched + timedelta(hours=1),
            updated_at=closed_at or sched,
        )  # fmt: skip
        db.add(n)
        if closed and a.passed:
            assert closed_at is not None  # noqa: S101
            if cert_no is not None and a is attendees[0]:
                k = cert_no
            else:
                ctx.cert_n[pcode] += 1
                while ctx.cert_n[pcode] in ctx.reserved_cert.get(pcode, set()):
                    ctx.cert_n[pcode] += 1
                k = ctx.cert_n[pcode]
            hours = Decimal(sum(minutes.values())) / Decimal(60)
            r = record(ctx, a.w, code, provider, last, TrainingRecordSource.session,
                       f"TRC-{pcode}-{last.year}-{k:05d}", None, pcode, s, closed_at,
                       hours.quantize(Decimal("0.01")), theory=theory)  # fmt: skip
            r.reviewed_by_user_id = ctx.uid(closer) if closer else None
            r.submitted_by_user_id = None
            n.record_id = r.id
    return s


# ---- planning ----------------------------------------------------------------------------------


def _plan(ctx: Ctx, pcode: str) -> PlanP:
    db = ctx.db
    thook.clear_cache(db)
    pl = PlanP(pcode, ctx.pid(pcode))
    ev = treq.evaluate_project(db, pl.pid, KPI_DAY)
    for dep in ev.f.deps:
        w = ev.f.workers.get(dep.worker_id)
        if w is not None and w.person_type == WorkerPersonType.contractor_worker:
            pl.deps[dep.worker_id] = dep
    working = set(
        db.scalars(
            select(WorkforceReturn.engagement_id).where(
                WorkforceReturn.project_id == pl.pid,
                WorkforceReturn.work_date >= SEP1,
                WorkforceReturn.work_date <= KPI_DAY,
                WorkforceReturn.no_work.is_(False),
            )
        )
    )
    pl.idle = {w for w, d in pl.deps.items() if d.engagement_id not in working}
    for r in ev.reqs:
        if not r.kpi_counted or r.level != MatrixLevel.mandatory:
            continue
        if r.dep.worker_id not in pl.deps:
            continue
        if r.state == RS.due:
            pl.due[r.key].add(r.dep.worker_id)
        elif r.state == RS.gap:
            pl.need[r.key].add(r.dep.worker_id)
    return pl


def _pick(ctx: Ctx, pool: list[uuid.UUID], n: int, what: str, sort: bool = True) -> list[uuid.UUID]:
    pool = sorted(pool, key=wk) if sort else list(pool)
    if len(pool) < n:
        raise RuntimeError(f"seed_train: only {len(pool)} candidates for {what} (need {n})")
    return ctx.rng.sample(pool, n)


def _choose_gaps(ctx: Ctx, pl: PlanP, protected: set[uuid.UUID]) -> None:
    exp = EXPECTED[pl.pcode]["gaps"]
    ind = set(pl.need.get("IND-GENERAL", set()))
    if len(ind) != exp["IND-GENERAL"]:
        raise RuntimeError(f"{pl.pcode}: IND-GENERAL gaps {len(ind)} ≠ {exp['IND-GENERAL']}")
    pl.gaps["IND-GENERAL"] = ind
    used = set(ind)
    # named designated gaps
    if pl.pcode == "ANIA-EXP":
        pl.gaps["FIRST-AID"].add(ctx.workers["WKR-000008"].id)
    else:
        pl.gaps["ELEC-QUALIFIED"].add(ctx.workers["WKR-000103"].id)
    used |= set().union(*pl.gaps.values())

    def free(code: str, extra: set[uuid.UUID] | None = None) -> list[uuid.UUID]:
        return [
            w for w in pl.need.get(code, set())
            if w not in protected and w not in used and (extra is None or w in extra)
            and pl.deps[w].mobilised_on <= date(2026, 9, 10)
        ]  # fmt: skip

    # HEAT ∩ IND
    overlap = 18 if pl.pcode == "ANIA-EXP" else 4
    heat_ind = [w for w in ind if w in pl.need.get("HEAT-AWR", set())]
    pl.gaps["HEAT-AWR"] |= set(_pick(ctx, heat_ind, overlap, "HEAT∩IND"))
    rest = exp["HEAT-AWR"] - overlap
    pl.gaps["HEAT-AWR"] |= set(_pick(ctx, free("HEAT-AWR"), rest, "HEAT"))
    used |= pl.gaps["HEAT-AWR"]
    # ELEC ⊇ LOTO
    n_elec = exp["ELEC-QUALIFIED"] - len(pl.gaps["ELEC-QUALIFIED"])
    elec = _pick(ctx, [w for w in free("ELEC-QUALIFIED") if w in pl.need.get("LOTO", set())],
                 n_elec, "ELEC")  # fmt: skip
    pl.gaps["ELEC-QUALIFIED"] |= set(elec)
    pl.gaps["LOTO"] |= set(elec[: exp["LOTO"]])
    used |= pl.gaps["ELEC-QUALIFIED"]
    for code, n in exp.items():
        if code in ("IND-GENERAL", "HEAT-AWR", "ELEC-QUALIFIED", "LOTO"):
            continue
        k = n - len(pl.gaps[code])
        pick = set(_pick(ctx, free(code), k, code))
        pl.gaps[code] |= pick
        used |= pick
    pl.used_gap = used


def _choose_k85(ctx: Ctx, pl: PlanP, protected: set[uuid.UUID]) -> None:
    taken: set[uuid.UUID] = set()
    for code, n in K85[pl.pcode].items():
        pool = [
            w for w in pl.need.get(code, set())
            if w not in protected and w not in pl.used_gap and w not in taken
            and pl.deps[w].mobilised_on <= date(2026, 8, 31)
        ]  # fmt: skip
        pick = set(_pick(ctx, pool, n, f"K-85 {code}"))
        pl.k85[code] = pick
        taken |= pick


def _expiring_record(ctx: Ctx, pl: PlanP, w: Worker, code: str) -> TrainingRecord:
    c = _course(ctx, code)
    vu = date(2026, 10, 14) + timedelta(days=ctx.rng.randint(0, 16))
    completed = add_months(vu + timedelta(days=1), -(c.validity_months or 12))
    prov = _default_provider(code)
    return record(ctx, w, code, prov, completed, IMP, pcode=pl.pcode)


def _default_provider(code: str) -> str:
    if code in ("AVSEC-AWR",):
        return "ASTA"
    if code in ("AIRSIDE-DRV", "AIRSIDE-RTF"):
        return "ASTA"
    if code in ("FIRST-AID", "FIRST-AID-R"):
        return "HAYAT"
    if code.startswith("NEBOSH") or code.startswith("IOSH"):
        return "GSA"
    if code == "OSHA-30":
        return "OTCME"
    return "INT-HSE"


def filler(ctx: Ctx, w: Worker, code: str, pcode: str) -> TrainingRecord:
    c = _course(ctx, code)
    months = c.validity_months
    lo = date(2025, 1, 10)
    if months is not None:
        lo = max(lo, add_months(date(2026, 11, 10), -months))
    hi = date(2026, 8, 25)
    completed = lo + timedelta(days=ctx.rng.randint(0, max((hi - lo).days, 0)))
    return record(ctx, w, code, _default_provider(code), completed, IMP, pcode=pcode)


# ---- September sessions ------------------------------------------------------------------------


def _work_days(month_start: date, month_end: date) -> list[date]:
    out = []
    d = month_start
    while d <= month_end:
        if d.weekday() not in (4, 5):
            out.append(d)
        d += timedelta(days=1)
    return out


def _sep_sessions(ctx: Ctx, pl: PlanP, protected: set[uuid.UUID], staff: dict[str, Worker]) -> None:
    db = ctx.db
    days = _work_days(date(2026, 9, 1), date(2026, 9, 29))
    for code, (n_att, n_fail) in SEP_SESSIONS[pl.pcode].items():
        c = _course(ctx, code)
        prov, trainer = TRAINER[pl.pcode][code]
        size = c.max_class_size or 12
        staff_here = [w for no, w in staff.items() if code in STAFF_ATTEND.get(no, [])
                      and tcommon.deployment(db, w.id, pl.pid) is not None]  # fmt: skip
        fixed: list[list[Att]] = []
        n_bulk = n_att
        # A.6 named closed sessions
        if pl.pcode == "ANIA-EXP" and code == "WAH":
            n_bulk -= 10
        n_sessions = max(1, math.ceil((n_bulk + len(staff_here)) / size))
        trainer_wid = None if trainer.startswith(("ext:", "user:")) else ctx.workers[trainer].id
        # candidates: need the code, not a designated gap / K-85, not protected
        needers = [
            w for w in pl.need.get(code, set())
            if w not in protected and w not in pl.gaps.get(code, set())
            and w not in pl.k85.get(code, set()) and (w, code) not in ctx.has
            and w != trainer_wid and w not in pl.idle
        ]  # fmt: skip
        needers.sort(key=wk)
        ctx.rng.shuffle(needers)
        needers.sort(key=lambda w: pl.deps[w].mobilised_on)
        fail_pool = [w for w in pl.gaps.get(code, set()) if w not in protected | pl.idle]
        fail_pool.sort(key=wk)
        ctx.rng.shuffle(fail_pool)
        n_fail_bulk = n_fail - 1 if (pl.pcode, code) == ("ANIA-EXP", "WAH") else n_fail
        fails = fail_pool[:n_fail_bulk]
        if len(fails) < n_fail_bulk:
            others = _non_needers(ctx, pl, code, protected, n_fail_bulk - len(fails))
            fails += others
        passes_n = n_bulk - n_fail_bulk
        passers = needers[:passes_n]
        if len(passers) < passes_n:
            passers += _non_needers(ctx, pl, code, protected, passes_n - len(passers),
                                    exclude=set(fails))  # fmt: skip
        people = [Att(ctx_w(ctx, w), True) for w in passers] + [
            Att(ctx_w(ctx, w), False) for w in fails
        ]
        # spread across sessions; each session gets a date ≥ every attendee's mobilisation
        people.sort(key=lambda a: pl.deps[a.w.id].mobilised_on if a.w.id in pl.deps else SEP1)
        chunks = [people[i::n_sessions] for i in range(n_sessions)]
        for i, sw in enumerate(staff_here):
            chunks[i % n_sessions].append(Att(sw, True))
        fixed = chunks
        for k, chunk in enumerate(fixed):
            if not chunk:
                continue
            latest = max(
                (pl.deps[a.w.id].mobilised_on for a in chunk if a.w.id in pl.deps), default=SEP1
            )
            cands = [d for d in days if d >= max(latest, SEP1)]
            n_days = math.ceil(float(c.min_duration_hours or 1) / 8)
            cands = [d for d in cands if d <= date(2026, 9, 29) - timedelta(days=n_days)] or cands
            pos = (k * 7 + len(code)) % len(cands)
            first = cands[pos]
            sdays = session_days(c, first)
            last = date.fromisoformat(sdays[-1]["date"])
            if last > date(2026, 9, 30):
                first = cands[0]
                sdays = session_days(c, first)
                last = date.fromisoformat(sdays[-1]["date"])
            noura_in = trainer == "user:noura.qahtani" or any(
                a.w.worker_no == "WKR-000011" for a in chunk
            )
            closer = "lina.haddad" if pl.pcode == "RBT-52" else (
                "faisal.harbi" if noura_in else "noura.qahtani")  # fmt: skip
            lang = "ar" if prov in ("ASTA", "HAYAT") else "en"
            session(ctx, pl.pcode, None, code, prov, trainer, sdays, chunk, SessionStatus.closed,
                    lang=lang, closed_at=at_d(last, 17), closer=closer,
                    capacity=max(len(chunk), 1))  # fmt: skip


def ctx_w(ctx: Ctx, wid: uuid.UUID) -> Worker:
    w = ctx.db.get(Worker, wid)
    assert w is not None  # noqa: S101
    return w


def _non_needers(
    ctx: Ctx,
    pl: PlanP,
    code: str,
    protected: set[uuid.UUID],
    n: int,
    exclude: set[uuid.UUID] | None = None,
) -> list[uuid.UUID]:
    """Workers for whom the code is not a counted / due requirement and who hold no record of
    it: a record (or a failure) changes no KPI."""
    c = _course(ctx, code)
    # a record of `code` meets requirements for code and for every code it satisfies (CC-6)
    sat = set(tcommon.satisfiers(ctx.db, code)) | set(c.satisfies or [])
    blocked: set[uuid.UUID] = set()
    for key in list(pl.need) + list(pl.due):
        if set(key.removeprefix("any:").split(",")) & ({code} | sat):
            blocked |= pl.need.get(key, set()) | pl.due.get(key, set())
    blocked |= {w for w in pl.deps for t in [code, *(c.satisfies or [])]
                if (w, t) in ctx.has}  # fmt: skip
    pool = [
        w for w in pl.deps
        if w not in protected and w not in blocked and w not in (exclude or set())
        and w not in pl.idle
        and (w, code) not in ctx.has and pl.deps[w].mobilised_on <= date(2026, 8, 31)
    ]  # fmt: skip
    return _pick(ctx, pool, n, f"non-needers {code}")


def _a6_sessions(ctx: Ctx, protected: set[uuid.UUID], plans: dict[str, PlanP]) -> None:
    db = ctx.db
    ania, rbt = plans["ANIA-EXP"], plans["RBT-52"]
    # Imran's August HEAT-AWR (RAWABI-TU)
    imran = ctx.workers["WKR-000001"]
    hc = _course(ctx, "HEAT-AWR")
    session(ctx, "ANIA-EXP", None, "HEAT-AWR", "RAWABI-TU", "WKR-000005",
            session_days(hc, date(2026, 8, 27)), [Att(imran, True)], SessionStatus.closed,
            lang="en", closed_at=at(2026, 8, 27, 12), closer="noura.qahtani",
            capacity=30)  # fmt: skip
    # 00031 WAH (moved to 2026-09-29, DECISIONS #105): Imran + 9 NAJD/SAHARA bulk, 1 failed
    najd = {ctx.engs[("ANIA-EXP", "NAJD")].id, ctx.engs[("ANIA-EXP", "SAHARA")].id}
    wah_need = [
        w for w in ania.need.get("WAH", set())
        if w not in protected and ania.deps[w].engagement_id in najd
        and w not in ania.k85.get("WAH", set())
    ]  # fmt: skip
    gap_wah = [w for w in ania.gaps["WAH"] if ania.deps[w].engagement_id in najd]
    if not gap_wah:
        raise RuntimeError("no NAJD/SAHARA WAH gap worker for 00031")
    failed = sorted(gap_wah, key=wk)[0]
    passers = _pick(ctx, [w for w in wah_need if w not in ania.gaps["WAH"]], 8, "00031")
    att = [Att(imran, True, Decimal("88.00"))] + [Att(ctx_w(ctx, w), True) for w in passers]
    att.append(Att(ctx_w(ctx, failed), False, Decimal("72.00")))
    wc = _course(ctx, "WAH")
    session(ctx, "ANIA-EXP", 31, "WAH", "INT-HSE", "user:noura.qahtani",
            session_days(wc, date(2026, 9, 29)), att, SessionStatus.closed, lang="en",
            interp=["ur", "hi"], closed_at=at(2026, 9, 29, 16, 30), closer="faisal.harbi",
            scheduled_at=at(2026, 9, 14, 10), capacity=10, cert_no=402)  # fmt: skip
    # RBT 00019 HEAT QIMMA-TU 24 QIMMA bulk (23 passed, 1 failed)
    qimma = ctx.engs[("RBT-52", "QIMMA")].id
    heat_need = [
        w for w in rbt.need.get("HEAT-AWR", set())
        if w not in protected and rbt.deps[w].engagement_id == qimma
        and w not in rbt.gaps["HEAT-AWR"] and w not in rbt.k85.get("HEAT-AWR", set())
        and rbt.deps[w].mobilised_on <= date(2026, 9, 14)
    ]  # fmt: skip
    hf = [w for w in rbt.gaps["HEAT-AWR"] if rbt.deps[w].mobilised_on <= date(2026, 9, 14)
          and rbt.deps[w].engagement_id == qimma]  # fmt: skip
    if not hf:
        raise RuntimeError("no QIMMA HEAT gap worker for 00019")
    att = [Att(ctx_w(ctx, w), True) for w in _pick(ctx, heat_need, 23, "00019")]
    att.append(Att(ctx_w(ctx, sorted(hf, key=wk)[0]), False))
    session(ctx, "RBT-52", 19, "HEAT-AWR", "QIMMA-TU", "user:yousef.ghamdi",
            [mkday(date(2026, 9, 14), 90)], att, SessionStatus.closed, lang="hi",
            interp=["ne", "bn"], closed_at=at(2026, 9, 15, 10), closer="lina.haddad",
            capacity=24)  # fmt: skip
    _ = db


def _booked_sessions(ctx: Ctx, protected: set[uuid.UUID], plans: dict[str, PlanP]) -> None:
    ania, rbt = plans["ANIA-EXP"], plans["RBT-52"]
    biju = ctx.workers["WKR-000017"]
    rawabi = ctx.engs[("ANIA-EXP", "RAWABI")].id
    # 00057 CSE-ATTENDANT 10-07: Biju + 9 RAWABI bulk
    pool = [w for w, d in ania.deps.items() if d.engagement_id == rawabi
            and w not in protected and (w, "CSE-ATTENDANT") not in ctx.has
            and d.mobilised_on <= date(2026, 8, 31)]  # fmt: skip
    att = [Att(biju, True, nominated_at=at(2026, 9, 28, 10))] + [
        Att(ctx_w(ctx, w), True, nominated_at=at(2026, 9, 28, 10))
        for w in _pick(ctx, pool, 9, "00057")
    ]
    session(ctx, "ANIA-EXP", 57, "CSE-ATTENDANT", "INT-HSE", "WKR-000018",
            [mkday(date(2026, 10, 7), 480)], att, SessionStatus.scheduled, lang="en",
            interp=["ur", "hi"], scheduled_at=at(2026, 9, 28, 9), capacity=10)  # fmt: skip
    # 00058 FIRE-WATCH 10-08: Ahmed Raza (nominated 09-15) + the 7 K-85 FIRE-WATCH holders
    ahmed = ctx.workers["WKR-000015"]
    att = [Att(ahmed, True, nominated_at=at(2026, 9, 15, 10))] + [
        Att(ctx_w(ctx, w), True, nominated_at=at(2026, 9, 15, 11))
        for w in sorted(ania.k85["FIRE-WATCH"], key=wk)
    ]
    session(ctx, "ANIA-EXP", 58, "FIRE-WATCH", "INT-HSE", "user:noura.qahtani",
            [{"date": "2026-10-08", "start_time": "07:00", "end_time": "12:00",
              "break_minutes": 30}], att, SessionStatus.scheduled, lang="ur", interp=["hi"],
            scheduled_at=at(2026, 9, 14, 9), capacity=8)  # fmt: skip
    # 00059 HEAT-AWR 10-11 (20 K-85 holders), 00060 SCAFF-AWR 10-12 (13 K-85 holders)
    booked = ((59, "HEAT-AWR", date(2026, 10, 11)), (60, "SCAFF-AWR", date(2026, 10, 12)))
    for no, code, d in booked:
        c = _course(ctx, code)
        att = [Att(ctx_w(ctx, w), True, nominated_at=at(2026, 9, 24, 10))
               for w in sorted(ania.k85[code], key=wk)]  # fmt: skip
        session(ctx, "ANIA-EXP", no, code, "RAWABI-TU", "WKR-000005", session_days(c, d), att,
                SessionStatus.scheduled, lang="en", scheduled_at=at(2026, 9, 24, 9),
                capacity=30)  # fmt: skip
    # 00061 AVSEC-AWR 10-15 (ASTA): Rajesh (nominated 10-02) + 11 GULFPAVE bulk
    rajesh = ctx.workers["WKR-000002"]
    gp = ctx.engs[("ANIA-EXP", "GULFPAVE")].id
    pool = [w for w, d in ania.deps.items() if d.engagement_id == gp and w not in protected
            and w not in ania.k85.get("AVSEC-AWR", set())
            and d.mobilised_on <= date(2026, 8, 31)]  # fmt: skip
    att = [Att(rajesh, True, nominated_at=at(2026, 10, 2, 10))] + [
        Att(ctx_w(ctx, w), True, nominated_at=at(2026, 10, 2, 10))
        for w in _pick(ctx, pool, 11, "00061")
    ]
    session(ctx, "ANIA-EXP", 61, "AVSEC-AWR", "ASTA", "ext:M. Al-Ghamdi",
            [{"date": "2026-10-15", "start_time": "08:00", "end_time": "12:00",
              "break_minutes": 15}], att, SessionStatus.scheduled, lang="ar",
            interp=["en", "hi", "ur"], scheduled_at=at(2026, 10, 2, 9), capacity=12)  # fmt: skip
    # RBT 00022 WAH 10-06 (In Progress at the clock): the 8 K-85 WAH holders
    wc = _course(ctx, "WAH")
    att = [Att(ctx_w(ctx, w), True, nominated_at=at(2026, 9, 22, 10))
           for w in sorted(rbt.k85["WAH"], key=wk)]  # fmt: skip
    session(ctx, "RBT-52", 22, "WAH", "INT-HSE", "WKR-000105",
            session_days(wc, date(2026, 10, 6)), att, SessionStatus.in_progress, lang="ar",
            interp=["ur", "tl"], scheduled_at=at(2026, 9, 22, 9), capacity=8)  # fmt: skip
    # RBT 00023 HEAT-AWR 10-13: the 4 K-85 HEAT holders
    att = [Att(ctx_w(ctx, w), True, nominated_at=at(2026, 9, 27, 10))
           for w in sorted(rbt.k85["HEAT-AWR"], key=wk)]  # fmt: skip
    session(ctx, "RBT-52", 23, "HEAT-AWR", "QIMMA-TU", "user:yousef.ghamdi",
            [mkday(date(2026, 10, 13), 90)], att, SessionStatus.scheduled, lang="hi",
            scheduled_at=at(2026, 9, 27, 9), capacity=30)  # fmt: skip


# ---- profiles of the bulk ----------------------------------------------------------------------


def _seed_profiles(ctx: Ctx, protected: set[uuid.UUID]) -> None:
    db = ctx.db
    for no, pcode, roles, zones in NAMED_PROFILES:
        _profile(ctx, _dep_of(ctx, no, pcode), roles, [ctx.zones[z].id for z in zones])
    db.flush()
    for pcode, spec in BULK_ROLES.items():
        pid = ctx.pid(pcode)
        deps = [
            d for d in db.scalars(select(Deployment).where(Deployment.project_id == pid)
                                  .order_by(Deployment.id))
            if _live(d, date(2026, 8, 20)) and d.worker_id not in protected
        ]  # fmt: skip
        taken: set[uuid.UUID] = set()
        named_count: dict[str, int] = defaultdict(int)
        for _no, pc, roles, zones in NAMED_PROFILES:
            if pc != pcode:
                continue
            for r in roles:
                named_count[r] += 1
            for z in zones:
                named_count[f"zone:{z}"] += 1
        for key, total in spec.items():
            n = total - named_count[key]
            if key.startswith("zone:"):
                zn = ctx.zones[key[5:]]
                pool = [d for d in deps if zn.site_id in (d.site_ids or []) and d.id not in taken]
            else:
                pool = [d for d in deps if d.id not in taken]
            pool.sort(key=lambda d: wk(d.worker_id))
            pick = ctx.rng.sample(pool, n)
            for d in pick:
                taken.add(d.id)
                if key.startswith("zone:"):
                    _profile(ctx, d, [], [ctx.zones[key[5:]].id])
                else:
                    _profile(ctx, d, [key], [])
    db.flush()


# ---- enforcement at the clock ------------------------------------------------------------------


EXCEPTIONS = {("WKR-000017", "CSE-ATTENDANT"), ("WKR-000028", "PTW-RECEIVER")}


def _clock_fillers(ctx: Ctx, pcode: str) -> None:
    """Live permit crews, receivers and WAP crews hold what their hooks need at the clock, except
    Biju (standby, CSE-ATTENDANT) and Sanjay (receiver, PTW-RECEIVER)."""
    db = ctx.db
    pid = ctx.pid(pcode)
    f = treq.load(db, pid, CLOCK_DAY, mobilised_only=False, enforcement=True)
    by_id = {w.id: w for w in f.workers.values()}
    for dep in f.deps:
        if dep.status == DeploymentStatus.demobilised:
            continue
        keys = f.enforcement.get(dep.worker_id, {})
        if not keys:
            continue
        w = by_id[dep.worker_id]
        for ln in f.lines:
            if not ln.enforcement or not ln.row.hook_key:
                continue
            if not any(k in keys for k in ln.row.hook_key.split("|")):
                continue
            for code in ln.codes:
                if (w.worker_no, code) in EXCEPTIONS:
                    continue
                if any((w.id, s) in ctx.has for s in tcommon.satisfiers(db, code)):
                    continue
                filler(ctx, w, code, pcode)
    # WAP crews on airside zones need AVSEC-AWR (zone profiles)
    from app.core.access_enums import WapStatus  # noqa: PLC0415
    from app.models import Wap  # noqa: PLC0415

    for wc, wap in db.execute(
        select(WapCrew, Wap).join(Wap, Wap.id == WapCrew.wap_id).where(Wap.project_id == pid)
    ):
        if wap.status not in (WapStatus.active, WapStatus.approved):
            continue
        cw = db.get(Worker, wc.worker_id)
        if cw is None or any((cw.id, s) in ctx.has for s in tcommon.satisfiers(db, "AVSEC-AWR")):
            continue
        filler(ctx, cw, "AVSEC-AWR", pcode)


# ---- daily returns (A.1) -----------------------------------------------------------------------


def _align_daily_returns(ctx: Ctx) -> None:
    db = ctx.db
    hours: dict[tuple[uuid.UUID, date], Decimal] = defaultdict(Decimal)
    for n, s in db.execute(
        select(TrainingNomination, TrainingSession).join(
            TrainingSession, TrainingSession.id == TrainingNomination.session_id
        )
    ):
        if s.status != SessionStatus.closed or not n.contractor_worker or n.engagement_id is None:
            continue
        for i, day in enumerate(s.days):
            d = date.fromisoformat(day["date"])
            if SEP1 <= d <= KPI_DAY:
                m = int((n.minutes_by_day or {}).get(str(i + 1), 0))
                hours[(n.engagement_id, d)] += Decimal(m) / Decimal(60)
    for rec in ctx.records:
        r = rec
        if r.project_sponsored and r.engagement_id and SEP1 <= r.completed_on <= KPI_DAY:
            hours[(r.engagement_id, r.completed_on)] += r.hours or Decimal(0)
    pids = [ctx.pid(c) for c in ("ANIA-EXP", "RBT-52")]
    rows = list(
        db.scalars(
            select(WorkforceReturn).where(
                WorkforceReturn.project_id.in_(pids),
                WorkforceReturn.work_date >= SEP1,
                WorkforceReturn.work_date <= KPI_DAY,
            )
        )
    )
    by_eng: dict[uuid.UUID, list[WorkforceReturn]] = defaultdict(list)
    for wr in rows:
        wr.training_hours = Decimal(0)
        if not wr.no_work and wr.engagement_id is not None:
            by_eng[wr.engagement_id].append(wr)
    for (eid, d), h in sorted(hours.items(), key=lambda x: (str(x[0][0]), x[0][1])):
        cands = by_eng.get(eid, [])
        if not cands:
            raise RuntimeError(f"no September daily return for engagement {eid}")
        best = min(cands, key=lambda r: (abs((r.work_date - d).days), str(r.id)))
        best.training_hours = (best.training_hours or Decimal(0)) + h
    db.flush()


# ---- numbering, QR, alerts ---------------------------------------------------------------------


def _finalise_records(ctx: Ctx) -> None:
    db = ctx.db
    imran_wah = next(
        r for r in ctx.records
        if r.worker_id == ctx.workers["WKR-000001"].id and r.course_code == "WAH"
    )  # fmt: skip
    seq = 0
    others = [r for r in ctx.records if r is not imran_wah]
    others.sort(key=lambda r: (r.completed_on, r.created_at))
    for r in others:
        seq += 1
        if seq == 731:
            seq += 1
        r.seq = seq
        r.record_no = tcommon.record_no(seq)
    imran_wah.seq = 731
    imran_wah.record_no = tcommon.record_no(731)
    # alerts already sent before the clock (30/14/7/0, GP-5 suppression for booked_in_time)
    for r in ctx.records:
        if r.valid_until is None or r.status != TRS.accepted:
            continue
        sent = []
        for step in (30, 14, 7, 0):
            if r.valid_until - timedelta(days=step) <= CLOCK_DAY:
                sent.append(str(step))
        r.alerts_sent = sent
    db.flush()
    for r in ctx.records:
        if r.source == TrainingRecordSource.session:
            db.add(
                QrToken(
                    id=uuid.uuid4(),
                    token=acommon.new_qr_token(),
                    kind=QrKind.TR,
                    project_id=r.project_id,
                    subject_id=r.id,
                    printed_ref=r.certificate_no,
                    status=QrTokenStatus.active,
                    created_at=r.reviewed_at or SEED_CLOCK,
                )
            )
    db.flush()
    # Ahmed Raza booked in time (00058): the 14-day step (09-26) was suppressed (GP-5)
    ahmed = ctx.workers["WKR-000015"].id
    for r in ctx.records:
        if r.worker_id == ahmed and r.course_code == "FIRE-WATCH":
            r.alerts_sent = ["30", "14s", "7"]


# ---- verification ------------------------------------------------------------------------------


def verify(db: Session) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    from app.kpi import training as ktrain  # noqa: PLC0415

    for pcode in EXPECTED:
        pid = db.scalar(select(Project.id).where(Project.code == pcode))
        assert pid is not None  # noqa: S101
        res = ktrain.requirement_kpis(db, pid, KPI_DAY)
        out[pcode] = res
    return out


def check(db: Session) -> None:
    got = verify(db)
    errs = []
    for pcode, exp in EXPECTED.items():
        g = got[pcode]
        for k in ("counted", "met", "gap", "workers", "workers_gap", "hook_gaps", "k85", "k88"):
            if g[k] != exp[k]:
                errs.append(f"{pcode} {k}: {g[k]} ≠ {exp[k]}")
        for code, n in exp["gaps"].items():
            if g["gaps_by_code"].get(code, 0) != n:
                errs.append(f"{pcode} gaps {code}: {g['gaps_by_code'].get(code, 0)} ≠ {n}")
    if errs:
        raise RuntimeError("seed_train verification failed: " + "; ".join(errs))


# ---- entry point -------------------------------------------------------------------------------


def seed_train_data(db: Session, verify_kpis: bool = True) -> None:
    if already_seeded(db):
        return
    if db.scalar(select(Project.id).where(Project.code == "ANIA-EXP")) is None:
        return
    ctx = Ctx(db)
    try:
        set_now(at(2026, 9, 1, 8))
        _seed_setup(ctx)
        _seed_workers(ctx)
        _seed_tas(ctx)
        protected = _protected(db)
        set_now(at(2026, 10, 1, 9))
        _seed_policy(ctx)
        _seed_matrix(ctx)
        set_now(at(2026, 8, 20, 9))
        _seed_profiles(ctx, protected)
        set_now(SEED_CLOCK)
        _seed_named_records(ctx)
        _flush_records(ctx)
        plans = {pc: _plan(ctx, pc) for pc in ("ANIA-EXP", "RBT-52")}
        for pl in plans.values():
            _choose_gaps(ctx, pl, protected)
            _choose_k85(ctx, pl, protected)
            for code, ws in pl.k85.items():
                for w in sorted(ws, key=wk):
                    _expiring_record(ctx, pl, ctx_w(ctx, w), code)
        _a6_sessions(ctx, protected, plans)
        _booked_sessions(ctx, protected, plans)
        staff = {no: ctx.workers[no] for no in STAFF_ATTEND}
        for pl in plans.values():
            _sep_sessions(ctx, pl, protected, staff)
        # 3 sponsored external FIRST-AID (HAYAT, 16 h, completed 2026-09-24) on ANIA-EXP
        ania = plans["ANIA-EXP"]
        pool = [w for w in ania.need.get("FIRST-AID", set())
                if w not in protected and w not in ania.gaps["FIRST-AID"]
                and w not in ania.k85.get("FIRST-AID", set())
                and (w, "FIRST-AID") not in ctx.has]  # fmt: skip
        for i, w in enumerate(_pick(ctx, pool, 3, "sponsored FIRST-AID")):
            record(ctx, ctx_w(ctx, w), "FIRST-AID", "HAYAT", date(2026, 9, 24), EXT,
                   f"HY-FA-TEST-26-09{24 + i:02d}", None, "ANIA-EXP",
                   reviewed=at(2026, 9, 27, 10), hours=Decimal("16.00"),
                   sponsored=True)  # fmt: skip
        # 3 of the recent SCAFF-trade workers hold SCAFF-AWR from earlier work (A.9: 54 due)
        _recent_scaff(ctx, ania, protected)
        for pl in plans.values():
            _fill(ctx, pl)
        for pc in ("ANIA-EXP", "RBT-52"):
            _clock_fillers(ctx, pc)
        _finalise_records(ctx)
        _align_daily_returns(ctx)
        db.flush()
        thook.clear_cache(db)
        cpolicy.clear_cache(db)
        _refresh_permits(ctx)
        if verify_kpis:
            check(db)
    finally:
        set_now(None)


def _refresh_permits(ctx: Ctx) -> None:
    """Live / approved permits are re-evaluated at the seed clock now that training hooks are
    registered (crew eligibility shows TRAINING_* instead of HOOK_NOT_AVAILABLE)."""
    from app.core.ptw_enums import PERMIT_LIVE, PermitStatus  # noqa: PLC0415
    from app.models import Permit  # noqa: PLC0415
    from app.services.ptw import evaluation  # noqa: PLC0415

    set_now(SEED_CLOCK)
    db = ctx.db
    for p in db.scalars(
        select(Permit)
        .where(Permit.status.in_([*PERMIT_LIVE, PermitStatus.approved]))
        .order_by(Permit.permit_no)
    ):
        evaluation.refresh(db, p, run_simops=False)
    db.flush()


def _flush_records(ctx: Ctx) -> None:
    """Records are added as they are made (temporary numbers, renumbered in _finalise_records);
    flush so the planner's evaluation sees them."""
    ctx.db.flush()
    thook.clear_cache(ctx.db)


def _recent_scaff(ctx: Ctx, pl: PlanP, protected: set[uuid.UUID]) -> None:
    due = [w for w in pl.due.get("SCAFF-AWR", set()) if w not in protected]
    want = len(pl.due.get("SCAFF-AWR", set())) - 54
    if want <= 0:
        return
    for w in _pick(ctx, due, want, "recent SCAFF"):
        filler(ctx, ctx_w(ctx, w), "SCAFF-AWR", pl.pcode)


def _fill(ctx: Ctx, pl: PlanP) -> None:
    for key, ws in pl.need.items():
        codes = key.removeprefix("any:").split(",") if key.startswith("any:") else [key]
        for w in sorted(ws, key=wk):
            if w in pl.gaps.get(key, set()):
                continue
            if any((w, s) in ctx.has for c in codes for s in tcommon.satisfiers(ctx.db, c)):
                continue
            c0 = _course(ctx, codes[0])
            if c0.category == CourseCategory.induction_link:
                continue
            filler(ctx, ctx_w(ctx, w), codes[0], pl.pcode)


def main() -> int:  # pragma: no cover - CLI
    from app.db.session import get_sessionmaker  # noqa: PLC0415

    with get_sessionmaker()() as db:
        seed_train_data(db)
        db.commit()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
