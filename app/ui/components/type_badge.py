"""TypeBadge component — reusable colored badge for file/content types."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget

# Preset colors for common types
_TYPE_COLORS: dict[str, str] = {
    "base": "#0078D4",
    "update": "#107C10",
    "dlc": "#E74856",
    "nsp": "#0063B1",
    "xci": "#7A7574",
    "nsz": "#2D7D9A",
    "xcz": "#767676",
    "nro": "#C239B3",
    "memcard": "#D83B01",
    "battery": "#107C10",
    "savestate": "#0078D4",
    "folder": "#FFB900",
}


class TypeBadge(QWidget):
    """A small colored badge displaying a type label."""

    def __init__(
        self,
        label: str,
        color: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label = label.upper()
        self._color = QColor(color or _TYPE_COLORS.get(label.lower(), "#666666"))
        self.setFixedHeight(20)
        self.setMinimumWidth(36)

        # Calculate width based on text
        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(self._label)
        self.setFixedWidth(text_width + 16)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw rounded rectangle background
        painter.setBrush(self._color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 4, 4)

        # Draw text
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._label)

        painter.end()
