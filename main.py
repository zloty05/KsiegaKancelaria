"""Punkt wejścia aplikacji Księga Kancelarii.

Startuje QApplication, inicjalizuje logowanie i bazę, tworzy główne okno oraz ikonę
tray. Aplikacja startuje ukryta do tray; zamknięcie okna (X) chowa do tray, a pozycja
„Zamknij" w menu tray kończy proces.
"""

from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from config import LOG_PATH, Config
from database import init_db
from ui.icon import app_icon


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> int:
    setup_logging()
    logger = logging.getLogger("main")
    logger.info("Start aplikacji Księga Kancelarii")

    app = QApplication(sys.argv)
    app.setApplicationName("Księga Kancelarii")
    app.setQuitOnLastWindowClosed(False)  # zamknięcie okna nie kończy procesu
    app.setWindowIcon(app_icon())

    # Inicjalizacja danych.
    config = Config.load()
    init_db()

    # Import tu, by logowanie i QApplication istniały wcześniej.
    from ui.main_window import MainWindow
    from ui.tray import TrayIcon

    window = MainWindow(config)
    tray = TrayIcon()

    # --- połączenia tray <-> okno ---
    tray.open_requested.connect(window.show_and_raise)
    tray.toggle_scanning.connect(window.toggle_scanning)
    tray.quit_requested.connect(app.quit)
    window.scanning_changed.connect(tray.set_scanning)

    tray.show()

    # Start ukryty do tray (okno nie pokazane).
    logger.info("Aplikacja gotowa — działa w tray")

    if not QApplication.instance():
        return 1
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
