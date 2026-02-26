"""ROM library — JSON-based ROM index management."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from app.models.rom_entry import RomEntry, RomInfo


def _rom_entry_from_dict(data: dict[str, Any]) -> RomEntry:
    """Reconstruct a RomEntry from a dict (loaded from JSON)."""
    rom_info_data = data.pop("rom_info", None)
    rom_info = RomInfo(**rom_info_data) if isinstance(rom_info_data, dict) else None
    return RomEntry(**data, rom_info=rom_info)


def _rom_entry_to_dict(entry: RomEntry) -> dict[str, Any]:
    """Convert a RomEntry to a serializable dict."""
    d = asdict(entry)
    # Clean up None rom_info
    if d.get("rom_info") is None:
        d.pop("rom_info", None)
    return d


class RomLibrary:
    """
    ROM index manager — reads/writes rom_library.json.

    Key format: "{platform}:{game_id}"
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._path = data_dir / "rom_library.json"
        self._roms: dict[str, RomEntry] = {}
        self._version = 1

    def load(self) -> None:
        """Load ROM index from disk."""
        self._roms.clear()
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            self._version = data.get("version", 1)
            for key, rom_data in data.get("roms", {}).items():
                try:
                    self._roms[key] = _rom_entry_from_dict(rom_data)
                except (TypeError, KeyError) as e:
                    logger.warning(f"Skipping malformed ROM entry '{key}': {e}")
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load ROM library: {e}")

    def save(self) -> None:
        """Persist ROM index to disk."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": self._version,
            "roms": {key: _rom_entry_to_dict(entry) for key, entry in self._roms.items()},
        }
        tmp = self._path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp.replace(self._path)
        except OSError as e:
            logger.error(f"Failed to save ROM library: {e}")
            tmp.unlink(missing_ok=True)

    @staticmethod
    def make_key(platform: str, game_id: str) -> str:
        return f"{platform}:{game_id}"

    def clear(self) -> None:
        """Remove all entries."""
        self._roms.clear()

    def add(self, entry: RomEntry) -> None:
        """Add or update a ROM entry."""
        if not entry.added_at:
            entry.added_at = datetime.now(tz=timezone.utc).isoformat()
        key = self.make_key(entry.platform, entry.game_id)
        self._roms[key] = entry

    def remove(self, platform: str, game_id: str) -> None:
        key = self.make_key(platform, game_id)
        self._roms.pop(key, None)

    def get(self, platform: str, game_id: str) -> RomEntry | None:
        key = self.make_key(platform, game_id)
        return self._roms.get(key)

    def find_by_hash(self, crc32: str) -> list[RomEntry]:
        """Find ROM entries by CRC32 hash."""
        return [e for e in self._roms.values() if e.hash_crc32 == crc32]

    def all_entries(self) -> list[RomEntry]:
        return list(self._roms.values())

    def entries_by_platform(self, platform: str) -> list[RomEntry]:
        return [e for e in self._roms.values() if e.platform == platform]

    def entries_by_emulator(self, emulator: str) -> list[RomEntry]:
        return [e for e in self._roms.values() if e.emulator == emulator]

    def update_path(self, old_path: str, new_path: str) -> None:
        """Update ROM path after rename."""
        for entry in self._roms.values():
            if entry.rom_path == old_path:
                entry.rom_path = new_path
                return

    def find_duplicates(self) -> list[list[RomEntry]]:
        """Find duplicate ROMs based on (platform, game_id) hash or identical hash."""
        hash_groups: dict[str, list[RomEntry]] = {}
        for entry in self._roms.values():
            if entry.hash_crc32:
                hk = f"{entry.platform}:{entry.hash_crc32}"
                if hk not in hash_groups:
                    hash_groups[hk] = []
                hash_groups[hk].append(entry)
        return [group for group in hash_groups.values() if len(group) > 1]

    @property
    def count(self) -> int:
        return len(self._roms)
