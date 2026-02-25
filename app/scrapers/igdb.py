"""IGDB scraper provider — uses Twitch/IGDB API for game metadata."""

from __future__ import annotations

import time
from typing import Any

import httpx
from loguru import logger

from app.models.scrape_result import ScrapeResult
from app.scrapers.base import ScraperProvider

# IGDB platform ID mapping (subset)
_PLATFORM_MAP: dict[str, int] = {
    "switch": 130,       # Nintendo Switch
    "ps2": 8,            # PlayStation 2
    "ps3": 9,            # PlayStation 3
    "ps4": 48,           # PlayStation 4
    "ps5": 167,          # PlayStation 5
    "psp": 38,           # PlayStation Portable
    "psvita": 46,        # PlayStation Vita
    "nes": 18,           # Nintendo Entertainment System
    "snes": 19,          # Super Nintendo
    "n64": 4,            # Nintendo 64
    "gc": 21,            # GameCube
    "wii": 5,            # Wii
    "wiiu": 41,          # Wii U
    "gb": 33,            # Game Boy
    "gbc": 22,           # Game Boy Color
    "gba": 24,           # Game Boy Advance
    "nds": 20,           # Nintendo DS
    "3ds": 37,           # Nintendo 3DS
    "genesis": 29,       # Sega Genesis / Mega Drive
    "saturn": 32,        # Sega Saturn
    "dreamcast": 23,     # Dreamcast
    "xbox": 11,          # Xbox
    "xbox360": 12,       # Xbox 360
    "xboxone": 49,       # Xbox One
    "pc": 6,             # PC (Windows)
}

_IGDB_IMAGE_BASE = "https://images.igdb.com/igdb/image/upload"


class IGDBProvider(ScraperProvider):
    """IGDB game metadata provider using Twitch API authentication."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: str | None = None
        self._token_expires_at: float = 0

    @property
    def name(self) -> str:
        return "igdb"

    @property
    def display_name(self) -> str:
        return "IGDB"

    def supports_platform(self, platform: str) -> bool:
        return platform.lower() in _PLATFORM_MAP

    def _ensure_token(self) -> str:
        """Obtain or refresh Twitch OAuth token."""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        try:
            resp = httpx.post(
                "https://id.twitch.tv/oauth2/token",
                params={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "client_credentials",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expires_at = time.time() + data.get("expires_in", 3600) - 60
            return self._access_token
        except Exception as e:
            logger.error(f"IGDB auth failed: {e}")
            raise

    def _api_request(self, endpoint: str, body: str) -> list[dict[str, Any]]:
        """Make an IGDB API request."""
        token = self._ensure_token()
        resp = httpx.post(
            f"https://api.igdb.com/v4/{endpoint}",
            content=body,
            headers={
                "Client-ID": self._client_id,
                "Authorization": f"Bearer {token}",
            },
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _detect_cjk_language(text: str) -> str | None:
        """Detect language from Unicode script in a CJK string.

        Returns "ja" if kana (hiragana/katakana) is found,
        "ko" if Hangul is found,
        "zh" if only CJK ideographs (no kana/Hangul),
        or None if no CJK characters at all.
        """
        has_kana = False
        has_hangul = False
        has_cjk = False
        for ch in text:
            cp = ord(ch)
            # Hiragana (U+3040–U+309F) or Katakana (U+30A0–U+30FF, U+31F0–U+31FF)
            if 0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF or 0x31F0 <= cp <= 0x31FF:
                has_kana = True
            # Hangul (U+AC00–U+D7AF, U+1100–U+11FF, U+3130–U+318F)
            elif 0xAC00 <= cp <= 0xD7AF or 0x1100 <= cp <= 0x11FF or 0x3130 <= cp <= 0x318F:
                has_hangul = True
            # CJK Unified Ideographs
            elif 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or 0x20000 <= cp <= 0x2A6DF:
                has_cjk = True
        if has_kana:
            return "ja"
        if has_hangul:
            return "ko"
        if has_cjk:
            return "zh"
        return None

    def search(self, query: str, platform: str) -> ScrapeResult | None:
        """Search IGDB for the best match."""
        results = self.search_multi(query, platform)
        return results[0] if results else None

    @staticmethod
    def _clean_query(raw: str) -> str:
        """Normalise a ROM title for use in IGDB wildcard queries.

        Strips separator characters (``- : –``), collapses whitespace, and
        escapes double-quotes so the result is safe to embed in an Apicalypse
        ``where`` clause.
        """
        import re
        cleaned = raw.replace("-", " ").replace(":", " ").replace("–", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned.replace('"', '\\"')

    def search_multi(self, query: str, platform: str) -> list[ScrapeResult]:
        """Search IGDB and return multiple results.

        Performs a wildcard match on both the primary ``name`` and
        ``alternative_names.name`` fields, filtered by platform.  The IGDB
        ``search`` keyword only indexes the primary name, but many ROM titles
        (e.g. *Pocket Monsters HeartGold*) are stored as alternative names.
        The IGDB website searches those too; we must as well.
        """
        platform_id = _PLATFORM_MAP.get(platform.lower())
        if platform_id is None:
            return []

        fields = (
            "fields name, summary, genres.name, first_release_date, "
            "involved_companies.company.name, involved_companies.publisher, "
            "involved_companies.developer, cover.image_id, "
            "screenshots.image_id, rating, total_rating, "
            "game_modes.name, themes.name, player_perspectives.name, "
            "alternative_names.name, alternative_names.comment, "
            "game_localizations.name, game_localizations.region; "
        )

        safe = self._clean_query(query)

        body = (
            f"{fields}"
            f'where (name ~ *"{safe}"* '
            f'| alternative_names.name ~ *"{safe}"*) '
            f"& platforms = ({platform_id}); "
            f"limit 10;"
        )
        return self._try_search(body, platform)

    def _try_search(self, body: str, platform: str) -> list[ScrapeResult]:
        """Execute an IGDB API request and parse results."""
        try:
            games = self._api_request("games", body)
        except Exception as e:
            logger.error(f"IGDB search failed: {e}")
            return []

        return [self._parse_game(game, platform) for game in games]

    def get_by_id(self, provider_id: str, platform: str) -> ScrapeResult | None:
        """Fetch by IGDB game ID."""
        body = (
            f"fields name, summary, genres.name, first_release_date, "
            f"involved_companies.company.name, involved_companies.publisher, "
            f"involved_companies.developer, cover.image_id, "
            f"screenshots.image_id, rating, total_rating, "
            f"game_modes.name, themes.name, "
            f"alternative_names.name, alternative_names.comment, "
            f"game_localizations.name, game_localizations.region; "
            f"where id = {provider_id};"
        )
        try:
            games = self._api_request("games", body)
            if games:
                return self._parse_game(games[0], platform)
        except Exception as e:
            logger.error(f"IGDB get_by_id failed: {e}")
        return None

    def _parse_game(self, game: dict[str, Any], platform: str) -> ScrapeResult:
        """Parse an IGDB game object into a ScrapeResult."""
        # Extract companies
        publisher = ""
        developer = ""
        for ic in game.get("involved_companies", []):
            company_name = ic.get("company", {}).get("name", "")
            if ic.get("publisher"):
                publisher = publisher or company_name
            if ic.get("developer"):
                developer = developer or company_name

        # Cover URL
        cover_url = ""
        cover = game.get("cover", {})
        if isinstance(cover, dict) and cover.get("image_id"):
            cover_url = f"{_IGDB_IMAGE_BASE}/t_cover_big/{cover['image_id']}.jpg"

        # Screenshots
        screenshots = []
        for ss in game.get("screenshots", []):
            if isinstance(ss, dict) and ss.get("image_id"):
                screenshots.append(
                    f"{_IGDB_IMAGE_BASE}/t_screenshot_big/{ss['image_id']}.jpg"
                )

        # Release date
        release_date = ""
        ts = game.get("first_release_date")
        if ts:
            from datetime import datetime, timezone

            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            release_date = dt.strftime("%Y-%m-%d")

        # Genres
        genres = [g["name"] for g in game.get("genres", []) if isinstance(g, dict)]

        # Parse multilingual titles from game_localizations and alternative_names
        title_en = game.get("name", "")
        title_ja = ""
        title_zh = ""

        # --- Source 1: game_localizations (detect language by Unicode script) ---
        localizations = game.get("game_localizations", [])
        for loc in localizations:
            if not isinstance(loc, dict):
                continue
            loc_name = loc.get("name", "")
            if not loc_name:
                continue
            lang = self._detect_cjk_language(loc_name)
            if lang == "ja" and not title_ja:
                title_ja = loc_name
            elif lang == "zh" and not title_zh:
                title_zh = loc_name

        # --- Source 2: alternative_names fallback ---
        alt_names_raw = game.get("alternative_names", [])

        # Pass 2a: exact country name as comment (e.g. comment="Japan")
        for alt in alt_names_raw:
            if not isinstance(alt, dict):
                continue
            comment = (alt.get("comment") or "").strip().lower()
            alt_name = alt.get("name", "")
            if not alt_name:
                continue
            if comment == "japan" and not title_ja:
                title_ja = alt_name
            elif comment in ("china", "taiwan", "hong kong") and not title_zh:
                title_zh = alt_name

        # Pass 2b: "Japanese title" style (skip translated / romanization)
        for alt in alt_names_raw:
            if not isinstance(alt, dict):
                continue
            comment = (alt.get("comment") or "").strip().lower()
            alt_name = alt.get("name", "")
            if not alt_name:
                continue
            if "translated" in comment or "romanization" in comment:
                continue
            if not title_ja and "japanese" in comment:
                title_ja = alt_name
            elif not title_zh and "chinese" in comment:
                title_zh = alt_name

        return ScrapeResult(
            provider="igdb",
            game_id=str(game.get("id", "")),
            title=title_en,
            title_en=title_en,
            title_ja=title_ja,
            title_zh=title_zh,
            overview=game.get("summary", ""),
            publisher=publisher,
            developer=developer,
            release_date=release_date,
            genre=", ".join(genres),
            tags=genres,
            boxart_url=cover_url,
            screenshot_urls=screenshots,
            rating=game.get("total_rating"),
            platform=platform,
        )
