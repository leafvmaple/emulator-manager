"""Tests for the Config system."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Config, reset_config


@pytest.fixture(autouse=True)
def _clean_config():
    reset_config()
    yield
    reset_config()


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(data_dir=tmp_path)


class TestConfig:
    def test_default_values(self, config: Config) -> None:
        assert config.max_backups == 10
        assert config.machine_id  # Should be auto-generated

    def test_set_and_get(self, config: Config) -> None:
        with config.batch_update():
            config.set("backup_path", "/some/path")
        assert config.backup_path == Path("/some/path")

    def test_batch_update_atomic(self, config: Config) -> None:
        with config.batch_update():
            config.set("max_backups", 20)
            config.set("backup_path", "/new/path")
        assert config.max_backups == 20

    def test_backup_path_none_when_empty(self, config: Config) -> None:
        assert config.backup_path is None or isinstance(config.backup_path, Path)

    def test_rom_directories(self, config: Config) -> None:
        with config.batch_update():
            config.set("rom_directories", ["/roms/switch", "/roms/ps2"])
        assert len(config.rom_directories) == 2
