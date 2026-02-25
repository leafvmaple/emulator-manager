"""Application context — service container for dependency injection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Config
    from app.core.backup import BackupManager
    from app.core.game_icon import GameIconProvider
    from app.core.rename_engine import RenameEngine
    from app.core.restore import RestoreManager
    from app.core.rom_manager import RomManager
    from app.core.scanner import Scanner
    from app.core.scraper import Scraper
    from app.core.sync import SyncManager
    from app.data.rom_library import RomLibrary
    from app.data.scrape_cache import ScrapeCache
    from app.plugins.plugin_manager import PluginManager


@dataclass
class AppContext:
    """
    Central service container.

    All pages/tabs receive this at construction time, replacing the
    fragile set_*() two-phase injection pattern.
    """

    config: Config
    plugin_manager: PluginManager

    # Save management services
    scanner: Scanner
    backup_manager: BackupManager
    restore_manager: RestoreManager
    sync_manager: SyncManager
    icon_provider: GameIconProvider

    # ROM management services
    rom_library: RomLibrary
    rom_manager: RomManager
    scraper: Scraper
    scrape_cache: ScrapeCache
    rename_engine: RenameEngine
