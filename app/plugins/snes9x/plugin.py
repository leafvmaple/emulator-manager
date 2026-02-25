"""Snes9x emulator plugin — SNES save management."""

from __future__ import annotations

from pathlib import Path

from app.models.emulator import EmulatorInfo
from app.models.game_save import GameSave, SaveFile, SaveType
from app.plugins.base import EmulatorPlugin


class Snes9xPlugin(EmulatorPlugin):
    @property
    def name(self) -> str:
        return "snes9x"

    @property
    def display_name(self) -> str:
        return "Snes9x"

    @property
    def supported_platforms(self) -> list[str]:
        return ["snes"]

    def detect_installation(
        self, extra_paths: list[str] | None = None
    ) -> list[EmulatorInfo]:
        installations: list[EmulatorInfo] = []
        candidates = [
            Path.home() / "Documents" / "Snes9x",
        ]
        if extra_paths:
            candidates.extend(Path(p) for p in extra_paths)

        for path in candidates:
            if path.exists():
                installations.append(
                    EmulatorInfo(
                        name="Snes9x",
                        install_path=path,
                        data_path=path,
                        supported_platforms=["snes"],
                    )
                )

        return installations

    def scan_saves(
        self,
        emulator: EmulatorInfo,
        custom_paths: list[str] | None = None,
    ) -> list[GameSave]:
        saves: list[GameSave] = []
        data_path = Path(emulator.data_path)

        # SRAM saves
        saves_dir = data_path / "Saves"
        if saves_dir.exists():
            for srm in saves_dir.glob("*.srm"):
                saves.append(
                    GameSave(
                        game_id=srm.stem,
                        game_name=srm.stem,
                        emulator=self.name,
                        platform="snes",
                        files=[
                            SaveFile(
                                path=srm,
                                save_type=SaveType.BATTERY,
                                size=srm.stat().st_size,
                            )
                        ],
                    )
                )

        return self.deduplicate(saves)

    def get_save_directories(self, emulator: EmulatorInfo) -> list[str]:
        d = Path(emulator.data_path) / "Saves"
        return [str(d)] if d.exists() else []
