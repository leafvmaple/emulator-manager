"""Restore manager — restore saves from backups with atomic file operations."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from app.core.path_resolver import from_portable_path
from app.models.backup_record import BackupRecord


@dataclass
class FileChange:
    """Information about a file that will be restored."""

    source_zip_path: str
    destination: Path
    exists_locally: bool = False
    local_modified: float = 0.0
    backup_modified: float = 0.0
    is_newer_locally: bool = False


@dataclass
class RestoreResult:
    """Result of a restore operation."""

    success: bool = True
    restored_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str = ""


class RestoreManager:
    """Restore saves from backup ZIPs with preview and atomic operations."""

    def preview_restore(self, record: BackupRecord) -> list[FileChange]:
        """Preview what files will be restored and check for conflicts."""
        changes: list[FileChange] = []
        zip_path = Path(record.zip_path)
        meta_path = Path(record.meta_path)

        if not zip_path.exists() or not meta_path.exists():
            return changes

        import json

        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

        for bp in meta.get("backup_paths", []):
            dest = from_portable_path(bp["source"])
            change = FileChange(
                source_zip_path=bp["zip_path"],
                destination=dest,
                exists_locally=dest.exists(),
            )
            if dest.exists() and dest.is_file():
                change.local_modified = dest.stat().st_mtime
                change.backup_modified = record.created_at.timestamp()
                change.is_newer_locally = change.local_modified > change.backup_modified
            changes.append(change)

        return changes

    def restore_backup(
        self,
        record: BackupRecord,
        force: bool = False,
    ) -> RestoreResult:
        """
        Restore a backup to its original locations.

        Uses atomic restore: extracts to temp dir first, then moves files.
        When force=False, skips files that are newer locally.
        """
        result = RestoreResult()
        zip_path = Path(record.zip_path)
        meta_path = Path(record.meta_path)

        if not zip_path.exists():
            result.success = False
            result.error = f"Backup ZIP not found: {zip_path}"
            return result

        if not meta_path.exists():
            result.success = False
            result.error = f"Backup metadata not found: {meta_path}"
            return result

        import json

        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

        backup_paths = meta.get("backup_paths", [])

        # Phase 1: Extract to temporary directory
        with tempfile.TemporaryDirectory(prefix="emu_restore_") as tmp_dir:
            tmp = Path(tmp_dir)
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(tmp)
            except zipfile.BadZipFile as e:
                result.success = False
                result.error = f"Corrupt backup ZIP: {e}"
                return result

            # Phase 2: Move files to destinations
            for bp in backup_paths:
                dest = from_portable_path(bp["source"])
                extracted = tmp / bp["zip_path"]

                if not extracted.exists():
                    result.warnings.append(f"Missing in archive: {bp['zip_path']}")
                    continue

                # Check force flag
                if not force and dest.exists():
                    if dest.is_file():
                        local_mtime = dest.stat().st_mtime
                        backup_mtime = record.created_at.timestamp()
                        if local_mtime > backup_mtime:
                            result.skipped_files.append(str(dest))
                            result.warnings.append(
                                f"Skipped (local is newer): {dest.name}"
                            )
                            continue

                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if bp.get("is_dir", False):
                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.copytree(extracted, dest)
                    else:
                        shutil.copy2(extracted, dest)
                    result.restored_files.append(str(dest))
                except OSError as e:
                    result.warnings.append(f"Failed to restore {dest.name}: {e}")
                    logger.error(f"Restore error for {dest}: {e}")

        if not result.restored_files and not result.error:
            if result.skipped_files:
                result.warnings.append("All files skipped — local saves are newer")
            else:
                result.success = False
                result.error = "No files were restored"

        logger.info(
            f"Restored {len(result.restored_files)} files from {zip_path.name}, "
            f"{len(result.skipped_files)} skipped"
        )
        return result
