"""SNES game plugin — ROM parsing and game identification for Super Nintendo."""

from __future__ import annotations

import json
import zlib
from pathlib import Path

from app.models.rom_entry import RomInfo
from app.plugins.base import GamePlugin
from app.plugins.snes.parsers import SNESHeaderInfo, parse_snes_header

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


class SNESGamePlugin(GamePlugin):
    """GamePlugin for the Super Nintendo Entertainment System platform."""

    @property
    def name(self) -> str:
        return "snes"

    @property
    def display_name(self) -> str:
        return "Super Nintendo Entertainment System"

    @property
    def platform(self) -> str:
        return "snes"

    # ── ROM extensions ──

    def get_rom_extensions(self) -> list[str]:
        return [".sfc", ".smc", ".fig", ".swc"]

    # ── ROM parsing ──

    def parse_rom_info(self, rom_path: Path) -> RomInfo | None:
        header = parse_snes_header(rom_path)

        crc_full, crc_nocopier = self._compute_crc32_pair(rom_path, header)
        title_name = ""
        region = ""
        publisher = ""
        version = "1.0"
        dat_crc32: list[str] | None = None
        matched_crc = ""

        if header:
            region = header.region
            publisher = header.publisher
            version = header.version_string

        # Try matching with both full and no-copier-header CRC32
        for crc in (crc_full, crc_nocopier):
            if not crc:
                continue
            # Priority 1: custom DB
            custom = _load_custom_db().get(crc)
            if custom:
                title_name = custom["name"]
                region = custom.get("region", region)
                matched_crc = crc
                dat_crc32 = [crc]
                break
            # Priority 2: official games DB
            db_name = _load_games_db().get(crc)
            if db_name:
                title_name = db_name
                matched_crc = crc
                dat_crc32 = [crc]
                break

        crc = matched_crc or crc_full

        # Priority 3: ROM header embedded title
        if not title_name and header:
            title_name = header.game_title

        # Priority 4: filename stem
        if not title_name:
            title_name = rom_path.stem

        info = RomInfo(
            title_id=crc or rom_path.stem,
            title_name=title_name,
            content_type="raw",
            file_type="base",
            region=region,
            publisher=publisher,
            version=version,
            dat_crc32=dat_crc32,
        )

        return info

    # ── Game ID extraction ──

    def extract_game_id(self, rom_path: Path) -> str:
        """
        Extract a canonical game ID from a SNES ROM.

        Uses CRC32 as the primary key. Tries both with and without
        copier header to match the database.
        """
        header = parse_snes_header(rom_path)
        crc_full, crc_nocopier = self._compute_crc32_pair(rom_path, header)
        db = _load_games_db()
        custom = _load_custom_db()
        for crc in (crc_full, crc_nocopier):
            if crc and (crc in db or crc in custom):
                return crc
        return crc_full or rom_path.stem

    # ── Scraper platform IDs ──

    def get_scraper_platform_ids(self) -> dict[str, str | int]:
        return {"igdb": 19, "screenscraper": 4}

    # ── Helpers ──

    @staticmethod
    def _compute_crc32_raw(path: Path, max_size: int = 64 * 1024 * 1024) -> str:
        """Compute CRC32 for the entire file."""
        try:
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
        except OSError:
            return ""

    @staticmethod
    def _compute_crc32_pair(
        path: Path, header: SNESHeaderInfo | None, max_size: int = 64 * 1024 * 1024
    ) -> tuple[str, str]:
        """Compute both full and headerless CRC32 for a SNES ROM.

        Returns (crc_full, crc_without_copier_header).
        If the file has a 512-byte copier header, the second CRC
        is computed without it. Otherwise both values are the same.
        """
        try:
            size = path.stat().st_size
            if size > max_size:
                return ("", "")
            with open(path, "rb") as f:
                data = f.read()
            crc_full = f"{zlib.crc32(data) & 0xFFFFFFFF:08X}"
            has_copier = header.has_copier_header if header else (size % 1024 == 512)
            if has_copier and len(data) > 512:
                crc_nocopier = f"{zlib.crc32(data[512:]) & 0xFFFFFFFF:08X}"
            else:
                crc_nocopier = crc_full
            return (crc_full, crc_nocopier)
        except OSError:
            return ("", "")
