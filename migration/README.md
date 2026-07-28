# Multiplekser Elektryka — migracja do architektury Enterprise SaaS

Zobacz `docs/ETAP_0_analiza_architektury.md` (analiza + plan + diagramy Mermaid) i najnowszy
`docs/RAPORT_ETAP_9.md` (co zrobione, co odłożone, jak uruchomić, plan kolejnego etapu).

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

API: `/auth/token` (logowanie, od Etapu 5), `/match` (dopasowanie, wymaga zalogowania), pelny CRUD
`/products` (od Etapu 4, zapis tylko rola admin), `/documents` (upload skanu + async OCR przez
Celery, od Etapu 7 - `POST` zwraca 202 natychmiast, `GET /documents/{id}` do odpytania statusu i
wyniku), `PATCH /documents/{id}/items/{item_id}` (weryfikacja ilosci/kodu przed generowaniem, od
Etapu 9), `POST /documents/{id}/generate` (eksport do formatu Optima, TXT/CP1250, od Etapu 9),
dokumentacja interaktywna z przyciskiem "Authorize" na `/docs`.

**Produkcja**: ustaw zmienna srodowiskowa `JWT_SECRET_KEY` na losowy, dlugi sekret - wartosc
domyslna w kodzie jest tylko do dewelopmentu lokalnego (patrz `docs/RAPORT_ETAP_5.md`, ryzyka).
Ustaw tez `GEMINI_API_KEY_FREE`/`GEMINI_API_KEY_PAID` (Google AI Studio) - bez nich dokumenty
koncza sie statusem `error`. **Nigdy nie wpisuj tych kluczy do kodu/repo** - patrz
`docs/RAPORT_ETAP_6.md`, zastrzezenie bezpieczenstwa (klucze zaszyte w starym `index.html`).
Ustaw `MINIO_ENDPOINT_URL`/`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` dla storage plikow (domyslne
wartosci pasuja do `docker-compose.yml`).
