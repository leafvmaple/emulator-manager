"""Save Library tab — displays detected game saves grouped by emulator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QTableWidgetItem,
    QHeaderView,
)
from qfluentwidgets import (
    PrimaryPushButton,
    SearchLineEdit,
    ComboBox,
    TableWidget,
    PushButton,
)
from qfluentwidgets import FluentIcon as FIF

from app.utils import format_size
from app.i18n import t

if TYPE_CHECKING:
    from app.context import AppContext
    from app.models.game_save import GameSave


class SaveLibraryTab(QWidget):
    """Save library view — shows detected saves from all emulators."""

    save_selected = Signal(object)  # GameSave

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._saves: list[GameSave] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()
        self._search = SearchLineEdit(self)
        self._search.setPlaceholderText(t("save_lib.search_placeholder"))
        self._search.textChanged.connect(self._on_filter)
        toolbar.addWidget(self._search, 1)

        self._emu_filter = ComboBox(self)
        self._emu_filter.addItem(t("save_lib.all_emulators"))
        self._emu_filter.currentIndexChanged.connect(self._on_filter)
        toolbar.addWidget(self._emu_filter)

        self._scan_btn = PrimaryPushButton(FIF.SYNC, t("save_lib.scan"), self)
        self._scan_btn.clicked.connect(self._on_scan)
        toolbar.addWidget(self._scan_btn)

        layout.addLayout(toolbar)

        # Table
        self._table = TableWidget(self)
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            [t("save_lib.col_name"), t("save_lib.col_emulator"), t("save_lib.col_platform"), t("save_lib.col_size"), t("save_lib.col_files")]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self._table.cellClicked.connect(self._on_row_clicked)
        layout.addWidget(self._table)

        # Status
        status_row = QHBoxLayout()
        self._status = PushButton(t("save_lib.ready"), self)
        self._status.setEnabled(False)
        status_row.addWidget(self._status)
        status_row.addStretch()
        layout.addLayout(status_row)

    def _on_scan(self) -> None:
        """Scan for saves across all emulators."""
        if not self._ctx.scanner:
            return
        self._scan_btn.setEnabled(False)
        self._status.setText(t("save_lib.scanning"))

        self._saves = self._ctx.scanner.scan_all_saves()
        self._refresh_table()
        self._update_emu_filter()

        self._status.setText(t("save_lib.n_saves", count=len(self._saves)))
        self._scan_btn.setEnabled(True)

    def _refresh_table(self, filter_text: str = "", emulator: str = "") -> None:
        self._table.setRowCount(0)
        for save in self._saves:
            if emulator and save.emulator != emulator:
                continue
            if filter_text and filter_text.lower() not in save.game_name.lower():
                continue

            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(save.game_name))
            self._table.setItem(row, 1, QTableWidgetItem(save.emulator))
            self._table.setItem(row, 2, QTableWidgetItem(save.platform.upper()))
            self._table.setItem(row, 3, QTableWidgetItem(format_size(save.total_size)))
            self._table.setItem(row, 4, QTableWidgetItem(str(len(save.files))))

    def _update_emu_filter(self) -> None:
        emus = sorted({s.emulator for s in self._saves})
        self._emu_filter.clear()
        self._emu_filter.addItem(t("save_lib.all_emulators"))
        for e in emus:
            self._emu_filter.addItem(e)

    def _on_filter(self) -> None:
        text = self._search.text()
        idx = self._emu_filter.currentIndex()
        emu = ""
        if idx > 0:
            emu = self._emu_filter.currentText()
        self._refresh_table(text, emu)

    def _on_row_clicked(self, row: int, _col: int) -> None:
        name_item = self._table.item(row, 0)
        emu_item = self._table.item(row, 1)
        if name_item and emu_item:
            for save in self._saves:
                if save.game_name == name_item.text() and save.emulator == emu_item.text():
                    self.save_selected.emit(save)
                    break
