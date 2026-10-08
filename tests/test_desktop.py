from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.core.config import settings
from src.main import app


@pytest.fixture
def desktop_mode():
    original_mode = settings.app_mode
    settings.app_mode = "desktop"
    yield
    settings.app_mode = original_mode

@pytest.fixture
def mock_keyring():
    with patch("keyring.get_password") as mock_get, \
         patch("keyring.set_password") as mock_set, \
         patch("keyring.delete_password") as mock_del:
        
        storage = {}
        def _get(service, username):
            return storage.get(f"{service}:{username}")
        def _set(service, username, password):
            storage[f"{service}:{username}"] = password
        def _del(service, username):
            if f"{service}:{username}" in storage:
                del storage[f"{service}:{username}"]
                
        mock_get.side_effect = _get
        mock_set.side_effect = _set
        mock_del.side_effect = _del
        
        yield mock_get, mock_set, mock_del

def test_token_enforcement(desktop_mode):
    client = TestClient(app)
    # Without token, should fail
    response = client.get("/api/providers/status")
    assert response.status_code == 401

    # With invalid token, should fail
    response = client.get("/api/providers/status", headers={"X-Assembly-Token": "invalid"})
    assert response.status_code == 401

    # With valid token, should pass
    # Since we need database for this endpoint to work properly without failing internally
    # But wait, GET /api/providers/status might require DB or Keystore.
    # Let's mock the keystore or use a simple endpoint
    response = client.get("/health")
    assert response.status_code == 200 # health is exempt

    with patch("src.api.keys.get_keystore") as mock_get_keystore:
        # Mock keystore so it doesn't try to access real or unmocked things
        response = client.get("/api/providers/status", headers={"X-Assembly-Token": settings.desktop_token})
        assert response.status_code == 200

def test_shutdown_endpoint(desktop_mode):
    client = TestClient(app)
    with patch("os.kill") as mock_kill:
        response = client.post("/shutdown", headers={"X-Assembly-Token": settings.desktop_token})
        assert response.status_code == 200
        mock_kill.assert_called_once()

def test_key_endpoints(desktop_mode, mock_keyring):
    client = TestClient(app)
    headers = {"X-Assembly-Token": settings.desktop_token}
    
    # Save key
    response = client.post("/api/keys", json={"provider": "gemini", "key": "test_key"}, headers=headers)
    assert response.status_code == 200
    
    # List keys
    response = client.get("/api/keys", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["provider"] == "gemini"
    assert data[0]["masked_key"] == "***"
    
    # Delete key
    response = client.delete("/api/keys/gemini", headers=headers)
    assert response.status_code == 200
    
    # List keys again
    response = client.get("/api/keys", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 0
