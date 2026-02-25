"""Switch game plugin — ROM parsing and game identification for Nintendo Switch."""

from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

from app.models.rom_entry import RomInfo
from app.plugins.base import GamePlugin
from app.plugins.switch.parsers import classify_title_id, parse_nsp, parse_xci


class SwitchGamePlugin(GamePlugin):
    """GamePlugin for the Nintendo Switch platform."""

    @property
    def name(self) -> str:
        return "switch"

    @property
    def display_name(self) -> str:
        return "Nintendo Switch"

    @property
    def platform(self) -> str:
        return "switch"

    # ── ROM extensions ──

    def get_rom_extensions(self) -> list[str]:
        return [".nsp", ".xci", ".nsz", ".xcz", ".nro"]

    # ── ROM parsing ──

    def parse_rom_info(self, rom_path: Path) -> RomInfo | None:
        suffix = rom_path.suffix.lower()
        try:
            if suffix in (".nsp", ".nsz"):
                return self._parse_nsp_info(rom_path)
            elif suffix in (".xci", ".xcz"):
                return self._parse_xci_info(rom_path)
            elif suffix == ".nro":
                return self._parse_nro_info(rom_path)
        except Exception as e:
            logger.debug(f"Failed to parse ROM '{rom_path.name}': {e}")
        return None

    def _parse_nsp_info(self, rom_path: Path) -> RomInfo:
        data = parse_nsp(rom_path)
        title_id = data.get("title_id", "") or ""
        info = RomInfo(
            title_id=title_id,
            content_type="nsp",
            file_type=classify_title_id(title_id) if title_id else "unknown",
        )
        self._fill_from_nacp(info, data.get("nacp"))
        if not info.title_name:
            info.title_name = self._extract_title_from_filename(rom_path)
        return info

    def _parse_xci_info(self, rom_path: Path) -> RomInfo:
        data = parse_xci(rom_path)
        title_id = data.get("title_id", "") or ""
        info = RomInfo(
            title_id=title_id,
            content_type="xci",
            file_type=classify_title_id(title_id) if title_id else "unknown",
        )
        self._fill_from_nacp(info, data.get("nacp"))
        if not info.title_name:
            info.title_name = self._extract_title_from_filename(rom_path)
        return info

    def _parse_nro_info(self, rom_path: Path) -> RomInfo:
        return RomInfo(
            title_name=self._extract_title_from_filename(rom_path),
            content_type="raw",
            file_type="base",
        )

    @staticmethod
    def _fill_from_nacp(info: RomInfo, nacp) -> None:
        if nacp is None:
            return
        info.title_name_zh = nacp.titles.get("zh_CN", "")
        info.title_name_en = nacp.titles.get("en_US", "")
        info.title_name_ja = nacp.titles.get("ja_JP", "")
        if not info.title_name:
            info.title_name = (
                info.title_name_zh or info.title_name_en or info.title_name_ja
            )
        info.publisher = nacp.publisher
        info.version = nacp.version

    @staticmethod
    def _extract_title_from_filename(rom_path: Path) -> str:
        """Best-effort title from filename: strip bracket/paren groups."""
        stem = rom_path.stem
        cleaned = re.sub(r"[\[\(].*?[\]\)]", "", stem)
        return cleaned.strip() or stem

    # ── Game ID extraction ──

    def extract_game_id(self, rom_path: Path) -> str:
        """
        Extract a canonical game ID from a Switch ROM.

        Priority: embedded title ID → filename bracket pattern → stem.
        """
        info = self.parse_rom_info(rom_path)
        if info and info.title_id:
            return info.title_id

        # Bracket pattern: [0100...000]
        m = re.search(r"\[([0-9A-Fa-f]{16})\]", rom_path.stem)
        if m:
            return m.group(1).upper()

        return rom_path.stem

    # ── Classification ──

    def classify_rom(self, rom_path: Path) -> str:
        """Classify a Switch ROM as base/update/dlc via title-ID suffix."""
        game_id = self.extract_game_id(rom_path)
        if re.fullmatch(r"[0-9A-Fa-f]{16}", game_id):
            return classify_title_id(game_id)
        return "unknown"

    # ── Scraper platform IDs ──

    def get_scraper_platform_ids(self) -> dict[str, str | int]:
        return {"igdb": 130, "screenscraper": 225}
