"""Users, invitations and role assignments (spec §3.6, §3.7, §4.3, §5.2 rules 13-16, 29)."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import Select, and_, exists, false, or_, select, true
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.enums import (
    AuditAction,
    Capability,
    ContractorStatus,
    EmployerType,
    EntityType,
    Language,
    Role,
    UserStatus,
)
from app.core.errors import ApiError, ErrorCode, validation_error
from app.core.text import like_pattern, search_blob
from app.models import Contractor, Project, ProjectEngagement, RoleAssignment, Site, User
from app.models.users import TokenKind
from app.schemas.auth import RoleAssignmentRead
from app.schemas.users import (
    RoleAssignmentCreate,
    RoleAssignmentUpdate,
    UserInvite,
    UserRead,
    UserTransitionRequest,
    UserUpdate,
)
from app.services import audit, auth
from app.services.common import duplicate, invalid_transition, paginate, require_reason
from app.services.permissions import (
    CONTRACTOR_ROLES,
    OFFICER_ASSIGNABLE,
    Grant,
    Principal,
    deny,
    forbidden_error,
)

PUBLIC_FIELDS = (
    "email",
    "full_name_en",
    "full_name_ar",
    "mobile",
    "employer_type",
    "employer_contractor_id",
    "job_title",
    "preferred_language",
)


def assignment_read(a: RoleAssignment, day: date) -> RoleAssignmentRead:
    return RoleAssignmentRead(
        id=a.id,
        user_id=a.user_id,
        role=a.role,
        project_id=a.project_id,
        site_ids=list(a.site_ids or []),
        contractor_engagement_id=a.contractor_engagement_id,
        valid_from=a.valid_from,
        valid_to=a.valid_to,
        is_active=a.is_active_on(day),
        revoked_at=a.revoked_at,
        created_at=a.created_at,
        created_by_user_id=a.created_by_user_id,
    )


def _assignment_dict(a: RoleAssignment) -> dict[str, Any]:
    return {
        "user_id": a.user_id,
        "role": a.role,
        "project_id": a.project_id,
        "site_ids": sorted(str(s) for s in a.site_ids or []),
        "contractor_engagement_id": a.contractor_engagement_id,
        "valid_from": a.valid_from,
        "valid_to": a.valid_to,
    }


def _user_dict(u: User) -> dict[str, Any]:
    return {f: getattr(u, f) for f in PUBLIC_FIELDS}


# ---- visibility ------------------------------------------------------------------------
def _engagement_contractors(db: Session, ids: frozenset[uuid.UUID]) -> set[uuid.UUID]:
    if not ids:
        return set()
    return set(
        db.scalars(
            select(ProjectEngagement.contractor_id).where(ProjectEngagement.id.in_(ids))
        ).all()
    )


def _scope_condition(db: Session, p: Principal, cap: Capability) -> Any:
    """SQL condition on User for users visible under ``cap`` (rule 9-11, matrix rows 11/12)."""
    grants = p.project_grants(cap)
    if grants is None:
        return true()
    conds: list[Any] = [User.id == p.user.id]
    for pid, g in grants.items():
        on_project = exists().where(
            RoleAssignment.user_id == User.id, RoleAssignment.project_id == pid
        )
        if g.engagement_ids is None:
            conds.append(on_project)
        else:
            contractors = _engagement_contractors(db, g.engagement_ids)
            if contractors:
                conds.append(and_(on_project, User.employer_contractor_id.in_(contractors)))
    return or_(*conds) if conds else false()


def _can(db: Session, p: Principal, cap: Capability, target: User) -> bool:
    if p.is_manager or target.id == p.user.id:
        return True
    stmt = select(User.id).where(User.id == target.id, _scope_condition(db, p, cap))
    return db.scalar(stmt) is not None


def get_visible_user(db: Session, p: Principal, user_id: uuid.UUID) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise deny(db, p, EntityType.user, user_id, what="User")
    if not _can(db, p, Capability.user_view_directory, target):
        raise deny(db, p, EntityType.user, user_id, what="User")
    return target


def user_read(db: Session, p: Principal, u: User, contacts: bool | None = None) -> UserRead:
    if contacts is None:
        contacts = _can(db, p, Capability.user_view_contacts, u)
    visible = [
        a
        for a in u.assignments
        if p.is_manager
        or a.user_id == p.user.id
        or (a.project_id and p.can_see_project(a.project_id))
    ]
    pending = None
    if u.status == UserStatus.invited:
        from app.models import UserToken  # noqa: PLC0415

        pending = db.scalar(
            select(UserToken.expires_at)
            .where(
                UserToken.user_id == u.id,
                UserToken.kind == TokenKind.invite,
                UserToken.used_at.is_(None),
                UserToken.superseded_at.is_(None),
            )
            .order_by(UserToken.created_at.desc())
            .limit(1)
        )
    data: dict[str, Any] = {
        "id": u.id,
        "full_name_en": u.full_name_en,
        "full_name_ar": u.full_name_ar,
        "employer_type": u.employer_type,
        "employer_contractor_id": u.employer_contractor_id,
        "job_title": u.job_title,
        "preferred_language": u.preferred_language,
        "status": u.status,
        "status_reason": u.status_reason,
        "mfa_enabled": u.mfa_enabled,
        "last_login_at": u.last_login_at,
        "invite_expires_at": pending,
        "locked_until": u.locked_until,
        "privacy_notice_version": u.privacy_notice_version,
        "privacy_notice_ack_at": u.privacy_notice_ack_at,
        "created_at": u.created_at,
        "updated_at": u.updated_at,
        "role_assignments": [assignment_read(a, p.today) for a in visible],
    }
    if contacts:
        data["email"] = u.email
        data["mobile"] = u.mobile
    return UserRead(**data)


def list_query(
    db: Session,
    p: Principal,
    *,
    project_id: uuid.UUID | None = None,
    role: Role | None = None,
    statuses: list[UserStatus] | None = None,
    employer_type: EmployerType | None = None,
    employer_contractor_id: uuid.UUID | None = None,
    q: str | None = None,
    sort: str = "name",
    lang: Language = Language.en,
) -> Select[User]:
    if not p.has_any(Capability.user_view_directory):
        raise forbidden_error()
    stmt = select(User).where(_scope_condition(db, p, Capability.user_view_directory))
    if project_id:
        stmt = stmt.where(
            exists().where(
                RoleAssignment.user_id == User.id, RoleAssignment.project_id == project_id
            )
        )
    if role:
        cond = [RoleAssignment.user_id == User.id, RoleAssignment.role == role]
        cond.append(RoleAssignment.revoked_at.is_(None))
        if project_id:
            cond.append(RoleAssignment.project_id == project_id)
        stmt = stmt.where(exists().where(*cond))
    if statuses:
        stmt = stmt.where(User.status.in_(statuses))
    if employer_type:
        stmt = stmt.where(User.employer_type == employer_type)
    if employer_contractor_id:
        stmt = stmt.where(User.employer_contractor_id == employer_contractor_id)
    if q:
        stmt = stmt.where(User.search_text.like(like_pattern(q)))
    desc = sort.startswith("-")
    key = sort.lstrip("-")
    if key == "email":
        col: Any = User.email
    elif key == "last_login_at":
        col = User.last_login_at
    elif lang == Language.ar:
        col = User.full_name_ar.collate("ar-x-icu")
    else:
        col = User.full_name_en.collate("en-x-icu")
    stmt = stmt.order_by(col.desc().nulls_last() if desc else col.asc().nulls_last(), User.id)
    return stmt


def list_users(
    db: Session, p: Principal, page: int, page_size: int, **filters: Any
) -> tuple[list[UserRead], int]:
    stmt = list_query(db, p, **filters)
    items, total = paginate(db, stmt, page, page_size)
    return [user_read(db, p, u) for u in items], total


# ---- assignment validation -------------------------------------------------------------
def _role_not_assignable(role: Role) -> ApiError:
    return ApiError(
        403,
        ErrorCode.ROLE_NOT_ASSIGNABLE,
        f"You may not assign the role {role.value}.",
        "لا يمكنك إسناد هذا الدور.",
    )


def _self_forbidden() -> ApiError:
    return ApiError(
        403,
        ErrorCode.SELF_MODIFICATION_FORBIDDEN,
        "You cannot change your own roles or status.",
        "لا يمكنك تعديل أدوارك أو حالتك.",
    )


def _authorize_assignment(
    db: Session, p: Principal, role: Role, project_id: uuid.UUID | None
) -> Grant:
    p.ensure_writer()
    if role == Role.hse_manager:
        if not p.is_manager:
            raise _role_not_assignable(role)
        return p.require(None, Capability.user_invite)
    assert project_id is not None  # noqa: S101 (schema guarantees)
    project = db.get(Project, project_id)
    if project is None or not p.can_see_project(project_id):
        raise deny(db, p, EntityType.project, project_id, project_id, "Project")
    grant = p.require(project_id, Capability.user_invite)
    if not p.is_manager and role not in OFFICER_ASSIGNABLE:
        raise _role_not_assignable(role)
    return grant


def _validate_assignment(
    db: Session,
    user: User,
    role: Role,
    project_id: uuid.UUID | None,
    site_ids: list[uuid.UUID],
    engagement_id: uuid.UUID | None,
    valid_from: date,
    valid_to: date | None,
    others: list[RoleAssignment],
    exclude_id: uuid.UUID | None = None,
) -> None:
    if user.status == UserStatus.deactivated:
        raise validation_error("user_id", "Roles cannot be assigned to a deactivated user.")
    if valid_to and valid_to < valid_from:
        raise validation_error("valid_to", "valid_to must be on or after valid_from.")
    live = [
        a
        for a in others
        if a.revoked_at is None
        and a.id != exclude_id
        and a.project_id == project_id
        and (a.valid_to is None or a.valid_to >= valid_from)
        and (valid_to is None or a.valid_from <= valid_to)
    ]
    sod = {Role.permit_issuer: Role.permit_receiver, Role.permit_receiver: Role.permit_issuer}
    if role in sod and any(a.role == sod[role] for a in live):
        raise ApiError(
            409,
            ErrorCode.SOD_CONFLICT,
            "Permit Issuer and Permit Receiver cannot be held by the same user on one project.",
            "لا يمكن الجمع بين دور مُصدِر التصريح ومستلم التصريح لنفس المستخدم في المشروع.",
        )
    if site_ids:
        found = set(
            db.scalars(
                select(Site.id).where(Site.id.in_(site_ids), Site.project_id == project_id)
            ).all()
        )
        if found != set(site_ids):
            raise validation_error("site_ids", "All sites must belong to the project.")
    if role in CONTRACTOR_ROLES:
        eng = db.get(ProjectEngagement, engagement_id) if engagement_id else None
        if eng is None or eng.project_id != project_id:
            raise validation_error(
                "contractor_engagement_id", "The engagement must be on the same project."
            )
        if (
            user.employer_type != EmployerType.contractor
            or eng.contractor_id != user.employer_contractor_id
        ):
            raise validation_error(
                "contractor_engagement_id",
                "The engagement must be the user's employer on this project (rule 29).",
            )
    if any(a.role == role for a in live):
        raise duplicate("role", "The user already holds this role on this project.")


def _create_assignment(
    db: Session, p: Principal, user: User, body: RoleAssignmentCreate
) -> RoleAssignment:
    valid_from = body.valid_from or p.today
    _validate_assignment(
        db,
        user,
        body.role,
        body.project_id,
        body.site_ids,
        body.contractor_engagement_id,
        valid_from,
        body.valid_to,
        list(user.assignments),
    )
    a = RoleAssignment(
        id=uuid.uuid4(),
        user_id=user.id,
        role=body.role,
        project_id=body.project_id,
        site_ids=list(body.site_ids),
        contractor_engagement_id=body.contractor_engagement_id,
        valid_from=valid_from,
        valid_to=body.valid_to,
        created_by_user_id=p.user.id,
        created_at=now(),
    )
    db.add(a)
    user.assignments.append(a)
    db.flush()
    audit.record(
        db,
        AuditAction.role_assigned,
        p.actor(body.project_id),
        entity_type=EntityType.role_assignment,
        entity_id=a.id,
        project_id=body.project_id,
        after=_assignment_dict(a),
    )
    return a


# ---- last HSE manager (rule 13) --------------------------------------------------------
def _active_manager_ids(db: Session, day: date) -> set[uuid.UUID]:
    rows = db.scalars(
        select(RoleAssignment)
        .join(User, User.id == RoleAssignment.user_id)
        .where(RoleAssignment.role == Role.hse_manager, User.status == UserStatus.active)
    ).all()
    return {a.user_id for a in rows if a.is_active_on(day)}


def _ensure_not_last_manager(
    db: Session, day: date, user_id: uuid.UUID, removing_assignment: RoleAssignment | None = None
) -> None:
    managers = _active_manager_ids(db, day)
    if user_id not in managers:
        return
    if removing_assignment is not None:
        # The user may hold another active hse_manager assignment.
        others = [
            a
            for a in db.scalars(
                select(RoleAssignment).where(
                    RoleAssignment.user_id == user_id,
                    RoleAssignment.role == Role.hse_manager,
                    RoleAssignment.id != removing_assignment.id,
                )
            ).all()
            if a.is_active_on(day)
        ]
        if others:
            return
    if managers - {user_id}:
        return
    raise ApiError(
        409,
        ErrorCode.LAST_HSE_MANAGER,
        "There must always be at least one active HSE Manager.",
        "يجب أن يكون هناك مدير صحة وسلامة وبيئة نشط واحد على الأقل.",
    )


# ---- invite / update / transitions -----------------------------------------------------
def invite(db: Session, p: Principal, body: UserInvite) -> User:
    p.require_any(Capability.user_invite)
    for ra in body.role_assignments:
        _authorize_assignment(db, p, ra.role, ra.project_id)
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise duplicate("email", "A user with this email already exists.")
    if body.employer_contractor_id:
        c = db.get(Contractor, body.employer_contractor_id)
        if c is None:
            raise validation_error("employer_contractor_id", "Contractor not found.")
        if c.status == ContractorStatus.blacklisted:
            raise validation_error("employer_contractor_id", "The contractor is blacklisted.")
    lang = body.preferred_language
    if lang is None:
        first_project = next((ra.project_id for ra in body.role_assignments if ra.project_id), None)
        settings = db.get(Project, first_project).settings if first_project else None  # type: ignore[union-attr]
        lang = settings.default_language if settings else Language.en
    user = User(
        id=uuid.uuid4(),
        email=body.email,
        full_name_en=body.full_name_en,
        full_name_ar=body.full_name_ar,
        mobile=body.mobile,
        employer_type=body.employer_type,
        employer_contractor_id=body.employer_contractor_id,
        job_title=body.job_title,
        preferred_language=lang,
        status=UserStatus.invited,
        invited_by_user_id=p.user.id,
        invited_at=now(),
        search_text=search_blob(body.full_name_en, body.full_name_ar, body.email),
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        AuditAction.user_invited,
        p.actor(body.role_assignments[0].project_id),
        entity_type=EntityType.user,
        entity_id=user.id,
        project_id=body.role_assignments[0].project_id,
        after=_user_dict(user),
    )
    for ra in body.role_assignments:
        _create_assignment(db, p, user, ra)
    auth.send_invite(db, user, p.user.id)
    return user


def update_user(db: Session, p: Principal, user_id: uuid.UUID, body: UserUpdate) -> User:
    target = get_visible_user(db, p, user_id)
    p.require(None, Capability.user_manage_status)
    changes = body.changes()
    new_type = changes.get("employer_type", target.employer_type)
    new_contractor = changes.get("employer_contractor_id", target.employer_contractor_id)
    if new_type != EmployerType.contractor:
        new_contractor = None
        changes["employer_contractor_id"] = None
    elif new_contractor is None:
        raise validation_error("employer_contractor_id", "Required when employer is a contractor.")
    if new_contractor != target.employer_contractor_id:
        for a in target.assignments:
            if a.role in CONTRACTOR_ROLES and a.is_active_on(p.today):
                raise validation_error(
                    "employer_contractor_id",
                    "Revoke contractor-scoped roles before changing the employer (rule 29).",
                )
    before = _user_dict(target)
    for k, v in changes.items():
        setattr(target, k, v)
    target.search_text = search_blob(target.full_name_en, target.full_name_ar, target.email)
    b, after = audit.diff(before, _user_dict(target))
    if after:
        audit.record(
            db,
            AuditAction.update,
            p.actor(),
            entity_type=EntityType.user,
            entity_id=target.id,
            before=b,
            after=after,
        )
    return target


def update_me(db: Session, p: Principal, changes: dict[str, Any]) -> User:
    u = p.user
    before = _user_dict(u)
    for k, v in changes.items():
        setattr(u, k, v)
    u.search_text = search_blob(u.full_name_en, u.full_name_ar, u.email)
    b, a = audit.diff(before, _user_dict(u))
    if a:
        audit.record(
            db,
            AuditAction.update,
            p.actor(),
            entity_type=EntityType.user,
            entity_id=u.id,
            before=b,
            after=a,
        )
    return u


def deactivate(db: Session, user: User, reason: str, actor: audit.AuditActor) -> None:
    before = user.status
    user.status = UserStatus.deactivated
    user.status_reason = reason
    auth.revoke_sessions(db, user.id, "deactivated")
    auth.invalidate_tokens(db, user.id)
    audit.record(
        db,
        AuditAction.user_status_changed,
        actor,
        entity_type=EntityType.user,
        entity_id=user.id,
        before={"status": before},
        after={"status": UserStatus.deactivated},
        details={"reason": reason},
    )


def transition_user(
    db: Session, p: Principal, user_id: uuid.UUID, body: UserTransitionRequest
) -> User:
    target = get_visible_user(db, p, user_id)
    p.require(None, Capability.user_manage_status)
    src, dst = target.status, body.to_status
    if dst == UserStatus.deactivated and src != UserStatus.deactivated:
        _ensure_not_last_manager(db, p.today, target.id)
    if target.id == p.user.id:
        raise _self_forbidden()
    if dst == UserStatus.deactivated and src in (
        UserStatus.invited,
        UserStatus.active,
        UserStatus.locked,
    ):
        deactivate(db, target, require_reason(body.reason, "deactivate a user"), p.actor())
        return target
    if dst == UserStatus.active and src == UserStatus.locked:
        target.status = UserStatus.active
        target.locked_until = None
        target.failed_login_count = 0
        target.failed_window_started_at = None
        target.status_reason = body.reason
    elif dst == UserStatus.active and src == UserStatus.deactivated:
        target.status = UserStatus.active
        target.status_reason = body.reason
        target.password_hash = None  # forces password reset (§4.3)
        target.activated_at = now()
        auth.send_reset(db, target)
    else:
        raise invalid_transition("User", src, dst)
    audit.record(
        db,
        AuditAction.user_status_changed,
        p.actor(),
        entity_type=EntityType.user,
        entity_id=target.id,
        before={"status": src},
        after={"status": target.status},
        details={"reason": body.reason},
    )
    return target


def resend_invite(db: Session, p: Principal, user_id: uuid.UUID) -> User:
    target = get_visible_user(db, p, user_id)
    projects = {a.project_id for a in target.assignments if a.project_id}
    p.ensure_writer()
    if not p.is_manager and not any(p.grant(pid, Capability.user_invite) for pid in projects):
        raise forbidden_error()
    if target.status != UserStatus.invited:
        raise invalid_transition("User", target.status, UserStatus.invited)
    auth.send_invite(db, target, p.user.id)
    audit.record(
        db,
        AuditAction.user_invited,
        p.actor(),
        entity_type=EntityType.user,
        entity_id=target.id,
        details={"resent": True},
    )
    return target


def add_assignment(
    db: Session, p: Principal, user_id: uuid.UUID, body: RoleAssignmentCreate
) -> RoleAssignment:
    target = get_visible_user(db, p, user_id)
    _authorize_assignment(db, p, body.role, body.project_id)
    if target.id == p.user.id:
        raise _self_forbidden()
    return _create_assignment(db, p, target, body)


def _get_assignment(
    db: Session, p: Principal, user_id: uuid.UUID, assignment_id: uuid.UUID
) -> tuple[User, RoleAssignment]:
    target = get_visible_user(db, p, user_id)
    a = db.get(RoleAssignment, assignment_id)
    if (
        a is None
        or a.user_id != target.id
        or not (p.is_manager or (a.project_id and p.can_see_project(a.project_id)))
    ):
        raise deny(db, p, EntityType.role_assignment, assignment_id, what="Role assignment")
    return target, a


def update_assignment(
    db: Session,
    p: Principal,
    user_id: uuid.UUID,
    assignment_id: uuid.UUID,
    body: RoleAssignmentUpdate,
) -> RoleAssignment:
    target, a = _get_assignment(db, p, user_id, assignment_id)
    _authorize_assignment(db, p, a.role, a.project_id)
    changes = body.changes()
    valid_to = changes.get("valid_to", a.valid_to)
    if a.role == Role.hse_manager and valid_to is not None and valid_to < p.today:
        _ensure_not_last_manager(db, p.today, target.id, a)
    if target.id == p.user.id:
        raise _self_forbidden()
    if a.revoked_at is not None:
        raise invalid_transition("Role assignment", "revoked", "updated")
    _validate_assignment(
        db,
        target,
        a.role,
        a.project_id,
        changes.get("site_ids", a.site_ids),
        a.contractor_engagement_id,
        changes.get("valid_from", a.valid_from),
        valid_to,
        list(target.assignments),
        exclude_id=a.id,
    )
    before = _assignment_dict(a)
    for k, v in changes.items():
        setattr(a, k, list(v) if k == "site_ids" else v)
    b, after = audit.diff(before, _assignment_dict(a))
    if after:
        audit.record(
            db,
            AuditAction.update,
            p.actor(a.project_id),
            entity_type=EntityType.role_assignment,
            entity_id=a.id,
            project_id=a.project_id,
            before=b,
            after=after,
        )
    return a


def end_assignment(db: Session, a: RoleAssignment, day: date, actor_id: uuid.UUID | None) -> None:
    a.valid_to = day if a.valid_from <= day else a.valid_from
    a.revoked_at = now()
    a.revoked_by_user_id = actor_id


def revoke_assignment(
    db: Session, p: Principal, user_id: uuid.UUID, assignment_id: uuid.UUID
) -> RoleAssignment:
    target, a = _get_assignment(db, p, user_id, assignment_id)
    p.ensure_writer()
    if a.role == Role.hse_manager:
        _ensure_not_last_manager(db, p.today, target.id, a)
    _authorize_assignment(db, p, a.role, a.project_id)
    if target.id == p.user.id:
        raise _self_forbidden()
    if a.revoked_at is not None:
        raise invalid_transition("Role assignment", "revoked", "revoked")
    before = _assignment_dict(a)
    end_assignment(db, a, p.today, p.user.id)
    b, after = audit.diff(before, _assignment_dict(a))
    audit.record(
        db,
        AuditAction.role_revoked,
        p.actor(a.project_id),
        entity_type=EntityType.role_assignment,
        entity_id=a.id,
        project_id=a.project_id,
        before=b,
        after=after,
    )
    return a
