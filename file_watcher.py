"""Monitorowanie folderu _Nowe\\ przez watchdog.

Handler emituje sygnał Qt (przez QObject) zamiast bezpośrednio dotykać GUI —
zgodnie z wymaganiem, że watchdog nie modyfikuje widgetów w swoim wątku.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

# Rozszerzenia traktowane jako skany/pisma do przetworzenia.
WATCHED_EXTENSIONS = {".pdf"}


class _Emitter(QObject):
    """Pośrednik emitujący sygnał z wątku watchdog do GUI."""

    file_detected = pyqtSignal(str)


class _NewFileHandler(FileSystemEventHandler):
    def __init__(self, emitter: _Emitter) -> None:
        super().__init__()
        self._emitter = emitter

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        path = Path(str(event.src_path))
        if path.suffix.lower() not in WATCHED_EXTENSIONS:
            return
        if self._wait_until_stable(path):
            logger.info("Wykryto nowy plik: %s", path)
            self._emitter.file_detected.emit(str(path))
        else:
            logger.warning("Plik nie ustabilizował się, pomijam: %s", path)

    @staticmethod
    def _wait_until_stable(path: Path, timeout: float = 30.0) -> bool:
        """Czeka aż rozmiar pliku przestanie rosnąć (skan w trakcie zapisu)."""
        last = -1
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                size = path.stat().st_size
            except OSError:
                time.sleep(0.5)
                continue
            if size == last and size > 0:
                return True
            last = size
            time.sleep(1.0)
        return path.exists()


class FolderWatcher:
    """Steruje obserwatorem watchdog dla folderu _Nowe."""

    def __init__(self) -> None:
        self.emitter = _Emitter()
        self._observer: Observer | None = None
        self._folder: str | None = None

    @property
    def is_running(self) -> bool:
        return self._observer is not None

    def start(self, folder: str) -> None:
        """Uruchamia obserwację wskazanego folderu (tworzy go, jeśli nie istnieje)."""
        if self._observer is not None:
            self.stop()
        os.makedirs(folder, exist_ok=True)
        self._folder = folder
        self._observer = Observer()
        self._observer.schedule(
            _NewFileHandler(self.emitter), folder, recursive=False
        )
        self._observer.start()
        logger.info("Watchdog uruchomiony na: %s", folder)

    def stop(self) -> None:
        """Zatrzymuje obserwację."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            logger.info("Watchdog zatrzymany")
