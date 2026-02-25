"""Backup manager — versioned ZIP backups with sidecar JSON metadata."""

from __future__ import annotations

import json
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from loguru import logger

from app.core.path_resolver import to_portable_path
from app.models.backup_record import BackupInfo, BackupPathInfo, BackupRecord

if TYPE_CHECKING:
    from app.config import Config
    from app.models.game_save import GameSave, SaveFile


class BackupQueryProtocol(Protocol):
    """Read-only backup query interface for SyncManager decoupling."""

    @property
    def backup_root(self) -> Path | None: ...

    def list_backups(self, emulator: str, game_id: str) -> list[BackupRecord]: ...

    def list_all_backups(self) -> dict[str, dict[str, list[BackupRecord]]]: ...


class BackupManager:
    """Versioned ZIP backup engine. Also implements BackupQueryProtocol."""

    def __init__(self, config: Config) -> None:
        self._config = config

    @property
    def backup_root(self) -> Path | None:
        return self._config.backup_path

    def _ensure_backup_root(self) -> Path:
        root = self.backup_root
        if not root:
            root = self._config.data_dir / "backups"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _game_backup_dir(self, emulator: str, game_id: str) -> Path:
        root = self._ensure_backup_root()
        d = root / emulator / game_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def create_backup(self, game_save: GameSave) -> BackupRecord:
        """Create a versioned ZIP backup for a game save."""
        backup_dir = self._game_backup_dir(game_save.emulator, game_save.game_id)
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")

        zip_path = backup_dir / f"{timestamp}.zip"
        meta_path = backup_dir / f"{timestamp}.json"

        backup_paths = self._write_zip(game_save, zip_path)
        self._write_sidecar(game_save, meta_path, backup_paths)
        self._rotate_backups(game_save.emulator, game_save.game_id)

        record = BackupRecord(
            zip_path=str(zip_path),
            meta_path=str(meta_path),
            emulator=game_save.emulator,
            game_id=game_save.game_id,
            game_name=game_save.game_name,
            platform=game_save.platform,
            crc32=game_save.crc32,
            size=zip_path.stat().st_size,
            created_at=datetime.now(tz=timezone.utc),
            source_machine=self._config.machine_id,
        )

        logger.info(f"Created backup: {zip_path.name} for {game_save.game_name}")
        return record

    def _write_zip(self, game_save: GameSave, zip_path: Path) -> list[BackupPathInfo]:
        """Write save files into a ZIP archive."""
        backup_paths: list[BackupPathInfo] = []

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for save_file in game_save.files:
                source = Path(save_file.path)
                if source.is_dir():
                    for child in source.rglob("*"):
                        if child.is_file():
                            zip_entry = f"{save_file.save_type}/{source.name}/{child.relative_to(source)}"
                            zf.write(child, zip_entry)
                    backup_paths.append(
                        BackupPathInfo(
                            source=to_portable_path(source),
                            save_type=save_file.save_type,
                            zip_path=f"{save_file.save_type}/{source.name}",
                            is_dir=True,
                        )
                    )
                elif source.is_file():
                    zip_entry = f"{save_file.save_type}/{source.name}"
                    zf.write(source, zip_entry)
                    backup_paths.append(
                        BackupPathInfo(
                            source=to_portable_path(source),
                            save_type=save_file.save_type,
                            zip_path=zip_entry,
                            is_dir=False,
                        )
                    )

        return backup_paths

    def _write_sidecar(
        self,
        game_save: GameSave,
        meta_path: Path,
        backup_paths: list[BackupPathInfo],
    ) -> None:
        """Write sidecar JSON metadata."""
        info = BackupInfo(
            game_name=game_save.game_name,
            game_id=game_save.game_id,
            emulator=game_save.emulator,
            platform=game_save.platform,
            crc32=game_save.crc32,
            source_machine=self._config.machine_id,
            backup_paths=backup_paths,
        )
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(asdict(info), f, ensure_ascii=False, indent=2)

    def _rotate_backups(self, emulator: str, game_id: str) -> None:
        """Remove oldest non-pinned backups exceeding max_backups."""
        records = self.list_backups(emulator, game_id)
        max_backups = self._config.max_backups
        unpinned = [r for r in records if not r.is_pinned]

        while len(unpinned) > max_backups:
            oldest = unpinned.pop()  # records are newest-first, so last = oldest
            try:
                Path(oldest.zip_path).unlink(missing_ok=True)
                Path(oldest.meta_path).unlink(missing_ok=True)
                logger.debug(f"Rotated old backup: {Path(oldest.zip_path).name}")
            except OSError as e:
                logger.warning(f"Failed to rotate backup: {e}")

    def list_backups(self, emulator: str, game_id: str) -> list[BackupRecord]:
        """List all backups for a game, newest first, with version numbers assigned."""
        backup_dir = self._game_backup_dir(emulator, game_id)
        if not backup_dir.exists():
            return []

        records: list[BackupRecord] = []
        for meta_file in sorted(backup_dir.glob("*.json"), reverse=True):
            zip_file = meta_file.with_suffix(".zip")
            if not zip_file.exists():
                continue
            try:
                with open(meta_file, encoding="utf-8") as f:
                    meta = json.load(f)
                record = BackupRecord(
                    zip_path=str(zip_file),
                    meta_path=str(meta_file),
                    emulator=meta.get("emulator", emulator),
                    game_id=meta.get("game_id", game_id),
                    game_name=meta.get("game_name", ""),
                    platform=meta.get("platform", ""),
                    crc32=meta.get("crc32", ""),
                    size=zip_file.stat().st_size,
                    source_machine=meta.get("source_machine", ""),
                )
                records.append(record)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Skipping malformed backup metadata: {meta_file}: {e}")

        # Assign version numbers: oldest=1, newest=N
        for i, record in enumerate(reversed(records), start=1):
            record.version = i

        return records

    def list_all_backups(self) -> dict[str, dict[str, list[BackupRecord]]]:
        """List all backups grouped by emulator → game_id."""
        root = self._ensure_backup_root()
        result: dict[str, dict[str, list[BackupRecord]]] = {}
        if not root.exists():
            return result

        for emu_dir in root.iterdir():
            if not emu_dir.is_dir():
                continue
            emu_name = emu_dir.name
            result[emu_name] = {}
            for game_dir in emu_dir.iterdir():
                if not game_dir.is_dir():
                    continue
                game_id = game_dir.name
                records = self.list_backups(emu_name, game_id)
                if records:
                    result[emu_name][game_id] = records

        return result

    def pin_backup(self, record: BackupRecord, label: str = "") -> None:
        """Mark a backup as pinned (exempt from rotation)."""
        meta_path = Path(record.meta_path)
        if meta_path.exists():
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = json.load(f)
                meta["is_pinned"] = True
                meta["pin_label"] = label
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
                record.is_pinned = True
                record.pin_label = label
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Failed to pin backup: {e}")
