"""Credential lifecycle engine (spec 2-access-permits §3.18, §4.3, §4.5, §4.9, §5.9, §6.2):
status events, suspensions (raised / confirmed / system), revocation, expiry, custody and the
strictest-wins effective validity with automatic dependency suspensions (LC-6)."""

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.access_enums import (
    DEPENDENCY_REASONS,
    BackgroundCheckStatus,
    CredentialAction,
    CredentialKind,
    CredentialReason,
    CustodyStatus,
    InductionStatus,
    LimitingFactor,
    QrTokenStatus,
    SuspensionState,
    ValidityStatus,
)
from app.core.clock import now, today
from app.models import (
    AccessSettings,
    Adp,
    AirportPass,
    Avp,
    CredentialEvent,
    CredentialSuspension,
    Deployment,
    InductionRecord,
    PassApplication,
    PassCategory,
    Project,
    ProjectEngagement,
    Vehicle,
    Wap,
    Worker,
)
from app.services.access import common

Cred = InductionRecord | AirportPass | Adp | Avp | Deployment | Wap

KIND_MODEL: dict[CredentialKind, type[Any]] = {
    CredentialKind.induction: InductionRecord,
    CredentialKind.airport_pass: AirportPass,
    CredentialKind.adp: Adp,
    CredentialKind.avp: Avp,
    CredentialKind.access_card: Deployment,
    CredentialKind.wap: Wap,
}

LF = LimitingFactor
DOC_FACTORS = {LF.istimara_expiry, LF.insurance_expiry, LF.mvpi_expiry}
TERMINAL_VALIDITY = {ValidityStatus.revoked, ValidityStatus.expired, ValidityStatus.withdrawn}


def kind_of(obj: Cred) -> CredentialKind:
    for k, m in KIND_MODEL.items():
        if isinstance(obj, m):
            return k
    raise TypeError(type(obj))


# ---- events and suspensions ----------------------------------------------------------------------


def event(
    db: Session,
    obj: Cred,
    action: CredentialAction,
    reason: CredentialReason,
    text: str | None = None,
    actor: uuid.UUID | None = None,
    at: datetime | None = None,
    expires_at: datetime | None = None,
) -> CredentialEvent:
    ev = CredentialEvent(
        id=uuid.uuid4(),
        project_id=obj.project_id,
        credential_kind=kind_of(obj),
        credential_id=obj.id,
        action=action,
        reason_code=reason,
        reason_text=text,
        actor_user_id=actor,
        occurred_at=at or now(),
        expires_at=expires_at,
        seed_fake=bool(getattr(obj, "seed_fake", False)),
    )
    db.add(ev)
    if not ev.seed_fake:
        from app.services.ptw import hooks  # noqa: PLC0415 (Phase 3 PT-8)

        hooks.mark_workers(db, [getattr(obj, "worker_id", None)])
    return ev


def open_suspensions(db: Session, obj: Cred) -> list[CredentialSuspension]:
    return list(
        db.scalars(
            select(CredentialSuspension)
            .where(
                CredentialSuspension.credential_kind == kind_of(obj),
                CredentialSuspension.credential_id == obj.id,
                CredentialSuspension.lifted_at.is_(None),
            )
            .order_by(CredentialSuspension.raised_at)
        )
    )


def _is_active(obj: Cred) -> bool:
    if isinstance(obj, InductionRecord):
        return obj.status == InductionStatus.valid
    if isinstance(obj, AirportPass | Adp | Avp):
        return obj.validity_status == ValidityStatus.active
    return True


def _is_live(obj: Cred) -> bool:
    """Not terminal (a suspension may be added / lifted)."""
    if isinstance(obj, InductionRecord):
        return obj.status in (InductionStatus.valid, InductionStatus.suspended)
    if isinstance(obj, AirportPass | Adp | Avp):
        return obj.validity_status in (ValidityStatus.active, ValidityStatus.suspended)
    return True


def _set_suspended(obj: Cred) -> None:
    if isinstance(obj, InductionRecord):
        obj.status = InductionStatus.suspended
        obj.status_changed_at = now()
    elif isinstance(obj, AirportPass | Adp | Avp):
        obj.validity_status = ValidityStatus.suspended


def set_active(obj: Cred) -> None:
    if isinstance(obj, InductionRecord):
        obj.status = InductionStatus.valid
        obj.status_changed_at = now()
    elif isinstance(obj, AirportPass | Adp | Avp):
        obj.validity_status = ValidityStatus.active


def suspend(
    db: Session,
    obj: Cred,
    state: SuspensionState,
    reason: CredentialReason,
    text: str | None,
    actor: uuid.UUID | None,
    *,
    at: datetime | None = None,
    expires_at: datetime | None = None,
    suspension_end: date | None = None,
) -> CredentialSuspension:
    at = at or now()
    s = CredentialSuspension(
        id=uuid.uuid4(),
        project_id=obj.project_id,
        credential_kind=kind_of(obj),
        credential_id=obj.id,
        state=state,
        reason_code=reason,
        reason_text=text,
        raised_by_user_id=actor,
        raised_at=at,
        expires_at=expires_at,
        suspension_end=suspension_end,
        confirmed_by_user_id=actor if state == SuspensionState.confirmed else None,
        confirmed_at=at if state == SuspensionState.confirmed else None,
        alerts_sent=[],
        seed_fake=bool(getattr(obj, "seed_fake", False)),
    )
    db.add(s)
    action = {
        SuspensionState.raised: CredentialAction.suspend_raised,
        SuspensionState.confirmed: CredentialAction.suspend_confirmed,
        SuspensionState.system: CredentialAction.auto_suspended,
    }[state]
    event(db, obj, action, reason, text, actor, at, expires_at)
    _set_suspended(obj)
    db.flush()
    return s


def lift(
    db: Session,
    obj: Cred,
    s: CredentialSuspension,
    actor: uuid.UUID | None,
    text: str | None = None,
    *,
    reason: CredentialReason | None = None,
    at: datetime | None = None,
) -> bool:
    """Close a suspension; the credential is reinstated when none remains open (LC-6).
    Returns True when the credential became active again."""
    at = at or now()
    s.lifted_at = at
    s.lifted_by_user_id = actor
    db.flush()
    if open_suspensions(db, obj) or not _is_live(obj):
        return False
    set_active(obj)
    action = CredentialAction.reinstated if actor else CredentialAction.auto_reinstated
    event(db, obj, action, reason or s.reason_code, text, actor, at)
    db.flush()
    return True


def system_suspend(
    db: Session, obj: Cred, reason: CredentialReason, text: str | None = None, **kw: Any
) -> CredentialSuspension | None:
    """Idempotent: one open system suspension per reason."""
    if not _is_live(obj):
        return None
    for s in open_suspensions(db, obj):
        if s.state == SuspensionState.system and s.reason_code == reason:
            return None
    return suspend(db, obj, SuspensionState.system, reason, text, None, **kw)


def system_lift(db: Session, obj: Cred, reasons: set[CredentialReason]) -> bool:
    lifted = False
    for s in open_suspensions(db, obj):
        if s.state == SuspensionState.system and s.reason_code in reasons:
            lifted = lift(db, obj, s, None) or lifted
    return lifted


def close_all(db: Session, obj: Cred, actor: uuid.UUID | None, at: datetime) -> None:
    for s in open_suspensions(db, obj):
        s.lifted_at = at
        s.lifted_by_user_id = actor


def return_due(db: Session, obj: AirportPass | Adp | Avp, trigger: date, s: AccessSettings) -> None:
    """§4.9 Held → Return Due (return_due_on = trigger + pass_return_days)."""
    if obj.custody_status == CustodyStatus.held:
        obj.custody_status = CustodyStatus.return_due
        obj.return_due_on = trigger + timedelta(days=s.pass_return_days)
        event(db, obj, CredentialAction.return_due, obj.revoked_reason or CredentialReason.other)


def revoke(
    db: Session,
    obj: Cred,
    reason: CredentialReason,
    text: str | None,
    actor: uuid.UUID | None,
    s: AccessSettings | None = None,
    at: datetime | None = None,
) -> bool:
    at = at or now()
    if isinstance(obj, InductionRecord):
        if obj.status not in (InductionStatus.valid, InductionStatus.suspended):
            return False
        close_all(db, obj, actor, at)
        obj.status = InductionStatus.revoked
        obj.status_changed_at = at
        event(db, obj, CredentialAction.revoked, reason, text, actor, at)
        return True
    if isinstance(obj, AirportPass | Adp | Avp):
        if obj.validity_status in TERMINAL_VALIDITY:
            return False
        close_all(db, obj, actor, at)
        was_pending = obj.validity_status == ValidityStatus.pending
        obj.validity_status = ValidityStatus.withdrawn if was_pending else ValidityStatus.revoked
        obj.revoked_at = at
        obj.revoked_reason = reason
        event(db, obj, CredentialAction.revoked, reason, text, actor, at)
        if not was_pending:
            return_due(db, obj, common.local_day(at), s or common.settings(db, obj.project_id))
        if isinstance(obj, Avp):
            common.end_qr(db, obj.id, QrTokenStatus.revoked)
        return True
    if isinstance(obj, Deployment):
        common.end_qr(db, obj.id, QrTokenStatus.revoked)
        event(db, obj, CredentialAction.revoked, reason, text, actor, at)
        return True
    return False


def expire(db: Session, obj: AirportPass | Adp | Avp, day: date, s: AccessSettings) -> None:
    if obj.validity_status not in (ValidityStatus.active, ValidityStatus.suspended):
        return
    close_all(db, obj, None, now())
    obj.validity_status = ValidityStatus.expired
    obj.expired_on = day
    event(db, obj, CredentialAction.expired, CredentialReason.other, None, None)
    return_due(db, obj, day, s)


# ---- effective validity (§6.2) -------------------------------------------------------------------


@dataclass
class Eff:
    eff: date | None
    limiting: LimitingFactor | None
    terms: dict[LimitingFactor, date | None]


def strictest(terms: dict[LimitingFactor, date | None]) -> Eff:
    best: tuple[date, LimitingFactor] | None = None
    for k, v in terms.items():  # insertion order breaks ties (own/card first)
        if v is not None and (best is None or v < best[0]):
            best = (v, k)
    return Eff(best[0] if best else None, best[1] if best else None, terms)


def background(app: PassApplication | None) -> dict[str, Any]:
    if app is None or app.background_enc is None:
        return {}
    data: dict[str, Any] = json.loads(crypto.decrypt(app.background_enc))
    return data


def set_background(app: PassApplication, data: dict[str, Any]) -> None:
    app.background_enc = crypto.encrypt(json.dumps(data, default=str))


def pass_eff(db: Session, ps: AirportPass) -> Eff:
    w = db.get(Worker, ps.worker_id)
    dep = db.get(Deployment, ps.deployment_id)
    eng = db.get(ProjectEngagement, ps.engagement_id) if ps.engagement_id else None
    project = db.get(Project, ps.project_id)
    cat = db.scalar(
        select(PassCategory).where(
            PassCategory.project_id == ps.project_id, PassCategory.code == ps.pass_category
        )
    )
    recheck = None
    if not ps.escorted and (cat is None or cat.background_check_required):
        bg = background(db.get(PassApplication, ps.application_id))
        if bg.get("recheck_due"):
            recheck = date.fromisoformat(str(bg["recheck_due"]))
    return strictest(
        {
            LF.card_expiry_date: ps.card_expiry_date,
            LF.worker_id_expiry_date: w.id_expiry_date if w else None,
            LF.deployment_planned_demob_on: dep.planned_demob_on if dep else None,
            LF.engagement_demobilisation_date: eng.demobilisation_date if eng else None,
            LF.project_planned_end_date: project.planned_end_date if project else None,
            LF.background_recheck_due: recheck,
        }
    )


def adp_eff(db: Session, a: Adp) -> Eff:
    ps = db.get(AirportPass, a.pass_id) if a.pass_id else None
    pe = pass_eff(db, ps) if ps else None
    return strictest(
        {
            LF.own_valid_until: a.own_valid_until,
            LF.pass_effective_valid_until: pe.eff if pe else None,
            LF.licence_expiry_date: a.licence_expiry_date,
        }
    )


def avp_eff(db: Session, a: Avp, hook_until: date | None = None) -> Eff:
    v = db.get(Vehicle, a.vehicle_id)
    assert v is not None  # noqa: S101
    terms = {
        LF.own_valid_until: a.own_valid_until,
        LF.istimara_expiry: v.istimara_expiry,
        LF.insurance_expiry: v.insurance_expiry,
        LF.mvpi_expiry: v.mvpi_expiry,
    }
    if hook_until is not None:
        terms[LF.equipment_certificate] = hook_until
    return strictest(terms)


def _reason_for(lf: LimitingFactor | None) -> CredentialReason:
    if lf == LF.worker_id_expiry_date:
        return CredentialReason.id_expired
    if lf == LF.licence_expiry_date:
        return CredentialReason.licence_expired
    if lf in DOC_FACTORS or lf == LF.equipment_certificate:
        return CredentialReason.vehicle_document_expired
    return CredentialReason.dependency_invalid


def _failing(e: Eff, day: date, own: LimitingFactor) -> tuple[bool, set[CredentialReason]]:
    """(own date passed, dependency reasons currently failing)."""
    expired_own = e.terms.get(own) is not None and day > e.terms[own]  # type: ignore[operator]
    failing = {_reason_for(k) for k, v in e.terms.items() if k != own and v is not None and day > v}
    return expired_own, failing


def _apply(
    db: Session,
    obj: AirportPass | Adp | Avp,
    e: Eff,
    day: date,
    own: LimitingFactor,
    extra_failing: set[CredentialReason],
    s: AccessSettings,
) -> None:
    obj.effective_valid_until = e.eff
    obj.limiting_factor = e.limiting
    if obj.validity_status not in (ValidityStatus.active, ValidityStatus.suspended):
        return
    expired_own, failing = _failing(e, day, own)
    failing |= extra_failing
    if expired_own:
        expire(db, obj, day, s)
        return
    for r in failing:
        system_suspend(db, obj, r)
    stale = {
        sp.reason_code
        for sp in open_suspensions(db, obj)
        if sp.state == SuspensionState.system
        and sp.reason_code in DEPENDENCY_REASONS
        and sp.reason_code not in failing
    }
    if stale:
        system_lift(db, obj, stale)


def evaluate_pass(db: Session, ps: AirportPass, day: date | None = None) -> None:
    day = day or today()
    s = common.settings(db, ps.project_id)
    extra: set[CredentialReason] = set()
    w = db.get(Worker, ps.worker_id)
    e = pass_eff(db, ps)
    if w is not None and not s.id_expiry_blocks_access:
        e.terms[LF.worker_id_expiry_date] = None
        e = strictest(e.terms)
    _apply(db, ps, e, day, LF.card_expiry_date, extra, s)
    if e.limiting == LF.background_recheck_due and e.eff is not None and day > e.eff:
        app = db.get(PassApplication, ps.application_id)
        bg = background(app)
        if app is not None and bg.get("status") == BackgroundCheckStatus.cleared.value:
            bg["status"] = BackgroundCheckStatus.expired.value
            set_background(app, bg)
    for a in db.scalars(select(Adp).where(Adp.pass_id == ps.id)):
        evaluate_adp(db, a, day)


def evaluate_adp(db: Session, a: Adp, day: date | None = None) -> None:
    day = day or today()
    s = common.settings(db, a.project_id)
    extra: set[CredentialReason] = set()
    ps = db.get(AirportPass, a.pass_id) if a.pass_id else None
    if ps is None or ps.validity_status != ValidityStatus.active:
        extra.add(CredentialReason.dependency_invalid)  # DP-7 pass suspended/expired/revoked
    _apply(db, a, adp_eff(db, a), day, LF.own_valid_until, extra, s)


def evaluate_avp(db: Session, a: Avp, day: date | None = None) -> None:
    day = day or today()
    _apply(db, a, avp_eff(db, a), day, LF.own_valid_until, set(), common.settings(db, a.project_id))


def refresh_worker(db: Session, worker_id: uuid.UUID, day: date | None = None) -> None:
    """Recompute every pass / ADP of the worker after a dependency changed (LC-2)."""
    for ps in db.scalars(select(AirportPass).where(AirportPass.worker_id == worker_id)):
        evaluate_pass(db, ps, day)
    for a in db.scalars(select(Adp).where(Adp.worker_id == worker_id, Adp.pass_id.is_(None))):
        evaluate_adp(db, a, day)


def refresh_vehicle(db: Session, vehicle_id: uuid.UUID, day: date | None = None) -> None:
    for a in db.scalars(select(Avp).where(Avp.vehicle_id == vehicle_id)):
        evaluate_avp(db, a, day)


# ---- reads ---------------------------------------------------------------------------------------


def live_valid(obj: AirportPass | Adp | Avp, day: date) -> bool:
    """LC-13: validity evaluated live (status active and today ≤ effective date)."""
    return (
        obj.validity_status == ValidityStatus.active
        and obj.effective_valid_until is not None
        and day <= obj.effective_valid_until
    )


def induction_valid_until(r: InductionRecord) -> date | None:
    """valid_until capped by an IN-9 re-induction date (expires on that date)."""
    if r.valid_until is None:
        return None
    if r.reinduction_due_on is not None:
        return min(r.valid_until, r.reinduction_due_on - timedelta(days=1))
    return r.valid_until
