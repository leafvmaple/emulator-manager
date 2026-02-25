"""NDS game plugin — ROM parsing and game identification for Nintendo DS."""

from __future__ import annotations

import json
import zlib
from pathlib import Path

from app.models.rom_entry import RomInfo
from app.plugins.base import GamePlugin
from app.plugins.nds.parsers import parse_nds_header

_games_db: dict[str, dict[str, str]] | None = None
_custom_db: dict[str, dict[str, str]] | None = None


def _load_games_db() -> dict[str, dict[str, str]]:
    """Lazy-load the serial → {name, crc32} mapping from games.json."""
    global _games_db
    if _games_db is None:
        db_path = Path(__file__).parent / "games.json"
        if db_path.exists():
            with open(db_path, encoding="utf-8") as f:
                raw = json.load(f)
            # Support both old format {serial: name} and new {serial: {name, crc32}}
            _games_db = {}
            for k, v in raw.items():
                if isinstance(v, str):
                    _games_db[k] = {"name": v, "crc32": ""}
                else:
                    _games_db[k] = v
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


class NDSGamePlugin(GamePlugin):
    """GamePlugin for the Nintendo DS platform."""

    @property
    def name(self) -> str:
        return "nds"

    @property
    def display_name(self) -> str:
        return "Nintendo DS"

    @property
    def platform(self) -> str:
        return "nds"

    # ── ROM extensions ──

    def get_rom_extensions(self) -> list[str]:
        return [".nds", ".dsi", ".ids", ".srl"]

    # ── ROM parsing ──

    def parse_rom_info(self, rom_path: Path) -> RomInfo | None:
        header = parse_nds_header(rom_path)
        if header is None:
            return None

        # Determine file_type from unit code
        file_type = header.device_type.lower()  # "nds", "nds+dsi", "dsi"

        title_name = ""
        region = header.region

        # Priority 1: custom DB (fan translations etc.) keyed by CRC32
        crc = self._compute_crc32(rom_path)
        if crc:
            custom = _load_custom_db().get(crc)
            if custom:
                title_name = custom["name"]
                region = custom.get("region", region)

        # Priority 2: official games DB keyed by serial
        dat_crc32: list[str] = []
        if not title_name and header.game_code:
            db_entry = _load_games_db().get(header.game_code.upper())
            if db_entry:
                title_name = db_entry["name"]
                raw_crc = db_entry.get("crc32", [])
                if isinstance(raw_crc, list):
                    dat_crc32 = raw_crc
                elif raw_crc:
                    dat_crc32 = [raw_crc]

        # Priority 3: ROM header embedded name
        if not title_name:
            title_name = header.game_title

        info = RomInfo(
            title_id=header.full_game_id,        # NTR-ADAE
            title_name=title_name,
            content_type="raw",
            file_type=file_type,
            region=region,
            publisher=header.publisher,
            version=header.version_string,
            dat_crc32=dat_crc32 or None,
        )

        return info

    # ── Game ID extraction ──

    def extract_game_id(self, rom_path: Path) -> str:
        """
        Extract a canonical game ID from an NDS ROM.

        Priority: header game code (NTR-XXXX) → CRC32 → filename stem.
        """
        header = parse_nds_header(rom_path)
        if header and header.game_code:
            return header.full_game_id  # e.g. "NTR-ADAE"

        # Fallback: CRC32
        try:
            crc = self._compute_crc32(rom_path)
            if crc:
                return crc
        except Exception:
            pass

        return rom_path.stem

    # ── Scraper platform IDs ──

    def get_scraper_platform_ids(self) -> dict[str, str | int]:
        return {"igdb": 20, "screenscraper": 15}

    # ── Helpers ──

    @staticmethod
    def _compute_crc32(path: Path, max_size: int = 256 * 1024 * 1024) -> str:
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
