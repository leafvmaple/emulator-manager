"""GBA game plugin — ROM parsing and game identification for Game Boy Advance."""

from __future__ import annotations

import json
import zlib
from pathlib import Path

from app.models.rom_entry import RomInfo
from app.plugins.base import GamePlugin
from app.plugins.gba.parsers import parse_gba_header

_games_db: dict[str, str] | None = None
_custom_db: dict[str, dict[str, str]] | None = None


def _load_games_db() -> dict[str, str]:
    """Lazy-load the CRC32 → name mapping from games.json."""
    global _games_db
    if _games_db is None:
        db_path = Path(__file__).parent / "games.json"
        if db_path.exists():
            with open(db_path, encoding="utf-8") as f:
                _games_db = json.load(f)
        else:
            _games_db = {}
    assert _games_db is not None
    return _games_db


def _load_custom_db() -> dict[str, dict[str, str]]:
    """Lazy-load the CRC32 → {name, region} mapping from games_custom.json."""
    global _custom_db
    if _custom_db is None:
        db_path = Path(__file__).parent / "games_custom.json"
        if db_path.exists():
            with open(db_path, encoding="utf-8") as f:
                _custom_db = json.load(f)
        else:
            _custom_db = {}
    assert _custom_db is not None
    return _custom_db


class GBAGamePlugin(GamePlugin):
    """GamePlugin for the Game Boy Advance platform."""

    @property
    def name(self) -> str:
        return "gba"

    @property
    def display_name(self) -> str:
        return "Game Boy Advance"

    @property
    def platform(self) -> str:
        return "gba"

    # ── ROM extensions ──

    def get_rom_extensions(self) -> list[str]:
        return [".gba", ".agb", ".mb"]

    # ── ROM parsing ──

    def parse_rom_info(self, rom_path: Path) -> RomInfo | None:
        header = parse_gba_header(rom_path)
        if header is None:
            return None

        title_name = ""
        region = header.region
        dat_crc32: list[str] | None = None

        # Compute CRC32 first
        crc = self._compute_crc32(rom_path)

        # Priority 1: custom DB (fan translations etc.) keyed by CRC32
        if crc:
            custom = _load_custom_db().get(crc)
            if custom:
                title_name = custom["name"]
                region = custom.get("region", region)
                dat_crc32 = [crc]

        # Priority 2: official games DB keyed by CRC32
        if not title_name and crc:
            db_name = _load_games_db().get(crc)
            if db_name:
                title_name = db_name
                dat_crc32 = [crc]

        # Priority 3: ROM header embedded name
        if not title_name:
            title_name = header.game_title

        info = RomInfo(
            title_id=header.full_game_id,       # AGB-AXVE
            title_name=title_name,
            content_type="raw",
            file_type="base",
            region=region,
            publisher=header.publisher,
            version=header.version_string,
            dat_crc32=dat_crc32,
        )

        return info

    # ── Game ID extraction ──

    def extract_game_id(self, rom_path: Path) -> str:
        """
        Extract a canonical game ID from a GBA ROM.

        Priority: header game code (AGB-XXXX) → CRC32 → filename stem.
        """
        header = parse_gba_header(rom_path)
        if header and header.game_code:
            return header.full_game_id  # e.g. "AGB-AXVE"

        # Fallback: CRC32 of the entire file (GBA ROMs are small enough)
        try:
            crc = self._compute_crc32(rom_path)
            if crc:
                return crc
        except Exception:
            pass

        return rom_path.stem

    # ── Scraper platform IDs ──

    def get_scraper_platform_ids(self) -> dict[str, str | int]:
        return {"igdb": 24, "screenscraper": 12}

    # ── Helpers ──

    @staticmethod
    def _compute_crc32(path: Path, max_size: int = 64 * 1024 * 1024) -> str:
        """Compute CRC32 for the ROM file (skip files > max_size)."""
        if path.stat().st_size > max_size:
            return ""
        crc = 0
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                crc = zlib.crc32(chunk, crc)
        return f"{crc & 0xFFFFFFFF:08X}"
