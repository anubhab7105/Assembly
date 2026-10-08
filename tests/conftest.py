"""Shared pytest fixtures for Assembly.

All fixtures are offline by construction: providers are MockProvider
instances (no network), the database is in-memory SQLite, and the
default mock plan sets needs_research=False so no search HTTP occurs.
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.base import Base  # noqa: E402
from src.orchestration.orchestrator import Orchestrator  # noqa: E402
from src.providers.mock_provider import MockProvider  # noqa: E402


@dataclass
class MockAssignment:
    """Duck-typed stand-in for providers.router.ModelAssignment."""

    provider: MockProvider
    model: str
    provider_name: str


class MockRouter:
    """Minimal router backed entirely by MockProviders."""

    def __init__(self, providers: List[MockProvider]) -> None:
        self._providers: Dict[str, MockProvider] = {p.provider_name: p for p in providers}

    def get_available_providers(self) -> List[str]:
        return list(self._providers.keys())

    def get_live_count(self) -> int:
        return len(self._providers)

    def route(
        self,
        agent_type: str,
        problem_type: str = "general",
        complexity: str = "medium",
        time_budget_minutes: int = 5,
        prefer_provider: Optional[str] = None,
    ) -> MockAssignment:
        name = prefer_provider if prefer_provider in self._providers else next(iter(self._providers))
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
    """Fail any test that attempts real network I/O (respx intercepts HTTP)."""
    import socket

    def _blocked(self: socket.socket, *args: object, **kwargs: object) -> object:
        raise RuntimeError("Network access is blocked in tests")

    monkeypatch.setattr(socket.socket, "connect", _blocked)


@pytest.fixture()
def mock_providers() -> List[MockProvider]:
    return [
        MockProvider(provider_name="mock-a"),
        MockProvider(provider_name="mock-b"),
        MockProvider(provider_name="mock-c"),
    ]


@pytest.fixture()
def mock_router(mock_providers: List[MockProvider]) -> MockRouter:
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
