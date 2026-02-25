"""Theme configuration — colors, fonts, and Fluent Design tokens."""

from __future__ import annotations

from qfluentwidgets import setTheme, setThemeColor, Theme


def apply_theme(dark: bool = False, accent_color: str = "#0078D4") -> None:
    """Apply the application theme."""
    setTheme(Theme.DARK if dark else Theme.LIGHT)
    setThemeColor(accent_color)
