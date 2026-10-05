"""In-app notifications (spec §7)."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, PageParams
from app.core.errors import error_responses, not_implemented
from app.schemas.audit import NotificationPage

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    response_model=NotificationPage,
    summary="My notifications, newest first",
    responses=error_responses(401, 403, 422),
)
def list_notifications(
    user: CurrentUser, pg: PageParams, unread_only: bool = False
) -> NotificationPage:
    raise not_implemented()


@router.post(
    "/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark one notification read",
    responses=error_responses(401, 403, 404),
)
def mark_notification_read(notification_id: uuid.UUID, user: CurrentUser) -> None:
    raise not_implemented()


@router.post(
    "/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark all my notifications read",
    responses=error_responses(401, 403),
)
def mark_all_notifications_read(user: CurrentUser) -> None:
    raise not_implemented()
