# Research module: multi-provider search with budget + cache.
from src.research.providers import (
    ArxivSearchProvider,
    DuckDuckGoSearchProvider,
    SearchProvider,
    SearchProviderError,
    SearchQuotaExhausted,
    SemanticScholarSearchProvider,
    TavilySearchProvider,
    WikipediaSearchProvider,
)
from src.research.router import SearchRouter, default_providers
from src.research.sanitize import (
    UNTRUSTED_SYSTEM_NOTE,
    sanitize_search_results,
    scan_for_injection,
)
from src.research.schemas import SearchResult

__all__ = [
    "ArxivSearchProvider",
    "DuckDuckGoSearchProvider",
    "SearchProvider",
    "SearchProviderError",
    "SearchQuotaExhausted",
    "SearchResult",
    "SearchRouter",
    "SemanticScholarSearchProvider",
    "TavilySearchProvider",
    "UNTRUSTED_SYSTEM_NOTE",
    "WikipediaSearchProvider",
    "default_providers",
    "sanitize_search_results",
    "scan_for_injection",
]
