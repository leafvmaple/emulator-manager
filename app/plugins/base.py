"""Plugin base classes — two distinct plugin types for different concerns.

EmulatorPlugin  → save management (detect emulator, scan saves)
GamePlugin      → ROM/game management (parse ROMs, resolve names, scraping context)
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.emulator import EmulatorInfo
    from app.models.game_save import GameSave
    from app.models.rom_entry import RomInfo


# ═══════════════════════════════════════════════════════════════════════════════
#  EmulatorPlugin — serves the save-management module
# ═══════════════════════════════════════════════════════════════════════════════

class EmulatorPlugin(ABC):
    """
    Abstract base for **emulator** plugins.

    Each implementation represents one emulator (Yuzu, PCSX2, Mesen …).
    Responsibilities:
      • Detect emulator installation paths
      • Scan save files / directories
      • Know which platform(s) the emulator supports
    """

    # ── Required interface ──

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier (e.g. 'yuzu', 'pcsx2')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name (e.g. 'Yuzu', 'PCSX2')."""
        ...

    @property
    @abstractmethod
    def supported_platforms(self) -> list[str]:
        """Platform IDs this emulator handles (e.g. ['switch'], ['ps2'])."""
        ...

    @abstractmethod
    def detect_installation(
        self, extra_paths: list[str] | None = None
    ) -> list[EmulatorInfo]:
        """Detect installed instances of this emulator."""
        ...

    @abstractmethod
    def scan_saves(
        self, emulator: EmulatorInfo, custom_paths: list[str] | None = None
    ) -> list[GameSave]:
        """Scan save files for the given emulator installation."""
        ...

    @abstractmethod
    def get_save_directories(self, emulator: EmulatorInfo) -> list[str]:
        """Return known save directory paths for this installation."""
        ...

    # ── Helpers ──

    @staticmethod
    def deduplicate(saves: list[GameSave]) -> list[GameSave]:
        """Remove duplicate saves based on (game_id, emulator) key."""
        seen: set[str] = set()
        unique: list[GameSave] = []
        for s in saves:
            key = f"{s.emulator}:{s.game_id}"
            if key not in seen:
                seen.add(key)
                unique.append(s)
        return unique

    @staticmethod
    def deduplicate_installations(installations: list[EmulatorInfo]) -> list[EmulatorInfo]:
        """Remove duplicate installations based on data_path."""
        seen: set[str] = set()
        unique: list[EmulatorInfo] = []
        for info in installations:
            key = str(info.data_path)
            if key not in seen:
                seen.add(key)
                unique.append(info)
        return unique


# ═══════════════════════════════════════════════════════════════════════════════
#  GamePlugin — serves the ROM / game-info module
# ═══════════════════════════════════════════════════════════════════════════════

class GamePlugin(ABC):
    """
    Abstract base for **game / platform** plugins.

    Each implementation represents one gaming platform (Switch, PS2, NES …).
    Responsibilities:
      • Know which ROM file extensions belong to this platform
      • Parse ROM files for embedded metadata (title ID, version, …)
      • Extract a canonical game ID from a ROM path
      • Resolve game ID → human-readable display name
      • Provide platform context for scrapers
    """

    _display_name_table: dict[str, dict[str, str]] = {}

    # ── Required interface ──

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier, matches the platform ID (e.g. 'switch', 'ps2')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable platform name (e.g. 'Nintendo Switch')."""
        ...

    @property
    @abstractmethod
    def platform(self) -> str:
        """Single platform ID this plugin handles."""
        ...

    @abstractmethod
    def get_rom_extensions(self) -> list[str]:
        """File extensions this platform uses (e.g. ['.nsp', '.xci'])."""
        ...

    @abstractmethod
    def parse_rom_info(self, rom_path: Path) -> RomInfo | None:
        """Deep-parse a ROM file to extract embedded metadata."""
        ...

    @abstractmethod
    def extract_game_id(self, rom_path: Path) -> str:
        """
        Extract a canonical game ID from a ROM file.

        For Switch: title ID from NSP/XCI header or filename bracket pattern.
        For other platforms: filename stem, CRC, or header-based ID.
        Falls back to the filename stem if nothing better is available.
        """
        ...

    # ── Optional interface (with defaults) ──

    def resolve_game_name(self, game_id: str) -> str | None:
        """
        Map a game ID to a human-readable display name.

        Uses the plugin's ``game_names.json`` file.  Subclasses may also query
        ROM-embedded NACP/header data or online sources.
        """
        if not self._display_name_table:
            self._load_display_name_table()
        names = self._display_name_table.get(game_id, {})
        if names:
            return (
                names.get("zh_CN")
                or names.get("en_US")
                or names.get("ja_JP")
                or None
            )
        return None

    def resolve_display_names(self, saves: list[GameSave]) -> None:
        """Batch-resolve game IDs to display names on save objects."""
        for save in saves:
            resolved = self.resolve_game_name(save.game_id)
            if resolved:
                save.game_name = resolved

    def get_scraper_platform_ids(self) -> dict[str, str | int]:
        """
        Return platform identifiers used by each scraper provider.

        Example for Switch: ``{"igdb": 130, "screenscraper": 225}``
        Default returns empty dict; subclasses should override.
        """
        return {}

    def classify_rom(self, rom_path: Path) -> str:
        """
        Classify a ROM file as 'base', 'update', 'dlc', or 'unknown'.

        Default returns 'unknown'.  Override for platforms with title-ID schemes.
        """
        return "unknown"

    # ── Internal ──

    def _load_display_name_table(self) -> None:
        """Load ``game_names.json`` from the plugin's directory."""
        plugin_dir = Path(__file__).parent / self.name
        names_file = plugin_dir / "game_names.json"
        if names_file.exists():
            try:
                with open(names_file, encoding="utf-8") as f:
                    self._display_name_table = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._display_name_table = {}
