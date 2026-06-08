# CLAUDE.md — Księga Kancelarii

Przewodnik dla Claude Code po tym projekcie. Czytaj na początku każdej sesji.

## Czym jest projekt

Desktopowa aplikacja **Windows (PyQt6)** dla kancelarii radcy prawnego. Automatyzuje
prowadzenie księgi kancelaryjnej: rozpoznaje skany pism sądowych (PDF), wyciąga dane
(sygnatura, sąd, **strona reprezentowana / strona przeciwna**, typ pisma, data) przez
**Claude Haiku API**, segreguje pliki do folderów spraw i prowadzi przeszukiwalny rejestr
SQLite z eksportem do Excela. Działa w zasobniku systemowym (tray). Cały interfejs po polsku.

- **Repo:** https://github.com/zloty05/KsiegaKancelaria.git, branch `main`
- **Ścieżka:** `C:\Users\zloty\OneDrive\PROJEKTY KZ 2026\Księga_Kancelaria`
- **Użytkownik:** zloty05@gmail.com (buduje dla radcy prawnego jako klienta)

## ⚠️ Pułapki — przeczytaj zanim cokolwiek zrobisz

1. **GIT — zagnieżdżone repo.** Katalog domowy `C:\Users\zloty` jest OSOBNYM repo git
   (jego origin → `Konfigurator_promocyjny.git`, inny projekt!). To repo ma własny
   `.git` w folderze projektu i własny origin (`KsiegaKancelaria.git`).
   - **NIGDY `git add -A`** — stageuj jawnie pliki projektu. `git add -A` wciągnąłby
     cały katalog domowy (`.ssh`, `AppData`, sekrety).
   - Wszystkie polecenia git uruchamiaj z `git -C "<ścieżka projektu>"`.
   - Commit message przez here-doc (`git commit -F -`), bo polskie znaki i nawiasy
     psują się przy `-m "..."` w bashu.

2. **SSL / antywirus.** zloty ma **Norton**, radca ma **ESET** — oba robią inspekcję
   HTTPS i podstawiają własny root cert. `certifi` na tym pada (`CERTIFICATE_VERIFY_FAILED`).
   Rozwiązane paczką **`truststore`** (`inject_into_ssl()` w [main.py](main.py)) — używa
   magazynu certyfikatów Windows. NIE wracać do certifi-only, NIE hardkodować certu AV.

3. **Python 3.14.** Jedyna wersja w systemie. Wersje pakietów w
   [requirements.txt](requirements.txt) są ZAKTUALIZOWANE względem pierwotnej specyfikacji
   (która miała stare piny bez wheeli dla 3.14). Nie cofać do starych wersji.

## Stack i wersje

PyQt6 6.11 · watchdog 6.0 · pdfplumber 0.11.9 · pytesseract 0.3.13 · Pillow 12.2 ·
anthropic 0.105 · openpyxl 3.1.5 · pywin32 312 · truststore 0.10.4 · pyinstaller 6.20

- **Model Claude:** `claude-haiku-4-5-20251001`, max_tokens 300.
- **Tesseract OCR** 5.4.0 (winget UB-Mannheim) + `pol.traineddata` w
  `C:\Program Files\Tesseract-OCR\tessdata\`. Wymagany tylko dla skanów-obrazów;
  PDF z warstwą tekstową działa bez niego.

### Model danych pisma (pola wyciągane przez Claude)
`DocumentData`/tabela `pisma`: `sygnatura`, `sad`, `typ_pisma`, `data_pisma`,
**`strona_reprezentowana`**, **`strona_przeciwna`**.
- **Strony to NIE powód/pozwany.** „Reprezentowana" = strona, którą reprezentuje
  kancelaria (pełnomocnik); „przeciwna" = druga strona. Claude rozpoznaje to po
  **nazwiskach radców** z configu (`nazwiska_radcow`) — nazwa kancelarii sama nie wystarcza,
  bo OCR psuje polskie znaki (Radców→Radc�w), a nazwiska przeżywają. Gdy niejednoznaczne →
  **oba pola null** (świadoma decyzja: nie zgadywać). Bez `nazwiska_radcow` w Ustawieniach
  rozpoznawanie nie zadziała.
- **`data_pisma`** = data SPORZĄDZENIA (nagłówek przy miejscowości), NIE daty z treści
  (terminy, daty zgonu/faktur). Prompt to wymusza; dodatkowo `_fallback_data_pisma`
  (regex na polskie daty słowne „19 maja 2026", odporny na OCR) działa, gdy Claude da null.
- **Wcześniejsze nazwy pól** to `strona_powodowa`/`strona_pozwana` — w starych bazach
  migrowane automatycznie (patrz `init_db`, `ALTER TABLE RENAME COLUMN`).

## Architektura

```
config.py              Config (dataclass) + load/save config.json
database.py            SQLite (tabela pisma) + CRUD + export_to_excel
document_processor.py  pdfplumber → OCR (gdy <50 znaków) → Claude Haiku; scala strony, fallback dat
folder_matcher.py      dopasowanie po sygnaturze/nazwisku; suggest/create folderów spraw
file_watcher.py        watchdog → pyqtSignal (NIE dotyka GUI bezpośrednio)
printer.py             druk: docx→PDF (Word COM) → ShellExecute; pdf bezpośrednio
autostart.py           wpis HKCU\...\Run (autostart Windows)
main.py                punkt wejścia: truststore, jasny motyw, tray, okno
ui/
  main_window.py       QMainWindow, 3 zakładki, badge "•N" na Nowe
  tray.py              QSystemTrayIcon + menu
  icon.py              ikona § (QPainter, brak pliku .ico)
  toast.py             ToastNotification (fade in/out, prawy dolny róg)
  tab_new.py           tryb skanowania + kolejka kart, przenoszenie plików, DB, toast
  tab_register.py      tabela, szukaj/filtruj, eksport Excel, menu kontekstowe
  tab_settings.py      foldery, klucz API, nazwa kancelarii + nazwiska radców, autostart, Tesseract
  document_card.py     karta zatwierdzenia (edytowalne pola, folder docelowy)
  processing_worker.py QRunnable — przetwarzanie poza wątkiem GUI
ksiega_kancelarii.spec  PyInstaller (dołącza cały Tesseract; NIE filtruje DLL)
```

### Reguły, które łatwo złamać
- **ZERO asyncio** — PyQt6 ma własny event loop. Długie operacje (Claude, OCR, Word COM)
  w `QThreadPool`/`QRunnable` (patrz [processing_worker.py](ui/processing_worker.py)).
- **Watchdog → tylko pyqtSignal**, nigdy bezpośrednia modyfikacja widgetów.
- **Jasny motyw wymuszony** w main.py (`apply_light_theme`, styl Fusion). Bez tego
  w ciemnym motywie Windows tekst pól jest biały na białym. Nie dodawać kolorów
  per-widget — paleta globalna załatwia sprawę.
- **Skanowanie bierze tylko NOWE pliki** — pliki leżące w `_Nowe` przed włączeniem
  trybu są celowo pomijane (świadoma decyzja użytkownika; brak `existing_files`).
- **Strony PDF się SCALAJĄ, nie nadpisują.** `process_document` pyta Claude osobno o każdą
  stronę (do `MAX_PAGES=3`). Dane są w nagłówku str. 1; strony 2-3 zwracają zwykle null.
  `_merge_data` uzupełnia tylko PUSTE pola — NIGDY nie wracać do `best = result` (kasowało
  dobry wynik str. 1 pustą str. 2; objawiało się to pustymi kartami dla pism bez sygnatury).
  Pętla przerywa się przez `_ma_komplet_danych` (data+typ + sygnatura lub obie strony) —
  typowe pismo = 1 zapytanie zamiast 3. Bezpiecznik: gdy niekompletne, doczytuje kolejne.
- Folder docelowy w karcie przelicza się z EDYTOWANYCH pól przy zatwierdzeniu
  (`_edited_data` w [document_card.py](ui/document_card.py)), o ile użytkownik nie ustawił
  folderu ręcznie.

## Dane runtime (poza repo)

`%APPDATA%\KsiegaKancelarii\` — `config.json`, `kancelaria.db`, `kancelaria.log`.
Klucz API trzymany w config.json (nie w repo). `config.json` ma też `nazwa_kancelarii`
i `nazwiska_radcow` (potrzebne do rozpoznania strony reprezentowanej).
`Config.load` filtruje nieznane pola → dokładanie nowych pól jest wstecznie bezpieczne.

## Komendy

```powershell
# Dev: uruchom z venv
.venv\Scripts\python.exe main.py

# Build paczki .exe z dołączonym Tesseractem (chudy bundle ~50 MB źródła):
#   tesseract_bundle/ to odchudzony Tesseract (tylko exe + DLL + pol/eng/osd)
$env:TESSERACT_DIR="...\Księga_Kancelaria\tesseract_bundle"
.venv\Scripts\pyinstaller.exe --noconfirm --clean ksiega_kancelarii.spec
# wynik: dist\KsiegaKancelarii\ (~492 MB; ZIP ~186 MB)
```

- Przed buildem ZAMKNIJ działający .exe (`Stop-Process KsiegaKancelarii`), bo blokuje pliki.
  Czasem proces ma uprawnienia, których `Stop-Process` nie ubije — zamknij wtedy z traya
  lub Menedżera zadań ręcznie. `--clean` potrafi paść na blokadzie `build\` (OneDrive) —
  usuń wtedy `build\` i `dist\` ręcznie i buduj bez `--clean`.
- **NIE filtrujemy DLL w `.spec`.** Próby usuwania „duplikatów" Tesseractu psuły paczkę:
  raz wycięły `libffi-8.dll` Pythona (→ `DLL load failed while importing _ctypes`, pada OCR,
  pliki-obrazy lądują w FALLBACK z pustymi polami), raz `libarchive-13.dll` i pół bundla
  (→ `tesseract.exe` nie startuje). Pełna, cięższa paczka > mniejszy, kruchy ZIP. Jeśli
  kiedyś wrócisz do odchudzania: testuj URUCHOMIENIE .exe na czystej maszynie po każdej
  zmianie, bo venv tego nie wyłapie (tam DLL Pythona są na miejscu systemowo).
- W paczce kod szuka Tesseractu w `sys._MEIPASS/tesseract` (`_bundled_tesseract`).

## Dystrybucja do radcy

`dist\KsiegaKancelarii\` + `INSTRUKCJA_DLA_RADCY.txt` → ZIP → WeTransfer/Dysk (za duże na mail).
Klucz API wysyłać OSOBNO (jak hasło). Windows/ESET ostrzeże o niepodpisanym .exe
(„Uruchom mimo to") — zniknie dopiero z certyfikatem podpisywania kodu.
- **Po instalacji radca MUSI wpisać w Ustawieniach** nazwę kancelarii i nazwiska radców
  (np. `Chmielewska-Szylar, Majchrzak`) — bez tego pola strony zostają puste.
- Jego stara baza zmigruje się sama przy pierwszym uruchomieniu (powodowa→reprezentowana).
- **Pisma testowe radcy są w `przykłady/` (gitignore — dane osobowe).** Skany bez warstwy
  tekstowej (idą przez OCR); dobre do testów dat i rozpoznawania stron.

## Stan / TODO

- ✅ v1.0 działa: skanowanie, OCR, Claude, rejestr, eksport, druk, tray, paczka .exe
- ✅ Wersja testowa zaakceptowana przez radcę
- ✅ v1.1: rozbicie stron (reprezentowana/przeciwna + rozpoznawanie po nazwiskach radców),
  lepsze wykrywanie dat (prompt + fallback słowny), scalanie stron + stop po komplecie,
  migracja bazy. Paczka przebudowana i przetestowana (start .exe OK).
- Możliwe później: certyfikat podpisywania kodu; instalator (Inno Setup) zamiast ZIP;
  fallback dat działa tylko gdy API odpowie — gdy całe wywołanie padnie (brak sieci),
  data nie jest wyciągana z OCR (do rozważenia, jeśli radca zgłosi).
