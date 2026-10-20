"""Pure-ASGI middleware that captures client IP, user agent and a request id."""

import json
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import RequestContext, set_request_context

MAX_BODY_BYTES = 64 * 1024 * 1024  # uploads are capped at 20 MB; photos in JSON at ~5 MB each


async def _too_large(send: Send) -> None:
    body = json.dumps(
        {
            "detail": {
                "code": "FILE_TOO_LARGE",
                "message": "Request body too large.",
                "message_ar": "حجم الطلب كبير جدًا.",
            }
        },
        ensure_ascii=False,
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, trust_proxy: bool = False) -> None:
        self.app = app
        self.trust_proxy = trust_proxy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if (headers.get("content-length") or "0").isdigit() and int(
            headers.get("content-length") or 0
        ) > MAX_BODY_BYTES:
            await _too_large(send)
            return
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
