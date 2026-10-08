"""Shared pytest fixtures for Assembly.

All fixtures are offline by construction: providers are MockProvider
instances (no network), the database is in-memory SQLite, and the
default mock plan sets needs_research=False so no search HTTP occurs.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.base import Base
from src.orchestration.orchestrator import Orchestrator
from src.providers.mock_provider import MockProvider


@dataclass
class MockAssignment:
    """Duck-typed stand-in for providers.router.ModelAssignment."""

    provider: MockProvider
    model: str
    provider_name: str


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
        )

    def route_for_planning(self) -> MockAssignment:
        return self.route("planner")


@pytest.fixture()
def fake_key() -> str:
    """Sentinel secret: must never appear in logs, DB rows, or responses."""
    return "sk-test-FAKE-KEY-DO-NOT-USE-7f3a9c4e2b"


@pytest.fixture(autouse=True)
def _block_network(monkeypatch) -> None:
    """Fail any test that attempts real external network I/O.

    Loopback is allowed: Windows asyncio builds its event loop on a
    127.0.0.1 socketpair, and respx intercepts HTTP without sockets.
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

    monkeypatch.setattr(socket.socket, "connect", _guarded)


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
