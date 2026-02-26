"""Import a No-Intro DAT file and generate a games.json for a platform plugin.

Usage:
    python -m tools.import_dat <platform> <dat_file>

Examples:
    python -m tools.import_dat gba "dat/Nintendo - Game Boy Advance (...).dat"
    python -m tools.import_dat nds "dat/Nintendo - Nintendo DS (...).dat"
    python -m tools.import_dat nes "dat/Nintendo - Nintendo Entertainment System (...).dat"
    python -m tools.import_dat snes "dat/Nintendo - Super Nintendo Entertainment System (...).dat"

The generated ``games.json`` is placed under ``app/plugins/<platform>/``.

For platforms with serial codes (GBA, NDS), keys are serial codes::

    {"AXVE": {"name": "Pokemon - Ruby Version", "crc32": ["AABBCCDD"]}}

For platforms without serial codes (NES, SNES), keys are CRC32 hashes::

    {"3577AB04": {"name": "'89 Dennou Kyuusei Uranai", "crc32": ["3577AB04"]}}
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def clean_game_name(raw_name: str) -> str:
    """Strip region / language / revision tags from a No-Intro name.

    "Pocket Monsters - Ruby (Japan)" → "Pocket Monsters - Ruby"
    "007 - Everything or Nothing (USA, Europe) (En,Fr,De)" → "007 - Everything or Nothing"
    """
    cleaned = re.sub(r"\s*\(.*$", "", raw_name).strip()
    return cleaned or raw_name


def parse_dat(dat_path: Path) -> tuple[dict, list[str]]:
    """Parse a No-Intro DAT XML and return ``(entries, unique_headers)``.

    *entries*: ``{serial: {name, crc32: [...]}}`` for serial-keyed DATs,
              ``{CRC32: name}`` for CRC-keyed DATs (NES, SNES …).
    *unique_headers*: deduplicated list of ROM header hex strings found in
                      the DAT (e.g. iNES headers from NES Headered DATs).
    """
    tree = ET.parse(dat_path)
    root = tree.getroot()

    # First pass: count serials to decide key mode
    total_roms = 0
    serial_count = 0
    for game_el in root.iter("game"):
        if (game_el.get("name", "")).startswith("[BIOS]"):
            continue
        for rom_el in game_el.iter("rom"):
            total_roms += 1
            serial = (rom_el.get("serial") or "").strip()
            if serial and not serial.startswith("!") and serial.lower() != "n/a":
                serial_count += 1

    # Use serial as key if majority (>50%) have valid serials
    use_serial = serial_count > total_roms * 0.5

    # Second pass: build entries and collect unique headers
    entries: dict = {}
    seen_headers: set[str] = set()

    for game_el in root.iter("game"):
        game_name = game_el.get("name", "")
        if not game_name or game_name.startswith("[BIOS]"):
            continue

        for rom_el in game_el.iter("rom"):
            serial = (rom_el.get("serial") or "").strip()
            crc32 = (rom_el.get("crc") or "").strip().upper()
            header = (rom_el.get("header") or "").strip()
            cleaned = clean_game_name(game_name)

            # Collect unique headers
            if header:
                seen_headers.add(header.replace(" ", ""))

            valid_serial = serial and not serial.startswith("!") and serial.lower() != "n/a"

            if use_serial and valid_serial:
                key = serial.upper()
                if key not in entries:
                    entries[key] = {"name": cleaned, "crc32": [crc32] if crc32 else []}
                elif crc32:
                    crc_list = entries[key]["crc32"]
                    assert isinstance(crc_list, list)
                    if crc32 not in crc_list:
                        crc_list.append(crc32)
            elif not use_serial and crc32:
                # CRC → name (simple string value)
                if crc32 not in entries:
                    entries[crc32] = cleaned

    return entries, sorted(seen_headers)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1

    platform = sys.argv[1].lower()
    dat_path = Path(sys.argv[2])

    if not dat_path.exists():
        print(f"Error: DAT file not found: {dat_path}")
        return 1

    plugin_dir = Path(__file__).resolve().parent.parent / "app" / "plugins" / platform
    if not plugin_dir.is_dir():
        print(f"Error: plugin directory not found: {plugin_dir}")
        print(f"  Available: {[p.name for p in plugin_dir.parent.iterdir() if p.is_dir() and not p.name.startswith('_')]}")
        return 1

    print(f"Parsing {dat_path.name} ...")
    entries, unique_headers = parse_dat(dat_path)
    print(f"  Found {len(entries)} games")

    out_path = plugin_dir / "games.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    print(f"  Written to {out_path}")

    if unique_headers:
        hdr_path = plugin_dir / "header.json"
        with open(hdr_path, "w", encoding="utf-8") as f:
            json.dump(unique_headers, f, indent=2)
        print(f"  Written {len(unique_headers)} unique headers to {hdr_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
