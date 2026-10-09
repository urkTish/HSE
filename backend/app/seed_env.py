# ruff: noqa: E501, C408, N806
"""Phase 6e seed (spec 6e-environmental Appendix A): settings, providers and licences, project
permits, waste streams, storage areas and the August–September consignments (EV1, EV5, A.4), the
instruments, devices, points and September readings (EV2, EV3, EV6), background declaration and
named exceedances (A.5), spills and spill kits (A.6), water, discharge days, the complaint and the
aspects (A.7), and the ENV v2 / WSA / DSN templates with their plans from 2026-10-01 (A.8),
reproducing EV9 for September 2026.

Everything is inserted directly (no alerts; notifications raised while seeding are removed).
Fictional; licence, permit and ticket numbers contain TEST. Differences from Appendix A forced by
the Phase 0–6d world are recorded in DECISIONS."""

from __future__ import annotations

import itertools
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.access_enums import QrKind
from app.core.clock import set_now
from app.core.emergency_enums import (
    AssetStatus,
    AssetType,
    CheckMethod,
    CheckOutcome,
    CheckResult,
)
from app.core.emergency_enums import RecordStatus as ERecordStatus
from app.core.env_enums import (
    AreaStatus,
    AspectCondition,
    AspectStatus,
    Averaging,
    BackgroundSource,
    ComplaintCategory,
    ComplaintChannel,
    ComplaintStatus,
    ConsignmentStatus,
    EnvInstrumentKind,
    EnvInstrumentStatus,
    EnvPermitType,
    EnvReadingSource,
    ExceedanceCause,
    ExceedanceStatus,
    Issuer,
    NoiseArea,
    NoisePeriod,
    Parameter,
    PointKind,
    PointSource,
    ProviderStatus,
    QuantityUnit,
    RecordState,
    Schedule,
    SpillSource,
    SpillStatus,
    SpillSubstance,
    SpillSurface,
    StorageAreaType,
    WasteRoute,
    WaterSource,
)
from app.core.field_enums import ItemType, StopRule, TemplateKind, VersionStatus
from app.core.hse_enums import (
    Activity,
    CaSourceType,
    CaStatus,
    EnvReached,
    InspectionAssigneeRole,
    InspectionFrequency,
    InspectionType,
    Weekday,
)
from app.core.security import token_digest
from app.models import (
    AssetCheck,
    BackgroundDeclaration,
    ChecklistTemplate,
    DischargeDay,
    EmailMessage,
    EmergencyAsset,
    EnvAspect,
    EnvComplaint,
    EnvExceedance,
    EnvInstrument,
    EnvMonitorDevice,
    EnvPermit,
    EnvPoint,
    EnvProvider,
    EnvReading,
    EnvSettings,
    Incident,
    InspectionPlan,
    Notification,
    Spill,
    WasteConsignment,
    WasteStorageArea,
    WasteStream,
    WaterEntry,
)
from app.schemas.env import Requirement
from app.seed_field import _cleanup, _item
from app.seed_heat import Ctx
from app.services.access import common as acommon
from app.services.emergency import reference as eref
from app.services.env import common as ec
from app.services.env import monitoring as mon
from app.services.env import reference as rf
from app.services.env.exceedances import margin

RIYADH = ZoneInfo("Asia/Riyadh")
SEED_CLOCK = datetime(2026, 10, 6, 7, 0, tzinfo=UTC)  # 10:00 Riyadh
NOTIFY_FROM = date(2026, 10, 1)
SEPT = (date(2026, 9, 1), date(2026, 9, 30))
FILL_TO = date(2026, 10, 5)  # readings continue to the day before the clock
D = Decimal
WS = rf.WS


def at(d: date, h: int, mi: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, mi, tzinfo=RIYADH).astimezone(UTC)


def days(d0: date, d1: date) -> list[date]:
    return [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]


def already_seeded(db: Session) -> bool:
    return db.scalar(select(EnvProvider.id).limit(1)) is not None


class ECtx(Ctx):
    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.providers: dict[str, EnvProvider] = {}
        self.licences: dict[str, EnvPermit] = {}
        self.permits: dict[str, EnvPermit] = {}
        self.areas: dict[str, WasteStorageArea] = {}
        self.ins: dict[str, EnvInstrument] = {}
        self.devs: dict[str, EnvMonitorDevice] = {}
        self.pts: dict[str, EnvPoint] = {}
        self.rseq: dict[tuple[uuid.UUID, date], itertools.count[int]] = {}
        self.readings: dict[tuple[str, str, datetime], EnvReading] = {}
        self.faisal = self.uid("faisal.harbi")

    def site(self, pcode: str, code: str) -> Any:
        return self.sites[(pcode, code)]

    def eng(self, pcode: str, short: str) -> uuid.UUID:
        return self.engs[(pcode, short)].id

    def officer(self, pcode: str) -> uuid.UUID:
        return self.uid("noura.qahtani" if pcode == "ANIA-EXP" else "lina.haddad")


# ---- A.1 settings, A.2 providers, A.3 permits ----------------------------------------------------

PROVIDERS: list[tuple[str, str, str, list[str], list[tuple[str, str]], tuple[Any, ...]]] = [
    # code, EN, AR, kinds, facilities, licence (type, issuer, ref, activities, classes, valid_to)
    ("GREENHAUL", "Green Haul Transport (TEST)", "النقل الأخضر (تجريبي)", ["transporter"], [],
     (EnvPermitType.mwan_licence, Issuer.mwan, "MWAN-TR-TEST-1101", ["collection_transport"], ["inert", "non_hazardous"], date(2027, 5, 31))),
    ("HAZMOVE", "HazMove Logistics (TEST)", "هازموف للنقل (تجريبي)", ["transporter"], [],
     (EnvPermitType.mwan_licence, Issuer.mwan, "MWAN-TR-TEST-1102", ["collection_transport"], ["hazardous"], date(2026, 11, 15))),
    ("SEWTANK", "Sewage Tankers Co. (TEST)", "شركة صهاريج الصرف (تجريبي)", ["sewage_tanker"], [],
     (EnvPermitType.mwan_licence, Issuer.mwan, "MWAN-TR-TEST-1103", ["collection_transport"], ["liquid_sewage"], date(2027, 1, 31))),
    ("RECYCON", "Recycon Riyadh (TEST)", "ريسايكون الرياض (تجريبي)", ["recycler"], [("RECYCON-1", "Recycon Riyadh plant")],
     (EnvPermitType.mwan_licence, Issuer.mwan, "MWAN-RC-TEST-2201", ["recycling"], ["inert"], date(2027, 2, 28))),
    ("METALCO", "Metalco Recycling (TEST)", "ميتالكو للتدوير (تجريبي)", ["recycler"], [("METALCO-1", "Metalco yard")],
     (EnvPermitType.mwan_licence, Issuer.mwan, "MWAN-RC-TEST-2202", ["recycling"], ["non_hazardous"], date(2027, 8, 31))),
    ("OILREF", "Oil Re-refinery (TEST)", "مصفاة إعادة تكرير الزيوت (تجريبي)", ["recycler"], [("OILREF-1", "Re-refinery")],
     (EnvPermitType.mwan_licence, Issuer.mwan, "MWAN-TF-TEST-3301", ["recycling", "treatment"], ["hazardous"], date(2027, 3, 31))),
    ("HAZTREAT", "HazTreat Facility (TEST)", "منشأة معالجة النفايات الخطرة (تجريبي)", ["treatment_facility"], [("HAZTREAT-1", "Hazardous treatment plant")],
     (EnvPermitType.mwan_licence, Issuer.mwan, "MWAN-TF-TEST-3302", ["treatment"], ["hazardous"], date(2026, 12, 31))),
    ("RIYADH-LF", "Riyadh Municipal Landfill (TEST)", "مردم الرياض البلدي (تجريبي)", ["landfill"], [("RIYADH-LF", "Municipal landfill")],
     (EnvPermitType.facility_authorisation, Issuer.momrah_municipality, "MUN-LF-TEST-4401", ["disposal"], ["inert", "non_hazardous"], date(2027, 12, 31))),
    ("STP-RUH", "Riyadh Sewage Treatment Plant (TEST)", "محطة معالجة الصرف بالرياض (تجريبي)", ["treatment_facility"], [("STP-RUH", "Sewage treatment plant")],
     (EnvPermitType.facility_authorisation, Issuer.nwc, "NWC-STP-TEST-5501", ["treatment"], ["liquid_sewage"], date(2027, 6, 30))),
    ("ENVLAB", "EnvLab Riyadh (TEST)", "مختبر البيئة بالرياض (تجريبي)", ["environmental_lab"], [],
     (EnvPermitType.lab_accreditation, Issuer.ncec, "NCEC-LAB-TEST-6601", [], [], date(2027, 4, 30))),
]  # fmt: skip

PERMITS: list[tuple[str, int, EnvPermitType, Issuer, str, str, date | None, date | None, date | None]] = [
    # project, seq, type, issuer, requirement, reference, valid_to, applies_from, applies_to
    ("ANIA-EXP", 1, EnvPermitType.ncec_env_permit_construction, Issuer.ncec, "NCEC-CONSTR", "ENVP-TEST-0001", date(2027, 3, 31), None, None),
    ("ANIA-EXP", 2, EnvPermitType.mwan_producer_registration, Issuer.mwan, "MWAN-REG", "MWAN-PRD-TEST-0420", date(2026, 10, 31), None, None),
    ("ANIA-EXP", 3, EnvPermitType.municipal_construction_permit, Issuer.momrah_municipality, "MUN-BLD", "BLD-TEST-7001", date(2027, 6, 30), None, None),
    ("ANIA-EXP", 4, EnvPermitType.cemp_approval, Issuer.airport_operator, "CEMP", "CEMP-TEST-AOP-3", None, None, None),
    ("RBT-52", 1, EnvPermitType.ncec_env_permit_construction, Issuer.ncec, "NCEC-CONSTR", "ENVP-TEST-0052", date(2027, 1, 31), None, None),
    ("RBT-52", 2, EnvPermitType.mwan_producer_registration, Issuer.mwan, "MWAN-REG", "MWAN-PRD-TEST-0521", date(2027, 2, 28), None, None),
    ("RBT-52", 3, EnvPermitType.municipal_construction_permit, Issuer.momrah_municipality, "MUN-BLD", "BLD-TEST-7052", date(2027, 9, 30), None, None),
    ("RBT-52", 4, EnvPermitType.dewatering_discharge_permit, Issuer.nwc, "DEWATER", "DWD-TEST-0310", date(2026, 9, 20), date(2026, 6, 1), date(2026, 12, 31)),
]  # fmt: skip


def _settings(ctx: ECtx) -> None:
    for pc in ("ANIA-EXP", "RBT-52"):
        ctx.db.add(
            EnvSettings(project_id=ctx.pid(pc), env_notifications_from=NOTIFY_FROM, values={})
        )
    ctx.db.flush()
    ec.clear_cache(ctx.db)


def _providers(ctx: ECtx) -> None:
    db = ctx.db
    for i, (code, en, ar, kinds, facs, lic) in enumerate(PROVIDERS):
        pv = EnvProvider(
            id=uuid.uuid4(),
            provider_code=code,
            name_en=en,
            name_ar=ar,
            cr_number=f"10109{i:05d}",
            kinds=kinds,
            contact_email=f"{code.lower()}@example.com",
            phone="+966110000000",
            facilities=[
                {
                    "facility_code": fc_,
                    "name_en": n,
                    "name_ar": n,
                    "city": "Riyadh",
                    "kind": kinds[0],
                }
                for fc_, n in facs
            ],
            status=ProviderStatus.approved,
            created_by_user_id=ctx.faisal,
            seed_fake=True,
        )
        db.add(pv)
        db.flush()
        ptype, issuer, ref, acts, classes, vto = lic
        scope: dict[str, Any] = {"activities": acts, "waste_classes": classes, "site_ids": []}
        if facs:
            scope["facility_code"] = facs[0][0]
        pm = EnvPermit(
            id=uuid.uuid4(),
            record_no=f"EPL-{code}-001",
            provider_id=pv.id,
            seq=1,
            permit_type=ptype,
            issuer=issuer,
            required=True,
            reference_no=ref,
            scope=scope,
            valid_from=date(2025, 6, 1),
            valid_to=vto,
            conditions=[],
            created_by_user_id=ctx.faisal,
            seed_fake=True,
        )
        db.add(pm)
        ctx.providers[code] = pv
        ctx.licences[code] = pm
    db.flush()


def _permits(ctx: ECtx) -> None:
    db = ctx.db
    for pc, seq, ptype, issuer, req, ref, vto, af, at_ in PERMITS:
        pm = EnvPermit(
            id=uuid.uuid4(),
            record_no=f"EPL-{pc}-{seq:03d}",
            project_id=ctx.pid(pc),
            seq=seq,
            permit_type=ptype,
            issuer=issuer,
            requirement_code=req,
            required=True,
            applies_from=af,
            applies_to=at_,
            reference_no=ref,
            scope={"activities": [], "waste_classes": [], "site_ids": []},
            valid_from=date(2026, 6, 1) if req == "DEWATER" else date(2025, 11, 1),
            valid_to=vto,
            conditions=[],
            created_by_user_id=ctx.officer(pc),
            seed_fake=True,
        )
        db.add(pm)
        ctx.permits[f"{pc}:{req}"] = pm
    db.flush()
    ec.clear_cache(db)


# ---- A.4 streams, storage areas, consignments ----------------------------------------------------

STREAMS = {
    "ANIA-EXP": ["inert_cd", "asphalt_planings", "metal_scrap", "wood", "packaging", "used_oil",
                 "general_mixed", "food_domestic", "oily_absorbents", "chemical_containers", "sewage"],
    "RBT-52": ["inert_cd", "metal_scrap", "wood", "packaging", "general_mixed", "paint_solvent"],
}  # fmt: skip

AREAS: list[tuple[str, str, str, str, StorageAreaType, list[str], int | None, bool]] = [
    # project, code, site, zone, type, streams, containment %, lidded
    ("ANIA-EXP", "WSA-SLAND-01", "S-LAND", "Z-LAY1", StorageAreaType.segregated_bay, ["inert_cd", "metal_scrap", "wood", "packaging", "general_mixed"], None, False),
    ("ANIA-EXP", "HWS-SLAND-01", "S-LAND", "Z-LAY1", StorageAreaType.hazardous_store, ["used_oil", "oily_absorbents", "chemical_containers"], 110, True),
    ("ANIA-EXP", "WSA-SLAND-02", "S-LAND", "Z-LAY1", StorageAreaType.compactor, ["food_domestic"], None, True),
    ("ANIA-EXP", "WSA-SAIR-01", "S-AIR", "Z-APR-21", StorageAreaType.sealed_bin_station, ["general_mixed", "packaging"], None, True),
    ("ANIA-EXP", "WSA-SAIR-02", "S-AIR", "Z-TWB", StorageAreaType.segregated_bay, ["asphalt_planings"], None, True),
    ("RBT-52", "WSA-SPOD-01", "S-POD", "Z-B4", StorageAreaType.segregated_bay, ["inert_cd", "metal_scrap", "wood", "packaging", "general_mixed"], None, False),
    ("RBT-52", "HWS-SPOD-01", "S-POD", "Z-B4", StorageAreaType.hazardous_store, ["paint_solvent"], 110, True),
]  # fmt: skip


def _waste_setup(ctx: ECtx) -> None:
    db = ctx.db
    for pc, codes in STREAMS.items():
        for code in codes:
            db.add(
                WasteStream(
                    id=uuid.uuid4(),
                    project_id=ctx.pid(pc),
                    stream_code=code,
                    default_route=WS[code][3],
                    density=WS[code][4],
                    active=True,
                    created_by_user_id=ctx.officer(pc),
                    seed_fake=True,
                )
            )
    for pc, code, site, zone, typ, streams, cont, lid in AREAS:
        acc = [
            {"stream_code": s, "started_on": None} for s in streams if WS[s][2].value == "hazardous"
        ]
        if code == "HWS-SLAND-01":
            acc = [
                {"stream_code": "used_oil", "started_on": None},
                {"stream_code": "oily_absorbents", "started_on": None},
                {"stream_code": "chemical_containers", "started_on": "2026-07-20"},
            ]
        a = WasteStorageArea(
            id=uuid.uuid4(),
            project_id=ctx.pid(pc),
            area_code=code,
            site_id=ctx.site(pc, site).id,
            zone_id=ctx.zone(pc, zone).id,
            type=typ,
            accepted_streams=streams,
            capacity_m3=D("40.0") if typ != StorageAreaType.hazardous_store else D("8.0"),
            secondary_containment_pct=cont,
            covered=typ != StorageAreaType.segregated_bay or lid,
            lidded_secured=lid,
            signage_bilingual=True,
            accumulation=acc,
            status=AreaStatus.active,
            created_by_user_id=ctx.officer(pc),
            seed_fake=True,
        )
        db.add(a)
        ctx.areas[code] = a
    db.flush()


ROUTE_FAC = {
    # stream → (route, facility provider, facility code, transporter)
    "inert_cd": (WasteRoute.recycle, "RECYCON", "RECYCON-1", "GREENHAUL"),
    "asphalt_planings": (WasteRoute.recycle, "RECYCON", "RECYCON-1", "GREENHAUL"),
    "metal_scrap": (WasteRoute.recycle, "METALCO", "METALCO-1", "GREENHAUL"),
    "wood": (WasteRoute.recycle, "METALCO", "METALCO-1", "GREENHAUL"),
    "packaging": (WasteRoute.recycle, "METALCO", "METALCO-1", "GREENHAUL"),
    "used_oil": (WasteRoute.recovery, "OILREF", "OILREF-1", "HAZMOVE"),
    "general_mixed": (WasteRoute.disposal_landfill, "RIYADH-LF", "RIYADH-LF", "GREENHAUL"),
    "food_domestic": (WasteRoute.disposal_landfill, "RIYADH-LF", "RIYADH-LF", "GREENHAUL"),
    "oily_absorbents": (WasteRoute.treatment, "HAZTREAT", "HAZTREAT-1", "HAZMOVE"),
    "paint_solvent": (WasteRoute.treatment, "HAZTREAT", "HAZTREAT-1", "HAZMOVE"),
    "sewage": (WasteRoute.treatment, "STP-RUH", "STP-RUH", "SEWTANK"),
}


class Load:
    def __init__(
        self, stream: str, qty: str, unit: QuantityUnit, net: str | None, **kw: Any
    ) -> None:
        self.stream, self.qty, self.unit, self.net = stream, D(qty), unit, net
        self.kw = kw


def _ania_loads() -> tuple[list[Load], list[Load], list[Load]]:
    """(August, September early 09-01..09-23, September late 09-24..09-30)."""
    T, M3, L = QuantityUnit.t, QuantityUnit.m3, QuantityUnit.L
    aug = (
        [Load("inert_cd", "14.0", T, "14.0") for _ in range(8)]
        + [Load("metal_scrap", "5.5", T, "5.5") for _ in range(3)]
        + [Load("general_mixed", "12", M3, "3.400") for _ in range(3)]
    )
    pool: dict[str, list[Load]] = {
        "inert_cd": [Load("inert_cd", "14.0", T, "14.0") for _ in range(30)],
        "asphalt_planings": [Load("asphalt_planings", "12.5", T, "12.5") for _ in range(12)],
        "metal_scrap": [Load("metal_scrap", "5.5", T, "5.5") for _ in range(7)],
        "wood": [Load("wood", "5.5", T, "5.5") for _ in range(4)],
        "packaging": [Load("packaging", "1.9", T, "1.9") for _ in range(5)],
        "used_oil": [Load("used_oil", "1100", L, "0.980")],
        "general_mixed": [Load("general_mixed", "12", M3, "3.400") for _ in range(16)]
        + [Load("general_mixed", "10", M3, "3.000")],
        "food_domestic": [Load("food_domestic", "6", M3, "2.0") for _ in range(7)],
        "oily_absorbents": [Load("oily_absorbents", "0.6", T, "0.6")],
        "sewage": [Load("sewage", "31", M3, None) for _ in range(10)],
    }
    late_n = {
        "inert_cd": 6,
        "asphalt_planings": 2,
        "metal_scrap": 1,
        "packaging": 1,
        "general_mixed": 3,
        "food_domestic": 2,
        "sewage": 2,
    }
    early: list[Load] = []
    late: list[Load] = []
    for code, xs in pool.items():
        k = late_n.get(code, 0)
        early += xs[: len(xs) - k]
        late += xs[len(xs) - k :]
    # interleave streams for a realistic mix
    early = [x for _, x in sorted(enumerate(early), key=lambda t: (t[0] % 7, t[0]))]
    late = [x for _, x in sorted(enumerate(late), key=lambda t: (t[0] % 5, t[0]))]
    # the general_mixed load received 2 days late (K-121)
    next(x for x in early if x.stream == "general_mixed").kw["late"] = 2
    early.insert(70, Load("used_oil", "1000", L, "0.820", ev5=True))
    late.insert(12, Load("general_mixed", "12", M3, None, ev1b=True))
    return aug, early, late


def _rbt_loads() -> tuple[list[Load], list[Load], list[Load]]:
    T, L = QuantityUnit.t, QuantityUnit.L
    aug = [Load("inert_cd", "10.0", T, "10.0") for _ in range(4)]
    sep = (
        [Load("inert_cd", "10.0", T, "10.0") for _ in range(6)]
        + [
            Load("inert_cd", "10.0", T, "10.0", route=WasteRoute.disposal_landfill)
            for _ in range(6)
        ]
        + [Load("metal_scrap", "4.6", T, "4.6") for _ in range(4)]
        + [Load("wood", "4.0", T, "4.0") for _ in range(3)]
        + [Load("packaging", "2.0", T, "2.0") for _ in range(4)]
        + [Load("general_mixed", "3.0", T, "3.0") for _ in range(8)]
        + [Load("paint_solvent", "1200", L, "1.200") for _ in range(3)]
    )
    sep = [x for _, x in sorted(enumerate(sep), key=lambda t: (t[0] % 6, t[0]))]
    early, late = sep[:26], sep[26:]
    early[3].kw["late"] = 1
    early[17].kw["late"] = 3
    return aug, early, late


def _consignments(ctx: ECtx) -> None:
    db = ctx.db
    rows: list[dict[str, Any]] = []
    for pc in ("ANIA-EXP", "RBT-52"):
        pid = ctx.pid(pc)
        aug, early, late = _ania_loads() if pc == "ANIA-EXP" else _rbt_loads()
        groups = [
            (aug, date(2026, 8, 25), 7),
            (early, date(2026, 9, 1), 23),
            (late, date(2026, 9, 24), 7),
        ]
        seq = itertools.count(330 if pc == "ANIA-EXP" else 120)
        gens = ["RAWABI", "NAJD", "SAHARA"] if pc == "ANIA-EXP" else ["QIMMA", "DLIFT"]
        k = 0
        for loads, d0, span in groups:
            for i, ld in enumerate(loads):
                k += 1
                s = ld.stream
                route, fac, fcode, tr = ROUTE_FAC[s]
                route = ld.kw.get("route", route)
                if route == WasteRoute.disposal_landfill:
                    fac, fcode = "RIYADH-LF", "RIYADH-LF"
                d = d0 + timedelta(days=(i * span) // len(loads))
                hh = 7 + i % 9
                dispatched = at(d, hh, (i * 7) % 60)
                if ld.kw.get("ev5"):
                    d, dispatched = date(2026, 9, 22), at(date(2026, 9, 22), 8, 30)
                if ld.kw.get("ev1b"):
                    d, dispatched = date(2026, 9, 29), at(date(2026, 9, 29), 11, 0)
                n = 412 if ld.kw.get("ev5") else next(seq)
                if n == 412 and not ld.kw.get("ev5"):
                    n = next(seq)
                # area, site and generator
                area: WasteStorageArea | None
                if pc == "ANIA-EXP":
                    gen = gens[k % 3]
                    if s == "asphalt_planings":
                        area, gen = ctx.areas["WSA-SAIR-02"], "GULFPAVE"
                    elif s in ("used_oil", "oily_absorbents"):
                        area = ctx.areas["HWS-SLAND-01"]
                    elif s == "food_domestic":
                        area = ctx.areas["WSA-SLAND-02"]
                    elif s == "sewage":
                        area = None
                    elif (
                        s in ("general_mixed", "packaging") and k % 4 == 0 and not ld.kw.get("ev1b")
                    ):
                        area, gen = ctx.areas["WSA-SAIR-01"], "RAWABI"
                    else:
                        area = ctx.areas["WSA-SLAND-01"]
                    site_id = area.site_id if area else ctx.site(pc, "S-LAND").id
                else:
                    gen = gens[k % 2]
                    area = ctx.areas["HWS-SPOD-01" if s == "paint_solvent" else "WSA-SPOD-01"]
                    site_id = area.site_id
                if ld.kw.get("ev5"):
                    gen = "RAWABI"
                airside = area is not None and area.area_code == "WSA-SAIR-01"
                plate = (
                    ("9012 JTR" if k % 2 else "9006 SXN")
                    if airside
                    else f"{4100 + k} {'RBT' if pc == 'RBT-52' else 'KSA'}"
                )
                dens = WS[s][4]
                est = (
                    ld.qty
                    if ld.unit == QuantityUnit.t
                    else (ld.qty * dens if ld.unit == QuantityUnit.m3 else ld.qty * dens / 1000)
                )
                if s == "sewage":
                    est = D(0)
                due = d + timedelta(days=7)
                if ld.kw.get("ev1b"):
                    recv = None
                elif ld.kw.get("ev5"):
                    recv = at(date(2026, 9, 30), 9, 40)
                elif "late" in ld.kw:
                    recv = at(due + timedelta(days=ld.kw["late"]), 10, 0)
                else:
                    recv = at(
                        min(
                            d + timedelta(days=2 if d < date(2026, 9, 24) else 1), date(2026, 10, 5)
                        ),
                        11,
                        (i * 13) % 60,
                    )
                net = D(ld.net) if ld.net is not None else None
                disc = None
                if net is not None and est:
                    disc = (abs(net - est) / est * 100).quantize(D("0.01"))
                is_haz = WS[s][2].value == "hazardous"
                status = ConsignmentStatus.dispatched
                if recv is not None:
                    status = (
                        ConsignmentStatus.received if ld.kw.get("ev5") else ConsignmentStatus.closed
                    )
                dispatcher = (
                    {"S-LAND": "fahad.mutairi", "S-AIR": "omar.siddiqui"}.get(
                        "S-AIR" if airside or s == "asphalt_planings" else "S-LAND", "fahad.mutairi"
                    )
                    if pc == "ANIA-EXP"
                    else "ibrahim.saleh"
                )
                rows.append(
                    dict(
                        id=uuid.uuid4(),
                        consignment_no=ec.ref("WCN", pc, d.year, n, 5),
                        year=d.year,
                        seq=n,
                        project_id=pid,
                        stream_code=s,
                        storage_area_id=area.id if area else None,
                        site_id=site_id,
                        generator_engagement_id=ctx.eng(pc, gen),
                        quantity=ld.qty,
                        unit=ld.unit,
                        estimated_t=est.quantize(D("0.001")),
                        route=route,
                        transporter_id=ctx.providers[tr].id,
                        transporter_licence_id=ctx.licences[tr].id,
                        facility_provider_id=ctx.providers[fac].id,
                        facility_code=fcode,
                        facility_licence_id=ctx.licences[fac].id,
                        vehicle_plate=plate,
                        driver_name=f"Driver {k:03d} (TEST)",
                        driver_mobile=f"+9665000{k:05d}",
                        mwan_manifest_ref=f"MWAN-MF-TEST-{n:05d}" if is_haz else None,
                        dispatched_at=dispatched,
                        dispatched_date=d,
                        dispatched_by_user_id=ctx.uid(dispatcher),
                        due_on=due,
                        received_at=recv - timedelta(hours=1) if recv else None,
                        received_net_t=net if recv and s != "sewage" else None,
                        ticket_ref=f"TKT-TEST-{pc[:3]}-{n:05d}" if recv else None,
                        receipt_recorded_at=recv,
                        discrepancy_pct=disc if recv and s != "sewage" else None,
                        warnings=[],
                        status=status,
                        closed_at=recv if status == ConsignmentStatus.closed else None,
                        created_at=dispatched,
                        updated_at=recv or dispatched,
                        created_by_user_id=ctx.uid(dispatcher),
                        seed_fake=True,
                    )
                )
    db.execute(insert(WasteConsignment), rows)
    db.flush()


# ---- A.5 instruments, points, readings -----------------------------------------------------------

INSTRUMENTS = [
    ("ANIA-EXP", "EMI-ANIA-EXP-01", EnvInstrumentKind.pm_station, "DustTrak DRX 8533 (TEST)", None, date(2027, 4, 30)),
    ("ANIA-EXP", "EMI-ANIA-EXP-02", EnvInstrumentKind.pm_sampler_24h, "MiniVol TAS (TEST)", None, date(2027, 1, 31)),
    ("ANIA-EXP", "EMI-ANIA-EXP-03", EnvInstrumentKind.sound_level_meter, "Nor140 SLM (TEST)", "1", date(2026, 12, 15)),
    ("RBT-52", "EMI-RBT-52-01", EnvInstrumentKind.pm_sampler_24h, "MiniVol TAS (TEST)", None, date(2027, 2, 28)),
    ("RBT-52", "EMI-RBT-52-02", EnvInstrumentKind.noise_station, "Cirrus Noise Station (TEST)", "1", date(2027, 3, 31)),
]  # fmt: skip

R = Requirement
P, AV, SC = Parameter, Averaging, Schedule
POINTS: list[tuple[str, str, str, str | None, PointKind, PointSource, NoiseArea | None, str | None, list[Requirement]]] = [
    ("ANIA-EXP", "D-SAIR-01", "S-AIR", "Z-TWB", PointKind.airside, PointSource.station, None, "EMI-ANIA-EXP-01",
     [R(parameter=P.pm10, averaging=AV.h1, schedule=SC.continuous), R(parameter=P.pm10, averaging=AV.h24, schedule=SC.continuous)]),
    ("ANIA-EXP", "D-SLAND-01", "S-LAND", "Z-LAY1", PointKind.boundary, PointSource.manual, None, "EMI-ANIA-EXP-02",
     [R(parameter=P.pm10, averaging=AV.h24, schedule=SC.weekly)]),
    ("ANIA-EXP", "V-SAIR", "S-AIR", None, PointKind.work_area, PointSource.visual, None, None,
     [R(parameter=P.visual_dust, averaging=AV.spot, schedule=SC.daily)]),
    ("ANIA-EXP", "V-SLAND", "S-LAND", None, PointKind.work_area, PointSource.visual, None, None,
     [R(parameter=P.visual_dust, averaging=AV.spot, schedule=SC.daily)]),
    ("ANIA-EXP", "N-SLAND-01", "S-LAND", "Z-PIERB", PointKind.boundary, PointSource.manual, NoiseArea.industrial, "EMI-ANIA-EXP-03",
     [R(parameter=P.laeq, averaging=AV.measurement, schedule=SC.weekly, period=NoisePeriod.day, alert_value=D(67), limit_value=D(70), library_ref="NA-industrial-day"),
      R(parameter=P.laeq, averaging=AV.measurement, schedule=SC.weekly, period=NoisePeriod.night, alert_value=D(67), limit_value=D(70), library_ref="NA-industrial-night")]),
    ("RBT-52", "D-STWR-01", "S-TWR", "Z-CORE", PointKind.sensitive_receptor, PointSource.manual, None, "EMI-RBT-52-01",
     [R(parameter=P.pm10, averaging=AV.h24, schedule=SC.weekly)]),
    ("RBT-52", "V-STWR", "S-TWR", None, PointKind.work_area, PointSource.visual, None, None,
     [R(parameter=P.visual_dust, averaging=AV.spot, schedule=SC.daily)]),
    ("RBT-52", "V-SPOD", "S-POD", None, PointKind.work_area, PointSource.visual, None, None,
     [R(parameter=P.visual_dust, averaging=AV.spot, schedule=SC.daily)]),
    ("RBT-52", "N-STWR-01", "S-TWR", "Z-CORE", PointKind.sensitive_receptor, PointSource.station, NoiseArea.mixed_commercial, "EMI-RBT-52-02",
     [R(parameter=P.laeq, averaging=AV.h1, schedule=SC.continuous)]),
    ("RBT-52", "W-SPOD-01", "S-POD", "Z-B4", PointKind.discharge, PointSource.manual, None, None,
     [R(parameter=P.ph, averaging=AV.spot, schedule=SC.daily), R(parameter=P.tss, averaging=AV.spot, schedule=SC.daily),
      R(parameter=P.oil_grease, averaging=AV.spot, schedule=SC.daily)]),
]  # fmt: skip

POINTS_CREATED = at(date(2026, 8, 31), 9, 0)


def _monitoring_setup(ctx: ECtx) -> None:
    db = ctx.db
    for pc, no, ikind, mm, cls, cal in INSTRUMENTS:
        x = EnvInstrument(
            id=uuid.uuid4(),
            project_id=ctx.pid(pc),
            instrument_no=no,
            kind=ikind,
            make_model=mm,
            serial_no=f"SN-TEST-{no[-5:]}",
            standard_class=cls,
            calibration_valid_until=cal,
            calibration_cert_ref=f"CAL-TEST-{no[-5:]}",
            status=EnvInstrumentStatus.active,
            created_by_user_id=ctx.officer(pc),
            seed_fake=True,
        )
        db.add(x)
        ctx.ins[no] = x
    db.flush()
    for pc, dev, ino in (
        ("ANIA-EXP", "DEV-EM-ANIA-01", "EMI-ANIA-EXP-01"),
        ("RBT-52", "DEV-EM-RBT-01", "EMI-RBT-52-02"),
    ):
        d = EnvMonitorDevice(
            id=uuid.uuid4(),
            project_id=ctx.pid(pc),
            instrument_id=ctx.ins[ino].id,
            device_id=dev,
            label=f"{dev} station",
            token_hash=token_digest(secrets.token_urlsafe(32)),
            registered_at=POINTS_CREATED,
            registered_by_user_id=ctx.officer(pc),
            last_seen_at=SEED_CLOCK - timedelta(minutes=1),
            seed_fake=True,
        )
        db.add(d)
        ctx.devs[ino] = d
    for pc, code, site, zn, kind, src, na, ins_no, reqs in POINTS:
        pt = EnvPoint(
            id=uuid.uuid4(),
            project_id=ctx.pid(pc),
            point_code=code,
            site_id=ctx.site(pc, site).id,
            zone_id=ctx.zone(pc, zn).id if zn else None,
            kind=kind,
            noise_area_category=na,
            source_kind=src,
            instrument_id=ctx.ins[ins_no].id if ins_no else None,
            permit_id=ctx.permits["RBT-52:DEWATER"].id if code == "W-SPOD-01" else None,
            requirements=mon.build_requirements(reqs, na),
            active=True,
            created_at=POINTS_CREATED,
            updated_at=POINTS_CREATED,
            created_by_user_id=ctx.officer(pc),
            seed_fake=True,
        )
        db.add(pt)
        ctx.pts[code] = pt
    db.flush()
    # A.5: BGD-RBT-52-2026-001 (NCM warning for 09-03 on S-TWR)
    db.add(
        BackgroundDeclaration(
            id=uuid.uuid4(),
            declaration_no="BGD-RBT-52-2026-001",
            year=2026,
            seq=1,
            project_id=ctx.pid("RBT-52"),
            site_ids=[ctx.site("RBT-52", "S-TWR").id],
            from_at=at(date(2026, 9, 3), 8),
            to_at=at(date(2026, 9, 3), 20),
            source=BackgroundSource.ncm_warning,
            source_ref="NCM-TEST-0903",
            declared_by_user_id=ctx.uid("lina.haddad"),
            created_by_user_id=ctx.uid("lina.haddad"),
            created_at=at(date(2026, 9, 3), 8, 30),
            seed_fake=True,
        )
    )
    db.flush()


def _reading(
    ctx: ECtx, code: str, param: Parameter, avg: Averaging, ws: datetime, we: datetime,
    value: Decimal, source: EnvReadingSource, created: datetime | None = None, **kw: Any,
) -> EnvReading:  # fmt: skip
    """mon.make_reading without the exceedance rules and the per-row flush (named exceedances are
    inserted explicitly)."""
    db = ctx.db
    pt = ctx.pts[code]
    c = ec.cfg(db, pt.project_id)
    day = mon.reading_day(we)
    period = c.period_of(ec.to_local(ws)) if param == Parameter.laeq else NoisePeriod.any
    result, limit = mon.evaluate(db, pt, param, avg, period, value)
    bg = mon.background_ref(db, pt, ws, we) if param in rf.DUST_PARAMS and avg != AV.min15 else None
    seq = next(ctx.rseq.setdefault((pt.project_id, day), itertools.count(1)))
    pc = "ANIA-EXP" if pt.project_id == ctx.pid("ANIA-EXP") else "RBT-52"
    created = created or (we + timedelta(minutes=5))
    warnings: list[str] = []
    if pt.kind == PointKind.discharge and avg != AV.min15:
        pm = ctx.permits["RBT-52:DEWATER"]
        if not ec.permit_valid_on(db, pm, day):
            warnings = ["PERMIT_NOT_VALID"]
    user = kw.pop("user", None)
    if user is None and source not in (EnvReadingSource.station, EnvReadingSource.derived):
        user = ctx.officer(pc)
    r = EnvReading(
        id=uuid.uuid4(),
        reading_no=f"ENR-{pc}-{day:%Y%m%d}-{seq:05d}",
        project_id=pt.project_id,
        day=day,
        seq=seq,
        point_id=pt.id,
        parameter=param,
        averaging=avg,
        period=period,
        window_start=ws,
        window_end=we,
        source=source,
        value=value,
        instrument_id=pt.instrument_id
        if source != EnvReadingSource.lab and pt.source_kind != PointSource.visual
        else None,
        device_pk=ctx.devs[next(k for k, v in ctx.ins.items() if v.id == pt.instrument_id)].id
        if source == EnvReadingSource.station
        else None,
        background=bg is not None,
        background_ref=bg,
        result=result,
        limit_value=limit,
        late_entry=kw.pop("late", False),
        recorded_by_user_id=user,
        photo_ids=[],
        warnings=warnings,
        status=RecordState.valid,
        created_at=created,
        updated_at=created,
        created_by_user_id=user,
        seed_fake=True,
        **kw,
    )
    db.add(r)
    ctx.readings[(code, f"{param.value}:{avg.value}", ws)] = r
    return r


def _hour(d: date, h: int) -> tuple[datetime, datetime]:
    return at(d, h), at(d, h) + timedelta(hours=1)


def _dust_station(ctx: ECtx) -> None:
    """D-SAIR-01 (EV2, EV6): derived hourly values, 24-h values on days with ≥ 75 % hours."""
    hours_on = {date(2026, 9, 5): 17, date(2026, 9, 12): 14}
    named = {
        (date(2026, 9, 16), 10): D("640.0"),
        (date(2026, 9, 16), 11): D("420.0"),
        (date(2026, 9, 28), 5): D("1240.0"),
    }
    quarters = {
        (date(2026, 9, 16), 10): ["610", "655", "640", "655"],
        (date(2026, 9, 28), 5): ["1180", "1260", "1250", "1270"],
    }
    for d in days(SEPT[0], FILL_TO):
        n = hours_on.get(d, 24)
        vals = []
        for h in range(n):
            if d == date(2026, 9, 16) and h not in (10, 11):
                v = D("184.1") if h == 0 else D("183.5")
            else:
                v = named.get((d, h), D(150 + (h * 37 + d.day * 11) % 70))
            ws, we = _hour(d, h)
            for qi, q in enumerate(quarters.get((d, h), [])):
                _reading(ctx, "D-SAIR-01", P.pm10, AV.min15, ws + timedelta(minutes=15 * qi),
                         ws + timedelta(minutes=15 * (qi + 1)), D(q), EnvReadingSource.station,
                         ws + timedelta(minutes=15 * (qi + 1), seconds=20))  # fmt: skip
            _reading(
                ctx,
                "D-SAIR-01",
                P.pm10,
                AV.h1,
                ws,
                we,
                v,
                EnvReadingSource.derived,
                we + timedelta(seconds=40),
            )
            vals.append(v)
        if n * 100 / 24 >= 75:
            _reading(ctx, "D-SAIR-01", P.pm10, AV.h24, at(d, 0), at(d + timedelta(days=1), 0),
                     mon.mean(P.pm10, vals), EnvReadingSource.derived, at(d + timedelta(days=1), 0, 1))  # fmt: skip


def _noise_station(ctx: ECtx) -> None:
    """N-STWR-01 (EV3, EV6): hourly LAeq (day ~59, night ~49), energy-mean 24-h values."""
    quarters = ["60.0", "62.0", "61.0", "62.0"]
    for d in days(SEPT[0], FILL_TO):
        vals = []
        for h in range(24):
            ws, we = _hour(d, h)
            v = (
                D("59.0") + D((h + d.day) % 3) / 2
                if 7 <= h < 22
                else D("49.0") + D((h + d.day) % 3) / 2
            )
            if d == date(2026, 9, 10) and h == 23:
                for qi, q in enumerate(quarters):
                    _reading(ctx, "N-STWR-01", P.laeq, AV.min15, ws + timedelta(minutes=15 * qi),
                             ws + timedelta(minutes=15 * (qi + 1)), D(q), EnvReadingSource.station)  # fmt: skip
                v = mon.mean(P.laeq, [D(q) for q in quarters])
            if d == date(2026, 9, 10) and h == 21:
                v = D("63.0")
            _reading(
                ctx,
                "N-STWR-01",
                P.laeq,
                AV.h1,
                ws,
                we,
                v,
                EnvReadingSource.derived,
                we + timedelta(seconds=40),
            )
            vals.append(v)
        _reading(ctx, "N-STWR-01", P.laeq, AV.h24, at(d, 0), at(d + timedelta(days=1), 0),
                 mon.mean(P.laeq, vals), EnvReadingSource.derived, at(d + timedelta(days=1), 0, 1))  # fmt: skip


def _manual(ctx: ECtx) -> None:
    db = ctx.db
    # weekly 24-h samples and noise measurements
    weekly = {
        "D-SLAND-01": [date(2026, 9, d) for d in (1, 8, 15, 22, 29)],
        "D-STWR-01": [date(2026, 9, d) for d in (3, 9, 16, 23, 30)],
        "N-SLAND-01": [date(2026, 9, d) for d in (2, 9, 16, 23, 30)],
    }
    for code, ds in weekly.items():
        for d in ds:
            if code == "N-SLAND-01":
                _reading(ctx, code, P.laeq, AV.measurement, at(d, 10), at(d, 10, 30), D("64.2"),
                         EnvReadingSource.manual, at(d, 10, 40), field_calibration_checked=True)  # fmt: skip
            else:
                v = (
                    D("410.0")
                    if (code, d) == ("D-STWR-01", date(2026, 9, 3))
                    else D(140 + d.day % 7 * 6)
                )
                _reading(ctx, code, P.pm10, AV.h24, at(d, 0), at(d + timedelta(days=1), 0), v,
                         EnvReadingSource.manual, at(d + timedelta(days=1), 9, 15))  # fmt: skip
    # visual scores (V-SLAND misses 09-19, V-SPOD misses 09-11 and 09-25)
    miss = {"V-SLAND": {date(2026, 9, 19)}, "V-SPOD": {date(2026, 9, 11), date(2026, 9, 25)}}
    for code in ("V-SAIR", "V-SLAND", "V-STWR", "V-SPOD"):
        who = {"V-SAIR": "omar.siddiqui", "V-SLAND": "fahad.mutairi"}.get(code, "ibrahim.saleh")
        for d in days(SEPT[0], FILL_TO):
            if d in miss.get(code, set()):
                continue
            _reading(ctx, code, P.visual_dust, AV.spot, at(d, 9), at(d, 9, 5), D(1 if d.day % 4 else 2),
                     EnvReadingSource.manual, at(d, 9, 6), user=ctx.uid(who))  # fmt: skip
    # W-SPOD-01 lab results (27 sampled days; TSS 85 sampled 09-24, recorded 09-27)
    lab = ctx.providers["ENVLAB"].id
    for d in days(SEPT[0], FILL_TO):
        if d in (date(2026, 9, 5), date(2026, 9, 12), date(2026, 9, 19)):
            continue
        rec = at(d + timedelta(days=1), 14)
        for param, v0 in ((P.ph, D("7.4")), (P.tss, D(28 + d.day % 9)), (P.oil_grease, D("3.2"))):
            v, rec_, late = v0, rec, False
            if (param, d) == (P.tss, date(2026, 9, 24)):
                v, rec_, late = D("85"), at(date(2026, 9, 27), 13), True
            _reading(ctx, "W-SPOD-01", param, AV.spot, at(d, 8), at(d, 8, 15), v, EnvReadingSource.lab,
                     rec_, lab_provider_id=lab, lab_report_ref=f"ENVLAB-TEST-{d:%m%d}", late=late)  # fmt: skip
    db.flush()


def _exceedances(ctx: ECtx) -> None:
    db = ctx.db
    noura, lina = ctx.uid("noura.qahtani"), ctx.uid("lina.haddad")

    def rd(code: str, key: str, d: date, h: int, mi: int = 0) -> EnvReading:
        return ctx.readings[(code, key, at(d, h, mi))]

    def exd(
        pc: str,
        seq: int,
        r: EnvReading,
        cause: ExceedanceCause,
        eng: str | None,
        status: ExceedanceStatus,
        reviewed: datetime,
        ended: datetime,
        act: str | None = None,
        ca: str | None = None,
    ) -> EnvExceedance:
        pt = db.get(EnvPoint, r.point_id)
        assert pt is not None and r.limit_value is not None  # noqa: S101
        x = EnvExceedance(
            id=uuid.uuid4(),
            exceedance_no=ec.ref("ENX", pc, 2026, seq, 4),
            year=2026,
            seq=seq,
            project_id=r.project_id,
            point_id=r.point_id,
            site_id=pt.site_id,
            parameter=r.parameter,
            averaging=r.averaging,
            period=r.period,
            reading_ids=[r.id],
            day=r.day,
            peak_value=r.value,
            limit_value=r.limit_value,
            margin_pct=margin(r.parameter, D(r.value), D(r.limit_value)).quantize(D("0.1")),
            started_at=r.window_start,
            ended_at=ended,
            episode_open=False,
            late_result=r.source == EnvReadingSource.lab,
            suggested_cause=ExceedanceCause.background_natural if r.background else None,
            background_ref=r.background_ref,
            cause=cause,
            responsible_engagement_id=ctx.eng(pc, eng) if eng else None,
            activity_en=act,
            activity_ar=act and "نشاط المشروع",
            immediate_action_en="Activity stopped and water suppression increased."
            if eng
            else None,
            immediate_action_ar="أوقف النشاط وزيد الرش بالمياه." if eng else None,
            reviewed_by_user_id=None
            if cause == ExceedanceCause.background_natural and r.background
            else (noura if pc == "ANIA-EXP" else lina),
            reviewed_at=reviewed,
            status=status,
            created_at=r.created_at,
            updated_at=reviewed,
            seed_fake=True,
        )
        db.add(x)
        db.flush()
        r.exceedance_id = x.id
        if ca is not None:
            set_now(reviewed)
            try:
                cao = ec.make_ca(
                    db,
                    ec.project(db, None, r.project_id),
                    CaSourceType.environmental,
                    x.id,
                    pt.site_id,
                    pt.zone_id,
                    x.responsible_engagement_id,
                    "major",
                    f"{x.exceedance_no}: {act}",
                    f"Exceedance {x.exceedance_no} at {pt.point_code}: {act}.",
                    None,
                    None,
                    x.reviewed_by_user_id,
                )
            finally:
                set_now(SEED_CLOCK)
            cao.seed_fake = True
            x.ca_id = cao.id
            if ca == "closed":
                cao.status = CaStatus.closed
                cao.completed_at = at(date(2026, 9, 19), 15)
                cao.completed_date = date(2026, 9, 19)
                cao.evidence_text = "Spray bars fitted to the milling machine; water bowser added."
                cao.verified_at = at(date(2026, 9, 20), 10)
                cao.verified_date = date(2026, 9, 20)
                cao.verification_comment = "Verified on site."
        return x

    d16, d28 = date(2026, 9, 16), date(2026, 9, 28)
    exd("ANIA-EXP", 17, rd("D-SAIR-01", "pm10:1h", d16, 10), ExceedanceCause.project_activity, "GULFPAVE",
        ExceedanceStatus.closed, at(d16, 14), at(d16, 11), "Asphalt milling on Twy B", "closed")  # fmt: skip
    exd("ANIA-EXP", 18, rd("D-SAIR-01", "pm10:1h", d28, 5), ExceedanceCause.background_natural, None,
        ExceedanceStatus.closed, at(date(2026, 10, 1), 0, 11), at(d28, 6))  # fmt: skip
    exd("RBT-52", 4, rd("D-STWR-01", "pm10:24h", date(2026, 9, 3), 0), ExceedanceCause.background_natural, None,
        ExceedanceStatus.closed, at(date(2026, 9, 7), 0, 11), at(date(2026, 9, 4), 0))  # fmt: skip
    exd("RBT-52", 5, rd("N-STWR-01", "laeq:1h", date(2026, 9, 10), 23), ExceedanceCause.project_activity, "QIMMA",
        ExceedanceStatus.reviewed, at(date(2026, 9, 11), 10), at(date(2026, 9, 11), 0), "Night concrete pour on level 31", "open")  # fmt: skip
    exd("RBT-52", 6, rd("W-SPOD-01", "tss:spot", date(2026, 9, 24), 8), ExceedanceCause.project_activity, "QIMMA",
        ExceedanceStatus.reviewed, at(date(2026, 9, 28), 11), at(date(2026, 9, 24), 8, 15), "Dewatering settlement tank bypassed", "open")  # fmt: skip
    db.flush()


# ---- A.6 spills and spill kits -------------------------------------------------------------------

KITS = [
    ("ANIA-EXP", "SAIR", "S-AIR", ["Z-APR-21", "Z-TWB", "Z-ILS33R"], 5, ["GULFPAVE", "RAWABI"]),
    (
        "ANIA-EXP",
        "SLAND",
        "S-LAND",
        ["Z-LAY1", "Z-LAY1", "Z-LAY1", "Z-MSCP", "Z-PIERB"],
        7,
        ["RAWABI", "NAJD"],
    ),
    ("RBT-52", "SPOD", "S-POD", ["Z-B4", "Z-FAC"], 3, ["QIMMA"]),
    ("RBT-52", "STWR", "S-TWR", ["Z-CORE", "Z-TC01"], 2, ["QIMMA"]),
]


def _kits(ctx: ECtx) -> dict[str, EmergencyAsset]:
    db = ctx.db
    out: dict[str, EmergencyAsset] = {}
    checks: list[dict[str, Any]] = []
    items = [x.value for x in eref.ASSET_TYPES[AssetType.spill_kit][4]]
    checker = {
        "S-AIR": "omar.siddiqui",
        "S-LAND": "fahad.mutairi",
        "S-TWR": "ibrahim.saleh",
        "S-POD": "ibrahim.saleh",
    }
    cseq: dict[str, int] = {}
    for pc, pre, site, zones, n, owners in KITS:
        pid = ctx.pid(pc)
        if pc not in cseq:
            cseq[pc] = int(
                db.scalar(
                    select(AssetCheck.seq)
                    .where(AssetCheck.project_id == pid, AssetCheck.year == 2026)
                    .order_by(AssetCheck.seq.desc())
                    .limit(1)
                )
                or 0
            )
        for i in range(1, n + 1):
            tag = f"SK-{pre}-{i:02d}"
            z = ctx.zone(pc, zones[(i - 1) % len(zones)])
            a = EmergencyAsset(
                id=uuid.uuid4(),
                project_id=pid,
                asset_tag=tag,
                asset_type=AssetType.spill_kit,
                site_id=ctx.site(pc, site).id,
                zone_id=z.id,
                location_en=f"{z.code} spill kit {i}",
                owner_engagement_id=ctx.eng(pc, owners[(i - 1) % len(owners)]),
                registered_on=date(2026, 8, 20),
                status=AssetStatus.in_service,
                expiries=[],
                seed_fake=True,
            )
            if tag == "SK-SAIR-02":
                a.used_at = at(date(2026, 9, 25), 10, 0)
            db.add(a)
            out[tag] = a
            for d in (
                date(2026, 8, 28),
                date(2026, 9, 26) if tag != "SK-SLAND-06" else date(2026, 9, 27),
            ):
                fail = tag == "SK-SLAND-06" and d.month == 9
                cseq[pc] += 1
                s = cseq[pc]
                checks.append(
                    dict(
                        id=uuid.uuid4(),
                        year=2026,
                        seq=s,
                        check_no=f"EAC-{pc}-2026-{s:06d}",
                        project_id=pid,
                        asset_id=a.id,
                        checked_at=at(d, 9, 10 + i),
                        checked_by_user_id=ctx.uid(checker[site]),
                        method=CheckMethod.qr_scan,
                        outcome=CheckOutcome.checked,
                        items=[
                            {"item": x, "answer": "fail" if fail and x == "EC05" else "pass"}
                            for x in items
                        ],
                        fixed_on_spot=False,
                        result=CheckResult.fail if fail else CheckResult.pass_,
                        photo_ids=[],
                        warnings=[],
                        status=ERecordStatus.valid,
                        seed_fake=True,
                        created_by_user_id=ctx.uid(checker[site]),
                    )
                )
    db.flush()
    for a in out.values():
        acommon.issue_qr(db, QrKind.EA, a.project_id, a.id, a.asset_tag)
    db.execute(insert(AssetCheck), checks)
    db.flush()
    return out


def _spills(ctx: ECtx, kits: dict[str, EmergencyAsset]) -> None:
    db = ctx.db
    inc = db.scalar(select(Incident).where(Incident.ref == "INC-ANIA-EXP-2026-0288"))
    hws = ctx.areas["HWS-SLAND-01"]
    rows = [
        # project, seq, local date/time, site, zone, engagement, substance, source, litres, reportable
        ("ANIA-EXP", 28, date(2026, 9, 4), (14, 20), "S-LAND", "Z-LAY1", "NAJD", SpillSubstance.hydraulic_oil, SpillSource.plant_leak, "5", False),
        ("ANIA-EXP", 29, date(2026, 9, 11), (8, 45), "S-LAND", "Z-LAY1", "RAWABI", SpillSubstance.diesel, SpillSource.refuelling, "8", False),
        ("ANIA-EXP", 30, date(2026, 9, 18), (11, 5), "S-LAND", "Z-PIERB", "SAHARA", SpillSubstance.paint, SpillSource.container_failure, "2", False),
        ("ANIA-EXP", 31, date(2026, 9, 25), (3, 20), "S-AIR", "Z-APR-21", "GULFPAVE", SpillSubstance.diesel, SpillSource.refuelling, "40", True),
        ("RBT-52", 3, date(2026, 9, 15), (10, 30), "S-POD", "Z-B4", "QIMMA", SpillSubstance.hydraulic_oil, SpillSource.plant_leak, "6", False),
    ]  # fmt: skip
    for pc, seq, d0, (h, mi), site, zone, eng, sub, src, litres, rep in rows:
        d, occurred = d0, at(d0, h, mi)
        site_id, eng_id = ctx.site(pc, site).id, ctx.eng(pc, eng)
        zone_id: uuid.UUID | None = ctx.zone(pc, zone).id
        linked = None
        if seq == 31 and pc == "ANIA-EXP" and inc is not None:
            # A.1: the spill takes the Phase 1 incident's date, site, zone and engagement
            linked = inc.id
            occurred, d, site_id, zone_id = (
                inc.occurred_at,
                inc.occurred_date,
                inc.site_id,
                inc.zone_id,
            )
            eng_id = inc.responsible_engagement_id or eng_id
        closed = occurred + timedelta(days=1, hours=4)
        db.add(
            Spill(
                id=uuid.uuid4(),
                spill_no=ec.ref("SPL", pc, 2026, seq, 4),
                year=2026,
                seq=seq,
                client_uuid=uuid.uuid4(),
                project_id=ctx.pid(pc),
                occurred_at=occurred,
                occurred_date=d,
                site_id=site_id,
                zone_id=zone_id,
                responsible_engagement_id=eng_id,
                substance=sub,
                source=src,
                quantity_l=D(litres),
                surface=SpillSurface.paved,
                contained=True,
                reached=EnvReached.none,
                spill_kit_asset_ids=[kits["SK-SAIR-02"].id]
                if seq == 31 and pc == "ANIA-EXP"
                else [],
                reportable=rep,
                incident_id=linked,
                cleanup_completed_at=occurred + timedelta(hours=3),
                cleanup_storage_area_id=hws.id if rep else None,
                absorbed_and_binned=not rep,
                recorded_by_user_id=ctx.officer(pc),
                closed_at=closed,
                status=SpillStatus.closed,
                created_at=occurred + timedelta(minutes=20),
                updated_at=closed,
                created_by_user_id=ctx.officer(pc),
                seed_fake=True,
            )
        )
    db.flush()


# ---- A.7 water, discharge, complaint, aspects ----------------------------------------------------


def _water(ctx: ECtx) -> None:
    db = ctx.db
    rows = [
        ("ANIA-EXP", "S-AIR", WaterSource.tanker, "1800", {"dust_suppression": "1800"}),
        ("ANIA-EXP", "S-AIR", WaterSource.treated_effluent, "4350", {"dust_suppression": "4350"}),
        (
            "ANIA-EXP",
            "S-LAND",
            WaterSource.network,
            "810",
            {"welfare": "500", "concrete_curing": "310"},
        ),
        (
            "RBT-52",
            "S-TWR",
            WaterSource.network,
            "1215",
            {"welfare": "715", "concrete_curing": "500"},
        ),
    ]
    for pc, site, src, vol, pur in rows:
        db.add(
            WaterEntry(
                id=uuid.uuid4(),
                project_id=ctx.pid(pc),
                site_id=ctx.site(pc, site).id,
                month="2026-09",
                source=src,
                volume_m3=D(vol),
                purpose=pur,
                status=RecordState.valid,
                created_at=at(date(2026, 10, 2), 9),
                created_by_user_id=ctx.officer(pc),
                seed_fake=True,
            )
        )
    pt = ctx.pts["W-SPOD-01"]
    for d in days(SEPT[0], FILL_TO):
        db.add(
            DischargeDay(
                id=uuid.uuid4(),
                project_id=pt.project_id,
                point_id=pt.id,
                day=d,
                volume_m3=D("120.0"),
                warnings=["PERMIT_NOT_VALID"] if d > date(2026, 9, 20) else [],
                created_at=at(d, 18),
                created_by_user_id=ctx.uid("lina.haddad"),
                seed_fake=True,
            )
        )
    x5 = db.scalar(
        select(EnvExceedance).where(EnvExceedance.exceedance_no == "ENX-RBT-52-2026-0005")
    )
    r = ctx.readings[("N-STWR-01", "laeq:1h", at(date(2026, 9, 10), 23))]
    db.add(
        EnvComplaint(
            id=uuid.uuid4(),
            complaint_no="ECP-RBT-52-2026-004",
            year=2026,
            seq=4,
            project_id=ctx.pid("RBT-52"),
            received_at=at(date(2026, 9, 10), 23, 40),
            received_date=date(2026, 9, 10),
            channel=ComplaintChannel.phone,
            category=ComplaintCategory.noise,
            site_id=ctx.site("RBT-52", "S-TWR").id,
            location_text="Residential building east of S-TWR",
            anonymous=False,
            complainant_name="Hamad Al-Otaibi / حمد العتيبي",
            complainant_contact="+966500000999",
            description="Loud concrete pump noise after 23:00.",
            reading_ids=[r.id],
            exceedance_ids=[x5.id] if x5 else [],
            investigation_en="Night pour on level 31 exceeded the night limit (ENX-RBT-52-2026-0005).",
            investigation_ar="صب ليلي في الطابق 31 تجاوز الحد الليلي.",
            response_due_on=date(2026, 9, 17),
            response_sent_at=at(date(2026, 9, 12), 11),
            response_summary="Night pours moved before 22:00; acoustic screens installed.",
            closed_at=at(date(2026, 9, 20), 10),
            status=ComplaintStatus.closed,
            created_at=at(date(2026, 9, 10), 23, 45),
            created_by_user_id=ctx.uid("lina.haddad"),
            seed_fake=True,
        )
    )
    db.flush()


ASPECTS: dict[str, list[tuple[Activity, str, str, list[str], int, int, bool, str, list[tuple[str, str | None]]]]] = {
    # activity, aspect, impact, sites, severity, likelihood, legal, control level, links (point, parameter / template)
    "ANIA-EXP": [
        (Activity.excavation, "dust_emission", "air_quality", ["S-LAND"], 3, 3, True, "engineering", [("D-SLAND-01", "pm10")]),
        (Activity.excavation, "land_disturbance", "soil_contamination", ["S-LAND"], 2, 2, False, "administrative", []),
        (Activity.concrete, "wastewater_discharge", "groundwater_contamination", ["S-LAND"], 3, 2, True, "engineering", [("ENV", None)]),
        (Activity.paving_asphalt, "dust_emission", "aviation_safety", ["S-AIR"], 4, 3, True, "engineering", [("D-SAIR-01", "pm10"), ("DSN", None)]),
        (Activity.paving_asphalt, "fod_generation", "aviation_safety", ["S-AIR"], 5, 2, True, "engineering", [("FOD", None)]),
        (Activity.driving_transport, "exhaust_emission", "climate", ["S-AIR", "S-LAND"], 2, 3, False, "administrative", []),
        (Activity.maintenance, "fuel_spill_risk", "soil_contamination", ["S-AIR"], 4, 2, True, "engineering", [("ENV", None)]),
        (Activity.housekeeping, "waste_generation", "resource_depletion", ["S-LAND"], 2, 4, True, "engineering", [("WSA", None)]),
        (Activity.housekeeping, "wildlife_attraction", "aviation_safety", ["S-AIR"], 4, 2, True, "engineering", [("WSA", None)]),
        (Activity.material_handling, "hazardous_material_storage", "soil_contamination", ["S-LAND"], 4, 2, True, "engineering", [("WSA", None)]),
        (Activity.steel_erection, "noise_vibration", "community_nuisance", ["S-LAND"], 2, 3, False, "administrative", [("N-SLAND-01", "laeq")]),
        (Activity.concrete, "water_consumption", "resource_depletion", ["S-AIR", "S-LAND"], 2, 3, False, "administrative", []),
        (Activity.airfield_lighting, "light_spill", "aviation_safety", ["S-AIR"], 3, 2, True, "administrative", []),
        (Activity.demolition, "dust_emission", "air_quality", ["S-LAND"], 3, 3, False, "engineering", [("D-SLAND-01", "pm10")]),
    ],
    "RBT-52": [
        (Activity.concrete, "noise_vibration", "community_nuisance", ["S-TWR"], 3, 4, True, "engineering", [("N-STWR-01", "laeq")]),
        (Activity.excavation, "wastewater_discharge", "groundwater_contamination", ["S-POD"], 4, 3, True, "engineering", [("W-SPOD-01", "tss")]),
        (Activity.excavation, "dust_emission", "air_quality", ["S-POD"], 3, 3, True, "engineering", [("V-SPOD", "visual_dust")]),
        (Activity.concrete, "dust_emission", "community_nuisance", ["S-TWR"], 3, 3, True, "engineering", [("D-STWR-01", "pm10")]),
        (Activity.housekeeping, "waste_generation", "resource_depletion", ["S-POD", "S-TWR"], 2, 4, True, "engineering", [("WSA", None)]),
        (Activity.mep_installation, "hazardous_material_storage", "soil_contamination", ["S-POD"], 3, 2, True, "engineering", [("WSA", None)]),
        (Activity.lifting, "noise_vibration", "community_nuisance", ["S-TWR"], 2, 3, False, "administrative", []),
        (Activity.driving_transport, "exhaust_emission", "climate", ["S-POD"], 2, 3, False, "administrative", []),
        (Activity.maintenance, "fuel_spill_risk", "soil_contamination", ["S-POD"], 3, 2, True, "engineering", [("ENV", None)]),
        (Activity.concrete, "water_consumption", "resource_depletion", ["S-TWR"], 2, 2, False, "administrative", []),
    ],
}  # fmt: skip


def _aspects(ctx: ECtx) -> None:
    db = ctx.db
    activated = date(2026, 3, 1)
    for pc, rows in ASPECTS.items():
        for i, (act, asp, imp, sites, sev, lik, legal, lvl, links) in enumerate(rows, start=1):
            ml = [
                {"point_id": str(ctx.pts[a].id), "parameter": b, "template_code": None} if b else
                {"point_id": None, "parameter": None, "template_code": a}
                for a, b in links
            ]  # fmt: skip
            ctl = (
                ("Water bowser and milling with spray bars", "صهريج مياه وكشط مع رشاشات")
                if (pc, i) == ("ANIA-EXP", 4)
                else (f"{asp.replace('_', ' ').capitalize()} control plan", "خطة ضبط")
            )
            db.add(
                EnvAspect(
                    id=uuid.uuid4(),
                    project_id=ctx.pid(pc),
                    aspect_no=f"ASP-{pc}-{i:03d}",
                    seq=i,
                    activity=act.value,
                    aspect=asp,
                    impact=imp,
                    condition=AspectCondition.normal,
                    site_ids=[ctx.site(pc, s).id for s in sites],
                    engagement_ids=[],
                    severity=sev,
                    likelihood=lik,
                    legal_requirement=legal,
                    permit_ids=[],
                    stakeholder_concern=False,
                    controls=[{"text_en": ctl[0], "text_ar": ctl[1], "control_level": lvl}],
                    monitoring_links=ml,
                    activated_on=activated,
                    review_due_on=date(2027, 2, 28),
                    review_flag=False,
                    status=AspectStatus.active,
                    created_by_user_id=ctx.officer(pc),
                    seed_fake=True,
                )
            )
    db.flush()


# ---- A.8 templates and plans ---------------------------------------------------------------------

ENV2 = [
    ("A", "Spill kits present and stocked at fuel and chemical points", "حقائب الانسكاب متوفرة ومجهزة عند نقاط الوقود والمواد الكيميائية", True),
    ("A", "No uncontained fuel or chemical", "لا وقود أو مواد كيميائية غير محتواة", True),
    ("A", "Drip trays under static plant", "صواني تنقيط تحت المعدات الثابتة", False),
    ("A", "Dust suppression in use on haul roads", "رش الغبار مستخدم على طرق النقل", False),
    ("A", "Waste segregated in labelled bins", "النفايات مفروزة في حاويات معنونة", False),
    ("B", "No waste burning", "لا حرق للنفايات", True),
    ("B", "Wheel wash working at the exit", "مغسلة العجلات تعمل عند المخرج", False),
    ("B", "Noisy work within permitted hours", "الأعمال المزعجة ضمن الساعات المسموح بها", False),
    ("B", "Dewatering discharge through settlement tank", "تصريف النزح عبر خزان الترسيب", False),
    ("B", "Stockpiles covered or wetted", "أكوام المواد مغطاة أو مرطبة", False),
    ("B", "Concrete washout in the designated pit", "غسيل الخرسانة في الحفرة المخصصة", False),
    ("B", "Environmental noticeboard up to date (bilingual)", "لوحة البيئة محدثة (بلغتين)", False),
]  # fmt: skip
WSA = [
    ("A", "Area signed in Arabic and English", "المنطقة معلّمة بالعربية والإنجليزية", False, False),
    ("A", "Streams segregated as signed", "المسارات مفروزة حسب اللافتات", False, False),
    ("A", "Hazardous store bunded and bund free of liquid", "مخزن المواد الخطرة محاط بحوض احتواء خالٍ من السوائل", True, False),
    ("A", "Containers closed and labelled", "الحاويات مغلقة ومعنونة", False, False),
    ("A", "Spill kit present at the store", "حقيبة الانسكاب متوفرة عند المخزن", True, False),
    ("B", "No overflow; collection booked", "لا فيضان؛ تم حجز النقل", False, False),
    ("B", "Lids secured against wind and wildlife (airside)", "الأغطية مثبتة ضد الرياح والحياة البرية (الجانب الجوي)", True, True),
    ("B", "No loose debris around the area (FOD)", "لا مخلفات سائبة حول المنطقة", False, False),
]  # fmt: skip
DSN = [
    ("A", "Water bowser available and working", "صهريج المياه متوفر ويعمل", False, False),
    ("A", "No visible dust plume crossing the runway / taxiway", "لا سحابة غبار مرئية تعبر المدرج أو الممر", True, True),
    ("A", "Milling and cutting with water sprays", "الكشط والقطع مع رش المياه", False, False),
    ("B", "Haul road speed limit respected", "التقيد بحد السرعة على طرق النقل", False, False),
    ("B", "Stockpiles covered or wetted", "أكوام المواد مغطاة أو مرطبة", False, False),
    ("B", "Visual dust score recorded", "تم تسجيل درجة الغبار المرئي", False, False),
]  # fmt: skip


def _templates(ctx: ECtx) -> None:
    from app.services.field.library import review_due  # noqa: PLC0415

    db = ctx.db
    pub = datetime(2026, 10, 1, 5, 0, tzinfo=UTC)
    v1 = db.scalar(
        select(ChecklistTemplate).where(
            ChecklistTemplate.template_code == "ENV", ChecklistTemplate.version == 1
        )
    )
    if v1 is not None:
        v1.status, v1.superseded_at = VersionStatus.superseded, pub

    def secs(code: str, en: str, ar: str) -> list[dict[str, Any]]:
        return [{"code": s, "title_en": f"{en} – part {k}", "title_ar": f"{ar} – الجزء {k}", "order": k}
                for k, s in ((1, "A"), (2, "B"))]  # fmt: skip

    defs: list[tuple[str, int, str, str, list[dict[str, Any]]]] = []
    items = [
        _item("ENV", n, s, en, ar, critical=c) for n, (s, en, ar, c) in enumerate(ENV2, start=1)
    ]
    defs.append(("ENV", 2, "Environmental", "البيئة", items))
    items = [
        _item(
            "WSA",
            n,
            s,
            en,
            ar,
            critical=c,
            airside_only=air,
            default_severity="major" if c else "minor",
        )
        for n, (s, en, ar, c, air) in enumerate(WSA, start=1)
    ]
    defs.append(("WSA", 1, "Waste storage area", "منطقة تخزين النفايات", items))
    items = [
        _item("DSN", n, s, en, ar, critical=c, airside_only=air,
              stop_rule=StopRule.stop_work.value if c else StopRule.none.value,
              default_severity="critical" if c else "minor")
        for n, (s, en, ar, c, air) in enumerate(DSN, start=1)
    ]  # fmt: skip
    defs.append(("DSN", 1, "Dust suppression and nuisance", "مكافحة الغبار والإزعاج", items))
    for code, ver, en, ar, its in defs:
        assert all(x["item_type"] == ItemType.yes_no.value for x in its)  # noqa: S101
        db.add(
            ChecklistTemplate(
                template_code=code,
                version=ver,
                kind=TemplateKind.inspection,
                inspection_type=InspectionType.environmental,
                audit_type=None,
                title_en=en,
                title_ar=ar,
                sections=secs(code, en, ar),
                items=its,
                zone_types=[],
                project_ids=[],
                review_due_on=review_due(pub),
                change_note="v2: 6e environmental items" if ver == 2 else None,
                authored_by_user_id=ctx.faisal,
                published_by_user_id=ctx.faisal,
                published_at=pub,
                superseded_at=None,
                status=VersionStatus.published,
                created_by_user_id=ctx.faisal,
            )
        )
    start = date(2026, 10, 1)
    plans = [
        ("ANIA-EXP", "WSA", "Waste storage areas — Airside", "S-AIR", InspectionFrequency.weekly, Weekday.sunday, []),
        ("ANIA-EXP", "WSA", "Waste storage areas — Terminal 3", "S-LAND", InspectionFrequency.weekly, Weekday.sunday, []),
        ("ANIA-EXP", "DSN", "Dust suppression — apron and taxiway", "S-AIR", InspectionFrequency.daily, None, ["Z-APR-21", "Z-TWB"]),
        ("ANIA-EXP", "ENV", "Environmental — Airside", "S-AIR", InspectionFrequency.monthly, None, []),
        ("ANIA-EXP", "ENV", "Environmental — Terminal 3", "S-LAND", InspectionFrequency.monthly, None, []),
        ("RBT-52", "WSA", "Waste storage areas — Tower", "S-TWR", InspectionFrequency.weekly, Weekday.sunday, []),
        ("RBT-52", "WSA", "Waste storage areas — Podium", "S-POD", InspectionFrequency.weekly, Weekday.sunday, []),
        ("RBT-52", "DSN", "Dust suppression — podium", "S-POD", InspectionFrequency.daily, None, []),
        ("RBT-52", "ENV", "Environmental — Tower", "S-TWR", InspectionFrequency.monthly, None, []),
        ("RBT-52", "ENV", "Environmental — Podium", "S-POD", InspectionFrequency.monthly, None, []),
    ]  # fmt: skip
    from app.core.field_enums import Rotation  # noqa: PLC0415

    for pc, tpl, name, site, freq, wd, rot in plans:
        db.add(
            InspectionPlan(
                id=uuid.uuid4(),
                project_id=ctx.pid(pc),
                name_en=name,
                name_ar=name,
                inspection_type=InspectionType.environmental,
                site_id=ctx.site(pc, site).id,
                zone_id=None,
                engagement_id=None,
                frequency=freq,
                weekday=wd,
                start_date=start,
                assignee_role=InspectionAssigneeRole.hse_officer,
                assignee_user_id=ctx.officer(pc),
                active=True,
                generated_until=start - timedelta(days=1),
                template_code=tpl,
                rotation=Rotation.zones if rot else Rotation.none,
                rotation_list=[ctx.zone(pc, z).id for z in rot],
            )
        )
    db.flush()


# ---- entry point ---------------------------------------------------------------------------------


def seed_env_data(db: Session) -> None:
    if already_seeded(db):
        return
    from app.models import Project  # noqa: PLC0415

    if db.scalar(select(Project.id).where(Project.code == "ANIA-EXP")) is None:
        return
    n0 = set(db.scalars(select(Notification.id)))
    e0 = set(db.scalars(select(EmailMessage.id)))
    ctx = ECtx(db)
    try:
        set_now(SEED_CLOCK)
        _settings(ctx)
        _providers(ctx)
        _permits(ctx)
        _waste_setup(ctx)
        _consignments(ctx)
        _monitoring_setup(ctx)
        _dust_station(ctx)
        _noise_station(ctx)
        _manual(ctx)
        db.flush()
        _exceedances(ctx)
        kits = _kits(ctx)
        _spills(ctx, kits)
        _water(ctx)
        _aspects(ctx)
        _templates(ctx)
        _cleanup(db, n0, e0)
        ec.clear_cache(db)
        db.info.pop("env_rseq", None)
        db.info.pop("env_ops", None)
    finally:
        set_now(None)


def main() -> int:  # pragma: no cover - CLI
    from app.db.session import get_sessionmaker  # noqa: PLC0415

    with get_sessionmaker()() as db:
        seed_env_data(db)
        db.commit()
    print("Phase 6e seed loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
