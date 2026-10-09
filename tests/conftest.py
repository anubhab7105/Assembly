"""Shared pytest fixtures for Assembly.

All fixtures are offline by construction: providers are MockProvider
instances (no network), the database is in-memory SQLite, and the
default mock plan sets needs_research=False so no search HTTP occurs.
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.base import Base
from src.orchestration.orchestrator import Orchestrator
from src.providers.mock_provider import MockProvider


@dataclass
class MockAssignment:
    """Duck-typed stand-in for providers.router.RoutingDecision."""

    provider: MockProvider
    model: str
    provider_name: str
    family: str = "mock"
    role: str = ""
    reason: str = "mock routing"


@dataclass
class MockTeamRouting:
    """Duck-typed stand-in for providers.router.TeamRouting."""

    decisions: list
    warnings: list = None
    degraded: bool = False
    families: list = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []
        if self.families is None:
            self.families = []


class MockRouter:
    """Minimal router backed entirely by MockProviders."""

    def __init__(self, providers: list[MockProvider]) -> None:
        self._providers: dict[str, MockProvider] = {
            p.provider_name: p for p in providers
        }

    def get_available_providers(self) -> list[str]:
        return list(self._providers.keys())

    def get_live_count(self) -> int:
        return len(self._providers)

    def route(
        self,
        agent_type: str,
        problem_type: str = "general",
        complexity: str = "medium",
        time_budget_minutes: int = 5,
        prefer_provider: str | None = None,
    ) -> MockAssignment:
        name = (
            prefer_provider
            if prefer_provider in self._providers
            else next(iter(self._providers))
        )
        provider = self._providers[name]
        return MockAssignment(
            provider=provider,
            model=provider.get_available_models()[0],
            provider_name=name,
            role=agent_type,
        )

    def route_for_planning(self) -> MockAssignment:
        return self.route("planner")

    def route_team(
        self,
        team: list,
        problem_type: str = "general",
        complexity: str = "medium",
        time_budget_minutes: int = 5,
    ) -> MockTeamRouting:
        decisions = [self.route(spec.get("agent_type", "solver")) for spec in team]
        return MockTeamRouting(
            decisions=decisions,
            families=sorted({d.provider_name for d in decisions}),
        )


@pytest.fixture()
def fake_key() -> str:
    """Sentinel secret: must never appear in logs, DB rows, or responses."""
    return "sk-test-FAKE-KEY-DO-NOT-USE-7f3a9c4e2b"


# ── New-shape models.yaml builder (single source for test catalogs) ──

DEFAULT_TEST_LIMITS: dict[str, Any] = {
    "rpm": 60,
    "rpd": 1000,
    "tpm": 10000,
    "context_tokens": 32000,
}

TEST_BASE_URL = "http://127.0.0.1:9/v1"


def make_models_yaml(
    tmp_path: Path,
    providers: dict[str, list[dict[str, Any]]],
    *,
    base: str = "openai-compatible",
    url: str = TEST_BASE_URL,
    enabled: bool | dict[str, bool] = True,
    filename: str = "models.yaml",
) -> Path:
    """Write a new-shape tmp models.yaml for tests. Returns the path.

    providers maps provider id → list of model dicts with id/family/roles
    plus optional scope and (partial) limits. Omitted scope/limit fields
    default to model scope + DEFAULT_TEST_LIMITS (all filled, so the
    router admits the provider); pass explicit values — including None
    for unknown or "unlimited" — to exercise validation/quota paths.
    Keys deliberately omitted from a model dict (e.g. no "id") stay
    omitted so loader validation tests keep failing loudly.
    """
    doc: dict[str, Any] = {"providers": {}}
    for provider_id, models in providers.items():
        flag = enabled if isinstance(enabled, bool) else enabled.get(provider_id, True)
        rendered: list[dict[str, Any]] = []
        for spec in models:
            merged: dict[str, Any] = dict(DEFAULT_TEST_LIMITS)
            merged.update(spec.get("limits") or {})
            entry: dict[str, Any] = {}
            for field in ("id", "family", "roles"):
                if field in spec:
                    entry[field] = spec[field]
            entry["scope"] = spec.get("scope", "model")
            entry["limits"] = merged
            rendered.append(entry)
        doc["providers"][provider_id] = {
            "base": base,
            "url": url,
            "enabled": flag,
            "models": rendered,
        }
    path = Path(tmp_path) / filename
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _block_network(monkeypatch) -> None:
    """Fail any test that attempts real external network I/O.

    Loopback is allowed: Windows asyncio builds its event loop on a
    127.0.0.1 socketpair, and respx intercepts HTTP without sockets.
    DNS is blocked outright: against a blackholed resolver getaddrinfo
    hangs for tens of seconds instead of failing fast.
    """
    import socket

    real_connect = socket.socket.connect

    def _guarded(
        self: socket.socket, address: object, *args: object, **kwargs: object
    ) -> object:
        host = address[0] if isinstance(address, tuple) else address
        if host in ("127.0.0.1", "::1", "localhost"):
            return real_connect(self, address, *args, **kwargs)
        raise RuntimeError(f"Network access is blocked in tests (tried {host})")

    def _blocked_dns(host, *args: object, **kwargs: object) -> object:
        if host in ("127.0.0.1", "::1", "localhost"):
            return socket._real_getaddrinfo(host, *args, **kwargs)
        raise RuntimeError(f"DNS is blocked in tests (tried {host})")

    monkeypatch.setattr(socket.socket, "connect", _guarded)
    socket._real_getaddrinfo = socket.getaddrinfo
    monkeypatch.setattr(socket, "getaddrinfo", _blocked_dns)


@pytest.fixture()
def mock_providers() -> list[MockProvider]:
    return [
        MockProvider(provider_name="mock-a"),
        MockProvider(provider_name="mock-b"),
        MockProvider(provider_name="mock-c"),
    ]


@pytest.fixture()
def mock_router(mock_providers: list[MockProvider]) -> MockRouter:
    return MockRouter(mock_providers)


@pytest.fixture()
def orchestrator(mock_router: MockRouter) -> Orchestrator:
    """Full Orchestrator with its router swapped for mocks (search untouched)."""
    orch = Orchestrator()
    orch.router = mock_router  # type: ignore[assignment]
    return orch


@pytest.fixture()
def db_session() -> Session:
    """In-memory SQLite session with all Assembly tables created."""
    engine = create_engine("sqlite:///:memory:")
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = testing_session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def clear_rate_limits() -> None:
    """Reset the global rate limit history between tests."""
    from src.core.rate_limit import _rate_limit_history, execution_tracker, _global_executions, _user_executions
    _rate_limit_history.clear()
    _global_executions = 0
    _user_executions.clear()
