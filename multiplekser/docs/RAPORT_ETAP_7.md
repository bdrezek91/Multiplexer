# Raport — Etap 7: Pipeline asynchroniczny (Celery + Redis) + storage plików (MinIO/S3)

Zakres uzgodniony z użytkownikiem przed startem: boto3 + moto (zamiast prawdziwego MinIO,
niedostępnego w tym środowisku), i **zastąpienie** synchronicznego `POST /ocr/recognize` z Etapu 6
nowym asynchronicznym `POST /documents`.

## Ograniczenie środowiska (zgłoszone przed startem)

Docker jest niedostępny w tym sandboxie (`docker ps` → brak demona), a serwer MinIO nie dał się
pobrać (proxy sieciowe blokuje `dl.min.io`). Zdecydowano: **boto3** jako klient (S3-kompatybilny —
działa bez zmian kodu z prawdziwym MinIO w `docker-compose.yml`, prawdziwym AWS S3 czy Azure Blob
przez S3 gateway) + **moto** do testów automatycznych. Do manualnej weryfikacji end-to-end w tym
sandboxie doinstalowano `moto[server]` (prawdziwy serwer HTTP emulujący S3, w przeciwieństwie do
`moto.mock_aws()` który działa tylko w obrębie jednego procesu Python — nie wystarczyłby do
sprawdzenia komunikacji między osobnym procesem API a osobnym procesem workera Celery).

## Co zostało zrobione

1. **`app/modules/documents/storage.py`** — `FileStorage` (interfejs) + `S3FileStorage` (boto3).
   `get_storage()` bez cache'owania w pamięci procesu (ta sama zasada co `Catalog.from_db()`/
   `get_db()` od Etapu 4) — dodatkowa korzyść: pozwala testom użyć `moto` bez ryzyka, że zwrócony
   zostanie wcześniej skonstruowany, prawdziwy klient.
2. **Modele `Document`/`DocumentItem`** (`app/modules/documents/models.py` + migracja
   `9de150ab780e`) — wg ERD z Etapu 0, z udokumentowanymi rozszerzeniami: `file_key`/`mime`/
   `original_filename` (storage), `magazyn` (audytowalność parametru dopasowania),
   `used_provider`/`rejected_count`/`error_message` (diagnostyka), `needs_review`/`form_note`/
   `uwagi`/`confidence` (dane z pipeline'u OCR z Etapu 6, inaczej ciche odrzucone przy zapisie),
   `match_kod`/`match_nazwa`/`match_jm` **zdenormalizowane** obok `matched_product_id` (FK) — wynik
   OCR to zapis historyczny „co dopasowaliśmy W TYM MOMENCIE”; poleganie wyłącznie na joinie przez
   FK oznaczałoby, że późniejsza edycja/usunięcie produktu w katalogu cicho zmienia treść już
   zakończonego dokumentu.
3. **`app/core/celery_app.py`** — konfiguracja Celery (broker+backend Redis, JSON serializacja).
4. **`app/modules/documents/tasks.py`** — `run_ocr_task(document_id, session)` jako **czysta
   funkcja** (bez brokera/DB własnego) reużywająca cały pipeline z Etapu 6 (`recognize_document`,
   `downscale_image`, Matcher), zapisująca wynik do `DocumentItem` (status `queued`→`processing`→
   `done`/`error`). `process_ocr_document` (zarejestrowany `@celery_app.task`) to **cienki
   wrapper** — otwiera własną sesję DB i deleguje dalej. Rozdzielenie „co robi zadanie” od „jak
   Celery je uruchamia” — ta sama zasada co `scripts/import_*.py` (logika oddzielona od CLI).
5. **`POST /documents`** (multipart: `plik`, opcjonalny `magazyn`) — upload do storage → wiersz
   `Document` (`status="queued"`) → `process_ocr_document.delay(...)` → **202** natychmiast (bez
   czekania na OCR). **`GET /documents/{id}`** — status + wynik (właściciel dokumentu lub admin,
   inni dostają 403). **`GET /documents`** — lista (nie-admin widzi tylko swoje). RBAC magazynu
   reużywa `check_magazyn_access` z Etapu 6 (ta sama reguła co `/match`).
6. **Usunięto** stary synchroniczny `/ocr/recognize` (`ocr/router.py`, `ocr/schemas.py`,
   `tests/test_ocr_api.py`) — logika pipeline'u (`ocr/pipeline.py`, `chain.py`, `providers.py`,
   `parsing.py`, `form_rows.py`) **pozostaje bez zmian**, teraz wywoływana z `tasks.py` zamiast
   bezpośrednio z routera.
7. **`docker-compose.yml`** — dodano serwis `minio` (image `minio/minio`, healthcheck) i serwis
   `worker` (ten sam obraz co `backend`, `command: celery -A app.core.celery_app worker`).
8. **26 nowych testów automatycznych** (`test_documents_storage.py`, `test_documents_task.py`,
   `test_documents_api.py`) — logika `run_ocr_task` testowana bezpośrednio na `db_session` (bez
   brokera), osobny lekki test potwierdza, że `process_ocr_document` poprawnie deleguje (wiring),
   testy API z `process_ocr_document.delay` zamockowanym (kontrakt HTTP, RBAC właściciela/
   magazynu), testy `S3FileStorage` na `moto.mock_aws()`. **Wszystkie testy: 101 zielonych + 1
   pominięty** (90 z Etapów 1-6 + 26 nowych, minus 15 usuniętych wraz ze starym `/ocr/recognize`).
9. **Manualna weryfikacja end-to-end z prawdziwym Redis i prawdziwym, OSOBNYM procesem workera**
   (opisana szczegółowo niżej) — złapała i pozwoliła naprawić realny błąd przed wypchnięciem kodu.

## Błąd znaleziony podczas manualnej weryfikacji (i naprawiony)

Uruchomiono lokalnie: `redis-server` (port 6380), `moto[server]` jako prawdziwy serwer HTTP
(emulacja S3/MinIO, port 9123 — w przeciwieństwie do `mock_aws()` używanego w testach
automatycznych, ten serwer jest osiągalny przez sieć z dowolnego procesu), `uvicorn` (API) i
**osobny proces** `celery worker`, każdy jako niezależny proces systemowy.

Pierwsza próba (`POST /documents` → worker przetwarza) zakończyła się błędem w workerze:
`NoReferencedTableError: Foreign key associated with column 'document.user_id' could not find
table 'app_user'`. Przyczyna: proces workera importuje tylko `app.core.celery_app` →
`app.modules.documents` (przez `autodiscover_tasks`) — nigdy `app.modules.users.models`, więc
SQLAlchemy nie mogło rozwiązać string-owego FK `ForeignKey("app_user.id")` przy pierwszej operacji
ORM w tym procesie. **Dokładnie ten sam rodzaj błędu**, naprawiony raz w `tests/conftest.py`
(Etap 5) dla procesu testowego — tym razem w procesie workera, który ma inny, mniejszy zestaw
importów niż proces API (`main.py` importuje pośrednio wszystko przez routery).

**Naprawa**: `app/core/celery_app.py` jawnie importuje wszystkie moduły `models.py` (matcher,
products, users, documents) przed konfiguracją Celery — tak samo jak `alembic/env.py` i
`tests/conftest.py`. Po naprawie: restart workera, ponowny upload → **pełny, poprawny przepływ**:
API przyjęło plik, wysłało go realną siecią HTTP do serwera S3-kompatybilnego, zapisało wiersz
`Document`, zleciło zadanie przez prawdziwy Redis; **osobny proces** workera odebrał zadanie,
pobrał plik przez HTTP z tego samego storage, wykonał 4 prawdziwe zapytania HTTP do Google Gemini
API (z celowo nieprawidłowym kluczem — poprawnie odrzucone jako `400 API_KEY_INVALID`), poprawnie
przeszedł całym łańcuchem fallback (4 próby na kluczu darmowym, 5. krok pominięty jako „brak
klucza” płatnego), i zapisał `status="error"` z pełną treścią błędu z powrotem do Postgresa —
odczytane poprawnie przez `GET /documents/{id}` z osobnego żądania HTTP. Środowisko testowe
(procesy, testowy użytkownik, dokument) posprzątane po weryfikacji.

## Decyzje projektowe wymagające odnotowania

- **Brak globalnego cache dla `get_storage()`** — świadoma kontynuacja zasady z Etapu 4
  (`Catalog.from_db()`/`get_db()` per-request zamiast singletona w pamięci procesu).
- **Oryginalny plik przechowywany bez zmian w storage; skalowanie (`downscale_image`) dzieje się
  dopiero przy przetwarzaniu** (w `run_ocr_task`, tuż przed wysłaniem do Gemini) — zachowuje pełną
  wierność zapisanego dokumentu źródłowego (audyt), zgodnie z tym jak downscaling działał w
  monolicie (operacja tuż przed wysyłką do AI, nie część „zapisu” niczego).
- **Brak wyniku Celery jako źródła prawdy o statusie** — `Document.status` w Postgresie jest
  jedynym źródłem prawdy (worker aktualizuje go bezpośrednio); backend Redis skonfigurowany, ale
  endpoint `GET /documents/{id}` nigdy go nie odpytuje — unika dwóch równoległych systemów
  śledzenia stanu.
- **`match_kod`/`match_nazwa`/`match_jm` zdenormalizowane** — patrz uzasadnienie w sekcji modeli
  wyżej.

## Co zostało świadomie odłożone (i dlaczego)

| Nieprzeniesione jeszcze | Uwaga | Plan |
|---|---|---|
| Prawdziwy serwis MinIO (uruchomiony w `docker-compose.yml`, nie zweryfikowany w tym sandboxie) | Docker niedostępny tutaj | Do zweryfikowania w środowisku z Dockerem (`docker compose up`) |
| Endpoint do pobrania oryginalnego pliku (`GET /documents/{id}/file`) | Nie proszone w tym etapie | Gdy pojawi się potrzeba (np. podgląd skanu we froncie) |
| Retry/dead-letter dla zadań Celery, które padły z przyczyn przejściowych (np. chwilowy brak sieci) | MVP - błąd zapisuje się jako `status="error"`, ponowna próba wymaga nowego uploadu | Do rozważenia gdy pojawi się realna potrzeba (Celery ma wbudowane mechanizmy retry) |
| Frontend React | Kolejny naturalny krok wg planu Etapu 0 | **Następny etap** |

## Ryzyka

1. **MinIO w `docker-compose.yml` nie zostało uruchomione naprawdę w tej sesji** (brak Dockera) —
   kod jest poprawny i przetestowany wobec S3-kompatybilnego API (moto wiernie emuluje kontrakt
   S3), ale finalna weryfikacja z prawdziwym MinIO powinna nastąpić w środowisku z Dockerem.
2. **Brak retry dla przejściowych błędów w `run_ocr_task`** — patrz „Co odłożone” wyżej.
3. Ryzyka z poprzednich etapów (sekret `JWT_SECRET_KEY`/klucze Gemini tylko w zmiennych
   środowiskowych, brak CI z Postgresem) pozostają aktualne, bez zmian.

## Jak uruchomić

Przez Docker (pełny stos, wymaga Dockera):
```bash
docker compose up
docker compose exec backend python -m scripts.import_catalog
docker compose exec backend python -m scripts.import_special_rules
docker compose exec backend python -m scripts.create_admin --email admin@przyklad.pl --password ...
```

Lokalnie (jak dotychczas w tej sesji, bez Dockera):
```bash
cd backend
pip install -r requirements.txt   # dochodza boto3, moto

alembic upgrade head
python -m scripts.import_catalog
python -m scripts.import_special_rules
python -m scripts.create_admin --email admin@przyklad.pl --password ...

pytest tests/ -v   # 101 testow zielonych + 1 pominiety (wymaga TEST_DATABASE_URL)

# Do realnego przetwarzania trzeba Redis + MinIO (lub S3-kompatybilny odpowiednik) + worker:
redis-server --port 6379 &
celery -A app.core.celery_app worker --loglevel=info &
uvicorn app.main:app --reload
```

Przykład:
```bash
curl -X POST http://localhost:8000/documents \
  -H "Authorization: Bearer <access_token>" \
  -F "plik=@skan.jpg" -F "magazyn=Zabrze"
# -> 202 {"id": "...", "status": "queued"}

curl http://localhost:8000/documents/<id> -H "Authorization: Bearer <access_token>"
```

## Plan kolejnego etapu

Frontend React (upload, tabela weryfikacji, generowanie) — zgodnie z planem etapów z Etapu 0,
teraz gdy backend ma pełny asynchroniczny przepływ OCR z trwałością wyniku.
