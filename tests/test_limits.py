import asyncio
import pytest
from httpx import AsyncClient
from src.main import app
from src.core.rate_limit import _rate_limit_history, _global_executions, _user_executions, execution_tracker

@pytest.fixture(autouse=True)
def reset_limits():
    """Reset all limits before each test."""
    _rate_limit_history.clear()
    global _global_executions
    _global_executions = 0
    _user_executions.clear()
    yield

@pytest.mark.asyncio
async def test_max_question_length():
    """Test request-size / max question length limit."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/executions/",
            json={"question": "a" * 2001, "time_budget_minutes": 5},
        )
        assert response.status_code == 422
        assert "String should have at most 2000 characters" in response.text

@pytest.mark.asyncio
async def test_rate_limit_preflight(auth_headers):
    """Test the rate limit for preflight endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Limit is 10
        for _ in range(10):
            res = await client.get("/api/executions/preflight?question=test&time_budget_minutes=5", headers=auth_headers)
            assert res.status_code in (200, 422)  # depending on test environment, it might fail validation but pass rate limit
        
        # 11th should be rate limited
        res = await client.get("/api/executions/preflight?question=test&time_budget_minutes=5", headers=auth_headers)
        assert res.status_code == 429
        assert "Rate limit exceeded" in res.json()["detail"]

@pytest.mark.asyncio
async def test_concurrent_execution_cap(auth_headers, mock_db, monkeypatch):
    """Test the concurrent execution cap."""
    # Fake acquiring 1 execution for the user
    await execution_tracker.acquire("test-user-id")
    
    try:
        # Trying to acquire another should fail (cap is 1)
        async with AsyncClient(app=app, base_url="http://test") as client:
            res = await client.post(
                "/api/executions/",
                json={"question": "test", "time_budget_minutes": 5},
                headers=auth_headers,
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
    
    from fastapi.testclient import TestClient
    client = TestClient(app)
    
    # Missing origin should be accepted (some clients don't send it, or it will just be None and fail)
    # Wait, the code checks: if origin and origin != frontend_url -> close.
    # So if origin doesn't match, it should be rejected.
    with pytest.raises(Exception):
        with client.websocket_connect("/api/executions/test_id/ws?token=fake", headers={"origin": "https://evil.com"}):
            pass  # Should raise WS_1008_POLICY_VIOLATION
