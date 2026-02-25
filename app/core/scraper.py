"""Scraper service — multi-source metadata scraping with per-field merge."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from app.models.scrape_result import MergedMetadata, MetadataField, ScrapeResult

if TYPE_CHECKING:
    from app.config import Config
    from app.data.scrape_cache import ScrapeCache
    from app.scrapers.base import ScraperProvider


class Scraper:
    """Multi-source metadata scraper with Playnite-style per-field priority merge."""

    def __init__(self, config: Config, cache: ScrapeCache) -> None:
        self._config = config
        self._cache = cache
        self._providers: dict[str, ScraperProvider] = {}

    def register_provider(self, provider: ScraperProvider) -> None:
        """Register a scraper provider."""
        self._providers[provider.name] = provider

    @property
    def providers(self) -> dict[str, ScraperProvider]:
        return dict(self._providers)

    def scrape(
        self,
        game_id: str,
        platform: str,
        query: str = "",
        force: bool = False,
    ) -> MergedMetadata:
        """
        Scrape metadata from all providers and merge by field priority.

        Returns cached merged result if available (unless force=True).
        """
        # Check cache first
        if not force:
            cached = self._cache.get_merged(platform, game_id)
            if cached:
                return cached

        # Scrape from all providers
        results: dict[str, ScrapeResult] = {}
        search_query = query or game_id

        for name, provider in self._providers.items():
            if not provider.supports_platform(platform):
                continue
            try:
                result = provider.search(search_query, platform)
                if result:
                    result.game_id = game_id
                    result.platform = platform
                    results[name] = result
                    self._cache.save_result(result)
                    logger.info(f"Scraped {name} for {search_query}: found")
                else:
                    logger.debug(f"Scraped {name} for {search_query}: not found")
            except Exception as e:
                logger.error(f"Scraper {name} failed for {search_query}: {e}")

        # Merge results
        merged = self._merge_results(results, platform)
        merged.game_id = game_id
        merged.platform = platform
        self._cache.save_merged(merged)
        return merged

    def scrape_single(
        self,
        provider_name: str,
        game_id: str,
        platform: str,
        query: str = "",
    ) -> ScrapeResult | None:
        """Scrape from a single provider."""
        provider = self._providers.get(provider_name)
        if not provider:
            logger.error(f"Provider not found: {provider_name}")
            return None

        try:
            result = provider.search(query or game_id, platform)
            if result:
                result.game_id = game_id
                result.platform = platform
                self._cache.save_result(result)
            return result
        except Exception as e:
            logger.error(f"Scraper {provider_name} failed: {e}")
            return None

    def _merge_results(
        self, results: dict[str, ScrapeResult], platform: str
    ) -> MergedMetadata:
        """Merge results from multiple providers using field-level priority."""
        merged = MergedMetadata()
        field_priority = self._config.field_priority

        for field_enum in MetadataField:
            field_name = field_enum.value
            # Get priority order for this field, default to provider registration order
            priority = field_priority.get(
                field_name, list(results.keys())
            )

            for provider_name in priority:
                if provider_name not in results:
                    continue
                result = results[provider_name]
                value = getattr(result, field_name, None)
                if value is not None and value != "" and value != []:
                    merged.fields[field_name] = value
                    merged.sources[field_name] = provider_name
                    break

        return merged

    def search_interactive(
        self, query: str, platform: str, provider_name: str | None = None
    ) -> list[ScrapeResult]:
        """Search for games interactively (for manual matching)."""
        results: list[ScrapeResult] = []

        if provider_name:
            providers = {provider_name: self._providers.get(provider_name)}
        else:
            providers = self._providers  # type: ignore[assignment]

        for name, provider in providers.items():
            if provider is None or not provider.supports_platform(platform):
                continue
            try:
                search_results = provider.search_multi(query, platform)
                results.extend(search_results)
            except Exception as e:
                logger.error(f"Interactive search failed ({name}): {e}")

        return results
