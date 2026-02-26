"""ROM entry and info models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RomFileType(StrEnum):
    """ROM file classification (especially for Switch)."""

    BASE = "base"
    UPDATE = "update"
    DLC = "dlc"
    UNKNOWN = "unknown"


class ContentType(StrEnum):
    """ROM container format."""

    NSP = "nsp"
    XCI = "xci"
    NSZ = "nsz"
    XCZ = "xcz"
    NRO = "nro"
    RAW = "raw"


@dataclass
class RomInfo:
    """ROM embedded metadata — extracted by plugin.parse_rom_info()."""

    title_id: str = ""
    title_name: str = ""
    title_name_zh: str = ""
    title_name_en: str = ""
    title_name_ja: str = ""
    publisher: str = ""
    version: str = ""
    version_raw: int = 0
    file_type: str = "unknown"  # base / update / dlc
    content_type: str = "raw"  # nsp / xci / nsz / xcz / raw
    region: str = ""
    languages: str = ""
    min_system_version: str = ""
    build_id: str = ""
    signature_valid: bool | None = None
    icon_path: str = ""
    dat_crc32: list[str] | None = None  # CRC32 list from No-Intro DAT (for verification)
    dat_id: int = -1  # Numeric ID from No-Intro DAT (-1 if unmatched or non-numeric)


@dataclass
class RomEntry:
    """ROM file index record — stored in rom_library.json."""

    rom_path: str
    platform: str
    emulator: str
    game_id: str  # Title ID / hash / filename stem
    file_size: int = 0
    hash_crc32: str = ""
    hash_sha1: str = ""
    added_at: str = ""
    rom_info: RomInfo | None = None
    scrape_status: str = "none"  # none / partial / done

    @property
    def display_name(self) -> str:
        """Best available display name, using region to pick language."""
        if self.rom_info:
            # Determine preferred language order based on ROM region
            region = (self.rom_info.region or "").lower()
            if region in ("japan",):
                order = (
                    self.rom_info.title_name_ja,
                    self.rom_info.title_name_en,
                    self.rom_info.title_name_zh,
                    self.rom_info.title_name,
                )
            elif region in ("china", "taiwan", "hong kong", "asia"):
                order = (
                    self.rom_info.title_name_zh,
                    self.rom_info.title_name_en,
                    self.rom_info.title_name_ja,
                    self.rom_info.title_name,
                )
            else:
                # USA, Europe, Germany, France, Spain, Italy, Australia, unknown
                order = (
                    self.rom_info.title_name_en,
                    self.rom_info.title_name_zh,
                    self.rom_info.title_name_ja,
                    self.rom_info.title_name,
                )
            for name in order:
                if name:
                    return name
        return self.game_id
