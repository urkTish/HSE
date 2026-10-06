"""Inspection plans and inspections (spec 1-dashboard §3.7, §4.4, §5.4)."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses, not_implemented
from app.core.hse_enums import InspectionStatus, InspectionTimeliness, InspectionType
from app.schemas.inspections import (
    InspectionCancel,
    InspectionComplete,
    InspectionPage,
    InspectionPlanCreate,
    InspectionPlanPage,
    InspectionPlanRead,
    InspectionPlanUpdate,
    InspectionRead,
    UnplannedInspectionCreate,
)

router = APIRouter(tags=["inspections"])


@router.get(
    "/projects/{project_id}/inspection-plans",
    response_model=InspectionPlanPage,
    summary="List inspection plans",
    responses=error_responses(401, 403, 404, 422),
)
def list_inspection_plans(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    active: bool | None = None,
    inspection_type: InspectionType | None = None,
    site_id: uuid.UUID | None = None,
) -> InspectionPlanPage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/inspection-plans",
    response_model=InspectionPlanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an inspection plan (capability 33 manage); generates instances 35 days ahead",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_inspection_plan(
    project_id: uuid.UUID, body: InspectionPlanCreate, user: CurrentUser, db: DB
) -> InspectionPlanRead:
    raise not_implemented()


@router.get(
    "/inspection-plans/{plan_id}",
    response_model=InspectionPlanRead,
    summary="Get an inspection plan",
    responses=error_responses(401, 403, 404),
)
def get_inspection_plan(plan_id: uuid.UUID, user: CurrentUser, db: DB) -> InspectionPlanRead:
    raise not_implemented()


@router.patch(
    "/inspection-plans/{plan_id}",
    response_model=InspectionPlanRead,
    summary="Edit a plan (affects future planned instances only, N-1)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_inspection_plan(
    plan_id: uuid.UUID, body: InspectionPlanUpdate, user: CurrentUser, db: DB
) -> InspectionPlanRead:
    raise not_implemented()


@router.get(
    "/projects/{project_id}/inspections",
    response_model=InspectionPage,
    summary="List inspections (planned instances and unplanned)",
    responses=error_responses(401, 403, 404, 422),
)
def list_inspections(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[InspectionStatus] | None, Query(alias="status")] = None,
    timeliness: Annotated[list[InspectionTimeliness] | None, Query()] = None,
    plan_id: uuid.UUID | None = None,
    inspection_type: InspectionType | None = None,
    site_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    assigned_to_me: bool = False,
    planned_from: date | None = None,
    planned_to: date | None = None,
    sort: Literal["planned_date", "-planned_date", "completed_at", "-completed_at"] = (
        "-planned_date"
    ),
) -> InspectionPage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/inspections",
    response_model=InspectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record an unplanned (ad-hoc) inspection (capability 33 record)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_unplanned_inspection(
    project_id: uuid.UUID, body: UnplannedInspectionCreate, user: CurrentUser, db: DB
) -> InspectionRead:
    raise not_implemented()


@router.get(
    "/inspections/{inspection_id}",
    response_model=InspectionRead,
    summary="Get an inspection",
    responses=error_responses(401, 403, 404),
)
def get_inspection(inspection_id: uuid.UUID, user: CurrentUser, db: DB) -> InspectionRead:
    raise not_implemented()


@router.post(
    "/inspections/{inspection_id}/complete",
    response_model=InspectionRead,
    summary="Record results of a planned/missed inspection",
    responses=error_responses(401, 403, 404, 409, 422),
)
def complete_inspection(
    inspection_id: uuid.UUID, body: InspectionComplete, user: CurrentUser, db: DB
) -> InspectionRead:
    raise not_implemented()


@router.post(
    "/inspections/{inspection_id}/cancel",
    response_model=InspectionRead,
    summary="Cancel a planned/missed inspection (reason; after Missed HSE Manager only)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def cancel_inspection(
    inspection_id: uuid.UUID, body: InspectionCancel, user: CurrentUser, db: DB
) -> InspectionRead:
    raise not_implemented()
