"""Users, role assignments, sessions and one-time tokens."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.clock import now
from app.core.enums import EmployerType, Language, Role, UserStatus
from app.db.base import Base
from app.models.base import TimestampMixin, UUIDPk, enum_col


class User(UUIDPk, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name_en: Mapped[str] = mapped_column(String(120))
    full_name_ar: Mapped[str | None] = mapped_column(String(120))
    mobile: Mapped[str | None] = mapped_column(String(16))
    employer_type: Mapped[EmployerType] = enum_col(EmployerType)
    employer_contractor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contractors.id"), index=True
    )
    job_title: Mapped[str | None] = mapped_column(String(80))
    preferred_language: Mapped[Language] = enum_col(Language, default=Language.en)
    status: Mapped[UserStatus] = enum_col(UserStatus, default=UserStatus.invited)
    status_reason: Mapped[str | None] = mapped_column(String(500))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    privacy_notice_version: Mapped[str | None] = mapped_column(String(20))
    privacy_notice_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inactivity_warned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    search_text: Mapped[str] = mapped_column(Text, default="")

    assignments: Mapped[list["RoleAssignment"]] = relationship(
        back_populates="user",
        foreign_keys="RoleAssignment.user_id",
        order_by="RoleAssignment.created_at",
    )


class RoleAssignment(UUIDPk, Base):
    __tablename__ = "role_assignments"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[Role] = enum_col(Role)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), index=True)
    site_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)), default=list)
    contractor_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_engagements.id")
    )
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ending_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="assignments", foreign_keys=[user_id])

    def is_active_on(self, day: date) -> bool:
        return (
            self.revoked_at is None
            and self.valid_from <= day
            and (self.valid_to is None or day <= self.valid_to)
        )


class UserSession(UUIDPk, Base):
    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(40))
    # Phase 3 §3.2.3 — password re-entry for signatures (login counts as an authentication)
    last_authenticated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(400))


class TokenKind(StrEnum):
    invite = "invite"
    password_reset = "password_reset"


class UserToken(UUIDPk, Base):
    __tablename__ = "user_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[TokenKind] = enum_col(TokenKind)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expiry_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
