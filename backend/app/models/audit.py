"""Append-only audit log, notifications and the email outbox."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.enums import AuditAction, AuditResult, EntityType, Language, NotificationKind, Role
from app.db.base import Base
from app.models.base import UUIDPk, enum_col


class AuditEntry(UUIDPk, Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_project_occurred", "project_id", "occurred_at"),
    )

    seq: Mapped[int] = mapped_column(BigInteger, unique=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    actor_role: Mapped[Role | None] = enum_col(Role, nullable=True)
    on_behalf_project_id: Mapped[uuid.UUID | None] = mapped_column()
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    action: Mapped[AuditAction] = enum_col(AuditAction)
    entity_type: Mapped[EntityType | None] = enum_col(EntityType, nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    project_id: Mapped[uuid.UUID | None] = mapped_column()
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    fields_read: Mapped[list[str] | None] = mapped_column(JSONB)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result: Mapped[AuditResult] = enum_col(AuditResult)
    request_id: Mapped[str | None] = mapped_column(String(64))
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class Notification(UUIDPk, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[NotificationKind] = enum_col(NotificationKind)
    title_en: Mapped[str] = mapped_column(String(200))
    title_ar: Mapped[str] = mapped_column(String(200))
    body_en: Mapped[str | None] = mapped_column(Text)
    body_ar: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[EntityType | None] = enum_col(EntityType, nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    project_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailMessage(UUIDPk, Base):
    """Outbox. A delivery worker (later phase / SMTP config) sends and marks rows."""

    __tablename__ = "email_outbox"

    to_email: Mapped[str] = mapped_column(String(254))
    to_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    language: Mapped[Language] = enum_col(Language)
    template: Mapped[str] = mapped_column(String(60))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
