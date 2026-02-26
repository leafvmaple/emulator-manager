"""ScreenScraper provider — uses ScreenScraper.fr API for game metadata."""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from app.models.scrape_result import ScrapeResult
from app.scrapers.base import ScraperProvider

_API_BASE = "https://www.screenscraper.fr/api2"

# ScreenScraper system ID mapping (subset)
_SYSTEM_MAP: dict[str, int] = {
    "switch": 225,
    "ps2": 58,
    "ps3": 59,
    "psp": 61,
    "psvita": 62,
    "nes": 3,
    "snes": 4,
    "n64": 14,
    "gc": 13,
    "wii": 16,
    "gb": 9,
    "gbc": 10,
    "gba": 12,
    "nds": 15,
    "3ds": 17,
    "genesis": 1,
    "saturn": 22,
    "dreamcast": 23,
    "xbox": 32,
    "xbox360": 33,
    "pc": 135,
}


def _build_proxy_url(config: Any) -> str:
    """Assemble proxy URL from config fields (protocol/host/port)."""
    scraper_cfg = config.get("scraper", {})
    host = scraper_cfg.get("proxy_host", "")
    if not host:
        return ""
    proto = scraper_cfg.get("proxy_protocol", "http")
    port = scraper_cfg.get("proxy_port", "")
    return f"{proto}://{host}:{port}" if port else f"{proto}://{host}"


class ScreenScraperProvider(ScraperProvider):
    """ScreenScraper.fr game metadata provider."""

    def __init__(
        self,
        dev_id: str,
        dev_password: str,
        username: str = "",
        password: str = "",
        software_name: str = "EmulatorManager",
        config: Any = None,
    ) -> None:
        self._dev_id = dev_id
        self._dev_password = dev_password
        self._username = username
        self._password = password
        self._software_name = software_name
        self._config = config

    def _http_client(self, **kwargs: Any) -> httpx.Client:
        """Create an httpx Client with optional proxy (read from config each time)."""
        if self._config:
            proxy = _build_proxy_url(self._config)
            if proxy:
                kwargs.setdefault("proxy", proxy)
        return httpx.Client(**kwargs)

    @property
    def name(self) -> str:
        return "screenscraper"

    @property
    def display_name(self) -> str:
        return "ScreenScraper"

    def supports_platform(self, platform: str) -> bool:
        return platform.lower() in _SYSTEM_MAP

    def _build_params(self, **extra: Any) -> dict[str, str]:
        """Build common API parameters."""
        params: dict[str, str] = {
            "devid": self._dev_id,
            "devpassword": self._dev_password,
            "softname": self._software_name,
            "output": "json",
        }
        if self._username:
            params["ssid"] = self._username
        if self._password:
            params["sspassword"] = self._password
        params.update({k: str(v) for k, v in extra.items()})
        return params

    def search(self, query: str, platform: str) -> ScrapeResult | None:
        results = self.search_multi(query, platform)
        return results[0] if results else None

    def search_multi(self, query: str, platform: str) -> list[ScrapeResult]:
        """Search ScreenScraper by game name."""
        system_id = _SYSTEM_MAP.get(platform.lower())
        if system_id is None:
            return []

        params = self._build_params(
            recherche=query,
            systemeid=system_id,
        )

        try:
            with self._http_client(timeout=30) as client:
                resp = client.get(
                    f"{_API_BASE}/jeuRecherche.php",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.error(f"ScreenScraper search failed: {e}")
            return []

        games = data.get("response", {}).get("jeux", [])
        return [self._parse_game(g, platform) for g in games[:10]]

    def get_by_id(self, provider_id: str, platform: str) -> ScrapeResult | None:
        """Fetch game by ScreenScraper game ID."""
        params = self._build_params(gameid=provider_id)

        try:
            with self._http_client(timeout=30) as client:
                resp = client.get(
                    f"{_API_BASE}/jeuInfos.php",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.error(f"ScreenScraper get_by_id failed: {e}")
            return None

        game = data.get("response", {}).get("jeu")
        if game:
            return self._parse_game(game, platform)
        return None

    def _parse_game(self, game: dict[str, Any], platform: str) -> ScrapeResult:
        """Parse a ScreenScraper game object into ScrapeResult."""
        title = self._get_text(game.get("noms", []), lang="en") or ""
        title_zh = self._get_text(game.get("noms", []), lang="zh")
        title_ja = self._get_text(game.get("noms", []), lang="ja")

        description = self._get_text(game.get("synopsis", []), lang="en") or ""

        publisher = self._get_text(game.get("editeur", {}).get("text", ""))
        developer = self._get_text(game.get("developpeur", {}).get("text", ""))

        # Extract dates
        release_date = ""
        dates = game.get("dates", [])
        if dates:
            for d in dates:
                if isinstance(d, dict):
                    release_date = d.get("text", "")
                    break

        # Genres
        genres: list[str] = []
        for genre in game.get("genres", []):
            if isinstance(genre, dict):
                names = genre.get("noms", [])
                en_name = self._get_text(names, lang="en")
                if en_name:
                    genres.append(en_name)

        # Cover art
        cover_url = ""
        medias = game.get("medias", [])
        for media in medias:
            if isinstance(media, dict) and media.get("type") == "box-2D":
                cover_url = media.get("url", "")
                break

        # Screenshots
        screenshots: list[str] = []
        for media in medias:
            if isinstance(media, dict) and media.get("type") == "ss":
                url = media.get("url", "")
                if url:
                    screenshots.append(url)

        result = ScrapeResult(
            provider="screenscraper",
            game_id=str(game.get("id", "")),
            title=title,
            title_en=title,
            title_ja=title_ja or "",
            title_zh=title_zh or "",
            overview=description,
            publisher=publisher or "",
            developer=developer or "",
            release_date=release_date,
            genre=", ".join(genres),
            tags=genres,
            boxart_url=cover_url,
            screenshot_urls=screenshots,
            platform=platform,
        )
        return result

    @staticmethod
    def _get_text(
        items: Any, lang: str = "en"
    ) -> str | None:
        """Extract text for a given language from ScreenScraper's multi-lang format."""
        if isinstance(items, str):
            return items
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("langue") == lang:
                    return item.get("text")
            # Fallback: return first available
            for item in items:
                if isinstance(item, dict) and item.get("text"):
                    return item.get("text")
        return None
