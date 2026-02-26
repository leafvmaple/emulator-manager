"""Application entry point — wires services and launches the UI."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.config import get_config
from app.context import AppContext
from app.core.backup import BackupManager
from app.core.game_icon import GameIconProvider
from app.core.rename_engine import RenameEngine
from app.core.restore import RestoreManager
from app.core.scanner import Scanner
from app.core.scraper import Scraper
from app.core.sync import SyncManager
from app.core.rom_manager import RomManager
from app.data.rom_library import RomLibrary
from app.data.scrape_cache import ScrapeCache
from app.logger import setup_logger
from app.plugins.plugin_manager import PluginManager
from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme
from app.i18n import set_language


def create_context() -> AppContext:
    """Wire all services and return an AppContext."""
    config = get_config()

    # Logger
    setup_logger(config.data_dir / "logs")

    # Plugins
    plugin_manager = PluginManager()
    plugin_manager.discover_plugins()

    # Core services
    scanner = Scanner(plugin_manager, config)
    backup_manager = BackupManager(config)
    restore_manager = RestoreManager()
    sync_manager = SyncManager(config, backup_manager)
    icon_provider = GameIconProvider(config.data_dir / "icons")

    # Data
    rom_library = RomLibrary(config.data_dir)
    rom_library.load()
    scrape_cache = ScrapeCache(config.data_dir / "scrape_cache")

    # ROM services
    rename_engine = RenameEngine()
    rom_manager = RomManager(config, rom_library, plugin_manager, rename_engine)
    scraper = Scraper(config, scrape_cache)

    # Register scraper providers (only if credentials configured)
    scraper_config = config.get("scraper", {})
    if scraper_config.get("igdb_client_id"):
        from app.scrapers.igdb import IGDBProvider

        scraper.register_provider(
            IGDBProvider(
                client_id=scraper_config["igdb_client_id"],
                client_secret=scraper_config.get("igdb_client_secret", ""),
                config=config,
            )
        )
    if scraper_config.get("screenscraper_dev_id"):
        from app.scrapers.screenscraper import ScreenScraperProvider

        scraper.register_provider(
            ScreenScraperProvider(
                dev_id=scraper_config["screenscraper_dev_id"],
                dev_password=scraper_config.get("screenscraper_dev_password", ""),
                username=scraper_config.get("screenscraper_username", ""),
                password=scraper_config.get("screenscraper_password", ""),
                config=config,
            )
        )

    return AppContext(
        config=config,
        plugin_manager=plugin_manager,
        scanner=scanner,
        backup_manager=backup_manager,
        restore_manager=restore_manager,
        sync_manager=sync_manager,
        icon_provider=icon_provider,
        rom_library=rom_library,
        rom_manager=rom_manager,
        scraper=scraper,
        scrape_cache=scrape_cache,
        rename_engine=rename_engine,
    )


def main() -> int:
    """Application entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("Emulator Manager")
    app.setOrganizationName("EmulatorManager")

    # Apply theme
    apply_theme(dark=True)

    # Wire services
    ctx = create_context()

    # Initialize i18n from config
    set_language(ctx.config.get("language", "zh_CN"))

    # Create and show main window
    window = MainWindow(ctx)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
