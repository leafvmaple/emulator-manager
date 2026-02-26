"""Save Backup tab — create versioned backups of game saves."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QTableWidgetItem,
    QHeaderView,
)
from qfluentwidgets import (
    PrimaryPushButton,
    PushButton,
    TableWidget,
    ProgressBar,
    CheckBox,
)
from qfluentwidgets import FluentIcon as FIF

from app.ui.utils import show_success, show_error
from app.utils import format_size
from app.i18n import t

if TYPE_CHECKING:
    from app.context import AppContext
    from app.models.game_save import GameSave


class BackupWorker(QThread):
    """Background worker for creating backups."""

    progress = Signal(int, int)
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, ctx: AppContext, saves: list, parent=None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._saves = saves

    def run(self) -> None:
        count = 0
        total = len(self._saves)
        for i, save in enumerate(self._saves):
            try:
                if self._ctx.backup_manager:
                    self._ctx.backup_manager.create_backup(save)
                    count += 1
            except Exception as e:
                self.error.emit(f"{save.game_name}: {e}")
            self.progress.emit(i + 1, total)
        self.finished.emit(count)


class SaveBackupTab(QWidget):
    """Save backup tab — select and backup game saves."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._saves: list[GameSave] = []
        self._worker: BackupWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()

        self._select_all = CheckBox(t("backup.select_all"), self)
        self._select_all.stateChanged.connect(self._on_select_all)
        toolbar.addWidget(self._select_all)

        toolbar.addStretch()

        self._refresh_btn = PushButton(FIF.SYNC, t("backup.refresh"), self)
        self._refresh_btn.clicked.connect(self._on_refresh)
        toolbar.addWidget(self._refresh_btn)

        self._backup_btn = PrimaryPushButton(FIF.SAVE, t("backup.backup_selected"), self)
        self._backup_btn.clicked.connect(self._on_backup)
        toolbar.addWidget(self._backup_btn)

        layout.addLayout(toolbar)

        # Progress
        self._progress = ProgressBar(self)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Table with checkboxes
        self._table = TableWidget(self)
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            [t("backup.col_select"), t("backup.col_name"), t("backup.col_emulator"), t("backup.col_size"), t("backup.col_last_backup")]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._table.setColumnWidth(0, 50)
        self._table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

    def _on_refresh(self) -> None:
        """Refresh save list from scanner in a background thread."""
        if not self._ctx.scanner:
            return
        from app.ui.tabs.save_library_tab import SaveScanWorker

        self._refresh_worker = SaveScanWorker(self._ctx, self)
        self._refresh_worker.finished.connect(self._on_refresh_finished)
        self._refresh_worker.start()

    def _on_refresh_finished(self, saves: list) -> None:
        """Handle refresh completion."""
        self._saves = saves
        self._refresh_table()
        self._refresh_worker = None

    def _refresh_table(self) -> None:
        self._table.setRowCount(0)
        for save in self._saves:
            row = self._table.rowCount()
            self._table.insertRow(row)

            cb = QTableWidgetItem()
            cb.setCheckState(0)  # Unchecked
            self._table.setItem(row, 0, cb)
            self._table.setItem(row, 1, QTableWidgetItem(save.game_name))
            self._table.setItem(row, 2, QTableWidgetItem(save.emulator))
            self._table.setItem(row, 3, QTableWidgetItem(format_size(save.total_size)))

            # Last backup time
            last_backup = t("backup.never")
            if self._ctx.backup_manager:
                backups = self._ctx.backup_manager.list_backups(save.emulator, save.game_id)
                if backups:
                    last_backup = backups[0].created_at.strftime("%Y-%m-%d %H:%M")
            self._table.setItem(row, 4, QTableWidgetItem(last_backup))

    def _on_select_all(self, state: int) -> None:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item:
                item.setCheckState(2 if state else 0)

    def _on_backup(self) -> None:
        """Create backups for selected saves."""
        selected: list[GameSave] = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.checkState() == 2:  # Checked
                if row < len(self._saves):
                    selected.append(self._saves[row])

        if not selected:
            show_error(self, t("backup.err_none_selected"), t("backup.err_none_selected_msg"))
            return

        self._backup_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, len(selected))

        self._worker = BackupWorker(self._ctx, selected, self)
        self._worker.progress.connect(lambda cur, _: self._progress.setValue(cur))
        self._worker.finished.connect(self._on_backup_finished)
        self._worker.start()

    def _on_backup_finished(self, count: int) -> None:
        self._progress.setVisible(False)
        self._backup_btn.setEnabled(True)
        show_success(self, t("backup.success"), t("backup.success_msg", count=count))
        self._on_refresh()
