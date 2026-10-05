"""Column helpers shared by all models."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now


def enum_col(enum_cls: type[StrEnum], **kw: Any) -> Any:
    """Store a StrEnum by value in a VARCHAR (no native PG enum, easy to extend)."""
    return mapped_column(
        Enum(
            enum_cls,
            native_enum=False,
            create_constraint=False,
            length=40,
            values_callable=lambda e: [m.value for m in e],
        ),
        **kw,
    )


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now, server_default=func.now()
    )
