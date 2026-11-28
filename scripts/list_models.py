"""List currently available model IDs per provider (names only, never keys).

Usage:  python scripts/list_models.py
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env.dev", override=True)
sys.path.insert(0, str(PROJECT_ROOT))

import httpx

from src.core.config import settings
from src.core.keystore import reveal


async def openai_compatible_models(
    client: httpx.AsyncClient, label: str, base_url: str, key: str
) -> None:
    try:
        response = await client.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {reveal(key)}"},
        )
        response.raise_for_status()
        ids = sorted(m["id"] for m in response.json().get("data", []))
        print(f"{label} ({len(ids)}):")
        for model_id in ids:
            print(f"  {model_id}")
    except Exception as exc:  # noqa: BLE001 — probe must report FAILED, never crash
        print(f"{label}: FAILED ({type(exc).__name__})")


async def gemini_models() -> None:
    """List Gemini models through the SDK's async iterator and close its client."""
    from google import genai

    client = genai.Client(api_key=reveal(settings.gemini_api_key))
    ids: list[str] = []
    try:
        async for model in await client.aio.models.list():
            if "generateContent" in (model.supported_actions or []):
                ids.append(model.name.removeprefix("models/"))
    finally:
        await client.aio.aclose()
    print(f"gemini ({len(ids)}):")
    for model_id in sorted(ids):
        print(f"  {model_id}")


async def main() -> None:
    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if settings.has_provider("groq"):
            await openai_compatible_models(
                client, "groq", "https://api.groq.com/openai/v1", settings.groq_api_key
            )
        if settings.has_provider("cerebras"):
            await openai_compatible_models(
                client, "cerebras", "https://api.cerebras.ai/v1", settings.cerebras_api_key
            )
        if settings.has_provider("mistral"):
            await openai_compatible_models(
                client, "mistral", "https://api.mistral.ai/v1", settings.mistral_api_key
            )
        if settings.has_provider("nvidia"):
            await openai_compatible_models(
                client, "nvidia", "https://integrate.api.nvidia.com/v1", settings.nvidia_api_key
            )

        # OpenRouter's model catalogue is public (no key needed).
        try:
            response = await client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()
            free = sorted(
                model["id"]
                for model in response.json().get("data", [])
                if any(
                    endpoint.get("pricing", {}).get("prompt") == "0"
                    for endpoint in [model]
                )
                or ":free" in model["id"]
            )
            print(f"openrouter free ({len(free)}):")
            for model_id in free:
                print(f"  {model_id}")
        except Exception as exc:  # noqa: BLE001 — probe must report FAILED, never crash
            print(f"openrouter: FAILED ({type(exc).__name__})")

    # SDK client has its own async transport lifecycle, outside httpx.
    if settings.has_provider("gemini"):
        try:
            await gemini_models()
        except Exception as exc:  # noqa: BLE001 — probe must report FAILED, never crash
            print(f"gemini: FAILED ({type(exc).__name__})")


if __name__ == "__main__":
    asyncio.run(main())
