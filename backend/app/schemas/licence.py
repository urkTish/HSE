"""Licence status and renewal (trial readiness, package B; D-289…D-298)."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel, StrictInput

LicenceStateName = Literal["none", "active", "expired", "invalid"]
LicenceBundle = Literal["trial", "basic", "professional", "enterprise"]


class LicenceUsage(ApiModel):
    used: int
    limit: int | None = Field(description="null = unlimited.")
    percent: int | None = Field(description="used / limit, rounded down; null when unlimited.")


class LicenceStorage(ApiModel):
    files_bytes: int = Field(description="Stored attachments and generated files.")
    database_bytes: int = Field(description="Size of the database.")
    used_bytes: int
    limit_gb: int | None = Field(description="null = unlimited.")
    percent: int | None
    warning: bool = Field(description="True from 80 % of the licence storage.")


class LicenceRead(ApiModel):
    state: LicenceStateName = Field(
        description="none = no licence key (unlimited); active; expired or invalid = read-only."
    )
    read_only: bool = Field(
        description="Writes are refused with 403 LICENCE_READ_ONLY (GET, exports, sign-in, the "
        "licence page and life-safety flows stay open)."
    )
    source: Literal["database", "environment"] | None = Field(
        description="Where the active key comes from: pasted on the licence page, or the "
        "server configuration (LICENCE_KEY / LICENCE_FILE)."
    )
    problem: str | None = Field(description="Why the key is invalid (English), else null.")
    licence_id: str | None
    customer: str | None
    bundle: LicenceBundle | None
    is_trial: bool
    issued_on: date | None
    valid_until: date | None = Field(description="Last day of use (Riyadh), inclusive.")
    days_left: int | None = Field(description="0 on the last day; negative once expired.")
    data_deletion_after: date | None = Field(
        description="Trial only: data is deleted after this date unless a plan is chosen "
        "(trial terms, PDPL). Not done automatically by the platform."
    )
    installed_at: datetime | None
    projects: LicenceUsage = Field(description="Open (not closed) projects.")
    users: LicenceUsage = Field(description="Users that are not deactivated.")
    ai_questions_month: LicenceUsage = Field(
        description="AI assistant questions asked this calendar month (whole install)."
    )
    storage: LicenceStorage
    can_manage: bool = Field(description="The caller may enter a new key (HSE Manager).")


class LicenceKeyInput(StrictInput):
    key: str = Field(
        min_length=10,
        max_length=8000,
        description="The licence key as received (HSE1.…); spaces and line breaks are ignored.",
    )
