"""Zarządzanie autostartem Windows przez klucz rejestru HKCU\\...\\Run."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "KsiegaKancelarii"


def _launch_command() -> str:
    """Polecenie startowe: zapakowany .exe lub `python main.py`."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    main_py = Path(__file__).resolve().parent / "main.py"
    return f'"{sys.executable}" "{main_py}"'


def is_enabled() -> bool:
    """Czy wpis autostartu istnieje."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.warning("Nie udało się odczytać autostartu: %s", exc)
        return False


def set_enabled(enabled: bool) -> None:
    """Dodaje lub usuwa wpis autostartu w rejestrze."""
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key, APP_NAME, 0, winreg.REG_SZ, _launch_command()
                )
                logger.info("Autostart włączony")
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    logger.info("Autostart wyłączony")
                except FileNotFoundError:
                    pass
    except OSError as exc:
        logger.error("Nie udało się ustawić autostartu: %s", exc)
        raise
