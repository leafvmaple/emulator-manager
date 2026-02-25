"""Register a custom / fan-translated ROM into a platform's games_custom.json.

Since fan-translated ROMs share the same serial as the original game,
the only way to distinguish them is by CRC32.  This tool computes the
CRC32 of a ROM file and records it with a custom display name and
region override.

Usage:
    python -m tools.add_custom_rom <platform> <rom_file> <name> [--region REGION]

Examples:
    python -m tools.add_custom_rom gba "口袋妖怪-红宝石(汉化).gba" "口袋妖怪 - 红宝石" --region China
    python -m tools.add_custom_rom nds "心金汉化版.nds" "口袋妖怪 - 心金" --region China

The result is written to ``app/plugins/<platform>/games_custom.json``.
Multiple invocations append to the same file.
"""

from __future__ import annotations

import argparse
import json
import sys
import zlib
from pathlib import Path


def compute_crc32(path: Path) -> str:
    """Compute CRC32 of a file, returned as 8-char uppercase hex."""
    crc = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            crc = zlib.crc32(chunk, crc)
    return f"{crc & 0xFFFFFFFF:08X}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register a custom / fan-translated ROM.",
    )
    parser.add_argument("platform", help="Plugin name (e.g. gba, nds)")
    parser.add_argument("rom_file", help="Path to the ROM file")
    parser.add_argument("name", help="Display name for this ROM")
    parser.add_argument(
        "--region",
        default="China",
        help="Region override (default: China)",
    )
    args = parser.parse_args()

    rom_path = Path(args.rom_file)
    if not rom_path.exists():
        print(f"Error: ROM file not found: {rom_path}")
        return 1

    plugin_dir = Path(__file__).resolve().parent.parent / "app" / "plugins" / args.platform
    if not plugin_dir.is_dir():
        print(f"Error: plugin directory not found: {plugin_dir}")
        return 1

    # Compute CRC32
    print(f"Computing CRC32 of {rom_path.name} ({rom_path.stat().st_size / 1048576:.1f} MB) ...")
    crc = compute_crc32(rom_path)
    print(f"  CRC32: {crc}")

    # Load existing custom DB
    custom_path = plugin_dir / "games_custom.json"
    db: dict[str, dict[str, str]] = {}
    if custom_path.exists():
        with open(custom_path, encoding="utf-8") as f:
            db = json.load(f)

    # Add / update entry
    db[crc] = {"name": args.name, "region": args.region}

    # Save
    with open(custom_path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    print(f"  Added: {crc} → {args.name} (region={args.region})")
    print(f"  Saved to {custom_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
