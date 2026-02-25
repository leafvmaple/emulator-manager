"""ROM manager — scan ROM directories, index entries, rename files."""

from __future__ import annotations

import hashlib
import zlib
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from app.config import Config
from app.core.rename_engine import RenameEngine
from app.data.rom_library import RomLibrary
from app.models.rom_entry import RomEntry, RomInfo
from app.plugins.base import GamePlugin
from app.plugins.plugin_manager import PluginManager


class RomManager:
    """
    ROM management orchestrator.

    Uses *GamePlugin* (per-platform) for ROM parsing, game-ID extraction
    and classification.  Uses *RomLibrary* for persistence and
    *RenameEngine* for template-based renaming.
    """

    def __init__(
        self,
        config: Config,
        rom_library: RomLibrary,
        plugin_manager: PluginManager,
        rename_engine: RenameEngine,
    ) -> None:
        self._config = config
        self._library = rom_library
        self._plugins = plugin_manager
        self._rename = rename_engine

    # ── Scanning ──

    def scan_directories(self) -> list[RomEntry]:
        """
        Scan all configured ROM directories and return new entries.

        ``config.rom_directories`` can be either:
          - ``dict[str, list[str]]``: ``{platform: [dir_paths]}``
          - ``list[str]``: flat list of directories (auto-detect platform)
        """
        raw: dict[str, list[str]] | list[str] = self._config.get("rom_directories", {})
        new_entries: list[RomEntry] = []

        if isinstance(raw, dict):
            # {platform: [dir_paths]} format
            for platform, dirs in raw.items():
                game_plugin = self._plugins.get_game_plugin(platform)
                if game_plugin is None:
                    logger.warning(f"No game plugin for platform '{platform}', skipping")
                    continue
                self._scan_dirs_with_plugin(dirs, game_plugin, new_entries)
        elif isinstance(raw, list):
            # Flat list — try every game plugin's extensions per file
            self._scan_dirs_auto(raw, new_entries)
        else:
            logger.warning(f"Unexpected rom_directories type: {type(raw)}")

        if new_entries:
            logger.info(f"Scan complete — {len(new_entries)} new ROM(s) indexed")
        self._library.save()
        return new_entries

    def _scan_dirs_with_plugin(
        self,
        dirs: list[str],
        game_plugin: GamePlugin,
        new_entries: list[RomEntry],
    ) -> None:
        """Scan directories using a specific game plugin."""
        extensions = set(game_plugin.get_rom_extensions())
        for dir_path in dirs:
            dir_p = Path(dir_path)
            if not dir_p.is_dir():
                logger.debug(f"ROM directory does not exist: {dir_path}")
                continue

            for file in dir_p.rglob("*"):
                if not file.is_file():
                    continue
                if file.suffix.lower() not in extensions:
                    continue

                entry = self._create_entry(file, game_plugin)
                if entry is None:
                    continue

                existing = self._library.get(entry.platform, entry.game_id)
                if existing is None:
                    self._library.add(entry)
                    new_entries.append(entry)
                    logger.debug(f"Indexed ROM: {file.name} → {entry.game_id}")
                else:
                    if entry.rom_info:
                        self._refresh_rom_info(existing, entry.rom_info)
                    if entry.hash_crc32:
                        existing.hash_crc32 = entry.hash_crc32

    def _scan_dirs_auto(
        self, dirs: list[str], new_entries: list[RomEntry]
    ) -> None:
        """Scan directories, auto-detecting platform by file extension."""
        # Build extension → GamePlugin lookup
        ext_map: dict[str, GamePlugin] = {}
        for gp in self._plugins.game_plugins:
            for ext in gp.get_rom_extensions():
                ext_map[ext.lower()] = gp

        for dir_path in dirs:
            dir_p = Path(dir_path)
            if not dir_p.is_dir():
                logger.debug(f"ROM directory does not exist: {dir_path}")
                continue

            for file in dir_p.rglob("*"):
                if not file.is_file():
                    continue
                game_plugin = ext_map.get(file.suffix.lower())
                if game_plugin is None:
                    continue

                entry = self._create_entry(file, game_plugin)
                if entry is None:
                    continue

                existing = self._library.get(entry.platform, entry.game_id)
                if existing is None:
                    self._library.add(entry)
                    new_entries.append(entry)
                    logger.debug(f"Indexed ROM: {file.name} → {entry.game_id}")
                else:
                    if entry.rom_info:
                        self._refresh_rom_info(existing, entry.rom_info)
                    if entry.hash_crc32:
                        existing.hash_crc32 = entry.hash_crc32

    # ── Entry creation ──

    def _create_entry(self, rom_path: Path, game_plugin: GamePlugin) -> RomEntry | None:
        try:
            rom_info = game_plugin.parse_rom_info(rom_path)
            game_id = game_plugin.extract_game_id(rom_path)
        except Exception as e:
            logger.warning(f"Plugin error parsing '{rom_path.name}': {e}")
            return None

        # Resolve display name
        display_name = ""
        if rom_info and rom_info.title_name:
            display_name = rom_info.title_name
        if not display_name:
            resolved = game_plugin.resolve_game_name(game_id)
            if resolved:
                display_name = resolved

        entry = RomEntry(
            rom_path=str(rom_path),
            platform=game_plugin.platform,
            emulator="",  # ROM entries are platform-scoped, not emulator-scoped
            game_id=game_id,
            file_size=rom_path.stat().st_size,
            hash_crc32=self._compute_crc32(rom_path),
            added_at=datetime.now(timezone.utc).isoformat(),
            rom_info=rom_info,
        )

        return entry

    @staticmethod
    def _refresh_rom_info(existing: RomEntry, new_info: RomInfo) -> None:
        """Update an existing entry's rom_info from a fresh parse.

        Only overwrites fields that come from the plugin (title_name, region,
        publisher, version, etc.).
        Scraper-populated fields (title_name_zh/en/ja, icon_path …) are kept.
        """
        old = existing.rom_info
        if old is None:
            existing.rom_info = new_info
            return
        old.title_name = new_info.title_name
        old.title_id = new_info.title_id or old.title_id
        old.region = new_info.region or old.region
        old.publisher = new_info.publisher or old.publisher
        old.version = new_info.version  # always overwrite from plugin
        old.file_type = new_info.file_type or old.file_type
        old.content_type = new_info.content_type or old.content_type
        old.dat_crc32 = new_info.dat_crc32 or old.dat_crc32

    # ── Hashing ──

    @staticmethod
    def _compute_crc32(path: Path, max_size: int = 1024 * 1024 * 1024) -> str:
        """Compute CRC32 of a ROM file (skip files > *max_size*)."""
        try:
            if path.stat().st_size > max_size:
                return ""
            crc = 0
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    crc = zlib.crc32(chunk, crc)
            return f"{crc & 0xFFFFFFFF:08X}"
        except OSError:
            return ""

    @staticmethod
    def _compute_hash(path: Path, max_bytes: int = 16 * 1024 * 1024) -> str:
        """SHA-256 of the first ``max_bytes`` of a file."""
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            remaining = max_bytes
            while remaining > 0:
                chunk = f.read(min(remaining, 65536))
                if not chunk:
                    break
                sha.update(chunk)
                remaining -= len(chunk)
        return sha.hexdigest()

    # ── Renaming ──

    def rename_rom(
        self, platform: str, game_id: str, template: str
    ) -> Path | None:
        """
        Rename a single ROM file using a template.

        Returns the new path on success, or None on failure.
        """
        entry = self._library.get(platform, game_id)
        if entry is None:
            logger.warning(f"ROM entry not found: {platform}:{game_id}")
            return None

        old_path = Path(entry.rom_path)
        if not old_path.exists():
            logger.warning(f"ROM file missing: {old_path}")
            return None

        tokens = self._build_rename_tokens(entry)
        new_name = self._rename.preview(template, tokens)

        new_path = old_path.parent / new_name
        if new_path == old_path:
            return old_path

        if new_path.exists():
            logger.warning(f"Target already exists: {new_path}")
            return None

        try:
            old_path.rename(new_path)
            entry.rom_path = str(new_path)
            self._library.save()
            logger.info(f"Renamed: {old_path.name} → {new_path.name}")
            return new_path
        except OSError as e:
            logger.error(f"Rename failed: {e}")
            return None

    def batch_rename(
        self,
        entries: list,
        template: str,
        *,
        dry_run: bool = False,
    ) -> list[tuple[str, str]]:
        """Preview or execute batch rename.

        *entries* can be a list of ``RomEntry`` objects or
        ``(platform, game_id)`` tuples.

        Returns ``[(old_name, new_name), …]``.
        When *dry_run* is True the files are **not** moved.
        """
        from app.models.rom_entry import RomEntry

        results: list[tuple[str, str]] = []
        for item in entries:
            if isinstance(item, RomEntry):
                entry = item
            else:
                platform, game_id = item
                entry = self._library.get(platform, game_id)
                if entry is None:
                    continue

            old_path = Path(entry.rom_path)
            old_name = old_path.name

            tokens = self._build_rename_tokens(entry)
            new_stem = self._rename.preview(template, tokens)
            # Preserve original extension
            new_name = new_stem + old_path.suffix if not new_stem.endswith(old_path.suffix) else new_stem

            if dry_run:
                results.append((old_name, new_name))
            else:
                new_path = old_path.parent / new_name
                if new_path == old_path:
                    results.append((old_name, new_name))
                    continue
                if new_path.exists():
                    logger.warning(f"Target already exists: {new_path}")
                    results.append((old_name, old_name))
                    continue
                try:
                    old_path.rename(new_path)
                    entry.rom_path = str(new_path)
                    logger.info(f"Renamed: {old_name} → {new_name}")
                    results.append((old_name, new_name))
                except OSError as e:
                    logger.error(f"Rename failed: {e}")
                    results.append((old_name, old_name))

        if not dry_run and any(old != new for old, new in results):
            self._library.save()

        return results

    def _build_rename_tokens(self, entry: RomEntry) -> dict[str, str]:
        """Build template variable values from a RomEntry."""
        tokens: dict[str, str] = {
            "platform": entry.platform,
            "ext": Path(entry.rom_path).suffix.lstrip("."),
            "crc32": entry.hash_crc32 or "",
        }

        info = entry.rom_info
        if info:
            tokens.update(
                {
                    "title_zh": info.title_name_zh,
                    "title_en": info.title_name_en,
                    "title_ja": info.title_name_ja,
                    "title_rom": info.title_name,
                    "title_id": info.title_id,
                    "region": info.region,
                    "languages": info.languages,
                    "version": info.version,
                    "file_type": info.file_type,
                    "content_type": info.content_type,
                    "publisher": info.publisher,
                }
            )

        # Fill game name from game plugin if we have a title_id but no zh name
        if not tokens.get("title_zh") and entry.game_id:
            plugin = self._plugins.get_game_plugin(entry.platform)
            if plugin:
                resolved = plugin.resolve_game_name(entry.game_id)
                if resolved:
                    tokens["title_zh"] = resolved

        return tokens

    # ── Entry removal ──

    def remove_entry(
        self, platform: str, game_id: str, delete_file: bool = False
    ) -> bool:
        """Remove a ROM entry from the library, optionally deleting the file."""
        entry = self._library.get(platform, game_id)
        if entry is None:
            return False

        if delete_file:
            p = Path(entry.rom_path)
            if p.exists():
                try:
                    p.unlink()
                    logger.info(f"Deleted ROM file: {p}")
                except OSError as e:
                    logger.error(f"Failed to delete ROM file: {e}")

        self._library.remove(platform, game_id)
        self._library.save()
        return True
