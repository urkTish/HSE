"""Installed licence keys (trial readiness, package B, D-289). One install = one customer; the
newest row is the active key. Rows are kept as a history of renewals."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.db.base import Base
from app.models.base import UUIDPk


class LicenceKey(UUIDPk, Base):
    __tablename__ = "licence_keys"
    __table_args__ = (Index("ix_licence_keys_installed_at", "installed_at"),)

    key: Mapped[str] = mapped_column(Text)
    licence_id: Mapped[str] = mapped_column(String(80))
    customer: Mapped[str] = mapped_column(String(200))
    bundle: Mapped[str] = mapped_column(String(20))
    valid_until: Mapped[date] = mapped_column(Date)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    installed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
