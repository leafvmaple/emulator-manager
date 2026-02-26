"""ROM Library tab — displays scanned ROMs as card list (vertical scroll)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    SearchLineEdit,
    ComboBox,
    PrimaryPushButton,
    PushButton,
    CaptionLabel,
    SmoothScrollArea,
    InfoBadge,
)
from qfluentwidgets import FluentIcon as FIF

from app.ui.components.game_card import GameCard
from app.i18n import t

if TYPE_CHECKING:
    from app.context import AppContext
    from app.models.rom_entry import RomEntry


class RomScanWorker(QThread):
    """Background worker for ROM directory scanning."""

    finished = Signal(int)  # number of new entries

    def __init__(self, ctx: AppContext, parent=None) -> None:
        super().__init__(parent)
        self._ctx = ctx

    def run(self) -> None:
        try:
            new_entries = self._ctx.rom_manager.scan_directories()
            self.finished.emit(len(new_entries))
        except Exception:
            self.finished.emit(0)


class RomLibraryTab(QWidget):
    """ROM library view with vertical card list, search, and platform filter."""

    rom_selected = Signal(object)  # RomEntry

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._entries: list[RomEntry] = []
        self._cards: list[GameCard] = []
        self._selected_card: GameCard | None = None
        self._worker: RomScanWorker | None = None
        self._dirty = True  # needs rebuild on next show

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)

        # ── Toolbar ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)

        self._search = SearchLineEdit(self)
        self._search.setPlaceholderText(t("rom_lib.search_placeholder"))
        self._search.textChanged.connect(self._on_filter)
        toolbar.addWidget(self._search, 1)

        self._platform_filter = ComboBox(self)
        self._platform_filter.addItem(t("rom_lib.all_platforms"))
        self._platform_filter.currentIndexChanged.connect(self._on_filter)
        toolbar.addWidget(self._platform_filter)

        self._count_badge = InfoBadge.attension("0", parent=self)
        self._count_badge.setFixedHeight(20)
        toolbar.addWidget(self._count_badge)

        self._scan_btn = PrimaryPushButton(FIF.SYNC, t("rom_lib.scan"), self)
        self._scan_btn.clicked.connect(self._on_scan)
        toolbar.addWidget(self._scan_btn)

        self._detail_btn = PushButton(FIF.INFO, t("rom_lib.view_detail"), self)
        self._detail_btn.clicked.connect(self._on_view_detail)
        toolbar.addWidget(self._detail_btn)

        layout.addLayout(toolbar)

        # ── Scrollable card list ──
        self._scroll = SmoothScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self._scroll_inner = QWidget()
        self._card_layout = QVBoxLayout(self._scroll_inner)
        self._card_layout.setContentsMargins(8, 8, 8, 8)
        self._card_layout.setSpacing(6)
        self._card_layout.addStretch()
        self._scroll.setWidget(self._scroll_inner)

        layout.addWidget(self._scroll, stretch=1)

        # ── Empty state ──
        self._empty_label = CaptionLabel(t("rom_lib.empty_hint"), self)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #888;")
        layout.addWidget(self._empty_label)
        self._empty_label.hide()

        # ── Status bar ──
        status_bar = QHBoxLayout()
        self._status_label = CaptionLabel(t("rom_lib.ready"), self)
        self._status_label.setStyleSheet("color: #888;")
        status_bar.addWidget(self._status_label)
        status_bar.addStretch()
        layout.addLayout(status_bar)

        self._loaded = False

    # ── Lifecycle ──

    def showEvent(self, event) -> None:  # noqa: ANN001
        """Reload data from rom_library only when data has changed."""
        super().showEvent(event)
        # Quick check: if entry count changed, mark dirty
        current_count = self._ctx.rom_library.count
        if current_count != len(self._entries):
            self._dirty = True
        if self._dirty:
            self._load_from_library()
            self._dirty = False

    def mark_dirty(self) -> None:
        """Mark the tab as needing a refresh on next show."""
        self._dirty = True

    # ── Data loading ──

    def _load_from_library(self) -> None:
        """Reload entries from the shared rom_library and refresh cards."""
        self._entries = list(self._ctx.rom_library.all_entries())
        self._rebuild_cards()
        self._update_platform_filter()
        n = len(self._cards)
        self._status_label.setText(t("rom_lib.n_games", count=len(self._entries)))
        self._count_badge.setText(str(n))

    def _on_scan(self) -> None:
        """Trigger ROM directory scan in a background thread."""
        if not self._ctx.rom_manager:
            return
        self._scan_btn.setEnabled(False)
        self._status_label.setText(t("rom_lib.scanning"))

        self._worker = RomScanWorker(self._ctx, self)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.start()

    def _on_scan_finished(self, new_count: int) -> None:
        """Handle scan completion — refresh UI on the main thread."""
        self._dirty = True
        self._load_from_library()
        self._dirty = False
        self._scan_btn.setEnabled(True)
        self._worker = None

    # ── Card management ──

    def _rebuild_cards(self, filter_text: str = "", platform: str = "") -> None:
        """Rebuild all game cards based on current entries and filters."""
        # Clear existing cards
        for c in self._cards:
            self._card_layout.removeWidget(c)
            c.deleteLater()
        self._cards.clear()
        self._selected_card = None

        shown = 0
        for entry in self._entries:
            # Apply filters
            if platform and entry.platform.lower() != platform.lower():
                continue
            display = entry.display_name
            if filter_text and filter_text.lower() not in display.lower():
                continue

            card = GameCard(self._ctx, entry, self._scroll_inner)
            card.clicked.connect(self._on_card_clicked)
            card.doubleClicked.connect(self._on_card_double_clicked)
            self._card_layout.insertWidget(
                self._card_layout.count() - 1, card,
            )
            self._cards.append(card)
            shown += 1

        if shown == 0 and self._entries:
            self._scroll.hide()
            self._empty_label.setText(t("rom_lib.no_match"))
            self._empty_label.show()
        elif not self._entries:
            self._scroll.hide()
            self._empty_label.setText(t("rom_lib.empty_hint"))
            self._empty_label.show()
        else:
            self._empty_label.hide()
            self._scroll.show()

        self._count_badge.setText(str(shown))

    def _update_platform_filter(self) -> None:
        """Update the platform filter combo box."""
        current = self._platform_filter.currentText()
        platforms = sorted({e.platform for e in self._entries})
        self._platform_filter.blockSignals(True)
        self._platform_filter.clear()
        self._platform_filter.addItem(t("rom_lib.all_platforms"))
        restore_idx = 0
        for i, p in enumerate(platforms, 1):
            self._platform_filter.addItem(p.upper())
            if p.upper() == current:
                restore_idx = i
        self._platform_filter.setCurrentIndex(restore_idx)
        self._platform_filter.blockSignals(False)

    # ── Events ──

    def _on_filter(self) -> None:
        """Apply search and platform filters."""
        text = self._search.text()
        idx = self._platform_filter.currentIndex()
        platform = ""
        if idx > 0:
            platform = self._platform_filter.currentText().lower()
        self._rebuild_cards(text, platform)

    def _on_card_clicked(self, entry: RomEntry) -> None:
        """Select a card."""
        # Deselect previous
        if self._selected_card is not None:
            self._selected_card.selected = False

        # Find and select new
        for card in self._cards:
            if card.entry is entry:
                card.selected = True
                self._selected_card = card
                break

        self.rom_selected.emit(entry)

    def _on_card_double_clicked(self, entry: RomEntry) -> None:
        """Double-click to open detail dialog."""
        self._show_detail_dialog(entry)

    def _on_view_detail(self) -> None:
        """View detail button handler."""
        if self._selected_card:
            self._show_detail_dialog(self._selected_card.entry)

    def _show_detail_dialog(self, entry: RomEntry) -> None:
        """Show the ROM detail dialog."""
        from app.ui.dialogs.rom_detail_dialog import RomDetailDialog
        dialog = RomDetailDialog(self._ctx, entry, self.window())
        dialog.exec()
