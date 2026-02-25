"""Scrape cache — per-game JSON file cache for scraped metadata."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from loguru import logger

from app.models.scrape_result import MergedMetadata, ScrapeResult


class ScrapeCache:
    """
    Scrape result cache.

    Each (platform, game_id) pair maps to a single JSON file:
      scrape_cache/{platform}/{game_id}.json

    File structure:
    {
        "merged": { ... MergedMetadata ... },
        "providers": {
            "igdb": { ... ScrapeResult ... },
            "screenscraper": { ... ScrapeResult ... }
        }
    }
    """

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir

    def _cache_path(self, platform: str, game_id: str) -> Path:
        return self._cache_dir / platform / f"{game_id}.json"

    def _load_cache_file(self, platform: str, game_id: str) -> dict[str, Any]:
        path = self._cache_path(platform, game_id)
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load scrape cache for {platform}:{game_id}: {e}")
            return {}

    def _save_cache_file(self, platform: str, game_id: str, data: dict[str, Any]) -> None:
        path = self._cache_path(platform, game_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp.replace(path)
        except OSError as e:
            logger.error(f"Failed to save scrape cache for {platform}:{game_id}: {e}")
            tmp.unlink(missing_ok=True)

    def get_merged(self, platform: str, game_id: str) -> MergedMetadata | None:
        data = self._load_cache_file(platform, game_id)
        merged_data = data.get("merged")
        if not merged_data:
            return None
        return MergedMetadata(**merged_data)

    def get_provider(self, platform: str, game_id: str, provider: str) -> ScrapeResult | None:
        data = self._load_cache_file(platform, game_id)
        providers = data.get("providers", {})
        provider_data = providers.get(provider)
        if not provider_data:
            return None
        return ScrapeResult(**provider_data)

    def save_result(self, result: ScrapeResult) -> None:
        """Save a single provider's scrape result."""
        data = self._load_cache_file(result.platform, result.game_id)
        if "providers" not in data:
            data["providers"] = {}
        data["providers"][result.provider] = asdict(result)
        self._save_cache_file(result.platform, result.game_id, data)

    def save_merged(self, merged: MergedMetadata) -> None:
        """Save the merged metadata result."""
        data = self._load_cache_file(merged.platform, merged.game_id)
        data["merged"] = asdict(merged)
        self._save_cache_file(merged.platform, merged.game_id, data)

    def is_cached(self, platform: str, game_id: str) -> bool:
        return self._cache_path(platform, game_id).exists()

    def invalidate(self, platform: str, game_id: str) -> None:
        path = self._cache_path(platform, game_id)
        if path.exists():
            path.unlink()
