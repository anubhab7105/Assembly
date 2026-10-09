"""
Assembly — Mock AI Provider (tests only).

A scripted in-memory implementation of the AIProvider interface.
Never touches the network. Responses are selected by matching markers
in the request messages against a scripts dict, so concurrent agent
calls stay deterministic regardless of completion order.

Supports fault injection for testing failure paths:
- "rate_limit": raise MockRateLimitError (HTTP 429 shape)
- "timeout": raise TimeoutError
- "malformed": return non-JSON content (exercises the text fallback)
- "tool_call": raise ToolCallError (native tool-call refusal shape)
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from src.providers.base import AIProvider, ChatMessage, ProviderResponse
from src.providers.errors import RateLimited, ToolCallError


class MockRateLimitError(RateLimited):
    """Simulated HTTP 429 rate-limit error (carries a status_code like httpx)."""

    def __init__(self, message: str = "Mock 429 rate limit exceeded") -> None:
        super().__init__("mock", message)
        self.status_code = 429


# (marker text, script key) — checked in order against system + user content.
# The researcher marker is the no-browsing rule from its system prompt
# (unique to that role; kept in sync with researcher.py by
# test_researcher_prompt_has_no_search_instructions).
_ROUTE_MARKERS: tuple[tuple[str, str], ...] = (
    ("Final Synthesizer", "synthesize"),
    ("You are the Planner", "plan"),
    ("find flaws", "critic"),
    ("NO web browsing", "researcher"),
    ("independently analyze and solve", "solver"),
)


def _default_scripts() -> dict[str, dict[str, Any]]:
    """Baseline scripts: every role returns valid, mutually agreeing JSON."""
    position = "The mock answer is 42."
    evidence = [
        {"claim": "Mock evidence point 1.", "source_id": "s1"},
        {"claim": "Mock evidence point 2.", "source_id": "s2"},
        {"claim": "Mock evidence point 3.", "source_id": ""},
    ]
    source = {
        "title": "Mock Source",
        "url": "https://example.com/mock",
        "snippet": "Mock excerpt supporting the answer.",
    }
    base = {
        "position": position,
        "confidence": 0.9,
        "reasoning_summary": "Mock reasoning summary.",
        "evidence": evidence,
        "supports": [],
        "disagrees_with": [],
        "remaining_uncertainty": ["Mock caveat."],
        "sources": [source],
    }
    return {
        "plan": {
            "problem_type": "general",
            "complexity": "medium",
            "needs_research": False,
            "team": [
                {"agent_type": "solver", "role_description": "Problem solver"},
                {"agent_type": "critic", "role_description": "Answer verifier"},
            ],
            "reasoning": "Mock plan.",
        },
        "solver": dict(base),
        "researcher": dict(base),
        "critic": dict(base),
        "synthesize": {
            **base,
            "position": "FINAL MOCK ANSWER: the mock answer is 42, verified by the team.",
            "confidence": 0.92,
        },
        "default": dict(base),
    }


class MockProvider(AIProvider):
    """
    Scripted test double for AIProvider.

    Args:
        scripts: script key → JSON-serializable response body (or raw string).
        latency_seconds: simulated per-call latency (async sleep, no network).
        input_tokens / output_tokens: fake usage reported on every response.
        fail_next: script key → fault applied once, then popped
            ("rate_limit" | "timeout" | "malformed" | "tool_call").
        always_fail: script key → fault applied on every matching call.
        provider_name / model: identity reported in responses and routing.
    """

    provider_name: str = "mock"

    def __init__(
        self,
        scripts: dict[str, dict[str, Any] | str] | None = None,
        latency_seconds: float = 0.0,
        input_tokens: int = 10,
        output_tokens: int = 20,
        reasoning_tokens: int = 0,
        fail_next: dict[str, str] | None = None,
        always_fail: dict[str, str] | None = None,
        provider_name: str = "mock",
        model: str = "mock-model",
    ) -> None:
        self.provider_name = provider_name
        self._model = model
        self._scripts: dict[str, dict[str, Any] | str] = (
            dict(scripts) if scripts else _default_scripts()
        )
        self.latency_seconds = latency_seconds
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.reasoning_tokens = reasoning_tokens
        self.fail_next: dict[str, str] = dict(fail_next or {})
        self.always_fail: dict[str, str] = dict(always_fail or {})
        self.calls: list[dict[str, Any]] = []

    @classmethod
    def from_fixture(cls, path: str | Path, **kwargs: Any) -> "MockProvider":
        """Build a MockProvider from a JSON fixture file.

        Fixture shape: {"scripts": {...}, "latency_seconds": 0.0,
        "input_tokens": 10, "output_tokens": 20, "reasoning_tokens": 0,
        "always_fail": {...}}.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        merged: dict[str, Any] = {
            "scripts": data.get("scripts"),
            "latency_seconds": data.get("latency_seconds", 0.0),
            "input_tokens": data.get("input_tokens", 10),
            "output_tokens": data.get("output_tokens", 20),
            "reasoning_tokens": data.get("reasoning_tokens", 0),
            "fail_next": data.get("fail_next"),
            "always_fail": data.get("always_fail"),
        }
        merged.update(kwargs)
        scripts = merged.pop("scripts")
        return cls(
            scripts=scripts,
            latency_seconds=merged.get("latency_seconds", 0.0),
            input_tokens=merged.get("input_tokens", 10),
            output_tokens=merged.get("output_tokens", 20),
            reasoning_tokens=merged.get("reasoning_tokens", 0),
            fail_next=merged.get("fail_next"),
            always_fail=merged.get("always_fail"),
            provider_name=merged.get("provider_name", "mock"),
            model=merged.get("model", "mock-model"),
        )

    def select_script_key(self, messages: list[ChatMessage]) -> str:
        """Pick a script key from request content (deterministic under concurrency)."""
        text = "\n".join(m.content for m in messages)
        for marker, key in _ROUTE_MARKERS:
            if marker in text:
                return key
        return "default" if "default" in self._scripts else "solver"

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> ProviderResponse:
        key = self.select_script_key(messages)
        self.calls.append({"script_key": key, "model": model or self._model})

        if self.latency_seconds > 0:
            await asyncio.sleep(self.latency_seconds)

        fault = self.fail_next.pop(key, None) or self.always_fail.get(key)
        if fault == "rate_limit":
            raise MockRateLimitError(f"Mock 429 on script '{key}'")
        if fault == "timeout":
            raise TimeoutError(f"Mock timeout on script '{key}'")
        if fault == "tool_call":
            raise ToolCallError(
                self.provider_name,
                "Mock tool-use failure on script "
                f"'{key}': Tool choice is none, but model called a tool",
            )
        if fault == "malformed":
            content = "this is not JSON, just plain text"
        else:
            body = self._scripts.get(key, self._scripts.get("default", {}))
            content = body if isinstance(body, str) else json.dumps(body)

        total = self.input_tokens + self.output_tokens
        return ProviderResponse(
            content=content,
            model=model or self._model,
            provider=self.provider_name,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            total_tokens=total,
            reasoning_tokens=self.reasoning_tokens,
        )

    def is_available(self) -> bool:
        return True

    def get_available_models(self) -> list[str]:
        return [self._model]
