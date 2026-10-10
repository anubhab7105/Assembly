import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from src.core.config import settings
from src.core.rate_limit import _ip_executions, _rate_limit_history
from src.database.base import get_db
from src.main import app


@pytest.fixture(autouse=True)
def reset_limits():
    """Reset all limits before each test (per-IP, no accounts)."""
    _rate_limit_history.clear()
    import src.core.rate_limit as rl

    rl._global_executions = 0
    _ip_executions.clear()
    app.dependency_overrides.pop(get_db, None)
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_max_question_length():
    """Test request-size / max question length limit."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/executions/",
            json={"question": "a" * 2001, "time_budget_minutes": 5},
        )
        assert response.status_code == 422
        assert "Invalid request." in response.text


@pytest.mark.asyncio
async def test_rate_limit_preflight():
    """Test the rate limit for preflight endpoint."""
    body = {"question": "test", "time_budget_minutes": 5}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(10):
            res = await client.post("/api/preflight", json=body)
            assert res.status_code in (200, 422)

        res = await client.post("/api/preflight", json=body)
        assert res.status_code == 429
        assert "Rate limit exceeded" in res.json()["detail"]


@pytest.mark.asyncio
async def test_concurrent_execution_cap(db_session, monkeypatch):
    """Test the per-IP concurrent execution cap (no accounts)."""
    import src.core.rate_limit as rl

    app.dependency_overrides[get_db] = lambda: db_session
    monkeypatch.setattr(rl, "MAX_RUNS_PER_IP", 0)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/executions/",
            json={"question": "test", "time_budget_minutes": 5},
        )
        assert res.status_code == 429
        assert "Concurrent execution limit" in res.json()["detail"] or "Global" in res.json()["detail"]


@pytest.mark.asyncio
async def test_websocket_origin_check(monkeypatch):
    """Test WebSocket origin checks."""
    monkeypatch.setattr(settings, "app_mode", "web")
    monkeypatch.setattr(settings, "frontend_url", "https://assembly.example.com")
    monkeypatch.setattr(settings, "cors_allow_list", "https://assembly.example.com")

    client = TestClient(app)

    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "/api/executions/ws/test_id", headers={"origin": "https://evil.com"}
        ) as ws,
    ):
        ws.receive_text()
