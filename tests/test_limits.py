import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi.testclient import TestClient
from src.main import app
from src.core.rate_limit import _rate_limit_history, _global_executions, _user_executions, execution_tracker
from src.core.security import get_current_user_id

@pytest.fixture(autouse=True)
def reset_limits():
    """Reset all limits before each test."""
    _rate_limit_history.clear()
    global _global_executions
    _global_executions = 0
    _user_executions.clear()
    
    # Override auth for all tests here
    app.dependency_overrides[get_current_user_id] = lambda: "test-user-id"
    yield
    app.dependency_overrides.pop(get_current_user_id, None)

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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Limit is 10
        for _ in range(10):
            res = await client.get("/api/executions/preflight?question=test&time_budget_minutes=5")
            assert res.status_code in (200, 422)
        
        # 11th should be rate limited
        res = await client.get("/api/executions/preflight?question=test&time_budget_minutes=5")
        assert res.status_code == 429
        assert "Rate limit exceeded" in res.json()["detail"]

@pytest.mark.asyncio
async def test_concurrent_execution_cap(db_session, monkeypatch):
    """Test the concurrent execution cap."""
    # Fake acquiring 1 execution for the user
    await execution_tracker.acquire("test-user-id")
    
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post(
                "/api/executions/",
                json={"question": "test", "time_budget_minutes": 5},
            )
            assert res.status_code == 429
            assert "Concurrent execution limit reached" in res.json()["detail"]
    finally:
        await execution_tracker.release("test-user-id")

@pytest.mark.asyncio
async def test_websocket_origin_check(monkeypatch):
    """Test WebSocket origin checks."""
    from src.core.config import settings
    monkeypatch.setattr(settings, "app_mode", "web")
    monkeypatch.setattr(settings, "frontend_url", "https://assembly.example.com")
    
    client = TestClient(app)
    
    with pytest.raises(Exception):
        with client.websocket_connect("/api/executions/test_id/ws?token=fake", headers={"origin": "https://evil.com"}):
            pass
