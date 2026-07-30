# Raport — Multiplekser Portable: wersja .exe na Windows (bez Dockera)

Na życzenie: wersja aplikacji, którą można pobrać jako pojedynczy plik `.exe` i uruchomić na
Windows bez Dockera, Postgresa, Redis, MinIO ani terminala. Decyzje potwierdzone wcześniej z
użytkownikiem: SQLite zamiast Postgresa (nie wbudowany prawdziwy Postgres), .exe budowany na
`windows-latest` w GitHub Actions (ten sandbox nie ma dostępu do Windows do kompilacji).

## Zasada: zero zmian w logice biznesowej

Cały kod parsera/matchera/generatora/OCR jest **dokładnie ten sam** co w wersji Docker. Zmieniły
się wyłącznie trzy warstwy infrastrukturalne, każda przełączana jedną flagą `settings.desktop_mode`
(domyślnie `False` - zero wpływu na istniejące wdrożenie):

| Warstwa | Docker/produkcja | Portable |
|---|---|---|
| Baza danych | PostgreSQL | SQLite (plik obok .exe) |
| Storage plików | MinIO/S3 | folder na dysku (`LocalFileStorage`) |
| Kolejka OCR | Celery + Redis | wątek w tym samym procesie |

## Co zostało zrobione

### Typy kolumn przenośne między Postgresem a SQLite
`sqlalchemy.dialects.postgresql.UUID`/`JSONB` zastąpione w 4 modelach (`documents`, `matcher`,
`products`, `users`) generycznymi `sqlalchemy.Uuid` (natywnie cross-dialect od SQLAlchemy 2.0) i
`PortableJSON` (`app/core/db_types.py`: `JSON().with_variant(JSONB(), "postgresql")` - JSONB na
Postgresie bez zmian, zwykły JSON gdzie indziej). **Zweryfikowane, że DDL na Postgresie jest
bajt-w-bajt identyczne jak przed zmianą** (ten sam `UUID`/`JSONB` w wygenerowanym `CREATE TABLE`)
- żadna nowa migracja Alembic dla istniejących wdrożeń Docker nie jest potrzebna.

### `app/core/db.py`
`check_same_thread=False` w `connect_args`, włączane automatycznie gdy `DATABASE_URL` zaczyna się
od `sqlite` (rozpoznanie po URL, nie po fladze - odporne niezależnie od trybu).

### `LocalFileStorage` (`documents/storage.py`)
Implementuje istniejący interfejs `FileStorage` (Strategy z Etapu 7) - zapis/odczyt z folderu na
dysku, z tworzeniem podfolderów z klucza (`documents/{uuid}/plik.jpg` - S3 nie ma prawdziwych
katalogów, lokalny system plików potrzebuje `mkdir -p`, znaleziony i naprawiony przy weryfikacji).
`get_storage()` wybiera ją zamiast `S3FileStorage` gdy `settings.desktop_mode`.

### `dispatch_ocr_task` (`documents/tasks.py`)
Nowa funkcja - jedyne miejsce, przez które router zleca przetwarzanie dokumentu (zastąpiła
bezpośrednie `process_ocr_document.delay()`). W trybie desktop odpala `run_ocr_task` (ta sama,
niezmieniona, testowana od Etapu 7 funkcja) na wątku w tym samym procesie; w trybie
Docker/produkcyjnym - bez zmian, Celery jak dotąd.

### `desktop_main.py` - punkt wejścia
- Dane (SQLite, wgrane dokumenty, `config.json`) trzymane **obok pliku .exe** (`dane/`), nie w
  AppData - żeby aplikacja była faktycznie przenośna (cały folder można skopiować/przenieść).
- Pierwsze uruchomienie: proste okno `tkinter` (biblioteka standardowa, zero dodatkowej
  zależności) zbiera e-mail/hasło admina i klucz Gemini - bez terminala, bez edycji plików.
  Generuje losowy `JWT_SECRET_KEY` samodzielnie.
- Bootstrap pierwszego uruchomienia woła **te same, już istniejące funkcje** co ścieżka Docker
  (`scripts.import_catalog`, `scripts.import_special_rules`, `users.repository.create_user`) -
  bezpośrednio, bez CLI - importuje oba katalogi (Elektryka+Hydraulika) i reguły specjalne.
- `/api/*` → istniejący `app.main.app` zamontowany jako pod-aplikacja (dokładnie ta sama zasada
  co `location /api/` w `nginx.conf` z Etapu 10 - strip prefiksu i przekazanie dalej), `/*` →
  zbudowany frontend (`SPAStaticFiles` - fallback na `index.html` dla tras React Router, ten sam
  mechanizm co `try_files $uri $uri/ /index.html` w Nginx, tylko po stronie Pythona).
- Po starcie serwera (wątek uvicorn) otwiera domyślną przeglądarkę na `http://127.0.0.1:8765`.

### Pakowanie (`multiplekser_portable.spec`, `requirements-portable.txt`)
PyInstaller, tryb `--onefile` (jeden plik do pobrania). Napotkane i rozwiązane realne problemy
pakowania (nie tylko teoretyczne):
1. Runtime hook PyInstallera dla `pkg_resources` łamie się przy nowszym `setuptools` (≥70) -
   `ModuleNotFoundError: backports` / `ImportError: platformdirs` **przy starcie exe**, mimo że
   sam build przechodzi bez błędu - znany problem ekosystemu. Fix: `setuptools<70` w środowisku
   budowania (`requirements-portable.txt`), zero wpływu na kod aplikacji.
2. Celery dynamicznie importuje własne podmoduły (`celery.fixups` i inne) przez `importlib` -
   niewidoczne dla statycznej analizy PyInstallera. Fix: `collect_submodules()` (nie pełne
   `collect_all()`, które ponownie ciągnęłoby metadane przez `pkg_resources`).

### GitHub Actions (`.github/workflows/build-portable.yml`)
`windows-latest` - buduje frontend, instaluje `requirements-portable.txt`, **odpala testy
desktopowe na prawdziwym Windowsie**, buduje `.exe`, wystawia jako artifact (każde uruchomienie
ręczne) i jako GitHub Release (tag `portable-v*`).

## Weryfikacja

- **Pełna suita backendu na Postgresie: 234 → 252 testów (18 nowych), zero regresji.**
- **`tests/test_portable_desktop.py`** (10 testów): round-trip UUID/JSON przez wszystkie 4
  moduły na prawdziwym pliku SQLite (nie tylko sprawdzenie DDL), `ilike` na SQLite,
  `LocalFileStorage` (w tym podfoldery z klucza), `dispatch_ocr_task` faktycznie przełącza się
  między wątkiem a Celery zależnie od `desktop_mode`.
- **`tests/test_desktop_main.py`** (8 testów): config na dysku (round-trip, czytelny JSON do
  ręcznej edycji), generowanie `JWT_SECRET_KEY`, `apply_env`, rozwiązywanie ścieżek zasobów.
  Świadomie POZA zakresem: samo okno `tkinter` i `main()` (wymagają GUI/prawdziwego startu -
  patrz niżej).
- **Dymny test pełnego przepływu** (poza pytest, osobny proces - żeby nie kolidować z globalnym
  stanem `settings` reszty suity): bootstrap świeżej bazy SQLite + oba katalogi, logowanie,
  `/api/products` dla obu działów, `/` serwuje frontend, fallback SPA dla tras React Router,
  **prawdziwy upload dokumentu przez `/api/documents` → wątek w tle → status `error`** (brak
  klucza Gemini w teście - oczekiwane, potwierdza że cała ścieżka storage+dispatch+baza działa).
- **Zbudowano faktyczny plik wykonywalny PyInstallerem w tym sandboksie** (wersja linuksowa ELF,
  nie `.exe` - Linux nie umie skompilować Windows) i **uruchomiono go jako osobny proces**:
  realny serwer wstał, odpowiedział na `/api/health` przez prawdziwe HTTP. To zweryfikowało cały
  graf zależności (FastAPI/uvicorn/SQLAlchemy/Pillow/Celery-jako-obiekt) faktycznie się pakuje i
  odpala - nie tylko teoretyczna analiza importów.

## Czego NIE dało się zweryfikować w tym środowisku

1. **Samo okno `tkinter` pierwszego uruchomienia** - ten sandbox (Linux, niestandardowy build
   Pythona) nie ma zbudowanego modułu `tkinter`; potwierdzone wprost (`ModuleNotFoundError` przy
   próbie importu, także w spakowanym exe). Kod używa wyłącznie standardowego, prostego API
   `tkinter`/`ttk` - ryzyko niskie, ale **wymaga realnego sprawdzenia na Windows** po pierwszym
   uruchomieniu workflow.
2. **Prawdziwy plik `.exe`** - budowany wyłącznie na `windows-latest` w CI (krok "Zbuduj .exe"),
   nigdy w tym sandboksie. Workflow odpala też testy desktopowe NA Windowsie przed budową, więc
   pierwsze uruchomienie samo wychwyci ewentualne różnice specyficzne dla Windows (ścieżki,
   uprawnienia, antywirus blokujący niepodpisany .exe - to ostatnie to znane ograniczenie
   niepodpisanych binarek PyInstallera, nie błąd w kodzie).
3. **Realny klucz Gemini** - jak w poprzednich krokach, poza zasięgiem tego środowiska.

## Jak zbudować / pobrać

```
GitHub → Actions → "Build Multiplekser Portable (Windows .exe)" → Run workflow
```
Po zakończeniu: artifact `Multiplekser-Portable-Windows` do pobrania z tej samej strony. Dla
stałego linku (Release) - wypchnij tag `portable-v1.0.0` (lub podobny).

Pierwsze uruchomienie `Multiplekser.exe`: okno z prośbą o e-mail/hasło administratora i klucz
Gemini API (Google AI Studio, darmowy poziom) → aplikacja sama się konfiguruje i otwiera
przeglądarkę. Kolejne uruchomienia - bez pytania, prosto do logowania.

## Co zostało świadomie odłożone

| Nieprzeniesione jeszcze | Uwaga | Plan |
|---|---|---|
| Aktualizacje schematu bazy dla istniejącej instalacji Portable | Świeży plik SQLite dostaje schemat wprost z aktualnych modeli (`Base.metadata.create_all`), bez śladu Alembic - dobre dla pierwszej instalacji, nie ma jeszcze historii migracji dla kolejnych wersji .exe | Gdy pojawi się pierwsza realna zmiana schematu po wydaniu Portable |
| Podpisywanie `.exe` (code signing) | Niepodpisany plik może być oznaczony przez Windows Defender/SmartScreen jako niezaufany | Certyfikat code-signing kosztuje i wymaga firmy/tożsamości - do rozważenia jeśli to realnie przeszkadza użytkownikom |
| Klucz Gemini płatny (`GEMINI_API_KEY_PAID`) w oknie startowym | Zebrany tylko darmowy klucz - można dopisać ręcznie do `dane/config.json` | Dodać drugie pole, jeśli okaże się potrzebne |

## Jak zweryfikować

```bash
cd backend
pytest tests/test_portable_desktop.py tests/test_desktop_main.py -v
pytest tests/ -q   # 252 testy, 1 pominiety (Postgres)
```
Faktyczny `.exe`: uruchom workflow `build-portable.yml` na GitHubie.
