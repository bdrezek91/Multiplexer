# Raport — twardnienie bezpieczeństwa logowania (blokada konta, rewokacja refresh tokenów)

Realizacja dwóch pozycji z tabeli "Co zostało świadomie odłożone" w `docs/RAPORT_ETAP_5.md`:
"Rate limiting logowania / blokada po nieudanych próbach" i "Rewokacja/blacklista refresh
tokenów, endpoint `/auth/logout`". Trzecia (TLS/HTTPS) nie wymagała zmian w kodzie — Caddy w
`docker-compose.prod.yml` już to obsługuje automatycznie (Let's Encrypt), wystarczy ustawić
`DOMAIN` w `.env` na realną domenę.

## Co zostało zrobione

### 1. Blokada konta po serii nieudanych logowań (`app/modules/users/lockout.py`)

Osobny mechanizm od istniejącego rate limitera per-IP (`app/core/rate_limit.py`, Etap "quick
winy", 5 prób/minutę) — ten sam Redis, nowy klucz. Rate limiter chroni przed jednym źródłem
requestów, nie przed rozproszonym atakiem na to samo konto z wielu adresów IP.

- 5 nieudanych prób logowania w oknie 15 minut blokuje logowanie na tym koncie na kolejne
  15 minut, niezależnie od adresu IP.
- Blokada sprawdzana w `POST /auth/token` **przed** odczytem użytkownika/weryfikacją hasła —
  zablokowane konto nie ujawnia nawet czy hasło było poprawne.
- Udane logowanie zeruje licznik.
- Fail-open przy niedostępności Redis (log ostrzeżenia, logowanie działa dalej) — spójne z
  istniejącym wzorcem w `ocr/cooldown.py` (Redis jest już krytyczną infrastrukturą w tym stosie
  — rate limiter/Celery i tak by ucierpiały przy jego awarii).

### 2. Rewokacja refresh tokenów, `POST /auth/logout` (`app/modules/users/token_blacklist.py`)

- Każdy token JWT (access i refresh) ma teraz unikalny `jti` (`security.py`).
- Nowy endpoint `POST /auth/logout` (body jak `/auth/refresh`: `{"refresh_token": "..."}`)
  wpisuje `jti` refresh tokenu na blacklistę w Redis, z TTL równym pozostałemu czasowi ważności
  tokenu (nie ma sensu trzymać dłużej niż token i tak by żył).
- `POST /auth/refresh` sprawdza blacklistę i odrzuca unieważniony token (`401`).
- Endpoint jest celowo idempotentny — nieprawidłowy/już wygasły token nie zwraca błędu (`204`
  zawsze), bo frontend i tak kasuje tokeny lokalnie niezależnie od wyniku.
- **Tylko refresh tokeny są rewokowane** — access token żyje krótko (domyślnie 30 min,
  `settings.access_token_expire_minutes`) i pozostaje ważny do naturalnego wygaśnięcia po
  wylogowaniu. Rewokacja access tokenów wymagałaby odpytywania Redis przy każdym żądaniu API
  chronionym przez `get_current_user`, nie tylko przy odświeżaniu — świadomy kompromis.

### Frontend

- `api/auth.ts`: `logout()` jest teraz asynchroniczny — czyści lokalne tokeny od razu (tak jak
  wcześniej), a w tle (best-effort, błędy sieci ignorowane) woła `POST /auth/logout`.
- `auth/AuthContext.tsx`: wywołanie `apiLogout()` opakowane w `void` (fire-and-forget, UI nie
  czeka na odpowiedź sieci przy wylogowaniu).

## Testy

- `tests/test_auth_lockout.py` (nowy, 4 testy) — jednostkowe testy `RedisLoginLockoutStore` na
  fałszywym Redisie (`_FakeRedis`, ten sam wzorzec co `test_ocr_cooldown.py`): próg 5 prób,
  reset, izolacja per-konto.
- `tests/test_auth.py` (+7 testów): blokada konta niezależna od rate limitera per-IP (test
  resetuje limiter po każdej próbie, żeby izolować mechanizm), zerowanie licznika po sukcesie,
  `/auth/logout` unieważnia token, idempotencja przy nieprawidłowym tokenie, wylogowanie jednej
  sesji nie psuje innej (dwa niezależne loginy tego samego użytkownika).
- `tests/conftest.py`: nowy autouse fixture `_reset_login_lockout` zerujący stan blokady dla
  `admin@test.local`/`magazynier@test.local` przed każdym testem — bez tego test symulujący 5
  nieudanych prób zablokowałby te konta na 15 minut dla całej reszty suity testowej (ten sam
  problem i rozwiązanie co istniejący `_reset_rate_limiter`).
- **Pełna suita: 327 → 336 testów backendu, zero regresji.** Frontend: `tsc -b` bez błędów,
  `oxlint` bez nowych ostrzeżeń, `vitest` 38/38 bez zmian.

## Co zostało świadomie odłożone

| Nieprzeniesione jeszcze | Uwaga | Plan |
|---|---|---|
| Rewokacja access tokenów | Wymagałoby odpytywania Redis przy każdym żądaniu API, nie tylko odświeżaniu — koszt wydajnościowy nieproporcjonalny do 30-minutowego okna ryzyka | Do rozważenia, jeśli okno 30 min okaże się realnym problemem |
| Wylogowanie ze wszystkich urządzeń naraz ("wyloguj wszędzie") | Wymagałoby osobnej listy aktywnych `jti` per użytkownik (nie tylko blacklisty pojedynczych tokenów) | Gdy pojawi się realna potrzeba |
| Konfigurowalny próg/czas blokady (obecnie stałe w kodzie: 5 prób / 15 min) | Zgodnie z konwencją reszty projektu (patrz stałe w `ocr/cooldown.py`) — nie przez `settings`, żeby nie rozrastać `.env` bez potrzeby | Przenieść do `settings`, jeśli operacyjnie zajdzie potrzeba zmiany bez redeployu |

## Jak zweryfikować

```bash
cd backend
pytest tests/test_auth.py tests/test_auth_lockout.py -v
pytest tests/ -q   # 336 testow, 1 pominiety
```

```bash
cd frontend
npx tsc -b && npm run lint && npx vitest run
```
