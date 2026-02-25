"""Shared utility functions."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

ILLEGAL_FILENAME_CHARS = '<>:"/\\|?*'


def format_size(size_bytes: int) -> str:
    """Format byte count to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def open_folder(path: str | Path) -> None:
    """Open a folder in the system file manager."""
    path = Path(path)
    target = path if path.is_dir() else path.parent

    system = platform.system()
    if system == "Windows":
        os.startfile(str(target))  # noqa: S606
    elif system == "Darwin":
        subprocess.Popen(["open", str(target)])  # noqa: S603, S607
    else:
        subprocess.Popen(["xdg-open", str(target)])  # noqa: S603, S607


def sanitize_filename(name: str) -> str:
    """Remove or replace illegal filename characters."""
    for ch in ILLEGAL_FILENAME_CHARS:
        name = name.replace(ch, "_")
    name = name.replace("\n", " ").replace("\r", "").strip()
    # Collapse multiple underscores / spaces
    while "  " in name:
        name = name.replace("  ", " ")
    while "__" in name:
        name = name.replace("__", "_")
    return name.strip(". ")
