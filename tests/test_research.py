"""Multi-provider research tests: all HTTP mocked via respx, no network."""

import logging

import httpx
import pytest
import respx

from src.core.config import settings
from src.orchestration.budget_controller import BudgetController
from src.research.providers import (
    ArxivSearchProvider,
    DuckDuckGoSearchProvider,
    SearchProvider,
    SearchProviderError,
    SearchQuotaExhausted,
    SearchResult,
    SemanticScholarSearchProvider,
    TavilySearchProvider,
    WikipediaSearchProvider,
)
from src.research.router import SearchRouter

ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>First Paper Title</title>
    <id>http://arxiv.org/abs/2301.00001</id>
    <summary>First abstract text.</summary>
    <published>2023-01-01T00:00:00Z</published>
  </entry>
  <entry>
    <title>Second Paper Title</title>
    <id>http://arxiv.org/abs/2301.00002</id>
    <summary>Second abstract text.</summary>
    <published>2023-02-01T00:00:00Z</published>
  </entry>
</feed>"""


class _StubProvider(SearchProvider):
    """In-memory provider double recording call order and count."""

    def __init__(
        self,
        name: str,
        results: list[SearchResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.provider_name = name
        self._results = results or []
        self._error = error
        self.calls: list[str] = []

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        self.calls.append(query)
        if self._error is not None:
            raise self._error
        return list(self._results[:max_results])


def _result(title: str = "T") -> SearchResult:
    return SearchResult(title=title, url="https://example.com", snippet="s")


# ── Schema ─────────────────────────────────────────────────────────────


def test_search_result_defaults() -> None:
    result = SearchResult(title="T", url="https://example.com")
    assert result.snippet == ""
    assert result.published is None
    assert result.source_type == "web"
    assert result.to_legacy_dict() == {
        "title": "T",
        "url": "https://example.com",
        "snippet": "",
    }


# ── Tavily ─────────────────────────────────────────────────────────────


@respx.mock
async def test_tavily_parses_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tavily_api_key", "tvly-test-key")
    provider = TavilySearchProvider()
    assert provider.is_available is True
    route = respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"title": "T", "url": "https://e.com", "content": "x" * 600}
                ]
            },
        )
    )
    results = await provider.search("mock query", max_results=1)
    assert route.called
    assert len(results) == 1
    assert results[0].snippet == "x" * 500
    assert results[0].source_type == "web"
    assert results[0].published is None


async def test_tavily_unavailable_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tavily_api_key", "")
    provider = TavilySearchProvider()
    assert provider.is_available is False
    with pytest.raises(SearchProviderError):
        await provider.search("anything")


@respx.mock
async def test_tavily_quota_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tavily_api_key", "tvly-test-key")
    respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(429, json={"error": "rate limited"})
    )
    with pytest.raises(SearchQuotaExhausted):
        await TavilySearchProvider().search("q")


# ── Wikipedia ──────────────────────────────────────────────────────────


@respx.mock
async def test_wikipedia_parses_and_strips_html() -> None:
    respx.get("https://en.wikipedia.org/w/api.php").mock(
        return_value=httpx.Response(
            200,
            json={
                "query": {
                    "search": [
                        {
                            "title": "Python",
                            "pageid": 42,
                            "snippet": 'a <span class="x">lang</span>',
                        }
                    ]
                }
            },
        )
    )
    results = await WikipediaSearchProvider().search("python")
    assert len(results) == 1
    assert results[0].title == "Python"
    assert results[0].url == "https://en.wikipedia.org/?curid=42"
    assert results[0].snippet == "a lang"
    assert results[0].source_type == "encyclopedia"


async def test_empty_query_makes_no_calls() -> None:
    assert await WikipediaSearchProvider().search("   ") == []
    assert await ArxivSearchProvider().search("") == []


# ── arXiv ───────────────────────────────────────────────────────────────


@respx.mock
async def test_arxiv_parses_feed() -> None:
    respx.get("https://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text=ARXIV_FEED)
    )
    results = await ArxivSearchProvider().search("quantum", max_results=2)
    assert [r.title for r in results] == ["First Paper Title", "Second Paper Title"]
    assert results[0].url == "http://arxiv.org/abs/2301.00001"
    assert results[0].snippet == "First abstract text."
    assert results[0].published == "2023-01-01T00:00:00Z"
    assert all(r.source_type == "paper" for r in results)


# ── Semantic Scholar ───────────────────────────────────────────────────


@respx.mock
async def test_semantic_scholar_parses() -> None:
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "title": "P1",
                        "abstract": "A" * 600,
                        "url": "https://s2.org/p1",
                        "year": 2023,
                    },
                    {
                        "title": "P2",
                        "abstract": "",
                        "url": "",
                        "openAccessPdf": {"url": "https://pdf.org/p2.pdf"},
                        "year": None,
                    },
                ]
            },
        )
    )
    results = await SemanticScholarSearchProvider().search("ml", max_results=2)
    assert len(results) == 2
    assert results[0].snippet == "A" * 500
    assert results[0].published == "2023"
    assert results[1].url == "https://pdf.org/p2.pdf"
    assert results[1].published is None
    assert all(r.source_type == "paper" for r in results)


@respx.mock
async def test_semantic_scholar_quota_carries_retry_after() -> None:
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(429, headers={"retry-after": "5"}, json={})
    )
    with pytest.raises(SearchQuotaExhausted) as exc_info:
        await SemanticScholarSearchProvider().search("ml")
    assert exc_info.value.retry_after == 5.0


# ── DuckDuckGo (unofficial) ────────────────────────────────────────────


def test_duckduckgo_marked_unofficial() -> None:
    assert DuckDuckGoSearchProvider.IS_UNOFFICIAL is True
    assert "UNOFFICIAL" in (DuckDuckGoSearchProvider.__doc__ or "")


@respx.mock
async def test_duckduckgo_parses_topics() -> None:
    respx.get("https://api.duckduckgo.com/").mock(
        return_value=httpx.Response(
            200,
            json={
                "AbstractText": "",
                "AbstractURL": "",
                "RelatedTopics": [
                    {"Text": "First hit", "FirstURL": "https://e.com/1"},
                    {
                        "Name": "group",
                        "Topics": [
                            {"Text": "Nested hit", "FirstURL": "https://e.com/2"},
                            {"Text": "", "FirstURL": ""},
                        ],
                    },
                ],
            },
        )
    )
    results = await DuckDuckGoSearchProvider().search("q", max_results=2)
    assert [r.url for r in results] == ["https://e.com/1", "https://e.com/2"]
    assert all(r.source_type == "unofficial" for r in results)


# ── Router: ordering ───────────────────────────────────────────────────


async def test_router_research_prefers_academic() -> None:
    names = ["tavily", "wikipedia", "arxiv", "semantic_scholar", "duckduckgo"]
    stubs = [_StubProvider(name) for name in names]
    router = SearchRouter(providers=stubs)
    ordered = [p.provider_name for p in router.order_for("research")]
    assert ordered[:3] == ["semantic_scholar", "arxiv", "wikipedia"]
    assert ordered[-1] == "duckduckgo"


async def test_router_general_prefers_web() -> None:
    names = ["arxiv", "semantic_scholar", "tavily", "wikipedia", "duckduckgo"]
    stubs = [_StubProvider(name) for name in names]
    router = SearchRouter(providers=stubs)
    ordered = [p.provider_name for p in router.order_for("general")]
    assert ordered[:2] == ["tavily", "wikipedia"]
    assert ordered[-1] == "duckduckgo"


async def test_router_falls_back_on_quota() -> None:
    first = _StubProvider("tavily", error=SearchQuotaExhausted("tavily"))
    second = _StubProvider("wikipedia", results=[_result("from-fallback")])
    router = SearchRouter(providers=[first, second])
    results = await router.search("q", problem_type="general")
    assert [r.title for r in results] == ["from-fallback"]
    assert first.calls == ["q"]
    assert second.calls == ["q"]


async def test_router_total_failure_returns_empty() -> None:
    stubs = [
        _StubProvider("tavily", error=SearchQuotaExhausted("tavily")),
        _StubProvider("wikipedia", error=SearchProviderError("down")),
    ]
    router = SearchRouter(providers=stubs)
    assert await router.search("q") == []


async def test_router_unexpected_error_falls_back() -> None:
    """Non-provider exceptions (e.g. validation) never escape search()."""
    first = _StubProvider("tavily", error=ValueError("bad shape"))
    second = _StubProvider("wikipedia", results=[_result("recovered")])
    router = SearchRouter(providers=[first, second])
    assert [r.title for r in await router.search("q")] == ["recovered"]
    broken = SearchRouter(
        providers=[_StubProvider("tavily", error=RuntimeError("boom"))]
    )
    assert await broken.search("q") == []


# ── Router: budget ─────────────────────────────────────────────────────


async def test_router_max_searches_budget_enforced() -> None:
    stub = _StubProvider("tavily", results=[_result()])
    router = SearchRouter(providers=[stub], max_searches=1)
    assert len(await router.search("first query")) == 1
    assert await router.search("second query") == []
    assert len(stub.calls) == 1
    assert router.searches_used == 1


async def test_router_budget_controller_blocks_without_calling() -> None:
    budget = BudgetController(3)
    budget.state.searches_used = budget.state.max_searches

    async def _fail(_query: str, _max_results: int = 5) -> list[SearchResult]:
        raise AssertionError("provider must not be called on exhausted budget")

    stub = _StubProvider("tavily", results=[_result()])
    stub.search = _fail  # type: ignore[method-assign]
    router = SearchRouter(providers=[stub], budget_controller=budget)
    assert await router.search("q") == []


async def test_router_empty_query_spends_no_budget() -> None:
    stub = _StubProvider("tavily", results=[_result()])
    router = SearchRouter(providers=[stub], max_searches=1)
    assert await router.search("   ") == []
    assert stub.calls == []
    assert router.searches_used == 0


# ── Router: cache ──────────────────────────────────────────────────────


async def test_router_cache_dedupes_identical_queries() -> None:
    stub = _StubProvider("tavily", results=[_result()])
    router = SearchRouter(providers=[stub], max_searches=10)
    first = await router.search("  Hello World ")
    second = await router.search("hello world")
    assert len(first) == len(second) == 1
    assert len(stub.calls) == 1
    assert router.cache_size == 1
    assert router.searches_used == 1


async def test_router_cache_empty_pass_not_refetched() -> None:
    stub = _StubProvider("tavily", results=[])
    router = SearchRouter(providers=[stub])
    assert await router.search("nohits") == []
    assert await router.search("nohits") == []
    assert len(stub.calls) == 1


# ── Key-leak scan ──────────────────────────────────────────────────────


@respx.mock
async def test_search_never_leaks_key(
    monkeypatch: pytest.MonkeyPatch,
    fake_key: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(settings, "tavily_api_key", fake_key)
    route = respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"title": "T", "url": "https://e.com", "content": "c"}]},
        )
    )
    with caplog.at_level(logging.INFO, logger="assembly"):
        results = await TavilySearchProvider().search("leak probe")
        router = SearchRouter(
            providers=[TavilySearchProvider(), _StubProvider("wikipedia")],
            max_searches=5,
        )
        await router.search("leak probe")
    assert route.called
    assert fake_key not in caplog.text
    assert fake_key not in str(results)
    assert fake_key not in str(router.searches_used)
