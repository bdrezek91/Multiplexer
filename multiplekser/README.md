# Multiplekser v1.0.0

Wewnętrzne narzędzie firmy **Dampol Investment**, które zamienia ręczne, papierowe wydawki
materiałowe (elektryka, hydraulika) w gotowy plik importowy do **Comarch Optima** — bez
przepisywania pozycji z ręki.

## Do czego to służy

Elektrycy i hydraulicy na budowie wypełniają papierową wydawkę (albo skan/zdjęcie/Excel) z
listą zużytych/wydanych materiałów. Ktoś musiał to później ręcznie przepisać do Optimy —
żmudne i podatne na literówki w kodach. Multiplekser robi to automatycznie:

1. **Upload** — użytkownik wgrywa zdjęcie/skan/PDF wydawki (opcjonalnie wskazując magazyn).
2. **Rozpoznanie (OCR przez AI, Gemini)** — system **sam wykrywa, czy to wydawka Elektryki czy
   Hydrauliki** (dwuetapowa klasyfikacja) i odczytuje pozycje wraz z ilościami.
3. **Dopasowanie do katalogu** — każda rozpoznana nazwa jest dopasowywana do konkretnego kodu
   produktu w Optimie (aliasy, atrybuty typu kolor/kraj/przekrój/moc, reguły specjalne
   wypracowane na realnych błędach produkcyjnych, warianty zależne od magazynu).
4. **Weryfikacja** — użytkownik widzi tabelę rozpoznanych pozycji z jakością dopasowania,
   poprawia ręcznie to, co niepewne, wybiera magazyn i którą kolumnę ilości traktować jako
   finalną (wydana/zużyta).
5. **Generowanie** — jeden przycisk tworzy plik w formacie gotowym do importu w Optimie
   (`kod;ilość;;jm;magazyn`, kodowanie CP1250).

Całość jest **wielodziałowa i wieloużytkownikowa**: role `admin` i `magazynier`, osobne katalogi
produktów per dział (Elektryka, Hydraulika — kolejne działy nie są planowane), pełna historia
dokumentów oraz panel administracyjny katalogu i użytkowników. Obie role mogą pracować na obu
magazynach; `magazyny_dostepne` pozostaje metadanym profilu i nie ogranicza dostępu.

To migracja jednoplikowego prototypu HTML/JS (`Multiplekser_Elektryka.html`) do architektury
webowej klasy produkcyjnej — logika biznesowa (parser/matcher/generator) przeniesiona 1:1,
zweryfikowana testami regresyjnymi na realnych przypadkach z produkcji, nie przepisana od zera.

Zobacz `docs/ETAP_0_analiza_architektury.md` (analiza + plan + diagramy Mermaid) i najnowszy
`docs/RAPORT_ETAP_HYDRAULIKA_6.md` (co zrobione, co odłożone, jak uruchomić, plan kolejnego
kroku) oraz `CLAUDE.md` (pełny, aktualny stan projektu i podjęte decyzje architektoniczne).

Szybki start (przez Docker - pelny stos, wymaga Dockera):
```bash
docker compose up
docker compose exec backend python -m scripts.import_catalog
docker compose exec backend python -m scripts.import_special_rules
docker compose exec backend python -m scripts.create_admin --email admin@przyklad.pl --password wybierz-mocne-haslo
```

Szybki start (lokalnie, bez Dockera - wymaga wlasnego Postgres/Redis/MinIO):
```bash
cd backend
pip install -r requirements.txt
alembic upgrade head                    # utworz tabele w Postgresie (DATABASE_URL w .env lub domyslny localhost)
python -m scripts.import_catalog        # zaimportuj katalog z tests/fixtures/baza_elektryka.json
python -m scripts.import_special_rules  # zaimportuj reguly specjalne (R3/R6/OCR overrides/wykluczenia)
python -m scripts.create_admin --email admin@przyklad.pl --password wybierz-mocne-haslo
pytest tests/ -v                        # wymaga tez bazy testowej, patrz TEST_DATABASE_URL w tests/conftest.py

redis-server &
celery -A app.core.celery_app worker --loglevel=info &
uvicorn app.main:app --reload
```

Frontend (od Etapu 8, wymaga dzialajacego backendu na :8000):
```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
npm run test  # Vitest
```

API: `/auth/token` (logowanie, od Etapu 5, chronione rate limitem per-IP i blokada konta po 5
nieudanych probach - patrz `docs/RAPORT_BEZPIECZENSTWO_1.md`), `/auth/logout` (uniewaznia refresh
token), `/match` (dopasowanie, wymaga zalogowania), pelny CRUD
`/products` (od Etapu 4, zapis tylko rola admin), `/documents` (upload skanu + async OCR przez
Celery, od Etapu 7 - `POST` zwraca 202 natychmiast, `GET /documents/{id}` do odpytania statusu i
wyniku), `PATCH /documents/{id}/items/{item_id}` (weryfikacja ilosci/kodu przed generowaniem, od
Etapu 9), `POST /documents/{id}/generate` (eksport do formatu Optima, TXT/CP1250, od Etapu 9),
`/users` (CRUD uzytkownikow + reset hasla, admin-only, od Etapu 11), dokumentacja interaktywna z
przyciskiem "Authorize" na `/docs`.

**Produkcja** (od Etapu 10) — osobny stos `docker-compose.prod.yml` (bez `--reload`/bind-mountu,
bez wystawionych na zewnatrz portow baz danych, jeden publiczny wpis - `caddy`, ktory
automatycznie wystawia darmowy certyfikat HTTPS gdy podasz domene, i reverse-proxuje do `web`
(Nginx: statyczny frontend + `/api/` do backendu pod tym samym originem), patrz
`docs/RAPORT_ETAP_10.md`):

```bash
cd multiplekser
cp .env.prod.example .env   # uzupelnij sekrety - patrz komentarze w pliku (WYMAGANE: haslo
                             # Postgresa, dane MinIO, JWT_SECRET_KEY - `openssl rand -hex 32`)
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend python -m scripts.import_catalog
docker compose -f docker-compose.prod.yml exec backend python -m scripts.import_special_rules
docker compose -f docker-compose.prod.yml exec backend python -m scripts.create_admin --email admin@przyklad.pl --password wybierz-mocne-haslo
```

Ustaw tez `GEMINI_API_KEY_FREE`/`GEMINI_API_KEY_PAID` (Google AI Studio) w `.env` - bez nich
dokumenty koncza sie statusem `error`. **Nigdy nie wpisuj tych kluczy do kodu/repo** - patrz
`docs/RAPORT_ETAP_6.md`, zastrzezenie bezpieczenstwa (klucze zaszyte w starym `index.html`).
Plik `.env` jest w `.gitignore` (sekrety) - `.env.prod.example` to tylko szablon bez wartosci.

Opcjonalnie ustaw tez `OPENAI_API_KEY` (platform.openai.com) - ostatni krok w lancuchu OCR
(patrz `backend/app/modules/ocr/chain.py`), uzywany WYLACZNIE gdy wszystkie kroki Gemini
zawioda (limit/awaria). Bez tego klucza ten krok jest po prostu pomijany, dokumenty dzialaja
normalnie na samym Gemini.

**Wlasny VPS (serwer w chmurze)** — skrocona sciezka od zera do dzialajacej, publicznej strony:

1. Zaloz serwer (Ubuntu 22.04/24.04) u dowolnego dostawcy (np. Hetzner CX22, DigitalOcean) - zapisz
   jego publiczny adres IP.
2. (Opcjonalnie, ale zalecane) kup domene i dodaj rekord DNS `A` wskazujacy na ten adres IP.
3. Zaloguj sie po SSH na serwer i zainstaluj Dockera:
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
4. Sklonuj repozytorium (potrzebny dostep do repo - np. `git clone` z tokenem albo przez SSH):
   ```bash
   git clone <url-repo>
   cd <repo>/multiplekser
   ```
5. Dalej dokladnie jak wyzej (`cp .env.prod.example .env`, uzupelnij sekrety - **w `DOMAIN` wpisz
   swoja domene z kroku 2, jesli ja masz**, `docker compose -f docker-compose.prod.yml up -d
   --build`, import katalogu/regul, `create_admin`).
6. Otworz `http://<adres-IP>/` (albo `https://twojadomena.pl/` jesli ustawiles `DOMAIN` - Caddy
   samo zalatwia certyfikat, moze to potrwac do minuty przy pierwszym starcie).

Kolejne zmiany w kodzie (po `git push` na branch) wdraza sie na serwerze przez:
```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build   # przebudowuje tylko zmienione uslugi
```
