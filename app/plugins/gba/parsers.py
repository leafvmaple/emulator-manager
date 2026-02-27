"""GBA ROM header parser — read game title, game code, maker code from .gba files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

# GBA ROM header layout (offsets from 0x00)
# 0x00 - 0x03 : ARM branch instruction (entry point)
# 0x04 - 0x9F : Nintendo logo (compressed bitmap)
# 0xA0 - 0xAB : Game title  (12 bytes, uppercase ASCII, padded with 0x00)
# 0xAC - 0xAF : Game code   (4 bytes, e.g. "AXVE" = Pokémon Ruby US)
# 0xB0 - 0xB1 : Maker code  (2 bytes, e.g. "01" = Nintendo)
# 0xB2        : Fixed value  (must be 0x96)
# 0xB3        : Main unit code (0x00 for GBA)
# 0xB4        : Device type
# 0xB5 - 0xBB : Reserved (7 bytes)
# 0xBC        : Software version
# 0xBD        : Complement check (header checksum)

_HEADER_SIZE = 0xC0  # minimum bytes needed

# Game code last character → region mapping
# Sources: devkitPro/ndstool ndscodes.cpp (J/E/P/D/F/I/S/H/K/X)
#          + well-known GBA additions (U=Australia, C=China/iQue)
_REGION_MAP: dict[str, str] = {
    "J": "Japan",
    "E": "USA",
    "P": "Europe",
    "D": "Germany",
    "F": "France",
    "S": "Spain",
    "I": "Italy",
    "H": "Netherlands",
    "U": "Australia",
    "K": "Korea",
    "C": "China",
    "X": "Europe",
}

# Well-known maker codes → publisher name
_MAKER_MAP: dict[str, str] = {
    "01": "Nintendo",
    "08": "Capcom",
    "13": "Electronic Arts",
    "20": "Activision",
    "41": "Ubisoft",
    "4F": "Eidos",
    "52": "Atlus",
    "5G": "Majesco",
    "69": "Electronic Arts (Victor)",
    "6S": "TDK Mediactive",
    "7D": "Vivendi Universal",
    "8P": "Sega",
    "A4": "Konami",
    "AF": "Namco",
    "B2": "Bandai",
    "C8": "Koei",
    "DA": "Tomy",
    "EB": "Atlus",
    "G9": "D3 Publisher",
    "MV": "Marvelous Entertainment",
}


@dataclass
class GBAHeaderInfo:
    """Parsed GBA ROM header data."""

    game_title: str = ""       # 12-char internal title
    game_code: str = ""        # 4-char game code (e.g. "AXVE")
    maker_code: str = ""       # 2-char maker code (e.g. "01")
    software_version: int = 0  # version byte
    valid_checksum: bool = False

    @property
    def region(self) -> str:
        if len(self.game_code) >= 4:
            return _REGION_MAP.get(self.game_code[3], "")
        return ""

    @property
    def publisher(self) -> str:
        return _MAKER_MAP.get(self.maker_code, "")

    @property
    def full_game_id(self) -> str:
        """Canonical ID: 'AGB-XXXX' format."""
        if self.game_code:
            return f"AGB-{self.game_code}"
        return ""

    @property
    def version_string(self) -> str:
        """Human-readable version: 0 → '1.0', 1 → '1.1', etc."""
        return f"1.{self.software_version}"


def parse_gba_header(path: Path) -> GBAHeaderInfo | None:
    """
    Parse the GBA ROM header from a ``.gba`` file.

    Returns ``None`` if the file is too small or doesn't look like a GBA ROM.
    """
    try:
        with open(path, "rb") as f:
            header = f.read(_HEADER_SIZE)
    except OSError as e:
        logger.debug(f"Failed to read GBA ROM '{path.name}': {e}")
        return None

    if len(header) < _HEADER_SIZE:
        return None

    # Validate fixed byte at 0xB2 (should be 0x96)
    if header[0xB2] != 0x96:
        logger.debug(f"GBA header validation failed for '{path.name}': "
                      f"byte 0xB2 = {header[0xB2]:#04x}, expected 0x96")
        # Don't return None — some homebrew ROMs lack this, still try to parse

    # Game title: 12 bytes at 0xA0
    game_title_raw = header[0xA0:0xAC]
    game_title = game_title_raw.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()

    # Game code: 4 bytes at 0xAC
    game_code_raw = header[0xAC:0xB0]
    game_code = game_code_raw.decode("ascii", errors="replace").strip("\x00").strip()

    # Maker code: 2 bytes at 0xB0
    maker_code_raw = header[0xB0:0xB2]
    maker_code = maker_code_raw.decode("ascii", errors="replace").strip("\x00").strip()

    # Software version: 1 byte at 0xBC
    software_version = header[0xBC]

    # Complement check: header[0xBD]
    # checksum = -(sum of bytes 0xA0..0xBC) - 0x19, truncated to 8 bits
    chk_sum = 0
    for i in range(0xA0, 0xBD):
        chk_sum += header[i]
    expected = (-(chk_sum + 0x19)) & 0xFF
    valid_checksum = header[0xBD] == expected

    return GBAHeaderInfo(
        game_title=game_title,
        game_code=game_code,
        maker_code=maker_code,
        software_version=software_version,
        valid_checksum=valid_checksum,
    )
