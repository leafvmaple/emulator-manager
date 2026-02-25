"""Plugin auto-discovery — manages both EmulatorPlugin and GamePlugin registries."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from loguru import logger

from app.models.emulator import EmulatorInfo
from app.plugins.base import EmulatorPlugin, GamePlugin


class PluginManager:
    """
    Auto-discovers plugin subclasses from ``app/plugins/<name>/plugin.py``.

    Each plugin module may export:
      - ``EmulatorPlugin`` subclass  → registered in the emulator registry
      - ``GamePlugin`` subclass      → registered in the game/platform registry
      - Or both — a single directory can contribute one of each.

    Usage::

        pm = PluginManager()
        pm.discover_plugins()
        pm.get_emulator_plugin("yuzu")       # → YuzuPlugin
        pm.get_game_plugin("switch")         # → SwitchGamePlugin
    """

    def __init__(self) -> None:
        self._emulator_plugins: dict[str, EmulatorPlugin] = {}
        self._game_plugins: dict[str, GamePlugin] = {}

    # ── Read-only access ──

    @property
    def emulator_plugins(self) -> list[EmulatorPlugin]:
        return list(self._emulator_plugins.values())

    @property
    def game_plugins(self) -> list[GamePlugin]:
        return list(self._game_plugins.values())

    # ── Discovery ──

    def discover_plugins(self) -> None:
        """Scan ``app/plugins/*/plugin.py`` and register all found plugins."""
        self._emulator_plugins.clear()
        self._game_plugins.clear()
        plugins_dir = Path(__file__).parent

        for module_info in pkgutil.iter_modules([str(plugins_dir)]):
            if not module_info.ispkg:
                continue
            module_name = f"app.plugins.{module_info.name}.plugin"
            try:
                module = importlib.import_module(module_name)
            except ImportError as e:
                logger.debug(f"Skipping plugin directory '{module_info.name}': {e}")
                continue

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if not isinstance(attr, type):
                    continue

                # Register EmulatorPlugin subclasses
                if (
                    issubclass(attr, EmulatorPlugin)
                    and attr is not EmulatorPlugin
                    and not getattr(attr, "__abstractmethods__", None)
                ):
                    self._register_emulator_plugin(attr, attr_name)

                # Register GamePlugin subclasses
                if (
                    issubclass(attr, GamePlugin)
                    and attr is not GamePlugin
                    and not getattr(attr, "__abstractmethods__", None)
                ):
                    self._register_game_plugin(attr, attr_name)

    def _register_emulator_plugin(self, cls: type[EmulatorPlugin], class_name: str) -> None:
        try:
            instance = cls()
            self._emulator_plugins[instance.name] = instance
            logger.info(f"Loaded emulator plugin: {instance.display_name} ({instance.name})")
        except Exception as e:
            logger.error(f"Failed to instantiate emulator plugin '{class_name}': {e}")

    def _register_game_plugin(self, cls: type[GamePlugin], class_name: str) -> None:
        try:
            instance = cls()
            self._game_plugins[instance.name] = instance
            logger.info(f"Loaded game plugin: {instance.display_name} ({instance.name})")
        except Exception as e:
            logger.error(f"Failed to instantiate game plugin '{class_name}': {e}")

    # ── Emulator plugin queries ──

    def get_emulator_plugin(self, name: str) -> EmulatorPlugin | None:
        """Look up an emulator plugin by its name."""
        return self._emulator_plugins.get(name)

    def get_emulators_for_platform(self, platform: str) -> list[EmulatorPlugin]:
        """Get all emulator plugins that support a given platform."""
        return [
            p for p in self._emulator_plugins.values()
            if platform in p.supported_platforms
        ]

    def detect_all_emulators(
        self, extra_paths: dict[str, list[str]] | None = None
    ) -> dict[str, list[EmulatorInfo]]:
        """Run detection across all emulator plugins."""
        result: dict[str, list[EmulatorInfo]] = {}
        extra = extra_paths or {}
        for plugin in self._emulator_plugins.values():
            try:
                installations = plugin.detect_installation(extra.get(plugin.name))
                installations = EmulatorPlugin.deduplicate_installations(installations)
                if installations:
                    result[plugin.name] = installations
                    logger.info(
                        f"Detected {len(installations)} installation(s) "
                        f"for {plugin.display_name}"
                    )
            except Exception as e:
                logger.error(f"Emulator plugin '{plugin.name}' detection failed: {e}")
        return result

    # ── Game plugin queries ──

    def get_game_plugin(self, platform: str) -> GamePlugin | None:
        """Look up a game plugin by platform identifier."""
        return self._game_plugins.get(platform)

    def get_all_rom_extensions(self) -> dict[str, list[str]]:
        """Return {platform: [extensions]} from all game plugins."""
        return {
            gp.platform: gp.get_rom_extensions()
            for gp in self._game_plugins.values()
        }

    # ── Legacy compat shims (can remove later) ──

    def get_plugin(self, name: str) -> EmulatorPlugin | None:
        """Alias for get_emulator_plugin — keeps scanner.py working."""
        return self.get_emulator_plugin(name)
