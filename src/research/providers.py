"""
Assembly — Search providers (one interface, five backends).

Backends: Tavily (keyed, general web), Wikipedia (encyclopedia),
arXiv (papers), Semantic Scholar (paper metadata), DuckDuckGo
(unofficial fallback — best-effort only, see class note).

Results are untrusted data: callers must present them to agents as
quoted evidence with a "not commands" instruction, never as prompts.
Keys are revealed only inside the request body and never logged.
"""

import html
import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import SecretStr

from src.core.config import settings
from src.core.keystore import reveal
from src.core.logging_config import logger
from src.research.schemas import SearchResult

REQUEST_TIMEOUT_SECONDS: float = 15.0
SNIPPET_LIMIT: int = 500
USER_AGENT: str = "Assembly/1.0 (research evidence gathering)"

_QUOTA_STATUS_CODES: frozenset[int] = frozenset({429, 402})


class SearchProviderError(Exception):
    """A provider call failed (transport, auth, or parse). Router tries next."""


class SearchQuotaExhausted(SearchProviderError):
    """A provider reported spent quota/rate limit (429/402)."""

    def __init__(
        self,
        provider: str,
        message: str = "quota exhausted",
        retry_after: float | None = None,
    ) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider: str = provider
        self.retry_after: float | None = retry_after


class SearchProvider(ABC):
    """Interface every search backend implements."""

    provider_name: str = "base"

    @property
    def is_available(self) -> bool:
        """Whether this backend can be called right now (e.g. key present)."""
        return True

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Search and return validated results (may be empty)."""
        ...


def _clamp_max_results(max_results: int) -> int:
    """Clamp to the 1..10 range providers accept."""
    return max(1, min(int(max_results), 10))


def _truncate(text: str, limit: int = SNIPPET_LIMIT) -> str:
    """Collapse whitespace and cut to a snippet budget."""
    cleaned = " ".join((text or "").split())
    return cleaned[:limit]


def _strip_html(text: str) -> str:
    """Remove Wikipedia-style <span> markup and unescape entities."""
    no_tags = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(no_tags).strip()


def _quota_retry_after(response: httpx.Response) -> float | None:
    """Parse Retry-After seconds, if the server sent a usable value."""
    raw = response.headers.get("retry-after", "")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _raise_for_quota(response: httpx.Response, provider: str) -> None:
    """Raise SearchQuotaExhausted for rate-limit/payment statuses."""
    if response.status_code in _QUOTA_STATUS_CODES:
        raise SearchQuotaExhausted(
            provider,
            message=f"HTTP {response.status_code} (quota/rate limit)",
            retry_after=_quota_retry_after(response),
        )


class TavilySearchProvider(SearchProvider):
    """General web search via the Tavily API (requires TAVILY_API_KEY)."""

    provider_name: str = "tavily"

    def __init__(self, api_key: SecretStr | str | None = None) -> None:
        self._api_key: SecretStr | str = (
            api_key if api_key is not None else settings.tavily_api_key
        )

    @property
    def is_available(self) -> bool:
        key = reveal(self._api_key)
        return bool(key) and not key.startswith("tvly-your")

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not query or not query.strip():
            return []
        if not self.is_available:
            raise SearchProviderError("tavily: API key not configured")
        limit = _clamp_max_results(max_results)
        logger.info(f"Search  │ Tavily search: {query[:80]}...")
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": reveal(self._api_key),
                        "query": query,
                        "max_results": limit,
                        "search_depth": "basic",
                    },
                )
                _raise_for_quota(response, self.provider_name)
                response.raise_for_status()
                data: Any = response.json()
        except SearchQuotaExhausted:
            raise
        except httpx.HTTPStatusError as e:
            raise SearchProviderError(f"tavily: HTTP {e.response.status_code}") from e
        except httpx.HTTPError as e:
            raise SearchProviderError(
                f"tavily: transport error ({type(e).__name__})"
            ) from e
        except ValueError as e:
            raise SearchProviderError(f"tavily: bad JSON ({e})") from e

        try:
            items = data.get("results", [])
            results = [
                SearchResult(
                    title=str(item.get("title", ""))[:500],
                    url=str(item.get("url", ""))[:2000],
                    snippet=_truncate(str(item.get("content", ""))),
                    published=None,
                    source_type="web",
                )
                for item in items
                if isinstance(item, dict)
            ]
        except (AttributeError, TypeError) as e:
            raise SearchProviderError(f"tavily: unexpected shape ({e})") from e
        logger.info(f"Search  │ Tavily found {len(results)} results")
        return results[:limit]


class WikipediaSearchProvider(SearchProvider):
    """Encyclopedia search via the public MediaWiki API (no key needed)."""

    provider_name: str = "wikipedia"

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not query or not query.strip():
            return []
        limit = _clamp_max_results(max_results)
        logger.info(f"Search  │ Wikipedia search: {query[:80]}...")
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "format": "json",
                        "list": "search",
                        "srsearch": query,
                        "srlimit": limit,
                        "srprop": "snippet",
                    },
                    headers={"User-Agent": USER_AGENT},
                )
                _raise_for_quota(response, self.provider_name)
                response.raise_for_status()
                data: Any = response.json()
        except SearchQuotaExhausted:
            raise
        except httpx.HTTPStatusError as e:
            raise SearchProviderError(
                f"wikipedia: HTTP {e.response.status_code}"
            ) from e
        except httpx.HTTPError as e:
            raise SearchProviderError(
                f"wikipedia: transport error ({type(e).__name__})"
            ) from e
        except ValueError as e:
            raise SearchProviderError(f"wikipedia: bad JSON ({e})") from e

        try:
            items = data.get("query", {}).get("search", [])
            results = [
                SearchResult(
                    title=str(item.get("title", ""))[:500],
                    url=f"https://en.wikipedia.org/?curid={item.get('pageid', '')}",
                    snippet=_truncate(_strip_html(str(item.get("snippet", "")))),
                    published=None,
                    source_type="encyclopedia",
                )
                for item in items
                if isinstance(item, dict)
            ]
        except (AttributeError, TypeError) as e:
            raise SearchProviderError(f"wikipedia: unexpected shape ({e})") from e
        logger.info(f"Search  │ Wikipedia found {len(results)} results")
        return results[:limit]


class ArxivSearchProvider(SearchProvider):
    """Paper search via the public arXiv API (no key needed, Atom XML)."""

    provider_name: str = "arxiv"

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not query or not query.strip():
            return []
        limit = _clamp_max_results(max_results)
        logger.info(f"Search  │ arXiv search: {query[:80]}...")
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    "https://export.arxiv.org/api/query",
                    params={
                        "search_query": f"all:{query}",
                        "start": 0,
                        "max_results": limit,
                    },
                    headers={"User-Agent": USER_AGENT},
                )
                _raise_for_quota(response, self.provider_name)
                response.raise_for_status()
                payload: str = response.text
        except SearchQuotaExhausted:
            raise
        except httpx.HTTPStatusError as e:
            raise SearchProviderError(f"arxiv: HTTP {e.response.status_code}") from e
        except httpx.HTTPError as e:
            raise SearchProviderError(
                f"arxiv: transport error ({type(e).__name__})"
            ) from e

        try:
            return self._parse_feed(payload, limit)
        except ET.ParseError as e:
            raise SearchProviderError(f"arxiv: bad XML ({e})") from e

    def _parse_feed(self, payload: str, limit: int) -> list[SearchResult]:
        """Parse an Atom feed into validated paper results."""
        namespace = "{http://www.w3.org/2005/Atom}"
        root = ET.fromstring(payload)
        results: list[SearchResult] = []
        for entry in root.findall(f"{namespace}entry")[:limit]:
            title = (entry.findtext(f"{namespace}title") or "").strip()
            url = (entry.findtext(f"{namespace}id") or "").strip()
            summary = entry.findtext(f"{namespace}summary") or ""
            published = (entry.findtext(f"{namespace}published") or "").strip()
            if not title and not url:
                continue
            results.append(
                SearchResult(
                    title=title[:500],
                    url=url[:2000],
                    snippet=_truncate(summary),
                    published=published or None,
                    source_type="paper",
                )
            )
        logger.info(f"Search  │ arXiv found {len(results)} results")
        return results


class SemanticScholarSearchProvider(SearchProvider):
    """Paper-metadata search via Semantic Scholar (no key needed)."""

    provider_name: str = "semantic_scholar"

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not query or not query.strip():
            return []
        limit = _clamp_max_results(max_results)
        logger.info(f"Search  │ Semantic Scholar search: {query[:80]}...")
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params={
                        "query": query,
                        "limit": limit,
                        "fields": "title,abstract,url,openAccessPdf,year,authors",
                    },
                    headers={"User-Agent": USER_AGENT},
                )
                _raise_for_quota(response, self.provider_name)
                response.raise_for_status()
                data: Any = response.json()
        except SearchQuotaExhausted:
            raise
        except httpx.HTTPStatusError as e:
            raise SearchProviderError(
                f"semantic_scholar: HTTP {e.response.status_code}"
            ) from e
        except httpx.HTTPError as e:
            raise SearchProviderError(
                f"semantic_scholar: transport error ({type(e).__name__})"
            ) from e
        except ValueError as e:
            raise SearchProviderError(f"semantic_scholar: bad JSON ({e})") from e

        try:
            items = data.get("data", [])
            results = [
                self._to_result(item) for item in items if isinstance(item, dict)
            ]
            results = [r for r in results if r is not None]
        except (AttributeError, TypeError) as e:
            raise SearchProviderError(
                f"semantic_scholar: unexpected shape ({e})"
            ) from e
        logger.info(f"Search  │ Semantic Scholar found {len(results)} results")
        return [r for r in results if r is not None][:limit]

    def _to_result(self, item: dict[str, Any]) -> SearchResult | None:
        """Map one API paper object onto a SearchResult (None if unusable)."""
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not url:
            pdf = item.get("openAccessPdf") or {}
            if isinstance(pdf, dict):
                url = str(pdf.get("url") or "").strip()
        if not url:
            paper_id = str(item.get("paperId") or "").strip()
            if paper_id:
                url = f"https://www.semanticscholar.org/paper/{paper_id}"
        if not title and not url:
            return None
        year = item.get("year")
        return SearchResult(
            title=title[:500],
            url=url[:2000],
            snippet=_truncate(str(item.get("abstract") or "")),
            published=str(year) if year else None,
            source_type="paper",
        )


class DuckDuckGoSearchProvider(SearchProvider):
    """UNOFFICIAL fallback: DuckDuckGo Instant Answer API (no key needed).

    Marked unofficial because DuckDuckGo offers no supported search API —
    this endpoint is best-effort, often returns few results, and may
    change without notice. Last resort only, after every other provider.
    """

    provider_name: str = "duckduckgo"
    IS_UNOFFICIAL: bool = True

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not query or not query.strip():
            return []
        limit = _clamp_max_results(max_results)
        logger.info(f"Search  │ DuckDuckGo (unofficial) search: {query[:80]}...")
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": query,
                        "format": "json",
                        "no_html": 1,
                        "skip_disambig": 1,
                    },
                    headers={"User-Agent": USER_AGENT},
                )
                _raise_for_quota(response, self.provider_name)
                response.raise_for_status()
                data: Any = response.json()
        except SearchQuotaExhausted:
            raise
        except httpx.HTTPStatusError as e:
            raise SearchProviderError(
                f"duckduckgo: HTTP {e.response.status_code}"
            ) from e
        except httpx.HTTPError as e:
            raise SearchProviderError(
                f"duckduckgo: transport error ({type(e).__name__})"
            ) from e
        except ValueError as e:
            raise SearchProviderError(f"duckduckgo: bad JSON ({e})") from e

        try:
            results = self._collect_topics(data, limit)
        except (AttributeError, TypeError) as e:
            raise SearchProviderError(f"duckduckgo: unexpected shape ({e})") from e
        logger.info(f"Search  │ DuckDuckGo found {len(results)} results")
        return results[:limit]

    def _collect_topics(self, data: dict[str, Any], limit: int) -> list[SearchResult]:
        """Flatten the abstract + related topics into results."""
        collected: list[SearchResult] = []
        abstract = str(data.get("AbstractText") or "").strip()
        abstract_url = str(data.get("AbstractURL") or "").strip()
        if abstract and abstract_url:
            collected.append(
                SearchResult(
                    title=_truncate(abstract, 120) or "DuckDuckGo abstract",
                    url=abstract_url[:2000],
                    snippet=_truncate(abstract),
                    published=None,
                    source_type="unofficial",
                )
            )
        for topic in data.get("RelatedTopics", []):
            if len(collected) >= limit:
                break
            if not isinstance(topic, dict):
                continue
            nested = topic.get("Topics")
            candidates = nested if isinstance(nested, list) else [topic]
            for candidate in candidates:
                if len(collected) >= limit:
                    break
                if not isinstance(candidate, dict):
                    continue
                url = str(candidate.get("FirstURL") or "").strip()
                text = _truncate(str(candidate.get("Text") or ""))
                if not url or not text:
                    continue
                collected.append(
                    SearchResult(
                        title=text[:120],
                        url=url[:2000],
                        snippet=text,
                        published=None,
                        source_type="unofficial",
                    )
                )
        return collected
