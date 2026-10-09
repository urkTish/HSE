"""The environment band (spec 6e-environmental §8.1 item 2), the 6e action panel (§8.2), post-storm
tasks derived from Phase 2 ops events (AIR-4) and spill-kit coverage (SPL-7)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import OpsEventType
from app.core.clock import now
from app.core.emergency_enums import AssetStatus, AssetType
from app.core.env_enums import (
    AreaStatus,
    ComplaintStatus,
    ConsignmentStatus,
    EnvActionKind,
    EnvPermitStatus,
    ExceedanceCause,
    ExceedanceStatus,
    SpillStatus,
)
from app.models import (
    ChecklistResponse,
    DischargeDay,
    EmergencyAsset,
    EnvComplaint,
    EnvExceedance,
    EnvPermit,
    EnvPoint,
    OpsEvent,
    Site,
    Spill,
    WasteConsignment,
    WasteStorageArea,
    Zone,
)
from app.schemas.env import EnvActionPanel, EnvActionRow, EnvBand, HazDeadline, PostStormTask
from app.services.env import common as ec
from app.services.env import exceedances as exd
from app.services.env import register, waste
from app.services.permissions import Principal

K = EnvActionKind
STORM_TEMPLATES = ("WSA", "ENV", "FOD")


# ---- AIR-4 post-storm tasks ----------------------------------------------------------------------


def post_storm_tasks(
    db: Session, project_id: uuid.UUID, since: datetime, at: datetime | None = None
) -> list[PostStormTask]:
    t = at or now()
    hours = int(ec.cfg(db, project_id)["post_storm_check_hours"])
    area_sites = {
        a.site_id
        for a in db.scalars(
            select(WasteStorageArea).where(
                WasteStorageArea.project_id == project_id,
                WasteStorageArea.status == AreaStatus.active,
            )
        )
    }
    out: list[PostStormTask] = []
    for ev in db.scalars(
        select(OpsEvent)
        .where(
            OpsEvent.project_id == project_id,
            OpsEvent.type == OpsEventType.dust_sandstorm,
            OpsEvent.ended_at.is_not(None),
            OpsEvent.ended_at >= since,
        )
        .order_by(OpsEvent.ended_at)
    ):
        assert ev.ended_at is not None  # noqa: S101
        sites = {ev.site_id} | {
            z.site_id for z in (db.get(Zone, zid) for zid in ev.zone_ids or []) if z is not None
        }
        due = ev.ended_at + timedelta(hours=hours)
        for sid in sorted(sites & area_sites, key=str):
            r = db.scalar(
                select(ChecklistResponse)
                .where(
                    ChecklistResponse.project_id == project_id,
                    ChecklistResponse.site_id == sid,
                    ChecklistResponse.template_code.in_(STORM_TEMPLATES),
                    ChecklistResponse.submitted.is_(True),
                    ChecklistResponse.voided.is_(False),
                    ChecklistResponse.completed_at >= ev.ended_at,
                    ChecklistResponse.completed_at <= due,
                )
                .order_by(ChecklistResponse.completed_at)
            )
            site = db.get(Site, sid)
            out.append(
                PostStormTask(
                    ops_no=ev.ops_no, site_id=sid, site_code=site.code if site else "?",
                    ended_at=ev.ended_at, due_at=due, met=r is not None,
                    met_by_inspection_id=r.inspection_id if r else None,
                    overdue=r is None and t > due,
                )
            )  # fmt: skip
    return out


# ---- SPL-7 spill-kit coverage --------------------------------------------------------------------


def kit_gaps(db: Session, project_id: uuid.UUID) -> list[str]:
    """Active hazardous / liquid stores without an in-service spill kit in the same zone."""
    from app.services.env import reference as rf  # noqa: PLC0415

    kit_zones = {
        a.zone_id
        for a in db.scalars(
            select(EmergencyAsset).where(
                EmergencyAsset.project_id == project_id,
                EmergencyAsset.asset_type == AssetType.spill_kit,
                EmergencyAsset.status == AssetStatus.in_service,
            )
        )
    }
    out = []
    for a in db.scalars(
        select(WasteStorageArea)
        .where(
            WasteStorageArea.project_id == project_id,
            WasteStorageArea.status == AreaStatus.active,
        )
        .order_by(WasteStorageArea.area_code)
    ):
        if a.type in rf.HAZ_STORES and a.zone_id not in kit_zones:
            z = db.get(Zone, a.zone_id) if a.zone_id else None
            out.append(f"{a.area_code} ({z.code if z else '—'})")
    return out


# ---- action panel (§8.2) -------------------------------------------------------------------------


def rows(db: Session, project_id: uuid.UUID, today: date) -> list[EnvActionRow]:
    out: list[EnvActionRow] = []

    def add(kind: K, ref: str, en: str, ar: str, eid: uuid.UUID | None, due: date | None) -> None:
        out.append(EnvActionRow(kind=kind, ref=ref, label_en=en, label_ar=ar, entity_id=eid,
                                due=due))  # fmt: skip

    for x in db.scalars(
        select(EnvExceedance)
        .where(
            EnvExceedance.project_id == project_id, EnvExceedance.status == ExceedanceStatus.open
        )
        .order_by(EnvExceedance.started_at)
    ):
        add(K.exceedances_awaiting_review, x.exceedance_no, "Exceedance awaiting review",
            "تجاوز بانتظار المراجعة", x.id, exd.review_due(db, x))  # fmt: skip
    for code, pms in sorted(ec.requirements(db, project_id).items()):
        if ec.applicable(pms, today) and not ec.requirement_in_force(db, project_id, code, today):
            add(K.requirements_not_in_force, code, "Permit requirement not in force",
                "متطلب تصريح غير ساري", pms[-1].id, None)  # fmt: skip
    cons = list(
        db.scalars(
            select(WasteConsignment).where(
                WasteConsignment.project_id == project_id,
                WasteConsignment.status.in_(
                    [ConsignmentStatus.dispatched, ConsignmentStatus.rejected]
                ),
            )
        )
    )
    redone = {c.redispatch_of_id for c in db.scalars(select(WasteConsignment).where(
        WasteConsignment.project_id == project_id, WasteConsignment.redispatch_of_id.is_not(None)
    ))}  # fmt: skip
    for c in sorted(cons, key=lambda c: c.consignment_no):
        if waste.overdue(c, today):
            add(K.consignments_overdue, c.consignment_no, "Consignment receipt overdue",
                "إثبات الاستلام متأخر", c.id, c.due_on)  # fmt: skip
        elif c.status == ConsignmentStatus.rejected and c.id not in redone:
            add(K.consignments_rejected, c.consignment_no, "Rejected load not re-dispatched",
                "حمولة مرفوضة لم يُعد إرسالها", c.id, None)  # fmt: skip
    for a in db.scalars(
        select(WasteStorageArea).where(
            WasteStorageArea.project_id == project_id, WasteStorageArea.status == AreaStatus.active
        )
    ):
        for h in waste.haz_deadlines(db, a, today):
            if h.overdue:
                add(K.haz_storage_overdue, f"{a.area_code} · {h.stream_code}",
                    "Hazardous storage time exceeded", "تجاوز مدة تخزين النفايات الخطرة", a.id,
                    h.deadline)  # fmt: skip
    for d in db.scalars(
        select(DischargeDay)
        .where(
            DischargeDay.project_id == project_id,
            DischargeDay.day >= today - timedelta(days=30),
        )
        .order_by(DischargeDay.day)
    ):
        if "PERMIT_NOT_VALID" in (d.warnings or []):
            pt = db.get(EnvPoint, d.point_id)
            add(K.discharge_without_permit, f"{pt.point_code if pt else '?'} · {d.day}",
                "Discharge without a valid permit", "تصريف دون تصريح ساري", d.id,
                d.day)  # fmt: skip
    for t in post_storm_tasks(db, project_id, ec.day_start(today - timedelta(days=7))):
        if t.overdue:
            add(K.post_storm_checks_unmet, f"{t.ops_no} · {t.site_code}",
                "Post-storm storage check not done", "لم يُنفذ فحص ما بعد العاصفة", None,
                ec.local_day(t.due_at))  # fmt: skip
    for g in kit_gaps(db, project_id):
        add(K.spill_kit_coverage_gap, g, "No in-service spill kit in the zone",
            "لا توجد حقيبة انسكاب جاهزة في المنطقة", None, None)  # fmt: skip
    for s in db.scalars(
        select(Spill).where(
            Spill.project_id == project_id,
            Spill.status.in_([SpillStatus.reported, SpillStatus.cleaned_up]),
            Spill.occurred_date < today - timedelta(days=7),
        )
    ):
        add(K.spills_not_closed, s.spill_no, "Spill not closed after 7 days",
            "انسكاب غير مغلق بعد 7 أيام", s.id, s.occurred_date + timedelta(days=7))  # fmt: skip
    for cp in db.scalars(
        select(EnvComplaint).where(
            EnvComplaint.project_id == project_id,
            EnvComplaint.status == ComplaintStatus.open,
            EnvComplaint.response_due_on < today,
        )
    ):
        add(K.complaints_past_due, cp.complaint_no, "Complaint response past due",
            "تجاوز موعد الرد على الشكوى", cp.id, cp.response_due_on)  # fmt: skip
    return out


def action_panel(db: Session, p: Principal, project_id: uuid.UUID) -> EnvActionPanel:
    ec.view_grant(db, p, project_id)
    items = rows(db, project_id, ec.local_day())
    counts: dict[str, int] = {}
    for r in items:
        counts[r.kind.value] = counts.get(r.kind.value, 0) + 1
    return EnvActionPanel(items=items, counts=counts)


# ---- band (§8.1 item 2) --------------------------------------------------------------------------


def used_providers(db: Session, project_id: uuid.UUID, today: date) -> set[uuid.UUID]:
    out: set[uuid.UUID] = set()
    for t, f in db.execute(
        select(WasteConsignment.transporter_id, WasteConsignment.facility_provider_id).where(
            WasteConsignment.project_id == project_id,
            WasteConsignment.dispatched_date >= today - timedelta(days=90),
        )
    ):
        out |= {t, f}
    return out


def band(db: Session, p: Principal, project_id: uuid.UUID) -> EnvBand:
    g = ec.view_grant(db, p, project_id)
    today = ec.local_day()
    t = now()
    xs = [
        x
        for x in db.scalars(
            select(EnvExceedance).where(
                EnvExceedance.project_id == project_id,
                EnvExceedance.status == ExceedanceStatus.open,
            )
        )
        if g.covers_site(x.site_id)
    ]
    reads = [exd.exceedance_read(db, x) for x in xs]
    reads.sort(key=lambda r: (not r.airside, r.started_at))
    recent = [
        exd.exceedance_read(db, x)
        for x in db.scalars(
            select(EnvExceedance).where(
                EnvExceedance.project_id == project_id,
                EnvExceedance.created_at >= t - timedelta(hours=24),
                EnvExceedance.status != ExceedanceStatus.voided,
            )
        )
    ]
    air24 = sum(
        1 for r in recent if r.airside and r.suggested_cause != ExceedanceCause.background_natural
    )
    pms: list[EnvPermit] = list(ec.project_permits(db, project_id))
    for pid in used_providers(db, project_id, today):
        pms += ec.licences(db, pid)
    expiring = [
        register.permit_read(db, pm)
        for pm in pms
        if ec.permit_status(db, pm, today) == EnvPermitStatus.expiring
    ]
    over = sum(
        1
        for c in db.scalars(
            select(WasteConsignment).where(
                WasteConsignment.project_id == project_id,
                WasteConsignment.status == ConsignmentStatus.dispatched,
                WasteConsignment.due_on < today,
            )
        )
        if ec.scope_ok(g, c.site_id, c.generator_engagement_id)
    )
    haz: list[HazDeadline] = []
    for a in db.scalars(
        select(WasteStorageArea).where(
            WasteStorageArea.project_id == project_id, WasteStorageArea.status == AreaStatus.active
        )
    ):
        haz += [h for h in waste.haz_deadlines(db, a, today) if h.days_left <= 14]
    storms = [x for x in post_storm_tasks(db, project_id, t - timedelta(hours=48), t) if not x.met]
    return EnvBand(
        open_exceedances=reads, airside_dust_alerts_24h=air24, expiring_permits=expiring,
        consignments_overdue=over, haz_storage_due=sorted(haz, key=lambda h: h.deadline),
        post_storm_tasks=storms,
    )  # fmt: skip
