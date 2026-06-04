"""Przetwarzanie dokumentów: ekstrakcja tekstu (PDF/OCR) + analiza Claude Haiku.

Algorytm:
  1. Otwórz PDF przez pdfplumber.
  2. Dla stron 1..3:
     a. Wyciągnij tekst; jeśli < 50 znaków → OCR (pytesseract, lang='pol').
     b. Wyślij tekst do Claude Haiku, sparsuj JSON.
     c. Jeśli jest sygnatura → przerwij (mamy dane).
  3. Zwróć DocumentData (nawet częściowy). Błędy nie blokują — pola pozostają None.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 300
MAX_PAGES = 3
MIN_TEXT_LEN = 50  # poniżej tej długości tekstu uruchamiamy OCR

SYSTEM_PROMPT = """\
Jesteś asystentem kancelarii prawnej. Wyciągasz dane z pism sądowych.
Odpowiadaj WYŁĄCZNIE w formacie JSON, bez żadnego dodatkowego tekstu.
Jeśli danych nie ma w tekście, użyj null."""

USER_PROMPT_TEMPLATE = """\
Wyciągnij dane z poniższego pisma sądowego i zwróć JSON:
{{
  "sygnatura": "sygnatura akt sprawy np. I C 123/24 lub null",
  "sad": "pełna nazwa sądu lub null",
  "typ_pisma": "typ pisma np. Wyrok, Postanowienie, Wezwanie, Zawiadomienie lub null",
  "data_pisma": "data w formacie YYYY-MM-DD lub null",
  "strona_powodowa": "imię i nazwisko lub nazwa firmy powoda lub null",
  "strona_pozwana": "imię i nazwisko lub nazwa firmy pozwanego lub null"
}}

Tekst pisma:
{tekst}"""


@dataclass
class DocumentData:
    """Dane wyciągnięte z pisma. Wszystkie pola mogą być None."""

    sygnatura: Optional[str] = None
    sad: Optional[str] = None
    typ_pisma: Optional[str] = None
    data_pisma: Optional[str] = None
    strona_powodowa: Optional[str] = None
    strona_pozwana: Optional[str] = None
    source_page: int = 0  # która strona dała wynik (1/2/3); 0 = brak


def _resolve_tesseract(tesseract_path: str = "") -> Optional[str]:
    """Ustala ścieżkę do tesseract.exe: jawna → PATH → typowe lokalizacje."""
    if tesseract_path and Path(tesseract_path).exists():
        return tesseract_path
    found = shutil.which("tesseract")
    if found:
        return found
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def tesseract_available(tesseract_path: str = "") -> bool:
    """Czy Tesseract jest dostępny (do ostrzeżenia w Ustawieniach)."""
    return _resolve_tesseract(tesseract_path) is not None


def _ocr_page(page, tesseract_path: str = "") -> str:
    """OCR pojedynczej strony pdfplumber (lang='pol'). Zwraca tekst lub ''."""
    exe = _resolve_tesseract(tesseract_path)
    if not exe:
        logger.warning("Tesseract niedostępny — pomijam OCR strony")
        return ""
    try:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = exe
        # Renderuj stronę do obrazu i puść OCR.
        image = page.to_image(resolution=300).original
        return pytesseract.image_to_string(image, lang="pol")
    except Exception as exc:  # noqa: BLE001 — OCR nie może wywrócić aplikacji
        logger.warning("OCR strony nie powiódł się: %s", exc)
        return ""


def _extract_page_text(page, tesseract_path: str = "") -> str:
    """Tekst strony: warstwa tekstowa, a gdy zbyt krótka — OCR."""
    text = page.extract_text() or ""
    if len(text.strip()) < MIN_TEXT_LEN:
        ocr = _ocr_page(page, tesseract_path)
        if len(ocr.strip()) > len(text.strip()):
            text = ocr
    return text


def _parse_claude_json(raw: str) -> dict:
    """Wyciąga obiekt JSON z odpowiedzi modelu (toleruje otoczkę tekstową)."""
    raw = raw.strip()
    # Usuń ewentualne ogrodzenie ```json ... ```
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lstrip().lower().startswith("json"):
            raw = raw.lstrip()[4:]
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Brak obiektu JSON w odpowiedzi")
    return json.loads(raw[start : end + 1])


def _normalize(value) -> Optional[str]:
    """Zamienia null/"null"/puste na None, resztę przycina do str."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "brak"):
        return None
    return s


def _analyze_text(text: str, api_key: str) -> Optional[DocumentData]:
    """Wysyła tekst do Claude Haiku i zwraca DocumentData lub None przy błędzie."""
    if not api_key:
        logger.info("Brak klucza API — pomijam analizę Claude")
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": USER_PROMPT_TEMPLATE.format(tekst=text[:6000])}
            ],
        )
        raw = "".join(block.text for block in msg.content if block.type == "text")
        data = _parse_claude_json(raw)
        return DocumentData(
            sygnatura=_normalize(data.get("sygnatura")),
            sad=_normalize(data.get("sad")),
            typ_pisma=_normalize(data.get("typ_pisma")),
            data_pisma=_normalize(data.get("data_pisma")),
            strona_powodowa=_normalize(data.get("strona_powodowa")),
            strona_pozwana=_normalize(data.get("strona_pozwana")),
        )
    except Exception as exc:  # noqa: BLE001 — błąd API nie może blokować aplikacji
        logger.warning("Analiza Claude nie powiodła się: %s", exc)
        return None


def process_document(
    file_path: str, api_key: str, tesseract_path: str = ""
) -> DocumentData:
    """Przetwarza PDF i zwraca DocumentData.

    Nigdy nie rzuca w normalnym toku — przy błędach zwraca DocumentData z None,
    aby radca mógł uzupełnić dane ręcznie.
    """
    path = Path(file_path)
    if not path.exists():
        logger.error("Plik nie istnieje: %s", file_path)
        return DocumentData()

    try:
        import pdfplumber
    except ImportError:
        logger.error("Brak pdfplumber")
        return DocumentData()

    best = DocumentData()
    try:
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages[:MAX_PAGES], start=1):
                text = _extract_page_text(page, tesseract_path)
                if len(text.strip()) < 10:
                    continue
                result = _analyze_text(text, api_key)
                if result is None:
                    continue
                result.source_page = page_num
                best = result
                if result.sygnatura:  # mamy sygnaturę → koniec
                    break
    except Exception as exc:  # noqa: BLE001
        logger.error("Błąd przetwarzania PDF %s: %s", file_path, exc)

    return best
