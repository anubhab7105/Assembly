"""
Assembly — Research / Web Search Engine

Web search integration for research-heavy questions (PRD Section 11).
"""

from typing import List, Dict, Optional
import httpx

from src.core.config import settings
from src.core.logging_config import logger


class SearchEngine:
    """
    Web search abstraction.
    
    Uses Tavily API when available, falls back to a no-op
    that returns empty results for the MVP.
    """

    def __init__(self):
        self.tavily_key = settings.tavily_api_key
        self.has_tavily = bool(self.tavily_key) and not self.tavily_key.startswith("tvly-your")

    async def search(
        self,
        query: str,
        max_results: int = 5,
    ) -> List[Dict[str, str]]:
        """
        Search the web and return structured results.
        
        Returns:
            List of {title, url, snippet} dicts.
        """
        if self.has_tavily:
            return await self._tavily_search(query, max_results)

        logger.warning("Search  │ No search API configured — returning empty results")
        return []

    async def _tavily_search(
        self,
        query: str,
        max_results: int = 5,
    ) -> List[Dict[str, str]]:
        """Search using Tavily API."""
        logger.info(f"Search  │ Tavily search: {query[:80]}...")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.tavily_key,
                        "query": query,
                        "max_results": max_results,
                        "search_depth": "basic",
                    },
                )
                response.raise_for_status()
                data = response.json()

            results = []
            for item in data.get("results", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", "")[:500],
                })

            logger.info(f"Search  │ Found {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Search  │ Tavily error: {e}")
            return []
