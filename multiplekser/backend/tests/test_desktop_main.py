"""Testy czesci logiki `desktop_main.py` (Multiplekser Portable, patrz docs/RAPORT_PORTABLE_1.md)
mozliwej do przetestowania bez GUI (tkinter) i bez faktycznego startu serwera - config na dysku,
zmienne srodowiskowe, rozwiazywanie sciezek zasobow. Okno dialogowe pierwszego uruchomienia i
`main()`/`bootstrap_first_run()` (uruchamiaja prawdziwy proces/GUI) sa celowo POZA zakresem tych
testow - weryfikowane manualnie (patrz raport)."""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import desktop_main


def test_load_config_zwraca_none_gdy_plik_nie_istnieje(tmp_path):
    assert desktop_main.load_config(tmp_path) is None


def test_save_i_load_config_round_trip(tmp_path):
    config = desktop_main.build_first_run_config("admin@test.local", "haslo123", "gemini-key-x")

    desktop_main.save_config(tmp_path, config)
    loaded = desktop_main.load_config(tmp_path)

    assert loaded == config


def test_build_first_run_config_generuje_losowy_jwt_secret():
    config1 = desktop_main.build_first_run_config("a@test.local", "haslo", "klucz")
    config2 = desktop_main.build_first_run_config("a@test.local", "haslo", "klucz")

    assert config1["jwt_secret_key"] != config2["jwt_secret_key"]  # kazde wywolanie - nowy sekret
    assert len(config1["jwt_secret_key"]) == 64  # secrets.token_hex(32) -> 64 znaki hex


def test_config_json_jest_czytelnym_jsonem_do_recznej_edycji(tmp_path):
    """Uzytkownik ma miec mozliwosc dopisac GEMINI_API_KEY_PAID recznie w config.json (README) -
    plik musi byc zwyklym, czytelnym JSON-em, nie np. zserializowanym obiektem binarnym."""
    config = desktop_main.build_first_run_config("a@test.local", "haslo", "klucz")
    desktop_main.save_config(tmp_path, config)

    raw = (tmp_path / desktop_main.CONFIG_FILENAME).read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["admin_email"] == "a@test.local"


@pytest.fixture()
def clean_env():
    keys = ["DESKTOP_MODE", "DATABASE_URL", "LOCAL_STORAGE_PATH", "JWT_SECRET_KEY", "GEMINI_API_KEY_FREE"]
    original = {k: os.environ.get(k) for k in keys}
    yield
    for k, v in original.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_apply_env_ustawia_sqlite_i_desktop_mode(tmp_path, clean_env):
    config = desktop_main.build_first_run_config("a@test.local", "haslo", "gemini-xyz")

    desktop_main.apply_env(config, tmp_path)

    assert os.environ["DESKTOP_MODE"] == "true"
    assert os.environ["DATABASE_URL"].startswith("sqlite:///")
    assert os.environ["DATABASE_URL"].endswith(desktop_main.DB_FILENAME)
    assert os.environ["LOCAL_STORAGE_PATH"] == str(tmp_path / "dokumenty")
    assert os.environ["JWT_SECRET_KEY"] == config["jwt_secret_key"]
    assert os.environ["GEMINI_API_KEY_FREE"] == "gemini-xyz"


def test_apply_env_bez_gemini_key_nie_ustawia_zmiennej(tmp_path, clean_env):
    config = desktop_main.build_first_run_config("a@test.local", "haslo", "")
    os.environ.pop("GEMINI_API_KEY_FREE", None)

    desktop_main.apply_env(config, tmp_path)

    assert "GEMINI_API_KEY_FREE" not in os.environ


def test_resource_path_nie_frozen_wzgledem_pliku_desktop_main(tmp_path):
    """Poza trybem `--frozen` (development/testy) zasoby sa wzgledem tego pliku - tak samo jak
    fixture'y testowe uzywane gdzie indziej w tej suicie (Path(__file__).parent)."""
    path = desktop_main.resource_path("tests/fixtures/baza_elektryka.json")

    assert path.is_file()


def test_data_dir_tworzy_folder_jesli_nie_istnieje(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop_main, "__file__", str(tmp_path / "desktop_main.py"))

    d = desktop_main.data_dir()

    assert d == tmp_path / "dane"
    assert d.is_dir()
