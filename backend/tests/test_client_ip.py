"""Client IP behind a proxy (RequestContextMiddleware): X-Forwarded-For or CLIENT_IP_HEADER."""

import asyncio

from starlette.types import Message, Receive, Scope, Send

from app.core.context import get_request_context
from app.core.middleware import RequestContextMiddleware


def _ip(headers: dict[str, str], **kwargs: object) -> str | None:
    seen: list[str | None] = []

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(get_request_context().ip_address)

    mw = RequestContextMiddleware(app, **kwargs)  # type: ignore[arg-type]
    scope: Scope = {
        "type": "http",
        "client": ("172.18.0.5", 40000),
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(_: Message) -> None:
        return None

    asyncio.run(mw(scope, receive, send))
    return seen[0]


HEADERS = {"X-Forwarded-For": "10.9.9.9, 203.0.113.1", "CF-Connecting-IP": "203.0.113.7"}


def test_proxy_headers_ignored_unless_trusted() -> None:
    assert _ip(HEADERS) == "172.18.0.5"
    assert _ip(HEADERS, client_ip_header="cf-connecting-ip") == "172.18.0.5"


def test_trusted_proxy_uses_first_forwarded_for_by_default() -> None:
    assert _ip(HEADERS, trust_proxy=True) == "10.9.9.9"


def test_client_ip_header_wins_and_falls_back_when_absent() -> None:
    assert _ip(HEADERS, trust_proxy=True, client_ip_header="CF-Connecting-IP") == "203.0.113.7"
    only_xff = {"X-Forwarded-For": "198.51.100.4"}
    assert _ip(only_xff, trust_proxy=True, client_ip_header="cf-connecting-ip") == "198.51.100.4"
