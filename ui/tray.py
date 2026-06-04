"""Ikona w zasobniku systemowym (system tray) z menu kontekstowym."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from ui.icon import app_icon


class TrayIcon(QSystemTrayIcon):
    """Ikona tray.

    Sygnały:
      open_requested    — żądanie pokazania głównego okna
      toggle_scanning   — przełączenie trybu skanowania
      quit_requested    — żądanie zamknięcia aplikacji
    """

    open_requested = pyqtSignal()
    toggle_scanning = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(app_icon(), parent)
        self.setToolTip("Księga Kancelarii")
        self._scanning = False

        self._menu = QMenu()
        self._act_open = QAction("📋 Otwórz Księgę Kancelarii", self._menu)
        self._act_open.triggered.connect(self.open_requested.emit)
        self._menu.addAction(self._act_open)

        self._menu.addSeparator()

        self._act_scan = QAction("⬤ Tryb skanowania: WYŁĄCZONY", self._menu)
        self._act_scan.triggered.connect(self.toggle_scanning.emit)
        self._menu.addAction(self._act_scan)

        self._menu.addSeparator()

        self._act_quit = QAction("✕ Zamknij", self._menu)
        self._act_quit.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(self._act_quit)

        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_requested.emit()

    def set_scanning(self, enabled: bool) -> None:
        """Aktualizuje etykietę pozycji menu wg trybu skanowania."""
        self._scanning = enabled
        if enabled:
            self._act_scan.setText("🟢 Tryb skanowania: WŁĄCZONY")
        else:
            self._act_scan.setText("🔴 Tryb skanowania: WYŁĄCZONY")
