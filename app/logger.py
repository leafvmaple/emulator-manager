"""Loguru-based logging setup."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def setup_logger(log_dir: Path | None = None) -> None:
    """Configure loguru with console + rotating file output."""
    logger.remove()

    # Console
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}",
        colorize=True,
    )

    # File
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            str(log_dir / "emulator-manager.log"),
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {name}:{line} | {message}",
            rotation="5 MB",
            retention="7 days",
            encoding="utf-8",
        )
