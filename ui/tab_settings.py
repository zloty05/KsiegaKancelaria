"""Zakładka Ustawienia: foldery, klucz API, nazwa kancelarii, autostart."""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import autostart
from config import Config
from document_processor import tesseract_available

logger = logging.getLogger(__name__)


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #2d3436; margin-top: 8px;")
    return lbl


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: #dfe6e9;")
    return line


class SettingsTab(QWidget):
    """Zakładka ustawień. Emituje settings_saved(Config) po zapisie."""

    settings_saved = pyqtSignal(object)

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._build_ui()
        self._load_from_config()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        # --- FOLDERY ---
        layout.addWidget(_section_label("FOLDERY"))
        layout.addWidget(QLabel("Folder skanów (_Nowe):"))
        self.edit_folder_nowe, row1 = self._folder_picker()
        layout.addLayout(row1)

        layout.addWidget(QLabel("Główny folder spraw:"))
        self.edit_folder_sprawy, row2 = self._folder_picker()
        layout.addLayout(row2)

        layout.addWidget(_separator())

        # --- API ---
        layout.addWidget(_section_label("API"))
        layout.addWidget(QLabel("Klucz Anthropic API:"))
        api_row = QHBoxLayout()
        self.edit_api_key = QLineEdit()
        self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_api_key.setPlaceholderText("sk-ant-...")
        api_row.addWidget(self.edit_api_key)
        self.btn_toggle_key = QPushButton("Pokaż")
        self.btn_toggle_key.setCheckable(True)
        self.btn_toggle_key.clicked.connect(self._toggle_key_visibility)
        api_row.addWidget(self.btn_toggle_key)
        layout.addLayout(api_row)

        layout.addWidget(_separator())

        # --- KANCELARIA ---
        layout.addWidget(_section_label("KANCELARIA"))
        layout.addWidget(QLabel("Nazwa kancelarii:"))
        self.edit_nazwa = QLineEdit()
        layout.addWidget(self.edit_nazwa)

        layout.addWidget(_separator())

        # --- SYSTEM ---
        layout.addWidget(_section_label("SYSTEM"))
        self.chk_autostart = QCheckBox("Uruchamiaj wraz z Windows")
        layout.addWidget(self.chk_autostart)

        # Ostrzeżenie o braku Tesseract (OCR).
        self.lbl_tesseract = QLabel()
        self.lbl_tesseract.setWordWrap(True)
        layout.addWidget(self.lbl_tesseract)

        layout.addStretch()

        # Zapis.
        save_row = QHBoxLayout()
        save_row.addStretch()
        self.btn_save = QPushButton("💾 Zapisz ustawienia")
        self.btn_save.setStyleSheet(
            "background-color: #0984e3; color: white; padding: 8px 18px;"
            " border-radius: 6px; font-weight: bold;"
        )
        self.btn_save.clicked.connect(self._on_save)
        save_row.addWidget(self.btn_save)
        layout.addLayout(save_row)

    def _folder_picker(self) -> tuple[QLineEdit, QHBoxLayout]:
        row = QHBoxLayout()
        edit = QLineEdit()
        row.addWidget(edit)
        btn = QPushButton("Przeglądaj")
        btn.clicked.connect(lambda: self._browse_folder(edit))
        row.addWidget(btn)
        return edit, row

    def _browse_folder(self, target: QLineEdit) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Wybierz folder", target.text() or ""
        )
        if folder:
            target.setText(folder)

    def _toggle_key_visibility(self) -> None:
        if self.btn_toggle_key.isChecked():
            self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_key.setText("Ukryj")
        else:
            self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_key.setText("Pokaż")

    def _load_from_config(self) -> None:
        c = self._config
        self.edit_folder_nowe.setText(c.folder_nowe)
        self.edit_folder_sprawy.setText(c.folder_sprawy)
        self.edit_api_key.setText(c.anthropic_api_key)
        self.edit_nazwa.setText(c.nazwa_kancelarii)
        self.chk_autostart.setChecked(c.autostart)
        self._refresh_tesseract_warning()

    def _refresh_tesseract_warning(self) -> None:
        if tesseract_available(self._config.tesseract_path):
            self.lbl_tesseract.setText("✅ Tesseract OCR wykryty — skany-obrazy będą rozpoznawane.")
            self.lbl_tesseract.setStyleSheet("color: #00b894;")
        else:
            self.lbl_tesseract.setText(
                "⚠️ Tesseract OCR nie został wykryty. Aplikacja działa dla plików PDF "
                "z warstwą tekstową, ale skany-obrazy nie będą rozpoznawane. "
                "Zainstaluj Tesseract OCR (z językiem polskim), aby włączyć OCR."
            )
            self.lbl_tesseract.setStyleSheet("color: #d63031;")

    def _on_save(self) -> None:
        c = self._config
        prev_autostart = c.autostart

        c.folder_nowe = self.edit_folder_nowe.text().strip()
        c.folder_sprawy = self.edit_folder_sprawy.text().strip()
        c.anthropic_api_key = self.edit_api_key.text().strip()
        c.nazwa_kancelarii = self.edit_nazwa.text().strip()
        c.autostart = self.chk_autostart.isChecked()

        try:
            c.save()
        except OSError as exc:
            QMessageBox.critical(self, "Błąd", f"Nie udało się zapisać ustawień:\n{exc}")
            return

        # Synchronizuj autostart z rejestrem, jeśli się zmienił.
        if c.autostart != prev_autostart:
            try:
                autostart.set_enabled(c.autostart)
            except OSError as exc:
                QMessageBox.warning(
                    self, "Autostart", f"Nie udało się zmienić autostartu:\n{exc}"
                )

        self._refresh_tesseract_warning()
        self.settings_saved.emit(c)
        QMessageBox.information(self, "Zapisano", "Ustawienia zostały zapisane.")
