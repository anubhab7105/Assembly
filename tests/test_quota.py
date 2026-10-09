"""Quota limiter tests: windows, cooldowns, day rollover, router skip.

All hermetic (in-memory SQLite, short windows, no network). Custom
catalogs come from tmp models.yaml files; the repo catalog is only read,
never written.
"""

import asyncio
import time
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.base import Base
from src.database.models import QuotaUsage
from src.orchestration.planner import Planner
from src.providers.config import KNOWN_FAMILIES, load_models_config
from src.providers.mock_provider import MockProvider
from src.providers.quota import (
    QuotaExhausted,
    QuotaLimiter,
    fingerprint_key,
    get_limiter,
    today_str,
)
from src.providers.router import ModelRouter
from tests.conftest import make_models_yaml

BASE_LIMITS = {"rpm": 1000, "rpd": 1000, "tpm": 10000, "context_tokens": 32000}


def _quota_providers() -> dict:
    """alpha (tight rpm) / beta (roomy) / gamma (defaults), all filled."""
    return {
        "alpha": [
            {
                "id": "alpha-fast",
                "family": "gpt-oss",
                "roles": ["solver", "planner"],
                "limits": {"rpm": 2, "rpd": 10, "tpm": "unlimited"},
            }
        ],
        "beta": [
            {
                "id": "beta-strong",
                "family": "qwen",
                "roles": ["solver", "critic", "synthesizer"],
                "limits": dict(BASE_LIMITS),
            }
        ],
        "gamma": [
            {
                "id": "gamma-flash",
                "family": "gemini",
                "roles": ["researcher", "planner"],
                "limits": dict(BASE_LIMITS),
            }
        ],
    }


def _day_providers() -> dict:
    """alpha with a tiny daily quota (model renamed to prove yaml-only ids)."""
    providers = _quota_providers()
    providers["alpha"] = [
        {
            "id": "solo-day",
            "family": "gpt-oss",
            "roles": ["solver", "planner"],
            "limits": {"rpm": 1000, "rpd": 3, "tpm": "unlimited"},
        }
    ]
    return providers


def _tpm_providers() -> dict:
    """alpha with a tiny token-per-minute window."""
    providers = _quota_providers()
    providers["alpha"] = [
        {
            "id": "solo-tpm",
            "family": "gpt-oss",
            "roles": ["solver", "planner"],
            "limits": {"rpm": 1000, "rpd": "unlimited", "tpm": 100},
        }
    ]
    return providers


def _tpd_providers() -> dict:
    """alpha with a tiny token-per-day budget (tracked like rpd)."""
    providers = _quota_providers()
    providers["alpha"] = [
        {
            "id": "solo-tpd",
            "family": "gpt-oss",
            "roles": ["solver", "planner"],
            "limits": {"rpm": 1000, "rpd": "unlimited", "tpm": "unlimited", "tpd": 200},
        }
    ]
    return providers


def _factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _limiter(tmp_path, providers=None, **kwargs):
    path = make_models_yaml(tmp_path, providers or _quota_providers())
    config = load_models_config(path)
    args = {
        "config": config,
        "session_factory": _factory(),
        "window_seconds": 2.0,
        "max_wait_seconds": 30.0,
        "max_in_flight": 5,
    }
    args.update(kwargs)
    return QuotaLimiter(**args), config


# ── Fingerprints ──────────────────────────────────────────────────


def test_fingerprint_stable_opaque_and_salted() -> None:
    left = fingerprint_key("k-secret")
    assert left == fingerprint_key("k-secret")
    assert len(left) == 16
    assert "k-secret" not in left
    assert fingerprint_key("k-other") != left
    assert fingerprint_key("k-secret", salt="pepper") != left


# ── Sliding windows ───────────────────────────────────────────────


async def test_rpm_window_waits_for_slot(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path)
    fingerprint = fingerprint_key("k1")
    async with await limiter.acquire("alpha", fingerprint, "alpha-fast"):
        pass
    async with await limiter.acquire("alpha", fingerprint, "alpha-fast"):
        pass
    started = time.monotonic()
    async with await limiter.acquire("alpha", fingerprint, "alpha-fast"):
        pass
    assert time.monotonic() - started >= 1.8


async def test_rpm_exhaustion_raises_when_wait_too_long(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path, max_wait_seconds=0.3)
    fingerprint = fingerprint_key("k1")
    async with await limiter.acquire("alpha", fingerprint, "alpha-fast"):
        pass
    async with await limiter.acquire("alpha", fingerprint, "alpha-fast"):
        pass
    with pytest.raises(QuotaExhausted):
        await limiter.acquire("alpha", fingerprint, "alpha-fast")


async def test_tpm_window_counts_estimated_tokens(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path, providers=_tpm_providers(), max_wait_seconds=0.5)
    fingerprint = fingerprint_key("k1")
    async with await limiter.acquire("alpha", fingerprint, "solo-tpm", est_tokens=60):
        pass
    assert limiter.remaining("alpha", fingerprint, "solo-tpm")["tpm_remaining"] == 40
    with pytest.raises(QuotaExhausted):
        await limiter.acquire("alpha", fingerprint, "solo-tpm", est_tokens=60)


async def test_parallel_calls_share_concurrency_cap(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path, max_in_flight=2)
    fingerprint = fingerprint_key("k-beta")
    active = 0
    peak = 0

    async def worker() -> None:
        nonlocal active, peak
        async with await limiter.acquire("beta", fingerprint, "beta-strong"):
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.2)
            active -= 1

    await asyncio.gather(*[worker() for _ in range(5)])
    assert peak <= 2
    assert peak == 2


# ── Cooldowns ─────────────────────────────────────────────────────


async def test_429_report_triggers_cooldown(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path)
    fingerprint = fingerprint_key("k1")
    async with await limiter.acquire("alpha", fingerprint, "alpha-fast"):
        pass
    assert not limiter.is_exhausted("alpha", fingerprint, "alpha-fast")
    limiter.report_429("alpha", fingerprint, "alpha-fast", retry_after=60.0)
    assert limiter.is_exhausted("alpha", fingerprint, "alpha-fast")
    assert limiter.remaining("alpha", fingerprint, "alpha-fast")["cooldown_seconds"] > 0
    started = time.monotonic()
    with pytest.raises(QuotaExhausted):
        await limiter.acquire("alpha", fingerprint, "alpha-fast")
    assert time.monotonic() - started < 1.0


async def test_429_without_retry_after_uses_default(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path)
    fingerprint = fingerprint_key("k1")
    limiter.report_429("alpha", fingerprint, "alpha-fast", retry_after=None)
    assert limiter.remaining("alpha", fingerprint, "alpha-fast")["cooldown_seconds"] > 0


# ── Daily counters + rollover ─────────────────────────────────────


async def test_day_rollover_resets_counters(tmp_path) -> None:
    factory = _factory()
    limiter, _config = _limiter(
        tmp_path, providers=_day_providers(), session_factory=factory
    )
    fingerprint = fingerprint_key("k-day")
    yesterday = (date.fromisoformat(today_str()) - timedelta(days=1)).isoformat()

    db = factory()
    db.add(
        QuotaUsage(
            provider="alpha",
            key_fingerprint=fingerprint,
            day=yesterday,
            model_id="solo-day",
            count=3,
        )
    )
    db.commit()
    db.close()

    assert limiter.remaining("alpha", fingerprint, "solo-day")["rpd_remaining"] == 3
    for _ in range(3):
        async with await limiter.acquire("alpha", fingerprint, "solo-day"):
            pass
    assert limiter.remaining("alpha", fingerprint, "solo-day")["rpd_remaining"] == 0
    with pytest.raises(QuotaExhausted):
        await limiter.acquire("alpha", fingerprint, "solo-day")
    assert limiter.is_exhausted("alpha", fingerprint, "solo-day")

    db = factory()
    rows = db.query(QuotaUsage).filter(QuotaUsage.provider == "alpha").all()
    by_day = {row.day: row.count for row in rows}
    assert by_day[yesterday] == 3  # yesterday untouched
    assert by_day[today_str()] == 3
    for row in rows:
        assert row.key_fingerprint == fingerprint
        assert row.model_id == "solo-day"
        assert "k-day" not in row.key_fingerprint
    db.close()


# ── Router + planner + status integration ─────────────────────────


def test_router_skips_exhausted_key(tmp_path) -> None:
    limiter, config = _limiter(tmp_path)
    keys = {"alpha": "k1", "beta": "k2", "gamma": "k3"}
    router = ModelRouter(config=config, keys=keys, limiter=limiter)
    assert router.get_live_count() == 3
    assert router.route("solver").provider_name == "alpha"

    limiter.report_429("alpha", fingerprint_key("k1"), "alpha-fast", retry_after=60.0)
    skipped = router.route("solver")
    assert skipped.provider_name == "beta"
    assert skipped.model == "beta-strong"
    assert router.route("solver", prefer_provider="alpha").provider_name == "beta"


async def test_planner_reads_capacity() -> None:
    stub = SimpleNamespace(
        route_for_planning=lambda: SimpleNamespace(
            provider=MockProvider(), model="m", provider_name="x"
        ),
        capacity_estimate=lambda minutes: {"per_provider": {"x": 5}, "total": 5},
    )
    plan = await Planner(stub).plan("What is the mock answer?", 3)
    assert plan.capacity == {"per_provider": {"x": 5}, "total": 5}


async def test_planner_without_capacity_support(mock_router) -> None:
    plan = await Planner(mock_router).plan("What is the mock answer?", 3)
    assert plan.capacity is None


async def test_status_reflects_limiter_remaining() -> None:
    from src.api.keys import providers_status

    response = await providers_status()
    assert response.providers != []
    for entry in response.providers:
        assert set(entry.families) <= set(KNOWN_FAMILIES)
        assert entry.rpm_remaining is None or entry.rpm_remaining >= 0
        assert entry.rpd_remaining is None or entry.rpd_remaining >= 0
        assert entry.cooldown_seconds >= 0


def test_account_scope_counts_one_shared_pool(tmp_path) -> None:
    """OpenRouter-style: two account-scope models share ONE rpd pool —
    the snapshot lists it once and capacity counts it once (35, not 70)."""
    from src.orchestration.capacity import KeyBudget, affordable_calls

    providers = {
        "or": [
            {
                "id": "free-a",
                "family": "gemma",
                "roles": ["solver"],
                "scope": "account",
                "limits": {"rpm": 20, "rpd": 50, "tpm": "unlimited"},
            },
            {
                "id": "free-b",
                "family": "nemotron",
                "roles": ["solver"],
                "scope": "account",
                "limits": {"rpm": 20, "rpd": 50, "tpm": "unlimited"},
            },
        ],
    }
    limiter, config = _limiter(tmp_path, providers=providers)
    router = ModelRouter(config=config, keys={"or": "k1"}, limiter=limiter)
    entries = [e for e in router.quota_snapshot() if e["provider"] == "or"]
    assert len(entries) == 1
    keys = [
        KeyBudget(
            provider=e["provider"],
            rpm_limit=e["rpm_limit"],
            rpd_remaining=e["rpd_remaining"],
            tpm_limit=e.get("tpm_limit"),
            tpd_remaining=e.get("tpd_remaining"),
        )
        for e in entries
    ]
    assert affordable_calls(keys, 5) == int(min(100, 50) * 0.7) == 35


def test_shared_singleton_exists() -> None:
    assert get_limiter() is get_limiter()


# ── Scopes: model buckets vs shared account buckets ───────────────


def _scoped_providers() -> dict:
    return {
        "solo": [
            {
                "id": "solo-a",
                "family": "qwen",
                "roles": ["solver"],
                "limits": {"rpm": 1000, "rpd": 5, "tpm": "unlimited"},
            },
            {
                "id": "solo-b",
                "family": "gemini",
                "roles": ["solver"],
                "limits": {"rpm": 1000, "rpd": 5, "tpm": "unlimited"},
            },
        ],
        "shared": [
            {
                "id": "shared-a",
                "family": "qwen",
                "roles": ["solver"],
                "scope": "account",
                "limits": {"rpm": 1000, "rpd": 4, "tpm": "unlimited"},
            },
            {
                "id": "shared-b",
                "family": "gemini",
                "roles": ["solver"],
                "scope": "account",
                "limits": {"rpm": 1000, "rpd": 4, "tpm": "unlimited"},
            },
        ],
    }


async def test_model_scope_buckets_are_independent(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path, providers=_scoped_providers())
    fingerprint = fingerprint_key("k-scope")
    for _ in range(5):
        async with await limiter.acquire("solo", fingerprint, "solo-a"):
            pass
    assert limiter.is_exhausted("solo", fingerprint, "solo-a")
    assert not limiter.is_exhausted("solo", fingerprint, "solo-b")
    assert limiter.remaining("solo", fingerprint, "solo-b")["rpd_remaining"] == 5


async def test_account_scope_models_share_one_bucket(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path, providers=_scoped_providers())
    fingerprint = fingerprint_key("k-shared")
    for _ in range(2):
        async with await limiter.acquire("shared", fingerprint, "shared-a"):
            pass
    for _ in range(2):
        async with await limiter.acquire("shared", fingerprint, "shared-b"):
            pass
    # 2 + 2 against the shared rpd of 4: both models are now spent.
    assert limiter.is_exhausted("shared", fingerprint, "shared-a")
    assert limiter.is_exhausted("shared", fingerprint, "shared-b")
    assert limiter.remaining("shared", fingerprint, "shared-a")["rpd_remaining"] == 0


async def test_429_cools_only_the_failing_model(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path, providers=_scoped_providers())
    fingerprint = fingerprint_key("k-429")
    async with await limiter.acquire("shared", fingerprint, "shared-a"):
        pass
    limiter.report_429("shared", fingerprint, "shared-a", retry_after=60.0)
    assert limiter.is_exhausted("shared", fingerprint, "shared-a")
    # Sibling on the same account bucket keeps serving...
    assert not limiter.is_exhausted("shared", fingerprint, "shared-b")
    async with await limiter.acquire("shared", fingerprint, "shared-b"):
        pass
    # ...and the 429 consumed nothing from the shared bucket (1 + 1 of 4).
    assert limiter.remaining("shared", fingerprint, "shared-b")["rpd_remaining"] == 2


async def test_tpm_pre_reject_uses_model_window(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path, providers=_tpm_providers(), max_wait_seconds=0.5)
    fingerprint = fingerprint_key("k-tpm2")
    with pytest.raises(QuotaExhausted, match="exceed.*tpm limit of 100"):
        await limiter.acquire("alpha", fingerprint, "solo-tpm", est_tokens=101)


async def test_tpd_tracked_like_rpd(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path, providers=_tpd_providers())
    fingerprint = fingerprint_key("k-tpd")
    for _ in range(4):
        async with await limiter.acquire(
            "alpha", fingerprint, "solo-tpd", est_tokens=50
        ):
            pass
    assert limiter.remaining("alpha", fingerprint, "solo-tpd")["tpd_remaining"] == 0
    assert limiter.is_exhausted("alpha", fingerprint, "solo-tpd")
    with pytest.raises(QuotaExhausted, match="daily token budget spent"):
        await limiter.acquire("alpha", fingerprint, "solo-tpd", est_tokens=50)


async def test_tpd_pre_reject_before_sending(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path, providers=_tpd_providers(), max_wait_seconds=0.5)
    fingerprint = fingerprint_key("k-tpd2")
    with pytest.raises(QuotaExhausted, match="daily token budget of 200"):
        await limiter.acquire("alpha", fingerprint, "solo-tpd", est_tokens=500)


async def test_tpd_absent_is_not_enforced(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path)
    fingerprint = fingerprint_key("k-notpd")
    async with await limiter.acquire(
        "alpha", fingerprint, "alpha-fast", est_tokens=10**6
    ):
        pass
    remaining = limiter.remaining("alpha", fingerprint, "alpha-fast")
    assert remaining["tpd_limit"] is None and remaining["tpd_remaining"] is None


async def test_unknown_model_fails_open(tmp_path) -> None:
    """Quota must never break runs: uncatalogued pairs get no windows."""
    limiter, _ = _limiter(tmp_path)
    fingerprint = fingerprint_key("k-unknown")
    async with await limiter.acquire("test", fingerprint, "m", est_tokens=10**9):
        pass
    assert limiter.remaining("test", fingerprint, "m")["rpd_remaining"] is None


async def test_unknown_pair_warns_once_per_pair(tmp_path, caplog) -> None:
    import logging

    limiter, _ = _limiter(tmp_path)
    fingerprint = fingerprint_key("k-warn")
    with caplog.at_level(logging.WARNING, logger="assembly"):
        for _ in range(3):
            async with await limiter.acquire("nope", fingerprint, "ghost"):
                pass
    warnings = [
        line
        for line in caplog.text.splitlines()
        if "unknown (provider, model) pair" in line
    ]
    assert len(warnings) == 1
    assert "nope/ghost" in warnings[0]


async def test_unlimited_fields_are_not_enforced(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path)
    fingerprint = fingerprint_key("k-unlim")
    for _ in range(3):
        async with await limiter.acquire(
            "alpha", fingerprint, "alpha-fast", est_tokens=10**6
        ):
            pass
    remaining = limiter.remaining("alpha", fingerprint, "alpha-fast")
    assert remaining["tpm_limit"] is None and remaining["tpm_remaining"] is None
