"""HSE department hierarchy (D-270): who holds which HSE position and who reports to whom."""

import uuid

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.enums import AuditAction, EntityType, HsePosition, Role, UserStatus
from app.core.errors import error_responses, not_found, validation_error
from app.models import RoleAssignment, User
from app.schemas.common import ApiModel, PatchInput
from app.services import audit
from app.services.permissions import forbidden_error

router = APIRouter(prefix="/hse-team", tags=["hse-team"])

HSE_ROLES = (Role.hse_manager, Role.hse_officer)


class HseTeamMember(ApiModel):
    id: uuid.UUID
    full_name_en: str
    full_name_ar: str | None
    email: str
    job_title: str | None
    hse_position: HsePosition | None
    reports_to_user_id: uuid.UUID | None
    roles: list[Role]


class HseTeam(ApiModel):
    items: list[HseTeamMember] = Field(
        description="Active users with an HSE role or an HSE position; build the tree from "
        "reports_to_user_id (null = top)."
    )


class HseTeamUpdate(PatchInput):
    hse_position: HsePosition | None = None
    reports_to_user_id: uuid.UUID | None = None


def _members(db: DB) -> list[User]:
    with_role = select(RoleAssignment.user_id).where(
        RoleAssignment.role.in_(HSE_ROLES), RoleAssignment.revoked_at.is_(None)
    )
    return list(
        db.scalars(
            select(User)
            .where(
                User.status != UserStatus.deactivated,
                (User.id.in_(with_role)) | (User.hse_position.is_not(None)),
            )
            .order_by(User.full_name_en)
        )
    )


def _read(u: User) -> HseTeamMember:
    roles = sorted({a.role for a in u.assignments if a.revoked_at is None})
    return HseTeamMember(
        id=u.id,
        full_name_en=u.full_name_en,
        full_name_ar=u.full_name_ar,
        email=u.email,
        job_title=u.job_title,
        hse_position=u.hse_position,
        reports_to_user_id=u.reports_to_user_id,
        roles=roles,
    )


@router.get(
    "",
    response_model=HseTeam,
    summary="HSE team and reporting lines",
    responses=error_responses(401),
)
def get_hse_team(user: CurrentUser, db: DB) -> HseTeam:
    return HseTeam(items=[_read(u) for u in _members(db)])


@router.patch(
    "/{user_id}",
    response_model=HseTeamMember,
    summary="Set a person's HSE position and who they report to (HSE Manager)",
    responses=error_responses(401, 403, 404, 422),
)
def update_hse_team_member(
    user_id: uuid.UUID, body: HseTeamUpdate, user: CurrentUser, db: DB
) -> HseTeamMember:
    if not user.is_manager:
        raise forbidden_error("Only the HSE Manager can change the HSE team.")
    target = db.get(User, user_id)
    if target is None:
        raise not_found("User")
    data = body.changes()
    boss_id = data.get("reports_to_user_id", target.reports_to_user_id)
    if boss_id is not None:
        if boss_id == target.id:
            raise validation_error("reports_to_user_id", "A person cannot report to themselves.")
        seen = {target.id}
        cur = db.get(User, boss_id)
        if cur is None:
            raise validation_error("reports_to_user_id", "Unknown user.")
        while cur is not None and cur.reports_to_user_id is not None:
            if cur.reports_to_user_id in seen or cur.id in seen:
                raise validation_error(
                    "reports_to_user_id", "That would make a loop in the reporting line."
                )
            seen.add(cur.id)
            cur = db.get(User, cur.reports_to_user_id)
    before = {"hse_position": target.hse_position, "reports_to_user_id": target.reports_to_user_id}
    for k, v in data.items():
        setattr(target, k, v)
    db.flush()
    audit.record(
        db,
        AuditAction.update,
        user.actor(None),
        entity_type=EntityType.user,
        entity_id=target.id,
        before=before,
        after={k: data[k] for k in data},
    )
    return _read(target)
