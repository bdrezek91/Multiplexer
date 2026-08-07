"""Testy integracyjne Etapu 5: logowanie, refresh, RBAC (rola admin, magazyny_dostepne)."""
from scripts.import_catalog import import_catalog
from scripts.import_special_rules import import_special_rules
from app.modules.matcher.special_rules import DEFAULT_SPECIAL_RULES
from tests.conftest import ADMIN_PASSWORD, MAGAZYNIER_PASSWORD


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


def test_login_blokada_konta_po_serii_bledow(client, admin_user):
    """Blokada per-konto (lockout.py) - niezalezna od rate limitera per-IP (@limiter.limit
    powyzej, 5/minute): resetujemy limiter po kazdej probie, zeby izolowac akurat blokade konta,
    nie ograniczenie IP z ktorego przychodzi caly test."""
    from app.core.rate_limit import limiter

    for _ in range(5):
        r = client.post("/auth/token", data={"username": admin_user.email, "password": "zle-haslo"})
        assert r.status_code == 401
        limiter.reset()

    # Nawet z POPRAWNYM haslem, konto jest zablokowane - limiter per-IP juz zresetowany wyzej,
    # wiec to musi byc blokada per-konto (lockout.py), nie efekt uboczny rate limitera.
    r = client.post("/auth/token", data={"username": admin_user.email, "password": ADMIN_PASSWORD})
    assert r.status_code == 429
    assert "zablokowane" in r.json()["detail"].lower()


def test_login_sukces_zeruje_licznik_nieudanych_prob(client, admin_user):
    from app.core.rate_limit import limiter

    for _ in range(4):
        r = client.post("/auth/token", data={"username": admin_user.email, "password": "zle-haslo"})
        assert r.status_code == 401
        limiter.reset()

    r = client.post("/auth/token", data={"username": admin_user.email, "password": ADMIN_PASSWORD})
    limiter.reset()
    assert r.status_code == 200

    # Po udanym logowaniu licznik jest wyzerowany - kolejna nieudana proba nie blokuje od razu.
    r = client.post("/auth/token", data={"username": admin_user.email, "password": "zle-haslo"})
    assert r.status_code == 401


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


def test_logout_uniewaznia_refresh_token(client, admin_user):
    login = client.post("/auth/token", data={"username": admin_user.email, "password": ADMIN_PASSWORD})
    refresh_token = login.json()["refresh_token"]

    r_logout = client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert r_logout.status_code == 204

    r_refresh = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r_refresh.status_code == 401
    assert "unieważniony" in r_refresh.json()["detail"]


def test_logout_z_nieprawidlowym_tokenem_jest_idempotentny(client):
    """Wylogowanie ma byc bezpieczne do wywolania nawet z juz nieprawidlowym/sfabrykowanym
    tokenem (patrz docstring endpointu) - frontend zawsze kasuje tokeny lokalnie niezaleznie."""
    r = client.post("/auth/logout", json={"refresh_token": "cos-nieprawidlowego"})
    assert r.status_code == 204


def test_logout_nie_uniewaznia_innych_tokenow_tego_uzytkownika(client, admin_user):
    """Kazdy refresh token ma wlasne 'jti' - wylogowanie jedna sesja nie psuje innej (np. drugie
    urzadzenie), inaczej niz globalna zmiana hasla."""
    login_1 = client.post("/auth/token", data={"username": admin_user.email, "password": ADMIN_PASSWORD})
    login_2 = client.post("/auth/token", data={"username": admin_user.email, "password": ADMIN_PASSWORD})
    refresh_token_1 = login_1.json()["refresh_token"]
    refresh_token_2 = login_2.json()["refresh_token"]

    client.post("/auth/logout", json={"refresh_token": refresh_token_1})

    assert client.post("/auth/refresh", json={"refresh_token": refresh_token_1}).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": refresh_token_2}).status_code == 200


def test_zapis_produktow_wymaga_roli_admin(client, magazynier_headers):
    r = client.post("/products", json={"kod": "RBAC TEST", "nazwa": "X"}, headers=magazynier_headers)
    assert r.status_code == 403


def test_zapis_produktow_dziala_dla_admina(client, admin_headers):
    r = client.post("/products", json={"kod": "RBAC TEST ADMIN", "nazwa": "X"}, headers=admin_headers)
    assert r.status_code == 201


def test_odczyt_produktow_dziala_dla_kazdej_roli(client, magazynier_headers):
    r = client.get("/products", headers=magazynier_headers)
    assert r.status_code == 200


def test_match_bez_tokenu_zwraca_401(client):
    r = client.post("/match", json={"query": "cokolwiek"})
    assert r.status_code == 401


def test_magazynier_ma_dostep_do_kazdego_magazynu(client, magazynier_headers, db_session, baza_elektryka_json):
    """magazynier_user ma magazyny_dostepne=['Zabrze'] (patrz conftest.py), ale ograniczenie RBAC
    do przypisanych magazynow zostalo usuniete (2026-08-04, na zyczenie uzytkownika) - magazynier
    ma teraz pelny dostep do kazdego magazynu, tak jak admin."""
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    r_ok = client.post(
        "/match", json={"query": "Bezpiecznik 25A Niemiecki", "magazyn": "Zabrze"}, headers=magazynier_headers
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["kod"] == "BEZPIECZNIK 25A NIEMIECKI"

    r_also_ok = client.post(
        "/match", json={"query": "Bezpiecznik 25A Niemiecki", "magazyn": "Czekanów"}, headers=magazynier_headers
    )
    assert r_also_ok.status_code == 200


def test_admin_ma_dostep_do_kazdego_magazynu(client, admin_headers, db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    r = client.post(
        "/match", json={"query": "Bezpiecznik 25A Niemiecki", "magazyn": "Czekanów"}, headers=admin_headers
    )
    assert r.status_code == 200
    assert r.json()["kod"] == "BEZPIECZNIK 25A NIEMIECKI 1P"


def test_match_bez_magazynu_dziala_dla_kazdej_roli(client, magazynier_headers, db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    r = client.post("/match", json={"query": "Grzejnik 1800W"}, headers=magazynier_headers)
    assert r.status_code == 200
    assert r.json()["kod"] == "GRZEJNIK 2000W"
