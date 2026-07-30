"""Multiplekser Portable - punkt wejscia dla wersji .exe na Windows (bez Dockera, bez
Postgresa/Redis/MinIO, bez terminala) - patrz docs/RAPORT_PORTABLE_1.md.

Rozni sie od normalnego wdrozenia (Docker/produkcja) WYLACZNIE konfiguracja, nie logika:
SQLite zamiast Postgresa, folder na dysku zamiast MinIO, watek w procesie zamiast Celery/Redis -
patrz app/core/config.py (`desktop_mode`), app/modules/documents/storage.py (`LocalFileStorage`),
app/modules/documents/tasks.py (`dispatch_ocr_task`). Caly kod biznesowy (parser/matcher/
generator/OCR) jest DOKLADNIE ten sam co w wersji Docker.

WAZNE: zmienne srodowiskowe (DATABASE_URL/DESKTOP_MODE/...) MUSZA byc ustawione PRZED
pierwszym importem czegokolwiek z `app.*` - `app.core.config.settings` to singleton tworzony
przy imporcie modulu (`Settings()` na koncu pliku), pydantic-settings czyta os.environ w tym
momencie. Dlatego wszystkie importy `app.*` w tym pliku sa lokalne (wewnatrz funkcji), nie na
gorze pliku.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import time
import webbrowser
from pathlib import Path

APP_PORT = 8765
CONFIG_FILENAME = "config.json"
DB_FILENAME = "multiplekser.db"


def resource_path(relative: str) -> Path:
    """Sciezka do zasobu spakowanego w exe (PyInstaller `--add-data`, patrz
    multiplekser_portable.spec) albo, przy uruchomieniu ze zrodel (development/testy), sciezka
    wzgledem tego pliku."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / relative


def data_dir() -> Path:
    """Folder na dane uzytkownika - OBOK pliku .exe (nie w AppData), zeby aplikacja byla
    faktycznie 'portable': cala jej zawartosc (program + baza + dokumenty) mozna przeniesc razem,
    np. na pendrive. Gdy uruchomiona ze zrodel (development), to `backend/dane/` w repo."""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    d = base / "dane"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_config(dir_: Path) -> dict | None:
    path = dir_ / CONFIG_FILENAME
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(dir_: Path, config: dict) -> None:
    (dir_ / CONFIG_FILENAME).write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def build_first_run_config(admin_email: str, admin_password: str, gemini_api_key: str) -> dict:
    """Wydzielone od okna dialogowego (ponizej) - testowalne bez tkinter/GUI."""
    return {
        "admin_email": admin_email,
        "admin_password": admin_password,
        "gemini_api_key_free": gemini_api_key,
        "jwt_secret_key": secrets.token_hex(32),
    }


def collect_first_run_config_via_dialog() -> dict | None:
    """Okno startowe (tylko przy pierwszym uruchomieniu - patrz load_config) - zbiera dane
    potrzebne do dzialania bez terminala/edycji plikow. Zwraca None jesli uzytkownik anulowal."""
    import tkinter as tk
    from tkinter import messagebox, ttk

    result: dict = {}

    root = tk.Tk()
    root.title("Multiplekser - pierwsze uruchomienie")
    root.geometry("480x320")

    ttk.Label(root, text="Witaj! Zanim zaczniesz, uzupelnij:", font=("", 11, "bold")).pack(pady=(16, 8))

    frame = ttk.Frame(root)
    frame.pack(fill="both", expand=True, padx=20)

    ttk.Label(frame, text="Adres e-mail administratora:").pack(anchor="w", pady=(8, 0))
    email_var = tk.StringVar()
    ttk.Entry(frame, textvariable=email_var, width=50).pack(fill="x")

    ttk.Label(frame, text="Haslo administratora:").pack(anchor="w", pady=(8, 0))
    password_var = tk.StringVar()
    ttk.Entry(frame, textvariable=password_var, show="*", width=50).pack(fill="x")

    ttk.Label(frame, text="Klucz Gemini API (Google AI Studio, darmowy poziom):").pack(anchor="w", pady=(8, 0))
    gemini_var = tk.StringVar()
    ttk.Entry(frame, textvariable=gemini_var, width=50).pack(fill="x")
    ttk.Label(
        frame, text="Klucz pozniej mozna zmienic edytujac dane/config.json", foreground="gray",
    ).pack(anchor="w", pady=(2, 0))

    def on_submit() -> None:
        if not email_var.get().strip() or not password_var.get() or not gemini_var.get().strip():
            messagebox.showerror("Multiplekser", "Wszystkie pola sa wymagane.")
            return
        result["admin_email"] = email_var.get().strip()
        result["admin_password"] = password_var.get()
        result["gemini_api_key"] = gemini_var.get().strip()
        root.destroy()

    ttk.Button(root, text="Uruchom Multiplekser", command=on_submit).pack(pady=16)
    root.mainloop()

    if not result:
        return None
    return build_first_run_config(result["admin_email"], result["admin_password"], result["gemini_api_key"])


def apply_env(config: dict, dir_: Path) -> None:
    os.environ["DESKTOP_MODE"] = "true"
    os.environ["DATABASE_URL"] = f"sqlite:///{(dir_ / DB_FILENAME).as_posix()}"
    os.environ["LOCAL_STORAGE_PATH"] = str(dir_ / "dokumenty")
    os.environ["JWT_SECRET_KEY"] = config["jwt_secret_key"]
    if config.get("gemini_api_key_free"):
        os.environ["GEMINI_API_KEY_FREE"] = config["gemini_api_key_free"]


def bootstrap_first_run(config: dict) -> None:
    """Wywolywane WYLACZNIE przy pierwszym uruchomieniu (swiezy plik SQLite) - tworzy tabele,
    importuje oba katalogi produktowe (Elektryka + Hydraulika), reguly specjalne i konto admina.
    Odpowiednik `alembic upgrade head` + `scripts.import_catalog` (x2) +
    `scripts.import_special_rules` + `scripts.create_admin` z README (sciezka Docker) - te same
    funkcje, wywolane bezposrednio zamiast przez CLI/`docker compose exec`."""
    import json as _json

    from app.core.db import Base, SessionLocal, engine

    # Import jawny wszystkich modeli ORM PRZED create_all - bez tego Base.metadata nie zna
    # tabel document/document_item/special_rule (ten sam blad juz raz naprawiony gdzie indziej,
    # patrz identyczny komentarz w tests/conftest.py i app/core/celery_app.py).
    from app.modules.documents import models as _documents_models  # noqa: F401
    from app.modules.matcher import models as _matcher_models  # noqa: F401
    from app.modules.products import models as _products_models  # noqa: F401
    from app.modules.users import models as _users_models  # noqa: F401
    from app.modules.matcher.special_rules import DEFAULT_SPECIAL_RULES
    from app.modules.users.repository import create_user
    from scripts.import_catalog import import_catalog
    from scripts.import_special_rules import import_special_rules

    Base.metadata.create_all(engine)

    session = SessionLocal()
    try:
        elektryka_data = _json.loads(resource_path("tests/fixtures/baza_elektryka.json").read_text(encoding="utf-8"))
        import_catalog(session, elektryka_data, dzial="elektryka")

        hydraulika_data = _json.loads(resource_path("tests/fixtures/baza_hydraulika.json").read_text(encoding="utf-8"))
        import_catalog(session, hydraulika_data, dzial="hydraulika")

        import_special_rules(session, DEFAULT_SPECIAL_RULES)

        create_user(session, email=config["admin_email"], password=config["admin_password"], rola="admin")
    finally:
        session.close()


class SPAStaticFiles:
    """Serwuje zbudowany frontend (Vite `dist/`) z fallbackiem na index.html dla tras React
    Router (np. /documents/abc-123) - dokladnie ta sama zasada co `try_files $uri $uri/
    /index.html` w nginx.conf (Etap 10), tylko zaimplementowana w Pythonie, bo w wersji Portable
    nie ma osobnego Nginx."""

    def __new__(cls, directory: Path):
        from starlette.exceptions import HTTPException
        from starlette.staticfiles import StaticFiles

        class _Impl(StaticFiles):
            async def get_response(self, path, scope):
                try:
                    return await super().get_response(path, scope)
                except HTTPException as exc:
                    if exc.status_code != 404:
                        raise
                    return await super().get_response("index.html", scope)

        return _Impl(directory=str(directory), html=True)


def build_app():
    """Sklada finalna aplikacje: `/api/*` -> caly istniejacy backend (app.main.app, bez zmian),
    `/*` -> zbudowany frontend. Ten sam podzial co Nginx w wersji produkcyjnej Docker
    (frontend/nginx.conf) - tylko w jednym procesie zamiast dwoch kontenerow."""
    from fastapi import FastAPI

    from app.main import app as api_app

    desktop_app = FastAPI(title="Multiplekser Portable")
    desktop_app.mount("/api", api_app)
    desktop_app.mount("/", SPAStaticFiles(resource_path("frontend_dist")), name="frontend")
    return desktop_app


def main() -> None:
    dir_ = data_dir()
    config = load_config(dir_)
    is_first_run = config is None

    if is_first_run:
        config = collect_first_run_config_via_dialog()
        if config is None:
            return  # uzytkownik anulowal okno startowe
        save_config(dir_, config)

    apply_env(config, dir_)

    if is_first_run:
        bootstrap_first_run(config)

    app = build_app()

    def _open_browser() -> None:
        time.sleep(1.5)
        webbrowser.open(f"http://127.0.0.1:{APP_PORT}")

    threading.Thread(target=_open_browser, daemon=True).start()

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=APP_PORT, log_level="warning")


if __name__ == "__main__":
    main()
