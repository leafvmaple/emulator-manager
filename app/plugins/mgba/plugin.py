"""mGBA emulator plugin — GBA / GB / GBC save management."""

from __future__ import annotations

from pathlib import Path

from app.models.emulator import EmulatorInfo
from app.models.game_save import GameSave, SaveFile, SaveType
from app.plugins.base import EmulatorPlugin


class MGBAPlugin(EmulatorPlugin):
    """EmulatorPlugin for the mGBA emulator."""

    @property
    def name(self) -> str:
        return "mgba"

    @property
    def display_name(self) -> str:
        return "mGBA"

    @property
    def supported_platforms(self) -> list[str]:
        return ["gba", "gb", "gbc"]

    # ── Detection ──

    def detect_installation(
        self, extra_paths: list[str] | None = None
    ) -> list[EmulatorInfo]:
        installations: list[EmulatorInfo] = []
        candidates = [
            # Portable: config dir next to mgba.exe (handled via extra_paths)
            # Standard data locations
            Path.home() / "AppData" / "Roaming" / "mGBA",
            Path.home() / "AppData" / "Local" / "mGBA",
        ]
        if extra_paths:
            candidates.extend(Path(p) for p in extra_paths)

        for path in candidates:
            if path.exists():
                installations.append(
                    EmulatorInfo(
                        name="mGBA",
                        install_path=path,
                        data_path=path,
                        supported_platforms=self.supported_platforms,
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

        # Battery saves (.sav) — mGBA saves alongside the ROM or in a savedir
        saves_dir = data_path / "saves"
        if saves_dir.exists():
            self._scan_battery_saves(saves_dir, saves)

        # Also check a common "savegames" folder
        savegames_dir = data_path / "savegames"
        if savegames_dir.exists():
            self._scan_battery_saves(savegames_dir, saves)

        # Save states (.ss0 .. .ss9, or .State1 .. .State9)
        states_dir = data_path / "states"
        if states_dir.exists():
            self._scan_save_states(states_dir, saves)

        # If the user specified custom paths, scan those too
        if custom_paths:
            for cp in custom_paths:
                cp_path = Path(cp)
                if cp_path.exists() and cp_path.is_dir():
                    self._scan_battery_saves(cp_path, saves)

        return self.deduplicate(saves)

    def _scan_battery_saves(self, directory: Path, saves: list[GameSave]) -> None:
        """Scan a directory for .sav battery save files."""
        for sav in directory.glob("*.sav"):
            saves.append(
                GameSave(
                    game_id=sav.stem,
                    game_name=sav.stem,
                    emulator=self.name,
                    platform="gba",
                    files=[
                        SaveFile(
                            path=sav,
                            save_type=SaveType.BATTERY,
                            size=sav.stat().st_size,
                        )
                    ],
                )
            )

    def _scan_save_states(self, directory: Path, saves: list[GameSave]) -> None:
        """Scan a directory for mGBA save state files (.ss0-.ss9)."""
        grouped: dict[str, list[Path]] = {}
        for ss in directory.iterdir():
            if not ss.is_file():
                continue
            # mGBA save states: <romname>.ss0 .. .ss9
            if ss.suffix.lower().startswith(".ss") and len(ss.suffix) == 4:
                grouped.setdefault(ss.stem, []).append(ss)

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
                    platform="gba",
                    files=save_files,
                )
            )

    # ── Save directories ──

    def get_save_directories(self, emulator: EmulatorInfo) -> list[str]:
        dirs: list[str] = []
        for sub in ("saves", "savegames", "states"):
            d = Path(emulator.data_path) / sub
            if d.exists():
                dirs.append(str(d))
        return dirs
