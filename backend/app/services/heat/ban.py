"""Midday ban for work without a permit (spec 6b-heat-stress §3.9, §3.10, MB-1…MB-6): patrol
checks and HSE Manager exemptions."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind
from app.core.errors import ErrorCode, not_found, validation_error
from app.core.heat_enums import BanExemptionStatus, PatrolOutcome, RecordStatus
from app.models import (
    BanExemption,
    BanPatrol,
    CorrectiveAction,
    Permit,
    ProjectEngagement,
    Zone,
)
from app.schemas.heat import (
    BanExemptionCreate,
    BanExemptionPage,
    BanExemptionRead,
    PatrolCreate,
    PatrolPage,
    PatrolRead,
    RevokeInput,
    VoidInput,
)
from app.services import audit
from app.services.common import invalid_transition, paginate
from app.services.heat import common as hc
from app.services.permissions import Principal

C = Capability
O = PatrolOutcome  # noqa: E741
K = NotificationKind
BX = BanExemptionStatus

# ---- patrols -------------------------------------------------------------------------------------


def patrol_read(db: Session, x: BanPatrol) -> PatrolRead:
    z = db.get(Zone, x.zone_id)
    ca = db.get(CorrectiveAction, x.ca_id) if x.ca_id else None
    return PatrolRead(
        id=x.id,
        patrol_no=x.patrol_no,
        project_id=x.project_id,
        zone_id=x.zone_id,
        zone_code=z.code if z else "?",
        checked_at=x.checked_at,
        checked_by=hc.user_ref(db, x.checked_by_user_id),
        outcome=x.outcome,
        engagement_id=x.engagement_id,
        contractor_code=hc.contractor_code(db, x.engagement_id),
        headcount=x.headcount,
        activity=x.activity,
        exemption_ref=x.exemption_ref,
        permit_id=x.permit_id,
        photo_ids=list(x.photo_ids or []),
        ca_ref=ca.ref if ca else None,
        status=x.status,
        void_reason=x.void_reason,
    )


def active_exemption(
    db: Session, project_id: uuid.UUID, engagement_id: uuid.UUID, zone_id: uuid.UUID, at: datetime
) -> str | None:
    """A 6b exemption (or a Phase 3 HT-4 exemption on a permit of the engagement in the zone)
    active at `at` that covers the engagement and the zone."""
    d = hc.local_day(at)
    for x in db.scalars(
        select(BanExemption).where(
            BanExemption.project_id == project_id,
            BanExemption.engagement_id == engagement_id,
            BanExemption.status == BX.active,
            BanExemption.date_from <= d,
            BanExemption.date_to >= d,
        )
    ):
        if zone_id in (x.zone_ids or []):
            return x.exemption_no
    from app.core.ptw_enums import ExemptionKind, ExemptionStatus  # noqa: PLC0415
    from app.models import PermitExemption  # noqa: PLC0415

    for pe, pm in db.execute(
        select(PermitExemption, Permit)
        .join(Permit, Permit.id == PermitExemption.permit_id)
        .where(
            Permit.project_id == project_id,
            Permit.engagement_id == engagement_id,
            PermitExemption.kind == ExemptionKind.midday_ban,
            PermitExemption.status == ExemptionStatus.granted,
        )
    ):
        if zone_id in (pm.zone_ids or []) and (pe.valid_to is None or pe.valid_to >= d):
            return pm.permit_no
    return None


def _not_in_window() -> object:
    return hc.err(
        422,
        ErrorCode.NOT_IN_BAN_WINDOW,
        "A patrol check is recorded only inside the midday-ban hours of a ban date (MB-1).",
        "تسجل جولة الحظر فقط خلال ساعات حظر الظهيرة في فترة الحظر.",
        field="checked_at",
    )


def create_patrol(
    db: Session, p: Principal, project_id: uuid.UUID, body: PatrolCreate
) -> PatrolRead:
    hc.project(db, p, project_id)
    g = p.require(project_id, C.heat_patrol_record)
    z = db.get(Zone, body.zone_id)
    zones = hc.zone_map(db, project_id)
    if z is None or z.id not in zones:
        raise validation_error("zone_id", "Unknown zone for this project.")
    if not g.covers_site(z.site_id):
        raise not_found("Zone")
    cfg = hc.cfg(db, project_id)
    at = now()
    if not cfg.in_ban(body.checked_at):
        raise _not_in_window()  # type: ignore[misc]
    if body.checked_at > at + timedelta(minutes=2) or body.checked_at < at - timedelta(hours=4):
        raise validation_error("checked_at", "Within the last 4 hours.")
    needs = body.outcome in (O.violation, O.exempt_work)
    if needs:
        if body.engagement_id is None:
            raise validation_error("engagement_id", "Name the contractor.")
        if body.headcount is None:
            raise validation_error("headcount", "Give the number of workers (1–500).")
        if not (body.activity or "").strip():
            raise validation_error("activity", "Describe the activity.")
        eng = db.get(ProjectEngagement, body.engagement_id)
        if eng is None or eng.project_id != project_id:
            raise validation_error("engagement_id", "Unknown engagement for this project.")
    ex_ref: str | None = None
    if body.outcome == O.exempt_work:
        assert body.engagement_id is not None  # noqa: S101
        ex_ref = active_exemption(db, project_id, body.engagement_id, z.id, body.checked_at)
        if ex_ref is None:
            raise hc.err(
                422,
                ErrorCode.NO_ACTIVE_EXEMPTION,
                "No active exemption covers this contractor and zone; record a violation.",
                "لا يوجد استثناء فعال لهذا المقاول وهذه المنطقة؛ سجل مخالفة.",
                field="outcome",
            )
    if body.permit_id is not None:
        pm = db.get(Permit, body.permit_id)
        if pm is None or pm.project_id != project_id:
            raise validation_error("permit_id", "Unknown permit for this project.")
    y = hc.local_day(body.checked_at).year
    seq = hc.next_seq(db, BanPatrol, project_id, y)
    x = BanPatrol(
        id=uuid.uuid4(),
        year=y,
        seq=seq,
        patrol_no=f"MBP-{hc.pcode(db, project_id)}-{y}-{seq:05d}",
        project_id=project_id,
        zone_id=z.id,
        checked_at=body.checked_at,
        checked_by_user_id=p.user.id,
        outcome=body.outcome,
        engagement_id=body.engagement_id if needs else None,
        headcount=body.headcount if needs else None,
        activity=(body.activity or "").strip() or None if needs else None,
        exemption_ref=ex_ref,
        permit_id=body.permit_id,
        photo_ids=list(body.photo_ids),
        status=RecordStatus.valid,
        created_by_user_id=p.user.id,
    )
    db.add(x)
    db.flush()
    hc.record(db, p, AuditAction.create, EntityType.ban_patrol, x, project_id)
    if body.outcome == O.violation:
        assert body.engagement_id is not None  # noqa: S101
        _violation(db, p, x, z)
    return patrol_read(db, x)


def _violation(db: Session, p: Principal, x: BanPatrol, z: Zone) -> None:
    """MB-3 CA and alerts; MB-4 permit link."""
    assert x.engagement_id is not None  # noqa: S101
    d = hc.local_day(x.checked_at)
    code = hc.contractor_code(db, x.engagement_id) or ""
    ca = hc.make_ca(
        db,
        x.project_id,
        x.id,
        z.site_id,
        z.id,
        x.engagement_id,
        f"Midday ban violation in {z.code} ({code})",
        f"Patrol {x.patrol_no}: {x.headcount} worker(s) of {code} in direct sun during the "
        f"midday ban ({x.activity}). Stop the work, brief the crew and plan the task outside the "
        "ban hours.",
        d + timedelta(days=1),
        p.user.id,
    )
    x.ca_id = ca.id
    db.flush()
    users = (
        hc.reps(db, x.project_id, x.engagement_id) | hc.officers(db, x.project_id) | hc.managers(db)
    )
    hc.send(
        db,
        users,
        K.heat_ban_violation,
        f"Midday ban violation in {z.code}: {code}, {x.headcount} worker(s) ({x.patrol_no}). "
        "MHRSD fines may apply.",
        f"مخالفة حظر العمل وقت الظهيرة في {z.code}: {code}، {x.headcount} عامل. قد تطبق غرامات.",
        x.project_id,
        EntityType.ban_patrol,
        x.id,
        email=True,
    )
    if x.permit_id is not None:
        audit.record(
            db,
            AuditAction.update,
            p.actor(x.project_id),
            entity_type=EntityType.permit,
            entity_id=x.permit_id,
            project_id=x.project_id,
            after={"midday_ban_violation": x.patrol_no},
        )


def list_patrols(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    zone_id: uuid.UUID | None,
    outcome: PatrolOutcome | None,
    day: date | None,
) -> PatrolPage:
    hc.project(db, p, project_id)
    hc.need(p, project_id, C.heat_view, write=False)
    stmt = select(BanPatrol).where(BanPatrol.project_id == project_id)
    if zone_id:
        stmt = stmt.where(BanPatrol.zone_id == zone_id)
    if outcome:
        stmt = stmt.where(BanPatrol.outcome == outcome)
    if day:
        stmt = stmt.where(
            BanPatrol.checked_at >= hc.day_start(day),
            BanPatrol.checked_at < hc.day_start(day + timedelta(days=1)),
        )
    stmt = stmt.order_by(BanPatrol.checked_at.desc())
    rows, total = paginate(db, stmt, page, page_size)
    return PatrolPage(
        items=[patrol_read(db, x) for x in rows], total=total, page=page, page_size=page_size
    )


def void_patrol(db: Session, p: Principal, patrol_id: uuid.UUID, body: VoidInput) -> PatrolRead:
    x = db.get(BanPatrol, patrol_id)
    if x is None or not p.can_see_project(x.project_id):
        raise not_found("Patrol check")
    p.require(x.project_id, C.heat_void)
    why = hc.reason(body.reason, 20)
    if x.status != RecordStatus.valid:
        raise invalid_transition("Patrol check", x.status, RecordStatus.voided)
    before = {"status": x.status.value}
    x.status, x.void_reason = RecordStatus.voided, why
    db.flush()
    hc.record(db, p, AuditAction.status_change, EntityType.ban_patrol, x, x.project_id, before)
    return patrol_read(db, x)


# ---- exemptions ----------------------------------------------------------------------------------


def exemption_read(db: Session, x: BanExemption) -> BanExemptionRead:
    zs = hc.zone_map(db, x.project_id)
    return BanExemptionRead(
        id=x.id,
        exemption_no=x.exemption_no,
        project_id=x.project_id,
        engagement_id=x.engagement_id,
        contractor_code=hc.contractor_code(db, x.engagement_id),
        zone_ids=list(x.zone_ids or []),
        zone_codes=[zs[z].code if z in zs else "?" for z in x.zone_ids or []],
        date_from=x.date_from,
        date_to=x.date_to,
        reason=x.reason,
        controls_en=x.controls_en,
        controls_ar=x.controls_ar,
        granted_by=hc.user_ref(db, x.granted_by_user_id),
        granted_at=x.granted_at,
        status=x.status,
        status_reason=x.status_reason,
    )


def grant(
    db: Session, p: Principal, project_id: uuid.UUID, body: BanExemptionCreate
) -> BanExemptionRead:
    hc.project(db, p, project_id)
    p.require(project_id, C.heat_exemption_grant)
    cfg = hc.cfg(db, project_id)
    eng = db.get(ProjectEngagement, body.engagement_id)
    if eng is None or eng.project_id != project_id:
        raise validation_error("engagement_id", "Unknown engagement for this project.")
    zones = hc.zone_map(db, project_id)
    if any(z not in zones for z in body.zone_ids):
        raise validation_error("zone_ids", "Unknown zone for this project.")
    if body.date_to < body.date_from:
        raise validation_error("date_to", "The end date is before the start date.")
    if not (cfg.ban_date(body.date_from) and cfg.ban_date(body.date_to)):
        raise hc.err(
            422,
            ErrorCode.OUTSIDE_BAN_PERIOD,
            "Exemption dates must be inside the midday-ban period.",
            "يجب أن تكون تواريخ الاستثناء ضمن فترة الحظر.",
            field="date_from",
        )
    if (body.date_to - body.date_from).days + 1 > 14:
        raise validation_error("date_to", "An exemption covers at most 14 days.")
    en, ar = (body.controls_en or "").strip(), (body.controls_ar or "").strip()
    if len(en) < 30 and len(ar) < 30:
        raise validation_error("controls_en", "Describe the controls in at least 30 characters.")
    at = now()
    y = body.date_from.year
    seq = hc.next_seq(db, BanExemption, project_id, y)
    x = BanExemption(
        id=uuid.uuid4(),
        year=y,
        seq=seq,
        exemption_no=f"MBX-{hc.pcode(db, project_id)}-{y}-{seq:03d}",
        project_id=project_id,
        engagement_id=body.engagement_id,
        zone_ids=list(body.zone_ids),
        date_from=body.date_from,
        date_to=body.date_to,
        reason=body.reason,
        controls_en=en or None,
        controls_ar=ar or None,
        granted_by_user_id=p.user.id,
        granted_at=at,
        status=BX.active,
        alerts_sent=[],
        created_by_user_id=p.user.id,
    )
    db.add(x)
    db.flush()
    hc.record(db, p, AuditAction.create, EntityType.ban_exemption, x, project_id)
    _tell(db, x, "granted", "منح")
    return exemption_read(db, x)


def _tell(db: Session, x: BanExemption, en: str, ar: str) -> None:
    hc.send(
        db,
        hc.officers(db, x.project_id) | hc.reps(db, x.project_id, x.engagement_id),
        K.heat_exemption,
        f"Midday-ban exemption {x.exemption_no} {en} ({x.date_from} → {x.date_to})",
        f"استثناء حظر الظهيرة {x.exemption_no}: {ar}",
        x.project_id,
        EntityType.ban_exemption,
        x.id,
    )


def revoke(
    db: Session, p: Principal, exemption_id: uuid.UUID, body: RevokeInput
) -> BanExemptionRead:
    x = db.get(BanExemption, exemption_id)
    if x is None or not p.can_see_project(x.project_id):
        raise not_found("Exemption")
    p.require(x.project_id, C.heat_exemption_grant)
    why = hc.reason(body.reason, 20)
    if x.status != BX.active:
        raise invalid_transition("Exemption", x.status, BX.revoked)
    before = {"status": x.status.value}
    x.status, x.status_reason = BX.revoked, why
    db.flush()
    hc.record(db, p, AuditAction.status_change, EntityType.ban_exemption, x, x.project_id, before)
    _tell(db, x, "revoked", "ألغي")
    return exemption_read(db, x)


def list_exemptions(
    db: Session,
    p: Principal,
    project_id: uuid.UUID,
    page: int,
    page_size: int,
    status: BanExemptionStatus | None,
) -> BanExemptionPage:
    hc.project(db, p, project_id)
    hc.need(p, project_id, C.heat_view, write=False)
    stmt = select(BanExemption).where(BanExemption.project_id == project_id)
    if status:
        stmt = stmt.where(BanExemption.status == status)
    stmt = stmt.order_by(BanExemption.exemption_no.desc())
    rows, total = paginate(db, stmt, page, page_size)
    return BanExemptionPage(
        items=[exemption_read(db, x) for x in rows], total=total, page=page, page_size=page_size
    )


def expire(db: Session, project_id: uuid.UUID, today: date) -> int:
    """§4.3: Active → Expired after date_to; 'ending tomorrow' alert the day before date_to."""
    n = 0
    for x in db.scalars(
        select(BanExemption).where(
            BanExemption.project_id == project_id, BanExemption.status == BX.active
        )
    ):
        if x.date_to < today:
            x.status = BX.expired
            n += 1
        elif x.date_to == today + timedelta(days=1) and "ending" not in (x.alerts_sent or []):
            x.alerts_sent = [*(x.alerts_sent or []), "ending"]
            _tell(db, x, "ends tomorrow", "ينتهي غداً")
    db.flush()
    return n
