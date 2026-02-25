"""Emulator information model."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EmulatorInfo:
    """Detected emulator installation."""

    name: str
    install_path: Path
    data_path: Path
    supported_platforms: list[str] = field(default_factory=list)
    is_portable: bool = False
    version: str = ""
