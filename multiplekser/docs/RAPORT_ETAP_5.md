# Raport — Etap 5: Auth (JWT + RBAC) + model użytkowników/magazynów

Zakres uzgodniony z użytkownikiem przed startem (3 pytania, wszystkie odpowiedzi "Recommended"):
role `admin`+`elektryk` na teraz, wszystko za JWT z zapisem katalogu tylko dla `admin` i
ograniczeniem `magazyn` w `/match` do `magazyny_dostepne`, bootstrapping przez
`scripts/create_admin.py`.

## Problem napotkany przed implementacją: niekompatybilne zależności z Etapu 1

`requirements.txt` od Etapu 1 zawierał `python-jose[cryptography]` i `passlib[bcrypt]`, ale nigdy
nie były faktycznie zaimportowane (Auth nie istniał). Przy pierwszym użyciu w tym środowisku:

1. `python-jose` psuł się przy imporcie (`cryptography`'s Rust bindings panikowały) - przyczyna:
   brak `cffi` w środowisku. **Naprawa**: dopisano `cffi==1.17.1` do `requirements.txt`.
2. `passlib` 1.7.4 (nierozwijany od 2020) wykrywa wersję `bcrypt` przez atrybut usunięty w
   `bcrypt>=4.1`, co realnie psuje hashowanie haseł (nie tylko ostrzeżenie). **Naprawa**: przypięto
   `bcrypt==4.0.1` (znany, udokumentowany workaround dla tej pary bibliotek).

Obie poprawki zweryfikowane bezpośrednio (hash+weryfikacja hasła, encode+decode JWT) przed dalszą
implementacją.

## Co zostało zrobione

1. **Model `app_user`** (`app/modules/users/models.py` + migracja `099794a318bb`) — `id` (uuid),
   `email` (unikalny, login), `hashed_password`, `rola` (string, nie enum bazodanowy — nowa rola to
   tylko nowa wartość, bez migracji), `magazyny_dostepne` (JSONB `list[str]`), `active` (bool).
   Nazwa tabeli `app_user`, nie `user` — `user` jest zarezerwowanym słowem w Postgresie.
2. **`security.py`** — `hash_password`/`verify_password` (bcrypt przez passlib),
   `create_access_token`/`create_refresh_token`/`decode_token` (JWT, HS256). Token niesie `sub`
   (user id) i `type` (`access`/`refresh` — token jednego typu nie działa jako drugi, sprawdzone
   testem). **Rola NIE jest ufana z tokenu** — `get_current_user` zawsze doczytuje świeży rekord z
   bazy, więc zmiana roli/dezaktywacja konta działa natychmiast, nie dopiero po wygaśnięciu tokenu.
3. **`repository.py`** (users) — `create_user`, `get_user_by_email`, `get_user_by_id`.
4. **RBAC** (`deps.py`) — `get_current_user` (401 przy braku/nieważnym tokenie),
   `require_admin` (403 gdy `rola != "admin"`).
5. **Router `/auth`** — `POST /auth/token` (logowanie, `OAuth2PasswordRequestForm` — działa też z
   przyciskiem "Authorize" w Swagger UI na `/docs`), `POST /auth/refresh`, `GET /auth/me`.
6. **Ochrona istniejących endpointów**:
   - `GET /products`, `GET /products/{kod}` — wymaga zalogowania (dowolna rola),
   - `POST`/`PUT`/`DELETE /products` — wymaga roli `admin`,
   - `POST /match` — wymaga zalogowania; parametr `magazyn` sprawdzany przeciw
     `magazyny_dostepne` użytkownika (`_check_magazyn_access` w `main.py`) — `admin` bez
     ograniczeń, `elektryk` dostaje 403 przy magazynie spoza swojej listy. Porównanie przez
     `magazyn_key()` (wcześniej prywatne `_magazyn_key` w matcherze, teraz publiczne i
     reużywane) — ta sama normalizacja co przy R5 (case-insensitive, "Zabrze"/"Czekanów").
7. **`scripts/create_admin.py`** — CLI bootstrapping (`--email`, `--password`, `--rola`,
   powtarzalne `--magazyn`), idempotentny (duplikat e-maila → komunikat, nie wyjątek).
   Zweryfikowany na lokalnej bazie dev.
8. **Naprawiony utajony błąd testowy** (z Etapu 2/3): `Base.metadata.create_all()` w
   `tests/conftest.py` polegało na przypadkowym imporcie modeli ORM przez inne pliki testowe
   (zadziałało dotąd, bo zawsze coś inne w zbiorze testów akurat importowało `products.models`/
   `matcher.models`). Uruchomienie samego `test_auth.py` ujawniło to: `app_user` nie istniało w
   bazie testowej. **Naprawa**: `conftest.py` jawnie importuje wszystkie moduły `models.py`
   (matcher, products, users) przed `create_all()`, niezależnie od tego, co pytest akurat zbiera.
9. **20 nowych testów** (`test_auth.py`, 14 + aktualizacja `test_products_api.py` o nagłówki
   autoryzacji): logowanie (sukces/złe hasło/nieistniejący user), `/auth/me` (z tokenem/bez),
   refresh (poprawny/odrzucenie access-jako-refresh), RBAC zapisu (`admin` ok / `elektryk` 403),
   RBAC magazynu (`elektryk` ograniczony do `Zabrze`, `admin` bez ograniczeń), `/match` bez tokenu
   → 401. **Wszystkie testy: 53/53 zielone** (39 z Etapów 1-4 + 14 nowych w `test_auth.py`).
10. Zweryfikowano end-to-end na realnym lokalnym Postgresie: login → `/auth/me` → CRUD bez tokenu
    (401) → CRUD z tokenem admina (201) → refresh → odrzucenie access-tokenu jako refresh (401).

## Decyzje projektowe wymagające odnotowania

- **`magazyny_dostepne` jako `list[str]` (JSONB), nie `uuid[]`** — ERD z Etapu 0 sugerował tablicę
  UUID (odnoszącą się do encji `Warehouse`), ale taka encja nigdzie w projekcie nie istnieje —
  `magazyn` jest wszędzie zwykłym stringiem (`WarehouseVariantModel.magazyn`, parametr `magazyn` w
  `/match`, `magazyn_key()` w matcherze). Wprowadzenie pełnej encji `Warehouse` teraz byłoby
  przedwczesną abstrakcją bez realnej korzyści (SOLID/DDD "tam gdzie daje korzyść, nie na siłę" —
  `CLAUDE.md`, zasada 9). Jeśli magazyny doczekają się własnych atrybutów (adres, dział, itd.),
  będzie to naturalny moment na wydzielenie encji — nie teraz.
- **Refresh token bez rewokacji/blacklisty** — stateless JWT, ważny do wygaśnięcia (7 dni) nawet po
  "wylogowaniu" (którego zresztą nie ma jako endpointu — nie było proszone). Świadomy uproszczony
  MVP; odnotowane jako ryzyko niżej.
- **`rola` jako wolny string, nie enum w bazie** — zgodnie z odpowiedzią użytkownika: kolejne role
  (`hydraulik` itd. przy Etapie 8+) to tylko nowa wartość w danych, zero zmian w kodzie/migracjach.
- **Naprawa `cffi`/`bcrypt`** — patrz sekcja wyżej, to nie była opcja projektowa tylko wymagana
  naprawa, żeby cokolwiek z tego etapu w ogóle działało.

## Co zostało świadomie odłożone (i dlaczego)

| Nieprzeniesione jeszcze | Uwaga | Plan |
|---|---|---|
| CRUD `/users` (zarządzanie kontami przez API) | Nie proszone w tym etapie — bootstrapping przez skrypt wystarcza na teraz | Gdy pojawi się realna potrzeba (np. UI administracyjne we froncie) |
| Rewokacja/blacklista refresh tokenów, endpoint `/auth/logout` | Patrz „Decyzje projektowe” wyżej | Gdy stanie się realnym wymaganiem (np. Redis, już w stacku) |
| Encja `Warehouse` jako pełnoprawny model | Patrz „Decyzje projektowe” wyżej | Gdy magazyny zyskają własne atrybuty |
| Rate limiting logowania / blokada po nieudanych próbach | Nie proszone, standardowe dla produkcji ale poza zakresem tego etapu | Etap poświęcony twardnieniu bezpieczeństwa, jeśli będzie potrzebny |
| Model `USER` z ERD miał tylko `email`/`rola`/`magazyny_dostepne` — bez `created_at` itp. | Minimalny zakres, YAGNI | Dodać gdy pojawi się realna potrzeba (audyt, itp.) |

## Ryzyka

1. **`JWT_SECRET_KEY` ma wartość domyślną w kodzie** (`app/core/config.py`) — bezpieczna tylko do
   dewelopmentu lokalnego. **Przed jakimkolwiek wdrożeniem poza laptopem trzeba ustawić zmienną
   środowiskową `JWT_SECRET_KEY`** na losowy, długi sekret — inaczej każdy zna sekret z repo.
2. **Brak rewokacji refresh tokenów** — skradziony/przechwycony refresh token działa do
   naturalnego wygaśnięcia (7 dni), nie da się go unieważnić wcześniej. Akceptowalne dla obecnej
   skali (mały zespół, brak dotychczas żadnego auth), ale do rozważenia przy realnym wdrożeniu.
3. **Brak ochrony przed brute-force logowania** (patrz „Co odłożone” wyżej).
4. **`passlib`+`bcrypt` to przypięta, znana-działająca, ale nie najnowsza kombinacja** —
   `passlib` jest nierozwijany; przy przyszłej aktualizacji `bcrypt` trzeba pamiętać, że podniesienie
   wersji może ponownie zepsuć hashowanie (patrz sekcja „Problem napotkany” wyżej). Do rozważenia
   w przyszłości: zamiana `passlib` na bezpośrednie użycie biblioteki `bcrypt` (bez pośrednika),
   jeśli `passlib` zacznie realnie przeszkadzać.

## Jak uruchomić

```bash
cd backend
pip install -r requirements.txt   # zawiera teraz tez cffi i przypiety bcrypt==4.0.1

alembic upgrade head
python -m scripts.import_catalog
python -m scripts.import_special_rules
python -m scripts.create_admin --email admin@przyklad.pl --password wybierz-mocne-haslo

pytest tests/ -v          # 53 testy, wszystkie zielone (wymaga TEST_DATABASE_URL, patrz conftest.py)

uvicorn app.main:app --reload   # /docs -> "Authorize" -> login adminem, testuj CRUD/match
```

Przykład logowania i użycia tokenu:
```bash
curl -X POST http://localhost:8000/auth/token \
  -d "username=admin@przyklad.pl&password=wybierz-mocne-haslo"
# -> {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}

curl http://localhost:8000/products -H "Authorization: Bearer <access_token>"
```

## Plan Etapu 6

Zgodnie z planem etapów z `docs/ETAP_0_analiza_architektury.md`:
1. Frontend React (upload, tabela weryfikacji, generowanie) — pierwszy etap dotykający UI.
2. Ewentualnie wcześniej: moduł OCR (Etap 4 z pierwotnego planu, wciąż nieprzeniesiony) jako
   Strategy + Celery async + MinIO — do ustalenia kolejność z użytkownikiem przy starcie etapu.
