"""Auth, session, profile and privacy-notice schemas (spec §3.6, §5.1)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import EmailStr, Field, model_validator

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
    mfa_required: bool = Field(
        default=False,
        description="D-299: the user's role needs two-step verification (MFA_REQUIRED_ROLES).",
    )
    mfa_setup_due: datetime | None = Field(
        default=None,
        description="Required but not enrolled: end of the grace period; null otherwise.",
    )
    mfa_setup_blocking: bool = Field(
        default=False,
        description="Grace period over: every API except the MFA set-up, /auth/me, privacy ack "
        "and logout answers 403 MFA_ENROLMENT_REQUIRED until the user enrols.",
    )
    last_login_at: datetime | None
    privacy_notice_version: str | None = Field(description="Version the user acknowledged.")
    privacy_notice_ack_at: datetime | None
    privacy_ack_required: bool = Field(
        description="True when the current notice version is not acknowledged. While true every "
        "API except privacy-notice ack and logout returns 403 PRIVACY_ACK_REQUIRED."
    )
    is_hse_manager: bool
    can_delete_projects: bool = Field(
        description="True for the platform administrator (PROJECT_DELETE_EMAILS): may delete "
        "projects and any other record (D-265, D-271)."
    )
    org_capabilities: list[Capability] = Field(
        description="Organisation-wide capabilities (from hse_manager); empty for other roles."
    )
    projects: list[ProjectAccess]
    role_assignments: list[RoleAssignmentRead] = Field(description="Active assignments only.")
    last_authenticated_at: datetime | None = Field(
        default=None,
        description="Phase 3 PT-15: last password entry in this session (login or re-auth).",
    )
    reauth_valid_until: datetime | None = Field(
        default=None,
        description="Signing actions need re-authentication until this moment "
        "(last_authenticated_at + step_up_reauth_minutes); null = re-auth needed now.",
    )


class ReauthRequest(StrictInput):
    """PT-15 step-up: re-enter the password before a signing action."""

    password: str = Field(min_length=1, max_length=128)


class ReauthResponse(ApiModel):
    reauthenticated_at: datetime
    valid_until: datetime = Field(
        description="Signing actions are accepted until this moment (step_up_reauth_minutes)."
    )


class LoginResponse(ApiModel):
    access_token: str = Field(description="JWT; same value as the hse_session cookie.")
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime = Field(description="Absolute session expiry (12 h after login).")
    idle_timeout_minutes: int = Field(description="Session ends after this many idle minutes.")
    mfa_pending: bool = Field(
        default=False,
        description="D-299: the password was right and the account uses two-step verification; "
        "send the code to POST /auth/mfa/verify within mfa_pending_minutes. Until then `user` is "
        "null and every other API answers 401 MFA_REQUIRED.",
    )
    user: Me | None = Field(description="Null while mfa_pending.")


# ---- two-step verification (D-299) ---------------------------------------------------------------
TOTP_CODE = Field(min_length=6, max_length=10, description="6-digit code from the authenticator.")


class MfaStatus(ApiModel):
    enabled: bool
    enabled_at: datetime | None
    required: bool = Field(description="The user's role needs two-step verification.")
    setup_due: datetime | None = Field(description="End of the grace period (required only).")
    blocking: bool = Field(description="Grace period over and not enrolled.")
    recovery_codes_remaining: int


class MfaSetupStart(ApiModel):
    secret: str = Field(description="Base32 secret for manual entry in the authenticator app.")
    otpauth_uri: str = Field(description="otpauth://totp/… URI for the QR code.")
    issuer: str
    account: str


class MfaCodeRequest(StrictInput):
    code: str = TOTP_CODE


class MfaVerifyRequest(StrictInput):
    """Exactly one of `code` and `recovery_code`."""

    code: str | None = Field(default=None, min_length=6, max_length=10)
    recovery_code: str | None = Field(
        default=None, min_length=8, max_length=20, description="One of the single-use codes."
    )

    @model_validator(mode="after")
    def _one(self) -> "MfaVerifyRequest":
        if bool(self.code) == bool(self.recovery_code):
            raise ValueError("Send either code or recovery_code.")
        return self


class MfaDisableRequest(StrictInput):
    password: str = Field(min_length=1, max_length=256)
    code: str = TOTP_CODE


class MfaRecoveryCodes(ApiModel):
    codes: list[str] = Field(description="Shown once; each works once. Older codes stop working.")


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
