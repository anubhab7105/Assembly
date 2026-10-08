"""List currently available model IDs per provider (names only, never keys).

Usage:  python scripts/list_models.py
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env.dev", override=True)
sys.path.insert(0, str(PROJECT_ROOT))

import httpx

from src.core.config import settings
from src.core.keystore import reveal


def openai_compatible_models(label: str, base_url: str, key: str) -> None:
    try:
        response = httpx.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {reveal(key)}"},
            timeout=30.0,
        )
        response.raise_for_status()
        ids = sorted(m["id"] for m in response.json().get("data", []))
        print(f"{label} ({len(ids)}):")
        for model_id in ids:
            print(f"  {model_id}")
    except Exception as exc:  # noqa: BLE001 — probe must report FAILED, never crash
        print(f"{label}: FAILED ({type(exc).__name__})")


def main() -> None:
    if settings.has_provider("groq"):
        openai_compatible_models(
            "groq", "https://api.groq.com/openai/v1", settings.groq_api_key
        )
    if settings.has_provider("cerebras"):
        openai_compatible_models(
            "cerebras", "https://api.cerebras.ai/v1", settings.cerebras_api_key
        )
    # OpenRouter model catalog is public (no key needed).
    try:
        response = httpx.get("https://openrouter.ai/api/v1/models", timeout=30.0)
        response.raise_for_status()
        free = sorted(
            m["id"]
            for m in response.json().get("data", [])
            if any(ep.get("pricing", {}).get("prompt") == "0" for ep in [m])
            or ":free" in m["id"]
        )
        print(f"openrouter free ({len(free)}):")
        for model_id in free:
            print(f"  {model_id}")
    except Exception as exc:  # noqa: BLE001 — probe must report FAILED, never crash
        print(f"openrouter: FAILED ({type(exc).__name__})")

    # Gemini via SDK model listing.
    if settings.has_provider("gemini"):
        try:
            import google.generativeai as genai

            genai.configure(api_key=reveal(settings.gemini_api_key))
            ids = sorted(
                m.name.replace("models/", "")
                for m in genai.list_models()
                if "generateContent" in m.supported_generation_methods
            )
            print(f"gemini ({len(ids)}):")
            for model_id in ids:
                print(f"  {model_id}")
        except Exception as exc:  # noqa: BLE001 — probe must report FAILED, never crash
            print(f"gemini: FAILED ({type(exc).__name__})")


if __name__ == "__main__":
    main()
