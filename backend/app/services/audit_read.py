"""Reading the audit log and change history (spec §5.6 rules 38-39, capability 16/17)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, false, not_, or_, select
from sqlalchemy.orm import Session

import app.services.corrective_actions as ca_svc
import app.services.incidents as inc_svc
import app.services.injury_cases as case_svc
import app.services.inspections as ins_svc
import app.services.meetings as meet_svc
import app.services.observations as obs_svc
import app.services.workforce as wf_svc
from app.core.enums import (
    AUTH_ACTIONS,
    AuditAction,
    AuditResult,
    Capability,
    EntityType,
    NotificationKind,
)
from app.core.errors import not_found
from app.models import AuditEntry, RoleAssignment, User
from app.schemas.audit import AuditChainVerification, AuditEntryRead, ChangeHistoryEntry
from app.services import audit, contractors, notify, org, projects, users
from app.services.permissions import Principal, forbidden_error

CHANGE_ACTIONS = (
    AuditAction.create,
    AuditAction.update,
    AuditAction.status_change,
    AuditAction.archive,
    AuditAction.settings_changed,
    AuditAction.user_invited,
    AuditAction.user_status_changed,
    AuditAction.role_assigned,
    AuditAction.role_revoked,
)


def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    clean = {i for i in ids if i}
    if not clean:
        return {}
    return dict(db.execute(select(User.id, User.full_name_en).where(User.id.in_(clean))).all())


def audit_query(
    db: Session,
    p: Principal,
    *,
    project_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actions: list[AuditAction] | None = None,
    entity_type: EntityType | None = None,
    entity_id: uuid.UUID | None = None,
    result: AuditResult | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
) -> Select[AuditEntry]:
    grants = p.project_grants(Capability.audit_log_read)
    if grants is not None and not grants:
        raise forbidden_error()
    stmt = select(AuditEntry)
    if grants is not None:  # HSE Officer: own projects, no auth events of other users
        stmt = stmt.where(
            AuditEntry.project_id.in_(list(grants)) if grants else false(),
            or_(
                not_(AuditEntry.action.in_(list(AUTH_ACTIONS))),
                AuditEntry.actor_user_id == p.user.id,
            ),
        )
    if project_id:
        stmt = stmt.where(AuditEntry.project_id == project_id)
    if actor_user_id:
        stmt = stmt.where(AuditEntry.actor_user_id == actor_user_id)
    if actions:
        stmt = stmt.where(AuditEntry.action.in_(actions))
    if entity_type:
        stmt = stmt.where(AuditEntry.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditEntry.entity_id == entity_id)
    if result:
        stmt = stmt.where(AuditEntry.result == result)
    if occurred_from:
        stmt = stmt.where(AuditEntry.occurred_at >= occurred_from)
    if occurred_to:
        stmt = stmt.where(AuditEntry.occurred_at < occurred_to)
    return stmt.order_by(AuditEntry.seq.desc())


def entry_reads(db: Session, p: Principal, entries: list[AuditEntry]) -> list[AuditEntryRead]:
    names = _names(db, {e.actor_user_id for e in entries})
    out = []
    for e in entries:
        data: dict[str, Any] = {
            "id": e.id,
            "seq": e.seq,
            "occurred_at": e.occurred_at,
            "actor_user_id": e.actor_user_id,
            "actor_name": names.get(e.actor_user_id) if e.actor_user_id else None,
            "actor_role": e.actor_role,
            "on_behalf_project_id": e.on_behalf_project_id,
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "project_id": e.project_id,
            "before": e.before,
            "after": e.after,
            "fields_read": e.fields_read,
            "details": e.details,
            "result": e.result,
            "request_id": e.request_id,
        }
        if p.is_manager:
            data.update(
                ip_address=e.ip_address, user_agent=e.user_agent, prev_hash=e.prev_hash, hash=e.hash
            )
        out.append(AuditEntryRead(**data))
    return out


def log_viewed(db: Session, p: Principal, filters: dict[str, Any], count: int) -> None:
    audit.record(
        db,
        AuditAction.audit_log_viewed,
        p.actor(filters.get("project_id")),
        entity_type=EntityType.audit_log,
        project_id=filters.get("project_id"),
        details={"filters": {k: v for k, v in filters.items() if v is not None}, "rows": count},
    )


def verify(db: Session, p: Principal) -> AuditChainVerification:
    p.require(None, Capability.audit_log_read)
    res = audit.verify_chain(db)
    entry = audit.record(
        db,
        AuditAction.audit_chain_verified,
        p.actor(),
        entity_type=EntityType.audit_log,
        result=AuditResult.success if res.ok else AuditResult.failed,
        details={
            "ok": res.ok,
            "checked": res.checked_count,
            "first_break_seq": res.first_break_seq,
        },
    )
    if not res.ok:
        notify.notify(
            db,
            notify.managers(db),
            NotificationKind.audit_chain_break,
            f"Audit chain break at entry #{res.first_break_seq}",
            f"خلل في سلسلة سجل التدقيق عند القيد #{res.first_break_seq}",
            entity_type=EntityType.audit_log,
        )
    assert entry is not None  # noqa: S101
    return AuditChainVerification(
        ok=res.ok,
        checked_count=res.checked_count,
        first_break_seq=res.first_break_seq,
        first_break_entry_id=res.first_break_entry_id,
        verified_at=entry.occurred_at,
    )


def _history_allowed(
    db: Session, p: Principal, entity_type: EntityType, entity_id: uuid.UUID
) -> None:
    """Rule 38 / capability 17: only records the caller can already see."""
    cap = Capability.history_view
    if entity_type == EntityType.project:
        projects.get_visible(db, p, entity_id)
        ok = p.grant(entity_id, cap) is not None
    elif entity_type == EntityType.project_settings:
        projects.get_settings_for(db, p, entity_id)
        ok = p.grant(entity_id, cap) is not None
    elif entity_type == EntityType.site:
        site = org.get_site(db, p, entity_id)
        g = p.grant(site.project_id, cap)
        ok = g is not None and g.covers_site(site.id)
    elif entity_type == EntityType.zone:
        zone = org.get_zone(db, p, entity_id)
        g = p.grant(zone.project_id, cap)
        ok = g is not None and g.covers_site(zone.site_id)
    elif entity_type == EntityType.contractor:
        contractors.get_visible(db, p, entity_id)
        ok = p.has_any(cap)
    elif entity_type == EntityType.project_engagement:
        e = contractors.get_engagement(db, p, entity_id)
        g = p.grant(e.project_id, cap)
        ok = g is not None and g.covers_engagement(e.id)
    elif entity_type == EntityType.user:
        users.get_visible_user(db, p, entity_id)
        ok = p.has_any(cap)
    elif entity_type == EntityType.role_assignment:
        a = db.get(RoleAssignment, entity_id)
        if a is None:
            raise not_found("Role assignment")
        users.get_visible_user(db, p, a.user_id)
        ok = p.has_any(cap)
    else:
        pid = _phase1_project(db, p, entity_type, entity_id)
        ok = p.grant(pid, cap) is not None
    if not ok:
        raise forbidden_error()


def _phase1_project(
    db: Session, p: Principal, entity_type: EntityType, entity_id: uuid.UUID
) -> uuid.UUID:
    """Phase 1 records: visible through their own service (404 otherwise); injured-person
    history needs identity and medical access (capabilities 29 and 30)."""
    et = EntityType
    if entity_type in (et.incident, et.investigation):
        return inc_svc.get_incident(db, p, entity_id).project_id
    if entity_type == et.injury_case:
        case, _ = case_svc._load(db, p, entity_id)
        if not (
            p.grant(case.project_id, Capability.injury_identity_view)
            and p.grant(case.project_id, Capability.injury_medical_view)
        ):
            raise forbidden_error("Injured-person history needs capabilities 29 and 30.")
        return case.project_id
    if entity_type == et.corrective_action:
        return ca_svc.get_ca(db, p, entity_id).project_id
    if entity_type == et.observation:
        return obs_svc.get_obs(db, p, entity_id).project_id
    if entity_type == et.inspection:
        return ins_svc.get_ins(db, p, entity_id).project_id
    if entity_type == et.inspection_plan:
        return ins_svc.get_plan(db, p, entity_id).project_id
    if entity_type == et.hse_meeting:
        return meet_svc._get(db, p, entity_id).project_id
    if entity_type == et.workforce_return:
        return wf_svc.get_row(db, p, entity_id).project_id
    raise not_found("History")


def history_query(
    db: Session, p: Principal, entity_type: EntityType, entity_id: uuid.UUID
) -> Select[AuditEntry]:
    _history_allowed(db, p, entity_type, entity_id)
    return (
        select(AuditEntry)
        .where(
            and_(
                AuditEntry.entity_type == entity_type,
                AuditEntry.entity_id == entity_id,
                AuditEntry.action.in_(CHANGE_ACTIONS),
            )
        )
        .order_by(AuditEntry.seq.desc())
    )


def history_reads(db: Session, entries: list[AuditEntry]) -> list[ChangeHistoryEntry]:
    names = _names(db, {e.actor_user_id for e in entries})
    return [
        ChangeHistoryEntry(
            id=e.id,
            occurred_at=e.occurred_at,
            actor_user_id=e.actor_user_id,
            actor_name=names.get(e.actor_user_id) if e.actor_user_id else None,
            action=e.action,
            before=e.before,
            after=e.after,
        )
        for e in entries
    ]
