# -*- mode: python ; coding: utf-8 -*-
"""Specyfikacja PyInstaller dla Księgi Kancelarii.

Budowa:
    pyinstaller ksiega_kancelarii.spec

Aby dołączyć Tesseract do paczki, ustaw zmienną środowiskową przed budową:
    set TESSERACT_DIR=C:\\Program Files\\Tesseract-OCR
Spec dołączy wtedy binaria Tesseract oraz pol.traineddata. Bez tej zmiennej
aplikacja użyje Tesseractu zainstalowanego w systemie (lub wskazanego w Ustawieniach).
"""

import os
from pathlib import Path

block_cipher = None

# Opcjonalne dołączenie Tesseract do paczki.
extra_datas = []
tess_dir = os.environ.get("TESSERACT_DIR", "")
if tess_dir and Path(tess_dir).exists():
    # Cały katalog Tesseract trafia do podfolderu 'tesseract' w paczce.
    extra_datas.append((tess_dir, "tesseract"))


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=extra_datas,
    hiddenimports=[
        "win32com.client",
        "pythoncom",
        "win32api",
        "win32print",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Usuń duplikaty: PyInstaller wykrywa biblioteki Tesseractu/ICU/Leptonica przez
# pytesseract i kopiuje je do głównego _internal — a my dołączamy CAŁY bundle
# Tesseractu osobno (datas → _internal/tesseract/). Bez tego filtra np.
# libtesseract-5.dll (~97 MB) i libicudt75.dll (~30 MB) lądują w paczce dwa razy.
# Aplikacja woła tesseract.exe wyłącznie z _internal/tesseract/, więc luźne kopie
# w _internal/ są zbędne. Zostawiamy je tylko, gdy NIE ma ich w bundlu.
if tess_dir and Path(tess_dir).exists():
    _bundle_dlls = {
        p.name.lower() for p in Path(tess_dir).rglob("*.dll")
    }
    a.binaries = [
        b for b in a.binaries
        if Path(b[0]).name.lower() not in _bundle_dlls
    ]


pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KsiegaKancelarii",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # aplikacja GUI — bez okna konsoli
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # ikona generowana w kodzie (QPainter, symbol §)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="KsiegaKancelarii",
)
