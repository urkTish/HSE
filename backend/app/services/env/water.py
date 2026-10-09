"""Water use, dewatering discharge days (spec 6e-environmental §3.14, WAT-1…WAT-3) and complaints
(§3.15, §4.7, CPL-1…CPL-3, P6e-2)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.env_enums import (
    Averaging,
    ComplaintAction,
    ComplaintCategory,
    ComplaintChannel,
    ComplaintStatus,
    Parameter,
    PointKind,
    RecordState,
)
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.models import DischargeDay, EnvComplaint, EnvPoint, EnvReading, WaterEntry
from app.schemas.env import (
    ComplaintCreate,
    ComplaintPage,
    ComplaintRead,
    ComplaintTransition,
    ComplaintUpdate,
    DischargeCreate,
    DischargePage,
    DischargeRead,
    EnvVoid,
    NearbyReadings,
    WaterCreate,
    WaterPage,
    WaterRead,
    WaterUpdate,
)
from app.services.env import common as ec
from app.services.env import reference as rf
from app.services.permissions import Principal

C = Capability
ET = EntityType
NK = NotificationKind
CS = ComplaintStatus
D = Decimal
PURPOSES = ("dust_suppression", "concrete_curing", "welfare", "other")
HELD = "Contact held by the HSE team"


def _conflict(en: str) -> ApiError:
    return ApiError(409, ErrorCode.INVALID_TRANSITION, en, "لا يمكن تنفيذ هذا الإجراء.")


# ---- water (WAT-1) -------------------------------------------------------------------------------


def water_read(w: WaterEntry) -> WaterRead:
    return WaterRead(
        id=w.id, project_id=w.project_id, site_id=w.site_id, month=w.month, source=w.source,
        volume_m3=str(ec.q1(w.volume_m3)),
        purpose={k: str(ec.q1(D(str(v)))) for k, v in (w.purpose or {}).items()},
        status=w.status, void_reason=w.void_reason,
    )  # fmt: skip


def edit_until(month: str) -> date:
    y, m = int(month[:4]), int(month[5:7])
    return date(y + (m == 12), 1 if m == 12 else m + 1, 10)


def _open_month(month: str) -> None:
    if ec.local_day() > edit_until(month):
        raise validation_error(
            "month", "This month is locked (after the 10th of the next month); void and re-enter.",
            msg_ar="الشهر مغلق للتعديل؛ ألغِ السجل وأعد إدخاله.",
        )  # fmt: skip


def _purpose(volume: Decimal, purpose: dict[str, Decimal]) -> dict[str, str]:
    if not purpose:
        return {}
    if any(k not in PURPOSES for k in purpose):
        raise validation_error("purpose", "Use dust_suppression, concrete_curing, welfare, other.")
    if sum(purpose.values(), D(0)) != volume:
        raise validation_error("purpose", "The purpose split must sum to the volume.")
    return {k: str(v) for k, v in purpose.items()}


def _water(db: Session, p: Principal, wid: uuid.UUID) -> WaterEntry:
    w = db.get(WaterEntry, wid)
    if w is None or not p.can_see_project(w.project_id):
        raise not_found("Water entry")
    g = ec.need(p, w.project_id, C.env_view, write=False)
    if not g.covers_site(w.site_id):
        raise not_found("Water entry")
    return w


def list_water(
    db: Session, p: Principal, project_id: uuid.UUID, month: str | None, page: int, size: int
) -> WaterPage:
    g = ec.view_grant(db, p, project_id)
    q = select(WaterEntry).where(WaterEntry.project_id == project_id)
    if month:
        q = q.where(WaterEntry.month == month)
    rows = [
        w
        for w in db.scalars(q.order_by(WaterEntry.month.desc(), WaterEntry.source))
        if g.covers_site(w.site_id)
    ]
    return ec.paged(WaterPage, rows, page, size, water_read)


def create_water(db: Session, p: Principal, project_id: uuid.UUID, body: WaterCreate) -> WaterRead:
    ec.project(db, p, project_id)
    ec.site_of(db, project_id, body.site_id)
    ec.require(p, project_id, C.env_reading_record, body.site_id, check_eng=False)
    _open_month(body.month)
    if db.scalar(
        select(WaterEntry.id).where(
            WaterEntry.project_id == project_id, WaterEntry.site_id == body.site_id,
            WaterEntry.month == body.month, WaterEntry.source == body.source,
            WaterEntry.status == RecordState.valid,
        )
    ):  # fmt: skip
        raise ec.code_err(
            ErrorCode.DUPLICATE_WATER_ENTRY,
            "An entry for this site, month and source exists; edit it instead.",
            "يوجد سجل لهذا الموقع والشهر والمصدر.", "source",
        )  # fmt: skip
    w = WaterEntry(
        id=uuid.uuid4(), project_id=project_id, site_id=body.site_id, month=body.month,
        source=body.source, volume_m3=body.volume_m3,
        purpose=_purpose(body.volume_m3, body.purpose), status=RecordState.valid,
        created_by_user_id=p.user.id,
    )  # fmt: skip
    db.add(w)
    db.flush()
    ec.record(db, p, AuditAction.create, ET.water_entry, w, project_id)
    return water_read(w)


def update_water(db: Session, p: Principal, wid: uuid.UUID, body: WaterUpdate) -> WaterRead:
    w = _water(db, p, wid)
    ec.require(p, w.project_id, C.env_reading_record, w.site_id, check_eng=False)
    if w.status != RecordState.valid:
        raise _conflict("The entry is voided.")
    _open_month(w.month)
    vol = body.volume_m3 if body.volume_m3 is not None else D(w.volume_m3)
    pur = body.purpose if body.purpose is not None else {
        k: D(str(v)) for k, v in (w.purpose or {}).items()
    }  # fmt: skip
    w.volume_m3 = vol
    w.purpose = _purpose(vol, pur)
    w.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.update, ET.water_entry, w, w.project_id)
    return water_read(w)


def void_water(db: Session, p: Principal, wid: uuid.UUID, body: EnvVoid) -> WaterRead:
    w = _water(db, p, wid)
    p.require(w.project_id, C.env_void)
    if w.status != RecordState.valid:
        raise _conflict("The entry is already voided.")
    w.void_reason = ec.reason(body.reason, 20)
    w.status = RecordState.voided
    db.flush()
    ec.record(db, p, AuditAction.status_change, ET.water_entry, w, w.project_id)
    return water_read(w)


# ---- discharge days (WAT-2, WAT-3) ---------------------------------------------------------------


def _permit_valid(db: Session, pt: EnvPoint, d: date) -> bool:
    pm = next((x for x in ec.project_permits(db, pt.project_id) if x.id == pt.permit_id), None)
    return ec.permit_valid_on(db, pm, d)


def discharge_read(db: Session, x: DischargeDay) -> DischargeRead:
    pt = db.get(EnvPoint, x.point_id)
    return DischargeRead(
        id=x.id, point_id=x.point_id, day=x.day, volume_m3=str(ec.q1(x.volume_m3)),
        permit_valid=bool(pt and _permit_valid(db, pt, x.day)),
        warnings=ec.warnings_of(x.warnings),
    )  # fmt: skip


def list_discharge(
    db: Session, p: Principal, project_id: uuid.UUID, page: int, size: int
) -> DischargePage:
    ec.view_grant(db, p, project_id)
    rows = list(
        db.scalars(
            select(DischargeDay)
            .where(DischargeDay.project_id == project_id)
            .order_by(DischargeDay.day.desc())
        )
    )
    return ec.paged(DischargePage, rows, page, size, lambda x: discharge_read(db, x))


def create_discharge(
    db: Session, p: Principal, project_id: uuid.UUID, body: DischargeCreate
) -> DischargeRead:
    from app.services.env import monitoring  # noqa: PLC0415

    ec.project(db, p, project_id)
    pt = db.get(EnvPoint, body.point_id)
    if pt is None or pt.project_id != project_id or pt.kind != PointKind.discharge:
        raise validation_error("point_id", "Name a discharge point of the project.")
    ec.require(p, project_id, C.env_reading_record, pt.site_id, check_eng=False)
    if body.day > ec.local_day():
        raise validation_error("day", "The day cannot be in the future.")
    if db.scalar(
        select(DischargeDay.id).where(DischargeDay.point_id == pt.id, DischargeDay.day == body.day)
    ):
        raise ApiError(409, ErrorCode.DUPLICATE_VALUE, "This day is already recorded.",
                       "اليوم مسجل مسبقاً.")  # fmt: skip
    warn = [] if _permit_valid(db, pt, body.day) else ["PERMIT_NOT_VALID"]
    x = DischargeDay(
        id=uuid.uuid4(), project_id=project_id, point_id=pt.id, day=body.day,
        volume_m3=body.volume_m3, warnings=warn, created_by_user_id=p.user.id,
    )  # fmt: skip
    db.add(x)
    db.flush()
    if warn:
        monitoring.discharge_alert(db, pt, body.day)
    ec.record(db, p, AuditAction.create, ET.discharge_day, x, project_id)
    return discharge_read(db, x)


# ---- complaints (CPL, P6e-2) ---------------------------------------------------------------------


def due_on(db: Session, project_id: uuid.UUID, received: date, ch: ComplaintChannel) -> date:
    c = ec.cfg(db, project_id)
    key = (
        "authority_complaint_response_days"
        if ch == ComplaintChannel.via_authority
        else "complaint_response_days"
    )
    return received + timedelta(days=int(c[key]))


def complaint_read(db: Session, p: Principal | None, x: EnvComplaint) -> ComplaintRead:
    can = p is not None and not ec.is_viewer(p, x.project_id) and (
        p.grant(x.project_id, C.env_complaint) is not None
    )  # fmt: skip
    if x.anonymous:
        note = None
    elif x.contact_deleted_at is not None:
        note = "deleted"
    elif not can:
        note = HELD
    else:
        note = None
    show = can and x.contact_deleted_at is None
    warns = (
        [
            ec.warn(
                "POSSIBLE_ID_NUMBER",
                "The text may contain an ID number.",
                "قد يحتوي النص على رقم هوية.",
                "description",
            )
        ]
        if ec.p18(x.description)
        else []
    )
    return ComplaintRead(
        id=x.id, complaint_no=x.complaint_no, project_id=x.project_id, received_at=x.received_at,
        channel=x.channel, category=x.category, site_id=x.site_id, location_text=x.location_text,
        anonymous=x.anonymous, complainant_name=x.complainant_name if show else None,
        complainant_contact=x.complainant_contact if show else None, contact_note=note,
        description=x.description, reading_ids=list(x.reading_ids or []),
        exceedance_ids=list(x.exceedance_ids or []), investigation_en=x.investigation_en,
        investigation_ar=x.investigation_ar, response_due_on=x.response_due_on,
        response_sent_at=x.response_sent_at, response_summary=x.response_summary,
        status=x.status, void_reason=x.void_reason, warnings=warns,
    )  # fmt: skip


def _complaint(db: Session, p: Principal, cid: uuid.UUID) -> EnvComplaint:
    x = db.get(EnvComplaint, cid)
    if x is None or not p.can_see_project(x.project_id):
        raise not_found("Complaint")
    g = ec.need(p, x.project_id, C.env_view, write=False)
    if not g.covers_site(x.site_id):
        raise not_found("Complaint")
    return x


def list_complaints(
    db: Session, p: Principal, project_id: uuid.UUID, status: list[ComplaintStatus] | None,
    page: int, size: int,
) -> ComplaintPage:  # fmt: skip
    g = ec.view_grant(db, p, project_id)
    q = select(EnvComplaint).where(EnvComplaint.project_id == project_id)
    if status:
        q = q.where(EnvComplaint.status.in_(status))
    rows = [
        x
        for x in db.scalars(q.order_by(EnvComplaint.received_at.desc()))
        if g.covers_site(x.site_id)
    ]
    return ec.paged(ComplaintPage, rows, page, size, lambda x: complaint_read(db, p, x))


def create_complaint(
    db: Session, p: Principal, project_id: uuid.UUID, body: ComplaintCreate
) -> ComplaintRead:
    pr = ec.project(db, p, project_id)
    ec.site_of(db, project_id, body.site_id)
    p.require(project_id, C.env_complaint)
    if body.received_at > now() + timedelta(minutes=2):
        raise validation_error("received_at", "The receipt time cannot be in the future.")
    d = ec.local_day(body.received_at)
    seq = ec.next_seq(db, EnvComplaint, project_id, d.year)
    x = EnvComplaint(
        id=uuid.uuid4(), complaint_no=ec.ref("ECP", pr.code, d.year, seq, 3), year=d.year,
        seq=seq, project_id=project_id, received_at=body.received_at, received_date=d,
        channel=body.channel, category=body.category, site_id=body.site_id,
        location_text=body.location_text, anonymous=body.anonymous,
        complainant_name=None if body.anonymous else body.complainant_name,
        complainant_contact=None if body.anonymous else body.complainant_contact,
        description=body.description, reading_ids=list(body.reading_ids),
        exceedance_ids=list(body.exceedance_ids),
        response_due_on=due_on(db, project_id, d, body.channel), status=CS.open,
        created_by_user_id=p.user.id,
    )  # fmt: skip
    db.add(x)
    db.flush()
    users = ec.officers(db, project_id)
    if body.channel == ComplaintChannel.via_authority:
        users |= ec.managers(db)
    ec.send(
        db, users, NK.env_complaint,
        f"Complaint {x.complaint_no} ({x.category.value}) received; reply by "
        f"{x.response_due_on.isoformat()}.",
        f"تم استلام الشكوى {x.complaint_no}؛ الرد قبل {x.response_due_on.isoformat()}.",
        project_id, ET.env_complaint, x.id, email=True,
    )  # fmt: skip
    ec.record(db, p, AuditAction.create, ET.env_complaint, x, project_id)
    return complaint_read(db, p, x)


def read_complaint(db: Session, p: Principal, cid: uuid.UUID) -> ComplaintRead:
    return complaint_read(db, p, _complaint(db, p, cid))


def update_complaint(
    db: Session, p: Principal, cid: uuid.UUID, body: ComplaintUpdate
) -> ComplaintRead:
    x = _complaint(db, p, cid)
    p.require(x.project_id, C.env_complaint)
    if x.status in (CS.closed, CS.voided):
        raise _conflict(f"The complaint is {x.status.value}.")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(x, k, list(v) if isinstance(v, list) else v)
    x.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.update, ET.env_complaint, x, x.project_id)
    return complaint_read(db, p, x)


def transition_complaint(
    db: Session, p: Principal, cid: uuid.UUID, body: ComplaintTransition
) -> ComplaintRead:
    x = _complaint(db, p, cid)
    pid = x.project_id
    a = body.action
    if a == ComplaintAction.void:
        p.require(pid, C.env_void)
        if x.status != CS.open:
            raise _conflict("Only an open complaint is voided.")
        x.void_reason = ec.reason(body.reason, 20)
        x.status = CS.voided
    elif a == ComplaintAction.respond:
        p.require(pid, C.env_complaint)
        if x.status != CS.open:
            raise _conflict("Only an open complaint is responded to.")
        if not body.response_summary:
            raise validation_error("response_summary", "Summarise the response.")
        x.response_summary = body.response_summary
        x.response_sent_at = body.response_sent_at or now()
        x.status = CS.responded
    else:
        p.require(pid, C.env_complaint)
        if x.status != CS.responded:
            raise _conflict("Respond before closing.")
        x.status, x.closed_at = CS.closed, now()
    x.updated_by_user_id = p.user.id
    db.flush()
    ec.record(db, p, AuditAction.status_change, ET.env_complaint, x, pid)
    return complaint_read(db, p, x)


def nearby_readings(db: Session, p: Principal, cid: uuid.UUID) -> NearbyReadings:
    """CPL-2: readings of the site's points within ± 2 h (dust or noise complaints)."""
    from app.services.env import monitoring  # noqa: PLC0415

    x = _complaint(db, p, cid)
    params: set[Parameter] = set()
    if x.category == ComplaintCategory.dust:
        params = set(rf.DUST_PARAMS)
    elif x.category == ComplaintCategory.noise:
        params = {Parameter.laeq}
    if not params:
        return NearbyReadings(items=[])
    pts = [
        pt.id
        for pt in db.scalars(
            select(EnvPoint).where(
                EnvPoint.project_id == x.project_id, EnvPoint.site_id == x.site_id
            )
        )
    ]
    t0, t1 = x.received_at - timedelta(hours=2), x.received_at + timedelta(hours=2)
    rows = db.scalars(
        select(EnvReading)
        .where(
            EnvReading.point_id.in_(pts or [uuid.uuid4()]),
            EnvReading.parameter.in_(list(params)),
            EnvReading.averaging != Averaging.min15,
            EnvReading.status == RecordState.valid,
            EnvReading.window_end >= t0,
            EnvReading.window_start <= t1,
        )
        .order_by(EnvReading.window_start)
    )
    return NearbyReadings(items=[monitoring.reading_read(db, p, r) for r in rows])


def retention(db: Session, project_id: uuid.UUID, today: date) -> int:
    """P6e-2: complainant data deleted `complainant_retention_months` after closure."""
    from app.services.train.common import add_months  # noqa: PLC0415

    months = int(ec.cfg(db, project_id)["complainant_retention_months"])
    n = 0
    for x in db.scalars(
        select(EnvComplaint).where(
            EnvComplaint.project_id == project_id,
            EnvComplaint.closed_at.is_not(None),
            EnvComplaint.contact_deleted_at.is_(None),
        )
    ):
        assert x.closed_at is not None  # noqa: S101
        if add_months(ec.local_day(x.closed_at), months) <= today and (
            x.complainant_name or x.complainant_contact
        ):
            x.complainant_name = x.complainant_contact = None
            x.contact_deleted_at = now()
            n += 1
    db.flush()
    return n
