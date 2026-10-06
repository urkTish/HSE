"""Corrective actions (spec 1-dashboard §3.8, §4.5, §5.5, §6.6)."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.hse_enums import CaPriority, CaSourceType, CaStatus, ControlLevel, OverdueBucket
from app.schemas.actions import (
    CaCreate,
    CaExtensionCreate,
    CaExtensionDecision,
    CaPage,
    CaRead,
    CaTransitionRequest,
    CaUpdate,
)
from app.services import corrective_actions as svc

router = APIRouter(tags=["corrective actions"])


@router.get(
    "/projects/{project_id}/corrective-actions",
    response_model=CaPage,
    summary="List corrective actions (scoped); `overdue=true` matches K-42 exactly",
    responses=error_responses(401, 403, 404, 422),
)
def list_corrective_actions(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[CaStatus] | None, Query(alias="status")] = None,
    overdue: bool | None = None,
    overdue_bucket: OverdueBucket | None = None,
    verification_overdue: Annotated[
        bool | None, Query(description="K-42b: pending verification > completed + 3 days.")
    ] = None,
    priority: Annotated[list[CaPriority] | None, Query()] = None,
    control_level: Annotated[list[ControlLevel] | None, Query()] = None,
    source_type: CaSourceType | None = None,
    source_id: uuid.UUID | None = None,
    site_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    owner_is_me: bool = False,
    verifier_is_me: bool = False,
    due_from: date | None = None,
    due_to: date | None = None,
    as_of: Annotated[date | None, Query(description="Evaluate overdue at this date.")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: Literal["due_date", "-due_date", "created_at", "-created_at", "priority"] = "due_date",
) -> CaPage:
    return svc.list_page(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        statuses=status_,
        overdue=overdue,
        overdue_bucket=overdue_bucket,
        verification_overdue=verification_overdue,
        priorities=priority,
        control_levels=control_level,
        source_type=source_type,
        source_id=source_id,
        site_ids=site_id,
        engagement_ids=engagement_id,
        include_subcontractors=include_subcontractors,
        owner_is_me=owner_is_me,
        verifier_is_me=verifier_is_me,
        due_from=due_from,
        due_to=due_to,
        as_of=as_of,
        q=q,
        sort=sort,
    )


@router.post(
    "/projects/{project_id}/corrective-actions",
    response_model=CaRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a corrective action (capability 34)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_corrective_action(
    project_id: uuid.UUID, body: CaCreate, user: CurrentUser, db: DB
) -> CaRead:
    return svc.create(db, user, project_id, body)


@router.get(
    "/corrective-actions/{ca_id}",
    response_model=CaRead,
    summary="Get a corrective action",
    responses=error_responses(401, 403, 404),
)
def get_corrective_action(ca_id: uuid.UUID, user: CurrentUser, db: DB) -> CaRead:
    return svc.read(db, user, ca_id)


@router.patch(
    "/corrective-actions/{ca_id}",
    response_model=CaRead,
    summary="Edit a corrective action",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_corrective_action(ca_id: uuid.UUID, body: CaUpdate, user: CurrentUser, db: DB) -> CaRead:
    return svc.update(db, user, ca_id, body)


@router.post(
    "/corrective-actions/{ca_id}/transitions",
    response_model=CaRead,
    summary="Accept / complete / verify / reject / cancel / reopen (§4.5)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_corrective_action(
    ca_id: uuid.UUID, body: CaTransitionRequest, user: CurrentUser, db: DB
) -> CaRead:
    return svc.transition(db, user, ca_id, body)


@router.post(
    "/corrective-actions/{ca_id}/extensions",
    response_model=CaRead,
    status_code=status.HTTP_201_CREATED,
    summary="Request a due-date extension (owner, CA-3)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def request_ca_extension(
    ca_id: uuid.UUID, body: CaExtensionCreate, user: CurrentUser, db: DB
) -> CaRead:
    return svc.request_extension(db, user, ca_id, body)


@router.post(
    "/corrective-actions/{ca_id}/extensions/{extension_id}/decision",
    response_model=CaRead,
    summary="Approve or reject an extension (HSE Officer/Manager, not the owner)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def decide_ca_extension(
    ca_id: uuid.UUID,
    extension_id: uuid.UUID,
    body: CaExtensionDecision,
    user: CurrentUser,
    db: DB,
) -> CaRead:
    return svc.decide_extension(db, user, ca_id, extension_id, body)
