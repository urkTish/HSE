"""Contractors and project engagements (spec §3.4, §3.5, §4.2, §5.4)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, PageParams
from app.core.enums import ContractorCategory, ContractorStatus
from app.core.errors import error_responses, not_implemented
from app.schemas.contractors import (
    ContractorCreate,
    ContractorPage,
    ContractorRead,
    ContractorTransitionRequest,
    ContractorUpdate,
    EngagementCreate,
    EngagementPage,
    EngagementRead,
    EngagementUpdate,
)

router = APIRouter(tags=["contractors"])

ContractorSort = Literal["short_code", "-short_code", "name", "-name", "cr_expiry_date"]


@router.get(
    "/contractors",
    response_model=ContractorPage,
    response_model_exclude_unset=True,
    summary="List contractors visible to the caller",
    description="`q` matches short code, CR and EN/AR names with Arabic normalisation "
    "(rule 45). Contact fields are omitted without capability 9.",
    responses=error_responses(401, 403, 422),
)
def list_contractors(
    user: CurrentUser,
    pg: PageParams,
    status_: Annotated[list[ContractorStatus] | None, Query(alias="status")] = None,
    category: ContractorCategory | None = None,
    project_id: Annotated[
        uuid.UUID | None, Query(description="Only contractors engaged on this project.")
    ] = None,
    cr_expiring_within_days: Annotated[
        int | None, Query(ge=0, le=365, description="CR expiry within N days (incl. expired).")
    ] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: ContractorSort = "short_code",
) -> ContractorPage:
    raise not_implemented()


@router.post(
    "/contractors",
    response_model=ContractorRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a contractor (draft)",
    responses=error_responses(401, 403, 409, 422),
)
def create_contractor(body: ContractorCreate, user: CurrentUser) -> ContractorRead:
    raise not_implemented()


@router.get(
    "/contractors/{contractor_id}",
    response_model=ContractorRead,
    response_model_exclude_unset=True,
    summary="Get a contractor",
    responses=error_responses(401, 403, 404),
)
def get_contractor(contractor_id: uuid.UUID, user: CurrentUser) -> ContractorRead:
    raise not_implemented()


@router.patch(
    "/contractors/{contractor_id}",
    response_model=ContractorRead,
    summary="Update a contractor",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_contractor(
    contractor_id: uuid.UUID, body: ContractorUpdate, user: CurrentUser
) -> ContractorRead:
    raise not_implemented()


@router.post(
    "/contractors/{contractor_id}/transitions",
    response_model=ContractorRead,
    summary="Change contractor status (submit, approve, return, suspend, reinstate, demobilise, "
    "blacklist, lift blacklist)",
    description="Blacklisting deactivates the contractor's users, ends their sessions and role "
    "assignments, and flags descendant engagements (rule 27).",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_contractor(
    contractor_id: uuid.UUID, body: ContractorTransitionRequest, user: CurrentUser
) -> ContractorRead:
    raise not_implemented()


@router.get(
    "/projects/{project_id}/engagements",
    response_model=EngagementPage,
    summary="List contractor engagements on a project (scoped to the contractor tree for "
    "contractor roles)",
    responses=error_responses(401, 403, 404, 422),
)
def list_engagements(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    tier: Annotated[int | None, Query(ge=1, le=3)] = None,
    contractor_id: uuid.UUID | None = None,
    parent_engagement_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
    parent_blacklisted: bool | None = None,
) -> EngagementPage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/engagements",
    response_model=EngagementRead,
    status_code=status.HTTP_201_CREATED,
    summary="Engage an approved contractor on a project",
    description="409 CONTRACTOR_NOT_APPROVED unless the contractor is approved; 422 when the "
    "parent tier is not tier-1 or is on another project.",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_engagement(
    project_id: uuid.UUID, body: EngagementCreate, user: CurrentUser
) -> EngagementRead:
    raise not_implemented()


@router.get(
    "/engagements/{engagement_id}",
    response_model=EngagementRead,
    summary="Get an engagement",
    responses=error_responses(401, 403, 404),
)
def get_engagement(engagement_id: uuid.UUID, user: CurrentUser) -> EngagementRead:
    raise not_implemented()


@router.patch(
    "/engagements/{engagement_id}",
    response_model=EngagementRead,
    summary="Update an engagement (scope, sites, dates)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_engagement(
    engagement_id: uuid.UUID, body: EngagementUpdate, user: CurrentUser
) -> EngagementRead:
    raise not_implemented()


@router.post(
    "/engagements/{engagement_id}/clear-parent-blacklisted",
    response_model=EngagementRead,
    summary="HSE Manager: mark a 'parent blacklisted' flag as reviewed",
    responses=error_responses(401, 403, 404, 409),
)
def clear_parent_blacklisted(engagement_id: uuid.UUID, user: CurrentUser) -> EngagementRead:
    raise not_implemented()
