"""Testy integracyjne Etapu 5: logowanie, refresh, RBAC (rola admin, magazyny_dostepne)."""
from scripts.import_catalog import import_catalog
from scripts.import_special_rules import import_special_rules
from app.modules.matcher.special_rules import DEFAULT_SPECIAL_RULES
from tests.conftest import ADMIN_PASSWORD, ELEKTRYK_PASSWORD


def test_login_sukces(client, admin_user):
    r = client.post("/auth/token", data={"username": admin_user.email, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]


def test_login_zle_haslo(client, admin_user):
    r = client.post("/auth/token", data={"username": admin_user.email, "password": "zle-haslo"})
    assert r.status_code == 401


def test_login_sukces_loguje_zdarzenie(client, admin_user, caplog):
    """Etap "quick winy" (2026-07-30) - strukturalne logowanie: udane logowanie zostawia slad
    (kto, kiedy) - patrz app/core/logging_config.py."""
    with caplog.at_level("INFO", logger="app.modules.users.router"):
        r = client.post("/auth/token", data={"username": admin_user.email, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    assert any(
        rec.getMessage() == "Logowanie" and getattr(rec, "email", None) == admin_user.email
        for rec in caplog.records
    )


def test_login_zle_haslo_loguje_ostrzezenie(client, admin_user, caplog):
    with caplog.at_level("WARNING", logger="app.modules.users.router"):
        r = client.post("/auth/token", data={"username": admin_user.email, "password": "zle-haslo"})
    assert r.status_code == 401
    assert any(
        rec.levelname == "WARNING" and rec.getMessage() == "Nieudane logowanie"
        for rec in caplog.records
    )


def test_login_nieistniejacy_uzytkownik(client):
    r = client.post("/auth/token", data={"username": "nikt@test.local", "password": "cokolwiek"})
    assert r.status_code == 401


def test_login_rate_limit_po_5_probach(client, admin_user):
    """Etap "quick winy" (2026-07-30) - ochrona przed brute-force: 5 prob/minute na /auth/token,
    niezaleznie od tego czy haslo bylo poprawne czy nie (limit liczy proby, nie tylko porazki)."""
    for _ in range(5):
        r = client.post("/auth/token", data={"username": admin_user.email, "password": "zle-haslo"})
        assert r.status_code == 401

    r = client.post("/auth/token", data={"username": admin_user.email, "password": "zle-haslo"})
    assert r.status_code == 429
    assert r.json() == {"detail": "Zbyt wiele prób logowania - spróbuj ponownie za chwilę"}

    # Nawet z POPRAWNYM haslem - limit blokuje IP/klucz, nie ocenia poprawnosci danych.
    r = client.post("/auth/token", data={"username": admin_user.email, "password": ADMIN_PASSWORD})
    assert r.status_code == 429


def test_me_bez_tokenu_zwraca_401(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_z_tokenem(client, admin_headers, admin_user):
    r = client.get("/auth/me", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == admin_user.email
    assert body["rola"] == "admin"


def test_refresh_wydaje_nowy_access_token(client, admin_user):
    login = client.post("/auth/token", data={"username": admin_user.email, "password": ADMIN_PASSWORD})
    refresh_token = login.json()["refresh_token"]

    r = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_refresh_odrzuca_access_token(client, admin_headers):
    access_token = admin_headers["Authorization"].removeprefix("Bearer ")
    r = client.post("/auth/refresh", json={"refresh_token": access_token})
    assert r.status_code == 401


def test_zapis_produktow_wymaga_roli_admin(client, elektryk_headers):
    r = client.post("/products", json={"kod": "RBAC TEST", "nazwa": "X"}, headers=elektryk_headers)
    assert r.status_code == 403


def test_zapis_produktow_dziala_dla_admina(client, admin_headers):
    r = client.post("/products", json={"kod": "RBAC TEST ADMIN", "nazwa": "X"}, headers=admin_headers)
    assert r.status_code == 201


def test_odczyt_produktow_dziala_dla_kazdej_roli(client, elektryk_headers):
    r = client.get("/products", headers=elektryk_headers)
    assert r.status_code == 200


def test_match_bez_tokenu_zwraca_401(client):
    r = client.post("/match", json={"query": "cokolwiek"})
    assert r.status_code == 401


def test_elektryk_ograniczony_do_przypisanych_magazynow(client, elektryk_headers, db_session, baza_elektryka_json):
    """elektryk_user ma magazyny_dostepne=['Zabrze'] (patrz conftest.py)."""
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    r_ok = client.post(
        "/match", json={"query": "Bezpiecznik 25A Niemiecki", "magazyn": "Zabrze"}, headers=elektryk_headers
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["kod"] == "BEZPIECZNIK 25A NIEMIECKI"

    r_forbidden = client.post(
        "/match", json={"query": "Bezpiecznik 25A Niemiecki", "magazyn": "Czekanów"}, headers=elektryk_headers
    )
    assert r_forbidden.status_code == 403


def test_admin_ma_dostep_do_kazdego_magazynu(client, admin_headers, db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    r = client.post(
        "/match", json={"query": "Bezpiecznik 25A Niemiecki", "magazyn": "Czekanów"}, headers=admin_headers
    )
    assert r.status_code == 200
    assert r.json()["kod"] == "BEZPIECZNIK 25A NIEMIECKI 1P"


def test_match_bez_magazynu_dziala_dla_kazdej_roli(client, elektryk_headers, db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    r = client.post("/match", json={"query": "Grzejnik 1800W"}, headers=elektryk_headers)
    assert r.status_code == 200
    assert r.json()["kod"] == "GRZEJNIK 2000W"
