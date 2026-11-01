"""Small helpers of the Q2 routes."""

from typing import Any

from app.schemas.hse_common import ApiWarning


def with_warnings(read: dict[str, Any], warnings: list[ApiWarning], **extra: Any) -> dict[str, Any]:
    return {**read, "warnings": [w.model_dump() for w in warnings], **extra}


def paper(body: Any) -> dict[str, Any] | None:
    p = getattr(body, "paper", None)
    return p.model_dump() if p is not None else None
