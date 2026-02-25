"""PCSX2 emulator plugin — PlayStation 2 save management."""

from __future__ import annotations

import re
from pathlib import Path

from app.models.emulator import EmulatorInfo
from app.models.game_save import GameSave, SaveFile, SaveType
from app.plugins.base import EmulatorPlugin


class PCSX2Plugin(EmulatorPlugin):
    @property
    def name(self) -> str:
        return "pcsx2"

    @property
    def display_name(self) -> str:
        return "PCSX2"

    @property
    def supported_platforms(self) -> list[str]:
        return ["ps2"]

    def detect_installation(
        self, extra_paths: list[str] | None = None
    ) -> list[EmulatorInfo]:
        installations: list[EmulatorInfo] = []
        candidates = [
            Path.home() / "Documents" / "PCSX2",
            Path.home() / "AppData" / "Roaming" / "PCSX2",
        ]
        if extra_paths:
            candidates.extend(Path(p) for p in extra_paths)

        for path in candidates:
            if path.exists():
                installations.append(
                    EmulatorInfo(
                        name="PCSX2",
                        install_path=path,
                        data_path=path,
                        supported_platforms=["ps2"],
                    )
                )

        return installations

    def scan_saves(
        self,
        emulator: EmulatorInfo,
        custom_paths: list[str] | None = None,
    ) -> list[GameSave]:
        saves: list[GameSave] = []

        # Memory cards
        memcard_dir = Path(emulator.data_path) / "memcards"
        if memcard_dir.exists():
            for mc in memcard_dir.glob("*.ps2"):
                saves.append(
                    GameSave(
                        game_id=mc.stem,
                        game_name=mc.stem,
                        emulator=self.name,
                        platform="ps2",
                        files=[
                            SaveFile(
                                path=mc,
                                save_type=SaveType.MEMCARD,
                                size=mc.stat().st_size,
                            )
                        ],
                    )
                )

        # Save states
        sstates_dir = Path(emulator.data_path) / "sstates"
        if sstates_dir.exists():
            # Group save states by game CRC
            grouped: dict[str, list[Path]] = {}
            for ss in sstates_dir.glob("*.p2s"):
                m = re.match(r"^([0-9A-Fa-f]+)", ss.stem)
                if m:
                    crc = m.group(1).upper()
                    grouped.setdefault(crc, []).append(ss)

            for crc, files in grouped.items():
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
                        game_id=crc,
                        game_name=crc,
                        emulator=self.name,
                        platform="ps2",
                        crc32=crc,
                        files=save_files,
                    )
                )

        return self.deduplicate(saves)

    def get_save_directories(self, emulator: EmulatorInfo) -> list[str]:
        dirs: list[str] = []
        for sub in ("memcards", "sstates"):
            d = Path(emulator.data_path) / sub
            if d.exists():
                dirs.append(str(d))
        return dirs
