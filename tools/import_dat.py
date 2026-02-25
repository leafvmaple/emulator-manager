"""Import a No-Intro DAT file and generate a games.json for a platform plugin.

Usage:
    python -m tools.import_dat <platform> <dat_file>

Examples:
    python -m tools.import_dat gba dat/Nintendo\ -\ Game\ Boy\ Advance\ (...).dat
    python -m tools.import_dat nds dat/Nintendo\ -\ Nintendo\ DS\ (...).dat

The generated ``games.json`` is placed under ``app/plugins/<platform>/``
and maps 4-character ROM serial codes to canonical game names::

    {
      "AXVE": "Pokemon - Ruby Version",
      "AXVJ": "Pocket Monsters - Ruby",
      ...
    }
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


def parse_dat(dat_path: Path) -> dict[str, dict[str, str | list[str]]]:
    """Parse a No-Intro DAT XML and return {serial: {name, crc32: [...]}}."""
    entries: dict[str, dict[str, str | list[str]]] = {}

    tree = ET.parse(dat_path)
    root = tree.getroot()

    for game_el in root.iter("game"):
        game_name = game_el.get("name", "")
        if not game_name or game_name.startswith("[BIOS]"):
            continue

        for rom_el in game_el.iter("rom"):
            serial = (rom_el.get("serial") or "").strip()
            if not serial or serial.startswith("!") or serial.lower() == "n/a":
                continue

            crc32 = (rom_el.get("crc") or "").strip().upper()
            cleaned = clean_game_name(game_name)
            key = serial.upper()
            if key not in entries:
                entries[key] = {"name": cleaned, "crc32": [crc32] if crc32 else []}
            elif crc32:
                crc_list = entries[key]["crc32"]
                assert isinstance(crc_list, list)
                if crc32 not in crc_list:
                    crc_list.append(crc32)

    return entries


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
    entries = parse_dat(dat_path)
    print(f"  Found {len(entries)} games with serial codes")

    out_path = plugin_dir / "games.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    print(f"  Written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
