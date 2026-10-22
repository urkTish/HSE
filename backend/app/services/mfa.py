"""Two-step verification with TOTP (RFC 6238) and single-use recovery codes (D-299, D-300).

Who must enrol is a setting (`MFA_REQUIRED_ROLES`, default `hse_manager,admin`; `admin` means the
PROJECT_DELETE_EMAILS administrators). A user who must enrol and has not gets `MFA_GRACE_DAYS`
from the first time the rule applied to them (`users.mfa_required_since`); after that every API
except the enrolment screens, `/auth/me`, privacy ack and logout answers 403
MFA_ENROLMENT_REQUIRED. Everyone else may turn MFA on (and off again) from their profile.

Codes: SHA-1, 6 digits, 30 s steps, one step of drift either way, and a code (time step) is never
accepted twice. Time comes from `app.core.clock.now()`, so a pinned test clock applies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.clock import now
from app.core.config import get_settings, project_deleters
from app.core.enums import AuditAction, EntityType, Role
from app.core.errors import ApiError, ErrorCode
from app.core.security import token_digest, verify_password
from app.models import User, UserRecoveryCode
from app.services import audit
from app.services.permissions import Principal

STEP_SECONDS = 30
DIGITS = 6
DRIFT_STEPS = 1
RECOVERY_CODES = 10
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i


# ---- TOTP primitives -----------------------------------------------------------------------------


def new_secret() -> str:
    """160-bit secret, base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    pad = "=" * (-len(secret) % 8)
    return base64.b32decode(secret.upper() + pad)


def code_at(secret: str, step: int) -> str:
    mac = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[off : off + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def step_of(at: datetime) -> int:
    return int(at.timestamp()) // STEP_SECONDS


def current_code(secret: str, at: datetime | None = None) -> str:
    return code_at(secret, step_of(at or now()))


def match_step(secret: str, code: str, last_step: int | None, at: datetime | None = None) -> int:
    """The time step the code belongs to, or -1 (wrong, expired or already used)."""
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != DIGITS:
        return -1
    centre = step_of(at or now())
    for step in range(centre - DRIFT_STEPS, centre + DRIFT_STEPS + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(code_at(secret, step), code):
            return step
    return -1


def otpauth_uri(secret: str, account: str) -> str:
    issuer = get_settings().mfa_issuer
    label = quote(f"{issuer}:{account}")
    query = urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "digits": DIGITS,
            "period": STEP_SECONDS,
            "algorithm": "SHA1",
        }
    )
    return f"otpauth://totp/{label}?{query}"


def _normalise_recovery(code: str) -> str:
    return "".join(ch for ch in code.lower() if ch.isalnum())


def _new_recovery_code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"


# ---- who must enrol ------------------------------------------------------------------------------


def required_roles() -> frozenset[str]:
    raw = get_settings().mfa_required_roles
    return frozenset(r.strip().lower() for r in raw.split(",") if r.strip())


def is_required(p: Principal) -> bool:
    roles = required_roles()
    if not roles:
        return False
    if "admin" in roles and p.user.email.lower() in project_deleters():
        return True
    if Role.hse_manager.value in roles and p.is_manager:
        return True
    return any(r.value in roles for s in p.projects.values() for r in s.roles)


@dataclass(frozen=True)
class MfaState:
    enabled: bool
    required: bool
    setup_due: datetime | None
    blocking: bool


def state(p: Principal, start_grace: bool = False) -> MfaState:
    """MFA position of the signed-in user. With `start_grace`, the grace clock starts the first
    time the rule applies (the caller's transaction persists it)."""
    u = p.user
    required = is_required(p)
    if not required or u.mfa_enabled:
        return MfaState(u.mfa_enabled, required, None, False)
    if u.mfa_required_since is None:
        if not start_grace:
            return MfaState(False, True, None, False)
        u.mfa_required_since = now()
    due = u.mfa_required_since + timedelta(days=get_settings().mfa_grace_days)
    return MfaState(False, True, due, now() >= due)


def enrolment_required() -> ApiError:
    return ApiError(
        403,
        ErrorCode.MFA_ENROLMENT_REQUIRED,
        "Your role needs two-step verification. Set it up to continue.",
        "يتطلب دورك التحقق بخطوتين. يرجى إعداده للمتابعة.",
    )


def mfa_required_error() -> ApiError:
    return ApiError(
        401,
        ErrorCode.MFA_REQUIRED,
        "Enter the code from your authenticator app to finish signing in.",
        "أدخل الرمز من تطبيق المصادقة لإكمال تسجيل الدخول.",
    )


def _bad_code(status: int = 422) -> ApiError:
    return ApiError(
        status,
        ErrorCode.MFA_CODE_INVALID,
        "The code is not valid. Check the time on your phone and try the newest code.",
        "الرمز غير صالح. تحقق من وقت هاتفك وجرّب أحدث رمز.",
    )


def _record(db: Session, p: Principal, change: str, **details: object) -> None:
    audit.record(
        db,
        AuditAction.mfa_changed,
        p.actor(),
        entity_type=EntityType.user,
        entity_id=p.user.id,
        details={"change": change, **details},
    )


def _secret(u: User) -> str | None:
    return crypto.decrypt(u.mfa_secret_enc) if u.mfa_secret_enc else None


def _check_totp(u: User, code: str) -> bool:
    secret = _secret(u)
    if secret is None:
        return False
    step = match_step(secret, code, u.mfa_last_step)
    if step < 0:
        return False
    u.mfa_last_step = step
    return True


def _replace_recovery_codes(db: Session, u: User) -> list[str]:
    db.execute(
        update(UserRecoveryCode)
        .where(UserRecoveryCode.user_id == u.id, UserRecoveryCode.used_at.is_(None))
        .values(used_at=now())
    )
    codes = [_new_recovery_code() for _ in range(RECOVERY_CODES)]
    for c in codes:
        db.add(UserRecoveryCode(user_id=u.id, code_hash=token_digest(_normalise_recovery(c))))
    db.flush()
    return codes


def recovery_codes_left(db: Session, user_id: object) -> int:
    return len(
        list(
            db.scalars(
                select(UserRecoveryCode.id).where(
                    UserRecoveryCode.user_id == user_id, UserRecoveryCode.used_at.is_(None)
                )
            )
        )
    )


# ---- enrolment -----------------------------------------------------------------------------------


def start_setup(db: Session, p: Principal) -> tuple[str, str]:
    """A new secret waits for its first code; calling again replaces it."""
    u = p.user
    if u.mfa_enabled:
        raise ApiError(
            409,
            ErrorCode.MFA_ALREADY_ENABLED,
            "Two-step verification is already on.",
            "التحقق بخطوتين مفعّل مسبقًا.",
        )
    secret = new_secret()
    u.mfa_pending_secret_enc = crypto.encrypt(secret)
    db.flush()
    return secret, otpauth_uri(secret, u.email)


def confirm_setup(db: Session, p: Principal, code: str) -> list[str]:
    u = p.user
    if u.mfa_enabled:
        raise ApiError(
            409,
            ErrorCode.MFA_ALREADY_ENABLED,
            "Two-step verification is already on.",
            "التحقق بخطوتين مفعّل مسبقًا.",
        )
    if not u.mfa_pending_secret_enc:
        raise ApiError(
            409,
            ErrorCode.MFA_SETUP_NOT_STARTED,
            "Start the set-up again: no QR code is waiting for a code.",
            "ابدأ الإعداد من جديد: لا يوجد رمز QR بانتظار التأكيد.",
        )
    secret = crypto.decrypt(u.mfa_pending_secret_enc)
    step = match_step(secret, code, None)
    if step < 0:
        raise _bad_code()
    u.mfa_secret_enc = u.mfa_pending_secret_enc
    u.mfa_pending_secret_enc = None
    u.mfa_enabled = True
    u.mfa_enabled_at = now()
    u.mfa_last_step = step
    codes = _replace_recovery_codes(db, u)
    if p.session is not None:
        p.session.mfa_pending = False
    _record(db, p, "enabled")
    return codes


def regenerate_codes(db: Session, p: Principal, code: str) -> list[str]:
    from app.services.auth import record_failed_password  # noqa: PLC0415

    u = p.user
    if not u.mfa_enabled:
        raise ApiError(
            409,
            ErrorCode.MFA_NOT_ENABLED,
            "Two-step verification is off.",
            "التحقق بخطوتين غير مفعّل.",
        )
    if not _check_totp(u, code):
        record_failed_password(u.id, "mfa_wrong_code")
        raise _bad_code()
    codes = _replace_recovery_codes(db, u)
    _record(db, p, "recovery_codes_regenerated")
    return codes


def disable(db: Session, p: Principal, password: str, code: str) -> None:
    from app.services.auth import record_failed_password  # noqa: PLC0415

    u = p.user
    if not u.mfa_enabled:
        raise ApiError(
            409,
            ErrorCode.MFA_NOT_ENABLED,
            "Two-step verification is off.",
            "التحقق بخطوتين غير مفعّل.",
        )
    if is_required(p):
        raise ApiError(
            409,
            ErrorCode.MFA_REQUIRED_FOR_ROLE,
            "Your role needs two-step verification, so it cannot be turned off.",
            "يتطلب دورك التحقق بخطوتين، لذا لا يمكن إيقافه.",
        )
    if not verify_password(password, u.password_hash):
        record_failed_password(u.id, "mfa_disable_wrong_password")
        raise ApiError(
            422,
            ErrorCode.CURRENT_PASSWORD_INCORRECT,
            "Current password is incorrect.",
            "كلمة المرور الحالية غير صحيحة.",
        )
    if not _check_totp(u, code):
        record_failed_password(u.id, "mfa_wrong_code")
        raise _bad_code()
    _clear(db, u)
    _record(db, p, "disabled")


def _clear(db: Session, u: User) -> None:
    u.mfa_enabled = False
    u.mfa_enabled_at = None
    u.mfa_secret_enc = None
    u.mfa_pending_secret_enc = None
    u.mfa_last_step = None
    db.execute(
        update(UserRecoveryCode)
        .where(UserRecoveryCode.user_id == u.id, UserRecoveryCode.used_at.is_(None))
        .values(used_at=now())
    )


def admin_reset(db: Session, p: Principal, user: User) -> None:
    """A lost phone: an HSE Manager clears another user's MFA. The user signs in with their
    password and enrols again (a new grace period starts if their role needs MFA); their open
    sessions end."""
    from app.services.auth import revoke_sessions  # noqa: PLC0415

    _clear(db, user)
    user.mfa_required_since = None
    revoke_sessions(db, user.id, "mfa_reset")
    audit.record(
        db,
        AuditAction.mfa_changed,
        p.actor(),
        entity_type=EntityType.user,
        entity_id=user.id,
        details={"change": "reset_by_manager"},
    )


# ---- sign-in -------------------------------------------------------------------------------------


def verify_sign_in(db: Session, p: Principal, code: str | None, recovery_code: str | None) -> str:
    """Second step of sign-in. Returns the method used (`totp` or `recovery_code`). Wrong codes
    count toward the login lockout (§5.1 rule 3) and are written even though the request fails."""
    from app.services.auth import record_failed_password  # noqa: PLC0415

    u = p.user
    method = "totp"
    ok = False
    if code:
        ok = _check_totp(u, code)
    elif recovery_code:
        method = "recovery_code"
        digest = token_digest(_normalise_recovery(recovery_code))
        row = db.scalar(
            select(UserRecoveryCode).where(
                UserRecoveryCode.user_id == u.id,
                UserRecoveryCode.code_hash == digest,
                UserRecoveryCode.used_at.is_(None),
            )
        )
        if row is not None:
            row.used_at = now()
            ok = True
    if not ok:
        record_failed_password(u.id, f"mfa_wrong_{method}")
        raise _bad_code(401)
    if p.session is not None:
        p.session.mfa_pending = False
        p.session.last_authenticated_at = now()
    u.failed_login_count = 0
    u.failed_window_started_at = None
    u.last_login_at = now()
    if method == "recovery_code":
        db.flush()
        _record(db, p, "recovery_code_used", remaining=recovery_codes_left(db, u.id))
    return method
