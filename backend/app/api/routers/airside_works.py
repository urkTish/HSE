"""NOTAM works clearances and obstacle/crane clearances (spec 2-access-permits §3.14, §3.15,
§4.6, §4.7, §5.7)."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.access_enums import ClearanceReason, NotamStatus, ObstacleStatus, WorksImpact
from app.core.errors import error_responses
from app.schemas.airside_works import (
    HeightFigures,
    NotamReplaceRequest,
    NotamRequestCreate,
    NotamRequestPage,
    NotamRequestRead,
    NotamRequestUpdate,
    NotamTransitionRequest,
    ObstacleCreate,
    ObstacleDecisionRequest,
    ObstaclePage,
    ObstaclePreviewRequest,
    ObstacleRead,
    ObstacleTransitionRequest,
    ObstacleUpdate,
)
from app.services.access import works as svc

router = APIRouter(tags=["airside-works"])

# ---- NOTAM --------------------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/notam-requests",
    response_model=NotamRequestPage,
    summary="NOTAM log (capability 73)",
    responses=error_responses(401, 403, 404, 422),
)
def list_notam_requests(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[NotamStatus] | None, Query(alias="status")] = None,
    zone_id: uuid.UUID | None = None,
    works_impact: WorksImpact | None = None,
    in_effect: bool | None = None,
    late_request: bool | None = None,
    not_issued_within_hours: Annotated[
        int | None, Query(ge=1, le=720, description="Action panel: start within N h, not issued.")
    ] = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> NotamRequestPage:
    return svc.list_notams(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        status_,
        zone_id,
        works_impact,
        in_effect,
        late_request,
        not_issued_within_hours,
        date_from,
        date_to,
    )


@router.post(
    "/projects/{project_id}/notam-requests",
    response_model=NotamRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a NOTAM works request (capability 69) → draft",
    responses=error_responses(401, 403, 404, 422),
)
def create_notam_request(
    project_id: uuid.UUID, body: NotamRequestCreate, user: CurrentUser, db: DB
) -> NotamRequestRead:
    return svc.create_notam(db, user, project_id, body)


@router.get(
    "/notam-requests/{ntm_id}",
    response_model=NotamRequestRead,
    summary="Get a NOTAM works record",
    responses=error_responses(401, 403, 404),
)
def get_notam_request(ntm_id: uuid.UUID, user: CurrentUser, db: DB) -> NotamRequestRead:
    return svc.read_notam(db, user, ntm_id)


@router.patch(
    "/notam-requests/{ntm_id}",
    response_model=NotamRequestRead,
    summary="Edit a draft NOTAM request (capability 69)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_notam_request(
    ntm_id: uuid.UUID, body: NotamRequestUpdate, user: CurrentUser, db: DB
) -> NotamRequestRead:
    return svc.update_notam(db, user, ntm_id, body)


@router.post(
    "/notam-requests/{ntm_id}/transitions",
    response_model=NotamRequestRead,
    summary="Move a NOTAM record through §4.6 (submit, request, issue, reject, cancel)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_notam_request(
    ntm_id: uuid.UUID, body: NotamTransitionRequest, user: CurrentUser, db: DB
) -> NotamRequestRead:
    return svc.transition_notam(db, user, ntm_id, body)


@router.post(
    "/notam-requests/{ntm_id}/replace",
    response_model=NotamRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a NOTAMR: issued → replaced, new Issued record (capability 70)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def replace_notam_request(
    ntm_id: uuid.UUID, body: NotamReplaceRequest, user: CurrentUser, db: DB
) -> NotamRequestRead:
    return svc.replace_notam(db, user, ntm_id, body)


# ---- obstacle / crane clearance -----------------------------------------------------------------


@router.get(
    "/projects/{project_id}/obstacle-clearances",
    response_model=ObstaclePage,
    summary="Obstacle clearance register with heights in m and ft (capability 73)",
    responses=error_responses(401, 403, 404, 422),
)
def list_obstacle_clearances(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    status_: Annotated[list[ObstacleStatus] | None, Query(alias="status")] = None,
    zone_id: uuid.UUID | None = None,
    reason: ClearanceReason | None = None,
    active_on: date | None = None,
    expiring_within_days: Annotated[int | None, Query(ge=0, le=90)] = None,
) -> ObstaclePage:
    return svc.list_obstacles(
        db,
        user,
        project_id,
        pg.page,
        pg.page_size,
        status_,
        zone_id,
        reason,
        active_on,
        expiring_within_days,
    )


@router.post(
    "/projects/{project_id}/obstacle-clearances",
    response_model=ObstacleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an obstacle/crane clearance (capability 71; any project, OB-1) → draft",
    responses=error_responses(401, 403, 404, 422),
)
def create_obstacle_clearance(
    project_id: uuid.UUID, body: ObstacleCreate, user: CurrentUser, db: DB
) -> ObstacleRead:
    return svc.create_obstacle(db, user, project_id, body)


@router.post(
    "/obstacle-clearances/preview",
    response_model=HeightFigures,
    summary="Compute heights, margin, penetration and reasons without saving (§6.4, OB-3)",
    responses=error_responses(401, 403, 404, 422),
)
def preview_obstacle_clearance(
    body: ObstaclePreviewRequest, user: CurrentUser, db: DB
) -> HeightFigures:
    return svc.preview(db, user, body)


@router.get(
    "/obstacle-clearances/{obs_id}",
    response_model=ObstacleRead,
    summary="Get an obstacle clearance",
    responses=error_responses(401, 403, 404),
)
def get_obstacle_clearance(obs_id: uuid.UUID, user: CurrentUser, db: DB) -> ObstacleRead:
    return svc.read_obstacle(db, user, obs_id)


@router.patch(
    "/obstacle-clearances/{obs_id}",
    response_model=ObstacleRead,
    summary="Edit a draft obstacle clearance (capability 71)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_obstacle_clearance(
    obs_id: uuid.UUID, body: ObstacleUpdate, user: CurrentUser, db: DB
) -> ObstacleRead:
    return svc.update_obstacle(db, user, obs_id, body)


@router.post(
    "/obstacle-clearances/{obs_id}/transitions",
    response_model=ObstacleRead,
    summary="Submit / suspend / restore / withdraw (§4.7)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def transition_obstacle_clearance(
    obs_id: uuid.UUID, body: ObstacleTransitionRequest, user: CurrentUser, db: DB
) -> ObstacleRead:
    return svc.transition_obstacle(db, user, obs_id, body)


@router.post(
    "/obstacle-clearances/{obs_id}/decision",
    response_model=ObstacleRead,
    summary="Record the GACA/operator decision (capability 72; OB-4)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def decide_obstacle_clearance(
    obs_id: uuid.UUID, body: ObstacleDecisionRequest, user: CurrentUser, db: DB
) -> ObstacleRead:
    return svc.decide(db, user, obs_id, body)
