# Księga Kancelarii v1.0

Desktopowa aplikacja Windows dla kancelarii radcy prawnego. Automatyzuje prowadzenie
rejestru pism **przychodzących** (skany z drukarki, np. Kyocera) i **wychodzących**
(dokumenty Word/PDF). Zastępuje papierową księgę kancelaryjną.

## Funkcje

- **Tryb skanowania** — monitoruje folder `_Nowe\` i automatycznie przetwarza nowe PDF.
- **Ekstrakcja danych** — pdfplumber dla PDF z warstwą tekstową, OCR (Tesseract, język
  polski) dla skanów-obrazów, analiza pisma przez Claude Haiku (sygnatura, sąd, typ
  pisma, data, strony).
- **Karty zatwierdzenia** — edytowalne pola, propozycja folderu sprawy, Zatwierdź/Odrzuć.
- **Dopasowanie folderów** — po sygnaturze (priorytet) lub nazwisku strony; przy braku
  proponuje nowy folder `Sprawy\YYYY\Nazwisko\Sygnatura\{przychodzące|wychodzące}\`.
- **Rejestr** — przeszukiwalna tabela, otwieranie plików/folderów, eksport do Excel.
- **Pisma wychodzące** — rejestracja docx/pdf z opcjonalnym drukiem (Word COM → PDF).
- **System tray** — aplikacja działa w tle, autostart z Windows.

## Wymagania

- Windows 10/11
- Python 3.14 (wersje pakietów w `requirements.txt` są dobrane pod 3.14)
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) z językiem **polskim**
  (`pol.traineddata`) — wymagany tylko dla skanów-obrazów; PDF z tekstem działa bez niego.
- MS Word — wymagany tylko do druku plików `.docx` (konwersja do PDF).
- Klucz API Anthropic (konfigurowany w zakładce Ustawienia).

## Instalacja (z kodu)

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

Instalacja Tesseract (winget):

```powershell
winget install -e --id UB-Mannheim.TesseractOCR --source winget
# + pobierz pol.traineddata do C:\Program Files\Tesseract-OCR\tessdata\
```

## Pierwsze uruchomienie

1. Uruchom aplikację — pojawi się ikona § w zasobniku (tray).
2. Otwórz okno (dwuklik na ikonę) → zakładka **Ustawienia**:
   - ustaw folder skanów `_Nowe` i główny folder spraw,
   - wklej klucz API Anthropic,
   - (opcjonalnie) włącz autostart.
3. Zakładka **Nowe** → włącz **Tryb skanowania**.
4. Wrzuć skan PDF do folderu `_Nowe\` → pojawi się karta z danymi → Zatwierdź.

## Dane aplikacji

Konfiguracja, baza i log są przechowywane w `%APPDATA%\KsiegaKancelarii\`:
- `config.json` — ustawienia
- `kancelaria.db` — baza SQLite rejestru
- `kancelaria.log` — log błędów

## Budowa .exe (PyInstaller)

```powershell
# (opcjonalnie) dołącz Tesseract do paczki:
set TESSERACT_DIR=C:\Program Files\Tesseract-OCR
.venv\Scripts\pyinstaller ksiega_kancelarii.spec
# wynik: dist\KsiegaKancelarii\KsiegaKancelarii.exe
```

## Architektura

| Moduł | Rola |
|-------|------|
| `config.py` | konfiguracja (config.json w %APPDATA%) |
| `database.py` | SQLite + eksport Excel |
| `document_processor.py` | pdfplumber + OCR + Claude Haiku |
| `folder_matcher.py` | dopasowanie/tworzenie folderów spraw |
| `file_watcher.py` | watchdog (pyqtSignal) |
| `printer.py` | druk (Word COM + ShellExecute) |
| `autostart.py` | wpis autostartu w rejestrze |
| `main.py` | punkt wejścia, tray + okno |
| `ui/` | komponenty PyQt6 (okno, zakładki, toast, karta, worker) |

Długie operacje (Claude API, OCR, konwersja Word) wykonywane są w `QThreadPool`,
aby nie blokować GUI. Watchdog komunikuje się z GUI wyłącznie przez sygnały Qt.
