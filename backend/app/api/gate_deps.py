"""Authentication for gate-check endpoints (spec 2-access-permits GC-1): a logged-in user with
capability 74, or a registered gate-device session bound to one gate."""

from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials

from app.api.deps import (
    DB,
    RawToken,
    bearer_scheme,
    cookie_scheme,
    gate_device_forbidden,
    get_acked_principal,
    get_principal,
)
from app.core.access_enums import GateCallerKind
from app.core.enums import Capability
from app.core.errors import ApiError, ErrorCode
from app.core.security import decode_jwt
from app.services.access import gates
from app.services.permissions import forbidden_error

GATE_SESSION_COOKIE = "hse_gate_session"

gate_cookie_scheme = APIKeyCookie(
    name=GATE_SESSION_COOKIE,
    auto_error=False,
    scheme_name="gateSessionCookie",
    description="httpOnly cookie set by POST /gate-device/login (gate-check endpoints only).",
)


GateCaller = gates.Caller


def get_gate_caller(
    db: DB,
    cookie: Annotated[str | None, Security(cookie_scheme)] = None,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)] = None,
    gate_cookie: Annotated[str | None, Security(gate_cookie_scheme)] = None,
) -> GateCaller:
    """GC-1: a gate-device session (bearer or `hse_gate_session` cookie) or a logged-in user
    holding capability 74 somewhere (the gate itself is checked per request)."""
    token = bearer.credentials if bearer else (gate_cookie or cookie)
    if not token:
        raise ApiError(401, ErrorCode.UNAUTHENTICATED, "Not authenticated.", "غير مسجل الدخول.")
    claims = decode_jwt(token)
    if claims and claims.get("typ") == "gate":
        if claims.get("kind") in ("weather_station", "muster_reader"):
            raise gate_device_forbidden()  # 6b HS-4 / 6c §11.3: not gate devices
        return gates.device_caller(db, claims)
    if not bearer and cookie is None and gate_cookie:
        raise ApiError(401, ErrorCode.UNAUTHENTICATED, "Invalid token.", "رمز غير صالح.")
    p = get_acked_principal(get_principal(RawToken(token), db))
    if not p.has_any(Capability.gate_check):
        raise forbidden_error()
    return GateCaller(GateCallerKind.user, p, None, None)


GateCallerDep = Annotated[GateCaller, Depends(get_gate_caller)]
