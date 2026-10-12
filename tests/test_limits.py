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


# ── Trusted-proxy boundary (fix-backlog item 8) ─────────────────────


def _spoofed_request(peer="10.0.0.1", headers=None):
    """Starlette request from `peer` carrying attacker-chosen headers."""
    from starlette.requests import Request

    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": raw,
            "client": (peer, 5000),
        }
    )


def test_forwarded_headers_ignored_by_default(monkeypatch):
    """TRUSTED_PROXY_COUNT=0: spoofed XFF/Forwarded cannot move buckets."""
    from src.core.rate_limit import client_ip

    monkeypatch.setattr(settings, "trusted_proxy_count", 0)
    spoofed = _spoofed_request(
        peer="10.0.0.1",
        headers={"x-forwarded-for": "9.9.9.9, 10.0.0.2", "forwarded": "for=8.8.8.8"},
    )
    assert client_ip(spoofed) == "10.0.0.1"


def test_trusted_proxy_honors_nth_from_right(monkeypatch):
    from src.core.rate_limit import client_ip

    headers = {"x-forwarded-for": "9.9.9.9, 10.0.0.2, 10.0.0.3"}
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    assert client_ip(_spoofed_request(headers=headers)) == "10.0.0.3"
    monkeypatch.setattr(settings, "trusted_proxy_count", 2)
    assert client_ip(_spoofed_request(headers=headers)) == "10.0.0.2"


def test_short_chain_falls_back_to_leftmost(monkeypatch):
    from src.core.rate_limit import client_ip

    monkeypatch.setattr(settings, "trusted_proxy_count", 5)
    req = _spoofed_request(headers={"x-forwarded-for": "9.9.9.9, 10.0.0.2"})
    assert client_ip(req) == "9.9.9.9"


def test_rfc_forwarded_header_supported(monkeypatch):
    from src.core.rate_limit import client_ip

    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    req = _spoofed_request(headers={"forwarded": "for=9.9.9.9"})
    assert client_ip(req) == "9.9.9.9"


def test_no_headers_uses_peer_ip(monkeypatch):
    from src.core.rate_limit import client_ip

    monkeypatch.setattr(settings, "trusted_proxy_count", 2)
    assert client_ip(_spoofed_request(peer="10.0.0.7")) == "10.0.0.7"


def test_invalid_proxy_count_fails_closed(monkeypatch):
    """Negative/garbage TRUSTED_PROXY_COUNT behaves as 0 (ignore headers)."""
    from src.core.rate_limit import client_ip

    for bad in (-3, "many"):
        monkeypatch.setattr(settings, "trusted_proxy_count", bad)
        req = _spoofed_request(headers={"x-forwarded-for": "9.9.9.9"})
        assert client_ip(req) == "10.0.0.1"


@pytest.mark.asyncio
async def test_spoofed_ips_share_one_bucket_by_default(monkeypatch):
    """End-to-end: two spoofed identities exhaust the same peer bucket."""
    from fastapi import HTTPException

    from src.core.rate_limit import check_rate_limit, client_ip

    monkeypatch.setattr(settings, "trusted_proxy_count", 0)
    buckets = {
        client_ip(_spoofed_request(headers={"x-forwarded-for": "1.1.1.1"})),
        client_ip(_spoofed_request(headers={"x-forwarded-for": "2.2.2.2"})),
    }
    assert buckets == {"10.0.0.1"}
    for _ in range(3):
        await check_rate_limit("ip:10.0.0.1", "spoof-probe", 3, 60)
    with pytest.raises(HTTPException) as exc_info:
        await check_rate_limit("ip:10.0.0.1", "spoof-probe", 3, 60)
    assert exc_info.value.status_code == 429
