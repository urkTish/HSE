"""Shared FastAPI dependencies: DB session, authentication, pagination."""

import logging
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Query, Request, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.clock import now
from app.core.config import GATE_SESSION_COOKIE, SESSION_COOKIE_NAME, get_settings
from app.core.enums import UserStatus
from app.core.errors import ApiError, ErrorCode
from app.core.security import decode_jwt
from app.db.session import get_sessionmaker
from app.models import User, UserSession
from app.services import audit, mfa
from app.services.permissions import Principal, build_principal

cookie_scheme = APIKeyCookie(
    name=SESSION_COOKIE_NAME,
    auto_error=False,
    scheme_name="sessionCookie",
    description="httpOnly SameSite=Lax cookie set by POST /auth/login.",
)
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="bearerAuth",
    description="Same JWT as the cookie, as `Authorization: Bearer <token>`.",
)


def get_db() -> Iterator[Session]:
    """One transaction per request: commit on success, rollback on error. Audit entries
    queued with ``defer=True`` are persisted in both cases."""
    db = get_sessionmaker()()
    try:
        yield db
        from app.services.ptw import hooks as ptw_hooks  # noqa: PLC0415

        try:
            ptw_hooks.process(db)
        except Exception:
            logging.getLogger("hse.api").exception("ptw hook refresh failed")
        audit.flush_deferred(db)
        db.commit()
    except Exception:
        db.rollback()
        if db.info.get(audit.DEFERRED_KEY):
            try:
                audit.flush_deferred(db)
                db.commit()
            except Exception:  # pragma: no cover - never mask the original error
                db.rollback()
        raise
    finally:
        db.close()


DB = Annotated[Session, Depends(get_db, scope="function")]

_SLOTS: list[threading.BoundedSemaphore] = []
_SLOTS_LOCK = threading.Lock()


def cpu_slot() -> Iterator[None]:
    """Bound the heavy KPI / dashboard reads computing at once in this process. They are CPU
    bound and the GIL runs one at a time anyway; a dashboard opens ~25 of them together, and
    when all ran at once every short request (login, logout, a save) waited for the GIL after
    each database round trip and took 5-10 s. Waiting here does not hold the GIL."""
    with _SLOTS_LOCK:
        if not _SLOTS:
            _SLOTS.append(threading.BoundedSemaphore(max(1, get_settings().kpi_cpu_slots)))
        slots = _SLOTS[0]
    with slots:
        yield


CPU_SLOT = Depends(cpu_slot, scope="function")


@dataclass(frozen=True)
class RawToken:
    token: str


def gate_device_forbidden() -> ApiError:
    return ApiError(
        403,
        ErrorCode.GATE_DEVICE_FORBIDDEN,
        "A gate device session can only perform gate checks.",
        "جلسة جهاز البوابة مخصصة لعمليات التحقق فقط.",
    )


def raw_token(
    request: Request,
    cookie: Annotated[str | None, Security(cookie_scheme)] = None,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)] = None,
) -> RawToken:
    token = bearer.credentials if bearer else cookie
    if not token:
        if request.cookies.get(GATE_SESSION_COOKIE):
            raise gate_device_forbidden()  # GC-1: device sessions only reach gate checks
        raise ApiError(401, ErrorCode.UNAUTHENTICATED, "Not authenticated.", "غير مسجل الدخول.")
    return RawToken(token)


def _expired() -> ApiError:
    return ApiError(
        401,
        ErrorCode.SESSION_EXPIRED,
        "Your session has ended. Please log in again.",
        "انتهت الجلسة. يرجى تسجيل الدخول مرة أخرى.",
    )


def _authenticate(token: RawToken, db: Session, allow_mfa_pending: bool) -> Principal:
    """Authenticate the request (cookie or bearer) and enforce session rules (§5.1 rule 4, 7).
    A session still waiting for its two-step code (D-299) passes only where allowed."""
    claims = decode_jwt(token.token)
    if not claims:
        raise ApiError(401, ErrorCode.UNAUTHENTICATED, "Invalid token.", "رمز غير صالح.")
    if claims.get("typ") == "gate":
        raise gate_device_forbidden()
    try:
        sid = uuid.UUID(str(claims.get("sid")))
        uid = uuid.UUID(str(claims.get("sub")))
    except ValueError as exc:
        raise ApiError(401, ErrorCode.UNAUTHENTICATED, "Invalid token.") from exc
    session = db.get(UserSession, sid)
    current = now()
    s = get_settings()
    if (
        session is None
        or session.user_id != uid
        or session.revoked_at is not None
        or session.expires_at <= current
        or session.last_seen_at + timedelta(minutes=s.session_idle_minutes) <= current
    ):
        raise _expired()
    user = db.get(User, uid)
    if user is None or user.status != UserStatus.active:
        raise _expired()
    if session.mfa_pending and not allow_mfa_pending:
        raise mfa.mfa_required_error()
    if current - session.last_seen_at > timedelta(seconds=30):
        session.last_seen_at = current
    return build_principal(db, user, session)


def get_principal(token: Annotated[RawToken, Depends(raw_token)], db: DB) -> Principal:
    return _authenticate(token, db, allow_mfa_pending=False)


def get_mfa_pending_principal(token: Annotated[RawToken, Depends(raw_token)], db: DB) -> Principal:
    """Also accepts a session that still needs its code (POST /auth/mfa/verify, logout)."""
    return _authenticate(token, db, allow_mfa_pending=True)


SessionUser = Annotated[Principal, Depends(get_principal)]
MfaPendingUser = Annotated[Principal, Depends(get_mfa_pending_principal)]


def get_privacy_acked_principal(p: SessionUser) -> Principal:
    """Rule 6: nothing but privacy-notice ack and logout until the notice is acknowledged."""
    if p.user.privacy_notice_version != get_settings().privacy_notice_version:
        raise ApiError(
            403,
            ErrorCode.PRIVACY_ACK_REQUIRED,
            "Please acknowledge the privacy notice first.",
            "يرجى الإقرار بإشعار الخصوصية أولاً.",
        )
    return p


MfaSetupUser = Annotated[Principal, Depends(get_privacy_acked_principal)]
"""Signed in and privacy acknowledged, two-step set-up possibly overdue: /auth/me and the MFA
set-up endpoints only."""


def get_acked_principal(p: MfaSetupUser) -> Principal:
    """D-299: a user whose role needs MFA and whose grace period is over reaches nothing but the
    set-up until they enrol."""
    if mfa.state(p).blocking:
        raise mfa.enrolment_required()
    return p


CurrentUser = Annotated[Principal, Depends(get_acked_principal)]


@dataclass(frozen=True)
class Pagination:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination(
    page: Annotated[int, Query(ge=1, description="1-based page number.")] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, description="Items per page.")] = 50,
) -> Pagination:
    return Pagination(page, page_size)


PageParams = Annotated[Pagination, Depends(pagination)]
