# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec dla Multiplekser Portable (.exe na Windows, bez Dockera) - patrz
docs/RAPORT_PORTABLE_1.md.

Zaklada, ze PRZED uruchomieniem `pyinstaller multiplekser_portable.spec`:
1. frontend zostal zbudowany (`npm run build` w ../frontend) i skopiowany do
   backend/frontend_dist/ (patrz .github/workflows/build-portable.yml - robi to automatycznie).
2. Zaleznosci sa zainstalowane z requirements-portable.txt (nie samego requirements.txt -
   PyInstaller nie jest tam, zeby nie bylo go w obrazie Docker/produkcyjnym).

Buduje pojedynczy plik .exe (`--onefile`, patrz `EXE(..., ...)` nizej) - jeden plik do pobrania i
uruchomienia, kosztem troche wolniejszego startu (samorozpakowanie do folderu tymczasowego przy
kazdym uruchomieniu, standardowe zachowanie PyInstallera w tym trybie).
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [
    ("frontend_dist", "frontend_dist"),
    ("tests/fixtures/baza_elektryka.json", "tests/fixtures"),
    ("tests/fixtures/baza_hydraulika.json", "tests/fixtures"),
]
binaries = []
hiddenimports = [
    "app.modules.documents.models",
    "app.modules.matcher.models",
    "app.modules.products.models",
    "app.modules.users.models",
]

# Pakiety z dynamicznymi importami (protokoly uvicorn, zaleznosci passlib/bcrypt) - statyczna
# analiza PyInstallera ich nie widzi, trzeba dolaczyc jawnie.
for pkg in ("uvicorn", "fastapi", "pydantic", "passlib", "bcrypt", "PIL"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Celery/kombu/billiard sa tylko SKONSTRUOWANE w trybie desktop (nigdy nie polaczone/uzyte -
# patrz dispatch_ocr_task w app/modules/documents/tasks.py), ale samo `Celery(...)` w
# app/core/celery_app.py i tak dynamicznie importuje kilka wlasnych podmodulow (np.
# celery.fixups) przez importlib - zwykla analiza PyInstallera tego nie widzi.
# collect_submodules() (nie collect_all()) - bez danych/binariow z pkg_resources/entry-pointow,
# ktore w praktyce lamaly build przy nowszym setuptools (patrz requirements-portable.txt).
for pkg in ("celery", "kombu", "billiard"):
    hiddenimports += collect_submodules(pkg)

a = Analysis(
    ["desktop_main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "moto"],  # dev/test-only, nie potrzebne w exe
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Multiplekser",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # bez okna terminala - patrz docs/RAPORT_PORTABLE_1.md, "bez terminala"
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
