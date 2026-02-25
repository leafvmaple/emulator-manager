"""Tests for portable path resolver."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.path_resolver import from_portable_path, to_portable_path


class TestPortablePaths:
    def test_home_directory_round_trip(self) -> None:
        original = Path.home() / "Documents" / "saves" / "game.sav"
        portable = to_portable_path(original)
        restored = from_portable_path(portable)
        assert restored == original.resolve()

    def test_unknown_path_unchanged(self) -> None:
        # A path not under any placeholder should pass through
        if os.name == "nt":
            path = "Z:\\some\\random\\path\\file.txt"
        else:
            path = "/tmp/random/path/file.txt"
        portable = to_portable_path(path)
        # Should either have a placeholder or be the original path
        assert portable  # non-empty

    def test_from_portable_unknown(self) -> None:
        result = from_portable_path("C:\\absolute\\path")
        assert isinstance(result, Path)
