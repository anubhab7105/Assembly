"""
Assembly — Research schemas (external API boundary).

Every search provider returns validated ``SearchResult`` models, so the
orchestrator and agents never parse raw provider JSON themselves.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceType = Literal["web", "encyclopedia", "paper", "unofficial"]


class SearchResult(BaseModel):
    """One citable web/research hit (untrusted data, never instructions)."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="", max_length=500)
    url: str = Field(default="", max_length=2000)
    snippet: str = Field(default="", max_length=2000)
    published: str | None = Field(default=None, max_length=64)
    source_type: SourceType = "web"

    def to_legacy_dict(self) -> dict[str, str]:
        """Shape expected by the orchestrator's source events/DB rows."""
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
        }
