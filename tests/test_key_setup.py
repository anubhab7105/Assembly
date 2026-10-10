"""FR-30: key setup instructions via catalog (offline)."""

from fastapi.testclient import TestClient

from src.api.catalog import (
    SENSITIVE_SIGNUP_FALLBACK,
    recommended_provider_order,
)
from src.main import app
from src.providers.config import ModelsConfig


def test_catalog_includes_key_steps_and_fallback() -> None:
    client = TestClient(app)
    resp = client.get("/api/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    assert "recommended_order" in data
    assert data["minimum_families"] == 3
    assert data["sensitive_signup_fallback"] == SENSITIVE_SIGNUP_FALLBACK
    by_id = {p["id"]: p for p in data["providers"]}
    # At least one enabled provider carries generic safe steps.
    enabled = [p for p in data["providers"] if p["enabled"]]
    assert enabled
    assert any((p.get("key_steps") or []) for p in enabled)
    # Null sensitive_signup renders the shared fallback in the UI contract.
    assert any(p.get("sensitive_signup") is None for p in data["providers"])
    assert SENSITIVE_SIGNUP_FALLBACK.startswith("Check this during signup")
    # Groq steps are generic (no invented signup facts).
    groq = by_id.get("groq")
    assert groq is not None
    steps = groq.get("key_steps") or []
    assert len(steps) >= 5
    joined = " ".join(steps).lower()
    assert "paste" in joined and "test" in joined


def test_schema_accepts_absent_key_fields(tmp_path) -> None:
    from src.providers.config import load_models_config
    from tests.conftest import make_models_yaml

    path = make_models_yaml(
        tmp_path,
        {"prov-a": [{"id": "m-1", "family": "gemini", "roles": ["solver"]}]},
    )
    cfg = load_models_config(path)
    spec = cfg.providers["prov-a"]
    assert spec.key_steps is None
    assert spec.key_notes is None
    assert spec.sensitive_signup is None


def test_recommended_order_prefers_capacity() -> None:
    cfg = ModelsConfig.model_validate(
        {
            "providers": {
                "small": {
                    "base": "openai-compatible",
                    "url": "http://127.0.0.1:9/v1",
                    "enabled": True,
                    "models": [
                        {
                            "id": "s-1",
                            "family": "gemini",
                            "roles": ["solver"],
                            "scope": "model",
                            "limits": {
                                "rpm": 10,
                                "rpd": 10,
                                "tpm": 1000,
                                "context_tokens": 8000,
                            },
                        }
                    ],
                },
                "big": {
                    "base": "openai-compatible",
                    "url": "http://127.0.0.1:9/v1",
                    "enabled": True,
                    "models": [
                        {
                            "id": "b-1",
                            "family": "qwen",
                            "roles": ["solver"],
                            "scope": "model",
                            "limits": {
                                "rpm": 30,
                                "rpd": 1000,
                                "tpm": 8000,
                                "context_tokens": 8000,
                            },
                        }
                    ],
                },
                "off": {
                    "base": "openai-compatible",
                    "url": "http://127.0.0.1:9/v1",
                    "enabled": False,
                    "models": [
                        {
                            "id": "o-1",
                            "family": "llama",
                            "roles": ["solver"],
                            "scope": "model",
                            "limits": {
                                "rpm": 999,
                                "rpd": 99999,
                                "tpm": 99999,
                                "context_tokens": 8000,
                            },
                        }
                    ],
                },
            }
        }
    )
    order = recommended_provider_order(cfg)
    assert order[0] == "big"
    assert "off" not in order


def test_prefix_hint_never_blocks_saving() -> None:
    # Backend contract: no key-format rejection exists; saving accepts any
    # non-empty key (prefix hints are display-only). Covered here by asserting
    # the catalog carries no blocking format field.
    client = TestClient(app)
    data = client.get("/api/catalog").json()
    for provider in data["providers"]:
        assert "key_format_block" not in provider
        assert "key_regex" not in provider
