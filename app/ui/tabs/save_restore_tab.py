"""Save Restore tab — restore saves from backups with preview."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QTableWidgetItem,
    QHeaderView,
    QSplitter,
)
from qfluentwidgets import (
    PrimaryPushButton,
    PushButton,
    ComboBox,
    TableWidget,
    MessageBox,
)
from qfluentwidgets import FluentIcon as FIF

from app.ui.utils import show_success, show_error, show_warning
from app.utils import format_size
from app.i18n import t

if TYPE_CHECKING:
    from app.context import AppContext
    from app.models.backup_record import BackupRecord


class SaveRestoreTab(QWidget):
    """Save restore tab — browse and restore from backups."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._backups: list[BackupRecord] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()

        self._emu_combo = ComboBox(self)
        self._emu_combo.addItem(t("restore.all_emulators"))
        self._emu_combo.currentIndexChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._emu_combo)

        toolbar.addStretch()

        self._refresh_btn = PushButton(FIF.SYNC, t("restore.refresh"), self)
        self._refresh_btn.clicked.connect(self._on_refresh)
        toolbar.addWidget(self._refresh_btn)

        self._restore_btn = PrimaryPushButton(FIF.DOWNLOAD, t("restore.restore"), self)
        self._restore_btn.clicked.connect(self._on_restore)
        toolbar.addWidget(self._restore_btn)

        layout.addLayout(toolbar)

        # Backups table
        self._table = TableWidget(self)
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            [t("restore.col_name"), t("restore.col_emulator"), t("restore.col_version"), t("restore.col_size"), t("restore.col_created"), t("restore.col_source")]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

    def _on_refresh(self) -> None:
        """Refresh backup list."""
        if not self._ctx.backup_manager:
            return

        self._backups.clear()
        all_backups = self._ctx.backup_manager.list_all_backups()

        emus = set()
        for emu, games in all_backups.items():
            emus.add(emu)
            for game_id, records in games.items():
                self._backups.extend(records)

        # Update filter
        self._emu_combo.clear()
        self._emu_combo.addItem(t("restore.all_emulators"))
        for emu in sorted(emus):
            self._emu_combo.addItem(emu)

        self._refresh_table()

    def _refresh_table(self, emu_filter: str = "") -> None:
        self._table.setRowCount(0)
        for record in self._backups:
            if emu_filter and record.emulator != emu_filter:
                continue

            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(record.game_name))
            self._table.setItem(row, 1, QTableWidgetItem(record.emulator))
            self._table.setItem(row, 2, QTableWidgetItem(f"v{record.version}"))
            self._table.setItem(row, 3, QTableWidgetItem(format_size(record.size)))
            self._table.setItem(
                row, 4,
                QTableWidgetItem(record.created_at.strftime("%Y-%m-%d %H:%M")),
            )
            self._table.setItem(row, 5, QTableWidgetItem(record.source_machine))

    def _on_filter_changed(self) -> None:
        idx = self._emu_combo.currentIndex()
        emu = ""
        if idx > 0:
            emu = self._emu_combo.currentText()
        self._refresh_table(emu)

    def _on_restore(self) -> None:
        """Restore selected backup."""
        row = self._table.currentRow()
        if row < 0 or row >= len(self._backups):
            show_warning(self, t("restore.err_none_selected"), t("restore.err_none_selected_msg"))
            return

        record = self._backups[row]

        # Preview
        if self._ctx.restore_manager:
            changes = self._ctx.restore_manager.preview_restore(record)
            newer = [c for c in changes if c.is_newer_locally]

            if newer:
                msg = MessageBox(
                    t("restore.confirm_overwrite"),
                    t("restore.confirm_overwrite_msg", count=len(newer)),
                    self,
                )
                if msg.exec():
                    force = True
                else:
                    force = False
            else:
                force = False

            result = self._ctx.restore_manager.restore_backup(record, force=force)

            if result.success:
                show_success(
                    self, t("restore.success"),
                    t("restore.success_msg", count=len(result.restored_files))
                )
            else:
                show_error(self, t("restore.failed"), result.error)
