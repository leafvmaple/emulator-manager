"""Settings page — app configuration UI."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QVBoxLayout, QWidget, QFileDialog
from qfluentwidgets import (
    ScrollArea,
    SettingCardGroup,
    PushSettingCard,
    SwitchSettingCard,
    ExpandGroupSettingCard,
    LineEdit,
    PasswordLineEdit,
    ComboBox as FluentComboBox,
)
from qfluentwidgets import FluentIcon as FIF

from app.i18n import t, set_language, supported_languages, current_language

if TYPE_CHECKING:
    from app.context import AppContext


class _LineEditSettingCard(PushSettingCard):
    """Setting card with a LineEdit for text input instead of a browse button."""

    def __init__(
        self,
        icon,
        title: str,
        content: str,
        placeholder: str,
        parent=None,
        is_password: bool = False,
    ) -> None:
        super().__init__("", icon, title, content, parent)
        # Replace the button with a line edit
        self.button.hide()
        if is_password:
            self._edit = PasswordLineEdit(self)
        else:
            self._edit = LineEdit(self)
        self._edit.setPlaceholderText(placeholder)
        self._edit.setMinimumWidth(280)
        self._edit.setMaximumWidth(400)
        self.hBoxLayout.insertWidget(2, self._edit)

    @property
    def text(self) -> str:
        return self._edit.text().strip()

    @text.setter
    def text(self, value: str) -> None:
        self._edit.setText(value)


class SettingsPage(ScrollArea):
    """Application settings page."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self.setObjectName("settingsPage")
        self.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # ── Language settings ──
        lang_group = SettingCardGroup(t("settings.language_group"), self)
        self._lang_card = PushSettingCard(
            "",
            FIF.LANGUAGE,
            t("settings.language"),
            t("settings.language_hint"),
            lang_group,
        )
        self._lang_card.button.hide()

        _LANG_LABELS = {"zh_CN": "简体中文", "en_US": "English", "ja_JP": "日本語"}
        self._lang_combo = FluentComboBox(self)
        for lang in supported_languages():
            self._lang_combo.addItem(_LANG_LABELS.get(lang, lang), userData=lang)
        # Select current language
        cur = current_language()
        for i in range(self._lang_combo.count()):
            if self._lang_combo.itemData(i) == cur:
                self._lang_combo.setCurrentIndex(i)
                break
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)
        self._lang_card.hBoxLayout.insertWidget(2, self._lang_combo)

        lang_group.addSettingCard(self._lang_card)
        layout.addWidget(lang_group)

        # ── Backup settings ──
        backup_group = SettingCardGroup(t("settings.backup_group"), self)
        self._backup_path_card = PushSettingCard(
            t("settings.browse"),
            FIF.FOLDER,
            t("settings.backup_dir"),
            str(ctx.config.backup_path or t("settings.not_set")),
            backup_group,
        )
        self._backup_path_card.clicked.connect(self._on_browse_backup)
        backup_group.addSettingCard(self._backup_path_card)
        layout.addWidget(backup_group)

        # ── Sync settings ──
        sync_group = SettingCardGroup(t("settings.sync_group"), self)
        self._sync_folder_card = PushSettingCard(
            t("settings.browse"),
            FIF.SYNC,
            t("settings.sync_folder"),
            str(ctx.config.sync_folder or t("settings.not_set")),
            sync_group,
        )
        self._sync_folder_card.clicked.connect(self._on_browse_sync)
        sync_group.addSettingCard(self._sync_folder_card)
        layout.addWidget(sync_group)

        # ── ROM settings ──
        rom_group = SettingCardGroup(t("settings.rom_group"), self)
        self._rom_dir_card = PushSettingCard(
            t("settings.add"),
            FIF.FOLDER_ADD,
            t("settings.rom_dirs"),
            self._format_rom_dirs(),
            rom_group,
        )
        self._rom_dir_card.clicked.connect(self._on_add_rom_dir)
        rom_group.addSettingCard(self._rom_dir_card)
        layout.addWidget(rom_group)

        # ── Scraper settings ──
        scraper_config = ctx.config.get("scraper", {})

        scraper_group = SettingCardGroup(t("settings.scraper_group"), self)

        # IGDB
        self._igdb_client_id_card = _LineEditSettingCard(
            FIF.GLOBE,
            t("settings.igdb_client_id"),
            t("settings.igdb_client_id_hint"),
            t("settings.igdb_client_id_placeholder"),
            scraper_group,
        )
        self._igdb_client_id_card.text = scraper_config.get("igdb_client_id", "")
        self._igdb_client_id_card._edit.editingFinished.connect(self._save_scraper_config)
        scraper_group.addSettingCard(self._igdb_client_id_card)

        self._igdb_client_secret_card = _LineEditSettingCard(
            FIF.FINGERPRINT,
            t("settings.igdb_client_secret"),
            t("settings.igdb_client_secret_hint"),
            t("settings.igdb_client_secret_placeholder"),
            scraper_group,
            is_password=True,
        )
        self._igdb_client_secret_card.text = scraper_config.get("igdb_client_secret", "")
        self._igdb_client_secret_card._edit.editingFinished.connect(self._save_scraper_config)
        scraper_group.addSettingCard(self._igdb_client_secret_card)

        # ScreenScraper
        self._ss_dev_id_card = _LineEditSettingCard(
            FIF.GLOBE,
            t("settings.ss_dev_id"),
            t("settings.ss_dev_hint"),
            t("settings.ss_dev_id_placeholder"),
            scraper_group,
        )
        self._ss_dev_id_card.text = scraper_config.get("screenscraper_dev_id", "")
        self._ss_dev_id_card._edit.editingFinished.connect(self._save_scraper_config)
        scraper_group.addSettingCard(self._ss_dev_id_card)

        self._ss_dev_password_card = _LineEditSettingCard(
            FIF.FINGERPRINT,
            t("settings.ss_dev_password"),
            t("settings.ss_dev_hint"),
            t("settings.ss_dev_password_placeholder"),
            scraper_group,
            is_password=True,
        )
        self._ss_dev_password_card.text = scraper_config.get("screenscraper_dev_password", "")
        self._ss_dev_password_card._edit.editingFinished.connect(self._save_scraper_config)
        scraper_group.addSettingCard(self._ss_dev_password_card)

        self._ss_username_card = _LineEditSettingCard(
            FIF.PEOPLE,
            t("settings.ss_username"),
            t("settings.ss_username_hint"),
            t("settings.ss_username_placeholder"),
            scraper_group,
        )
        self._ss_username_card.text = scraper_config.get("screenscraper_username", "")
        self._ss_username_card._edit.editingFinished.connect(self._save_scraper_config)
        scraper_group.addSettingCard(self._ss_username_card)

        self._ss_password_card = _LineEditSettingCard(
            FIF.FINGERPRINT,
            t("settings.ss_password"),
            t("settings.ss_password_hint"),
            t("settings.ss_password_placeholder"),
            scraper_group,
            is_password=True,
        )
        self._ss_password_card.text = scraper_config.get("screenscraper_password", "")
        self._ss_password_card._edit.editingFinished.connect(self._save_scraper_config)
        scraper_group.addSettingCard(self._ss_password_card)

        layout.addWidget(scraper_group)

        layout.addStretch(1)
        self.setWidget(container)

    def _on_browse_backup(self) -> None:
        path = QFileDialog.getExistingDirectory(self, t("settings.choose_backup_dir"))
        if path:
            with self._ctx.config.batch_update():
                self._ctx.config.set("backup_path", path)
            self._backup_path_card.setContent(path)

    def _on_language_changed(self, index: int) -> None:
        lang = self._lang_combo.itemData(index)
        if lang and lang != current_language():
            set_language(lang)
            with self._ctx.config.batch_update():
                self._ctx.config.set("language", lang)

    def _on_browse_sync(self) -> None:
        path = QFileDialog.getExistingDirectory(self, t("settings.choose_sync_folder"))
        if path:
            with self._ctx.config.batch_update():
                self._ctx.config.set("sync_folder", path)
            self._sync_folder_card.setContent(path)

    def _on_add_rom_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, t("settings.choose_rom_dir"))
        if path:
            dirs = list(self._ctx.config.rom_directories)
            if path not in dirs:
                dirs.append(path)
                with self._ctx.config.batch_update():
                    self._ctx.config.set("rom_directories", dirs)
                self._rom_dir_card.setContent(self._format_rom_dirs())

    def _format_rom_dirs(self) -> str:
        dirs = self._ctx.config.rom_directories
        if not dirs:
            return t("settings.not_set")
        return "; ".join(str(d) for d in dirs[:3]) + ("..." if len(dirs) > 3 else "")

    def _save_scraper_config(self) -> None:
        """Persist all scraper credentials to config."""
        scraper = self._ctx.config.get("scraper", {})
        scraper["igdb_client_id"] = self._igdb_client_id_card.text
        scraper["igdb_client_secret"] = self._igdb_client_secret_card.text
        scraper["screenscraper_dev_id"] = self._ss_dev_id_card.text
        scraper["screenscraper_dev_password"] = self._ss_dev_password_card.text
        scraper["screenscraper_username"] = self._ss_username_card.text
        scraper["screenscraper_password"] = self._ss_password_card.text
        with self._ctx.config.batch_update():
            self._ctx.config.set("scraper", scraper)
