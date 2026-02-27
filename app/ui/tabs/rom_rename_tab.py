"""ROM Rename tab — batch rename with template preview."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QCheckBox,
)
from qfluentwidgets import (
    PrimaryPushButton,
    PushButton,
    ComboBox,
    LineEdit,
    TableWidget,
    CaptionLabel,
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
        self._output_dir: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)

        # ── Output folder row ──
        out_row = QHBoxLayout()
        out_row.addWidget(CaptionLabel(t("rename.output_dir"), self))

        self._output_edit = LineEdit(self)
        self._output_edit.setPlaceholderText(t("rename.output_dir_placeholder"))
        self._output_edit.setReadOnly(True)
        out_row.addWidget(self._output_edit, 1)

        self._browse_btn = PushButton(FIF.FOLDER, t("rename.browse"), self)
        self._browse_btn.clicked.connect(self._on_browse_output)
        out_row.addWidget(self._browse_btn)

        self._mode_combo = ComboBox(self)
        self._mode_combo.addItem(t("rename.mode_move"), userData="move")
        self._mode_combo.addItem(t("rename.mode_copy"), userData="copy")
        self._mode_combo.setMinimumWidth(80)
        out_row.addWidget(self._mode_combo)

        self._clear_btn = PushButton(FIF.CLOSE, t("rename.clear"), self)
        self._clear_btn.clicked.connect(self._on_clear_output)
        out_row.addWidget(self._clear_btn)

        layout.addLayout(out_row)

        # ── Filter row ──
        filter_row = QHBoxLayout()

        filter_row.addWidget(CaptionLabel(t("rename.filter_platform"), self))
        self._platform_combo = ComboBox(self)
        self._platform_combo.addItem(t("rename.filter_all"), userData="")
        for gp in sorted(self._ctx.plugin_manager.game_plugins, key=lambda p: p.platform):
            self._platform_combo.addItem(gp.platform.upper(), userData=gp.platform)
        self._platform_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._platform_combo)

        filter_row.addWidget(CaptionLabel(t("rename.filter_scrape"), self))
        self._scrape_combo = ComboBox(self)
        self._scrape_combo.addItem(t("rename.filter_all"), userData="")
        self._scrape_combo.addItem(t("rename.filter_scraped"), userData="done")
        self._scrape_combo.addItem(t("rename.filter_unscraped"), userData="none")
        self._scrape_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._scrape_combo)

        filter_row.addWidget(CaptionLabel(t("rename.filter_identify"), self))
        self._identify_combo = ComboBox(self)
        self._identify_combo.addItem(t("rename.filter_all"), userData="")
        self._identify_combo.addItem(t("rename.filter_identified"), userData="yes")
        self._identify_combo.addItem(t("rename.filter_unidentified"), userData="no")
        self._identify_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._identify_combo)

        filter_row.addStretch()
        layout.addLayout(filter_row)

        # ── Template row ──
        tmpl_row = QHBoxLayout()

        self._template_combo = ComboBox(self)
        self._template_combo.addItems(["simple", "with_id", "full", "organized"])
        self._template_combo.currentIndexChanged.connect(self._on_template_changed)
        tmpl_row.addWidget(self._template_combo)

        self._template_edit = LineEdit(self)
        self._template_edit.setPlaceholderText(t("rename.template_hint"))
        self._template_edit.textChanged.connect(self._on_template_text_changed)
        tmpl_row.addWidget(self._template_edit, 1)

        self._preview_btn = PushButton(FIF.VIEW, t("rename.preview"), self)
        self._preview_btn.clicked.connect(self._on_preview)
        tmpl_row.addWidget(self._preview_btn)

        self._rename_btn = PrimaryPushButton(FIF.EDIT, t("rename.execute"), self)
        self._rename_btn.clicked.connect(self._on_rename)
        tmpl_row.addWidget(self._rename_btn)

        layout.addLayout(tmpl_row)

        # ── Selection buttons row ──
        sel_row = QHBoxLayout()
        self._select_all_btn = PushButton(t("rename.select_all"), self)
        self._select_all_btn.clicked.connect(lambda: self._toggle_all(True))
        sel_row.addWidget(self._select_all_btn)

        self._deselect_all_btn = PushButton(t("rename.deselect_all"), self)
        self._deselect_all_btn.clicked.connect(lambda: self._toggle_all(False))
        sel_row.addWidget(self._deselect_all_btn)

        sel_row.addStretch()
        layout.addLayout(sel_row)

        # ── Preview table (with checkbox column) ──
        self._table = TableWidget(self)
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels([
            "", t("rename.col_current"), t("rename.col_arrow"), t("rename.col_new"),
        ])
        self._table.setColumnWidth(0, 40)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self._table.setColumnWidth(2, 30)
        self._table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        # Load default template
        self._on_template_changed()

    # ── Output folder ──

    def _on_browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, t("rename.choose_output_dir"))
        if path:
            self._output_dir = path
            self._output_edit.setText(path)

    def _on_clear_output(self) -> None:
        self._output_dir = ""
        self._output_edit.clear()

    # ── Selection helpers ──

    def _toggle_all(self, checked: bool) -> None:
        self._batch_toggling = True
        for row in range(self._table.rowCount()):
            cb = self._table.cellWidget(row, 0)
            if isinstance(cb, QCheckBox):
                cb.setChecked(checked)
        self._batch_toggling = False
        self._update_checked_previews()

    def _get_selected_indices(self) -> list[int]:
        """Return indices of checked rows."""
        selected = []
        for row in range(self._table.rowCount()):
            cb = self._table.cellWidget(row, 0)
            if isinstance(cb, QCheckBox) and cb.isChecked():
                selected.append(row)
        return selected

    def _on_check_toggled(self) -> None:
        """When a checkbox is toggled, update that row's preview."""
        if getattr(self, "_batch_toggling", False):
            return
        self._update_checked_previews()

    def _on_filter_changed(self) -> None:
        """Re-run preview when filter selection changes."""
        self._on_preview()

    def _get_template_string(self, key: str) -> str:
        from app.ui.constants import DEFAULT_TEMPLATES
        return DEFAULT_TEMPLATES.get(key, "{filename}")

    def _on_template_changed(self) -> None:
        key = self._template_combo.currentText()
        template = self._get_template_string(key)
        self._template_edit.blockSignals(True)
        self._template_edit.setText(template)
        self._template_edit.blockSignals(False)
        self._on_preview()

    def _on_template_text_changed(self) -> None:
        """Template text changed — only update previews for checked rows."""
        if self._table.rowCount() == 0:
            self._on_preview()
        else:
            self._update_checked_previews()

    def _on_preview(self) -> None:
        """Full rebuild: reload entries and populate table (resets checkboxes)."""
        if not self._ctx.rom_manager or not self._ctx.rom_library:
            return

        all_entries = list(self._ctx.rom_library.all_entries())

        # Apply filters
        platform_filter = self._platform_combo.currentData() or ""
        scrape_filter = self._scrape_combo.currentData() or ""
        identify_filter = self._identify_combo.currentData() or ""

        self._entries = []
        for e in all_entries:
            if platform_filter and e.platform != platform_filter:
                continue
            status = e.scrape_status or "none"
            if scrape_filter and status != scrape_filter:
                continue
            if identify_filter:
                identified = e.rom_info is not None and e.rom_info.dat_id >= 0
                if identify_filter == "yes" and not identified:
                    continue
                if identify_filter == "no" and identified:
                    continue
            self._entries.append(e)

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

            changed = old_name != new_name
            cb = QCheckBox()
            cb.setChecked(changed)
            cb.toggled.connect(self._on_check_toggled)
            self._table.setCellWidget(row, 0, cb)

            self._table.setItem(row, 1, QTableWidgetItem(old_name))
            self._table.setItem(row, 2, QTableWidgetItem("→" if changed else ""))
            new_item = QTableWidgetItem(new_name if changed else "")
            if changed:
                new_item.setForeground(QColor("#2ecc71"))
            self._table.setItem(row, 3, new_item)

    def _update_checked_previews(self) -> None:
        """Recompute new filenames only for checked rows; clear unchecked rows."""
        template = self._template_edit.text().strip()
        if not template or not self._entries:
            return

        for row in range(self._table.rowCount()):
            cb = self._table.cellWidget(row, 0)
            if not isinstance(cb, QCheckBox):
                continue

            if cb.isChecked() and row < len(self._entries):
                entry = self._entries[row]
                tokens = self._ctx.rom_manager._build_rename_tokens(entry)
                new_stem = self._ctx.rename_engine.preview(template, tokens)
                old_path = Path(entry.rom_path)
                new_name = new_stem + old_path.suffix if not new_stem.endswith(old_path.suffix) else new_stem

                self._table.setItem(row, 2, QTableWidgetItem("→"))
                new_item = QTableWidgetItem(new_name)
                new_item.setForeground(QColor("#2ecc71"))
                self._table.setItem(row, 3, new_item)
            else:
                self._table.setItem(row, 2, QTableWidgetItem(""))
                self._table.setItem(row, 3, QTableWidgetItem(""))

    def _on_rename(self) -> None:
        """Execute batch rename / copy for selected entries only."""
        if not self._ctx.rom_manager or not self._entries:
            show_warning(self, t("rename.err_no_roms"), t("rename.err_no_roms_msg"))
            return

        template = self._template_edit.text().strip()
        if not template:
            return

        selected = self._get_selected_indices()
        if not selected:
            show_warning(self, t("rename.err_no_roms"), t("rename.err_none_selected_msg"))
            return

        chosen = [self._entries[i] for i in selected if i < len(self._entries)]

        if self._output_dir:
            # Copy or move to output folder with new names
            out = Path(self._output_dir)
            out.mkdir(parents=True, exist_ok=True)
            results = self._ctx.rom_manager.batch_rename(
                chosen, template, dry_run=True
            )
            mode = self._mode_combo.currentData() or "copy"
            count = 0
            for (entry, (_, new_name)) in zip(chosen, results):
                src = Path(entry.rom_path)
                dst = out / new_name
                if dst.exists():
                    show_warning(self, t("rename.err_conflict"), str(dst))
                    continue
                try:
                    if mode == "move":
                        shutil.move(str(src), dst)
                        entry.rom_path = str(dst)
                    else:
                        shutil.copy2(src, dst)
                    count += 1
                except OSError as e:
                    show_error(self, t("rename.err_copy_failed"), str(e))
            if mode == "move":
                self._ctx.rom_library.save()
                show_success(self, t("rename.success"), t("rename.success_move_msg", count=count))
            else:
                show_success(self, t("rename.success"), t("rename.success_copy_msg", count=count))
        else:
            # Rename in-place
            results = self._ctx.rom_manager.batch_rename(
                chosen, template, dry_run=False
            )
            changed = sum(1 for old, new in results if old != new)
            show_success(self, t("rename.success"), t("rename.success_msg", count=changed))

        self._on_preview()  # Refresh
