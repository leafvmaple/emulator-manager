"""Save Management page — container with SegmentedWidget tabs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget, QStackedWidget
from qfluentwidgets import SegmentedWidget, ScrollArea

from app.i18n import t

if TYPE_CHECKING:
    from app.context import AppContext


class SaveManagementPage(ScrollArea):
    """Save Management container page with segmented navigation."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self.setObjectName("saveManagementPage")
        self.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 16, 24, 0)
        layout.setSpacing(12)

        self._pivot = SegmentedWidget(self)
        layout.addWidget(self._pivot, 0, Qt.AlignLeft)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        self.setWidget(container)

        self._init_tabs()

    def _init_tabs(self) -> None:
        """Initialize tab pages."""
        from app.ui.tabs.save_library_tab import SaveLibraryTab
        from app.ui.tabs.save_backup_tab import SaveBackupTab
        from app.ui.tabs.save_restore_tab import SaveRestoreTab
        from app.ui.tabs.save_sync_tab import SaveSyncTab

        tabs = [
            ("save_library", t("tab.save_library"), SaveLibraryTab(self._ctx, self)),
            ("save_backup", t("tab.save_backup"), SaveBackupTab(self._ctx, self)),
            ("save_restore", t("tab.save_restore"), SaveRestoreTab(self._ctx, self)),
            ("save_sync", t("tab.save_sync"), SaveSyncTab(self._ctx, self)),
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
