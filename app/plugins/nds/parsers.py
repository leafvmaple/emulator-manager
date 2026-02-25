"""NDS ROM header parser — read game title, game code, maker code from .nds files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

# NDS ROM header layout (offsets from 0x00)
# 0x00 - 0x0B : Game title      (12 bytes, uppercase ASCII, padded with 0x00)
# 0x0C - 0x0F : Game code       (4 bytes, e.g. "ADAE" = Pokémon Diamond US)
# 0x10 - 0x11 : Maker code      (2 bytes, e.g. "01" = Nintendo)
# 0x12        : Unit code        (0x00 = NDS, 0x02 = NDS+DSi, 0x03 = DSi only)
# 0x13        : Encryption seed select
# 0x14 - 0x17 : Device capacity  (power of 2, chip size = 128KB << value)
# 0x1E        : ROM version
# 0x1F        : Internal flags (bit 2: autostart)
# 0x68 - 0x6B : Icon/title offset (pointer to banner)
# 0x80 - 0x83 : ARM9 ROM offset
# 0x15C       : Header checksum (CRC16 of bytes 0x00–0x15D)

_HEADER_SIZE = 0x200  # minimum bytes needed (512-byte NDS header)

# Game code first character → category
# A/B/C/D/H/I/K/T/U/V/Y = normal games
# The last character of game code → region
_REGION_MAP: dict[str, str] = {
    "J": "Japan",
    "E": "USA",
    "P": "Europe",
    "O": "International",
    "K": "Korea",
    "W": "Europe (alt)",
    "D": "Germany",
    "F": "France",
    "S": "Spain",
    "I": "Italy",
    "U": "Australia",
    "C": "China",
}

# Well-known maker codes → publisher name
_MAKER_MAP: dict[str, str] = {
    "01": "Nintendo",
    "08": "Capcom",
    "13": "Electronic Arts",
    "20": "Activision",
    "41": "Ubisoft",
    "4F": "Eidos",
    "4Q": "Disney",
    "52": "Atlus",
    "5G": "Majesco",
    "5H": "Take-Two",
    "69": "Electronic Arts (Victor)",
    "70": "Atari",
    "78": "THQ",
    "7D": "Vivendi Universal",
    "8P": "Sega",
    "A4": "Konami",
    "AF": "Namco Bandai",
    "B2": "Bandai",
    "C8": "Koei",
    "DA": "Tomy",
    "E9": "Natsume",
    "EB": "Atlus",
    "EL": "Sprint",
    "G9": "D3 Publisher",
    "GD": "Square Enix",
    "MV": "Marvelous Entertainment",
    "NK": "Neverland",
    "VZ": "Level-5",
    "WR": "Warner Bros.",
    "XS": "Aksys Games",
}

# Unit code → device type
_UNIT_CODE_MAP: dict[int, str] = {
    0x00: "NDS",
    0x02: "NDS+DSi",
    0x03: "DSi",
}


@dataclass
class NDSHeaderInfo:
    """Parsed NDS ROM header data."""

    game_title: str = ""       # 12-char internal title
    game_code: str = ""        # 4-char game code (e.g. "ADAE")
    maker_code: str = ""       # 2-char maker code (e.g. "01")
    unit_code: int = 0         # 0x00=NDS, 0x02=NDS+DSi, 0x03=DSi
    rom_version: int = 0       # version byte
    rom_size: int = 0          # total ROM size in bytes
    has_banner: bool = False   # whether icon/title data exists

    @property
    def region(self) -> str:
        """Determine region from last character of game code."""
        if len(self.game_code) >= 4:
            return _REGION_MAP.get(self.game_code[3], "")
        return ""

    @property
    def publisher(self) -> str:
        return _MAKER_MAP.get(self.maker_code, "")

    @property
    def device_type(self) -> str:
        return _UNIT_CODE_MAP.get(self.unit_code, "NDS")

    @property
    def full_game_id(self) -> str:
        """Canonical ID: 'NTR-XXXX' format (NTR = Nitro, Nintendo DS codename)."""
        if self.game_code:
            return f"NTR-{self.game_code}"
        return ""

    @property
    def version_string(self) -> str:
        """Human-readable version: 0 → '1.0', 1 → '1.1', etc."""
        return f"1.{self.rom_version}"


def parse_nds_header(path: Path) -> NDSHeaderInfo | None:
    """
    Parse the NDS ROM header from a ``.nds`` file.

    Returns ``None`` if the file is too small or doesn't look like an NDS ROM.
    """
    try:
        with open(path, "rb") as f:
            header = f.read(_HEADER_SIZE)
    except OSError as e:
        logger.debug(f"Failed to read NDS ROM '{path.name}': {e}")
        return None

    if len(header) < _HEADER_SIZE:
        return None

    # Game title: 12 bytes at 0x00
    game_title_raw = header[0x00:0x0C]
    game_title = game_title_raw.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()

    # Game code: 4 bytes at 0x0C
    game_code_raw = header[0x0C:0x10]
    game_code = game_code_raw.decode("ascii", errors="replace").strip("\x00").strip()

    # Validate: game code should be 4 printable ASCII characters
    if len(game_code) != 4 or not game_code.isascii() or not game_code.isprintable():
        logger.debug(f"NDS header: invalid game code '{game_code!r}' for '{path.name}'")
        # Don't bail out — still try to use what we have

    # Maker code: 2 bytes at 0x10
    maker_code_raw = header[0x10:0x12]
    maker_code = maker_code_raw.decode("ascii", errors="replace").strip("\x00").strip()

    # Unit code: 1 byte at 0x12
    unit_code = header[0x12]

    # ROM version: 1 byte at 0x1E
    rom_version = header[0x1E]

    # Device capacity → ROM size
    capacity = header[0x14]
    rom_size = (128 * 1024) << capacity if capacity < 16 else 0

    # Icon/title offset: 4 bytes LE at 0x68
    icon_offset = int.from_bytes(header[0x68:0x6C], "little")
    has_banner = icon_offset != 0

    return NDSHeaderInfo(
        game_title=game_title,
        game_code=game_code,
        maker_code=maker_code,
        unit_code=unit_code,
        rom_version=rom_version,
        rom_size=rom_size,
        has_banner=has_banner,
    )
