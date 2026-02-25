"""ROM Rename tab — batch rename with template preview."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
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
    ComboBox,
    LineEdit,
    TableWidget,
)
from qfluentwidgets import FluentIcon as FIF

from app.ui.utils import show_success, show_error, show_warning
from app.i18n import t

if TYPE_CHECKING:
    from app.context import AppContext


class RomRenameTab(QWidget):
    """Batch ROM rename tab with template editing and live preview."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._entries: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)

        # Template row
        tmpl_row = QHBoxLayout()

        self._template_combo = ComboBox(self)
        self._template_combo.addItems(["simple", "with_id", "full", "organized"])
        self._template_combo.currentIndexChanged.connect(self._on_template_changed)
        tmpl_row.addWidget(self._template_combo)

        self._template_edit = LineEdit(self)
        self._template_edit.setPlaceholderText(t("rename.template_hint"))
        self._template_edit.textChanged.connect(self._on_preview)
        tmpl_row.addWidget(self._template_edit, 1)

        self._preview_btn = PushButton(FIF.VIEW, t("rename.preview"), self)
        self._preview_btn.clicked.connect(self._on_preview)
        tmpl_row.addWidget(self._preview_btn)

        self._rename_btn = PrimaryPushButton(FIF.EDIT, t("rename.execute"), self)
        self._rename_btn.clicked.connect(self._on_rename)
        tmpl_row.addWidget(self._rename_btn)

        layout.addLayout(tmpl_row)

        # Preview table
        self._table = TableWidget(self)
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels([t("rename.col_current"), t("rename.col_arrow"), t("rename.col_new")])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self._table.setColumnWidth(1, 30)
        self._table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        # Load default template
        self._on_template_changed()

    def _get_template_string(self, key: str) -> str:
        from app.ui.constants import DEFAULT_TEMPLATES
        return DEFAULT_TEMPLATES.get(key, "{filename}")

    def _on_template_changed(self) -> None:
        key = self._template_combo.currentText()
        template = self._get_template_string(key)
        self._template_edit.setText(template)

    def _on_preview(self) -> None:
        """Preview rename results."""
        if not self._ctx.rom_manager or not self._ctx.rom_library:
            return

        self._entries = list(self._ctx.rom_library.all_entries())
        template = self._template_edit.text().strip()
        if not template or not self._entries:
            return

        results = self._ctx.rom_manager.batch_rename(
            self._entries, template, dry_run=True
        )

        self._table.setRowCount(0)
        for old_name, new_name in results:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(old_name))
            self._table.setItem(row, 1, QTableWidgetItem("→"))
            self._table.setItem(row, 2, QTableWidgetItem(new_name))

            # Highlight changed new name in soft green
            if old_name != new_name:
                new_item = self._table.item(row, 2)
                if new_item:
                    new_item.setForeground(QColor("#2ecc71"))

    def _on_rename(self) -> None:
        """Execute batch rename."""
        if not self._ctx.rom_manager or not self._entries:
            show_warning(self, t("rename.err_no_roms"), t("rename.err_no_roms_msg"))
            return

        template = self._template_edit.text().strip()
        if not template:
            return

        results = self._ctx.rom_manager.batch_rename(
            self._entries, template, dry_run=False
        )

        changed = sum(1 for old, new in results if old != new)
        show_success(self, t("rename.success"), t("rename.success_msg", count=changed))
        self._on_preview()  # Refresh
