"""Auth, session, profile and privacy-notice schemas (spec §3.6, §5.1)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import EmailStr, Field

from app.core.enums import (
    Capability,
    CapabilityScope,
    EmployerType,
    Language,
    Role,
    UserStatus,
)
from app.schemas.common import ApiModel, PatchInput, StrictInput

PASSWORD_DESCRIPTION = (
    "At least 12 characters, at least 3 of 4 classes (upper, lower, digit, symbol), not equal to "
    "the email local part and not a common breached password (spec §5.1 rule 2)."
)
MOBILE_PATTERN = r"^\+[1-9]\d{7,14}$"


class LoginRequest(StrictInput):
    email: EmailStr = Field(description="Login email (case-insensitive).")
    password: str = Field(min_length=1, max_length=256)


class CapabilityGrant(ApiModel):
    capability: Capability
    scope: CapabilityScope = Field(
        description="How far the capability reaches on this project (matrix legend §5.10)."
    )


class ProjectAccess(ApiModel):
    """What the current user may do on one project (union of active assignments, rule 9)."""

    project_id: uuid.UUID
    project_code: str
    roles: list[Role]
    capabilities: list[CapabilityGrant]
    site_ids: list[uuid.UUID] | None = Field(
        description="Sites the user is restricted to; null = all sites of the project (rule 11)."
    )
    contractor_engagement_ids: list[uuid.UUID] = Field(
        description="Engagements the user is scoped to (Contractor HSE Rep / Permit Receiver)."
    )
    read_only: bool = Field(description="True when the user only holds viewer_client here.")


class RoleAssignmentRead(ApiModel):
    """A role held by a user, optionally scoped to a project, sites and a contractor."""

    id: uuid.UUID
    user_id: uuid.UUID
    role: Role
    project_id: uuid.UUID | None = Field(description="Null only for hse_manager (org-wide).")
    site_ids: list[uuid.UUID] = Field(description="Empty = all sites of the project.")
    contractor_engagement_id: uuid.UUID | None = Field(
        description="Required for contractor_hse_rep and permit_receiver."
    )
    valid_from: date
    valid_to: date | None
    is_active: bool = Field(description="True if today (Asia/Riyadh) is within the validity.")
    revoked_at: datetime | None
    created_at: datetime
    created_by_user_id: uuid.UUID | None


class Me(ApiModel):
    """The authenticated user, with resolved permissions for UI gating (server still enforces)."""

    id: uuid.UUID
    email: str
    full_name_en: str
    full_name_ar: str | None
    mobile: str | None
    employer_type: EmployerType
    employer_contractor_id: uuid.UUID | None
    job_title: str | None
    preferred_language: Language
    display_language: Language = Field(
        description="Resolved UI language: preferred_language, then project default, then en "
        "(rule 43)."
    )
    status: UserStatus
    mfa_enabled: bool
    last_login_at: datetime | None
    privacy_notice_version: str | None = Field(description="Version the user acknowledged.")
    privacy_notice_ack_at: datetime | None
    privacy_ack_required: bool = Field(
        description="True when the current notice version is not acknowledged. While true every "
        "API except privacy-notice ack and logout returns 403 PRIVACY_ACK_REQUIRED."
    )
    is_hse_manager: bool
    org_capabilities: list[Capability] = Field(
        description="Organisation-wide capabilities (from hse_manager); empty for other roles."
    )
    projects: list[ProjectAccess]
    role_assignments: list[RoleAssignmentRead] = Field(description="Active assignments only.")


class LoginResponse(ApiModel):
    access_token: str = Field(description="JWT; same value as the hse_session cookie.")
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime = Field(description="Absolute session expiry (12 h after login).")
    idle_timeout_minutes: int = Field(description="Session ends after this many idle minutes.")
    user: Me


class MeUpdate(PatchInput):
    """Own-profile edit (capability 19)."""

    non_nullable = frozenset({"full_name_en", "preferred_language"})

    full_name_en: str | None = Field(default=None, min_length=1, max_length=120)
    full_name_ar: str | None = Field(default=None, max_length=120)
    mobile: str | None = Field(default=None, pattern=MOBILE_PATTERN, description="E.164.")
    preferred_language: Language | None = None


class PasswordChangeRequest(StrictInput):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256, description=PASSWORD_DESCRIPTION)


class PrivacyNotice(ApiModel):
    version: str = Field(examples=["PN-1.0"])
    text_en: str
    text_ar: str


class PrivacyAckRequest(StrictInput):
    version: str = Field(description="Must equal the current notice version.")


class InvitationTokenRequest(StrictInput):
    token: str = Field(min_length=16, max_length=200, description="Token from the invite link.")


class InvitationInfo(ApiModel):
    email: str
    full_name_en: str
    full_name_ar: str | None
    preferred_language: Language
    expires_at: datetime
    privacy_notice: PrivacyNotice


class InvitationAcceptRequest(StrictInput):
    token: str = Field(min_length=16, max_length=200)
    password: str = Field(min_length=12, max_length=256, description=PASSWORD_DESCRIPTION)
    privacy_notice_version: str = Field(description="Acknowledged notice version.")
    preferred_language: Language | None = None


class PasswordResetRequest(StrictInput):
    email: EmailStr


class PasswordResetConfirm(StrictInput):
    token: str = Field(min_length=16, max_length=200)
    new_password: str = Field(min_length=12, max_length=256, description=PASSWORD_DESCRIPTION)


class AcceptedResponse(ApiModel):
    accepted: Literal[True] = True
    message: str = Field(description="Generic message; never reveals whether the email exists.")
