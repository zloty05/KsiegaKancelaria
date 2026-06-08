"""Dopasowanie i tworzenie folderów spraw.

Logika:
  1. Szukaj folderu, którego nazwa zawiera sygnaturę (z `/`→`_`).
  2. W razie braku — folder zawierający nazwisko strony reprezentowanej/przeciwnej.
  3. Gdy znaleziono → zwróć podfolder przychodzące\\ lub wychodzące\\.
  4. Gdy nie znaleziono → suggest_new_folder().
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from document_processor import DocumentData

logger = logging.getLogger(__name__)

SUBFOLDER_IN = "przychodzące"
SUBFOLDER_OUT = "wychodzące"


def sanitize(text: str) -> str:
    """Zamienia znaki niedozwolone w nazwach folderów Windows na podkreślenia."""
    text = text.strip()
    text = re.sub(r'[\\/:*?"<>|]', "_", text)
    text = re.sub(r"\s+", "_", text)
    return text.strip("_")


def _subfolder_name(kierunek: str) -> str:
    return SUBFOLDER_OUT if kierunek == "OUT" else SUBFOLDER_IN


def _iter_dirs(root: Path):
    """Iteruje po wszystkich podkatalogach root (rekurencyjnie), pomijając przych./wych."""
    skip = {SUBFOLDER_IN, SUBFOLDER_OUT}
    for p in root.rglob("*"):
        if p.is_dir() and p.name not in skip:
            yield p


def find_matching_folder(
    data: DocumentData, sprawy_root: str, kierunek: str = "IN"
) -> Optional[str]:
    """Zwraca ścieżkę podfolderu (przychodzące/wychodzące) najlepiej pasującej sprawy.

    Dopasowanie po sygnaturze (priorytet), potem po nazwisku strony. Zwraca None,
    gdy nic nie pasuje.
    """
    root = Path(sprawy_root)
    if not root.exists():
        logger.info("Folder spraw nie istnieje: %s", sprawy_root)
        return None

    sub = _subfolder_name(kierunek)

    # 1) Dopasowanie po sygnaturze.
    if data.sygnatura:
        syg_key = sanitize(data.sygnatura).lower()
        if syg_key:
            for d in _iter_dirs(root):
                if syg_key in sanitize(d.name).lower():
                    return str(d / sub)

    # 2) Dopasowanie po nazwisku strony.
    nazwiska = [s for s in (data.strona_reprezentowana, data.strona_przeciwna) if s]
    for nazwisko in nazwiska:
        key = sanitize(nazwisko).lower()
        if not key:
            continue
        for d in _iter_dirs(root):
            if key in sanitize(d.name).lower():
                return str(d / sub)

    return None


def suggest_new_folder(data: DocumentData, sprawy_root: str, kierunek: str = "IN") -> str:
    """Proponuje ścieżkę nowego folderu sprawy (z podfolderem kierunku).

    Format: sprawy_root\\YYYY\\Nazwisko_Imie\\Sygnatura_z_podkreślnikami\\<kierunek>\\
    """
    rok = datetime.now().strftime("%Y")
    if data.data_pisma:
        m = re.match(r"(\d{4})", data.data_pisma)
        if m:
            rok = m.group(1)

    nazwa_strony = data.strona_reprezentowana or data.strona_przeciwna or "Nieznana_strona"
    nazwa_strony = sanitize(nazwa_strony) or "Nieznana_strona"

    if data.sygnatura:
        nazwa_sprawy = sanitize(data.sygnatura)
    else:
        nazwa_sprawy = "Bez_sygnatury_" + datetime.now().strftime("%Y%m%d_%H%M%S")

    sub = _subfolder_name(kierunek)
    return str(Path(sprawy_root) / rok / nazwa_strony / nazwa_sprawy / sub)


def create_folder_structure(folder_path: str) -> None:
    """Tworzy folder sprawy wraz z podfolderami przychodzące\\ i wychodzące\\.

    `folder_path` może wskazywać podfolder kierunku — tworzymy oba rodzeństwa.
    """
    path = Path(folder_path)
    # Jeśli ścieżka kończy się na podfolder kierunku, baza sprawy = rodzic.
    if path.name in (SUBFOLDER_IN, SUBFOLDER_OUT):
        base = path.parent
    else:
        base = path
    (base / SUBFOLDER_IN).mkdir(parents=True, exist_ok=True)
    (base / SUBFOLDER_OUT).mkdir(parents=True, exist_ok=True)
    logger.info("Utworzono strukturę folderów: %s", base)
