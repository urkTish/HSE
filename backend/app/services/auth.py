"""Authentication, sessions, lockout, invitations, password reset, privacy notice (§5.1)."""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from importlib import resources

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.config import get_settings
from app.core.context import get_request_context
from app.core.enums import (
    AuditAction,
    AuditResult,
    Capability,
    EntityType,
    NotificationKind,
    UserStatus,
)
from app.core.errors import ApiError, ErrorCode, FieldError
from app.core.security import (
    encode_jwt,
    hash_password,
    new_token,
    password_problems,
    token_digest,
    verify_password,
)
from app.models import AuditEntry, TokenKind, User, UserSession, UserToken
from app.schemas.auth import (
    CapabilityGrant,
    InvitationInfo,
    Me,
    PrivacyNotice,
    ProjectAccess,
    RoleAssignmentRead,
)
from app.services import audit, notify
from app.services.audit import SYSTEM, AuditActor
from app.services.permissions import ROLE_RANK, Principal, build_principal, capability_list


def invalid_credentials() -> ApiError:
    return ApiError(
        401,
        ErrorCode.INVALID_CREDENTIALS,
        "Email or password is incorrect.",
        "البريد الإلكتروني أو كلمة المرور غير صحيحة.",
    )


@lru_cache
def privacy_notice() -> PrivacyNotice:
    data = json.loads(
        resources.files("app.data").joinpath("privacy_notice.json").read_text("utf-8")
    )
    data["version"] = get_settings().privacy_notice_version
    return PrivacyNotice(**data)


# ---- sessions --------------------------------------------------------------------------
@dataclass(frozen=True)
class IssuedSession:
    token: str
    session: UserSession


def create_session(db: Session, user: User) -> IssuedSession:
    s = get_settings()
    ctx = get_request_context()
    current = now()
    session = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        created_at=current,
        last_seen_at=current,
        expires_at=current + timedelta(hours=s.session_absolute_hours),
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
    )
    db.add(session)
    db.flush()
    return IssuedSession(encode_jwt(user.id, session.id, session.expires_at), session)


def revoke_sessions(
    db: Session, user_id: uuid.UUID, reason: str, except_id: uuid.UUID | None = None
) -> None:
    """Rule 7: revocation is checked on every request, so it is effective immediately."""
    stmt = update(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
    )
    if except_id:
        stmt = stmt.where(UserSession.id != except_id)
    db.execute(stmt.values(revoked_at=now(), revoked_reason=reason))


def invalidate_tokens(db: Session, user_id: uuid.UUID, kind: TokenKind | None = None) -> None:
    stmt = update(UserToken).where(
        UserToken.user_id == user_id,
        UserToken.used_at.is_(None),
        UserToken.superseded_at.is_(None),
    )
    if kind:
        stmt = stmt.where(UserToken.kind == kind)
    db.execute(stmt.values(superseded_at=now()))


def issue_token(
    db: Session, user: User, kind: TokenKind, created_by: uuid.UUID | None = None
) -> str:
    s = get_settings()
    invalidate_tokens(db, user.id, kind)
    raw = new_token()
    ttl = (
        timedelta(hours=s.invite_token_hours)
        if kind == TokenKind.invite
        else timedelta(minutes=s.reset_token_minutes)
    )
    db.add(
        UserToken(
            user_id=user.id,
            kind=kind,
            token_hash=token_digest(raw),
            expires_at=now() + ttl,
            created_by_user_id=created_by,
        )
    )
    db.flush()
    return raw


def send_invite(db: Session, user: User, created_by: uuid.UUID | None) -> str:
    raw = issue_token(db, user, TokenKind.invite, created_by)
    notify.send_email(
        db, user, "invite", link=notify.link(f"/invite?token={raw}", user.preferred_language)
    )
    return raw


def send_reset(db: Session, user: User) -> str:
    raw = issue_token(db, user, TokenKind.password_reset)
    notify.send_email(
        db,
        user,
        "password_reset",
        link=notify.link(f"/reset-password?token={raw}", user.preferred_language),
    )
    return raw


# ---- login / lockout -------------------------------------------------------------------
def _auto_unlock(db: Session, user: User, current: datetime) -> None:
    if user.status == UserStatus.locked and user.locked_until and user.locked_until <= current:
        user.status = UserStatus.active
        user.locked_until = None
        user.failed_login_count = 0
        user.failed_window_started_at = None
        audit.record(
            db,
            AuditAction.user_status_changed,
            SYSTEM,
            entity_type=EntityType.user,
            entity_id=user.id,
            before={"status": UserStatus.locked},
            after={"status": UserStatus.active},
            details={"reason": "lock period elapsed"},
        )


def _register_failure(db: Session, user: User, current: datetime) -> None:
    s = get_settings()
    window = timedelta(minutes=s.lockout_window_minutes)
    if user.failed_window_started_at is None or current - user.failed_window_started_at > window:
        user.failed_window_started_at = current
        user.failed_login_count = 1
    else:
        user.failed_login_count += 1
    if user.failed_login_count >= s.lockout_threshold:
        user.status = UserStatus.locked
        user.locked_until = current + timedelta(minutes=s.lockout_minutes)
        revoke_sessions(db, user.id, "locked")
        audit.record(
            db,
            AuditAction.account_locked,
            SYSTEM,
            entity_type=EntityType.user,
            entity_id=user.id,
            before={"status": UserStatus.active},
            after={"status": UserStatus.locked, "locked_until": user.locked_until},
            details={"failed_attempts": user.failed_login_count},
        )
        notify.send_email(db, user, "account_locked")
        notify.notify(
            db,
            [user.id],
            NotificationKind.account_locked,
            "Your account was locked",
            "تم قفل حسابك",
            entity_type=EntityType.user,
            entity_id=user.id,
        )
        locks_24h = db.scalar(
            select(func.count())
            .select_from(AuditEntry)
            .where(
                AuditEntry.action == AuditAction.account_locked,
                AuditEntry.entity_id == user.id,
                AuditEntry.occurred_at >= current - timedelta(hours=24),
            )
        )
        if (locks_24h or 0) >= 3:
            notify.notify(
                db,
                notify.managers(db),
                NotificationKind.account_locked,
                f"{user.full_name_en} was locked 3+ times in 24 h",
                f"تم قفل حساب {user.full_name_ar or user.full_name_en} 3 مرات أو أكثر خلال 24 ساعة",
                entity_type=EntityType.user,
                entity_id=user.id,
            )


def login(db: Session, email: str, password: str) -> tuple[IssuedSession, User]:
    """Rules 1-3. Failure paths commit their bookkeeping before raising."""
    email = email.strip().lower()
    current = now()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        verify_password(password, None)
        audit.record(
            db,
            AuditAction.login_failed,
            SYSTEM,
            result=AuditResult.failed,
            details={"email": email, "reason": "unknown_email"},
        )
        db.commit()
        raise invalid_credentials()
    _auto_unlock(db, user, current)
    ok = verify_password(password, user.password_hash)
    actor = AuditActor(user.id)
    if user.status != UserStatus.active or not ok:
        reason = user.status.value if user.status != UserStatus.active else "wrong_password"
        audit.record(
            db,
            AuditAction.login_failed,
            actor,
            entity_type=EntityType.user,
            entity_id=user.id,
            result=AuditResult.failed,
            details={"email": email, "reason": reason},
        )
        if user.status == UserStatus.active:
            _register_failure(db, user, current)
        locked = user.status == UserStatus.locked and ok
        db.commit()
        if locked:
            raise ApiError(
                401,
                ErrorCode.ACCOUNT_LOCKED,
                "Account locked after too many failed logins. Try again in 15 minutes.",
                "تم قفل الحساب بسبب محاولات فاشلة كثيرة. حاول مرة أخرى بعد 15 دقيقة.",
            )
        raise invalid_credentials()
    had_sessions = db.scalar(
        select(func.count()).select_from(UserSession).where(UserSession.user_id == user.id)
    )
    ctx = get_request_context()
    known = db.scalar(
        select(func.count())
        .select_from(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.ip_address == ctx.ip_address,
            UserSession.user_agent == ctx.user_agent,
        )
    )
    user.failed_login_count = 0
    user.failed_window_started_at = None
    user.last_login_at = current
    issued = create_session(db, user)
    if had_sessions and not known:
        notify.send_email(db, user, "new_login", ip=ctx.ip_address or "unknown")
    audit.record(
        db, AuditAction.login_success, actor, entity_type=EntityType.user, entity_id=user.id
    )
    return issued, user


def logout(db: Session, p: Principal) -> None:
    if p.session:
        p.session.revoked_at = now()
        p.session.revoked_reason = "logout"
    audit.record(
        db, AuditAction.logout, p.actor(), entity_type=EntityType.user, entity_id=p.user.id
    )


# ---- passwords -------------------------------------------------------------------------
def check_password(password: str, email: str, field: str = "password") -> None:
    problems = password_problems(password, email)
    if problems:
        msg = "Password " + "; ".join(problems) + "."
        raise ApiError(
            422,
            ErrorCode.WEAK_PASSWORD,
            msg,
            "كلمة المرور لا تستوفي السياسة.",
            errors=[FieldError(loc=["body", field], msg=p, type="weak_password") for p in problems],
        )


def change_password(db: Session, p: Principal, current_pw: str, new_pw: str) -> None:
    if not verify_password(current_pw, p.user.password_hash):
        raise ApiError(
            422,
            ErrorCode.CURRENT_PASSWORD_INCORRECT,
            "Current password is incorrect.",
            "كلمة المرور الحالية غير صحيحة.",
        )
    check_password(new_pw, p.user.email, "new_password")
    p.user.password_hash = hash_password(new_pw)
    revoke_sessions(
        db, p.user.id, "password_changed", except_id=p.session.id if p.session else None
    )
    audit.record(
        db,
        AuditAction.password_changed,
        p.actor(),
        entity_type=EntityType.user,
        entity_id=p.user.id,
    )


def _find_token(db: Session, raw: str, kind: TokenKind, invalid: ErrorCode) -> UserToken:
    tok = db.scalar(select(UserToken).where(UserToken.token_hash == token_digest(raw)))
    if tok is None or tok.kind != kind or tok.used_at or tok.superseded_at:
        raise ApiError(
            404, invalid, "This link is invalid or was already used.", "الرابط غير صالح."
        )
    if tok.expires_at <= now():
        code = ErrorCode.INVITE_EXPIRED if kind == TokenKind.invite else invalid
        raise ApiError(410, code, "This link has expired.", "انتهت صلاحية الرابط.")
    return tok


def validate_invite(db: Session, raw: str) -> tuple[UserToken, User]:
    tok = _find_token(db, raw, TokenKind.invite, ErrorCode.INVITE_INVALID)
    user = db.get(User, tok.user_id)
    if user is None or user.status != UserStatus.invited:
        raise ApiError(404, ErrorCode.INVITE_INVALID, "This invite is no longer valid.")
    return tok, user


def invitation_info(db: Session, raw: str) -> InvitationInfo:
    tok, user = validate_invite(db, raw)
    return InvitationInfo(
        email=user.email,
        full_name_en=user.full_name_en,
        full_name_ar=user.full_name_ar,
        preferred_language=user.preferred_language,
        expires_at=tok.expires_at,
        privacy_notice=privacy_notice(),
    )


def _check_notice_version(version: str) -> None:
    if version != get_settings().privacy_notice_version:
        raise ApiError(
            409,
            ErrorCode.PRIVACY_NOTICE_VERSION_MISMATCH,
            "The privacy notice has changed; please read the current version.",
            "تم تحديث إشعار الخصوصية؛ يرجى قراءة النسخة الحالية.",
        )


def _ack(db: Session, user: User, version: str) -> None:
    user.privacy_notice_version = version
    user.privacy_notice_ack_at = now()
    audit.record(
        db,
        AuditAction.privacy_notice_acknowledged,
        AuditActor(user.id),
        entity_type=EntityType.user,
        entity_id=user.id,
        after={"privacy_notice_version": version},
    )


def accept_invite(
    db: Session, raw: str, password: str, version: str, language: str | None
) -> tuple[IssuedSession, User]:
    tok, user = validate_invite(db, raw)
    check_password(password, user.email)
    _check_notice_version(version)
    current = now()
    tok.used_at = current
    user.password_hash = hash_password(password)
    user.status = UserStatus.active
    user.activated_at = current
    user.last_login_at = current
    if language:
        user.preferred_language = language  # type: ignore[assignment]
    actor = AuditActor(user.id)
    audit.record(
        db,
        AuditAction.user_status_changed,
        actor,
        entity_type=EntityType.user,
        entity_id=user.id,
        before={"status": UserStatus.invited},
        after={"status": UserStatus.active},
        details={"reason": "invite accepted"},
    )
    _ack(db, user, version)
    issued = create_session(db, user)
    audit.record(
        db, AuditAction.login_success, actor, entity_type=EntityType.user, entity_id=user.id
    )
    return issued, user


def acknowledge(db: Session, p: Principal, version: str) -> None:
    _check_notice_version(version)
    _ack(db, p.user, version)


def request_reset(db: Session, email: str) -> None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or user.status not in (UserStatus.active, UserStatus.locked):
        return
    send_reset(db, user)
    audit.record(
        db,
        AuditAction.password_reset_requested,
        AuditActor(user.id),
        entity_type=EntityType.user,
        entity_id=user.id,
    )


def confirm_reset(db: Session, raw: str, new_password: str) -> None:
    tok = _find_token(db, raw, TokenKind.password_reset, ErrorCode.RESET_TOKEN_INVALID)
    user = db.get(User, tok.user_id)
    if user is None or user.status not in (UserStatus.active, UserStatus.locked):
        raise ApiError(404, ErrorCode.RESET_TOKEN_INVALID, "This link is invalid.")
    check_password(new_password, user.email, "new_password")
    tok.used_at = now()
    user.password_hash = hash_password(new_password)
    revoke_sessions(db, user.id, "password_reset")
    audit.record(
        db,
        AuditAction.password_changed,
        AuditActor(user.id),
        entity_type=EntityType.user,
        entity_id=user.id,
        details={"via": "reset_link"},
    )


# ---- Me --------------------------------------------------------------------------------
def build_me(db: Session, p: Principal) -> Me:
    from app.services.users import assignment_read  # noqa: PLC0415  (avoid import cycle)

    projects: list[ProjectAccess] = []
    for scope in sorted(p.projects.values(), key=lambda s: s.project_code):
        site_sets = [set(a.site_ids) for a in scope.assignments]
        sites = None if any(not s for s in site_sets) else sorted(set().union(*site_sets))
        projects.append(
            ProjectAccess(
                project_id=scope.project_id,
                project_code=scope.project_code,
                roles=sorted(scope.roles, key=lambda r: ROLE_RANK[r]),
                capabilities=[
                    CapabilityGrant(capability=c, scope=g.scope) for c, g in capability_list(scope)
                ],
                site_ids=sites,
                contractor_engagement_ids=sorted(
                    {
                        a.contractor_engagement_id
                        for a in scope.assignments
                        if a.contractor_engagement_id
                    }
                ),
                read_only=scope.read_only,
            )
        )
    u = p.user
    current_version = get_settings().privacy_notice_version
    assignments: list[RoleAssignmentRead] = [
        assignment_read(a, p.today) for a in p.active_assignments
    ]
    return Me(
        id=u.id,
        email=u.email,
        full_name_en=u.full_name_en,
        full_name_ar=u.full_name_ar,
        mobile=u.mobile,
        employer_type=u.employer_type,
        employer_contractor_id=u.employer_contractor_id,
        job_title=u.job_title,
        preferred_language=u.preferred_language,
        display_language=u.preferred_language,
        status=u.status,
        mfa_enabled=u.mfa_enabled,
        last_login_at=u.last_login_at,
        privacy_notice_version=u.privacy_notice_version,
        privacy_notice_ack_at=u.privacy_notice_ack_at,
        privacy_ack_required=u.privacy_notice_version != current_version,
        is_hse_manager=p.is_manager,
        org_capabilities=list(Capability) if p.is_manager else [],
        projects=projects,
        role_assignments=assignments,
    )


def me_for_user(db: Session, user: User, session: UserSession | None) -> Me:
    return build_me(db, build_principal(db, user, session))
