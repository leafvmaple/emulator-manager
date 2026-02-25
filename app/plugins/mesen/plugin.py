"""Mesen emulator plugin — NES/SNES/GB/GBC/GBA save management."""

from __future__ import annotations

from pathlib import Path

from app.models.emulator import EmulatorInfo
from app.models.game_save import GameSave, SaveFile, SaveType
from app.plugins.base import EmulatorPlugin


class MesenPlugin(EmulatorPlugin):
    @property
    def name(self) -> str:
        return "mesen"

    @property
    def display_name(self) -> str:
        return "Mesen"

    @property
    def supported_platforms(self) -> list[str]:
        return ["nes", "snes", "gb", "gbc", "gba"]

    def detect_installation(
        self, extra_paths: list[str] | None = None
    ) -> list[EmulatorInfo]:
        installations: list[EmulatorInfo] = []
        candidates = [
            Path.home() / "Documents" / "Mesen2",
            Path.home() / "Documents" / "Mesen",
        ]
        if extra_paths:
            candidates.extend(Path(p) for p in extra_paths)

        for path in candidates:
            if path.exists():
                installations.append(
                    EmulatorInfo(
                        name="Mesen",
                        install_path=path,
                        data_path=path,
                        supported_platforms=self.supported_platforms,
                    )
                )

        return installations

    def scan_saves(
        self,
        emulator: EmulatorInfo,
        custom_paths: list[str] | None = None,
    ) -> list[GameSave]:
        saves: list[GameSave] = []

        # Battery saves (.sav)
        saves_dir = Path(emulator.data_path) / "Saves"
        if saves_dir.exists():
            for sav in saves_dir.glob("*.sav"):
                saves.append(
                    GameSave(
                        game_id=sav.stem,
                        game_name=sav.stem,
                        emulator=self.name,
                        platform=self._guess_platform(sav),
                        files=[
                            SaveFile(
                                path=sav,
                                save_type=SaveType.BATTERY,
                                size=sav.stat().st_size,
                            )
                        ],
                    )
                )

        # Save states
        states_dir = Path(emulator.data_path) / "SaveStates"
        if states_dir.exists():
            grouped: dict[str, list[Path]] = {}
            for ss in states_dir.glob("*.mss"):
                grouped.setdefault(ss.stem.rsplit("_", 1)[0], []).append(ss)

            for game_name, files in grouped.items():
                save_files = [
                    SaveFile(
                        path=f,
                        save_type=SaveType.SAVESTATE,
                        size=f.stat().st_size,
                    )
                    for f in files
                ]
                saves.append(
                    GameSave(
                        game_id=game_name,
                        game_name=game_name,
                        emulator=self.name,
                        platform="nes",
                        files=save_files,
                    )
                )

        return self.deduplicate(saves)

    def get_save_directories(self, emulator: EmulatorInfo) -> list[str]:
        dirs: list[str] = []
        for sub in ("Saves", "SaveStates"):
            d = Path(emulator.data_path) / sub
            if d.exists():
                dirs.append(str(d))
        return dirs

    @staticmethod
    def _guess_platform(path: Path) -> str:
        """Try to guess platform from parent directory or file patterns."""
        parent = path.parent.name.lower()
        if "snes" in parent or "sfc" in parent:
            return "snes"
        if "gb" in parent:
            return "gb"
        if "gba" in parent:
            return "gba"
        return "nes"
