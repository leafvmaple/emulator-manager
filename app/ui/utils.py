"""UI utility functions — shared helpers for the UI layer."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget
from qfluentwidgets import InfoBar, InfoBarPosition


def show_success(parent: QWidget, title: str, content: str = "") -> None:
    """Show a success InfoBar."""
    InfoBar.success(
        title=title,
        content=content,
        orient=1,  # Vertical
        isClosable=True,
        position=InfoBarPosition.TOP_RIGHT,
        duration=3000,
        parent=parent,
    )


def show_error(parent: QWidget, title: str, content: str = "") -> None:
    """Show an error InfoBar."""
    InfoBar.error(
        title=title,
        content=content,
        orient=1,
        isClosable=True,
        position=InfoBarPosition.TOP_RIGHT,
        duration=5000,
        parent=parent,
    )


def show_warning(parent: QWidget, title: str, content: str = "") -> None:
    """Show a warning InfoBar."""
    InfoBar.warning(
        title=title,
        content=content,
        orient=1,
        isClosable=True,
        position=InfoBarPosition.TOP_RIGHT,
        duration=4000,
        parent=parent,
    )


def show_info(parent: QWidget, title: str, content: str = "") -> None:
    """Show an info InfoBar."""
    InfoBar.info(
        title=title,
        content=content,
        orient=1,
        isClosable=True,
        position=InfoBarPosition.TOP_RIGHT,
        duration=3000,
        parent=parent,
    )
