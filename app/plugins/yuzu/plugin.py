"""Yuzu emulator plugin — Nintendo Switch save management via Yuzu."""

from __future__ import annotations

import re
from pathlib import Path

from app.models.emulator import EmulatorInfo
from app.models.game_save import GameSave, SaveFile, SaveType
from app.plugins.base import EmulatorPlugin


class YuzuPlugin(EmulatorPlugin):
    """EmulatorPlugin for the Yuzu Switch emulator."""

    @property
    def name(self) -> str:
        return "yuzu"

    @property
    def display_name(self) -> str:
        return "Yuzu"

    @property
    def supported_platforms(self) -> list[str]:
        return ["switch"]

    # ── Detection ──

    def detect_installation(
        self, extra_paths: list[str] | None = None
    ) -> list[EmulatorInfo]:
        installations: list[EmulatorInfo] = []
        candidates = [
            Path.home() / "AppData" / "Roaming" / "yuzu",
            Path.home() / "AppData" / "Local" / "yuzu",
        ]
        if extra_paths:
            candidates.extend(Path(p) for p in extra_paths)

        for path in candidates:
            if path.exists():
                installations.append(
                    EmulatorInfo(
                        name="Yuzu",
                        install_path=path,
                        data_path=path,
                        supported_platforms=["switch"],
                    )
                )

        return self.deduplicate_installations(installations)

    # ── Save scanning ──

    def scan_saves(
        self,
        emulator: EmulatorInfo,
        custom_paths: list[str] | None = None,
    ) -> list[GameSave]:
        saves: list[GameSave] = []
        data_path = Path(emulator.data_path)

        # Yuzu save path:  nand/user/save/0000000000000000/<user_id>/<title_id>/
        save_root = data_path / "nand" / "user" / "save" / "0000000000000000"
        if save_root.exists():
            for user_dir in save_root.iterdir():
                if not user_dir.is_dir():
                    continue
                for title_dir in user_dir.iterdir():
                    if not title_dir.is_dir():
                        continue
                    title_id = title_dir.name.upper()
                    if not re.fullmatch(r"[0-9A-F]{16}", title_id):
                        continue

                    total_size = sum(
                        f.stat().st_size
                        for f in title_dir.rglob("*")
                        if f.is_file()
                    )
                    if total_size == 0:
                        continue

                    saves.append(
                        GameSave(
                            game_id=title_id,
                            game_name=title_id,
                            emulator=self.name,
                            platform="switch",
                            files=[
                                SaveFile(
                                    path=title_dir,
                                    save_type=SaveType.FOLDER,
                                    size=total_size,
                                )
                            ],
                        )
                    )

        # Custom paths
        if custom_paths:
            for cp in custom_paths:
                cp_path = Path(cp)
                if cp_path.exists():
                    for title_dir in cp_path.iterdir():
                        if title_dir.is_dir() and re.fullmatch(
                            r"[0-9A-F]{16}", title_dir.name.upper()
                        ):
                            saves.append(
                                GameSave(
                                    game_id=title_dir.name.upper(),
                                    game_name=title_dir.name.upper(),
                                    emulator=self.name,
                                    platform="switch",
                                    files=[
                                        SaveFile(
                                            path=title_dir,
                                            save_type=SaveType.FOLDER,
                                            size=sum(
                                                f.stat().st_size
                                                for f in title_dir.rglob("*")
                                                if f.is_file()
                                            ),
                                        )
                                    ],
                                )
                            )

        return self.deduplicate(saves)

    # ── Save directories ──

    def get_save_directories(self, emulator: EmulatorInfo) -> list[str]:
        dirs: list[str] = []
        save_root = (
            Path(emulator.data_path) / "nand" / "user" / "save" / "0000000000000000"
        )
        if save_root.exists():
            dirs.append(str(save_root))
        return dirs
