"""Main window — FluentWindow with 3 sidebar pages."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QSize
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import FluentWindow, NavigationItemPosition

from app.i18n import t
from app.ui.pages.rom_management_page import RomManagementPage
from app.ui.pages.save_management_page import SaveManagementPage
from app.ui.pages.settings_page import SettingsPage

if TYPE_CHECKING:
    from app.context import AppContext


class MainWindow(FluentWindow):
    """Application main window with sidebar navigation."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self._ctx = ctx

        self.setWindowTitle("Emulator Manager")
        self.setMinimumSize(QSize(960, 640))
        self.resize(1200, 800)

        self._init_pages()

    def _init_pages(self) -> None:
        """Initialize navigation pages."""
        # ROM Management
        self._rom_page = RomManagementPage(self._ctx, self)
        self.addSubInterface(self._rom_page, FIF.GAME, t("nav.rom_management"))

        # Save Management
        self._save_page = SaveManagementPage(self._ctx, self)
        self.addSubInterface(self._save_page, FIF.SAVE, t("nav.save_management"))

        # Settings (bottom position)
        self._settings_page = SettingsPage(self._ctx, self)
        self.addSubInterface(
            self._settings_page,
            FIF.SETTING,
            t("nav.settings"),
            position=NavigationItemPosition.BOTTOM,
        )
