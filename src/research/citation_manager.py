"""
Assembly — Citation Manager

Tracks, deduplicates, and formats sources for the final answer (PRD Section 11).
"""

from typing import List, Dict, Set


class CitationManager:
    """
    Manages sources and citations across an execution.
    
    Collects sources from multiple agents and research results,
    deduplicates by URL, and produces the final source list.
    """

    def __init__(self):
        self._sources: List[Dict[str, str]] = []
        self._seen_urls: Set[str] = set()

    def add_source(self, title: str, url: str = "", snippet: str = ""):
        """Add a source, deduplicating by URL."""
        if url and url in self._seen_urls:
            return
        if url:
            self._seen_urls.add(url)

        self._sources.append({
            "title": title,
            "url": url,
            "snippet": snippet,
        })

    def add_sources(self, sources: List[Dict[str, str]]):
        """Add multiple sources."""
        for s in sources:
            self.add_source(
                title=s.get("title", ""),
                url=s.get("url", ""),
                snippet=s.get("snippet", ""),
            )

    def get_final_sources(self, used_only: bool = True) -> List[Dict[str, str]]:
        """Get the final deduplicated source list."""
        return self._sources

    def clear(self):
        """Reset for a new execution."""
        self._sources.clear()
        self._seen_urls.clear()
