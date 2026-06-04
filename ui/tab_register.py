"""Zakładka Rejestr: tabela pism, wyszukiwanie/filtrowanie, eksport do Excel."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import database
from database import Pismo

logger = logging.getLogger(__name__)

KIERUNEK_PL = {"IN": "← przych.", "OUT": "→ wych."}

# Kolumny wyświetlane w tabeli (klucz Pismo, nagłówek).
# Klucz "_strony" jest wirtualny — składa stronę powodową i pozwaną.
TABLE_COLUMNS = [
    ("data_pisma", "Data"),
    ("sygnatura", "Sygnatura"),
    ("_strony", "Strony"),
    ("typ_pisma", "Typ pisma"),
    ("kierunek", "Kierunek"),
    ("nazwa_pliku", "Plik"),
]


class RegisterTab(QWidget):
    """Zakładka rejestru z tabelą i eksportem."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pisma: list[Pismo] = []
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Pasek wyszukiwania.
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Szukaj:"))
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("sygnatura, sąd, strona, typ...")
        self.edit_search.returnPressed.connect(self._on_search)
        self.edit_search.textChanged.connect(self._on_search_live)
        search_row.addWidget(self.edit_search, stretch=1)
        btn_search = QPushButton("🔍")
        btn_search.clicked.connect(self._on_search)
        search_row.addWidget(btn_search)
        layout.addLayout(search_row)

        # Tabela.
        self.table = QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels([h for _, h in TABLE_COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, stretch=1)

        # Eksport.
        export_row = QHBoxLayout()
        export_row.addStretch()
        btn_export = QPushButton("📊 Eksportuj do Excel")
        btn_export.setStyleSheet(
            "background-color: #00b894; color: white; padding: 8px 16px;"
            " border-radius: 6px; font-weight: bold;"
        )
        btn_export.clicked.connect(self._export_excel)
        export_row.addWidget(btn_export)
        layout.addLayout(export_row)

    # --- dane ---------------------------------------------------------------

    def reload(self) -> None:
        """Wczytuje wszystkie pisma z bazy i wypełnia tabelę."""
        self._pisma = database.get_all_pisma()
        self._populate(self._pisma)

    def _populate(self, pisma: list[Pismo]) -> None:
        self.table.setRowCount(len(pisma))
        for r, p in enumerate(pisma):
            for c, (key, _) in enumerate(TABLE_COLUMNS):
                if key == "_strony":
                    val = " / ".join(
                        filter(None, [p.strona_powodowa, p.strona_pozwana])
                    )
                else:
                    val = getattr(p, key)
                if key == "kierunek":
                    val = KIERUNEK_PL.get(val, val)
                item = QTableWidgetItem("" if val is None else str(val))
                # Zapamiętaj id pisma w pierwszej kolumnie.
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, p.id)
                self.table.setItem(r, c, item)

    # --- wyszukiwanie -------------------------------------------------------

    def _on_search(self) -> None:
        query = self.edit_search.text().strip()
        if query:
            self._populate(database.search_pisma(query))
        else:
            self._populate(self._pisma)

    def _on_search_live(self, text: str) -> None:
        if not text.strip():
            self._populate(self._pisma)

    # --- interakcje ---------------------------------------------------------

    def _selected_pismo(self) -> Pismo | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        pismo_id = item.data(Qt.ItemDataRole.UserRole)
        for p in database.get_all_pisma():
            if p.id == pismo_id:
                return p
        return None

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        self._open_file()

    def _show_context_menu(self, pos) -> None:
        if self.table.currentRow() < 0:
            return
        menu = QMenu(self)
        act_open = QAction("Otwórz plik", menu)
        act_open.triggered.connect(self._open_file)
        act_folder = QAction("Otwórz folder", menu)
        act_folder.triggered.connect(self._open_folder)
        act_delete = QAction("Usuń wpis", menu)
        act_delete.triggered.connect(self._delete_entry)
        menu.addAction(act_open)
        menu.addAction(act_folder)
        menu.addSeparator()
        menu.addAction(act_delete)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _open_file(self) -> None:
        p = self._selected_pismo()
        if p and p.sciezka_pliku and os.path.exists(p.sciezka_pliku):
            os.startfile(p.sciezka_pliku)  # type: ignore[attr-defined]
        else:
            QMessageBox.warning(self, "Plik", "Plik nie istnieje na dysku.")

    def _open_folder(self) -> None:
        p = self._selected_pismo()
        if p and p.sciezka_pliku:
            folder = str(Path(p.sciezka_pliku).parent)
            if os.path.exists(folder):
                os.startfile(folder)  # type: ignore[attr-defined]
                return
        QMessageBox.warning(self, "Folder", "Folder nie istnieje na dysku.")

    def _delete_entry(self) -> None:
        p = self._selected_pismo()
        if not p:
            return
        reply = QMessageBox.question(
            self,
            "Usuń wpis",
            f"Usunąć wpis z rejestru?\n{p.sygnatura or p.nazwa_pliku}\n\n"
            "(Plik na dysku NIE zostanie usunięty.)",
        )
        if reply == QMessageBox.StandardButton.Yes and p.id is not None:
            database.delete_pismo(p.id)
            self.reload()

    # --- eksport ------------------------------------------------------------

    def _export_excel(self) -> None:
        default_name = f"Rejestr_Kancelarii_{datetime.now():%Y-%m-%d}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Eksportuj rejestr", default_name, "Pliki Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            database.export_to_excel(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Eksport", f"Nie udało się wyeksportować:\n{exc}")
            return
        reply = QMessageBox.question(
            self, "Eksport zakończony", f"Zapisano do:\n{path}\n\nOtworzyć plik?"
        )
        if reply == QMessageBox.StandardButton.Yes:
            os.startfile(path)  # type: ignore[attr-defined]
