"""UI constants — shared strings, dimensions, platform mappings."""

from __future__ import annotations

# Platform display names (English → localization can override)
PLATFORM_NAMES: dict[str, str] = {
    "switch": "Nintendo Switch",
    "ps2": "PlayStation 2",
    "ps3": "PlayStation 3",
    "psp": "PlayStation Portable",
    "psvita": "PlayStation Vita",
    "nes": "NES",
    "snes": "SNES",
    "n64": "Nintendo 64",
    "gc": "GameCube",
    "wii": "Wii",
    "gb": "Game Boy",
    "gbc": "Game Boy Color",
    "gba": "Game Boy Advance",
    "nds": "Nintendo DS",
    "3ds": "Nintendo 3DS",
    "genesis": "Sega Genesis",
    "saturn": "Sega Saturn",
    "dreamcast": "Dreamcast",
    "xbox": "Xbox",
    "xbox360": "Xbox 360",
    "pc": "PC",
}

# Default rename templates
DEFAULT_TEMPLATES: dict[str, str] = {
    "simple": "{title_en|title_zh|filename}",
    "with_id": "{title_en|title_zh|filename} [{title_id}]",
    "full": "{title_zh|title_en|filename}{?version: [v{version}]}{?content_type: ({content_type})}",
    "organized": "[{platform}] {title_en|title_zh|filename}{?content_type: ({content_type})}",
}

# Card dimensions
CARD_MIN_WIDTH = 280
CARD_MAX_WIDTH = 400
CARD_ICON_SIZE = 48
TABLE_ROW_HEIGHT = 36

# Sidebar item keys
NAV_ROM_MANAGEMENT = "rom_management"
NAV_SAVE_MANAGEMENT = "save_management"
NAV_SETTINGS = "settings"
