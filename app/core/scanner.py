"""Save scanner — detect emulators and scan save files."""

from __future__ import annotations

from loguru import logger

from app.config import Config
from app.models.emulator import EmulatorInfo
from app.models.game_save import GameSave
from app.plugins.base import EmulatorPlugin
from app.plugins.plugin_manager import PluginManager


class Scanner:
    """
    Save-scanning orchestrator.

    Uses *EmulatorPlugin* instances to detect emulator installations and
    scan save files.  Optionally delegates display-name resolution to the
    corresponding *GamePlugin* for each emulator's platform.
    """

    def __init__(self, plugin_manager: PluginManager, config: Config) -> None:
        self._plugins = plugin_manager
        self._config = config

    # ── Detection ──

    def detect_all_emulators(self) -> dict[str, list[EmulatorInfo]]:
        """
        Detect installed emulators.

        Extra paths from ``config.emulators`` are forwarded to each plugin.
        """
        extra_paths: dict[str, list[str]] = {}
        configured = self._config.get("emulators", {})
        for emu_name, emu_conf in configured.items():
            paths = emu_conf.get("extra_paths", [])
            if paths:
                extra_paths[emu_name] = paths

        return self._plugins.detect_all_emulators(extra_paths)

    # ── Scanning ──

    def scan_all_saves(
        self, detected: dict[str, list[EmulatorInfo]] | None = None,
    ) -> list[GameSave]:
        """
        Scan save files for all detected emulators.

        If ``detected`` is not supplied, runs detection first.
        After scanning, display names are resolved via the matching
        GamePlugin (if available).
        """
        if detected is None:
            detected = self.detect_all_emulators()

        all_saves: list[GameSave] = []

        for emu_name, installations in detected.items():
            plugin = self._plugins.get_emulator_plugin(emu_name)
            if plugin is None:
                logger.warning(f"No emulator plugin for '{emu_name}'")
                continue

            for emulator in installations:
                try:
                    saves = plugin.scan_saves(emulator)
                    logger.debug(
                        f"{plugin.display_name}: found {len(saves)} save(s) "
                        f"at {emulator.data_path}"
                    )
                    all_saves.extend(saves)
                except Exception as e:
                    logger.error(
                        f"Save scan failed for {plugin.display_name} "
                        f"at {emulator.data_path}: {e}"
                    )

        # Deduplicate
        all_saves = EmulatorPlugin.deduplicate(all_saves)

        # Resolve display names via game plugins
        self._resolve_display_names(all_saves)

        logger.info(f"Total saves collected: {len(all_saves)}")
        return all_saves

    # ── Name resolution ──

    def _resolve_display_names(self, saves: list[GameSave]) -> None:
        """
        Batch-resolve game IDs to display names using GamePlugin.

        Groups saves by platform and delegates to the matching game plugin.
        """
        by_platform: dict[str, list[GameSave]] = {}
        for save in saves:
            by_platform.setdefault(save.platform, []).append(save)

        for platform, platform_saves in by_platform.items():
            game_plugin = self._plugins.get_game_plugin(platform)
            if game_plugin is None:
                continue
            game_plugin.resolve_display_names(platform_saves)
