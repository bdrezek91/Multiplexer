"""Testy integracyjne Etapu 11: zarzadzanie uzytkownikami w UI (backend, admin-only)."""
from tests.conftest import MAGAZYNIER_PASSWORD


def test_list_users_wymaga_roli_admin(client, magazynier_headers):
    r = client.get("/users", headers=magazynier_headers)
    assert r.status_code == 403


def test_list_users_dziala_dla_admina(client, admin_headers, admin_user, magazynier_user):
    r = client.get("/users", headers=admin_headers)
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()}
    assert {admin_user.email, magazynier_user.email} <= emails


def test_create_user_wymaga_roli_admin(client, magazynier_headers):
    r = client.post(
        "/users", json={"email": "nowy@test.local", "password": "haslo1234"}, headers=magazynier_headers
    )
    assert r.status_code == 403


def test_create_user_sukces(client, admin_headers):
    r = client.post(
        "/users",
        json={
            "email": "nowy@test.local", "password": "haslo1234",
            "rola": "magazynier", "magazyny_dostepne": ["Zabrze"],
        },
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "nowy@test.local"
    assert body["rola"] == "magazynier"
    assert body["magazyny_dostepne"] == ["Zabrze"]
    assert body["active"] is True
    assert "password" not in body and "hashed_password" not in body


def test_create_user_duplikat_email_zwraca_409(client, admin_headers, admin_user):
    r = client.post("/users", json={"email": admin_user.email, "password": "haslo1234"}, headers=admin_headers)
    assert r.status_code == 409


def test_create_user_nieprawidlowa_rola_zwraca_400(client, admin_headers):
    r = client.post(
        "/users", json={"email": "zla-rola@test.local", "password": "haslo1234", "rola": "superadmin"},
        headers=admin_headers,
    )
    assert r.status_code == 400


def test_create_user_za_krotkie_haslo_zwraca_422(client, admin_headers):
    r = client.post("/users", json={"email": "krotkie@test.local", "password": "abc"}, headers=admin_headers)
    assert r.status_code == 422


def test_update_user_sukces(client, admin_headers, magazynier_user):
    r = client.put(
        f"/users/{magazynier_user.id}",
        json={
            "email": magazynier_user.email, "rola": "magazynier",
            "magazyny_dostepne": ["Zabrze", "Czekanów"], "active": True,
        },
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["magazyny_dostepne"] == ["Zabrze", "Czekanów"]


def test_update_user_dezaktywacja(client, admin_headers, magazynier_user):
    r = client.put(
        f"/users/{magazynier_user.id}",
        json={"email": magazynier_user.email, "rola": "magazynier", "magazyny_dostepne": [], "active": False},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["active"] is False


def test_update_user_nieistniejacy_zwraca_404(client, admin_headers):
    r = client.put(
        "/users/00000000-0000-0000-0000-000000000000",
        json={"email": "x@test.local", "rola": "magazynier", "magazyny_dostepne": [], "active": True},
        headers=admin_headers,
    )
    assert r.status_code == 404


def test_update_user_email_zajety_przez_innego_zwraca_409(client, admin_headers, admin_user, magazynier_user):
    r = client.put(
        f"/users/{magazynier_user.id}",
        json={"email": admin_user.email, "rola": "magazynier", "magazyny_dostepne": [], "active": True},
        headers=admin_headers,
    )
    assert r.status_code == 409


def test_update_user_wymaga_roli_admin(client, magazynier_headers, magazynier_user):
    r = client.put(
        f"/users/{magazynier_user.id}",
        json={"email": magazynier_user.email, "rola": "magazynier", "magazyny_dostepne": [], "active": True},
        headers=magazynier_headers,
    )
    assert r.status_code == 403


def test_admin_nie_moze_zdezaktywowac_samego_siebie(client, admin_headers, admin_user):
    r = client.put(
        f"/users/{admin_user.id}",
        json={"email": admin_user.email, "rola": "admin", "magazyny_dostepne": [], "active": False},
        headers=admin_headers,
    )
    assert r.status_code == 400


def test_admin_nie_moze_zdegradowac_samego_siebie(client, admin_headers, admin_user):
    r = client.put(
        f"/users/{admin_user.id}",
        json={"email": admin_user.email, "rola": "magazynier", "magazyny_dostepne": [], "active": True},
        headers=admin_headers,
    )
    assert r.status_code == 400


def test_admin_moze_edytowac_wlasny_email_bez_zmiany_roli_i_aktywnosci(client, admin_headers, admin_user):
    r = client.put(
        f"/users/{admin_user.id}",
        json={"email": "nowy-admin-email@test.local", "rola": "admin", "magazyny_dostepne": [], "active": True},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["email"] == "nowy-admin-email@test.local"


def test_reset_password_sukces_i_nowe_haslo_dziala(client, admin_headers, magazynier_user):
    r = client.post(
        f"/users/{magazynier_user.id}/reset-password",
        json={"new_password": "nowe-haslo-123"},
        headers=admin_headers,
    )
    assert r.status_code == 200

    login = client.post("/auth/token", data={"username": magazynier_user.email, "password": "nowe-haslo-123"})
    assert login.status_code == 200

    old_login = client.post("/auth/token", data={"username": magazynier_user.email, "password": MAGAZYNIER_PASSWORD})
    assert old_login.status_code == 401


def test_reset_password_wymaga_roli_admin(client, magazynier_headers, magazynier_user):
    r = client.post(
        f"/users/{magazynier_user.id}/reset-password",
        json={"new_password": "nowe-haslo-123"}, headers=magazynier_headers,
    )
    assert r.status_code == 403


def test_reset_password_nieistniejacy_uzytkownik_zwraca_404(client, admin_headers):
    r = client.post(
        "/users/00000000-0000-0000-0000-000000000000/reset-password",
        json={"new_password": "nowe-haslo-123"}, headers=admin_headers,
    )
    assert r.status_code == 404


def test_list_users_bez_tokenu_zwraca_401(client):
    r = client.get("/users")
    assert r.status_code == 401
