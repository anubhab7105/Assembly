"""Privacy notice catalog tests (PRD FR-35).

- privacy_note is optional on ProviderSpec (absent allowed, never fails).
- GET /api/catalog exposes per-provider privacy notes (names only, no keys).
"""

from fastapi.testclient import TestClient


def test_privacy_note_optional_in_schema(tmp_path) -> None:
    from src.providers.config import load_models_config
    from tests.conftest import make_models_yaml

    providers = {
        "pa": [{"id": "pa-m", "family": "gpt-oss", "roles": ["solver"]}],
    }
    config = load_models_config(make_models_yaml(tmp_path, providers))
    assert config.providers["pa"].privacy_note is None


def test_privacy_note_accepted_when_present(tmp_path) -> None:
    import yaml

    from src.providers.config import load_models_config
    from tests.conftest import DEFAULT_TEST_LIMITS, TEST_BASE_URL

    doc = {
        "providers": {
            "pa": {
                "base": "openai-compatible",
                "url": TEST_BASE_URL,
                "enabled": True,
                "privacy_note": "Custom note.",
                "models": [
                    {
                        "id": "pa-m",
                        "family": "gpt-oss",
                        "roles": ["solver"],
                        "scope": "model",
                        "limits": dict(DEFAULT_TEST_LIMITS),
                    }
                ],
            }
        }
    }
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    config = load_models_config(path)
    assert config.providers["pa"].privacy_note == "Custom note."


def test_catalog_exposes_privacy_notes() -> None:
    from src.main import app

    client = TestClient(app)
    res = client.get("/api/catalog")
    assert res.status_code == 200, res.text
    body = res.json()
    by_id = {p["id"]: p for p in body["providers"]}
    assert "gemini" in by_id
    assert (
        by_id["gemini"].get("privacy_note")
        == "Free-tier requests may be used by Google to improve its products. "
        "Avoid sending sensitive or confidential information."
    )
    # No keys in catalog response.
    assert "provider_keys" not in body
    for provider in body["providers"]:
        assert "privacy_note" in provider
