"""ROM detail dialog — displays full metadata for a ROM entry."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QWidget,
    QFormLayout,
    QSizePolicy,
)
from qfluentwidgets import (
    MessageBoxBase,
    SubtitleLabel,
    BodyLabel,
    CaptionLabel,
    CardWidget,
    TextEdit,
)

if TYPE_CHECKING:
    from app.context import AppContext
    from app.models.rom_entry import RomEntry
    from app.models.scrape_result import ScrapeResult

from app.i18n import t


class RomDetailDialog(MessageBoxBase):
    """Dialog that shows full ROM metadata + scraped info."""

    def __init__(self, ctx: AppContext, entry: RomEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._entry = entry

        self.yesButton.setText(t("detail.close"))
        self.cancelButton.hide()

        self.widget.setMinimumWidth(600)
        self.widget.setMinimumHeight(500)

        layout = QVBoxLayout()

        # ── Header: icon + title ──
        header = QHBoxLayout()

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(128, 128)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setStyleSheet(
            "QLabel { background: #2d2d2d; border-radius: 8px; }"
        )
        self._load_icon()
        header.addWidget(self._icon_label)

        title_area = QVBoxLayout()
        title_area.setSpacing(4)
        title_label = SubtitleLabel(entry.display_name)
        title_label.setWordWrap(True)
        title_area.addWidget(title_label)

        platform_label = CaptionLabel(t("detail.platform_id", platform=entry.platform.upper(), game_id=entry.game_id))
        title_area.addWidget(platform_label)

        if entry.rom_info:
            if entry.rom_info.publisher:
                title_area.addWidget(CaptionLabel(t("detail.publisher", publisher=entry.rom_info.publisher)))
            if entry.rom_info.region:
                title_area.addWidget(CaptionLabel(t("detail.region", region=entry.rom_info.region)))

        title_area.addStretch()
        header.addLayout(title_area, 1)
        layout.addLayout(header)

        # ── Scrollable content ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(300)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(12)

        # ROM file info card
        rom_card = self._make_card(t("detail.rom_file_info"))
        rom_form = QFormLayout()
        rom_form.setSpacing(6)
        rom_form.addRow(t("detail.file_path"), self._val_label(entry.rom_path))
        rom_form.addRow(t("detail.file_size"), self._val_label(self._format_size(entry.file_size)))
        if entry.hash_crc32:
            rom_form.addRow("CRC32:", self._val_label(entry.hash_crc32))
        if entry.added_at:
            rom_form.addRow(t("detail.added_time"), self._val_label(entry.added_at[:19].replace("T", " ")))

        status_text = {"none": t("detail.status_none"), "partial": t("detail.status_partial"), "done": t("detail.status_done")}.get(
            entry.scrape_status, entry.scrape_status
        )
        rom_form.addRow(t("detail.scrape_status"), self._val_label(status_text))

        rom_card.layout().addLayout(rom_form)
        scroll_layout.addWidget(rom_card)

        # ROM embedded info card
        if entry.rom_info:
            ri = entry.rom_info
            embed_card = self._make_card(t("detail.rom_info_card"))
            embed_form = QFormLayout()
            embed_form.setSpacing(6)

            if ri.title_name:
                embed_form.addRow(t("detail.original_title"), self._val_label(ri.title_name))
            if ri.title_name_en:
                embed_form.addRow(t("detail.en_title"), self._val_label(ri.title_name_en))
            if ri.title_name_zh:
                embed_form.addRow(t("detail.zh_title"), self._val_label(ri.title_name_zh))
            if ri.title_name_ja:
                embed_form.addRow(t("detail.ja_title"), self._val_label(ri.title_name_ja))
            if ri.title_id:
                embed_form.addRow("Title ID:", self._val_label(ri.title_id))
            if ri.content_type:
                embed_form.addRow(t("detail.format"), self._val_label(ri.content_type.upper()))
            if ri.file_type:
                embed_form.addRow(t("detail.type"), self._val_label(ri.file_type))
            if ri.version:
                embed_form.addRow(t("detail.version"), self._val_label(ri.version))
            if ri.region:
                embed_form.addRow(t("detail.region_label"), self._val_label(ri.region))
            if ri.languages:
                embed_form.addRow(t("detail.language"), self._val_label(ri.languages))

            embed_card.layout().addLayout(embed_form)
            scroll_layout.addWidget(embed_card)

        # Scraped metadata card
        scrape_result = self._load_scrape_result()
        if scrape_result:
            scrape_card = self._make_card(t("detail.scrape_info_card"))
            scrape_form = QFormLayout()
            scrape_form.setSpacing(6)

            if scrape_result.title:
                scrape_form.addRow(t("detail.title"), self._val_label(scrape_result.title))
            if scrape_result.developer:
                scrape_form.addRow(t("detail.developer"), self._val_label(scrape_result.developer))
            if scrape_result.publisher:
                scrape_form.addRow(t("detail.publisher_label"), self._val_label(scrape_result.publisher))
            if scrape_result.genre:
                scrape_form.addRow(t("detail.genre"), self._val_label(scrape_result.genre))
            if scrape_result.release_date:
                scrape_form.addRow(t("detail.release_date"), self._val_label(scrape_result.release_date))
            if scrape_result.series:
                scrape_form.addRow(t("detail.series"), self._val_label(scrape_result.series))
            if scrape_result.age_rating:
                scrape_form.addRow(t("detail.age_rating"), self._val_label(scrape_result.age_rating))
            if scrape_result.rating is not None:
                scrape_form.addRow(t("detail.rating"), self._val_label(f"{scrape_result.rating:.1f}"))
            if scrape_result.tags:
                scrape_form.addRow(t("detail.tags"), self._val_label(", ".join(scrape_result.tags)))
            scrape_form.addRow(t("detail.source"), self._val_label(scrape_result.provider))

            scrape_card.layout().addLayout(scrape_form)

            # Overview / description
            if scrape_result.overview:
                overview_label = QLabel(t("detail.description"))
                overview_label.setStyleSheet("font-weight: bold;")
                scrape_card.layout().addWidget(overview_label)

                overview_text = TextEdit()
                overview_text.setPlainText(scrape_result.overview)
                overview_text.setReadOnly(True)
                overview_text.setMaximumHeight(150)
                scrape_card.layout().addWidget(overview_text)

            # Boxart
            if scrape_result.boxart_local:
                boxart_path = Path(scrape_result.boxart_local)
                if boxart_path.exists():
                    boxart_label = QLabel(t("detail.cover"))
                    boxart_label.setStyleSheet("font-weight: bold;")
                    scrape_card.layout().addWidget(boxart_label)

                    img_label = QLabel()
                    pixmap = QPixmap(str(boxart_path))
                    if not pixmap.isNull():
                        pixmap = pixmap.scaled(
                            200, 280,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        img_label.setPixmap(pixmap)
                    scrape_card.layout().addWidget(img_label)

            scroll_layout.addWidget(scrape_card)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        self.viewLayout.addLayout(layout)

    def _load_icon(self) -> None:
        """Try to load the game icon from cache."""
        icon_path = self._ctx.icon_provider.get_icon_path(
            self._entry.platform, self._entry.game_id
        )
        if icon_path and icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    128, 128,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._icon_label.setPixmap(pixmap)
                return

        # Fallback: show placeholder text
        self._icon_label.setText(t("detail.no_icon"))
        self._icon_label.setStyleSheet(
            "QLabel { background: #2d2d2d; border-radius: 8px; color: #888; font-size: 14px; }"
        )

    def _load_scrape_result(self) -> ScrapeResult | None:
        """Load the best available scrape result from cache."""
        for provider in ("igdb", "screenscraper"):
            result = self._ctx.scrape_cache.get_provider(
                self._entry.platform, self._entry.game_id, provider
            )
            if result:
                return result
        return None

    @staticmethod
    def _make_card(title: str) -> CardWidget:
        """Create a titled card widget."""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        label = SubtitleLabel(title)
        label.setStyleSheet("font-size: 14px;")
        card_layout.addWidget(label)
        return card

    @staticmethod
    def _val_label(text: str) -> BodyLabel:
        label = BodyLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        return label

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        elif size < 1024 ** 2:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 ** 3:
            return f"{size / 1024 ** 2:.1f} MB"
        else:
            return f"{size / 1024 ** 3:.2f} GB"
