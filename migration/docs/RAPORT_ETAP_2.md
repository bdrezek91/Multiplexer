# Raport — Etap 2: Model danych (SQLAlchemy + Alembic) + import katalogu do Postgresa

## Co zostało zrobione

1. **Modele SQLAlchemy** (`app/modules/products/models.py`) — `ProductModel`, `ProductAliasModel`,
   `WarehouseVariantModel`, dokładnie wg ERD z `docs/ETAP_0_analiza_architektury.md` (uuid PK,
   `kod` UNIQUE+indeks, `atrybuty` jako `JSONB`, relacje 1:N produkt→aliasy i produkt→warianty
   magazynowe z `cascade="all, delete-orphan"`).
2. **Konfiguracja bazy** — `app/core/config.py` (`Settings.database_url`, czytany z env
   `DATABASE_URL`, domyślnie zgodny z `docker-compose.yml`) i `app/core/db.py` (`engine`,
   `SessionLocal`, `Base`, `get_db()` jako FastAPI dependency).
3. **Alembic** zainicjalizowany w `backend/alembic/` — `env.py` podpięty pod `Base.metadata` i pod
   `settings.database_url` (jeden config zamiast dwóch źródeł prawdy). Migracja startowa
   `fdafa7346dc0` — zweryfikowana end-to-end na realnym lokalnym Postgresie: `upgrade head`,
   `downgrade base`, ponowny `upgrade head`, wszystkie bezbłędnie.
4. **Skrypt importu** (`backend/scripts/import_catalog.py`) — wczytuje
   `tests/fixtures/baza_elektryka.json` (sekcje `generyczne`+`archiwalne`), zapisuje do Postgresa.
   **Idempotentny** — klucz to `kod`; istniejący produkt jest aktualizowany (aliasy i warianty
   magazynowe zastępowane), nowy tworzony. Zweryfikowano: pierwszy import → 671 utworzonych
   (379+292, zgodnie z `meta.liczba_generyczne`/`liczba_archiwalne` w JSON), drugi import tych
   samych danych → 0 utworzonych / 671 zaktualizowanych, bez duplikatów.
5. **`Catalog.from_db(session)`** (`app/modules/products/catalog.py`) — odpowiednik
   `from_json_dict`, buduje te same dataclassy domenowe (`Product`/`Alias`) z wierszy ORM
   (`selectinload` na aliasy i warianty, bez N+1). `main.py` (`/match`) czyta katalog wyłącznie
   z Postgresa — plik JSON pozostaje tylko jako fixture testowe, nie jest już źródłem danych API.
6. **Testy integracyjne** (`backend/tests/test_catalog_db.py`, 5 nowych testów) na **realnej bazie
   testowej** (Postgres, nie SQLite/mock — żeby złapać różnice specyficzne dla dialektu, np. JSONB):
   import tworzy oczekiwaną liczbę produktów, import jest idempotentny, `Catalog.from_db` zwraca
   tylko `generyczne`, aliasy i warianty magazynowe są poprawnie przenoszone, `match_against_catalog`
   daje identyczny wynik niezależnie czy katalog pochodzi z bazy czy z JSON. Fixture `db_session`
   izoluje każdy test przez SAVEPOINT (`join_transaction_mode="create_savepoint"`) i rollback po
   teście, mimo że `import_catalog()` robi `commit()` wewnątrz.
7. **Wszystkie testy przechodzą: 16/16** (11 z Etapu 1 bez zmian + 5 nowych).
8. **Dockerfile** — `CMD` uruchamia teraz `alembic upgrade head` przed `uvicorn`, więc
   `docker compose up` tworzy schemat automatycznie (import katalogu pozostaje osobnym, ręcznym
   krokiem — patrz „Jak uruchomić" niżej).

## Decyzje projektowe wymagające odnotowania

- **Pola spoza ERD** (`kod_producenta`, `zrodlo_stanu`, `stan` z JSON) — ERD z Etapu 0 przewiduje
  dla `PRODUCT` tylko ogólną kolumnę `atrybuty jsonb`, bez osobnych kolumn na te pola. Żeby nic nie
  zgubić (zasada 8 z `CLAUDE.md`), trafiają do `atrybuty["_meta"]`. Nie są używane przez
  Parser/Matcher, więc nie wpływają na logikę dopasowania. Jeśli w kolejnych etapach (np. moduł
  Integracje/stan magazynowy) okażą się potrzebne jako pełnoprawne kolumny/tabela — do
  doprecyzowania wtedy.
- **UUID generowane po stronie Pythona** (`default=uuid.uuid4`), nie przez rozszerzenie Postgresa
  (`gen_random_uuid()`/`uuid-ossp`) — prostsze, bez zależności od rozszerzenia bazy.

## Co zostało świadomie odłożone (i dlaczego)

| Nieprzeniesione jeszcze | Gdzie w monolicie | Plan |
|---|---|---|
| Reguły specyficzne dla kodów (R3 szynoprzewód→zestaw, R6 grzejnik wg mocy, wykluczenie wkręt OSB, R4 16/12 bez HI) jako dane w tabeli `special_rules` | `matchAgainstCatalog()` w `index.html`, komentarze `// R3`/`// R6`/`// R4` | **Etap 3** — świadomie wydzielone z Etapu 2 (potwierdzone z użytkownikiem): to zmiana logiki Matchera, nie tylko modelu danych, więc żeby Etap 2 pozostał mały i w pełni działający, robimy to osobno |
| `snapToFormRow` / `FORM_PHYSICAL_ORDER` / sortowanie wyniku wg fizycznej kolejności | `generateOutput()` | Etap 2/3 → moduł **Generator** (bez zmian względem raportu Etapu 1) |
| OCR (Gemini/NVIDIA, `AI_CHAIN`) | `runAI()` | Etap 4 → moduł **OCR** jako Strategy Pattern |
| Eksport do formatu Optima | `generateOutput()` końcówka | Etap 3 → moduł **Integracje** |
| Użytkownicy/role/magazyny | brak w monolicie | Etap 5 |
| Pełny CRUD produktów przez API | — | Etap 3 |

## Ryzyka

1. **Import katalogu nie jest częścią automatycznego startu kontenera** — celowo, żeby nie
   nadpisywać danych produkcyjnych przy każdym restarcie. `docker compose up` tworzy schemat
   (migracje), ale pusty — import trzeba uruchomić ręcznie raz (`python -m scripts.import_catalog`).
2. **Testy integracyjne wymagają realnej bazy Postgres** (`TEST_DATABASE_URL`, domyślnie
   `multiplekser_test` na `localhost`) — bez niej `pytest` częściowo się wywali (5 testów w
   `test_catalog_db.py`). Do rozważenia w Etapie 3: CI z serwisem Postgres (GitHub Actions
   `services:`), żeby to było odtwarzalne bez ręcznego setupu.
3. **`atrybuty["_meta"]`** to tymczasowe rozwiązanie (patrz „Decyzje projektowe" wyżej) — jeśli stan
   magazynowy (`stan`, `zrodlo_stanu`) stanie się aktywnie używany (np. moduł Integracje), będzie
   wymagał osobnych, indeksowalnych kolumn zamiast zagnieżdżonego JSON.
4. **Katalog nadal ładowany raz do pamięci procesu przy pierwszym request** (`get_catalog()` w
   `main.py`, taki sam wzorzec jak w Etapie 1) — zmiana danych w bazie wymaga restartu API. Do
   rozwiązania w Etapie 3 razem z pełnym CRUD (np. invalidacja cache po zapisie).

## Jak uruchomić

```bash
cd backend
pip install -r requirements.txt

# Baza deweloperska (lokalnie, bez Dockera) - dopasuj DATABASE_URL do wlasnego Postgresa,
# domyslny w app/core/config.py odpowiada docker-compose.yml
alembic upgrade head
python -m scripts.import_catalog

# Testy - potrzebna dodatkowo baza testowa (TEST_DATABASE_URL, domyslnie multiplekser_test)
pytest tests/ -v          # 16 testow, wszystkie zielone

uvicorn app.main:app --reload   # API na http://localhost:8000, dokumentacja na /docs
```

Albo przez Docker (migracje uruchamiają się automatycznie przy starcie kontenera, import ręcznie):
```bash
docker compose up
docker compose exec backend python -m scripts.import_catalog
curl http://localhost:8000/health
```

## Plan Etapu 3

1. Reguły specyficzne (R3/R6/R4/wkręt) jako dane w tabeli `special_rules` + silnik ewaluacji w
   Matcherze zamiast hardkodowanych `if`-ów w `matchAgainstCatalog()` (odłożone z Etapu 2).
2. FastAPI: pełny CRUD produktów (`/products`) + endpoint dopasowania jako pełnoprawny serwis
   (wstrzykiwana sesja DB przez `get_db()`, nie globalny cache w pamięci procesu).
3. Testy integracyjne API (poza smoke testem z Etapu 1).
4. Rozważenie CI z serwisem Postgres dla testów integracyjnych (ryzyko 2 wyżej).
