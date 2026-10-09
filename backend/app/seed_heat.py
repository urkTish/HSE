"""Phase 6b seed (spec 6b-heat-stress Appendix A): settings, instruments, station device,
monitoring points, rest stations, the 2026 season (readings, patrols, welfare checks, exemptions,
September acclimatisation plans, heat-illness log) and the named records of A.5, reproducing HS7
(September 2026) and HS8 (season 2026).

Everything 6b is inserted directly (no alerts). Phase 1 changes are limited to §11.2 item 5: the
W1 #4 heat case moves to 13:50, and existing Jun–Aug cases take a heat nature so that the season
has the HS8 counts (category counts per month unchanged). Fictional; serials contain TEST."""

from __future__ import annotations

import itertools
import math
import secrets
import uuid
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus, WorkerPersonType
from app.core.clock import set_now
from app.core.heat_enums import (
    BanExemptionReason,
    BanExemptionStatus,
    CheckAnswer,
    Cooling,
    HeatLogSource,
    HeatLogStatus,
    InstrumentKind,
    InstrumentStatus,
    PatrolOutcome,
    PlanStatus,
    PlanTriggerKind,
    PlanType,
    PointSourceKind,
    ReadingSource,
    RecordStatus,
    ReviewAnswer,
    ReviewQuestion,
    StationType,
    WelfareItem,
)
from app.core.hse_enums import CaStatus, IncidentStatus
from app.core.security import token_digest
from app.models import (
    AcclimatisationPlan,
    BanExemption,
    BanPatrol,
    Contractor,
    Deployment,
    FitnessHold,
    HeatIllnessEntry,
    HeatInstrument,
    HeatSettings,
    HeatStationDevice,
    HeatWelfareCheck,
    Incident,
    InjuryCase,
    MonitoringPoint,
    Project,
    ProjectEngagement,
    RestStation,
    Site,
    User,
    WbgtReading,
    Worker,
    Zone,
)
from app.services.heat import common as hc

RIYADH = ZoneInfo("Asia/Riyadh")
SEED_CLOCK = datetime(2026, 10, 6, 7, 0, tzinfo=UTC)  # 10:00 Riyadh
SEASON = (date(2026, 5, 1), date(2026, 9, 30))
D = Decimal
R4_VALUE = D("31.0")
CAP = D("30.4")  # acclimatised heavy R3 (≤ 30.5)
HEAT_TRADES = ("labourer", "steel_fixer", "steel_erector", "scaffolder", "rigger", "mason",
               "carpenter", "flagman", "welder")  # fmt: skip


def at(d: date, h: int, mi: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, mi, tzinfo=RIYADH).astimezone(UTC)


def days(d0: date, d1: date) -> Iterator[date]:
    d = d0
    while d <= d1:
        yield d
        d += timedelta(days=1)


# ---- context ------------------------------------------------------------------------------------


class Ctx:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.projects = {p.code: p for p in db.scalars(select(Project))}
        self.users = {u.email.split("@")[0]: u for u in db.scalars(select(User))}
        self.engs: dict[tuple[str, str], ProjectEngagement] = {}
        code_of = {p.id: p.code for p in self.projects.values()}
        for e, c in db.execute(
            select(ProjectEngagement, Contractor).join(
                Contractor, Contractor.id == ProjectEngagement.contractor_id
            )
        ):
            self.engs[(code_of[e.project_id], c.short_code)] = e
        self.sites = {(code_of[s.project_id], s.code): s for s in db.scalars(select(Site))}
        self.zones: dict[tuple[str, str], Zone] = {}
        for z, s in db.execute(select(Zone, Site).join(Site, Site.id == Zone.site_id)):
            self.zones[(code_of[s.project_id], z.code)] = z
        self.counters: dict[tuple[str, str], itertools.count[int]] = {}
        self.reserved: dict[tuple[str, str], set[int]] = defaultdict(set)
        self.points: dict[str, MonitoringPoint] = {}
        self.instruments: dict[str, HeatInstrument] = {}
        self.stations: dict[str, RestStation] = {}
        self.device: HeatStationDevice | None = None

    def pid(self, pcode: str) -> uuid.UUID:
        return self.projects[pcode].id

    def uid(self, key: str) -> uuid.UUID:
        return self.users[key].id

    def zone(self, pcode: str, code: str) -> Zone:
        return self.zones[(pcode, code)]

    def seq(self, kind: str, pcode: str) -> int:
        c = self.counters.setdefault((kind, pcode), itertools.count(1))
        while True:
            n = next(c)
            if n not in self.reserved[(kind, pcode)]:
                return n


def already_seeded(db: Session) -> bool:
    return db.scalar(select(HeatInstrument.id).limit(1)) is not None


# ---- A.7 settings, A.2 instruments / devices / points, A.3 stations -----------------------------


def _settings(ctx: Ctx) -> None:
    for code in ("ANIA-EXP", "RBT-52"):
        s = ctx.db.get(HeatSettings, ctx.pid(code))
        if s is None:
            s = HeatSettings(project_id=ctx.pid(code), values={})
            ctx.db.add(s)
        s.heat_register_from = date(2026, 5, 1)
        s.heat_ptw_enforcement_from = date(2026, 10, 1)
    ctx.db.flush()
    hc.clear_cache(ctx.db)
    hc.ensure_table(ctx.db)


INSTRUMENTS = [
    # no, project, seq, kind, model, serial, valid_until
    ("HSM-ANIA-EXP-01", "ANIA-EXP", 1, InstrumentKind.fixed_station, "WBGT station WS-200",
     "TEST-WS-0001", date(2027, 3, 31)),
    ("HSM-ANIA-EXP-02", "ANIA-EXP", 2, InstrumentKind.handheld_meter, "Handheld WBGT HM-50",
     "TEST-HM-0002", date(2026, 10, 20)),
    ("HSM-RBT-52-01", "RBT-52", 1, InstrumentKind.handheld_meter, "Handheld WBGT HM-50",
     "TEST-HM-0003", date(2027, 2, 28)),
]  # fmt: skip
POINTS = [
    # code, project, site, instrument, source, zones
    ("P-SAIR-STN", "ANIA-EXP", "S-AIR", "HSM-ANIA-EXP-01", PointSourceKind.station,
     ["Z-APR-21", "Z-TWB", "Z-ILS33R"]),
    ("P-SLAND-M1", "ANIA-EXP", "S-LAND", "HSM-ANIA-EXP-02", PointSourceKind.manual, ["Z-LAY1"]),
    ("P-STWR-M1", "RBT-52", "S-TWR", "HSM-RBT-52-01", PointSourceKind.manual,
     ["Z-TC01", "Z-FAC"]),
]  # fmt: skip
STATIONS = [
    ("RS-SAIR-01", "ANIA-EXP", "S-AIR", ["Z-APR-21"], StationType.cooled_cabin,
     Cooling.air_conditioning, 20),
    ("RS-SAIR-02", "ANIA-EXP", "S-AIR", ["Z-TWB", "Z-ILS33R"], StationType.mobile_shade_unit,
     Cooling.misting, 12),
    ("RS-SLAND-01", "ANIA-EXP", "S-LAND", ["Z-LAY1"], StationType.shaded_shelter, Cooling.fans,
     30),
    ("RS-SLAND-02", "ANIA-EXP", "S-LAND", ["Z-PIERB", "Z-MSCP"], StationType.indoor_rest_area,
     Cooling.air_conditioning, 40),
    ("RS-TWR-01", "RBT-52", "S-TWR", ["Z-TC01"], StationType.cooled_cabin,
     Cooling.air_conditioning, 25),
    ("RS-TWR-02", "RBT-52", "S-POD", ["Z-FAC"], StationType.shaded_shelter, Cooling.fans, 15),
]  # fmt: skip


def _registers(ctx: Ctx) -> None:
    db = ctx.db
    for no, pc, seq, kind, model, serial, until in INSTRUMENTS:
        x = HeatInstrument(
            id=uuid.uuid4(),
            instrument_no=no,
            project_id=ctx.pid(pc),
            seq=seq,
            kind=kind,
            make_model=model,
            serial_no=serial,
            iso7243_compliant=True,
            calibration_valid_until=until,
            calibration_cert_ref=f"TEST-CAL-{seq:03d}-{pc}",
            status=InstrumentStatus.active,
        )
        db.add(x)
        ctx.instruments[no] = x
    db.flush()
    st = ctx.instruments["HSM-ANIA-EXP-01"]
    ctx.device = HeatStationDevice(
        id=uuid.uuid4(),
        project_id=st.project_id,
        instrument_id=st.id,
        device_id="DEV-WS-ANIA-01",
        label="S-AIR weather station (TEST)",
        token_hash=token_digest(secrets.token_urlsafe(32)),
        registered_at=at(date(2026, 4, 20), 9),
        registered_by_user_id=ctx.uid("noura.qahtani"),
        last_seen_at=at(date(2026, 10, 6), 10),
        seed_fake=True,
    )
    db.add(ctx.device)
    for code, pc, site, ins, src, zones in POINTS:
        pt = MonitoringPoint(
            id=uuid.uuid4(),
            project_id=ctx.pid(pc),
            point_code=code,
            site_id=ctx.sites[(pc, site)].id,
            zone_ids=[ctx.zone(pc, z).id for z in zones],
            source_kind=src,
            instrument_id=ctx.instruments[ins].id,
            solar_load=True,
            active=True,
        )
        db.add(pt)
        ctx.points[code] = pt
    for code, pc, site, zones, typ, cooling, cap in STATIONS:
        rs = RestStation(
            id=uuid.uuid4(),
            project_id=ctx.pid(pc),
            station_code=code,
            site_id=ctx.sites[(pc, site)].id,
            zone_ids=[ctx.zone(pc, z).id for z in zones],
            station_type=typ,
            capacity_persons=cap,
            cooling=cooling,
            active=True,
        )
        db.add(rs)
        ctx.stations[code] = rs
    db.flush()


# ---- readings (A.4, A.6, A.8) --------------------------------------------------------------------

A4_STATION = ["24.1", "24.6", "25.0", "25.3", "25.7", "26.0", "26.3", "26.6", "26.8", "26.7",
              "26.8", "26.9", "26.9", "27.0", "26.9", "27.2", "27.8"]  # fmt: skip
SEPT = (date(2026, 9, 1), date(2026, 9, 30))
STATION_R4_DAYS = [d for d in range(1, 27) if d not in (17, 22)]  # 24 days, 09-26 = 1 h
RBT_R4_DAYS = list(range(1, 20))  # 19 days × 2 h


def _daily_max(d: date, rng_seed: int) -> D:
    """A.6 daily maxima: May 27–30, Jun–Aug 29–33 (pseudo-random, deterministic)."""
    x = (d.toordinal() * 7919 + rng_seed * 104729) % 1000 / 1000
    lo, hi = (27.0, 30.0) if d.month == 5 else (29.0, 33.0)
    return D(str(round(lo + (hi - lo) * x, 1)))


def _curve(d: date, h: int, mi: int, mx: D) -> D:
    """06:00 → 13:30 rising, → 20:00 falling; 06:00 = max − 6 °C."""
    t = h + mi / 60
    lo = mx - D(6)
    shape = (t - 6) / 7.5 if t <= 13.5 else max(0.0, 1 - (t - 13.5) / 9)
    v = lo + (mx - lo) * D(str(round(math.sin(shape * math.pi / 2), 4)))
    return hc.q1(v)


@dataclass
class Rows:
    rows: list[dict[str, Any]]
    seq: dict[tuple[uuid.UUID, date], int]


def _reading(
    ctx: Ctx, rows: Rows, pc: str, pt: str, when: datetime, w: D, user: str | None
) -> None:
    point = ctx.points[pt]
    d = when.astimezone(RIYADH).date()
    key = (point.project_id, d)
    n = rows.seq.get(key, 0) + 1
    rows.seq[key] = n
    station = point.source_kind == PointSourceKind.station
    t = ctx._table  # type: ignore[attr-defined]
    rows.rows.append(
        {
            "id": uuid.uuid4(),
            "reading_no": f"WBG-{pc}-{d.strftime('%Y%m%d')}-{n:04d}",
            "project_id": point.project_id,
            "local_date": d,
            "seq": n,
            "point_id": point.id,
            "zone_id": None,
            "permit_id": None,
            "measured_at": when,
            "source": ReadingSource.station if station else ReadingSource.manual,
            "instrument_id": point.instrument_id,
            "device_pk": ctx.device.id if station and ctx.device else None,
            "ta_c": None,
            "tnwb_c": None,
            "tg_c": None,
            "rh_pct": None,
            "wbgt_entered_c": None if station else w,
            "wbgt_c": w,
            "regime_cells": hc.cells(t, D("0.0"), w),
            "recorded_by_user_id": ctx.uid(user) if user else None,
            "late_entry": False,
            "status": RecordStatus.valid,
            "voided_at": None,
            "voided_by_user_id": None,
            "void_reason": None,
            "created_at": when + timedelta(minutes=1),
            "seed_fake": True,
        }
    )


def _readings(ctx: Ctx) -> None:
    ctx._table = hc.table(ctx.db)  # type: ignore[attr-defined]
    rows = Rows([], {})
    sept0, sept1 = SEPT
    for d in days(*SEASON):
        sept = sept0 <= d <= sept1
        # station P-SAIR-STN every 15 min 06:00–20:00 (numbered first on each date)
        mx = CAP if sept else _daily_max(d, 1)
        for i in range(57):
            h, mi = 6 + i // 4, (i % 4) * 15
            if sept and d.day == 17 and h in (10, 11):
                continue  # A.8: 2 uncovered slots
            w = _curve(d, h, mi, mx)
            if sept and d.day in STATION_R4_DAYS:
                end = (13, 30) if d.day != 26 else (12, 30)
                if (12, 0) <= (h, mi) <= end:
                    w = R4_VALUE
            if sept and d.day == 22 and (h, mi) == (13, 45):
                w = D("30.4")  # HS6
            if w > CAP and sept and w != R4_VALUE:
                w = CAP
            _reading(ctx, rows, "ANIA-EXP", "P-SAIR-STN", at(d, h, mi), w, None)
        # manual points hourly 07:00–17:00
        for pt, pc, user, miss_to, r4_days in (
            ("P-SLAND-M1", "ANIA-EXP", "fahad.mutairi", 18, ()),
            ("P-STWR-M1", "RBT-52", "lina.haddad", 20, RBT_R4_DAYS),
        ):
            mx = CAP if sept else _daily_max(d, 2 if pc == "ANIA-EXP" else 3) - D("0.3")
            for h in range(7, 18):
                if sept and h == 7 and d.day <= miss_to:
                    continue
                w = _curve(d, h, 0, mx)
                if sept and d.day in r4_days and h in (12, 13):
                    w = R4_VALUE
                _reading(ctx, rows, pc, pt, at(d, h), w, user)
    # A.4: 2026-10-06
    d = date(2026, 10, 6)
    for i, v in enumerate(A4_STATION):
        _reading(ctx, rows, "ANIA-EXP", "P-SAIR-STN", at(d, 6 + i // 4, (i % 4) * 15), D(v), None)
    _reading(ctx, rows, "ANIA-EXP", "P-SLAND-M1", at(d, 8), D("25.9"), "fahad.mutairi")
    _reading(ctx, rows, "ANIA-EXP", "P-SLAND-M1", at(d, 9), D("26.8"), "fahad.mutairi")
    _reading(ctx, rows, "RBT-52", "P-STWR-M1", at(d, 9), D("25.4"), "lina.haddad")
    for i in range(0, len(rows.rows), 2000):
        ctx.db.execute(insert(WbgtReading), rows.rows[i : i + 2000])
    ctx.db.flush()


# ---- patrols, exemptions (A.5, A.6, A.8) ---------------------------------------------------------

BAN = (date(2026, 6, 15), date(2026, 9, 15))
ANIA_REQ = ["Z-APR-21", "Z-TWB", "Z-ILS33R", "Z-LAY1"]
RBT_REQ = ["Z-TC01", "Z-FAC"]
SEPT_MISSED = {("Z-ILS33R", 3), ("Z-TWB", 10)}
SUMMER_MISSED = {
    ("Z-TWB", date(2026, 6, 20)), ("Z-ILS33R", date(2026, 6, 27)), ("Z-LAY1", date(2026, 7, 4)),
    ("Z-APR-21", date(2026, 7, 11)), ("Z-TWB", date(2026, 7, 18)), ("Z-ILS33R", date(2026, 7, 25)),
    ("Z-LAY1", date(2026, 8, 1)), ("Z-APR-21", date(2026, 8, 8)), ("Z-TWB", date(2026, 8, 15)),
    ("Z-ILS33R", date(2026, 8, 22)),
}  # fmt: skip
SUMMER_VIOLATIONS = {
    ("Z-LAY1", date(2026, 6, 18)): ("SAHARA", 3, "carrying rebar in direct sun"),
    ("Z-APR-21", date(2026, 6, 29)): ("GULFPAVE", 2, "line marking on the apron"),
    ("Z-LAY1", date(2026, 7, 7)): ("RAWABI", 4, "formwork in direct sun"),
    ("Z-TWB", date(2026, 7, 14)): ("GULFPAVE", 3, "kerb laying"),
    ("Z-LAY1", date(2026, 7, 28)): ("SAHARA", 2, "scaffold dismantling"),
    ("Z-ILS33R", date(2026, 8, 5)): ("NAJD", 3, "cable trench backfilling"),
    ("Z-LAY1", date(2026, 8, 19)): ("RAWABI", 5, "unloading blocks"),
}  # fmt: skip
NAMED_PATROLS = {
    ("Z-LAY1", date(2026, 9, 8)): (188, (12, 40), "fahad.mutairi", "SAHARA", 4,
                                   "loading scaffold tubes in direct sun", date(2026, 9, 9)),
    ("Z-LAY1", date(2026, 9, 14)): (214, (13, 15), "noura.qahtani", "RAWABI", 3,
                                    "unloading cement bags", date(2026, 9, 15)),
}  # fmt: skip


def _patrol(
    ctx: Ctx, pc: str, zone: str, when: datetime, user: str, outcome: PatrolOutcome,
    seq: int | None = None, eng: str | None = None, headcount: int | None = None,
    activity: str | None = None, exemption: str | None = None,
) -> BanPatrol:  # fmt: skip
    n = seq if seq is not None else ctx.seq("patrol", pc)
    x = BanPatrol(
        id=uuid.uuid4(),
        year=2026,
        seq=n,
        patrol_no=f"MBP-{pc}-2026-{n:05d}",
        project_id=ctx.pid(pc),
        zone_id=ctx.zone(pc, zone).id,
        checked_at=when,
        checked_by_user_id=ctx.uid(user),
        outcome=outcome,
        engagement_id=ctx.engs[(pc, eng)].id if eng else None,
        headcount=headcount,
        activity=activity,
        exemption_ref=exemption,
        permit_id=None,
        photo_ids=[],
        ca_id=None,
        status=RecordStatus.valid,
    )
    ctx.db.add(x)
    return x


def _closed_ca(ctx: Ctx, x: BanPatrol, z: Zone, closed: date) -> None:
    eng = x.engagement_id
    assert eng is not None  # noqa: S101
    ca = hc.make_ca(
        ctx.db, x.project_id, x.id, z.site_id, z.id, eng,
        f"Midday-ban violation {x.patrol_no} in {z.code}",
        f"{x.headcount} workers {x.activity} during the midday ban ({x.patrol_no}). Stop outdoor "
        "work 12:00–15:00 or obtain an exemption.",
        closed, ctx.uid("noura.qahtani"),
    )  # fmt: skip
    d0 = x.checked_at.astimezone(RIYADH).date()
    ca.created_date = d0
    ca.due_date = ca.original_due_date = d0 + timedelta(days=1)
    ca.status = CaStatus.closed
    ca.completed_at = at(closed, 10)
    ca.verified_at = at(closed, 11)
    ca.closed_at = at(closed, 11)
    x.ca_id = ca.id


def _patrols(ctx: Ctx) -> None:
    for (_z, _d), v in NAMED_PATROLS.items():
        ctx.reserved[("patrol", "ANIA-EXP")].add(v[0])
    recorder = {"Z-APR-21": "omar.siddiqui", "Z-TWB": "omar.siddiqui",
                "Z-ILS33R": "omar.siddiqui", "Z-LAY1": "fahad.mutairi"}  # fmt: skip
    named: list[tuple[BanPatrol, Zone, date]] = []
    for i, d in enumerate(days(*BAN)):
        sept = d.month == 9
        for j, zc in enumerate(ANIA_REQ):
            if (sept and (zc, d.day) in SEPT_MISSED) or (zc, d) in SUMMER_MISSED:
                continue
            ok = (
                PatrolOutcome.no_outdoor_work
                if (i + j) % 2
                else PatrolOutcome.compliant_shaded_or_indoor
            )
            nm = NAMED_PATROLS.get((zc, d))
            if nm is not None:
                seq, (h, mi), user, eng, hcnt, act, closed = nm
                x = _patrol(ctx, "ANIA-EXP", zc, at(d, h, mi), user, PatrolOutcome.violation,
                            seq, eng, hcnt, act)  # fmt: skip
                named.append((x, ctx.zone("ANIA-EXP", zc), closed))
                continue
            sv = SUMMER_VIOLATIONS.get((zc, d))
            if sv is not None:
                _patrol(ctx, "ANIA-EXP", zc, at(d, 13, 5), recorder[zc], PatrolOutcome.violation,
                        None, sv[0], sv[1], sv[2])  # fmt: skip
            elif zc == "Z-LAY1" and d in (date(2026, 7, 20), date(2026, 7, 21)):
                _patrol(ctx, "ANIA-EXP", zc, at(d, 13, 0), recorder[zc], PatrolOutcome.exempt_work,
                        None, "RAWABI", 6, "water main repair under exemption",
                        "MBX-ANIA-EXP-2026-004")  # fmt: skip
            else:
                _patrol(ctx, "ANIA-EXP", zc, at(d, 12, 20 + j * 10), recorder[zc], ok)
            if sept and zc == "Z-APR-21" and d.day <= 12:  # A.8: 70 patrols
                _patrol(ctx, "ANIA-EXP", zc, at(d, 14, 30), "noura.qahtani",
                        PatrolOutcome.no_outdoor_work)  # fmt: skip
        for j, zc in enumerate(RBT_REQ):
            _patrol(ctx, "RBT-52", zc, at(d, 12, 30 + j * 15), "lina.haddad",
                    PatrolOutcome.compliant_shaded_or_indoor)  # fmt: skip
            if sept and zc == "Z-TC01" and d.day <= 2:  # A.8: 32 patrols
                _patrol(ctx, "RBT-52", zc, at(d, 14, 40), "lina.haddad",
                        PatrolOutcome.no_outdoor_work)  # fmt: skip
    ctx.db.flush()
    for x, z, closed in named:
        _closed_ca(ctx, x, z, closed)
    ctx.db.flush()


EXEMPTIONS = [
    (1, "SAHARA", ["Z-LAY1"], date(2026, 6, 22), date(2026, 6, 23), BanExemptionReason.emergency_repair,  # noqa: E501
     "Burst pipe repair; shade canopy; 15/45 regime; water station at the work front"),
    (2, "GULFPAVE", ["Z-APR-21"], date(2026, 7, 2), date(2026, 7, 2),
     BanExemptionReason.emergency_repair,
     "Apron joint failure repair; shade canopy; 15/45 regime; paramedic on standby"),
    (3, "NAJD", ["Z-ILS33R"], date(2026, 8, 12), date(2026, 8, 13),
     BanExemptionReason.emergency_repair,
     "ILS cable fault repair; shade canopy; 15/45 regime; cooled cabin within 50 m"),
    (4, "RAWABI", ["Z-LAY1"], date(2026, 7, 20), date(2026, 7, 21),
     BanExemptionReason.emergency_repair,
     "Water main repair; shade canopy; 15/45 regime; paramedic on standby"),
]  # fmt: skip


def _exemptions(ctx: Ctx) -> None:
    for seq, eng, zones, d0, d1, reason, controls in EXEMPTIONS:
        ctx.db.add(
            BanExemption(
                id=uuid.uuid4(),
                year=2026,
                seq=seq,
                exemption_no=f"MBX-ANIA-EXP-2026-{seq:03d}",
                project_id=ctx.pid("ANIA-EXP"),
                engagement_id=ctx.engs[("ANIA-EXP", eng)].id,
                zone_ids=[ctx.zone("ANIA-EXP", z).id for z in zones],
                date_from=d0,
                date_to=d1,
                reason=reason,
                controls_en=controls,
                controls_ar="ضوابط: مظلة، نظام عمل وراحة 15/45، مياه باردة",
                granted_by_user_id=ctx.uid("faisal.harbi"),
                granted_at=at(d0 - timedelta(days=1), 16),
                status=BanExemptionStatus.expired,
                status_reason="date_to passed",
                alerts_sent=["ending"],
            )
        )
    ctx.db.flush()


# ---- welfare checks (A.5, A.8) ---------------------------------------------------------------

SLAND02_MISSED = {5, 12, 19, 26}
CRIT = WelfareItem.HW01
NONCRIT = WelfareItem.HW03


def _items(na: bool, fail: WelfareItem | None) -> list[dict[str, Any]]:
    out = []
    for i in WelfareItem:
        a = CheckAnswer.pass_
        if na and i == WelfareItem.HW02:
            a = CheckAnswer.na
        if fail is not None and i == fail:
            a = CheckAnswer.fail
        out.append({"item": i.value, "answer": a.value, "note": None})
    return out


def _welfare(ctx: Ctx) -> None:
    rows: list[dict[str, Any]] = []
    checker = {"RS-SAIR-01": "omar.siddiqui", "RS-SAIR-02": "omar.siddiqui",
               "RS-SLAND-01": "fahad.mutairi", "RS-SLAND-02": "fahad.mutairi",
               "RS-TWR-01": "lina.haddad", "RS-TWR-02": "lina.haddad"}  # fmt: skip
    ctx.reserved[("welfare", "ANIA-EXP")].add(3117)
    # September plan per project: (n.a. count, non-critical fails, critical fails)
    plan = {"ANIA-EXP": (40, 27, 6), "RBT-52": (20, 12, 2)}
    k = {"ANIA-EXP": 0, "RBT-52": 0}
    for d in days(*SEASON):
        for code, pc, *_rest in STATIONS:
            st = ctx.stations[code]
            sept = d.month == 9
            if sept and code == "RS-SLAND-02" and d.day in SLAND02_MISSED:
                continue
            named = code == "RS-SAIR-01" and d == date(2026, 9, 22)
            na, fail = False, None
            if sept and not named:
                n_na, n_nc, n_cr = plan[pc]
                i = k[pc]
                k[pc] += 1
                if i < n_na:
                    na = True
                elif i < n_na + n_nc:
                    fail = NONCRIT
                elif i < n_na + n_nc + n_cr:
                    fail = CRIT
            seq = 3117 if named else ctx.seq("welfare", pc)
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "year": 2026,
                    "seq": seq,
                    "check_no": f"HWC-{pc}-2026-{seq:05d}",
                    "project_id": st.project_id,
                    "station_id": st.id,
                    "engagement_id": None,
                    "checked_at": at(d, 7, 30),
                    "checked_by_user_id": ctx.uid(checker[code]),
                    "items": _items(na, fail),
                    "water_temp_c": None if na else (D("12.5") if sept else D("12.0")),
                    "persons_present": 6,
                    "ca_ids": [],
                    "status": RecordStatus.valid,
                    "void_reason": None,
                }
            )
    ctx.db.execute(insert(HeatWelfareCheck), rows)
    ctx.db.flush()


# ---- acclimatisation plans (A.5, A.8) ------------------------------------------------------------


def _plan_days(cfg: hc.Cfg, sched: list[int], dates: list[date], who: str, bad: bool) -> list[Any]:
    out = []
    for i, (pct, d) in enumerate(zip(sched, dates, strict=True), start=1):
        followed = not (bad and i == 3)
        out.append(
            {
                "day_no": i,
                "work_date": d.isoformat(),
                "max_pct": pct,
                "max_minutes": int(D(pct) * cfg.dec("standard_shift_hours") * 60 / 100),
                "confirmed_by": who,
                "confirmed_at": at(d, 18).isoformat(),
                "followed": followed,
                "note": None if followed else "Worked the full shift in the sun on day 3.",
            }
        )
    return out


def _plans(ctx: Ctx) -> None:
    db = ctx.db
    ctx.reserved[("plan", "ANIA-EXP")].add(412)
    used: set[uuid.UUID] = set()
    for pc, n, bad_n in (("ANIA-EXP", 48, 4), ("RBT-52", 9, 0)):
        cfg = hc.cfg(db, ctx.pid(pc))
        sched = list(cfg["acclimatisation_schedules"]["new_worker"])
        deps = list(
            db.scalars(
                select(Deployment)
                .join(Worker, Worker.id == Deployment.worker_id)
                .where(
                    Deployment.project_id == ctx.pid(pc),
                    Deployment.status == DeploymentStatus.mobilised,
                    Worker.seq >= 1000,
                    Worker.person_type == WorkerPersonType.contractor_worker,
                )
                .order_by(Worker.seq)
            )
        )
        deps = [x for x in deps if x.trade.value in HEAT_TRADES and x.worker_id not in used][:n]
        if len(deps) < n:
            raise RuntimeError(f"seed_heat: {len(deps)} deployments < {n} on {pc}")
        who = str(ctx.uid("noura.qahtani" if pc == "ANIA-EXP" else "lina.haddad"))
        for i, dep in enumerate(deps):
            used.add(dep.worker_id)
            end = date(2026, 9, 5 + i % 25)
            dates = [end - timedelta(days=4 - j) for j in range(5)]
            seq = ctx.seq("plan", pc)
            db.add(
                AcclimatisationPlan(
                    id=uuid.uuid4(),
                    year=2026,
                    seq=seq,
                    plan_no=f"ACP-{pc}-2026-{seq:05d}",
                    project_id=dep.project_id,
                    deployment_id=dep.id,
                    worker_id=dep.worker_id,
                    engagement_id=dep.engagement_id,
                    plan_type=PlanType.new_worker,
                    trigger={
                        "kind": PlanTriggerKind.mobilisation.value,
                        "on": dates[0].isoformat(),
                    },
                    trigger_date=dates[0],
                    schedule_pct=sched,
                    days=_plan_days(cfg, sched, dates, who, i < bad_n),
                    status=PlanStatus.completed,
                    completed_on=end,
                    ended_at=at(end + timedelta(days=1), 0, 7),
                    alerts_sent=[],
                )
            )
    # Ganesh: ACP-ANIA-EXP-2026-00412, post_heat_illness, Waiting Restriction (HS4d)
    from app.services.heat import plans as hplans  # noqa: PLC0415
    from app.services.med import common as mcommon  # noqa: PLC0415

    g = db.scalar(select(Worker).where(Worker.worker_no == "WKR-000033"))
    assert g is not None  # noqa: S101
    gdep = mcommon.deployment(db, g.id, ctx.pid("ANIA-EXP"))
    assert gdep is not None  # noqa: S101
    cfg = hc.cfg(db, ctx.pid("ANIA-EXP"))
    sched = list(cfg["acclimatisation_schedules"]["returner"])
    db.add(
        AcclimatisationPlan(
            id=uuid.uuid4(),
            year=2026,
            seq=412,
            plan_no="ACP-ANIA-EXP-2026-00412",
            project_id=gdep.project_id,
            deployment_id=gdep.id,
            worker_id=g.id,
            engagement_id=gdep.engagement_id,
            plan_type=PlanType.post_heat_illness,
            trigger={
                "kind": PlanTriggerKind.hold_release.value,
                "ref": "MFH-ANIA-EXP-2026-00019",
                "on": "2026-09-23",
            },
            trigger_date=date(2026, 9, 23),
            schedule_pct=sched,
            days=hplans._days(cfg, sched),
            status=PlanStatus.waiting_restriction,
            alerts_sent=[],
        )
    )
    db.flush()


# ---- §11.2 item 5 and the heat-illness log (A.5, A.6, HS6, HS8) ------------------------------

# month → (MTC wanted, FAC wanted) per project (HS8; RBT: 2 FAC in July)
WANT = {
    "ANIA-EXP": {6: (2, 3), 7: (2, 4), 8: (1, 3), 9: (1, 0)},
    "RBT-52": {7: (0, 2)},
}


def _cases(ctx: Ctx, pc: str) -> list[tuple[InjuryCase, Incident]]:
    db = ctx.db
    rows = db.execute(
        select(InjuryCase, Incident)
        .join(Incident, Incident.id == InjuryCase.incident_id)
        .where(
            Incident.project_id == ctx.pid(pc),
            Incident.occurred_date >= SEASON[0],
            Incident.occurred_date <= SEASON[1],
            Incident.work_related.is_(True),
            Incident.status != IncidentStatus.voided,
        )
        .order_by(Incident.occurred_at, Incident.ref, InjuryCase.person_no)
    )
    return list(rows)


def _cat(c: InjuryCase) -> str:
    return (c.confirmed_category or c.derived_category).value


def _heat_cases(ctx: Ctx) -> dict[str, list[tuple[InjuryCase, Incident]]]:
    out: dict[str, list[tuple[InjuryCase, Incident]]] = {}
    for pc, months in WANT.items():
        rows = _cases(ctx, pc)
        chosen: list[tuple[InjuryCase, Incident]] = []
        for m, (n_mtc, n_fac) in months.items():
            for cat, n in (("MTC", n_mtc), ("FAC", n_fac)):
                pool = [(c, i) for c, i in rows if i.occurred_date.month == m and _cat(c) == cat]
                heat = [x for x in pool if x[0].nature.value in ("heat_exhaustion", "heat_stroke")]
                other = [x for x in pool if x not in heat]
                pick = (heat + other)[:n]
                if len(pick) < n:
                    raise RuntimeError(f"seed_heat: {pc} {m:02d} {cat}: {len(pick)} < {n}")
                for c, _i in pick:
                    if c.nature.value not in ("heat_exhaustion", "heat_stroke"):
                        c.nature = type(c.nature)("heat_exhaustion")
                chosen += pick
        out[pc] = sorted(chosen, key=lambda x: x[1].occurred_at)
    ctx.db.flush()
    return out


def _heat_awr(ctx: Ctx) -> None:
    """HS6: Ganesh's HEAT-AWR is in force on 2026-09-22. The Phase 5 seed gives him a record
    completed 2026-09-24 only, so the previous year's record (2025-09-24 → 2026-09-23) is added
    (a clone of that record with its own number and certificate)."""
    from sqlalchemy import func  # noqa: PLC0415

    from app.models import TrainingRecord  # noqa: PLC0415

    db = ctx.db
    g = db.scalar(select(Worker).where(Worker.worker_no == "WKR-000033"))
    if g is None:
        return
    cur = db.scalar(
        select(TrainingRecord).where(
            TrainingRecord.worker_id == g.id, TrainingRecord.course_code == "HEAT-AWR"
        )
    )
    if cur is None or cur.completed_on <= date(2026, 9, 22):
        return
    seq = int(db.scalar(select(func.max(TrainingRecord.seq))) or 0) + 1
    cols = {c.key: getattr(cur, c.key) for c in TrainingRecord.__mapper__.column_attrs}
    for k, v in list(cols.items()):  # the year-earlier record was submitted/reviewed a year ago
        if isinstance(v, datetime):
            cols[k] = v - timedelta(days=365)
    cols.update(
        id=uuid.uuid4(),
        seq=seq,
        record_no=f"TRR-{seq:06d}",
        certificate_no=f"{cur.certificate_no}-2025"[:40],
        completed_on=date(2025, 9, 24),
        valid_until=date(2026, 9, 23),
        printed_expiry=date(2026, 9, 23) if cur.printed_expiry else None,
    )
    db.add(TrainingRecord(**cols))
    db.flush()


def _log(ctx: Ctx) -> None:
    from app.services.heat import log as heat_log  # noqa: PLC0415

    db = ctx.db
    _heat_awr(ctx)
    sept_case = None
    for c, inc in _cases(ctx, "ANIA-EXP"):
        if inc.occurred_date == date(2026, 9, 22) and c.nature.value == "heat_exhaustion":
            inc.occurred_at = at(date(2026, 9, 22), 13, 50)  # §11.2 item 5
            inc.zone_id = ctx.zone("ANIA-EXP", "Z-APR-21").id
            sept_case = c
    db.flush()
    chosen = _heat_cases(ctx)
    noura = ctx.uid("noura.qahtani")
    for pc, rows in chosen.items():
        nums = iter([n for n in range(1, 40) if not (pc == "ANIA-EXP" and n == 14)])
        for c, inc in rows:
            hold = db.scalar(
                select(FitnessHold).where(
                    FitnessHold.source_type == "injury_case", FitnessHold.source_id == c.id
                )
            )
            cx = heat_log.context(db, inc.project_id, inc.occurred_at, inc.zone_id, c.worker_id,
                                  c, hold)  # fmt: skip
            ganesh = c is sept_case
            seq = 14 if ganesh else next(nums)
            answers = {q.value: ReviewAnswer.yes.value for q in ReviewQuestion}
            if ganesh:
                answers[ReviewQuestion.HC3.value] = ReviewAnswer.no.value
            rv_at = at(date(2026, 9, 24), 10) if ganesh else inc.occurred_at + timedelta(days=2)
            review = {
                "answers": answers,
                "factors_text": "Crew worked about 40 min without rest." if ganesh else None,
                "by": str(noura if pc == "ANIA-EXP" else ctx.uid("lina.haddad")),
                "at": rv_at.isoformat(),
            }
            db.add(
                HeatIllnessEntry(
                    id=uuid.uuid4(),
                    year=2026,
                    seq=seq,
                    entry_no=f"HIL-{pc}-2026-{seq:03d}",
                    project_id=inc.project_id,
                    source_type=HeatLogSource.injury_case,
                    source_id=c.id,
                    worker_id=c.worker_id,
                    engagement_id=c.employer_engagement_id,
                    event_at=inc.occurred_at,
                    zone_id=inc.zone_id,
                    context=cx,
                    review=review,
                    control_gap=heat_log.control_gap(cx, review),
                    status=HeatLogStatus.reviewed,
                    hold_id=hold.id if hold else None,
                    alerts_sent=["officer", "manager"],
                )
            )
    db.flush()


# ---- entry point --------------------------------------------------------------------------------


def seed_heat_data(db: Session) -> None:
    if already_seeded(db):
        return
    if db.scalar(select(Project.id).where(Project.code == "ANIA-EXP")) is None:
        return
    ctx = Ctx(db)
    try:
        set_now(SEED_CLOCK)
        _settings(ctx)
        _registers(ctx)
        _readings(ctx)
        _exemptions(ctx)
        _patrols(ctx)
        _welfare(ctx)
        _plans(ctx)
        _log(ctx)
        db.flush()
        hc.clear_cache(db)
    finally:
        set_now(None)


def main() -> int:  # pragma: no cover - CLI
    from app.db.session import get_sessionmaker  # noqa: PLC0415

    with get_sessionmaker()() as db:
        seed_heat_data(db)
        db.commit()
    print("Heat seed loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
