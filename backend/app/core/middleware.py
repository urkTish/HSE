"""Pure-ASGI middleware that captures client IP, user agent and a request id."""

import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import RequestContext, set_request_context


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, trust_proxy: bool = False) -> None:
        self.app = app
        self.trust_proxy = trust_proxy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        ip = scope["client"][0] if scope.get("client") else None
        if self.trust_proxy and "x-forwarded-for" in headers:
            ip = headers["x-forwarded-for"].split(",")[0].strip()
        request_id = headers.get("x-request-id") or uuid.uuid4().hex
        set_request_context(
            RequestContext(
                ip_address=ip,
                user_agent=(headers.get("user-agent") or "")[:400] or None,
                request_id=request_id[:64],
            )
        )

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append(
                    (b"x-request-id", request_id[:64].encode("latin-1"))
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)
