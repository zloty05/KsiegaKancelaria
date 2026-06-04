"""Punkt wejścia aplikacji Księga Kancelarii.

Startuje QApplication, inicjalizuje logowanie i bazę, tworzy główne okno oraz ikonę
tray. Aplikacja startuje ukryta do tray; zamknięcie okna (X) chowa do tray, a pozycja
„Zamknij" w menu tray kończy proces.
"""

from __future__ import annotations

import logging
import sys

# Użyj magazynu certyfikatów Windows do weryfikacji SSL. Dzięki temu połączenia
# z Claude API działają przez antywirusy z inspekcją HTTPS (Norton, ESET, Kaspersky
# itd.), które podstawiają własny certyfikat root — bez wyłączania ochrony.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001 — brak truststore nie może blokować startu
    pass

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


def apply_light_theme(app: "QApplication") -> None:
    """Wymusza jasny, spójny motyw niezależnie od ciemnego motywu Windows.

    Bez tego w trybie ciemnym Windows tekst pól (QLineEdit) i etykiet jest jasny
    na jasnym tle — nieczytelny. Styl Fusion + jasna paleta dają stały wygląd.
    """
    from PyQt6.QtGui import QColor, QPalette

    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#f5f6fa"))
    pal.setColor(QPalette.ColorRole.WindowText, QColor("#2d3436"))
    pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#eef0f5"))
    pal.setColor(QPalette.ColorRole.Text, QColor("#2d3436"))
    pal.setColor(QPalette.ColorRole.Button, QColor("#f5f6fa"))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor("#2d3436"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#2d3436"))
    pal.setColor(QPalette.ColorRole.Highlight, QColor("#0984e3"))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8395a7"))
    app.setPalette(pal)


def main() -> int:
    setup_logging()
    logger = logging.getLogger("main")
    logger.info("Start aplikacji Księga Kancelarii")

    app = QApplication(sys.argv)
    app.setApplicationName("Księga Kancelarii")
    app.setQuitOnLastWindowClosed(False)  # zamknięcie okna nie kończy procesu
    app.setWindowIcon(app_icon())
    apply_light_theme(app)

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
