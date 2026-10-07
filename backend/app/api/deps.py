"""Shared FastAPI dependencies: DB session, authentication, pagination."""

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
from app.services import audit
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


def get_principal(token: Annotated[RawToken, Depends(raw_token)], db: DB) -> Principal:
    """Authenticate the request (cookie or bearer) and enforce session rules (§5.1 rule 4, 7)."""
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
    if current - session.last_seen_at > timedelta(seconds=30):
        session.last_seen_at = current
    return build_principal(db, user, session)


SessionUser = Annotated[Principal, Depends(get_principal)]


def get_acked_principal(p: SessionUser) -> Principal:
    """Rule 6: nothing but privacy-notice ack and logout until the notice is acknowledged."""
    if p.user.privacy_notice_version != get_settings().privacy_notice_version:
        raise ApiError(
            403,
            ErrorCode.PRIVACY_ACK_REQUIRED,
            "Please acknowledge the privacy notice first.",
            "يرجى الإقرار بإشعار الخصوصية أولاً.",
        )
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
