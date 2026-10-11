"""
Assembly — SearchRouter: question-type ordering, budget, fallback, cache.

Ordering: ``research`` questions try academic sources first
(Semantic Scholar → arXiv → Wikipedia → Tavily → DuckDuckGo);
every other type tries general web first
(Tavily → Wikipedia → Semantic Scholar → arXiv → DuckDuckGo).

Budget: one logical ``search()`` call costs exactly one search against
the execution budget (a ``BudgetController`` or a plain ``max_searches``
cap). Cache hits and empty queries cost nothing.

Fallback: quota/auth/transport/parse failures move to the next provider;
total failure returns [] instead of raising, so the run continues.

Cache: per-router in-memory dict keyed on
(normalized query, max_results, problem type); only completed passes
are cached, so a total-failure query may be retried later in the run.
"""

from src.core.logging_config import logger
from src.orchestration.budget_controller import BudgetController
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
from src.research.schemas import SearchResult

#: Providers tried first for research questions (academic sources first).
_ACADEMIC_FIRST: tuple[str, ...] = (
    "semantic_scholar",
    "arxiv",
    "wikipedia",
    "tavily",
    "duckduckgo",
)

#: Providers tried first for every other question type (web first).
_WEB_FIRST: tuple[str, ...] = (
    "tavily",
    "wikipedia",
    "semantic_scholar",
    "arxiv",
    "duckduckgo",
)


def normalize_query(query: str) -> str:
    """Collapse whitespace and casefold for cache keys."""
    return " ".join((query or "").strip().casefold().split())


def normalize_problem_type(problem_type: str) -> str:
    """Lowercase the planner type, defaulting unknowns to general."""
    value = (problem_type or "").strip().lower()
    return value or "general"


def default_providers(tavily_key=None) -> list[SearchProvider]:
    """Build the standard five-provider set (Tavily self-gates on its key).

    An explicit per-request Tavily key enables the keyed provider;
    otherwise the keyless providers (Wikipedia, arXiv, Semantic Scholar,
    DuckDuckGo) still serve.
    """
    return [
        TavilySearchProvider(api_key=tavily_key),
        WikipediaSearchProvider(),
        ArxivSearchProvider(),
        SemanticScholarSearchProvider(),
        DuckDuckGoSearchProvider(),
    ]


class SearchRouter:
    """Route one query to the best-ordered providers under a search budget."""

    def __init__(
        self,
        providers: list[SearchProvider] | None = None,
        budget_controller: BudgetController | None = None,
        max_searches: int | None = None,
        default_max_results: int = 5,
    ) -> None:
        self._providers: list[SearchProvider] = (
            list(providers) if providers is not None else default_providers()
        )
        self._budget: BudgetController | None = budget_controller
        self._max_searches: int | None = max_searches
        self._default_max_results: int = max(1, int(default_max_results))
        self._cache: dict[tuple[str, int, str], list[SearchResult]] = {}
        self._local_used: int = 0
        # Provider names that returned results in the latest search()
        # (names only — safe to surface to the user).
        self._last_used: list[str] = []

    @property
    def providers(self) -> list[SearchProvider]:
        """Configured providers in construction order (read-only copy)."""
        return list(self._providers)

    @property
    def cache_size(self) -> int:
        """Number of cached query results in this run."""
        return len(self._cache)

    @property
    def last_providers_used(self) -> list[str]:
        """Provider names behind the latest search results (names only)."""
        return list(self._last_used)

    @property
    def searches_used(self) -> int:
        """Searches spent (controller count when one is attached)."""
        if self._budget is not None:
            return self._budget.state.searches_used
        return self._local_used

    def clear_cache(self) -> None:
        """Drop all cached results (new execution reuses the router)."""
        self._cache.clear()

    def order_for(self, problem_type: str) -> list[SearchProvider]:
        """Providers ordered for a question type, unavailable ones skipped."""
        available = [p for p in self._providers if p.is_available]
        preferred = (
            _ACADEMIC_FIRST
            if normalize_problem_type(problem_type) == "research"
            else _WEB_FIRST
        )
        by_name = {p.provider_name: p for p in available}
        ordered = [by_name[name] for name in preferred if name in by_name]
        ordered.extend(p for p in available if p.provider_name not in preferred)
        return ordered

    def _budget_allows(self) -> bool:
        """Check the execution search budget without spending it."""
        if self._budget is not None:
            return self._budget.can_search()
        if self._max_searches is not None:
            return self._local_used < self._max_searches
        return True

    def _record_search(self, count: int = 1) -> None:
        """Spend budget for one completed provider pass."""
        if self._budget is not None:
            self._budget.record_search(count)
        else:
            self._local_used += count

    async def search(
        self,
        query: str,
        max_results: int | None = None,
        problem_type: str = "general",
    ) -> list[SearchResult]:
        """Search once under budget, fanning through providers in order.

        Cache hits and empty queries cost no budget and make no HTTP
        calls. Total provider failure returns [] (never raises).
        """
        normalized_pt = normalize_problem_type(problem_type)
        key_query = normalize_query(query)
        if not key_query:
            return []
        limit = max_results if max_results is not None else self._default_max_results
        limit = max(1, min(int(limit), 10))

        cache_key = (key_query, limit, normalized_pt)
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.info(f"Search  │ Cache hit: {query[:80]}...")
            return list(cached)

        if not self._budget_allows():
            logger.warning("Search  │ Search budget exhausted — skipping query")
            return []

        ordered = self.order_for(normalized_pt)
        if not ordered:
            logger.warning("Search  │ No search providers available")
            return []

        attempted = False
        succeeded = False
        used: list[str] = []
        for provider in ordered:
            try:
                results = await provider.search(query, max_results=limit)
            except SearchQuotaExhausted as e:
                attempted = True
                logger.warning(f"Search  │ Quota out, falling back ({e})")
                continue
            except SearchProviderError as e:
                attempted = True
                logger.warning(
                    f"Search  │ {provider.provider_name} failed "
                    f"({type(e).__name__}: {e}); falling back"
                )
                continue
            except Exception as e:  # noqa: BLE001 — total failure returns [], never raises
                attempted = True
                logger.warning(
                    f"Search  │ {provider.provider_name} failed unexpectedly "
                    f"({type(e).__name__}); falling back"
                )
                continue
            attempted = True
            succeeded = True
            if not results:
                continue
            used.append(provider.provider_name)
            trimmed = list(results[:limit])
            self._record_search(1)
            self._cache[cache_key] = trimmed
            self._last_used = used
            return list(trimmed)

        # All providers empty or failed: spend the attempt once. Cache the
        # genuinely-empty pass (every provider answered); a total failure
        # (all raised) stays uncached so a later retry may succeed.
        if attempted:
            self._record_search(1)
        if succeeded:
            self._cache[cache_key] = []
        self._last_used = used
        return []
