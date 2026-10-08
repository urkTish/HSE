# ruff: noqa: E501
"""Phase 3 bulk history (3-ptw Appendix A.9; every row `seed_fake`).

June–September 2026 permits, shifts, suspensions, audits, SIMOPS conflicts and isolations are
written as rows (no service calls: they are terminal history) from a deterministic plan so that
every Y12 figure and its June–August history is reproduced exactly:

- K-62 by type (MONTHS[...].issued, critical lifts), K-69 closed / expired, K-70 lapses;
- K-63 permit-shifts for September (one shift per permit-day, plus the second shift after every
  same-day suspension: midday ban 12:00 → 15:00, other reasons 08:30 → 09:30);
- K-46 / K-46b / K-61 / K-64 from the field audits (counts stored per Y12, see DECISIONS #66);
- K-65 suspensions by reason (routine shift_end suspensions are not written as rows);
- K-66 gas-required shifts (ANIA-EXP: every shift of a confined-space permit and of the hot-work /
  excavation permits placed in Z-MSCP; RBT-52 has none);
- K-67 isolations open at 09-30 (de-isolated 10-01), K-68 conflicts by result (none open).

No bulk permit is live at the seed clock: September carry-overs end on 10-01 / 10-02.
"""

from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.core.hse_enums import CaPriority, CaSourceType, CaStatus, ControlLevel
from app.core.ptw_enums import (
    AuditAnswer,
    AuditFindingSeverity,
    CrewLineStatus,
    DistanceBasis,
    Exposure,
    IsolationStatus,
    JsaStatus,
    PermitStatus,
    PermitType,
    PtwAuditStatus,
    PtwAuditType,
    PtwCrewRole,
    ShiftEndType,
    SimopsConflictStatus,
    SimopsResult,
    StatusReason,
)
from app.models import (
    CorrectiveAction,
    IsolationCertificate,
    Jsa,
    Permit,
    PermitCrew,
    PermitShift,
    PermitSuspension,
    PtwAudit,
    SimopsConflict,
    Worker,
)
from app.seed_ptw import SEED_AT, Ctx, at
from app.services.access.common import local_day

T = PermitType
R = StatusReason
YEAR = 2026
EMERGENCY = "Assembly point per zone plan; emergency 997; first aid: site clinic"
BAN = (date(YEAR, 6, 15), date(YEAR, 9, 15))
NAMED_PERMIT_SEQ = {"ANIA-EXP": {399, 405, 408, 410, 412, 413}, "RBT-52": {279, 287, 288, 290}}
NAMED_AUDIT_SEQ = {"ANIA-EXP": {187, 188}, "RBT-52": set()}


@dataclass(frozen=True)
class Month:
    issued: dict[str, int]
    critical_lifts: int
    carry_out: int
    expired: int
    lapsed: int
    field: int
    distinct: int
    applicable: int
    compliant: int
    critical_items: int
    docs: int
    susp: dict[str, int]
    conflicts: tuple[int, int]  # prohibited, conditional
    unpermitted: int = 0
    midday: int | None = None  # None = ~40 % of eligible permit-days
    gas: tuple[int, int] | None = None  # (gas-required shifts ended, compliant)
    shifts: int | None = None  # K-63 target
    carry_out_iso: int = (
        0  # carry-outs (non-electrical) holding an extra isolation open at month end
    )
    long_term_iso: int = 0


def _types(**kw: int) -> dict[str, int]:
    return kw


MONTHS: dict[str, dict[int, Month]] = {
    "ANIA-EXP": {
        6: Month(
            _types(
                general=31,
                hot_work=25,
                work_at_height=20,
                lifting=12,
                excavation=7,
                electrical_isolation=6,
                confined_space=4,
                radiography=1,
                airside_works=2,
            ),
            2,
            8,
            3,
            3,
            58,
            55,
            1334,
            1202,
            1,
            18,
            {
                "ops_suspension": 4,
                "gas_test_failed": 1,
                "audit_critical": 1,
                "stop_work": 3,
                "wind_limit": 2,
                "simops_conflict": 1,
            },
            (1, 7),
        ),
        7: Month(
            _types(
                general=35,
                hot_work=28,
                work_at_height=23,
                lifting=14,
                excavation=8,
                electrical_isolation=6,
                confined_space=4,
                radiography=2,
                airside_works=2,
            ),
            3,
            10,
            5,
            4,
            61,
            57,
            1403,
            1240,
            2,
            19,
            {
                "ops_suspension": 5,
                "gas_test_failed": 2,
                "audit_critical": 2,
                "stop_work": 3,
                "wind_limit": 3,
                "weather": 1,
            },
            (2, 8),
        ),
        8: Month(
            _types(
                general=37,
                hot_work=30,
                work_at_height=24,
                lifting=15,
                excavation=9,
                electrical_isolation=6,
                confined_space=4,
                radiography=2,
                airside_works=2,
            ),
            3,
            11,
            4,
            2,
            60,
            56,
            1380,
            1256,
            2,
            18,
            {
                "ops_suspension": 4,
                "gas_test_failed": 1,
                "audit_critical": 2,
                "stop_work": 4,
                "wind_limit": 2,
                "key_role_ineligible": 1,
            },
            (1, 6),
        ),
        9: Month(
            _types(
                general=34,
                hot_work=28,
                work_at_height=22,
                lifting=14,
                excavation=8,
                electrical_isolation=6,
                confined_space=4,
                radiography=2,
                airside_works=2,
            ),
            3,
            14,
            4,
            5,
            64,
            58,
            1472,
            1361,
            3,
            20,
            {
                "ops_suspension": 5,
                "gas_test_failed": 2,
                "audit_critical": 3,
                "stop_work": 4,
                "key_role_ineligible": 1,
                "wind_limit": 2,
                "simops_conflict": 1,
            },
            (2, 7),
            unpermitted=1,
            midday=41,
            gas=(96, 91),
            shifts=610,
            carry_out_iso=2,
            long_term_iso=2,
        ),
    },
    "RBT-52": {
        6: Month(
            _types(
                work_at_height=9,
                hot_work=7,
                lifting=6,
                general=3,
                electrical_isolation=1,
                excavation=1,
            ),
            2,
            2,
            1,
            1,
            12,
            12,
            276,
            256,
            0,
            4,
            {"wind_limit": 1, "stop_work": 1},
            (0, 4),
        ),
        7: Month(
            _types(
                work_at_height=15,
                hot_work=12,
                lifting=10,
                general=5,
                electrical_isolation=2,
                excavation=1,
            ),
            3,
            3,
            2,
            2,
            20,
            19,
            460,
            426,
            1,
            6,
            {"wind_limit": 2, "audit_critical": 1, "stop_work": 1, "weather": 1},
            (0, 6),
        ),
        8: Month(
            _types(
                work_at_height=11,
                hot_work=10,
                lifting=8,
                general=4,
                electrical_isolation=1,
                excavation=1,
            ),
            2,
            3,
            1,
            1,
            16,
            15,
            368,
            342,
            0,
            5,
            {"wind_limit": 2, "simops_conflict": 1},
            (0, 4),
        ),
        # September bulk only: PTW-RBT-52-2026-0279 (named, electrical, issued 09-29, 2 shifts) adds the rest of Y12.
        9: Month(
            _types(
                work_at_height=14,
                hot_work=12,
                lifting=10,
                general=5,
                electrical_isolation=1,
                excavation=1,
            ),
            4,
            5,
            3,
            2,
            22,
            21,
            506,
            471,
            1,
            8,
            {
                "wind_limit": 2,
                "stop_work": 1,
                "audit_critical": 1,
                "simops_conflict": 1,
                "weather": 1,
            },
            (0, 4),
            midday=9,
            shifts=238,
        ),
    },
}

DURATION = {
    "general": (3, 7),
    "hot_work": (2, 5),
    "work_at_height": (3, 6),
    "lifting": (1, 2),
    "excavation": (4, 8),
    "electrical_isolation": (2, 4),
    "confined_space": (1, 3),
    "radiography": (1, 2),
    "airside_works": (2, 4),
}

# zone → (site, exposure); gas_test_zone zones are only used for gas permits (ANIA Z-MSCP).
ZONES = {
    "Z-APR-21": ("S-AIR", Exposure.outdoor_direct_sun),
    "Z-TWB": ("S-AIR", Exposure.outdoor_direct_sun),
    "Z-ILS33R": ("S-AIR", Exposure.outdoor_direct_sun),
    "Z-PIERB": ("S-LAND", Exposure.outdoor_shaded),
    "Z-MSCP": ("S-LAND", Exposure.outdoor_shaded),
    "Z-LAY1": ("S-LAND", Exposure.outdoor_direct_sun),
    "Z-CORE": ("S-TWR", Exposure.indoor),
    "Z-TC01": ("S-TWR", Exposure.outdoor_direct_sun),
    "Z-FAC": ("S-POD", Exposure.outdoor_direct_sun),
}
TYPE_ZONES = {
    "ANIA-EXP": {
        "general": ["Z-PIERB", "Z-LAY1", "Z-TWB", "Z-ILS33R", "Z-APR-21"],
        "hot_work": ["Z-PIERB", "Z-LAY1", "Z-TWB", "Z-ILS33R"],
        "work_at_height": ["Z-PIERB", "Z-LAY1"],
        "lifting": ["Z-PIERB", "Z-LAY1"],
        "excavation": ["Z-TWB", "Z-ILS33R", "Z-LAY1"],
        "electrical_isolation": ["Z-PIERB", "Z-LAY1"],
        "confined_space": ["Z-MSCP"],
        "radiography": ["Z-PIERB"],
        "airside_works": ["Z-TWB", "Z-ILS33R", "Z-APR-21"],
    },
    "RBT-52": {
        "general": ["Z-CORE", "Z-FAC"],
        "hot_work": ["Z-CORE"],
        "work_at_height": ["Z-CORE", "Z-FAC"],
        "lifting": ["Z-TC01"],
        "excavation": ["Z-FAC"],
        "electrical_isolation": ["Z-CORE"],
    },
}
SITE_ENGS = {
    "S-AIR": ["GULFPAVE", "RAWABI"],
    "S-LAND": ["NAJD", "RAWABI"],
    "S-TWR": ["QIMMA"],
    "S-POD": ["QIMMA"],
}
RECEIVER = {
    "GULFPAVE": "sanjay.verma",
    "NAJD": "ramesh.kumar",
    "RAWABI": "faris.anazi",
    "QIMMA": "joseph.mathew",
}
AREA = {
    "S-AIR": "omar.siddiqui",
    "S-LAND": "fahad.mutairi",
    "S-TWR": "ibrahim.saleh",
    "S-POD": "ibrahim.saleh",
}
ISSUER = {"ANIA-EXP": "khalid.otaibi", "RBT-52": "majed.shammari"}
OFFICER = {"ANIA-EXP": "noura.qahtani", "RBT-52": "lina.haddad"}
ISO_AUTH = {"ANIA-EXP": "nasser.shahrani", "RBT-52": "ibrahim.saleh"}
LOCKBOX = {"ANIA-EXP": "LB-ANIA-012", "RBT-52": "LB-RBT-003"}
CREW = {
    "general": [PtwCrewRole.supervisor, PtwCrewRole.worker, PtwCrewRole.worker],
    "hot_work": [PtwCrewRole.supervisor, PtwCrewRole.hot_work_operative, PtwCrewRole.fire_watch],
    "work_at_height": [PtwCrewRole.supervisor, PtwCrewRole.worker, PtwCrewRole.worker],
    "lifting": [
        PtwCrewRole.lift_supervisor,
        PtwCrewRole.crane_operator,
        PtwCrewRole.rigger,
        PtwCrewRole.signaller,
    ],
    "excavation": [PtwCrewRole.supervisor, PtwCrewRole.worker],
    "electrical_isolation": [PtwCrewRole.supervisor, PtwCrewRole.electrician],
    "confined_space": [
        PtwCrewRole.supervisor,
        PtwCrewRole.entrant,
        PtwCrewRole.entrant,
        PtwCrewRole.standby_person,
    ],
    "radiography": [PtwCrewRole.supervisor, PtwCrewRole.worker],
    "airside_works": [PtwCrewRole.supervisor, PtwCrewRole.worker],
}
TITLES = {
    "general": "General construction works",
    "hot_work": "Welding and cutting of steel members",
    "work_at_height": "Work at height on steelwork and facade",
    "lifting": "Lifting of materials",
    "excavation": "Excavation for services",
    "electrical_isolation": "Electrical works under isolation",
    "confined_space": "Manhole inspection and repair",
    "radiography": "Weld radiography",
    "airside_works": "Airside pavement and marking works",
}
FIELD_CODES = [f"A{n:02d}" for n in range(1, 21)]
SUSP_TEXT = {
    "ops_suspension": "Airside operations suspended the work (aircraft movement).",
    "gas_test_failed": "Periodic gas test failed; area ventilated and re-tested.",
    "audit_critical": "Critical audit finding; corrected on site before resuming.",
    "stop_work": "Stop-work by the area authority; unsafe condition corrected.",
    "key_role_ineligible": "Fire watch induction expired; replaced by an eligible worker.",
    "wind_limit": "Wind above the lift limit; resumed when the wind dropped.",
    "simops_conflict": "SIMOPS conflict with an adjacent permit; work re-sequenced.",
    "weather": "Dust storm; work stopped until visibility improved.",
}


@dataclass
class BP:
    project: str
    ptype: str
    month: int
    issue: date
    end: date
    critical: bool = False
    gas: bool = False
    carry_out: bool = False
    outcome: str = "closed"
    zone: str = ""
    site: str = ""
    eng: str = ""
    exposure: Exposure = Exposure.outdoor_shaded
    high_risk: bool = False
    events: dict[date, str] = field(default_factory=dict)  # day → suspension reason (or "midday")
    lapsed: set[date] = field(default_factory=set)
    gas_nc: set[date] = field(default_factory=set)
    iso: list[dict[str, Any]] = field(default_factory=list)
    row: Permit | None = None

    @property
    def days(self) -> list[date]:
        n = (self.end - self.issue).days + 1
        return [self.issue + timedelta(days=i) for i in range(n)]

    def days_in(self, m: int) -> list[date]:
        return [d for d in self.days if d.month == m]

    def ban_outdoor(self, d: date) -> bool:
        return self.exposure == Exposure.outdoor_direct_sun and BAN[0] <= d <= BAN[1]

    def shifts_in(self, m: int) -> int:
        return sum(2 if d in self.events else 1 for d in self.days_in(m))


def _last(m: int) -> int:
    return calendar.monthrange(YEAR, m)[1]


class Planner:
    def __init__(self, ctx: Ctx, project: str) -> None:
        self.ctx = ctx
        self.project = project
        self.rng = ctx.rng
        self.permits: list[BP] = []
        self.audits: list[dict[str, Any]] = []
        self.conflicts: list[dict[str, Any]] = []

    # ---- permits ---------------------------------------------------------------------------------

    def plan_permits(self) -> None:
        rng = self.rng
        carry_in: list[BP] = []
        for m, mc in MONTHS[self.project].items():
            last = _last(m)
            types: list[str] = [t for t, n in mc.issued.items() for _ in range(n)]
            rng.shuffle(types)
            # carry-outs: the electrical ones first in September (isolations open at 09-30)
            elec = [i for i, t in enumerate(types) if t == "electrical_isolation"]
            want_elec = (3 if self.project == "ANIA-EXP" else 1) if m == 9 else 0
            co_idx = set(elec[:want_elec])
            others = [i for i, t in enumerate(types) if i not in co_idx and t != "lifting"]
            rng.shuffle(others)
            for i in others:
                if len(co_idx) >= mc.carry_out:
                    break
                co_idx.add(i)
            lifts = [i for i, t in enumerate(types) if t == "lifting"]
            crit = set(lifts[: mc.critical_lifts])
            month_permits = []
            for i, t in enumerate(types):
                lo, hi = DURATION[t]
                n = 1 if i in crit else rng.randint(lo, hi)
                if i in co_idx:
                    issue = date(YEAR, m, rng.randint(last - 6, last))
                    nm = m + 1
                    end = date(YEAR, nm, 1 if m == 9 else rng.randint(1, 2))
                else:
                    issue = date(YEAR, m, rng.randint(1, last - n + 1))
                    end = issue + timedelta(days=n - 1)
                bp = BP(self.project, t, m, issue, end, critical=i in crit, carry_out=i in co_idx)
                month_permits.append(bp)
            ending = carry_in + [b for b in month_permits if not b.carry_out]
            for b in rng.sample(ending, mc.expired):
                b.outcome = "expired"
            self.permits += month_permits
            if mc.shifts is not None:
                self._adjust_days(m, ending, mc)
            carry_in = [b for b in month_permits if b.carry_out]

    def _adjust_days(self, m: int, ending: list[BP], mc: Month) -> None:
        """Shift the end day of permits ending in the month until K-63 matches (before events)."""
        assert mc.shifts is not None
        splits = sum(mc.susp.values()) + (mc.midday or 0)
        target = mc.shifts - splits
        live = [b for b in self.permits if b.days_in(m)]
        last = _last(m)
        adj = [b for b in ending if not b.critical]
        guard = 0
        while True:
            cur = sum(len(b.days_in(m)) for b in live)
            if cur == target:
                return
            guard += 1
            assert guard < 100000, "cannot reach the permit-shift target"
            b = self.rng.choice(adj)
            if cur < target and b.end.day < last and b.end.month == m:
                b.end += timedelta(days=1)
            elif (
                cur > target
                and b.end > b.issue
                and b.end.month == m
                and (b.end.day > 1 or b.issue.month == m)
            ):
                b.end -= timedelta(days=1)

    # ---- zones, gas, roles ----------------------------------------------------------------------

    def place(self) -> None:
        rng = self.rng
        gas_set: set[int] = set()
        if self.project == "ANIA-EXP":
            for b in self.permits:
                if b.ptype == "confined_space":
                    b.gas = True
            for m, mc in MONTHS[self.project].items():
                pool = [
                    b
                    for b in self.permits
                    if b.month == m and b.ptype in ("hot_work", "excavation") and not b.carry_out
                ]
                if mc.gas is None:
                    for b in rng.sample(pool, max(1, len(pool) // 4)):
                        b.gas = True
                    continue
                fixed = sum(len(b.days_in(m)) for b in self.permits if b.gas and b.days_in(m))
                need = mc.gas[0] - fixed - mc.susp.get("gas_test_failed", 0)
                pick = _subset(pool, need, m, rng)
                assert pick is not None, f"no gas subset for {self.project} {m}"
                for b in pick:
                    b.gas = True
            gas_set = {id(b) for b in self.permits if b.gas}
        for b in self.permits:
            if id(b) in gas_set:
                b.zone = "Z-MSCP"
            else:
                b.zone = rng.choice(TYPE_ZONES[self.project][b.ptype])
            b.site, b.exposure = ZONES[b.zone]
            b.eng = "RAWABI" if b.ptype == "confined_space" else rng.choice(SITE_ENGS[b.site])
            b.high_risk = (
                b.ptype in ("confined_space", "radiography")
                or b.critical
                or (b.ptype == "hot_work" and (b.site == "S-AIR" or b.gas))
                or (b.ptype in ("work_at_height", "excavation") and rng.random() < 0.5)
            )

    # ---- events ---------------------------------------------------------------------------------

    def _free(self, m: int, pred: Any = None, nongas: bool = True) -> list[tuple[BP, date]]:
        out = []
        for b in self.permits:
            if nongas and b.gas:
                continue
            if pred is not None and not pred(b):
                continue
            for d in b.days_in(m):
                if d not in b.events and d not in b.lapsed:
                    out.append((b, d))
        return out

    def events(self) -> None:
        rng = self.rng
        for m, mc in MONTHS[self.project].items():
            susp = dict(mc.susp)
            # conflicts (pairs live on the same day, same site)
            by_day: dict[tuple[date, str], list[BP]] = {}
            for b in self.permits:
                for d in b.days_in(m):
                    by_day.setdefault((d, b.site), []).append(b)
            keys = [k for k, v in by_day.items() if len(v) >= 2 and k[0].day < _last(m)]
            rng.shuffle(keys)
            results = [SimopsResult.prohibited] * mc.conflicts[0] + [
                SimopsResult.conditional
            ] * mc.conflicts[1]
            for res, (d, _site) in zip(results, keys, strict=False):
                a, bb = rng.sample(by_day[(d, _site)], 2)
                c = {"a": a, "b": bb, "day": d, "result": res}
                self.conflicts.append(c)
                if susp.get("simops_conflict") and not a.gas and d not in a.events:
                    a.events[d] = "simops_conflict"
                    susp["simops_conflict"] -= 1
            assert susp.get("simops_conflict", 0) == 0, "simops suspension not placed"
            # critical field audits → audit_critical suspensions
            crit_days = rng.sample(self._free(m), mc.critical_items)
            for b, d in crit_days:
                b.events[d] = "audit_critical"
            susp["audit_critical"] = susp.get("audit_critical", 0) - mc.critical_items
            assert susp["audit_critical"] == 0
            for reason, n in susp.items():
                if not n:
                    continue
                if reason == "ops_suspension":
                    pool = self._free(m, lambda b: b.site == "S-AIR")
                elif reason == "wind_limit":
                    pool = self._free(m, lambda b: b.ptype == "lifting")
                elif reason == "gas_test_failed":
                    pool = [(b, d) for b, d in self._free(m, lambda b: b.gas, nongas=False)]
                else:
                    pool = self._free(m)
                for b, d in rng.sample(pool, n):
                    b.events[d] = reason
            # midday ban (outdoor direct sun, 06-15…09-15)
            pool = [(b, d) for b, d in self._free(m) if b.ban_outdoor(d)]
            n = mc.midday if mc.midday is not None else int(len(pool) * 0.4)
            for b, d in rng.sample(pool, n):
                b.events[d] = "midday"
            # lapses (not on a closing day)
            pool = [
                (b, d)
                for b, d in self._free(m, nongas=False)
                if not (d == b.end and b.outcome == "closed") and d not in b.events
            ]
            for b, d in rng.sample(pool, mc.lapsed):
                b.lapsed.add(d)
            # gas non-compliant shifts
            if mc.gas is not None:
                gshifts = [(b, d) for b in self.permits if b.gas for d in b.days_in(m)]
                total = sum(2 if d in b.events else 1 for b, d in gshifts)
                assert total == mc.gas[0], (self.project, m, total)
                for b, d in rng.sample(
                    [x for x in gshifts if x[1] not in x[0].events], mc.gas[0] - mc.gas[1]
                ):
                    b.gas_nc.add(d)
            elif self.project == "ANIA-EXP":
                gshifts = [
                    (b, d) for b in self.permits if b.gas for d in b.days_in(m) if d not in b.events
                ]
                for b, d in rng.sample(gshifts, max(1, len(gshifts) // 25)):
                    b.gas_nc.add(d)
            if mc.shifts is not None:
                got = sum(b.shifts_in(m) for b in self.permits)
                assert got == mc.shifts, (self.project, m, got)
            self._plan_audits(m, mc, crit_days)

    def _plan_audits(self, m: int, mc: Month, crit_days: list[tuple[BP, date]]) -> None:
        rng = self.rng
        live = [b for b in self.permits if b.days_in(m)]
        crit_permits = [b for b, _d in crit_days]
        others = [b for b in live if b not in crit_permits]
        chosen = crit_permits + rng.sample(others, mc.distinct - len(crit_permits))
        visits: list[tuple[BP, date, bool]] = [(b, d, True) for b, d in crit_days]
        for b in chosen[len(crit_permits) :]:
            visits.append((b, rng.choice(b.days_in(m)), False))
        twice = [b for b in chosen if len(b.days_in(m)) >= 2]
        for b in rng.sample(twice, mc.field - mc.distinct):
            used = {d for x, d, _c in visits if x is b}
            free = [d for d in b.days_in(m) if d not in used]
            visits.append((b, rng.choice(free), False))
        assert len(visits) == mc.field
        apps = _spread(mc.applicable, mc.field)
        ncs = _spread(mc.applicable - mc.compliant, mc.field, rng)
        for i, (b, d, crit) in enumerate(visits):
            nc = max(ncs[i], 1) if crit else ncs[i]
            self.audits.append(
                {
                    "type": PtwAuditType.field,
                    "bp": b,
                    "day": d,
                    "applicable": apps[i],
                    "nc": nc,
                    "critical": crit,
                }
            )
        # rebalance if a critical audit had 0 NC planned
        extra = sum(
            a["nc"]
            for a in self.audits
            if a.get("day") and a["day"].month == m and a["type"] == PtwAuditType.field
        ) - (mc.applicable - mc.compliant)
        for a in self.audits:
            if extra <= 0:
                break
            if (
                a["type"] == PtwAuditType.field
                and a["day"].month == m
                and not a["critical"]
                and a["nc"] > 0
            ):
                a["nc"] -= 1
                extra -= 1
        ended = [
            b for b in self.permits if b.end.month == m and b.end.day < _last(m) and not b.high_risk
        ]
        for b in rng.sample(ended, mc.docs):
            self.audits.append(
                {
                    "type": PtwAuditType.document_review,
                    "bp": b,
                    "day": b.end + timedelta(days=1),
                    "applicable": 12,
                    "nc": rng.choice([0, 0, 1]),
                    "critical": False,
                }
            )
        for _ in range(mc.unpermitted):
            self.audits.append(
                {
                    "type": PtwAuditType.unpermitted_work,
                    "bp": None,
                    "day": date(YEAR, m, 17),
                    "applicable": 1,
                    "nc": 1,
                    "critical": True,
                }
            )


def _spread(total: int, n: int, rng: Any = None) -> list[int]:
    base, rem = divmod(total, n)
    out = [base + (1 if i < rem else 0) for i in range(n)]
    if rng is not None:
        rng.shuffle(out)
    return out


def _subset(pool: list[BP], need: int, m: int, rng: Any) -> list[BP] | None:
    items = list(pool)
    rng.shuffle(items)
    reach: dict[int, list[int]] = {0: []}
    for i, b in enumerate(items):
        w = len(b.days_in(m))
        for s, path in list(reach.items()):
            t = s + w
            if t <= need and t not in reach:
                reach[t] = [*path, i]
    if need not in reach:
        return None
    return [items[i] for i in reach[need]]


# ---- writing rows --------------------------------------------------------------------------------


def _t(d: date, h: int, mi: int = 0) -> datetime:
    return at(d.year, d.month, d.day, h, mi)


class Writer:
    def __init__(self, ctx: Ctx, project: str, plan: Planner) -> None:
        self.ctx = ctx
        self.db = ctx.db
        self.project = project
        self.plan = plan
        self.pid = ctx.pid(project)
        self.pools: dict[tuple[str, str], list[uuid.UUID]] = {}

    def pool(self, eng: str, site: str) -> list[uuid.UUID]:
        key = (eng, site)
        if key not in self.pools:
            from app.models import Deployment

            e = self.ctx.eng(self.project, eng)
            sid = self.ctx.site(self.project, site).id
            rows = self.db.execute(
                select(Worker.id, Deployment.site_ids)
                .join(Deployment, Deployment.worker_id == Worker.id)
                .where(
                    Worker.seq >= 1000,
                    Deployment.engagement_id == e.id,
                    Deployment.demobilised_on.is_(None),
                )
                .order_by(Worker.seq)
            ).all()
            self.pools[key] = [wid for wid, sites in rows if sid in (sites or [])][:120]
        return self.pools[key]

    def uid(self, key: str) -> uuid.UUID:
        return self.ctx.uid(key)

    def _template(self, ptype: str) -> Jsa:
        mine = [
            j
            for no, j in sorted(self.ctx.templates.items())
            if no.startswith(f"JSA-T-{self.project}-")
        ]
        exact = [j for j in mine if list(j.work_types or []) == [ptype]]
        anyt = [j for j in mine if ptype in (j.work_types or [])]
        return (exact or anyt or mine)[0]

    def write(self) -> None:
        self._permits()
        self._isolations()
        self._conflicts()
        self._audits()
        self.db.flush()

    # ---- permits / shifts / suspensions -------------------------------------------------------

    def _permits(self) -> None:
        db = self.db
        rng = self.plan.rng
        plan = sorted(self.plan.permits, key=lambda b: (b.issue, b.ptype, b.zone))
        skip = NAMED_PERMIT_SEQ[self.project]
        seq = 0
        issuer = self.uid(ISSUER[self.project])
        jsas: list[Jsa] = []
        for b in plan:
            seq += 1
            while seq in skip:
                seq += 1
            receiver = self.uid(RECEIVER[b.eng])
            area = self.uid(AREA[b.site])
            hse = self.uid(OFFICER[self.project]) if b.high_risk else None
            zone = self.ctx.zones[b.zone]
            site = self.ctx.site(self.project, b.site)
            eng = self.ctx.eng(self.project, b.eng)
            issued = _t(b.issue, 6, 15)
            req = issued - timedelta(
                minutes=rng.choice([90, 120, 150, 180, 210, 240, 300, 360, 480, 960])
            )
            ban_any = b.exposure == Exposure.outdoor_direct_sun and any(
                BAN[0] <= d <= BAN[1] for d in b.days
            )
            windows = (
                [
                    {"start_local": "06:00", "end_local": "12:00", "weekdays": WEEK},
                    {"start_local": "15:00", "end_local": "18:00", "weekdays": WEEK},
                ]
                if ban_any
                else [{"start_local": "06:00", "end_local": "18:00", "weekdays": WEEK}]
            )
            crew_n = len(CREW[b.ptype])
            pool = self.pool(b.eng, b.site)
            crew = rng.sample(pool, crew_n) if len(pool) >= crew_n else pool[:crew_n]
            p = Permit(
                id=uuid.uuid4(),
                project_id=self.pid,
                year=YEAR,
                seq=seq,
                permit_no=f"PTW-{self.project}-{YEAR}-{seq:04d}",
                site_id=site.id,
                zone_ids=[zone.id],
                location_desc=f"{b.zone} work area {rng.randint(1, 40)}",
                grid_x_m=Decimal(rng.randint(0, 3000)) / 10,
                grid_y_m=Decimal(rng.randint(0, 3000)) / 10,
                engagement_id=eng.id,
                work_types=[b.ptype],
                primary_type=T(b.ptype),
                high_risk=b.high_risk,
                critical_lift=b.critical,
                title=TITLES[b.ptype],
                scope_en=f"{TITLES[b.ptype]} ({b.zone}).",
                exposure=b.exposure,
                valid_from_at=_t(b.issue, 6),
                valid_to_at=_t(b.end, 18),
                windows=windows,
                receiver_user_id=receiver,
                area_authority_user_id=area,
                issuer_user_id=issuer,
                hse_reviewer_user_id=hse,
                supervisor_worker_id=crew[0] if crew else None,
                emergency_info=EMERGENCY,
                sections={},
                checklists={},
                blockers=[],
                warnings=[],
                status=PermitStatus.closed if b.outcome == "closed" else PermitStatus.expired,
                first_requested_at=req,
                requested_at=req,
                reviewed_at=req + timedelta(minutes=40),
                approved_at=issued - timedelta(minutes=20),
                first_issued_at=issued,
                issued_at=issued,
                started_at=_t(b.issue, 6, 30),
                created_at=req - timedelta(minutes=30),
                updated_at=_t(b.end, 18, 40),
                created_by_user_id=receiver,
                seed_fake=True,
            )
            db.add(p)
            b.row = p
            tpl = self._template(b.ptype)
            j = Jsa(
                id=uuid.uuid4(),
                project_id=self.pid,
                jsa_no="JSA-" + p.permit_no.removeprefix("PTW-"),
                seq=seq,
                revision=0,
                is_template=False,
                template_id=tpl.id,
                engagement_id=eng.id,
                permit_id=p.id,
                work_types=[b.ptype],
                title_en=TITLES[b.ptype],
                steps=list(tpl.steps or []),
                residual_acceptances=[
                    {
                        "role": "issuer",
                        "user_id": str(issuer),
                        "at": (req + timedelta(minutes=60)).isoformat(),
                    }
                ],
                crew_briefings=[],
                approved_by_user_id=issuer,
                approved_at=req + timedelta(minutes=60),
                status=JsaStatus.approved,
                alerts_sent=[],
                created_by_user_id=receiver,
                created_at=req - timedelta(minutes=20),
                seed_fake=True,
            )
            jsas.append(j)
            p.jsa_id = j.id
            for i, wid in enumerate(crew):
                db.add(
                    PermitCrew(
                        id=uuid.uuid4(),
                        permit_id=p.id,
                        worker_id=wid,
                        crew_role=CREW[b.ptype][i],
                        status=CrewLineStatus.listed,
                        eligible=True,
                        evaluated_at=issued,
                        created_at=req,
                    )
                )
            self._shifts(b, p, receiver, issuer)
        db.flush()
        db.add_all(jsas)
        db.flush()

    def _shifts(self, b: BP, p: Permit, receiver: uuid.UUID, issuer: uuid.UUID) -> None:
        db = self.db
        n = 0
        days = b.days
        last_end: datetime | None = None
        for d in days:
            final = d == b.end
            ev = b.events.get(d)
            day_end = (11, 45) if (b.ban_outdoor(d) and ev != "midday") else (16, 30)
            planned = _t(d, 12) if b.ban_outdoor(d) else _t(d, 18)
            parts: list[tuple[datetime, datetime, datetime, ShiftEndType]] = []
            if ev == "midday":
                parts.append((_t(d, 6, 30), _t(d, 12), _t(d, 12), ShiftEndType.suspended))
                parts.append((_t(d, 15), _t(d, 17, 30), _t(d, 18), ShiftEndType.shift_end))
                db.add(
                    PermitSuspension(
                        id=uuid.uuid4(),
                        permit_id=p.id,
                        project_id=self.pid,
                        suspended_at=_t(d, 12),
                        reason=R.midday_ban,
                        routine=True,
                        detail="Midday work ban (12:00–15:00).",
                        auto_source_ref="midday_ban",
                        resumed_at=_t(d, 15),
                        resumed_by_user_id=receiver,
                        seed_fake=True,
                    )
                )
            elif ev is not None:
                parts.append((_t(d, 6, 30), _t(d, 8, 30), planned, ShiftEndType.suspended))
                parts.append((_t(d, 9, 30), _t(d, *day_end), planned, ShiftEndType.shift_end))
                db.add(
                    PermitSuspension(
                        id=uuid.uuid4(),
                        permit_id=p.id,
                        project_id=self.pid,
                        suspended_at=_t(d, 8, 30),
                        reason=R(ev),
                        routine=False,
                        raised_by_user_id=issuer
                        if ev in ("stop_work", "audit_critical", "ops_suspension")
                        else None,
                        detail=SUSP_TEXT[ev],
                        resumed_at=_t(d, 9, 30),
                        resumed_by_user_id=issuer,
                        cause_cleared_text=SUSP_TEXT[ev],
                        seed_fake=True,
                    )
                )
            elif d in b.lapsed:
                parts.append((_t(d, 6, 30), planned, planned, ShiftEndType.lapsed))
            else:
                parts.append((_t(d, 6, 30), _t(d, *day_end), planned, ShiftEndType.shift_end))
            for i, (s, e, pe, et0) in enumerate(parts):
                n += 1
                et = et0
                if final and i == len(parts) - 1 and b.outcome == "closed":
                    et = ShiftEndType.closed
                db.add(
                    PermitShift(
                        id=uuid.uuid4(),
                        permit_id=p.id,
                        project_id=self.pid,
                        shift_no=n,
                        started_at=s,
                        planned_end_at=pe,
                        receiver_user_id=receiver,
                        issuer_user_id=issuer,
                        ended_at=e,
                        end_type=et,
                        gas_required=b.gas,
                        gas_compliant=(d not in b.gas_nc) if b.gas else None,
                        seed_fake=True,
                    )
                )
                last_end = e
        assert last_end is not None
        if b.outcome == "closed":
            p.closed_at = last_end + timedelta(minutes=15)
            p.ended_at = p.closed_at
            p.closure_request = {
                "requested_by_user_id": str(receiver),
                "requested_at": last_end.isoformat(),
                "work_status": "complete",
                "remaining_work": None,
            }
        else:
            p.ended_at = p.valid_to_at
            p.status_reason = None
            p.post_expiry_check = {
                "checked_by_user_id": str(issuer),
                "checked_at": (p.valid_to_at + timedelta(minutes=40)).isoformat(),
                "site_visit_confirmed": True,
                "area_safe": True,
                "area_note": None,
                "entrants_zero": True,
                "personal_locks_removed": True,
                "fire_watch_status": None,
                "ca_id": None,
            }

    # ---- isolations -----------------------------------------------------------------------------

    def _isolations(self) -> None:
        db = self.db
        plan = self.plan
        rows: list[tuple[datetime, dict[str, Any]]] = []
        for b in plan.permits:
            if b.ptype == "electrical_isolation":
                rows.append(
                    (
                        _t(b.issue, 5, 50),
                        {
                            "permits": [b],
                            "start": b.issue,
                            "open_to": b.end if b.end.month > 9 else None,
                            "desc": f"Distribution board {b.zone} DB-{plan.rng.randint(1, 40):02d}",
                        },
                    )
                )
        mc = MONTHS[self.project].get(9)
        if mc is not None and (mc.carry_out_iso or mc.long_term_iso):
            co = [
                b
                for b in plan.permits
                if b.month == 9 and b.carry_out and b.ptype != "electrical_isolation"
            ]
            co_iso = co[: mc.carry_out_iso + mc.long_term_iso]
            for b in co_iso[: mc.carry_out_iso]:
                rows.append(
                    (
                        _t(b.issue, 5, 50),
                        {
                            "permits": [b],
                            "start": b.issue,
                            "open_to": b.end,
                            "desc": f"Pump set isolation {b.zone}",
                        },
                    )
                )
            early = [
                b
                for b in plan.permits
                if b.month == 9
                and not b.carry_out
                and b.issue.day <= 14
                and b.ptype in ("general", "work_at_height")
            ]
            for i, b in enumerate(co_iso[mc.carry_out_iso :]):
                first = early[i]
                rows.append(
                    (
                        _t(first.issue, 5, 50),
                        {
                            "permits": [first, b],
                            "start": first.issue,
                            "open_to": b.end,
                            "desc": f"Long-term isolation of feeder {first.zone} F-{i + 1}",
                            "long": True,
                        },
                    )
                )
        rows.sort(key=lambda r: r[0])
        auth = self.uid(ISO_AUTH[self.project])
        lockbox = self.ctx.locks[LOCKBOX[self.project]].id
        for seq, (t0, r) in enumerate(rows, start=1):
            b_last = r["permits"][-1]
            if r["open_to"] is not None:
                done = _t(date(YEAR, 10, 1), 17)
            elif b_last.outcome == "closed":
                assert b_last.row is not None and b_last.row.closed_at is not None
                done = b_last.row.closed_at + timedelta(minutes=25)
            else:
                done = _t(b_last.end, 18, 30)
            reviews = []
            if r.get("long"):
                t = t0 + timedelta(days=7)
                while t < done:
                    reviews.append(
                        {
                            "by": str(auth),
                            "at": t.isoformat(),
                            "in_place": True,
                            "note": "Weekly review: locks and tags in place.",
                        }
                    )
                    t += timedelta(days=7)
            c = IsolationCertificate(
                id=uuid.uuid4(),
                project_id=self.pid,
                year=YEAR,
                seq=seq,
                iso_no=f"ISO-{self.project}-{YEAR}-{seq:04d}",
                engagement_id=r["permits"][0].row.engagement_id,
                equipment_desc=r["desc"],
                energy_types=["electrical"],
                hv=False,
                isolation_authority_user_id=auth,
                lockbox_id=lockbox,
                status=IsolationStatus.deisolated,
                isolated_at=t0,
                verified_at=t0 + timedelta(minutes=15),
                deisolation_requested_at=done - timedelta(minutes=20),
                deisolation_authorised_by_user_id=self.uid(ISSUER[self.project]),
                deisolation_authorised_at=done - timedelta(minutes=10),
                deisolated_at=done,
                reviews=reviews,
                created_at=t0 - timedelta(hours=12),
                updated_at=done,
                created_by_user_id=auth,
                seed_fake=True,
            )
            db.add(c)
            for b in r["permits"]:
                assert b.row is not None
                b.row.isolation_cert_ids = [*(b.row.isolation_cert_ids or []), c.id]

    # ---- conflicts ------------------------------------------------------------------------------

    def _conflicts(self) -> None:
        rows = sorted(self.plan.conflicts, key=lambda c: (c["day"], c["a"].row.permit_no))
        rng = self.plan.rng
        for seq, c in enumerate(rows, start=1):
            a, b = c["a"].row, c["b"].row
            det = _t(c["day"], 8, 25)
            prohibited = c["result"] == SimopsResult.prohibited
            rule = (
                rng.choice(["SM-R01", "SM-R03"])
                if prohibited
                else rng.choice(["SM-R02", "SM-R05b", "SM-R06", "SM-R08"])
            )
            self.db.add(
                SimopsConflict(
                    id=uuid.uuid4(),
                    project_id=self.pid,
                    year=YEAR,
                    seq=seq,
                    conflict_no=f"SIM-{self.project}-{YEAR}-{seq:04d}",
                    permit_a_id=a.id,
                    permit_b_id=b.id,
                    rule_code=rule,
                    distance_m=Decimal(rng.randint(20, 140)) / 10,
                    distance_basis=DistanceBasis.grid,
                    overlap_from=_t(c["day"], 6),
                    overlap_to=_t(c["day"], 18),
                    result=c["result"],
                    required_controls_en="Re-sequence the work or apply the rule's controls.",
                    status=SimopsConflictStatus.closed,
                    detected_at=det,
                    coordinated_at=None if prohibited else det + timedelta(minutes=45),
                    resolved_at=det + timedelta(minutes=90),
                    seed_fake=True,
                )
            )

    # ---- audits ---------------------------------------------------------------------------------

    def _audits(self) -> None:
        rng = self.plan.rng
        rows = []
        for a in self.plan.audits:
            if a["type"] == PtwAuditType.field:
                t = _t(a["day"], 8, 20) if a["critical"] else _t(a["day"], 10)
            elif a["type"] == PtwAuditType.document_review:
                t = _t(a["day"], 9)
            else:
                t = _t(a["day"], 11, 10)
            rows.append((t, a))
        rows.sort(key=lambda r: r[0])
        skip = NAMED_AUDIT_SEQ[self.project]
        seq = 0
        officer = OFFICER[self.project]
        cas: list[tuple[datetime, uuid.UUID, str, Permit | None, dict[str, Any]]] = []
        for t, a in rows:
            seq += 1
            while seq in skip:
                seq += 1
            b: BP | None = a["bp"]
            p = b.row if b else None
            if p is not None and p.hse_reviewer_user_id is not None:
                auditor = (
                    "faisal.harbi"
                    if b is not None and (self.project == "RBT-52" or b.site == "S-AIR")
                    else "nasser.shahrani"
                )
            else:
                auditor = officer if rng.random() < 0.7 else "faisal.harbi"
            app, nc = a["applicable"], a["nc"]
            if a["type"] == PtwAuditType.unpermitted_work:
                items: list[dict[str, Any]] = [
                    {
                        "code": "A00",
                        "answer": "non_compliant",
                        "severity": "critical",
                        "note": "Excavation found without a permit; stopped.",
                        "photo_attachment_ids": [],
                    }
                ]
                comp, crit = 0, 1
            else:
                codes = FIELD_CODES if a["type"] == PtwAuditType.field else FIELD_CODES[:12]
                crit_code = rng.choice(["A10", "A12", "A05"]) if a["critical"] else None
                rest = [c for c in codes[1:] if c != crit_code]
                nc_codes = set(rng.sample(rest, min(nc - (1 if crit_code else 0), len(rest))))
                if crit_code:
                    nc_codes.add(crit_code)
                items = [
                    {
                        "code": c,
                        "answer": (
                            AuditAnswer.non_compliant if c in nc_codes else AuditAnswer.compliant
                        ).value,
                        "severity": (
                            AuditFindingSeverity.critical
                            if c == crit_code
                            else AuditFindingSeverity.minor
                        ).value,
                        "note": None,
                        "photo_attachment_ids": [],
                    }
                    for c in codes
                ]
                comp, crit = app - nc, 1 if a["critical"] else 0
            completed = t + timedelta(minutes=40)
            aid = uuid.uuid4()
            if crit:
                code = (
                    "A00"
                    if p is None
                    else next(str(x["code"]) for x in items if x["severity"] == "critical")
                )
                cas.append((t, aid, code, p, a))
            self.db.add(
                PtwAudit(
                    id=aid,
                    project_id=self.pid,
                    year=YEAR,
                    seq=seq,
                    audit_no=f"PTA-{self.project}-{YEAR}-{seq:05d}",
                    audit_type=a["type"],
                    permit_id=p.id if p else None,
                    site_id=p.site_id if p else self.ctx.site(self.project, "S-AIR").id,
                    zone_id=p.zone_ids[0] if p else self.ctx.zones["Z-TWB"].id,
                    engagement_id=p.engagement_id
                    if p
                    else self.ctx.eng(self.project, "GULFPAVE").id,
                    auditor_user_id=self.uid(auditor),
                    audited_at=t,
                    items=items,
                    applicable_count=app,
                    compliant_count=comp,
                    critical_count=crit,
                    score_pct=(Decimal(comp) * 100 / Decimal(app)).quantize(Decimal("0.1"))
                    if app
                    else None,
                    stop_work_issued_at=t - timedelta(minutes=5) if p is None else None,
                    unpermitted_work_desc="Trench excavation near taxiway B edge without a permit."
                    if p is None
                    else None,
                    permit_suspended=bool(a["critical"]) and p is not None,
                    status=PtwAuditStatus.locked
                    if completed + timedelta(days=7) <= SEED_AT
                    else PtwAuditStatus.completed,
                    completed_at=completed,
                    edit_log=[],
                    created_at=t,
                    updated_at=completed,
                    created_by_user_id=self.uid(auditor),
                    seed_fake=True,
                )
            )
        self.db.flush()
        self._cas(cas)

    def _cas(
        self, rows: list[tuple[datetime, uuid.UUID, str, Permit | None, dict[str, Any]]]
    ) -> None:
        """AU-4/AU-5: every critical finding has its critical CA (closed, verified on time)."""
        from sqlalchemy import func

        seq = int(
            self.db.scalar(
                select(func.max(CorrectiveAction.seq)).where(
                    CorrectiveAction.project_id == self.pid, CorrectiveAction.year == YEAR
                )
            )
            or 0
        )
        owner = self.uid("ahmed.zahrani" if self.project == "ANIA-EXP" else "yousef.ghamdi")
        verifier = self.uid(OFFICER[self.project])
        for t, aid, code, p, _a in rows:
            seq += 1
            d0 = local_day(t)
            self.db.add(
                CorrectiveAction(
                    id=uuid.uuid4(),
                    project_id=self.pid,
                    year=YEAR,
                    seq=seq,
                    ref=f"CA-{self.project}-{YEAR}-{seq:05d}",
                    source_type=CaSourceType.ptw_audit,
                    source_id=aid,
                    site_id=p.site_id if p else self.ctx.site(self.project, "S-AIR").id,
                    zone_id=p.zone_ids[0] if p else self.ctx.zones["Z-TWB"].id,
                    responsible_engagement_id=p.engagement_id
                    if p
                    else self.ctx.eng(self.project, "GULFPAVE").id,
                    title=f"{code}: correct the critical PTW audit finding",
                    description=f"{code} found non-compliant (critical) in a field audit; corrected, crew re-briefed and the permit re-inspected before work resumed.",
                    control_level=ControlLevel.engineering
                    if code in ("A05", "A12")
                    else ControlLevel.administrative,
                    priority=CaPriority.critical,
                    owner_id=owner,
                    verifier_id=verifier,
                    created_date=d0,
                    due_date=d0 + timedelta(days=2),
                    original_due_date=d0 + timedelta(days=2),
                    status=CaStatus.closed,
                    completed_at=t + timedelta(hours=26),
                    completed_date=d0 + timedelta(days=1),
                    evidence_text="Corrected on site; re-inspection record and photos attached.",
                    verified_at=t + timedelta(hours=48),
                    verified_date=d0 + timedelta(days=2),
                    verification_comment="Verified on site.",
                    created_by_user_id=verifier,
                    created_at=t + timedelta(minutes=30),
                    updated_at=t + timedelta(hours=48),
                    seed_fake=True,
                )
            )


WEEK = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]


def run(ctx: Ctx) -> None:
    for project in ("ANIA-EXP", "RBT-52"):
        plan = Planner(ctx, project)
        plan.plan_permits()
        plan.place()
        plan.events()
        Writer(ctx, project, plan).write()
