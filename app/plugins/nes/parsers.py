"""NES ROM header parser — read iNES/NES 2.0 header from .nes files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

# iNES header layout (16 bytes)
# 0x00 - 0x03 : Magic "NES\x1A"
# 0x04        : PRG ROM size in 16 KB units
# 0x05        : CHR ROM size in 8 KB units
# 0x06        : Flags 6 — mapper (low nibble), mirroring, battery, trainer
# 0x07        : Flags 7 — mapper (high nibble), VS/Playchoice, NES 2.0
# 0x08        : Flags 8 — PRG RAM size (rarely used in iNES 1.0)
# 0x09        : Flags 9 — TV system (0 = NTSC, 1 = PAL)
# 0x0A        : Flags 10 — TV system, PRG RAM presence (unofficial)
# 0x0B - 0x0F : Padding (should be zero)

_INES_MAGIC = b"NES\x1a"
_HEADER_SIZE = 16

# Flags 9 → region mapping
_TV_SYSTEM_MAP: dict[int, str] = {
    0: "NTSC",
    1: "PAL",
}


@dataclass
class NESHeaderInfo:
    """Parsed NES ROM header data."""

    prg_rom_size: int = 0      # PRG ROM in bytes
    chr_rom_size: int = 0      # CHR ROM in bytes
    mapper: int = 0            # mapper number
    mirroring: str = ""        # "horizontal" or "vertical"
    has_battery: bool = False  # battery-backed PRG RAM
    has_trainer: bool = False  # 512-byte trainer present
    is_nes2: bool = False      # NES 2.0 format
    tv_system: str = ""        # "NTSC" or "PAL"
    rom_size: int = 0          # total ROM file size

    @property
    def region(self) -> str:
        if self.tv_system == "PAL":
            return "Europe"
        return ""

    @property
    def version_string(self) -> str:
        return "1.0"


def parse_nes_header(path: Path) -> NESHeaderInfo | None:
    """
    Parse the iNES/NES 2.0 header from a ``.nes`` file.

    Returns ``None`` if the file is too small or doesn't have the iNES magic.
    """
    try:
        file_size = path.stat().st_size
        with open(path, "rb") as f:
            header = f.read(_HEADER_SIZE)
    except OSError as e:
        logger.debug(f"Failed to read NES ROM '{path.name}': {e}")
        return None

    if len(header) < _HEADER_SIZE:
        return None

    # Validate magic bytes
    if header[:4] != _INES_MAGIC:
        logger.debug(f"NES header: invalid magic for '{path.name}'")
        return None

    prg_rom_size = header[4] * 16384   # 16 KB units
    chr_rom_size = header[5] * 8192    # 8 KB units

    flags6 = header[6]
    flags7 = header[7]
    flags9 = header[9]

    # Mapper number: low nibble from flags6 high bits, high nibble from flags7 high bits
    mapper = (flags6 >> 4) | (flags7 & 0xF0)

    # Mirroring: bit 0 of flags6 (0 = horizontal, 1 = vertical)
    # Bit 3 = four-screen mode overrides
    if flags6 & 0x08:
        mirroring = "four-screen"
    elif flags6 & 0x01:
        mirroring = "vertical"
    else:
        mirroring = "horizontal"

    has_battery = bool(flags6 & 0x02)
    has_trainer = bool(flags6 & 0x04)

    # NES 2.0 detection: bits 2-3 of flags7 == 0b10
    is_nes2 = (flags7 & 0x0C) == 0x08

    # TV system
    tv_system = _TV_SYSTEM_MAP.get(flags9 & 0x01, "NTSC")

    return NESHeaderInfo(
        prg_rom_size=prg_rom_size,
        chr_rom_size=chr_rom_size,
        mapper=mapper,
        mirroring=mirroring,
        has_battery=has_battery,
        has_trainer=has_trainer,
        is_nes2=is_nes2,
        tv_system=tv_system,
        rom_size=file_size,
    )
