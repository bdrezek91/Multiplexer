"""Testy integracyjne Etapu 4: CRUD /products i /match jako serwis z sesja DB per-request.

Od Etapu 5 wszystkie endpointy wymagaja autoryzacji (patrz test_auth.py dla testow samego RBAC:
401/403, ograniczenie magazynu) - tutaj uzywamy admin_headers, bo CRUD zapisu i tak wymaga roli admin.
"""
from scripts.import_catalog import import_catalog
from scripts.import_special_rules import import_special_rules
from app.modules.matcher.special_rules import DEFAULT_SPECIAL_RULES


def test_list_products_na_pustej_bazie(client, admin_headers):
    r = client.get("/products", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_create_get_update_delete_cycle(client, admin_headers):
    payload = {
        "kod": "TEST KOD API",
        "nazwa": "Testowy produkt API",
        "jm": "SZT",
        "grupa": "Testowa grupa",
        "aliasy": ["testowy alias api"],
        "warianty_magazynowe": {"Zabrze": "TEST KOD API ZABRZE"},
    }
    r = client.post("/products", json=payload, headers=admin_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["kod"] == "TEST KOD API"
    assert body["aliasy"] == ["testowy alias api"]
    assert body["warianty_magazynowe"] == {"Zabrze": "TEST KOD API ZABRZE"}

    r = client.get("/products/TEST KOD API", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["nazwa"] == "Testowy produkt API"

    r = client.put(
        "/products/TEST KOD API", json={**payload, "nazwa": "Zmieniona nazwa", "aliasy": []}, headers=admin_headers
    )
    assert r.status_code == 200
    assert r.json()["nazwa"] == "Zmieniona nazwa"
    assert r.json()["aliasy"] == []

    r = client.delete("/products/TEST KOD API", headers=admin_headers)
    assert r.status_code == 204

    r = client.get("/products/TEST KOD API", headers=admin_headers)
    assert r.status_code == 404


def test_create_z_duplikatem_kodu_zwraca_409(client, admin_headers):
    payload = {"kod": "DUPLIKAT TEST", "nazwa": "Pierwszy"}
    assert client.post("/products", json=payload, headers=admin_headers).status_code == 201
    r = client.post("/products", json={**payload, "nazwa": "Drugi"}, headers=admin_headers)
    assert r.status_code == 409


def test_get_nieistniejacego_produktu_zwraca_404(client, admin_headers):
    r = client.get("/products/NIE MA TAKIEGO KODU", headers=admin_headers)
    assert r.status_code == 404


def test_update_nieistniejacego_produktu_zwraca_404(client, admin_headers):
    r = client.put("/products/NIE MA TAKIEGO KODU", json={"nazwa": "X"}, headers=admin_headers)
    assert r.status_code == 404


def test_delete_nieistniejacego_produktu_zwraca_404(client, admin_headers):
    r = client.delete("/products/NIE MA TAKIEGO KODU", headers=admin_headers)
    assert r.status_code == 404


def test_list_products_filtruje_po_statusie_i_grupie(client, admin_headers):
    client.post("/products", json={"kod": "FILTR GEN", "nazwa": "A", "grupa": "Grupa X", "status": "generyczny"}, headers=admin_headers)
    client.post("/products", json={"kod": "FILTR ARCH", "nazwa": "B", "grupa": "Grupa X", "status": "archiwalny"}, headers=admin_headers)
    client.post("/products", json={"kod": "FILTR INNA GRUPA", "nazwa": "C", "grupa": "Grupa Y", "status": "generyczny"}, headers=admin_headers)

    r = client.get("/products", params={"status": "archiwalny"}, headers=admin_headers)
    kody = {p["kod"] for p in r.json()}
    assert kody == {"FILTR ARCH"}

    r = client.get("/products", params={"grupa": "Grupa X"}, headers=admin_headers)
    kody = {p["kod"] for p in r.json()}
    assert kody == {"FILTR GEN", "FILTR ARCH"}

    r = client.get("/products", params={"search": "inna"}, headers=admin_headers)
    kody = {p["kod"] for p in r.json()}
    assert kody == set()  # search dziala na "nazwa", nie na "grupa"


def test_match_endpoint_dziala_z_sesja_per_request(client, admin_headers, db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    r = client.post("/match", json={"query": "Grzejnik 1800W"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["kod"] == "GRZEJNIK 2000W"

    r = client.post("/match", json={"query": "Bezpiecznik 25A Niemiecki", "magazyn": "Czekanów"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["kod"] == "BEZPIECZNIK 25A NIEMIECKI 1P"


def test_match_widzi_produkt_utworzony_przez_crud_bez_restartu(client, admin_headers):
    """Roznica wzgledem Etapu 2/3 (globalny cache): /match po CRUD widzi zmiany natychmiast,
    bo katalog jest budowany per-request z tej samej sesji DB, nie cache'owany w pamieci procesu."""
    client.post("/products", json={
        "kod": "SWIEZY PRODUKT",
        "nazwa": "Swiezy produkt bez restartu",
        "aliasy": ["swiezy produkt bez restartu"],
    }, headers=admin_headers)

    r = client.post("/match", json={"query": "Swiezy produkt bez restartu"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["kod"] == "SWIEZY PRODUKT"
