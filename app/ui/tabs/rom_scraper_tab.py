"""ROM Scraper tab — metadata scraping with ROM list and manual matching."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QTableWidgetItem,
    QHeaderView,
    QSplitter,
    QLabel,
)
from qfluentwidgets import (
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    ComboBox,
    TableWidget,
    ProgressBar,
)
from qfluentwidgets import FluentIcon as FIF

from pathlib import Path

from app.models.scrape_result import ScrapeResult
from app.ui.utils import show_success, show_error
from app.i18n import t

if TYPE_CHECKING:
    from app.context import AppContext
    from app.models.rom_entry import RomEntry


class ScrapeWorker(QThread):
    """Background worker for scraping metadata."""

    progress = Signal(int, int)  # current, total
    finished = Signal(int)  # count scraped
    error = Signal(str)

    def __init__(self, ctx: AppContext, entries: list, parent=None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._entries = entries

    def run(self) -> None:
        count = 0
        total = len(self._entries)
        for i, entry in enumerate(self._entries):
            try:
                if self._ctx.scraper:
                    query = entry.display_name
                    self._ctx.scraper.scrape(
                        entry.game_id, entry.platform, query=query
                    )
                    # Persist scrape status back to rom_library
                    entry.scrape_status = "done"
                    self._ctx.rom_library.add(entry)
                    count += 1
            except Exception as e:
                self.error.emit(f"{entry.display_name}: {e}")
            self.progress.emit(i + 1, total)
        # Save all changes in one shot after the loop
        if count:
            try:
                self._ctx.rom_library.save()
            except Exception as e:
                self.error.emit(t("scraper.save_failed", error=str(e)))
        self.finished.emit(count)


class SearchWorker(QThread):
    """Background worker for interactive search — keeps GUI responsive."""

    results_ready = Signal(list)  # list[ScrapeResult]
    error = Signal(str)

    def __init__(self, ctx: AppContext, query: str, platform: str,
                 provider_name: str, parent=None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._query = query
        self._platform = platform
        self._provider_name = provider_name

    def run(self) -> None:
        try:
            results = self._ctx.scraper.search_interactive(
                self._query, self._platform, provider_name=self._provider_name
            )
            self.results_ready.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class RomScraperTab(QWidget):
    """Metadata scraping tab — shows ROM library entries and supports batch/manual scraping."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._entries: list[RomEntry] = []
        self._worker: ScrapeWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)

        # ── Top toolbar ──
        toolbar = QHBoxLayout()

        self._refresh_btn = PushButton(FIF.SYNC, t("scraper.refresh"), self)
        self._refresh_btn.clicked.connect(self._load_entries)
        toolbar.addWidget(self._refresh_btn)

        self._scrape_selected_btn = PrimaryPushButton(FIF.DOWNLOAD, t("scraper.scrape_selected"), self)
        self._scrape_selected_btn.clicked.connect(self._on_scrape_selected)
        toolbar.addWidget(self._scrape_selected_btn)

        self._scrape_all_btn = PushButton(FIF.DOWNLOAD, t("scraper.scrape_all"), self)
        self._scrape_all_btn.clicked.connect(self._on_scrape_all)
        toolbar.addWidget(self._scrape_all_btn)

        self._detail_btn = PushButton(FIF.INFO, t("scraper.view_detail"), self)
        self._detail_btn.clicked.connect(self._on_view_detail)
        toolbar.addWidget(self._detail_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ── Progress ──
        self._progress = ProgressBar(self)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # ── Splitter: ROM list (top) + search results (bottom) ──
        splitter = QSplitter(Qt.Orientation.Vertical, self)

        # ROM list table
        rom_container = QWidget()
        rom_layout = QVBoxLayout(rom_container)
        rom_layout.setContentsMargins(0, 0, 0, 0)

        self._rom_table = TableWidget(self)
        self._rom_table.setColumnCount(9)
        self._rom_table.setHorizontalHeaderLabels([
            t("scraper.col_dat_id"),
            t("scraper.col_filename"),
            t("scraper.col_title_id"),
            t("scraper.col_name"),
            t("scraper.col_crc32"),
            t("scraper.col_version"),
            t("scraper.col_platform"),
            t("scraper.col_region"),
            t("scraper.col_status"),
        ])
        self._rom_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self._rom_table.horizontalHeader().setStretchLastSection(True)
        self._rom_table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self._rom_table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self._rom_table.cellClicked.connect(self._on_rom_clicked)
        self._rom_table.cellDoubleClicked.connect(self._on_rom_double_clicked)
        rom_layout.addWidget(self._rom_table)
        splitter.addWidget(rom_container)

        # Search results panel
        search_container = QWidget()
        search_layout = QVBoxLayout(search_container)
        search_layout.setContentsMargins(0, 8, 0, 0)

        search_toolbar = QHBoxLayout()
        search_toolbar.addWidget(QLabel(t("scraper.manual_search")))
        self._search = SearchLineEdit(self)
        self._search.setPlaceholderText(t("scraper.search_placeholder"))
        self._search.returnPressed.connect(self._on_manual_search)
        search_toolbar.addWidget(self._search, 1)

        self._provider_combo = ComboBox(self)
        self._provider_combo.addItems(["IGDB", "ScreenScraper"])
        search_toolbar.addWidget(self._provider_combo)

        self._search_btn = PushButton(FIF.SEARCH, t("scraper.search"), self)
        self._search_btn.clicked.connect(self._on_manual_search)
        search_toolbar.addWidget(self._search_btn)

        self._apply_btn = PrimaryPushButton(FIF.ACCEPT, t("scraper.apply_to_rom"), self)
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._on_apply_result)
        search_toolbar.addWidget(self._apply_btn)

        search_layout.addLayout(search_toolbar)

        self._result_table = TableWidget(self)
        self._result_table.setColumnCount(5)
        self._result_table.setHorizontalHeaderLabels(
            [t("scraper.col_result_name"), t("scraper.col_publisher"), t("scraper.col_genre"), t("scraper.col_release_date"), t("scraper.col_source")]
        )
        self._result_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._result_table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self._result_table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self._result_table.itemSelectionChanged.connect(self._on_result_selection_changed)
        search_layout.addWidget(self._result_table)
        splitter.addWidget(search_container)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        # Load on first show
        self._loaded = False
        self._search_results: list[ScrapeResult] = []
        self._search_worker: SearchWorker | None = None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Always reload from rom_library to stay in sync
        self._load_entries()

    # ── Data loading ──

    def _load_entries(self) -> None:
        """Load ROM entries from the library, sorted by dat_id ascending, and refresh the table."""
        self._entries = list(self._ctx.rom_library.all_entries())
        self._entries.sort(key=lambda e: e.rom_info.dat_id if e.rom_info else -1)
        self._refresh_rom_table()

    def _refresh_rom_table(self) -> None:
        """Populate the ROM table with current entries."""
        self._rom_table.setRowCount(0)
        for entry in self._entries:
            row = self._rom_table.rowCount()
            self._rom_table.insertRow(row)

            dat_id = entry.rom_info.dat_id if entry.rom_info else -1
            dat_id_text = str(dat_id)
            filename = Path(entry.rom_path).name if entry.rom_path else ""
            title_id = entry.rom_info.title_id if entry.rom_info else entry.game_id
            version = entry.rom_info.version if entry.rom_info else ""

            self._rom_table.setItem(row, 0, QTableWidgetItem(dat_id_text))
            self._rom_table.setItem(row, 1, QTableWidgetItem(filename))
            self._rom_table.setItem(row, 2, QTableWidgetItem(title_id))
            self._rom_table.setItem(row, 3, QTableWidgetItem(entry.display_name))

            # CRC32 cell with color coding
            crc_item = QTableWidgetItem(entry.hash_crc32)
            dat_crcs = entry.rom_info.dat_crc32 if entry.rom_info else None
            if entry.hash_crc32 and dat_crcs:
                if entry.hash_crc32.upper() in [c.upper() for c in dat_crcs]:
                    crc_item.setForeground(QColor("#2ecc71"))  # green — verified
                else:
                    crc_item.setForeground(QColor("#e74c3c"))  # red — mismatch
            elif entry.hash_crc32:
                crc_item.setForeground(QColor("#e74c3c"))  # red — not in database
            self._rom_table.setItem(row, 4, crc_item)

            self._rom_table.setItem(row, 5, QTableWidgetItem(version))
            self._rom_table.setItem(row, 6, QTableWidgetItem(entry.platform.upper()))

            region = entry.rom_info.region if entry.rom_info else ""
            self._rom_table.setItem(row, 7, QTableWidgetItem(region))

            status = entry.scrape_status or "none"
            status_text = {"none": t("scraper.status_none"), "partial": t("scraper.status_partial"), "done": t("scraper.status_done")}.get(
                status, status
            )
            self._rom_table.setItem(row, 8, QTableWidgetItem(status_text))

    # ── ROM row click → prefill search ──

    def _on_rom_clicked(self, row: int, _col: int) -> None:
        """Click a ROM row to prefill the search box with its name."""
        name_item = self._rom_table.item(row, 3)  # col 3 = game name
        if name_item:
            self._search.setText(name_item.text())

    # ── Scraping ──

    def _on_scrape_selected(self) -> None:
        """Scrape selected ROM entries."""
        selected_rows = {idx.row() for idx in self._rom_table.selectedIndexes()}
        if not selected_rows:
            show_error(self, t("scraper.err_no_selection"), t("scraper.err_no_selection_msg"))
            return
        entries = [self._entries[r] for r in sorted(selected_rows) if r < len(self._entries)]
        self._start_scrape(entries)

    def _on_scrape_all(self) -> None:
        """Start batch scraping for all ROM entries."""
        if not self._entries:
            show_error(self, t("scraper.err_no_roms"), t("scraper.err_no_roms_msg"))
            return
        self._start_scrape(self._entries)

    def _start_scrape(self, entries: list) -> None:
        if not self._ctx.scraper:
            show_error(self, t("scraper.err_not_configured"), t("scraper.err_not_configured_msg"))
            return

        self._scrape_all_btn.setEnabled(False)
        self._scrape_selected_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, len(entries))

        self._worker = ScrapeWorker(self._ctx, entries, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_scrape_finished)
        self._worker.error.connect(lambda msg: show_error(self, t("scraper.err_scrape"), msg))
        self._worker.start()

    def _on_progress(self, current: int, total: int) -> None:
        self._progress.setValue(current)

    def _on_scrape_finished(self, count: int) -> None:
        self._progress.setVisible(False)
        self._scrape_all_btn.setEnabled(True)
        self._scrape_selected_btn.setEnabled(True)
        self._load_entries()  # Refresh status
        show_success(self, t("scraper.success_scrape"), t("scraper.success_scrape_msg", count=count))

    # ── Manual search (async) ──

    def _on_manual_search(self) -> None:
        """Launch async search — keeps GUI responsive."""
        query = self._search.text().strip()
        if not query:
            return
        if not self._ctx.scraper or not self._ctx.scraper.providers:
            show_error(
                self,
                t("scraper.err_no_api_key"),
                t("scraper.err_no_api_key_msg"),
            )
            return

        # Determine platform from selected ROM row
        platform = "gba"  # default
        selected_rows = {idx.row() for idx in self._rom_table.selectedIndexes()}
        if selected_rows:
            row = min(selected_rows)
            if row < len(self._entries):
                platform = self._entries[row].platform

        provider_name = self._provider_combo.currentText().lower()

        # Check if the selected provider is actually registered
        if provider_name not in self._ctx.scraper.providers:
            available = list(self._ctx.scraper.providers.keys())
            if not available:
                show_error(self, t("scraper.err_no_provider"), t("scraper.err_no_provider_msg"))
                return
            provider_name = available[0]

        self._search_btn.setEnabled(False)
        self._search_btn.setText(t("scraper.searching"))
        self._apply_btn.setEnabled(False)

        self._search_worker = SearchWorker(
            self._ctx, query, platform, provider_name, self
        )
        self._search_worker.results_ready.connect(self._on_search_results)
        self._search_worker.error.connect(self._on_search_error)
        self._search_worker.start()

    def _on_search_error(self, msg: str) -> None:
        """Handle search worker error."""
        show_error(self, t("scraper.search_failed"), msg)
        self._search_btn.setEnabled(True)
        self._search_btn.setText(t("scraper.search"))

    def _on_search_results(self, results: list) -> None:
        """Handle search worker results — populate the result table."""
        self._search_results = results
        self._result_table.setRowCount(0)

        if not results:
            self._result_table.insertRow(0)
            self._result_table.setItem(
                0, 0, QTableWidgetItem(t("scraper.no_results"))
            )
        else:
            for result in results:
                row = self._result_table.rowCount()
                self._result_table.insertRow(row)
                self._result_table.setItem(row, 0, QTableWidgetItem(result.title or ""))
                self._result_table.setItem(row, 1, QTableWidgetItem(result.publisher or ""))
                self._result_table.setItem(
                    row, 2, QTableWidgetItem(result.genre or "")
                )
                self._result_table.setItem(row, 3, QTableWidgetItem(result.release_date or ""))
                self._result_table.setItem(row, 4, QTableWidgetItem(result.provider))

        self._search_btn.setEnabled(True)
        self._search_btn.setText(t("scraper.search"))

    # ── Result selection & apply ──

    def _on_result_selection_changed(self) -> None:
        """Enable apply button when a search result is selected."""
        has_result_selected = bool(self._result_table.selectedIndexes())
        has_rom_selected = bool(self._rom_table.selectedIndexes())
        self._apply_btn.setEnabled(has_result_selected and has_rom_selected)

    def _on_apply_result(self) -> None:
        """Apply the selected search result to the selected ROM entry.

        This does real work:
          1. Updates RomInfo titles from scraped data
          2. Downloads and caches the icon/boxart
          3. Saves scrape result to scrape cache
          4. Updates scrape_status and persists to rom_library
        """
        from app.models.rom_entry import RomInfo

        # Get selected result
        result_rows = {idx.row() for idx in self._result_table.selectedIndexes()}
        if not result_rows:
            show_error(self, t("scraper.err_no_result_sel"), t("scraper.err_no_result_sel_msg"))
            return
        result_row = min(result_rows)
        if result_row >= len(self._search_results):
            return
        result = self._search_results[result_row]

        # Get selected ROM entry
        rom_rows = {idx.row() for idx in self._rom_table.selectedIndexes()}
        if not rom_rows:
            show_error(self, t("scraper.err_no_rom_sel"), t("scraper.err_no_rom_sel_msg"))
            return
        rom_row = min(rom_rows)
        if rom_row >= len(self._entries):
            return
        entry = self._entries[rom_row]

        # Fill game_id and platform from the ROM entry into the result
        result.game_id = entry.game_id
        result.platform = entry.platform

        try:
            # 1. Update RomInfo with scraped metadata
            if entry.rom_info is None:
                entry.rom_info = RomInfo()
            ri = entry.rom_info

            if result.title:
                ri.title_name = result.title
                # Populate multilingual titles from scrape result
                ri.title_name_en = result.title_en or result.title
                if result.title_ja:
                    ri.title_name_ja = result.title_ja
                if result.title_zh:
                    ri.title_name_zh = result.title_zh
            if result.publisher and not ri.publisher:
                ri.publisher = result.publisher

            # 2. Download icon/boxart
            icon_url = result.icon_url or result.boxart_url
            if icon_url:
                icon_path = self._ctx.icon_provider.download_icon(
                    entry.platform, entry.game_id, icon_url
                )
                if icon_path:
                    ri.icon_path = str(icon_path)
                    result.icon_local = str(icon_path)

            # Download boxart separately if different from icon
            if result.boxart_url and result.boxart_url != result.icon_url:
                boxart_path = self._ctx.icon_provider.download_icon(
                    entry.platform, f"{entry.game_id}_boxart", result.boxart_url
                )
                if boxart_path:
                    result.boxart_local = str(boxart_path)

            # 3. Save scrape result to cache
            self._ctx.scrape_cache.save_result(result)

            # 4. Update entry scrape status and persist
            entry.scrape_status = "done"
            self._ctx.rom_library.add(entry)
            self._ctx.rom_library.save()

            # Refresh ROM table row
            name_item = self._rom_table.item(rom_row, 3)  # col 3 = game name
            if name_item:
                name_item.setText(entry.display_name)
            status_item = self._rom_table.item(rom_row, 8)  # col 8 = status
            if status_item:
                status_item.setText(t("scraper.status_done"))

            show_success(
                self,
                t("scraper.apply_success"),
                t("scraper.apply_success_msg", title=result.title, name=entry.display_name),
            )
        except Exception as e:
            show_error(self, t("scraper.apply_failed"), str(e))

    # ── Detail view ──

    def _on_rom_double_clicked(self, row: int, _col: int) -> None:
        """Double-click a ROM row to view its details."""
        if row < len(self._entries):
            self._show_detail_dialog(self._entries[row])

    def _on_view_detail(self) -> None:
        """View detail button handler."""
        rom_rows = {idx.row() for idx in self._rom_table.selectedIndexes()}
        if not rom_rows:
            show_error(self, t("scraper.err_select_rom_first"), t("scraper.err_select_rom_first_msg"))
            return
        row = min(rom_rows)
        if row < len(self._entries):
            self._show_detail_dialog(self._entries[row])

    def _show_detail_dialog(self, entry: RomEntry) -> None:
        """Show the ROM detail dialog."""
        from app.ui.dialogs.rom_detail_dialog import RomDetailDialog
        dialog = RomDetailDialog(self._ctx, entry, self.window())
        dialog.exec()
