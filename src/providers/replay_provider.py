"""
Assembly — Record & replay providers (demo-day fallback, fast regression).

Record mode wraps every provider handed out by the router and stores each
model request/response pair (keys excluded — only provider/model names,
messages, response content, and token counts) to a JSON file.

Replay mode serves those recorded responses back in order, with optional
simulated delays, so a full execution replays offline with no keys and no
network.

Ordering note: records form ONE global FIFO in call-completion order. A
replay reproduces the recording exactly when its calls arrive in the same
order, which holds for mock-speed runs; concurrent solves may interleave
differently on slow networks. Error records (timeouts, 429s, outages)
replay as the same failure shapes so retries/fallbacks follow the same
path they did when recorded.
"""

import asyncio
import collections
import copy
import dataclasses
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.core.logging_config import logger
from src.providers.base import AIProvider, ChatMessage, ProviderResponse
from src.providers.errors import (
    AuthError,
    BadResponse,
    ProviderDown,
    ProviderError,
    RateLimited,
)

RECORDING_VERSION = 1

# Exception type -> short record tag. Anything else records as "error".
_ERROR_TAGS: tuple[tuple[type, str], ...] = (
    (RateLimited, "rate_limit"),
    (AuthError, "auth_error"),
    (ProviderDown, "provider_down"),
    (BadResponse, "bad_response"),
    (TimeoutError, "timeout"),
)


class ReplayExhaustedError(Exception):
    """A replay run needed more model calls than the recording holds.

    This means the replayed code path diverged from the recorded one
    (different team, extra retries, new debate rounds). Failing loudly
    beats silently looping stale responses — especially on demo day.
    """


def classify_record_error(exc: BaseException) -> str:
    """Map an exception to its short recording tag."""
    for error_type, tag in _ERROR_TAGS:
        if isinstance(exc, error_type):
            return tag
    return "error"


def raise_recorded_error(provider_name: str, error: dict[str, Any]) -> None:
    """Re-raise a recorded failure with its original shape. Never returns."""
    message = str(error.get("message", "recorded provider failure"))
    tag = error.get("type", "error")
    if tag == "timeout":
        raise TimeoutError(message)
    if tag == "rate_limit":
        raise RateLimited(provider_name, message)
    if tag == "auth_error":
        raise AuthError(provider_name, message)
    if tag == "provider_down":
        raise ProviderDown(provider_name, message)
    if tag == "bad_response":
        raise BadResponse(provider_name, message)
    raise ProviderError(provider_name, message)


def response_to_record(response: ProviderResponse) -> dict[str, Any]:
    """Serialize a provider response for the recording file."""
    return {
        "content": response.content,
        "model": response.model,
        "provider": response.provider,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "total_tokens": response.total_tokens,
        "reasoning_tokens": response.reasoning_tokens,
        "finish_reason": response.finish_reason,
    }


def response_from_record(record: dict[str, Any]) -> ProviderResponse:
    """Rebuild a ProviderResponse from a recorded response dict."""
    body = record["response"]
    return ProviderResponse(
        content=body["content"],
        model=body.get("model", ""),
        provider=body.get("provider", ""),
        input_tokens=body.get("input_tokens", 0),
        output_tokens=body.get("output_tokens", 0),
        total_tokens=body.get("total_tokens", 0),
        reasoning_tokens=body.get("reasoning_tokens", 0),
        finish_reason=body.get("finish_reason", "stop"),
    )


def save_recording(
    path: str | Path,
    records: list[dict[str, Any]],
    question: str | None = None,
    time_budget_minutes: int | None = None,
) -> Path:
    """Write a recording file. Returns the resolved path."""
    resolved = Path(path)
    if resolved.parent != Path(".") and str(resolved.parent):
        resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": RECORDING_VERSION,
        "question": question,
        "time_budget_minutes": time_budget_minutes,
        "records": list(records),
    }
    resolved.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info(f"Replay  │ Saved {len(records)} recorded call(s) to {resolved}")
    return resolved


def load_recording(path: str | Path) -> dict[str, Any]:
    """Load and minimally validate a recording file."""
    resolved = Path(path)
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load recording {resolved}: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != RECORDING_VERSION:
        raise ValueError(
            f"unsupported recording {resolved}: expected version {RECORDING_VERSION}"
        )
    records = data.get("records")
    if not isinstance(records, list):
        raise TypeError(f"corrupt recording {resolved}: 'records' must be a list")
    for index, record in enumerate(records):
        if not isinstance(record, dict) or "messages" not in record:
            raise TypeError(f"corrupt recording {resolved}: record {index} invalid")
        if record.get("response") is None and record.get("error") is None:
            raise ValueError(
                f"corrupt recording {resolved}: record {index} has no response or error"
            )
    data["records"] = records
    return data


class RecordingProvider(AIProvider):
    """Decorator: records every generate() call, then behaves identically.

    Wraps any live provider. Records hold provider/model names, messages,
    response content, token counts, latency, and classified failures —
    never API keys (keys travel in headers, never in messages).
    """

    def __init__(
        self,
        inner: AIProvider,
        records: list[dict[str, Any]] | None = None,
        family: str = "",
    ) -> None:
        self._inner = inner
        self._records = records if records is not None else []
        self._family = family

    @property
    def provider_name(self) -> str:
        return self._inner.provider_name

    @property
    def records(self) -> list[dict[str, Any]]:
        """Recorded calls so far (shared list when constructed that way)."""
        return self._records

    @property
    def family(self) -> str:
        """Model family captured at wrap time (for replay fidelity)."""
        return self._family

    def save(
        self,
        path: str | Path,
        question: str | None = None,
        time_budget_minutes: int | None = None,
    ) -> Path:
        """Persist everything recorded so far to a JSON file."""
        return save_recording(
            path,
            self._records,
            question=question,
            time_budget_minutes=time_budget_minutes,
        )

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> ProviderResponse:
        started = time.perf_counter()
        try:
            response = await self._inner.generate(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        except Exception as exc:
            self._records.append(
                {
                    "provider": self.provider_name,
                    "model": model,
                    "family": self._family,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": m.role, "content": m.content} for m in messages
                    ],
                    "response": None,
                    "error": {
                        "type": classify_record_error(exc),
                        "message": str(exc),
                    },
                    "latency_ms": (time.perf_counter() - started) * 1000.0,
                }
            )
            raise
        self._records.append(
            {
                "provider": self.provider_name,
                "model": model,
                "family": self._family,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "response": response_to_record(response),
                "error": None,
                "latency_ms": (time.perf_counter() - started) * 1000.0,
            }
        )
        return response

    def is_available(self) -> bool:
        return self._inner.is_available()

    def get_available_models(self) -> list[str]:
        return self._inner.get_available_models()


class ReplayProvider(AIProvider):
    """Serves recorded responses back in call order. Offline, keyless.

    All instances built for one run share a single FIFO of records, so
    concurrent agents consume responses in recorded completion order.
    Set delay_scale=0.0 for instant (fast-regression) replay.
    """

    def __init__(
        self,
        records: collections.deque,
        provider_name: str = "replay",
        model: str = "replay-model",
        delay_scale: float = 1.0,
    ) -> None:
        self._records = records
        self._provider_name = provider_name
        self._model = model
        self.delay_scale = delay_scale
        self.calls: list[dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def remaining(self) -> int:
        """Records left in the shared queue."""
        return len(self._records)

    async def generate(
        self,
        messages: list[ChatMessage],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> ProviderResponse:
        _ = (messages, temperature, max_tokens, kwargs)  # replay is content-ordered
        try:
            record = self._records.popleft()
        except IndexError:
            raise ReplayExhaustedError(
                "replay ran out of recorded responses: the replayed code path "
                "made more model calls than the recording holds (extra debate "
                "round? extra retry?). Re-record, or check for divergence."
            ) from None
        self.calls.append(
            {"provider": record.get("provider"), "model": record.get("model")}
        )
        delay = (record.get("latency_ms") or 0.0) / 1000.0 * self.delay_scale
        if delay > 0:
            await asyncio.sleep(delay)
        error = record.get("error")
        if error is not None:
            raise_recorded_error(self._provider_name, error)
        return response_from_record(record)

    def is_available(self) -> bool:
        return True

    def get_available_models(self) -> list[str]:
        return [self._model]


def _wrap_decision(decision: Any, records: list[dict[str, Any]]) -> Any:
    """Swap a routing decision's provider for a recording wrapper.

    Preserves provider_name/model/family/role so attribution and diversity
    accounting behave exactly as the unwrapped run.
    """
    wrapped = RecordingProvider(
        decision.provider, records, family=getattr(decision, "family", "")
    )
    try:
        return dataclasses.replace(decision, provider=wrapped)
    except (TypeError, ValueError):
        clone = copy.copy(decision)
        clone.provider = wrapped
        return clone


class RecordingRouter:
    """Wraps a live router so every handed-out provider records its calls.

    Unknown attributes delegate to the inner router, so quota snapshots,
    capacity estimates, and availability checks keep working untouched.
    All wrapped providers share one records list (global call order).
    """

    def __init__(self, inner: Any, records: list[dict[str, Any]] | None = None):
        self._inner = inner
        self._records: list[dict[str, Any]] = records if records is not None else []

    @property
    def records(self) -> list[dict[str, Any]]:
        """All recorded calls so far, in completion order."""
        return self._records

    def save(
        self,
        path: str | Path,
        question: str | None = None,
        time_budget_minutes: int | None = None,
    ) -> Path:
        """Persist the recording to a JSON file."""
        return save_recording(
            path,
            self._records,
            question=question,
            time_budget_minutes=time_budget_minutes,
        )

    def __getattr__(self, name: str) -> Any:
        if name.startswith(("__", "_inner", "_records")):
            raise AttributeError(name)
        return getattr(self._inner, name)

    def _wrap(self, decision: Any) -> Any:
        return _wrap_decision(decision, self._records)

    def route(self, *args: Any, **kwargs: Any) -> Any:
        """Route one agent, wrapping the chosen provider for recording."""
        return self._wrap(self._inner.route(*args, **kwargs))

    def route_for_planning(self, *args: Any, **kwargs: Any) -> Any:
        """Route the planner call, wrapping the chosen provider."""
        return self._wrap(self._inner.route_for_planning(*args, **kwargs))

    def route_team(self, *args: Any, **kwargs: Any) -> Any:
        """Route a whole team, wrapping every chosen provider."""
        routing = self._inner.route_team(*args, **kwargs)
        try:
            routing.decisions = [self._wrap(d) for d in routing.decisions]
        except (AttributeError, TypeError):
            pass
        return routing

    def fallback_for(self, decision: Any, error: Exception) -> Any:
        """Fall back through the inner router, wrapping the replacement."""
        fallback = self._inner.fallback_for(decision, error)
        if fallback is None:
            return None
        return self._wrap(fallback)


class ReplayRouter:
    """Duck-typed router serving one recording across replay providers.

    All instances share a single FIFO, so responses come back in recorded
    completion order. Team roles spread round-robin over the recorded
    providers; families come from the recording so diversity accounting
    (same-family votes, critic separation) replays faithfully.
    """

    def __init__(
        self,
        records: list[dict[str, Any]],
        delay_scale: float = 1.0,
    ) -> None:
        self._queue: collections.deque = collections.deque(records)
        self._delay_scale = delay_scale
        self._providers: dict[str, ReplayProvider] = {}
        self._families: dict[str, str] = {}
        self._models: dict[str, str] = {}
        for record in records:
            name = str(record.get("provider", "replay"))
            if name not in self._providers:
                self._providers[name] = ReplayProvider(
                    self._queue,
                    provider_name=name,
                    model=str(record.get("model") or "replay-model"),
                    delay_scale=delay_scale,
                )
            family = str(record.get("family") or "")
            if family and name not in self._families:
                self._families[name] = family
            model = record.get("model")
            if model and name not in self._models:
                self._models[name] = str(model)
        if not self._providers:
            raise ValueError("cannot build a replay router: recording holds no calls")
        self._names = list(self._providers.keys())
        self._cursor = 0

    @classmethod
    def from_file(cls, path: str | Path, delay_scale: float = 1.0) -> "ReplayRouter":
        """Build a replay router straight from a recording file."""
        data = load_recording(path)
        return cls(data["records"], delay_scale=delay_scale)

    @property
    def remaining(self) -> int:
        """Recorded calls not yet consumed."""
        return len(self._queue)

    def _next_name(self) -> str:
        name = self._names[self._cursor % len(self._names)]
        self._cursor += 1
        return name

    def _decision(self, agent_type: str, name: str) -> SimpleNamespace:
        provider = self._providers[name]
        return SimpleNamespace(
            provider=provider,
            model=self._models.get(name, provider.get_available_models()[0]),
            provider_name=name,
            family=self._families.get(name, name),
            role=agent_type,
            reason="replay of recorded run",
        )

    def get_available_providers(self) -> list[str]:
        return list(self._names)

    def get_live_count(self) -> int:
        return len(self._names)

    def route(
        self,
        agent_type: str = "solver",
        problem_type: str = "general",
        complexity: str = "medium",
        time_budget_minutes: int = 5,
        prefer_provider: str | None = None,
        allowed_families: list | None = None,
    ) -> SimpleNamespace:
        """Route one agent, spreading across recorded providers.

        `allowed_families` is accepted and ignored: replay must reproduce
        the recorded run exactly, pins do not apply.
        """
        _ = (problem_type, complexity, time_budget_minutes, allowed_families)
        name = (
            prefer_provider if prefer_provider in self._providers else self._next_name()
        )
        return self._decision(agent_type, name)

    def route_for_planning(
        self, allowed_families: list | None = None
    ) -> SimpleNamespace:
        """The planner call is first in any recording: use provider zero."""
        _ = allowed_families  # replay reproduces the recording; pins N/A
        return self._decision("planner", self._names[0])

    def route_team(
        self,
        team: list,
        problem_type: str = "general",
        complexity: str = "medium",
        time_budget_minutes: int = 5,
        allowed_families: list | None = None,
    ) -> SimpleNamespace:
        """Route a team round-robin so roles spread like the original run."""
        _ = (problem_type, complexity, time_budget_minutes, allowed_families)
        decisions = [
            self._decision(
                spec.get("agent_type", "solver"), self._names[i % len(self._names)]
            )
            for i, spec in enumerate(team)
        ]
        return SimpleNamespace(
            decisions=decisions,
            warnings=[],
            degraded=False,
            families=sorted({d.family for d in decisions}),
        )


def replay_router_for(
    records: list[dict[str, Any]], delay_scale: float = 1.0
) -> ReplayRouter:
    """Build a replay router from in-memory records (tests, scripts)."""
    return ReplayRouter(records, delay_scale=delay_scale)
