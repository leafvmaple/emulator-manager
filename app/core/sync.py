"""Sync manager — multi-device save synchronization via shared folder."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from app.config import Config
    from app.core.backup import BackupQueryProtocol


@dataclass
class SyncManifestEntry:
    """Tracks per-game sync state."""

    emulator: str
    game_id: str
    last_sync: str  # ISO datetime
    source_machine: str
    file_hash: str  # SHA-256 of the ZIP
    crc32: str = ""


@dataclass
class ConflictInfo:
    """Information about a sync conflict."""

    emulator: str
    game_id: str
    game_name: str
    local_hash: str
    remote_hash: str
    local_time: str
    remote_time: str
    remote_machine: str


class ConflictResolution:
    USE_LOCAL = "use_local"
    USE_REMOTE = "use_remote"
    KEEP_BOTH = "keep_both"
    SKIP = "skip"


@dataclass
class SyncResult:
    """Result of a sync operation."""

    pushed: int = 0
    pulled: int = 0
    conflicts: list[ConflictInfo] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class SyncManager:
    """
    Multi-device save sync via a shared folder (OneDrive, Google Drive, etc.).

    Directory structure:
      {sync_folder}/emulator-save-manager/{emulator}/{game_id}/
        ├── {timestamp}.zip
        └── {timestamp}.json
      {sync_folder}/emulator-save-manager/sync_manifest.json
    """

    def __init__(self, config: Config, backup_query: BackupQueryProtocol) -> None:
        self._config = config
        self._backup_query = backup_query

    @property
    def sync_root(self) -> Path | None:
        sf = self._config.sync_folder
        if sf is None or not sf.exists():
            return None
        return sf / "emulator-save-manager"

    @property
    def is_configured(self) -> bool:
        return self.sync_root is not None

    def _manifest_path(self) -> Path | None:
        root = self.sync_root
        if root is None:
            return None
        return root / "sync_manifest.json"

    def _read_manifest(self) -> dict[str, SyncManifestEntry]:
        """Read the sync manifest."""
        path = self._manifest_path()
        if path is None or not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return {
                key: SyncManifestEntry(**entry) for key, entry in data.items()
            }
        except (json.JSONDecodeError, OSError, TypeError) as e:
            logger.warning(f"Failed to read sync manifest: {e}")
            return {}

    def _write_manifest(self, entries: dict[str, SyncManifestEntry]) -> None:
        """Write the sync manifest."""
        path = self._manifest_path()
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        from dataclasses import asdict

        data = {key: asdict(entry) for key, entry in entries.items()}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error(f"Failed to write sync manifest: {e}")

    @staticmethod
    def _file_hash(path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def push(self, emulator: str, game_id: str) -> SyncResult:
        """Push local backups to sync folder."""
        result = SyncResult()
        root = self.sync_root
        if root is None:
            result.errors.append("Sync folder not configured")
            return result

        local_backups = self._backup_query.list_backups(emulator, game_id)
        if not local_backups:
            return result

        sync_dir = root / emulator / game_id
        sync_dir.mkdir(parents=True, exist_ok=True)

        # Copy the newest backup
        newest = local_backups[0]
        src_zip = Path(newest.zip_path)
        src_meta = Path(newest.meta_path)

        if src_zip.exists():
            dst_zip = sync_dir / src_zip.name
            dst_meta = sync_dir / src_meta.name
            if not dst_zip.exists() or self._file_hash(src_zip) != self._file_hash(dst_zip):
                shutil.copy2(src_zip, dst_zip)
                if src_meta.exists():
                    shutil.copy2(src_meta, dst_meta)
                result.pushed += 1

                # Update manifest
                manifest = self._read_manifest()
                key = f"{emulator}:{game_id}"
                manifest[key] = SyncManifestEntry(
                    emulator=emulator,
                    game_id=game_id,
                    last_sync=datetime.now(tz=timezone.utc).isoformat(),
                    source_machine=self._config.machine_id,
                    file_hash=self._file_hash(dst_zip),
                    crc32=newest.crc32,
                )
                self._write_manifest(manifest)

        return result

    def pull(self, emulator: str, game_id: str) -> SyncResult:
        """Pull remote backups from sync folder to local."""
        result = SyncResult()
        root = self.sync_root
        if root is None:
            result.errors.append("Sync folder not configured")
            return result

        backup_root = self._backup_query.backup_root
        if backup_root is None:
            result.errors.append("Local backup path not configured")
            return result

        sync_dir = root / emulator / game_id
        if not sync_dir.exists():
            return result

        local_dir = backup_root / emulator / game_id
        local_dir.mkdir(parents=True, exist_ok=True)

        for zip_file in sorted(sync_dir.glob("*.zip"), reverse=True):
            local_zip = local_dir / zip_file.name
            if not local_zip.exists():
                shutil.copy2(zip_file, local_zip)
                meta_file = zip_file.with_suffix(".json")
                if meta_file.exists():
                    shutil.copy2(meta_file, local_dir / meta_file.name)
                result.pulled += 1
                break  # Only pull the newest

        return result

    def sync_all(self) -> SyncResult:
        """Push and pull all backups."""
        result = SyncResult()
        if not self.is_configured:
            result.errors.append("Sync folder not configured")
            return result

        all_backups = self._backup_query.list_all_backups()
        for emulator, games in all_backups.items():
            for game_id in games:
                try:
                    push_result = self.push(emulator, game_id)
                    result.pushed += push_result.pushed
                    result.conflicts.extend(push_result.conflicts)
                except Exception as e:
                    result.errors.append(f"Push {emulator}/{game_id}: {e}")

        # Also pull anything in sync folder that we don't have locally
        root = self.sync_root
        if root and root.exists():
            for emu_dir in root.iterdir():
                if not emu_dir.is_dir() or emu_dir.name == "sync_manifest.json":
                    continue
                for game_dir in emu_dir.iterdir():
                    if not game_dir.is_dir():
                        continue
                    try:
                        pull_result = self.pull(emu_dir.name, game_dir.name)
                        result.pulled += pull_result.pulled
                    except Exception as e:
                        result.errors.append(
                            f"Pull {emu_dir.name}/{game_dir.name}: {e}"
                        )

        return result
