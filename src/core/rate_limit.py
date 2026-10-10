"""Assembly — abuse protection without accounts (per-IP rate limits)."""

import asyncio
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from src.core.config import settings

_rate_limit_history: dict[tuple[str, str], list[float]] = defaultdict(list)
_rate_limit_lock = asyncio.Lock()

_global_executions = 0
_ip_executions: dict[str, int] = defaultdict(int)

MAX_GLOBAL_EXECUTIONS = 50
MAX_RUNS_PER_IP = 2


def _forwarded_chain(request: Request) -> list[str]:
    """Client-claimed proxy chain, leftmost (original) first.

    Prefers X-Forwarded-For; falls back to RFC 7239 Forwarded ``for=``
    entries. Returns [] when neither header is present. Values are
    untrusted input — only used when TRUSTED_PROXY_COUNT > 0.
    """
    xff = request.headers.get("x-forwarded-for", "")
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if parts:
        return parts
    out: list[str] = []
    for segment in request.headers.get("forwarded", "").split(","):
        for pair in segment.split(";"):
            name, _, value = pair.partition("=")
            if name.strip().lower() == "for" and value.strip():
                out.append(value.strip().strip('"').strip("[]"))
    return out


def client_ip(request: Request) -> str:
    """Best-effort client IP for rate-limit buckets.

    The forwarded chain is honored ONLY when TRUSTED_PROXY_COUNT > 0
    (N trusted hops: the Nth address from the right; a shorter chain
    falls back to its leftmost entry). With the default 0, forwarded
    headers are ignored outright so spoofed values cannot move a client
    into another bucket.
    """
    try:
        trusted = max(0, int(settings.trusted_proxy_count or 0))
    except (TypeError, ValueError):
        trusted = 0
    if trusted > 0:
        chain = _forwarded_chain(request)
        if chain:
            if len(chain) >= trusted:
                return chain[-trusted]
            return chain[0]
    return request.client.host if request.client else "unknown"


async def count_invalid_request(ip: str) -> None:
    """Count one validation failure (422/413) against the looser budget.

    Raises HTTPException 429 when the per-IP invalid budget is spent.
    Real runs use the run budget instead, so typos never block real runs.
    """
    await check_rate_limit(
        f"ip:{ip}", "invalid", settings.rate_limit_invalid_per_min_per_ip, 60
    )


async def check_rate_limit(key: str, action: str, limit: int, window_seconds: int) -> None:
    now = time.time()
    async with _rate_limit_lock:
        history = _rate_limit_history[(key, action)]
        while history and history[0] < now - window_seconds:
            history.pop(0)
        if len(history) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {action}",
            )
        history.append(now)


def rate_limiter(action: str, limit: int, window_seconds: int):
    """Dependency enforcing per-IP rate limits (no accounts)."""

    async def dependency(request: Request) -> bool:
        await check_rate_limit(f"ip:{client_ip(request)}", action, limit, window_seconds)
        return True

    return dependency


def unauth_rate_limiter(action: str, limit: int, window_seconds: int):
    """Alias kept for compat: all limiters are now per-IP."""
    return rate_limiter(action, limit, window_seconds)


class ExecutionTracker:
    """Global + per-IP concurrency cap (stateless, in-memory)."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()

    async def acquire(self, key: str = "global") -> None:
        global _global_executions
        async with self.lock:
            if _global_executions >= MAX_GLOBAL_EXECUTIONS:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Global concurrent execution cap reached. Please try again later.",
                )
            if _ip_executions[key] >= MAX_RUNS_PER_IP:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Concurrent execution limit reached ({MAX_RUNS_PER_IP}). "
                    "Wait for your current run to finish.",
                )
            _global_executions += 1
            _ip_executions[key] += 1

    async def release(self, key: str = "global") -> None:
        global _global_executions
        async with self.lock:
            _global_executions = max(0, _global_executions - 1)
            _ip_executions[key] = max(0, _ip_executions[key] - 1)


execution_tracker = ExecutionTracker()
