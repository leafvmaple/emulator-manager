"""Import No-Intro DAT files and generate games.json for platform plugins.

Usage:
    python -m tools.import_dat                     # auto-scan dat/ directory
    python -m tools.import_dat <platform> <dat>    # import a single DAT file

Examples:
    python -m tools.import_dat gba "dat/Nintendo - Game Boy Advance (...).dat"
    python -m tools.import_dat nds "dat/Nintendo - Nintendo DS (...).dat"
    python -m tools.import_dat nes "dat/Nintendo - Nintendo Entertainment System (...).dat"
    python -m tools.import_dat snes "dat/Nintendo - Super Nintendo Entertainment System (...).dat"

The generated ``games.json`` is placed under ``app/plugins/<platform>/``.

Keys are CRC32 hashes::

    {"3577AB04": {"name": "'89 Dennou Kyuusei Uranai", "id": 5678}}
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def clean_game_name(raw_name: str) -> str:
    """Strip region / language / revision tags from a No-Intro name.

    "Pocket Monsters - Ruby (Japan)" → "Pocket Monsters - Ruby"
    "007 - Everything or Nothing (USA, Europe) (En,Fr,De)" → "007 - Everything or Nothing"
    """
    cleaned = re.sub(r"\s*\(.*$", "", raw_name).strip()
    return cleaned or raw_name


def parse_dat(dat_path: Path) -> tuple[dict[str, Any], list[str]]:
    """Parse a No-Intro DAT XML and return ``(entries, unique_headers)``.

    *entries*: ``{CRC32: {name, id}}`` — all plugins use CRC-based lookup.
    *unique_headers*: deduplicated list of ROM header hex strings found in
                      the DAT (e.g. iNES headers from NES Headered DATs).
    """
    tree = ET.parse(dat_path)
    root = tree.getroot()

    entries: dict[str, Any] = {}
    seen_headers: set[str] = set()

    for game_el in root.iter("game"):
        game_name = game_el.get("name", "")
        if not game_name or game_name.startswith("[BIOS]"):
            continue

        # Extract game id — skip games with non-numeric id
        raw_id = (game_el.get("id") or "").strip()
        if not raw_id.isdigit():
            continue
        dat_id = int(raw_id)

        for rom_el in game_el.iter("rom"):
            crc32 = (rom_el.get("crc") or "").strip().upper()
            header = (rom_el.get("header") or "").strip()
            cleaned = clean_game_name(game_name)

            # Collect unique headers
            if header:
                seen_headers.add(header.replace(" ", ""))

            if crc32 and crc32 not in entries:
                entries[crc32] = {"name": cleaned, "id": dat_id}

    return entries, sorted(seen_headers)


# DAT filename keyword → platform plugin mapping
# Order matters: more specific keywords must come first
_DAT_PLATFORM_MAP: list[tuple[str, str]] = [
    ("Super Nintendo Entertainment System", "snes"),
    ("Nintendo Entertainment System", "nes"),
    ("Game Boy Advance", "gba"),
    ("Nintendo 3DS", "n3ds"),
    ("Nintendo DS", "nds"),
]


def _guess_platform(dat_name: str) -> str | None:
    """Guess platform from DAT filename using keyword matching."""
    for keyword, platform in _DAT_PLATFORM_MAP:
        if keyword in dat_name:
            return platform
    return None


def _import_one(platform: str, dat_path: Path) -> bool:
    """Import a single DAT file for a given platform. Returns True on success."""
    plugin_dir = Path(__file__).resolve().parent.parent / "app" / "plugins" / platform
    if not plugin_dir.is_dir():
        print(f"  Error: plugin directory not found: {plugin_dir}")
        return False

    print(f"  Parsing {dat_path.name} → {platform} ...")
    entries, unique_headers = parse_dat(dat_path)
    print(f"    Found {len(entries)} games")

    out_path = plugin_dir / "games.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    print(f"    Written to {out_path}")

    if unique_headers:
        hdr_path = plugin_dir / "header.json"
        with open(hdr_path, "w", encoding="utf-8") as f:
            json.dump(unique_headers, f, indent=2)
        print(f"    Written {len(unique_headers)} unique headers to {hdr_path}")

    return True


def main() -> int:
    # Mode 1: no args → auto-scan dat/ directory
    if len(sys.argv) == 1:
        dat_dir = Path(__file__).resolve().parent.parent / "dat"
        if not dat_dir.is_dir():
            print(f"Error: dat directory not found: {dat_dir}")
            return 1

        dat_files = sorted(dat_dir.glob("*.dat"))
        if not dat_files:
            print(f"No .dat files found in {dat_dir}")
            return 1

        print(f"Found {len(dat_files)} DAT file(s) in {dat_dir}\n")
        success = 0
        skipped: list[str] = []
        for dat_path in dat_files:
            platform = _guess_platform(dat_path.stem)
            if platform is None:
                skipped.append(dat_path.name)
                continue
            if _import_one(platform, dat_path):
                success += 1
            print()

        if skipped:
            print(f"Skipped {len(skipped)} unrecognized DAT file(s):")
            for name in skipped:
                print(f"  - {name}")
        print(f"\nDone: {success} platform(s) imported.")
        return 0

    # Mode 2: explicit <platform> <dat_file>
    if len(sys.argv) != 3:
        print(__doc__)
        return 1

    platform = sys.argv[1].lower()
    dat_path = Path(sys.argv[2])

    if not dat_path.exists():
        print(f"Error: DAT file not found: {dat_path}")
        return 1

    return 0 if _import_one(platform, dat_path) else 1


if __name__ == "__main__":
    sys.exit(main())
