"""ROM Tools tab — miscellaneous ROM utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    SettingCardGroup,
    PushSettingCard,
)
from qfluentwidgets import FluentIcon as FIF

from app.ui.utils import show_info
from app.i18n import t

if TYPE_CHECKING:
    from app.context import AppContext


class RomToolsTab(QWidget):
    """Miscellaneous ROM tools and utilities."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)

        # Duplicate finder
        dup_group = SettingCardGroup(t("tools.dup_detection"), self)
        self._dup_card = PushSettingCard(
            t("tools.detect"),
            FIF.SEARCH,
            t("tools.find_dup_roms"),
            t("tools.find_dup_desc"),
            dup_group,
        )
        self._dup_card.clicked.connect(self._on_find_duplicates)
        dup_group.addSettingCard(self._dup_card)
        layout.addWidget(dup_group)

        # Library maintenance
        maint_group = SettingCardGroup(t("tools.lib_maintenance"), self)
        self._verify_card = PushSettingCard(
            t("tools.verify"),
            FIF.CHECKBOX,
            t("tools.verify_roms"),
            t("tools.verify_desc"),
            maint_group,
        )
        self._verify_card.clicked.connect(self._on_verify)
        maint_group.addSettingCard(self._verify_card)

        self._export_card = PushSettingCard(
            t("tools.export"),
            FIF.SAVE,
            t("tools.export_list"),
            t("tools.export_desc"),
            maint_group,
        )
        self._export_card.clicked.connect(self._on_export)
        maint_group.addSettingCard(self._export_card)
        layout.addWidget(maint_group)

        layout.addStretch(1)

    def _on_find_duplicates(self) -> None:
        if not self._ctx.rom_library:
            return
        dups = self._ctx.rom_library.find_duplicates()
        show_info(self, t("tools.dup_result"), t("tools.dup_result_msg", count=len(dups)))

    def _on_verify(self) -> None:
        if not self._ctx.rom_library:
            return
        from pathlib import Path

        entries = list(self._ctx.rom_library.all_entries())
        missing = [e for e in entries if not Path(e.path).exists()]
        show_info(self, t("tools.verify_result"), t("tools.verify_result_msg", total=len(entries), missing=len(missing)))

    def _on_export(self) -> None:
        show_info(self, t("tools.export_wip"), t("tools.export_wip_msg"))
