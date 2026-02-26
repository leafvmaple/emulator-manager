"""SNES ROM header parser — read internal header from .sfc/.smc files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

# SNES internal ROM header can be at different offsets depending on mapping mode:
# LoROM: 0x7FB0  (header at 0x7FC0, but we read from 0x7FB0 for maker code)
# HiROM: 0xFFB0
# ExLoROM: 0x407FB0
# ExHiROM: 0x40FFB0
#
# If the file has a 512-byte copier header (SMC), add 0x200 to all offsets.
#
# Internal header layout (relative to base):
# +0x10 (0xFFC0) : Game title       (21 bytes, ASCII, space-padded)
# +0x19 (0xFFD9) : Map mode         (1 byte)
# +0x1A (0xFFDA) : ROM type / chipset (1 byte)
# +0x1B (0xFFDB) : ROM size         (1 byte, 2^N KB)
# +0x1C (0xFFDC) : RAM size         (1 byte, 2^N KB)
# +0x1D (0xFFDD) : Country code     (1 byte)
# +0x1E (0xFFDE) : Licensee code    (1 byte, 0x33 = extended)
# +0x1F (0xFFDF) : Version number   (1 byte)
# +0x20 (0xFFE0) : Checksum complement (2 bytes LE)
# +0x22 (0xFFE2) : Checksum         (2 bytes LE)
#
# Extended header (if licensee == 0x33), at base +0x00:
# +0x00 (0xFFB0) : Maker code       (2 bytes, ASCII)
# +0x02 (0xFFB2) : Game code        (4 bytes, ASCII)

_HEADER_OFFSETS_LOROM = 0x7FB0
_HEADER_OFFSETS_HIROM = 0xFFB0

# Country code → region mapping
_COUNTRY_MAP: dict[int, str] = {
    0x00: "Japan",
    0x01: "USA",
    0x02: "Europe",
    0x03: "Sweden",
    0x04: "Finland",
    0x05: "Denmark",
    0x06: "France",
    0x07: "Netherlands",
    0x08: "Spain",
    0x09: "Germany",
    0x0A: "Italy",
    0x0B: "China",
    0x0C: "Indonesia",
    0x0D: "Korea",
    0x0F: "Canada",
    0x10: "Brazil",
    0x11: "Australia",
}

# Well-known licensee codes (old style, 1 byte)
_LICENSEE_MAP: dict[int, str] = {
    0x01: "Nintendo",
    0x08: "Capcom",
    0x0A: "Jaleco",
    0x13: "Electronic Arts",
    0x18: "Hudson Soft",
    0x1A: "Yanoman",
    0x33: "(extended)",  # uses 2-byte maker code
    0x41: "Ubisoft",
    0x4F: "Eidos",
    0x51: "Acclaim",
    0x52: "Activision",
    0x5D: "Tradewest",
    0x69: "Electronic Arts",
    0x78: "THQ",
    0x8B: "Bullet-Proof Software",
    0x99: "ARC / Pack-In Video",
    0xA4: "Konami",
    0xAF: "Namco",
    0xB2: "Bandai",
    0xBF: "Game Arts",
    0xC3: "Square",
    0xC5: "Data East",
    0xC8: "Koei",
    0xDA: "Tomy",
    0xEB: "Atlus",
}

# Extended maker codes (2-byte ASCII, used when licensee == 0x33)
_MAKER_MAP: dict[str, str] = {
    "01": "Nintendo",
    "08": "Capcom",
    "33": "Ocean / Acclaim",
    "41": "Ubisoft",
    "52": "Activision",
    "78": "THQ",
    "8P": "Sega",
    "A4": "Konami",
    "AF": "Namco",
    "B2": "Bandai",
    "C3": "Square Soft",
    "C5": "Data East",
    "C8": "Koei",
    "E9": "Natsume",
    "GD": "Square Enix",
}


@dataclass
class SNESHeaderInfo:
    """Parsed SNES ROM header data."""

    game_title: str = ""       # 21-char internal title
    game_code: str = ""        # 4-char game code (extended header only)
    maker_code: str = ""       # 2-char maker code (extended header only)
    country_code: int = 0      # country byte
    licensee_code: int = 0     # old licensee code
    rom_version: int = 0       # version byte
    rom_size: int = 0          # declared ROM size in bytes
    ram_size: int = 0          # declared RAM size in bytes
    has_battery: bool = False  # from ROM type byte
    mapping_mode: str = ""     # "LoROM" or "HiROM"
    has_copier_header: bool = False

    @property
    def region(self) -> str:
        return _COUNTRY_MAP.get(self.country_code, "")

    @property
    def publisher(self) -> str:
        # Extended maker code takes priority
        if self.maker_code:
            pub = _MAKER_MAP.get(self.maker_code)
            if pub:
                return pub
        # Fall back to old licensee code
        pub = _LICENSEE_MAP.get(self.licensee_code, "")
        return pub if pub != "(extended)" else ""

    @property
    def version_string(self) -> str:
        """Human-readable version: 0 → '1.0', 1 → '1.1', etc."""
        return f"1.{self.rom_version}"


def _try_parse_at(data: bytes, base: int) -> SNESHeaderInfo | None:
    """Try to parse a SNES internal header at the given offset."""
    if base + 0x30 > len(data):
        return None

    # Read fields relative to base (base = 0xFFB0 or 0x7FB0, etc.)
    # Title starts at base+0x10 (0xFFC0), 21 bytes through base+0x24 (0xFFD4)
    # Map mode at 0xFFD5 = base+0x25, etc.
    game_title_raw = data[base + 0x10: base + 0x25]  # 21 bytes
    map_mode = data[base + 0x25]
    rom_type = data[base + 0x26]
    rom_size_byte = data[base + 0x27]
    ram_size_byte = data[base + 0x28]
    country_code = data[base + 0x29]
    licensee_code = data[base + 0x2A]
    version = data[base + 0x2B]

    # Checksum validation
    checksum_complement = int.from_bytes(data[base + 0x2C: base + 0x2E], "little")
    checksum = int.from_bytes(data[base + 0x2E: base + 0x30], "little")

    # Basic validation: complement XOR checksum should be 0xFFFF
    if (checksum ^ checksum_complement) != 0xFFFF:
        return None

    # Game title: 21 bytes ASCII
    game_title = game_title_raw.decode("ascii", errors="replace").strip("\x00").strip()
    # Filter out obviously invalid titles
    if not game_title or all(c == "\x00" or c == "\xff" or c == " " for c in game_title):
        return None

    # ROM/RAM sizes
    rom_size = (1 << rom_size_byte) * 1024 if rom_size_byte < 16 else 0
    ram_size = (1 << ram_size_byte) * 1024 if ram_size_byte > 0 and ram_size_byte < 16 else 0

    # Battery: bit 1 of rom_type, or specific type values
    has_battery = bool(rom_type & 0x02)

    # Mapping mode
    mapping = "HiROM" if (map_mode & 0x01) else "LoROM"

    # Extended header: maker code + game code (only if licensee == 0x33)
    maker_code = ""
    game_code = ""
    if licensee_code == 0x33:
        maker_raw = data[base + 0x00: base + 0x02]
        maker_code = maker_raw.decode("ascii", errors="replace").strip("\x00").strip()
        game_raw = data[base + 0x02: base + 0x06]
        game_code = game_raw.decode("ascii", errors="replace").strip("\x00").strip()

    return SNESHeaderInfo(
        game_title=game_title,
        game_code=game_code,
        maker_code=maker_code,
        country_code=country_code,
        licensee_code=licensee_code,
        rom_version=version,
        rom_size=rom_size,
        ram_size=ram_size,
        has_battery=has_battery,
        mapping_mode=mapping,
    )


def parse_snes_header(path: Path) -> SNESHeaderInfo | None:
    """
    Parse the SNES ROM internal header from a ``.sfc`` or ``.smc`` file.

    Handles both LoROM and HiROM mapping, with or without 512-byte copier header.
    Returns ``None`` if parsing fails.
    """
    try:
        file_size = path.stat().st_size
        with open(path, "rb") as f:
            data = f.read(min(file_size, 0x10200))  # read enough for any header location
    except OSError as e:
        logger.debug(f"Failed to read SNES ROM '{path.name}': {e}")
        return None

    if len(data) < 0x8000:
        return None

    # Detect 512-byte copier header (file size % 1024 == 512)
    has_copier = (file_size % 1024) == 512
    offset = 0x200 if has_copier else 0

    # Try LoROM first, then HiROM
    for base in [_HEADER_OFFSETS_LOROM, _HEADER_OFFSETS_HIROM]:
        result = _try_parse_at(data, base + offset)
        if result is not None:
            result.has_copier_header = has_copier
            return result

    logger.debug(f"SNES header: no valid header found for '{path.name}'")
    return None
