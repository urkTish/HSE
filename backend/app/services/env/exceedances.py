"""Exceedances (spec 6e-environmental §3.12, §4.5, EXD-1…EXD-6, AIR-1, ASP-3 (a)): episodes from
valid readings, alerts within the request (EXD-1 "within 60 s"), background suggestion and
auto-review, review with CA, void."""

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
    EnvInstrumentStatus,
    ExceedanceCause,
    ExceedanceStatus,
    Parameter,
    ReadingResult,
    RecordState,
)
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.hse_enums import CaSourceType, CaStatus
from app.models import CorrectiveAction, EnvExceedance, EnvInstrument, EnvPoint, EnvReading
from app.schemas.env import EnvVoid, ExceedancePage, ExceedanceRead, ExceedanceReview
from app.services.env import common as ec
from app.services.env import reference as rf
from app.services.permissions import Principal

C = Capability
ET = EntityType
NK = NotificationKind
XS = ExceedanceStatus
EC = ExceedanceCause
D = Decimal
AIRSIDE_MSG = (
    "Works dust may affect visibility on the airside — consider an operational suspension "
    "(Phase 2 ops-event form).",
    "قد يؤثر غبار الأعمال على الرؤية في الجانب الجوي",
)


def margin(param: Parameter, peak: Decimal, limit: Decimal) -> Decimal:
    """§3.12: (peak − limit) ÷ limit × 100; pH: distance outside the range."""
    if not limit:
        return D(0)
    if param == Parameter.ph and peak < limit:
        return (limit - peak) / limit * 100
    return (peak - limit) / limit * 100


def _worse(param: Parameter, a: Decimal, b: Decimal, limit: Decimal) -> bool:
    if param == Parameter.ph:
        return abs(a - limit) > abs(b - limit)
    return a > b


def _open_episode(db: Session, r: EnvReading) -> EnvExceedance | None:
    return db.scalar(
        select(EnvExceedance)
        .where(
            EnvExceedance.point_id == r.point_id,
            EnvExceedance.parameter == r.parameter,
            EnvExceedance.averaging == r.averaging,
            EnvExceedance.period == r.period,
            EnvExceedance.episode_open.is_(True),
            EnvExceedance.status != XS.voided,
        )
        .order_by(EnvExceedance.started_at.desc())
    )


def on_reading(db: Session, r: EnvReading, pt: EnvPoint) -> EnvExceedance | None:
    """EXD-1 / EXD-2 / EXD-6 for a valid reading that is not raw `15min`."""
    if r.averaging == Averaging.min15 or r.status != RecordState.valid:
        return None
    late = r.late_entry or r.source.value == "lab"
    ep = None if late else _open_episode(db, r)
    if ep is not None and r.window_start < ep.started_at:
        ep = None
    if r.result != ReadingResult.exceedance:
        if ep is not None:
            ep.episode_open = False
            db.flush()
        return None
    assert r.limit_value is not None  # noqa: S101
    if ep is not None:
        ep.reading_ids = [*(ep.reading_ids or []), r.id]
        if _worse(r.parameter, D(r.value), D(ep.peak_value), D(ep.limit_value)):
            ep.peak_value = r.value
            ep.margin_pct = margin(r.parameter, D(r.value), D(ep.limit_value)).quantize(D("0.1"))
        ep.ended_at = r.window_end
        r.exceedance_id = ep.id
        db.flush()
        return ep
    pr = ec.project(db, None, r.project_id)
    seq = ec.next_seq(db, EnvExceedance, r.project_id, r.day.year)
    x = EnvExceedance(
        id=uuid.uuid4(), exceedance_no=ec.ref("ENX", pr.code, r.day.year, seq, 4),
        year=r.day.year, seq=seq, project_id=r.project_id, point_id=pt.id, site_id=pt.site_id,
        parameter=r.parameter, averaging=r.averaging, period=r.period, reading_ids=[r.id],
        day=r.day, peak_value=r.value, limit_value=r.limit_value,
        margin_pct=margin(r.parameter, D(r.value), D(r.limit_value)).quantize(D("0.1")),
        started_at=r.window_start, ended_at=r.window_end, episode_open=not late,
        late_result=late, suggested_cause=EC.background_natural if r.background else None,
        background_ref=r.background_ref, status=XS.open, created_at=r.created_at,
        updated_at=r.created_at, seed_fake=r.seed_fake,
    )  # fmt: skip
    db.add(x)
    db.flush()
    r.exceedance_id = x.id
    alert_opened(db, x, pt)
    db.flush()
    return x


def alert_opened(db: Session, x: EnvExceedance, pt: EnvPoint) -> None:
    """EXD-1 (EXD-6 "late result") and AIR-1."""
    from app.services.env.monitoring import airside  # noqa: PLC0415

    label = " (late result)" if x.late_result else ""
    label_ar = " (نتيجة متأخرة)" if x.late_result else ""
    en = (
        f"{x.exceedance_no}{label}: {rf.PA[x.parameter][0]} {ec.q1(x.peak_value)} "
        f"{rf.unit_of(x.parameter)} above {ec.q1(x.limit_value)} at {pt.point_code}."
    )
    ar = f"{x.exceedance_no}{label_ar}: تجاوز الحد عند {pt.point_code}."
    users = ec.officers(db, x.project_id) | ec.site_engineers(db, x.project_id, x.site_id)
    if ec.once(db, f"env:exd:{x.id}"):
        ec.send(db, users, NK.env_exceedance, en, ar, x.project_id, ET.env_exceedance, x.id,
                email=True)  # fmt: skip
    if airside(db, pt) and x.suggested_cause != EC.background_natural:
        extra = ec.cap_holders(db, x.project_id, C.wap_suspend, x.site_id) | ec.managers(db)
        if ec.once(db, f"env:air1:{x.id}"):
            ec.send(
                db, extra, NK.airside_dust_alert,
                f"{x.exceedance_no} at {pt.point_code}: {AIRSIDE_MSG[0]}",
                f"{x.exceedance_no} عند {pt.point_code}: {AIRSIDE_MSG[1]}",
                x.project_id, ET.env_exceedance, x.id, email=True,
            )  # fmt: skip


def review_due(db: Session, x: EnvExceedance) -> date:
    return ec.local_day(x.created_at) + timedelta(
        days=int(ec.cfg(db, x.project_id)["exceedance_review_days"])
    )


def project_caused(x: EnvExceedance) -> bool:
    """K-123: not voided, cause (or while unreviewed the suggestion) not background_natural."""
    if x.status == XS.voided:
        return False
    c = x.cause if x.cause is not None else x.suggested_cause
    return c != EC.background_natural


def exceedance_read(db: Session, x: EnvExceedance) -> ExceedanceRead:
    from app.services.env.monitoring import airside  # noqa: PLC0415

    pt = db.get(EnvPoint, x.point_id)
    ca_ref, ca_status = ec.ca_info(db, x.ca_id)
    return ExceedanceRead(
        id=x.id, exceedance_no=x.exceedance_no, project_id=x.project_id, point_id=x.point_id,
        point_code=pt.point_code if pt else "?", site_id=x.site_id, parameter=x.parameter,
        averaging=x.averaging, period=x.period, reading_ids=list(x.reading_ids or []), day=x.day,
        peak_value=str(ec.q1(x.peak_value)), limit_value=str(ec.q1(x.limit_value)),
        margin_pct=str(ec.q1(x.margin_pct)), started_at=x.started_at, ended_at=x.ended_at,
        late_result=x.late_result, airside=bool(pt and airside(db, pt)),
        suggested_cause=x.suggested_cause, background_ref=x.background_ref, cause=x.cause,
        responsible_engagement_id=x.responsible_engagement_id, activity_en=x.activity_en,
        activity_ar=x.activity_ar, immediate_action_en=x.immediate_action_en,
        immediate_action_ar=x.immediate_action_ar, ca_id=x.ca_id, ca_ref=ca_ref,
        ca_status=ca_status, review_due_on=review_due(db, x), reviewed_at=x.reviewed_at,
        status=x.status, project_caused=project_caused(x),
    )  # fmt: skip


def _exceedance(db: Session, p: Principal, xid: uuid.UUID) -> EnvExceedance:
    x = db.get(EnvExceedance, xid)
    if x is None or not p.can_see_project(x.project_id):
        raise not_found("Exceedance")
    g = ec.need(p, x.project_id, C.env_view, write=False)
    if not g.covers_site(x.site_id):
        raise not_found("Exceedance")
    return x


def list_exceedances(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    status: list[ExceedanceStatus] | None,
    point_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
    page: int,
    size: int,
) -> ExceedancePage:
    g = ec.view_grant(db, p, project_id)
    q = select(EnvExceedance).where(EnvExceedance.project_id == project_id)
    if status:
        q = q.where(EnvExceedance.status.in_(status))
    if point_id:
        q = q.where(EnvExceedance.point_id == point_id)
    if date_from:
        q = q.where(EnvExceedance.day >= date_from)
    if date_to:
        q = q.where(EnvExceedance.day <= date_to)
    rows = [
        x
        for x in db.scalars(q.order_by(EnvExceedance.started_at.desc()))
        if g.covers_site(x.site_id)
    ]
    return ec.paged(ExceedancePage, rows, page, size, lambda x: exceedance_read(db, x))


def read_exceedance(db: Session, p: Principal, xid: uuid.UUID) -> ExceedanceRead:
    return exceedance_read(db, _exceedance(db, p, xid))


def review(db: Session, p: Principal, xid: uuid.UUID, body: ExceedanceReview) -> ExceedanceRead:
    """EXD-5 (and EXD-4 reclassification of a background exceedance)."""
    x = _exceedance(db, p, xid)
    p.require(x.project_id, C.env_review)
    reclass = x.status == XS.closed and x.cause == EC.background_natural
    if x.status not in (XS.open, XS.reviewed) and not reclass:
        raise ApiError(409, ErrorCode.INVALID_TRANSITION, "This exceedance cannot be reviewed.",
                       "لا يمكن مراجعة هذا التجاوز.")  # fmt: skip
    if body.cause == EC.project_activity and body.responsible_engagement_id is None:
        raise ec.code_err(
            ErrorCode.ENGAGEMENT_REQUIRED, "Name the responsible contractor (EXD-5).",
            "حدد المقاول المسؤول.", "responsible_engagement_id",
        )  # fmt: skip
    ec.eng_of_project(db, x.project_id, body.responsible_engagement_id)
    if body.cause == EC.instrument_fault and not _fault_handled(db, x):
        raise validation_error(
            "cause", "Void the readings or quarantine the instrument first (EXD-5)."
        )
    x.cause = body.cause
    x.responsible_engagement_id = body.responsible_engagement_id
    x.activity_en, x.activity_ar = body.activity_en, body.activity_ar
    x.immediate_action_en, x.immediate_action_ar = (
        body.immediate_action_en,
        body.immediate_action_ar,
    )
    x.reviewed_by_user_id, x.reviewed_at = p.user.id, now()
    want_ca = body.cause == EC.project_activity or (
        body.create_ca and body.cause in (EC.third_party, EC.unknown)
    )
    if want_ca and x.ca_id is None:
        pt = db.get(EnvPoint, x.point_id)
        pr = ec.project(db, None, x.project_id)
        ca = ec.make_ca(
            db, pr, CaSourceType.environmental, x.id, x.site_id, pt.zone_id if pt else None,
            body.responsible_engagement_id, "major",
            f"{x.exceedance_no}: {rf.PA[x.parameter][0]} exceedance at "
            f"{pt.point_code if pt else ''}",
            f"{x.exceedance_no} peak {ec.q1(x.peak_value)} {rf.unit_of(x.parameter)} vs limit "
            f"{ec.q1(x.limit_value)}. Activity: {body.activity_en or '—'}. Immediate action: "
            f"{body.immediate_action_en}",
            None, None, p.user.id,
        )  # fmt: skip
        x.ca_id = ca.id
    cur = db.get(CorrectiveAction, x.ca_id) if x.ca_id else None
    x.status = XS.reviewed if cur is not None and cur.status != CaStatus.closed else XS.closed
    x.episode_open = False if x.status == XS.closed else x.episode_open
    if body.cause == EC.project_activity:
        from app.services.env import register  # noqa: PLC0415

        register.flag_aspects(
            db, x.project_id, x.site_id, {rf.PARAM_ASPECT[x.parameter]}, x.exceedance_no
        )
    db.flush()
    ec.record(db, p, AuditAction.update, ET.env_exceedance, x, x.project_id)
    return exceedance_read(db, x)


def _fault_handled(db: Session, x: EnvExceedance) -> bool:
    rs = [db.get(EnvReading, i) for i in x.reading_ids or []]
    if rs and all(r is not None and r.status == RecordState.voided for r in rs):
        return True
    for r in rs:
        ins = db.get(EnvInstrument, r.instrument_id) if r and r.instrument_id else None
        if ins is not None and ins.status == EnvInstrumentStatus.quarantined:
            return True
    return False


def void(db: Session, p: Principal, xid: uuid.UUID, body: EnvVoid) -> ExceedanceRead:
    x = _exceedance(db, p, xid)
    p.require(x.project_id, C.env_void)
    if x.status in (XS.voided, XS.closed):
        raise ApiError(409, ErrorCode.INVALID_TRANSITION, "This exceedance cannot be voided.",
                       "لا يمكن إلغاء هذا التجاوز.")  # fmt: skip
    x.void_reason = ec.reason(body.reason, 20)
    x.status, x.episode_open = XS.voided, False
    db.flush()
    ec.record(db, p, AuditAction.status_change, ET.env_exceedance, x, x.project_id)
    return exceedance_read(db, x)


# ---- jobs ----------------------------------------------------------------------------------------


def daily(db: Session, project_id: uuid.UUID, today: date) -> None:
    """EXD-3 auto-review of background exceedances; closure when the CA is Closed."""
    for x in db.scalars(
        select(EnvExceedance).where(
            EnvExceedance.project_id == project_id,
            EnvExceedance.status.in_([XS.open, XS.reviewed]),
        )
    ):
        if x.status == XS.open and x.suggested_cause == EC.background_natural:
            if review_due(db, x) <= today:
                x.cause, x.status, x.reviewed_at = EC.background_natural, XS.closed, now()
                x.episode_open = False
        elif x.status == XS.reviewed and x.ca_id:
            ca = db.get(CorrectiveAction, x.ca_id)
            if ca is not None and ca.status == CaStatus.closed:
                x.status = XS.closed
    db.flush()


def review_alerts(db: Session, project_id: uuid.UUID, today: date) -> int:
    """EXD-5: at the deadline, then daily, to the HSE Officers."""
    n = 0
    for x in db.scalars(
        select(EnvExceedance).where(
            EnvExceedance.project_id == project_id, EnvExceedance.status == XS.open
        )
    ):
        if x.suggested_cause == EC.background_natural or review_due(db, x) > today:
            continue
        if ec.once(db, f"env:exd_review:{x.id}:{today.isoformat()}"):
            n += ec.send(
                db, ec.officers(db, project_id), NK.env_exceedance,
                f"{x.exceedance_no} is awaiting review (due {review_due(db, x).isoformat()}).",
                f"التجاوز {x.exceedance_no} بانتظار المراجعة.",
                project_id, ET.env_exceedance, x.id, email=True,
            )  # fmt: skip
    return n
