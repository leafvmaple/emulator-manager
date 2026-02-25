"""Abstract base class for metadata scraper providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.scrape_result import ScrapeResult


class ScraperProvider(ABC):
    """Abstract interface for a game metadata scraping source."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this provider (e.g. 'igdb', 'screenscraper')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name (e.g. 'IGDB', 'ScreenScraper')."""
        ...

    @abstractmethod
    def supports_platform(self, platform: str) -> bool:
        """Whether this provider supports the given platform."""
        ...

    @abstractmethod
    def search(self, query: str, platform: str) -> ScrapeResult | None:
        """Search for a game and return the best match."""
        ...

    @abstractmethod
    def search_multi(self, query: str, platform: str) -> list[ScrapeResult]:
        """Search for games and return multiple results for manual selection."""
        ...

    def get_by_id(self, provider_id: str, platform: str) -> ScrapeResult | None:
        """Fetch a game by its provider-specific ID. Optional."""
        return None
