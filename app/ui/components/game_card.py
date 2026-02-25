"""GameCard — horizontal card component for displaying a ROM entry.

Styled after leafvmaple/emulator-save-manager: full-width CardWidget with
icon on the left, title + badges + meta in the centre, and action buttons
on the right.  Used inside a vertical scrollable list.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor, QBrush, QLinearGradient, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CardWidget,
    CaptionLabel,
    StrongBodyLabel,
    TransparentToolButton,
    FluentIcon as FIF,
    setFont,
)

if TYPE_CHECKING:
    from app.context import AppContext
    from app.models.rom_entry import RomEntry

from app.i18n import t

# ── Platform colours ────────────────────────────────────────────────────
_PLATFORM_COLORS: dict[str, str] = {
    "switch": "#e60012",
    "gba": "#4a2d82",
    "gbc": "#8b008b",
    "gb": "#2e8b57",
    "nds": "#333333",
    "3ds": "#ce0f2d",
    "n64": "#006400",
    "snes": "#7b2d8b",
    "nes": "#c41e3a",
    "ps2": "#003087",
    "ps1": "#003087",
    "psp": "#003087",
    "genesis": "#1a1a2e",
    "megadrive": "#1a1a2e",
}

# ── Status labels ─────────────────────────────────────────────────────
def _get_status_map() -> dict[str, tuple[str, str]]:
    return {
        "done":    (t("card.scraped"), "#107c10"),
        "partial": (t("card.partial"),  "#ff8c00"),
        "none":    (t("card.not_scraped"), "#888888"),
    }


class _PlatformBadge(QLabel):
    """Small coloured pill showing the platform name."""

    def __init__(self, platform: str, parent: QWidget | None = None) -> None:
        super().__init__(platform.upper(), parent)
        color = _PLATFORM_COLORS.get(platform.lower(), "#555")
        self.setStyleSheet(
            f"background:{color}; color:#ffffff; border-radius:3px;"
            f" padding:1px 6px; font-size:10px; font-weight:bold;"
        )
        self.setFixedHeight(18)


class _StatusBadge(QLabel):
    """Small coloured pill for scrape status."""

    def __init__(self, status: str, parent: QWidget | None = None) -> None:
        text, color = _get_status_map().get(status, (t("card.not_scraped"), "#888"))
        super().__init__(text, parent)
        self.setStyleSheet(
            f"background:{color}; color:#ffffff; border-radius:3px;"
            f" padding:1px 6px; font-size:10px; font-weight:bold;"
        )
        self.setFixedHeight(18)


# ── Helpers ─────────────────────────────────────────────────────────────

def _format_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{size_bytes} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} TB"


# ── Card ────────────────────────────────────────────────────────────────

class GameCard(CardWidget):
    """Full-width horizontal card representing one ROM entry.

    Layout::

        ┌──────┬─────────────────────────────────────────┬────────┐
        │ Icon │  Title   [Platform] [Status]            │  📂  ℹ │
        │      │  ID: xxxx  |  Size: 12 MB  |  CRC: xxx │        │
        └──────┴─────────────────────────────────────────┴────────┘
    """

    ICON_WIDTH = 48
    ICON_MAX_HEIGHT = 64

    clicked = Signal(object)        # RomEntry
    doubleClicked = Signal(object)  # RomEntry

    def __init__(
        self,
        ctx: "AppContext",
        entry: "RomEntry",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._entry = entry
        self._selected = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 10)
        root.setSpacing(14)

        # ── Icon ──
        self._icon_label = QLabel(self)
        self._icon_label.setFixedWidth(self.ICON_WIDTH)
        self._icon_label.setMaximumHeight(self.ICON_MAX_HEIGHT)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_icon()
        root.addWidget(self._icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        # ── Info column ──
        info = QVBoxLayout()
        info.setSpacing(4)
        info.setContentsMargins(0, 0, 0, 0)

        # Row 1: title + badges
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self._title_label = StrongBodyLabel(entry.display_name, self)
        setFont(self._title_label, 13, QFont.Weight.DemiBold)
        row1.addWidget(self._title_label)

        row1.addWidget(_PlatformBadge(entry.platform, self))
        row1.addWidget(_StatusBadge(entry.scrape_status or "none", self))
        row1.addStretch()
        info.addLayout(row1)

        # Row 2: metadata
        row2 = QHBoxLayout()
        row2.setSpacing(14)

        row2.addWidget(CaptionLabel(f"ID: {entry.game_id}", self))

        if entry.file_size:
            row2.addWidget(CaptionLabel(_format_size(entry.file_size), self))

        if entry.hash_crc32:
            crc_lbl = CaptionLabel(f"CRC32: {entry.hash_crc32}", self)
            crc_lbl.setStyleSheet("color:#0078d4;")
            row2.addWidget(crc_lbl)

        # ROM-embedded publisher
        if entry.rom_info and entry.rom_info.publisher:
            row2.addWidget(CaptionLabel(entry.rom_info.publisher, self))

        row2.addStretch()
        info.addLayout(row2)

        root.addLayout(info, 1)

        # ── Action buttons ──
        open_btn = TransparentToolButton(FIF.FOLDER, self)
        open_btn.setFixedSize(32, 32)
        open_btn.setToolTip(t("card.open_folder"))
        open_btn.clicked.connect(self._open_folder)
        root.addWidget(open_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        detail_btn = TransparentToolButton(FIF.INFO, self)
        detail_btn.setFixedSize(32, 32)
        detail_btn.setToolTip(t("card.view_detail"))
        detail_btn.clicked.connect(lambda: self.doubleClicked.emit(self._entry))
        root.addWidget(detail_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    # ── Properties ──

    @property
    def entry(self) -> "RomEntry":
        return self._entry

    @property
    def selected(self) -> bool:
        return self._selected

    @selected.setter
    def selected(self, value: bool) -> None:
        self._selected = value
        if value:
            self.setStyleSheet("GameCard { border: 1px solid #0078d4; }")
        else:
            self.setStyleSheet("")

    # ── Icon loading ──

    def _load_icon(self) -> None:
        """Load cover art from cache → boxart → embedded icon → fallback."""
        pixmap: QPixmap | None = None

        # 1. Cached icon
        icon_path = self._ctx.icon_provider.get_icon_path(
            self._entry.platform, self._entry.game_id,
        )
        if icon_path and icon_path.exists():
            pixmap = QPixmap(str(icon_path))

        # 2. Cached boxart
        if pixmap is None or pixmap.isNull():
            boxart_path = self._ctx.icon_provider.get_icon_path(
                self._entry.platform, f"{self._entry.game_id}_boxart",
            )
            if boxart_path and boxart_path.exists():
                pixmap = QPixmap(str(boxart_path))

        # 3. ROM-embedded icon
        if (pixmap is None or pixmap.isNull()) and self._entry.rom_info and self._entry.rom_info.icon_path:
            p = Path(self._entry.rom_info.icon_path)
            if p.exists():
                pixmap = QPixmap(str(p))

        if pixmap is not None and not pixmap.isNull():
            scaled = pixmap.scaled(
                self.ICON_WIDTH, self.ICON_MAX_HEIGHT,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._icon_label.setPixmap(scaled)
        else:
            self._set_fallback_icon()

    def _set_fallback_icon(self) -> None:
        """Generate a placeholder icon with the first character."""
        w, h = self.ICON_WIDTH, self.ICON_MAX_HEIGHT
        pixmap = QPixmap(w, h)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        hue = hash(self._entry.game_id) % 360
        c1 = QColor.fromHsl(hue, 120, 60)
        c2 = QColor.fromHsl((hue + 40) % 360, 100, 40)
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0, c1)
        grad.setColorAt(1, c2)
        painter.fillRect(0, 0, w, h, QBrush(grad))

        char = (self._entry.display_name or "?")[0].upper()
        font = QFont("Segoe UI", 22, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QPen(QColor(255, 255, 255, 200)))
        painter.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, char)
        painter.end()

        self._icon_label.setPixmap(pixmap)

    def refresh(self) -> None:
        """Refresh display from entry data."""
        self._title_label.setText(self._entry.display_name)
        self._load_icon()

    def update_icon(self, pm: QPixmap) -> None:
        """Replace the icon with a supplied pixmap."""
        scaled = pm.scaled(
            self.ICON_WIDTH, self.ICON_MAX_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._icon_label.setPixmap(scaled)

    # ── Events ──

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._entry)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit(self._entry)
        super().mouseDoubleClickEvent(event)

    # ── Helpers ──

    def _open_folder(self) -> None:
        """Open the folder containing this ROM file."""
        folder = str(Path(self._entry.rom_path).parent)
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])  # noqa: S603
        else:
            subprocess.Popen(["xdg-open", folder])  # noqa: S603
