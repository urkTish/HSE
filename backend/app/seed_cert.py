"""Phase 4 seed (spec 4-third-party-cert Appendix A; every row `seed_fake`).

Runs on top of the Phase 0-3 Appendix A world, idempotently (skipped when a TPI exists). Rows are
written directly (as the Phase 3 bulk history is) with the values the services would compute
(§6.1 strictest-wins validity, §6.2 caps, §6.3 defect due dates, SF-5 tags), so that:
- the named rows of A.2-A.8 are in their "status at seed" at the shared clock 2026-10-06 10:00;
- the bulk rows reproduce the September 2026 KPIs of Z11 / A.10 exactly at as_of 2026-09-30.

Deviations (DECISIONS): Phase 2 bulk deployments of unnamed workers that no Phase 3 row uses are
re-traded (to / from `labourer`) so that the mapped-trade populations of A.10 exist; Bikash Rai
(WKR-000104) is on RBT-52 in the Phase 2 world, so the "rigger not in force" of ANIA-EXP is a
bulk worker and Bikash is RBT-52's; VEH-0110 does not exist (DL-MC-01 has no vehicle link).
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.access_enums import DeploymentStatus, HookKind, QrKind, QrTokenStatus, WorkerIdType
from app.core.cert_enums import (
    AccreditationBody,
    AccreditationStandard,
    BanReason,
    BanStatus,
    CertificateStatus,
    CertInspectionType,
    CertKind,
    CertLevel,
    CertLimitingFactor,
    CertStatusReason,
    CertVerificationMethod,
    ConfigurationEventType,
    DefectCategory,
    DefectSource,
    DefectStatus,
    EquipmentBlacklistReason,
    EquipmentCertCategory,
    EquipmentDeploymentStatus,
    EquipmentSubtype,
    HookStage,
    IdMatchResult,
    LineResult,
    NameMatch,
    ScaffoldInspectionResult,
    ScaffoldInspectionType,
    ScaffoldStatus,
    ScaffoldTagStatus,
    ScaffoldType,
    ServiceStatus,
    ServiceStatusReason,
    TpiBlacklistScope,
    TpiKind,
    TpiStatus,
    VerificationOutcome,
    VerificationStatus,
)
from app.core.clock import set_now
from app.core.hse_enums import Trade
from app.core.text import search_blob
from app.kpi.periods import add_months
from app.models import (
    CertificationBan,
    CertVerification,
    ConfigurationEvent,
    Contractor,
    Deployment,
    EquipmentBlacklistEvent,
    EquipmentCertificate,
    EquipmentCertLine,
    EquipmentDefect,
    EquipmentDeployment,
    EquipmentItem,
    EquipmentStatusEvent,
    HookPolicyState,
    PermitCrew,
    PersonnelCertificate,
    Project,
    ProjectEngagement,
    PtwAppointment,
    Scaffold,
    ScaffoldInspection,
    Site,
    Tpi,
    TpiAccreditation,
    User,
    Vehicle,
    WapCrew,
    Worker,
    Zone,
)
from app.services.access import common as acommon
from app.services.cert import reference as ref
from app.services.cert import settings as cset

RIYADH = ZoneInfo("Asia/Riyadh")
Q = EquipmentCertCategory
ST = EquipmentSubtype
CS = CertificateStatus
SS = ServiceStatus
KPI_DAY = date(2026, 9, 30)
SEP1 = date(2026, 9, 1)


def at(y: int, m: int, d: int, h: int = 9, mi: int = 0) -> datetime:
    """Local Riyadh wall time → UTC."""
    return datetime(y, m, d, h, mi, tzinfo=RIYADH).astimezone(UTC)


def at_d(d: date, h: int = 9, mi: int = 0) -> datetime:
    return at(d.year, d.month, d.day, h, mi)


def interval(cat: Q) -> int:
    e = ref.EQC.get(cat)
    return int(e.interval_months) if e and e.interval_months else 12


def line_validity(
    cat: Q, inspected: date, printed: date | None
) -> tuple[date, date, CertLimitingFactor]:
    """§6.1: valid_until = min(printed_next_due, add_months(inspected, n) − 1 day)."""
    end = add_months(inspected, interval(cat)) - timedelta(days=1)
    if printed is None or end < printed:
        return end, end, CertLimitingFactor.category_interval
    return end, printed, CertLimitingFactor.printed_next_due


def inspected_for(cat: Q, valid_until: date) -> date:
    """The inspection date whose interval ends on valid_until."""
    return add_months(valid_until + timedelta(days=1), -interval(cat))


def cap_validity(
    code: str, issued: date, printed: date | None
) -> tuple[date, date, CertLimitingFactor]:
    """§6.2: valid_until = min(printed_expiry, add_months(issued, cap) − 1 day)."""
    p = ref.PCT.get(code)
    cap = p.cap_months if p else 36
    end = add_months(issued, cap) - timedelta(days=1)
    if printed is None or end < printed:
        return end, end, CertLimitingFactor.cap
    return end, printed, CertLimitingFactor.printed_expiry


class Ctx:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.rng = random.Random(20261001)
        self.projects = {p.code: p for p in db.scalars(select(Project))}
        code_of = {p.id: p.code for p in self.projects.values()}
        self.sites = {(code_of[s.project_id], s.code): s for s in db.scalars(select(Site))}
        self.zones = {z.code: z for z in db.scalars(select(Zone))}
        self.engs: dict[tuple[str, str], ProjectEngagement] = {}
        self.contractors: dict[str, Contractor] = {}
        for e, c in db.execute(
            select(ProjectEngagement, Contractor).join(
                Contractor, Contractor.id == ProjectEngagement.contractor_id
            )
        ):
            self.engs[(code_of[e.project_id], c.short_code)] = e
            self.contractors[c.short_code] = c
        self.users = {u.email.split("@")[0]: u for u in db.scalars(select(User))}
        self.workers = {w.worker_no: w for w in db.scalars(select(Worker).where(Worker.seq < 1000))}
        self.tpis: dict[str, Tpi] = {}
        self.items: dict[str, EquipmentItem] = {}
        self.deps: dict[str, EquipmentDeployment] = {}
        self.item_seq = 0
        self.dep_seq: dict[str, int] = {}
        self.pc_seq = 0
        self.defect_seq: dict[str, int] = {}
        self.cert_n = 0

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


def already_seeded(db: Session) -> bool:
    return db.scalar(select(Tpi.id).limit(1)) is not None


# ---- A.2 TPIs ----

LIFTING = [
    "tower_crane", "mobile_crane", "crawler_crane", "loader_crane", "overhead_gantry_crane",
    "construction_hoist", "mast_climber", "bmu", "man_basket", "lifting_accessory", "tripod_winch",
]  # fmt: skip
TPIS: list[dict[str, Any]] = [
    {
        "code": "AICC", "en": "Arabian Inspection & Certification Co. (test)",
        "ar": "العربية للفحص والشهادات (تجريبي)",
        "kinds": [TpiKind.inspection_body, TpiKind.personnel_certification_body],
        "status": TpiStatus.approved, "portal": "https://verify.aicc-test.example",
        "domains": ["verify.aicc-test.example", "aicc-test.example"],
        "email": "certs@verify.aicc-test.example", "country": "SA", "cr": "1010000901",
        "acc": [
            (AccreditationStandard.iso_iec_17020, "SAC-IB-TEST-0101",
             [*LIFTING, "mewp", "forklift", "telehandler", "excavator", "wheel_loader",
              "piling_rig", "concrete_pump_boom", "pressure_vessel"], [], date(2027, 6, 30)),
            (AccreditationStandard.iso_iec_17024, "SAC-PC-TEST-0102", [],
             ["CRANE-OPERATOR", "RIGGER", "SIGNALLER", "BANKSMAN", "MEWP-OPERATOR",
              "FORKLIFT-OPERATOR", "TELEHANDLER-OPERATOR", "PLANT-OPERATOR"], date(2027, 6, 30)),
        ],
        "checked": True,
    },
    {
        "code": "NKTI", "en": "Najm Kingdom Technical Inspection (test)",
        "ar": "نجم المملكة للفحص الفني (تجريبي)", "kinds": [TpiKind.inspection_body],
        "status": TpiStatus.approved, "portal": "https://nkti-test.example",
        "domains": ["nkti-test.example"], "country": "SA", "cr": "1010000902",
        "acc": [(AccreditationStandard.iso_iec_17020, "SAC-IB-TEST-0201",
                 ["tower_crane", "mobile_crane", "crawler_crane", "construction_hoist",
                  "pressure_vessel"], [], date(2026, 11, 2))],
        "checked": True,
    },
    {
        "code": "MLIS", "en": "Mediterranean Lifting Inspection Services (test)",
        "ar": "خدمات فحص الرفع المتوسطية (تجريبي)", "kinds": [TpiKind.inspection_body],
        "status": TpiStatus.pending_approval, "email": "inspect@mlis-test.example",
        "domains": ["mlis-test.example"], "country": "CY", "foreign": "CY-TEST-7781",
        "acc": [(AccreditationStandard.iso_iec_17020, "ILAC-IB-TEST-0301",
                 ["lifting_accessory"], [], date(2027, 12, 31))],
        "body": AccreditationBody.ilac_mra_other, "checked": False,
    },
    {
        "code": "DSPC", "en": "Desert Skills Personnel Certification (test)",
        "ar": "الصحراء لاعتماد الكفاءات (تجريبي)", "kinds": [TpiKind.personnel_certification_body],
        "status": TpiStatus.approved, "portal": "https://dspc-test.example",
        "domains": ["dspc-test.example"], "country": "SA", "cr": "1010000904",
        "acc": [(AccreditationStandard.iso_iec_17024, "SAC-PC-TEST-0401", [],
                 ["SCAFFOLDER", "SCAFFOLD-INSPECTOR", "GAS-TESTER", "ROPE-ACCESS"],
                 date(2027, 9, 30))],
        "checked": True,
    },
    {
        "code": "FNDT", "en": "Falcon NDT Certification (test)",
        "ar": "الصقر لاعتماد الفحص غير الإتلافي (تجريبي)", "kinds": [TpiKind.ndt_body],
        "status": TpiStatus.approved, "email": "verify@fndt-test.example",
        "domains": ["fndt-test.example"], "country": "SA", "cr": "1010000905",
        "acc": [(AccreditationStandard.iso_iec_17024, "SAC-PC-TEST-0501", [], ["RADIOGRAPHER"],
                 date(2028, 1, 31))],
        "checked": True,
    },
    {
        "code": "GCAL", "en": "Gulf Calibration Laboratory (test)",
        "ar": "مختبر الخليج للمعايرة (تجريبي)", "kinds": [TpiKind.calibration_lab],
        "status": TpiStatus.approved, "email": "cal@gcal-test.example",
        "domains": ["gcal-test.example"], "country": "SA", "cr": "1010000906",
        "acc": [(AccreditationStandard.iso_iec_17025, "SAC-CL-TEST-0601", [], [],
                 date(2027, 3, 31))],
        "checked": True,
    },
    {
        "code": "QUICKCERT", "en": "QuickCert Inspections (test)", "ar": "كويك سيرت (تجريبي)",
        "kinds": [TpiKind.inspection_body, TpiKind.personnel_certification_body],
        "status": TpiStatus.blacklisted, "domains": ["quickcert-test.example"], "country": "SA",
        "cr": "1010000907",
        "acc": [(AccreditationStandard.iso_iec_17020, "SAC-IB-TEST-0701", ["forklift"],
                 ["SCAFFOLDER"], date(2027, 1, 31))],
        "checked": False,
    },
]  # fmt: skip


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _seed_tpis(ctx: Ctx) -> None:
    db = ctx.db
    for t in TPIS:
        row = Tpi(
            id=uuid.uuid4(),
            tpi_code=t["code"],
            legal_name_en=t["en"],
            legal_name_ar=t["ar"],
            name_norm_en=_norm(t["en"]),
            name_norm_ar=_norm(t["ar"]),
            kinds=[k.value for k in t["kinds"]],
            country=t["country"],
            cr_number=t.get("cr"),
            foreign_reg_no=t.get("foreign"),
            verification_portal_url=t.get("portal"),
            verification_domains=t.get("domains", []),
            verification_email=t.get("email"),
            status=t["status"],
            approved_by_user_id=ctx.faisal if t["status"] != TpiStatus.pending_approval else None,
            approved_at=at(2026, 1, 10) if t["status"] != TpiStatus.pending_approval else None,
            seed_fake=True,
            created_at=at(2026, 1, 5),
            updated_at=at(2026, 9, 20) if t["code"] == "QUICKCERT" else at(2026, 1, 10),
        )
        if t["code"] == "QUICKCERT":
            row.status_reason = (
                "Certificates not traceable in TPI records; verification returned not found "
                "(review 2027-03-20)."
            )
            row.blacklist_scope = TpiBlacklistScope.all_certificates
            row.blacklisted_on = date(2026, 9, 20)
        db.add(row)
        db.flush()
        ctx.tpis[t["code"]] = row
        for std, no, cats, types, until in t["acc"]:
            db.add(
                TpiAccreditation(
                    id=uuid.uuid4(),
                    tpi_id=row.id,
                    accreditation_body=t.get("body", AccreditationBody.sac),
                    standard=std,
                    accreditation_no=no,
                    scope_categories=cats,
                    scope_cert_types=types,
                    valid_from=date(2025, 1, 1),
                    valid_until=until,
                    register_checked_at=at(2026, 1, 10) if t["checked"] else None,
                    register_checked_by_user_id=ctx.uid("noura.qahtani") if t["checked"] else None,
                    register_check_note="Listed on the accreditation register (test)."
                    if t["checked"]
                    else None,
                    seed_fake=True,
                    created_at=at(2026, 1, 5),
                    updated_at=at(2026, 1, 10),
                )
            )
    db.flush()


# ---- A.8 / A.9 settings and hook policy ----


def _seed_policy(ctx: Ctx) -> None:
    db = ctx.db
    for code, p in ctx.projects.items():
        s = cset.get(db, p.id)
        s.require_client_approved_tpi = False
        s.unverified_acceptance_hours = 0
        for kind in (HookKind.personnel_certificate, HookKind.equipment_certificate):
            db.add(
                HookPolicyState(
                    id=uuid.uuid4(),
                    project_id=p.id,
                    kind=kind,
                    provider_registered_on=date(2026, 10, 1),
                    critical_block_from=date(2026, 10, 8),
                    general_block_from=date(2026, 10, 31),
                    original_general_block_from=date(2026, 10, 31),
                    stage=HookStage.transition,
                    created_by_user_id=ctx.faisal,
                    seed_fake=True,
                    created_at=at(2026, 10, 1, 8),
                    updated_at=at(2026, 10, 1, 8),
                )
            )
        _ = code
    db.flush()
    from app.services.cert import policy  # noqa: PLC0415

    policy.clear_cache(db)


# ---- workers: WKR-000022 / 000023 and the mapped-trade populations (A.1, A.10) ----


def _protected(db: Session) -> set[uuid.UUID]:
    ids: set[uuid.UUID] = set(db.scalars(select(Worker.id).where(Worker.seq < 1000)))
    ids |= set(db.scalars(select(PermitCrew.worker_id)))
    ids |= set(db.scalars(select(WapCrew.worker_id)))
    ids |= {x for x in db.scalars(select(PtwAppointment.holder_worker_id)) if x is not None}
    return ids


def _live(d: Deployment) -> bool:
    return (
        d.status == DeploymentStatus.mobilised
        and d.mobilised_on <= KPI_DAY
        and (d.demobilised_on is None or d.demobilised_on > KPI_DAY)
    )


NEW_NAMED = [
    (22, "Nadeem Akhtar", "نديم أختر", "PK", "2000001022", Trade.scaffolder),
    (23, "Ferdinand Reyes", "فرديناند رييس", "PH", "2000001023", Trade.supervisor),
]


def _seed_workers(ctx: Ctx) -> None:
    db = ctx.db
    protected = _protected(db)
    eng = ctx.engs[("ANIA-EXP", "SAHARA")]
    for seq, en, ar, nat, id_no, trade in NEW_NAMED:
        no = f"WKR-{seq:06d}"
        if no in ctx.workers:
            continue
        cand = db.execute(
            select(Worker, Deployment)
            .join(Deployment, Deployment.worker_id == Worker.id)
            .where(Worker.seq >= 1000, Deployment.engagement_id == eng.id)
            .order_by(Worker.seq)
        ).all()
        for w, d in cand:
            if w.id in protected or not _live(d):
                continue
            it = WorkerIdType.iqama
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
            w.search_text = search_blob(no, en, ar)
            d.trade = trade
            ctx.workers[no] = w
            protected.add(w.id)
            break
        else:
            raise RuntimeError(f"no SAHARA bulk worker to convert into {no}")
    db.flush()
    targets = {
        "ANIA-EXP": {Trade.crane_operator: 14, Trade.rigger: 46, Trade.scaffolder: 160},
        "RBT-52": {Trade.crane_operator: 6, Trade.rigger: 18, Trade.scaffolder: 24},
    }
    mapped = set(targets["ANIA-EXP"])
    for pcode, want in targets.items():
        deps = [
            d
            for d in db.scalars(
                select(Deployment)
                .where(Deployment.project_id == ctx.pid(pcode))
                .order_by(Deployment.id)
            )
            if _live(d)
        ]
        spare = [
            d
            for d in deps
            if d.trade not in mapped and d.worker_id not in protected
            and d.trade in (Trade.labourer, Trade.other, Trade.carpenter, Trade.mason,
                            Trade.painter, Trade.steel_fixer)
        ]  # fmt: skip
        spare.sort(key=lambda d: (d.trade != Trade.labourer, str(d.id)))
        for trade, want_n in want.items():
            have = [d for d in deps if d.trade == trade]
            if len(have) > want_n:
                movable = [d for d in have if d.worker_id not in protected]
                for d in movable[: len(have) - want_n]:
                    d.trade = Trade.labourer
            elif len(have) < want_n:
                for _ in range(want_n - len(have)):
                    if not spare:
                        raise RuntimeError(f"not enough bulk workers to re-trade on {pcode}")
                    spare.pop(0).trade = trade
    db.flush()


# ---- equipment helpers ----


def _item(
    ctx: Ctx,
    tag: str,
    cat: Q,
    owner: str,
    *,
    sub: ST | None = None,
    swl: str | None = None,
    no: int | None = None,
    status: ServiceStatus = SS.in_service,
    reason: ServiceStatusReason | None = None,
    since: datetime | None = None,
    vehicle: str | None = None,
    persons: int | None = None,
    height: str | None = None,
    serial: str | None = None,
    manufacturer: str = "TestLift",
) -> EquipmentItem:
    db = ctx.db
    if no is None:
        ctx.item_seq += 1
        no = ctx.item_seq
    serial = serial or f"TESTSN-{tag}"
    veh = None
    if vehicle:
        veh = db.scalar(select(Vehicle.id).where(Vehicle.vehicle_no == vehicle))
    it = EquipmentItem(
        id=uuid.uuid4(),
        seq=no,
        equipment_no=f"EQP-{no:06d}",
        category=cat,
        subtype=sub,
        manufacturer=manufacturer,
        manufacturer_norm=manufacturer.upper(),
        model=f"{cat.value.replace('_', ' ').title()} T{no % 90 + 10}",
        serial_no=serial,
        serial_norm=serial.upper().replace("-", "").replace(" ", ""),
        year_of_manufacture=2016 + no % 9,
        owner_contractor_id=ctx.contractors[owner].id,
        vehicle_id=veh,
        rated_capacity_t=Decimal(swl) if swl else None,
        persons_capacity=persons,
        max_height_m=Decimal(height) if height else None,
        lifting_duty=cat in (Q.mobile_crane, Q.tower_crane, Q.crawler_crane, Q.lifting_accessory,
                             Q.construction_hoist, Q.man_basket, Q.telehandler, Q.forklift),
        service_status=status,
        service_status_reason=reason,
        service_status_since=since,
        seed_fake=True,
        created_at=at(2026, 3, 1),
        updated_at=since or at(2026, 3, 1),
    )  # fmt: skip
    db.add(it)
    ctx.items[tag] = it
    return it


def _deploy(
    ctx: Ctx,
    it: EquipmentItem,
    pcode: str,
    owner: str,
    tag: str,
    *,
    site: str,
    zone: str | None,
    arrived: date,
    demob: date | None = None,
) -> EquipmentDeployment:
    db = ctx.db
    ctx.dep_seq[pcode] = ctx.dep_seq.get(pcode, 0) + 1
    seq = ctx.dep_seq[pcode]
    dep = EquipmentDeployment(
        id=uuid.uuid4(),
        project_id=ctx.pid(pcode),
        seq=seq,
        deployment_no=f"EQD-{pcode}-{seq:04d}",
        equipment_id=it.id,
        engagement_id=ctx.engs[(pcode, owner)].id,
        tag=tag,
        site_ids=[ctx.sites[(pcode, site)].id],
        zone_id=ctx.zones[zone].id if zone else None,
        planned_arrival_on=arrived,
        approved_by_user_id=ctx.officer(pcode),
        approved_at=at_d(arrived - timedelta(days=2)),
        arrived_at=at_d(arrived, 8),
        arrival_inspection={
            "at": at_d(arrived, 11).isoformat(),
            "by_user_id": str(ctx.officer(pcode)),
            "result": "pass",
            "checklist": [],
            "notes": None,
            "defects": [],
        },
        arrival_inspection_passed=True,
        demobilised_on=demob,
        status=EquipmentDeploymentStatus.demobilised
        if demob
        else EquipmentDeploymentStatus.on_site,
        seed_fake=True,
        created_at=at_d(arrived - timedelta(days=5)),
        updated_at=at_d(demob or arrived),
    )
    db.add(dep)
    db.flush()
    t = acommon.issue_qr(db, QrKind.EQ, dep.project_id, dep.id, f"{pcode}-{tag}")
    t.created_at = at_d(arrived - timedelta(days=2))
    if demob is not None:
        # EM-5 / BL-3: the old sticker was revoked at demobilisation (gate → CREDENTIAL_REVOKED)
        t.status = QrTokenStatus.revoked
        t.ended_at = at_d(demob, 11)
    ctx.deps[tag] = dep
    return dep


def _event(
    ctx: Ctx,
    it: EquipmentItem,
    when: datetime,
    to: ServiceStatus,
    reason: ServiceStatusReason | None = None,
    frm: ServiceStatus | None = None,
    ref_: str | None = None,
) -> None:
    ctx.db.add(
        EquipmentStatusEvent(
            id=uuid.uuid4(),
            equipment_id=it.id,
            occurred_at=when,
            from_status=frm,
            to_status=to,
            reason=reason,
            ref=ref_,
            seed_fake=True,
        )
    )


def _cert(
    ctx: Ctx,
    pcode: str,
    tpi: str,
    cert_no: str,
    items: list[EquipmentItem],
    inspected: date,
    printed: date | None,
    *,
    itype: CertInspectionType = CertInspectionType.periodic,
    submitted: datetime | None = None,
    accepted: datetime | None = None,
    verified: datetime | None = None,
    status: CertificateStatus = CS.accepted,
    result: LineResult = LineResult.pass_,
    swl: str | None = None,
    reason: CertStatusReason | None = None,
    ended: date | None = None,
    config_ref: str | None = None,
    load_test: dict[str, Any] | None = None,
    verify_outcome: VerificationOutcome | None = VerificationOutcome.confirmed,
) -> tuple[EquipmentCertificate, list[EquipmentCertLine]]:
    db = ctx.db
    submitted = submitted or at_d(inspected + timedelta(days=1), 9)
    accepted = accepted if accepted is not None else (submitted + timedelta(hours=3))
    t = ctx.tpis[tpi]
    s = cset.get(db, ctx.pid(pcode))
    vs = VerificationStatus.verified if verified else VerificationStatus.not_verified
    if verify_outcome in (VerificationOutcome.not_found, VerificationOutcome.details_differ):
        vs = VerificationStatus.failed
    c = EquipmentCertificate(
        id=uuid.uuid4(),
        project_id=ctx.pid(pcode),
        tpi_id=t.id,
        cert_no=cert_no,
        inspection_type=itype,
        inspected_on=inspected,
        issued_on=inspected,
        printed_next_due=printed,
        inspector_name="Eng. Test Inspector (fake)",
        tpi_verification_url=(t.verification_portal_url + f"/c/{cert_no}")
        if t.verification_portal_url
        else None,
        status=status,
        status_reason=reason,
        verification_status=vs,
        verification_due_on=acommon.local_day(submitted) + timedelta(days=s.verification_due_days),
        submitted_by_user_id=ctx.rep(pcode),
        submitted_at=submitted,
        reviewed_by_user_id=ctx.officer(pcode) if status != CS.submitted else None,
        reviewed_at=accepted if status != CS.submitted else None,
        accepted_at=accepted if status != CS.submitted else None,
        verified_at=verified,
        in_force_from=max(accepted, verified) if verified and status != CS.submitted else None,
        ended_on=ended,
        seed_fake=True,
        created_at=submitted - timedelta(hours=1),
        updated_at=verified or accepted or submitted,
    )
    db.add(c)
    db.flush()
    lines = []
    for it in items:
        if result == LineResult.fail:
            iend, vu, lf = None, None, None
        else:
            iend, vu, lf = line_validity(it.category, inspected, printed)
        ln = EquipmentCertLine(
            id=uuid.uuid4(),
            certificate_id=c.id,
            equipment_id=it.id,
            serial_as_printed=it.serial_no,
            result=result,
            swl_t=Decimal(swl) if swl else it.rated_capacity_t,
            configuration_ref=config_ref,
            load_test=load_test,
            lifting_duty_certified=it.lifting_duty,
            interval_end=iend,
            valid_until=vu,
            limiting_factor=lf,
            created_at=submitted,
        )
        db.add(ln)
        lines.append(ln)
    db.flush()
    if verified is not None or verify_outcome in (
        VerificationOutcome.not_found,
        VerificationOutcome.details_differ,
    ):
        _verification(ctx, CertKind.equipment, c.id, pcode, t, verified or submitted,
                      verify_outcome or VerificationOutcome.confirmed)  # fmt: skip
    ctx.cert_n += 1
    return c, lines


def _verification(
    ctx: Ctx,
    kind: CertKind,
    cert_id: uuid.UUID,
    pcode: str,
    t: Tpi,
    when: datetime,
    outcome: VerificationOutcome,
) -> None:
    ok = outcome == VerificationOutcome.confirmed
    ctx.db.add(
        CertVerification(
            id=uuid.uuid4(),
            cert_kind=kind,
            cert_id=cert_id,
            project_id=ctx.pid(pcode),
            tpi_id=t.id,
            method=CertVerificationMethod.tpi_portal
            if t.verification_portal_url
            else CertVerificationMethod.tpi_email,
            channel_used=t.verification_portal_url or t.verification_email or t.tpi_code,
            outcome=outcome,
            reference=f"VER-TEST-{uuid.uuid4().hex[:8].upper()}",
            performed_by_user_id=ctx.officer(pcode),
            performed_at=when,
            counts_as_verification=True,
            verification_status_after=VerificationStatus.verified
            if ok
            else VerificationStatus.failed,
            created_at=when,
            seed_fake=True,
        )
    )


def _defect(
    ctx: Ctx,
    pcode: str,
    seq: int,
    cat: DefectCategory,
    desc: str,
    raised: datetime,
    *,
    item: EquipmentItem | None,
    owner: str,
    due: date | None = None,
    tpi_due: date | None = None,
    status: DefectStatus = DefectStatus.open,
    closed: datetime | None = None,
    source: DefectSource = DefectSource.site_inspection,
    source_ref: str | None = None,
    destroyed: bool = False,
    tag: bool = False,
    overdue: bool = False,
) -> EquipmentDefect:
    d = EquipmentDefect(
        id=uuid.uuid4(),
        project_id=ctx.pid(pcode),
        year=2026,
        seq=seq,
        defect_no=f"DEF-{pcode}-2026-{seq:04d}",
        equipment_id=item.id if item else None,
        engagement_id=ctx.engs[(pcode, owner)].id,
        source=source,
        source_ref=source_ref,
        category=cat,
        description_en=desc,
        raised_by_user_id=ctx.officer(pcode),
        raised_at=raised,
        physical_tag_applied=tag or cat == DefectCategory.A,
        tpi_due_date=tpi_due,
        due_date=due,
        status=status,
        overdue_applied=overdue,
        seed_fake=True,
        created_at=raised,
        updated_at=closed or raised,
    )
    if status == DefectStatus.closed and closed is not None:
        d.closed_at = closed
        d.closed_by_user_id = ctx.officer(pcode)
        # the service's stored shapes (defects.close / destroy / rectify)
        d.closure = {
            "method": "destroyed" if destroyed else "hse_verification",
            "cert_line_id": None,
            "note": "Destroyed (test)." if destroyed else "Rectification verified (test).",
            "evidence_attachment_ids": [],
        }
        if destroyed:
            d.closure["returned_to_manufacturer"] = False
        else:
            d.rectified_at = closed - timedelta(hours=4)
            d.rectified_by_user_id = ctx.rep(pcode)
            d.rectification = {
                "description": "Repaired and checked by the owner (test).",
                "done_by_text": "Owner's maintenance team (test)",
                "done_at": d.rectified_at.isoformat(),
                "evidence_attachment_ids": [],
            }
    ctx.db.add(d)
    ctx.defect_seq[pcode] = max(ctx.defect_seq.get(pcode, 0), seq)
    return d


# ---- A.3 / A.4 named equipment ----


def _seed_named_equipment(ctx: Ctx) -> None:
    db = ctx.db
    A, R = "ANIA-EXP", "RBT-52"
    ctx.item_seq = 0

    def named(
        no: int, tag: str, cat: Q, owner: str, pcode: str, site: str, zone: str | None, **kw: Any
    ) -> EquipmentItem:
        demob = kw.pop("demob", None)
        arrived = kw.pop("arrived", date(2026, 6, 1))
        it = _item(ctx, tag, cat, owner, no=no, **kw)
        db.flush()
        _deploy(ctx, it, pcode, owner, tag, site=site, zone=zone, arrived=arrived, demob=demob)
        return it  # fmt: skip

    # RW-MC-03 — AICC 2025-11-06 → 2026-11-05 (Z1b, Z10)
    it = named(
        3,
        "RW-MC-03",
        Q.mobile_crane,
        "RAWABI",
        A,
        "S-LAND",
        "Z-LAY1",
        swl="50.000",
        vehicle="VEH-0003",
        since=at(2025, 11, 7),
        arrived=date(2025, 11, 10),
    )
    _cert(ctx, A, "AICC", "AICC-EQ-TEST-25-1106", [it], date(2025, 11, 6), date(2026, 11, 5),
          verified=at(2025, 11, 8))  # fmt: skip
    # GP-EX-05 — PLANT-TPI
    it = named(5, "GP-EX-05", Q.excavator, "GULFPAVE", A, "S-LAND", "Z-LAY1",
               vehicle="VEH-0005", since=at(2026, 2, 11))  # fmt: skip
    _cert(ctx, A, "AICC", "AICC-EQ-TEST-26-0210", [it], date(2026, 2, 10), date(2027, 2, 9),
          verified=at(2026, 2, 12))  # fmt: skip
    # RW-MEWP-07 — Out of Service (A defect 0007, 2026-09-26)
    it = named(7, "RW-MEWP-07", Q.mewp, "RAWABI", A, "S-LAND", "Z-PIERB", sub=ST.boom,
               persons=2, height="18.00", status=SS.out_of_service,
               reason=ServiceStatusReason.defect_a, since=at(2026, 9, 26, 10))  # fmt: skip
    _cert(ctx, A, "AICC", "AICC-EQ-TEST-26-0605", [it], date(2026, 6, 5), date(2026, 12, 4),
          verified=at(2026, 6, 7))  # fmt: skip
    _event(ctx, it, at(2026, 6, 7), SS.in_service)
    _event(ctx, it, at(2026, 9, 26, 10), SS.out_of_service, ServiceStatusReason.defect_a,
           SS.in_service, "DEF-ANIA-EXP-2026-0007")  # fmt: skip
    mewp7 = it
    # NJ-MC-02 — NKTI (accreditation to 2026-11-02)
    it = named(12, "NJ-MC-02", Q.mobile_crane, "NAJD", A, "S-LAND", "Z-LAY1", swl="40.000",
               since=at(2026, 3, 18))  # fmt: skip
    _cert(ctx, A, "NKTI", "NKTI-TEST-26-0331", [it], date(2026, 3, 16), date(2027, 3, 15),
          verified=at(2026, 3, 18))  # fmt: skip
    njmc = it
    # WRS-NJ-0117 — Retired 2026-09-12 (A defect 0004 from INC-ANIA-EXP-2026-0150)
    it = named(17, "WRS-NJ-0117", Q.lifting_accessory, "NAJD", A, "S-LAND", None,
               sub=ST.wire_rope_sling, swl="8.500", status=SS.retired,
               reason=ServiceStatusReason.retired_destroyed, since=at(2026, 9, 12, 9),
               demob=date(2026, 9, 12), arrived=date(2026, 5, 20))  # fmt: skip
    _cert(ctx, A, "AICC", "AICC-EQ-TEST-26-0518", [it], date(2026, 5, 18), date(2026, 11, 17),
          verified=at(2026, 5, 20))  # fmt: skip
    _event(ctx, it, at(2026, 9, 11, 15), SS.out_of_service, ServiceStatusReason.defect_a,
           SS.in_service, "DEF-ANIA-EXP-2026-0004")  # fmt: skip
    _event(ctx, it, at(2026, 9, 12, 9), SS.retired, ServiceStatusReason.retired_destroyed,
           SS.out_of_service)  # fmt: skip
    wrs = it
    # GP-FL-03 — QUICKCERT revoked 2026-09-20; AICC 2026-09-23 → In Service 09-23 (Z8)
    it = named(21, "GP-FL-03", Q.forklift, "GULFPAVE", A, "S-LAND", "Z-LAY1", swl="3.000",
               since=at(2026, 9, 23, 15))  # fmt: skip
    _cert(ctx, A, "QUICKCERT", "QC-EQ-TEST-26-0042", [it], date(2026, 7, 8), date(2027, 7, 7),
          submitted=at(2026, 7, 9), verified=at(2026, 7, 10), status=CS.revoked,
          reason=CertStatusReason.tpi_blacklisted, ended=date(2026, 9, 20))  # fmt: skip
    _cert(ctx, A, "AICC", "AICC-EQ-TEST-26-0923", [it], date(2026, 9, 23), date(2027, 9, 22),
          submitted=at(2026, 9, 23, 10), accepted=at(2026, 9, 23, 12),
          verified=at(2026, 9, 23, 15))  # fmt: skip
    _event(ctx, it, at(2026, 7, 10), SS.in_service)
    _event(ctx, it, at(2026, 9, 20, 11), SS.quarantined, ServiceStatusReason.tpi_blacklisted,
           SS.in_service)  # fmt: skip
    _event(ctx, it, at(2026, 9, 23, 15), SS.in_service, None, SS.quarantined)
    # RW-MB-01 — man basket
    it = named(24, "RW-MB-01", Q.man_basket, "RAWABI", A, "S-LAND", "Z-PIERB", swl="0.300",
               persons=2, since=at(2026, 7, 16))  # fmt: skip
    _cert(ctx, A, "AICC", "AICC-EQ-TEST-26-0715", [it], date(2026, 7, 15), date(2027, 1, 14),
          verified=at(2026, 7, 16))  # fmt: skip
    # SH-TH-02 — Blacklisted 2026-09-05, deployment Demobilised
    it = named(31, "SH-TH-02", Q.telehandler, "SAHARA", A, "S-LAND", "Z-PIERB",
               status=SS.blacklisted, reason=ServiceStatusReason.blacklisted,
               since=at(2026, 9, 5, 11), demob=date(2026, 9, 5), arrived=date(2026, 8, 20),
               serial="TESTSN-TH-0202")  # fmt: skip
    _event(ctx, it, at(2026, 8, 20), SS.awaiting_certificate)
    _event(ctx, it, at(2026, 9, 5, 11), SS.blacklisted, ServiceStatusReason.blacklisted,
           SS.awaiting_certificate)  # fmt: skip
    db.add(
        EquipmentBlacklistEvent(
            id=uuid.uuid4(), equipment_id=it.id,
            reason_code=EquipmentBlacklistReason.identity_unverifiable,
            reason_text="Serial plate re-stamped; identity cannot be verified (test record).",
            from_date=date(2026, 9, 5), by_user_id=ctx.faisal, seed_fake=True,
            created_at=at(2026, 9, 5, 11), updated_at=at(2026, 9, 5, 11),
        )
    )  # fmt: skip
    # SH-MEWP-12 — Z1a
    it = named(32, "SH-MEWP-12", Q.mewp, "SAHARA", A, "S-LAND", "Z-PIERB", sub=ST.scissor,
               height="12.00", persons=2, swl="0.230", since=at(2026, 9, 4),
               arrived=date(2026, 8, 28))  # fmt: skip
    _cert(ctx, A, "AICC", "AICC-EQ-TEST-26-0902", [it], date(2026, 9, 2), date(2027, 9, 1),
          submitted=at(2026, 9, 3), verified=at(2026, 9, 4))  # fmt: skip
    # NAJD accessory batch NJ-ACC-01…38 — one certificate, 38 lines (Z1d)
    batch = []
    for i in range(38):
        batch.append(
            named(40 + i, f"NJ-ACC-{i + 1:02d}", Q.lifting_accessory, "NAJD", A, "S-LAND", None,
                  sub=ST.shackle if i % 2 else ST.chain_sling, swl="5.000",
                  since=at(2026, 9, 16), arrived=date(2026, 9, 1))
        )  # fmt: skip
    _cert(ctx, A, "AICC", "AICC-EQ-TEST-26-0914", batch, date(2026, 9, 14), date(2027, 9, 13),
          submitted=at(2026, 9, 15), verified=at(2026, 9, 16))  # fmt: skip
    # RBT-52: TC-01 (Z3)
    it = named(101, "TC-01", Q.tower_crane, "QIMMA", R, "S-TWR", "Z-TC01", sub=ST.flat_top,
               swl="12.000", serial="TESTSN-TC-0001", since=at(2026, 9, 29, 16),
               arrived=date(2026, 1, 10))  # fmt: skip
    _old, old_lines = _cert(
        ctx, R, "NKTI", "NKTI-TEST-26-0118", [it], date(2026, 1, 18), date(2027, 1, 17),
        itype=CertInspectionType.initial, verified=at(2026, 1, 20), status=CS.suspended,
        reason=CertStatusReason.configuration_changed, ended=date(2026, 9, 28),
        config_ref="HUH 180.00 m, jib 60 m, 6 tie-ins",
    )  # fmt: skip
    ev = ConfigurationEvent(
        id=uuid.uuid4(), equipment_id=it.id, project_id=ctx.pid(R),
        event_type=ConfigurationEventType.climb_jacking, occurred_at=at(2026, 9, 28, 14),
        new_configuration="HUH 236.00 m, jib 60 m, 9 tie-ins", new_height_m=Decimal("236.00"),
        suspended_line_ids=[old_lines[0].id], seed_fake=True,
        created_by_user_id=ctx.officer(R), created_at=at(2026, 9, 28, 14, 5),
        updated_at=at(2026, 9, 29, 16),
    )  # fmt: skip
    db.add(ev)
    db.flush()
    new, new_lines = _cert(
        ctx, R, "NKTI", "NKTI-TEST-26-0929", [it], date(2026, 9, 29), date(2027, 9, 28),
        itype=CertInspectionType.after_configuration_change, submitted=at(2026, 9, 29, 13),
        accepted=at(2026, 9, 29, 15, 40), verified=at(2026, 9, 29, 16),
        config_ref="HUH 236.00 m, jib 60 m, 9 tie-ins",
        load_test={"percent_of_swl": "110.0", "test_load_t": "13.200"},
    )  # fmt: skip
    new.configuration_event_id = ev.id
    ev.cleared_by_line_id = new_lines[0].id
    ev.cleared_at = at(2026, 9, 29, 16)
    old_lines[0].suspended_for_configuration = True
    old_lines[0].suspended_at = at(2026, 9, 28, 14)
    old_lines[0].superseded_by_line_id = new_lines[0].id
    _event(ctx, it, at(2026, 1, 20), SS.in_service)
    _event(ctx, it, at(2026, 9, 28, 14), SS.quarantined, ServiceStatusReason.configuration_changed,
           SS.in_service, "climb_jacking")  # fmt: skip
    _event(ctx, it, at(2026, 9, 29, 16), SS.in_service, None, SS.quarantined)
    # SB-RBT-04, DL-MC-01, CH-RBT-01
    it = named(104, "SB-RBT-04", Q.lifting_accessory, "QIMMA", R, "S-TWR", "Z-CORE",
               sub=ST.spreader_beam, swl="20.000", since=at(2026, 8, 12))  # fmt: skip
    _cert(ctx, R, "AICC", "AICC-EQ-TEST-26-0811", [it], date(2026, 8, 11), date(2027, 2, 10),
          verified=at(2026, 8, 12))  # fmt: skip
    it = named(110, "DL-MC-01", Q.mobile_crane, "DLIFT", R, "S-POD", "Z-B4", swl="60.000",
               status=SS.quarantined, reason=ServiceStatusReason.certificate_expired,
               since=at(2026, 8, 15, 0, 5), arrived=date(2025, 9, 1))  # fmt: skip
    _cert(ctx, R, "AICC", "AICC-EQ-TEST-25-0815", [it], date(2025, 8, 15), date(2026, 8, 14),
          verified=at(2025, 8, 17), status=CS.expired, ended=date(2026, 8, 15))  # fmt: skip
    _event(ctx, it, at(2025, 9, 1), SS.in_service)
    _event(ctx, it, at(2026, 8, 15, 0, 5), SS.quarantined, ServiceStatusReason.certificate_expired,
           SS.in_service)  # fmt: skip
    it = named(112, "CH-RBT-01", Q.construction_hoist, "QIMMA", R, "S-TWR", "Z-CORE",
               swl="2.000", persons=20, since=at(2026, 8, 21))  # fmt: skip
    _cert(ctx, R, "NKTI", "NKTI-TEST-26-0820", [it], date(2026, 8, 20), date(2027, 2, 19),
          verified=at(2026, 8, 21))  # fmt: skip

    # ---- A.4 fixtures (ANIA-EXP, RAWABI tree) ----
    ctx.item_seq = 200
    fx = {}

    def fixture(tag: str, cat: Q, owner: str, **kw: Any) -> EquipmentItem:
        demob = kw.pop("demob", None)
        it = _item(ctx, tag, cat, owner, **kw)
        db.flush()
        _deploy(ctx, it, A, owner, tag, site="S-LAND", zone="Z-PIERB", arrived=date(2026, 3, 1),
                demob=demob)  # fmt: skip
        fx[tag] = it
        return it

    # FX-ACC-0201: line expired 2026-09-18 (no renewal) → quarantined 09-19
    it = fixture("FX-ACC-0201", Q.lifting_accessory, "NAJD", sub=ST.shackle, swl="6.500",
                 status=SS.quarantined, reason=ServiceStatusReason.certificate_expired,
                 since=at(2026, 9, 19, 0, 5))  # fmt: skip
    ins = inspected_for(Q.lifting_accessory, date(2026, 9, 18))
    _cert(ctx, A, "AICC", "AICC-EQ-TEST-26-0319", [it], ins, None,
          submitted=at_d(ins + timedelta(days=1)), verified=at_d(ins + timedelta(days=2)),
          status=CS.expired, ended=date(2026, 9, 19))  # fmt: skip
    # FX-FL-06: line expired 2026-09-25
    it = fixture("FX-FL-06", Q.forklift, "RAWABI", swl="2.500", status=SS.quarantined,
                 reason=ServiceStatusReason.certificate_expired, since=at(2026, 9, 26, 0, 5))  # fmt: skip
    ins = inspected_for(Q.forklift, date(2026, 9, 25))
    _cert(ctx, A, "AICC", "AICC-EQ-TEST-25-0926", [it], ins, None,
          submitted=at_d(ins + timedelta(days=1)), verified=at_d(ins + timedelta(days=2)),
          status=CS.expired, ended=date(2026, 9, 26))  # fmt: skip
    # FX-ACC-0230 / 0231: accepted 2026-09-29, verification pending (window 0 h → not in force)
    a230 = fixture("FX-ACC-0230", Q.lifting_accessory, "RAWABI", sub=ST.synthetic_sling,
                   swl="2.000", status=SS.quarantined,
                   reason=ServiceStatusReason.certificate_unverified, since=at(2026, 9, 29, 14))  # fmt: skip
    a231 = fixture("FX-ACC-0231", Q.lifting_accessory, "RAWABI", sub=ST.synthetic_sling,
                   swl="2.000", status=SS.quarantined,
                   reason=ServiceStatusReason.certificate_unverified, since=at(2026, 9, 29, 14))  # fmt: skip
    _cert(ctx, A, "AICC", "AICC-EQ-TEST-26-0928", [a230, a231], date(2026, 9, 28),
          date(2027, 3, 27), submitted=at(2026, 9, 29, 9), accepted=at(2026, 9, 29, 14),
          verified=None, verify_outcome=None)  # fmt: skip
    # FX-TH-04: older valid line, then a 2026-09-22 periodic FAIL (supersedes, EC-10) → OOS
    it = fixture("FX-TH-04", Q.telehandler, "RAWABI", swl="4.000", status=SS.out_of_service,
                 reason=ServiceStatusReason.failed_inspection, since=at(2026, 9, 22, 15))  # fmt: skip
    _o, olines = _cert(ctx, A, "AICC", "AICC-EQ-TEST-26-0115", [it], date(2026, 1, 15),
                       date(2027, 1, 14), verified=at(2026, 1, 17), status=CS.superseded,
                       reason=CertStatusReason.newer_certificate, ended=date(2026, 9, 22))  # fmt: skip
    _fc, flines = _cert(ctx, A, "AICC", "AICC-EQ-TEST-26-0922", [it], date(2026, 9, 22), None,
                       submitted=at(2026, 9, 22, 11), accepted=at(2026, 9, 22, 14),
                       verified=at(2026, 9, 22, 15), result=LineResult.fail)  # fmt: skip
    olines[0].superseded_by_line_id = flines[0].id
    _event(ctx, it, at(2026, 3, 1), SS.in_service)
    _event(ctx, it, at(2026, 9, 22, 15), SS.out_of_service, ServiceStatusReason.failed_inspection,
           SS.in_service, "AICC-EQ-TEST-26-0922")  # fmt: skip
    th4, th4_line = it, flines[0]
    # FX-EX-11: B defect 0003 overdue → OOS 2026-09-21 00:05; certificate valid
    it = fixture("FX-EX-11", Q.excavator, "NAJD", status=SS.out_of_service,
                 reason=ServiceStatusReason.defect_b_overdue, since=at(2026, 9, 21, 0, 5))  # fmt: skip
    _cert(ctx, A, "AICC", "AICC-EQ-TEST-26-0405", [it], date(2026, 4, 5), date(2027, 4, 4),
          verified=at(2026, 4, 7))  # fmt: skip
    _event(ctx, it, at(2026, 4, 7), SS.in_service)
    _event(ctx, it, at(2026, 9, 21, 0, 5), SS.out_of_service, ServiceStatusReason.defect_b_overdue,
           SS.in_service, "DEF-ANIA-EXP-2026-0003")  # fmt: skip
    ex11 = it
    # FX-ACC-0240: A defect 0006 (2026-09-19) → Retired (demobilised)
    it = fixture("FX-ACC-0240", Q.lifting_accessory, "NAJD", sub=ST.chain_sling, swl="3.150",
                 status=SS.retired, reason=ServiceStatusReason.retired_destroyed,
                 since=at(2026, 9, 20, 9), demob=date(2026, 9, 20))  # fmt: skip
    _cert(ctx, A, "AICC", "AICC-EQ-TEST-26-0610", [it], date(2026, 6, 10), date(2026, 12, 9),
          verified=at(2026, 6, 12))  # fmt: skip
    _event(ctx, it, at(2026, 6, 12), SS.in_service)
    _event(ctx, it, at(2026, 9, 19, 10), SS.out_of_service, ServiceStatusReason.defect_a,
           SS.in_service, "DEF-ANIA-EXP-2026-0006")  # fmt: skip
    _event(ctx, it, at(2026, 9, 20, 9), SS.retired, ServiceStatusReason.retired_destroyed,
           SS.out_of_service)  # fmt: skip
    acc240 = it
    # FX-ACC-0219: chain sling valid to 2026-10-03 (K-73 on 09-30); expired at seed (Z4a)
    it = fixture("FX-ACC-0219", Q.lifting_accessory, "NAJD", sub=ST.chain_sling, swl="3.150",
                 status=SS.quarantined, reason=ServiceStatusReason.certificate_expired,
                 since=at(2026, 10, 4, 0, 5))  # fmt: skip
    ins = inspected_for(Q.lifting_accessory, date(2026, 10, 3))
    _cert(ctx, A, "AICC", "AICC-EQ-TEST-26-0404", [it], ins, None,
          submitted=at_d(ins + timedelta(days=1)), verified=at_d(ins + timedelta(days=2)),
          status=CS.expired, ended=date(2026, 10, 4))  # fmt: skip
    _event(ctx, it, at_d(ins + timedelta(days=2)), SS.in_service)
    _event(ctx, it, at(2026, 10, 4, 0, 5), SS.quarantined, ServiceStatusReason.certificate_expired,
           SS.in_service)  # fmt: skip
    db.flush()

    # ---- A.5 named defects ----
    _defect(ctx, A, 3, DefectCategory.B, "Hydraulic hose chafing on boom (test).",
            at(2026, 8, 21, 10), item=ex11, owner="NAJD", due=date(2026, 9, 20),
            overdue=True)  # fmt: skip
    _defect(ctx, A, 4, DefectCategory.A, "Wire rope sling crushed and kinked in incident (test).",
            at(2026, 9, 11, 15), item=wrs, owner="NAJD", status=DefectStatus.closed,
            closed=at(2026, 9, 12, 9), source=DefectSource.incident,
            source_ref="INC-ANIA-EXP-2026-0150", destroyed=True)  # fmt: skip
    _defect(ctx, A, 5, DefectCategory.B, "Worn hook latch spring (test).", at(2026, 9, 24, 11),
            item=njmc, owner="NAJD", due=date(2026, 10, 24), tpi_due=date(2026, 10, 31),
            source=DefectSource.tpi_inspection)  # fmt: skip
    _defect(ctx, A, 6, DefectCategory.A, "Chain sling link elongation beyond limit (test).",
            at(2026, 9, 19, 10), item=acc240, owner="NAJD", status=DefectStatus.closed,
            closed=at(2026, 9, 20, 9), destroyed=True)  # fmt: skip
    _defect(ctx, A, 7, DefectCategory.A, "Hydraulic leak on slew ring (test).",
            at(2026, 9, 26, 10), item=mewp7, owner="RAWABI", tag=True)  # fmt: skip
    d8 = _defect(ctx, A, 8, DefectCategory.A, "Boom section crack found at periodic inspection "
                 "(test).", at(2026, 9, 22, 15), item=th4, owner="RAWABI",
                 source=DefectSource.tpi_inspection, source_ref="AICC-EQ-TEST-26-0922")  # fmt: skip
    d8.cert_line_id = th4_line.id
    mewp7.tagged_out_by_user_id = ctx.officer(A)
    db.flush()


# ---- A.10 bulk equipment ----

BULK_EQ = {
    "ANIA-EXP": {
        Q.mobile_crane: 4, Q.crawler_crane: 1, Q.mewp: 12, Q.forklift: 6, Q.telehandler: 5,
        Q.excavator: 16, Q.man_basket: 1, Q.pressure_vessel: 9, Q.lifting_accessory: 80,
    },
    "RBT-52": {
        Q.mobile_crane: 1, Q.construction_hoist: 1, Q.mewp: 4, Q.forklift: 1, Q.telehandler: 2,
        Q.man_basket: 1, Q.lifting_accessory: 33, Q.pressure_vessel: 3,
    },
}  # fmt: skip
PREFIX = {
    Q.mobile_crane: "MC", Q.crawler_crane: "CC", Q.mewp: "MEWP", Q.forklift: "FL",
    Q.telehandler: "TH", Q.excavator: "EX", Q.man_basket: "MB", Q.pressure_vessel: "PV",
    Q.lifting_accessory: "ACC", Q.construction_hoist: "CH",
}  # fmt: skip
SUBTYPE = {
    Q.mewp: ST.scissor,
    Q.lifting_accessory: ST.shackle,
    Q.pressure_vessel: ST.air_receiver,
}
OWNERS = {
    "ANIA-EXP": (["RAWABI", "NAJD"], ["GULFPAVE", "SAHARA"]),
    "RBT-52": (["QIMMA", "DLIFT"], ["QIMMA"]),
}
SITES = {"ANIA-EXP": ("S-LAND", ["Z-PIERB", "Z-MSCP", "Z-LAY1"]), "RBT-52": ("S-TWR", ["Z-CORE"])}


def _seed_bulk_equipment(ctx: Ctx) -> dict[str, list[EquipmentCertificate]]:
    """Valid bulk items; K-73 expiring ones (10 / 4) inside [2026-10-08, 2026-10-30]."""
    db = ctx.db
    rng = ctx.rng
    ctx.item_seq = 1000
    expiring = {"ANIA-EXP": 10, "RBT-52": 4}
    rawabi_left = {"ANIA-EXP": 71, "RBT-52": 46}
    certs: dict[str, list[EquipmentCertificate]] = {"ANIA-EXP": [], "RBT-52": []}
    for pcode, by_cat in BULK_EQ.items():
        site, zones = SITES[pcode]
        n = 0
        tree, other = OWNERS[pcode]
        for cat, count in by_cat.items():
            for _i in range(count):
                n += 1
                if rawabi_left[pcode] > 0:
                    owner = tree[n % len(tree)]
                    rawabi_left[pcode] -= 1
                else:
                    owner = other[n % len(other)]
                tag = f"FX-{PREFIX[cat]}-{pcode[:1]}{n:03d}"
                it = _item(ctx, tag, cat, owner, sub=SUBTYPE.get(cat),
                           swl=None if cat in (Q.excavator, Q.pressure_vessel) else "5.000",
                           since=at(2026, 3, 2))  # fmt: skip
                db.flush()
                _deploy(ctx, it, pcode, owner, tag, site=site, zone=zones[n % len(zones)],
                        arrived=date(2026, 3, 1) + timedelta(days=n % 60))  # fmt: skip
                if expiring[pcode] > 0 and cat == Q.lifting_accessory:
                    expiring[pcode] -= 1
                    vu = date(2026, 10, 8) + timedelta(days=(n * 3) % 23)
                    ins = inspected_for(cat, vu)
                    printed = None
                else:
                    ins = date(2026, 5, 20) + timedelta(days=rng.randrange(0, 100))
                    printed = add_months(ins, interval(cat)) - timedelta(days=1)
                ctx.cert_n += 1
                c, _l = _cert(
                    ctx, pcode, "AICC", f"AICC-EQ-TEST-{pcode[:1]}{n:04d}", [it], ins, printed,
                    submitted=at_d(ins + timedelta(days=1)),
                    verified=at_d(ins + timedelta(days=2), 11),
                )  # fmt: skip
                certs[pcode].append(c)
    db.flush()
    return certs


# ---- A.5 / A.10 bulk defects (K-80) ----


def _seed_bulk_defects(ctx: Ctx) -> None:
    db = ctx.db
    plan = {
        # ANIA: 11 bulk B defects due in September (10 on time, 1 closed one day late)
        "ANIA-EXP": [1, 2, 9, 10, 11, 12, 13, 14, 15, 16, 17],
        "RBT-52": [1, 2, 3],
    }
    for pcode, seqs in plan.items():
        items = [
            ctx.items[t]
            for t, d in ctx.deps.items()
            if d.project_id == ctx.pid(pcode) and t.startswith("FX-") and "-ACC-" not in t
            and d.status == EquipmentDeploymentStatus.on_site
            and ctx.items[t].service_status == SS.in_service and t[3:5] != "TH"
        ]  # fmt: skip
        items = [i for i in items if i.seq > 1000]
        for k, seq in enumerate(seqs):
            it = items[k * 3 % len(items)]
            due = date(2026, 9, 3) + timedelta(days=k * 2)
            raised = at_d(due - timedelta(days=14), 10)
            late = pcode == "ANIA-EXP" and k == len(seqs) - 1
            closed = at_d(due + timedelta(days=1) if late else due - timedelta(days=1), 15)
            dep = next(d for d in ctx.deps.values() if d.equipment_id == it.id)
            owner = next(c for (p, c), e in ctx.engs.items() if e.id == dep.engagement_id)
            _defect(ctx, pcode, seq, DefectCategory.B, "Guard fixing loose / label worn (test).",
                    raised, item=it, owner=owner, due=due, status=DefectStatus.closed,
                    closed=closed)  # fmt: skip
    db.flush()


# ---- A.6 scaffolds (K-75, K-81) ----


def _scaffold(
    ctx: Ctx,
    pcode: str,
    seq: int,
    tag: str,
    owner: str,
    zone: str,
    stype: ScaffoldType,
    height: str,
    inspections: list[tuple[datetime, ScaffoldInspectionResult, str | None]],
    *,
    status: ScaffoldStatus = ScaffoldStatus.in_use,
    tag_status: ScaffoldTagStatus | None = None,
    supervisor: uuid.UUID,
    inspector: uuid.UUID,
    restrictions: tuple[str, str] | None = None,
) -> Scaffold:
    db = ctx.db
    sc = Scaffold(
        id=uuid.uuid4(),
        project_id=ctx.pid(pcode),
        seq=seq,
        scaffold_no=f"SCF-{pcode}-{seq:04d}",
        tag=tag,
        engagement_id=ctx.engs[(pcode, owner)].id,
        zone_id=ctx.zones[zone].id,
        location_desc=f"{zone} grid {seq % 40 + 1} (test)",
        scaffold_type=stype,
        height_m=Decimal(height),
        load_class=3,
        erection_supervisor_worker_id=supervisor,
        erection_crew_worker_ids=[],
        status=status,
        seed_fake=True,
        created_at=at(2026, 8, 1),
        updated_at=inspections[-1][0] if inspections else at(2026, 8, 1),
    )
    db.add(sc)
    db.flush()
    last = None
    for when, res, _note in inspections:
        until = (
            None
            if res == ScaffoldInspectionResult.red
            else acommon.local_day(when) + timedelta(days=6)
        )
        si = ScaffoldInspection(
            id=uuid.uuid4(),
            scaffold_id=sc.id,
            inspection_type=ScaffoldInspectionType.periodic if last else ScaffoldInspectionType.handover,
            inspected_at=when,
            inspector_worker_id=inspector,
            recorded_by_user_id=ctx.officer(pcode),
            checklist=_sic_checklist(res),
            result=res,
            restrictions_en=restrictions[0] if restrictions and res == ScaffoldInspectionResult.yellow else None,
            restrictions_ar=restrictions[1] if restrictions and res == ScaffoldInspectionResult.yellow else None,
            tag_valid_until=until,
            created_at=when,
            seed_fake=True,
        )  # fmt: skip
        db.add(si)
        last = si
    if last is not None:
        sc.last_inspection_id = last.id
        sc.tag_valid_until = last.tag_valid_until
        sc.restrictions_en = last.restrictions_en
        sc.restrictions_ar = last.restrictions_ar
        sc.tag_status = tag_status or ScaffoldTagStatus(last.result.value)
    acommon.issue_qr(db, QrKind.EQ, sc.project_id, sc.id, f"{pcode}-{tag}")
    return sc


def _worker_of(ctx: Ctx, pcode: str, owner: str, trade: Trade | None = None) -> uuid.UUID:
    stmt = select(Deployment.worker_id).where(
        Deployment.engagement_id == ctx.engs[(pcode, owner)].id,
        Deployment.status == DeploymentStatus.mobilised,
    )
    if trade is not None:
        stmt = stmt.where(Deployment.trade == trade)
    wid = ctx.db.scalar(stmt.limit(1))
    if wid is None:
        wid = ctx.db.scalar(
            select(Deployment.worker_id).where(Deployment.project_id == ctx.pid(pcode)).limit(1)
        )
    assert wid is not None  # noqa: S101
    return wid


def _seed_scaffolds(ctx: Ctx) -> None:
    G, Y, Rd = (
        ScaffoldInspectionResult.green,
        ScaffoldInspectionResult.yellow,
        ScaffoldInspectionResult.red,
    )
    A = "ANIA-EXP"
    ferdinand = ctx.workers["WKR-000023"].id
    sup_a = _worker_of(ctx, A, "SAHARA", Trade.scaffolder)
    _scaffold(ctx, A, 142, "SC-0142", "SAHARA", "Z-PIERB", ScaffoldType.independent_tied, "14.00",
              [(at(2026, 9, 24, 8), G, None), (at(2026, 10, 1, 8), G, None)],
              supervisor=sup_a, inspector=ferdinand)  # fmt: skip
    _scaffold(ctx, A, 150, "SC-0150", "SAHARA", "Z-PIERB", ScaffoldType.mobile_tower, "8.00",
              [(at(2026, 9, 29, 9), Rd, "Missing toe-boards; base plate on sand")],
              status=ScaffoldStatus.closed_red, supervisor=sup_a, inspector=ferdinand)  # fmt: skip
    _scaffold(ctx, A, 151, "SC-0151", "NAJD", "Z-PIERB", ScaffoldType.birdcage, "6.00",
              [(at(2026, 9, 25, 8), G, None), (at(2026, 10, 2, 8), Y, None)],
              supervisor=_worker_of(ctx, A, "NAJD"), inspector=ferdinand,
              restrictions=("Harness and lanyard required — guardrail removed at loading point.",
                            "يلزم حزام الأمان والحبل — الدرابزين مزال عند نقطة التحميل."))  # fmt: skip
    # bulk ANIA-EXP: 94 In Use (3 expired at 2026-09-30: SC-0160…0162), RBT-52: 22 In Use
    for pcode, count, start, zones, owners in (
        (A, 94, 160, ["Z-PIERB", "Z-MSCP", "Z-LAY1"], ["RAWABI", "NAJD", "SAHARA"]),
        ("RBT-52", 22, 1, ["Z-CORE", "Z-B4", "Z-FAC"], ["QIMMA", "DLIFT"]),
    ):
        for i in range(count):
            seq = start + i
            owner = "RAWABI" if pcode == A and i < 3 else owners[i % len(owners)]
            sup = _worker_of(ctx, pcode, owner)
            if pcode == A and i < 3:
                first = date(2026, 9, 22) if i == 0 else date(2026, 9, 23)
                insp: list[tuple[datetime, ScaffoldInspectionResult, str | None]] = [
                    (at_d(first - timedelta(days=7), 8), G, None),
                    (at_d(first, 8), G, None),
                ]
                tag_status: ScaffoldTagStatus | None = ScaffoldTagStatus.expired
            else:
                d1 = date(2026, 9, 24) + timedelta(days=i % 6)
                insp = [(at_d(d1, 8), G, None), (at_d(d1 + timedelta(days=7), 8), G, None)]
                tag_status = None
            _scaffold(ctx, pcode, seq, f"SC-{seq:04d}", owner, zones[i % len(zones)],
                      ScaffoldType.system_modular, "10.00", insp, tag_status=tag_status,
                      supervisor=sup, inspector=ferdinand)  # fmt: skip
    ctx.db.flush()


# ---- A.7 personnel certificates and A.10 bulk (K-76, K-77, K-79) ----


def _pc(
    ctx: Ctx,
    pcode: str,
    w: Worker,
    code: str,
    tpi: str,
    cert_no: str,
    issued: date,
    printed: date | None,
    *,
    status: CertificateStatus = CS.accepted,
    submitted: datetime | None = None,
    verified: datetime | None = None,
    scope: list[str] | None = None,
    cap_t: str | None = None,
    level: CertLevel | None = None,
    reason: CertStatusReason | None = None,
    verify_outcome: VerificationOutcome | None = VerificationOutcome.confirmed,
) -> PersonnelCertificate:
    db = ctx.db
    ctx.pc_seq += 1
    submitted = submitted or at_d(issued + timedelta(days=2))
    accepted = submitted + timedelta(hours=4) if status not in (CS.submitted, CS.rejected) else None
    if (
        verified is None
        and verify_outcome == VerificationOutcome.confirmed
        and status != CS.submitted
    ):
        verified = submitted + timedelta(days=1)
    cap_end, vu, lf = cap_validity(code, issued, printed)
    s = cset.get(db, ctx.pid(pcode))
    failed = verify_outcome in (VerificationOutcome.not_found, VerificationOutcome.details_differ)
    pc = PersonnelCertificate(
        id=uuid.uuid4(),
        seq=ctx.pc_seq,
        record_no=f"PCR-{ctx.pc_seq:06d}",
        project_id=ctx.pid(pcode),
        worker_id=w.id,
        cert_type=code,
        tpi_id=ctx.tpis[tpi].id,
        cert_no=cert_no,
        issued_on=issued,
        printed_expiry=printed,
        cap_end=cap_end,
        valid_until=vu,
        limiting_factor=lf,
        scope_categories=scope or [],
        max_capacity_t=Decimal(cap_t) if cap_t else None,
        level=level,
        name_as_printed=w.full_name_en,
        id_match_result=IdMatchResult.matched,
        name_match=NameMatch.exact,
        status=status,
        status_reason=reason,
        verification_status=VerificationStatus.failed if failed else (
            VerificationStatus.verified if verified else VerificationStatus.not_verified),
        verification_due_on=acommon.local_day(submitted) + timedelta(days=s.verification_due_days),
        submitted_by_user_id=ctx.rep(pcode),
        submitted_at=submitted,
        reviewed_by_user_id=ctx.officer(pcode) if accepted or status == CS.rejected else None,
        reviewed_at=accepted,
        accepted_at=accepted,
        verified_at=verified,
        in_force_from=max(accepted, verified) if accepted and verified else None,
        ended_on=date(2026, 9, 17) if status == CS.rejected else (
            vu + timedelta(days=1) if status == CS.expired else None),
        seed_fake=True,
        created_at=submitted - timedelta(hours=1),
        updated_at=verified or accepted or submitted,
    )  # fmt: skip
    db.add(pc)
    db.flush()
    if verified is not None or failed:
        _verification(ctx, CertKind.personnel, pc.id, pcode, ctx.tpis[tpi], verified or
                      (submitted + timedelta(days=2)),
                      verify_outcome or VerificationOutcome.confirmed)  # fmt: skip
    return pc


def _seed_named_personnel(ctx: Ctx) -> None:
    db = ctx.db
    A, R = "ANIA-EXP", "RBT-52"
    W = ctx.workers
    _pc(ctx, A, W["WKR-000019"], "CRANE-OPERATOR", "AICC", "AICC-OP-TEST-24-0412",
        date(2024, 4, 1), date(2027, 3, 31), scope=["mobile_crane", "crawler_crane"],
        cap_t="60.000")  # fmt: skip
    _pc(ctx, R, W["WKR-000102"], "CRANE-OPERATOR", "AICC", "AICC-OP-TEST-25-0815",
        date(2025, 8, 15), date(2028, 8, 14), scope=["tower_crane"], cap_t="16.000")  # fmt: skip
    _pc(ctx, R, W["WKR-000108"], "RIGGER", "AICC", "AICC-RG-TEST-23-1021", date(2023, 10, 21),
        date(2026, 10, 20), level=CertLevel.level_2)  # fmt: skip
    _pc(ctx, R, W["WKR-000108"], "SIGNALLER", "AICC", "AICC-SG-TEST-25-0303", date(2025, 3, 3),
        date(2028, 3, 2))  # fmt: skip
    _pc(ctx, A, W["WKR-000009"], "RIGGER", "AICC", "AICC-RG-TEST-24-0601", date(2024, 6, 1),
        date(2027, 5, 31), level=CertLevel.level_1)  # fmt: skip
    _pc(ctx, R, W["WKR-000104"], "RIGGER", "AICC", "AICC-RG-TEST-23-0901", date(2023, 9, 1),
        date(2026, 8, 31), level=CertLevel.level_1, status=CS.expired)  # fmt: skip
    _pc(ctx, A, W["WKR-000018"], "GAS-TESTER", "DSPC", "DSPC-GT-TEST-26-0420", date(2026, 4, 20),
        date(2028, 4, 19))  # fmt: skip
    _pc(ctx, A, W["WKR-000020"], "RADIOGRAPHER", "FNDT", "FNDT-RT-TEST-22-0601",
        date(2022, 6, 1), date(2027, 5, 31), level=CertLevel.level_ii)  # fmt: skip
    old = _pc(ctx, A, W["WKR-000001"], "SCAFFOLDER", "DSPC", "DSPC-SC-TEST-21-1011",
              date(2021, 10, 11), date(2026, 10, 10), level=CertLevel.basic)  # fmt: skip
    _pc(ctx, A, W["WKR-000001"], "SCAFFOLDER", "DSPC", "DSPC-SC-TEST-26-1002", date(2026, 10, 2),
        date(2031, 10, 1), level=CertLevel.basic, status=CS.submitted,
        submitted=at(2026, 10, 4, 8, 30), verify_outcome=None)  # fmt: skip
    _ = old
    nadeem = W["WKR-000022"]
    _pc(ctx, A, nadeem, "SCAFFOLDER", "QUICKCERT", "QC-SC-TEST-26-0777", date(2026, 9, 1),
        date(2031, 8, 31), status=CS.rejected, reason=CertStatusReason.verification_failed,
        submitted=at(2026, 9, 15, 10), verify_outcome=VerificationOutcome.not_found)  # fmt: skip
    db.add(
        CertificationBan(
            id=uuid.uuid4(), worker_id=nadeem.id, scope_all=True, cert_types=[],
            reason_code=BanReason.forged_certificate,
            reason_text="Card not found in the issuing TPI's records (test record).",
            from_date=date(2026, 9, 17), review_due_on=date(2027, 3, 17),
            status=BanStatus.active, created_by_user_id=ctx.faisal, seed_fake=True,
            created_at=at(2026, 9, 17, 12), updated_at=at(2026, 9, 17, 12),
        )
    )  # fmt: skip
    _pc(ctx, A, W["WKR-000023"], "SCAFFOLD-INSPECTOR", "DSPC", "DSPC-SI-TEST-25-0110",
        date(2025, 1, 10), date(2030, 1, 9))  # fmt: skip
    _pc(ctx, A, W["WKR-000002"], "PLANT-OPERATOR", "AICC", "AICC-PO-TEST-25-0505",
        date(2025, 5, 5), date(2028, 5, 4), scope=["excavator"])  # fmt: skip
    db.flush()


TRADE_CODE = {
    Trade.crane_operator: ("CRANE-OPERATOR", "OP"),
    Trade.rigger: ("RIGGER", "RG"),
    Trade.scaffolder: ("SCAFFOLDER", "SC"),
}
# (not in force, expiring ≤ 30 days at 2026-09-30) per project and trade; named rows included
BULK_PC = {
    "ANIA-EXP": {Trade.crane_operator: (1, 3), Trade.rigger: (2, 5), Trade.scaffolder: (7, 8)},
    "RBT-52": {Trade.crane_operator: (0, 1), Trade.rigger: (0, 2), Trade.scaffolder: (1, 1)},
}
# K-79 September submissions to add on top of the named ones: (in time, late)
BULK_SUBS = {"ANIA-EXP": (126, 17), "RBT-52": (36, 3)}


def _seed_bulk_personnel(ctx: Ctx, eq_certs: dict[str, list[EquipmentCertificate]]) -> None:
    db = ctx.db
    named_ids = set(db.scalars(select(PersonnelCertificate.worker_id)))
    sep_pool: dict[str, list[Any]] = {"ANIA-EXP": [], "RBT-52": []}
    n = 0
    for pcode, plan in BULK_PC.items():
        deps = [
            d
            for d in db.scalars(
                select(Deployment)
                .where(Deployment.project_id == ctx.pid(pcode))
                .order_by(Deployment.mobilised_on, Deployment.id)
            )
            if _live(d) and d.trade in TRADE_CODE and d.worker_id not in named_ids
        ]
        for trade, (missing, expiring) in plan.items():
            code, short = TRADE_CODE[trade]
            rows = [d for d in deps if d.trade == trade]
            for k, d in enumerate(rows):
                w = db.get(Worker, d.worker_id)
                assert w is not None  # noqa: S101
                n += 1
                no = (
                    f"DSPC-{short}-TEST-{n:05d}"
                    if code == "SCAFFOLDER"
                    else f"AICC-{short}-TEST-{n:05d}"
                )
                tpi = "DSPC" if code == "SCAFFOLDER" else "AICC"
                level = (
                    CertLevel.level_2
                    if code == "RIGGER"
                    else (CertLevel.basic if code == "SCAFFOLDER" else None)
                )
                scope = (
                    ["mobile_crane", "crawler_crane", "tower_crane"]
                    if code == "CRANE-OPERATOR"
                    else None
                )
                if k < missing:
                    if k % 2 == 0:  # expired card; the other half has none
                        _pc(ctx, pcode, w, code, tpi, no, date(2023, 6, 1), date(2026, 5, 31),
                            status=CS.expired, level=level, scope=scope)  # fmt: skip
                    continue
                if k < missing + expiring:
                    vu = date(2026, 10, 7) + timedelta(days=(k * 5) % 24)
                    issued = add_months(vu + timedelta(days=1), -36)
                    _pc(ctx, pcode, w, code, tpi, no, issued, vu, level=level, scope=scope)
                    continue
                issued = date(2025, 1, 15) + timedelta(days=(n * 7) % 500)
                pc = _pc(ctx, pcode, w, code, tpi, no, issued, add_months(issued, 36)
                         - timedelta(days=1), level=level, scope=scope)  # fmt: skip
                sep_pool[pcode].append(pc)
    # K-79: move bulk submissions into September (personnel first, then equipment)
    for pcode, (in_time, late) in BULK_SUBS.items():
        pool = sep_pool[pcode] + list(eq_certs[pcode])
        need = in_time + late
        if len(pool) < need:
            raise RuntimeError(f"K-79 pool too small on {pcode}: {len(pool)} < {need}")
        for k, c in enumerate(pool[:need]):
            day = date(2026, 9, 2) + timedelta(days=k % 24)
            sub = at_d(day, 9)
            ver = sub + timedelta(days=5 if k >= in_time else 1, hours=2)
            if isinstance(c, PersonnelCertificate):
                if c.issued_on > day:
                    c.issued_on = day - timedelta(days=10)
                    c.cap_end, c.valid_until, c.limiting_factor = cap_validity(
                        c.cert_type, c.issued_on, c.printed_expiry
                    )
                kind = CertKind.personnel
            else:
                if c.inspected_on > day:
                    c.inspected_on = c.issued_on = day - timedelta(days=1)
                    for ln in db.scalars(
                        select(EquipmentCertLine).where(EquipmentCertLine.certificate_id == c.id)
                    ):
                        it = db.get(EquipmentItem, ln.equipment_id)
                        assert it is not None  # noqa: S101
                        ln.interval_end, ln.valid_until, ln.limiting_factor = line_validity(
                            it.category, c.inspected_on, c.printed_next_due
                        )
                kind = CertKind.equipment
            c.submitted_at = sub
            c.accepted_at = c.reviewed_at = sub + timedelta(hours=4)
            c.verified_at = ver
            c.in_force_from = ver
            c.verification_due_on = day + timedelta(days=3)
            v = db.scalar(
                select(CertVerification).where(
                    CertVerification.cert_kind == kind, CertVerification.cert_id == c.id
                )
            )
            if v is not None:
                v.performed_at = v.created_at = ver
    db.flush()


# ---- entry point ----


def _sic_checklist(res: ScaffoldInspectionResult) -> list[dict[str, str]]:
    """SIC checklist rows in the service's stored shape {item, result}; a red result fails
    the first item, every other item passes."""
    from app.core.cert_enums import ChecklistItemResult, ScaffoldChecklistItem  # noqa: PLC0415

    out = []
    for i, it in enumerate(ScaffoldChecklistItem):
        r = (
            ChecklistItemResult.fail
            if (i == 0 and res == ScaffoldInspectionResult.red)
            else ChecklistItemResult.pass_
        )
        out.append({"item": it.value, "result": r.value})
    return out


SEED_CLOCK = at(2026, 10, 6, 10)  # HSE_CLOCK_AT


def _seed_links(ctx: Ctx) -> None:
    """3-ptw v1.1 §11.4 / 2-access-permits v1.2 X3 at the seed clock: name the operators of the
    Phase 3 lifting appliances (HK4-9: TC-01 → Ali Hassan, VEH-0003 / RW-MC-03 → Zaheer Abbas),
    resolve the Phase 4 items of every permit equipment line, re-evaluate the Approved and live
    permits of both projects with the providers registered, and recompute the AVPs of vehicles
    linked to an item (HK4-11: VEH-0003 → 2026-11-05)."""
    from app.core.ptw_enums import PERMIT_LIVE, PermitStatus  # noqa: PLC0415
    from app.models import Permit, PermitEquipment  # noqa: PLC0415
    from app.services.access import lifecycle  # noqa: PLC0415
    from app.services.ptw import evaluation  # noqa: PLC0415

    db = ctx.db
    W = ctx.workers
    permits = list(
        db.scalars(
            select(Permit)
            .where(Permit.status.in_([*PERMIT_LIVE, PermitStatus.approved]))
            .order_by(Permit.permit_no)
        )
    )
    for p in permits:
        for line in db.scalars(select(PermitEquipment).where(PermitEquipment.permit_id == p.id)):
            evaluation.resolve_line_item(db, p, line)
            if line.operator_worker_id is None and evaluation.operator_code(db, line):
                it = (
                    db.get(EquipmentItem, line.equipment_item_id)
                    if line.equipment_item_id
                    else None
                )
                if it is not None and it.category == Q.tower_crane:
                    line.operator_worker_id = W["WKR-000102"].id
                elif it is not None and it.category == Q.mobile_crane:
                    line.operator_worker_id = W["WKR-000019"].id
    db.flush()
    for p in permits:
        evaluation.refresh(db, p, run_simops=False)
    for vid in db.scalars(
        select(EquipmentItem.vehicle_id).where(EquipmentItem.vehicle_id.is_not(None))
    ):
        if vid is not None:
            lifecycle.refresh_vehicle(db, vid)


def seed_cert_data(db: Session) -> None:
    if already_seeded(db):
        return
    if db.scalar(select(Project.id).where(Project.code == "ANIA-EXP")) is None:
        return
    ctx = Ctx(db)
    try:
        set_now(at(2026, 10, 1, 8))
        _seed_tpis(ctx)
        _seed_policy(ctx)
        _seed_workers(ctx)
        _seed_named_equipment(ctx)
        eq = _seed_bulk_equipment(ctx)
        _seed_bulk_defects(ctx)
        _seed_scaffolds(ctx)
        _seed_named_personnel(ctx)
        _seed_bulk_personnel(ctx, eq)
        db.flush()
        set_now(SEED_CLOCK)
        _seed_links(ctx)
        db.flush()
    finally:
        set_now(None)


def main() -> int:  # pragma: no cover - CLI
    from app.db.session import get_sessionmaker  # noqa: PLC0415

    with get_sessionmaker()() as db:
        seed_cert_data(db)
        db.commit()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
