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

CUSTOM_YAML = """
providers:
  alpha:
    base: openai-compatible
    url: http://127.0.0.1:9/v1
    enabled: true
    models:
      - {id: alpha-fast, family: gpt-oss, roles: [solver, planner], context_tokens: null}
    limits: {rpm: 2, rpd: 10, tpm: null}
  beta:
    base: openai-compatible
    url: http://127.0.0.1:9/v1
    enabled: true
    models:
      - {id: beta-strong, family: qwen, roles: [solver, critic, synthesizer], context_tokens: null}
    limits: {rpm: 1000, rpd: 1000, tpm: null}
  gamma:
    base: openai-compatible
    url: http://127.0.0.1:9/v1
    enabled: true
    models:
      - {id: gamma-flash, family: gemini, roles: [researcher, planner], context_tokens: null}
    limits: {rpm: null, rpd: null, tpm: null}
"""

DAY_YAML = CUSTOM_YAML.replace(
    "- {id: alpha-fast, family: gpt-oss, roles: [solver, planner], context_tokens: null}",
    "- {id: solo-day, family: gpt-oss, roles: [solver, planner], context_tokens: null}",
).replace("{rpm: 2, rpd: 10, tpm: null}", "{rpm: 1000, rpd: 3, tpm: null}", 1)

TPM_YAML = CUSTOM_YAML.replace(
    "- {id: alpha-fast, family: gpt-oss, roles: [solver, planner], context_tokens: null}",
    "- {id: solo-tpm, family: gpt-oss, roles: [solver, planner], context_tokens: null}",
).replace("{rpm: 2, rpd: 10, tpm: null}", "{rpm: 1000, rpd: null, tpm: 100}", 1)


def _factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _limiter(tmp_path, yaml_text=CUSTOM_YAML, **kwargs):
    path = tmp_path / "models.yaml"
    path.write_text(yaml_text, encoding="utf-8")
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
    async with await limiter.acquire("alpha", fingerprint):
        pass
    async with await limiter.acquire("alpha", fingerprint):
        pass
    started = time.monotonic()
    async with await limiter.acquire("alpha", fingerprint):
        pass
    assert time.monotonic() - started >= 1.8


async def test_rpm_exhaustion_raises_when_wait_too_long(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path, max_wait_seconds=0.3)
    fingerprint = fingerprint_key("k1")
    async with await limiter.acquire("alpha", fingerprint):
        pass
    async with await limiter.acquire("alpha", fingerprint):
        pass
    with pytest.raises(QuotaExhausted):
        await limiter.acquire("alpha", fingerprint)


async def test_tpm_window_counts_estimated_tokens(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path, yaml_text=TPM_YAML, max_wait_seconds=0.5)
    fingerprint = fingerprint_key("k1")
    async with await limiter.acquire("alpha", fingerprint, est_tokens=60):
        pass
    assert limiter.remaining("alpha", fingerprint)["tpm_remaining"] == 40
    with pytest.raises(QuotaExhausted):
        await limiter.acquire("alpha", fingerprint, est_tokens=60)


async def test_parallel_calls_share_concurrency_cap(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path, max_in_flight=2)
    fingerprint = fingerprint_key("k-beta")
    active = 0
    peak = 0

    async def worker() -> None:
        nonlocal active, peak
        async with await limiter.acquire("beta", fingerprint):
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
    async with await limiter.acquire("alpha", fingerprint):
        pass
    assert not limiter.is_exhausted("alpha", fingerprint)
    limiter.report_429("alpha", fingerprint, retry_after=60.0)
    assert limiter.is_exhausted("alpha", fingerprint)
    assert limiter.remaining("alpha", fingerprint)["cooldown_seconds"] > 0
    started = time.monotonic()
    with pytest.raises(QuotaExhausted):
        await limiter.acquire("alpha", fingerprint)
    assert time.monotonic() - started < 1.0


async def test_429_without_retry_after_uses_default(tmp_path) -> None:
    limiter, _ = _limiter(tmp_path)
    fingerprint = fingerprint_key("k1")
    limiter.report_429("alpha", fingerprint, retry_after=None)
    assert limiter.remaining("alpha", fingerprint)["cooldown_seconds"] > 0


# ── Daily counters + rollover ─────────────────────────────────────


async def test_day_rollover_resets_counters(tmp_path) -> None:
    factory = _factory()
    limiter, _config = _limiter(tmp_path, yaml_text=DAY_YAML, session_factory=factory)
    fingerprint = fingerprint_key("k-day")
    yesterday = (date.fromisoformat(today_str()) - timedelta(days=1)).isoformat()

    db = factory()
    db.add(
        QuotaUsage(
            provider="alpha", key_fingerprint=fingerprint, day=yesterday, count=3
        )
    )
    db.commit()
    db.close()

    assert limiter.remaining("alpha", fingerprint)["rpd_remaining"] == 3
    for _ in range(3):
        async with await limiter.acquire("alpha", fingerprint):
            pass
    assert limiter.remaining("alpha", fingerprint)["rpd_remaining"] == 0
    with pytest.raises(QuotaExhausted):
        await limiter.acquire("alpha", fingerprint)
    assert limiter.is_exhausted("alpha", fingerprint)

    db = factory()
    rows = db.query(QuotaUsage).filter(QuotaUsage.provider == "alpha").all()
    by_day = {row.day: row.count for row in rows}
    assert by_day[yesterday] == 3  # yesterday untouched
    assert by_day[today_str()] == 3
    for row in rows:
        assert row.key_fingerprint == fingerprint
        assert "k-day" not in row.key_fingerprint
    db.close()


# ── Router + planner + status integration ─────────────────────────


def test_router_skips_exhausted_key(tmp_path) -> None:
    limiter, config = _limiter(tmp_path)
    keys = {"alpha": "k1", "beta": "k2", "gamma": "k3"}
    router = ModelRouter(config=config, keys=keys, limiter=limiter)
    assert router.get_live_count() == 3
    assert router.route("solver").provider_name == "alpha"

    limiter.report_429("alpha", fingerprint_key("k1"), retry_after=60.0)
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

    response = await providers_status(user_id="test-user")
    assert response.providers != []
    for entry in response.providers:
        assert set(entry.families) <= set(KNOWN_FAMILIES)
        assert entry.rpm_remaining is None or entry.rpm_remaining >= 0
        assert entry.rpd_remaining is None or entry.rpd_remaining >= 0
        assert entry.cooldown_seconds >= 0


def test_shared_singleton_exists() -> None:
    assert get_limiter() is get_limiter()
