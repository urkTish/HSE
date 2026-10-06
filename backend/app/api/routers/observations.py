"""Safety observations (spec 1-dashboard §3.6, §4.3, §5.3)."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses, not_implemented
from app.core.hse_enums import ObservationCategory, ObservationStatus, ObservationType, RiskRating
from app.schemas.observations import (
    ObservationCloseRequest,
    ObservationCreate,
    ObservationPage,
    ObservationRead,
    ObservationUpdate,
)

router = APIRouter(tags=["observations"])


@router.get(
    "/projects/{project_id}/observations",
    response_model=ObservationPage,
    response_model_exclude_unset=True,
    summary="List observations (scoped; anonymous observers hidden except HSE Manager)",
    responses=error_responses(401, 403, 404, 422),
)
def list_observations(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[ObservationStatus] | None, Query(alias="status")] = None,
    obs_type: Annotated[list[ObservationType] | None, Query()] = None,
    category: ObservationCategory | None = None,
    risk_rating: RiskRating | None = None,
    site_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    zone_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    engagement_id: Annotated[list[uuid.UUID] | None, Query()] = None,
    include_subcontractors: bool = True,
    without_ca_over_hours: Annotated[
        int | None,
        Query(ge=1, description="Action panel: high-risk unsafe, open, no CA after N hours."),
    ] = None,
    mine: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: Literal["observed_at", "-observed_at"] = "-observed_at",
) -> ObservationPage:
    raise not_implemented()


@router.post(
    "/projects/{project_id}/observations",
    response_model=ObservationRead,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an observation (capability 32)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_observation(
    project_id: uuid.UUID, body: ObservationCreate, user: CurrentUser, db: DB
) -> ObservationRead:
    raise not_implemented()


@router.get(
    "/observations/{observation_id}",
    response_model=ObservationRead,
    response_model_exclude_unset=True,
    summary="Get an observation",
    responses=error_responses(401, 403, 404),
)
def get_observation(observation_id: uuid.UUID, user: CurrentUser, db: DB) -> ObservationRead:
    raise not_implemented()


@router.patch(
    "/observations/{observation_id}",
    response_model=ObservationRead,
    response_model_exclude_unset=True,
    summary="Edit an observation (observer / closers in scope)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_observation(
    observation_id: uuid.UUID, body: ObservationUpdate, user: CurrentUser, db: DB
) -> ObservationRead:
    raise not_implemented()


@router.post(
    "/observations/{observation_id}/close",
    response_model=ObservationRead,
    response_model_exclude_unset=True,
    summary="Close an open observation with a comment (capability 32 close)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def close_observation(
    observation_id: uuid.UUID, body: ObservationCloseRequest, user: CurrentUser, db: DB
) -> ObservationRead:
    raise not_implemented()
