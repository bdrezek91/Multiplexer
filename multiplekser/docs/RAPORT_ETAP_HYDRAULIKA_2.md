# Raport — Krok Hydraulika-2: routing API wg działu

Zakres wybrany przez użytkownika (`AskUserQuestion`, spośród trzech opcji po
`RAPORT_ETAP_HYDRAULIKA_1.md`): mniejszy krok pośredni — parametr `dzial` na istniejących
endpointach zamiast pełnej ścieżki OCR z automatyczną klasyfikacją (Gemini, krok 6.6-6.7 z
`docs/MIGRATION_PLAN_HYDRAULIKA.md` — wciąż odłożone).

## Co zostało zrobione

### `/products` (CRUD)

- `app/modules/products/router.py`: wszystkie 5 endpointów (`GET` lista, `GET {kod}`, `POST`,
  `PUT {kod}`, `DELETE {kod}`) przyjmują teraz query param `dzial: Literal["elektryka",
  "hydraulika"] = "elektryka"` — FastAPI/Pydantic zwraca **422** dla nieznanej wartości (nie
  zgaduje, nie ignoruje).
- `products/repository.py` już miał parametr `dzial` (dodany w Kroku 1, nieużywany przez
  router) — ten krok tylko go podłącza.
- `ProductOut` (schemas.py) zwraca teraz pole `dzial`, żeby klient API widział przynależność
  produktu bez zgadywania.

### `/match`

- `MatchRequest` (main.py) dostał pole `dzial: Literal["elektryka", "hydraulika"] =
  "elektryka"`.
- Endpoint dispatchuje: `dzial="hydraulika"` → `Catalog.from_db(session, dzial="hydraulika")`
  + `match_against_catalog_hydraulika()` (bez `special_rules` — `DEFAULT_SPECIAL_RULES_HYDRAULIKA`
  jest pusta, patrz Krok 1); w przeciwnym razie ścieżka Elektryki **bez żadnej zmiany**
  (`match_against_catalog` + `rules_from_db`).

### Krok 6.8 — weryfikacja neutralności Generatora (bez zakładania)

Sprawdzone wprost w kodzie (`generator/core.py`, `constants.py`): **Generator NIE jest
neutralny działowo** — `generate_output()` na stałe importuje `match_against_catalog`
(nie `_hydraulika`), `DEFAULT_SPECIAL_RULES`, oraz cały zestaw reguł biznesowych specyficznych
dla elektryki (`ALWAYS_INCLUDE_BASE`, `CABLE_TRAYS_BLACK/WHITE`, `TRAY_BY_SIZE`,
`WKRET_OCYNK_ALWAYS`, regexy `_OSB_RE`/`_LAMPA_SZYNO_RE`/`_SZYNO_MB_RE`/`_KORYT_RE` — koryta
kablowe, szynoprzewody, wkręty OSB, to pojęcia z instalacji elektrycznych, nie hydraulicznych).

**Wniosek**: generowanie receptury dla Hydrauliki wymaga osobnej analizy biznesowej (czy
monolit `Multipekser_Hydraulika.html` w ogóle miał odpowiednik `generateOutput()`, jakie są
jego "always-include" i reguły specjalne, jeśli są) — to **nowa praca analityczna**, nie
routing. Dlatego w tym kroku: `/documents/{id}/generate` **pozostaje nietknięty**
(nadal domyślnie i wyłącznie Elektryka — `documents/router.py`/`tasks.py` wciąż wołają
`Catalog.from_db(session)` bez `dzial`, jak przed tym krokiem). Brak zmiany kodu = brak
ryzyka wygenerowania błędnej receptury dla Hydrauliki, bo ta ścieżka po prostu nie jest jeszcze
osiągalna dla tego działu.

### Testy

`tests/test_products_api.py` (+4), `tests/conftest.py` (+fixture `baza_hydraulika_json`):

- `/match` z `dzial="hydraulika"` trafia we właściwy katalog.
- `/match` **bez** `dzial` (domyślne) NIE widzi produktu istniejącego tylko w Hydraulice —
  potwierdza, że domyślny filtr faktycznie izoluje, nie tylko "wygląda na" izolację.
- Pełny cykl CRUD z tym samym `kod` w obu działach niezależnie (utworzenie, odczyt, lista,
  usunięcie w jednym dziale nie rusza drugiego) — realny test na parze `(kod, dzial)` z
  Kroku 1, tym razem przez HTTP, nie repozytorium bezpośrednio.
- Nieznana wartość `dzial` (np. `"stolarka"`) → 422 na obu endpointach.

**Pełna suita: 199 testów, 1 pominięty, zero regresji** (177 z Kroku 0 → 195 po Kroku 1 → 199
teraz).

## Co zostało świadomie odłożone

| Nieprzeniesione jeszcze | Uwaga | Plan |
|---|---|---|
| Klasyfikacja dokumentu przez Gemini (automatyczny wybór działu) | Poza zakresem wybranym przez użytkownika w tym kroku | Krok 6.6-6.7, jeśli/gdy wybrany |
| `/documents` (upload/OCR/generate) świadome działu | Wymaga 6.6-6.7 (klasyfikacja) ORAZ analizy biznesowej Generatora Hydrauliki (patrz wyżej) | Dwa osobne, niezależne kawałki pracy |
| Frontend: przełącznik działu w UI (katalog, wyszukiwanie dopasowania) | `/products`/`/match` są gotowe do wywołania z `dzial`, ale UI wciąż go nie wysyła (domyślnie `elektryka`, zero regresji) | Krok frontendowy, gdy backend całości (w tym OCR) będzie gotowy |
| Reguły specjalne Hydrauliki w bazie (`special_rule.dzial`) | Wciąż niepotrzebne — `DEFAULT_SPECIAL_RULES_HYDRAULIKA` puste (V1) | Gdy pojawi się pierwszy realny wyjątek |

## Jak zweryfikować

```bash
cd backend
pytest tests/test_products_api.py -v   # w tym 4 nowe testy routingu dzialowego
pytest tests/ -q                       # 199 testow, 1 pominiety
```

Ręcznie (curl, po `docker compose up`):

```bash
curl -X POST localhost:8000/match -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "Zawór kątowy 1/2x3/4", "dzial": "hydraulika"}'
```

## Plan kolejnego kroku

Czekam na sygnał. W kolejce (nieuszeregowane, do wyboru): 6.6-6.7 (OCR + klasyfikacja
działu), analiza biznesowa Generatora dla Hydrauliki (odrębna od OCR), albo frontend
(przełącznik działu w UI, korzystający z już gotowego routingu API z tego kroku).
