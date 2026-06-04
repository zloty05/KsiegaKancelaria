"""Karta dokumentu oczekującego na zatwierdzenie (zakładka Nowe).

Stany karty:
  - processing: zwinięta, „przetwarzanie..."
  - ready (rozwinięta): edytowalne pola + folder docelowy + Zatwierdź/Odrzuć
  - ready (zwinięta): podsumowanie w jednej linii (pozostałe w kolejce)
"""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import folder_matcher
from config import Config
from document_processor import DocumentData


class DocumentCard(QFrame):
    """Karta jednego dokumentu.

    Sygnały:
      approved(dict) — zatwierdzono; dict zawiera dane + ścieżki + kierunek + druk
      rejected(str)  — odrzucono; arg = file_path
    """

    approved = pyqtSignal(dict)
    rejected = pyqtSignal(str)

    def __init__(
        self,
        file_path: str,
        config: Config,
        kierunek: str = "IN",
        allow_print: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.file_path = file_path
        self._config = config
        self.kierunek = kierunek
        self._allow_print = allow_print
        self._data: DocumentData | None = None
        self._target_folder: str = ""
        self._folder_manually_set = False
        self._expanded = False

        self.setObjectName("documentCard")
        self.setStyleSheet(
            """
            #documentCard {
                background-color: #ffffff;
                border: 1px solid #b2bec3;
                border-radius: 8px;
            }
            QLabel#fileName { font-weight: bold; font-size: 13px; color: #2d3436; }
            QLabel#folderLabel { color: #0984e3; }
            """
        )
        self._build_processing_ui()

    # --- UI: stan przetwarzania --------------------------------------------

    def _build_processing_ui(self) -> None:
        self._clear_layout()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        name = QLabel(f"📄 {Path(self.file_path).name}")
        name.setObjectName("fileName")
        layout.addWidget(name)
        layout.addStretch()
        layout.addWidget(QLabel("[przetwarzanie...]"))

    # --- UI: stan gotowy (rozwinięty) --------------------------------------

    def set_data(self, data: DocumentData) -> None:
        """Ustawia dane z przetwarzania i przebudowuje kartę do stanu gotowego."""
        self._data = data
        # Wyznacz folder docelowy.
        match = folder_matcher.find_matching_folder(
            data, self._config.folder_sprawy, self.kierunek
        )
        if match:
            self._target_folder = match
        else:
            self._target_folder = folder_matcher.suggest_new_folder(
                data, self._config.folder_sprawy, self.kierunek
            )
        self.set_expanded(self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        """Przełącza między widokiem rozwiniętym a zwiniętym (dla gotowej karty)."""
        self._expanded = expanded
        if self._data is None:
            return
        if expanded:
            self._build_expanded_ui()
        else:
            self._build_collapsed_ui()

    def _build_expanded_ui(self) -> None:
        self._clear_layout()
        data = self._data
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        name = QLabel(f"📄 {Path(self.file_path).name}")
        name.setObjectName("fileName")
        layout.addWidget(name)

        form = QFormLayout()
        form.setSpacing(6)
        self.edit_sygnatura = QLineEdit(data.sygnatura or "")
        self.edit_sad = QLineEdit(data.sad or "")
        self.edit_typ = QLineEdit(data.typ_pisma or "")
        self.edit_data = QLineEdit(data.data_pisma or "")
        strony = " / ".join(filter(None, [data.strona_powodowa, data.strona_pozwana]))
        self.edit_strony = QLineEdit(strony)
        form.addRow("Sygnatura akt:", self.edit_sygnatura)
        form.addRow("Sąd:", self.edit_sad)
        form.addRow("Typ pisma:", self.edit_typ)
        form.addRow("Data pisma:", self.edit_data)
        form.addRow("Strony:", self.edit_strony)
        layout.addLayout(form)

        layout.addWidget(QLabel("📁 Folder docelowy:"))
        folder_row = QHBoxLayout()
        self.lbl_folder = QLabel(self._target_folder)
        self.lbl_folder.setObjectName("folderLabel")
        self.lbl_folder.setWordWrap(True)
        folder_row.addWidget(self.lbl_folder, stretch=1)
        btn_change = QPushButton("📁 Zmień")
        btn_change.clicked.connect(self._change_folder)
        folder_row.addWidget(btn_change)
        layout.addLayout(folder_row)

        if self._allow_print:
            self.chk_print = QCheckBox("Drukuj na drukarce")
            layout.addWidget(self.chk_print)

        # Przyciski akcji.
        actions = QHBoxLayout()
        btn_ok = QPushButton("✅ Zatwierdź")
        btn_ok.setStyleSheet(
            "background-color: #00b894; color: white; padding: 8px 16px;"
            " border-radius: 6px; font-weight: bold;"
        )
        btn_ok.clicked.connect(self._on_approve)
        btn_reject = QPushButton("🗑️ Odrzuć")
        btn_reject.setStyleSheet(
            "background-color: #d63031; color: white; padding: 8px 16px;"
            " border-radius: 6px; font-weight: bold;"
        )
        btn_reject.clicked.connect(lambda: self.rejected.emit(self.file_path))
        actions.addWidget(btn_ok)
        actions.addWidget(btn_reject)
        layout.addLayout(actions)

    def _build_collapsed_ui(self) -> None:
        self._clear_layout()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        name = QLabel(f"📄 {Path(self.file_path).name}")
        name.setObjectName("fileName")
        layout.addWidget(name)
        layout.addStretch()
        syg = (self._data.sygnatura if self._data else "") or "—"
        layout.addWidget(QLabel(syg))

    # --- akcje --------------------------------------------------------------

    def _change_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Wybierz folder docelowy", self._target_folder or self._config.folder_sprawy
        )
        if chosen:
            self._target_folder = chosen
            self._folder_manually_set = True
            self.lbl_folder.setText(chosen)

    def _edited_data(self) -> tuple[DocumentData, str, str]:
        """Buduje DocumentData z aktualnych (edytowalnych) pól karty."""
        strony = self.edit_strony.text().strip()
        powod, pozwany = (strony.split(" / ", 1) + [""])[:2] if strony else ("", "")
        data = DocumentData(
            sygnatura=self.edit_sygnatura.text().strip() or None,
            sad=self.edit_sad.text().strip() or None,
            typ_pisma=self.edit_typ.text().strip() or None,
            data_pisma=self.edit_data.text().strip() or None,
            strona_powodowa=powod.strip() or None,
            strona_pozwana=pozwany.strip() or None,
        )
        return data, powod.strip(), pozwany.strip()

    def _on_approve(self) -> None:
        edited, powod, pozwany = self._edited_data()

        # Jeśli użytkownik nie zmienił folderu ręcznie, przelicz propozycję na podstawie
        # poprawionych pól (np. dopiero teraz wpisana sygnatura/strony).
        target_folder = self._target_folder
        if not self._folder_manually_set:
            match = folder_matcher.find_matching_folder(
                edited, self._config.folder_sprawy, self.kierunek
            )
            target_folder = match or folder_matcher.suggest_new_folder(
                edited, self._config.folder_sprawy, self.kierunek
            )

        payload = {
            "file_path": self.file_path,
            "sygnatura": edited.sygnatura,
            "sad": edited.sad,
            "typ_pisma": edited.typ_pisma,
            "data_pisma": edited.data_pisma,
            "strona_powodowa": powod or None,
            "strona_pozwana": pozwany or None,
            "kierunek": self.kierunek,
            "target_folder": target_folder,
            "drukuj": bool(getattr(self, "chk_print", None) and self.chk_print.isChecked()),
        }
        self.approved.emit(payload)

    # --- pomocnicze ---------------------------------------------------------

    def _clear_layout(self) -> None:
        old = self.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
            QWidget().setLayout(old)  # odłącz stary layout
