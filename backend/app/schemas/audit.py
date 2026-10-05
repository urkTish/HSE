"""Audit log, change history and notifications (spec §3.10, §5.6, §7)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.core.enums import AuditAction, AuditResult, EntityType, NotificationKind, Role
from app.schemas.common import ApiModel, Page


class AuditEntryRead(ApiModel):
    id: uuid.UUID
    seq: int = Field(description="Monotonic sequence number in the hash chain.")
    occurred_at: datetime
    actor_user_id: uuid.UUID | None = Field(description="Null = system job.")
    actor_name: str | None
    actor_role: Role | None
    on_behalf_project_id: uuid.UUID | None
    ip_address: str | None = Field(default=None, description="HSE Manager only (rule 38).")
    user_agent: str | None = Field(default=None, description="HSE Manager only (rule 38).")
    action: AuditAction
    entity_type: EntityType | None
    entity_id: uuid.UUID | None
    project_id: uuid.UUID | None
    before: dict[str, Any] | None = Field(description="Changed fields only; sensitive = '***'.")
    after: dict[str, Any] | None
    fields_read: list[str] | None
    details: dict[str, Any] | None = Field(
        description="Extra context: reason, export row count/filter, purge range, denied path."
    )
    result: AuditResult
    request_id: str | None
    prev_hash: str | None = Field(default=None, description="HSE Manager only.")
    hash: str | None = Field(default=None, description="HSE Manager only.")


class AuditEntryPage(Page[AuditEntryRead]):
    pass


class ChangeHistoryEntry(ApiModel):
    """Who/when/what changed on a record the caller can see (no IP, rule 38)."""

    id: uuid.UUID
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    actor_name: str | None
    action: AuditAction
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class ChangeHistoryPage(Page[ChangeHistoryEntry]):
    pass


class AuditChainVerification(ApiModel):
    ok: bool
    checked_count: int
    first_break_seq: int | None = Field(description="Sequence of the first broken entry.")
    first_break_entry_id: uuid.UUID | None
    verified_at: datetime


class NotificationRead(ApiModel):
    id: uuid.UUID
    kind: NotificationKind
    title_en: str
    title_ar: str
    body_en: str | None
    body_ar: str | None
    entity_type: EntityType | None
    entity_id: uuid.UUID | None
    project_id: uuid.UUID | None
    created_at: datetime
    read_at: datetime | None


class NotificationPage(Page[NotificationRead]):
    unread_count: int
