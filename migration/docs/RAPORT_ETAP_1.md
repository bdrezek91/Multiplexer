# Raport — Etap 1: Szkielet repo + moduł Matcher/Parser w Pythonie

## Co zostało zrobione

1. **Struktura repo** wg podziału modułowego z Etapu 0: `backend/app/modules/{ocr,parser,matcher,generator,integrations,products,users}` — każdy moduł jako osobny pakiet Python, gotowy na dalszą rozbudowę bez naruszania pozostałych.
2. **Modul Parser** (`modules/parser/core.py`) — pełny port `coreAndAttrs()` z monolitu: wzorce kraju/koloru/krotności/prądu/wymiaru/przekroju/średnicy/biegunowości/modułów/montażu, `diceCoeff`, `bigrams`, `stripDiacritics`.
3. **Modul Produkty** (`modules/products/catalog.py`) — model domenowy `Product`/`Alias`/`Catalog`, budowa `first_word_group` (blokada grupy) dynamicznie z katalogu, wczytywanie z JSON (tymczasowo — Etap 2 podmieni na SQLAlchemy).
4. **Modul Matcher** (`modules/matcher/core.py`) — pełny port `matchAgainstCatalog()`: dopasowanie po aliasach z preferencją specyficzności, blokada grupy, wszystkie konflikty atrybutów, hierarchia tie-break (conflicts→missing→ratio), uogólniona reguła dominującego kraju.
5. **11 testów regresyjnych** (`tests/test_matcher.py`) — każdy odtwarza **realny błąd znaleziony i naprawiony w tej sesji** (nie testy syntetyczne) + smoke test na pełnych 153 wierszach formularza. **11/11 przechodzi.**
6. **Docker Compose** (Postgres + Redis + backend) + `Dockerfile` + minimalne FastAPI z endpointem `/match` — zweryfikowane end-to-end (TestClient, status 200, poprawny wynik dopasowania).

## Co zostało świadomie odłożone (i dlaczego)

Zgodnie z zasadą „nie usuwaj funkcji bez uzasadnienia" — nic nie zostało usunięte, ale część logiki **jeszcze nie przeniesiona**, żeby Etap 1 pozostał mały i w pełni działający:

| Nieprzeniesione jeszcze | Gdzie w monolicie | Plan |
|---|---|---|
| Reguły specyficzne dla konkretnych kodów (R3 szynoprzewód→zestaw, R6 grzejnik wg mocy, wkręt ocynk, wkręt OSB) | `matchAgainstCatalog()`, sekcje z komentarzami `// R3` itd. | Etap 2: wydzielone jako dane konfiguracyjne (`special_rules` w bazie), nie kod |
| `snapToFormRow` / `FORM_PHYSICAL_ORDER` / sortowanie wyniku wg fizycznej kolejności | `generateOutput()` | Etap 2 → moduł **Generator** |
| OCR (Gemini/NVIDIA, `AI_CHAIN`) | `runAI()` | Etap 4 → moduł **OCR** jako Strategy Pattern (patrz diagram klas w Etapie 0) |
| Eksport do formatu Optima, warianty magazynowe | `generateOutput()` końcówka | Etap 2 → moduł **Integracje** |
| Użytkownicy/role/magazyny | brak w monolicie | Etap 5 |

## Ryzyka

1. **Katalog wciąż w JSON, nie w bazie** — celowe dla Etapu 1 (żeby nie łączyć dwóch dużych zmian naraz). Endpoint `/match` czyta plik przy starcie i trzyma w pamięci procesu — do podmiany w Etapie 2.
2. **Reguły specyficzne dla kodów nieprzeniesione** — jeśli ktoś użyje API `/match` już teraz na produkcji, straci np. automatyczne rozpoznanie grzejnika wg mocy. Endpoint na razie **wyłącznie do celów deweloperskich/testowych**, nie do produkcyjnego użycia przed Etapem 2.
3. **Brak testów samego FastAPI (poza smoke testem)** — do uzupełnienia w Etapie 3 razem z pełnym CRUD.

## Jak uruchomić

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v          # 11 testów, wszystkie zielone
uvicorn app.main:app --reload   # API na http://localhost:8000, dokumentacja na /docs
```

Albo przez Docker:
```bash
docker compose up
curl http://localhost:8000/health
```

## Plan Etapu 2

1. Model SQLAlchemy (`Product`, `Alias`, `WarehouseVariant`) wg ERD z Etapu 0.
2. Migracja Alembic + skrypt importu `baza_elektryka.json` → PostgreSQL.
3. Podmiana `Catalog.from_json_dict()` na `Catalog.from_db(session)`.
4. Przeniesienie reguł specyficznych (R3/R6/wkręt) jako dane w tabeli `special_rules`, nie kod.
5. Rozszerzenie testów o warstwę repozytorium (testy integracyjne z bazą testową).
