"""Wątek roboczy do przetwarzania dokumentów (Claude API + OCR) poza GUI."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from document_processor import DocumentData, process_document

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    """Sygnały emitowane przez ProcessingWorker."""

    finished = pyqtSignal(str, object)  # (file_path, DocumentData)
    error = pyqtSignal(str, str)        # (file_path, komunikat)


class ProcessingWorker(QRunnable):
    """Przetwarza pojedynczy dokument w puli wątków (QThreadPool)."""

    def __init__(self, file_path: str, api_key: str, tesseract_path: str = "") -> None:
        super().__init__()
        self.file_path = file_path
        self.api_key = api_key
        self.tesseract_path = tesseract_path
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            data = process_document(self.file_path, self.api_key, self.tesseract_path)
            self.signals.finished.emit(self.file_path, data)
        except Exception as exc:  # noqa: BLE001 — zgłoś, nie wywracaj puli
            logger.exception("Błąd workera dla %s", self.file_path)
            # Mimo błędu zwracamy pusty DocumentData, by karta dała się wypełnić ręcznie.
            self.signals.finished.emit(self.file_path, DocumentData())
            self.signals.error.emit(self.file_path, str(exc))
