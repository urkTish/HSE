"""Option 7a seed (spec 7a-vehicle-accident-details Appendix A; fictional, seed_fake = true, report
numbers contain TEST). Additive only: new incidents, vehicle rows, report files and notification
records; no earlier seed row is changed (AC31, DECISIONS). Tests find the incidents by title.

VW1 (ANIA-EXP, September 2026): 0201 public road, GULFPAVE pickup VEH-0002 striking a private
car, MTC to the driver; 0204 site road near miss, RAWABI tipper, licence wrong_class; 0209
airside GSE damage 12,000 SAR; 0212 public road commuting_own, NAJD private car, LTI; 0215 public
road commuting_company_transport, GULFPAVE crew bus struck by a private car, 2 MTC. October
fixture 0231 (2026-10-11, public road, no injury) creates the NAJM-V requirement, open at the
6g clock."""

from __future__ import annotations

import random
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access_enums import LicenceClass, LicenceIssuer, PlateType
from app.core.clock import set_now
from app.core.hse_enums import (
    Agency,
    AirsideFlag,
    AssetType,
    AttachmentOwner,
    CaseCategory,
    ExternalBody,
    IncidentShift,
    IncidentStatus,
    IncidentType,
    Mechanism,
)
from app.core.vehicle_enums import (
    VehCategory,
    VehDamage,
    VehDocState,
    VehDriverKind,
    VehJourneyPurpose,
    VehLight,
    VehOwnership,
    VehReportAuthority,
    VehRoadType,
    VehRole,
    VehSeatBelt,
    VehSpeedSource,
    VehSurface,
)
from app.models import (
    EmailMessage,
    ExternalNotification,
    Incident,
    IncidentVehicle,
    InjuryCase,
    Notification,
    Project,
    Vehicle,
    Worker,
)
from app.seed_field import _cleanup
from app.seed_hse import Spec, _ctx, _incident
from app.services import incident_vehicles as veh
from app.services import incidents as inc_svc

SEED_CLOCK = datetime(2026, 10, 12, 7, 0, tzinfo=UTC)  # 10:00 Riyadh (7a §9 clock)
PDF = b"%PDF-1.4\n% TEST accident report (fictional)\n%%EOF\n"
TITLES = {
    "0201": "Pickup struck a private car on Airport Road (km 12)",
    "0204": "Tipper reversing near miss on the site haul road",
    "0209": "GSE tug damaged on the apron (airside vehicle incident)",
    "0212": "Commuting crash in a worker's own car (single vehicle)",
    "0215": "Crew bus struck by a private car on the camp road",
    "0231": "Minor collision with a private car on a public road, no injury",
}


def already_seeded(db: Session) -> bool:
    return (
        db.scalar(select(IncidentVehicle.id).where(IncidentVehicle.seed_fake.is_(True)).limit(1))
        is not None
    )


def _local(d: date, h: int, mi: int) -> datetime:
    return datetime(d.year, d.month, d.day, h - 3, mi, tzinfo=UTC)  # Asia/Riyadh = UTC+3


def _worker(db: Session, no: str) -> Worker:
    w = db.scalar(select(Worker).where(Worker.worker_no == no))
    assert w is not None, no  # noqa: S101
    return w


def _make(
    ctx: Any,
    spec: Spec,
    at: datetime,
    status: IncidentStatus,
    *,
    zone: str | None,
    potential: int,
    **fields: Any,
) -> tuple[Incident, list[InjuryCase]]:
    inc = _incident(ctx, spec)
    cases = list(ctx.inc_cases[inc.id])
    inc.occurred_at = at
    inc.occurred_date = spec.d
    inc.reported_at = at + timedelta(minutes=50)
    inc.zone_id = ctx.zones[zone].id if zone else None
    inc.status = status
    inc.closed_at = at + timedelta(days=12) if status == IncidentStatus.closed else None
    inc.potential_severity = potential
    inc.title = spec.title or inc.title
    inc.description = f"{inc.title}. Area made safe; supervisor informed."
    inc.immediate_actions = "Scene secured, traffic controlled, first aid given where needed"
    inc.shift = IncidentShift.night if at.hour + 3 >= 20 or at.hour + 3 < 5 else IncidentShift.day
    inc.vehicle_involved = True
    for k, v in fields.items():
        setattr(inc, k, v)
    inc.recorded_not_counted = inc.journey_purpose in (
        VehJourneyPurpose.commuting_own,
        VehJourneyPurpose.commuting_company_transport,
    )
    return inc, cases


def _row(inc: Incident, seq: int, **fields: Any) -> IncidentVehicle:
    r = IncidentVehicle(
        id=uuid.uuid4(),
        incident_id=inc.id,
        project_id=inc.project_id,
        occurred_date=inc.occurred_date,
        seq=seq,
        licence_prefilled_from_adp=False,
        prompt_alerted=True,  # seeds insert without alerts
        seed_fake=True,
    )
    for k, v in fields.items():
        setattr(r, k, v)
    return r


def _vw1(ctx: Any, db: Session) -> list[tuple[Incident, list[InjuryCase], list[IncidentVehicle]]]:
    inj = IncidentType.injury_illness
    out = []
    eng = {k: e.id for k, e in ctx.engs.items()}
    veh2 = db.scalar(select(Vehicle).where(Vehicle.vehicle_no == "VEH-0002"))
    assert veh2 is not None  # noqa: S101
    jomar, rawabi_drv = _worker(db, "WKR-000003"), _worker(db, "WKR-001006")
    rajesh, osman = _worker(db, "WKR-000002"), _worker(db, "WKR-000009")
    bus_drv = _worker(db, "WKR-000004")

    # 0201 — public road, GULFPAVE pickup striking a private car, MTC to the driver
    d = date(2026, 9, 21)
    spec = Spec(d, "GULFPAVE", [inj], CaseCategory.MTC, hour=6, site="S-LAND",
                mechanism=Mechanism.struck_against, title=TITLES["0201"], trade=None)  # fmt: skip
    inc, cases = _make(
        ctx, spec, _local(d, 6, 40), IncidentStatus.reported, zone=None, potential=3,
        road_type=VehRoadType.public_road, road_location="Airport Rd, eastbound km 12",
        journey_purpose=VehJourneyPurpose.material_delivery, light=VehLight.dusk_dawn,
        surface=VehSurface.dry, report_authority=VehReportAuthority.najm,
        report_no="NJM-TEST-2026-00871", report_date=d, liability_pct_own=100,
        third_party_damage_desc="Private car rear bumper and boot lid",
        third_party_damage_cost_sar=Decimal("4500.00"),
    )  # fmt: skip
    c = cases[0]
    c.mechanism, c.agency = Mechanism.vehicle_plant_collision, Agency.light_vehicle
    c.person_name, c.worker_id = jomar.full_name_en, jomar.id
    rows = [
        _row(inc, 1, ownership=VehOwnership.contractor, engagement_id=eng["GULFPAVE"],
             vehicle_id=veh2.id, plate_type=veh2.plate_type,
             plate_letters_ar=veh2.plate_letters_ar, plate_letters_en=veh2.plate_letters_en,
             plate_digits=veh2.plate_digits, category=VehCategory.pickup,
             make_model=veh2.make_model[:60], role=VehRole.striking, damage=VehDamage.major,
             damage_cost_sar=Decimal("18000.00"), seat_belt=VehSeatBelt.worn, speed_kmh=72,
             speed_limit_kmh=80, speed_source=VehSpeedSource.report,
             driver_kind=VehDriverKind.worker, worker_id=jomar.id, driver_case_no=1),
        _row(inc, 2, ownership=VehOwnership.third_party, plate_type=PlateType.private,
             plate_letters_ar="ا ب ج", plate_letters_en="ABJ", plate_digits="1234",
             category=VehCategory.private_car, make_model="Sedan TEST", role=VehRole.struck,
             damage=VehDamage.minor, seat_belt=VehSeatBelt.unknown,
             driver_kind=VehDriverKind.external, external_driver_name="Test Driver",
             insurer="Test Takaful", policy_no="TEST-POL-7781",
             doc_istimara=VehDocState.unknown, doc_insurance=VehDocState.valid,
             doc_mvpi=VehDocState.unknown),
    ]  # fmt: skip
    adp = veh.adp_of(db, inc.project_id, jomar.id)
    if adp is not None:
        rows[0].licence_issuer, rows[0].licence_class = adp.licence_issuer, adp.licence_class
        rows[0].licence_expiry, rows[0].licence_prefilled_from_adp = adp.licence_expiry_date, True
    else:
        rows[0].licence_issuer, rows[0].licence_class = LicenceIssuer.ksa, LicenceClass.private
        rows[0].licence_expiry = date(2028, 6, 30)
    out.append((inc, cases, rows))

    # 0204 — site road near miss, RAWABI tipper reversing, private licence on a tipper
    d = date(2026, 9, 10)
    spec = Spec(d, "RAWABI", [IncidentType.near_miss], hour=14, site="S-LAND",
                title=TITLES["0204"])  # fmt: skip
    inc, cases = _make(
        ctx, spec, _local(d, 14, 15), IncidentStatus.closed, zone="Z-PIERB", potential=4,
        road_type=VehRoadType.site_road, road_location="Haul road behind Pier B",
        journey_purpose=VehJourneyPurpose.work_task, light=VehLight.daylight,
        surface=VehSurface.sand_on_road, report_authority=VehReportAuthority.none_internal,
    )  # fmt: skip
    inc.status_reason = "Near miss reviewed at the daily briefing; banksman rule re-briefed"
    rows = [
        _row(inc, 1, ownership=VehOwnership.contractor, engagement_id=eng["RAWABI"],
             plate_type=PlateType.transport, plate_letters_ar="ر س ط",
             plate_letters_en="RST", plate_digits="4417", category=VehCategory.tipper,
             make_model="Tipper TEST 20 m3", role=VehRole.single_vehicle,
             damage=VehDamage.none, seat_belt=VehSeatBelt.worn,
             driver_kind=VehDriverKind.worker, worker_id=rawabi_drv.id,
             licence_issuer=LicenceIssuer.ksa, licence_class=LicenceClass.private,
             licence_expiry=date(2028, 5, 31), doc_istimara=VehDocState.valid,
             doc_insurance=VehDocState.valid, doc_mvpi=VehDocState.valid),
    ]  # fmt: skip
    out.append((inc, cases, rows))

    # 0209 — airside apron, GULFPAVE GSE tug, property damage 12,000 SAR
    d = date(2026, 9, 17)
    spec = Spec(d, "GULFPAVE", [IncidentType.property_damage], hour=23, site="S-AIR",
                flags=[AirsideFlag.airside_vehicle_incident], title=TITLES["0209"],
                shift=IncidentShift.night)  # fmt: skip
    inc, cases = _make(
        ctx, spec, _local(d, 23, 30), IncidentStatus.closed, zone="Z-APR-21", potential=3,
        road_type=VehRoadType.airside, road_location=None,
        journey_purpose=VehJourneyPurpose.work_task, light=VehLight.dark_lit,
        surface=VehSurface.dry, report_authority=VehReportAuthority.none_internal,
        pd_asset_type=AssetType.vehicle, pd_estimated_cost_sar=Decimal("12000.00"),
    )  # fmt: skip
    inc.status_reason = "Quick close: tug repaired, apron driving refresher given"
    rows = [
        _row(inc, 1, ownership=VehOwnership.contractor, engagement_id=eng["GULFPAVE"],
             plate_type=PlateType.none, category=VehCategory.other,
             make_model="GSE tug TEST", role=VehRole.striking, damage=VehDamage.major,
             damage_cost_sar=Decimal("12000.00"), seat_belt=VehSeatBelt.worn, speed_kmh=12,
             speed_limit_kmh=15, speed_source=VehSpeedSource.estimate,
             driver_kind=VehDriverKind.worker, worker_id=rajesh.id,
             licence_issuer=LicenceIssuer.ksa, licence_class=LicenceClass.heavy_equipment,
             licence_expiry=date(2027, 12, 31), doc_istimara=VehDocState.unknown,
             doc_insurance=VehDocState.valid, doc_mvpi=VehDocState.unknown),
    ]  # fmt: skip
    out.append((inc, cases, rows))

    # 0212 — public road, commuting in own car, NAJD worker, LTI (recorded, not counted)
    d = date(2026, 9, 27)
    spec = Spec(d, "NAJD", [inj], CaseCategory.LTI, days_away=6, hour=5, site="S-LAND",
                mechanism=Mechanism.struck_against, title=TITLES["0212"])  # fmt: skip
    inc, cases = _make(
        ctx, spec, _local(d, 5, 50), IncidentStatus.reported, zone=None, potential=4,
        road_type=VehRoadType.public_road, road_location="Camp road to site, km 3",
        journey_purpose=VehJourneyPurpose.commuting_own, light=VehLight.dark_unlit,
        surface=VehSurface.sand_on_road, report_authority=VehReportAuthority.traffic_police,
        report_no="TP-TEST-2026-3310", report_date=d,
        work_related=False, not_work_related_reason=_commuting_reason(),
        work_related_rationale="Commuting in own car before the shift (OSHA 1904.5)",
    )  # fmt: skip
    c = cases[0]
    c.mechanism, c.agency, c.commuting = Mechanism.vehicle_overturn, Agency.light_vehicle, True
    c.person_name, c.worker_id = osman.full_name_en, osman.id
    rows = [
        _row(inc, 1, ownership=VehOwnership.third_party, plate_type=PlateType.private,
             plate_letters_ar="د ك ل", plate_letters_en="DKL", plate_digits="7311",
             category=VehCategory.private_car, make_model="Sedan TEST",
             role=VehRole.single_vehicle, damage=VehDamage.total_loss,
             seat_belt=VehSeatBelt.not_worn, driver_kind=VehDriverKind.worker,
             worker_id=osman.id, licence_issuer=LicenceIssuer.ksa,
             licence_class=LicenceClass.private, licence_expiry=date(2027, 8, 31),
             insurer="Test Insurance Co", policy_no="TEST-POL-3310",
             doc_istimara=VehDocState.valid, doc_insurance=VehDocState.valid,
             doc_mvpi=VehDocState.unknown, driver_case_no=1),
    ]  # fmt: skip
    out.append((inc, cases, rows))

    # 0215 — public road, commuting by company bus (GULFPAVE crew bus), 2 MTC passengers
    d = date(2026, 9, 29)
    spec = Spec(d, "GULFPAVE", [inj], CaseCategory.MTC, hour=5, site="S-LAND",
                mechanism=Mechanism.struck_against, title=TITLES["0215"])  # fmt: skip
    inc, cases = _make(
        ctx, spec, _local(d, 5, 30), IncidentStatus.reported, zone=None, potential=4,
        road_type=VehRoadType.public_road, road_location="Camp → site road, km 7",
        journey_purpose=VehJourneyPurpose.commuting_company_transport,
        light=VehLight.dark_unlit, surface=VehSurface.dry,
        report_authority=VehReportAuthority.traffic_police, report_no="TP-TEST-2026-3354",
        report_date=d, work_related=False, not_work_related_reason=_commuting_reason(),
        work_related_rationale="Company bus from camp to site before the shift (OSHA 1904.5)",
    )  # fmt: skip
    first = cases[0]
    first.mechanism, first.agency, first.commuting = (
        Mechanism.vehicle_plant_collision,
        Agency.heavy_vehicle,
        True,
    )
    second = InjuryCase(
        **{
            k: getattr(first, k)
            for k in InjuryCase.__table__.columns.keys()  # noqa: SIM118
            if k not in ("id", "person_no", "created_at", "updated_at")
        }
    )
    second.id, second.person_no = uuid.uuid4(), 2
    second.person_name = "Test Passenger Two"
    second.employee_no = f"{first.employee_no}-2"
    second.gosi_case_ref = f"{first.gosi_case_ref}-2" if first.gosi_case_ref else None
    cases.append(second)
    ctx.inc_cases[inc.id] = cases
    ctx.cases.append(second)
    rows = [
        _row(inc, 1, ownership=VehOwnership.contractor, engagement_id=eng["GULFPAVE"],
             plate_type=PlateType.transport, plate_letters_ar="ب ع د",
             plate_letters_en="BED", plate_digits="5521", category=VehCategory.bus,
             make_model="Crew bus TEST 30-seat", role=VehRole.struck, damage=VehDamage.major,
             damage_cost_sar=Decimal("26000.00"), seat_belt=VehSeatBelt.worn, speed_kmh=55,
             speed_limit_kmh=80, speed_source=VehSpeedSource.vehicle_recorder,
             driver_kind=VehDriverKind.worker, worker_id=bus_drv.id,
             licence_issuer=LicenceIssuer.ksa, licence_class=LicenceClass.public_transport,
             licence_expiry=date(2027, 4, 30), doc_istimara=VehDocState.valid,
             doc_insurance=VehDocState.valid, doc_mvpi=VehDocState.valid),
        _row(inc, 2, ownership=VehOwnership.third_party, plate_type=PlateType.private,
             plate_letters_ar="س ن ه", plate_letters_en="SNH", plate_digits="8820",
             category=VehCategory.private_car, make_model="SUV TEST", role=VehRole.striking,
             damage=VehDamage.major, seat_belt=VehSeatBelt.unknown,
             driver_kind=VehDriverKind.external, external_driver_name="Test Third Driver",
             insurer="Test Takaful", policy_no="TEST-POL-8820",
             doc_istimara=VehDocState.unknown, doc_insurance=VehDocState.valid,
             doc_mvpi=VehDocState.unknown),
    ]  # fmt: skip
    out.append((inc, cases, rows))
    return out


def _commuting_reason() -> Any:
    from app.core.hse_enums import NotWorkRelatedReason  # noqa: PLC0415

    return NotWorkRelatedReason.commuting


def _oct_0231(ctx: Any) -> tuple[Incident, list[InjuryCase], list[IncidentVehicle]]:
    eng = ctx.engs["GULFPAVE"].id
    d = date(2026, 10, 11)
    spec = Spec(d, "GULFPAVE", [IncidentType.property_damage], hour=16, site="S-LAND",
                title=TITLES["0231"])  # fmt: skip
    inc, cases = _make(
        ctx, spec, _local(d, 16, 10), IncidentStatus.reported, zone=None, potential=2,
        road_type=VehRoadType.public_road, road_location="King Fahd Rd, southbound km 4",
        journey_purpose=VehJourneyPurpose.material_delivery, light=VehLight.daylight,
        surface=VehSurface.dry, report_authority=VehReportAuthority.najm,
        pd_asset_type=AssetType.vehicle, pd_estimated_cost_sar=Decimal("3500.00"),
        report_alert_on=d + timedelta(days=7),  # §7 reminder while report_no is missing
    )  # fmt: skip
    rows = [
        _row(inc, 1, ownership=VehOwnership.contractor, engagement_id=eng,
             plate_type=PlateType.private, plate_letters_ar="ق ل م",
             plate_letters_en="GLZ", plate_digits="6402", category=VehCategory.van,
             make_model="Van TEST", role=VehRole.struck, damage=VehDamage.minor,
             damage_cost_sar=Decimal("3500.00"), seat_belt=VehSeatBelt.worn,
             driver_kind=VehDriverKind.external, external_driver_name="Test Van Driver",
             doc_istimara=VehDocState.valid, doc_insurance=VehDocState.valid,
             doc_mvpi=VehDocState.valid),
    ]  # fmt: skip
    return inc, cases, rows


def seed_vehicle_data(db: Session) -> None:
    """Appendix A (additive)."""
    if already_seeded(db):
        return
    project = db.scalar(select(Project).where(Project.code == "ANIA-EXP"))
    if (
        project is None
        or db.scalar(select(Vehicle.id).where(Vehicle.vehicle_no == "VEH-0002")) is None
    ):
        return
    from app.services.attachments import store  # noqa: PLC0415
    from app.services.followup import common as fc  # noqa: PLC0415
    from app.services.followup import requirements as rq  # noqa: PLC0415

    n0 = set(db.scalars(select(Notification.id)))
    e0 = set(db.scalars(select(EmailMessage.id)))
    try:
        set_now(SEED_CLOCK)
        ctx = _ctx(db, project, random.Random(20261011))  # noqa: S311 (seed data)
        top = db.scalar(
            select(func.max(Incident.seq)).where(
                Incident.project_id == project.id, Incident.year == 2026
            )
        )
        ctx.seq[("INC", 2026)] = int(top or 0)
        ctx.person_seq = 7000
        made = _vw1(ctx, db)
        made.append(_oct_0231(ctx))
        for inc, cases, rows in made:
            db.add(inc)
            db.flush()
            db.add_all(cases)
            db.flush()
            for r in rows:
                db.add(r)
                db.flush()
                veh._compute(db, inc, r)
            db.flush()
        reporter = ctx.users["noura.qahtani"].id
        # Phase 1 I-20 records for the September incidents (before followup_rules_from)
        for inc, cases, _ in made[:-1]:
            for req in inc_svc.required_notifications(inc, cases):
                police = req.body == ExternalBody.police
                db.add(
                    ExternalNotification(
                        incident_id=inc.id,
                        body=req.body,
                        notified_at=inc.occurred_at + timedelta(minutes=40 if police else 300),
                        reference_no=(inc.report_no if police and inc.report_no
                                      else f"SEED-{req.body.value.upper()}-{inc.seq:04d}"),
                        notified_by_user_id=reporter,
                        alerts_sent=[],
                    )
                )  # fmt: skip
        # one archived report file each for 0201, 0212, 0215 (VA-14)
        for inc, _, _ in made[:-1]:
            if inc.report_no:
                store(db, AttachmentOwner.incident_accident_report, inc.id, inc.project_id,
                      f"{inc.report_no}.pdf", PDF, "application/pdf", reporter)  # fmt: skip
        # 0231 (after followup_rules_from): the 6f NAJM-V requirement, open at the clock
        oct_inc = made[-1][0]
        rq.derive(db, oct_inc, oct_inc.occurred_at + timedelta(minutes=20))
        _cleanup(db, n0, e0)
        fc.clear_cache(db)
        db.flush()
    finally:
        set_now(None)


def vw1_refs(db: Session) -> dict[str, str]:
    """Title key (0201 …) → generated ref, for tests and the frontend worker."""
    out = {}
    for key, title in TITLES.items():
        ref = db.scalar(select(Incident.ref).where(Incident.title == title))
        if ref:
            out[key] = ref
    return out


__all__ = ["seed_vehicle_data", "vw1_refs"]
