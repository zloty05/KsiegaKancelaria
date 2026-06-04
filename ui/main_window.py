"""Główne okno aplikacji z trzema zakładkami: Nowe, Rejestr, Ustawienia."""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QMainWindow, QTabWidget, QWidget

from config import Config
from ui.icon import app_icon
from ui.tab_new import NewTab
from ui.tab_register import RegisterTab
from ui.tab_settings import SettingsTab

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Okno główne.

    Sygnał scanning_changed(bool) propaguje stan trybu skanowania do tray.
    """

    scanning_changed = pyqtSignal(bool)

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config

        self.setWindowTitle("📋 Księga Kancelarii")
        self.setWindowIcon(app_icon())
        self.resize(720, 600)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tab_new = NewTab(config)
        self.tab_register = RegisterTab()
        self.tab_settings = SettingsTab(config)

        self._idx_new = self.tabs.addTab(self.tab_new, "📥 Nowe")
        self.tabs.addTab(self.tab_register, "📋 Rejestr")
        self.tabs.addTab(self.tab_settings, "⚙️ Ustawienia")

        # --- połączenia ---
        self.tab_new.scanning_changed.connect(self.scanning_changed.emit)
        self.tab_new.queue_changed.connect(self._update_badge)
        self.tab_new.registered.connect(self.tab_register.reload)
        self.tab_settings.settings_saved.connect(self._on_settings_saved)

        self._update_badge(0)

    # --- API dla tray -------------------------------------------------------

    def show_and_raise(self) -> None:
        """Pokazuje i wysuwa okno na wierzch (z tray)."""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toggle_scanning(self) -> None:
        self.tab_new.toggle_scanning()

    # --- obsługa zdarzeń ----------------------------------------------------

    def _update_badge(self, count: int) -> None:
        if count > 0:
            self.tabs.setTabText(self._idx_new, f"📥 Nowe  •{count}")
        else:
            self.tabs.setTabText(self._idx_new, "📥 Nowe")

    def _on_settings_saved(self, config: Config) -> None:
        self._config = config
        self.tab_new.update_config(config)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt API)
        """Zamknięcie okna (X) chowa do tray zamiast kończyć proces."""
        event.ignore()
        self.hide()
        logger.info("Okno schowane do tray")
