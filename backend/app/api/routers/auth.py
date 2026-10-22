"""Authentication, own profile, invitations, password reset, privacy notice (spec §5.1)."""

from fastapi import APIRouter, Response, status

from app.api.deps import DB, CurrentUser, MfaPendingUser, MfaSetupUser, SessionUser
from app.core.config import SESSION_COOKIE_NAME, get_settings
from app.core.errors import error_responses
from app.models import User
from app.schemas.auth import (
    AcceptedResponse,
    InvitationAcceptRequest,
    InvitationInfo,
    InvitationTokenRequest,
    LoginRequest,
    LoginResponse,
    Me,
    MeUpdate,
    MfaCodeRequest,
    MfaDisableRequest,
    MfaRecoveryCodes,
    MfaSetupStart,
    MfaStatus,
    MfaVerifyRequest,
    PasswordChangeRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    PrivacyAckRequest,
    PrivacyNotice,
    ReauthRequest,
    ReauthResponse,
)
from app.services import auth as svc
from app.services import mfa as mfa_svc
from app.services import users as user_svc

router = APIRouter(prefix="/auth", tags=["auth"])
public_router = APIRouter(tags=["auth"])


def _login_response(
    db: DB, response: Response, issued: svc.IssuedSession, user: User
) -> LoginResponse:
    s = get_settings()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        issued.token,
        max_age=s.session_absolute_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=s.cookie_secure,
        path="/",
    )
    pending = issued.session.mfa_pending
    return LoginResponse(
        access_token=issued.token,
        expires_at=issued.session.expires_at,
        idle_timeout_minutes=s.session_idle_minutes,
        mfa_pending=pending,
        user=None if pending else svc.me_for_user(db, user, issued.session),
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in with email and password",
    description="Sets the httpOnly `hse_session` cookie and returns the same JWT. Unknown email "
    "and wrong password give an identical 401 INVALID_CREDENTIALS. After 10 failures in 15 min "
    "the account is locked for 15 min (401 ACCOUNT_LOCKED). With two-step verification on, the "
    "response has `mfa_pending: true` and no user; finish with POST /auth/mfa/verify (D-299).",
    responses=error_responses(401, 422),
)
def login(body: LoginRequest, response: Response, db: DB) -> LoginResponse:
    issued, user = svc.login(db, body.email, body.password)
    return _login_response(db, response, issued, user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out (revokes the session, clears the cookie)",
    responses=error_responses(401),
)
def logout(user: MfaPendingUser, response: Response, db: DB) -> None:
    svc.logout(db, user)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT


@router.get(
    "/me",
    response_model=Me,
    summary="Current user with resolved roles and capabilities",
    responses=error_responses(401, 403),
)
def get_me(user: MfaSetupUser, db: DB) -> Me:
    return svc.build_me(db, user)


@router.patch(
    "/me",
    response_model=Me,
    summary="Edit own profile (name, mobile, language)",
    responses=error_responses(401, 403, 422),
)
def update_me(body: MeUpdate, user: CurrentUser, db: DB) -> Me:
    user_svc.update_me(db, user, body.changes())
    return svc.build_me(db, user)


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change own password",
    description="Other sessions of the user are revoked.",
    responses=error_responses(401, 403, 422),
)
def change_password(body: PasswordChangeRequest, user: CurrentUser, db: DB) -> None:
    svc.change_password(db, user, body.current_password, body.new_password)


@router.post(
    "/reauth",
    response_model=ReauthResponse,
    summary="Step-up re-authentication before signing (Phase 3 PT-15)",
    description="Wrong password → 401 REAUTH_REQUIRED (counts toward the login lockout). "
    "Signing endpoints return 401 REAUTH_REQUIRED when the last re-auth is older than "
    "step_up_reauth_minutes.",
    responses=error_responses(401, 403, 422, 429),
)
def reauthenticate(body: ReauthRequest, user: CurrentUser, db: DB) -> ReauthResponse:
    at, until = svc.reauthenticate(db, user, body.password)
    return ReauthResponse(reauthenticated_at=at, valid_until=until)


@router.post(
    "/privacy-notice/ack",
    response_model=Me,
    summary="Acknowledge the current privacy notice",
    description="Allowed before acknowledgement (rule 6). 409 PRIVACY_NOTICE_VERSION_MISMATCH "
    "if `version` is not the current one.",
    responses=error_responses(401, 409, 422),
)
def acknowledge_privacy_notice(body: PrivacyAckRequest, user: SessionUser, db: DB) -> Me:
    svc.acknowledge(db, user, body.version)
    return svc.build_me(db, user)


@router.post(
    "/invitations/validate",
    response_model=InvitationInfo,
    summary="Check an invite token (no auth)",
    description="404 INVITE_INVALID for unknown/used/superseded tokens; 410 INVITE_EXPIRED "
    "after 72 h.",
    responses=error_responses(404, 410, 422),
)
def validate_invitation(body: InvitationTokenRequest, db: DB) -> InvitationInfo:
    return svc.invitation_info(db, body.token)


@router.post(
    "/invitations/accept",
    response_model=LoginResponse,
    summary="Accept an invite: set password, acknowledge privacy notice, log in",
    responses=error_responses(404, 409, 410, 422),
)
def accept_invitation(body: InvitationAcceptRequest, response: Response, db: DB) -> LoginResponse:
    issued, user = svc.accept_invite(
        db, body.token, body.password, body.privacy_notice_version, body.preferred_language
    )
    return _login_response(db, response, issued, user)


@router.post(
    "/password-reset",
    response_model=AcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password reset email (always 202)",
    responses=error_responses(422),
)
def request_password_reset(body: PasswordResetRequest, db: DB) -> AcceptedResponse:
    svc.request_reset(db, body.email)
    return AcceptedResponse(
        message="If the account exists, a reset link has been sent to its email."
    )


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set a new password with a reset token (single use, 60 min)",
    responses=error_responses(404, 410, 422),
)
def confirm_password_reset(body: PasswordResetConfirm, db: DB) -> None:
    svc.confirm_reset(db, body.token, body.new_password)


@public_router.get(
    "/privacy-notice",
    response_model=PrivacyNotice,
    summary="Current privacy notice text (public)",
)
def get_privacy_notice() -> PrivacyNotice:
    return svc.privacy_notice()


# ---- two-step verification (D-299, D-300) --------------------------------------------------------
@router.post(
    "/mfa/verify",
    response_model=LoginResponse,
    summary="Second sign-in step: authenticator code or a recovery code",
    description="Accepts only a session from POST /auth/login with `mfa_pending: true`. Wrong "
    "codes give 401 MFA_CODE_INVALID and count toward the login lockout. A recovery code works "
    "once. Re-sets the cookie with the full session lifetime.",
    responses=error_responses(401, 409, 422),
)
def verify_mfa(
    body: MfaVerifyRequest, user: MfaPendingUser, response: Response, db: DB
) -> LoginResponse:
    issued = svc.complete_mfa(db, user, body.code, body.recovery_code)
    return _login_response(db, response, issued, user.user)


@router.get(
    "/mfa",
    response_model=MfaStatus,
    summary="Own two-step verification status",
    responses=error_responses(401, 403),
)
def mfa_status(user: MfaSetupUser, db: DB) -> MfaStatus:
    st = mfa_svc.state(user, start_grace=True)
    return MfaStatus(
        enabled=st.enabled,
        enabled_at=user.user.mfa_enabled_at,
        required=st.required,
        setup_due=st.setup_due,
        blocking=st.blocking,
        recovery_codes_remaining=mfa_svc.recovery_codes_left(db, user.user.id) if st.enabled else 0,
    )


@router.post(
    "/mfa/setup",
    response_model=MfaSetupStart,
    summary="Start set-up: a new secret and its otpauth:// URI for the QR code",
    description="The secret is active only after POST /auth/mfa/confirm with a valid code. "
    "409 MFA_ALREADY_ENABLED when it is on.",
    responses=error_responses(401, 403, 409),
)
def start_mfa_setup(user: MfaSetupUser, db: DB) -> MfaSetupStart:
    secret, uri = mfa_svc.start_setup(db, user)
    return MfaSetupStart(
        secret=secret, otpauth_uri=uri, issuer=get_settings().mfa_issuer, account=user.user.email
    )


@router.post(
    "/mfa/confirm",
    response_model=MfaRecoveryCodes,
    summary="Finish set-up with the first code; returns 10 recovery codes (shown once)",
    responses=error_responses(401, 403, 409, 422),
)
def confirm_mfa_setup(body: MfaCodeRequest, user: MfaSetupUser, db: DB) -> MfaRecoveryCodes:
    return MfaRecoveryCodes(codes=mfa_svc.confirm_setup(db, user, body.code))


@router.post(
    "/mfa/recovery-codes",
    response_model=MfaRecoveryCodes,
    summary="Replace the recovery codes (needs a current authenticator code)",
    description="The old codes stop working. A wrong code counts toward the login lockout.",
    responses=error_responses(401, 403, 409, 422),
)
def regenerate_recovery_codes(body: MfaCodeRequest, user: MfaSetupUser, db: DB) -> MfaRecoveryCodes:
    return MfaRecoveryCodes(codes=mfa_svc.regenerate_codes(db, user, body.code))


@router.post(
    "/mfa/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Turn two-step verification off (password and a current code)",
    description="409 MFA_REQUIRED_FOR_ROLE when the user's role needs it.",
    responses=error_responses(401, 403, 409, 422),
)
def disable_mfa(body: MfaDisableRequest, user: CurrentUser, db: DB) -> None:
    mfa_svc.disable(db, user, body.password, body.code)
