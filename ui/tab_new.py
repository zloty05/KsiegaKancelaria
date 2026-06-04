"""Zakładka Nowe: tryb skanowania + kolejka kart do zatwierdzenia."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from PyQt6.QtCore import QThreadPool, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import database
import folder_matcher
from config import Config
from file_watcher import FolderWatcher
from ui.document_card import DocumentCard
from ui.processing_worker import ProcessingWorker
from ui.toast import show_toast

logger = logging.getLogger(__name__)


class NewTab(QWidget):
    """Zakładka Nowe.

    Sygnały:
      scanning_changed(bool) — zmiana trybu skanowania
      queue_changed(int)     — zmiana liczby oczekujących kart (badge)
      registered()           — zarejestrowano pismo (odśwież rejestr)
    """

    scanning_changed = pyqtSignal(bool)
    queue_changed = pyqtSignal(int)
    registered = pyqtSignal()

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._scanning = False
        self._cards: list[DocumentCard] = []
        self._pool = QThreadPool.globalInstance()

        self._watcher = FolderWatcher()
        self._watcher.emitter.file_detected.connect(self._on_file_detected)

        self._build_ui()

    # --- UI -----------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        self.btn_scan = QPushButton()
        self.btn_scan.setMinimumHeight(48)
        self.btn_scan.clicked.connect(self.toggle_scanning)
        layout.addWidget(self.btn_scan)
        self._update_scan_button()

        # Obszar przewijany z kartami.
        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(10)
        self._cards_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._cards_container)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(scroll, stretch=1)

        # Separator + przycisk pisma wychodzącego.
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #dfe6e9;")
        layout.addWidget(sep)

        self.btn_outgoing = QPushButton("📤 Zarejestruj pismo wychodzące")
        self.btn_outgoing.setMinimumHeight(40)
        self.btn_outgoing.setStyleSheet(
            "background-color: #6c5ce7; color: white; border-radius: 6px;"
            " font-weight: bold;"
        )
        self.btn_outgoing.clicked.connect(self._register_outgoing)
        layout.addWidget(self.btn_outgoing)

    def _update_scan_button(self) -> None:
        if self._scanning:
            self.btn_scan.setText("🟢 TRYB SKANOWANIA: WŁĄCZONY — czekam na skany...")
            self.btn_scan.setStyleSheet(
                "background-color: #00b894; color: white; font-weight: bold;"
                " font-size: 13px; border-radius: 8px;"
            )
        else:
            self.btn_scan.setText("🔴 TRYB SKANOWANIA: WYŁĄCZONY — kliknij aby włączyć")
            self.btn_scan.setStyleSheet(
                "background-color: #d63031; color: white; font-weight: bold;"
                " font-size: 13px; border-radius: 8px;"
            )

    # --- tryb skanowania ----------------------------------------------------

    def toggle_scanning(self) -> None:
        self.set_scanning(not self._scanning)

    def set_scanning(self, enabled: bool) -> None:
        if enabled == self._scanning:
            return
        self._scanning = enabled
        if enabled:
            self._watcher.start(self._config.folder_nowe)
            # Przetwórz pliki już obecne w folderze.
            for f in self._watcher.existing_files():
                self._on_file_detected(f)
        else:
            self._watcher.stop()
        self._update_scan_button()
        self.scanning_changed.emit(enabled)

    # --- przetwarzanie ------------------------------------------------------

    def _on_file_detected(self, file_path: str) -> None:
        # Pomiń, jeśli plik już jest w kolejce.
        if any(c.file_path == file_path for c in self._cards):
            return
        card = DocumentCard(file_path, self._config, kierunek="IN")
        card.approved.connect(self._on_card_approved)
        card.rejected.connect(self._on_card_rejected)
        self._add_card(card)

        worker = ProcessingWorker(
            file_path, self._config.anthropic_api_key, self._config.tesseract_path
        )
        worker.signals.finished.connect(self._on_processing_finished)
        self._pool.start(worker)

    def _on_processing_finished(self, file_path: str, data) -> None:
        for card in self._cards:
            if card.file_path == file_path:
                card.set_data(data)
                break
        self._refresh_expansion()

    # --- zarządzanie kartami ------------------------------------------------

    def _add_card(self, card: DocumentCard) -> None:
        self._cards.append(card)
        # Wstaw przed elastycznym wypełniaczem (ostatni element).
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
        self._refresh_expansion()
        self.queue_changed.emit(len(self._cards))

    def _remove_card(self, card: DocumentCard) -> None:
        if card in self._cards:
            self._cards.remove(card)
        self._cards_layout.removeWidget(card)
        card.deleteLater()
        self._refresh_expansion()
        self.queue_changed.emit(len(self._cards))

    def _refresh_expansion(self) -> None:
        """Pierwsza gotowa karta rozwinięta, pozostałe zwinięte."""
        first_ready_done = False
        for card in self._cards:
            if card._data is None:
                continue
            card.set_expanded(not first_ready_done)
            first_ready_done = True

    # --- zatwierdzanie / odrzucanie ----------------------------------------

    def _on_card_rejected(self, file_path: str) -> None:
        for card in list(self._cards):
            if card.file_path == file_path:
                self._remove_card(card)
                break

    def _on_card_approved(self, payload: dict) -> None:
        try:
            target_folder = payload["target_folder"]
            folder_matcher.create_folder_structure(target_folder)
            os.makedirs(target_folder, exist_ok=True)

            src = Path(payload["file_path"])
            dest = Path(target_folder) / src.name
            dest = self._unique_dest(dest)

            if src.exists():
                shutil.move(str(src), str(dest))
            final_path = str(dest)
            nazwa_pliku = dest.name
        except OSError as exc:
            QMessageBox.critical(self, "Błąd", f"Nie udało się przenieść pliku:\n{exc}")
            return

        # Zapis do bazy.
        database.add_pismo(
            data_pisma=payload["data_pisma"],
            sygnatura=payload["sygnatura"],
            sad=payload["sad"],
            typ_pisma=payload["typ_pisma"],
            strona_powodowa=payload["strona_powodowa"],
            strona_pozwana=payload["strona_pozwana"],
            kierunek=payload["kierunek"],
            sciezka_pliku=final_path,
            nazwa_pliku=nazwa_pliku,
        )

        # Opcjonalny druk (pisma wychodzące).
        if payload.get("drukuj"):
            self._print_file(final_path)

        # Toast.
        kier_pl = "przychodzące" if payload["kierunek"] == "IN" else "wychodzące"
        show_toast(
            "✅ Pismo zarejestrowane",
            f"Sygnatura: {payload['sygnatura'] or '—'}\n📁 {target_folder} ({kier_pl})",
            folder_path=target_folder,
        )

        # Usuń kartę i odśwież.
        for card in list(self._cards):
            if card.file_path == payload["file_path"]:
                self._remove_card(card)
                break
        self.registered.emit()

    @staticmethod
    def _unique_dest(dest: Path) -> Path:
        """Zapobiega nadpisaniu — dokleja licznik, jeśli plik istnieje."""
        if not dest.exists():
            return dest
        stem, suffix, i = dest.stem, dest.suffix, 1
        while True:
            cand = dest.with_name(f"{stem}_{i}{suffix}")
            if not cand.exists():
                return cand
            i += 1

    def _print_file(self, file_path: str) -> None:
        try:
            from printer import print_file

            ok = print_file(file_path)
            if not ok:
                QMessageBox.warning(
                    self, "Drukowanie", "Nie udało się wydrukować pliku."
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Błąd drukowania: %s", exc)
            QMessageBox.warning(self, "Drukowanie", f"Błąd drukowania:\n{exc}")

    # --- pismo wychodzące ---------------------------------------------------

    def _register_outgoing(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz pismo wychodzące",
            self._config.folder_sprawy,
            "Dokumenty (*.docx *.pdf)",
        )
        if not file_path:
            return
        if any(c.file_path == file_path for c in self._cards):
            return
        card = DocumentCard(
            file_path, self._config, kierunek="OUT", allow_print=True
        )
        card.approved.connect(self._on_card_approved)
        card.rejected.connect(self._on_card_rejected)
        self._add_card(card)

        # PDF można przetworzyć; docx — pusta karta do ręcznego wypełnienia.
        if file_path.lower().endswith(".pdf"):
            worker = ProcessingWorker(
                file_path, self._config.anthropic_api_key, self._config.tesseract_path
            )
            worker.signals.finished.connect(self._on_processing_finished)
            self._pool.start(worker)
        else:
            from document_processor import DocumentData

            card.set_data(DocumentData())
            self._refresh_expansion()

    def update_config(self, config: Config) -> None:
        """Aktualizuje konfigurację (np. po zmianie ustawień)."""
        self._config = config
