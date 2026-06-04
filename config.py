"""Konfiguracja aplikacji Księga Kancelarii.

Przechowuje ustawienia w pliku config.json w katalogu %APPDATA%\\KsiegaKancelarii\\.
Tam też trafia baza danych i log aplikacji.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


def app_data_dir() -> Path:
    """Zwraca katalog danych aplikacji (%APPDATA%\\KsiegaKancelarii), tworząc go."""
    base = os.environ.get("APPDATA") or str(Path.home())
    path = Path(base) / "KsiegaKancelarii"
    path.mkdir(parents=True, exist_ok=True)
    return path


CONFIG_PATH = app_data_dir() / "config.json"
DB_PATH = app_data_dir() / "kancelaria.db"
LOG_PATH = app_data_dir() / "kancelaria.log"


@dataclass
class Config:
    """Ustawienia aplikacji zapisywane do config.json."""

    folder_nowe: str = r"C:\Kancelaria\_Nowe"
    folder_sprawy: str = r"C:\Kancelaria\Sprawy"
    anthropic_api_key: str = ""
    nazwa_kancelarii: str = ""
    autostart: bool = True
    # Ścieżka do tesseract.exe; pusta = autodetekcja (PATH / Program Files).
    tesseract_path: str = ""

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        """Wczytuje konfigurację z pliku JSON; przy braku/błędzie zwraca domyślną."""
        if not path.exists():
            cfg = cls()
            cfg.save(path)
            return cfg
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Nie udało się wczytać config.json (%s) — używam domyślnych", exc)
            return cls()
        # Przepuść tylko znane pola, by nie wywrócić się na starszym/nowszym pliku.
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def save(self, path: Path = CONFIG_PATH) -> None:
        """Zapisuje konfigurację do pliku JSON (UTF-8, wcięcia)."""
        try:
            path.write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("Nie udało się zapisać config.json: %s", exc)
            raise
