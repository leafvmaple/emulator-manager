"""Tests for the BackupManager."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.backup import BackupManager
from app.models.game_save import GameSave, SaveFile, SaveType


@pytest.fixture
def tmp_config(tmp_path: Path):
    """Create a mock Config pointing to a temp directory."""
    config = MagicMock()
    config.backup_path = tmp_path / "backups"
    config.data_dir = tmp_path
    config.max_backups = 5
    config.machine_id = "test-machine"
    return config


@pytest.fixture
def manager(tmp_config) -> BackupManager:
    return BackupManager(tmp_config)


@pytest.fixture
def sample_save(tmp_path: Path) -> GameSave:
    """Create a sample save with a real file."""
    save_dir = tmp_path / "saves"
    save_dir.mkdir()
    save_file = save_dir / "save.dat"
    save_file.write_bytes(b"save data content")

    return GameSave(
        game_id="GAME001",
        game_name="Test Game",
        emulator="test_emu",
        platform="switch",
        files=[
            SaveFile(
                path=str(save_file),
                save_type=SaveType.FILE,
                size=save_file.stat().st_size,
            )
        ],
    )


class TestBackupCreation:
    def test_creates_zip_and_sidecar(self, manager: BackupManager, sample_save: GameSave) -> None:
        record = manager.create_backup(sample_save)
        assert Path(record.zip_path).exists()
        assert Path(record.meta_path).exists()

    def test_zip_contains_save_file(self, manager: BackupManager, sample_save: GameSave) -> None:
        import zipfile

        record = manager.create_backup(sample_save)
        with zipfile.ZipFile(record.zip_path) as zf:
            names = zf.namelist()
            assert any("save.dat" in n for n in names)

    def test_sidecar_has_correct_metadata(self, manager: BackupManager, sample_save: GameSave) -> None:
        record = manager.create_backup(sample_save)
        with open(record.meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["game_name"] == "Test Game"
        assert meta["emulator"] == "test_emu"


class TestBackupListing:
    def test_list_empty(self, manager: BackupManager) -> None:
        result = manager.list_backups("nonexistent", "game1")
        assert result == []

    def test_list_after_backup(self, manager: BackupManager, sample_save: GameSave) -> None:
        manager.create_backup(sample_save)
        result = manager.list_backups("test_emu", "GAME001")
        assert len(result) == 1
        assert result[0].game_name == "Test Game"
        assert result[0].version == 1

    def test_version_numbering(self, manager: BackupManager, sample_save: GameSave) -> None:
        for _ in range(3):
            manager.create_backup(sample_save)
        result = manager.list_backups("test_emu", "GAME001")
        assert len(result) == 3
        # Newest first, version numbers: oldest=1, newest=3
        assert result[0].version == 3
        assert result[2].version == 1
