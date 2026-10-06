"""A scripted stand-in for the Anthropic client (no API key in tests).

Each step is an `LlmResponse` or a callable ``(messages) -> LlmResponse``; the fake records
every request so tests can assert on what would have been sent to the provider.
"""

import copy
import json
from collections.abc import Callable
from typing import Any

from app.ai.client import AiUnavailable, LlmBlock, LlmResponse

Step = LlmResponse | Callable[[list[dict[str, Any]]], LlmResponse] | Exception


class FakeLlm:
    def __init__(self) -> None:
        self.steps: list[Step] = []
        self.calls: list[dict[str, Any]] = []
        self._n = 0

    def script(self, *steps: Step) -> "FakeLlm":
        self.steps = list(steps)
        self.calls = []
        return self

    def create(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> LlmResponse:
        self.calls.append(
            {
                "model": model,
                "system": system,
                "messages": copy.deepcopy(messages),
                "tools": [t["name"] for t in tools],
            }
        )
        if not self.steps:
            raise AssertionError("FakeLlm: no scripted step left")
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step(messages) if callable(step) else step

    def sent(self) -> str:
        """Everything that would have been sent to the provider, as one string."""
        return json.dumps(self.calls, ensure_ascii=False, default=str)


def use(name: str, **params: Any) -> LlmResponse:
    return LlmResponse(
        content=[LlmBlock(type="tool_use", id=f"toolu_{name}", name=name, input=params)],
        stop_reason="tool_use",
        model="fake-model",
        input_tokens=10,
        output_tokens=5,
    )


def say(text: str) -> LlmResponse:
    return LlmResponse(
        content=[LlmBlock(type="text", text=text)],
        stop_reason="end_turn",
        model="fake-model",
        input_tokens=10,
        output_tokens=5,
    )


def last_results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parsed tool results of the latest tool round."""
    for m in reversed(messages):
        if m["role"] == "user" and isinstance(m["content"], list):
            return [json.loads(b["content"]) for b in m["content"] if b["type"] == "tool_result"]
    return []


def all_results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parsed tool results of every tool round so far."""
    out = []
    for m in messages:
        if m["role"] == "user" and isinstance(m["content"], list):
            out += [json.loads(b["content"]) for b in m["content"] if b["type"] == "tool_result"]
    return out


def timeout() -> AiUnavailable:
    return AiUnavailable("timeout")
