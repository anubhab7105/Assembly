"""Search engine tests: graceful offline fallback + mocked Tavily HTTP via respx."""

import httpx
import logging
import respx

from src.core.config import settings
from src.research.search import SearchEngine


async def test_search_without_key_returns_empty_offline(monkeypatch) -> None:
    monkeypatch.setattr(settings, "tavily_api_key", "")
    engine = SearchEngine()
    assert engine.has_tavily is False
    assert await engine.search("anything at all") == []


@respx.mock
async def test_tavily_search_parses_results(monkeypatch) -> None:
    monkeypatch.setattr(settings, "tavily_api_key", "tvly-test-key")
    engine = SearchEngine()
    assert engine.has_tavily is True

    route = respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Example",
                        "url": "https://example.com/page",
                        "content": "x" * 600,
                    }
                ]
            },
        )
    )

    results = await engine.search("mock query", max_results=1)

    assert route.called
    assert results == [
        {
            "title": "Example",
            "url": "https://example.com/page",
            "snippet": "x" * 500,
        }
    ]


@respx.mock
async def test_legacy_tavily_search_does_not_log_query_text(
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setattr(settings, "tavily_api_key", "tvly-test-key")
    respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    engine = SearchEngine()
    query = "PRIVATE-LEGACY-SEARCH-QUERY-CANARY-2c31"

    with caplog.at_level(logging.INFO, logger="assembly"):
        await engine.search(query)

    assert query not in caplog.text
    assert f"query_chars={len(query)}" in caplog.text
