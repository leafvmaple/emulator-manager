"""Tests for _extract_version_from_filename in rom_manager and NES plugin."""

from __future__ import annotations

import pytest

from app.core.rom_manager import RomManager
from app.plugins.nes.plugin import _extract_version_from_filename as nes_extract


@pytest.mark.parametrize(
    "stem, expected",
    [
        # Rev integer
        ("Game (Rev 1)", "1"),
        ("Game (Rev 2)", "2"),
        ("Game (rev 3)", "3"),
        # Rev decimal
        ("Game (Rev 1.1)", "1.1"),
        ("Game (Rev 2.3)", "2.3"),
        # Bracket version
        ("Game [1.1]", "1"),
        ("Game [1.2]", "2"),
        # Beta without number
        ("Game (Beta)", "beta"),
        ("Game (beta)", "beta"),
        ("Game (BETA)", "beta"),
        # Beta with number
        ("Game (Beta 1)", "beta 1"),
        ("Game (Beta 2)", "beta 2"),
        ("Game (beta 3)", "beta 3"),
        # Beta combined with Rev — special version takes priority
        ("Game (Rev 1) (Beta)", "beta"),
        # Virtual Console
        ("Game (Virtual Console)", "vc"),
        ("Game (virtual console)", "vc"),
        ("Game (VIRTUAL CONSOLE)", "vc"),
        # Virtual Console combined with Rev — special version takes priority
        ("Game (Rev 2) (Virtual Console)", "vc"),
        # Sample
        ("Game (Sample)", "sample"),
        ("Game (sample)", "sample"),
        ("Game (Rev 1) (Sample)", "sample"),
        # No match
        ("Game (USA)", ""),
        ("Plain Game Name", ""),
    ],
)
def test_rom_manager_extract_version(stem: str, expected: str) -> None:
    assert RomManager._extract_version_from_filename(stem) == expected


@pytest.mark.parametrize(
    "stem, expected",
    [
        ("Game (Rev 1)", "1"),
        ("Game (Rev 1.1)", "1.1"),
        ("Game (Beta)", "beta"),
        ("Game (Beta 1)", "beta 1"),
        ("Game (Virtual Console)", "vc"),
        ("Game (Rev 2) (Virtual Console)", "vc"),
        ("Game (Sample)", "sample"),
        ("Plain Game Name", ""),
    ],
)
def test_nes_extract_version(stem: str, expected: str) -> None:
    assert nes_extract(stem) == expected
