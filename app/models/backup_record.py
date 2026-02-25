"""Backup record models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BackupPathInfo:
    """Information about a single backed-up file within a ZIP."""

    source: str  # Original path (portable format with ${DOCUMENTS} etc.)
    save_type: str
    zip_path: str  # Path inside the ZIP
    is_dir: bool = False


@dataclass
class BackupInfo:
    """Sidecar metadata for a backup ZIP (written as JSON)."""

    game_name: str  # Unified with GameSave.game_name
    game_id: str
    emulator: str
    platform: str
    crc32: str = ""
    source_machine: str = ""
    backup_paths: list[BackupPathInfo] = field(default_factory=list)


@dataclass
class BackupRecord:
    """In-memory representation of a discovered backup."""

    zip_path: str
    meta_path: str
    emulator: str
    game_id: str
    game_name: str = ""
    platform: str = ""
    crc32: str = ""
    version: int = 0
    size: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    is_pinned: bool = False
    pin_label: str = ""
    source_machine: str = ""
