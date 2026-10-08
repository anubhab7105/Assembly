"""
Assembly — per-key quota limiter (free-tier survival).

Tracks request counts per (provider, key fingerprint) for sliding
per-minute / per-day windows using limits from models.yaml, enforces a
per-provider asyncio concurrency cap, persists daily counters in the
quota_usage table so they survive restarts, and exposes remaining
capacity to the planner and the status endpoint.

The raw key is NEVER stored: only a salted SHA-256 prefix (16 hex chars)
identifies a key in memory and in the database.
"""

import asyncio
import hashlib
import os
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Self

from src.core.logging_config import logger

DAY_SECONDS = 24 * 3600
DEFAULT_COOLDOWN_SECONDS = 60.0
MAX_COOLDOWN_SECONDS = 3600.0


def today_str() -> str:
    """Current day in UTC (YYYY-MM-DD). UTC keeps day boundaries
    identical on desktop and hosted machines in any timezone."""
    return datetime.now(timezone.utc).date().isoformat()


class QuotaExhausted(Exception):
    """Raised when a key may not be used right now (cooldown or quota spent)."""

    def __init__(
        self, provider: str, key_id: str, reason: str, retry_after: float = 0.0
    ) -> None:
        super().__init__(f"{provider}: quota exhausted ({reason})")
        self.provider = provider
        self.key_id = key_id
        self.reason = reason
        self.retry_after = retry_after


def _default_salt() -> str:
    """Stable per-deployment salt. Override with QUOTA_SALT for rotation."""
    salt = os.environ.get("QUOTA_SALT", "")
    if not salt:
        try:
            from src.core.config import settings
            from src.core.keystore import reveal

            salt = reveal(settings.jwt_secret_key)
        except Exception:  # noqa: BLE001 — fall back to a documented dev constant
            salt = ""
    return salt or "assembly-dev-quota"


def fingerprint_key(key: Any, salt: str | None = None) -> str:
    """Salted SHA-256 prefix identifying a key without storing it."""
    from src.core.keystore import reveal

    raw = reveal(key)
    digest = hashlib.sha256(f"{salt or _default_salt()}:{raw}".encode()).hexdigest()
    return digest[:16]


class QuotaLease:
    """Held concurrency slot + recorded usage. Release when the call ends."""

    def __init__(
        self, limiter: "QuotaLimiter", provider: str, slot: asyncio.Semaphore
    ) -> None:
        self._limiter = limiter
        self._provider = provider
        self._slot = slot
        self._released = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        self.release()

    def release(self) -> None:
        if not self._released:
            self._released = True
            self._limiter._release_slot(self._provider)
            self._slot.release()


class QuotaLimiter:
    """Sliding-window RPM/TPM + daily RPD + cooldowns + concurrency caps."""

    def __init__(
        self,
        config: Any = None,
        session_factory: Callable[[], Any] | None = None,
        window_seconds: float = 60.0,
        max_wait_seconds: float = 120.0,
        max_in_flight: int = 5,
    ) -> None:
        from src.providers.config import load_models_config

        self._config = config or load_models_config()
        self._session_factory = session_factory
        self._window = window_seconds
        self._max_wait = max_wait_seconds
        self._max_in_flight = max(1, max_in_flight)
        self._minute_calls: dict[tuple[str, str], deque[float]] = {}
        self._minute_tokens: dict[tuple[str, str], deque[tuple[float, int]]] = {}
        self._cooldowns: dict[tuple[str, str], float] = {}
        self._slots: dict[str, asyncio.Semaphore] = {}
        self._in_flight: dict[str, int] = {}

    # ── internal helpers ─────────────────────────────────────────────

    def _limits(self, provider: str) -> Any:
        spec = self._config.providers.get(provider)
        return spec.limits if spec else None

    def _prune(self, provider: str, key_id: str, now: float) -> None:
        calls = self._minute_calls.setdefault((provider, key_id), deque())
        while calls and calls[0] <= now - self._window:
            calls.popleft()
        tokens = self._minute_tokens.setdefault((provider, key_id), deque())
        while tokens and tokens[0][0] <= now - self._window:
            tokens.popleft()

    def _cooldown_left(self, provider: str, key_id: str) -> float:
        return max(0.0, self._cooldowns.get((provider, key_id), 0.0) - time.monotonic())

    def _session(self) -> Any:
        if self._session_factory is not None:
            return self._session_factory()
        from src.database.base import SessionLocal

        return SessionLocal()

    def _today_used(self, provider: str, key_id: str) -> int | None:
        """Calls already spent today, or None when no daily limit applies."""
        limits = self._limits(provider)
        if limits is None or limits.rpd is None:
            return None
        try:
            from src.database.models import QuotaUsage

            db = self._session()
            try:
                row = (
                    db.query(QuotaUsage)
                    .filter(
                        QuotaUsage.provider == provider,
                        QuotaUsage.key_fingerprint == key_id,
                        QuotaUsage.day == today_str(),
                    )
                    .first()
                )
                return row.count if row else 0
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001 — quota must never break runs
            logger.warning(f"Quota   │ day-counter read failed: {exc}")
            return None

    def _record(self, provider: str, key_id: str, est_tokens: int) -> None:
        now = time.monotonic()
        self._minute_calls.setdefault((provider, key_id), deque()).append(now)
        if est_tokens > 0:
            self._minute_tokens.setdefault((provider, key_id), deque()).append(
                (now, est_tokens)
            )
        limits = self._limits(provider)
        if limits is None or limits.rpd is None:
            return
        try:
            from src.database.models import QuotaUsage

            db = self._session()
            try:
                row = (
                    db.query(QuotaUsage)
                    .filter(
                        QuotaUsage.provider == provider,
                        QuotaUsage.key_fingerprint == key_id,
                        QuotaUsage.day == today_str(),
                    )
                    .first()
                )
                if row is None:
                    row = QuotaUsage(
                        provider=provider,
                        key_fingerprint=key_id,
                        day=today_str(),
                    )
                    db.add(row)
                row.count = (row.count or 0) + 1
                row.tokens = (row.tokens or 0) + max(0, est_tokens)
                db.commit()
                # Drop rows older than yesterday; fingerprints rotate anyway.
                cutoff = (
                    datetime.now(timezone.utc).date() - timedelta(days=2)
                ).isoformat()
                db.query(QuotaUsage).filter(QuotaUsage.day < cutoff).delete()
                db.commit()
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001 — quota must never break runs
            logger.warning(f"Quota   │ day-counter write failed: {exc}")

    def _slot_for(self, provider: str) -> asyncio.Semaphore:
        slot = self._slots.get(provider)
        if slot is None:
            slot = asyncio.Semaphore(self._max_in_flight)
            self._slots[provider] = slot
        return slot

    def _release_slot(self, provider: str) -> None:
        self._in_flight[provider] = max(0, self._in_flight.get(provider, 1) - 1)

    async def _wait_for_room(
        self,
        used: int,
        limit: int,
        provider: str,
        key_id: str,
        deadline: float,
        what: str,
    ) -> None:
        """Sleep until the sliding window frees a slot, or raise on timeout."""
        while used >= limit:
            now = time.monotonic()
            if now >= deadline:
                raise QuotaExhausted(provider, key_id, f"{what} window full")
            calls = self._minute_calls.get((provider, key_id), deque())
            wake_at = (calls[0] + self._window) if calls else now
            await asyncio.sleep(max(0.0, min(wake_at - now, deadline - now) + 0.05))
            self._prune(provider, key_id, time.monotonic())
            calls = self._minute_calls.get((provider, key_id), deque())
            used = len(calls)

    # ── public API ───────────────────────────────────────────────────

    async def acquire(
        self, provider: str, key_id: str, est_tokens: int = 0
    ) -> QuotaLease:
        """Take a concurrency slot + record usage. Waits on full windows
        (bounded by max_wait_seconds), raises QuotaExhausted on cooldown,
        spent daily quota, or wait timeout. Use as
        `async with await limiter.acquire(...)`."""
        now = time.monotonic()
        left = self._cooldown_left(provider, key_id)
        if left > 0:
            raise QuotaExhausted(provider, key_id, "cooling down", retry_after=left)
        limits = self._limits(provider)
        if limits is not None and limits.rpd is not None:
            used = self._today_used(provider, key_id)
            if used is not None and used >= limits.rpd:
                raise QuotaExhausted(provider, key_id, "daily quota spent")
        deadline = now + self._max_wait
        if limits is not None and limits.rpm is not None:
            self._prune(provider, key_id, now)
            used = len(self._minute_calls.get((provider, key_id), deque()))
            await self._wait_for_room(
                used, limits.rpm, provider, key_id, deadline, "rpm"
            )
        if limits is not None and limits.tpm is not None and est_tokens > 0:
            self._prune(provider, key_id, time.monotonic())
            spent = sum(
                t for _, t in self._minute_tokens.get((provider, key_id), deque())
            )
            while spent + est_tokens > limits.tpm and time.monotonic() < deadline:
                await asyncio.sleep(0.5)
                self._prune(provider, key_id, time.monotonic())
                spent = sum(
                    t for _, t in self._minute_tokens.get((provider, key_id), deque())
                )
            if spent + est_tokens > limits.tpm:
                raise QuotaExhausted(provider, key_id, "tpm window full")
        # A cooldown may have landed while waiting: re-check before recording.
        left = self._cooldown_left(provider, key_id)
        if left > 0:
            raise QuotaExhausted(provider, key_id, "cooling down", retry_after=left)
        slot = self._slot_for(provider)
        await slot.acquire()
        try:
            self._in_flight[provider] = self._in_flight.get(provider, 0) + 1
            self._record(provider, key_id, est_tokens)
        except BaseException:
            # A cancellation landing here must not leak the semaphore permit
            # or the in-flight counter (today: no await sits between acquire
            # and return, so this is defense-in-depth for future edits).
            self._in_flight[provider] = max(0, self._in_flight.get(provider, 1) - 1)
            slot.release()
            raise
        return QuotaLease(self, provider, slot)

    def report_429(
        self, provider: str, key_id: str, retry_after: float | None = None
    ) -> None:
        """Put a key on cooldown after a 429. Names only are ever logged."""
        wait = (
            retry_after if retry_after and retry_after > 0 else DEFAULT_COOLDOWN_SECONDS
        )
        self._cooldowns[(provider, key_id)] = time.monotonic() + min(
            wait, MAX_COOLDOWN_SECONDS
        )
        logger.info(
            f"Quota   │ {provider} cooling down for {min(wait, MAX_COOLDOWN_SECONDS):.0f}s"
        )

    def is_exhausted(self, provider: str, key_id: str) -> bool:
        """True when a key must be skipped: cooling down or daily quota spent.
        A full per-minute window is transient (acquire waits), not exhaustion."""
        if self._cooldown_left(provider, key_id) > 0:
            return True
        limits = self._limits(provider)
        if limits is not None and limits.rpd is not None:
            used = self._today_used(provider, key_id)
            if used is not None and used >= limits.rpd:
                return True
        return False

    def remaining(self, provider: str, key_id: str) -> dict[str, Any]:
        """Remaining capacity snapshot for planner and status views."""
        now = time.monotonic()
        self._prune(provider, key_id, now)
        limits = self._limits(provider)
        out: dict[str, Any] = {
            "rpm_limit": None,
            "rpm_remaining": None,
            "tpm_limit": None,
            "tpm_remaining": None,
            "rpd_limit": None,
            "rpd_remaining": None,
            "cooldown_seconds": round(self._cooldown_left(provider, key_id), 1),
            "in_flight": self._in_flight.get(provider, 0),
        }
        if limits is None:
            return out
        if limits.rpm is not None:
            out["rpm_limit"] = limits.rpm
            out["rpm_remaining"] = max(
                0, limits.rpm - len(self._minute_calls.get((provider, key_id), deque()))
            )
        if limits.tpm is not None:
            spent = sum(
                t for _, t in self._minute_tokens.get((provider, key_id), deque())
            )
            out["tpm_limit"] = limits.tpm
            out["tpm_remaining"] = max(0, limits.tpm - spent)
        if limits.rpd is not None:
            used = self._today_used(provider, key_id)
            out["rpd_limit"] = limits.rpd
            out["rpd_remaining"] = (
                limits.rpd if used is None else max(0, limits.rpd - used)
            )
        return out

    def reset(self) -> None:
        """Drop in-memory windows and cooldowns (day rows in the DB stay)."""
        self._minute_calls.clear()
        self._minute_tokens.clear()
        self._cooldowns.clear()
        self._slots.clear()
        self._in_flight.clear()


_limiter: QuotaLimiter | None = None


def get_limiter(**kwargs: Any) -> QuotaLimiter:
    """Process-wide limiter shared by router, providers, and status views."""
    global _limiter
    if _limiter is None:
        _limiter = QuotaLimiter(**kwargs)
    return _limiter
