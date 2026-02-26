"""Application configuration — JSON-based, with file locking and batch update support."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from loguru import logger

_instance: "Config | None" = None

# Default data directory
_DEFAULT_DATA_DIR = Path.home() / "Documents" / "EmulatorManager"


def get_config() -> Config:
    """Module-level factory — single global Config instance."""
    global _instance
    if _instance is None:
        _instance = Config()
    return _instance


def reset_config() -> None:
    """Reset the global config instance (for testing)."""
    global _instance
    _instance = None


class Config:
    """JSON-based application configuration with file locking."""

    _DEFAULTS: dict[str, Any] = {
        "language": "zh_CN",
        "theme": "auto",
        "backup_path": "",
        "sync_folder": "",
        "max_backups": 5,
        "machine_id": "",
        "emulators": {},
        "auto_scan_on_start": False,
        "auto_sync_on_start": False,
        # ROM management
        "rom_directories": {},
        # Scraper
        "scraper": {
            "proxy_protocol": "http",
            "proxy_host": "",
            "proxy_port": "",
            "igdb_client_id": "",
            "igdb_client_secret": "",
            "screenscraper_dev_id": "",
            "screenscraper_dev_password": "",
            "screenscraper_username": "",
            "screenscraper_password": "",
            "download_artwork": True,
            "artwork_dir": "",
            "field_priority": {
                "title": ["igdb", "screenscraper"],
                "overview": ["igdb", "screenscraper"],
                "release_date": ["igdb", "screenscraper"],
                "genre": ["igdb", "screenscraper"],
                "developer": ["igdb", "screenscraper"],
                "publisher": ["igdb", "screenscraper"],
                "players": ["igdb", "screenscraper"],
                "rating": ["igdb", "screenscraper"],
                "community_score": ["igdb", "screenscraper"],
                "age_rating": ["igdb", "screenscraper"],
                "series": ["igdb", "screenscraper"],
                "tags": ["igdb", "screenscraper"],
                "boxart": ["screenscraper", "igdb"],
                "background": ["screenscraper", "igdb"],
                "icon": ["screenscraper", "igdb"],
                "screenshots": ["screenscraper", "igdb"],
            },
        },
        # Rename
        "rename": {
            "default_template": "{title_zh|title_en} [{title_id}].{ext}",
            "saved_templates": [
                {
                    "name": "Switch标准",
                    "template": "{title_zh} [{title_id}][v{version}].{ext}",
                },
                {"name": "简洁英文", "template": "{title_en}.{ext}"},
            ],
        },
    }

    def __init__(self, config_dir: Path | None = None) -> None:
        self._data: dict[str, Any] = {}
        self._dir = config_dir or _DEFAULT_DATA_DIR
        self._path = self._dir / "config.json"
        self._lock = threading.Lock()
        self._defer_save = False
        self._load()

    def _load(self) -> None:
        """Load config from disk, merging with defaults."""
        self._data = json.loads(json.dumps(self._DEFAULTS))  # deep copy defaults
        if self._path.exists():
            try:
                with open(self._path, encoding="utf-8") as f:
                    user_data = json.load(f)
                self._deep_merge(self._data, user_data)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load config, using defaults: {e}")

        # Ensure machine_id
        if not self._data.get("machine_id"):
            self._data["machine_id"] = uuid4().hex[:12]
            self._save()

    def _deep_merge(self, base: dict, override: dict) -> None:
        """Recursively merge override into base."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _save(self) -> None:
        """Persist config to disk with file locking."""
        if self._defer_save:
            return
        with self._lock:
            self._dir.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_suffix(".tmp")
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                tmp_path.replace(self._path)
            except OSError as e:
                logger.error(f"Failed to save config: {e}")
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)

    @contextmanager
    def batch_update(self) -> Iterator[None]:
        """Context manager for batching multiple config changes into a single write."""
        self._defer_save = True
        try:
            yield
        finally:
            self._defer_save = False
            self._save()

    # ── Generic access ──

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by dot-separated key path."""
        parts = key.split(".")
        node = self._data
        for part in parts:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def set(self, key: str, value: Any) -> None:
        """Set a config value by dot-separated key path."""
        parts = key.split(".")
        node = self._data
        for part in parts[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value
        self._save()

    # ── Typed properties ──

    @property
    def data_dir(self) -> Path:
        return self._dir

    @property
    def language(self) -> str:
        return self._data.get("language", "zh_CN")

    @language.setter
    def language(self, value: str) -> None:
        self.set("language", value)

    @property
    def theme(self) -> str:
        return self._data.get("theme", "auto")

    @theme.setter
    def theme(self, value: str) -> None:
        self.set("theme", value)

    @property
    def backup_path(self) -> Path | None:
        raw = self._data.get("backup_path", "")
        return Path(raw) if raw else None

    @backup_path.setter
    def backup_path(self, value: Path | None) -> None:
        self.set("backup_path", str(value) if value else "")

    @property
    def sync_folder(self) -> Path | None:
        raw = self._data.get("sync_folder", "")
        return Path(raw) if raw else None

    @sync_folder.setter
    def sync_folder(self, value: Path | None) -> None:
        self.set("sync_folder", str(value) if value else "")

    @property
    def max_backups(self) -> int:
        return int(self._data.get("max_backups", 5))

    @max_backups.setter
    def max_backups(self, value: int) -> None:
        self.set("max_backups", value)

    @property
    def machine_id(self) -> str:
        return self._data.get("machine_id", "")

    @property
    def auto_scan_on_start(self) -> bool:
        return bool(self._data.get("auto_scan_on_start", False))

    @auto_scan_on_start.setter
    def auto_scan_on_start(self, value: bool) -> None:
        self.set("auto_scan_on_start", value)

    @property
    def auto_sync_on_start(self) -> bool:
        return bool(self._data.get("auto_sync_on_start", False))

    @auto_sync_on_start.setter
    def auto_sync_on_start(self, value: bool) -> None:
        self.set("auto_sync_on_start", value)

    @property
    def rom_directories(self) -> dict[str, list[str]]:
        return self._data.get("rom_directories", {})

    @rom_directories.setter
    def rom_directories(self, value: dict[str, list[str]]) -> None:
        self.set("rom_directories", value)

    @property
    def emulators(self) -> dict[str, dict[str, Any]]:
        return self._data.get("emulators", {})

    @property
    def scraper_config(self) -> dict[str, Any]:
        return self._data.get("scraper", {})

    @property
    def rename_config(self) -> dict[str, Any]:
        return self._data.get("rename", {})

    @property
    def artwork_dir(self) -> Path:
        raw = self.scraper_config.get("artwork_dir", "")
        if raw:
            return Path(raw)
        return self._dir / "artwork"

    @property
    def field_priority(self) -> dict[str, list[str]]:
        return self.scraper_config.get("field_priority", {})
