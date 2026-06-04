"""Drukowanie plików na drukarce Windows.

- .docx → konwersja do PDF przez Word COM, potem druk PDF.
- .pdf  → druk przez ShellExecute "print" (domyślna aplikacja PDF / drukarka).

Gdy MS Word nie jest dostępny, druk .docx nie powiedzie się — zwracamy False
z czytelnym logiem, ale aplikacja nie jest blokowana.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _docx_to_pdf(docx_path: str) -> Optional[str]:
    """Konwertuje .docx do PDF przez Word COM. Zwraca ścieżkę PDF lub None."""
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        logger.error("Brak pywin32 — nie można użyć Word COM")
        return None

    pythoncom.CoInitialize()
    word = None
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(str(Path(docx_path).resolve()))
        pdf_path = str(Path(tempfile.gettempdir()) / (Path(docx_path).stem + ".pdf"))
        # 17 = wdFormatPDF
        doc.SaveAs(pdf_path, FileFormat=17)
        doc.Close(False)
        logger.info("Skonwertowano %s -> %s", docx_path, pdf_path)
        return pdf_path
    except Exception as exc:  # noqa: BLE001
        logger.error("Konwersja Word->PDF nie powiodła się (czy MS Word jest zainstalowany?): %s", exc)
        return None
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:  # noqa: BLE001
                pass
        pythoncom.CoUninitialize()


def _print_pdf(pdf_path: str, printer_name: Optional[str] = None) -> bool:
    """Drukuje PDF. Próbuje win32api.ShellExecute z czasownikiem 'print'/'printto'."""
    try:
        import win32api

        if printer_name:
            win32api.ShellExecute(
                0, "printto", pdf_path, f'"{printer_name}"', ".", 0
            )
        else:
            win32api.ShellExecute(0, "print", pdf_path, None, ".", 0)
        logger.info("Wysłano do druku: %s", pdf_path)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Druk PDF nie powiódł się: %s", exc)
        return False


def print_file(file_path: str, printer_name: Optional[str] = None) -> bool:
    """Drukuje plik (.pdf lub .docx). Zwraca True przy powodzeniu."""
    if not os.path.exists(file_path):
        logger.error("Plik do druku nie istnieje: %s", file_path)
        return False

    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return _print_pdf(file_path, printer_name)
    if ext == ".docx":
        pdf = _docx_to_pdf(file_path)
        if pdf is None:
            return False
        return _print_pdf(pdf, printer_name)

    logger.error("Nieobsługiwany format do druku: %s", ext)
    return False
