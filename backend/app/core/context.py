"""Per-request context (client IP, user agent, request id) for audit entries."""

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    ip_address: str | None = None
    user_agent: str | None = None
    request_id: str | None = None


_ctx: ContextVar[RequestContext] = ContextVar("request_ctx", default=RequestContext())  # noqa: B039


def get_request_context() -> RequestContext:
    return _ctx.get()


def set_request_context(ctx: RequestContext) -> None:
    _ctx.set(ctx)
