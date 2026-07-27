# Raport — Etap 4: Pełny CRUD /products + /match jako serwis z sesją DB per-request

Zakres zgodny z planem z `RAPORT_ETAP_3.md`.

## Co zostało zrobione

1. **Warstwa repozytorium** (`app/modules/products/repository.py`) — `list_products`,
   `get_product`, `create_product`, `update_product`, `delete_product`, operujące bezpośrednio na
   `ProductModel` (ORM), odrębne od `Catalog`/`Product` w `catalog.py` (te służą wyłącznie do
   **czytania** katalogu na potrzeby Matchera, nie do zapisu). Własne wyjątki domenowe
   (`ProductNotFoundError`, `DuplicateKodError`) mapowane w routerze na kody HTTP.
2. **Schematy Pydantic** (`app/modules/products/schemas.py`) — `ProductCreate`/`ProductUpdate`/
   `ProductOut`, aliasy i warianty magazynowe reprezentowane jako `list[str]`/`dict[str,str]`
   (ten sam kształt co katalog domenowy), nie jako osobne zagnieżdżone zasoby REST — prostsze,
   bo w praktyce zawsze edytowane razem z produktem.
3. **Router** (`app/modules/products/router.py`, `APIRouter(prefix="/products")`):
   - `GET /products` — lista z filtrami `status`, `grupa`, `search` (po `nazwa`, `ILIKE`) i
     paginacją (`limit` domyślnie 50, max 200; `offset`),
   - `GET /products/{kod}` — 404 gdy brak,
   - `POST /products` — 201, 409 przy duplikacie `kod` (klucz biznesowy, unikalny w bazie od Etapu 2),
   - `PUT /products/{kod}` — pełna aktualizacja (aliasy i warianty magazynowe zastępowane, nie
     scalane), 404 gdy brak,
   - `DELETE /products/{kod}` — 204, 404 gdy brak. **Hard delete** — usuwanie z bazy, nie soft
     delete. Odpowiednikiem „archiwizacji” jest `PUT` ze `status="archiwalny"` (już istniejące pole
     z ERD Etapu 0, dotychczas używane tylko przy imporcie z JSON).
4. **`/match` jako pełnoprawny serwis** — usunięto globalny cache `_catalog`/`_special_rules` w
   pamięci procesu (z Etapów 2-3). `main.py` buduje `Catalog.from_db(session)` i
   `rules_from_db(session)` **per request**, z sesji wstrzykiwanej przez `Depends(get_db)` — ta
   sama sesja co w CRUD. Efekt: `/match` widzi zmiany zrobione przez CRUD **natychmiast**, bez
   restartu API (zweryfikowane testem `test_match_widzi_produkt_utworzony_przez_crud_bez_restartu`).
5. **9 nowych testów integracyjnych** (`tests/test_products_api.py`) na realnej bazie testowej:
   pełny cykl create→get→update→delete, 409 na duplikacie, 404 na wszystkich operacjach na
   nieistniejącym kodzie, filtrowanie listy (`status`, `grupa`, `search`), `/match` po
   przełączeniu na sesję per-request (w tym wariant magazynowy), oraz test potwierdzający
   natychmiastową widoczność zmian z CRUD w `/match`.
6. **Fixture `client`** (`tests/conftest.py`) — `TestClient` z `app.dependency_overrides[get_db]`
   podmienionym na `db_session` (ta sama izolacja SAVEPOINT+rollback co dotychczasowe testy DB).
7. **Wszystkie testy: 39/39 zielone** (11 z Etapu 1 + 5 z Etapu 2 + 14 z Etapu 3 + 9 nowych).
8. Zweryfikowano end-to-end na realnym lokalnym Postgresie przez `TestClient`: `/health`,
   `/match`, pełny cykl CRUD (create → get → duplicate 409 → update → delete → get 404).

## Decyzje projektowe wymagające odnotowania

- **Hard delete, nie soft delete** — CRUD usuwa rekord fizycznie z bazy (kaskadowo kasuje też
  aliasy i warianty magazynowe, `cascade="all, delete-orphan"` z modelu w Etapie 2). Pole `status`
  (`generyczny`/`archiwalny`) z ERD pozostaje mechanizmem „archiwizacji” — semantycznie różnym od
  usunięcia (archiwalne produkty nadal istnieją w bazie i CRUD, tylko `Catalog.from_db` je pomija
  przy dopasowaniu, zgodnie z zachowaniem z Etapu 1/2).
- **PUT jest pełną zamianą, nie PATCH** — `aliasy`/`warianty_magazynowe` przesłane w żądaniu
  **zastępują** całość (brak scalania częściowego). Prostsze, przewidywalne REST-owo; PATCH
  częściowy nie był potrzebny do niczego w obecnym zakresie.
- **Brak cache po stronie `/match`** — świadomy krok wstecz wydajnościowo (każde zapytanie buduje
  cały katalog ~671 produktów + reguły specjalne od nowa z bazy) w zamian za świeżość danych i
  prostotę (brak logiki invalidacji). Przy 671 produktach to pojedyncze milisekundy (zapytania +
  budowa struktur w pamięci) — nieodczuwalne teraz, ale odnotowane jako przyszłe ryzyko
  wydajnościowe do rozważenia (np. cache z invalidacją po zapisie, albo Redis) gdy katalog
  urośnie znacząco lub ruch będzie wysoki.
- **Aliasy/warianty magazynowe jako pola produktu, nie osobne endpointy REST** — w obecnym
  zakresie nie ma potrzeby zarządzania nimi niezależnie od produktu-rodzica (nie mają własnego
  cyklu życia ani identyfikatora używanego gdziekolwiek indziej).

## Co zostało świadomie odłożone (i dlaczego)

| Nieprzeniesione jeszcze | Uwaga | Plan |
|---|---|---|
| CRUD/API dla `special_rule` | Reguły specjalne nadal edytowalne tylko przez `scripts/import_special_rules.py` (kod → baza) | Do rozważenia gdy pojawi się realna potrzeba edycji przez UI, nie teraz |
| CI z serwisem Postgres dla testów integracyjnych | Odłożone już w Etapie 2/3, nadal aktualne — testy nadal wymagają ręcznie postawionej bazy testowej | Etap 5 lub wcześniej, jeśli zacznie przeszkadzać w pracy |
| Cache/wydajność `/match` przy większym katalogu lub ruchu | Patrz „Decyzje projektowe” wyżej | Gdy pojawi się realny problem wydajnościowy, nie prewencyjnie |
| OCR (Gemini/NVIDIA), moduł Generator, Integracje Optima, Auth | Bez zmian względem wcześniejszych raportów | Kolejne etapy wg planu z Etapu 0 |

## Ryzyka

1. **Brak paginacji domyślnie „bezpiecznej” dla dużych katalogów w przyszłości** — `limit` ma sensowny
   default (50) i twardy sufit (200), więc `GET /products` bez parametrów nie zwróci wszystkich
   671 produktów naraz — to celowe ograniczenie, nie przeoczenie.
2. **`PUT` bez optymistycznej blokady (`ETag`/`version`)** — dwóch równoczesnych edytorów tego
   samego produktu nadpisze się nawzajem bez ostrzeżenia. Nieistotne przy braku wielu użytkowników
   (Etap Auth jeszcze nie istnieje) — do rozważenia przy wprowadzaniu ról/wielu użytkowników.
3. Patrz też ryzyka z Etapu 2/3 dot. braku CI z Postgresem — nadal aktualne, bez zmian.

## Jak uruchomić

```bash
cd backend
pip install -r requirements.txt

alembic upgrade head
python -m scripts.import_catalog
python -m scripts.import_special_rules

pytest tests/ -v          # 39 testow, wszystkie zielone (wymaga TEST_DATABASE_URL, patrz conftest.py)

uvicorn app.main:app --reload   # dokumentacja API: http://localhost:8000/docs
```

Przykłady CRUD:
```bash
curl http://localhost:8000/products?limit=5
curl http://localhost:8000/products/"GRZEJNIK 2000W"
curl -X POST http://localhost:8000/products -H "Content-Type: application/json" \
  -d '{"kod": "NOWY PRODUKT", "nazwa": "Nowy produkt", "grupa": "Testowa"}'
curl -X DELETE http://localhost:8000/products/"NOWY PRODUKT"
```

## Plan Etapu 5

Zgodnie z planem etapów z `docs/ETAP_0_analiza_architektury.md`:
1. Auth (JWT + odświeżanie tokenów) i RBAC.
2. Model użytkowników/magazynów (`USER` z ERD Etapu 0 — obecnie nieprzeniesiony, monolit go nie miał).
3. Ograniczenie dostępu do CRUD/`match`/`magazyn` wg roli i przypisanych magazynów.
4. Do rozważenia przy okazji: CI z serwisem Postgres (odłożone z Etapu 2/3/4).
