"""ROM Management page — container with SegmentedWidget tabs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget, QStackedWidget
from qfluentwidgets import SegmentedWidget, ScrollArea

from app.i18n import t

if TYPE_CHECKING:
    from app.context import AppContext


class RomManagementPage(ScrollArea):
    """ROM Management container page with segmented navigation."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self.setObjectName("romManagementPage")
        self.setWidgetResizable(True)

        # Container
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 16, 24, 0)
        layout.setSpacing(12)

        # Segmented navigation
        self._pivot = SegmentedWidget(self)
        layout.addWidget(self._pivot, 0, Qt.AlignLeft)

        # Stacked widget for tab content
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        self.setWidget(container)

        self._init_tabs()

    def _init_tabs(self) -> None:
        """Initialize tab pages."""
        from app.ui.tabs.rom_library_tab import RomLibraryTab
        from app.ui.tabs.rom_scraper_tab import RomScraperTab
        from app.ui.tabs.rom_rename_tab import RomRenameTab
        from app.ui.tabs.rom_tools_tab import RomToolsTab

        tabs = [
            ("rom_library", t("tab.rom_library"), RomLibraryTab(self._ctx, self)),
            ("rom_scraper", t("tab.rom_scraper"), RomScraperTab(self._ctx, self)),
            ("rom_rename", t("tab.rom_rename"), RomRenameTab(self._ctx, self)),
            ("rom_tools", t("tab.rom_tools"), RomToolsTab(self._ctx, self)),
        ]

        for key, label, widget in tabs:
            widget.setObjectName(key)
            self._stack.addWidget(widget)
            self._pivot.addItem(routeKey=key, text=label)

        # Connect signal — idiomatic QFluentWidgets pattern
        self._pivot.currentItemChanged.connect(
            lambda k: self._stack.setCurrentWidget(self.findChild(QWidget, k))
        )

        # Select first tab
        self._stack.setCurrentWidget(tabs[0][2])
        self._pivot.setCurrentItem(tabs[0][0])
