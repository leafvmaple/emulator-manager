"""Switch ROM format parsers — pure Python NSP (PFS0) and XCI (HFS0/XCI) parsing."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from loguru import logger


@dataclass
class NACPData:
    """Nintendo Application Control Property data."""

    titles: dict[str, str]  # lang_code -> title
    publisher: str = ""
    version: str = ""


@dataclass
class CNMTData:
    """Content Meta data."""

    title_id: str = ""
    version_raw: int = 0
    content_type: int = 0  # 0x80=Application, 0x81=Patch, 0x82=AddOnContent
    required_version: int = 0

    @property
    def version_string(self) -> str:
        major = (self.version_raw >> 26) & 0x3F
        minor = (self.version_raw >> 20) & 0x3F
        patch = (self.version_raw >> 16) & 0xF
        return f"{major}.{minor}.{patch}"

    @property
    def content_type_name(self) -> str:
        return {0x80: "Application", 0x81: "Patch", 0x82: "AddOnContent"}.get(
            self.content_type, f"Unknown({self.content_type:#x})"
        )


# NACP language indices
_NACP_LANGUAGES = [
    "ja", "en_US", "fr", "de", "it", "es", "zh_CN", "ko",
    "nl", "pt", "ru", "zh_TW", "en_GB", "fr_CA", "es_419",
    "zh_Hans", "zh_Hant",
]


def parse_pfs0(data: bytes) -> list[tuple[str, bytes]]:
    """Parse a PFS0 (Partition FS) container, returning (filename, content) pairs."""
    if len(data) < 16:
        return []

    magic = data[:4]
    if magic != b"PFS0":
        raise ValueError(f"Not a PFS0 container: {magic!r}")

    num_files = struct.unpack_from("<I", data, 4)[0]
    string_table_size = struct.unpack_from("<I", data, 8)[0]

    file_entries_offset = 16
    file_entry_size = 24  # offset(8) + size(8) + string_offset(4) + padding(4)
    string_table_offset = file_entries_offset + num_files * file_entry_size
    data_offset = string_table_offset + string_table_size

    entries: list[tuple[str, bytes]] = []
    for i in range(num_files):
        entry_offset = file_entries_offset + i * file_entry_size
        file_data_offset, file_size, name_offset = struct.unpack_from(
            "<QQI", data, entry_offset
        )

        # Read null-terminated filename
        name_start = string_table_offset + name_offset
        name_end = data.index(b"\x00", name_start)
        filename = data[name_start:name_end].decode("utf-8", errors="replace")

        content_start = data_offset + file_data_offset
        content = data[content_start : content_start + file_size]
        entries.append((filename, content))

    return entries


def parse_nacp(data: bytes) -> NACPData:
    """Parse NACP (control.nacp) for titles, publisher, version."""
    titles: dict[str, str] = {}
    publisher = ""

    # Each title entry is 0x300 bytes (0x200 name + 0x100 publisher)
    for i, lang in enumerate(_NACP_LANGUAGES):
        if i >= 16:
            break
        offset = i * 0x300
        if offset + 0x300 > len(data):
            break

        name_raw = data[offset : offset + 0x200]
        pub_raw = data[offset + 0x200 : offset + 0x300]

        name = name_raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()
        pub = pub_raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()

        if name:
            titles[lang] = name
        if pub and not publisher:
            publisher = pub

    # Version string at offset 0x3060
    version = ""
    if len(data) >= 0x3070:
        ver_raw = data[0x3060:0x3070]
        version = ver_raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()

    return NACPData(titles=titles, publisher=publisher, version=version)


def parse_cnmt(data: bytes) -> CNMTData:
    """Parse CNMT (content meta) for title ID and version."""
    if len(data) < 0x20:
        return CNMTData()

    title_id_raw = struct.unpack_from("<Q", data, 0)[0]
    version = struct.unpack_from("<I", data, 8)[0]
    content_type = data[0x0C]

    return CNMTData(
        title_id=f"{title_id_raw:016X}",
        version_raw=version,
        content_type=content_type,
    )


def _read_nca_header_title_id(f: BinaryIO, nca_offset: int) -> str | None:
    """Try to read title ID from NCA header (unencrypted portion)."""
    try:
        f.seek(nca_offset)
        header = f.read(0x400)
        if len(header) < 0x400:
            return None

        # NCA magic at offset 0x200
        if header[0x200:0x204] != b"NCA3" and header[0x200:0x204] != b"NCA2":
            return None

        # Title ID at offset 0x210 in NCA header
        title_id = struct.unpack_from("<Q", header, 0x210)[0]
        return f"{title_id:016X}"
    except Exception:
        return None


def classify_title_id(title_id: str) -> str:
    """Classify a Switch title ID: base=000, update=800, DLC=001-7FF."""
    if len(title_id) < 4:
        return "unknown"
    suffix = int(title_id[-3:], 16)
    if suffix == 0x000:
        return "base"
    elif suffix == 0x800:
        return "update"
    elif 0x001 <= suffix <= 0x7FF:
        return "dlc"
    return "unknown"


def parse_nsp(path: Path) -> dict:
    """Parse an NSP file to extract metadata."""
    result: dict = {"format": "nsp", "title_id": None, "nacp": None, "cnmt": None}

    with open(path, "rb") as f:
        header = f.read(16)
        if header[:4] != b"PFS0":
            logger.warning(f"Not a valid NSP: {path.name}")
            return result

        num_files = struct.unpack_from("<I", header, 4)[0]
        string_table_size = struct.unpack_from("<I", header, 8)[0]

        file_entry_size = 24
        entries_data = f.read(num_files * file_entry_size)
        string_table = f.read(string_table_size)
        data_start = 16 + num_files * file_entry_size + string_table_size

        for i in range(num_files):
            entry = entries_data[i * file_entry_size : (i + 1) * file_entry_size]
            offset, size, name_off = struct.unpack_from("<QQI", entry, 0)

            name_end = string_table.index(b"\x00", name_off)
            filename = string_table[name_off:name_end].decode("utf-8", errors="replace")

            # Look for CNMT NCA to get title ID
            if filename.endswith(".cnmt.nca"):
                title_id = _read_nca_header_title_id(f, data_start + offset)
                if title_id:
                    result["title_id"] = title_id

            # We can't easily parse encrypted NCAs for NACP
            # so we rely on filename patterns and CNMT

        # Try to extract title ID from filename if not found
        if not result["title_id"]:
            import re
            m = re.search(r"\[([0-9A-Fa-f]{16})\]", path.stem)
            if m:
                result["title_id"] = m.group(1).upper()

    return result


def parse_xci(path: Path) -> dict:
    """Parse an XCI file to extract metadata."""
    result: dict = {"format": "xci", "title_id": None, "nacp": None, "cnmt": None}

    with open(path, "rb") as f:
        # XCI header
        header = f.read(0x200)
        if len(header) < 0x200:
            return result

        # Magic "HEAD" at offset 0x100
        if header[0x100:0x104] != b"HEAD":
            # Try to extract from filename
            import re
            m = re.search(r"\[([0-9A-Fa-f]{16})\]", path.stem)
            if m:
                result["title_id"] = m.group(1).upper()
            return result

        # HFS0 partition offset at 0x130
        hfs0_offset = struct.unpack_from("<Q", header, 0x130)[0]

        try:
            f.seek(hfs0_offset)
            hfs0_header = f.read(16)
            if hfs0_header[:4] == b"HFS0":
                # Read root HFS0 to find secure partition
                num_files = struct.unpack_from("<I", hfs0_header, 4)[0]
                # Each HFS0 entry: offset(8), size(8), string_offset(4), hashed_size(4), padding(8), hash(32)
                hfs0_entry_size = 0x40
                hfs0_entries = f.read(num_files * hfs0_entry_size)
                hfs0_string_table_size = struct.unpack_from("<I", hfs0_header, 8)[0]
                hfs0_string_table = f.read(hfs0_string_table_size)

                for i in range(num_files):
                    entry = hfs0_entries[i * hfs0_entry_size : (i + 1) * hfs0_entry_size]
                    _, _, name_off = struct.unpack_from("<QQI", entry, 0)
                    name_end = hfs0_string_table.index(b"\x00", name_off)
                    name = hfs0_string_table[name_off:name_end].decode("utf-8", errors="replace")

                    if name == "secure":
                        # Found secure partition — contains NCAs
                        pass  # Would need further parsing of encrypted content
        except Exception as e:
            logger.debug(f"XCI parsing incomplete for {path.name}: {e}")

    # Fallback: extract from filename
    if not result["title_id"]:
        import re
        m = re.search(r"\[([0-9A-Fa-f]{16})\]", path.stem)
        if m:
            result["title_id"] = m.group(1).upper()

    return result
