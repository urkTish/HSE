"""Common credential lifecycle API (spec 2-access-permits §3.18, §4.3, §4.5, §4.9, §5.9 LC-1…LC-14)
for induction records, airport passes, ADPs, AVPs and access cards (deployments)."""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access_enums import (
    DEPENDENCY_REASONS,
    CredentialAction,
    CredentialKind,
    CredentialReason,
    CustodyStatus,
    DeploymentStatus,
    InductionStatus,
    QrKind,
    QrTokenStatus,
    SuspensionState,
    ValidityStatus,
)
from app.core.clock import now, today
from app.core.enums import AuditAction, Capability, EntityType, NotificationKind, Role
from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.models import (
    Adp,
    AirportPass,
    Avp,
    CredentialEvent,
    CredentialSuspension,
    Deployment,
    InductionRecord,
    Vehicle,
    Worker,
)
from app.schemas.access_common import CredentialEventRead, ValidityBlock
from app.schemas.access_common import CredentialSuspension as SuspensionRead
from app.schemas.credentials import (
    AuthorityNotifiedRequest,
    ConfirmSuspensionRequest,
    CredentialEventPage,
    CredentialState,
    LossReportRequest,
    ReinstateRequest,
    ReturnRequest,
    RevokeRequest,
    SuspendRequest,
)
from app.services import audit, notify, projects
from app.services.access import common, lifecycle, workers
from app.services.common import paginate
from app.services.hse_common import Refs, contractor_reps
from app.services.permissions import Principal, forbidden_error

C = Capability
Obj = InductionRecord | AirportPass | Adp | Avp | Deployment
ENTITY = {
    CredentialKind.induction: EntityType.induction_record,
    CredentialKind.airport_pass: EntityType.airport_pass,
    CredentialKind.adp: EntityType.adp,
    CredentialKind.avp: EntityType.avp,
    CredentialKind.access_card: EntityType.worker_deployment,
}
MANUAL_LIFT_BLOCKED = DEPENDENCY_REASONS


@dataclass
class Subject:
    kind: CredentialKind
    obj: Obj
    project_id: uuid.UUID
    site_ids: list[uuid.UUID] | None
    engagement_id: uuid.UUID | None
    worker: Worker | None
    vehicle: Vehicle | None

    @property
    def number(self) -> str:
        o = self.obj
        if isinstance(o, InductionRecord):
            return o.induction_no
        if isinstance(o, AirportPass):
            return o.pass_no
        if isinstance(o, Adp):
            return o.adp_no or "—"
        if isinstance(o, Avp):
            return o.avp_no or "—"
        return self.worker.worker_no if self.worker else "—"


def subject(db: Session, kind: CredentialKind, credential_id: uuid.UUID) -> Subject | None:
    model = lifecycle.KIND_MODEL.get(kind)
    if model is None or kind == CredentialKind.wap:
        return None
    obj = db.get(model, credential_id)
    if obj is None:
        return None
    if isinstance(obj, Avp):
        v = db.get(Vehicle, obj.vehicle_id)
        return Subject(kind, obj, obj.project_id, None, obj.engagement_id, None, v)
    dep_id = obj.id if isinstance(obj, Deployment) else obj.deployment_id
    d = db.get(Deployment, dep_id)
    w = db.get(Worker, obj.worker_id)
    return Subject(
        kind,
        obj,
        obj.project_id,
        list(d.site_ids or []) if d else None,
        d.engagement_id if d else getattr(obj, "engagement_id", None),
        w,
        None,
    )


def _load(db: Session, p: Principal, kind: CredentialKind, cid: uuid.UUID) -> Subject:
    s = subject(db, kind, cid)
    if s is None:
        raise not_found("Credential")
    projects.get_visible(db, p, s.project_id)
    view = C.worker_view if s.vehicle is None else C.access_works_view
    g = p.grant(s.project_id, view) or p.grant(s.project_id, C.worker_view)
    if not common.grant_covers(g, s.site_ids, s.engagement_id):
        raise forbidden_error("This credential is outside your scope.")
    return s


def _require(p: Principal, s: Subject, cap: Capability) -> None:
    common.require_cap(p, s.project_id, cap, s.site_ids, s.engagement_id)


def _confirm_cap(kind: CredentialKind) -> Capability:
    return (
        C.induction_suspend_revoke
        if kind == CredentialKind.induction
        else (C.credential_suspend_confirm)
    )


def _has(p: Principal, s: Subject, cap: Capability) -> bool:
    return common.grant_covers(p.grant(s.project_id, cap), s.site_ids, s.engagement_id)


def _terminal() -> ApiError:
    return ApiError(
        409,
        ErrorCode.CREDENTIAL_TERMINAL,
        "The credential is revoked, expired, superseded or lost (LC-5).",
        "التصريح ملغى أو منتهٍ أو مفقود.",
    )


def _live(s: Subject) -> bool:
    o = s.obj
    if isinstance(o, InductionRecord):
        return o.status in (InductionStatus.valid, InductionStatus.suspended)
    if isinstance(o, AirportPass | Adp | Avp):
        return o.validity_status in (ValidityStatus.active, ValidityStatus.suspended)
    return o.status == DeploymentStatus.mobilised


def _not_for_card(s: Subject, what: str) -> None:
    if s.kind == CredentialKind.access_card:
        raise validation_error(
            "kind", f"Access cards cannot be {what}; revoke or reissue the card instead."
        )


# ---- reads --------------------------------------------------------------------------------------


def _event_read(e: CredentialEvent, refs: Refs) -> CredentialEventRead:
    return CredentialEventRead(
        id=e.id,
        credential_kind=e.credential_kind,
        credential_id=e.credential_id,
        action=e.action,
        reason_code=e.reason_code,
        reason_text=e.reason_text,
        actor=refs.user(e.actor_user_id),
        occurred_at=e.occurred_at,
        expires_at=e.expires_at,
    )


def suspension_read(sp: CredentialSuspension, refs: Refs) -> SuspensionRead:
    return SuspensionRead(
        state=sp.state,
        reason_code=sp.reason_code,
        reason_text=sp.reason_text,
        raised_by=refs.user(sp.raised_by_user_id),
        raised_at=sp.raised_at,
        expires_at=sp.expires_at if sp.state == SuspensionState.raised else None,
        suspension_end=sp.suspension_end,
    )


def state(db: Session, p: Principal | None, s: Subject) -> CredentialState:
    o = s.obj
    refs = Refs(db)
    events = list(
        db.scalars(
            select(CredentialEvent)
            .where(
                CredentialEvent.credential_kind == s.kind,
                CredentialEvent.credential_id == o.id,
            )
            .order_by(CredentialEvent.occurred_at.desc())
            .limit(10)
        )
    )
    tok = common.latest_qr(db, o.id) if s.kind == CredentialKind.access_card else None
    cred = o if isinstance(o, AirportPass | Adp | Avp) else None
    eff = None
    if isinstance(o, InductionRecord):
        eff = lifecycle.induction_valid_until(o)
    elif cred is not None:
        eff = cred.effective_valid_until
    return CredentialState(
        kind=s.kind,
        id=o.id,
        number=s.number,
        worker=common.worker_ref(s.worker, common.can_see_names(p, s.project_id))
        if s.worker
        else None,
        vehicle_no=s.vehicle.vehicle_no if s.vehicle else None,
        engagement=refs.eng(s.engagement_id),
        validity_status=cred.validity_status if cred else None,
        induction_status=o.status if isinstance(o, InductionRecord) else None,
        token_status=tok.status if tok else None,
        effective_valid_until=eff,
        limiting_factor=cred.limiting_factor if cred else None,
        custody_status=cred.custody_status if cred else None,
        return_due_on=cred.return_due_on if cred else None,
        returned_at=cred.returned_at if cred else None,
        received_by=refs.user(cred.received_by_user_id) if cred else None,
        lost_reported_at=cred.lost_reported_at if cred else None,
        authority_notified_at=cred.authority_notified_at if cred else None,
        open_suspensions=[suspension_read(x, refs) for x in lifecycle.open_suspensions(db, o)],
        events=[_event_read(e, refs) for e in events],
    )


def read_state(db: Session, p: Principal, kind: CredentialKind, cid: uuid.UUID) -> CredentialState:
    return state(db, p, _load(db, p, kind, cid))


def list_events(
    db: Session, p: Principal, kind: CredentialKind, cid: uuid.UUID, page: int, page_size: int
) -> CredentialEventPage:
    s = _load(db, p, kind, cid)
    stmt = (
        select(CredentialEvent)
        .where(CredentialEvent.credential_kind == kind, CredentialEvent.credential_id == s.obj.id)
        .order_by(CredentialEvent.occurred_at.desc())
    )
    rows, total = paginate(db, stmt, page, page_size)
    refs = Refs(db).load(users=[e.actor_user_id for e in rows])
    return CredentialEventPage(
        items=[_event_read(e, refs) for e in rows], total=total, page=page, page_size=page_size
    )


# ---- notifications ------------------------------------------------------------------------------


def holder_audience(db: Session, s: Subject) -> set[uuid.UUID]:
    users = set(notify.users_with_role(db, Role.hse_officer, [s.project_id]))
    users.update(contractor_reps(db, s.project_id, s.engagement_id))
    return users


def status_changed(db: Session, s: Subject, what_en: str, what_ar: str) -> None:
    """§7 credential status change → holder's Contractor HSE Reps and HSE Officers. No ID
    numbers in texts (P2-x)."""
    notify.notify(
        db,
        holder_audience(db, s),
        NotificationKind.credential_status_changed,
        f"{s.number}: {what_en}",
        f"{s.number}: {what_ar}",
        None,
        None,
        ENTITY[s.kind],
        s.obj.id,
        s.project_id,
    )


def _audit(db: Session, p: Principal, s: Subject, action: str, details: dict[str, object]) -> None:
    audit.record(
        db,
        AuditAction.update,
        p.actor(s.project_id),
        entity_type=ENTITY[s.kind],
        entity_id=s.obj.id,
        project_id=s.project_id,
        details={"credential_action": action, **details},
    )


# ---- after-change cascades ----------------------------------------------------------------------


def after_change(db: Session, s: Subject) -> None:
    """A pass changing state re-evaluates the worker's ADPs (DP-3 dependency, AC37)."""
    if isinstance(s.obj, AirportPass):
        for a in db.scalars(select(Adp).where(Adp.pass_id == s.obj.id)):
            lifecycle.evaluate_adp(db, a)
    db.flush()


# ---- actions ------------------------------------------------------------------------------------


def suspend(
    db: Session, p: Principal, kind: CredentialKind, cid: uuid.UUID, body: SuspendRequest
) -> CredentialState:
    s = _load(db, p, kind, cid)
    _not_for_card(s, "suspended")
    p.ensure_writer()
    if body.reason_code in DEPENDENCY_REASONS:
        raise validation_error("reason_code", "Dependency reasons are applied by the system only.")
    if not _live(s):
        raise _terminal()
    text = common.reason_text(body.reason_text)
    if _has(p, s, _confirm_cap(kind)):
        sp = lifecycle.suspend(
            db, s.obj, SuspensionState.confirmed, body.reason_code, text, p.user.id
        )
    elif _has(p, s, C.credential_suspend_raise):
        st = common.settings(db, s.project_id)
        sp = lifecycle.suspend(
            db,
            s.obj,
            SuspensionState.raised,
            body.reason_code,
            text,
            p.user.id,
            expires_at=now() + timedelta(hours=st.raised_suspension_max_hours),
        )
        notify.notify(
            db,
            notify.users_with_role(db, Role.hse_officer, [s.project_id]),
            NotificationKind.raised_suspension_pending,
            f"Suspension raised on {s.number}: confirm within {st.raised_suspension_max_hours} h",
            f"تم رفع إيقاف على {s.number}: يلزم التأكيد خلال {st.raised_suspension_max_hours} ساعة",
            None,
            None,
            ENTITY[s.kind],
            s.obj.id,
            s.project_id,
        )
    else:
        _require(p, s, C.credential_suspend_raise)
        raise forbidden_error()
    status_changed(db, s, "suspended", "تم الإيقاف")
    after_change(db, s)
    _audit(db, p, s, f"suspend_{sp.state.value}", {"reason_code": body.reason_code.value})
    return state(db, p, s)


def confirm(
    db: Session,
    p: Principal,
    kind: CredentialKind,
    cid: uuid.UUID,
    body: ConfirmSuspensionRequest,
) -> CredentialState:
    s = _load(db, p, kind, cid)
    _require(p, s, _confirm_cap(kind))
    raised = [x for x in lifecycle.open_suspensions(db, s.obj) if x.state == SuspensionState.raised]
    if not raised:
        raise ApiError(
            409,
            ErrorCode.INVALID_TRANSITION,
            "There is no raised suspension to confirm.",
            "لا يوجد إيقاف مرفوع لتأكيده.",
        )
    text = common.reason_text(body.reason_text)
    for sp in raised:
        sp.state = SuspensionState.confirmed
        sp.confirmed_by_user_id = p.user.id
        sp.confirmed_at = now()
        sp.expires_at = None
        lifecycle.event(
            db, s.obj, CredentialAction.suspend_confirmed, sp.reason_code, text, p.user.id
        )
    db.flush()
    _audit(db, p, s, "suspend_confirmed", {})
    return state(db, p, s)


def reinstate(
    db: Session, p: Principal, kind: CredentialKind, cid: uuid.UUID, body: ReinstateRequest
) -> CredentialState:
    s = _load(db, p, kind, cid)
    _not_for_card(s, "reinstated")
    _require(p, s, _confirm_cap(kind))
    o = s.obj
    opened = lifecycle.open_suspensions(db, o)
    if not opened:
        raise ApiError(
            409,
            ErrorCode.INVALID_TRANSITION,
            "The credential is not suspended.",
            "التصريح غير موقوف.",
        )
    if isinstance(o, InductionRecord):
        vu = lifecycle.induction_valid_until(o)
        if vu is not None and vu < today():
            raise _terminal()
    day = today()
    manual = [x for x in opened if x.reason_code not in MANUAL_LIFT_BLOCKED]
    running = [x for x in manual if x.suspension_end is not None and day <= x.suspension_end]
    if running:
        end = max(x.suspension_end for x in running if x.suspension_end)
        raise ApiError(
            422,
            ErrorCode.SUSPENSION_PERIOD_RUNNING,
            f"The suspension period runs until {end.isoformat()}; reinstate from "
            f"{(end + timedelta(days=1)).isoformat()} (DP-8).",
            f"فترة الإيقاف سارية حتى {end.isoformat()}.",
            meta={"suspension_end": end.isoformat()},
        )
    if not manual:
        raise ApiError(
            409,
            ErrorCode.SYSTEM_SUSPENSION,
            "This suspension is lifted automatically when the dependency becomes valid (LC-6).",
            "يرفع هذا الإيقاف تلقائياً عند تصحيح المتطلب المرتبط.",
        )
    text = common.reason_text(body.reason_text)
    at = now()
    for sp in manual:
        sp.lifted_at = at
        sp.lifted_by_user_id = p.user.id
    db.flush()
    if not lifecycle.open_suspensions(db, o):
        lifecycle.set_active(o)
        lifecycle.event(db, o, CredentialAction.reinstated, body.reason_code, text, p.user.id, at)
        status_changed(db, s, "reinstated", "أعيد التفعيل")
    after_change(db, s)
    _audit(db, p, s, "reinstated", {"reason_code": body.reason_code.value})
    return state(db, p, s)


def revoke(
    db: Session, p: Principal, kind: CredentialKind, cid: uuid.UUID, body: RevokeRequest
) -> CredentialState:
    s = _load(db, p, kind, cid)
    cap = C.worker_edit if kind == CredentialKind.access_card else _confirm_cap(kind)
    _require(p, s, cap)
    if body.reason_code in DEPENDENCY_REASONS:
        raise validation_error("reason_code", "Dependency reasons are applied by the system only.")
    if not _live(s):
        raise _terminal()
    text = common.reason_text(body.reason_text)
    lifecycle.revoke(db, s.obj, body.reason_code, text, p.user.id)
    status_changed(db, s, "revoked", "تم السحب")
    after_change(db, s)
    _audit(db, p, s, "revoked", {"reason_code": body.reason_code.value})
    return state(db, p, s)


def _custody_obj(s: Subject) -> AirportPass | Adp | Avp | None:
    return s.obj if isinstance(s.obj, AirportPass | Adp | Avp) else None


def record_return(
    db: Session, p: Principal, kind: CredentialKind, cid: uuid.UUID, body: ReturnRequest
) -> CredentialState:
    s = _load(db, p, kind, cid)
    _require(p, s, C.credential_custody)
    at = body.returned_at or now()
    if at > now():
        raise validation_error("returned_at", "returned_at cannot be in the future (LC-11).")
    o = _custody_obj(s)
    if o is None:
        if s.kind != CredentialKind.access_card:
            raise validation_error("kind", "Induction records have no physical custody.")
        lifecycle.event(
            db, s.obj, CredentialAction.returned, CredentialReason.other, body.notes, p.user.id, at
        )
        _audit(db, p, s, "returned", {})
        return state(db, p, s)
    if o.custody_status != CustodyStatus.return_due:
        raise ApiError(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Only credentials marked Return Due can be returned.",
            "يمكن تسجيل الإرجاع فقط للتصاريح المستحقة الإرجاع.",
        )
    o.custody_status = CustodyStatus.returned
    o.returned_at = at
    o.received_by_user_id = p.user.id
    late = o.return_due_on is not None and common.local_day(at) > o.return_due_on
    lifecycle.event(
        db,
        o,
        CredentialAction.returned,
        o.revoked_reason or CredentialReason.other,
        body.notes,
        p.user.id,
        at,
    )
    db.flush()
    _audit(db, p, s, "returned", {"late": late})
    return state(db, p, s)


def report_loss(
    db: Session, p: Principal, kind: CredentialKind, cid: uuid.UUID, body: LossReportRequest
) -> CredentialState:
    """LC-12."""
    s = _load(db, p, kind, cid)
    _require(p, s, C.credential_custody)
    at = body.lost_reported_at or now()
    text = common.reason_text(body.reason_text)
    if s.kind == CredentialKind.induction:
        raise validation_error("kind", "Induction records have no physical card.")
    if isinstance(s.obj, Deployment):
        d = s.obj
        if d.status != DeploymentStatus.mobilised:
            raise _terminal()
        common.end_qr(db, d.id, QrTokenStatus.rotated, lost=True)
        common.issue_qr(db, QrKind.AC, d.project_id, d.id, workers.printed_ref(db, d))
        d.reissue_count += 1
        d.access_card_issued_on = today()
        lifecycle.event(
            db, d, CredentialAction.lost_reported, body.reason_code, text, p.user.id, at
        )
        lifecycle.event(
            db, d, CredentialAction.token_rotated, body.reason_code, text, p.user.id, at
        )
        db.flush()
        _audit(db, p, s, "lost_reported", {})
        return state(db, p, s)
    o = _custody_obj(s)
    assert o is not None  # noqa: S101
    if o.custody_status not in (CustodyStatus.held, CustodyStatus.return_due):
        raise _terminal()
    if o.validity_status in (ValidityStatus.active, ValidityStatus.suspended):
        lifecycle.revoke(db, o, body.reason_code, text, p.user.id)
    o.custody_status = CustodyStatus.lost
    o.return_due_on = None
    o.lost_reported_at = at
    o.authority_notified_at = body.authority_notified_at
    if isinstance(o, Avp):
        common.end_qr(db, o.id, QrTokenStatus.revoked, lost=True)
    lifecycle.event(db, o, CredentialAction.lost_reported, body.reason_code, text, p.user.id, at)
    notify.notify(
        db,
        holder_audience(db, s),
        NotificationKind.credential_lost,
        f"{s.number} reported lost",
        f"تم الإبلاغ عن فقد {s.number}",
        "Inform the pass office within the reporting deadline.",
        "يرجى إبلاغ مكتب التصاريح خلال المهلة المحددة.",
        ENTITY[s.kind],
        o.id,
        s.project_id,
    )
    after_change(db, s)
    _audit(db, p, s, "lost_reported", {"reason_code": body.reason_code.value})
    return state(db, p, s)


def authority_notified(
    db: Session,
    p: Principal,
    kind: CredentialKind,
    cid: uuid.UUID,
    body: AuthorityNotifiedRequest,
) -> CredentialState:
    s = _load(db, p, kind, cid)
    _require(p, s, C.credential_custody)
    o = _custody_obj(s)
    if o is None or o.custody_status != CustodyStatus.lost:
        raise ApiError(
            409,
            ErrorCode.INVALID_TRANSITION,
            "Only lost credentials need an authority notification.",
            "يلزم الإبلاغ فقط للتصاريح المفقودة.",
        )
    if body.authority_notified_at > now() or (
        o.lost_reported_at and body.authority_notified_at < o.lost_reported_at - timedelta(days=7)
    ):
        raise validation_error("authority_notified_at", "Not a plausible notification time.")
    o.authority_notified_at = body.authority_notified_at
    db.flush()
    _audit(db, p, s, "authority_notified", {})
    return state(db, p, s)


def validity_block(
    db: Session, o: AirportPass | Adp | Avp, refs: Refs | None = None
) -> ValidityBlock:
    refs = refs or Refs(db)
    day = today()
    return ValidityBlock(
        validity_status=o.validity_status,
        effective_valid_until=o.effective_valid_until,
        limiting_factor=o.limiting_factor,
        days_left=common.days_left(o.effective_valid_until, day),
        custody_status=o.custody_status,
        return_due_on=o.return_due_on,
        return_overdue=bool(
            o.custody_status == CustodyStatus.return_due
            and o.return_due_on is not None
            and day > o.return_due_on
        ),
        returned_at=o.returned_at,
        received_by=refs.user(o.received_by_user_id),
        lost_reported_at=o.lost_reported_at,
        authority_notified_at=o.authority_notified_at,
        open_suspensions=[suspension_read(x, refs) for x in lifecycle.open_suspensions(db, o)],
    )
