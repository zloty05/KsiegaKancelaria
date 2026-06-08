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
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 300
MAX_PAGES = 3
MIN_TEXT_LEN = 50  # poniżej tej długości tekstu uruchamiamy OCR

# Polskie nazwy miesięcy w dopełniaczu → numer. Klucze zredukowane do ASCII
# (bez ogonków), bo OCR psuje polskie znaki — porównujemy po _ascii_month().
_MIESIACE = {
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4,
    "maja": 5, "czerwca": 6, "lipca": 7, "sierpnia": 8,
    "wrzesnia": 9, "pazdziernika": 10, "listopada": 11, "grudnia": 12,
    # OCR często gubi "ś"/"ź" w nazwach — warianty bez tych liter:
    "wrzenia": 9, "padziernika": 10,
}

SYSTEM_PROMPT = """\
Jesteś asystentem kancelarii prawnej. Wyciągasz dane z pism sądowych.
Odpowiadaj WYŁĄCZNIE w formacie JSON, bez żadnego dodatkowego tekstu.
Jeśli danych nie ma w tekście, użyj null.
Tekst pochodzi z OCR i może mieć uszkodzone polskie znaki — interpretuj go mimo to."""

USER_PROMPT_TEMPLATE = """\
Wyciągnij dane z poniższego pisma sądowego i zwróć WYŁĄCZNIE JSON:
{{
  "sygnatura": "sygnatura akt sprawy np. I C 123/24 lub null",
  "sad": "pełna nazwa sądu lub null",
  "typ_pisma": "typ pisma np. Wyrok, Postanowienie, Pozew, Wezwanie, Wniosek lub null",
  "data_pisma": "data SPORZĄDZENIA pisma w formacie YYYY-MM-DD lub null",
  "strona_reprezentowana": "osoba/podmiot reprezentowany przez naszą kancelarię lub null",
  "strona_przeciwna": "druga strona (przeciwnik) lub null"
}}

ZASADY dla data_pisma:
- To data SPORZĄDZENIA/WYSŁANIA pisma — ZAWSZE na POCZĄTKU dokumentu: w prawym
  górnym rogu, w nagłówku obok miejscowości lub w pierwszym zdaniu. Bierz
  PIERWSZĄ datę idąc od góry. Format dowolny: "13-04-2026", "13.04.2026",
  "2026-04-13" lub słowny "13 kwietnia 2026r.".
- NIE bierz dat z TREŚCI: terminów płatności, rat, tabel kosztów, dat zgonu
  ("zm. ..."), dat faktur, dat odsetek ("od dnia ..."), terminów ("do dnia ...").
- Jeśli na początku jest kilka dat — wybierz najwcześniej występującą (najwyżej).

ZASADY dla stron (KLUCZOWE):
- Naszą kancelarię reprezentują radcowie: {nazwiska_radcow}
  (kancelaria: {nazwa_kancelarii}).
- Znajdź zwrot "reprezentowany/a przez", "repr. przez" lub "w imieniu" wskazujący,
  przy KTÓREJ stronie stoją nasi radcowie (dopasuj po NAZWISKACH — nazwa kancelarii
  bywa zniekształcona przez OCR).
- Ta strona to "strona_reprezentowana", druga to "strona_przeciwna".
- W polach podaj OSOBY/PODMIOTY z dokumentu, NIGDY nazwy naszej kancelarii ani
  nazwisk naszych radców.
- Jeśli NIE potrafisz jednoznacznie ustalić, którą stronę reprezentujemy —
  ustaw OBA pola na null. NIE zgaduj.

Tekst pisma:
{tekst}"""


@dataclass
class DocumentData:
    """Dane wyciągnięte z pisma. Wszystkie pola mogą być None."""

    sygnatura: Optional[str] = None
    sad: Optional[str] = None
    typ_pisma: Optional[str] = None
    data_pisma: Optional[str] = None
    strona_reprezentowana: Optional[str] = None
    strona_przeciwna: Optional[str] = None
    source_page: int = 0  # która strona dała wynik (1/2/3); 0 = brak


def _bundled_tesseract() -> Optional[str]:
    """Ścieżka do Tesseractu dołączonego do paczki PyInstaller (jeśli istnieje).

    W paczce (sys.frozen) pliki leżą w sys._MEIPASS; .spec dołącza Tesseract do
    podfolderu 'tesseract'. Ustawiamy też TESSDATA_PREFIX, by OCR znalazł pol.traineddata.
    """
    import sys

    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    exe = Path(base) / "tesseract" / "tesseract.exe"
    if exe.exists():
        tessdata = exe.parent / "tessdata"
        if tessdata.exists():
            os.environ.setdefault("TESSDATA_PREFIX", str(tessdata))
        return str(exe)
    return None


def _resolve_tesseract(tesseract_path: str = "") -> Optional[str]:
    """Ustala ścieżkę do tesseract.exe: jawna → paczka → PATH → typowe lokalizacje."""
    if tesseract_path and Path(tesseract_path).exists():
        return tesseract_path
    bundled = _bundled_tesseract()
    if bundled:
        return bundled
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


def _ascii_month(name: str) -> str:
    """Redukuje nazwę miesiąca do ASCII (usuwa ogonki i znaki zastępcze OCR)."""
    repl = str.maketrans("ąćęłńóśźż", "acelnoszz")
    s = name.lower().translate(repl)
    return "".join(ch for ch in s if ch.isalpha())


# Okno nagłówka: data SPORZĄDZENIA jest na początku pisma (prawy górny róg,
# nagłówek lub pierwsze zdanie). Skanujemy tylko tyle, by nie sięgnąć treści,
# gdzie roją się daty-pułapki (terminy, raty, tabele kosztów, daty wyroków).
_HEAD_LEN = 500

# Polska data słowna: "19 maja 2026" (klasa miesiąca dopuszcza znak zastępczy OCR �).
_DATA_SLOWNA = re.compile(
    r"(\d{1,2})\s+([A-Za-ząćęłńóśźżĄĆĘŁŃÓŚŹŻ�]+)\s+(\d{4})"
)

# Data cyfrowa w nagłówku: DD-MM-YYYY / DD.MM.YYYY / DD/MM/YYYY oraz ISO YYYY-MM-DD.
# Wymagamy separatorów i 4-cyfrowego roku, by nie łapać sygnatur (np. "126/25").
_DATA_CYFROWA = re.compile(
    r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})(?!\d)"
)
_DATA_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")


def _valid_date(year: int, month: int, day: int) -> Optional[str]:
    """Zwraca YYYY-MM-DD, gdy składowe tworzą sensowną datę, inaczej None."""
    if 1 <= day <= 31 and 1 <= month <= 12 and 2000 <= year <= 2100:
        return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def _fallback_data_pisma(text: str) -> Optional[str]:
    """Pierwsza data od góry = data SPORZĄDZENIA pisma. Zwraca YYYY-MM-DD lub None.

    Reguła pozycyjna: data sporządzenia/wysłania jest zawsze na początku pisma
    (prawy górny róg, nagłówek lub pierwsze zdanie) — w dowolnym formacie:
    cyfrowym ("13-04-2026", "13.04.2026"), ISO ("2026-04-13") lub słownym
    ("13 kwietnia 2026"). Bierzemy NAJWCZEŚNIEJ występującą sensowną datę w oknie
    nagłówka, więc daty z treści (raty, terminy, tabele kosztów) nie wchodzą w grę.
    """
    head = text[:_HEAD_LEN]

    # Zbierz kandydatów z trzech formatów wraz z pozycją wystąpienia w tekście.
    candidates: list[tuple[int, str]] = []

    for m in _DATA_ISO.finditer(head):
        iso = _valid_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if iso:
            candidates.append((m.start(), iso))

    for m in _DATA_CYFROWA.finditer(head):
        iso = _valid_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if iso:
            candidates.append((m.start(), iso))

    for m in _DATA_SLOWNA.finditer(head):
        month = _MIESIACE.get(_ascii_month(m.group(2)))
        if month:
            iso = _valid_date(int(m.group(3)), month, int(m.group(1)))
            if iso:
                candidates.append((m.start(), iso))

    if not candidates:
        return None
    # Pierwsza data idąc od góry (najmniejsza pozycja w tekście).
    candidates.sort(key=lambda c: c[0])
    return candidates[0][1]


def _analyze_text(
    text: str,
    api_key: str,
    nazwa_kancelarii: str = "",
    nazwiska_radcow: str = "",
) -> Optional[DocumentData]:
    """Wysyła tekst do Claude Haiku i zwraca DocumentData lub None przy błędzie."""
    if not api_key:
        logger.info("Brak klucza API — pomijam analizę Claude")
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        prompt = USER_PROMPT_TEMPLATE.format(
            tekst=text[:6000],
            nazwa_kancelarii=nazwa_kancelarii or "(brak danych)",
            nazwiska_radcow=nazwiska_radcow or "(brak danych)",
        )
        msg = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(block.text for block in msg.content if block.type == "text")
        data = _parse_claude_json(raw)
        result = DocumentData(
            sygnatura=_normalize(data.get("sygnatura")),
            sad=_normalize(data.get("sad")),
            typ_pisma=_normalize(data.get("typ_pisma")),
            data_pisma=_normalize(data.get("data_pisma")),
            strona_reprezentowana=_normalize(data.get("strona_reprezentowana")),
            strona_przeciwna=_normalize(data.get("strona_przeciwna")),
        )
        # Data sporządzenia = pierwsza data od góry (reguła pozycyjna). Ma
        # PIERWSZEŃSTWO przed Claude: model myli się przy dokumentach z gęstwą
        # dat w treści (tabele kosztów, raty) i bierze datę z treści zamiast
        # nagłówka. Reguła patrzy na pozycję, nie na sens — i tu jest pewniejsza.
        # Claude zostaje tylko gdy reguła nic nie znajdzie w oknie nagłówka.
        head_date = _fallback_data_pisma(text)
        if head_date is not None:
            result.data_pisma = head_date
        return result
    except Exception as exc:  # noqa: BLE001 — błąd API nie może blokować aplikacji
        logger.warning("Analiza Claude nie powiodła się: %s", exc)
        return None


def _merge_data(best: DocumentData, new: DocumentData, page_num: int) -> None:
    """Uzupełnia puste pola `best` wartościami z `new` (nie nadpisuje istniejących).

    Kolejne strony pisma zwykle zwracają mniej danych (często same null), więc
    pierwsza strona, na której pole zostało wykryte, jest wiarygodna i zostaje.
    """
    for field in (
        "sygnatura", "sad", "typ_pisma", "data_pisma",
        "strona_reprezentowana", "strona_przeciwna",
    ):
        if getattr(best, field) is None and getattr(new, field) is not None:
            setattr(best, field, getattr(new, field))
            if best.source_page == 0:
                best.source_page = page_num


def _ma_komplet_danych(d: DocumentData) -> bool:
    """Czy mamy dość danych, by przerwać skanowanie kolejnych stron.

    Dane pisma są zwykle w nagłówku 1. strony. Uznajemy za komplet, gdy mamy
    datę i typ oraz albo sygnaturę (klasyczne pismo sądowe), albo obie strony
    (pisma procesowe/wezwania bez sygnatury). Bez tego doczytujemy kolejne strony.
    """
    if not (d.data_pisma and d.typ_pisma):
        return False
    if d.sygnatura:
        return True
    return bool(d.strona_reprezentowana and d.strona_przeciwna)


def process_document(
    file_path: str,
    api_key: str,
    tesseract_path: str = "",
    nazwa_kancelarii: str = "",
    nazwiska_radcow: str = "",
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
                result = _analyze_text(
                    text, api_key, nazwa_kancelarii, nazwiska_radcow
                )
                if result is None:
                    continue
                # Scal: uzupełniaj puste pola best danymi z tej strony, ale NIE
                # nadpisuj już znalezionych (kolejne strony często zwracają null).
                _merge_data(best, result, page_num)
                # Komplet danych nagłówka → nie ma sensu OCR-ować i odpytywać dalej.
                # Dane pisma są zwykle na 1. stronie; kolejne strony to ciąg treści.
                if _ma_komplet_danych(best):
                    break
    except Exception as exc:  # noqa: BLE001
        logger.error("Błąd przetwarzania PDF %s: %s", file_path, exc)

    return best
