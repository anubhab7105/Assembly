"""Bounded, free-first HTML crawling for Assembly research.

The crawler intentionally uses only the existing HTTPX dependency and the
Python standard library. It fetches static HTML only; JavaScript rendering
is a separate optional adapter and is not part of the base install.
"""

from __future__ import annotations

import asyncio
import ipaddress
import inspect
import socket
import time
from collections import deque
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "AssemblyCrawler/1.0 (+https://github.com/anubhab7105/Assembly)"
DEFAULT_MAX_PAGES = 5
DEFAULT_MAX_DEPTH = 1
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_TOTAL_TIMEOUT_SECONDS = 8.0
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_EXTRACTED_CHARS = 12_000
MAX_REDIRECTS = 5
ROBOTS_MAX_BYTES = 100_000
MIN_HOST_INTERVAL_SECONDS = 0.2
_MAX_SEED_PAGES = 3
_MAX_LINKS_PER_PAGE = 20
_ALLOWED_PORTS = {"http": 80, "https": 443}
_BLOCKED_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    "iframe",
    "template",
}
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class UnsafeURL(ValueError):
    """A URL is not safe for an outbound crawler request."""


@dataclass(frozen=True)
class ExtractedPage:
    """Bounded text and links extracted from one permitted HTML page."""

    url: str
    title: str
    text: str
    links: tuple[str, ...]


@dataclass(frozen=True)
class _FetchedResponse:
    url: str
    status_code: int
    content_type: str
    body: bytes


Resolver = Callable[
    [str, int], Iterable[str] | Awaitable[Iterable[str]]
]


class _ReadableHTMLParser(HTMLParser):
    """Small standard-library extractor that discards active/boilerplate tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[tuple[str, bool]] = []
        self._title_depth = 0
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []
        self.links: list[str] = []

    @property
    def _inside_ignored(self) -> bool:
        return any(ignored for _, ignored in self._stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        inherited = self._inside_ignored
        attrs_map = dict(attrs)
        style = (attrs_map.get("style") or "").replace(" ", "").lower()
        is_hidden = (
            "hidden" in attrs_map
            or (attrs_map.get("aria-hidden") or "").lower() == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        )
        if name == "title":
            self._title_depth += 1
        ignored = (
            inherited
            or is_hidden
            or name in _BLOCKED_TAGS
            or name in {"head", "title"}
        )
        if name == "a" and not ignored:
            href = attrs_map.get("href")
            if href:
                self.links.append(href)
        if name not in _VOID_TAGS:
            self._stack.append((name, ignored))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name == "title" and self._title_depth:
            self._title_depth -= 1
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == name:
                del self._stack[index:]
                break

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        if self._title_depth:
            self._title_parts.append(value)
        elif not self._inside_ignored:
            self._text_parts.append(value)

    def result(self) -> tuple[str, str, list[str]]:
        title = " ".join(" ".join(self._title_parts).split())[:500]
        text = " ".join(" ".join(self._text_parts).split())[:MAX_EXTRACTED_CHARS]
        return title, text, self.links


def _origin(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    port = parts.port or _ALLOWED_PORTS.get(scheme)
    if not scheme or not host or port is None:
        raise UnsafeURL("URL has no valid origin")
    default_port = _ALLOWED_PORTS.get(scheme)
    display_host = f"[{host}]" if ":" in host else host
    suffix = "" if port == default_port else f":{port}"
    return f"{scheme}://{display_host}{suffix}"


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication without changing its destination."""
    parts = urlsplit((url or "").strip())
    if parts.scheme.lower() not in {"http", "https"}:
        raise UnsafeURL("Only HTTP and HTTPS URLs are supported")
    if parts.username is not None or parts.password is not None:
        raise UnsafeURL("Credentials in URLs are not allowed")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or "%" in host:
        raise UnsafeURL("URL host is invalid")
    try:
        port = parts.port
    except ValueError as exc:
        raise UnsafeURL("URL port is invalid") from exc
    expected_port = _ALLOWED_PORTS[parts.scheme.lower()]
    if port is not None and port != expected_port:
        raise UnsafeURL("Non-standard ports are not allowed")
    netloc = f"[{host}]" if ":" in host else host
    path = parts.path or "/"
    normalized = urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))
    normalized, _ = urldefrag(normalized)
    return normalized


class WebCrawler:
    """Conservative same-origin crawler with robots and outbound-IP checks."""

    def __init__(
        self,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_depth: int = DEFAULT_MAX_DEPTH,
        request_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        total_timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        resolver: Resolver | None = None,
    ) -> None:
        self.max_pages = max(1, min(int(max_pages), DEFAULT_MAX_PAGES))
        self.max_depth = max(0, min(int(max_depth), DEFAULT_MAX_DEPTH))
        self.request_timeout_seconds = max(0.1, float(request_timeout_seconds))
        self.total_timeout_seconds = max(0.1, float(total_timeout_seconds))
        self.max_response_bytes = max(
            1024, min(int(max_response_bytes), DEFAULT_MAX_RESPONSE_BYTES)
        )
        self._resolver = resolver
        self._client: httpx.AsyncClient | None = None
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_request_at: dict[str, float] = {}

    async def crawl(self, results: list[object]) -> list[dict[str, str]]:
        """Enrich up to three search hits and append same-origin linked pages.

        Search hits are retained as a fallback when a page cannot be fetched.
        The returned dictionaries keep the research layer's title/url/snippet
        boundary and therefore remain compatible with the existing sanitizer.
        """
        normalized_results = [_as_result_dict(item) for item in (results or [])]
        if not normalized_results:
            return []
        seeds = normalized_results[: min(_MAX_SEED_PAGES, self.max_pages)]
        output = [dict(item) for item in normalized_results]
        seen: set[str] = set()
        queue: deque[tuple[str, str, int]] = deque()
        attempted = 0
        try:
            async with asyncio.timeout(self.total_timeout_seconds):
                async with httpx.AsyncClient(
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "text/html,application/xhtml+xml,text/plain",
                    },
                    follow_redirects=False,
                    timeout=self.request_timeout_seconds,
                ) as client:
                    self._client = client
                    for index, seed in enumerate(seeds):
                        raw_url = seed.get("url", "")
                        try:
                            url = normalize_url(raw_url)
                            origin = _origin(url)
                        except (UnsafeURL, ValueError):
                            continue
                        if url in seen or attempted >= self.max_pages:
                            continue
                        seen.add(url)
                        attempted += 1
                        page = await self._fetch_page(url, origin)
                        if page is None:
                            continue
                        output[index] = {
                            "title": page.title or seed.get("title", "Untitled"),
                            "url": page.url,
                            "snippet": page.text or seed.get("snippet", ""),
                        }
                        if self.max_depth >= 1:
                            for href in page.links[:_MAX_LINKS_PER_PAGE]:
                                try:
                                    linked = normalize_url(urljoin(page.url, href))
                                    if _origin(linked) != origin or linked in seen:
                                        continue
                                except (UnsafeURL, ValueError):
                                    continue
                                seen.add(linked)
                                queue.append((linked, origin, 1))

                    while queue and attempted < self.max_pages:
                        url, origin, depth = queue.popleft()
                        if depth > self.max_depth:
                            continue
                        attempted += 1
                        page = await self._fetch_page(url, origin)
                        if page is None or not page.text:
                            continue
                        output.append(
                            {
                                "title": page.title or "Untitled",
                                "url": page.url,
                                "snippet": page.text,
                            }
                        )
        except TimeoutError:
            # A crawl is optional enrichment: preserve every search hit if the
            # run's crawler budget expires. Cancellation still propagates.
            return output
        finally:
            self._client = None
        return output

    async def _resolve_ips(self, host: str, port: int) -> list[str]:
        if self._resolver is not None:
            resolved = self._resolver(host, port)
            if inspect.isawaitable(resolved):
                resolved = await resolved
            return [str(address) for address in resolved]
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return list({record[4][0] for record in records})

    async def _validate_public_url(self, url: str) -> str:
        normalized = normalize_url(url)
        parts = urlsplit(normalized)
        host = parts.hostname or ""
        port = parts.port or _ALLOWED_PORTS[parts.scheme]
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            # Block common local names before DNS resolution.
            if host == "localhost" or host.endswith(
                (".localhost", ".local", ".internal")
            ):
                raise UnsafeURL("Local and internal hosts are not allowed")
            addresses = await self._resolve_ips(host, port)
        else:
            addresses = [str(literal)]
        if not addresses:
            raise UnsafeURL("Host did not resolve")
        for address in addresses:
            try:
                ip = ipaddress.ip_address(address)
            except ValueError as exc:
                raise UnsafeURL("Host resolved to an invalid address") from exc
            if not ip.is_global:
                raise UnsafeURL(
                    "Private, reserved, and non-public IP addresses are blocked"
                )
        return normalized

    async def _pace_host(self, origin: str) -> None:
        """Keep requests sequential and add a small per-origin pause."""
        now = time.monotonic()
        previous = self._last_request_at.get(origin)
        if previous is not None:
            delay = MIN_HOST_INTERVAL_SECONDS - (now - previous)
            if delay > 0:
                await asyncio.sleep(delay)
        self._last_request_at[origin] = time.monotonic()

    async def _read_response(
        self,
        url: str,
        expected_origin: str,
        *,
        allow_redirects: bool = True,
        max_bytes: int | None = None,
    ) -> _FetchedResponse | None:
        assert self._client is not None
        current = url
        byte_limit = min(self.max_response_bytes, max_bytes or self.max_response_bytes)
        visited: set[str] = set()
        for redirect_count in range(MAX_REDIRECTS + 1):
            current = await self._validate_public_url(current)
            if _origin(current) != expected_origin:
                raise UnsafeURL("Cross-origin navigation is not allowed")
            if current in visited:
                return None
            visited.add(current)
            await self._pace_host(expected_origin)
            async with self._client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if (
                        not location
                        or not allow_redirects
                        or redirect_count >= MAX_REDIRECTS
                    ):
                        return _FetchedResponse(current, response.status_code, "", b"")
                    current = urljoin(current, location)
                    continue
                content_type = (
                    response.headers.get("content-type", "")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )
                if response.status_code < 200 or response.status_code >= 300:
                    return _FetchedResponse(
                        current, response.status_code, content_type, b""
                    )
                length_header = response.headers.get("content-length", "")
                try:
                    declared_length = int(length_header)
                except ValueError:
                    declared_length = 0
                if declared_length > byte_limit:
                    return _FetchedResponse(current, 413, content_type, b"")
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > byte_limit:
                        return _FetchedResponse(current, 413, content_type, b"")
                    chunks.append(chunk)
                return _FetchedResponse(
                    current, response.status_code, content_type, b"".join(chunks)
                )
        return None

    async def _robots_allowed(self, url: str, origin: str) -> bool:
        if origin not in self._robots:
            robots_url = f"{origin}/robots.txt"
            try:
                response = await self._read_response(
                    robots_url, origin, max_bytes=ROBOTS_MAX_BYTES
                )
            except (UnsafeURL, httpx.HTTPError, OSError, TimeoutError):
                self._robots[origin] = None
            else:
                if (
                    response is None
                    or response.status_code in {401, 403}
                    or response.status_code >= 500
                ):
                    self._robots[origin] = None
                elif response.status_code in {404, 410}:
                    self._robots[origin] = RobotFileParser()
                    self._robots[origin].parse(["User-agent: *", "Allow: /"])
                elif 200 <= response.status_code < 300:
                    try:
                        text = response.body.decode("utf-8", errors="replace")
                        parser = RobotFileParser()
                        parser.set_url(robots_url)
                        parser.parse(text.splitlines())
                        self._robots[origin] = parser
                    except (ValueError, UnicodeError):
                        self._robots[origin] = None
                else:
                    self._robots[origin] = None
        rules = self._robots[origin]
        return bool(rules is not None and rules.can_fetch(USER_AGENT, url))

    async def _fetch_page(self, url: str, origin: str) -> ExtractedPage | None:
        if not await self._robots_allowed(url, origin):
            return None
        try:
            response = await self._read_response(url, origin)
        except (UnsafeURL, ValueError, httpx.HTTPError, OSError, TimeoutError):
            return None
        if (
            response is None
            or response.status_code < 200
            or response.status_code >= 300
            or response.content_type not in {"text/html", "application/xhtml+xml"}
        ):
            return None
        parser = _ReadableHTMLParser()
        try:
            parser.feed(response.body.decode("utf-8", errors="replace"))
            parser.close()
        except (ValueError, AssertionError):
            return None
        title, text, links = parser.result()
        return ExtractedPage(
            url=response.url,
            title=title,
            text=text,
            links=tuple(links),
        )


def _as_result_dict(result: object) -> dict[str, str]:
    """Normalize dict, Pydantic model, or SearchResult-like objects."""
    if isinstance(result, dict):
        raw = result
    elif hasattr(result, "to_legacy_dict"):
        raw = result.to_legacy_dict()
    elif hasattr(result, "model_dump"):
        raw = result.model_dump()
    else:
        raw = {}
    return {
        "title": str(raw.get("title", "") or "")[:500],
        "url": str(raw.get("url", "") or "")[:2000],
        "snippet": str(raw.get("snippet", "") or "")[:MAX_EXTRACTED_CHARS],
    }


def normalize_search_results(results: list[object]) -> list[dict[str, str]]:
    """Convert provider models or dictionaries to the legacy research shape."""
    return [_as_result_dict(item) for item in (results or [])]


async def crawl_search_results(
    results: list[object],
    *,
    total_timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT_SECONDS,
) -> list[dict[str, str]]:
    """Public convenience function used by the orchestrator."""
    normalized = normalize_search_results(results)
    if not normalized or total_timeout_seconds <= 0:
        return normalized
    crawler = WebCrawler(
        total_timeout_seconds=min(
            float(total_timeout_seconds), DEFAULT_TOTAL_TIMEOUT_SECONDS
        )
    )
    return await crawler.crawl(normalized)
