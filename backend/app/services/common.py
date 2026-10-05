"""Small helpers shared by services."""

from collections.abc import Sequence
from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.enums import ProjectStatus
from app.core.errors import ApiError, ErrorCode, FieldError, validation_error
from app.models import Project

T = TypeVar("T")


def paginate(db: Session, stmt: Select[T], page: int, page_size: int) -> tuple[Sequence[T], int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(stmt.limit(page_size).offset((page - 1) * page_size)).unique().all()
    return items, total


def duplicate(field: str, message: str) -> ApiError:
    return ApiError(
        409,
        ErrorCode.DUPLICATE_VALUE,
        message,
        "القيمة مستخدمة مسبقاً.",
        errors=[FieldError(loc=["body", field], msg=message, type="duplicate")],
    )


def ensure_open(project: Project) -> None:
    """Rule 22: a closed project rejects every create/update on itself and its children."""
    if project.status == ProjectStatus.closed:
        raise ApiError(
            409,
            ErrorCode.PROJECT_CLOSED,
            f"Project {project.code} is closed and read-only.",
            f"المشروع {project.code} مغلق وللاطلاع فقط.",
        )


def require_reason(reason: str | None, transition: str) -> str:
    if not reason or not reason.strip():
        raise validation_error("reason", f"A reason is required to {transition}.")
    return reason.strip()


def invalid_transition(entity: str, src: Any, dst: Any) -> ApiError:
    s = getattr(src, "value", src)
    d = getattr(dst, "value", dst)
    return ApiError(
        409,
        ErrorCode.INVALID_TRANSITION,
        f"{entity} cannot change from {s} to {d}.",
        "انتقال الحالة غير مسموح.",
    )


def condition_not_met(message: str, message_ar: str | None = None) -> ApiError:
    return ApiError(409, ErrorCode.TRANSITION_CONDITION_NOT_MET, message, message_ar)
