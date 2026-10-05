"""In-app notifications (spec §7)."""

import uuid

from fastapi import APIRouter, status
from sqlalchemy import func, select, update

from app.api.deps import DB, CurrentUser, PageParams
from app.core.clock import now
from app.core.errors import error_responses, not_found
from app.models import Notification
from app.schemas.audit import NotificationPage, NotificationRead
from app.services.common import paginate

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    response_model=NotificationPage,
    summary="My notifications, newest first",
    responses=error_responses(401, 403, 422),
)
def list_notifications(
    user: CurrentUser, pg: PageParams, db: DB, unread_only: bool = False
) -> NotificationPage:
    stmt = select(Notification).where(Notification.user_id == user.user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    items, total = paginate(
        db, stmt.order_by(Notification.created_at.desc()), pg.page, pg.page_size
    )
    unread = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.user.id, Notification.read_at.is_(None))
    )
    return NotificationPage(
        items=[NotificationRead.model_validate(n) for n in items],
        total=total,
        page=pg.page,
        page_size=pg.page_size,
        unread_count=unread or 0,
    )


@router.post(
    "/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark one notification read",
    responses=error_responses(401, 403, 404),
)
def mark_notification_read(notification_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.user.id:
        raise not_found("Notification")
    n.read_at = n.read_at or now()


@router.post(
    "/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark all my notifications read",
    responses=error_responses(401, 403),
)
def mark_all_notifications_read(user: CurrentUser, db: DB) -> None:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.user.id, Notification.read_at.is_(None))
        .values(read_at=now())
    )
