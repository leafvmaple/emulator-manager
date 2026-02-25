"""Game save data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class SaveType(StrEnum):
    """Type of save data."""

    MEMCARD = "memcard"
    BATTERY = "battery"
    SAVESTATE = "savestate"
    FOLDER = "folder"
    FILE = "file"


@dataclass
class SaveFile:
    """Individual save file."""

    path: Path
    save_type: SaveType
    size: int = 0
    modified_time: float = 0.0


@dataclass
class GameSave:
    """Collection of save files for one game under one emulator."""

    emulator: str
    game_name: str
    game_id: str
    platform: str
    crc32: str = ""
    files: list[SaveFile] = field(default_factory=list)

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)
