"""Game icon/cover art provider."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from loguru import logger

# Type alias for cover art resolvers
CoverResolver = Callable[[str], list[str] | None]


class GameIconProvider:
    """Downloads and caches game cover art/icons."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir
        self._resolvers: dict[str, CoverResolver] = {}

    def register_resolver(self, platform: str, resolver: CoverResolver) -> None:
        """Register a cover art resolver for a platform."""
        self._resolvers[platform] = resolver

    def get_icon_path(self, platform: str, game_id: str) -> Path | None:
        """Get cached icon path, or None if not available."""
        if self._cache_dir is None:
            return None
        icon_dir = self._cache_dir / platform / game_id
        for ext in (".jpg", ".png", ".jpeg", ".webp"):
            icon = icon_dir / f"icon{ext}"
            if icon.exists():
                return icon
        return None

    def download_icon(self, platform: str, game_id: str, url: str) -> Path | None:
        """Download an icon from a URL and cache it locally."""
        if self._cache_dir is None:
            return None

        import httpx

        icon_dir = self._cache_dir / platform / game_id
        icon_dir.mkdir(parents=True, exist_ok=True)

        # Determine extension from URL
        ext = Path(url).suffix or ".jpg"
        icon_path = icon_dir / f"icon{ext}"

        if icon_path.exists():
            return icon_path

        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                icon_path.write_bytes(resp.content)
            return icon_path
        except Exception as e:
            logger.warning(f"Failed to download icon for {platform}:{game_id}: {e}")
            return None
