# ruff: noqa: E501, C408
"""Phase 6c seed (spec 6c-emergency-drills Appendix A): settings, ERPs, assembly points,
contacts, zone profiles, the roster, rescue teams (with the Phase 4 item TW-01 and the Phase 5
CSE-RESCUE / WAH-RESCUE records of §11.6 item 3), emergency assets with their checks since
2026-03-01, the drill history, the named September 2026 drills with their musters, and the two
events of A.7, reproducing ED9 where the Phase 0–6b world allows (differences in DECISIONS).

Everything is inserted directly (no alerts). Fictional; tags, refs and serials contain TEST."""

from __future__ import annotations

import itertools
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.access_enums import DeploymentStatus, QrKind
from app.core.cert_enums import EquipmentCertCategory, ServiceStatus, TpiStatus
from app.core.clock import set_now
from app.core.emergency_enums import (
    ActiveStatus,
    Agency,
    ApKind,
    AssetStatus,
    AssetType,
    CheckMethod,
    CheckOutcome,
    CheckResult,
    DrillShift,
    DrillStatus,
    DrillType,
    EmergencyRole,
    EntryMethod,
    EntryState,
    ErpStatus,
    EventStatus,
    EventType,
    MusterSource,
    RecordStatus,
    ResolutionReason,
    ResponseType,
    RosterShift,
    ScenarioType,
    TeamType,
)
from app.models import (
    AssemblyPoint,
    AssetCheck,
    Deployment,
    Drill,
    EmergencyAsset,
    EmergencyContact,
    EmergencyEvent,
    EmergencySettings,
    EquipmentItem,
    Erp,
    Incident,
    RescueTeam,
    RosterAssignment,
    Tpi,
    TrainingRecord,
    Worker,
    ZoneEmergencyProfile,
)
from app.seed_heat import Ctx
from app.services.access import common as acommon
from app.services.emergency import common as ec
from app.services.emergency import reference as ref

RIYADH = ZoneInfo("Asia/Riyadh")
SEED_CLOCK = datetime(2026, 10, 6, 7, 0, tzinfo=UTC)  # 10:00 Riyadh
REGISTER_FROM = date(2026, 3, 1)
CHECKS_UNTIL = date(2026, 10, 5)
ES = ScenarioType
DT = DrillType
AT = AssetType


def at(d: date, h: int, mi: int = 0, s: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, h, mi, s, tzinfo=RIYADH).astimezone(UTC)


def iso(x: datetime) -> str:
    return x.isoformat()


def already_seeded(db: Session) -> bool:
    return db.scalar(select(Erp.id).limit(1)) is not None


class ECtx(Ctx):
    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self.erps: dict[str, Erp] = {}
        self.aps: dict[str, AssemblyPoint] = {}
        self.teams: dict[str, RescueTeam] = {}
        self.assets: dict[str, EmergencyAsset] = {}
        self.workers = {
            w.worker_no: w
            for w in db.scalars(
                select(Worker).where(
                    Worker.worker_no.in_(
                        ["WKR-000005", "WKR-000008", "WKR-000016", "WKR-000017", "WKR-000021",
                         ]
                    )
                )
            )
        }  # fmt: skip

        # height teams: WAH holders picked by qualification (the Phase 5 world assigns FIRST-AID
        # and WAH per run): lead = lowest worker_no with WAH and FIRST-AID, then WAH holders
        self.wah = {"ANIA-EXP": self._wah_people("ANIA-EXP", 3),
                    "RBT-52": self._wah_people("RBT-52", 2)}  # fmt: skip
        for ws in self.wah.values():
            for w in db.scalars(select(Worker).where(Worker.worker_no.in_(ws))):
                self.workers[w.worker_no] = w

    def _wah_people(self, pcode: str, n: int) -> list[str]:
        until = date(2027, 3, 1)
        valid = (
            select(TrainingRecord.worker_id)
            .where(TrainingRecord.status == "accepted", TrainingRecord.valid_until >= until)
        )  # fmt: skip
        rows = self.db.execute(
            select(Worker.worker_no, Worker.id)
            .join(Deployment, Deployment.worker_id == Worker.id)
            .where(
                Deployment.project_id == self.pid(pcode),
                Deployment.status == "mobilised",
                Worker.id.in_(valid.where(TrainingRecord.course_code == "WAH")),
            )
            .order_by(Worker.worker_no)
        ).all()
        fa = set(self.db.scalars(valid.where(TrainingRecord.course_code == "FIRST-AID")))
        lead = next(no for no, wid in rows if wid in fa)
        return [lead, *[no for no, _ in rows if no != lead][: n - 1]]

    def dep(self, pcode: str, wno: str) -> Deployment:
        w = self.workers[wno]
        d = self.db.scalar(
            select(Deployment).where(
                Deployment.worker_id == w.id, Deployment.project_id == self.pid(pcode)
            )
        )
        assert d is not None  # noqa: S101
        return d

    def site(self, pcode: str, code: str) -> Any:
        return self.sites[(pcode, code)]


# ---- A.9 settings --------------------------------------------------------------------------------


def _settings(ctx: ECtx) -> None:
    for code, enf in (("ANIA-EXP", date(2026, 10, 1)), ("RBT-52", None)):
        s = ctx.db.get(EmergencySettings, ctx.pid(code))
        if s is None:
            s = EmergencySettings(project_id=ctx.pid(code), values={})
            ctx.db.add(s)
        s.emergency_register_from = REGISTER_FROM
        s.emergency_ptw_enforcement_from = enf
        if code == "ANIA-EXP":
            # S-LAND's one gate is a delivery gate: the spec treats the site as gateless (ED2,
            # ED3 count mode) → presence and musters use the no-gate rules there (DECISIONS)
            s.values = {"gate_presence_excluded_site_ids": [str(ctx.site(code, "S-LAND").id)]}
    ctx.db.flush()
    ec.clear_cache(ctx.db)


# ---- §11.5 / §11.6 Phase 4 and Phase 5 additions -------------------------------------------------


def _phase45(ctx: ECtx) -> dict[str, Any]:
    db = ctx.db
    tpi = Tpi(
        id=uuid.uuid4(),
        tpi_code="FIRESAFE",
        legal_name_en="FireSafe Maintenance Co. (fictional)",
        legal_name_ar="شركة فاير سيف للصيانة (وهمية)",
        name_norm_en="firesafe maintenance co fictional",
        name_norm_ar="شركة فاير سيف للصيانة وهمية",
        kinds=["fire_protection_service"],
        country="SA",
        cr_number="7000004470",
        contact_name="Civil Defense licence CD-TEST-LIC-0447 (valid to 2027-06-30)",
        status=TpiStatus.approved,
        seed_fake=True,
    )
    db.add(tpi)
    raw = ctx.engs[("ANIA-EXP", "RAWABI")]
    seq = (
        db.scalar(select(EquipmentItem.seq).order_by(EquipmentItem.seq.desc()).limit(1)) or 0
    ) + 1
    tw = EquipmentItem(
        id=uuid.uuid4(),
        seq=seq,
        equipment_no=f"EQP-{seq:06d}",
        category=EquipmentCertCategory.tripod_winch,
        manufacturer="RescueLift (fictional)",
        manufacturer_norm="rescuelift fictional",
        model="TW-01 tripod and winch",
        serial_no="TW-01-TEST",
        serial_norm="TW01TEST",
        year_of_manufacture=2024,
        owner_contractor_id=raw.contractor_id,
        owner_fleet_no="TW-01",
        service_status=ServiceStatus.in_service,
        service_status_since=at(date(2026, 3, 1), 8),
        documents=[{"kind": "certificate", "ref": "AICC TEST", "valid_until": "2027-02-28"}],
        seed_fake=True,
    )
    db.add(tw)
    # §11.6 item 3: CSE-RESCUE for the RT-ANIA-CSE-01 members, WAH-RESCUE for the height teams
    tmpl = db.scalar(select(TrainingRecord).where(TrainingRecord.course_code == "CSE-RESCUE"))
    assert tmpl is not None  # noqa: S101
    seq0 = db.scalar(select(TrainingRecord.seq).order_by(TrainingRecord.seq.desc()).limit(1)) or 0
    n = itertools.count(seq0 + 1)
    rows = [
        ("ANIA-EXP", "WKR-000016", "CSE-RESCUE", date(2026, 3, 2), date(2027, 3, 1)),
        ("ANIA-EXP", "WKR-000017", "CSE-RESCUE", date(2026, 3, 2), date(2027, 3, 1)),
        *[("ANIA-EXP", w, "WAH-RESCUE", date(2026, 2, 10), date(2028, 2, 9))
          for w in ctx.wah["ANIA-EXP"]],
        *[("RBT-52", w, "WAH-RESCUE", date(2025, 6, 1), date(2027, 5, 31))
          for w in ctx.wah["RBT-52"]],
    ]  # fmt: skip
    skip = {"id", "seq", "record_no", "worker_id", "course_code", "certificate_no", "completed_on",
            "valid_until", "project_id", "engagement_id", "name_as_printed", "submitted_at",
            "reviewed_at", "verified_at", "in_force_from", "created_at", "updated_at",
            "alerts_sent"}  # fmt: skip
    base = {
        c.key: getattr(tmpl, c.key) for c in TrainingRecord.__table__.columns if c.key not in skip
    }
    for i, (pc, wno, code, done, until) in enumerate(rows):
        d = ctx.dep(pc, wno)
        s = next(n)
        inforce = at(done + timedelta(days=2), 10)
        db.add(
            TrainingRecord(
                **base,
                id=uuid.uuid4(),
                seq=s,
                record_no=f"TRR-{s:06d}",
                worker_id=d.worker_id,
                course_code=code,
                certificate_no=f"INT-HSE-6C-TEST-{i + 1:03d}",
                completed_on=done,
                valid_until=until,
                project_id=d.project_id,
                engagement_id=d.engagement_id,
                name_as_printed=ctx.workers[wno].full_name_en,
                submitted_at=inforce,
                reviewed_at=inforce,
                verified_at=inforce,
                in_force_from=inforce,
                alerts_sent=[],
            )
        )
    db.flush()
    return {"tpi": tpi, "tw": tw}


# ---- A.2 ERPs, assembly points, contacts, profiles -----------------------------------------------


def _scn(
    code: str, st: ScenarioType, sites: list[uuid.UUID], resp: ResponseType, dt: DrillType,
    freq: int, agencies: list[Agency], **extra: Any,
) -> dict[str, Any]:  # fmt: skip
    en, ar = ref.SCENARIOS[st]
    return {
        "scenario_code": code,
        "scenario_type": st.value,
        "site_ids": [str(x) for x in sites],
        "alarm_signal_en": "Continuous siren and air horn",
        "alarm_signal_ar": "صافرة متواصلة وبوق هوائي",
        "response_type": resp.value,
        "response_summary_en": f"{en}: raise the alarm, respond per the ERP, account at the AP.",
        "response_summary_ar": f"{ar}: إطلاق الإنذار والاستجابة حسب الخطة والحصر في نقطة التجمع.",
        "agencies": [a.value for a in agencies],
        "drill_type": dt.value,
        "drill_frequency_months": freq,
        "rescue_plan_refs": extra.get("rescue_plan_refs", []),
        "no_such_work": extra.get("no_such_work", False),
    }


def _erps(ctx: ECtx) -> None:
    db = ctx.db
    ag = Agency
    cd, rc = ag.civil_defense, ag.red_crescent
    a = ctx.pid("ANIA-EXP")
    a_sites = [ctx.site("ANIA-EXP", "S-AIR").id, ctx.site("ANIA-EXP", "S-LAND").id]
    a_sc = [
        _scn("SC-FIRE", ES.fire_explosion, a_sites, ResponseType.site_evacuation,
             DT.evacuation_full, 6, [cd, rc, ag.airport_arff]),
        _scn("SC-MED", ES.medical_emergency, a_sites, ResponseType.local_response,
             DT.medical_response, 6, [rc, ag.site_clinic]),
        _scn("SC-WX", ES.severe_weather, a_sites, ResponseType.local_response, DT.tabletop, 12,
             [cd]),
        _scn("SC-CSE", ES.confined_space_rescue, a_sites, ResponseType.local_response,
             DT.cse_rescue, 12, [cd, rc], rescue_plan_refs=["RP-CSE-TEST-01"]),
        _scn("SC-WAH", ES.height_rescue, a_sites, ResponseType.local_response,
             DT.height_rescue, 12, [cd, rc], rescue_plan_refs=["RP-WAH-TEST-01"]),
        _scn("SC-AIRCRAFT", ES.aircraft_emergency, [a_sites[0]], ResponseType.zone_evacuation,
             DT.airport_exercise, 12, [ag.airport_arff, ag.airport_aocc]),
        _scn("SC-GAS", ES.gas_release, [a_sites[1]], ResponseType.zone_evacuation, DT.tabletop,
             12, [cd, rc]),
        _scn("SC-UTIL", ES.utility_strike, a_sites, ResponseType.local_response, DT.tabletop, 12,
             [ag.electricity_utility, cd]),
    ]  # fmt: skip
    r = ctx.pid("RBT-52")
    r_sites = [ctx.site("RBT-52", "S-TWR").id, ctx.site("RBT-52", "S-POD").id]
    r_sc = [
        _scn("SC-FIRE", ES.fire_explosion, r_sites, ResponseType.site_evacuation,
             DT.evacuation_full, 6, [cd, rc]),
        _scn("SC-MED", ES.medical_emergency, r_sites, ResponseType.local_response,
             DT.medical_response, 6, [rc, ag.site_clinic]),
        _scn("SC-WX", ES.severe_weather, r_sites, ResponseType.local_response, DT.tabletop, 12,
             [cd]),
        _scn("SC-CSE", ES.confined_space_rescue, r_sites, ResponseType.local_response,
             DT.cse_rescue, 12, [cd, rc], no_such_work=True),
        _scn("SC-WAH", ES.height_rescue, r_sites, ResponseType.local_response,
             DT.height_rescue, 12, [cd, rc], rescue_plan_refs=["RP-RBT-WAH-TEST-01"]),
        _scn("SC-COLLAPSE", ES.structural_collapse, r_sites, ResponseType.site_evacuation,
             DT.tabletop, 12, [cd, rc]),
    ]  # fmt: skip
    noura, faisal, lina = ctx.uid("noura.qahtani"), ctx.uid("faisal.harbi"), ctx.uid("lina.haddad")
    for pid, pc, rev, sites, sc, approved, due, prep, extra in (
        (a, "ANIA-EXP", 3, a_sites, a_sc, date(2026, 2, 15), date(2027, 2, 14), noura,
         {"client_acceptance_ref": "ANIA-CL-ERP-TEST-03", "accepted_on": date(2026, 2, 12),
          "airport_interface_ref": "OEXX-AEP-TEST-2026"}),
        (r, "RBT-52", 2, r_sites, r_sc, date(2025, 10, 1), date(2026, 9, 30), lina, {}),
    ):  # fmt: skip
        e = Erp(
            id=uuid.uuid4(),
            erp_no=f"ERP-{pc}-r{rev}",
            project_id=pid,
            revision=rev,
            title_en=f"{pc} emergency response plan",
            title_ar=f"خطة الاستجابة للطوارئ {pc}",
            document_ref=f"{pc}-ERP-TEST-r{rev}",
            site_ids=sites,
            scenarios=sc,
            prepared_by_user_id=prep,
            submitted_at=at(approved - timedelta(days=3), 10),
            approved_by_user_id=faisal,
            approved_at=at(approved, 11),
            review_due_on=due,
            review_required=False,
            review_triggers=[],
            status=ErpStatus.approved,
            alerts_sent=[],
            created_by_user_id=prep,
            seed_fake=True,
            **extra,
        )
        db.add(e)
        ctx.erps[pc] = e
    db.flush()


APS = [
    # code, project, site, zone, kind, zones served, capacity, location
    ("AP-SAIR-01", "ANIA-EXP", "S-AIR", None, ApKind.primary, ["Z-APR-21", "Z-TWB", "Z-ILS33R"],
     800, "Contractor compound beside G-AAP3"),
    ("AP-SAIR-02", "ANIA-EXP", "S-AIR", None, ApKind.alternate,
     ["Z-APR-21", "Z-TWB", "Z-ILS33R"], 400, "Service road east"),
    ("AP-SLAND-01", "ANIA-EXP", "S-LAND", "Z-LAY1", ApKind.primary,
     ["Z-PIERB", "Z-MSCP", "Z-LAY1"], 1500, "Laydown area 1, north end"),
    ("AP-SLAND-02", "ANIA-EXP", "S-LAND", None, ApKind.alternate, ["Z-PIERB", "Z-MSCP", "Z-LAY1"],
     1000, "Landside north plaza"),
    ("AP-STWR-01", "RBT-52", "S-TWR", None, ApKind.primary, ["Z-CORE", "Z-TC01"], 600,
     "Tower site car park"),
    ("AP-SPOD-01", "RBT-52", "S-POD", None, ApKind.primary, ["Z-B4", "Z-FAC"], 400,
     "Podium entrance plaza"),
]  # fmt: skip
CONTACTS = [
    (Agency.civil_defense, "Civil Defense", "الدفاع المدني", "998"),
    (Agency.red_crescent, "Saudi Red Crescent", "الهلال الأحمر السعودي", "997"),
    (Agency.police, "Police", "الشرطة", "999"),
    (Agency.unified_911, "Unified emergency number", "الرقم الموحد للطوارئ", "911"),
    (Agency.site_clinic, "Site clinic", "عيادة الموقع", "+966110000911"),
    (Agency.hospital, "Al-Noor General Hospital (fictional)", "مستشفى النور العام (وهمي)",
     "+966110000912"),
]  # fmt: skip
AIRPORT_CONTACTS = [
    (Agency.airport_arff, "Airport ARFF", "إطفاء وإنقاذ المطار", "+966110009998"),
    (Agency.airport_aocc, "Airport AOCC", "مركز عمليات المطار", "+966110009997"),
    (Agency.airport_security, "Airport security", "أمن المطار", "+966110009996"),
]


def _aps(ctx: ECtx) -> None:
    db = ctx.db
    for code, pc, site, zone, kind, served, cap, loc in APS:
        a = AssemblyPoint(
            id=uuid.uuid4(),
            project_id=ctx.pid(pc),
            ap_code=code,
            site_id=ctx.site(pc, site).id,
            zone_id=ctx.zone(pc, zone).id if zone else None,
            location_en=loc,
            location_ar=loc,
            capacity_persons=cap,
            zones_served=[ctx.zone(pc, z).id for z in served],
            kind=kind,
            status=ActiveStatus.active,
            seed_fake=True,
        )
        db.add(a)
        db.flush()
        acommon.issue_qr(db, QrKind.MP, a.project_id, a.id, code)
        ctx.aps[code] = a
    for pc in ("ANIA-EXP", "RBT-52"):
        rows = CONTACTS + (AIRPORT_CONTACTS if pc == "ANIA-EXP" else [])
        for ag, en, ar, phone in rows:
            db.add(
                EmergencyContact(
                    id=uuid.uuid4(), project_id=ctx.pid(pc), site_ids=[], agency=ag.value,
                    display_name_en=en, display_name_ar=ar, phone=phone, available_24h=True,
                    priority=1, active=True, seed_fake=True,
                )
            )  # fmt: skip
    db.add(
        ZoneEmergencyProfile(
            zone_id=ctx.zone("RBT-52", "Z-B4").id, project_id=ctx.pid("RBT-52"),
            eyewash_required=True, warden_required=True, notes="Concrete admixtures",
        )
    )  # fmt: skip
    db.add(
        ZoneEmergencyProfile(
            zone_id=ctx.zone("ANIA-EXP", "Z-MSCP").id, project_id=ctx.pid("ANIA-EXP"),
            min_extinguishers=4, warden_required=True,
        )
    )  # fmt: skip
    db.flush()


# ---- A.3 roster ----------------------------------------------------------------------------------


def _holders(ctx: ECtx, pc: str, code: str, status: str = "accepted") -> list[Deployment]:
    q = (
        select(Deployment)
        .join(TrainingRecord, TrainingRecord.worker_id == Deployment.worker_id)
        .where(
            Deployment.project_id == ctx.pid(pc),
            Deployment.status == DeploymentStatus.mobilised,
            TrainingRecord.course_code == code,
            TrainingRecord.status == status,
        )
        .order_by(Deployment.id)
    )
    return list(dict.fromkeys(ctx.db.scalars(q)))


def _roster(ctx: ECtx) -> None:
    db = ctx.db
    seq: dict[str, itertools.count[int]] = {}
    by = {"ANIA-EXP": ctx.uid("noura.qahtani"), "RBT-52": ctx.uid("lina.haddad")}

    def add(
        pc: str, role: EmergencyRole, site: str, shift: RosterShift,
        dep: Deployment | None = None, user: uuid.UUID | None = None, zones: list[str] | None = None,
    ) -> None:  # fmt: skip
        n = next(seq.setdefault(pc, itertools.count(1)))
        db.add(
            RosterAssignment(
                id=uuid.uuid4(), assignment_no=f"EOR-{pc}-{n:05d}", project_id=ctx.pid(pc),
                seq=n, role=role, deployment_id=dep.id if dep else None, user_id=user,
                site_id=ctx.site(pc, site).id,
                zone_ids=[ctx.zone(pc, z).id for z in zones or []], shift=shift,
                valid_from=REGISTER_FROM, designated_by_user_id=by[pc], seed_fake=True,
            )
        )  # fmt: skip

    site_zones = {
        "S-AIR": ["Z-APR-21", "Z-TWB", "Z-ILS33R"], "S-LAND": ["Z-PIERB", "Z-MSCP", "Z-LAY1"],
        "S-TWR": ["Z-CORE", "Z-TC01"], "S-POD": ["Z-B4", "Z-FAC"],
    }  # fmt: skip
    code_of = {s.id: s.code for s in ctx.sites.values()}
    named = {ctx.dep("ANIA-EXP", "WKR-000005").id}
    for pc in ("ANIA-EXP", "RBT-52"):
        for role, course in ((EmergencyRole.first_aider, "FIRST-AID"),
                             (EmergencyRole.fire_warden, "FIRE-WARDEN")):  # fmt: skip
            deps = _holders(ctx, pc, course)
            if pc == "ANIA-EXP" and role == EmergencyRole.first_aider:
                deps += _holders(ctx, pc, course, "rejected")  # Waleed Saleh (ED2)
            for d in deps:
                if d.id in named:
                    continue
                sites = sorted(code_of[s] for s in d.site_ids or [] if s in code_of)
                if not sites:
                    continue
                site = sites[0]
                shift = RosterShift.both if site == "S-AIR" else RosterShift.day
                zones = site_zones[site] if role == EmergencyRole.fire_warden else None
                add(pc, role, site, shift, dep=d, zones=zones)
    mf = ctx.dep("ANIA-EXP", "WKR-000005")
    add("ANIA-EXP", EmergencyRole.fire_warden, "S-AIR", RosterShift.day, dep=mf, zones=["Z-APR-21"])
    add("ANIA-EXP", EmergencyRole.emergency_coordinator, "S-AIR", RosterShift.day,
        user=ctx.uid("omar.siddiqui"))  # fmt: skip
    add("ANIA-EXP", EmergencyRole.emergency_coordinator, "S-AIR", RosterShift.night, dep=mf)
    add("ANIA-EXP", EmergencyRole.emergency_coordinator, "S-LAND", RosterShift.day,
        user=ctx.uid("fahad.mutairi"))  # fmt: skip
    for site in ("S-TWR", "S-POD"):
        add("RBT-52", EmergencyRole.emergency_coordinator, site, RosterShift.day,
            user=ctx.uid("ibrahim.saleh"))  # fmt: skip
    db.flush()


# ---- A.5 assets and checks -----------------------------------------------------------------------

# project, site prefix, site, type, count, zones (round robin), owners (round robin)
ASSET_PLAN = [
    ("ANIA-EXP", "SAIR", "S-AIR", AT.fire_extinguisher, 120, ["Z-APR-21", "Z-TWB", "Z-ILS33R"],
     ["GULFPAVE", "RAWABI"]),
    ("ANIA-EXP", "SLAND", "S-LAND", AT.fire_extinguisher, 180, ["Z-PIERB", "Z-MSCP", "Z-LAY1"],
     ["RAWABI", "NAJD", "SAHARA"]),
    ("ANIA-EXP", "SAIR", "S-AIR", AT.first_aid_kit, 18, ["Z-APR-21", "Z-TWB", "Z-ILS33R"],
     ["GULFPAVE"]),
    ("ANIA-EXP", "SLAND", "S-LAND", AT.first_aid_kit, 28, ["Z-PIERB", "Z-MSCP", "Z-LAY1"],
     ["RAWABI", "NAJD"]),
    ("ANIA-EXP", "SAIR", "S-AIR", AT.aed, 4, ["Z-APR-21", "Z-TWB"], ["GULFPAVE"]),
    ("ANIA-EXP", "SLAND", "S-LAND", AT.aed, 4, ["Z-PIERB", "Z-LAY1"], ["RAWABI"]),
    ("ANIA-EXP", "SAIR", "S-AIR", AT.eyewash_portable, 4, ["Z-APR-21", "Z-TWB"], ["GULFPAVE"]),
    ("ANIA-EXP", "SLAND", "S-LAND", AT.eyewash_portable, 6, ["Z-PIERB", "Z-MSCP", "Z-LAY1"],
     ["RAWABI"]),
    ("ANIA-EXP", "SLAND", "S-LAND", AT.eyewash_plumbed, 4, ["Z-PIERB", "Z-MSCP"], ["RAWABI"]),
    ("ANIA-EXP", "SAIR", "S-AIR", AT.alarm_call_point, 6, ["Z-APR-21", "Z-TWB"], ["RAWABI"]),
    ("ANIA-EXP", "SLAND", "S-LAND", AT.alarm_call_point, 12, ["Z-PIERB", "Z-MSCP", "Z-LAY1"],
     ["RAWABI"]),
    ("ANIA-EXP", "SAIR", "S-AIR", AT.siren_air_horn, 2, ["Z-APR-21"], ["RAWABI"]),
    ("ANIA-EXP", "SLAND", "S-LAND", AT.siren_air_horn, 4, ["Z-PIERB", "Z-LAY1"], ["RAWABI"]),
    ("ANIA-EXP", "SAIR", "S-AIR", AT.stretcher, 4, ["Z-APR-21", "Z-TWB"], ["GULFPAVE"]),
    ("ANIA-EXP", "SLAND", "S-LAND", AT.stretcher, 8, ["Z-PIERB", "Z-MSCP", "Z-LAY1"], ["RAWABI"]),
    ("ANIA-EXP", "SLAND", "S-LAND", AT.rescue_kit_height, 2, ["Z-LAY1"], ["RAWABI"]),
    ("ANIA-EXP", "SLAND", "S-LAND", AT.fire_blanket, 6, ["Z-PIERB", "Z-LAY1"], ["RAWABI"]),
    ("RBT-52", "STWR", "S-TWR", AT.fire_extinguisher, 70, ["Z-CORE", "Z-TC01"], ["QIMMA", "DLIFT"]),
    ("RBT-52", "SPOD", "S-POD", AT.fire_extinguisher, 40, ["Z-B4", "Z-FAC"], ["QIMMA"]),
    ("RBT-52", "STWR", "S-TWR", AT.first_aid_kit, 12, ["Z-CORE", "Z-TC01"], ["QIMMA"]),
    ("RBT-52", "SPOD", "S-POD", AT.first_aid_kit, 8, ["Z-B4", "Z-FAC"], ["QIMMA"]),
    ("RBT-52", "STWR", "S-TWR", AT.aed, 2, ["Z-CORE"], ["QIMMA"]),
    ("RBT-52", "SPOD", "S-POD", AT.aed, 1, ["Z-FAC"], ["QIMMA"]),
    ("RBT-52", "SPOD", "S-POD", AT.eyewash_portable, 2, ["Z-B4"], ["QIMMA"]),
    ("RBT-52", "STWR", "S-TWR", AT.eyewash_portable, 2, ["Z-CORE"], ["QIMMA"]),
    ("RBT-52", "STWR", "S-TWR", AT.alarm_call_point, 8, ["Z-CORE", "Z-TC01"], ["QIMMA"]),
    ("RBT-52", "SPOD", "S-POD", AT.alarm_call_point, 4, ["Z-B4", "Z-FAC"], ["QIMMA"]),
    ("RBT-52", "STWR", "S-TWR", AT.stretcher, 4, ["Z-CORE", "Z-TC01"], ["QIMMA"]),
    ("RBT-52", "SPOD", "S-POD", AT.stretcher, 2, ["Z-FAC"], ["QIMMA"]),
    ("RBT-52", "STWR", "S-TWR", AT.rescue_kit_height, 1, ["Z-CORE"], ["QIMMA"]),
]  # fmt: skip
PREFIX = {
    AT.fire_extinguisher: "FE", AT.first_aid_kit: "FAK", AT.aed: "AED", AT.eyewash_portable: "EWP",
    AT.eyewash_plumbed: "EWS", AT.alarm_call_point: "MCP", AT.siren_air_horn: "SIR",
    AT.stretcher: "STR", AT.rescue_kit_height: "RK", AT.fire_blanket: "FB",
}  # fmt: skip
# tag → (kind, value): not-ready states at 2026-09-30 per A.8
NOT_READY: dict[str, tuple[str, Any]] = {
    **{f"FE-SAIR-{i:04d}": ("stop", date(2026, 8, 25)) for i in (3, 6, 9, 12, 15, 18)},
    **{f"FE-SAIR-{i:04d}": ("oos", date(2026, 9, 21 + k)) for k, i in enumerate((21, 24, 27, 30, 33))},
    "FAK-SLAND-03": ("missing", date(2026, 9, 22)),
    "FAK-SLAND-06": ("missing", date(2026, 9, 23)),
    "FE-SLAND-0150": ("service", date(2025, 9, 20)),
    **{f"FE-SPOD-{i:04d}": ("stop", date(2026, 8, 26)) for i in (2, 4, 6, 8, 10)},
    **{f"FE-STWR-{i:04d}": ("oos", date(2026, 9, 24 + k)) for k, i in enumerate((5, 10, 15))},
    "AED-SPOD-01": ("pads", date(2026, 9, 25)),
}  # fmt: skip


def _items(t: AssetType, fail: str | None = None) -> list[dict[str, str]]:
    return [
        {"item": x.value, "answer": "fail" if x.value == fail else "pass"}
        for x in ref.ASSET_TYPES[t][4]
    ]


def _assets(ctx: ECtx, tpi: Tpi) -> None:
    db = ctx.db
    checker = {
        "S-AIR": ctx.uid("omar.siddiqui"), "S-LAND": ctx.uid("fahad.mutairi"),
        "S-TWR": ctx.uid("ibrahim.saleh"), "S-POD": ctx.uid("ibrahim.saleh"),
    }  # fmt: skip
    counter: dict[tuple[str, int], itertools.count[int]] = {}
    checks: list[dict[str, Any]] = []
    idx = 0
    for pc, pre, site, t, count, zones, owners in ASSET_PLAN:
        pid = ctx.pid(pc)
        for i in range(1, count + 1):
            idx += 1
            width = 4 if t == AT.fire_extinguisher else 2
            tag = f"{PREFIX[t]}-{pre}-{i:0{width}d}"
            zone = ctx.zone(pc, zones[(i - 1) % len(zones)])
            owner = ctx.engs[(pc, owners[(i - 1) % len(owners)])]
            nr = NOT_READY.get(tag)
            a = EmergencyAsset(
                id=uuid.uuid4(), project_id=pid, asset_tag=tag, asset_type=t,
                site_id=ctx.site(pc, site).id, zone_id=zone.id,
                location_en=f"{zone.code} position {i}", owner_engagement_id=owner.id,
                registered_on=date(2026, 2, 20), status=AssetStatus.in_service, expiries=[],
                seed_fake=True,
            )  # fmt: skip
            if t == AT.fire_extinguisher:
                a.subtype = "co2" if i % 5 == 0 else "dcp_abc"
                a.capacity = "5 kg" if a.subtype == "co2" else "6 kg"
                a.manufactured_year = 2023 if a.subtype == "co2" else 2019 + i % 6
                a.serial_no = f"TEST-{tag}"
                a.service_provider_tpi_id = tpi.id
                a.service_ref = f"FS-TEST-2025-{8000 + idx}"
                a.last_service_on = date(2025, 10, 15) + timedelta(days=(i * 7) % 240)
            if t == AT.rescue_kit_height:
                a.last_service_on = date(2026, 1, 10)
                a.serial_no = f"TEST-{tag}"
            if t == AT.aed:
                a.expiries = [
                    {"item": "pads", "expires_on": "2027-03-31"},
                    {"item": "battery", "expires_on": "2028-06-30"},
                ]
            if t == AT.eyewash_portable:
                a.expiries = [{"item": "eyewash_fluid", "expires_on": "2027-01-31"}]
            if tag == "FE-SLAND-0142":
                a.owner_engagement_id = ctx.engs[(pc, "RAWABI")].id
                a.zone_id = ctx.zone(pc, "Z-LAY1").id
                a.subtype, a.capacity, a.manufactured_year = "dcp_abc", "6 kg", 2019
                a.service_ref, a.last_service_on = "FS-TEST-2025-8831", date(2025, 10, 10)
            if tag == "AED-SAIR-01":
                a.expiries = [
                    {"item": "pads", "expires_on": "2026-10-31"},
                    {"item": "battery", "expires_on": "2028-06-30"},
                ]
            if nr is not None and nr[0] == "service":
                a.last_service_on = nr[1]
            if nr is not None and nr[0] == "pads":
                a.expiries = [
                    {"item": "pads", "expires_on": nr[1].isoformat()},
                    {"item": "battery", "expires_on": "2028-06-30"},
                ]
            db.add(a)
            ctx.assets[tag] = a
            # checks at the interval from 2026-03-01 (offset per asset) until the clock
            iv = ref.ASSET_TYPES[t][2]
            day = REGISTER_FROM + timedelta(days=idx % iv)
            stop = CHECKS_UNTIL
            if tag == "FE-SLAND-0142":
                stop = date(2026, 8, 31)
            if nr is not None and nr[0] in ("stop", "oos", "missing"):
                stop = nr[1]
            dates = []
            while day <= stop:
                dates.append(day)
                day += timedelta(days=iv)
            if tag == "FE-SLAND-0142" and dates[-1] != date(2026, 8, 31):
                dates.append(date(2026, 8, 31))
            if nr is not None and nr[0] in ("oos", "missing") and dates[-1] != nr[1]:
                dates.append(nr[1])
            for k, d in enumerate(dates):
                last = k == len(dates) - 1
                outcome, result, items = CheckOutcome.checked, CheckResult.pass_, _items(t)
                if last and nr is not None and nr[0] == "oos":
                    result, items = CheckResult.fail, _items(t, "EC04")
                if last and nr is not None and nr[0] == "missing":
                    outcome, result, items = CheckOutcome.missing, CheckResult.fail, []
                key = (pc, d.year)
                s = next(counter.setdefault(key, itertools.count(1)))
                checks.append(
                    {
                        "id": uuid.uuid4(), "year": d.year, "seq": s,
                        "check_no": f"EAC-{pc}-{d.year}-{s:06d}", "project_id": pid,
                        "asset_id": a.id, "checked_at": at(d, 9, idx % 50),
                        "checked_by_user_id": checker[site], "method": CheckMethod.qr_scan,
                        "outcome": outcome, "items": items, "fixed_on_spot": False,
                        "result": result, "photo_ids": [], "warnings": [],
                        "status": RecordStatus.valid, "seed_fake": True,
                        "created_by_user_id": checker[site],
                    }
                )  # fmt: skip
            if nr is not None and nr[0] in ("oos", "missing"):
                a.status = AssetStatus.out_of_service if nr[0] == "oos" else AssetStatus.missing
                a.status_changed_on = nr[1]
                a.status_reason = "Seeded check failure" if nr[0] == "oos" else "Not found"
    db.flush()
    for a in ctx.assets.values():
        acommon.issue_qr(db, QrKind.EA, a.project_id, a.id, a.asset_tag)
    for i in range(0, len(checks), 2000):
        db.execute(insert(AssetCheck), checks[i : i + 2000])
    db.flush()


# ---- A.4 rescue teams ----------------------------------------------------------------------------


def _teams(ctx: ECtx, tw: EquipmentItem) -> None:
    db = ctx.db
    rows = [
        ("RT-ANIA-CSE-01", "ANIA-EXP", TeamType.confined_space, ["S-LAND"], "WKR-000021",
         ["WKR-000016", "WKR-000017"], [tw.id], [], date(2025, 10, 1)),
        ("RT-ANIA-WAH-01", "ANIA-EXP", TeamType.height, ["S-AIR", "S-LAND"], ctx.wah["ANIA-EXP"][0],
         ctx.wah["ANIA-EXP"][1:], [], ["RK-SLAND-01"], date(2025, 3, 1)),
        ("RT-RBT-WAH-01", "RBT-52", TeamType.height, ["S-TWR"], ctx.wah["RBT-52"][0],
         ctx.wah["RBT-52"][1:],
         [], ["RK-STWR-01"], date(2025, 3, 1)),
    ]  # fmt: skip
    for code, pc, tt, sites, lead, members, items, kits, created in rows:
        t = RescueTeam(
            id=uuid.uuid4(), project_id=ctx.pid(pc), team_code=code, team_type=tt,
            site_ids=[ctx.site(pc, s).id for s in sites], lead_deployment_id=ctx.dep(pc, lead).id,
            member_deployment_ids=[ctx.dep(pc, m).id for m in members], equipment_item_ids=items,
            asset_ids=[ctx.assets[k].id for k in kits], created_on=created,
            status=ActiveStatus.active, alerts_sent=[], seed_fake=True,
        )  # fmt: skip
        db.add(t)
        ctx.teams[code] = t
    db.flush()


# ---- A.6 drills ----------------------------------------------------------------------------------

TL_OFFSETS: dict[DrillType, dict[str, int]] = {
    DT.evacuation_full: {"evacuation_complete_at": 420, "headcount_complete_at": 900,
                         "all_clear_at": 1500},
    DT.medical_response: {"first_responder_at": 180, "all_clear_at": 1200},
    DT.cse_rescue: {"casualty_reached_at": 300, "casualty_recovered_at": 720},
    DT.height_rescue: {"casualty_reached_at": 240, "casualty_recovered_at": 540},
    DT.tabletop: {"all_clear_at": 7200},
    DT.airport_exercise: {"all_clear_at": 5400},
}  # fmt: skip
# (number, project, type, site, team, date, hour, shift, announced, scenario)
HISTORY = [
    ("DRL-ANIA-EXP-2025-011", "ANIA-EXP", DT.height_rescue, "S-LAND", "RT-ANIA-WAH-01",
     date(2025, 4, 20), 10, DrillShift.day, True, "SC-WAH"),
    ("DRL-ANIA-EXP-2025-014", "ANIA-EXP", DT.evacuation_full, "S-AIR", None, date(2025, 9, 21), 22,
     DrillShift.night, True, "SC-FIRE"),
    ("DRL-ANIA-EXP-2025-019", "ANIA-EXP", DT.cse_rescue, "S-LAND", "RT-ANIA-CSE-01",
     date(2025, 10, 20), 10, DrillShift.day, True, "SC-CSE"),
    ("DRL-ANIA-EXP-2025-016", "ANIA-EXP", DT.tabletop, None, None, date(2025, 9, 30), 9,
     DrillShift.day, True, "SC-GAS"),
    ("DRL-ANIA-EXP-2025-021", "ANIA-EXP", DT.evacuation_full, "S-LAND", None, date(2025, 11, 10),
     11, DrillShift.day, False, "SC-FIRE"),
    ("DRL-ANIA-EXP-2026-002", "ANIA-EXP", DT.airport_exercise, "S-AIR", None, date(2026, 1, 15),
     9, DrillShift.day, True, "SC-AIRCRAFT"),
    ("DRL-ANIA-EXP-2026-003", "ANIA-EXP", DT.evacuation_full, "S-AIR", None, date(2026, 1, 20), 11,
     DrillShift.day, False, "SC-FIRE"),
    ("DRL-ANIA-EXP-2026-005", "ANIA-EXP", DT.evacuation_full, "S-AIR", None, date(2026, 3, 1), 10,
     DrillShift.day, True, "SC-FIRE"),
    ("DRL-ANIA-EXP-2026-006", "ANIA-EXP", DT.medical_response, "S-LAND", None, date(2026, 3, 7),
     10, DrillShift.day, True, "SC-MED"),
    ("DRL-ANIA-EXP-2026-007", "ANIA-EXP", DT.evacuation_full, "S-LAND", None, date(2026, 3, 18),
     10, DrillShift.day, True, "SC-FIRE"),
    ("DRL-ANIA-EXP-2026-008", "ANIA-EXP", DT.medical_response, "S-AIR", None, date(2026, 3, 28),
     10, DrillShift.day, True, "SC-MED"),
    ("DRL-ANIA-EXP-2026-012", "ANIA-EXP", DT.height_rescue, "S-LAND", "RT-ANIA-WAH-01",
     date(2026, 4, 12), 10, DrillShift.day, True, "SC-WAH"),
    ("DRL-ANIA-EXP-2026-024", "ANIA-EXP", DT.evacuation_full, "S-AIR", None, date(2026, 8, 20), 10,
     DrillShift.day, True, "SC-FIRE"),
    ("DRL-RBT-52-2025-009", "RBT-52", DT.height_rescue, "S-TWR", "RT-RBT-WAH-01",
     date(2025, 9, 15), 10, DrillShift.day, True, "SC-WAH"),
    ("DRL-RBT-52-2025-010", "RBT-52", DT.tabletop, None, None, date(2025, 9, 25), 9,
     DrillShift.day, True, "SC-COLLAPSE"),
    ("DRL-RBT-52-2026-001", "RBT-52", DT.evacuation_full, "S-TWR", None, date(2026, 1, 12), 11,
     DrillShift.day, False, "SC-FIRE"),
    ("DRL-RBT-52-2026-002", "RBT-52", DT.evacuation_full, "S-POD", None, date(2026, 2, 2), 11,
     DrillShift.day, False, "SC-FIRE"),
    ("DRL-RBT-52-2026-003", "RBT-52", DT.evacuation_full, "S-POD", None, date(2026, 3, 1), 10,
     DrillShift.day, True, "SC-FIRE"),
    ("DRL-RBT-52-2026-004", "RBT-52", DT.medical_response, "S-TWR", None, date(2026, 3, 1), 14,
     DrillShift.day, True, "SC-MED"),
    ("DRL-RBT-52-2026-005", "RBT-52", DT.evacuation_full, "S-TWR", None, date(2026, 3, 11), 10,
     DrillShift.day, True, "SC-FIRE"),
    ("DRL-RBT-52-2026-006", "RBT-52", DT.medical_response, "S-POD", None, date(2026, 3, 19), 10,
     DrillShift.day, True, "SC-MED"),
    ("DRL-RBT-52-2026-009", "RBT-52", DT.evacuation_full, "S-POD", None, date(2026, 8, 15), 10,
     DrillShift.day, True, "SC-FIRE"),
    ("DRL-RBT-52-2026-010", "RBT-52", DT.medical_response, "S-TWR", None, date(2026, 8, 16), 10,
     DrillShift.day, True, "SC-MED"),
    # September 2026 (A.6), satisfactory
    ("DRL-ANIA-EXP-2026-029", "ANIA-EXP", DT.medical_response, "S-LAND", None, date(2026, 9, 6),
     10, DrillShift.day, True, "SC-MED"),
    ("DRL-ANIA-EXP-2026-033", "ANIA-EXP", DT.medical_response, "S-AIR", None, date(2026, 9, 27),
     10, DrillShift.day, True, "SC-MED"),
    ("DRL-ANIA-EXP-2026-035", "ANIA-EXP", DT.tabletop, None, None, date(2026, 9, 29), 9,
     DrillShift.day, True, "SC-GAS"),
    ("DRL-RBT-52-2026-013", "RBT-52", DT.medical_response, "S-POD", None, date(2026, 9, 18), 10,
     DrillShift.day, True, "SC-MED"),
    ("DRL-RBT-52-2026-014", "RBT-52", DT.tabletop, None, None, date(2026, 9, 24), 9,
     DrillShift.day, True, "SC-COLLAPSE"),
]  # fmt: skip


def _people(ctx: ECtx, pc: str, site: str | None) -> tuple[uuid.UUID, uuid.UUID]:
    if pc == "RBT-52":
        return ctx.uid("ibrahim.saleh"), ctx.uid("lina.haddad")
    cond = ctx.uid("omar.siddiqui") if site == "S-AIR" else ctx.uid("fahad.mutairi")
    return cond, ctx.uid("noura.qahtani")


def _drill(
    ctx: ECtx, no: str, pc: str, t: DrillType, site: str | None, team: str | None, alarm: datetime,
    shift: DrillShift, announced: bool, scen: str, offsets: dict[str, int] | None = None,
    **extra: Any,
) -> Drill:  # fmt: skip
    from app.services.emergency import drills as em_drills  # noqa: PLC0415

    year, seq = int(no.split("-")[-2]), int(no.rsplit("-", maxsplit=1)[-1])
    cond, ev = _people(ctx, pc, site)
    tl = {"alarm_at": iso(alarm)}
    for k, sec in (offsets if offsets is not None else TL_OFFSETS[t]).items():
        tl[k] = iso(alarm + timedelta(seconds=sec))
    d = Drill(
        id=uuid.uuid4(), year=year, seq=seq, drill_no=no, project_id=ctx.pid(pc), drill_type=t,
        scenario_code=scen, site_id=ctx.site(pc, site).id if site else None, zone_ids=[],
        team_id=ctx.teams[team].id if team else None, planned_at=alarm, shift=shift,
        announced=announced, suspend_permits=t in ref.MUSTER_TYPES, conductor_user_id=cond,
        evaluator_user_ids=[ev], timeline=tl, targets={}, external_participation=[],
        late_entry=False, conducted_at=alarm, status=DrillStatus.conducted, alerts_sent=[],
        created_by_user_id=cond, seed_fake=True, **extra,
    )  # fmt: skip
    ctx.db.add(d)
    ctx.db.flush()
    d.targets = em_drills._targets(ctx.db, d)
    return d


def _evaluate(
    ctx: ECtx, d: Drill, when: datetime, fails: tuple[str, ...] = (), simple: bool = True
) -> None:
    from app.services.emergency import drills as em_drills  # noqa: PLC0415

    crit = {
        c.value: ("fail" if c.value in fails else "pass") for c in ref.RELEVANT_DC[d.drill_type]
    }
    ev = d.evaluator_user_ids[0]
    if simple:
        d.evaluation = {
            "criteria": [{"criterion": k, "answer": v} for k, v in crit.items()],
            "findings": [], "summary_en": None, "summary_ar": None, "evaluated_by": str(ev),
            "evaluated_at": iso(when),
        }  # fmt: skip
        d.status = DrillStatus.evaluated
        d.result = em_drills.result_of(ctx.db, d)
        return
    set_now(when)
    try:
        em_drills.apply_evaluation(ctx.db, d, crit, [], ev, when)
    finally:
        set_now(SEED_CLOCK)


def _drills(ctx: ECtx) -> None:
    from app.services.emergency import muster as mu  # noqa: PLC0415

    db = ctx.db
    for no, pc, t, site, team, d0, h, shift, ann, scen in HISTORY:
        d = _drill(ctx, no, pc, t, site, team, at(d0, h), shift, ann, scen)
        _evaluate(ctx, d, at(d0 + timedelta(days=1), 12))
    # DRL-RBT-52-2026-012 (ED9): evac 9.2, headcount 15.0, no muster record
    d = _drill(
        ctx, "DRL-RBT-52-2026-012", "RBT-52", DT.evacuation_full, "S-TWR", None,
        at(date(2026, 9, 10), 10), DrillShift.day, True, "SC-FIRE",
        {"evacuation_complete_at": 552, "headcount_complete_at": 900, "all_clear_at": 1320},
    )  # fmt: skip
    _evaluate(ctx, d, at(date(2026, 9, 11), 12))

    # ED3: DRL-ANIA-EXP-2026-031, unannounced, S-LAND, count mode
    alarm = at(date(2026, 9, 17), 10)
    d = _drill(
        ctx, "DRL-ANIA-EXP-2026-031", "ANIA-EXP", DT.evacuation_full, "S-LAND", None, alarm,
        DrillShift.day, False, "SC-FIRE", {"evacuation_complete_at": 520, "all_clear_at": 1860},
    )  # fmt: skip
    d.status = DrillStatus.in_progress
    m = mu.open_muster(
        db, d.project_id, MusterSource.drill, d.id, d.site_id, None, alarm, True,  # type: ignore[arg-type]
        d.conductor_user_id,
    )  # fmt: skip
    m.seed_fake = True
    d.muster_id = m.id
    fahad = str(ctx.uid("fahad.mutairi"))
    t1, t2, t3 = (
        alarm + timedelta(minutes=12),
        alarm + timedelta(minutes=14),
        at(date(2026, 9, 17), 10, 24, 10),
    )
    eng = {c: str(ctx.engs[("ANIA-EXP", c)].id) for c in ("RAWABI", "NAJD", "SAHARA")}
    m.counts = [
        {"engagement_id": eng["RAWABI"], "expected": 610, "accounted": 608, "by": fahad,
         "at": iso(t1), "resolved": [{"reason": "off_site_confirmed", "count": 2, "note": None,
                                      "at": iso(t2)}]},
        {"engagement_id": eng["NAJD"], "expected": 520, "accounted": 520, "by": fahad,
         "at": iso(t1), "resolved": []},
        {"engagement_id": eng["SAHARA"], "expected": 282, "accounted": 281, "by": fahad,
         "at": iso(t1), "resolved": [{"reason": "found_on_site", "count": 1,
                                      "note": "Pier B level 3 stairwell", "at": iso(t3)}]},
    ]  # fmt: skip
    db.flush()
    mu.on_found(db, m, m.muster_no, ctx.engs[("ANIA-EXP", "SAHARA")].id)
    mu.reconcile(db, m)
    mu.close(db, m, alarm + timedelta(seconds=1860))
    d.status = DrillStatus.conducted
    _evaluate(ctx, d, at(date(2026, 9, 18), 11), fails=("DC02",), simple=False)

    # ED4: DRL-ANIA-EXP-2026-034, night, S-AIR, roll mode
    alarm = at(date(2026, 9, 24), 23)
    d = _drill(
        ctx, "DRL-ANIA-EXP-2026-034", "ANIA-EXP", DT.evacuation_full, "S-AIR", None, alarm,
        DrillShift.night, True, "SC-FIRE", {"evacuation_complete_at": 375, "all_clear_at": 1800},
        plan_note="AOCC informed: AOCC-LOG-TEST-388",
    )  # fmt: skip
    d.status = DrillStatus.in_progress
    m = mu.open_muster(
        db, d.project_id, MusterSource.drill, d.id, d.site_id, None, alarm, False,  # type: ignore[arg-type]
        d.conductor_user_id,
    )  # fmt: skip
    m.seed_fake = True
    d.muster_id = m.id
    es = mu.entries(db, m)
    omar = ctx.uid("omar.siddiqui")
    ap = ctx.aps["AP-SAIR-01"].id
    n = len(es)
    scan_end = alarm + timedelta(minutes=12, seconds=5)
    for i, e in enumerate(es):
        e.seed_fake = True
        if i < n - 8:
            e.state, e.method, e.ap_id, e.by_user_id = (
                EntryState.accounted,
                EntryMethod.scan,
                ap,
                omar,
            )
            e.at = alarm + timedelta(seconds=180 + (i * 545) // max(n - 9, 1))
        elif i < n - 6:
            e.state, e.method, e.by_user_id, e.at = (
                EntryState.accounted,
                EntryMethod.tick,
                omar,
                scan_end,
            )
        elif i < n - 2:
            e.state, e.by_user_id = EntryState.resolved, omar
            e.resolution_reason = ResolutionReason.left_site_no_exit_scan
            e.at = at(date(2026, 9, 24), 23, 15, 40)
        else:
            e.state, e.by_user_id = EntryState.resolved, omar
            e.resolution_reason = ResolutionReason.off_site_confirmed
            e.at = at(date(2026, 9, 24), 23, 17, 30)
    db.flush()
    mu.reconcile(db, m)
    mu.close(db, m, alarm + timedelta(seconds=1800))
    d.status = DrillStatus.conducted
    _evaluate(ctx, d, at(date(2026, 9, 25), 11), simple=False)
    db.flush()


# ---- A.7 events ----------------------------------------------------------------------------------


def _events(ctx: ECtx) -> None:
    db = ctx.db
    a = ctx.pid("ANIA-EXP")
    inc = db.scalar(select(Incident).where(Incident.ref == "INC-ANIA-EXP-2026-0285"))
    noura = ctx.uid("noura.qahtani")
    rows: list[dict[str, Any]] = [
        dict(
            seq=3, event_type=EventType.false_alarm, site="S-LAND", zones=["Z-PIERB"],
            location_en="Pier B, call point knocked by a forklift", raised=at(date(2026, 9, 3), 9, 12),
            by=ctx.uid("fahad.mutairi"), response=ResponseType.local_response, fr=None, ext=[],
            cas=0, incident=None, clear=at(date(2026, 9, 3), 9, 20),
            reviewed=at(date(2026, 9, 4), 11),
        ),
        dict(
            seq=4, event_type=EventType.medical_emergency, site="S-AIR", zones=["Z-APR-21"],
            location_en="Stand 24", raised=at(date(2026, 9, 22), 13, 52), by=ctx.uid("omar.siddiqui"),
            response=ResponseType.local_response, fr=at(date(2026, 9, 22), 13, 55),
            ext=[{"agency": "red_crescent", "called_at": iso(at(date(2026, 9, 22), 13, 56)),
                  "arrived_at": iso(at(date(2026, 9, 22), 14, 9)), "reference": "SRCA-TEST-2209"}],
            cas=1, incident=inc.id if inc else None, clear=at(date(2026, 9, 22), 14, 20),
            reviewed=at(date(2026, 9, 24), 10),
        ),
    ]  # fmt: skip
    for r in rows:
        e = EmergencyEvent(
            id=uuid.uuid4(), year=2026, seq=r["seq"], event_no=f"EMV-ANIA-EXP-2026-{r['seq']:03d}",
            project_id=a, event_type=r["event_type"], site_id=ctx.site("ANIA-EXP", r["site"]).id,
            zone_ids=[ctx.zone("ANIA-EXP", z).id for z in r["zones"]], location_en=r["location_en"],
            raised_at=r["raised"], declared_by_user_id=r["by"], response_type=r["response"],
            first_responder_at=r["fr"], external_services=r["ext"], casualties_count=r["cas"],
            incident_id=r["incident"], all_clear_at=r["clear"], all_clear_by_user_id=r["by"],
            review={"what_worked": "Fast first response and clear communication.",
                    "issues": "None significant.", "erp_update_needed": False, "ca_ids": [],
                    "reviewed_by": str(noura), "reviewed_at": iso(r["reviewed"])},
            late_entry=False, status=EventStatus.reviewed, alerts_sent=[],
            created_by_user_id=r["by"], seed_fake=True,
        )  # fmt: skip
        db.add(e)
    db.flush()


# ---- entry point ---------------------------------------------------------------------------------


def seed_emergency_data(db: Session) -> None:
    if already_seeded(db):
        return
    from app.models import Project  # noqa: PLC0415

    if db.scalar(select(Project.id).where(Project.code == "ANIA-EXP")) is None:
        return
    ctx = ECtx(db)
    try:
        set_now(SEED_CLOCK)
        _settings(ctx)
        extra = _phase45(ctx)
        _erps(ctx)
        _aps(ctx)
        _roster(ctx)
        _assets(ctx, extra["tpi"])
        _teams(ctx, extra["tw"])
        _drills(ctx)
        _events(ctx)
        db.flush()
        ec.clear_cache(db)
        # The §11.6 item 3 CSE-RESCUE / WAH-RESCUE records satisfy crew hooks (CSE-RESCUE covers
        # CSE-ATTENDANT): re-evaluate live permits so stored crew eligibility matches, as the 6a
        # and 5-training seeds do after adding their records.
        from app.seed_med import _refresh_permits  # noqa: PLC0415

        _refresh_permits(db)
    finally:
        set_now(None)


def main() -> int:  # pragma: no cover - CLI
    from app.db.session import get_sessionmaker  # noqa: PLC0415

    with get_sessionmaker()() as db:
        seed_emergency_data(db)
        db.commit()
    print("Emergency seed loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
