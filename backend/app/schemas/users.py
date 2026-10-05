"""Users and role assignments (spec §3.6, §3.7, §4.3, §5.2)."""

import uuid
from datetime import date, datetime

from pydantic import EmailStr, Field, field_validator, model_validator

from app.core.enums import EmployerType, Language, Role, UserStatus
from app.schemas.auth import MOBILE_PATTERN, RoleAssignmentRead
from app.schemas.common import ApiModel, Page, PatchInput, StrictInput, Timestamps

CONTACT_NOTE = " Omitted when the caller lacks capability 12 (view user email/mobile)."


class RoleAssignmentCreate(StrictInput):
    role: Role
    project_id: uuid.UUID | None = Field(
        default=None, description="Required for every role except hse_manager (must be null)."
    )
    site_ids: list[uuid.UUID] = Field(
        default_factory=list, description="Empty = all sites; sites must belong to the project."
    )
    contractor_engagement_id: uuid.UUID | None = Field(
        default=None,
        description="Required for contractor_hse_rep and permit_receiver; must be the user's "
        "employer's engagement on that project.",
    )
    valid_from: date | None = Field(default=None, description="Defaults to today (Asia/Riyadh).")
    valid_to: date | None = None

    @model_validator(mode="after")
    def _rules(self) -> "RoleAssignmentCreate":
        if self.role == Role.hse_manager:
            if self.project_id is not None or self.site_ids or self.contractor_engagement_id:
                raise ValueError(
                    "hse_manager is organisation-wide: no project, sites or contractor"
                )
        elif self.project_id is None:
            raise ValueError("project_id is required for this role")
        needs_contractor = self.role in (Role.contractor_hse_rep, Role.permit_receiver)
        if needs_contractor and self.contractor_engagement_id is None:
            raise ValueError("contractor_engagement_id is required for this role")
        if not needs_contractor and self.contractor_engagement_id is not None:
            raise ValueError("contractor_engagement_id is only allowed for contractor roles")
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be on or after valid_from")
        return self


class RoleAssignmentUpdate(PatchInput):
    non_nullable = frozenset({"site_ids", "valid_from"})

    site_ids: list[uuid.UUID] | None = None
    valid_from: date | None = None
    valid_to: date | None = None


class RoleAssignmentList(ApiModel):
    items: list[RoleAssignmentRead]


class UserInvite(StrictInput):
    """Invite a user (capability 10). Sends an invite email valid for 72 h."""

    email: EmailStr = Field(description="Unique; stored lower-cased.")
    full_name_en: str = Field(min_length=1, max_length=120)
    full_name_ar: str | None = Field(default=None, max_length=120)
    mobile: str | None = Field(default=None, pattern=MOBILE_PATTERN)
    employer_type: EmployerType
    employer_contractor_id: uuid.UUID | None = Field(
        default=None, description="Required iff employer_type = contractor."
    )
    job_title: str | None = Field(default=None, max_length=80)
    preferred_language: Language | None = Field(
        default=None, description="Defaults to the first assigned project's default_language."
    )
    role_assignments: list[RoleAssignmentCreate] = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()

    @model_validator(mode="after")
    def _employer(self) -> "UserInvite":
        if (self.employer_type == EmployerType.contractor) != (
            self.employer_contractor_id is not None
        ):
            raise ValueError("employer_contractor_id is required iff employer_type is contractor")
        return self


class UserUpdate(PatchInput):
    """Edit another user's profile (HSE Manager)."""

    non_nullable = frozenset({"full_name_en", "employer_type", "preferred_language"})

    full_name_en: str | None = Field(default=None, min_length=1, max_length=120)
    full_name_ar: str | None = Field(default=None, max_length=120)
    mobile: str | None = Field(default=None, pattern=MOBILE_PATTERN)
    employer_type: EmployerType | None = None
    employer_contractor_id: uuid.UUID | None = None
    job_title: str | None = Field(default=None, max_length=80)
    preferred_language: Language | None = None


class UserRead(Timestamps):
    """A user. The password hash is never returned (AC35)."""

    id: uuid.UUID
    email: str | None = Field(default=None, description="Personal." + CONTACT_NOTE)
    mobile: str | None = Field(default=None, description="Personal." + CONTACT_NOTE)
    full_name_en: str
    full_name_ar: str | None
    employer_type: EmployerType
    employer_contractor_id: uuid.UUID | None
    job_title: str | None
    preferred_language: Language
    status: UserStatus
    status_reason: str | None
    mfa_enabled: bool
    last_login_at: datetime | None
    invite_expires_at: datetime | None = Field(description="Set while status = invited.")
    locked_until: datetime | None
    privacy_notice_version: str | None
    privacy_notice_ack_at: datetime | None
    role_assignments: list[RoleAssignmentRead] = Field(
        description="Assignments visible to the caller (active and ended)."
    )


class UserPage(Page[UserRead]):
    pass


class UserTransitionRequest(StrictInput):
    """HSE Manager only (capability 13): to `deactivated` (reason required) from active/locked/
    invited; to `active` from locked (unlock) or deactivated (reactivate; forces password reset
    by email)."""

    to_status: UserStatus
    reason: str | None = Field(default=None, max_length=500)
