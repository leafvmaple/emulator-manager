"""ROM manager — scan ROM directories, index entries, rename files."""

from __future__ import annotations

import hashlib
import re
import tempfile
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from app.config import Config
from app.core.rename_engine import RenameEngine
from app.data.rom_library import RomLibrary
from app.models.rom_entry import RomEntry
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
        Scan all configured ROM directories and return all entries.

        Clears the library first, then rebuilds from scratch.
        """
        raw: dict[str, list[str]] | list[str] = self._config.get("rom_directories", {})

        self._library.clear()
        entries: list[RomEntry] = []

        if isinstance(raw, dict):
            for platform, dirs in raw.items():
                game_plugin = self._plugins.get_game_plugin(platform)
                if game_plugin is None:
                    logger.warning(f"No game plugin for platform '{platform}', skipping")
                    continue
                self._scan_dirs_with_plugin(dirs, game_plugin, entries)
        elif isinstance(raw, list):
            self._scan_dirs_auto(raw, entries)
        else:
            logger.warning(f"Unexpected rom_directories type: {type(raw)}")

        logger.info(f"Scan complete — {len(entries)} ROM(s) indexed")
        self._library.save()
        return entries

    def _scan_dirs_with_plugin(
        self,
        dirs: list[str],
        game_plugin: GamePlugin,
        entries: list[RomEntry],
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
                suffix = file.suffix.lower()
                if suffix == ".zip":
                    entry = self._create_entry_from_zip(file, game_plugin)
                elif suffix in extensions:
                    entry = self._create_entry(file, game_plugin)
                else:
                    continue
                if entry is None:
                    continue

                self._library.add(entry)
                entries.append(entry)
                logger.debug(f"Indexed ROM: {file.name} → {entry.game_id}")

    def _scan_dirs_auto(
        self, dirs: list[str], entries: list[RomEntry]
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
                suffix = file.suffix.lower()

                if suffix == ".zip":
                    # Peek inside zip to determine plugin
                    entry = self._create_entry_from_zip_auto(file, ext_map)
                else:
                    game_plugin = ext_map.get(suffix)
                    if game_plugin is None:
                        continue
                    entry = self._create_entry(file, game_plugin)
                if entry is None:
                    continue

                self._library.add(entry)
                entries.append(entry)
                logger.debug(f"Indexed ROM: {file.name} → {entry.game_id}")

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

        raw_crc = self._compute_crc32(rom_path)
        # If the plugin matched via DAT (e.g. NES header normalization),
        # use the DAT CRC so the UI can show a verified match.
        if rom_info and rom_info.dat_crc32:
            hash_crc = rom_info.dat_crc32[0]
        else:
            hash_crc = raw_crc

        entry = RomEntry(
            rom_path=str(rom_path),
            platform=game_plugin.platform,
            emulator="",  # ROM entries are platform-scoped, not emulator-scoped
            game_id=game_id,
            file_size=rom_path.stat().st_size,
            hash_crc32=hash_crc,
            added_at=datetime.now(timezone.utc).isoformat(),
            rom_info=rom_info,
        )

        return entry

    def _create_entry_from_zip(
        self, zip_path: Path, game_plugin: GamePlugin
    ) -> RomEntry | None:
        """Extract ROM from zip, parse with *game_plugin*, return entry."""
        real_exts = {e for e in game_plugin.get_rom_extensions() if e != ".zip"}
        return self._process_zip(zip_path, real_exts, game_plugin)

    def _create_entry_from_zip_auto(
        self, zip_path: Path, ext_map: dict[str, GamePlugin]
    ) -> RomEntry | None:
        """Open zip, detect plugin from inner file extension, parse ROM."""
        try:
            with zipfile.ZipFile(zip_path) as zf:
                for name in zf.namelist():
                    inner_ext = Path(name).suffix.lower()
                    plugin = ext_map.get(inner_ext)
                    if plugin is not None:
                        real_exts = {e for e in plugin.get_rom_extensions() if e != ".zip"}
                        return self._process_zip(zip_path, real_exts, plugin)
        except (zipfile.BadZipFile, OSError) as e:
            logger.debug(f"Cannot open zip '{zip_path.name}': {e}")
        return None

    def _process_zip(
        self, zip_path: Path, rom_exts: set[str], game_plugin: GamePlugin
    ) -> RomEntry | None:
        """Core zip processing: extract first matching ROM to a temp file."""
        try:
            with zipfile.ZipFile(zip_path) as zf:
                rom_name: str | None = None
                for name in zf.namelist():
                    if Path(name).suffix.lower() in rom_exts:
                        rom_name = name
                        break
                if rom_name is None:
                    return None

                original_data = zf.read(rom_name)
                suffix = Path(rom_name).suffix
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(original_data)
                    tmp_path = Path(tmp.name)
        except (zipfile.BadZipFile, OSError, KeyError) as e:
            logger.debug(f"Failed to extract from zip '{zip_path.name}': {e}")
            return None

        try:
            entry = self._create_entry(tmp_path, game_plugin)
            if entry is not None:
                # If the plugin modified the ROM (e.g. NES header fix),
                # propagate the change back into the ZIP archive.
                with open(tmp_path, "rb") as f:
                    fixed_data = f.read()
                if fixed_data != original_data:
                    self._update_rom_in_zip(zip_path, rom_name, fixed_data)

                entry.rom_path = str(zip_path)
                entry.file_size = zip_path.stat().st_size

                # Derive version/region from ZIP filename (No-Intro convention)
                if entry.rom_info is not None:
                    fname_ver = self._extract_version_from_filename(zip_path.stem)
                    if fname_ver:
                        entry.rom_info.version = fname_ver
                    fname_region = self._extract_region_from_filename(zip_path.stem)
                    if fname_region:
                        entry.rom_info.region = fname_region
            return entry
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

    @staticmethod
    def _extract_version_from_filename(stem: str) -> str:
        """Extract version from No-Intro filename patterns.

        - ``(Rev 1)`` → ``"1.1"``
        - ``(Rev 2)`` → ``"1.2"``
        - ``[1.1]`` → ``"1.1"``
        - No match → ``""``
        """
        m = re.search(r"\(Rev\s+(\d+)\)", stem, re.IGNORECASE)
        if m:
            return f"1.{m.group(1)}"
        m = re.search(r"\[1\.(\d+)\]", stem)
        if m:
            return f"1.{m.group(1)}"
        return ""

    # No-Intro region tags (full names + abbreviations)
    _REGION_TAGS: dict[str, str] = {
        "Japan": "Japan", "USA": "USA", "Europe": "Europe",
        "World": "World", "Korea": "Korea", "China": "China",
        "Taiwan": "Taiwan", "Asia": "Asia", "Australia": "Australia",
        "Brazil": "Brazil", "Canada": "Canada", "France": "France",
        "Germany": "Germany", "Italy": "Italy", "Spain": "Spain",
        "Sweden": "Sweden", "Netherlands": "Netherlands",
        # Abbreviations
        "JP": "Japan", "JPN": "Japan",
        "US": "USA", "U": "USA",
        "EU": "Europe", "EUR": "Europe",
        "KR": "Korea", "KOR": "Korea",
        "CN": "China", "CHN": "China",
        "TW": "Taiwan",
        "AU": "Australia", "AUS": "Australia",
        "BR": "Brazil", "BRA": "Brazil",
        "CA": "Canada", "CAN": "Canada",
        "FR": "France", "FRA": "France",
        "DE": "Germany", "GER": "Germany",
        "IT": "Italy", "ITA": "Italy",
        "ES": "Spain", "SPA": "Spain",
        "SE": "Sweden", "SWE": "Sweden",
        "NL": "Netherlands", "NED": "Netherlands",
        "W": "World",
        "J": "Japan", "E": "Europe",
    }

    @staticmethod
    def _extract_region_from_filename(stem: str) -> str:
        """Extract region from filename brackets, e.g. '(USA)', '(Japan, USA)', or '[US]'."""
        for m in re.finditer(r"[\(\[]([^)\]]+)[\)\]]", stem):
            parts = [p.strip() for p in m.group(1).split(",")]
            for part in parts:
                if part in RomManager._REGION_TAGS:
                    return RomManager._REGION_TAGS[part]
        return ""

    @staticmethod
    def _update_rom_in_zip(
        zip_path: Path, rom_name: str, fixed_data: bytes
    ) -> None:
        """Rewrite a ZIP archive with updated ROM data; backup first."""
        import shutil

        other_entries: list[tuple[str, bytes]] = []
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if name != rom_name:
                    other_entries.append((name, zf.read(name)))

        bak = zip_path.with_suffix(zip_path.suffix + ".bak")
        if not bak.exists():
            shutil.copy2(zip_path, bak)
            logger.info(f"Backup: {zip_path.name} → {bak.name}")

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(rom_name, fixed_data)
            for name, data in other_entries:
                zf.writestr(name, data)
        logger.info(f"Updated ROM in ZIP: {zip_path.name}/{rom_name}")

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

    # Full region name → short code
    _REGION_SHORT: dict[str, str] = {
        "japan": "JP",
        "usa": "US",
        "europe": "EU",
        "europe (alt)": "EU",
        "china": "CN",
        "taiwan": "TW",
        "hong kong": "HK",
        "korea": "KR",
        "international": "INT",
        "world": "W",
        "asia": "AS",
        "australia": "AU",
        "germany": "DE",
        "france": "FR",
        "spain": "ES",
        "italy": "IT",
        "netherlands": "NL",
        "sweden": "SE",
        "finland": "FI",
        "denmark": "DK",
        "canada": "CA",
        "brazil": "BR",
        "indonesia": "ID",
        "ntsc": "US",
        "pal": "EU",
    }

    def _build_rename_tokens(self, entry: RomEntry) -> dict[str, str]:
        """Build template variable values from a RomEntry."""
        info = entry.rom_info
        tokens: dict[str, str] = {
            "platform": entry.platform,
            "ext": Path(entry.rom_path).suffix.lstrip("."),
            "crc32": entry.hash_crc32 or "",
            "id": str(info.dat_id) if info and info.dat_id >= 0 else "",
        }

        if info:
            tokens.update(
                {
                    "title_zh": info.title_name_zh,
                    "title_en": info.title_name_en,
                    "title_ja": info.title_name_ja,
                    "title_rom": info.title_name,
                    "title_id": info.title_id,
                    "region": self._REGION_SHORT.get(info.region.lower(), info.region) if info.region else "",
                    "languages": info.languages,
                    "version": info.version,
                    "file_type": info.file_type,
                    "content_type": info.content_type,
                    "publisher": info.publisher,
                }
            )

        # {title} — pick best name based on app language
        tokens["title"] = entry.display_name

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
