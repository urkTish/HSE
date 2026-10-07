"""Authentication for gate-check endpoints (spec 2-access-permits GC-1): a logged-in user with
capability 74, or a registered gate-device session bound to one gate."""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials

from app.api.deps import DB, bearer_scheme, cookie_scheme
from app.core.access_enums import GateCallerKind
from app.core.errors import not_implemented
from app.services.permissions import Principal

GATE_SESSION_COOKIE = "hse_gate_session"

gate_cookie_scheme = APIKeyCookie(
    name=GATE_SESSION_COOKIE,
    auto_error=False,
    scheme_name="gateSessionCookie",
    description="httpOnly cookie set by POST /gate-device/login (gate-check endpoints only).",
)


@dataclass(frozen=True)
class GateCaller:
    kind: GateCallerKind
    principal: Principal | None
    device_pk: uuid.UUID | None
    gate_id: uuid.UUID | None


def get_gate_caller(
    db: DB,
    cookie: Annotated[str | None, Security(cookie_scheme)] = None,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)] = None,
    gate_cookie: Annotated[str | None, Security(gate_cookie_scheme)] = None,
) -> GateCaller:
    raise not_implemented()


GateCallerDep = Annotated[GateCaller, Depends(get_gate_caller)]
