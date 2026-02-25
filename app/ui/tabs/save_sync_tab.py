"""Save Sync tab — multi-device save synchronization."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    PrimaryPushButton,
    PushButton,
    BodyLabel,
    CardWidget,
    SettingCardGroup,
    PushSettingCard,
)
from qfluentwidgets import FluentIcon as FIF

from app.ui.utils import show_success, show_error, show_info
from app.i18n import t

if TYPE_CHECKING:
    from app.context import AppContext


class SyncWorker(QThread):
    """Background sync worker."""

    finished = Signal(int, int, int)  # pushed, pulled, errors

    def __init__(self, ctx: AppContext, mode: str = "all", parent=None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._mode = mode

    def run(self) -> None:
        if not self._ctx.sync_manager:
            self.finished.emit(0, 0, 1)
            return

        result = self._ctx.sync_manager.sync_all()
        self.finished.emit(result.pushed, result.pulled, len(result.errors))


class SaveSyncTab(QWidget):
    """Multi-device save sync tab."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._worker: SyncWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 0)

        # Status card
        status_card = CardWidget(self)
        status_layout = QVBoxLayout(status_card)

        self._status_label = BodyLabel(t("sync.status"), self)
        status_layout.addWidget(self._status_label)

        self._sync_info = BodyLabel("", self)
        status_layout.addWidget(self._sync_info)

        layout.addWidget(status_card)

        # Actions
        actions = QHBoxLayout()

        self._sync_btn = PrimaryPushButton(FIF.SYNC, t("sync.sync_now"), self)
        self._sync_btn.clicked.connect(self._on_sync)
        actions.addWidget(self._sync_btn)

        self._push_btn = PushButton(FIF.UP, t("sync.push_only"), self)
        self._push_btn.clicked.connect(self._on_push)
        actions.addWidget(self._push_btn)

        self._pull_btn = PushButton(FIF.DOWN, t("sync.pull_only"), self)
        self._pull_btn.clicked.connect(self._on_pull)
        actions.addWidget(self._pull_btn)

        actions.addStretch()
        layout.addLayout(actions)

        # Settings
        settings_group = SettingCardGroup(t("sync.settings_group"), self)
        self._folder_card = PushSettingCard(
            t("sync.settings"),
            FIF.FOLDER,
            t("sync.sync_folder"),
            str(ctx.config.sync_folder or t("sync.not_configured")),
            settings_group,
        )
        settings_group.addSettingCard(self._folder_card)
        layout.addWidget(settings_group)

        layout.addStretch(1)

        self._update_status()

    def _update_status(self) -> None:
        if not self._ctx.sync_manager:
            self._status_label.setText(t("sync.sync_not_configured"))
            self._sync_info.setText(t("sync.sync_not_configured_msg"))
            self._sync_btn.setEnabled(False)
            self._push_btn.setEnabled(False)
            self._pull_btn.setEnabled(False)
        elif self._ctx.sync_manager.is_configured:
            self._status_label.setText(t("sync.ready"))
            self._sync_info.setText(t("sync.ready_msg", folder=self._ctx.config.sync_folder))
        else:
            self._status_label.setText(t("sync.folder_unavailable"))
            self._sync_info.setText(t("sync.folder_unavailable_msg"))

    def _on_sync(self) -> None:
        self._run_sync("all")

    def _on_push(self) -> None:
        self._run_sync("push")

    def _on_pull(self) -> None:
        self._run_sync("pull")

    def _run_sync(self, mode: str) -> None:
        if not self._ctx.sync_manager:
            show_error(self, t("sync.sync_not_configured"))
            return

        self._sync_btn.setEnabled(False)
        self._push_btn.setEnabled(False)
        self._pull_btn.setEnabled(False)

        self._worker = SyncWorker(self._ctx, mode, self)
        self._worker.finished.connect(self._on_sync_finished)
        self._worker.start()

    def _on_sync_finished(self, pushed: int, pulled: int, errors: int) -> None:
        self._sync_btn.setEnabled(True)
        self._push_btn.setEnabled(True)
        self._pull_btn.setEnabled(True)

        if errors > 0:
            show_error(self, t("sync.complete_errors"), t("sync.complete_errors_msg", pushed=pushed, pulled=pulled, errors=errors))
        else:
            show_success(self, t("sync.complete"), t("sync.complete_msg", pushed=pushed, pulled=pulled))
