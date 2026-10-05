"""Users and role assignments (spec §3.6, §3.7, §4.3, §5.2)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, PageParams
from app.core.enums import EmployerType, Role, UserStatus
from app.core.errors import error_responses, not_implemented
from app.schemas.auth import RoleAssignmentRead
from app.schemas.users import (
    RoleAssignmentCreate,
    RoleAssignmentList,
    RoleAssignmentUpdate,
    UserInvite,
    UserPage,
    UserRead,
    UserTransitionRequest,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])

UserSort = Literal["name", "-name", "email", "-email", "last_login_at", "-last_login_at"]


@router.get(
    "",
    response_model=UserPage,
    response_model_exclude_unset=True,
    summary="User directory (scoped; email/mobile omitted without capability 12)",
    responses=error_responses(401, 403, 422),
)
def list_users(
    user: CurrentUser,
    pg: PageParams,
    project_id: uuid.UUID | None = None,
    role: Role | None = None,
    status_: Annotated[list[UserStatus] | None, Query(alias="status")] = None,
    employer_type: EmployerType | None = None,
    employer_contractor_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Name/email search.")] = None,
    sort: UserSort = "name",
) -> UserPage:
    raise not_implemented()


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a user with initial role assignments",
    description="HSE Officer may only assign site_engineer, permit_issuer, permit_receiver, "
    "contractor_hse_rep, viewer_client on own projects (rule 14) → 403 ROLE_NOT_ASSIGNABLE.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def invite_user(body: UserInvite, user: CurrentUser) -> UserRead:
    raise not_implemented()


@router.get(
    "/{user_id}",
    response_model=UserRead,
    response_model_exclude_unset=True,
    summary="Get a user",
    responses=error_responses(401, 403, 404),
)
def get_user(user_id: uuid.UUID, user: CurrentUser) -> UserRead:
    raise not_implemented()


@router.patch(
    "/{user_id}",
    response_model=UserRead,
    summary="Edit a user's profile (HSE Manager)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_user(user_id: uuid.UUID, body: UserUpdate, user: CurrentUser) -> UserRead:
    raise not_implemented()


@router.post(
    "/{user_id}/transitions",
    response_model=UserRead,
    summary="Deactivate, unlock or reactivate a user (HSE Manager)",
    description="409 LAST_HSE_MANAGER when it would leave no active HSE Manager; 403 "
    "SELF_MODIFICATION_FORBIDDEN on own account.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_user(user_id: uuid.UUID, body: UserTransitionRequest, user: CurrentUser) -> UserRead:
    raise not_implemented()


@router.post(
    "/{user_id}/resend-invite",
    response_model=UserRead,
    summary="Re-send the invite (new token; old one invalidated)",
    responses=error_responses(401, 403, 404, 409),
)
def resend_invite(user_id: uuid.UUID, user: CurrentUser) -> UserRead:
    raise not_implemented()


@router.get(
    "/{user_id}/role-assignments",
    response_model=RoleAssignmentList,
    summary="List a user's role assignments",
    responses=error_responses(401, 403, 404),
)
def list_role_assignments(user_id: uuid.UUID, user: CurrentUser) -> RoleAssignmentList:
    raise not_implemented()


@router.post(
    "/{user_id}/role-assignments",
    response_model=RoleAssignmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a role",
    description="409 SOD_CONFLICT for permit_issuer + permit_receiver on one project (rule 16).",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_role_assignment(
    user_id: uuid.UUID, body: RoleAssignmentCreate, user: CurrentUser
) -> RoleAssignmentRead:
    raise not_implemented()


@router.patch(
    "/{user_id}/role-assignments/{assignment_id}",
    response_model=RoleAssignmentRead,
    summary="Change sites or validity of a role assignment",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_role_assignment(
    user_id: uuid.UUID,
    assignment_id: uuid.UUID,
    body: RoleAssignmentUpdate,
    user: CurrentUser,
) -> RoleAssignmentRead:
    raise not_implemented()


@router.post(
    "/{user_id}/role-assignments/{assignment_id}/revoke",
    response_model=RoleAssignmentRead,
    summary="Revoke a role assignment (kept for history, end-dated today)",
    responses=error_responses(401, 403, 404, 409),
)
def revoke_role_assignment(
    user_id: uuid.UUID, assignment_id: uuid.UUID, user: CurrentUser
) -> RoleAssignmentRead:
    raise not_implemented()
