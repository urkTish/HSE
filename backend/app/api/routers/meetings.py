"""HSE meetings (spec 1-dashboard §3.9)."""

import uuid
from datetime import date

from fastapi import APIRouter, Response, status

from app.api.deps import DB, CurrentUser, PageParams
from app.core.errors import error_responses
from app.core.hse_enums import MeetingType
from app.schemas.meetings import HseMeetingCreate, HseMeetingPage, HseMeetingRead, HseMeetingUpdate
from app.services import meetings as svc

router = APIRouter(tags=["hse meetings"])


@router.get(
    "/projects/{project_id}/hse-meetings",
    response_model=HseMeetingPage,
    summary="List HSE meetings",
    responses=error_responses(401, 403, 404, 422),
)
def list_hse_meetings(
    project_id: uuid.UUID,
    user: CurrentUser,
    pg: PageParams,
    db: DB,
    meeting_type: MeetingType | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> HseMeetingPage:
    return svc.list_page(
        db, user, project_id, pg.page, pg.page_size, meeting_type, date_from, date_to
    )


@router.post(
    "/projects/{project_id}/hse-meetings",
    response_model=HseMeetingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record an HSE meeting (HSE Officer/Manager)",
    responses=error_responses(401, 403, 404, 409, 422),
)
def create_hse_meeting(
    project_id: uuid.UUID, body: HseMeetingCreate, user: CurrentUser, db: DB
) -> HseMeetingRead:
    return svc.create(db, user, project_id, body)


@router.get(
    "/hse-meetings/{meeting_id}",
    response_model=HseMeetingRead,
    summary="Get an HSE meeting",
    responses=error_responses(401, 403, 404),
)
def get_hse_meeting(meeting_id: uuid.UUID, user: CurrentUser, db: DB) -> HseMeetingRead:
    return svc.read(db, user, meeting_id)


@router.patch(
    "/hse-meetings/{meeting_id}",
    response_model=HseMeetingRead,
    summary="Edit an HSE meeting",
    responses=error_responses(401, 403, 404, 409, 422),
)
def update_hse_meeting(
    meeting_id: uuid.UUID, body: HseMeetingUpdate, user: CurrentUser, db: DB
) -> HseMeetingRead:
    return svc.update(db, user, meeting_id, body)


@router.delete(
    "/hse-meetings/{meeting_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an HSE meeting",
    responses=error_responses(401, 403, 404, 409),
)
def delete_hse_meeting(meeting_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    svc.delete(db, user, meeting_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
