"""
Assembly — per-key, per-model quota limiter (free-tier survival).

Tracks request counts per (provider, key fingerprint, bucket) for sliding
per-minute / per-day windows using per-model limits from models.yaml,
enforces a per-provider asyncio concurrency cap, persists daily counters
in the quota_usage table so they survive restarts, and exposes remaining
capacity to the planner and the status endpoint.

Buckets: a model with scope "model" gets its own bucket (the model id);
a model with scope "account" shares its provider's "" bucket (e.g. the
OpenRouter free daily cap spans all free models on one key). Cooldowns
after a 429 are always per (provider, key, model): a rate-limited model
cools down without consuming or resetting any bucket window.

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

# Account-scope bucket id: shared by every account-scoped model on one key.
ACCOUNT_BUCKET = ""


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
    """Stable per-deployment salt. Override with QUOTA_SALT for rotation.

    Uses the dedicated quota_salt setting (QUOTA_SALT env var) so the JWT
    signing key is never reused as a cryptographic salt. Falls back to a
    per-process random value for dev only.
    """
    # 1. Explicit QUOTA_SALT env var (takes precedence for rotation).
    salt = os.environ.get("QUOTA_SALT", "")
    if salt:
        return salt
    # 2. Pydantic settings quota_salt field (preferred in all modes).
    try:
        from src.core.config import settings
        from src.core.keystore import reveal

        configured = reveal(settings.quota_salt)
        if configured:
            return configured
    except Exception:  # noqa: BLE001 — quota must never crash
        pass
    # 3. Dev fallback: a per-process random value (not the JWT key).
    #    Not stable across restarts — acceptable for dev/desktop where
    #    quota counters are ephemeral anyway.
    return "assembly-dev-quota"


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
    """Sliding-window RPM/TPM + daily RPD + cooldowns + concurrency caps.

    All quota state is keyed (provider, key fingerprint, bucket); model
    cooldowns are keyed (provider, key fingerprint, model id).
    """

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
        self._minute_calls: dict[tuple[str, str, str], deque[float]] = {}
        self._minute_tokens: dict[tuple[str, str, str], deque[tuple[float, int]]] = {}
        self._cooldowns: dict[tuple[str, str, str], float] = {}
        self._slots: dict[str, asyncio.Semaphore] = {}
        self._in_flight: dict[str, int] = {}
        self._warned_unknown_pairs: set[tuple[str, str]] = set()
        self._day_counts: dict[tuple[str, str, str], list[int]] = {}
        self._snapshot: dict[tuple[str, str], tuple[int, int]] = {}

    # ── internal helpers ─────────────────────────────────────────────

    def _lookup(self, provider: str, model_id: str) -> tuple[Any, str, str]:
        """(limits, scope, bucket) for one catalog model.

        Unknown (provider, model) pairs fail open (None limits = no
        windows): quota must never break runs — routing only ever emits
        catalog models, so anything else is a test double or a custom
        provider outside the catalog.
        """
        try:
            limits = self._config.limits_of(provider, model_id)
            scope = self._config.scope_of(provider, model_id)
        except (KeyError, AttributeError):
            if (provider, model_id) not in self._warned_unknown_pairs:
                self._warned_unknown_pairs.add((provider, model_id))
                logger.warning(
                    f"Quota   │ unknown (provider, model) pair "
                    f"{provider}/{model_id} — no limits enforced (fail-open)"
                )
            return None, "model", model_id
        bucket = model_id if scope == "model" else ACCOUNT_BUCKET
        return limits, scope, bucket

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        """An enforceable int limit, or None for null/"unlimited"."""
        if isinstance(value, bool):
            return None
        return value if isinstance(value, int) else None

    def _prune(self, provider: str, key_id: str, bucket: str, now: float) -> None:
        calls = self._minute_calls.setdefault((provider, key_id, bucket), deque())
        while calls and calls[0] <= now - self._window:
            calls.popleft()
        tokens = self._minute_tokens.setdefault((provider, key_id, bucket), deque())
        while tokens and tokens[0][0] <= now - self._window:
            tokens.popleft()

    def _cooldown_left(self, provider: str, key_id: str, model_id: str) -> float:
        return max(
            0.0,
            self._cooldowns.get((provider, key_id, model_id), 0.0) - time.monotonic(),
        )

    def _session(self) -> Any:
        from src.core.config import settings

        if settings.is_web:
            raise RuntimeError("stateless web: no database session")
        if self._session_factory is not None:
            return self._session_factory()
        from src.database.base import SessionLocal

        return SessionLocal()

    # ── client usage snapshot (stateless web) ────────────────────────
    # The browser tracks daily usage in IndexedDB and sends it with each
    # run. The limiter takes max(in-memory, snapshot) per bucket, so a
    # restarted server never under-counts a key it cannot see.

    def set_usage_snapshot(self, entries: Any) -> None:
        """Load a client usage_snapshot: [{provider, model, count, tokens}]."""
        merged: dict[tuple[str, str], tuple[int, int]] = {}
        for entry in entries or []:
            if isinstance(entry, dict):
                provider = str(entry.get("provider", ""))
                model = str(entry.get("model", ""))
                try:
                    count = max(0, int(entry.get("count", 0) or 0))
                except (TypeError, ValueError):
                    count = 0
                try:
                    tokens = max(0, int(entry.get("tokens", 0) or 0))
                except (TypeError, ValueError):
                    tokens = 0
            else:
                provider = str(getattr(entry, "provider", ""))
                model = str(getattr(entry, "model", ""))
                count = max(0, int(getattr(entry, "count", 0) or 0))
                tokens = max(0, int(getattr(entry, "tokens", 0) or 0))
            if not provider:
                continue
            key = (provider, model)
            prev = merged.get(key, (0, 0))
            merged[key] = (prev[0] + count, prev[1] + tokens)
        self._snapshot = merged

    def _snapshot_for(self, provider: str, bucket: str) -> tuple[int, int]:
        snap: dict[tuple[str, str], tuple[int, int]] = getattr(self, "_snapshot", {})
        if not snap:
            return 0, 0
        if bucket == "":
            # Account scope: shared pool sums every model on the provider.
            total_c = sum(c for (p, _m), (c, _t) in snap.items() if p == provider)
            total_t = sum(_t for (p, _m), (c, _t) in snap.items() if p == provider)
            return total_c, total_t
        return snap.get((provider, bucket), (0, 0))

    def _today_counters(
        self, provider: str, key_id: str, bucket: str
    ) -> tuple[int, int]:
        """(calls, tokens) spent today: max(memory, snapshot, DB).

        Web mode has no DB: memory + client snapshot only. Desktop adds
        persisted rows. Fail-open: a DB error reads as memory+snapshot.
        """
        mem = self._day_counts.get((provider, key_id, bucket), [0, 0])
        mem_c, mem_t = mem[0], mem[1]
        snap_c, snap_t = self._snapshot_for(provider, bucket)
        best_c, best_t = max(mem_c, snap_c), max(mem_t, snap_t)
        try:
            from src.core.config import settings

            if settings.is_web:
                return best_c, best_t
            from src.database.models import QuotaUsage

            db = self._session()
            try:
                row = (
                    db.query(QuotaUsage)
                    .filter(
                        QuotaUsage.provider == provider,
                        QuotaUsage.key_fingerprint == key_id,
                        QuotaUsage.day == today_str(),
                        QuotaUsage.model_id == bucket,
                    )
                    .first()
                )
                if row is None:
                    return best_c, best_t
                return max(best_c, row.count or 0), max(best_t, row.tokens or 0)
            finally:
                db.close()
        except RuntimeError:
            return best_c, best_t
        except Exception as exc:  # noqa: BLE001 — quota must never break runs
            logger.warning(f"Quota   │ day-counter read failed: {exc}")
            return best_c, best_t

    def _record(
        self,
        provider: str,
        key_id: str,
        bucket: str,
        est_tokens: int,
        track_day: bool,
    ) -> None:
        now = time.monotonic()
        self._minute_calls.setdefault((provider, key_id, bucket), deque()).append(now)
        if est_tokens > 0:
            self._minute_tokens.setdefault((provider, key_id, bucket), deque()).append(
                (now, est_tokens)
            )
        if not track_day:
            return
        # In-memory day counters work in every mode (web has no DB).
        slot = self._day_counts.setdefault((provider, key_id, bucket), [0, 0])
        slot[0] += 1
        slot[1] += max(0, est_tokens)
        try:
            from src.core.config import settings

            if settings.is_web:
                return
            from src.database.models import QuotaUsage

            db = self._session()
            try:
                row = (
                    db.query(QuotaUsage)
                    .filter(
                        QuotaUsage.provider == provider,
                        QuotaUsage.key_fingerprint == key_id,
                        QuotaUsage.day == today_str(),
                        QuotaUsage.model_id == bucket,
                    )
                    .first()
                )
                if row is None:
                    row = QuotaUsage(
                        provider=provider,
                        key_fingerprint=key_id,
                        day=today_str(),
                        model_id=bucket,
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
        bucket: str,
        deadline: float,
        what: str,
    ) -> None:
        """Sleep until the sliding window frees a slot, or raise on timeout."""
        while used >= limit:
            now = time.monotonic()
            if now >= deadline:
                raise QuotaExhausted(provider, key_id, f"{what} window full")
            calls = self._minute_calls.get((provider, key_id, bucket), deque())
            wake_at = (calls[0] + self._window) if calls else now
            await asyncio.sleep(max(0.0, min(wake_at - now, deadline - now) + 0.05))
            self._prune(provider, key_id, bucket, time.monotonic())
            calls = self._minute_calls.get((provider, key_id, bucket), deque())
            used = len(calls)

    # ── public API ───────────────────────────────────────────────────

    async def acquire(
        self, provider: str, key_id: str, model_id: str, est_tokens: int = 0
    ) -> QuotaLease:
        """Take a concurrency slot + record usage. Waits on full windows
        (bounded by max_wait_seconds), raises QuotaExhausted on cooldown,
        spent daily quota, or wait timeout. A single request estimated
        above the model's tpm is rejected before sending. Use as
        `async with await limiter.acquire(...)`."""
        now = time.monotonic()
        left = self._cooldown_left(provider, key_id, model_id)
        if left > 0:
            raise QuotaExhausted(provider, key_id, "cooling down", retry_after=left)
        limits, _scope, bucket = self._lookup(provider, model_id)
        rpm = self._int_or_none(limits.rpm) if limits is not None else None
        rpd = self._int_or_none(limits.rpd) if limits is not None else None
        tpm = self._int_or_none(limits.tpm) if limits is not None else None
        tpd = self._int_or_none(limits.tpd) if limits is not None else None
        if tpm is not None and est_tokens > tpm:
            raise QuotaExhausted(
                provider,
                key_id,
                f"estimated {est_tokens} tokens exceed the {model_id} "
                f"tpm limit of {tpm} — reduce max_tokens",
            )
        if tpd is not None and est_tokens > tpd:
            raise QuotaExhausted(
                provider,
                key_id,
                f"estimated {est_tokens} tokens exceed the {model_id} "
                f"daily token budget of {tpd} — reduce max_tokens",
            )
        if rpd is not None or tpd is not None:
            used_calls, used_tokens = self._today_counters(provider, key_id, bucket)
            if rpd is not None and used_calls >= rpd:
                raise QuotaExhausted(provider, key_id, "daily quota spent")
            if tpd is not None and used_tokens + est_tokens > tpd:
                raise QuotaExhausted(
                    provider,
                    key_id,
                    f"daily token budget spent ({used_tokens} of {tpd} "
                    "tokens used) — try tomorrow or a smaller max_tokens",
                )
        deadline = now + self._max_wait
        if rpm is not None:
            self._prune(provider, key_id, bucket, now)
            used = len(self._minute_calls.get((provider, key_id, bucket), deque()))
            await self._wait_for_room(
                used, rpm, provider, key_id, bucket, deadline, "rpm"
            )
        if tpm is not None and est_tokens > 0:
            self._prune(provider, key_id, bucket, time.monotonic())
            spent = sum(
                t
                for _, t in self._minute_tokens.get((provider, key_id, bucket), deque())
            )
            while spent + est_tokens > tpm and time.monotonic() < deadline:
                await asyncio.sleep(0.5)
                self._prune(provider, key_id, bucket, time.monotonic())
                spent = sum(
                    t
                    for _, t in self._minute_tokens.get(
                        (provider, key_id, bucket), deque()
                    )
                )
            if spent + est_tokens > tpm:
                raise QuotaExhausted(provider, key_id, "tpm window full")
        # A cooldown may have landed while waiting: re-check before recording.
        left = self._cooldown_left(provider, key_id, model_id)
        if left > 0:
            raise QuotaExhausted(provider, key_id, "cooling down", retry_after=left)
        slot = self._slot_for(provider)
        await slot.acquire()
        try:
            self._in_flight[provider] = self._in_flight.get(provider, 0) + 1
            self._record(
                provider, key_id, bucket, est_tokens, rpd is not None or tpd is not None
            )
        except BaseException:
            # A cancellation landing here must not leak the semaphore permit
            # or the in-flight counter (today: no await sits between acquire
            # and return, so this is defense-in-depth for future edits).
            self._in_flight[provider] = max(0, self._in_flight.get(provider, 1) - 1)
            slot.release()
            raise
        return QuotaLease(self, provider, slot)

    def report_429(
        self,
        provider: str,
        key_id: str,
        model_id: str,
        retry_after: float | None = None,
    ) -> None:
        """Put one model on cooldown after a 429. Names only are ever logged.

        Only the model's cooldown is set (honoring Retry-After): bucket
        windows are neither consumed nor reset, so sibling models on an
        account-scope key keep serving.
        """
        wait = (
            retry_after if retry_after and retry_after > 0 else DEFAULT_COOLDOWN_SECONDS
        )
        self._cooldowns[(provider, key_id, model_id)] = time.monotonic() + min(
            wait, MAX_COOLDOWN_SECONDS
        )
        logger.info(
            f"Quota   │ {provider}/{model_id} cooling down "
            f"for {min(wait, MAX_COOLDOWN_SECONDS):.0f}s"
        )

    def is_exhausted(self, provider: str, key_id: str, model_id: str) -> bool:
        """True when a model must be skipped: cooling down or bucket spent.
        A full per-minute window is transient (acquire waits), not exhaustion."""
        if self._cooldown_left(provider, key_id, model_id) > 0:
            return True
        try:
            limits, _scope, bucket = self._lookup(provider, model_id)
        except KeyError:
            return True
        if limits is None:
            return False
        rpd = self._int_or_none(limits.rpd)
        tpd = self._int_or_none(limits.tpd)
        if rpd is None and tpd is None:
            return False
        used_calls, used_tokens = self._today_counters(provider, key_id, bucket)
        return (rpd is not None and used_calls >= rpd) or (
            tpd is not None and used_tokens >= tpd
        )

    def remaining(self, provider: str, key_id: str, model_id: str) -> dict[str, Any]:
        """Remaining capacity snapshot for one model for planner/status views."""
        now = time.monotonic()
        try:
            limits, scope, bucket = self._lookup(provider, model_id)
        except KeyError:
            limits, scope, bucket = None, "model", model_id
        if limits is None:
            return {
                "rpm_limit": None,
                "rpm_remaining": None,
                "tpm_limit": None,
                "tpm_remaining": None,
                "rpd_limit": None,
                "rpd_remaining": None,
                "tpd_limit": None,
                "tpd_remaining": None,
                "cooldown_seconds": 0.0,
                "in_flight": self._in_flight.get(provider, 0),
                "scope": "model",
                "model": model_id,
            }
        self._prune(provider, key_id, bucket, now)
        rpm = self._int_or_none(limits.rpm)
        tpm = self._int_or_none(limits.tpm)
        rpd = self._int_or_none(limits.rpd)
        tpd = self._int_or_none(limits.tpd)
        out: dict[str, Any] = {
            "rpm_limit": None,
            "rpm_remaining": None,
            "tpm_limit": None,
            "tpm_remaining": None,
            "rpd_limit": None,
            "rpd_remaining": None,
            "tpd_limit": None,
            "tpd_remaining": None,
            "cooldown_seconds": round(
                self._cooldown_left(provider, key_id, model_id), 1
            ),
            "in_flight": self._in_flight.get(provider, 0),
            "scope": scope,
            "model": model_id,
        }
        if rpm is not None:
            out["rpm_limit"] = rpm
            out["rpm_remaining"] = max(
                0,
                rpm - len(self._minute_calls.get((provider, key_id, bucket), deque())),
            )
        if tpm is not None:
            spent = sum(
                t
                for _, t in self._minute_tokens.get((provider, key_id, bucket), deque())
            )
            out["tpm_limit"] = tpm
            out["tpm_remaining"] = max(0, tpm - spent)
        if rpd is not None:
            used_calls, _ = self._today_counters(provider, key_id, bucket)
            out["rpd_limit"] = rpd
            out["rpd_remaining"] = max(0, rpd - used_calls)
        if tpd is not None:
            _, used_tokens = self._today_counters(provider, key_id, bucket)
            out["tpd_limit"] = tpd
            out["tpd_remaining"] = max(0, tpd - used_tokens)
        return out

    def reset(self) -> None:
        """Drop in-memory windows, cooldowns, day counts and snapshot."""
        self._minute_calls.clear()
        self._minute_tokens.clear()
        self._cooldowns.clear()
        self._slots.clear()
        self._in_flight.clear()
        self._day_counts.clear()
        self._snapshot = {}


_limiter: QuotaLimiter | None = None


def get_limiter(**kwargs: Any) -> QuotaLimiter:
    """Process-wide limiter shared by router, providers, and status views."""
    global _limiter
    if _limiter is None:
        _limiter = QuotaLimiter(**kwargs)
    return _limiter
