"""NES game plugin — ROM parsing and game identification for Nintendo Entertainment System."""

from __future__ import annotations

import json
import re
import tempfile
import zlib
from pathlib import Path

from loguru import logger

from app.models.rom_entry import RomInfo
from app.plugins.base import GamePlugin
from app.plugins.nes.parsers import parse_nes_header

_games_db: dict[str, str] | None = None
_dat_headers: list[bytes] | None = None
_custom_db: dict[str, dict[str, str]] | None = None


def _load_games_db() -> dict[str, str]:
    """Lazy-load the CRC32 → name mapping from games.json."""
    global _games_db
    if _games_db is None:
        db_path = Path(__file__).parent / "games.json"
        if db_path.exists():
            with open(db_path, encoding="utf-8") as f:
                raw = json.load(f)
            _games_db = {}
            for crc, val in raw.items():
                _games_db[crc] = val if isinstance(val, str) else val.get("name", "")
        else:
            _games_db = {}
    assert _games_db is not None
    return _games_db


def _load_dat_headers() -> list[bytes]:
    """Lazy-load the deduplicated DAT headers from header.json."""
    global _dat_headers
    if _dat_headers is None:
        hdr_path = Path(__file__).parent / "header.json"
        if hdr_path.exists():
            with open(hdr_path, encoding="utf-8") as f:
                _dat_headers = [bytes.fromhex(h) for h in json.load(f)]
        else:
            _dat_headers = []
    assert _dat_headers is not None
    return _dat_headers


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


# No-Intro filename region tags → region string
_REGION_TAGS: dict[str, str] = {
    "Japan": "Japan",
    "USA": "USA",
    "Europe": "Europe",
    "World": "World",
    "Korea": "Korea",
    "China": "China",
    "Taiwan": "Taiwan",
    "Asia": "Asia",
    "Australia": "Australia",
    "Brazil": "Brazil",
    "Canada": "Canada",
    "France": "France",
    "Germany": "Germany",
    "Italy": "Italy",
    "Spain": "Spain",
    "Sweden": "Sweden",
    "Netherlands": "Netherlands",
}


def _extract_region_from_filename(stem: str) -> str:
    """Extract region from No-Intro style filename brackets, e.g. '(Japan)' or '(USA, Europe)'."""
    m = re.search(r"\(([^)]+)\)", stem)
    if not m:
        return ""
    content = m.group(1)
    # Check each comma-separated part
    parts = [p.strip() for p in content.split(",")]
    for part in parts:
        if part in _REGION_TAGS:
            return _REGION_TAGS[part]
    return ""


class NESGamePlugin(GamePlugin):
    """GamePlugin for the Nintendo Entertainment System platform."""

    @property
    def name(self) -> str:
        return "nes"

    @property
    def display_name(self) -> str:
        return "Nintendo Entertainment System"

    @property
    def platform(self) -> str:
        return "nes"

    # ── ROM extensions ──

    def get_rom_extensions(self) -> list[str]:
        return [".nes", ".unf", ".unif", ".fds"]

    # ── ROM parsing ──

    def parse_rom_info(self, rom_path: Path) -> RomInfo | None:
        header = parse_nes_header(rom_path)
        if header is None:
            return None

        crc = self._compute_crc32(rom_path)
        title_name = ""
        region = _extract_region_from_filename(rom_path.stem) or header.region
        dat_crc32: list[str] | None = None

        # Priority 1: custom DB (fan translations etc.) keyed by CRC32
        if crc:
            custom = _load_custom_db().get(crc)
            if custom:
                title_name = custom["name"]
                region = custom.get("region", region)
                dat_crc32 = [crc]

        # Priority 2: official games DB keyed by CRC32 (direct match)
        if not title_name and crc:
            db_name = _load_games_db().get(crc)
            if db_name:
                title_name = db_name
                dat_crc32 = [crc]

        # Priority 3: header-based matching — try each known DAT header
        # to compensate for iNES 1.0 vs NES 2.0 header differences.
        # Fixes the ROM file in-place on match.
        if not title_name and crc:
            matched_crc = self._match_with_dat_header(rom_path)
            if matched_crc:
                title_name = _load_games_db().get(matched_crc, "")
                dat_crc32 = [matched_crc]
                crc = matched_crc

        # Priority 4: filename stem (NES has no embedded game title)
        if not title_name:
            title_name = rom_path.stem

        return RomInfo(
            title_id=crc or rom_path.stem,
            title_name=title_name,
            content_type="raw",
            file_type="base",
            region=region,
            version=header.version_string,
            dat_crc32=dat_crc32,
        )

    # ── Game ID extraction ──

    def extract_game_id(self, rom_path: Path) -> str:
        """
        Extract a canonical game ID from a NES ROM.

        Uses CRC32 as the primary key since NES ROMs lack serial codes.
        """
        crc = self._compute_crc32(rom_path)
        if crc:
            return crc
        return rom_path.stem

    # ── Scraper platform IDs ──

    def get_scraper_platform_ids(self) -> dict[str, str | int]:
        return {"igdb": 18, "screenscraper": 3}

    # ── Helpers ──

    @staticmethod
    def _compute_crc32(path: Path, max_size: int = 64 * 1024 * 1024) -> str:
        """Compute CRC32 for the ROM file (skip files > max_size)."""
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
    def _match_with_dat_header(
        path: Path, max_size: int = 64 * 1024 * 1024
    ) -> str:
        """Try each DAT header to find a CRC match; fix in-place on success.

        Returns matched CRC string, or ``""`` if no match found.
        """
        headers = _load_dat_headers()
        if not headers:
            return ""
        try:
            size = path.stat().st_size
            if size > max_size or size < 16:
                return ""
            with open(path, "rb") as f:
                data = f.read()
            if data[:4] != b"NES\x1a":
                return ""
            body = data[16:]
            games = _load_games_db()
            for hdr in headers:
                crc = zlib.crc32(hdr + body) & 0xFFFFFFFF
                crc_str = f"{crc:08X}"
                if crc_str in games:
                    _fix_nes_header(path, data, hdr)
                    return crc_str
            return ""
        except OSError:
            return ""


def _fix_nes_header(path: Path, original_data: bytes, correct_header: bytes) -> None:
    """Replace the iNES header; backup real ROM files, skip temp files."""
    if original_data[:16] == correct_header:
        return

    # Skip backup for temp files (from ZIP extraction)
    try:
        is_temp = path.resolve().parent == Path(tempfile.gettempdir()).resolve()
    except (OSError, ValueError):
        is_temp = False

    if not is_temp:
        import shutil

        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            shutil.copy2(path, bak)
            logger.info(f"Backup: {path.name} → {bak.name}")

    with open(path, "wb") as f:
        f.write(correct_header + original_data[16:])
    logger.info(f"Fixed iNES header: {path.name}")
