"""Security regression tests for HTTP request-boundary handling."""

from fastapi.testclient import TestClient

from src.core.config import settings
from src.main import app


def test_malformed_content_length_is_rejected_without_internal_error(monkeypatch):
    """Invalid Content-Length must not become an unhandled 500 or leak data."""
    monkeypatch.setattr(settings, "app_mode", "web")
    monkeypatch.setattr(settings, "app_env", "development")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(
        "/health",
        headers={"content-length": "not-a-number"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid Content-Length."}
    assert "not-a-number" not in response.text


def test_negative_content_length_is_rejected_without_processing_body(monkeypatch):
    """Negative request sizes are invalid even when they don't exceed the cap."""
    monkeypatch.setattr(settings, "app_mode", "web")
    monkeypatch.setattr(settings, "app_env", "development")
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(
        "/health",
        headers={"content-length": "-1"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid Content-Length."}


def test_oversized_content_length_keeps_existing_safe_response(monkeypatch):
    """Normal oversized-body handling remains deterministic and generic."""
    monkeypatch.setattr(settings, "app_mode", "web")
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "max_body_bytes", 8)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(
        "/health",
        headers={"content-length": "9"},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large."}
