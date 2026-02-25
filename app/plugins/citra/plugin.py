"""Citra emulator plugin — Nintendo 3DS save management."""

from __future__ import annotations

import re
from pathlib import Path

from app.models.emulator import EmulatorInfo
from app.models.game_save import GameSave, SaveFile, SaveType
from app.plugins.base import EmulatorPlugin


class CitraPlugin(EmulatorPlugin):
    @property
    def name(self) -> str:
        return "citra"

    @property
    def display_name(self) -> str:
        return "Citra"

    @property
    def supported_platforms(self) -> list[str]:
        return ["3ds"]

    def detect_installation(
        self, extra_paths: list[str] | None = None
    ) -> list[EmulatorInfo]:
        installations: list[EmulatorInfo] = []
        candidates = [
            Path.home() / "AppData" / "Roaming" / "Citra",
        ]
        if extra_paths:
            candidates.extend(Path(p) for p in extra_paths)

        for path in candidates:
            if path.exists():
                installations.append(
                    EmulatorInfo(
                        name="Citra",
                        install_path=path,
                        data_path=path,
                        supported_platforms=["3ds"],
                    )
                )

        return installations

    def scan_saves(
        self,
        emulator: EmulatorInfo,
        custom_paths: list[str] | None = None,
    ) -> list[GameSave]:
        saves: list[GameSave] = []

        # Citra saves: sdmc/Nintendo 3DS/<id>/<id>/title/<high>/<low>/data/
        sdmc = Path(emulator.data_path) / "sdmc" / "Nintendo 3DS"
        if sdmc.exists():
            for title_dir in sdmc.rglob("title"):
                if not title_dir.is_dir():
                    continue
                for high_dir in title_dir.iterdir():
                    if not high_dir.is_dir():
                        continue
                    for low_dir in high_dir.iterdir():
                        if not low_dir.is_dir():
                            continue
                        data_dir = low_dir / "data" / "00000001"
                        if data_dir.exists():
                            title_id = f"{high_dir.name}{low_dir.name}".upper()
                            if not re.match(r'^[0-9A-F]+$', title_id):
                                continue

                            files = [
                                SaveFile(
                                    path=data_dir,
                                    save_type=SaveType.FOLDER,
                                    size=sum(
                                        f.stat().st_size
                                        for f in data_dir.rglob("*")
                                        if f.is_file()
                                    ),
                                )
                            ]
                            saves.append(
                                GameSave(
                                    game_id=title_id,
                                    game_name=title_id,
                                    emulator=self.name,
                                    platform="3ds",
                                    files=files,
                                )
                            )

        return self.deduplicate(saves)

    def get_save_directories(self, emulator: EmulatorInfo) -> list[str]:
        d = Path(emulator.data_path) / "sdmc" / "Nintendo 3DS"
        return [str(d)] if d.exists() else []
