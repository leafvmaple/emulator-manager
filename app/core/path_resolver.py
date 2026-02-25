"""Portable path resolver — replace machine-specific paths with placeholders."""

from __future__ import annotations

import os
import platform
from pathlib import Path

# Placeholder tokens
_PLACEHOLDERS = {
    "${DOCUMENTS}": None,  # Resolved at runtime
    "${APPDATA}": None,
    "${LOCALAPPDATA}": None,
    "${HOME}": None,
}


def _get_documents_path() -> Path:
    """Get the real Documents path (handles relocated folders on Windows)."""
    if platform.system() == "Windows":
        try:
            import ctypes.wintypes

            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            # CSIDL_PERSONAL = 0x0005
            ctypes.windll.shell32.SHGetFolderPathW(None, 0x0005, None, 0, buf)  # type: ignore[union-attr]
            return Path(buf.value)
        except Exception:
            pass
    return Path.home() / "Documents"


def _resolve_placeholders() -> dict[str, Path]:
    """Build the placeholder-to-path mapping for the current system."""
    return {
        "${DOCUMENTS}": _get_documents_path(),
        "${APPDATA}": Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))),
        "${LOCALAPPDATA}": Path(
            os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        ),
        "${HOME}": Path.home(),
    }


def to_portable_path(path: str | Path) -> str:
    """Convert an absolute path to a portable path string with placeholders."""
    path_str = str(Path(path).resolve())
    mapping = _resolve_placeholders()
    # Sort by longest path first to get the most specific match
    sorted_items = sorted(mapping.items(), key=lambda x: len(str(x[1])), reverse=True)
    for placeholder, resolved in sorted_items:
        resolved_str = str(resolved)
        if path_str.startswith(resolved_str):
            return placeholder + path_str[len(resolved_str) :]
    return path_str


def from_portable_path(portable: str) -> Path:
    """Convert a portable path string back to an absolute Path."""
    mapping = _resolve_placeholders()
    for placeholder, resolved in mapping.items():
        if portable.startswith(placeholder):
            return resolved / portable[len(placeholder) :].lstrip("/\\")
    return Path(portable)
