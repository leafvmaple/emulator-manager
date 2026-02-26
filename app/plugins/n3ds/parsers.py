"""3DS ROM header parser — read product code, title ID, maker code from .3ds/.cia/.cxi files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

# ══════════════════════════════════════════════════════════════════════
# 3DS ROM Format Summary
# ══════════════════════════════════════════════════════════════════════
#
# .3ds  → NCSD container (cartridge dump)
#   - 0x000-0x0FF : RSA-2048 signature
#   - 0x100-0x103 : Magic "NCSD"
#   - 0x104-0x107 : Image size (media units, 1 MU = 0x200 bytes)
#   - 0x108-0x10F : Media ID (8 bytes LE)
#   - 0x120-0x15F : Partition table (8 entries × 8 bytes)
#     • Partition 0: main NCCH (game CXI)
#     • Entry format: 4-byte offset (MU) + 4-byte size (MU)
#
# .cia  → CTR Importable Archive (eShop / installable)
#   - CIA header:
#     0x00 : header size (4 bytes LE)
#     0x08 : cert chain size (4 bytes LE)
#     0x0C : ticket size (4 bytes LE)
#     0x10 : TMD size (4 bytes LE)
#     0x14 : meta size (4 bytes LE)
#     0x18 : content size (8 bytes LE)
#   - Sections are 64-byte aligned
#   - Content section contains NCCH
#
# .cxi  → NCCH directly (executable partition)
#
# NCCH Header (at partition/file offset):
#   - 0x000-0x0FF : RSA-2048 signature
#   - 0x100-0x103 : Magic "NCCH"
#   - 0x104-0x107 : Content size (media units)
#   - 0x108-0x10F : Partition ID (8 bytes LE)
#   - 0x110-0x111 : Maker code (2 bytes ASCII)
#   - 0x112-0x113 : Version (2 bytes LE)
#   - 0x118-0x11F : Program ID (8 bytes LE)
#   - 0x150-0x15F : Product code (16 bytes ASCII, e.g. "CTR-P-AXXX")
# ══════════════════════════════════════════════════════════════════════

_MEDIA_UNIT = 0x200  # 1 media unit = 512 bytes

# Product code last character → region
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
    "T": "Taiwan",
    "A": "Asia",
    "H": "Netherlands",
    "R": "Russia",
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
    "G9": "D3 Publisher",
    "GD": "Square Enix",
    "MV": "Marvelous Entertainment",
    "VZ": "Level-5",
    "WR": "Warner Bros.",
    "XS": "Aksys Games",
}

# TMD signature type → total signature header size (type + sig + padding)
_TMD_SIG_SIZES: dict[int, int] = {
    0x00010000: 0x240,  # RSA_4096_SHA1
    0x00010001: 0x140,  # RSA_2048_SHA1
    0x00010002: 0x80,   # ECDSA_SHA1
    0x00010003: 0x240,  # RSA_4096_SHA256
    0x00010004: 0x140,  # RSA_2048_SHA256
    0x00010005: 0x80,   # ECDSA_SHA256
}


@dataclass
class N3DSHeaderInfo:
    """Parsed 3DS ROM header data."""

    product_code: str = ""     # e.g. "CTR-P-AXXX"
    maker_code: str = ""       # 2-char maker code
    title_id: str = ""         # 16-hex-char title ID (e.g. "0004000000055D00")
    version: int = 0           # NCCH version field
    content_size: int = 0      # Content size in bytes
    is_ncsd: bool = False      # True for .3ds, False for .cia/.cxi

    @property
    def game_code(self) -> str:
        """Extract 4-char game code from product code (e.g. 'AXXX' from 'CTR-P-AXXX')."""
        if self.product_code and "-" in self.product_code:
            parts = self.product_code.split("-")
            if len(parts) >= 3:
                return parts[2][:4]
        if len(self.product_code) == 4:
            return self.product_code
        return self.product_code

    @property
    def region(self) -> str:
        """Determine region from last character of game code."""
        code = self.game_code
        if len(code) >= 4:
            return _REGION_MAP.get(code[3], "")
        return ""

    @property
    def publisher(self) -> str:
        return _MAKER_MAP.get(self.maker_code, "")

    @property
    def full_product_code(self) -> str:
        """Full product code, always with 'CTR-' prefix."""
        if self.product_code and self.product_code.startswith("CTR"):
            return self.product_code
        return ""

    @property
    def version_string(self) -> str:
        """Human-readable version from NCCH version field."""
        major = self.version >> 10
        minor = (self.version >> 4) & 0x3F
        patch = self.version & 0xF
        if major == 0 and minor == 0 and patch == 0:
            return "1.0"
        return f"{major}.{minor}.{patch}"


def _align64(offset: int) -> int:
    """Align offset up to 64-byte boundary."""
    return (offset + 63) & ~63


def _parse_ncch_at_raw(data: bytes) -> N3DSHeaderInfo | None:
    """
    Parse NCCH header from raw data.

    Expects at least 0x200 bytes where the NCCH signature starts at 0x000
    and the magic is at 0x100.
    """
    if len(data) < 0x200:
        return None

    if data[0x100:0x104] != b"NCCH":
        return None

    # Content size in media units
    content_size_mu = int.from_bytes(data[0x104:0x108], "little")
    content_size = content_size_mu * _MEDIA_UNIT

    # Partition ID (8 bytes LE → display as big-endian hex)
    title_id = data[0x108:0x110][::-1].hex().upper()

    # Maker code (2 bytes ASCII at 0x110)
    maker_code = data[0x110:0x112].decode("ascii", errors="replace").strip("\x00")

    # Version (2 bytes LE at 0x112)
    version = int.from_bytes(data[0x112:0x114], "little")

    # Product code (16 bytes ASCII at 0x150)
    product_code = (
        data[0x150:0x160]
        .decode("ascii", errors="replace")
        .strip("\x00")
        .strip()
    )

    return N3DSHeaderInfo(
        product_code=product_code,
        maker_code=maker_code,
        title_id=title_id,
        version=version,
        content_size=content_size,
    )


def parse_3ds_header(path: Path) -> N3DSHeaderInfo | None:
    """
    Parse a ``.3ds`` file (NCSD cartridge dump).

    Reads the NCSD header to locate partition 0, then parses its NCCH header.
    Returns ``None`` if the file is not a valid NCSD image.
    """
    try:
        with open(path, "rb") as f:
            header = f.read(0x200)
            if len(header) < 0x200:
                return None

            # Check NCSD magic at 0x100
            if header[0x100:0x104] != b"NCSD":
                return None

            # Partition 0 offset and size from table at 0x120
            part0_offset_mu = int.from_bytes(header[0x120:0x124], "little")
            part0_size_mu = int.from_bytes(header[0x124:0x128], "little")
            if part0_offset_mu == 0 or part0_size_mu == 0:
                return None

            part0_offset = part0_offset_mu * _MEDIA_UNIT

            # Read NCCH header at partition 0
            f.seek(part0_offset)
            ncch_data = f.read(0x200)
            if len(ncch_data) < 0x200:
                return None

    except OSError as e:
        logger.debug(f"Failed to read 3DS ROM '{path.name}': {e}")
        return None

    info = _parse_ncch_at_raw(ncch_data)
    if info:
        info.is_ncsd = True
        # Fall back to NCSD Media ID if NCCH didn't provide a title ID
        if not info.title_id or info.title_id == "0" * 16:
            media_id = header[0x108:0x110][::-1].hex().upper()
            info.title_id = media_id
    return info


def parse_cia_header(path: Path) -> N3DSHeaderInfo | None:
    """
    Parse a ``.cia`` file (CTR Importable Archive).

    Extracts title ID from the TMD and game metadata from the NCCH content.
    Returns ``None`` if the file is not a valid CIA.
    """
    try:
        with open(path, "rb") as f:
            cia_header = f.read(0x20)
            if len(cia_header) < 0x20:
                return None

            header_size = int.from_bytes(cia_header[0x00:0x04], "little")
            cert_size = int.from_bytes(cia_header[0x08:0x0C], "little")
            ticket_size = int.from_bytes(cia_header[0x0C:0x10], "little")
            tmd_size = int.from_bytes(cia_header[0x10:0x14], "little")

            # Sanity check
            if header_size == 0 or header_size > 0x10000:
                return None

            # Calculate section offsets (each section is 64-byte aligned)
            cert_offset = _align64(header_size)
            ticket_offset = cert_offset + _align64(cert_size)
            tmd_offset = ticket_offset + _align64(ticket_size)
            content_offset = tmd_offset + _align64(tmd_size)

            # Extract title ID from TMD
            title_id = ""
            if tmd_size >= 0x200:
                f.seek(tmd_offset)
                tmd_data = f.read(min(tmd_size, 0x200))
                if len(tmd_data) >= 0x1A0:
                    sig_type = int.from_bytes(tmd_data[0x00:0x04], "big")
                    sig_header_size = _TMD_SIG_SIZES.get(sig_type, 0x140)
                    tid_offset = sig_header_size + 0x4C
                    if len(tmd_data) >= tid_offset + 8:
                        title_id = tmd_data[tid_offset:tid_offset + 8].hex().upper()

            # Read NCCH from content section
            f.seek(content_offset)
            ncch_data = f.read(0x200)
            if len(ncch_data) < 0x200:
                return None

    except OSError as e:
        logger.debug(f"Failed to read CIA file '{path.name}': {e}")
        return None

    info = _parse_ncch_at_raw(ncch_data)
    if info:
        info.is_ncsd = False
        if title_id and title_id != "0" * 16:
            info.title_id = title_id
    elif title_id and title_id != "0" * 16:
        # Content is encrypted — we still have the TMD title ID
        info = N3DSHeaderInfo(title_id=title_id, is_ncsd=False)

    return info


def parse_cxi_header(path: Path) -> N3DSHeaderInfo | None:
    """
    Parse a ``.cxi`` / ``.app`` file (bare NCCH executable).

    Returns ``None`` if the file is not a valid NCCH.
    """
    try:
        with open(path, "rb") as f:
            data = f.read(0x200)
            if len(data) < 0x200:
                return None
    except OSError as e:
        logger.debug(f"Failed to read CXI file '{path.name}': {e}")
        return None

    return _parse_ncch_at_raw(data)


def parse_n3ds_rom(path: Path) -> N3DSHeaderInfo | None:
    """
    Auto-detect 3DS ROM format and parse header.

    Dispatch order by extension:
      ``.3ds`` → NCSD,  ``.cia`` → CIA,  ``.cxi`` / ``.app`` → NCCH
    Unknown extensions are tried in NCSD → CIA → NCCH order.
    """
    suffix = path.suffix.lower()

    if suffix == ".3ds":
        return parse_3ds_header(path)
    if suffix == ".cia":
        return parse_cia_header(path)
    if suffix in (".cxi", ".app"):
        return parse_cxi_header(path)

    # Unknown extension — try each format
    for parser in (parse_3ds_header, parse_cia_header, parse_cxi_header):
        result = parser(path)
        if result:
            return result
    return None
