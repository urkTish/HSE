"""LLM client seam. `AnthropicClient` wraps the official SDK; tests install a fake with
`set_client_factory`. Responses are normalised to `LlmResponse` so the tool loop does not
depend on SDK types."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic

from app.core.config import get_settings
from app.core.errors import ApiError, ErrorCode

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AiUnavailable(Exception):  # noqa: N818
    """Provider not configured, unreachable, timed out or refused (AI-18)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class LlmBlock:
    type: str  # "text" | "tool_use"
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class LlmResponse:
    content: list[LlmBlock]
    stop_reason: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def text(self) -> str:
        return "".join(b.text for b in self.content if b.type == "text")

    @property
    def tool_uses(self) -> list[LlmBlock]:
        return [b for b in self.content if b.type == "tool_use"]

    def assistant_content(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for b in self.content:
            if b.type == "text" and b.text:
                out.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        return out


class LlmClient(Protocol):
    def create(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> LlmResponse: ...


class AnthropicClient:
    def __init__(self, api_key: str, timeout: float, fallbacks: bool) -> None:
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=1)
        self._fallbacks = fallbacks

    def create(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> LlmResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        try:
            if self._fallbacks:
                msg: Any = self._client.beta.messages.create(
                    betas=[FALLBACK_BETA], fallbacks="default", **kwargs
                )
            else:
                msg = self._client.messages.create(**kwargs)
        except anthropic.APITimeoutError as e:
            raise AiUnavailable("timeout") from e
        except anthropic.APIConnectionError as e:
            raise AiUnavailable("connection") from e
        except anthropic.APIStatusError as e:
            raise AiUnavailable(f"status_{e.status_code}") from e
        if msg.stop_reason == "refusal":
            raise AiUnavailable("refusal")
        blocks: list[LlmBlock] = []
        for b in msg.content:
            if b.type == "text":
                blocks.append(LlmBlock(type="text", text=b.text))
            elif b.type == "tool_use":
                blocks.append(
                    LlmBlock(type="tool_use", id=b.id, name=b.name, input=dict(b.input or {}))
                )
        return LlmResponse(
            content=blocks,
            stop_reason=str(msg.stop_reason),
            model=str(msg.model),
            input_tokens=int(msg.usage.input_tokens or 0),
            output_tokens=int(msg.usage.output_tokens or 0),
        )


def configured() -> bool:
    return bool((get_settings().anthropic_api_key or "").strip())


def _default_factory() -> LlmClient:
    s = get_settings()
    key = (s.anthropic_api_key or "").strip()
    if not key:
        raise AiUnavailable("no_api_key")
    return AnthropicClient(key, s.ai_timeout_seconds, s.ai_server_fallbacks)


_override: dict[str, Callable[[], LlmClient]] = {}


def set_client_factory(factory: Callable[[], LlmClient] | None) -> None:
    """Tests: install a fake client (None restores the SDK client)."""
    _override.clear()
    if factory is not None:
        _override["factory"] = factory


def available() -> bool:
    return bool(_override) or configured()


def get_client() -> LlmClient:
    return _override.get("factory", _default_factory)()


def unavailable_error(reason: str = "no_api_key") -> ApiError:
    msg = (
        "The AI assistant is not configured (no API key)."
        if reason == "no_api_key"
        else "The AI assistant is unavailable right now. The dashboard is unaffected."
    )
    return ApiError(503, ErrorCode.AI_UNAVAILABLE, msg, "المساعد الذكي غير متاح حالياً.")
