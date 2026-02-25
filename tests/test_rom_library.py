"""Tests for RomLibrary JSON index."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.data.rom_library import RomLibrary
from app.models.rom_entry import RomEntry


@pytest.fixture
def library(tmp_path: Path) -> RomLibrary:
    return RomLibrary(tmp_path / "rom_library.json")


@pytest.fixture
def sample_entry() -> RomEntry:
    return RomEntry(
        path="/roms/switch/zelda.nsp",
        platform="switch",
        emulator="switch",
        file_size=1024 * 1024 * 100,
        game_id="0100509005AF0000",
    )


class TestRomLibrary:
    def test_add_and_get(self, library: RomLibrary, sample_entry: RomEntry) -> None:
        library.add_entry(sample_entry)
        result = library.get("0100509005AF0000", "switch")
        assert result is not None
        assert result.path == "/roms/switch/zelda.nsp"

    def test_remove(self, library: RomLibrary, sample_entry: RomEntry) -> None:
        library.add_entry(sample_entry)
        library.remove("0100509005AF0000", "switch")
        assert library.get("0100509005AF0000", "switch") is None

    def test_find_by_path(self, library: RomLibrary, sample_entry: RomEntry) -> None:
        library.add_entry(sample_entry)
        result = library.find_by_path("/roms/switch/zelda.nsp")
        assert result is not None

    def test_entries_by_platform(self, library: RomLibrary, sample_entry: RomEntry) -> None:
        library.add_entry(sample_entry)
        entries = library.entries_by_platform("switch")
        assert len(entries) == 1

    def test_persistence(self, tmp_path: Path, sample_entry: RomEntry) -> None:
        path = tmp_path / "rom_library.json"
        lib1 = RomLibrary(path)
        lib1.add_entry(sample_entry)

        # Reload
        lib2 = RomLibrary(path)
        result = lib2.get("0100509005AF0000", "switch")
        assert result is not None
