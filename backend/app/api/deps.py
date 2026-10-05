"""Shared FastAPI dependencies: auth schemes, pagination."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import SESSION_COOKIE_NAME
from app.core.errors import ApiError, ErrorCode

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


@dataclass(frozen=True)
class RawToken:
    token: str


def raw_token(
    cookie: Annotated[str | None, Security(cookie_scheme)] = None,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)] = None,
) -> RawToken:
    token = bearer.credentials if bearer else cookie
    if not token:
        raise ApiError(401, ErrorCode.UNAUTHENTICATED, "Not authenticated.", "غير مسجل الدخول.")
    return RawToken(token)


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


def get_principal(token: Annotated[RawToken, Depends(raw_token)]) -> RawToken:
    """Resolves the authenticated user (stage 1 placeholder)."""
    return token


CurrentUser = Annotated[RawToken, Depends(get_principal)]
