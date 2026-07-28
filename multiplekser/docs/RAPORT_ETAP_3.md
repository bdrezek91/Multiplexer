# Raport — Etap 3: Reguły specjalne jako dane (special_rules) + R5 warianty magazynowe

Zakres uzgodniony z użytkownikiem: **tylko logika Matchera** (bez CRUD/testów API — odłożone do
Etapu 4, żeby zachować filozofię małych, w pełni działających kroków z Etapu 1).

## Co odkryto przed implementacją (research, nie zgadywanie)

Dokładne porównanie `matchAgainstCatalog()` z monolitu (`index.html`) z portem z Etapu 1 ujawniło
więcej luk niż wskazywał `RAPORT_ETAP_1.md`/`RAPORT_ETAP_2.md`:

1. **Błąd z Etapu 2**: `import_catalog.py` gubił pola `regula_dopasowania`, `regula_domyslna`,
   `uwaga`, `przelicznik`, `przelicznik_opak`, `regula_przelicznika`,
   `wariant_wg_dominujacego_standardu` z JSON — nie trafiały nawet do `atrybuty._meta`.
2. Wykluczenie „Lampa LED na szynoprzewód” (już wliczona w zestaw) — całkowicie nieprzeniesione.
3. `OCR_TOLERANT_OVERRIDES` (3 ręczne wyjątki: wkręt ocynk, MBN316E, peszel) — nieprzeniesione.
4. **R5 (warianty magazynowe)** — `match_against_catalog()` nie miał nawet parametru `magazyn`;
   dane `warianty_magazynowe` zaimportowane do bazy w Etapie 2 nigdzie nie były używane.
5. Stary, wąski R1b („gniazdo z klapką grafit”, zakodowany na sztywno w JS) — wymagał weryfikacji,
   czy generalna reguła dominującego kraju z Etapu 1 już go pokrywa.

## Co zostało zrobione

1. **Naprawa importu** (`scripts/import_catalog.py`) — wszystkie pola spoza ERD trafiają teraz do
   `atrybuty._meta`, nic nie jest już cicho gubione.
2. **Model `special_rule`** (`app/modules/matcher/models.py` + migracja `e14bd64f173f`) — jeden,
   generyczny, typowany schemat (`rule_type`, `pattern`, `target_kod`, `kod_template`,
   `value_regex`, `rounding_steps`, `default_value`, `normalize`, `priority`, `active`,
   `description`) obsługujący 3 kategorie z monolitu bez osobnych tabel na każdą:
   - `exclude` — zapytanie dopasowane do wzorca nigdy nie ma kodu,
   - `override` — zapytanie zwraca wprost `target_kod` (z pominięciem ogólnego dopasowania),
   - `power_rounding` — wartość liczbowa z zapytania zaokrąglana do najbliższego z `rounding_steps`,
     wstawiana w `kod_template` (jedyna reguła sparametryzowana, nie tylko regex→kod).
3. **`DEFAULT_SPECIAL_RULES`** (`app/modules/matcher/special_rules.py`) — 9 reguł, port 1:1:
   lampa-na-szynoprzewód (exclude), wkręt OSB (exclude), końcówka 16/12 (exclude, przeniesiona
   z hardkodowanego Pythona z Etapu 1), R3 szynoprzewód czarny/biały → zestaw (2 wiersze zamiast
   1 regexu z alternatywą — ten sam efekt, prostszy silnik), R6 grzejnik wg mocy
   (`power_rounding`), 3× OCR override (wkręt ocynk, MBN316E, peszel). Kod jest źródłem prawdy
   (jak `OCR_TOLERANT_OVERRIDES` w JS), tabela w bazie to warstwa runtime (edycja bez deployu) —
   analogicznie jak katalog ma JSON jako fixture i Postgres jako runtime.
4. **Silnik `evaluate_special_rules()`** — iteruje aktywne reguły wg `priority` (kolejność 1:1 z
   `if`-chainem w JS), zwraca pierwszy trafiony wynik. Zaokrąglanie mocy grzejnika ma dokładnie ten
   sam tie-break co JS: porównanie ścisłe `<`, remis wygrywa pierwszy (mniejszy) krok z listy —
   zweryfikowane testem (`750W` → `500W`, nie `1000W`).
5. **R5 (`apply_warehouse_variant`, `resolve_by_kod`, `_magazyn_key`)** w `matcher/core.py` —
   `match_against_catalog()` ma teraz parametr `magazyn`, stosowany w **obu** miejscach zwrotu
   wyniku z ogólnej ścieżki dopasowania (trafienie aliasowe i pełne dopasowanie po atrybutach),
   dokładnie jak `applyWarehouseVariant()` w JS.
6. **Refaktor bez zmiany zachowania**: `MatchResult` wydzielony do `matcher/result.py` (żeby
   uniknąć cyklu importów `core.py` ↔ `special_rules.py`), `matcher/__init__.py` eksportuje pełne
   nowe API.
7. **Skrypt importu reguł** (`scripts/import_special_rules.py`) — idempotentny (klucz naturalny:
   `rule_type`+`pattern`), zweryfikowany: pierwszy import → 9 utworzonych, drugi → 9
   zaktualizowanych/0 nowych.
8. **`main.py`** — `/match` przyjmuje teraz `magazyn`, czyta reguły specjalne z bazy
   (`get_special_rules()`, cache w pamięci procesu jak katalog), zweryfikowane end-to-end przez
   `TestClient` na realnym Postgresie (grzejnik, szynoprzewód, wykluczenie lampy, peszel, wariant
   magazynowy Czekanów, dominujący kraj DE dla gniazda grafit).
9. **14 nowych testów**: `test_special_rules.py` (11, na katalogu z JSON — szybkie, bez zależności
   od bazy) + `test_special_rules_db.py` (3, integracyjne na realnej bazie testowej, w tym test
   potwierdzający że `rules_from_db()` daje identyczny wynik jak `DEFAULT_SPECIAL_RULES`).
   **Wszystkie testy: 30/30 zielone** (11 z Etapu 1 + 5 z Etapu 2 + 14 nowych).
10. Smoke test na pełnych ~153 wierszach formularza (`test_full_form_rows_regression`) osiąga
    teraz **dokładnie 146 ok / 6 excluded / 1 bad** — pełna zgodność z wynikiem udokumentowanym w
    komentarzu testu jako stan monolitu JS (przed Etapem 3 część z tych 146 pozycji — grzejnik,
    szynoprzewód, wkręt ocynk — nie trafiała jeszcze poprawnie).

## Decyzje projektowe wymagające odnotowania

- **R3 rozbite na 2 wiersze zamiast 1 regexu z alternatywą** — ten sam wyzwalacz i wynik dla
  każdego koloru osobno, ale prostszy, bardziej generyczny silnik ewaluacji (nie trzeba mapować
  przechwyconej grupy regexu na kod — każdy wiersz to wprost `wzorzec → kod`).
- **Stary R1b (gniazdo z klapką grafit) NIE został przeniesiony do `special_rules`** — test
  `test_stary_r1b_gniazdo_grafit_pokryty_regula_ogolna` potwierdza, że generalna reguła
  dominującego kraju z Etapu 1 daje **dokładnie ten sam wynik** (PL przy remisie/braku danych, DE
  gdy `dominant_country="DE"`). Dodanie osobnej reguły byłoby duplikacją martwego kodu.
- **`mbn316e` → `WYŁĄCZNIK NADPRĄDOWY 3P 16A`** — kod istnieje w fixture i ma też pełny alias
  („Wyłącznik nadprądowy MBN316E polska 3P 16A”), więc override nie jest w pełni redundantny:
  obsługuje przypadek, gdy OCR odczytał **tylko** fragment „mbn316e”, za mało tokenów żeby
  dopasować się przez mechanizm aliasów (wymaga wszystkich tokenów aliasu w zapytaniu).
- **Reguły specjalne cache'owane w pamięci procesu API** (jak katalog) — zmiana w bazie wymaga
  restartu `/match`, tak samo jak ryzyko 4 z `RAPORT_ETAP_2.md`. Do rozwiązania razem w Etapie 4.

## Co zostało świadomie odłożone (i dlaczego)

| Nieprzeniesione jeszcze | Gdzie w monolicie | Plan |
|---|---|---|
| Pełny CRUD produktów (`/products`) + endpoint dopasowania jako pełnoprawny serwis (DB session przez `get_db()`, nie globalny cache) | — | **Etap 4** (świadomie wydzielone z Etapu 3, potwierdzone z użytkownikiem) |
| Testy integracyjne API (poza smoke testem) | — | Etap 4 |
| `snapToFormRow` / `FORM_PHYSICAL_ORDER` / sortowanie wg fizycznej kolejności | `generateOutput()` | moduł **Generator** (bez zmian względem wcześniejszych raportów) |
| `regula_przelicznika`/`przelicznik`/`przelicznik_opak` (przeliczniki ILOŚCI, nie dopasowania — R3 metry→zestaw, R4 wkręt opak) | `generateOutput()` | moduł **Generator**, dane już zachowane w `atrybuty._meta` od tego etapu |
| OCR (Gemini/NVIDIA) | `runAI()` | Etap OCR (Strategy Pattern) |
| Eksport do formatu Optima | `generateOutput()` końcówka | moduł **Integracje** |
| Użytkownicy/role/magazyny | brak w monolicie | Etap Auth |

## Ryzyka

1. **Import reguł specjalnych nie jest częścią automatycznego startu kontenera** (jak katalog w
   Etapie 2) — trzeba uruchomić ręcznie `python -m scripts.import_special_rules` po migracjach.
   Pusta tabela `special_rule` = `/match` działa BEZ żadnych reguł specjalnych (nie ma fallbacku na
   `DEFAULT_SPECIAL_RULES` w `main.py` — świadomie, żeby baza była jedynym źródłem prawdy w
   runtime, a nie cichy fallback na kod).
2. **Reguły specjalne w pamięci procesu** — patrz „Decyzje projektowe” wyżej, to samo ryzyko co
   katalog w Etapie 2.
3. **`regula_dopasowania`/`przelicznik`/itd. w `atrybuty._meta` to tekst opisowy, nie ustrukturyzowane
   dane** — Etap 3 naprawił utratę tych danych, ale nie zamienił ich w wykonywalną logikę (poza
   R3/R6, które zostały ręcznie przepisane jako `special_rules` na podstawie tego tekstu +
   analizy JS). Przeliczniki ilości (Generator) będą wymagały podobnej pracy przy przenoszeniu
   `generateOutput()`.

## Jak uruchomić

```bash
cd backend
pip install -r requirements.txt

alembic upgrade head
python -m scripts.import_catalog
python -m scripts.import_special_rules

pytest tests/ -v          # 30 testow, wszystkie zielone (wymaga TEST_DATABASE_URL, patrz conftest.py)

uvicorn app.main:app --reload
```

Przykład z wariantem magazynowym i regułą specjalną:
```bash
curl -X POST http://localhost:8000/match -H "Content-Type: application/json" \
  -d '{"query": "Grzejnik 1800W"}'
curl -X POST http://localhost:8000/match -H "Content-Type: application/json" \
  -d '{"query": "Bezpiecznik 25A Niemiecki", "magazyn": "Czekanów"}'
```

## Plan Etapu 4

1. Pełny CRUD `/products` (Create/Read/Update/Delete) z sesją DB przez `get_db()` zamiast
   globalnego cache w pamięci procesu — w tym invalidacja/odświeżanie katalogu i reguł po zapisie.
2. `/match` jako pełnoprawny serwis wstrzykujący sesję DB per-request.
3. Testy integracyjne API (`TestClient` + baza testowa) poza dotychczasowym smoke testem.
4. Rozważenie CI z serwisem Postgres dla testów integracyjnych (ryzyko odłożone z Etapu 2/3).
